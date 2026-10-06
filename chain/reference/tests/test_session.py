import unittest
from dataclasses import replace

from dagp_ref.comprehension import Scoreboard
from dagp_ref.params import Params
from dagp_ref.roles import Actor, Role
from dagp_ref.session import ELECTION, Effects, Phase
from dagp_ref.tally import Kind, Outcome
from dagp_ref.treasury import CreditLedger, RuleViolation, Treasury
from tests.fixtures import MODULE, P, Society


def court(soc, ref, action, target):
    soc.reg.register_ruling(MODULE, ref, action, target)
    return Actor("COURT", ref)


def voters_of(soc, s):
    return [c for c in soc.citizens + soc.examiners if c not in s.board.members]


def cast_all(soc, s, plan):
    """plan: list of (choice, count)."""
    vs = iter(voters_of(soc, s))
    for choice, n in plan:
        for _ in range(n):
            soc.vote(s, next(vs), choice)


class Happy(unittest.TestCase):
    def test_passed_vote_opens_escrow_and_reserve_is_converted(self):
        soc = Society()
        tr, cr = Treasury(free=1000), CreditLedger()
        cr.grant("A", 2)
        cr.spend("A", 1)
        eff = Effects(tr, cr, "projX", 300, [100, 100, 100], "A")
        s = soc.session(effects=eff)
        self.assertEqual((tr.free, tr.reserved["projX"]), (700, 300))          # D-02: reserved at open
        cast_all(soc, s, [("Y", 18), ("N", 6), ("A", 2)])
        self.assertEqual(soc.run_to_final(s), Outcome.PASSED)
        self.assertEqual((tr.escrow["projX"], tr.free, "projX" in tr.reserved), (300, 700, False))
        tr.assert_invariants()

    def test_failed_vote_releases_reservation_no_refund(self):
        soc = Society()
        tr, cr = Treasury(free=1000), CreditLedger()
        eff = Effects(tr, cr, "p", 300, [300], "A")
        s = soc.session(effects=eff)
        cast_all(soc, s, [("Y", 5), ("N", 20)])
        self.assertEqual(soc.run_to_final(s), Outcome.FAILED)
        self.assertEqual((tr.free, cr.balance.get("A", 0)), (1000, 0))
        tr.assert_invariants()

    def test_no_quorum_refunds_credit_and_releases(self):
        soc = Society()
        tr, cr = Treasury(free=500), CreditLedger()
        eff = Effects(tr, cr, "p", 200, [200], "A")
        s = soc.session(effects=eff)
        cast_all(soc, s, [("Y", 3)])                                           # 3 of 34
        self.assertEqual(soc.run_to_final(s), Outcome.NO_QUORUM)
        self.assertEqual((tr.free, cr.balance["A"]), (500, P.proposal_cost))   # D-12
        norefund = Params(min_citizen_age=10, exam_items=3, sample_articles=2, refund_on_no_quorum=False)
        soc2 = Society(p=norefund)
        cr2, tr2 = CreditLedger(), Treasury(free=500)
        s2 = soc2.session(effects=Effects(tr2, cr2, "p", 200, [200], "A"))
        cast_all(soc2, s2, [("Y", 3)])
        soc2.run_to_final(s2)
        self.assertEqual(cr2.balance.get("A", 0), 0)

    def test_weighted_outcome_differs_from_head_count(self):
        soc = Society()
        s = soc.session()
        vs = iter(voters_of(soc, s))
        for _ in range(9):                                                      # 9 N readers, weight 6
            soc.vote(s, next(vs), "N", declared=("a1", "a2", "a3"))
        for _ in range(12):                                                     # 12 Y non-readers, weight 3
            soc.vote(s, next(vs), "Y", declared=())
        soc.run_to_final(s)
        r = s.result
        self.assertEqual((r.yes_w, r.no_w), (36, 54))
        self.assertEqual(s.outcome, Outcome.FAILED)                            # understanding outweighs count

    def test_constitutional_vote_needs_two_thirds(self):
        soc = Society()
        s = soc.session(kind=Kind.CONSTITUTIONAL)
        cast_all(soc, s, [("Y", 12), ("N", 8)])                                 # 60%
        self.assertEqual(soc.run_to_final(s), Outcome.FAILED)


