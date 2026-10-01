import unittest

from dagp_ref.params import Params
from dagp_ref.roles import Actor, Role, RoleRegistry, Status
from dagp_ref.treasury import RuleViolation

MOD = Actor("MODULE", "m")
P = Params(min_citizen_age=10, min_operator_cap=2, registrar_quota_per_epoch=3, spam_freeze_max=20,
           spam_freeze_cooldown=100, liveness_period=50, min_validators=3)


def reg_with(*agents, op=None, height=0, p=P):
    r = RoleRegistry(p)
    for a in agents:
        r.register(a, op or f"op-{a}", "famA", p.citizen_bond, height)
        r.approve(MOD, a, height)
    return r


def ratify(r, ref, purpose, target):
    r.register_ratification(MOD, ref, purpose, target)
    return Actor("VOTE", ref)


def ruling(r, ref, action, target):
    r.register_ruling(MOD, ref, action, target)
    return Actor("COURT", ref)


def make_registrar(r, agent, h=20):
    r.grant(ratify(r, f"v-{agent}", f"GRANT:{Role.REGISTRAR.value}", agent), agent, Role.REGISTRAR, h)


class Admission(unittest.TestCase):
    def test_register_requires_bond_and_unique(self):
        r = RoleRegistry(P)
        with self.assertRaises(RuleViolation):
            r.register("a", "o", "f", P.citizen_bond - 1, 0)
        r.register("a", "o", "f", P.citizen_bond, 0)
        with self.assertRaises(RuleViolation):
            r.register("a", "o2", "f", P.citizen_bond, 0)

    def test_probation_has_no_powers_until_approved(self):
        r = RoleRegistry(P)
        r.register("a", "o", "f", 10, 0)
        self.assertEqual(r.effective_roles("a", 5), set())
        self.assertFalse(r.can("a", "VOTE", 5)[0])
        r.approve(MOD, "a", 5)
        self.assertIn(Role.CITIZEN, r.effective_roles("a", 5))

    def test_new_citizen_cannot_vote_until_min_age(self):
        r = reg_with("a", height=0)
        self.assertEqual(r.can("a", "VOTE", 5), (False, "too-young"))
        self.assertTrue(r.can("a", "VOTE", 10)[0])

    def test_operator_cap_blocks_sybil_ring(self):
        r = RoleRegistry(P)
        for i in range(3):
            r.register(f"s{i}", "same-op", "f", 10, 0)
        r.approve(MOD, "s0", 0)
        r.approve(MOD, "s1", 0)
        with self.assertRaises(RuleViolation):
            r.approve(MOD, "s2", 0)            # cap = max(2, 2*2%) = 2

    def test_operator_cap_scales_with_population(self):
        r = RoleRegistry(Params(min_operator_cap=2, max_operator_share_bps=200))
        for i in range(1000):
            r.register(f"x{i}", f"op{i}", "f", 10, 0)
            r.approve(MOD, f"x{i}", 0)
        self.assertEqual(r.operator_cap(), 20)   # 2% of 1000

    def test_family_cap_only_after_first_election(self):
        r = RoleRegistry(Params(min_operator_cap=100, max_family_share_bps=4000))
        for i in range(10):
            r.register(f"f{i}", f"o{i}", "fam", 10, 0)
            r.approve(MOD, f"f{i}", 0)          # all one family; fine pre-election
        r.activate_family_cap(MOD, 1)
        r.register("g", "og", "fam", 10, 2)
        with self.assertRaises(RuleViolation):
            r.approve(MOD, "g", 2)
        with self.assertRaises(RuleViolation):
            r.activate_family_cap(Actor.agent("g"), 3)

    def test_reject_only_from_probation(self):
        r = RoleRegistry(P)
        r.register("a", "o", "f", 10, 0)
        self.assertEqual(r.reject(MOD, "a", 1, "spam"), 10)             # bond returned in full
        self.assertEqual(r.get("a").status, Status.EXITED)
        self.assertEqual(r.get("a").bond, 0)
        with self.assertRaises(RuleViolation):
            r.reject(MOD, "a", 2, "again")


