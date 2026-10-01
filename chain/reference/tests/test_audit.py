import unittest

from dagp_ref.comprehension import Submission, Verdict, evaluate, grade_item_verdicts, plan_exam
from dagp_ref.params import Params
from dagp_ref.sortition import audit_sample_size, draw, panel_size, threshold
from dagp_ref.treasury import RuleViolation
from tests.fixtures import P, Society


def voters_of(soc, s):
    return [c for c in soc.citizens if c not in s.board.members]


class Panels(unittest.TestCase):
    def test_panel_is_deterministic_excludes_owner_and_board(self):
        soc = Society()
        s = soc.session()
        v = voters_of(soc, s)[0]
        att = s.request_exam(v, "x", 55)
        p1, p2 = s.panel_for(att.ticket), s.panel_for(att.ticket)
        self.assertEqual(p1.members, p2.members)
        self.assertEqual(len(p1.members), P.exam_panel)
        self.assertFalse(set(p1.members) & set(s.board.members))
        self.assertNotIn(v, p1.members)
        self.assertEqual(p1.threshold, threshold(P.exam_panel))

    def test_panels_spread_load_across_the_pool(self):
        soc = Society(n=60, n_ex=40)
        s = soc.session()
        seen = set()
        for i, v in enumerate(voters_of(soc, s)[:50]):
            att = s.request_exam(v, "x", 55)
            seen |= set(s.panel_for(att.ticket).members)
        self.assertGreater(len(seen), 25)          # work is spread, not concentrated on one board

    def test_pool_too_small(self):
        soc = Society(n=10, n_ex=6)                 # board 5 leaves a pool of 1 < panel 3
        s = soc.session()
        att = s.request_exam(voters_of(soc, s)[0], "x", 55)
        with self.assertRaises(RuleViolation):
            s.panel_for(att.ticket)

    def test_default_certification_board_size_matches_the_math(self):
        d = Params()
        g = panel_size(d.assumed_bad_bps, d.board_fail_den)
        self.assertEqual((g, threshold(g)), (51, 26))
        board = draw(b"beacon", [f"e{i}" for i in range(400)], g)
        self.assertEqual(len(set(board)), 51)


class Audits(unittest.TestCase):
    def fraud_vote(self, soc, s, voter):
        att, tok, _ = soc.get_token(s, voter, declared=("a1", "a2"), ok_prop=False, ok_art=False,
                                    hostile=2, secret="sec")
        s.cast_ballot(voter, "Y", tok, "sec", att.n, s.electorate.proof(voter), 56)
        return att, tok

    def test_honest_token_passes_audit(self):
        soc = Society()
        s = soc.session()
        v = voters_of(soc, s)[0]
        soc.vote(s, v, "Y")
        ticket = next(iter(s.issued))
        tok = s.issued[ticket][0]
        self.assertEqual(s.audit(ticket, Verdict(True, tok.R, False), 60), "OK")
        self.assertIn(v, s._sealed)

    def test_fraudulent_token_is_struck_revoked_and_panel_flagged(self):
        soc = Society()
        s = soc.session()
        v = voters_of(soc, s)[0]
        att, tok = self.fraud_vote(soc, s, v)
        self.assertIn(v, s._sealed)
        self.assertEqual(s.audit(att.ticket, Verdict(False, 0, False), 60), "STRUCK")
        self.assertNotIn(v, s._sealed)
        self.assertNotIn(v, s.commits)
        self.assertEqual(s.struck, [v])
        self.assertIn(att.ticket, s.revoked)
        for m, _ in tok.sigs:
            self.assertEqual(s.scoreboard.disagreements[m] >= 1, True)
        with self.assertRaises(RuleViolation):                       # the revoked token cannot be reused
            s.cast_ballot(v, "Y", tok, "sec", att.n, s.electorate.proof(v), 61)

    def test_inflated_weight_is_corrected_not_struck(self):
        soc = Society()
        s = soc.session()
        v = voters_of(soc, s)[0]
        att, tok, _ = soc.get_token(s, v, declared=("a1", "a2", "a3"), ok_art=False, hostile=2)
        s.cast_ballot(v, "Y", tok, "sec", att.n, s.electorate.proof(v), 56)
        self.assertEqual(s._sealed[v][1], 3 + tok.R)
        self.assertEqual(s.audit(att.ticket, Verdict(True, 0, True), 60), "CORRECTED")
        self.assertEqual(s._sealed[v][1], 3)
        self.assertEqual(s.issued[att.ticket][0].R, 0)

    def test_correction_before_the_ballot_is_cast(self):
        soc = Society()
        s = soc.session()
        v = voters_of(soc, s)[0]
        att, tok, _ = soc.get_token(s, v, declared=("a1", "a2"), ok_art=False, hostile=2)
        self.assertEqual(s.audit(att.ticket, Verdict(True, 0, True), 60), "CORRECTED")
        self.assertNotIn(v, s._sealed)

    def test_audit_guards(self):
        soc = Society()
        s = soc.session()
        with self.assertRaises(RuleViolation):
            s.audit("ghost", Verdict(True, 0, False), 60)
        v = voters_of(soc, s)[0]
        soc.vote(s, v, "Y")
        t = next(iter(s.issued))
        s.close(s.w.vote_end)
        with self.assertRaises(RuleViolation):
            s.audit(t, Verdict(False, 0, False), s.w.vote_end)       # audits run during voting

    def test_audit_sample_size_is_independent_of_population(self):
        soc = Society(n=800, n_ex=14)
        s = soc.session()
        for v in voters_of(soc, s)[:800]:
            att = s.request_exam(v, "x", 55)
            plan = s.plan(att, ())
            sub = Submission(att.ticket, (), soc.answers(s, plan))
            panel = s.panel_for(att.ticket)
            good = grade_item_verdicts(s.bank, plan, sub)
            s.grade(att, sub, {m: good for m in panel.members}, list(panel.members), 55)
        n = audit_sample_size(P.audit_fraud_bps, P.audit_miss_den)
        self.assertEqual(n, 688)
        sample = s.audit_sample()
        self.assertEqual(len(sample), n)
        self.assertEqual(len(set(sample)), n)
        self.assertEqual(sample, s.audit_sample())                    # deterministic, recomputable

    def test_five_percent_token_fraud_is_caught_by_the_fixed_size_sample(self):
        soc = Society(n=1000, n_ex=14)
        s = soc.session()
        vs = voters_of(soc, s)
        cheaters = set(vs[i] for i in range(0, 1000, 20))              # 5%
        truth = {}
        for v in vs[:1000]:
            att = s.request_exam(v, "x", 55)
            plan = s.plan(att, ())
            sub = Submission(att.ticket, (), soc.answers(s, plan, ok_prop=v not in cheaters))
            panel = s.panel_for(att.ticket)
            honest = grade_item_verdicts(s.bank, plan, sub)
            lie = {k: True for k in honest}                             # corrupt panel rubber-stamps
            verdicts = {m: (lie if v in cheaters else honest) for m in panel.members}
            s.grade(att, sub, verdicts, list(panel.members), 55)
            truth[att.ticket] = (v, v not in cheaters)
        sample = s.audit_sample()
        struck = sum(1 for t in sample
                     if s.audit(t, Verdict(truth[t][1], 0, False), 60) == "STRUCK")
        self.assertEqual(len(sample), 688)
        self.assertGreater(struck, 15)                                  # ~35 expected of 50 cheaters
        print(f"\n[audit] {struck} of {len(cheaters)} fraudulent tokens caught by a {len(sample)}-ticket sample")


if __name__ == "__main__":
    unittest.main()
