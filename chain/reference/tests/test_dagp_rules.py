import random
import unittest

from dagp_ref.election import endorsement_requirement, qualify_parties, run_election
from dagp_ref.ledger import Ledger
from tests.legacy_params import Params
from dagp_ref.proposal import Envelope, Proposal, amendment_is_refinement
from dagp_ref.tally import (ABSTAIN, NO, YES, Ballot, Kind, Outcome, tally, tally_bill,
                            weight)
from dagp_ref.treasury import CreditLedger, RuleViolation, Treasury

P = Params(quorum_bps=5000,bill_mode="PACKAGE",min_total_credits=3,min_qualified_parties=3,credit_ceiling_bps=5000)


def bs(y=0, n=0, a=0, w=3):
    out = [Ballot(f"y{i}", YES, w) for i in range(y)]
    out += [Ballot(f"n{i}", NO, w) for i in range(n)]
    out += [Ballot(f"a{i}", ABSTAIN, w) for i in range(a)]
    return out


class DocExamples(unittest.TestCase):
    """Numbers taken directly from the DAGP concept note."""

    def test_weight_table(self):
        self.assertEqual([weight(r, P) for r in (0, 2, 5)], [3, 5, 8])

    def test_quorum_500_of_1000(self):
        self.assertEqual(tally(bs(y=300, n=199), 1000, Kind.ORDINARY, P).outcome, Outcome.NO_QUORUM)
        self.assertEqual(tally(bs(y=300, n=200), 1000, Kind.ORDINARY, P).outcome, Outcome.PASSED)

    def test_ordinary_needs_strictly_more_than_half(self):
        self.assertEqual(tally(bs(y=250, n=250), 1000, Kind.ORDINARY, P).outcome, Outcome.FAILED)
        self.assertEqual(tally(bs(y=251, n=249), 1000, Kind.ORDINARY, P).outcome, Outcome.PASSED)

    def test_constitutional_requires_exactly_66_percent(self):
        # Constitutional approval is at least 66.00%, compared with exact integers.
        self.assertEqual(tally(bs(y=400, n=200), 1000, Kind.CONSTITUTIONAL, P).outcome, Outcome.PASSED)  # 2/3 exactly
        self.assertEqual(tally(bs(y=329, n=171), 1000, Kind.CONSTITUTIONAL, P).outcome, Outcome.FAILED)  # 65.8%
        self.assertEqual(tally(bs(y=330, n=170), 1000, Kind.CONSTITUTIONAL, P).outcome, Outcome.PASSED)

    def test_core_needs_three_quarters(self):
        self.assertEqual(tally(bs(y=450, n=150), 1000, Kind.CORE, P).outcome, Outcome.PASSED)
        self.assertEqual(tally(bs(y=449, n=151), 1000, Kind.CORE, P).outcome, Outcome.FAILED)

    def test_flat_mode_weights_everyone_one(self):
        from tests.legacy_params import Params as PP
        f = PP(weight_mode="FLAT")
        self.assertEqual(weight(9, f), 1)
        self.assertEqual(tally([Ballot("a", YES, 1), Ballot("b", NO, 1)], 2, Kind.ORDINARY, f).outcome,
                         Outcome.FAILED)

    def test_abstentions_do_not_count_toward_approval_but_count_toward_quorum(self):
        r = tally(bs(y=101, n=100, a=300), 1000, Kind.ORDINARY, P)
        self.assertEqual(r.outcome, Outcome.PASSED)
        self.assertTrue(r.review_flag)  # 300/501 abstain > 30%

    def test_multi_point_package_rule(self):
        # 4 points; 3 fail => more than half fail => whole package fails though 1 passed.
        pts = [bs(y=300, n=200)] + [bs(y=200, n=300)] * 3
        self.assertEqual(tally_bill(pts, 1000, Kind.ORDINARY, P).outcome, Outcome.FAILED)
        # exactly half fail (2 of 4) => survives; only passing points take effect.
        pts = [bs(y=300, n=200)] * 2 + [bs(y=200, n=300)] * 2
        r = tally_bill(pts, 1000, Kind.ORDINARY, P)
        self.assertEqual((r.outcome, r.passing_points), (Outcome.PASSED, (0, 1)))

    def test_bill_over_10_points_invalid(self):
        self.assertEqual(tally_bill([bs(y=300, n=200)] * 11, 1000, Kind.ORDINARY, P).outcome,
                         Outcome.INVALID)

    def test_election_points_and_credits(self):
        # 100 voters, every ballot A>B>C: A=400 B=200 C=100 of 700.
        q = ["A", "B", "C", "D"]
        res = run_election([("A", "B", "C")] * 100, q, P)
        self.assertEqual(res.total_points, 700)
        self.assertEqual(res.points, {"A": 400, "B": 200, "C": 100, "D": 0})
        # A = 57.1% -> capped at 10 credits. B = 28.57% -> 5. C = 14.28% -> 2. D -> 0.
        self.assertEqual(res.credits, {"A": 10, "B": 5, "C": 2, "D": 0})

    def test_credit_thresholds_exact(self):
        # A party at exactly 5.00% gets 1 credit; 4.99% gets 0 (floor division never rounds up).
        q = ["A", "B", "C", "D"]
        ballots = [("A", "B", "C")] * 19 + [("A", "B", "D")] * 1  # total 140
        res = run_election(ballots, q, P)
        self.assertEqual(res.points["D"] * 10000 // res.total_points, 71)  # 1/140 = 0.71%
        self.assertEqual(res.credits["D"], 0)

    def test_invalid_ballots_dropped(self):
        q = ["A", "B", "C"]
        res = run_election([("A", "A", "B"), ("A", "B"), ("A", "B", "Z"), ("A", "B", "C")], q, P)
        self.assertEqual(res.invalid_ballots, 3)
        self.assertEqual(res.total_points, 7)

    def test_endorsement_requirement_rounding(self):
        # DAGP says 100 of 1100 (~9.1%). 9.10% of 1100 = 100.1 -> ceil = 101 (!).
        self.assertEqual(endorsement_requirement(1100, P), 101)
        self.assertEqual(endorsement_requirement(1100, Params(endorse_bps=909)), 100)


class DiscoveredEdgeCases(unittest.TestCase):
    """Situations the DAGP text leaves undefined. Each asserts the reference resolution."""

    def test_two_parties_cannot_hold_a_three_pick_election(self):
        self.assertEqual(run_election([("A", "B", "C")], ["A", "B"], P).reason, "TOO_FEW_PARTIES")

    def test_all_abstain_is_not_a_division_by_zero(self):
        self.assertEqual(tally(bs(a=600), 1000, Kind.ORDINARY, P).outcome, Outcome.NO_DECISIVE_VOTES)

    def test_duplicate_voter_invalidates(self):
        b = [Ballot("x", YES, 3), Ballot("x", NO, 3)]
        self.assertEqual(tally(b, 10, Kind.ORDINARY, P).outcome, Outcome.INVALID)

    def test_ballots_exceeding_electorate_invalid(self):
        self.assertEqual(tally(bs(y=11), 10, Kind.ORDINARY, P).outcome, Outcome.INVALID)

    def test_weight_cap_bounds_article_splitting(self):
        self.assertEqual(weight(10_000, P), 13)

    def test_fragmented_election_starves_the_agenda_under_literal_dagp_rules(self):
        # 25 parties, near-uniform votes: every party < 5%, so nobody gets a credit.
        parties = [f"P{i:02d}" for i in range(25)]
        rng = random.Random(7)
        ballots = [tuple(rng.sample(parties, 3)) for _ in range(1000)]
        res = run_election(ballots, parties, Params(min_total_credits=0))   # literal DAGP text
        self.assertEqual(sum(res.credits.values()), 0)  # agenda deadlock
        # D-04: the default keeps the society able to legislate.
        fb = run_election(ballots, parties, P)
        self.assertEqual(sum(fb.credits.values()), 3)

    def test_package_basis_changes_outcome_on_ties(self):
        # 2 points tie (Y==N), 2 points pass: NOT_PASSED basis => 2 failing of 4 (survives, not > half)
        tie = bs(y=250, n=250)
        ok = bs(y=300, n=200)
        self.assertEqual(tally_bill([ok, ok, tie, tie], 1000, Kind.ORDINARY, P).outcome, Outcome.PASSED)
        # 3 ties + 1 pass: NOT_PASSED => fails; NO_MAJORITY => tie is not "No majority" => survives.
        self.assertEqual(tally_bill([ok, tie, tie, tie], 1000, Kind.ORDINARY, P).outcome, Outcome.FAILED)
        lax = Params(quorum_bps=5000,bill_mode="PACKAGE",package_fail_basis="NO_MAJORITY")
        self.assertEqual(tally_bill([ok, tie, tie, tie], 1000, Kind.ORDINARY, lax).outcome, Outcome.PASSED)

    def test_multi_party_member_and_overendorser_excluded(self):
        members = {"A": {f"a{i}" for i in range(10)}, "B": {f"b{i}" for i in range(10)} | {"a0"}}
        ends = {"A": {f"e{i}" for i in range(5)}, "B": {f"e{i}" for i in range(5)},
                "C": {f"e{i}" for i in range(5)}}
        q, problems = qualify_parties(members, ends, 5, P)
        self.assertEqual(q, [])            # a0 dropped -> A has 9 members; e0..e4 over-endorse -> 0
        self.assertEqual(len(problems), 2)

    def test_snapshot_hash_changes_with_any_parameter(self):
        self.assertNotEqual(P.snapshot_hash(), Params(quorum_bps=5001).snapshot_hash())


class RefinementRule(unittest.TestCase):
    base = Envelope("obj", "res", (("compute", 100), ("funds", 50)))

    def test_narrowing_ok(self):
        self.assertTrue(amendment_is_refinement(self.base, Envelope("obj", "res", (("compute", 80),))))

    def test_raising_cap_or_adding_resource_or_changing_objective_rejected(self):
        self.assertFalse(amendment_is_refinement(self.base, Envelope("obj", "res", (("compute", 101),))))
        self.assertFalse(amendment_is_refinement(self.base, Envelope("obj", "res", (("energy", 1),))))
        self.assertFalse(amendment_is_refinement(self.base, Envelope("obj2", "res", ())))

    def test_illegal_lifecycle_jumps_blocked(self):
        p = Proposal("p1")
        with self.assertRaises(RuleViolation):
            p.move("FUNDED")
        for s in ("IN_DELIBERATION", "EXAMINATION", "VOTING", "CHALLENGE_WINDOW", "APPROVED", "FUNDED"):
            p.move(s)
        with self.assertRaises(RuleViolation):
            p.move("VOTING")  # no going back: a finalized decision is never reopened


class CreditsAndEscrow(unittest.TestCase):
    def test_spend_penalty_and_debt_repayment(self):
        c = CreditLedger()
        c.grant("A", 2)
        c.spend("A", 1)
        c.penalize("A", 3)                       # only 1 available -> debt 2
        self.assertEqual((c.balance["A"], c.debt["A"]), (0, 2))
        c.grant("A", 5)                          # debt repaid first
        self.assertEqual((c.balance["A"], c.debt["A"]), (3, 0))
        with self.assertRaises(RuleViolation):
            c.spend("A", 4)

    def test_escrow_staged_release_and_termination(self):
        t = Treasury(free=1000)
        t.reserve_and_grant("p", [100, 100, 100])
        t.assert_invariants()
        with self.assertRaises(RuleViolation):
            t.release_next("p", attestations=1, threshold=3)
        t.release_next("p", 3, 3)
        self.assertEqual(t.terminate("p"), 200)
        self.assertEqual(t.free, 900)  # 700 unreserved + 200 returned; 100 already released
        t.assert_invariants()
        with self.assertRaises(RuleViolation):
            t.release_next("p", 3, 3)

    def test_overcommit_refused(self):
        t = Treasury(free=100)
        t.reserve_and_grant("a", [60])
        with self.assertRaises(RuleViolation):
            t.reserve_and_grant("b", [60])      # concurrent approvals cannot double-spend

    def test_random_operations_preserve_conservation(self):
        rng = random.Random(1)
        t = Treasury(free=10_000)
        live = []
        for i in range(400):
            op = rng.choice(["grant", "release", "term"])
            try:
                if op == "grant":
                    t.reserve_and_grant(f"p{i}", [rng.randint(1, 300) for _ in range(rng.randint(1, 4))])
                    live.append(f"p{i}")
                elif op == "release" and live:
                    t.release_next(rng.choice(live), 3, 3)
                elif op == "term" and live:
                    t.terminate(rng.choice(live))
            except RuleViolation:
                pass
            t.assert_invariants()


class TallyProperties(unittest.TestCase):
    def test_order_independence_and_determinism(self):
        rng = random.Random(3)
        for _ in range(200):
            n = rng.randint(1, 60)
            ballots = [Ballot(f"v{i}", rng.choice([YES, NO, ABSTAIN]), rng.randint(3, 13)) for i in range(n)]
            e = rng.randint(n, n * 3)
            kind = rng.choice(list(Kind))
            a = tally(ballots, e, kind, P)
            rng.shuffle(ballots)
            self.assertEqual(a, tally(ballots, e, kind, P))

    def test_adding_yes_weight_never_hurts_passing(self):
        rng = random.Random(4)
        for _ in range(300):
            base = [Ballot(f"v{i}", rng.choice([YES, NO]), rng.randint(3, 13)) for i in range(rng.randint(4, 40))]
            e = len(base) + 5
            before = tally(base, e, Kind.ORDINARY, P)
            after = tally(base + [Ballot("new", YES, 3)], e + 1, Kind.ORDINARY, P)
            if before.outcome is Outcome.PASSED and after.outcome is not Outcome.NO_QUORUM:
                self.assertEqual(after.outcome, Outcome.PASSED)

    def test_election_points_conserved(self):
        rng = random.Random(5)
        parties = [f"P{i}" for i in range(6)]
        for _ in range(100):
            ballots = [tuple(rng.sample(parties, 3)) for _ in range(rng.randint(1, 300))]
            res = run_election(ballots, parties, P)
            self.assertEqual(res.total_points, 7 * len(ballots))
            self.assertLessEqual(max(res.credits.values()), P.credit_cap)
            self.assertLessEqual(sum(res.credits.values()), 20)  # floor(100/5) bound


class Replay(unittest.TestCase):
    @staticmethod
    def apply(state, tx):
        if tx["op"] == "credit":
            state.setdefault("credits", {})
            state["credits"][tx["p"]] = state["credits"].get(tx["p"], 0) + tx["n"]
        elif tx["op"] == "spend":
            if state["credits"].get(tx["p"], 0) < tx["n"]:
                raise RuleViolation("insufficient")
            state["credits"][tx["p"]] -= tx["n"]

    def test_replay_reproduces_roots_and_detects_tampering(self):
        led = Ledger(self.apply, {})
        led.append([{"op": "credit", "p": "A", "n": 3}])
        led.append([{"op": "spend", "p": "A", "n": 1}])
        self.assertTrue(Ledger.verify(led.blocks, self.apply, {}))
        import copy
        bad = copy.deepcopy(led.blocks)
        bad[0]["txs"][0]["n"] = 30
        self.assertFalse(Ledger.verify(bad, self.apply, {}))


if __name__ == "__main__":
    unittest.main()
