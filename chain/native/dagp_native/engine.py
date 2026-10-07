"""Authenticated consensus adapter. MODULE/COURT/VOTE capabilities are never user args.

The Go ABCI host verifies real Ed25519 envelopes and BLS beacon proofs. Each
receipt below records an already-authenticated action; it is not a cryptographic
signature or a secret simulation key. The adapter selects the exact signed
protocol message and never gives users raw object/method access.
"""
from dataclasses import asdict,replace
import json
import re
from dagp_ref.params import Params
from dagp_ref.crypto_sim import H,hx,MerkleTree
from dagp_ref.roles import Actor,Role,Status,Identity,RoleRegistry,SENSITIVE_OFFICES
from dagp_ref.assignments import TaskAssignments,KINDS
from dagp_ref.parties import PartyRegistry,PreElection
from dagp_ref.election import valid_ballot
from dagp_ref.campaign import Campaign,Program
from dagp_ref.comprehension import (Question,QuestionBank,AttemptRegistry,Submission,Board,
                                   evaluate,majority)
from dagp_ref.session import VoteSession,Windows,Phase,ELECTION,snapshot_electorate
from dagp_ref.review import ProposalReview,VotingDraft,Milestone,BillPoint
from dagp_ref.proposal import Envelope
from dagp_ref.treasury import Treasury,CreditLedger,RuleViolation
from dagp_ref.policy import ParameterGovernance,MonthlyCredits
from dagp_ref.tally import Kind,Outcome
from dagp_ref.payments import MilestonePayments,MilestoneApproval
from dagp_ref.societies import SocietyTree
from dagp_ref.admin import AdminCouncil

M=Actor('MODULE','native-keeper')


def fields(value,required,optional=()):
    if type(value) is not dict or set(value)-set(required)-set(optional) or set(required)-set(value):
        raise RuleViolation('exact typed message fields required')
    return value


def bounded(value,limit=128):
    if type(value) is not str or not 0<len(value)<=limit:
        raise RuleViolation('bounded nonempty string required')
    return value


def number(value,minimum=0,maximum=(1<<53)-1):
    if type(value) is not int or not minimum<=value<=maximum:
        raise RuleViolation('bounded integer required')
    return value


def pairs(value):
    if type(value) is not list or any(type(x) is not list or len(x)!=2 for x in value):
        raise RuleViolation('pair list required')
    return tuple(tuple(x) for x in value)


def bank(issue,value):
    fields(value,('questions','clusters'))
    if type(value['questions']) is not list or not 5<=len(value['questions'])<=256:
        raise RuleViolation('bounded committed question bank required')
    qs=[]
    for q in value['questions']:
        fields(q,('id','article','options','key_commit','prompt','choices','source_hash'))
        qs.append(Question(bounded(q['id']),bounded(q['article'],256),q['options'],
            bounded(q['key_commit'],64),bounded(q['prompt'],4096),tuple(q['choices']),q['source_hash']))
        if len(q['key_commit'])!=64 or any(c not in '0123456789abcdef' for c in q['key_commit']):
            raise RuleViolation('invalid answer commitment')
    if type(value['clusters']) is not dict or len(value['clusters'])>128:
        raise RuleViolation('bounded article cluster map required')
    for a,c in value['clusters'].items():bounded(a,256);bounded(c,256)
    return QuestionBank(issue,qs,value['clusters'])


def draft(value):
    fields(value,('title','goal','result','body','budget','milestones','points','parameters','caps'))
    def milestones(items):
        if type(items) is not list:raise RuleViolation('milestone list required')
        out=[]
        for m in items:
            fields(m,('label','amount','acceptance'));out.append(Milestone(**m))
        return tuple(out)
    points=[]
    for p in value['points']:
        fields(p,('id','text','budget','milestones','requires'))
        points.append(BillPoint(p['id'],p['text'],p['budget'],milestones(p['milestones']),tuple(p['requires'])))
    return VotingDraft(value['title'],value['goal'],value['result'],value['body'],
        Envelope(hx('goal',value['goal']),hx('result',value['result']),pairs(value['caps'])),
        value['budget'],milestones(value['milestones']),tuple(points),pairs(value['parameters']))


class Receipts:
    def __init__(self):
        self.proofs={};self.context='';self.signers=set()
    def attest(self,agent,message):
        receipt=hx('native-ed25519-receipt-v1',self.context,agent,message)
        self.proofs[agent,message.hex(),receipt]=True
        return receipt
    def sign(self,agent,message):
        if agent not in self.signers:raise RuleViolation('no authenticated grader authority')
        return self.attest(agent,message)
    def verify(self,agent,message,receipt):
        return type(receipt) is str and self.proofs.get((agent,message.hex(),receipt),False)
    def reset(self):
        self.context='';self.signers=set()


