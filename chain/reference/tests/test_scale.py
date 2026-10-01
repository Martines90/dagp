import random
import time
import unittest
from fractions import Fraction
from math import comb

from dagp_ref.crypto_sim import MerkleTree, SimKeyring, H, merkle_root, verify_proof
from dagp_ref.election import run_election
from dagp_ref.params import BPS, Params
from dagp_ref.scale import (Electorate, audit_shard, election_from_shards, shard_count, shard_of,
                            summarize_election_shard, summarize_shard, tally_sharded)
from dagp_ref.sortition import audit_sample_size, draw, panel_size, threshold
from dagp_ref.tally import ABSTAIN, NO, YES, Ballot, Kind, Outcome, tally
from dagp_ref.treasury import RuleViolation

P = Params(shard_target=1000)


class Sortition(unittest.TestCase):
    ids = [f"e{i}" for i in range(500)]

    def test_deterministic_order_independent_and_sized(self):
        a = draw(b"seed", self.ids, 7)
        b = draw(b"seed", reversed(self.ids), 7)
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), 7)
        self.assertNotEqual(a, draw(b"other", self.ids, 7))

    def test_exclusion_and_bad_k(self):
        a = draw(b"s", self.ids, 5)
        b = draw(b"s", self.ids, 5, exclude=set(a))
        self.assertFalse(set(a) & set(b))
        with self.assertRaises(ValueError):
            draw(b"s", self.ids, 0)

    def test_roughly_uniform(self):
        counts = {i: 0 for i in range(10)}
        pool = [f"x{i}" for i in range(10)]
        for s in range(2000):
            counts[pool.index(draw(str(s).encode(), pool, 1)[0])] += 1
        self.assertTrue(all(120 < c < 280 for c in counts.values()), counts)

    def test_candidate_added_after_seed_cannot_be_predicted_but_is_just_a_hash(self):
        # Anyone can verify membership: a winner's score is below every non-winner's score.
        from dagp_ref.sortition import score
        w = draw(b"s", self.ids, 5)
        worst = max(score(b"s", x) for x in w)
        self.assertTrue(all(score(b"s", x) > worst for x in self.ids if x not in w))


