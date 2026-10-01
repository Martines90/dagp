"""Sharded tally and Merkle electorate: constant work per shard, O(log N) proofs, any N.

Design: ballots are partitioned by shard = H(voter) mod S. Each shard produces a ShardSummary
(counts, weights, Merkle root of its ballot leaves). The chain adds S small summaries; it never
touches N ballots in one step. Anyone can audit one shard by recomputation; a wrong summary is
a self-contained fraud proof (the shard's ballots + root). The same `decide()` function gives
the outcome, so sharded and direct tallies are identical by construction (and by test).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .crypto_sim import H, MerkleTree, merkle_root
from .election import run_election
from .params import Params
from .tally import ABSTAIN, NO, YES, Ballot, Kind, Outcome, TallyResult, decide, min_weight
from .treasury import RuleViolation


def shard_count(expected_voters: int, p: Params) -> int:
    """Smallest power of two with <= shard_target expected ballots per shard."""
    s = 1
    while s * p.shard_target < expected_voters:
        s *= 2
    return s


def shard_of(voter: str, shards: int) -> int:
    return int.from_bytes(H(b"shard", voter)[:8], "big") % shards


def ballot_leaf(b: Ballot) -> bytes:
    return H(b.voter, b.choice, b.weight)


@dataclass(frozen=True)
class ShardSummary:
    shard: int
    count: int
    yes_w: int
    no_w: int
    abstain_n: int
    root: bytes


def summarize_shard(shard: int, shards: int, ballots: Iterable[Ballot], p: Params) -> ShardSummary:
    seen, y, n, a, leaves = set(), 0, 0, 0, []
    mw = min_weight(p)
    for b in sorted(ballots, key=lambda x: x.voter):
        if shard_of(b.voter, shards) != shard:
            raise RuleViolation("ballot in wrong shard")
        if b.voter in seen:
            raise RuleViolation("duplicate voter")
        if b.choice not in (YES, NO, ABSTAIN) or b.weight < mw:
            raise RuleViolation("malformed ballot")
        seen.add(b.voter)
        leaves.append(ballot_leaf(b))
        if b.choice == YES:
            y += b.weight
        elif b.choice == NO:
            n += b.weight
        else:
            a += 1
    return ShardSummary(shard, len(leaves), y, n, a, merkle_root(leaves))


def audit_shard(summary: ShardSummary, shards: int, ballots: Iterable[Ballot], p: Params) -> bool:
    """True iff the published summary equals the recomputation (a False is a fraud proof)."""
    try:
        return summarize_shard(summary.shard, shards, ballots, p) == summary
    except RuleViolation:
        return False


def tally_sharded(summaries: list[ShardSummary], shards: int, electorate: int, kind: Kind,
                  p: Params) -> tuple[TallyResult, bytes]:
    """Returns (result, global commitment = Merkle root over shard roots)."""
    if sorted(s.shard for s in summaries) != list(range(shards)):
        return TallyResult(Outcome.INVALID, 0, 0, 0, 0, False), b""
    part = sum(s.count for s in summaries)
    if part > electorate or electorate <= 0:
        return TallyResult(Outcome.INVALID, 0, 0, 0, 0, False), b""
    ordered = sorted(summaries, key=lambda s: s.shard)
    res = decide(sum(s.yes_w for s in ordered), sum(s.no_w for s in ordered),
                 sum(s.abstain_n for s in ordered), part, electorate, kind, p)
    return res, merkle_root([s.root for s in ordered])


# ---------------------------------------------------------------- electorate snapshot
class Electorate:
    """Merkle commitment over the sorted eligible ids. The session stores only (root, P);
    voters present an O(log N) inclusion proof."""

    def __init__(self, ids: Iterable[str]):
        self.ids = sorted(set(ids))
        self._index = {a: i for i, a in enumerate(self.ids)}
        self._tree = MerkleTree([a.encode() for a in self.ids])
        self.size = len(self.ids)

    @property
    def root(self) -> bytes:
        return self._tree.root

    def proof(self, agent: str):
        if agent not in self._index:
            raise RuleViolation("not in electorate")
        return self._tree.proof(self._index[agent])


# ---------------------------------------------------------------- sharded election points
@dataclass(frozen=True)
class ElectionShard:
    points: tuple    # sorted ((party, pts), ...)
    invalid: int
    count: int


def summarize_election_shard(picks_by_voter: dict[str, tuple], qualified: list[str],
                             p: Params) -> ElectionShard:
    from .election import valid_ballot
    pts: dict[str, int] = {q: 0 for q in qualified}
    bad = 0
    for _, picks in sorted(picks_by_voter.items()):
        if not valid_ballot(picks, qualified, p):
            bad += 1
            continue
        for party, w in zip(picks, p.ballot_picks):
            pts[party] += w
    return ElectionShard(tuple(sorted(pts.items())), bad, len(picks_by_voter))


def election_from_shards(shards: list[ElectionShard], qualified: list[str], p: Params):
    """Expand shard point totals into the same allocation run_election produces."""
    from .election import ElectionResult
    from .params import BPS
    if len(qualified) < p.min_qualified_parties:
        return ElectionResult(False, "TOO_FEW_PARTIES", {}, 0, {}, 0)
    points = {q: 0 for q in qualified}
    bad = 0
    for s in shards:
        bad += s.invalid
        for q, v in s.points:
            points[q] += v
    total = sum(points.values())
    if total == 0:
        return ElectionResult(False, "NO_VALID_BALLOTS", points, 0, {}, bad)
    # Delegate the points->credits step to the one implementation: synthesize equivalent input.
    from .election import allocate_credits
    return ElectionResult(True, "OK", points, total, allocate_credits(points, total, p), bad)
