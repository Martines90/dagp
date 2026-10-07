"""Coordinated insider abuse: one thousand citizens, fifty elected administrators."""
import copy
import unittest
from dagp_ref.admin import AdminCouncil
from dagp_ref.crypto_sim import SimKeyring
from dagp_ref.emergency import Emergency
from tests.legacy_params import Params
from dagp_ref.roles import Actor,Role,RoleRegistry,Status
from dagp_ref.treasury import RuleViolation,Treasury

MODULE=Actor('MODULE','test')

def society():
    r=RoleRegistry(Params(min_citizen_age=1));kr=SimKeyring()
    for n in range(1000):
        a=f'a{n}' if n<50 else f'c{n}'
        r.register(a,f'op-{a}','family',10,0);r.approve(MODULE,a,0)
        if n<50:
            kr.register(a)
            for role in (Role.ADMIN,Role.REGISTRAR,Role.SAFETY_COUNCIL):
                ref=f'grant-{a}-{role.value}'
                r.register_ratification(MODULE,ref,f'GRANT:{role.value}',a)
                r.grant(Actor('VOTE',ref),a,role,1)
    return r,kr

class InsiderAbuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=society()
    def setUp(self):self.r,self.kr=copy.deepcopy(self.base);self.c=AdminCouncil('A',self.r,self.kr)
    def case(self,target='a0',height=100):
        m=self.c.open_message('a49',target,'e'*64,height)
        return self.c.open('a49',target,'e'*64,height,self.kr.sign('a49',m))
    def approve(self,a,case,height=100):
        return self.c.approve(a,case,height,self.kr.sign(a,self.c.approval_message(case)))
    def ruling(self,ref,action,target,issuer):
        self.r.register_ruling(MODULE,ref,action,target,issuer)
        return Actor('COURT',ref)
    def test_ten_hostile_admins_damage_is_bounded(self):
        accepted=0
        for n in range(50):
            actor=Actor.agent(f'a{n//5}');target=f'c{50+n}'
            try:self.r.suspend(actor,target,100,110,'malicious freeze');accepted+=1
            except RuleViolation:pass
        self.assertEqual(accepted,20)
        self.assertEqual(sum(i.status is Status.SUSPENDED for i in self.r.ids.values()),20)
        self.assertEqual(len(self.r.protection_events),20)
        self.r.tick(110)
        self.assertTrue(all(self.r.get(f'c{50+n}').status is Status.ACTIVE for n in range(50)))
    def test_25_of_50_contain_official_24_do_not(self):
        case=self.case()
        for n in range(1,25):self.assertFalse(self.approve(f'a{n}',case))
        self.assertTrue(self.r.can('a0','REGISTRAR_ACT',100)[0])
        self.assertTrue(self.approve('a25',case))
        for action in ('REGISTRAR_ACT','PAUSE','ADMIN_VOTE'):self.assertFalse(self.r.can('a0',action,100)[0])
        self.assertTrue(self.r.can('a0','VOTE',100)[0]);self.assertTrue(self.r.can('a0','FILE_CASE',100)[0])
        self.assertEqual(self.r.get('a0').status,Status.ACTIVE)
        with self.assertRaises(RuleViolation):self.r.suspend(Actor.agent('a0'),'c50',100,110,'retaliation')
        with self.assertRaises(RuleViolation):self.r.ban(self.ruling('retaliate','BAN','c50','a0'),'c50',100,'retaliation')
        self.assertTrue(self.r.can('a0','REGISTRAR_ACT',400)[0])
    def test_ten_cannot_recall_honest_admin(self):
        case=self.case('a40')
        for n in range(10):self.assertFalse(self.approve(f'a{n}',case))
        self.assertEqual(self.c.threshold,25);self.assertTrue(self.r.can('a40','REGISTRAR_ACT',100)[0])
    def test_duplicate_replay_wrong_chain_and_bad_signature(self):
        case=self.case();self.approve('a1',case)
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.approve('a1',case)
        with self.assertRaises(RuleViolation):self.c.approve('a2',case,100,'forged')
        self.assertEqual(before,self.r.__dict__)
        with self.assertRaises(RuleViolation):self.approve('a0',case)
        other=AdminCouncil('B',self.r,self.kr)
        sig=self.kr.sign('a49',self.c.open_message('a49','a1','e'*64,100))
        with self.assertRaises(RuleViolation):other.open('a49','a1','e'*64,100,sig)
    def test_roster_cannot_shrink_during_case_or_by_admin_request(self):
        case=self.case();self.r.get('a49').status=Status.SUSPENDED
        self.assertEqual(self.c.threshold,25)
        with self.assertRaises(RuleViolation):self.c.refresh(Actor.agent('a1'),100)
        with self.assertRaises(RuleViolation):self.approve('a49',case)
    def test_same_operator_votes_do_not_multiply(self):
        case=self.case()
        for n in range(1,26):self.r.get(f'a{n}').operator='cartel'
        for n in range(1,26):self.assertFalse(self.approve(f'a{n}',case))
    def test_expired_vote_snapshot_copy_and_no_chained_hold(self):
        case=self.case();self.c.case(case).approvals.update({f'a{n}' for n in range(50)})
        self.assertFalse(self.approve('a1',case))
        with self.assertRaises(RuleViolation):self.approve('a2',case,200)
        second=self.case('a1',201)
        for n in range(2,27):self.approve(f'a{n}',second,201)
        with self.assertRaises(RuleViolation):self.case('a1',501)
    def test_operator_and_combined_ban_suspend_revoke_budgets(self):
        self.r.get('a1').operator=self.r.get('a0').operator
        self.r.suspend(Actor.agent('a0'),'c50',100,110,'spam')
        self.r.ban(self.ruling('ban','BAN','c51','a0'),'c51',100,'court')
        before=copy.deepcopy(self.r.__dict__)
        ref=self.ruling('third','REVOKE:CITIZEN','c52','a1');before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.revoke(ref,'c52',Role.CITIZEN,100,'bypass')
        self.assertEqual(before,self.r.__dict__)
    def test_reference_rotation_cannot_reset_court_budget(self):
        for n in range(2):self.r.ban(self.ruling(f'b{n}','BAN',f'c{50+n}','a0'),f'c{50+n}',100,'court')
        third=self.ruling('fresh-reference','BAN','c52','a0')
        with self.assertRaises(RuleViolation):self.r.ban(third,'c52',100,'court')
        self.assertNotIn('fresh-reference',self.r.used_refs)
    def test_rolling_window_has_no_midnight_burst_or_backdating(self):
        day=self.r.p.protection_day_blocks
        for n in range(2):self.r.suspend(Actor.agent('a0'),f'c{50+n}',day-1,day+5,'spam')
        with self.assertRaises(RuleViolation):self.r.suspend(Actor.agent('a0'),'c52',day,day+5,'boundary')
        with self.assertRaises(RuleViolation):self.r.suspend(Actor.agent('a0'),'c52',1,5,'backdate')
        self.r.suspend(Actor.agent('a0'),'c52',2*day-1,2*day+5,'new day')
    def test_global_ban_cap_across_ten_admins(self):
        for n in range(5):self.r.ban(self.ruling(f'ban{n}','BAN',f'c{50+n}',f'a{n}'),f'c{50+n}',100,'court')
        sixth=self.ruling('sixth','BAN','c55','a5')
        with self.assertRaises(RuleViolation):self.r.ban(sixth,'c55',100,'court')
        self.assertNotIn('sixth',self.r.used_refs)
    def test_ten_safety_members_cannot_pause_every_project(self):
        t=Treasury(100);e=Emergency(self.r.p,self.r,t)
        for n in range(20):t.reserve_and_grant(f'p{n}',[1])
        for n in range(10):e.pause(f'a{n}',f'p{n}',100+n,1,'investigation')
        before=copy.deepcopy((t,e.history,self.r.protection_events))
        with self.assertRaises(RuleViolation):e.pause('a10','p10',110,1,'shutdown')
        self.assertEqual(before,(t,e.history,self.r.protection_events))
    def test_authorization_reference_cannot_be_reassigned(self):
        self.r.register_ruling(MODULE,'fixed','BAN','c50','a0')
        with self.assertRaises(RuleViolation):self.r.register_ruling(MODULE,'fixed','BAN','c51','a1')
        with self.assertRaises(RuleViolation):self.r.register_ratification(MODULE,'fixed','GRANT:ADMIN','c51')
    def test_quarantined_official_can_get_independent_review(self):
        case=self.case()
        for n in range(1,26):self.approve(f'a{n}',case)
        self.r.lift_admin_hold(self.ruling('review','ADMIN_RESTORE','a0','a49'),'a0',101)
        self.assertTrue(self.r.can('a0','ADMIN_VOTE',101)[0])

    def test_concurrent_pauses_cannot_shut_down_all_projects(self):
        t=Treasury(100);e=Emergency(self.r.p,self.r,t)
        for n in range(20):t.reserve_and_grant(f'p{n}',[1])
        for n in range(4):e.pause(f'a{n}',f'p{n}',100,5,'investigation')
        with self.assertRaises(RuleViolation):e.pause('a4','p4',100,5,'shutdown')
        self.assertEqual(sum(e.is_paused(f'p{n}',100) for n in range(20)),4)
    def test_invalid_security_configuration_is_rejected(self):
        for name,value in [('protection_day_blocks',0),('sanction_actor_limit',True),
                           ('admin_vote_window',-1),('pause_concurrent_bps',10001)]:
            with self.assertRaises(ValueError):Params(**{name:value})
    def test_official_role_revocation_cannot_bypass_budget(self):
        for n in range(2):
            target=f'a{40+n}';ref=self.ruling(f'revoke{n}','REVOKE:REGISTRAR',target,'a0')
            self.r.revoke(ref,target,Role.REGISTRAR,100,'court')
        target='a42';ref=self.ruling('revoke3','REVOKE:REGISTRAR',target,'a0')
        with self.assertRaises(RuleViolation):self.r.revoke(ref,target,Role.REGISTRAR,100,'bypass')
    def test_unattributed_court_references_share_one_budget(self):
        for n in range(2):
            self.r.register_ruling(MODULE,f'legacy{n}','BAN',f'c{50+n}')
            self.r.ban(Actor('COURT',f'legacy{n}'),f'c{50+n}',100,'court')
        self.r.register_ruling(MODULE,'legacy3','BAN','c52')
        with self.assertRaises(RuleViolation):self.r.ban(Actor('COURT','legacy3'),'c52',100,'bypass')
    def test_validator_sanctions_preserve_quorum_and_minimum(self):
        from dataclasses import replace
        self.r.p=replace(self.r.p,min_validators=3)
        nodes=[f'c{n}' for n in range(50,57)]
        for a in nodes:self.r.get(a).roles.add(Role.VALIDATOR)
        self.r.validators=nodes
        for n in range(2):self.r.suspend(self.ruling(f'node{n}','SUSPEND',nodes[n],f'a{n}'),nodes[n],100,110,'court')
        third=self.ruling('node3','SUSPEND',nodes[2],'a2');before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.suspend(third,nodes[2],100,110,'kill quorum')
        self.assertEqual(before,self.r.__dict__)

    def test_sanction_budget_exhaustion_does_not_block_protective_removal(self):
        for n in range(20):self.r.suspend(Actor.agent(f'a{n//2}'),f'c{50+n}',100,110,'attack')
        case=self.case(height=101)
        for n in range(10,35):self.approve(f'a{n}',case,101)
        ref=self.ruling('dismiss','ADMIN_DISMISS','a0','a49')
        self.r.dismiss_admin(ref,'a0',102)
        self.assertEqual(self.r.get('a0').roles,{Role.CITIZEN})
        self.assertTrue(self.r.can('a0','VOTE',500)[0]);self.assertFalse(self.r.can('a0','REGISTRAR_ACT',500)[0])
    def test_court_cannot_dismiss_official_without_peer_containment(self):
        ref=self.ruling('premature','ADMIN_DISMISS','a0','a49');before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.dismiss_admin(ref,'a0',100)
        self.assertEqual(before,self.r.__dict__)
    def test_containment_never_disables_validator_quorum(self):
        self.r.get('a0').roles.add(Role.VALIDATOR);self.r.validators=['a0']
        case=self.case()
        for n in range(1,26):self.approve(f'a{n}',case)
        self.assertTrue(self.r.can('a0','VALIDATE',100)[0])
        self.r.dismiss_admin(self.ruling('review','ADMIN_DISMISS','a0','a49'),'a0',101)
        self.assertTrue(self.r.can('a0','VALIDATE',101)[0])

    def test_operator_wide_exclusion_needs_public_vote(self):
        ref=self.ruling('operator-ban','BAN','c50','a0');before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.ban(ref,'c50',100,'collective punishment',ban_operator=True)
        self.assertEqual(before,self.r.__dict__)
    def test_council_parameter_changes_cannot_change_open_vote(self):
        from dataclasses import replace
        case=self.case();self.r.p=replace(self.r.p,admin_containment_duration=99999)
        with self.assertRaises(RuleViolation):self.approve('a1',case)

    def test_registrar_freeze_preserves_ballot_appeal_and_key_custody(self):
        from dagp_ref.session import snapshot_electorate
        from dagp_ref.keys import KeyManager
        victim='c50';manager=KeyManager(self.r.p,self.r,self.kr);manager.enroll(victim)
        self.r.suspend(Actor.agent('a0'),victim,100,110,'spam')
        for action in ('VOTE','ENDORSE','FILE_CASE'):self.assertTrue(self.r.can(victim,action,100)[0])
        self.assertIn(victim,snapshot_electorate(self.r,100).ids)
        new=manager.new_key(victim)
        manager.begin_rotation(victim,new,'nonce',manager.sign_op('ROTATE',victim,'c50#1',new,'nonce'),100)
        manager.cancel(victim,'cancel',manager.sign_op('CANCEL',victim,'c50#1',new,'cancel'),101)
        self.assertIsNone(manager.state[victim].pending)
    def test_court_suspension_still_restricts_civic_powers(self):
        self.r.suspend(self.ruling('court','SUSPEND','c50','a0'),'c50',100,110,'judicial')
        self.assertFalse(self.r.can('c50','VOTE',100)[0])

    def test_spam_freeze_does_not_shield_target_from_judicial_review(self):
        self.r.suspend(Actor.agent('a0'),'c50',100,110,'spam')
        self.r.suspend(self.ruling('upgrade','SUSPEND','c50','a1'),'c50',101,115,'judicial')
        self.assertFalse(self.r.can('c50','VOTE',101)[0])
        self.assertEqual(self.r.get('c50').suspended_by,'COURT')

    def test_cluster_quota_failure_is_atomic_for_all_members(self):
        actors={}
        for n in range(3):
            a=f'c{50+n}';self.r.get(a).operator='ring'
            actors[a]=self.ruling(f'cluster{n}','SUSPEND',a,'a0')
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.suspend_cluster(Actor('COURT','batch'),'ring',100,110,actors)
        self.assertEqual(before,self.r.__dict__)
    def test_admission_global_quota_is_shared_across_admins(self):
        for n in range(251):self.r.register(f'new{n}',f'new-op{n}','f',10,100)
        for n in range(250):self.r.approve(Actor.agent(f'a{n//50}'),f'new{n}',100)
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.approve(Actor.agent('a5'),'new250',100)
        self.assertEqual(before,self.r.__dict__)
    def test_accountable_court_issuer_cannot_sanction_self(self):
        ref=self.ruling('self','BAN','a0','a0');before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.ban(ref,'a0',100,'self ruling')
        self.assertEqual(before,self.r.__dict__)

    def test_registrar_cannot_strip_or_restore_citizenship_roles(self):
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.revoke(Actor.agent('a0'),'a40',Role.CITIZEN,100,'purge')
        self.assertEqual(before,self.r.__dict__)
        self.r.revoke(self.ruling('citizenship','REVOKE:CITIZEN','c50','a0'),'c50',Role.CITIZEN,100,'judicial')
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.grant(Actor.agent('a1'),'c50',Role.CITIZEN,101)
        self.assertEqual(before,self.r.__dict__)
