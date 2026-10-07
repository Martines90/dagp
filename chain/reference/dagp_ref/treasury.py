"""Credit ledger and milestone escrow. Conservation and cap invariants are checked by tests."""
from __future__ import annotations

from dataclasses import dataclass, field


class RuleViolation(Exception):
    pass


def _integer(n, minimum=0):
    if type(n) is not int or n < minimum:
        raise RuleViolation("amount must be an integer within bounds")


def _budget(tranches):
    if not tranches:
        raise RuleViolation("budget requires positive tranches")
    for n in tranches:
        _integer(n, 1)
    return sum(tranches)


@dataclass
class CreditLedger:
    balance: dict = field(default_factory=dict)
    debt: dict = field(default_factory=dict)
    month: tuple | None = None
    eligible_parties: frozenset | None = None

    def grant(self, party: str, n: int) -> None:
        _integer(n)
        # Debt is repaid first, so a failed project's penalty cannot be dodged by waiting.
        owed = self.debt.get(party, 0)
        pay = min(owed, n)
        self.debt[party] = owed - pay
        allowed=self.eligible_parties is None or party in self.eligible_parties
        self.balance[party] = self.balance.get(party, 0) + (n-pay if allowed else 0)

    def spend(self, party: str, n: int) -> None:
        _integer(n, 1)
        if self.eligible_parties is not None and party not in self.eligible_parties:
            raise RuleViolation("party is not in the current parliament")
        if self.balance.get(party, 0) < n:
            raise RuleViolation("insufficient credits")
        self.balance[party] -= n

    def penalize(self, party: str, n: int) -> None:
        _integer(n)
        take = min(self.balance.get(party, 0), n)
        self.balance[party] = self.balance.get(party, 0) - take
        self.debt[party] = self.debt.get(party, 0) + (n - take)


@dataclass
class Treasury:
    free: int
    reserved: dict = field(default_factory=dict)    # project -> amount held while its vote is open
    escrow: dict = field(default_factory=dict)      # project -> remaining locked
    granted: dict = field(default_factory=dict)     # project -> total approved
    released: dict = field(default_factory=dict)    # project -> total paid out
    tranches: dict = field(default_factory=dict)    # project -> list[int]
    milestone_conditions: dict = field(default_factory=dict)  # reviewed immutable acceptance records
    paid_idx: dict = field(default_factory=dict)    # project -> next tranche index
    terminated: set = field(default_factory=set)
    paused_until: dict = field(default_factory=dict)  # project -> height; 0/absent = running
    _initial_total: int = 0

    def __post_init__(self):
        _integer(self.free)
        self._initial_total = self.free

    def total(self) -> int:
        return (self.free + sum(self.reserved.values()) + sum(self.escrow.values())
                + sum(self.released.values()))

    # --- D-02: reserve at vote-open so concurrent votes cannot jointly exceed the treasury ---
    def reserve(self, project: str, amount: int) -> None:
        _integer(amount, 1)
        if project in self.reserved or project in self.granted:
            raise RuleViolation("project already reserved or funded")
        if amount <= 0 or amount > self.free:
            raise RuleViolation("cannot reserve")
        self.free -= amount
        self.reserved[project] = amount

    def release_reservation(self, project: str) -> int:
        amt = self.reserved.pop(project, None)
        if amt is None:
            raise RuleViolation("no reservation")
        self.free += amt
        return amt

    def commit_reserved(self, project: str, tranches: list[int]) -> None:
        """Convert a reservation into an escrow. Tranches may total less than the ceiling
        (the difference returns to free); never more."""
        if project not in self.reserved:
            raise RuleViolation("no reservation")
        amount = _budget(tranches)
        ceiling = self.reserved[project]
        if project in self.granted or amount > ceiling:
            raise RuleViolation("already funded or tranches exceed reservation")
        # Every check precedes mutation; never call a helper that can refuse mid-commit.
        del self.reserved[project]
        self.free += ceiling - amount
        self._grant(project, tranches, amount)

    def reserve_and_grant(self, project: str, tranches: list[int]) -> None:
        amount = _budget(tranches)
        if project in self.granted or project in self.reserved:
            raise RuleViolation("project already funded or reserved")
        if amount > self.free:
            raise RuleViolation("unfundable budget")
        self.free -= amount
        self._grant(project, tranches, amount)

    def _grant(self, project, tranches, amount):
        self.escrow[project] = amount
        self.granted[project] = amount
        self.released[project] = 0
        self.tranches[project] = list(tranches)
        self.paid_idx[project] = 0

    def release_next(self, project: str, attestations: int, threshold: int,
                     height: int | None = None) -> int:
        _integer(attestations)
        _integer(threshold, 1)
        if project not in self.granted:
            raise RuleViolation("unknown project")
        if self.paused_until.get(project, 0) and height is None:
            raise RuleViolation("height required for a project with a pause history")
        if height is not None:
            _integer(height)
        if project in self.terminated:
            raise RuleViolation("project terminated")
        if height is not None and height < self.paused_until.get(project, 0):
            raise RuleViolation("project paused")
        if attestations < threshold:
            raise RuleViolation("insufficient milestone attestations")
        i = self.paid_idx[project]
        if i >= len(self.tranches[project]):
            raise RuleViolation("no tranche left")
        amt = self.tranches[project][i]
        self.escrow[project] -= amt
        self.released[project] += amt
        self.paid_idx[project] = i + 1
        return amt

    def terminate(self, project: str) -> int:
        """Unspent escrow returns to the treasury; nothing already released is clawed back
        here (clawback of misused funds is a judicial remedy, not an automatic one)."""
        if project in self.terminated:
            raise RuleViolation("already terminated")
        back = self.escrow[project]
        self.escrow[project] = 0
        self.free += back
        self.terminated.add(project)
        return back

    def assert_invariants(self) -> None:
        assert self.total() == self._initial_total, "conservation violated"
        for pr in self.granted:
            assert self.released[pr] <= self.granted[pr]
            assert self.escrow[pr] >= 0
            assert self.escrow[pr] + self.released[pr] <= self.granted[pr]
