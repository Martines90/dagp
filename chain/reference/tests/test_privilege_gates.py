"""Security boundaries tested against production defaults, without legacy timing overrides."""
import copy
import unittest
from dagp_ref.params import Params
from dagp_ref.policy import validate_changes
from dagp_ref.roles import Actor,Role,RoleRegistry
from dagp_ref.admin import AdminCouncil
from dagp_ref.crypto_sim import SimKeyring
from dagp_ref.treasury import RuleViolation

M=Actor('MODULE','test')
D=Params().protection_day_blocks

class PrivilegeGates(unittest.TestCase):
    def setUp(self):
        self.r=RoleRegistry(Params())
        for n in range(70):
            a=f'c{n}'
            self.r.register(a,f'op{n}','family',10,0);self.r.approve(M,a,0)
    def vote(self,a,role,ref=None,sponsor=None):
        ref=ref or f'{a}-{role.value}'
        self.r.register_ratification(M,ref,'GRANT:'+role.value,a,sponsor=sponsor)
        return Actor('VOTE',ref)
    def appoint(self,a,role=Role.ADMIN,h=30*D,sponsor=None,ref=None):
        v=self.vote(a,role,ref,sponsor);self.r.grant(v,a,role,h);return v
    def sponsor(self):self.appoint('c0');return 'c0'
    def test_citizen_cannot_vote_join_or_endorse_before_warmup(self):
        for action in ('VOTE','JOIN_PARTY','ENDORSE'):
            self.assertFalse(self.r.can('c0',action,3*D-1)[0])
            self.assertTrue(self.r.can('c0',action,3*D)[0])
    def test_month_tenure_applies_to_every_sensitive_office(self):
        for role in (Role.ADMIN,Role.REGISTRAR,Role.SAFETY_COUNCIL,Role.VOTE_SUPERVISOR):
            with self.subTest(role=role):
                v=self.vote('c0',role)
                with self.assertRaises(RuleViolation):self.r.grant(v,'c0',role,30*D-1)
                self.assertNotIn(v.ident,self.r.used_refs)
                self.r.grant(v,'c0',role,30*D)
    def test_no_sensitive_action_before_activation_even_direct_role_checks(self):
        for role,action in ((Role.ADMIN,'ADMIN_VOTE'),(Role.REGISTRAR,'REGISTRAR_ACT'),
                (Role.SAFETY_COUNCIL,'PAUSE'),(Role.VOTE_SUPERVISOR,'SUPERVISE_VOTE')):
            self.appoint('c0',role)
            self.assertNotIn(role,self.r.effective_roles('c0',32*D-1))
            self.assertFalse(self.r.can('c0',action,32*D-1)[0])
            self.assertTrue(self.r.can('c0',action,32*D)[0])
    def test_pending_registrar_cannot_admit_applicants(self):
        self.appoint('c0',Role.REGISTRAR)
        self.r.register('new','newop','family',10,30*D)
        with self.assertRaises(RuleViolation):self.r.approve(Actor.agent('c0'),'new',32*D-1)
        self.r.approve(Actor.agent('c0'),'new',32*D)
    def test_pending_admin_cannot_sponsor_or_issue_rulings(self):
        self.sponsor();v=self.vote('c1',Role.ADMIN,sponsor='c0')
        with self.assertRaises(RuleViolation):self.r.grant(v,'c1',Role.ADMIN,32*D-1)
        with self.assertRaises(RuleViolation):self.r.register_ruling(M,'court','BAN','c2',issuer='c0',height=32*D-1)
        self.assertNotIn('court',self.r.rulings)
    def test_five_per_sponsor_across_office_types_and_rolling_boundary(self):
        self.sponsor()
        for n,role in enumerate((Role.ADMIN,Role.REGISTRAR,Role.SAFETY_COUNCIL,Role.VOTE_SUPERVISOR,Role.ADMIN),1):
            self.appoint(f'c{n}',role,h=32*D,sponsor='c0')
        v=self.vote('c6',Role.ADMIN,sponsor='c0')
        for h in (32*D+1,33*D-1):
            with self.assertRaises(RuleViolation):self.r.grant(v,'c6',Role.ADMIN,h)
        self.assertNotIn(v.ident,self.r.used_refs)
        self.r.grant(v,'c6',Role.ADMIN,33*D)
    def test_twenty_globally_even_without_admin_sponsor(self):
        for n in range(20):self.appoint(f'c{n}')
        v=self.vote('c20',Role.ADMIN)
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.grant(v,'c20',Role.ADMIN,31*D-1)
        self.assertEqual(before,self.r.__dict__)
        self.r.grant(v,'c20',Role.ADMIN,31*D)
    def test_unilateral_admin_cannot_appoint(self):
        self.sponsor()
        with self.assertRaises(RuleViolation):self.r.grant(Actor.agent('c0'),'c1',Role.ADMIN,32*D)
    def test_duplicate_grant_does_not_restart_delay_or_spend_vote(self):
        self.appoint('c0');v=self.vote('c0',Role.ADMIN,ref='duplicate')
        with self.assertRaises(RuleViolation):self.r.grant(v,'c0',Role.ADMIN,31*D)
        self.assertEqual(self.r.get('c0').role_ready[Role.ADMIN],32*D)
        self.assertNotIn(v.ident,self.r.used_refs)
    def test_revocation_before_activation_and_regrant_require_fresh_delay(self):
        self.appoint('c0')
        self.r.register_ratification(M,'revoke','REVOKE:ADMIN','c0')
        self.r.revoke(Actor('VOTE','revoke'),'c0',Role.ADMIN,31*D,'cancel')
        self.appoint('c0',h=32*D,ref='again')
        self.assertFalse(self.r.can('c0','ADMIN_VOTE',34*D-1)[0])
        self.assertTrue(self.r.can('c0','ADMIN_VOTE',34*D)[0])
    def test_contained_sponsor_loses_appointment_authority(self):
        self.sponsor();v=self.vote('c1',Role.ADMIN,sponsor='c0')
        self.r.admin_holds['c0']=35*D
        with self.assertRaises(RuleViolation):self.r.grant(v,'c1',Role.ADMIN,32*D)
        self.assertNotIn(v.ident,self.r.used_refs)
    def test_same_operator_sponsorship_is_refused(self):
        self.sponsor();self.r.get('c1').operator='op0'
        v=self.vote('c1',Role.SAFETY_COUNCIL,sponsor='c0')
        with self.assertRaises(RuleViolation):self.r.grant(v,'c1',Role.SAFETY_COUNCIL,32*D)
    def test_pending_admins_do_not_change_council_denominator(self):
        for n in range(5):self.appoint(f'c{n}')
        with self.assertRaises(RuleViolation):AdminCouncil('chain',self.r,SimKeyring(),height=32*D-1)
        council=AdminCouncil('chain',self.r,SimKeyring(),height=32*D)
        self.appoint('c5',h=32*D)
        self.assertEqual(council.threshold,3)
        self.assertEqual(self.r.agents_with(Role.ADMIN,32*D),[f'c{n}' for n in range(5)])
    def test_backdated_appointments_cannot_restore_expired_budgets(self):
        self.appoint('c0',h=32*D);v=self.vote('c1',Role.ADMIN)
        with self.assertRaises(RuleViolation):self.r.grant(v,'c1',Role.ADMIN,31*D)
    def test_security_floors_and_ceilings_cannot_be_disabled(self):
        for key,value in (('citizen_activation_days',2),('official_min_citizen_days',29),
                ('official_activation_days',1),('appointment_actor_limit',6),('appointment_global_limit',21)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):Params(**{key:value})
                with self.assertRaises(RuleViolation):validate_changes(Params(),((key,value),))
    def test_regranted_citizenship_resets_tenure(self):
        self.appoint('c0')
        self.r.register_ruling(M,'lose','REVOKE:CITIZEN','c0')
        self.r.revoke(Actor('COURT','lose'),'c0',Role.CITIZEN,32*D,'review')
        self.r.register_ruling(M,'restore','GRANT:CITIZEN','c0')
        self.r.grant(Actor('COURT','restore'),'c0',Role.CITIZEN,33*D)
        self.assertFalse(self.r.can('c0','ADMIN_VOTE',36*D)[0])
        self.assertTrue(self.r.can('c0','ADMIN_VOTE',63*D)[0])
    def test_operator_alias_cannot_double_sponsorship_budget(self):
        self.appoint('c0');self.appoint('c1')
        # Emulate two keys later proven to have one controlling operator.
        self.r.get('c1').operator=self.r.get('c0').operator
        for n in range(2,7):self.appoint(f'c{n}',Role.SAFETY_COUNCIL,32*D,sponsor='c0')
        v=self.vote('c7',Role.SAFETY_COUNCIL,sponsor='c1')
        with self.assertRaises(RuleViolation):self.r.grant(v,'c7',Role.SAFETY_COUNCIL,32*D)
    def test_ten_coordinated_sponsors_cannot_exceed_global_budget(self):
        for n in range(10):self.appoint(f'c{n}')
        accepted=0
        for n in range(50):
            v=self.vote(f'c{10+n}',Role.SAFETY_COUNCIL,sponsor=f'c{n//5}')
            try:self.r.grant(v,f'c{10+n}',Role.SAFETY_COUNCIL,32*D);accepted+=1
            except RuleViolation:pass
        self.assertEqual(accepted,20)
        self.assertEqual(sum(Role.SAFETY_COUNCIL in i.roles for i in self.r.ids.values()),20)