class Rejections(unittest.TestCase):
    def setUp(self):
        self.soc = Society()
        self.s = self.soc.session(recused=frozenset({"c0", "c1"}))
        self.v = voters_of(self.soc, self.s)

    def test_no_token_no_vote_and_token_not_transferable(self):
        soc, s = self.soc, self.s
        a, b = [c for c in self.v if c not in ("c0", "c1")][:2]
        att, tok, _ = soc.get_token(s, a)
        with self.assertRaises(RuleViolation):                                   # b uses a's token
            s.cast_ballot(b, "Y", tok, "sec", att.n, s.electorate.proof(b), 56)
        with self.assertRaises(RuleViolation):                                   # a with wrong secret
            s.cast_ballot(a, "Y", tok, "wrong", att.n, s.electorate.proof(a), 56)
        with self.assertRaises(RuleViolation):                                   # a with wrong attempt no.
            s.cast_ballot(a, "Y", tok, "sec", att.n + 1, s.electorate.proof(a), 56)
        s.cast_ballot(a, "Y", tok, "sec", att.n, s.electorate.proof(a), 56)

    def test_double_vote_blocked(self):
        soc, s = self.soc, self.s
        a = [c for c in self.v if c not in ("c0", "c1")][0]
        att, tok, _ = soc.get_token(s, a)
        s.cast_ballot(a, "Y", tok, "sec", att.n, s.electorate.proof(a), 56)
        with self.assertRaises(RuleViolation):
            s.cast_ballot(a, "N", tok, "sec", att.n, s.electorate.proof(a), 57)
        att2, tok2, _ = soc.get_token(s, a, secret="sec2")
        with self.assertRaises(RuleViolation):                                   # fresh token, same voter
            s.cast_ballot(a, "N", tok2, "sec2", att2.n, s.electorate.proof(a), 57)

    def test_recused_party_members_cannot_take_exam_or_vote(self):
        with self.assertRaises(RuleViolation):
            self.soc.get_token(self.s, "c0")
        self.assertNotIn("c0", self.s.electorate.ids)

    def test_board_members_cannot_vote(self):
        m = self.s.board.members[0]
        with self.assertRaises(RuleViolation):
            self.soc.get_token(self.s, m)            # can("VOTE") passes; board rule blocks casting
            
    def test_board_member_blocked_at_cast(self):
        soc, s = self.soc, self.s
        m = s.board.members[0]
        a = [c for c in self.v if c not in ("c0", "c1")][0]
        att, tok, _ = soc.get_token(s, a)
        with self.assertRaises(RuleViolation):
            s.cast_ballot(m, "Y", tok, "sec", att.n, [], 56)

    def test_outsider_with_valid_role_but_not_in_snapshot(self):
        soc, s = self.soc, self.s
        soc.reg.register("late", "op-late", "f", 10, 60)
        soc.reg.approve(MODULE, "late", 60)
        soc.kr.register("late")
        # joined after the snapshot and is too young anyway
        with self.assertRaises(RuleViolation):
            soc.get_token(s, "late", height=61)

    def test_snapshot_membership_enforced_even_if_age_ok(self):
        soc = Society()
        s = soc.session()
        soc.reg.register("late", "op-late", "f", 10, 0)
        soc.reg.approve(MODULE, "late", 0)
        soc.kr.register("late")
        a = [c for c in voters_of(soc, s)][0]
        self.assertNotIn("late", s.electorate.ids)
        att, tok, _ = soc.get_token(s, "late", height=55)
        with self.assertRaises(RuleViolation):
            s.cast_ballot("late", "Y", tok, "sec", att.n, s.electorate.proof(a), 56)   # stolen proof

    def test_suspended_and_banned_voters_blocked_after_snapshot(self):
        soc, s = self.soc, self.s
        a, b = [c for c in self.v if c not in ("c0", "c1")][:2]
        soc.reg.suspend(court(soc, "s1", "SUSPEND", a), a, 52, 500, "x")
        soc.reg.ban(court(soc, "b1", "BAN", b), b, 52, "x")
        for x in (a, b):
            with self.assertRaises(RuleViolation):
                soc.get_token(s, x)

    def test_dormant_voter_blocked(self):
        soc, s = self.soc, self.s
        a = [c for c in self.v if c not in ("c0", "c1")][0]
        soc.reg.tick(2000)
        with self.assertRaises(RuleViolation):
            soc.get_token(s, a, height=55)

    def test_windows(self):
        soc, s = self.soc, self.s
        a = [c for c in self.v if c not in ("c0", "c1")][0]
        with self.assertRaises(RuleViolation):
            soc.get_token(s, a, height=49)                                        # before open
        with self.assertRaises(RuleViolation):
            soc.get_token(s, a, height=s.w.vote_end)                              # at close
        with self.assertRaises(RuleViolation):
            s.close(s.w.vote_end - 1)                                             # too early

    def test_token_expiry_and_wrong_issue(self):
        soc, s = self.soc, self.s
        a = [c for c in self.v if c not in ("c0", "c1")][0]
        att, tok, _ = soc.get_token(s, a, height=55)
        with self.assertRaises(RuleViolation):
            s.cast_ballot(a, "Y", tok, "sec", att.n, s.electorate.proof(a), tok.expires)
        other = soc.session(issue="prop2", height=50)
        b = [c for c in voters_of(soc, other)][0]
        att2, tok2, _ = soc.get_token(other, b)
        s3 = soc.session(issue="prop3", height=50)
        with self.assertRaises(RuleViolation):
            s3.cast_ballot(b, "Y", tok2, "sec", att2.n, s3.electorate.proof(b), 56)

    def test_bad_election_ballot_shape_and_empty_electorate(self):
        soc = Society()
        with self.assertRaises(RuleViolation):
            soc.session(kind=ELECTION)                                            # no parties
        el = soc.session(kind=ELECTION, qualified_parties=["A", "B", "C"])
        v = voters_of(soc, el)[0]
        att, tok, _ = soc.get_token(el, v)
        with self.assertRaises(RuleViolation):
            el.cast_ballot(v, "A", tok, "sec", att.n, el.electorate.proof(v), 56)   # not a tuple