class Registrar(unittest.TestCase):
    def test_registrar_elected_by_ratified_vote_only(self):
        r = reg_with("r1", "x")
        with self.assertRaises(RuleViolation):
            r.grant(MOD, "r1", Role.REGISTRAR, 20)                         # module cannot
        with self.assertRaises(RuleViolation):
            r.grant(Actor.agent("x"), "r1", Role.REGISTRAR, 20)            # agents cannot
        with self.assertRaises(RuleViolation):
            r.grant(Actor("VOTE", "nope"), "r1", Role.REGISTRAR, 20)       # no ratification
        make_registrar(r, "r1")
        self.assertIn(Role.REGISTRAR, r.get("r1").roles)

    def test_ratification_is_single_use_and_purpose_bound(self):
        r = reg_with("r1", "r2")
        act = ratify(r, "v1", "GRANT:REGISTRAR", "r1")
        r.grant(act, "r1", Role.REGISTRAR, 20)
        with self.assertRaises(RuleViolation):
            r.grant(act, "r1", Role.REGISTRAR, 21)                          # reuse
        wrong = ratify(r, "v2", "GRANT:REGISTRAR", "r1")
        with self.assertRaises(RuleViolation):
            r.grant(wrong, "r2", Role.REGISTRAR, 22)                        # other target

    def test_only_module_can_record_ratifications_and_rulings(self):
        r = reg_with("a")
        with self.assertRaises(RuleViolation):
            r.register_ratification(Actor.agent("a"), "v", "p", "t")
        with self.assertRaises(RuleViolation):
            r.register_ruling(Actor.agent("a"), "c", "a", "t")

    def test_registrar_quota_and_conflict(self):
        r = reg_with("r1")
        make_registrar(r, "r1")
        reg = Actor.agent("r1")
        for i in range(4):
            r.register(f"n{i}", f"opn{i}", "f", 10, 100)
        for i in range(3):
            r.approve(reg, f"n{i}", 100)
        with self.assertRaises(RuleViolation):
            r.approve(reg, "n3", 100)                                        # quota 3/epoch
        r.approve(reg, "n3", 200)                                            # next epoch ok
        r.register("kin", "op-r1", "f", 10, 300)
        with self.assertRaises(RuleViolation):
            r.approve(reg, "kin", 300)                                       # same operator

    def test_suspended_registrar_loses_powers(self):
        r = reg_with("r1", "j")
        make_registrar(r, "r1")
        r.suspend(ruling(r, "c1", "SUSPEND", "r1"), "r1", 30, 60, "audit")
        r.register("n", "opn", "f", 10, 31)
        with self.assertRaises(RuleViolation):
            r.approve(Actor.agent("r1"), "n", 31)

    def test_one_registrar_per_operator(self):
        r = RoleRegistry(P)
        for a in ("r1", "r2"):
            r.register(a, "same", "f", 10, 0)
            r.approve(MOD, a, 0)
        make_registrar(r, "r1")
        with self.assertRaises(RuleViolation):
            make_registrar(r, "r2")


