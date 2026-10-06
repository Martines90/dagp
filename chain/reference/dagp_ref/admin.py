"""Peer containment of administrative powers, never an automatic citizenship ban.

Frozen council denominator, signed approvals, independent operators and bounded holds.
Uses simulation signatures; a native keeper must authenticate enrollment and commands.
"""
import copy
from dataclasses import dataclass, field
from .crypto_sim import H, hx
from .roles import Actor, Role, Status
from .treasury import RuleViolation

@dataclass
class ContainmentCase:
    target: str
    evidence: str
    opened: int
    expires: int
    roster_version: int
    approvals: set = field(default_factory=set)
    applied: bool = False

class AdminCouncil:
    def __init__(self, chain, registry, keyring):
        if not isinstance(chain,str) or not chain:raise RuleViolation('chain domain required')
        self.chain,self.reg,self.kr=chain,registry,keyring
        self._rules_hash=registry.p.snapshot_hash()
        self._roster=self._snapshot()
        self._version=1;self._cases={};self._last_target={};self._height=0

    def _snapshot(self):
        members=tuple(self.reg.agents_with(Role.ADMIN))
        operators={self.reg.get(a).operator for a in members}
        if len(members)<self.reg.p.admin_min_council or len(operators)!=len(members):
            raise RuleViolation('insufficient independent administrators')
        return members

    @property
    def threshold(self):return (len(self._roster)+1)//2

    def _live(self,member,height):
        if member not in self._roster or not self.reg.can(member,'ADMIN_VOTE',height)[0]:
            raise RuleViolation('not an eligible administrator')

    def _time(self,height):
        if self.reg.p.snapshot_hash()!=self._rules_hash:
            raise RuleViolation("council rules changed; versioned migration required")
        if type(height) is not int or height<self._height:
            raise RuleViolation('invalid or backdated council height')

    def open_message(self,member,target,evidence,height):
        return H(b'dagp-admin-open-v1',self.chain,self._version,member,target,evidence,height)

    def open(self,member,target,evidence,height,signature):
        self._time(height);self._live(member,height)
        if target not in self._roster or self.reg.get(target).status is not Status.ACTIVE:
            raise RuleViolation('target is not an active roster administrator')
        if self.reg.get(member).operator==self.reg.get(target).operator:
            raise RuleViolation('self or operator-conflicted complaint')
        if (not isinstance(evidence,str) or len(evidence)!=64
                or any(c not in '0123456789abcdef' for c in evidence)):
            raise RuleViolation('evidence commitment required')
        if any(c.target==target and not c.applied and height<c.expires for c in self._cases.values()):
            raise RuleViolation('one open case per target')
        if height<self._last_target.get(target,-10**12)+2*self.reg.p.admin_containment_duration:
            raise RuleViolation('containment cooldown; use independent court review')
        if not isinstance(signature,str) or not self.kr.verify(member,self.open_message(member,target,evidence,height),signature):
            raise RuleViolation('invalid complaint signature')
        case_id=hx('admin-case',self.chain,self._version,member,target,evidence,height)
        if case_id in self._cases:raise RuleViolation('case replay')
        self._cases[case_id]=ContainmentCase(target,evidence,height,height+self.reg.p.admin_vote_window,self._version)
        self._height=height
        self.reg._log(height,Actor.agent(member),'ADMIN_CASE',target,case_id)
        return case_id

    def approval_message(self,case_id):
        c=self._cases.get(case_id)
        if c is None:raise RuleViolation('unknown containment case')
        return H(b'dagp-admin-approve-v1',self.chain,case_id,c.roster_version,c.target,c.evidence,c.expires)

    def approve(self,member,case_id,height,signature):
        self._time(height);self._live(member,height)
        c=self._cases.get(case_id)
        if c is None or c.applied or not c.opened<=height<c.expires:
            raise RuleViolation('case is not open')
        if member in c.approvals:raise RuleViolation('duplicate approval')
        if self.reg.get(member).operator==self.reg.get(c.target).operator:
            raise RuleViolation('target cannot approve own containment')
        if not isinstance(signature,str) or not self.kr.verify(member,self.approval_message(case_id),signature):
            raise RuleViolation('invalid approval signature')
        approvals=c.approvals|{member}
        # Recheck all supporters: subsequent revocations/holds and operator mergers cannot count.
        eligible=[a for a in approvals if self.reg.can(a,'ADMIN_VOTE',height)[0]
                  and self.reg.get(a).operator!=self.reg.get(c.target).operator]
        operators={self.reg.get(a).operator for a in eligible}
        apply=len(operators)>=self.threshold
        c.approvals=approvals;self._height=height
        if apply:
            self.reg.admin_holds[c.target]=height+self.reg.p.admin_containment_duration
            self._last_target[c.target]=height;c.applied=True
            self.reg._log(height,Actor('MODULE','admin-council'),'ADMIN_CONTAINED',c.target,
                          f'{case_id}:until={self.reg.admin_holds[c.target]}')
        else:self.reg._log(height,Actor.agent(member),'ADMIN_APPROVAL',c.target,case_id)
        return apply

    def case(self,case_id):return copy.deepcopy(self._cases[case_id])

    def refresh(self,actor,height):
        self._time(height)
        if any(not c.applied and height<c.expires for c in self._cases.values()):
            raise RuleViolation('cannot change roster during open cases')
        roster=self._snapshot()
        self.reg._authorize(actor,{'VOTE'},height,'ADMIN_ROSTER',','.join(roster))
        self.reg._spend(actor);self._roster=roster;self._version+=1;self._height=height
        self.reg._log(height,actor,'ADMIN_ROSTER',','.join(roster))