class Sealing(unittest.TestCase):
    def test_ballots_hidden_until_close_then_public(self):
        soc = Society()
        s = soc.session()
        cast_all(soc, s, [("Y", 3)])
        with self.assertRaises(RuleViolation):
            s.ballots_public()
        with self.assertRaises(RuleViolation):
            s.certificate_message()
        s.close(s.w.vote_end)
        self.assertEqual(len(s.ballots_public()), 3)
        self.assertEqual(len(s.commits), 3)
        with self.assertRaises(RuleViolation):
            s.close(s.w.vote_end)                                                 # only once

    def test_rules_locked_at_open(self):
        soc = Society()
        s = soc.session()
        s.p = replace(s.p, quorum_bps=2000)                                          # someone "changes the law"
        with self.assertRaises(RuleViolation):
            s.close(s.w.vote_end)


class Certification(unittest.TestCase):
    def setUp(self):
        self.soc = Society()
        self.s = self.soc.session()
        cast_all(self.soc, self.s, [("Y", 15), ("N", 5)])
        self.s.close(self.s.w.vote_end)
        self.h = self.s.w.vote_end

    def sign(self, m, msg=None):
        return self.soc.kr.sign(m, msg or self.s.certificate_message())

    def test_bad_signature_outsider_and_late_certification_rejected(self):
        s, m = self.s, self.s.board.members
        with self.assertRaises(RuleViolation):
            s.certify(m[0], self.sign(m[0], b"a different tally"), self.h)       # board "disagrees" with chain
        outsider = next(e for e in self.soc.examiners if e not in m)
        with self.assertRaises(RuleViolation):
            s.certify(outsider, self.sign(outsider), self.h)
        with self.assertRaises(RuleViolation):
            s.certify(m[0], self.sign(m[0]), s.w.certify_end)
        with self.assertRaises(RuleViolation):
            s.advance(self.h)                                                      # not before certify_end

    def test_threshold_certificates_move_to_challenge(self):
        s, m = self.s, self.s.board.members
        for x in m[:2]:
            s.certify(x, self.sign(x), self.h)
        self.assertEqual(s.phase, Phase.CLOSED)
        s.certify(m[2], self.sign(m[2]), self.h)
        self.assertEqual(s.phase, Phase.CERTIFIED)
        s.advance(self.h)
        self.assertEqual(s.phase, Phase.CHALLENGE)
        self.assertFalse(s.board_default)
        with self.assertRaises(RuleViolation):
            s.advance(self.h)

    def test_silent_board_cannot_block_outcome_and_is_flagged(self):
        s, m = self.s, self.s.board.members
        s.certify(m[0], self.sign(m[0]), self.h)
        s.advance(s.w.certify_end)
        self.assertTrue(s.board_default)
        self.assertEqual(s.flagged_members, sorted(m[1:]))
        self.assertEqual(s.finalize(s.w.challenge_end), Outcome.PASSED)

    def test_finalize_guards(self):
        s = self.s
        with self.assertRaises(RuleViolation):
            s.finalize(s.w.challenge_end)                                          # not in challenge phase
        s.advance(s.w.certify_end)
        with self.assertRaises(RuleViolation):
            s.finalize(s.w.challenge_end - 1)                                      # window open
        s.finalize(s.w.challenge_end)
        with self.assertRaises(RuleViolation):
            s.finalize(s.w.challenge_end)                                          # only once