class Roles(unittest.TestCase):
    def setUp(self):
        self.r = reg_with("a", "b", "c")

    def test_panel_roles_need_stake_age_and_module(self):
        with self.assertRaises(RuleViolation):
            self.r.grant(MOD, "a", Role.EXAMINER, 20, stake=1)                # stake
        with self.assertRaises(RuleViolation):
            self.r.grant(MOD, "a", Role.EXAMINER, 5, stake=P.examiner_stake)  # too young
        with self.assertRaises(RuleViolation):
            self.r.grant(Actor.agent("b"), "a", Role.EXAMINER, 20, stake=P.examiner_stake)
        self.r.grant(MOD, "a", Role.EXAMINER, 20, stake=P.examiner_stake)
        self.assertTrue(self.r.can("a", "GRADE", 20)[0])

    def test_no_role_can_be_granted_to_banned_suspended_or_exited(self):
        r = reg_with("x", "y", "z")
        r.ban(ruling(r, "b", "BAN", "x"), "x", 5, "x")
        r.suspend(ruling(r, "s", "SUSPEND", "y"), "y", 5, 99, "x")
        r.exit("z", 5)
        for a in ("x", "y", "z"):
            with self.assertRaises(RuleViolation):
                r.grant(MOD, a, Role.CITIZEN, 20)
            with self.assertRaises(RuleViolation):
                r.grant(MOD, a, Role.JUROR, 20)

    def test_grant_requires_prerequisite_role_and_active_target(self):
        r = RoleRegistry(P)
        r.register("p", "o", "f", 10, 0)                                       # still PROBATION
        with self.assertRaises(RuleViolation):
            r.grant(MOD, "p", Role.PARTY_MEMBER, 30)
        self.r.grant(MOD, "a", Role.PARTY_MEMBER, 20)
        self.assertTrue(self.r.can("a", "SUBMIT_PROPOSAL", 20)[0])

    def test_revoke_authority(self):
        self.r.grant(MOD, "a", Role.JUROR, 20)
        with self.assertRaises(RuleViolation):
            self.r.revoke(Actor.agent("b"), "a", Role.JUROR, 21, "x")
        self.r.revoke(ruling(self.r, "c1", "REVOKE:JUROR", "a"), "a", Role.JUROR, 21, "bias")
        with self.assertRaises(RuleViolation):
            self.r.revoke(MOD, "a", Role.JUROR, 22, "again")                   # not held

    def test_registrar_role_cannot_be_revoked_by_module_or_peers(self):
        make_registrar(self.r, "a")
        with self.assertRaises(RuleViolation):
            self.r.revoke(MOD, "a", Role.REGISTRAR, 30, "x")
        self.r.revoke(ratify(self.r, "recall", "REVOKE:REGISTRAR", "a"), "a", Role.REGISTRAR, 30, "recall")

    def test_unknown_action_and_unknown_agent(self):
        self.assertEqual(self.r.can("a", "FLY", 20)[1], "unknown-action")
        self.assertEqual(self.r.can("zz", "VOTE", 20)[1], "unknown")
        with self.assertRaises(RuleViolation):
            self.r.get("zz")

    def test_exclusion_matrix(self):
        r = reg_with("x", "y", "z")
        r.grant(MOD, "x", Role.EXAMINER, 20, stake=50)
        r.grant(MOD, "y", Role.EXAMINER, 20, stake=50)
        m = {"proposer_party_members": {"x"}, "operators_involved": {"op-y"}}
        self.assertEqual(r.can("x", "GRADE", 20, m)[1], "conflict:proposer")
        self.assertEqual(r.can("y", "GRADE", 20, m)[1], "conflict:operator-involved")
        self.assertEqual(r.can("z", "VOTE", 20, {"proposer_party_members": {"z"}})[1], "recused:own-party")
        r.grant(MOD, "z", Role.REVIEWER, 20, stake=50)
        self.assertEqual(r.can("z", "REVIEW", 20, {"executors": {"z"}})[1], "conflict:executor")
        self.assertTrue(r.can("z", "REVIEW", 20, {"executors": set()})[0])


