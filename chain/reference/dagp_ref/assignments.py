"""Committed-pool, future-beacon task assignments. MODULE is a trusted keeper capability.
Native deployment must verify an unbiasable beacon; simulation bytes are not such a proof.
"""
from dataclasses import dataclass,asdict
from math import ceil
from .crypto_sim import H,hx
from .roles import Actor,Role
from .sortition import panel_size
from .treasury import RuleViolation

KINDS={
    'review':(Role.VOTE_SUPERVISOR,'SUPERVISE_VOTE',2),
    'certification':(Role.EXAMINER,'GRADE',None),
    'admission':(Role.REGISTRAR,'REGISTRAR_ACT',1),
    'verification':(Role.VERIFIER,'VERIFY',3),
    'jury':(Role.JUROR,'JUDGE',5),
    'outcome':(Role.REVIEWER,'REVIEW',3),
    'executor':(Role.EXECUTOR,'BID',3),
    'admin_review':(Role.ADMIN,'ADMIN_VOTE',5),
}

@dataclass(frozen=True)
class FrozenTask:
    kind:str
    task:str
    subjects:tuple
    operators:tuple
    pool:tuple  # immutable (agent, operator, family) triples
    round:int
    height:int
    count:int
    commitment:str

@dataclass(frozen=True)
class Assignment:
    commitment:str
    round:int
    members:tuple
    digest:str