class PanelMath(unittest.TestCase):
    def test_size_meets_target_with_independent_float_check(self):
        g = panel_size(2000, 1_000_000)
        self.assertEqual(g % 2, 1)
        f = 0.2
        tail = sum(comb(g, i) * f ** i * (1 - f) ** (g - i) for i in range(g // 2 + 1, g + 1))
        self.assertLess(tail, 1e-6)
        g2 = g - 2
        tail2 = sum(comb(g2, i) * f ** i * (1 - f) ** (g2 - i) for i in range(g2 // 2 + 1, g2 + 1))
        self.assertGreaterEqual(tail2, 1e-6)       # minimal: the next smaller odd size fails

    def test_monotone_in_adversary_and_target(self):
        sizes = [panel_size(b, 1_000_000) for b in (500, 1000, 2000, 3000)]
        self.assertEqual(sizes, sorted(sizes))
        self.assertLessEqual(panel_size(2000, 1000), panel_size(2000, 1_000_000_000))

    def test_requires_honest_majority(self):
        with self.assertRaises(ValueError):
            panel_size(5000, 1000)
        with self.assertRaises(ValueError):
            panel_size(4900, 10 ** 12, max_size=11)

    def test_threshold_is_strict_majority(self):
        self.assertEqual([threshold(g) for g in (5, 7, 31)], [3, 4, 16])

    def test_board_size_is_independent_of_population(self):
        # The function has no population argument at all: a million citizens need the same board.
        self.assertEqual(panel_size(2000, 10 ** 6), panel_size(2000, 10 ** 6))
        self.assertLess(panel_size(2000, 10 ** 6), 60)


class AuditSampling(unittest.TestCase):
    def test_sample_size_property(self):
        n = audit_sample_size(100, 1000)                # catch 1% cheating, miss <= 0.1%
        keep = BPS - 100
        self.assertLessEqual(Fraction(keep, BPS) ** n, Fraction(1, 1000))
        self.assertGreater(Fraction(keep, BPS) ** (n - 1), Fraction(1, 1000))
        self.assertTrue(600 < n < 800)

    def test_extremes(self):
        self.assertEqual(audit_sample_size(BPS, 10 ** 9), 1)
        with self.assertRaises(ValueError):
            audit_sample_size(0, 10)

    def test_simulated_detection_rate(self):
        rng = random.Random(9)
        n = audit_sample_size(500, 100)                 # 5% cheaters, miss <= 1%
        misses = 0
        for _ in range(2000):
            pop = [rng.random() < 0.05 for _ in range(n)]
            misses += not any(pop)
        self.assertLess(misses / 2000, 0.03)


class Merkle(unittest.TestCase):
    def test_all_sizes_prove_and_verify(self):
        for n in range(1, 41):
            leaves = [f"l{i}".encode() for i in range(n)]
            t = MerkleTree(leaves)
            for i in range(n):
                self.assertTrue(verify_proof(t.root, leaves[i], t.proof(i)), (n, i))

    def test_tamper_and_wrong_leaf_fail(self):
        leaves = [f"l{i}".encode() for i in range(17)]
        t = MerkleTree(leaves)
        pr = t.proof(5)
        self.assertFalse(verify_proof(t.root, b"l6", pr))
        bad = [(H(b"x"), r) for _, r in pr]
        self.assertFalse(verify_proof(t.root, leaves[5], bad))
        self.assertFalse(verify_proof(MerkleTree(leaves[:-1]).root, leaves[5], pr))
        with self.assertRaises(IndexError):
            t.proof(17)

    def test_leaf_and_node_domains_are_separated(self):
        a, b = b"a", b"b"
        two = MerkleTree([a, b]).root
        self.assertNotEqual(two, MerkleTree([two]).root)   # second-preimage style confusion fails
        self.assertEqual(MerkleTree([]).root, MerkleTree([]).root)

    def test_proof_size_is_logarithmic_at_100k(self):
        ids = [f"agent{i}" for i in range(100_000)]
        el = Electorate(ids)
        self.assertEqual(el.size, 100_000)
        pr = el.proof("agent77777")
        self.assertLessEqual(len(pr), 17)
        self.assertTrue(verify_proof(el.root, b"agent77777", pr))
        self.assertFalse(verify_proof(el.root, b"outsider", pr))
        with self.assertRaises(RuleViolation):
            el.proof("outsider")

    def test_keyring_rejects_unknown_forged_and_duplicate(self):
        kr = SimKeyring()
        kr.register("a")
        with self.assertRaises(ValueError):
            kr.register("a")
        s = kr.sign("a", b"m")
        self.assertTrue(kr.verify("a", b"m", s))
        self.assertFalse(kr.verify("a", b"m2", s))
        self.assertFalse(kr.verify("ghost", b"m", s))


def groups(ballots, shards):
    g = [[] for _ in range(shards)]
    for b in ballots:
        g[shard_of(b.voter, shards)].append(b)
    return g


class ShardedTally(unittest.TestCase):
    def random_ballots(self, n, seed):
        rng = random.Random(seed)
        return [Ballot(f"v{i}", rng.choice([YES, YES, NO, ABSTAIN]), rng.randint(3, 13)) for i in range(n)]

    def test_sharded_equals_direct_for_all_kinds(self):
        for seed in range(6):
            ballots = self.random_ballots(8000, seed)
            e = 12_000
            s = shard_count(e, P)
            sums = [summarize_shard(i, s, g, P) for i, g in enumerate(groups(ballots, s))]
            for kind in Kind:
                res, _ = tally_sharded(sums, s, e, kind, P)
                self.assertEqual(res, tally(ballots, e, kind, P), (seed, kind))

    def test_shard_count_grows_with_population_not_work_per_shard(self):
        self.assertEqual(shard_count(500, P), 1)
        self.assertEqual(shard_count(1000, P), 1)
        self.assertEqual(shard_count(1001, P), 2)
        self.assertEqual(shard_count(1_000_000, P), 1024)
        self.assertEqual(shard_count(1_000_000, Params()), 128)

    def test_commitment_is_order_independent_and_changes_with_any_ballot(self):
        ballots = self.random_ballots(3000, 1)
        s = shard_count(4000, P)
        def commit(bs):
            sums = [summarize_shard(i, s, g, P) for i, g in enumerate(groups(bs, s))]
            return tally_sharded(sums, s, 4000, Kind.ORDINARY, P)[1]
        c1 = commit(ballots)
        random.Random(2).shuffle(ballots)
        self.assertEqual(c1, commit(ballots))
        ballots[0] = Ballot(ballots[0].voter, NO if ballots[0].choice != NO else YES, ballots[0].weight)
        self.assertNotEqual(c1, commit(ballots))

    def test_fraud_proof_detects_wrong_summary(self):
        ballots = self.random_ballots(5000, 3)
        s = shard_count(6000, P)
        g = groups(ballots, s)
        good = summarize_shard(2, s, g[2], P)
        self.assertTrue(audit_shard(good, s, g[2], P))
        from dataclasses import replace
        lie = replace(good, yes_w=good.yes_w + 1)
        self.assertFalse(audit_shard(lie, s, g[2], P))
        self.assertFalse(audit_shard(good, s, g[2][1:], P))          # dropped ballot
        self.assertFalse(audit_shard(good, s, g[3], P))              # wrong shard's ballots

    def test_malformed_inputs_rejected(self):
        b = Ballot("v1", YES, 3)
        s = 2
        sh = shard_of("v1", s)
        with self.assertRaises(RuleViolation):
            summarize_shard(1 - sh, s, [b], P)                      # wrong shard
        with self.assertRaises(RuleViolation):
            summarize_shard(sh, s, [b, b], P)                       # duplicate
        with self.assertRaises(RuleViolation):
            summarize_shard(sh, s, [Ballot("v1", "?", 3)], P)
        with self.assertRaises(RuleViolation):
            summarize_shard(sh, s, [Ballot("v1", YES, 1)], P)       # below base weight

    def test_missing_or_extra_shard_and_overcount_invalid(self):
        s = 4
        sums = [summarize_shard(i, s, [], P) for i in range(s)]
        self.assertEqual(tally_sharded(sums[:3], s, 10, Kind.ORDINARY, P)[0].outcome, Outcome.INVALID)
        self.assertEqual(tally_sharded(sums, s, 0, Kind.ORDINARY, P)[0].outcome, Outcome.INVALID)
        # more ballots than electorate
        ballots = [Ballot(f"v{i}", YES, 3) for i in range(50)]
        ss = [summarize_shard(i, s, g, P) for i, g in enumerate(groups(ballots, s))]
        self.assertEqual(tally_sharded(ss, s, 10, Kind.ORDINARY, P)[0].outcome, Outcome.INVALID)

    def test_one_million_voters(self):
        """End-to-end tally at 1,000,000 voters through the production path."""
        n, p = 1_000_000, Params()             # shard_target 10_000 -> 128 shards
        s = shard_count(n, p)
        t0 = time.time()
        buckets = [[] for _ in range(s)]
        yes_w = no_w = abst = 0
        for i in range(n):
            ch = YES if i % 10 < 6 else (NO if i % 10 < 9 else ABSTAIN)   # 60/30/10
            w = 3 + (i % 5)
            v = f"agent{i}"
            buckets[shard_of(v, s)].append(Ballot(v, ch, w))
            if ch == YES:
                yes_w += w
            elif ch == NO:
                no_w += w
            else:
                abst += 1
        sums = [summarize_shard(i, s, b, p) for i, b in enumerate(buckets)]
        res, commit = tally_sharded(sums, s, n, Kind.ORDINARY, p)
        dt = time.time() - t0
        self.assertEqual((res.yes_w, res.no_w, res.abstain_n, res.participation), (yes_w, no_w, abst, n))
        self.assertEqual(res.outcome, Outcome.PASSED)
        self.assertEqual(len(commit), 32)
        # Work per shard is bounded; the chain itself only adds `s` tiny summaries.
        self.assertLess(max(x.count for x in sums), 2 * p.shard_target)
        print(f"\n[scale] 1,000,000 ballots, {s} shards tallied in {dt:.1f}s; max shard={max(x.count for x in sums)}")


class ShardedElection(unittest.TestCase):
    def test_equals_run_election(self):
        rng = random.Random(4)
        parties = [f"P{i}" for i in range(8)]
        picks = {f"v{i}": tuple(rng.sample(parties, 3)) for i in range(5000)}
        picks["bad1"] = ("P0", "P0", "P1")
        picks["bad2"] = ("P0", "P1")
        p = Params()
        direct = run_election(list(picks.values()), parties, p)
        s = 8
        parts = [dict() for _ in range(s)]
        for v, pk in picks.items():
            parts[shard_of(v, s)][v] = pk
        shards = [summarize_election_shard(x, parties, p) for x in parts]
        self.assertEqual(election_from_shards(shards, parties, p), direct)

    def test_edge_results(self):
        p = Params()
        self.assertEqual(election_from_shards([], ["A", "B"], p).reason, "TOO_FEW_PARTIES")
        sh = summarize_election_shard({"v": ("A", "A", "B")}, ["A", "B", "C"], p)
        self.assertEqual(election_from_shards([sh], ["A", "B", "C"], p).reason, "NO_VALID_BALLOTS")


if __name__ == "__main__":
    unittest.main()
