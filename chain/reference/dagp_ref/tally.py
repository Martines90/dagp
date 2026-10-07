"""Deterministic decision rules for proposals and multi-point bills (integer arithmetic only).

`decide()` is the single decision function; both the direct path (`tally`) and the sharded
path (`scale.tally_sharded`) call it, so there is one definition of "passed" at any scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .params import BPS, Params

YES, NO, ABSTAIN = "Y", "N", "A"


class Outcome(str, Enum):
    PASSED = "PASSED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NO_QUORUM = "NO_QUORUM"
    NO_DECISIVE_VOTES = "NO_DECISIVE_VOTES"  # only abstentions (Yw + Nw == 0)
    INVALID = "INVALID"


class Kind(str, Enum):
    FORMATION = "FORMATION"
    MERGER = "MERGER"
    PARAMETER = "PARAMETER"
    ORDINARY = "ORDINARY"
    CONSTITUTIONAL = "CONSTITUTIONAL"
    EARLY_ELECTION = "EARLY_ELECTION"
    CORE = "CORE"


@dataclass(frozen=True, slots=True)
class Ballot:
    voter: str
    choice: str
    weight: int  # already computed; must be >= 1 (FLAT) or >= base_weight (WEIGHTED)


@dataclass(frozen=True)
class TallyResult:
    outcome: Outcome
    participation: int
    yes_w: int
    no_w: int
    abstain_n: int
    review_flag: bool


def weight(read_articles: int, p: Params) -> int:
    """W = 3 + min(R, cap) in WEIGHTED mode; 1 in FLAT mode. Caller has passed the gate."""
    if read_articles < 0:
        raise ValueError("R must be non-negative")
    if p.weight_mode == "FLAT":
        return 1
    return p.base_weight + min(read_articles, p.max_articles_counted)


def max_weight(p: Params) -> int:
    return 1 if p.weight_mode == "FLAT" else p.base_weight + p.max_articles_counted


def min_weight(p: Params) -> int:
    return 1 if p.weight_mode == "FLAT" else p.base_weight


def _threshold(kind: Kind, p: Params) -> tuple[tuple[int, int], bool]:
    """Returns ((num, den), strict). Ordinary is strictly-greater; the others are at-least."""
    if kind is Kind.PARAMETER:
        return (p.parameter_approval_bps,BPS),False
    if kind is Kind.CONSTITUTIONAL:
        return (p.constitutional_approval_bps,BPS),False
    if kind is Kind.ORDINARY:
        return p.ordinary, True
    if kind is Kind.CORE:
        return p.core, False
    return p.supermajority, False


def decide(yes_w: int, no_w: int, abst: int, part: int, electorate: int, kind: Kind,
           p: Params, *, yes_n: int | None = None, abstain_w: int | None = None) -> TallyResult:
    if (any(type(n) is not int or n < 0 for n in (yes_w, no_w, abst, part, electorate))
            or electorate <= 0 or part > electorate or abst > part
            or not (part - abst) * min_weight(p) <= yes_w + no_w <= (part - abst) * max_weight(p)):
        return TallyResult(Outcome.INVALID, 0, 0, 0, 0, False)
    if kind in (Kind.FORMATION, Kind.MERGER):
        if (type(yes_n) is not int or type(abstain_w) is not int or not 0 <= yes_n <= part-abst
                or not yes_n*min_weight(p) <= yes_w <= yes_n*max_weight(p)
                or not (part-abst-yes_n)*min_weight(p) <= no_w <= (part-abst-yes_n)*max_weight(p)
                or not abst*min_weight(p) <= abstain_w <= abst*max_weight(p)):
            return TallyResult(Outcome.INVALID, 0, 0, 0, 0, False)
        quorum = max(p.quorum_bps, 8000 if kind is Kind.MERGER else max(5000,p.constitutional_quorum_bps))
        approval = max(8000 if kind is Kind.MERGER else 6600, p.constitutional_approval_bps)
        if part*BPS < quorum*electorate:
            outcome = Outcome.NO_QUORUM
        elif not part:
            outcome = Outcome.NO_DECISIVE_VOTES
        else:
            outcome = Outcome.PASSED if (yes_n*BPS >= approval*part and
                        yes_w*BPS >= approval*(yes_w+no_w+abstain_w)) else Outcome.FAILED
        return TallyResult(outcome, part, yes_w, no_w, abst, part > 0 and abst*BPS > p.abstain_review_bps*part)
    flag = part > 0 and abst * BPS > p.abstain_review_bps * part
    quorum=max(p.quorum_bps,p.constitutional_quorum_bps) if kind in (Kind.CONSTITUTIONAL,Kind.CORE) else p.quorum_bps
    if part * BPS < quorum * electorate:
        return TallyResult(Outcome.NO_QUORUM, part, yes_w, no_w, abst, flag)
    if yes_w + no_w == 0:
        return TallyResult(Outcome.NO_DECISIVE_VOTES, part, yes_w, no_w, abst, flag)
    (num, den), strict = _threshold(kind, p)
    lhs, rhs = yes_w * den, num * (yes_w + no_w)
    ok = lhs > rhs if strict else lhs >= rhs
    return TallyResult(Outcome.PASSED if ok else Outcome.FAILED, part, yes_w, no_w, abst, flag)


def tally(ballots: list[Ballot], electorate: int, kind: Kind, p: Params) -> TallyResult:
    voters = [b.voter for b in ballots]
    bad = TallyResult(Outcome.INVALID, 0, 0, 0, 0, False)
    if len(set(voters)) != len(voters) or electorate <= 0 or len(ballots) > electorate:
        return bad
    mw = min_weight(p)
    if any(b.choice not in (YES, NO, ABSTAIN) or type(b.weight) is not int or not mw <= b.weight <= max_weight(p) for b in ballots):
        return bad
    yes_w = sum(b.weight for b in ballots if b.choice == YES)
    no_w = sum(b.weight for b in ballots if b.choice == NO)
    abst = sum(1 for b in ballots if b.choice == ABSTAIN)
    return decide(yes_w, no_w, abst, len(ballots), electorate, kind, p,
                  yes_n=sum(b.choice == YES for b in ballots),
                  abstain_w=sum(b.weight for b in ballots if b.choice == ABSTAIN))


@dataclass(frozen=True)
class BillResult:
    outcome: Outcome
    point_outcomes: tuple
    passing_points: tuple  # indices eligible to take effect after finalization
    review_flag: bool = False


def tally_bill(point_ballots: list[list[Ballot]], electorate: int, kind: Kind,
               p: Params) -> BillResult:
    """Tally independent clauses, or an explicitly configured legacy package."""
    n = len(point_ballots)
    if n == 0 or n > p.max_bill_points:
        return BillResult(Outcome.INVALID, (), ())
    results = [tally(b, electorate, kind, p) for b in point_ballots]
    outs = tuple(r.outcome for r in results)
    review = any(r.review_flag for r in results)
    if any(r.outcome is Outcome.INVALID for r in results):
        return BillResult(Outcome.INVALID, outs, (), review)
    if p.bill_mode == "INDEPENDENT":
        passed=tuple(i for i,r in enumerate(results) if r.outcome is Outcome.PASSED)
        outcome = (Outcome.PASSED if len(passed)==n else Outcome.PARTIAL if passed else
                   Outcome.NO_QUORUM if all(r.outcome is Outcome.NO_QUORUM for r in results) else Outcome.FAILED)
        return BillResult(outcome,outs,passed,review)
    if any(r.outcome is Outcome.NO_QUORUM for r in results):
        return BillResult(Outcome.NO_QUORUM, outs, (), review)
    passed = [i for i, r in enumerate(results) if r.outcome is Outcome.PASSED]
    if p.package_fail_basis == "NO_MAJORITY":
        failing = sum(1 for r in results if r.no_w > r.yes_w)
    else:
        failing = n - len(passed)
    if 2 * failing > n or not passed:
        return BillResult(Outcome.FAILED, outs, (), review)
    return BillResult(Outcome.PASSED, outs, tuple(passed), review)