class TaskAssignments:
    def __init__(self,chain,registry):
        if not isinstance(chain,str) or not chain or getattr(registry,'assignments',None) is not None:
            raise RuleViolation('unique assignment registry and chain required')
        self.chain,self.reg=chain,registry
        self._tasks={};self._results={};self._beacons={};self._events=[]
        self._cancelled={};self._cancellations=[]
        self._round=0;self._height=0
        registry.assignments=self
    def _module(self,actor):
        if type(actor) is not Actor or actor.kind!='MODULE':raise RuleViolation('assignment keeper only')
    def _time(self,height):
        if type(height) is not int or height<self._height:raise RuleViolation('backdated assignment clock')
    def _operators(self,subjects):
        operators={self.reg.get(a).operator for a in subjects}
        # Exclude the subjects' entire political party, not only their own identity.
        parties=getattr(self.reg,'party_registry',None)
        if parties is not None:
            for a in subjects:
                party=parties._party.get(a)
                if party is not None:
                    operators.update(self.reg.get(m).operator for m in parties._members[party])
        return operators

    def freeze(self,actor,kind,task,subjects,round,height):
        self._module(actor);self._time(height)
        if (type(kind) is not str or kind not in KINDS or not isinstance(task,str) or not 0<len(task)<=256
                or type(round) is not int or round!=self._round+1 or (kind,task) in self._tasks):
            raise RuleViolation('unique task and next unrevealed beacon round required')
        if type(subjects) not in (tuple,list,set,frozenset) or any(type(a) is not str for a in subjects):
            raise RuleViolation("typed task subjects required")
        subjects=tuple(sorted(set(subjects)))
        if not subjects:raise RuleViolation('task subjects required')
        operators=self._operators(subjects)
        # Earlier stages of the same process cannot subsequently judge their own work.
        for (prior_kind,prior_task),result in self._results.items():
            if prior_task==task and prior_kind!=kind:
                operators.update(self.reg.get(a).operator for a in result.members)
        if any(t.kind==kind and set(t.operators)&operators and (t.kind,t.task) not in self._results and (t.kind,t.task) not in self._cancelled
               for t in self._tasks.values()):
            raise RuleViolation('subject already has a committed outstanding task')
        role,action,count=KINDS[kind]
        if count is None:count=panel_size(self.reg.p.assumed_bad_bps,self.reg.p.board_fail_den)
        if kind=='review':count=max(count,self.reg.p.review_supervisors)
        matter={'operators_involved':operators}
        recent=[e for e in self._events if height-30*self.reg.p.protection_day_blocks<e[0]]
        pair_counts={}
        for _,event_kind,subject,op in recent:
            if event_kind==kind and subject in operators:
                pair_counts[subject,op]=pair_counts.get((subject,op),0)+1
        blocked_operators={op for (_,op),count in pair_counts.items() if count>=2}
        pool=tuple((a,self.reg.get(a).operator,self.reg.get(a).family)
                   for a in self.reg.agents_with(role,height)
                   if self.reg.get(a).operator not in operators and self.reg.can(a,action,height,matter)[0]
                   and self.reg.get(a).operator not in blocked_operators)
        if len({op for _,op,_ in pool})<count:raise RuleViolation('insufficient independent task pool')
        commitment=hx('assignment-pool-v1',self.chain,kind,task,subjects,sorted(operators),pool,round,height,count)
        frozen=FrozenTask(kind,task,subjects,tuple(sorted(operators)),pool,round,height,count,commitment)
        self._tasks[kind,task]=frozen;self._height=height
        self.reg._log(height,actor,'ASSIGNMENT_FROZEN',task,commitment)
        return frozen
    def publish_beacon(self,actor,round,seed,height):
        self._module(actor);self._time(height)
        waiting=[t for t in self._tasks.values() if t.round==round]
        if (type(round) is not int or round!=self._round+1 or type(seed) is not bytes or len(seed)!=32
                or not waiting or any(height<=t.height for t in waiting)):
            raise RuleViolation('future committed beacon required')
        self._beacons[round]=(seed,height);self._round=round;self._height=height
        self.reg._log(height,actor,'ASSIGNMENT_BEACON',str(round),seed.hex())
    def assign(self,actor,kind,task,height):
        self._module(actor);self._time(height)
        if type(kind) is not str or type(task) is not str:raise RuleViolation("typed task domain required")
        key=(kind,task)
        if key in self._cancelled:raise RuleViolation("assignment permanently cancelled")
        if key not in self._tasks:raise RuleViolation('unknown assignment task')
        if key in self._results:return self._results[key]
        frozen=self._tasks[key]
        if frozen.round not in self._beacons:raise RuleViolation('beacon has not arrived')
        seed,beacon_height=self._beacons[frozen.round]
        if height<beacon_height:raise RuleViolation('assignment precedes beacon')
        role,action,_=KINDS[kind]
        recent=[e for e in self._events if height-30*self.reg.p.protection_day_blocks<e[0]]
        conflicts=set(frozen.operators)|self._operators(frozen.subjects)
        ranked=sorted(frozen.pool,key=lambda c:(H('assignment-operator-rank-v1',self.chain,seed,frozen.commitment,c[1]),
                                              H('assignment-agent-rank-v1',seed,frozen.commitment,c[0]),c))
        selected=[];operators=set();families={}
        for agent,op,family in ranked:
            if op in operators or families.get(family,0)>=ceil(frozen.count/2):continue
            selected.append(agent);operators.add(op);families[family]=families.get(family,0)+1
            if len(selected)==frozen.count:break
        if len(selected)!=frozen.count:raise RuleViolation('independent pool exhausted; no owner-selected fallback')
        members=tuple(selected)
        for agent in members:
            identity=self.reg.get(agent)
            if ((agent,identity.operator,identity.family) not in frozen.pool
                    or identity.operator in conflicts or not self.reg.can(agent,action,height,
                        {'operators_involved':conflicts})[0]):
                raise RuleViolation('selected worker unavailable; no post-beacon substitution')
        result=Assignment(frozen.commitment,frozen.round,members,hx('assignment-result-v1',frozen.commitment,seed,members))
        self._results[key]=result;self._height=height
        self._events=recent+[(height,kind,subject,op) for subject in frozen.operators for op in operators]
        self.reg._log(height,actor,'TASK_ASSIGNED',task,result.digest)
        return result
    def snapshot(self,kind,task):
        if type(kind) is not str or type(task) is not str or (kind,task) not in self._tasks:
            raise RuleViolation('known typed task required')
        frozen=self._tasks[kind,task];result=self._results.get((kind,task))
        beacon=self._beacons.get(frozen.round)
        return dict(frozen=asdict(frozen),result=asdict(result) if result else None,
                    beacon=dict(round=frozen.round,seed=beacon[0].hex(),height=beacon[1]) if beacon else None,
                    cancelled_evidence=self._cancelled.get((kind,task)))

    def cancel(self,actor,kind,task,height,evidence):
        self._time(height)
        if type(kind) is not str or type(task) is not str:raise RuleViolation("typed task domain required")
        key=(kind,task);frozen=self._tasks.get(key)
        if (frozen is None or key in self._cancelled or height<frozen.height+2*self.reg.p.protection_day_blocks
                or not isinstance(evidence,str) or len(evidence)!=64
                or any(c not in '0123456789abcdef' for c in evidence)):
            raise RuleViolation('delayed public cancellation evidence required')
        self.reg._authorize(actor,{'VOTE'},height,'ASSIGNMENT_CANCEL',frozen.commitment)
        recent=[e for e in self._cancellations if height-30*self.reg.p.protection_day_blocks<e[0]]
        if (any(set(e[1])&set(frozen.operators) for e in recent)
                or sum(height-self.reg.p.protection_day_blocks<e[0] for e in recent)>=5):
            raise RuleViolation('cancellation budget exhausted')
        self.reg._spend(actor);self._cancelled[key]=evidence;self._height=height
        self._cancellations=recent+[(height,frozen.operators)]
        self.reg._log(height,actor,'ASSIGNMENT_CANCELLED',task,frozen.commitment+':'+evidence)

    def require(self,chain,kind,task,members,height,subjects):
        self._time(height)
        if (type(kind) is not str or type(task) is not str or type(members) not in (tuple,list)
                or type(subjects) not in (tuple,list,set,frozenset) or any(type(a) is not str for a in subjects)):
            raise RuleViolation("typed assignment receipt context required")
        frozen=self._tasks.get((kind,task));result=self._results.get((kind,task))
        if (chain!=self.chain or (kind,task) in self._cancelled or frozen is None or result is None or tuple(members)!=result.members
                or tuple(sorted(set(subjects)))!=frozen.subjects):
            raise RuleViolation('matching committed task assignment required')
        if height<self._beacons[result.round][1]:raise RuleViolation('assignment not yet effective')
        _,action,_=KINDS[kind]
        conflicts=set(frozen.operators)|self._operators(frozen.subjects)
        for a in result.members:
            identity=self.reg.get(a)
            if ((a,identity.operator,identity.family) not in frozen.pool or identity.operator in conflicts
                    or not self.reg.can(a,action,height,{'operators_involved':conflicts})[0]):
                raise RuleViolation('assigned worker is no longer eligible')
        return result

def require_assignment(registry,chain,kind,task,members,height,subjects):
    if getattr(registry.p,'_historical_assignments',False):return
    service=getattr(registry,'assignments',None)
    if service is None:raise RuleViolation('task assignment registry required')
    return service.require(chain,kind,task,members,height,subjects)
