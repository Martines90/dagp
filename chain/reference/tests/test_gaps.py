"""Edge paths that the feature suites do not reach: each asserts a fail-closed behavior."""
import unittest
from dataclasses import replace

from dagp_ref.election import qualify_parties, run_election
from dagp_ref.ledger import Ledger
from tests.legacy_params import Params
from dagp_ref.roles import Actor, Role, RoleRegistry, Status
from dagp_ref.tally import ABSTAIN, NO, YES, Ballot, Kind, Outcome, tally, tally_bill, weight
from dagp_ref.treasury import RuleViolation, Treasury
from tests.fixtures import MODULE, Society

P = Params()


def bs(y=0, n=0, a=0):
    return ([Ballot(f"y{i}", YES, 3) for i in range(y)] + [Ballot(f"n{i}", NO, 3) for i in range(n)]
            + [Ballot(f"a{i}", ABSTAIN, 3) for i in range(a)])


class TallyEdges(unittest.TestCase):
    def test_negative_r_rejected(self):
        with self.assertRaises(ValueError):
            weight(-1, P)

    def test_invalid_inputs(self):
        self.assertEqual(tally(bs(y=1), 0, Kind.ORDINARY, P).outcome, Outcome.INVALID)
        self.assertEqual(tally([Ballot("x", "?", 3)], 5, Kind.ORDINARY, P).outcome, Outcome.INVALID)
        self.assertEqual(tally([Ballot("x", YES, 2)], 5, Kind.ORDINARY, P).outcome, Outcome.INVALID)

    def test_bill_propagates_invalid_and_no_quorum(self):
        ok = bs(y=300, n=200)
        dup = [Ballot("x", YES, 3), Ballot("x", NO, 3)]
        self.assertEqual(tally_bill([ok, dup], 1000, Kind.ORDINARY, P).outcome, Outcome.INVALID)
        self.assertEqual(tally_bill([ok, bs(y=10)], 1000, Kind.ORDINARY, replace(P,bill_mode="PACKAGE")).outcome, Outcome.NO_QUORUM)
        self.assertEqual(tally_bill([], 1000, Kind.ORDINARY, P).outcome, Outcome.INVALID)

    def test_bill_with_no_passing_point_fails(self):
        tie = bs(y=250, n=250)
        self.assertEqual(tally_bill([tie], 1000, Kind.ORDINARY, P).outcome, Outcome.FAILED)


class ElectionEdges(unittest.TestCase):
    def test_qualification_success_path(self):
        members = {"A": {f"a{i}" for i in range(10)}, "B": {f"b{i}" for i in range(10)},
                   "C": {f"c{i}" for i in range(9)}}                       # C is one member short
        ends = {"A": {f"e{i}" for i in range(6)}, "B": {f"f{i}" for i in range(6)},
                "C": {f"g{i}" for i in range(6)}}
        q, problems = qualify_parties(members, ends, 5, P)
        self.assertEqual((q, problems), (["A", "B"], []))
        ends["A"] = {f"e{i}" for i in range(4)}                              # A one endorsement short
        self.assertEqual(qualify_parties(members, ends, 5, P)[0], ["B"])

    def test_no_valid_ballots(self):
        res = run_election([("A", "A", "B")], ["A", "B", "C"], P)
        self.assertEqual((res.valid, res.reason), (False, "NO_VALID_BALLOTS"))


class TreasuryEdges(unittest.TestCase):
    def test_reservation_guards(self):
        t = Treasury(free=100)
        t.reserve("p", 50)
        with self.assertRaises(RuleViolation):
            t.reserve("p", 10)                                  # already reserved
        with self.assertRaises(RuleViolation):
            t.reserve("q", 0)
        with self.assertRaises(RuleViolation):
            t.reserve("q", 51)                                  # only 50 free
        with self.assertRaises(RuleViolation):
            t.release_reservation("nope")
        with self.assertRaises(RuleViolation):
            t.commit_reserved("nope", [1])
        with self.assertRaises(RuleViolation):
            t.commit_reserved("p", [30, 30])                    # exceeds the 50 ceiling
        with self.assertRaises(RuleViolation):
            t.commit_reserved("p", [0])
        t.commit_reserved("p", [20, 20])                        # spends less than the ceiling
        self.assertEqual((t.free, t.escrow["p"]), (60, 40))
        with self.assertRaises(RuleViolation):
            t.reserve("p", 5)                                   # funded projects cannot re-reserve
        with self.assertRaises(RuleViolation):
            t.reserve_and_grant("p", [1])
        t.assert_invariants()

    def test_tranche_exhaustion_and_double_terminate(self):
        t = Treasury(free=100)
        t.reserve_and_grant("p", [10])
        t.release_next("p", 3, 3)
        with self.assertRaises(RuleViolation):
            t.release_next("p", 3, 3)                           # no tranche left
        t.terminate("p")
        with self.assertRaises(RuleViolation):
            t.terminate("p")
        t.assert_invariants()