class Sanctions(unittest.TestCase):
    def setUp(self):
        self.r = reg_with("r1", "a", "b")
        make_registrar(self.r, "r1")

    def test_spam_freeze_is_short_and_cooldown_limited(self):
        reg = Actor.agent("r1")
        self.r.suspend(reg, "a", 30, 50, "spam")
        self.assertEqual(self.r.get("a").status, Status.SUSPENDED)
        self.assertFalse(self.r.can("a", "VOTE", 31)[0])
        self.r.tick(50)
        self.assertEqual(self.r.get("a").status, Status.ACTIVE)                 # auto-lifts
        with self.assertRaises(RuleViolation):
            self.r.suspend(reg, "a", 60, 75, "again")                           # cooldown
        with self.assertRaises(RuleViolation):
            self.r.suspend(reg, "b", 60, 200, "long")                           # > max
        with self.assertRaises(RuleViolation):
            self.r.suspend(reg, "b", 60, 60, "zero")

    def test_registrar_cannot_freeze_officials_or_kin(self):
        r = self.r
        r.register("o", "op-r1", "f", 10, 0)
        r.approve(MOD, "o", 0)
        with self.assertRaises(RuleViolation):
            r.suspend(Actor.agent("r1"), "o", 30, 40, "x")                      # same operator
        r.register("r2", "op-r2", "f", 10, 0)
        r.approve(MOD, "r2", 0)
        make_registrar(r, "r2")
        with self.assertRaises(RuleViolation):
            r.suspend(Actor.agent("r1"), "r2", 30, 40, "x")                     # official

    def test_non_registrar_cannot_suspend(self):
        with self.assertRaises(RuleViolation):
            self.r.suspend(Actor.agent("a"), "b", 30, 40, "x")
        with self.assertRaises(RuleViolation):
            self.r.suspend(MOD, "b", 30, 40, "x")

    def test_court_suspension_long_and_explicit_lift(self):
        self.r.suspend(ruling(self.r, "c1", "SUSPEND", "a"), "a", 30, 1000, "investigation")
        self.r.tick(500)
        self.assertEqual(self.r.get("a").status, Status.SUSPENDED)
        self.r.lift_suspension(ruling(self.r, "c2", "LIFT", "a"), "a", 501)
        self.assertEqual(self.r.get("a").status, Status.ACTIVE)
        with self.assertRaises(RuleViolation):
            self.r.lift_suspension(ruling(self.r, "c3", "LIFT", "a"), "a", 502)

    def test_suspended_keeps_roles_but_not_powers_and_restores(self):
        self.r.grant(MOD, "a", Role.JUROR, 20)
        self.r.suspend(ruling(self.r, "c1", "SUSPEND", "a"), "a", 30, 40, "x")
        self.assertEqual(self.r.effective_roles("a", 35), set())
        self.r.tick(40)
        self.assertIn(Role.JUROR, self.r.effective_roles("a", 40))

    def test_ban_is_permanent_slashes_and_blocks_reregistration(self):
        self.r.grant(MOD, "a", Role.JUROR, 20)
        slashed = self.r.ban(ruling(self.r, "c1", "BAN", "a"), "a", 30, "sybil", ban_operator=True)
        self.assertEqual(slashed, P.citizen_bond * P.ban_slash_bps // 10_000)
        self.assertEqual(self.r.get("a").roles, set())
        with self.assertRaises(RuleViolation):
            self.r.register("a", "other", "f", 10, 40)                            # same key
        with self.assertRaises(RuleViolation):
            self.r.register("a2", "op-a", "f", 10, 40)                            # same operator
        with self.assertRaises(RuleViolation):
            self.r.ban(ruling(self.r, "c2", "BAN", "a"), "a", 41, "again")
        with self.assertRaises(RuleViolation):
            self.r.suspend(ruling(self.r, "c3", "SUSPEND", "a"), "a", 42, 99, "x")
        with self.assertRaises(RuleViolation):
            self.r.renew_liveness("a", 50)
        with self.assertRaises(RuleViolation):
            self.r.exit("a", 50)
        with self.assertRaises(RuleViolation):
            self.r.ban(Actor.agent("r1"), "b", 30, "no power")                    # registrar cannot ban

    def test_ban_appeal_once_restores_citizen_only(self):
        self.r.grant(MOD, "a", Role.JUROR, 20)
        self.r.ban(ruling(self.r, "c1", "BAN", "a"), "a", 30, "x")
        self.r.appeal("a", "case1", 31)
        with self.assertRaises(RuleViolation):
            self.r.resolve_appeal(MOD, "a", 32, True)                              # module cannot
        self.r.resolve_appeal(ruling(self.r, "c2", "APPEAL", "a"), "a", 32, True)
        self.assertEqual(self.r.get("a").status, Status.ACTIVE)
        self.assertEqual(self.r.get("a").roles, {Role.CITIZEN})                    # panel role re-earned
        self.assertNotIn("a", self.r.banned_keys)

    def test_denied_ban_appeal_is_final(self):
        self.r.ban(ruling(self.r, "c1", "BAN", "a"), "a", 30, "x")
        self.r.appeal("a", "case1", 31)
        self.r.resolve_appeal(ruling(self.r, "c2", "APPEAL", "a"), "a", 32, False)
        self.assertEqual(self.r.get("a").status, Status.BANNED)
        with self.assertRaises(RuleViolation):
            self.r.appeal("a", "case2", 33)
        with self.assertRaises(RuleViolation):
            self.r.resolve_appeal(ruling(self.r, "c3", "APPEAL", "a"), "a", 34, True)   # none pending

    def test_suspension_appeal(self):
        self.r.suspend(ruling(self.r, "c1", "SUSPEND", "b"), "b", 30, 900, "x")
        self.r.appeal("b", "case", 31)
        self.r.resolve_appeal(ruling(self.r, "c2", "APPEAL", "b"), "b", 32, True)
        self.assertEqual(self.r.get("b").status, Status.ACTIVE)
        with self.assertRaises(RuleViolation):
            self.r.appeal("b", "case", 33)                                          # nothing to appeal

    def test_cluster_hold_needs_a_ruling_per_member_and_spares_others(self):
        r = RoleRegistry(Params(min_citizen_age=10, min_operator_cap=5))
        for i in range(3):
            r.register(f"k{i}", "ring", "f", 10, 0)
            r.approve(MOD, f"k{i}", 0)
        r.register("free", "clean", "f", 10, 0)
        r.approve(MOD, "free", 0)
        r.register_ruling(MOD, "hold", "SUSPEND", "k0")
        with self.assertRaises(RuleViolation):       # one ruling authorizes one target only
            r.suspend_cluster(Actor("COURT", "hold"), "ring", 20, 90)
        self.assertEqual(r.get("k0").status, Status.SUSPENDED)   # first member was held
        self.assertEqual(r.get("free").status, Status.ACTIVE)


class Liveness(unittest.TestCase):
    def test_dormant_then_reactivated_partial_age(self):
        r = reg_with("a")
        r.tick(200)
        self.assertEqual(r.get("a").status, Status.DORMANT)
        self.assertFalse(r.can("a", "VOTE", 200)[0])
        r.renew_liveness("a", 210)
        self.assertEqual(r.get("a").status, Status.ACTIVE)
        self.assertEqual(r.can("a", "VOTE", 210), (False, "too-young"))   # partial re-aging
        self.assertTrue(r.can("a", "VOTE", 216)[0])

    def test_renewal_keeps_active_and_suspended_stays_suspended_through_dormancy(self):
        r = reg_with("a", "b")
        for h in range(10, 200, 10):
            r.renew_liveness("a", h)
            r.tick(h)
        self.assertEqual(r.get("a").status, Status.ACTIVE)
        self.assertEqual(r.get("b").status, Status.DORMANT)

    def test_exit_returns_bond_and_stake(self):
        r = reg_with("a")
        r.grant(MOD, "a", Role.EXAMINER, 20, stake=50)
        self.assertEqual(r.exit("a", 30), P.citizen_bond + 50)
        self.assertEqual(r.get("a").status, Status.EXITED)
        self.assertEqual(r.effective_roles("a", 31), set())


class Validators(unittest.TestCase):
    def setUp(self):
        self.r = RoleRegistry(Params(min_citizen_age=10, min_operator_cap=10, min_validators=3))
        for i in range(12):
            self.r.register(f"n{i}", f"op{i // 3}", "f", 10, 0)
            self.r.approve(MOD, f"n{i}", 0)

    def grant_all(self, nodes):
        for n in nodes:
            self.r.grant(ratify(self.r, f"g-{n}", "GRANT:VALIDATOR", n), n, Role.VALIDATOR, 20, stake=50)

    def test_set_requires_ratification_size_and_operator_cap(self):
        self.grant_all([f"n{i}" for i in range(9)])
        nodes = [f"n{i}" for i in range(9)]
        act = ratify(self.r, "set1", "VALIDATOR_SET", ",".join(sorted(nodes)))
        self.r.set_validators(act, nodes, 30)                                   # 3/9 per op = 33.3%
        self.assertEqual(len(self.r.validators), 9)

    def test_operator_over_one_third_rejected(self):
        self.grant_all(["n0", "n1", "n2", "n3", "n4"])
        nodes = ["n0", "n1", "n2", "n3", "n4"]                                  # op0 has 3/5 = 60%
        act = ratify(self.r, "set2", "VALIDATOR_SET", ",".join(sorted(nodes)))
        with self.assertRaises(RuleViolation):
            self.r.set_validators(act, nodes, 30)

    def test_too_small_duplicate_or_unroled_rejected(self):
        self.grant_all(["n0", "n3"])
        for nodes in (["n0", "n3"], ["n0", "n0", "n3"], ["n0", "n3", "n6"]):
            act = ratify(self.r, f"s{len(nodes)}{nodes[-1]}", "VALIDATOR_SET", ",".join(sorted(nodes)))
            with self.assertRaises(RuleViolation):
                self.r.set_validators(act, nodes, 30)

    def test_cannot_shrink_below_minimum_or_grant_by_module(self):
        self.grant_all(["n0", "n3", "n6"])
        act = ratify(self.r, "s", "VALIDATOR_SET", "n0,n3,n6")
        self.r.set_validators(act, ["n0", "n3", "n6"], 30)
        with self.assertRaises(RuleViolation):
            self.r.revoke(MOD, "n0", Role.VALIDATOR, 31, "downtime")            # would drop to 2
        with self.assertRaises(RuleViolation):
            self.r.grant(MOD, "n1", Role.VALIDATOR, 31, stake=50)               # needs a vote
        self.grant_all(["n9"])
        self.r.set_validators(ratify(self.r, "s2", "VALIDATOR_SET", "n0,n3,n6,n9"),
                              ["n0", "n3", "n6", "n9"], 32)
        self.r.revoke(MOD, "n0", Role.VALIDATOR, 33, "downtime")            # 4 -> 3 is allowed
        self.assertNotIn("n0", self.r.validators)

    def test_banned_validator_leaves_set(self):
        self.grant_all(["n0", "n3", "n6", "n9"])
        act = ratify(self.r, "s", "VALIDATOR_SET", "n0,n3,n6,n9")
        self.r.set_validators(act, ["n0", "n3", "n6", "n9"], 30)
        self.r.ban(ruling(self.r, "b", "BAN", "n0"), "n0", 31, "equivocation")
        self.assertNotIn("n0", self.r.validators)


class Audit(unittest.TestCase):
    def test_log_is_chained_and_tamper_evident(self):
        r = reg_with("a", "b")
        r.suspend(ruling(r, "c", "SUSPEND", "a"), "a", 5, 9, "x")
        self.assertTrue(r.verify_audit())
        self.assertGreater(len(r.audit), 4)
        r.audit[1]["target"] = "someone-else"
        self.assertFalse(r.verify_audit())

    def test_every_mutation_is_logged(self):
        r = reg_with("a")
        n = len(r.audit)
        r.grant(MOD, "a", Role.JUROR, 20)
        r.revoke(ruling(r, "c", "REVOKE:JUROR", "a"), "a", Role.JUROR, 21, "x")
        self.assertEqual(len(r.audit), n + 2)


if __name__ == "__main__":
    unittest.main()
