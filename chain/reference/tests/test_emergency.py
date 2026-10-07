import unittest

from dagp_ref.emergency import Emergency
from tests.legacy_params import Params
from dagp_ref.proposal import FilingRegistry
from dagp_ref.roles import Actor, Role, RoleRegistry
from dagp_ref.treasury import RuleViolation, Treasury
from tests.fixtures import MODULE

P = Params(min_citizen_age=10, pause_max=50)


def setup():
    r = RoleRegistry(P)
    for a in ("c1", "c2", "cit"):
        r.register(a, f"op-{a}", "f", 10, 0)
        r.approve(MODULE, a, 0)
    for a in ("c1", "c2"):
        r.register_ratification(MODULE, f"g-{a}", "GRANT:SAFETY_COUNCIL", a)
        r.grant(Actor("VOTE", f"g-{a}"), a, Role.SAFETY_COUNCIL, 20)
    t = Treasury(free=1000)
    t.reserve_and_grant("p", [100, 100])
    return r, t, Emergency(P, r, t)


class Pause(unittest.TestCase):
    def test_only_council_may_pause_with_reason_and_bounded_duration(self):
        r, t, e = setup()
        for who in ("cit", "ghost"):
            with self.assertRaises(RuleViolation):
                e.pause(who, "p", 30, 10, "risk")
        with self.assertRaises(RuleViolation):
            e.pause("c1", "p", 30, 10, "")                      # reason required
        for d in (0, -1, P.pause_max + 1):
            with self.assertRaises(RuleViolation):
                e.pause("c1", "p", 30, d, "risk")
        with self.assertRaises(RuleViolation):
            e.pause("c1", "nope", 30, 10, "risk")
        self.assertEqual(e.pause("c1", "p", 30, 20, "risk"), 50)

    def test_pause_freezes_release_and_auto_expires(self):
        r, t, e = setup()
        e.pause("c1", "p", 30, 20, "risk")
        with self.assertRaises(RuleViolation):
            t.release_next("p", 3, 3, height=40)                  # frozen
        self.assertTrue(e.is_paused("p", 49))
        self.assertEqual(t.release_next("p", 3, 3, height=50), 100)   # expired by height alone
        self.assertFalse(e.is_paused("p", 50))
        t.assert_invariants()

    def test_pause_cannot_spend_cancel_or_move_money(self):
        r, t, e = setup()
        before = (t.free, dict(t.escrow), dict(t.released))
        e.pause("c1", "p", 30, 20, "risk")
        self.assertEqual(before, (t.free, dict(t.escrow), dict(t.released)))
        self.assertNotIn("p", t.terminated)

    def test_no_stacking_and_no_chained_repause_without_a_vote(self):
        r, t, e = setup()
        e.pause("c1", "p", 30, 20, "risk")
        with self.assertRaises(RuleViolation):
            e.pause("c2", "p", 35, 20, "again")                   # already paused
        with self.assertRaises(RuleViolation):
            e.pause("c2", "p", 50, 20, "again")                   # cooldown after unratified pause
        self.assertEqual(e.pause("c2", "p", 50 + P.pause_max, 10, "new evidence"), 110)

    def test_ratification_extends_only_via_matching_unused_vote(self):
        r, t, e = setup()
        e.pause("c1", "p", 30, 20, "risk")
        with self.assertRaises(RuleViolation):
            e.ratify(MODULE, "p", 40, 200)                         # module cannot ratify
        r.register_ratification(MODULE, "v", "PAUSE_RATIFY", "p")
        with self.assertRaises(RuleViolation):
            e.ratify(Actor("VOTE", "v"), "p", 40, 50)              # must extend
        e.ratify(Actor("VOTE", "v"), "p", 40, 200)
        self.assertTrue(e.is_paused("p", 150))
        with self.assertRaises(RuleViolation):
            e.ratify(Actor("VOTE", "v"), "p", 41, 300)             # single-use
        self.assertTrue(e.pause("c1", "p", 200 + 1, 10, "new") > 0)  # ratified -> no cooldown
        with self.assertRaises(RuleViolation):
            e.ratify(Actor("VOTE", "none"), "p", 300, 400)         # nothing live

    def test_suspended_council_member_cannot_pause(self):
        r, t, e = setup()
        r.register_ruling(MODULE, "s", "SUSPEND", "c1")
        r.suspend(Actor("COURT", "s"), "c1", 25, 99, "x")
        with self.assertRaises(RuleViolation):
            e.pause("c1", "p", 30, 10, "risk")

    def test_audit_trail(self):
        r, t, e = setup()
        n = len(r.audit)
        e.pause("c1", "p", 30, 10, "risk")
        self.assertEqual(len(r.audit), n + 1)
        self.assertTrue(r.verify_audit())


class Filing(unittest.TestCase):
    def test_cooldown(self):
        f = FilingRegistry(500)
        f.file("obj", 0)
        with self.assertRaises(RuleViolation):
            f.file("obj", 499)
        f.file("other", 10)
        f.file("obj", 500)


if __name__ == "__main__":
    unittest.main()
