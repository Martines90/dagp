"""Party qualification, 4/2/1 ballots, and points -> proposal-credit allocation."""
from __future__ import annotations

from dataclasses import dataclass

from .params import BPS, Params


def endorsement_requirement(population: int, p: Params) -> int:
    """Frozen to an absolute number at cycle start (ceil, so 9.1% of 1100 -> 101 not 100;
    callers who want the DAGP figure of exactly 100 should set it explicitly)."""
    return -(-population * p.endorse_bps // BPS)


def qualify_parties(members: dict[str, set], endorsements: dict[str, set], required: int,
                    p: Params, eligible: set | None = None) -> tuple[list[str], list[str]]:
    """Returns (qualified, problems). Each agent endorses at most `endorsements_per_agent`
    distinct parties and belongs to at most one party; violating agents are dropped
    entirely from the count (fail closed) and reported."""
    problems: list[str] = []
    if eligible is not None:
        unknown = set().union(*members.values(), *endorsements.values()) - eligible
        if unknown:
            problems.append(f"ineligible supporters excluded: {sorted(unknown)}")
        members = {q: set(ms) & eligible for q, ms in members.items()}
        endorsements = {q: set(es) & eligible for q, es in endorsements.items()}
    seen_member: dict[str, str] = {}
    bad_members: set[str] = set()
    for party, ms in members.items():
        for m in ms:
            if m in seen_member and seen_member[m] != party:
                bad_members.add(m)
            seen_member[m] = party
    per_agent: dict[str, list[str]] = {}
    for party, es in endorsements.items():
        for e in es:
            per_agent.setdefault(e, []).append(party)
    over = {a for a, ps in per_agent.items() if len(ps) > p.endorsements_per_agent}
    if bad_members:
        problems.append(f"multi-party members excluded: {sorted(bad_members)}")
    if over:
        problems.append(f"over-endorsing agents excluded: {sorted(over)}")
    qualified = []
    for party in sorted(members):
        m = len(members[party] - bad_members)
        e = len(endorsements.get(party, set()) - over)
        if m >= p.min_party_members and e >= required:
            qualified.append(party)
    return qualified, problems


def valid_ballot(picks: tuple, qualified: list[str], p: Params) -> bool:
    return (isinstance(picks, (tuple, list)) and all(isinstance(x, str) for x in picks)
            and len(picks) == min(len(p.ballot_picks),len(qualified))
            and len(set(picks)) == len(picks)
            and all(x in qualified for x in picks))


@dataclass(frozen=True)
class ElectionResult:
    valid: bool
    reason: str
    points: dict
    total_points: int
    credits: dict
    invalid_ballots: int
    governing_parties: tuple = ()


def allocate_credits(points: dict, total: int, p: Params) -> dict:
    credits = {}
    for party, pts in points.items():
        share_bps = pts * BPS // total  # floor: never rounds a party UP past a threshold
        if share_bps < p.party_threshold_bps:
            credits[party] = 0
        else:
            credits[party] = min(p.credit_cap, share_bps // p.credit_step_bps)
    if sum(credits.values()) < p.min_total_credits:
        # D-04 fallback: top parties by points (ties broken by party id) get floor credits.
        order = sorted(points, key=lambda q: (-points[q], q))
        for q in order[: p.min_total_credits]:
            credits[q] = max(credits[q], p.floor_credits_each)
    return credits


def run_election(ballots: list[tuple], qualified: list[str], p: Params) -> ElectionResult:
    if len(qualified) < p.min_qualified_parties:
        return ElectionResult(False, "TOO_FEW_PARTIES", {}, 0, {}, 0)
    points = {q: 0 for q in qualified}
    bad = 0
    for picks in ballots:
        if not valid_ballot(picks, qualified, p):
            bad += 1
            continue
        for party, pts in zip(picks, p.ballot_picks):
            points[party] += pts
    total = sum(points.values())
    if total == 0:
        return ElectionResult(False, "NO_VALID_BALLOTS", points, 0, {}, bad)

    return result_from_points(points,total,bad,p)


def result_from_points(points,total,bad,p):
    """Parliament eligibility is separate from receiving a positive credit allowance."""
    governing=tuple(sorted(q for q,n in points.items() if n*BPS>=total*p.party_threshold_bps))
    credits=allocate_credits(points,total,p)
    return ElectionResult(bool(governing),'OK' if governing else 'NO_PARLIAMENT_PARTIES',points,total,credits,bad,governing)