class LedgerEdges(unittest.TestCase):
    def test_broken_chain_link_detected(self):
        def apply(state, tx):
            state["n"] = state.get("n", 0) + tx["n"]
        led = Ledger(apply, {})
        led.append([{"n": 1}])
        led.append([{"n": 2}])
        blocks = [dict(b) for b in led.blocks]
        blocks[1]["prev"] = "0" * 64
        self.assertFalse(Ledger.verify(blocks, apply, {}))
        self.assertTrue(Ledger.verify(led.blocks, apply, {}))


class RoleEdges(unittest.TestCase):
    def setUp(self):
        self.p = Params(min_citizen_age=10, min_operator_cap=5, min_validators=3)
        self.r = RoleRegistry(self.p)
        for a in ("a", "b"):
            self.r.register(a, f"op-{a}", "f", 10, 0)
            self.r.approve(MODULE, a, 0)

    def test_missing_role_reason(self):
        self.assertEqual(self.r.can("a", "GRADE", 50), (False, "missing-role:EXAMINER"))

    def test_approve_twice_and_missing_prerequisite(self):
        with self.assertRaises(RuleViolation):
            self.r.approve(MODULE, "a", 5)                       # already active
        self.r.get("a").roles.discard(Role.CITIZEN)             # simulate a citizen whose role lapsed
        with self.assertRaises(RuleViolation):
            self.r.grant(MODULE, "a", Role.PARTY_MEMBER, 20)

    def test_validator_must_be_removed_from_set_before_exit(self):
        r = RoleRegistry(self.p)
        for i in range(3):
            r.register(f"v{i}", f"o{i}", "f", 10, 0)
            r.approve(MODULE, f"v{i}", 0)
            r.register_ratification(MODULE, f"g{i}", f"GRANT:VALIDATOR", f"v{i}")
            r.grant(Actor("VOTE", f"g{i}"), f"v{i}", Role.VALIDATOR, 20, stake=50)
        r.register_ratification(MODULE, "set", "VALIDATOR_SET", "v0,v1,v2")
        r.set_validators(Actor("VOTE", "set"), ["v0", "v1", "v2"], 30)
        with self.assertRaises(RuleViolation):
            r.exit("v0", 40)
        self.assertEqual(r.get("v0").status, Status.ACTIVE)     # the refused exit changed nothing
        self.assertIn("v0", r.validators)

    def test_cluster_hold_returns_members_when_each_is_authorized(self):
        r = RoleRegistry(self.p)
        for i in range(2):
            r.register(f"k{i}", "ring", "f", 10, 0)
            r.approve(MODULE, f"k{i}", 0)
        court = Actor("COURT", "hold")
        rulings = {}
        for agent in ("k0","k1"):
            r.register_ruling(MODULE,f"hold-{agent}","SUSPEND",agent)
            rulings[agent] = Actor("COURT",f"hold-{agent}")
        self.assertEqual(r.suspend_cluster(court,"ring",20,90,rulings),["k0","k1"])
        self.assertTrue(all(r.get(a).status is Status.SUSPENDED for a in ("k0", "k1")))


class SessionEdges(unittest.TestCase):
    def test_empty_electorate_rejected(self):
        soc = Society(n=2, n_ex=5)
        with self.assertRaises(RuleViolation):
            soc.session(board_size=5, recused=frozenset(soc.citizens + soc.examiners))

    def test_cast_and_grade_only_while_voting(self):
        soc = Society()
        s = soc.session()
        v = [c for c in soc.citizens if c not in s.board.members][0]
        att, tok, _ = soc.get_token(s, v)
        s.close(s.w.vote_end)
        with self.assertRaises(RuleViolation):
            s.cast_ballot(v, "Y", tok, "sec", att.n, s.electorate.proof(v), 56)   # phase CLOSED
        with self.assertRaises(RuleViolation):
            s.certify(s.board.members[0], "sig", s.w.certify_end)                   # past window
        s.advance(s.w.certify_end)
        with self.assertRaises(RuleViolation):
            s.certify(s.board.members[0], "sig", s.w.vote_end)                      # in CHALLENGE phase


if __name__ == "__main__":
    unittest.main()
