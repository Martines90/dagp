"""Signed party discussion and supervised refinements before a proposal vote opens."""
import copy
from dataclasses import asdict,dataclass
import json
from .crypto_sim import H,hx
from .proposal import Envelope,amendment_is_refinement
from .roles import Role,Actor
from .session import Effects,VoteSession,snapshot_electorate
from .tally import Kind
from .treasury import RuleViolation,CreditLedger,_integer

@dataclass(frozen=True)
class Milestone:
    label: str
    amount: int
    acceptance: str

@dataclass(frozen=True)
class BillPoint:
    point_id: str
    text: str
    budget: int = 0
    milestones: tuple = ()
    requires: tuple = ()

@dataclass(frozen=True)
class VotingDraft:
    title: str
    goal: str
    result: str
    body: str
    envelope: Envelope
    budget: int = 0
    milestones: tuple = ()
    points: tuple = ()
    parameter_changes: tuple = ()

    def digest(self):
        return hx('voting-draft-v1',json.dumps(asdict(self),sort_keys=True,separators=(',',':')))

class ProposalReview:
    def __init__(self,chain,issue,owner,party,parties,supervisors,draft,registry,keyring,
                 open_height,review_end,credits=None):
        if (not isinstance(chain,str) or not chain or not isinstance(issue,str) or not issue
                or type(open_height) is not int or type(review_end) is not int
                or not 0<=open_height<review_end):raise RuleViolation('invalid review domain/windows')
        self.chain,self.issue,self.owner,self.party=chain,issue,owner,party
        self.reg,self.kr=registry,keyring;self._rules=registry.p.snapshot_hash()
        self.open_height,self.review_end=open_height,review_end
        self._parties={p:frozenset(members) for p,members in parties.items()}
        members=[a for group in self._parties.values() for a in group]
        if len(set(members))!=len(members):raise RuleViolation('one party membership per discussion participant')
        self._supervisors=tuple(supervisors)
        if owner not in self._parties.get(party,()) or not registry.can(owner,'SUBMIT_PROPOSAL',open_height)[0]:
            raise RuleViolation('owner is not an authorized member of proposing party')
        self._original=copy.deepcopy(draft);self._validate(draft)
        if (len(set(self._supervisors))!=len(self._supervisors)
                or len(self._supervisors)<registry.p.review_supervisors
                or len({registry.get(a).operator for a in self._supervisors})!=len(self._supervisors)):
            raise RuleViolation('insufficient distinct supervisor operators')
        for a in self._supervisors:self._supervisor(a,open_height)
        self._draft=copy.deepcopy(draft);self._version=1;self._approvals={}
        self._comments=[];self._history=[];self._amendments=[];self._height=open_height
        self._changed=open_height;self._locked=None;self._opened=False
        self._credits=credits
        if credits is not None and type(credits) is not CreditLedger:raise RuleViolation('credit ledger required')
        self._credit_month=credits.month if credits is not None else None
        if credits is not None:
            _integer(registry.p.proposal_cost,1)
            credits.spend(party,registry.p.proposal_cost)

    def _validate(self,draft):
        if type(draft) is not VotingDraft:raise RuleViolation('typed voting draft required')
        for text in (draft.title,draft.goal,draft.result,draft.body):
            if not isinstance(text,str) or not 0<len(text)<=16384:raise RuleViolation('draft text outside bounds')
        if (type(draft.envelope) is not Envelope or type(draft.envelope.caps) is not tuple
                or any(type(pair) is not tuple or len(pair)!=2 for pair in draft.envelope.caps)
                or not amendment_is_refinement(draft.envelope,draft.envelope)):
            raise RuleViolation('malformed envelope')
        if (draft.envelope.objective_hash!=hx('goal',draft.goal)
                or draft.envelope.result_hash!=hx('result',draft.result)):
            raise RuleViolation('goal/result commitments do not match content')
        if type(draft.budget) is not int or draft.budget<0 or type(draft.milestones) is not tuple or len(draft.milestones)>32:
            raise RuleViolation('invalid budget or milestones')
        if draft.budget>dict(draft.envelope.caps).get('treasury',0):raise RuleViolation('budget exceeds treasury cap')
        labels=set();total=0
        for m in draft.milestones:
            if (type(m) is not Milestone or not isinstance(m.label,str) or not 0<len(m.label)<=128
                    or m.label in labels or type(m.amount) is not int or m.amount<=0
                    or not isinstance(m.acceptance,str) or not 0<len(m.acceptance)<=4096):
                raise RuleViolation('invalid milestone')
            labels.add(m.label);total+=m.amount
        if total!=draft.budget or (draft.budget>0 and not draft.milestones):raise RuleViolation('milestones must sum to budget')
        if type(draft.points) is not tuple or len(draft.points)>self.reg.p.max_bill_points:
            raise RuleViolation('invalid bill points')
        if draft.parameter_changes:
            from .policy import validate_changes
            validate_changes(self.reg.p,draft.parameter_changes)
            if draft.points or draft.budget:raise RuleViolation('parameter referendums are atomic and unfunded')
        if draft.points:
            if any(type(p) is not BillPoint for p in draft.points):raise RuleViolation("typed bill points required")
            ids=tuple(p.point_id for p in draft.points)
            if any(type(q) is not str or not 0<len(q)<=128 for q in ids):raise RuleViolation('invalid bill point ID')
            if len(set(ids))!=len(ids):raise RuleViolation('duplicate bill point')
            for point in draft.points:
                if (type(point) is not BillPoint or not isinstance(point.point_id,str) or not 0<len(point.point_id)<=128
                        or not isinstance(point.text,str) or not 0<len(point.text)<=4096
                        or type(point.budget) is not int or point.budget<0 or type(point.requires) is not tuple
                        or any(type(q) is not str or q not in ids or q==point.point_id for q in point.requires)
                        or len(set(point.requires))!=len(point.requires)
                        or type(point.milestones) is not tuple or any(type(m) is not Milestone for m in point.milestones)
                        or sum(m.amount for m in point.milestones)!=point.budget):
                    raise RuleViolation('invalid point budget/dependencies')
            if sum(p.budget for p in draft.points)!=draft.budget or tuple(m for p in draft.points for m in p.milestones)!=draft.milestones:
                raise RuleViolation('point budgets must partition overall milestones')
            deps={p.point_id:p.requires for p in draft.points}
            visited=set()
            def visit(q,path):
                if q in path:raise RuleViolation('cyclic point dependencies')
                if q in visited:return
                for other in deps[q]:visit(other,path|{q})
                visited.add(q)
            for q in ids:visit(q,set())


    def _time(self,height,editing=True):
        if type(height) is not int or height<self._height or self.reg.p.snapshot_hash()!=self._rules:
            raise RuleViolation('invalid/backdated height or changed rules')
        if self._locked is not None:raise RuleViolation('review record is locked')
        if editing and not self.open_height<=height<self.review_end:raise RuleViolation('review window closed')

    def _owner(self,agent,height):
        if agent!=self.owner or not self.reg.can(agent,'SUBMIT_PROPOSAL',height)[0]:raise RuleViolation('proposing owner only')

    def _supervisor(self,agent,height):
        conflicts={self.reg.get(a).operator for a in self._parties[self.party]}
        if (agent not in self._supervisors or not self.reg.can(agent,'SUPERVISE_VOTE',height)[0]
                or self.reg.get(agent).operator in conflicts):raise RuleViolation('supervisor unauthorized or conflicted')

    def _signature(self,agent,message,signature):
        if not isinstance(signature,str) or not self.kr.verify(agent,message,signature):raise RuleViolation('invalid signature')

    def comment_message(self,agent,party,text,parent,nonce):
        return H(b'proposal-comment-v1',self.chain,self.issue,self._version,self._draft.digest(),agent,party,text,parent,nonce)

    def comment(self,agent,party,text,parent,nonce,height,signature):
        self._time(height)
        if (agent not in self._parties.get(party,()) or not self.reg.can(agent,'POST_ARTICLE',height)[0]
                or not isinstance(text,str) or not 0<len(text)<=4096
                or not isinstance(nonce,str) or not 0<len(nonce)<=128 or len(self._comments)>=200
                or sum(c['agent']==agent for c in self._comments)>=20
                or sum(c['party']==party for c in self._comments)>=max(1,200//len(self._parties))):
            raise RuleViolation('invalid party comment')
        if parent is not None and (type(parent) is not int or not 0<=parent<len(self._comments)):
            raise RuleViolation('unknown parent comment')
        if any(c['agent']==agent and c['nonce']==nonce for c in self._comments):raise RuleViolation('comment replay')
        self._signature(agent,self.comment_message(agent,party,text,parent,nonce),signature)
        self._comments.append(dict(agent=agent,party=party,text=text,parent=parent,nonce=nonce,height=height,version=self._version,record_hash=self._draft.digest(),signature=signature))
        self._height=height;self.reg._log(height,Actor.agent(agent),'REVIEW_COMMENT',self.issue,str(len(self._comments)-1))
        return len(self._comments)-1

    def amendment_message(self,draft,nonce):
        return H(b'proposal-amend-v1',self.chain,self.issue,self._version+1,draft.digest(),nonce)

    def amend(self,agent,draft,nonce,height,signature):
        self._time(height);self._owner(agent,height);self._validate(draft)
        if self._version>=20:raise RuleViolation("review version limit reached")
        if not isinstance(nonce,str) or not 0<len(nonce)<=128:raise RuleViolation('amendment nonce required')
        if not amendment_is_refinement(self._original.envelope,draft.envelope):
            raise RuleViolation('material change requires a fresh proposal')
        if not amendment_is_refinement(self._draft.envelope,draft.envelope) or draft.budget>self._draft.budget:
            raise RuleViolation('approved/pending caps and budget cannot increase')
        if tuple(p.point_id for p in draft.points)!=tuple(p.point_id for p in self._original.points):
            raise RuleViolation('point identity changes require a new proposal')
        if any(new.budget>old.budget for old,new in zip(self._draft.points,draft.points)):
            raise RuleViolation('point budgets cannot increase')
        self._signature(agent,self.amendment_message(draft,nonce),signature)
        self._history.append(dict(version=self._version,draft=self._draft,approvals=copy.deepcopy(self._approvals)))
        self._amendments.append(dict(version=self._version+1,record_hash=draft.digest(),nonce=nonce,height=height,signature=signature))
        self._draft=copy.deepcopy(draft);self._version+=1;self._approvals={};self._changed=height;self._height=height
        self.reg._log(height,Actor.agent(agent),'REVIEW_AMENDMENT',self.issue,self._draft.digest())

    def approval_message(self):
        return H(b'proposal-review-approve-v1',self.chain,self.issue,self._version,self._draft.digest(),self._rules)

    def approve(self,supervisor,note,height,signature):
        self._time(height);self._supervisor(supervisor,height)
        if supervisor in self._approvals or not isinstance(note,str) or not 0<len(note)<=1024:
            raise RuleViolation('duplicate approval or missing semantic assessment')
        self._signature(supervisor,H(self.approval_message(),note),signature)
        self._approvals[supervisor]=dict(note=note,height=height,signature=signature)
        self._height=height;self.reg._log(height,Actor.agent(supervisor),'REVIEW_APPROVED',self.issue,self._draft.digest())

    def lock_message(self):
        return H(b"proposal-review-lock-v1",self.chain,self.issue,self._version,self._draft.digest(),self._rules)

    def lock(self,agent,height,signature):
        self._time(height,editing=False);self._owner(agent,height)
        self._signature(agent,self.lock_message(),signature)
        if height<max(self.review_end,self._changed+self.reg.p.review_notice_blocks):raise RuleViolation('review/notice window incomplete')
        operators=set()
        for a in self._approvals:
            try:self._supervisor(a,height)
            except RuleViolation:continue
            operators.add(self.reg.get(a).operator)
        if len(operators)<self.reg.p.review_supervisors:raise RuleViolation('insufficient independent supervisor approvals')
        self._locked=copy.deepcopy(self._draft);self._height=height
        self.reg._log(height,Actor.agent(agent),'REVIEW_LOCKED',self.issue,self._locked.digest())
        return copy.deepcopy(self._locked)

    def open_vote(self,treasury=None,**session_args):
        if self._locked is None or self._opened:raise RuleViolation('lock record once before vote')
        if self.reg.p.snapshot_hash()!=self._rules:raise RuleViolation('review rules changed')
        if self._locked.budget and treasury is None:raise RuleViolation('common treasury required')
        if session_args.get('open_height',-1)<self._height:raise RuleViolation('vote predates locked review')
        forbidden={'issue','p','registry','keyring','effects','recused','approved_record_hash','electorate_root','electorate_size','credits','point_ids','point_dependencies','parameter_changes'}
        if forbidden & session_args.keys():raise RuleViolation('cannot override reviewed proposal effects')
        if session_args['bank'].issue_id!=self.issue or session_args['board'].issue!=self.issue:
            raise RuleViolation('examination or certification board belongs to another issue')
        if bool(self._locked.parameter_changes)!=(session_args.get('kind') is Kind.PARAMETER):
            raise RuleViolation('parameter changes require parameter referendum rules')
        if session_args.get('kind') not in tuple(Kind):raise RuleViolation('proposal review cannot open an election')
        effects=Effects(treasury,self._credits,self.issue,self._locked.budget,
                        [m.amount for m in self._locked.milestones],self.party,self._locked.milestones,
                        self._credit_month,tuple(p.budget for p in self._locked.points),
                        tuple(tuple(m.amount for m in p.milestones) for p in self._locked.points),
                        tuple(p.milestones for p in self._locked.points))
        electorate=snapshot_electorate(self.reg,session_args['open_height'],
                                       set(self._parties[self.party])|set(session_args['board'].members))
        session=VoteSession(issue=self.issue,p=self.reg.p,registry=self.reg,keyring=self.kr,
                            electorate_root=electorate.root,electorate_size=electorate.size,
                            recused=self._parties[self.party],effects=effects,
                            approved_record_hash=self._locked.digest(),
                            point_ids=tuple(p.point_id for p in self._locked.points),
                            point_dependencies=tuple(p.requires for p in self._locked.points),
                            parameter_changes=self._locked.parameter_changes,**session_args)
        session.electorate=electorate
        self._opened=True
        return session

    def snapshot(self):
        return copy.deepcopy(dict(version=self._version,draft=self._draft,comments=self._comments,
                                  approvals=self._approvals,history=self._history,amendments=self._amendments,locked=self._locked))
