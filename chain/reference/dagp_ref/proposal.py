"""Proposal lifecycle (legal-transition table) and the refinement rule."""
from __future__ import annotations

from dataclasses import dataclass

from .treasury import RuleViolation

TRANSITIONS = {
    "DRAFT": {"IN_DELIBERATION", "WITHDRAWN"},
    "IN_DELIBERATION": {"EXAMINATION", "WITHDRAWN", "VOIDED"},
    "EXAMINATION": {"VOTING", "VOIDED"},
    "VOTING": {"CHALLENGE_WINDOW", "VOIDED"},
    "CHALLENGE_WINDOW": {"APPROVED", "REJECTED", "VOIDED"},
    "APPROVED": {"FUNDED", "APPROVED_UNFUNDED"},
    "APPROVED_UNFUNDED": {"FUNDED", "EXPIRED"},
    "FUNDED": {"EXECUTING"},
    "EXECUTING": {"PAUSED", "CORRECTIVE_VOTE", "COMPLETED", "TERMINATED"},
    "PAUSED": {"EXECUTING", "TERMINATED"},
    "CORRECTIVE_VOTE": {"EXECUTING", "TERMINATED"},
    "COMPLETED": {"OUTCOME_REVIEW"},
    "TERMINATED": {"OUTCOME_REVIEW"},
    "OUTCOME_REVIEW": {"CLOSED_SUCCESS", "CLOSED_FAILURE"},
    "REJECTED": set(), "WITHDRAWN": set(), "VOIDED": set(), "EXPIRED": set(),
    "CLOSED_SUCCESS": set(), "CLOSED_FAILURE": set(),
}


@dataclass(frozen=True)
class Envelope:
    """The immutable 'core commitment' fixed when the credit is spent."""
    objective_hash: str
    result_hash: str
    caps: tuple  # ((resource, max_amount), ...) sorted by resource


def amendment_is_refinement(orig: Envelope, amended: Envelope) -> bool:
    """On-chain *structural* half of the refinement rule: same objective and result commitments,
    and no resource line above its original cap, no new resource kinds. Whether a narrowing
    still 'means the same project' is a semantic question decided by a jury on challenge."""
    if orig.objective_hash != amended.objective_hash or orig.result_hash != amended.result_hash:
        return False
    for envelope in (orig, amended):
        if (len({k for k, _ in envelope.caps}) != len(envelope.caps)
                or any(not isinstance(k,str) or not k or type(v) is not int or v < 0
                       for k,v in envelope.caps)):
            return False
    o = dict(orig.caps)
    return all(k in o and v <= o[k] for k, v in amended.caps)


@dataclass
class Proposal:
    id: str
    state: str = "DRAFT"

    def move(self, to: str) -> None:
        if to not in TRANSITIONS[self.state]:
            raise RuleViolation(f"illegal transition {self.state} -> {to}")
        self.state = to


class FilingRegistry:
    """D-12: the same objective cannot be re-filed within `cooldown` heights of its last filing,
    so a defeated or refunded proposal cannot be used to spam the voters' attention."""

    def __init__(self, cooldown: int):
        self.cooldown = cooldown
        self.last: dict[str, int] = {}

    def file(self, objective_hash: str, height: int) -> None:
        prev = self.last.get(objective_hash)
        if prev is not None and height - prev < self.cooldown:
            raise RuleViolation("objective re-filed inside the cooldown")
        self.last[objective_hash] = height
