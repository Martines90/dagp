import unittest

from dagp_ref.crypto_sim import H, SimKeyring
from dagp_ref.keys import KeyManager
from tests.legacy_params import Params
from dagp_ref.roles import Actor, RoleRegistry
from dagp_ref.treasury import RuleViolation
from tests.fixtures import MODULE

P = Params(min_citizen_age=10, rotation_delay=50, recovery_delay=250, max_session_ttl=100, min_guardians=3)


def world():
    kr, r = SimKeyring(), RoleRegistry(P)
    km = KeyManager(P, r, kr)
    for a in ("alice", "g1", "g2", "g3", "g4", "mallory"):
        r.register(a, f"op-{a}", "f", 10, 0)
        r.approve(MODULE, a, 0)
        km.enroll(a)
    return kr, r, km


def set_guardians(km, k=2, who=("g1", "g2", "g3"), h=1):
    m = H(b"guardians", "alice", ",".join(sorted(who)), k, "n-g")
    km.set_guardians("alice", tuple(who), k, "n-g", km.kr.sign("alice#1", m), h)


class Rotation(unittest.TestCase):
    def test_rotation_needs_old_key_waits_and_swaps(self):
        kr, r, km = world()
        new = km.new_key("alice")
        sig = km.sign_op("ROTATE", "alice", "alice#1", new, "n1")
        with self.assertRaises(RuleViolation):
            km.begin_rotation("alice", new, "n1", km.sign_op("ROTATE", "alice", "mallory#1", new, "n1"), 5)
        eff = km.begin_rotation("alice", new, "n1", sig, 5)
        self.assertEqual(eff, 55)
        msg = b"vote"
        self.assertTrue(km.verify("alice", msg, kr.sign("alice#1", msg)))        # old valid during delay
        self.assertFalse(km.verify("alice", msg, kr.sign(new, msg)))
        km.tick(54)
        self.assertEqual(km.state["alice"].active, "alice#1")
        km.tick(55)
        self.assertFalse(km.verify("alice", msg, kr.sign("alice#1", msg)))       # old dead after swap
        self.assertTrue(km.verify("alice", msg, kr.sign(new, msg)))
        self.assertIsNone(km.state["alice"].pending)
        self.assertTrue(r.verify_audit())

    def test_replayed_nonce_and_double_pending_rejected(self):
        kr, r, km = world()
        new = km.new_key("alice")
        sig = km.sign_op("ROTATE", "alice", "alice#1", new, "n1")
        km.begin_rotation("alice", new, "n1", sig, 5)
        with self.assertRaises(RuleViolation):
            km.begin_rotation("alice", new, "n1", sig, 6)                        # pending
        km.tick(60)
        with self.assertRaises(RuleViolation):                                   # old sig replay, now wrong signer
            km.begin_rotation("alice", new, "n1", sig, 61)

    def test_owner_can_cancel_inside_the_delay_only(self):
        kr, r, km = world()
        new = km.new_key("alice")
        km.begin_rotation("alice", new, "n1", km.sign_op("ROTATE", "alice", "alice#1", new, "n1"), 5)
        with self.assertRaises(RuleViolation):
            km.cancel("alice", "c1", km.sign_op("CANCEL", "alice", "mallory#1", new, "c1"), 10)
        km.cancel("alice", "c1", km.sign_op("CANCEL", "alice", "alice#1", new, "c1"), 10)
        km.tick(100)
        self.assertEqual(km.state["alice"].active, "alice#1")
        with self.assertRaises(RuleViolation):
            km.cancel("alice", "c2", "x", 11)                                    # nothing pending

    def test_cancel_cannot_reuse_a_nonce(self):
        kr, r, km = world()
        new = km.new_key("alice")
        km.begin_rotation("alice", new, "n1", km.sign_op("ROTATE", "alice", "alice#1", new, "n1"), 5)
        with self.assertRaises(RuleViolation):
            km.cancel("alice", "n1", km.sign_op("CANCEL", "alice", "alice#1", new, "n1"), 10)
        self.assertIsNotNone(km.state["alice"].pending)                           # refusal changed nothing

    def test_court_can_cancel_a_hostile_rotation(self):
        kr, r, km = world()
        new = km.new_key("mallory")
        km.begin_rotation("mallory", new, "n", km.sign_op("ROTATE", "mallory", "mallory#1", new, "n"), 5)
        with self.assertRaises(RuleViolation):
            km.cancel_by_court(Actor("COURT", "none"), "mallory", 6)
        r.register_ruling(MODULE, "c", "CANCEL_KEYOP", "mallory")
        km.cancel_by_court(Actor("COURT", "c"), "mallory", 6)
        self.assertIsNone(km.state["mallory"].pending)
        with self.assertRaises(RuleViolation):
            r.register_ruling(MODULE, "c2", "CANCEL_KEYOP", "mallory")
            km.cancel_by_court(Actor("COURT", "c2"), "mallory", 7)               # nothing pending

    def test_blocked_for_banned_suspended_and_unknown(self):
        kr, r, km = world()
        r.register_ruling(MODULE, "b", "BAN", "mallory")
        r.ban(Actor("COURT", "b"), "mallory", 3, "x")
        new = "mallory#2"
        kr.register(new)
        with self.assertRaises(RuleViolation):
            km.begin_rotation("mallory", new, "n", km.sign_op("ROTATE", "mallory", "mallory#1", new, "n"), 5)
        with self.assertRaises(RuleViolation):
            km.enroll("alice")                                                    # twice
        with self.assertRaises(RuleViolation):
            km.enroll("ghost")


