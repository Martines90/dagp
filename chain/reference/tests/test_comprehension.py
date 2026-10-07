import unittest

from dagp_ref.comprehension import (PROPOSAL_ARTICLE, AttemptRegistry, Board, Question, QuestionBank,
                                    Scoreboard, Submission, Token, Verdict, commit_key, evaluate,
                                    grade_item_verdicts, issue_token, majority, plan_exam,
                                    verify_token)
from dagp_ref.crypto_sim import SimKeyring
from tests.legacy_params import Params
from dagp_ref.tally import weight
from dagp_ref.treasury import RuleViolation
from tests.fixtures import ARTICLES, CLUSTERS, P, Society, build_bank


class Bank(unittest.TestCase):
    def test_keys_must_match_commitments(self):
        qs = [Question("q", PROPOSAL_ARTICLE, 4, commit_key(2, "salt"))]
        bank = QuestionBank("i", qs, {})
        with self.assertRaises(RuleViolation):
            bank.load_keys({"q": (3, "salt")})           # wrong answer
        with self.assertRaises(RuleViolation):
            bank.load_keys({"q": (2, "other")})          # wrong salt
        with self.assertRaises(RuleViolation):
            bank.answer_ok("q", 2)                       # not revealed yet
        bank.load_keys({"q": (2, "salt")})
        self.assertTrue(bank.answer_ok("q", 2))
        self.assertFalse(bank.answer_ok("q", 1))

    def test_root_commits_to_every_question(self):
        b1, _ = build_bank("x")
        b2, _ = build_bank("x")
        b3, _ = build_bank("y")
        self.assertEqual(b1.root, b2.root)
        self.assertNotEqual(b1.root, b3.root)

    def test_draw_is_seeded_and_voter_specific(self):
        bank, _ = build_bank()
        a = [q.qid for q in bank.draw(b"s1", PROPOSAL_ARTICLE, 3)]
        self.assertEqual(a, [q.qid for q in bank.draw(b"s1", PROPOSAL_ARTICLE, 3)])
        seen = {tuple(q.qid for q in bank.draw(bytes([i]), PROPOSAL_ARTICLE, 3)) for i in range(40)}
        self.assertGreater(len(seen), 5)              # different voters get different sets
        self.assertEqual(bank.articles(), sorted(ARTICLES))