class Challenges(unittest.TestCase):
    def build(self, n_yes=15, n_no=5, n_abs=0):
        soc = Society()
        tr, cr = Treasury(free=500), CreditLedger()
        s = soc.session(effects=Effects(tr, cr, "p", 200, [200], "A"))
        cast_all(soc, s, [("Y", n_yes), ("N", n_no), ("A", n_abs)])
        s.close(s.w.vote_end)
        s.advance(s.w.certify_end)
        return soc, s, tr, cr

    def test_upheld_challenge_voids_refunds_and_releases(self):
        soc, s, tr, cr = self.build()
        idx = s.challenge("c5", "process violation", s.w.certify_end + 1)
        with self.assertRaises(RuleViolation):
            s.finalize(s.w.challenge_end)                                          # unresolved
        s.rule(court(soc, "r1", "CHALLENGE", f"prop1:{idx}"), idx, True, s.w.certify_end + 2)
        self.assertEqual(s.finalize(s.w.challenge_end), "VOIDED")
        self.assertEqual((s.phase, tr.free, cr.balance["A"]), (Phase.VOIDED, 500, 1))
        tr.assert_invariants()

    def test_rejected_challenge_keeps_result(self):
        soc, s, tr, _ = self.build()
        idx = s.challenge("c5", "frivolous", s.w.certify_end + 1)
        s.rule(court(soc, "r1", "CHALLENGE", f"prop1:{idx}"), idx, False, s.w.certify_end + 2)
        self.assertEqual(s.finalize(s.w.challenge_end), Outcome.PASSED)
        self.assertIn("p", tr.escrow)

    def test_challenge_guards(self):
        soc, s, *_ = self.build()
        with self.assertRaises(RuleViolation):
            s.challenge("c5", "late", s.w.challenge_end)                           # window closed
        with self.assertRaises(RuleViolation):
            s.challenge("nobody", "x", s.w.certify_end)                             # not a citizen
        idx = s.challenge("c5", "x", s.w.certify_end)
        with self.assertRaises(RuleViolation):
            s.rule(Actor("COURT", "no-ruling"), idx, True, s.w.certify_end)        # court needs a ruling
        with self.assertRaises(RuleViolation):
            s.rule(Actor.agent("c5"), idx, True, s.w.certify_end)                   # agents cannot rule
        r = court(soc, "r1", "CHALLENGE", f"prop1:{idx}")
        s.rule(r, idx, False, s.w.certify_end)
        with self.assertRaises(RuleViolation):
            s.rule(court(soc, "r2", "CHALLENGE", f"prop1:{idx}"), idx, True, s.w.certify_end)

    def test_challenge_not_possible_before_window(self):
        soc = Society()
        s = soc.session()
        with self.assertRaises(RuleViolation):
            s.challenge("c5", "x", 60)

    def test_high_abstention_forces_incoherence_jury(self):
        soc, s, tr, cr = self.build(n_yes=6, n_no=4, n_abs=12)                     # 55% abstain
        self.assertTrue(s.result.review_flag)
        self.assertEqual(s.challenges[0].grounds, "INCOHERENCE")
        with self.assertRaises(RuleViolation):
            s.finalize(s.w.challenge_end)                                          # cannot skip the jury
        s.rule(court(soc, "j", "CHALLENGE", "prop1:0"), 0, False, s.w.certify_end)
        self.assertEqual(s.finalize(s.w.challenge_end), Outcome.PASSED)

    def test_incoherence_upheld_voids(self):
        soc, s, tr, cr = self.build(n_yes=6, n_no=4, n_abs=12)
        s.rule(court(soc, "j", "CHALLENGE", "prop1:0"), 0, True, s.w.certify_end)
        self.assertEqual(s.finalize(s.w.challenge_end), "VOIDED")
        self.assertEqual(tr.free, 500)