class World:
    def __init__(self,chain,now,charter,public_keys):
        fields(charter,('identities','common_budget','balances','beacon','root','constraints'),('bootstrap',))
        self.chain=chain;self.now=number(now,1,253402300799)
        self.params=Params(protection_day_blocks=86400,min_citizen_age=3*86400,
            campaign_min_blocks=7*86400,max_election_cycle_blocks=90*86400,
            review_notice_blocks=86400,challenge_window=2*86400,
            token_ttl=7*86400,party_suspend_max=30*86400,party_case_window=7*86400,
            rotation_delay=2*86400,recovery_delay=7*86400,admin_vote_window=86400,
            admin_containment_duration=6*3600,spam_freeze_max=86400,
            spam_freeze_cooldown=7*86400,liveness_period=365*86400)
        self.registry=RoleRegistry(self.params);self.receipts=Receipts()
        self.public_keys=dict(public_keys);self.wallets={k:number(v) for k,v in charter['balances'].items()}
        self.treasury=Treasury(number(charter['common_budget']))
        self.supply=self.treasury.free+sum(self.wallets.values())
        if set(charter['identities'])!=set(public_keys):raise RuleViolation('complete charter identity map required')
        for agent,record in sorted(charter['identities'].items()):
            fields(record,('operator','family','citizen_since','roles'))
            age=number(record['citizen_since'],1,now)
            roles={Role(r) for r in record['roles']}
            if Role.PARTY_MEMBER in roles or Role.VALIDATOR in roles:
                raise RuleViolation('political membership/consensus validators cannot be charter roles')
            if roles and Role.CITIZEN not in roles:raise RuleViolation('charter roles require citizenship')
            founding=bool(charter.get('bootstrap')) and agent==charter['bootstrap'].get('founder') and age==now
            if not founding and roles and now-age<3*86400:raise RuleViolation('citizenship warmup required at genesis')
            if not founding and roles&SENSITIVE_OFFICES and now-age<32*86400:raise RuleViolation('charter offices require mature tenure and activation')
            stake=self.params.examiner_stake if roles & {Role.EXAMINER,Role.VERIFIER,Role.REVIEWER,Role.EXECUTOR} else 0
            bond=self.params.citizen_bond
            self.debit(agent,bond+stake)
            identity=Identity(agent,bounded(record['operator']),bounded(record['family']),bond,age,
                status=Status.ACTIVE if roles else Status.PROBATION,roles=roles,stake=stake,
                activated=age,last_seen=now)
            self.registry.ids[agent]=identity
        self.assignments=TaskAssignments(chain,self.registry)
        self.parties=PartyRegistry(chain,self.registry,self.receipts)
        self.credits=CreditLedger();self.policy=ParameterGovernance(self.registry)
        self.monthly=MonthlyCredits(self.credits,self.registry)
        self.attempts=AttemptRegistry(self.params)
        self.tree=SocietyTree(chain,bounded(charter['root']),self.registry,self.receipts,
                              self.treasury,pairs(charter['constraints']))
        self.scoped={charter['root']:{'parties':self.parties,'credits':self.credits,'monthly':self.monthly}}
        self.payments=MilestonePayments(chain,self.registry,self.receipts,0)
        self.payments._treasury=self.treasury
        self.payments._emergency.tr=self.treasury
        self.council=None if charter.get('bootstrap') else AdminCouncil(chain,self.registry,self.receipts,now)
        self.beacon=charter['beacon'];self.rounds={};self.pending={};self.pre={};self.programs={};self.campaigns={}
        self.reviews={};self.sessions={};self.exam_submissions={};self.grades={};self.failed=set()
        self.milestone_approvals={};self.beneficiaries={};self.finished=set();self.court_cases={};self.tokens={};self.audit_votes={};self.role_consents={};self.role_decisions={}
        self.rotations={};self.guardians={};self.recoveries={};self.session_keys={}
        self.bootstrap=None
        if charter.get('bootstrap'):
            from .bootstrap import initialize
            initialize(self,charter['bootstrap'])
        self.assert_invariants()

    def debit(self,agent,amount):
        amount=number(amount)
        if self.wallets.get(agent,0)<amount:raise RuleViolation('insufficient spendable balance')
        self.wallets[agent]-=amount

    def assert_invariants(self):
        self.treasury.assert_invariants()
        if any(type(v) is not int or v<0 for v in self.wallets.values()):raise RuleViolation('wallet invariant')
        locked=sum(i.bond+i.stake for i in self.registry.ids.values())
        total=self.treasury.free+sum(self.treasury.reserved.values())+sum(self.treasury.escrow.values())+locked+sum(self.wallets.values())
        if total!=self.supply:raise RuleViolation('native monetary conservation')
        if not self.registry.verify_audit():raise RuleViolation('registry audit corruption')
        if len(self.registry.ids)>1024:raise RuleViolation('native pilot account bound')
        if len(set(self.public_keys.values()))!=len(self.public_keys):raise RuleViolation('duplicate identity key')
        if self.bootstrap:
            b=self.bootstrap
            if not 0<=b['spent']<=b['budget']<=6000:raise RuleViolation('fixed founding budget invariant')
            keys=[v['key'] for v in b['invites'].values() if self.now<v['expires']]
            if len(keys)!=len(set(keys)):raise RuleViolation('duplicate live invited key')

    def tick(self,now):
        if type(now) is not int or not self.now<=now<=253402300799:raise RuleViolation('consensus clock reversal')
        previous=self.registry.p
        self.now=now;self.policy.tick(now);self.params=self.registry.p
        self.registry.tick(now)
        for scope in self.scoped:
            if scope!=self.tree.root:self.tree.view(scope).tick(now)
        if previous!=self.registry.p:
            # ParameterGovernance's allowlist cannot change council/office rules.
            # Keep open cases and their roster version; only migrate the full hash.
            if self.council:self.council._rules_hash=self.registry.p.snapshot_hash()
        if self.council is None and len({self.registry.get(a).operator for a in self.registry.agents_with(Role.ADMIN,now)})>=5:
            self.council=AdminCouncil(self.chain,self.registry,self.receipts,now)
        self.session_keys={key:grant for key,grant in self.session_keys.items() if now<grant['expires']}
        for scope in self.scoped.values():
            if scope['monthly'].points is not None:scope['monthly'].tick(now)

    def sig(self,agent,message):return self.receipts.attest(agent,message)

    def scope(self,name):
        name=name or self.tree.root
        if name not in self.scoped:raise RuleViolation('inactive society scope')
        reg=self.registry if name==self.tree.root else self.tree.view(name)
        return reg,self.scoped[name]

    def parties_snapshot(self,parties):
        return {p:parties.members(p,self.now,True) for p in sorted(parties._members)}

    def task_service(self,kind,task):
        services=[self.assignments]+[self.tree.view(s).assignments for s in self.scoped if s!=self.tree.root]
        matches=[service for service in services if (kind,task) in service._tasks]
        if len(matches)!=1:raise RuleViolation('unique committed jurisdiction task required')
        return matches[0]

    def freeze(self,kind,task,subjects,registry=None):
        service=(registry or self.registry).assignments
        relative=service._round+1
        fields(self.beacon,('public_key','genesis_time','period','scheme'))
        if self.beacon['scheme']!='pedersen-bls-unchained':raise RuleViolation('unsupported beacon scheme')
        period=number(self.beacon['period'],1,86400);start=number(self.beacon['genesis_time'],1)
        absolute=max(1,(self.now-start)//period+2)
        key=relative if service is self.assignments else (service.reg.scope,relative)
        if key not in self.rounds:self.rounds[key]=absolute
        if start+(self.rounds[key]-1)*period<=self.now:raise RuleViolation('pending beacon round must be published before new pool freezes')
        service.freeze(M,kind,task,tuple(sorted(set(subjects))),relative,self.now)

    def members(self,kind,task):
        return self.task_service(kind,task).assign(M,kind,task,self.now).members

    def open_session(self,issue,reg,bank_value,windows,kind,mandate=None,campaign=None,review=None):
        if issue in self.sessions:raise RuleViolation('session already exists')
        b=bank(issue,bank_value);self.banks[issue]=b
        members=self.members('certification',issue);service=self.task_service('certification',issue);assignment=service._results['certification',issue]
        seed=service._beacons[assignment.round][0]
        w=Windows(*[number(x,self.now+1) for x in windows])
        if w.certify_end-w.vote_end<86400 or w.challenge_end-w.certify_end<2*86400:
            raise RuleViolation('certification and challenge minimum windows')
        board=Board('certification:'+issue,members,issue)
        conflicts=frozenset(campaign.member_operators) if campaign else frozenset()
        pool=[a for a in reg.agents_with(Role.EXAMINER,self.now) if reg.can(a,'GRADE',self.now,{'operators_involved':conflicts})[0]]
        kwargs=dict(kind=kind,board=board,bank=b,attempts=self.attempts,beacon=seed,
                    open_height=self.now,windows=w,pool=pool)
        if review:s=review.open_vote(treasury=None if reg is not self.registry else self.treasury,**kwargs)
        else:
            electorate=mandate.electorate if mandate else snapshot_electorate(reg,self.now)
            s=VoteSession(issue,p=reg.p,registry=reg,keyring=self.receipts,electorate_root=electorate.root,
                electorate_size=electorate.size,qualified_parties=list(campaign.pre_qualified) if campaign else None,
                campaign=campaign,institutional=mandate,approved_record_hash=mandate.payload if mandate else '',**kwargs)
            s.electorate=electorate
        self.sessions[issue]=s
        return s

    def execute(self,actor,operation,a,txid,verified=None):
        bounded(actor);bounded(operation);fields(a,()) if operation=='tick' else None
        if actor not in self.public_keys and operation not in ('identity.challenge','merger.claim'):raise RuleViolation('unknown authenticated actor')
        self.receipts.context=txid
        self.banks=getattr(self,'banks',{})
        out=self.dispatch(actor,operation,a,verified or {})
        self.transaction_receipts=getattr(self,'transaction_receipts',{})
        self.transaction_receipts[actor]={'txid':txid,'operation':operation,'time':self.now,'result':json.loads(json.dumps(out))}
        self.receipts.reset();self.assert_invariants()
        return out

    def dispatch(self,actor,op,a,verified):
        n=self.now
        from .bootstrap import seed,authorized,operate,registration
        if op.startswith('bootstrap.'):return operate(self,actor,op,a,verified)
        if seed(self) and not (op in {'tick','wallet.transfer','identity.challenge','identity.register','identity.heartbeat','identity.exit'} or op.startswith(('key.','party.','pre.','campaign.program'))):
            raise RuleViolation('ordinary governance requires irreversible founding graduation')
        if op=='tick':return {'time':n}
        if op=='wallet.transfer':
            fields(a,('to','amount'));to=bounded(a['to']);amount=number(a['amount'],1)
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',to) is None:raise RuleViolation('account identifier required')
            if to not in self.wallets:
                if len(self.wallets)>=1024 or amount<self.params.citizen_bond+1 or not (self.registry.can(actor,'VOTE',n)[0] or authorized(self,actor)):raise RuleViolation('bounded citizen-funded admission required')
                operator=self.registry.get(actor).operator
                events=[e for e in getattr(self,'funding_events',[]) if n-86400<e[0]]
                if len(events)>=40 or sum(e[1]==operator for e in events)>=5:raise RuleViolation('daily new-account sponsorship limit')
                self.funding_events=events+[(n,operator)]
            self.debit(actor,amount);self.wallets[to]=self.wallets.get(to,0)+amount;return {'transferred':amount}
        if op=='identity.challenge':
            fields(a,('key',))
            if seed(self):
                invitation=self.bootstrap['invites'].get(actor)
                if (self.now>=self.bootstrap['expires'] or invitation is None or self.now>=invitation['expires']
                    or a['key']!=invitation['key']):
                    raise RuleViolation('challenge must possess the live consensus-invited key')
            if actor in self.public_keys or not verified.get('registration_key'):raise RuleViolation('fresh key possession required')
            if len(self.public_keys)>=1024 or self.wallets.get(actor,0)<self.params.citizen_bond+1:raise RuleViolation('prefunded challenge and account capacity required')
            self.debit(actor,1);self.treasury.free+=1;self.treasury._initial_total+=1
            self.challenges=getattr(self,'challenges',{})
            challenge=hx('native-admission-challenge',self.chain,actor,verified['registration_key'],n,self.receipts.context)
            self.challenges[actor]=(challenge,n,n+86400)
            self.public_keys[actor]=verified['registration_key']
            return {'challenge':challenge,'expires':n+86400}
        if op=='identity.register':
            fields(a,('operator','family','key','challenge'))
            challenge=getattr(self,'challenges',{}).get(actor)
            if actor in self.registry.ids or challenge is None or a['challenge']!=challenge[0] or not challenge[1]<n<challenge[2] or a['key']!=self.public_keys[actor]:raise RuleViolation('live prior consensus challenge required')
            # Go signs the exact challenge-bound request; no fetch of agent-controlled URLs.
            bounded(a['challenge'],256);self.debit(actor,self.params.citizen_bond)
            if seed(self):
                self.wallets[actor]+=self.params.citizen_bond
                result=registration(self,actor,bounded(a['operator']),bounded(a['family']))
                del self.challenges[actor];return result
            self.registry.register(actor,bounded(a['operator']),bounded(a['family']),self.params.citizen_bond,n)
            del self.challenges[actor];self.freeze('admission',actor,(actor,))
            return {'status':'PROBATION','task':actor}
        if op=='identity.admit':
            fields(a,('target','accept','reason'));target=bounded(a['target']);members=self.members('admission',target)
            if actor not in members or type(a['accept']) is not bool:raise RuleViolation('assigned registrar required')
            if a['accept']:self.registry.approve(Actor.agent(actor),target,n)
            else:
                amount=self.registry.reject(Actor.agent(actor),target,n,bounded(a['reason'],4096))
                self.wallets[target]=self.wallets.get(target,0)+amount
            return {'status':self.registry.get(target).status.value}
        if op=='identity.heartbeat':
            fields(a,());self.registry.renew_liveness(actor,n);return {'alive':True}
        if op=='identity.exit':
            fields(a,());i=self.registry.get(actor)
            if i.stake or actor in self.parties._party:raise RuleViolation('settle professional stake and party membership first')
            amount=self.registry.exit(actor,n);self.wallets[actor]=self.wallets.get(actor,0)+amount;return {'refunded':amount}
        if op=='identity.freeze':
            fields(a,('target','duration','evidence'));self.registry.suspend(Actor.agent(actor),a['target'],n,n+number(a['duration'],1,86400),bounded(a['evidence'],64));return {'frozen':a['target']}
        if op=='beacon.publish':
            fields(a,('round','absolute_round','signature'),('scope',))
            scope=a.get('scope',self.tree.root);reg,_=self.scope(scope);service=reg.assignments
            key=a['round'] if service is self.assignments else (scope,a['round'])
            if not verified.get('beacon_seed') or self.rounds.get(key)!=a['absolute_round']:raise RuleViolation('verified scheduled BLS beacon required')
            service.publish_beacon(M,a['round'],bytes.fromhex(verified['beacon_seed']),n)
            return {'round':a['round']}
        if op=='party.consent':
            fields(a,('party','members','nonce','scope'));reg,scope=self.scope(a['scope']);parties=scope['parties']
            members=tuple(a['members']);message=parties.formation_message(a['party'],members,a['nonce'])
            if actor not in members or len(members)>1024:raise RuleViolation('founder consent belongs to roster')
            parties._citizen(actor,n);key=(a['scope'],a['party'],members,a['nonce'])
            consent=self.pending.setdefault(('party',key),{})
            if actor in consent:raise RuleViolation('duplicate founder consent')
            consent[actor]=self.sig(actor,message)
            if set(consent)==set(members):
                parties.form(a['party'],members,a['nonce'],n,consent);del self.pending['party',key]
            return {'consented':actor,'formed':a['party'] in parties._members}
        if op=='party.membership':
            fields(a,('party','action','nonce','scope'));_,scope=self.scope(a['scope']);p=scope['parties']
            p.membership(actor,a['party'],a['action'],a['nonce'],n,self.sig(actor,p.membership_message(actor,a['party'],a['action'],a['nonce'])))
            return {'party':p._party.get(actor)}
        if op=='party.case':
            fields(a,('party','target','action','duration','evidence','nonce','scope'));_,scope=self.scope(a['scope']);p=scope['parties']
            msg=p.sanction_message(actor,a['party'],a['target'],a['action'],a['duration'],a['evidence'],a['nonce'])
            cid=p.open_case(actor,a['party'],a['target'],a['action'],a['duration'],a['evidence'],a['nonce'],n,self.sig(actor,msg));return {'case':cid}
        if op=='party.approve':
            fields(a,('case','scope'));_,scope=self.scope(a['scope']);p=scope['parties']
            return {'applied':p.approve(actor,a['case'],n,self.sig(actor,p.approval_message(a['case'])))}
        if op=='pre.open':
            fields(a,('cycle','close','deadline','scope'));reg,scope=self.scope(a['scope']);scope['parties']._citizen(actor,n)
            if a['cycle'] in self.pre:raise RuleViolation('cycle reused')
            self.pre[a['cycle']]=PreElection(scope['parties'],a['cycle'],n,number(a['close'],n+1),number(a['deadline'],n+1))
            return {'candidates':self.pre[a['cycle']].candidates}
        if op=='pre.vote':
            fields(a,('cycle','picks'));p=self.pre[a['cycle']];picks=tuple(a['picks'])
            p.cast(actor,picks,p.electorate.proof(actor),n,self.sig(actor,p.ballot_message(actor,picks)));return {'cast':True}
        if op=='pre.close':
            fields(a,('cycle',));return asdict(self.pre[a['cycle']].close(n))
        if op=='campaign.program':
            fields(a,('cycle','party','program','vision','nonce'))
            p=self.pre[a['cycle']]
            if p.result is None or not p.result.valid:raise RuleViolation('qualified pre-election required')
            p.parties._member(actor,a['party'],n)
            if a['party'] not in p.result.qualified:raise RuleViolation('unqualified party')
            entry=Program(a['party'],actor,a['program'],a['vision'],a['nonce'])
            entry=Program(**dict(asdict(entry),signature=self.sig(actor,entry.message(self.chain,p.result.commitment))))
            self.programs[a['cycle'],a['party']]=entry;return {'committed':True}
        if op=='campaign.publish':
            fields(a,('cycle','issue','bank','end'));p=self.pre[a['cycle']]
            programs=tuple(self.programs[a['cycle'],q] for q in p.result.qualified)
            b=bank(a['issue'],a['bank']);c=Campaign.publish(p,a['issue'],programs,b,n,number(a['end'],n+1))
            self.campaigns[a['issue']]=(c,a['bank']);subjects=tuple(sorted(x for x in self.registry.ids if self.registry.get(x).operator in c.member_operators))
            self.freeze('certification',a['issue'],subjects,p.reg);return {'campaign':c.digest()}
        if op=='election.open':
            fields(a,('issue','windows'));c,b=self.campaigns[a['issue']]
            # Candidate cycle belongs to the same registry as the pre-election.
            reg=next(p.reg for p in self.pre.values() if p.result and p.result.commitment==c.pre_commitment)
            self.open_session(a['issue'],reg,b,a['windows'],ELECTION,campaign=c);return {'opened':True}
        if op=='role.accept':
            fields(a,('issue','commitment'));r=self.reviews[a['issue']];effect=self.pending[r.issue][7]
            if effect is None or effect['action']!='GRANT' or actor!=effect['target'] or a['commitment']!=r._draft.digest():raise RuleViolation('candidate consent to exact reviewed office required')
            self.role_consents[r.issue]=r._draft.digest();return {'consented':True}
        if op=='role.apply':
            fields(a,('issue',));decision=self.role_decisions[a['issue']];s=self.sessions[a['issue']];effect=decision['effect']
            if actor not in (effect.get('target'),effect['sponsor']) or decision['applied'] or n>=decision['expires']:raise RuleViolation('unexpired unapplied finalized role decision required')
            if effect['action']=='GRANT' and self.role_consents.get(s.issue)!=s.approved_record_hash:raise RuleViolation('candidate consent is stale or absent')
            self.apply_effect(s,effect);decision['applied']=True;return {'applied':True}
        if op=='proposal.prepare':
            fields(a,('issue','party','draft','review_end','scope','bank','kind','effect'))
            reg,scope=self.scope(a['scope']);p=scope['parties'];p._member(actor,a['party'],n)
            issue=bounded(a['issue']);kind=Kind(a['kind'])
            if kind in (Kind.FORMATION,Kind.MERGER,Kind.CORE):raise RuleViolation('dedicated structural/core workflow required')
            if issue in self.pending or issue in self.reviews:raise RuleViolation('issue reused')
            d=draft(a['draft']);b=bank(issue,a['bank'])
            if len([q for q in b.questions.values() if q.article_id=='__proposal__'])<reg.p.exam_items:
                raise RuleViolation('topic comprehension questions required')
            effect=self.validate_effect(a['effect'],kind,d,actor)
            if reg is not self.registry and (effect is not None or kind is Kind.PARAMETER):raise RuleViolation('local votes cannot change root offices or protocol parameters')
            d=self.bind_draft(d,b,effect)
            self.pending[issue]=(actor,a['party'],d,number(a['review_end'],n+86400),a['scope'],a['bank'],kind,effect)
            if reg is not self.registry:reg.validate_draft(issue,d,n)
            self.freeze('review',issue,p.members(a['party'],n,True),reg);return {'prepared':issue,'commitment':d.digest()}
        if op=='proposal.begin':
            fields(a,('issue',));owner,party,d,end,name,b,kind,effect=self.pending[a['issue']]
            if actor!=owner:raise RuleViolation('proposal owner required')
            reg,scope=self.scope(name);p=scope['parties'];members=self.members('review',a['issue'])
            self.reviews[a['issue']]=ProposalReview(self.chain,a['issue'],actor,party,self.parties_snapshot(p),members,d,reg,self.receipts,n,end,scope['credits'])
            return {'supervisors':members,'version':1,'commitment':d.digest()}
        if op=='proposal.comment':
            fields(a,('issue','party','text','parent','nonce'));r=self.reviews[a['issue']]
            msg=r.comment_message(actor,a['party'],a['text'],a['parent'],a['nonce'])
            return {'comment':r.comment(actor,a['party'],a['text'],a['parent'],a['nonce'],n,self.sig(actor,msg))}
        if op=='proposal.amend':
            fields(a,('issue','draft','nonce','bank','version','commitment'));r=self.reviews[a['issue']];self.review_version(r,a);d=draft(a['draft'])
            b=bank(a['issue'],a['bank']);d=self.bind_draft(d,b,self.pending[r.issue][7])
            r.amend(actor,d,a['nonce'],n,self.sig(actor,r.amendment_message(d,a['nonce'])))
            old=self.pending[a['issue']];self.pending[a['issue']]=old[:5]+(a['bank'],)+old[6:]
            return {'version':r._version}
        if op=='proposal.approve':
            fields(a,('issue','note','version','commitment'));r=self.reviews[a['issue']];self.review_version(r,a)
            r.approve(actor,a['note'],n,self.sig(actor,H(r.approval_message(),a['note'])));return {'approved':True}
        if op=='proposal.lock':
            fields(a,('issue','version','commitment'));r=self.reviews[a['issue']];self.review_version(r,a);r.lock(actor,n,self.sig(actor,r.lock_message()))
            subjects=tuple(r._parties[r.party]);self.freeze('certification',r.issue,subjects,r.reg)
            if r._locked.budget:self.freeze('verification',r.issue,subjects)
            return {'record':r._locked.digest()}
        if op=='proposal.open':
            fields(a,('issue','windows','beneficiary'));r=self.reviews[a['issue']]
            if actor!=r.owner:raise RuleViolation('proposal owner required')
            if a['beneficiary'] not in r._parties[r.party]:raise RuleViolation('beneficiary must be named proposing party citizen')
            old=self.pending[r.issue];self.open_session(r.issue,r.reg,old[5],a['windows'],old[6],review=r)
            self.beneficiaries[r.issue]=a['beneficiary'];return {'opened':True}
        if op=='exam.request':
            fields(a,('issue','secret'));s=self.sessions[a['issue']];attempt=s.request_exam(actor,bounded(a['secret'],256),n)
            return {'ticket':attempt.ticket,'attempt':attempt.n,'panel':s.panel_for(attempt.ticket).members}
        if op=='exam.submit':
            fields(a,('issue','ticket','declared','answers'));s=self.sessions[a['issue']];attempt=self.attempts.records[a['ticket']]
            if attempt.voter!=actor or attempt.issue!=s.issue or a['ticket'] in self.exam_submissions:
                raise RuleViolation('owned unsubmitted exam ticket required')
            s._check_open(n);sub=Submission(a['ticket'],tuple(a['declared']),tuple(sorted(dict(a['answers']).items())))
            s.plan(attempt,sub.declared_articles)
            if any(type(v) is not int or not 0<=v<=31 for _,v in sub.answers):raise RuleViolation('bounded answer choices required')
            self.exam_submissions[a['ticket']]=sub;return {'submitted':True}
        if op=='exam.grade':
            fields(a,('issue','ticket','verdicts'));s=self.sessions[a['issue']];ticket=a['ticket'];attempt=self.attempts.records[ticket]
            panel=s.panel_for(ticket);s._check_open(n)
            if actor not in panel.members or not s.registry.can(actor,'GRADE',n,s._matter())[0] or ticket in s.issued or ticket in self.failed:
                raise RuleViolation('eligible assigned grader required')
            sub=self.exam_submissions[ticket];plan=s.plan(attempt,sub.declared_articles)
            items=[q.qid for q in plan.proposal_qs]+[q.qid for _,q in plan.sampled]
            if type(a['verdicts']) is not dict or set(a['verdicts'])!=set(items) or any(type(v) is not bool for v in a['verdicts'].values()):
                raise RuleViolation('complete per-item verdicts required')
            votes=self.grades.setdefault(ticket,{})
            if actor in votes:raise RuleViolation('duplicate examiner judgment')
            votes[actor]=a['verdicts']
            if len(votes)<panel.threshold:return {'graded':False}
            verdict=evaluate(plan,majority(votes,items),s.p)
            if not verdict.passed:self.failed.add(ticket);return {'graded':True,'passed':False}
            self.receipts.signers=set(votes)
            before=s.registry.get(attempt.voter).bond
            tok,slashed=s.grade(attempt,sub,votes,sorted(votes),n);self.tokens[ticket]=tok
            slash=before-s.registry.get(attempt.voter).bond
            self.treasury.free+=slash;self.treasury._initial_total+=slash
            return {'graded':True,'passed':True,'read_articles':tok.R,'slashed':slashed}
        if op=='exam.audit':
            fields(a,('issue','ticket','verdicts'));s=self.sessions[a['issue']];ticket=a['ticket']
            if actor not in s.board.members or ticket not in s.audit_sample() or not s.registry.can(actor,'GRADE',n,s._matter())[0]:raise RuleViolation('assigned sampled certification auditor required')
            s._check_open(n);attempt=self.attempts.records[ticket];sub=self.exam_submissions[ticket];plan=s.plan(attempt,sub.declared_articles)
            items=[q.qid for q in plan.proposal_qs]+[q.qid for _,q in plan.sampled]
            if type(a['verdicts']) is not dict or set(a['verdicts'])!=set(items) or any(type(v) is not bool for v in a['verdicts'].values()):raise RuleViolation('complete audit verdicts required')
            votes=self.audit_votes.setdefault((s.issue,ticket),{})
            if actor in votes:raise RuleViolation('duplicate certification audit')
            votes[actor]=a['verdicts']
            if len(votes)<s.board.threshold:return {'audited':False}
            result=s.audit(ticket,evaluate(plan,majority(votes,items),s.p),n);return {'audited':True,'result':result}
        if op=='vote.cast':
            fields(a,('issue','ticket','choice','secret'));s=self.sessions[a['issue']];attempt=self.attempts.records[a['ticket']]
            token=self.tokens[a['ticket']];choice=a['choice']
            if type(choice) is list:choice=tuple(choice)
            elif type(choice) is dict:
                if set(choice)-set(s.point_ids):raise RuleViolation('unknown bill point')
                choice=tuple(choice.get(point) for point in s.point_ids)
            if s.kind!=ELECTION:
                normalize=lambda c: {'YES':'Y','NO':'N','ABSTAIN':'A'}.get(c,c)
                choice=tuple(normalize(c) for c in choice) if type(choice) is tuple else normalize(choice)
            if s.kind==ELECTION and not valid_ballot(choice,s.qualified,s.p):raise RuleViolation('invalid election ballot')
            if s.kind!=ELECTION and not s.point_ids and choice not in ('Y','N','A'):raise RuleViolation('invalid decision ballot')
            s.cast_ballot(actor,choice,token,a['secret'],attempt.n,s.electorate.proof(actor),n);return {'cast':True}
        if op=='vote.close':
            fields(a,('issue',));s=self.sessions[a['issue']];s.close(n);return {'phase':s.phase.value}
        if op=='vote.certify':
            fields(a,('issue',));s=self.sessions[a['issue']];s.certify(actor,self.sig(actor,s.certificate_message()),n);return {'certified':True}
        if op=='vote.advance':
            fields(a,('issue',));s=self.sessions[a['issue']];s.advance(n);return {'phase':s.phase.value}
        if op=='vote.challenge':
            fields(a,('issue','grounds'));s=self.sessions[a['issue']];idx=s.challenge(actor,a['grounds'],n)
            cid=s.issue+':challenge:'+str(idx);self.court_cases[cid]={'issue':s.issue,'index':idx,'votes':{},'subjects':(actor,)+tuple(s.board.members)}
            self.freeze('jury',cid,self.court_cases[cid]['subjects']);return {'case':cid}
        if op=='court.judge' and a.get('case') in self.court_cases and 'issue' in self.court_cases[a['case']]:
            fields(a,('case','upheld','evidence'));c=self.court_cases[a['case']];members=self.members('jury',a['case'])
            if actor not in members or actor in c['votes'] or type(a['upheld']) is not bool:
                raise RuleViolation('one judgment per assigned juror')
            if not self.registry.can(actor,'JUDGE',n,{'operators_involved':{self.registry.get(x).operator for x in c['subjects']}})[0]:raise RuleViolation('current independent jury authority required')
            bounded(a['evidence'],64);c['votes'][actor]=a['upheld']
            yes=sum(c['votes'].values());no=len(c['votes'])-yes
            if max(yes,no)>len(members)//2:
                s=self.sessions[c['issue']];ref=hx('native-jury-ruling',a['case'],sorted(c['votes'].items()))
                self.registry.register_ruling(M,ref,'CHALLENGE',f'{s.issue}:{c["index"]}')
                s.rule(Actor('COURT',ref),c['index'],yes>no,n)
                return {'resolved':True,'upheld':yes>no}
            return {'resolved':False}
        if op=='vote.finalize':
            fields(a,('issue',));s=self.sessions[a['issue']]
            if s.issue in self.finished:raise RuleViolation('decision already applied')
            result=s.finalize(n)
            if s.phase is Phase.FINAL:
                if s.kind==ELECTION and s.outcome is Outcome.PASSED:
                    scope=next(v for v in self.scoped.values() if v['monthly'].registry is s.registry)
                    scope['monthly'].record_election(s,n)
                    if s.registry is self.registry:self.registry.activate_family_cap(M,n)
                if s.kind is Kind.PARAMETER and s.outcome is Outcome.PASSED:self.policy.schedule(s,n)
                if s.outcome in (Outcome.PASSED,Outcome.PARTIAL) and s.issue in self.pending:
                    effect=self.pending[s.issue][7]
                    if effect is not None:self.role_decisions[s.issue]={'effect':effect,'expires':n+30*86400,'applied':False}
                    if s.registry is self.registry:self.tree.record_root_decision(M,s,n)
                    if s.effects.ceiling and s.issue in self.treasury.granted:
                        members=self.members('verification',s.issue);subjects=tuple(s.recused)
                        excluded=frozenset(self.registry.get(x).operator for x in subjects)
                        self.payments._policies[s.issue]=(members,len(members)//2+1,excluded,subjects)
                self.finished.add(s.issue)
            return {'phase':s.phase.value,'outcome':result.value if hasattr(result,'value') else result}
        if op=='milestone.approve':
            fields(a,('project','index','amount','evidence','valid_from','expires'))
            approval=MilestoneApproval(self.chain,**a);key=approval.message().hex()
            signatures=self.milestone_approvals.setdefault(key,{})
            if actor in signatures:raise RuleViolation('duplicate milestone approval')
            policy=self.payments._policies[approval.project]
            index=self.treasury.paid_idx[approval.project]
            if (actor not in policy[0] or not self.registry.can(actor,'VERIFY',n)[0]
                    or self.registry.get(actor).operator in policy[2]
                    or not approval.valid_from<=n<approval.expires or type(approval.index) is not int
                    or approval.index!=index or index>=len(self.treasury.tranches[approval.project])
                    or type(approval.amount) is not int or approval.amount!=self.treasury.tranches[approval.project][index]
                    or type(approval.evidence) is not str or len(approval.evidence)!=64
                    or any(c not in '0123456789abcdef' for c in approval.evidence)):
                raise RuleViolation('current assigned verifier and exact live tranche required')
            signatures[actor]=self.sig(actor,approval.message())
            if len(signatures)>=policy[1]:
                amount=self.payments.release(approval,signatures,n)
                recipient=self.beneficiaries[approval.project];self.wallets[recipient]=self.wallets.get(recipient,0)+amount
                return {'released':amount}
            return {'released':0}
        if op=='treasury.pause':
            fields(a,('project','duration','reason'));until=self.payments.pause(actor,a['project'],n,a['duration'],a['reason']);return {'until':until}
        if op=='admin.open':
            fields(a,('target','evidence'));cid=self.council.open(actor,a['target'],a['evidence'],n,self.sig(actor,self.council.open_message(actor,a['target'],a['evidence'],n)));return {'case':cid}
        if op=='admin.approve':
            fields(a,('case',));return {'applied':self.council.approve(actor,a['case'],n,self.sig(actor,self.council.approval_message(a['case'])))}
        if op.startswith('court.'):
            return self.judicial_operation(actor,op,a)
        if op.startswith('merger.'):
            from .merger import operate
            return operate(self,actor,op,a,verified,fields,number,bounded)
        if op.startswith('key.'):
            return self.key_operation(actor,op,a,verified)
        if op.startswith('society.'):
            return self.society_operation(actor,op,a)
        raise RuleViolation('unsupported authenticated protocol operation')

    def validate_effect(self,effect,kind,d,owner):
        if effect is None:return None
        if type(effect) is dict and effect.get('action')=='REFRESH_ADMIN_COUNCIL':
            fields(effect,('action','roster'))
            if kind is not Kind.ORDINARY or d.points or d.budget or not self.registry.can(owner,'ADMIN_VOTE',self.now)[0]:raise RuleViolation('atomic unfunded council referendum and mature sponsor required')
            roster=tuple(effect['roster'])
            if roster!=self.council._snapshot(self.now):raise RuleViolation('exact current mature council roster required')
            return {'action':effect['action'],'roster':roster,'sponsor':owner}
        fields(effect,('action','target','role','sponsor','stake'))
        if kind is not Kind.ORDINARY or d.points or d.budget:raise RuleViolation('authority changes require atomic ordinary referendum')
        if effect['action'] not in ('GRANT','REVOKE'):raise RuleViolation('unknown authority effect')
        role=Role(effect['role'])
        if role in (Role.CITIZEN,Role.PARTY_MEMBER,Role.VALIDATOR):raise RuleViolation('dedicated admission/party/consensus authority required')
        if effect['target'] not in self.registry.ids or effect['sponsor']!=owner or not self.registry.can(owner,'ADMIN_VOTE',self.now)[0]:raise RuleViolation('mature named administrative sponsor required')
        if self.registry.get(owner).operator==self.registry.get(effect['target']).operator:raise RuleViolation('sponsor conflict')
        stake=number(effect['stake'])
        professional=role in {Role.EXAMINER,Role.VERIFIER,Role.REVIEWER,Role.EXECUTOR}
        if effect['action']=='GRANT' and (professional and stake<self.params.examiner_stake or not professional and stake!=0):raise RuleViolation('exact professional stake policy')
        if effect['action']=='REVOKE' and stake!=0:raise RuleViolation('revocation carries no stake charge')
        return dict(effect)

    def apply_effect(self,s,effect):
        if effect is None:return
        if s.registry is not self.registry:raise RuleViolation('root role changes require a root electorate decision')
        if effect['action']=='REFRESH_ADMIN_COUNCIL':
            roster=tuple(effect['roster'])
            if roster!=self.council._snapshot(self.now):raise RuleViolation('council roster changed; fresh referendum required')
            ref='decision:'+s.issue
            self.registry.register_ratification(M,ref,'ADMIN_ROSTER',','.join(roster))
            self.council.refresh(Actor('VOTE',ref),self.now);return
        role=Role(effect['role']);ref='decision:'+s.issue
        self.registry.register_ratification(M,ref,effect['action']+':'+role.value,effect['target'],effect['sponsor'])
        authority=Actor('VOTE',ref)
        if effect['action']=='GRANT':
            self.debit(effect['target'],effect['stake']);self.registry.grant(authority if role in SENSITIVE_OFFICES else M,effect['target'],role,self.now,effect['stake'])
        else:
            self.registry.revoke(authority if role in SENSITIVE_OFFICES else M,effect['target'],role,self.now,'finalized referendum')

    @staticmethod
    def bind_draft(d,b,effect):
        binding=json.dumps({'question_bank':b.record_hash(),'authority_effect':effect},sort_keys=True,separators=(',',':'))
        return replace(d,body=d.body+'\n\nNative authorization binding: '+binding)

    @staticmethod
    def review_version(r,a):
        if a['version']!=r._version or a['commitment']!=r._draft.digest():
            raise RuleViolation('stale proposal version or authorization commitment')

    def key_operation(self,actor,op,a,verified):
        n=self.now
        if op=='key.rotate':
            fields(a,('key','proof'))
            if not verified.get('new_key') or actor in self.rotations:raise RuleViolation('new-key possession or pending rotation')
            if a['key'] in self.public_keys.values() or a['key'] in self.session_keys or any(x[0]==a['key'] for x in self.rotations.values()) or any(x['key']==a['key'] for x in self.recoveries.values()):raise RuleViolation('key already owned or reserved')
            self.rotations[actor]=(a['key'],n+self.params.rotation_delay);return {'ready':self.rotations[actor][1]}
        if op=='key.cancel':
            fields(a,())
            if actor not in self.rotations and actor not in self.recoveries:raise RuleViolation('no pending key change')
            self.rotations.pop(actor,None);self.recoveries.pop(actor,None);return {'cancelled':True}
        if op=='key.activate':
            fields(a,())
            key,ready=self.rotations[actor]
            if n<ready:raise RuleViolation('key activation delay')
            self.public_keys[actor]=key;del self.rotations[actor];self.session_keys={k:v for k,v in self.session_keys.items() if v['account']!=actor}
            return {'activated':True}
        if op=='key.guardians':
            fields(a,('guardians','threshold'));guardians=tuple(a['guardians']);k=number(a['threshold'],3,len(guardians))
            if len(guardians)>32 or len(set(guardians))!=len(guardians) or actor in guardians:raise RuleViolation('distinct bounded recovery guardians')
            ops=[]
            for g in guardians:
                if not self.registry.can(g,'VOTE',n)[0]:raise RuleViolation('mature civic guardian required')
                operator=self.registry.get(g).operator
                if operator==self.registry.get(actor).operator or operator in ops:raise RuleViolation('independent guardian operators required')
                ops.append(operator)
            self.guardians[actor]=(guardians,k);self.recoveries.pop(actor,None);return {'threshold':k}
        if op=='key.recover':
            fields(a,('target','key','proof','nonce'));target=a['target'];guardians,k=self.guardians[target]
            if actor not in guardians or not self.registry.can(actor,'VOTE',n)[0] or not verified.get('new_key'):raise RuleViolation('current authorized guardian/new-key proof required')
            if target in self.rotations:raise RuleViolation('ordinary rotation pending')
            bounded(a['nonce'])
            proposal=self.recoveries.get(target)
            if proposal is None:
                if a['key'] in self.public_keys.values() or a['key'] in self.session_keys or any(x[0]==a['key'] for x in self.rotations.values()) or any(x['key']==a['key'] for x in self.recoveries.values()):raise RuleViolation('recovery key already reserved')
                proposal={'key':a['key'],'nonce':a['nonce'],'votes':set(),'ready':0,'opened':n,'expires':n+30*86400}
                self.recoveries[target]=proposal
            if proposal['key']!=a['key'] or proposal['nonce']!=a['nonce'] or actor in proposal['votes'] or n>=proposal['expires']:raise RuleViolation('conflicting/duplicate/expired recovery')
            proposal['votes'].add(actor)
            if len(proposal['votes'])>=k and not proposal['ready']:proposal['ready']=n+self.params.recovery_delay
            return {'ready':proposal['ready']}
        if op=='key.recovery_activate':
            fields(a,('target',));target=a['target'];proposal=self.recoveries[target];guardians,k=self.guardians[target]
            if actor not in proposal['votes'] or not proposal['ready'] or not proposal['ready']<=n<proposal['expires']:raise RuleViolation('guardian activation or delay')
            live=[g for g in proposal['votes'] if g in guardians and self.registry.can(g,'VOTE',n)[0]]
            operators={self.registry.get(g).operator for g in live}
            if len(operators)<k or self.registry.get(target).operator in operators:raise RuleViolation('recovery coalition lost independent civic authority')
            self.public_keys[target]=proposal['key'];del self.recoveries[target];self.session_keys={key:v for key,v in self.session_keys.items() if v['account']!=target};return {'recovered':True}
        if op=='key.session':
            fields(a,('key','proof','operations','expires'))
            allowed={'vote.cast','exam.request','exam.submit','pre.vote','proposal.comment'}
            operations=tuple(a['operations']);expires=number(a['expires'],n+1,n+86400)
            if not verified.get('new_key') or not operations or not set(operations)<=allowed or len(set(operations))!=len(operations):raise RuleViolation('bounded session scopes and key proof required')
            if a['key'] in self.public_keys.values() or a['key'] in self.session_keys or any(x[0]==a['key'] for x in self.rotations.values()) or any(x['key']==a['key'] for x in self.recoveries.values()):raise RuleViolation('session key already owned or reserved')
            if sum(grant['account']==actor for grant in self.session_keys.values())>=32:raise RuleViolation('bounded active session keys')
            self.session_keys[a['key']]={'account':actor,'operations':operations,'expires':expires};return {'expires':expires}
        if op=='key.session_revoke':
            fields(a,('key',));record=self.session_keys[a['key']]
            if record['account']!=actor:raise RuleViolation('session owner required')
            del self.session_keys[a['key']];return {'revoked':True}
        raise RuleViolation('unknown key operation')

    def society_operation(self,actor,op,a):
        n=self.now
        if op=='society.consent':
            fields(a,('parent','child','members','constraints','nonce','expires'))
            members=tuple(a['members']);charter=pairs(a['constraints'])
            if actor not in members:raise RuleViolation('subsociety founder required')
            registry=self.tree.view(a['parent'])
            if not registry.can(actor,'VOTE',n)[0]:raise RuleViolation('eligible parent citizen required')
            message=self.tree.formation_message(a['parent'],a['child'],members,charter,a['nonce'])
            key=('child',a['child'],message.hex());consents=self.pending.setdefault(key,{})
            if actor in consents:raise RuleViolation('duplicate subgroup consent')
            consents[actor]=self.sig(actor,message)
            request=None
            if set(consents)==set(members):
                request=self.tree.propose_child(a['parent'],a['child'],members,charter,a['nonce'],n,a['expires'],consents)
                self.freeze_ancestors(request)
                del self.pending[key]
            return {'request':request}
        if op=='society.request':
            fields(a,('scope','issue','draft','expires','stage'),('bank','kind','effect'))
            registry,_=self.scope(a['scope'])
            if not registry.can(actor,'SUBMIT_PROPOSAL',n)[0]:raise RuleViolation('local proposing party member required')
            if a['stage']=='PRE':
                fields(a,('scope','issue','draft','expires','stage','bank','kind','effect'))
                d=draft(a['draft']);effect=self.validate_effect(a['effect'],Kind(a['kind']),d,actor)
                d=self.bind_draft(d,bank(a['issue'],a['bank']),effect);payload=d.digest();budget=d.budget
                subjects=tuple(self.scoped[a['scope']]['parties'].members(self.scoped[a['scope']]['parties']._party[actor],n,True))
            elif a['stage']=='FINAL':
                s=self.sessions[a['issue']]
                if s.registry is not registry:raise RuleViolation('scope mismatch')
                budget,_,_=self.tree._local_effects(s);payload=s.approved_record_hash;subjects=tuple(s.recused)
            else:raise RuleViolation('parent request stage')
            request=self.tree.request(M,a['scope'],a['issue'],payload,budget,subjects,n,a['expires'],a['stage'])
            self.freeze_ancestors(request);return {'request':request}
        if op=='society.approve':
            fields(a,('request','authority','note'));parent=self.tree.view(a['authority']);service=parent.assignments
            service.assign(M,'hierarchy_review',a['request'],n)
            message=self.tree.review_message(a['request'],a['note'],a['authority'])
            self.tree.approve(a['request'],actor,a['note'],n,self.sig(actor,message),a['authority']);return {'approved':True}
        if op=='society.preapprove':
            fields(a,('request',));self.tree.activate_preapproval(a['request'],n);return {'preapproved':True}
        if op=='society.mandates':
            fields(a,('child',));mandates=self.tree.formation_mandates(a['child'],n)
            return {'issues':[m.issue for m in mandates]}
        if op=='society.vote_prepare':
            fields(a,('issue',));mandate=self.tree._mandates[a['issue']]
            self.freeze('certification',mandate.issue,mandate.subjects,mandate.registry)
            return {'prepared':True}
        if op=='society.vote_open':
            fields(a,('issue','bank','windows'));mandate=self.tree._mandates[a['issue']]
            self.open_session(mandate.issue,mandate.registry,a['bank'],a['windows'],mandate.kind,mandate=mandate)
            return {'opened':True}
        if op=='society.activate':
            fields(a,('child',));reg=self.tree.activate_child(a['child'],n)
            # Existing global credentials remain qualifications; political offices and
            # local party membership require local decisions.
            reg.assignments=TaskAssignments(self.chain,reg)
            parties=PartyRegistry(self.chain,reg,self.receipts);credits=CreditLedger()
            self.scoped[a['child']]={'parties':parties,'credits':credits,'monthly':MonthlyCredits(credits,reg)}
            return {'activated':True}
        if op=='society.finalize':
            fields(a,('request','issue'));s=self.sessions[a['issue']];_,tranches,_=self.tree._local_effects(s)
            project=self.tree.finalize_local(a['request'],s,tranches,n)
            if tranches:
                # Verifiers are globally qualified and selected outside local beneficiaries.
                members=self.members('verification',s.issue);subjects=tuple(s.recused);excluded=frozenset(self.registry.get(x).operator for x in subjects)
                self.payments._policies[project]=(members,len(members)//2+1,excluded,subjects)
                self.beneficiaries[project]=self.beneficiaries[s.issue]
            return {'project':project}
        if op=='society.expire':
            fields(a,('scope','issue'));self.tree.expire(a['scope'],a['issue'],n);return {'expired':True}
        raise RuleViolation('unknown society operation')

    def freeze_ancestors(self,request):
        r=self.tree._requests[request]
        for authority in self.tree.ancestry(r.scope)[:-1]:
            reg=self.tree.view(authority)
            service=getattr(reg,'assignments',None)
            if service is None:raise RuleViolation('parent assignment service missing')
            self.freeze('hierarchy_review',request,r.subjects,reg)

    def judicial_operation(self,actor,op,a):
        n=self.now
        if op=='court.appeal':
            fields(a,('evidence',))
            if len(a['evidence'])!=64:raise RuleViolation('appeal evidence commitment')
            originals=[c for c in self.court_cases.values() if c.get('target')==actor and c.get('applied')]
            if not originals:raise RuleViolation('existing judicial sanction required')
            original=originals[-1];issuer=original['issuer'];cid=hx('native-judicial-appeal',actor,self.receipts.context)
            self.registry.appeal(actor,cid,n)
            self.court_cases[cid]={'target':actor,'action':'APPEAL','duration':0,'evidence':a['evidence'],'subjects':(actor,issuer),'votes':{},'expires':n+14*86400,'ref':cid,'decision':None,'applied':False}
            self.freeze('jury','court:'+cid,(actor,issuer));return {'case':cid}
        if op=='court.open':
            fields(a,('target','action','duration','evidence'))
            action=a['action'];target=a['target'];i=self.registry.get(target)
            if self.bootstrap and target in self.registry.validators and action=='SUSPEND':raise RuleViolation('active consensus validators require coordinated replacement before judicial suspension')
            if not self.registry.can(actor,'FILE_CASE',n)[0] or self.registry.get(actor).operator==i.operator:raise RuleViolation('independent civic complainant required')
            if action not in ('BAN','SUSPEND','LIFT','ADMIN_DISMISS','ADMIN_RESTORE') or len(a['evidence'])!=64 or any(c not in '0123456789abcdef' for c in a['evidence']):raise RuleViolation('bounded judicial action/evidence')
            number(a['duration'],1,30*86400) if action=='SUSPEND' else number(a['duration'],0,0)
            if any(c.get('target')==target and not c.get('applied') and n<c['expires'] for c in self.court_cases.values() if 'target' in c):raise RuleViolation('one pending identity case per target')
            cid=hx('native-identity-case',self.chain,actor,a,n,self.receipts.context)
            self.court_cases[cid]={'target':target,'action':action,'duration':a['duration'],'evidence':a['evidence'],'subjects':(actor,target),'votes':{},'expires':n+14*86400,'ref':cid,'decision':None,'applied':False}
            self.freeze('jury','court:'+cid,(actor,target));return {'case':cid}
        if op=='court.judge':
            fields(a,('case','upheld','evidence'));cid=a['case'];c=self.court_cases[cid];members=self.members('jury','court:'+cid)
            if c['decision'] is not None or n>=c['expires'] or actor not in members or actor in c['votes'] or type(a['upheld']) is not bool:raise RuleViolation('one timely decision per assigned independent juror')
            if not self.registry.can(actor,'JUDGE',n,{'operators_involved':{self.registry.get(x).operator for x in c['subjects']}})[0]:raise RuleViolation('live qualified juror required')
            if len(a['evidence'])!=64:raise RuleViolation('judgment evidence hash')
            c['votes'][actor]=a['upheld'];yes=sum(c['votes'].values());no=len(c['votes'])-yes
            if max(yes,no)>len(members)//2:
                c['decision']=yes>no
                if c['decision']:self.freeze('admin_review','court:'+c['ref'],c['subjects'])
            return {'decided':c['decision']}
        if op=='court.apply':
            fields(a,('case',));c=self.court_cases[a['case']]
            if c['decision'] is not True or c['applied'] or n>=c['expires']:raise RuleViolation('unexpired independent judgment required')
            members=self.members('admin_review','court:'+c['ref'])
            if actor!=members[0]:raise RuleViolation('assigned accountable court administrator required')
            self.registry.register_ruling(M,c['ref'],c['action'],c['target'],actor,n,c['subjects'])
            court=Actor('COURT',c['ref']);i=self.registry.get(c['target']);before=i.bond+i.stake
            if c['action']=='BAN':self.registry.ban(court,c['target'],n,c['evidence'])
            elif c['action']=='SUSPEND':self.registry.suspend(court,c['target'],n,n+c['duration'],c['evidence'])
            elif c['action']=='LIFT':self.registry.lift_suspension(court,c['target'],n)
            elif c['action']=='ADMIN_DISMISS':self.registry.dismiss_admin(court,c['target'],n)
            elif c['action']=='ADMIN_RESTORE':self.registry.lift_admin_hold(court,c['target'],n)
            elif c['action']=='APPEAL':self.registry.resolve_appeal(court,c['target'],n,True)
            c['issuer']=actor
            after=i.bond+i.stake;slash=before-after
            self.treasury.free+=slash;self.treasury._initial_total+=slash;c['applied']=True
            return {'applied':True,'forfeited':slash}
        raise RuleViolation('unknown judiciary operation')