class Plan(unittest.TestCase):
    def setUp(self):
        self.bank, self.keys = build_bank()

    def test_duplicate_clusters_count_once(self):
        plan = plan_exam(self.bank, b"s", "t", ("a3", "a4"), P)      # same cluster c3
        self.assertEqual(len(plan.declared), 1)
        plan = plan_exam(self.bank, b"s", "t", ("a1", "a2", "a3", "a4"), P)
        self.assertEqual(len(plan.declared), 3)

    def test_unknown_article_and_empty_bank_rejected(self):
        with self.assertRaises(RuleViolation):
            plan_exam(self.bank, b"s", "t", ("nope",), P)
        empty = QuestionBank("e", [], {"a": "c"})
        with self.assertRaises(RuleViolation):
            plan_exam(empty, b"s", "t", (), P)
        only_prop = QuestionBank("e", [Question("q", PROPOSAL_ARTICLE, 2, commit_key(0, "s"))], {"a": "c"})
        with self.assertRaises(RuleViolation):
            plan_exam(only_prop, b"s", "t", ("a",), P)              # article without a question

    def test_declaring_nothing_gives_r_zero(self):
        plan = plan_exam(self.bank, b"s", "t", (), P)
        self.assertEqual(plan.sampled, ())
        items = {q.qid: True for q in plan.proposal_qs}
        self.assertEqual(evaluate(plan, items, P), Verdict(True, 0, False))

    def test_r_is_capped(self):
        many = Params(max_articles_counted=2, min_citizen_age=10, exam_items=3, sample_articles=2)
        plan = plan_exam(self.bank, b"s", "t", ("a1", "a2", "a3"), many)
        self.assertEqual(len(plan.declared), 2)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.bank, self.keys = build_bank()
        self.plan = plan_exam(self.bank, b"s", "t", ("a1", "a2", "a3"), P)
        self.all_ok = {q.qid: True for q in self.plan.proposal_qs}
        self.all_ok.update({q.qid: True for _, q in self.plan.sampled})

    def test_pass_threshold_boundary(self):
        res = dict(self.all_ok)
        res[self.plan.proposal_qs[0].qid] = False            # 2/3 = 66.7% < 70%
        self.assertFalse(evaluate(self.plan, res, P).passed)
        self.assertTrue(evaluate(self.plan, self.all_ok, P).passed)
        relaxed = Params(exam_pass_bps=6600, min_citizen_age=10, exam_items=3, sample_articles=2)
        self.assertTrue(evaluate(self.plan, res, relaxed).passed)

    def test_honest_reader_keeps_declared_r(self):
        self.assertEqual(evaluate(self.plan, self.all_ok, P), Verdict(True, 3, False))

    def test_lying_about_reading_extrapolates_down_and_slashes(self):
        res = dict(self.all_ok)
        first = self.plan.sampled[0][1].qid
        res[first] = False                                   # 1 of 2 samples failed
        v = evaluate(self.plan, res, P)
        self.assertEqual((v.passed, v.R, v.slash), (True, 1 * 3 // 2, True))
        res2 = {k: (False if k in {q.qid for _, q in self.plan.sampled} else v) for k, v in self.all_ok.items()}
        v2 = evaluate(self.plan, res2, P)
        self.assertEqual((v2.R, v2.slash), (0, True))

    def test_majority_needs_strict_majority(self):
        vs = {"m1": {"q": True}, "m2": {"q": True}, "m3": {"q": False}, "m4": {"q": False}}
        self.assertFalse(majority(vs, ["q"])["q"])           # 2/4 is not a majority
        vs["m5"] = {"q": True}
        self.assertTrue(majority(vs, ["q"])["q"])


class Tokens(unittest.TestCase):
    def setUp(self):
        self.kr = SimKeyring()
        for m in "abcde":
            self.kr.register(m)
        self.board = Board("b1", tuple("abcde"), "iss")
        self.v = Verdict(True, 4, False)

    def tok(self, signers="abc", issue="iss", height=0):
        return issue_token(self.board, self.kr, issue, "tk", self.v, list(signers), height, P)

    def test_valid_token_and_threshold(self):
        verify_token(self.tok("abc"), self.board, self.kr, "iss", 1)
        with self.assertRaises(RuleViolation):
            verify_token(self.tok("ab"), self.board, self.kr, "iss", 1)

    def test_duplicate_signers_do_not_count_twice(self):
        t = self.tok("a")
        t2 = Token(t.issue, t.ticket, t.R, t.expires, t.board_id, t.sigs * 3)
        with self.assertRaises(RuleViolation):
            verify_token(t2, self.board, self.kr, "iss", 1)

    def test_outsider_signatures_ignored(self):
        self.kr.register("x")
        t = self.tok("ab")
        forged = Token(t.issue, t.ticket, t.R, t.expires, t.board_id,
                       t.sigs + (("x", self.kr.sign("x", t.message())),))
        with self.assertRaises(RuleViolation):
            verify_token(forged, self.board, self.kr, "iss", 1)

    def test_tampered_fields_invalidate(self):
        t = self.tok("abc")
        for bad in (Token(t.issue, t.ticket, t.R + 5, t.expires, t.board_id, t.sigs),       # inflate R
                    Token(t.issue, "other", t.R, t.expires, t.board_id, t.sigs),
                    Token(t.issue, t.ticket, t.R, t.expires + 999, t.board_id, t.sigs)):
            with self.assertRaises(RuleViolation):
                verify_token(bad, self.board, self.kr, "iss", 1)

    def test_expiry_wrong_issue_wrong_board(self):
        t = self.tok("abc", height=0)
        with self.assertRaises(RuleViolation):
            verify_token(t, self.board, self.kr, "iss", t.expires)            # expired
        with self.assertRaises(RuleViolation):
            verify_token(t, self.board, self.kr, "other-issue", 1)
        with self.assertRaises(RuleViolation):
            verify_token(t, Board("b2", tuple("abcde"), "iss"), self.kr, "iss", 1)

    def test_no_token_for_failed_exam(self):
        with self.assertRaises(RuleViolation):
            issue_token(self.board, self.kr, "iss", "tk", Verdict(False, 0, False), ["a"], 0, P)

    def test_non_board_signer_dropped_at_issue(self):
        self.kr.register("x")
        t = issue_token(self.board, self.kr, "iss", "tk", self.v, ["a", "x"], 0, P)
        self.assertEqual([m for m, _ in t.sigs], ["a"])


class Attempts(unittest.TestCase):
    def test_limit_is_per_identity_not_per_ticket(self):
        ar = AttemptRegistry(P)
        toks = [ar.open("i", "v", f"secret{k}").ticket for k in range(P.exam_max_attempts)]
        self.assertEqual(len(set(toks)), P.exam_max_attempts)
        with self.assertRaises(RuleViolation):
            ar.open("i", "v", "fresh-secret")                      # new secret does not reset it
        ar.open("i2", "v", "s")                                   # other issue is independent
        ar.open("i", "w", "s")                                    # other voter independent

    def test_ticket_ownership(self):
        ar = AttemptRegistry(P)
        a = ar.open("i", "v", "s")
        self.assertTrue(ar.owns("v", a.ticket))
        self.assertFalse(ar.owns("w", a.ticket))
        self.assertFalse(ar.owns("v", "forged"))


class Scores(unittest.TestCase):
    def test_canary_flagging(self):
        sb = Scoreboard(P)
        for i in range(P.canary_min_samples):
            sb.record_canary("good", True)
            sb.record_canary("bad", i % 2 == 0)                   # 50% accuracy
            sb.record_item("bad", agreed=False)
        for _ in range(5):
            sb.record_canary("new", False)                        # too few samples to judge
        self.assertEqual(sb.flagged(), ["bad"])
        self.assertEqual(sb.disagreements["bad"], P.canary_min_samples)


class EndToEndGrading(unittest.TestCase):
    def test_hostile_minority_cannot_flip_but_majority_can(self):
        soc = Society()
        s = soc.session()
        voters = [c for c in soc.citizens if c not in s.board.members]
        # Panel of 3. 1 hostile: honest majority still passes a correct exam ...
        _, tok, _ = soc.get_token(s, voters[0], hostile=1)
        self.assertGreaterEqual(tok.R, 0)
        # ... and the lone hostile grader cannot pass a wrong exam.
        with self.assertRaises(RuleViolation):
            soc.get_token(s, voters[1], ok_prop=False, hostile=1)
        # 2 of 3 hostile (the assumption boundary that random sortition makes improbable) CAN pass
        # a wrong exam: this is exactly what the certification-board audit exists to catch.
        _, tok, _ = soc.get_token(s, voters[2], ok_prop=False, ok_art=False, hostile=2)
        self.assertIsNotNone(tok)

    def test_weight_follows_verified_reading(self):
        soc = Society()
        s = soc.session()
        v = [c for c in soc.citizens if c not in s.board.members]
        _, t0, _ = soc.get_token(s, v[0], declared=())
        _, t2, _ = soc.get_token(s, v[1], declared=("a1", "a2"))
        _, t3, _ = soc.get_token(s, v[2], declared=("a1", "a2", "a3", "a4"))   # a3/a4 dedup -> 3
        self.assertEqual([weight(t.R, P) for t in (t0, t2, t3)], [3, 5, 6])

    def test_liar_is_slashed_and_loses_weight(self):
        soc = Society()
        s = soc.session()
        v = [c for c in soc.citizens if c not in s.board.members][0]
        before = soc.reg.get(v).bond
        _, tok, slashed = soc.get_token(s, v, declared=("a1", "a2", "a3"), ok_art=False)
        self.assertTrue(slashed)
        self.assertEqual(tok.R, 0)
        self.assertEqual(soc.reg.get(v).bond, before - P.citizen_bond // 10)
        self.assertIn(v, s.slashed)

    def test_failed_exam_then_retry_then_limit(self):
        soc = Society()
        s = soc.session()
        v = [c for c in soc.citizens if c not in s.board.members][0]
        for _ in range(2):
            with self.assertRaises(RuleViolation):
                soc.get_token(s, v, ok_prop=False, secret="a")
        soc.get_token(s, v, secret="a")                                # third attempt passes
        with self.assertRaises(RuleViolation):
            soc.get_token(s, v, secret="a")                            # fourth: limit reached

    def test_grade_input_validation(self):
        soc = Society()
        s = soc.session()
        v = [c for c in soc.citizens if c not in s.board.members][0]
        att = s.request_exam(v, "x", 55)
        plan = s.plan(att, ("a1",))
        sub = Submission(att.ticket, ("a1",), soc.answers(s, plan))
        good = grade_item_verdicts(s.bank, plan, sub)
        m = s.panel_for(att.ticket).members
        with self.assertRaises(RuleViolation):
            s.grade(att, sub, {"outsider": good, m[0]: good, m[1]: good}, list(m), 55)
        with self.assertRaises(RuleViolation):
            s.grade(att, sub, {m[0]: good}, list(m), 55)                # below threshold
        with self.assertRaises(RuleViolation):
            s.grade(att, Submission("forged", ("a1",), sub.answers), {k: good for k in m}, list(m), 55)
        with self.assertRaises(RuleViolation):
            s.grade(att, sub, {k: good for k in m}, list(m)[:1], 55)    # signers below threshold
        board_member = s.board.members[0]
        with self.assertRaises(RuleViolation):                          # certification board is not a grader
            s.grade(att, sub, {board_member: good, m[0]: good, m[1]: good}, list(m), 55)
        tok, _ = s.grade(att, sub, {k: good for k in m}, list(m), 55)
        self.assertEqual(tok.issue, "prop1")


if __name__ == "__main__":
    unittest.main()