class Recovery(unittest.TestCase):
    def test_guardian_setup_validation(self):
        kr, r, km = world()
        def go(who, k, signer="alice#1", nonce="n"):
            m = H(b"guardians", "alice", ",".join(sorted(who)), k, nonce)
            km.set_guardians("alice", tuple(who), k, nonce, kr.sign(signer, m), 1)
        for who, k in ((("g1", "g2"), 2), (("g1", "g1", "g2"), 2), (("g1", "g2", "g3"), 1),
                       (("g1", "g2", "g3"), 4), (("g1", "g2", "alice"), 2), (("g1", "g2", "ghost"), 2)):
            with self.assertRaises((RuleViolation,)):
                go(who, k)
        with self.assertRaises(RuleViolation):
            go(("g1", "g2", "g3"), 2, signer="mallory#1")                         # wrong signer
        r.register("kin", "op-alice", "f", 10, 0)
        r.approve(MODULE, "kin", 0)
        km.enroll("kin")
        with self.assertRaises(RuleViolation):
            go(("g1", "g2", "kin"), 2, nonce="n3")                                # same operator as owner
        go(("g1", "g2", "g3"), 2, nonce="ok")
        with self.assertRaises(RuleViolation):
            go(("g1", "g2", "g3"), 2, nonce="ok")                                 # nonce reuse

    def test_k_of_n_recovery_with_long_delay_and_session_wipe(self):
        kr, r, km = world()
        set_guardians(km)
        new = km.new_key("alice")
        sess = "alice-sess"
        kr.register(sess)
        exp = 80
        m = km.session_msg("alice", sess, {"VOTE"}, exp, "sn")
        km.grant_session("alice", sess, {"VOTE"}, exp, "sn", kr.sign("alice#1", m), 2)
        sigs = {g: km.sign_op("RECOVER", "alice", f"{g}#1", new, "rn") for g in ("g1", "g2")}
        eff = km.begin_recovery("alice", new, "rn", sigs, 10)
        self.assertEqual(eff, 10 + P.recovery_delay)
        km.tick(eff - 1)
        self.assertEqual(km.state["alice"].active, "alice#1")
        km.tick(eff)
        self.assertEqual(km.state["alice"].active, new)
        self.assertTrue(km.state["alice"].sessions[sess].revoked)                 # all sessions die

    def test_insufficient_duplicate_outsider_or_forged_guardian_sigs(self):
        kr, r, km = world()
        set_guardians(km)
        new = km.new_key("alice")
        one = {"g1": km.sign_op("RECOVER", "alice", "g1#1", new, "rn")}
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn", one, 10)
        outsider = dict(one, g4=km.sign_op("RECOVER", "alice", "g4#1", new, "rn"))
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn", outsider, 10)                   # g4 not a guardian
        forged = dict(one, g2=km.sign_op("RECOVER", "alice", "mallory#1", new, "rn"))
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn", forged, 10)
        wrong_target = {g: km.sign_op("RECOVER", "alice", f"{g}#1", "evil#9", "rn") for g in ("g1", "g2")}
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn", wrong_target, 10)               # signed a different key
        with self.assertRaises(RuleViolation):
            km.begin_recovery("mallory", new, "rn", one, 10)                      # no guardians registered

    def test_owner_vetoes_recovery_during_delay(self):
        kr, r, km = world()
        set_guardians(km)
        new = km.new_key("alice")
        sigs = {g: km.sign_op("RECOVER", "alice", f"{g}#1", new, "rn") for g in ("g1", "g3")}
        km.begin_recovery("alice", new, "rn", sigs, 10)
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn2", sigs, 11)                      # one at a time
        km.cancel("alice", "veto", km.sign_op("CANCEL", "alice", "alice#1", new, "veto"), 100)
        km.tick(10_000)
        self.assertEqual(km.state["alice"].active, "alice#1")

    def test_suspended_guardian_does_not_count(self):
        kr, r, km = world()
        set_guardians(km)
        r.register_ruling(MODULE, "s", "SUSPEND", "g2")
        r.suspend(Actor("COURT", "s"), "g2", 2, 999, "x")
        new = km.new_key("alice")
        sigs = {g: km.sign_op("RECOVER", "alice", f"{g}#1", new, "rn") for g in ("g1", "g2")}
        with self.assertRaises(RuleViolation):
            km.begin_recovery("alice", new, "rn", sigs, 10)


