"""Signed party membership, local sanctions and 5/3-point pre-election ballots.

Authentication uses the reference HMAC keyring. Native keepers must authenticate
identities/time and persist these state machines atomically.
"""
import copy
from dataclasses import dataclass,field
from .crypto_sim import H,hx
from .roles import Actor,Role
from .session import snapshot_electorate
from .treasury import RuleViolation
from .params import BPS

@dataclass
class MemberCase:
    party:str
    target:str
    action:str
    duration:int
    evidence:str
    roster:tuple
    opened:int
    expires:int
    approvals:set=field(default_factory=set)
    applied:bool=False

class PartyRegistry:
    def __init__(self,chain,registry,keyring):
        if not isinstance(chain,str) or not chain or getattr(registry,'party_registry',None) is not None:
            raise RuleViolation('unique party registry and chain domain required')
        self.chain,self.reg,self.kr=chain,registry,keyring
        self._members={};self._party={};self._banned={};self._suspended={};self._cases={};self._used=set();self._campaigns={};self._height=0;self._locked_until=0
        registry.party_registry=self
    def _time(self,height,membership=False):
        if type(height) is not int or height<self._height:raise RuleViolation('invalid or backdated party height')
        if membership and height<self._locked_until:raise RuleViolation('election membership frozen')
    def _citizen(self,agent,height):
        if not self.reg.can(agent,'VOTE',height)[0]:raise RuleViolation('eligible citizen required')
    def _sig(self,agent,message,signature):
        if not isinstance(signature,str) or not self.kr.verify(agent,message,signature):raise RuleViolation('invalid party signature')
    def formation_message(self,party,members,nonce):return H(b'party-form-v1',self.chain,party,tuple(sorted(members)),nonce)
    def form(self,party,members,nonce,height,signatures):
        self._time(height,True)
        if (type(party) is not str or not 0<len(party)<=128 or party in self._members
                or type(members) is not tuple or any(type(a) is not str for a in members)
                or len(set(members))!=len(members) or len(members)<self.reg.p.min_party_members
                or type(nonce) is not str or not 0<len(nonce)<=128):raise RuleViolation('party needs distinct consenting founders')
        if set(signatures)!=set(members):raise RuleViolation('all founders must consent')
        message=self.formation_message(party,members,nonce)
        for a in members:
            self._citizen(a,height)
            if a in self._party:raise RuleViolation('one party membership per citizen')
            self._sig(a,message,signatures[a])
        self._members[party]=set(members);self._banned[party]=set();self._height=height
        for a in members:self._party[a]=party;self.reg.get(a).roles.add(Role.PARTY_MEMBER)
        self.reg._log(height,Actor('MODULE','parties'),'PARTY_FORMED',party,hx(message))
    def membership_message(self,agent,party,action,nonce):return H(b'party-membership-v1',self.chain,agent,party,action,nonce)
    def membership(self,agent,party,action,nonce,height,signature):
        self._time(height,True);self._citizen(agent,height)
        if type(nonce) is not str or not 0<len(nonce)<=128 or (agent,nonce) in self._used:raise RuleViolation('membership nonce replay')
        if party not in self._members or action not in ('JOIN','LEAVE'):raise RuleViolation('unknown membership action')
        if action=='JOIN' and (agent in self._party or agent in self._banned[party]):raise RuleViolation('already affiliated or banned from party')
        if action=='LEAVE' and self._party.get(agent)!=party:raise RuleViolation('not a party member')
        self._sig(agent,self.membership_message(agent,party,action,nonce),signature)
        if action=='JOIN':
            self._members[party].add(agent);self._party[agent]=party;self.reg.get(agent).roles.add(Role.PARTY_MEMBER)
            self.reg.party_holds[agent]=self._suspended.get((party,agent),0)
        else:self._members[party].remove(agent);del self._party[agent];self.reg.get(agent).roles.discard(Role.PARTY_MEMBER);self.reg.party_holds.pop(agent,None)
        self._used.add((agent,nonce));self._height=height
        self.reg._log(height,Actor.agent(agent),'PARTY_'+action,party,nonce)
    def members(self,party,height,include_suspended=False):
        if party not in self._members:raise RuleViolation('unknown party')
        return tuple(sorted(a for a in self._members[party] if include_suspended or height>=self.reg.party_holds.get(a,0)))
    def _member(self,agent,party,height):
        self._citizen(agent,height)
        if self._party.get(agent)!=party or height<self.reg.party_holds.get(agent,0):raise RuleViolation('active party member required')
    def sanction_message(self,proposer,party,target,action,duration,evidence,nonce):
        return H(b'party-case-v1',self.chain,proposer,party,target,action,duration,evidence,nonce)
    def open_case(self,proposer,party,target,action,duration,evidence,nonce,height,signature):
        self._time(height);self._member(proposer,party,height)
        if (self._party.get(target)!=party or action not in ('BAN','SUSPEND') or type(duration) is not int
                or (action=='BAN' and duration!=0) or (action=='SUSPEND' and not 1<=duration<=self.reg.p.party_suspend_max)
                or type(evidence) is not str or len(evidence)!=64 or any(c not in '0123456789abcdef' for c in evidence)
                or type(nonce) is not str or not 0<len(nonce)<=128):raise RuleViolation('invalid party sanction')
        if any(c.party==party and c.target==target and not c.applied and height<c.expires for c in self._cases.values()):
            raise RuleViolation('one live member case per target')
        message=self.sanction_message(proposer,party,target,action,duration,evidence,nonce);case_id=hx(message)
        if case_id in self._cases:raise RuleViolation('party case replay')
        self._sig(proposer,message,signature)
        self._cases[case_id]=MemberCase(party,target,action,duration,evidence,self.members(party,height,True),height,height+self.reg.p.party_case_window)
        self._height=height;self.reg._log(height,Actor.agent(proposer),'PARTY_CASE',target,case_id)
        return case_id
    def approval_message(self,case_id):
        c=self._cases.get(case_id)
        if c is None:raise RuleViolation('unknown party case')
        return H(b'party-case-approve-v1',self.chain,case_id,c.party,c.target,c.action,c.duration,c.roster,c.expires)
    def approve(self,agent,case_id,height,signature):
        self._time(height);c=self._cases.get(case_id)
        if c is None or c.applied or height>=c.expires or agent not in c.roster or agent in c.approvals:
            raise RuleViolation('expired/applied case or duplicate/outsider approval')
        self._member(agent,c.party,height)
        if self._party.get(c.target)!=c.party:raise RuleViolation('target left party')
        self._sig(agent,self.approval_message(case_id),signature)
        approvals=c.approvals|{agent}
        live=[a for a in approvals if self._party.get(a)==c.party and self.reg.can(a,'VOTE',height)[0]
              and height>=self.reg.party_holds.get(a,0)]
        apply=2*len(live)>=len(c.roster)
        c.approvals=approvals;self._height=height
        if apply:
            if c.action=='BAN':
                self._members[c.party].remove(c.target);del self._party[c.target];self._banned[c.party].add(c.target)
                self.reg.get(c.target).roles.discard(Role.PARTY_MEMBER);self.reg.party_holds.pop(c.target,None)
            else:
                self._suspended[(c.party,c.target)]=height+c.duration
                self.reg.party_holds[c.target]=height+c.duration
            c.applied=True
        self.reg._log(height,Actor.agent(agent),'PARTY_'+('SANCTIONED' if apply else 'APPROVAL'),c.target,case_id)
        return apply
    def case(self,case_id):return copy.deepcopy(self._cases[case_id])

