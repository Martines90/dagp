"""Messy-voter fuzz: random faults against a live VoteSession.
Properties: refused casts change nothing; <=1 ballot per voter; session result == independent
direct tally of the public ballots; money conserved; challenge/finalize never leaves funds reserved."""
import copy
import random
import unittest

from tests.legacy_params import Params
from dagp_ref.roles import Actor
from dagp_ref.session import Effects
from dagp_ref.tally import Ballot, Kind, Outcome, tally
from dagp_ref.treasury import CreditLedger, RuleViolation, Treasury
from tests.fixtures import MODULE, Society


def sess_state(s):
    return copy.deepcopy((s._sealed, s.commits, s.phase, s.attempts.count, s.slashed, s.token_count))


class SessionFuzz(unittest.TestCase):
    def run_seed(self, seed):
        rng = random.Random(seed)
        small = Params(min_citizen_age=10, exam_items=3, sample_articles=2, shard_target=rng.choice([3, 8, 10_000]), exam_panel=3)
        soc = Society(n=rng.randint(20, 40), n_ex=14, p=small)
        tr, cr = Treasury(free=1000), CreditLedger()
        eff = Effects(tr, cr, "proj", 400, [200, 200], "A")
        kind = rng.choice([Kind.ORDINARY, Kind.CONSTITUTIONAL])
        s = soc.session(issue=f"i{seed}", kind=kind, effects=eff, recused=frozenset(rng.sample(soc.citizens, 2)))
        voters = [c for c in soc.citizens + soc.examiners if c in s.electorate.ids]
        tokens = {}
        refused = accepted = 0
        for _ in range(250):
            v = rng.choice(voters + ["stranger", s.board.members[0]])
            h = rng.choice([55, 60, 99, 120, 40])             # some outside [50, 150)
            fault = rng.choice(["none", "none", "none", "bad_exam", "stolen", "secret", "double", "proof"])
            try:
                if v not in tokens or fault == "bad_exam":
                    sec = f"s{rng.randint(0, 9)}"
                    att, tok, _ = soc.get_token(s, v, declared=rng.choice([(), ("a1",), ("a1", "a2", "a3")]),
                                                height=h, ok_prop=(fault != "bad_exam"), secret=sec)
                    tokens[v] = (att, tok, sec)
                att, tok, sec = tokens[v]
                if fault == "stolen":
                    att, tok, sec = tokens[rng.choice(list(tokens))]
                if fault == "secret":
                    sec = "wrong"
                proof = s.electorate.proof(v) if v in s.electorate.ids else []
                if fault == "proof" and voters:
                    proof = s.electorate.proof(rng.choice(voters))
                before = sess_state(s)
                try:
                    s.cast_ballot(v, rng.choice(["Y", "Y", "N", "A"]), tok, sec, att.n, proof, h)
                    accepted += 1
                except RuleViolation:
                    refused += 1
                    self.assertEqual(before, sess_state(s), f"seed {seed}: refused cast mutated state")
            except RuleViolation:
                refused += 1
        self.assertEqual(len(s._sealed), len(set(s._sealed)))
        self.assertLessEqual(len(s._sealed), len(voters))
        self.assertTrue(set(s._sealed) <= set(s.electorate.ids))
        self.assertTrue(set(s._sealed).isdisjoint(s.board.members))
        s.close(s.w.vote_end)
        direct = tally([Ballot(v, c, w) for v, (c, w) in s.ballots_public().items()], s.size, kind, s.p)
        self.assertEqual(s.result, direct, f"seed {seed}: sharded session != direct tally")
        for m in s.board.members[: s.board.threshold]:
            s.certify(m, soc.kr.sign(m, s.certificate_message()), s.w.vote_end)
        s.advance(s.w.vote_end)
        if s.challenges:                                        # mandatory incoherence jury
            for i in range(len(s.challenges)):
                soc.reg.register_ruling(MODULE, f"c{i}", "CHALLENGE", f"{s.issue}:{i}")
                s.rule(Actor("COURT", f"c{i}"), i, False, s.w.vote_end)
        out = s.finalize(s.w.challenge_end)
        tr.assert_invariants()
        self.assertEqual(tr.reserved, {})                       # nothing left dangling
        self.assertEqual(("proj" in tr.escrow), out is Outcome.PASSED)
        return accepted, refused, out

    def test_many_seeds(self):
        outcomes, acc, ref = set(), 0, 0
        for seed in range(30):
            a, r, o = self.run_seed(seed)
            acc, ref = acc + a, ref + r
            outcomes.add(o)
        self.assertGreater(acc, 300)
        self.assertGreater(ref, 1000)
        self.assertGreater(len(outcomes), 1)                   # exercised more than one outcome


if __name__ == "__main__":
    unittest.main()
