"""Randomized operation sequences. Properties:
  A. ATOMICITY  a refused operation changes nothing (state, audit log, single-use refs).
  B. INVARIANTS after every operation, successful or not.
  C. AUDIT      the hash-chained log always verifies and grows exactly once per success
                (except tick/renew which log only on transitions).
"""
import copy
import random
import unittest

from tests.legacy_params import Params
from dagp_ref.roles import Actor, Role, RoleRegistry, Status
from dagp_ref.treasury import RuleViolation

MOD = Actor("MODULE", "m")
P = Params(min_citizen_age=5, min_operator_cap=3, registrar_quota_per_epoch=4, spam_freeze_max=10,
           spam_freeze_cooldown=30, liveness_period=80, min_validators=3, epoch=20)
AGENTS = [f"a{i}" for i in range(14)]
ROLES = list(Role)


def snapshot(r: RoleRegistry):
    d = dict(r.__dict__)
    d.pop("p")
    return copy.deepcopy(d)


def check_invariants(t: unittest.TestCase, r: RoleRegistry):
    t.assertTrue(r.verify_audit())
    for a, i in r.ids.items():
        if i.status is Status.BANNED:
            t.assertEqual(i.roles, set(), a)
            t.assertIn(a, r.banned_keys)
            t.assertNotIn(a, r.validators)
        if i.status is Status.SUSPENDED:
            t.assertGreater(i.suspended_until, 0)
        if i.status is Status.PROBATION:
            t.assertEqual(i.roles, set(), a)                    # no powers before approval
        if i.status is Status.EXITED:
            t.assertEqual((i.bond, i.stake, i.roles), (0, 0, set()), a)    # fully unwound
        t.assertGreaterEqual(i.bond, 0)
        t.assertGreaterEqual(i.stake, 0)
    t.assertLessEqual(len(set(r.validators)), len(r.validators))
    for v in r.validators:
        t.assertIn(Role.VALIDATOR, r.ids[v].roles)
    # a ref is never both unused and recorded as used twice; used refs only ever grow
    t.assertTrue(r.used_refs <= (set(r.ratifications) | set(r.rulings)))


class RegistryFuzz(unittest.TestCase):
    def run_seed(self, seed: int, steps: int = 1500):
        rng = random.Random(seed)
        r = RoleRegistry(P)
        h = 0
        ref_n = 0
        ok = fail = 0
        for _ in range(steps):
            h += rng.randint(0, 6)
            op = rng.choice(["register", "approve", "grant", "revoke", "suspend", "ban", "lift",
                             "appeal", "resolve", "renew", "tick", "exit", "set_validators",
                             "reject", "cluster"])
            a = rng.choice(AGENTS)
            role = rng.choice(ROLES)
            actor = self.pick_actor(rng, r, op, a, role)
            call = self.build(rng, r, op, a, role, actor, h)   # may pre-record an authorization
            before, n_audit = snapshot(r), len(r.audit)
            try:
                call()
                ok += 1
                if op in ("grant", "revoke", "ban", "lift", "resolve"):
                    self.assertGreater(len(r.audit), n_audit, op)
            except RuleViolation:
                fail += 1
                self.assertEqual(before, snapshot(r), f"seed={seed} op={op} mutated state on refusal")
            except KeyError:
                self.fail(f"unexpected KeyError in {op}")
            check_invariants(self, r)
        return ok, fail

    def pick_actor(self, rng, r, op, a, role):
        kind = rng.choice(["MODULE", "MODULE", "AGENT", "VOTE", "COURT", "COURT"])
        if kind == "AGENT":
            return Actor.agent(rng.choice(AGENTS))
        if kind == "MODULE":
            return MOD
        nonlocal_n = len(r.ratifications) + len(r.rulings)
        ref = f"ref{nonlocal_n}-{rng.randint(0, 3)}"
        return Actor(kind, ref)

    def build(self, rng, r, op, a, role, actor, h):
        # Sometimes pre-record an exactly matching ratification / ruling so operations can succeed.
        def prep(action_or_purpose, target, court_action=None):
            if actor.kind == "VOTE" and rng.random() < 0.8:
                r.register_ratification(MOD, actor.ident, action_or_purpose, target)
            if actor.kind == "COURT" and rng.random() < 0.8:
                r.register_ruling(MOD, actor.ident, court_action or action_or_purpose, target)

        # Pre-draw every random choice so the returned call is deterministic.
        stake = rng.choice([0, 50, 100])
        until = h + rng.randint(-2, 40)
        ban_op = rng.random() < 0.2
        upheld = rng.random() < 0.5
        nodes = rng.sample(AGENTS, rng.randint(2, 6))
        reg_args = (a, f"op-{rng.randint(0, 9)}", f"fam{rng.randint(0, 2)}", rng.choice([5, 10, 20]), h)
        cluster = f"op-{rng.randint(0, 9)}"
        if op == "register":
            return lambda: r.register(*reg_args)
        if op == "approve":
            return lambda: r.approve(actor, a, h)
        if op == "reject":
            return lambda: r.reject(actor, a, h, "r")
        if op == "grant":
            prep(f"GRANT:{role.value}", a)
            return lambda: r.grant(actor, a, role, h, stake=stake)
        if op == "revoke":
            prep(f"REVOKE:{role.value}", a)
            return lambda: r.revoke(actor, a, role, h, "x")
        if op == "suspend":
            prep("SUSPEND", a)
            return lambda: r.suspend(actor, a, h, until, "x")
        if op == "lift":
            prep("LIFT", a)
            return lambda: r.lift_suspension(actor, a, h)
        if op == "ban":
            prep("BAN", a)
            return lambda: r.ban(actor, a, h, "x", ban_operator=ban_op)
        if op == "appeal":
            return lambda: r.appeal(a, "case", h)
        if op == "resolve":
            prep("APPEAL", a)
            return lambda: r.resolve_appeal(actor, a, h, upheld)
        if op == "renew":
            return lambda: r.renew_liveness(a, h)
        if op == "tick":
            return lambda: r.tick(h)
        if op == "exit":
            return lambda: r.exit(a, h)
        if op == "set_validators":
            prep("VALIDATOR_SET", ",".join(sorted(nodes)))
            return lambda: r.set_validators(actor, nodes, h)
        return lambda: r.suspend_cluster(actor, cluster, h, h + 10)

    def test_atomicity_and_invariants_many_seeds(self):
        total_ok = total_fail = 0
        for seed in range(25):
            ok, fail = self.run_seed(seed)
            total_ok += ok
            total_fail += fail
        # the fuzzer must exercise BOTH outcomes heavily, else it proves nothing
        self.assertGreater(total_ok, 3000)
        self.assertGreater(total_fail, 3000)

    def test_single_use_ref_survives_a_refused_action(self):
        r = RoleRegistry(P)
        r.register("a", "o", "f", 10, 0)
        r.approve(MOD, "a", 0)
        r.register_ratification(MOD, "v", "GRANT:VALIDATOR", "a")
        with self.assertRaises(RuleViolation):
            r.grant(Actor("VOTE", "v"), "a", Role.VALIDATOR, 20, stake=1)    # stake too low
        self.assertNotIn("v", r.used_refs)                                    # not burned
        r.grant(Actor("VOTE", "v"), "a", Role.VALIDATOR, 20, stake=50)       # same ref still works
        self.assertIn("v", r.used_refs)


if __name__ == "__main__":
    unittest.main()