@dataclass(frozen=True)
class PreElectionResult:
    valid:bool
    reason:str
    points:tuple
    total_points:int
    qualified:tuple
    participation:int
    electorate_size:int
    commitment:str

class PreElection:
    def __init__(self,parties,cycle,open_height,close_height,locked_until):
        parties._time(open_height,True)
        if (type(cycle) is not str or not 0<len(cycle)<=128 or type(close_height) is not int
                or type(locked_until) is not int or not open_height<close_height<locked_until
                or locked_until-open_height>parties.reg.p.max_election_cycle_blocks):raise RuleViolation('invalid pre-election windows')
        self.parties=parties;self.reg=parties.reg;self.kr=parties.kr;self.p=self.reg.p
        self.cycle,self.open_height,self.close_height,self.locked_until=cycle,open_height,close_height,locked_until
        self.electorate=snapshot_electorate(self.reg,open_height)
        self.members=tuple((p,parties.members(p,open_height,True)) for p in sorted(parties._members)
            if len([a for a in parties.members(p,open_height) if self.reg.can(a,'VOTE',open_height)[0]])>=self.p.min_party_members)
        if not self.members:raise RuleViolation('no eligible formed parties')
        self.candidates=tuple(p for p,_ in self.members);self._ballots={};self._height=open_height;self.result=None
        self.snapshot=hx('pre-election-snapshot',parties.chain,cycle,self.members,self.electorate.root,self.p.snapshot_hash())
        if cycle in getattr(parties,'_cycles',set()):raise RuleViolation('pre-election cycle replay')
        if not hasattr(parties,'_cycles'):parties._cycles=set()
        parties._cycles.add(cycle);parties._locked_until=locked_until;parties._height=open_height
    def ballot_message(self,voter,picks):return H(b'pre-election-ballot-v1',self.parties.chain,self.snapshot,voter,picks)
    def cast(self,voter,picks,proof,height,signature):
        from .crypto_sim import verify_proof
        if (type(height) is not int or height<self._height or height<self.parties._height or not self.open_height<=height<self.close_height
                or self.result is not None or voter in self._ballots):raise RuleViolation('pre-election closed/backdated/duplicate ballot')
        self.parties._citizen(voter,height)
        if not verify_proof(self.electorate.root,voter.encode(),proof):raise RuleViolation('not in frozen pre-election electorate')
        if (type(picks) is not tuple or len(picks)!=2 or type(picks[0]) is not str or picks[0] not in self.candidates
                or (picks[1] is not None and (type(picks[1]) is not str or picks[1] not in self.candidates or picks[1]==picks[0]))):
            raise RuleViolation('distinct primary/secondary support choices required')
        self.parties._sig(voter,self.ballot_message(voter,picks),signature)
        self._ballots[voter]=picks;self._height=height;self.parties._height=height
    def close(self,height):
        if type(height) is not int or height<self._height or height<self.parties._height or height<self.close_height or self.result is not None:
            raise RuleViolation('pre-election not closable')
        points={p:0 for p in self.candidates}
        for picks in self._ballots.values():
            for party,amount in zip(picks,self.p.pre_ballot_points):
                if party is not None:points[party]+=amount
        total=sum(points.values());participation=len(self._ballots)
        valid=bool(total) and participation*BPS>=self.electorate.size*self.p.quorum_bps
        qualified=tuple(p for p in self.candidates if valid and points[p]*BPS>=total*self.p.pre_threshold_bps)
        reason='OK' if qualified else 'NO_QUORUM' if not valid else 'NO_QUALIFIED_PARTIES'
        commitment=hx('pre-election-result',self.snapshot,sorted(self._ballots.items()),sorted(points.items()),qualified)
        self.result=PreElectionResult(bool(qualified),reason,tuple(sorted(points.items())),total,qualified,participation,self.electorate.size,commitment)
        self._height=height;self.parties._height=height;self.reg._log(height,Actor('MODULE','pre-election'),'PRE_ELECTION_CLOSED',self.cycle,commitment)
        return self.result
    def ballots_public(self):
        if self.result is None:raise RuleViolation('pre-election ballots sealed until close')
        return dict(self._ballots)
