"""Authenticated milestone controller. Simulation signatures; native port requires Ed25519.

The controller owns its escrow. No raw treasury reference is exposed as an API.
The native keeper must make numeric Treasury.release_next inaccessible to transactions.
"""
from dataclasses import dataclass
from .crypto_sim import H
from .roles import Status, Role
from .treasury import Treasury, RuleViolation

@dataclass(frozen=True)
class MilestoneApproval:
    chain: str
    project: str
    index: int
    amount: int
    evidence: str
    valid_from: int
    expires: int

    def message(self):
        return H(b'dagp-milestone-v1',self.chain,self.project,self.index,self.amount,
                 self.evidence,self.valid_from,self.expires)

class MilestonePayments:
    def __init__(self, chain, registry, keyring, free):
        if not isinstance(chain,str) or not chain:
            raise RuleViolation('chain domain required')
        self.chain,self.registry,self.keyring=chain,registry,keyring
        self._treasury=Treasury(free)
        self._policies={}
        from .emergency import Emergency
        self._emergency=Emergency(registry.p,registry,self._treasury)

    def fund(self, project, tranches, verifiers, threshold, excluded_operators, height=0):
        """Trusted finalized-vote entry point, never a public funding transaction."""
        members=tuple(verifiers);excluded=frozenset(excluded_operators)
        if (type(threshold) is not int or threshold < 2 or threshold > len(members) or 2*threshold <= len(members)
                or len(set(members)) != len(members) or project in self._policies):
            raise RuleViolation('invalid verifier policy')
        if not excluded or any(not isinstance(op,str) or not op for op in excluded):
            raise RuleViolation('explicit beneficiary operator exclusions required')
        operators=[]
        for member in members:
            identity=self.registry.get(member)
            if identity.status is not Status.ACTIVE or Role.VERIFIER not in identity.roles:
                raise RuleViolation('verifier not authorized')
            operators.append(identity.operator)
        if len(set(operators)) != len(members) or set(operators)&excluded:
            raise RuleViolation('verifier conflict of interest')
        from .assignments import require_assignment
        subjects=tuple(sorted(a for a in self.registry.ids if self.registry.get(a).operator in excluded))
        require_assignment(self.registry,self.chain,"verification",project,members,height,subjects)
        self._treasury.reserve_and_grant(project,tranches)
        self._policies[project]=(members,threshold,excluded,subjects)

    def release(self, approval, signatures, height):
        if (type(height) is not int or height < 0 or approval.chain != self.chain
                or any(type(n) is not int or n < 0 for n in
                       (approval.index,approval.amount,approval.valid_from,approval.expires))
                or not approval.valid_from <= height < approval.expires
                or not isinstance(approval.evidence,str) or len(approval.evidence) != 64
                or any(c not in '0123456789abcdef' for c in approval.evidence)):
            raise RuleViolation('invalid milestone approval')
        project=approval.project
        if project not in self._policies:
            raise RuleViolation('unknown project')
        members,threshold,excluded,subjects=self._policies[project]
        from .assignments import require_assignment
        require_assignment(self.registry,self.chain,"verification",project,members,height,subjects)
        index=self._treasury.paid_idx[project]
        if (approval.index != index or index >= len(self._treasury.tranches[project])
                or approval.amount != self._treasury.tranches[project][index]):
            raise RuleViolation('wrong tranche or replay')
        operators=set()
        for member,sig in signatures.items():
            identity=self.registry.get(member)
            if (member not in members or identity.status is not Status.ACTIVE
                    or not self.registry.can(member,"VERIFY",height)[0]
                    or identity.operator in excluded or identity.operator in operators
                    or not isinstance(sig,str)
                    or not self.keyring.verify(member,approval.message(),sig)):
                raise RuleViolation('invalid or conflicted verifier signature')
            operators.add(identity.operator)
        if len(operators) < threshold:
            raise RuleViolation('insufficient independent signatures')
        amount=self._treasury.release_next(project,len(operators),threshold,height)
        self._treasury.assert_invariants()
        return amount

    def pause(self, council_member, project, height, duration, reason):
        return self._emergency.pause(council_member,project,height,duration,reason)

    def ratify_pause(self, actor, project, height, extend_to):
        return self._emergency.ratify(actor,project,height,extend_to)

    def snapshot(self):
        import copy
        return copy.deepcopy(self._treasury)