class HaltCompensation(unittest.TestCase):
    def test_extend_shifts_open_windows_and_is_module_only(self):
        soc = Society()
        s = soc.session()
        end = s.w.vote_end
        with self.assertRaises(RuleViolation):
            s.extend(Actor.agent("c1"), 30)
        with self.assertRaises(RuleViolation):
            s.extend(MODULE, 0)
        s.extend(MODULE, 30)
        self.assertEqual(s.w.vote_end, end + 30)
        v = voters_of(soc, s)[0]
        soc.vote(s, v, "Y", height=end + 10)                                        # still open thanks to outage credit
        with self.assertRaises(RuleViolation):
            s.close(end)                                                            # cannot close early


class ElectionSession(unittest.TestCase):
    def test_full_election_allocates_credits(self):
        soc = Society(n=40)
        parties = ["A", "B", "C", "D"]
        s = soc.session(issue="elec", kind=ELECTION, qualified_parties=parties)
        vs = voters_of(soc, s)
        picks = [("A", "B", "C")] * 20 + [("B", "A", "D")] * 10 + [("C", "D", "A")] * 5
        for v, pk in zip(vs, picks):
            soc.vote(s, v, pk, declared=())
        soc.run_to_final(s)
        r = s.result
        self.assertTrue(r.valid)
        self.assertEqual(r.total_points, 7 * 35)
        self.assertEqual(r.points["A"], 20 * 4 + 10 * 2 + 5 * 1)
        self.assertEqual(sum(r.credits.values()) <= 20, True)
        self.assertEqual(s.outcome, Outcome.PASSED)

    def test_election_with_invalid_party_picks_counts_as_invalid(self):
        soc = Society(n=12)
        s = soc.session(issue="e2", kind=ELECTION, qualified_parties=["A", "B", "C"])
        v = voters_of(soc, s)
        soc.vote(s, v[0], ("A", "B", "Z"), declared=())
        soc.vote(s, v[1], ("A", "A", "B"), declared=())
        soc.run_to_final(s)
        self.assertFalse(s.result.valid)
        self.assertEqual(s.result.invalid_ballots, 2)
        self.assertEqual(s.outcome, Outcome.NO_QUORUM)


class ScaleInSession(unittest.TestCase):
    def test_many_shards_same_result_as_one(self):
        small = Params(min_citizen_age=10, exam_items=3, sample_articles=2, shard_target=4)
        a, b = Society(p=small), Society()
        sa, sb = a.session(), b.session()
        for soc, s in ((a, sa), (b, sb)):
            cast_all(soc, s, [("Y", 14), ("N", 9), ("A", 3)])
            soc.run_to_final(s)
        self.assertGreater(len(sa.shard_summaries), 1)
        self.assertEqual(len(sb.shard_summaries), 1)
        self.assertEqual(sa.result, sb.result)


if __name__ == "__main__":
    unittest.main()