class Sessions(unittest.TestCase):
    def setUp(self):
        self.kr, self.r, self.km = world()
        self.kr.register("alice-s")
        self.msg = b"cast ballot"

    def grant(self, scope, exp=60, nonce="s1", h=5):
        m = self.km.session_msg("alice", "alice-s", scope, exp, nonce)
        self.km.grant_session("alice", "alice-s", scope, exp, nonce, self.kr.sign("alice#1", m), h)

    def test_scope_expiry_and_revocation(self):
        self.grant({"VOTE"})
        sig = self.kr.sign("alice-s", self.msg)
        self.assertTrue(self.km.verify_action("alice", "VOTE", self.msg, sig, "alice-s", 10))
        self.assertFalse(self.km.verify_action("alice", "ENDORSE", self.msg, sig, "alice-s", 10))   # scope
        self.assertFalse(self.km.verify_action("alice", "VOTE", self.msg, sig, "alice-s", 60))      # expired
        self.assertFalse(self.km.verify_action("alice", "VOTE", self.msg, "bad", "alice-s", 10))
        self.km.revoke_session("alice", "alice-s", 11)
        self.assertFalse(self.km.verify_action("alice", "VOTE", self.msg, sig, "alice-s", 12))
        with self.assertRaises(RuleViolation):
            self.km.revoke_session("alice", "nope", 12)

    def test_session_key_cannot_do_key_management_or_exceed_limits(self):
        self.grant({"VOTE"})
        new = self.km.new_key("alice")
        bad = self.km.sign_op("ROTATE", "alice", "alice-s", new, "x")              # signed by session key
        with self.assertRaises(RuleViolation):
            self.km.begin_rotation("alice", new, "x", bad, 6)
        for scope in ({"KEY_ROTATE"}, set(), {"VOTE", "BOND"}):
            with self.assertRaises(RuleViolation):
                self.grant(scope, nonce=f"x{len(scope)}{sorted(scope)}")
        with self.assertRaises(RuleViolation):
            self.grant({"VOTE"}, exp=5 + P.max_session_ttl + 1, nonce="long")
        with self.assertRaises(RuleViolation):
            self.grant({"VOTE"}, exp=5, nonce="past")
        with self.assertRaises(RuleViolation):
            self.grant({"VOTE"}, nonce="s1")                                          # nonce reuse
        with self.assertRaises(RuleViolation):
            m = self.km.session_msg("alice", "ghost-key", {"VOTE"}, 60, "g")
            self.km.grant_session("alice", "ghost-key", {"VOTE"}, 60, "g", self.kr.sign("alice#1", m), 5)
        with self.assertRaises(RuleViolation):
            self.km.grant_session("alice", "alice-s", {"VOTE"}, 60, "bs", "forged", 5)

    def test_active_key_and_banned_identity(self):
        sig = self.kr.sign("alice#1", self.msg)
        self.assertTrue(self.km.verify_action("alice", "VOTE", self.msg, sig, "alice#1", 1))
        self.assertFalse(self.km.verify_action("ghost", "VOTE", self.msg, sig, "alice#1", 1))
        self.r.register_ruling(MODULE, "b", "BAN", "alice")
        self.r.ban(Actor("COURT", "b"), "alice", 2, "x")
        self.assertFalse(self.km.verify_action("alice", "VOTE", self.msg, sig, "alice#1", 3))


if __name__ == "__main__":
    unittest.main()
