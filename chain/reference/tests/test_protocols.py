from dataclasses import replace
import unittest
from dagp_ref.payments import MilestoneApproval,MilestonePayments
from dagp_ref.roles import Role,Status
from dagp_ref.treasury import RuleViolation
from dagp_ref.proposal import Envelope,amendment_is_refinement
from tests.test_keys import world,set_guardians

class Payments(unittest.TestCase):
    def setUp(self):
        self.kr,self.reg,_=world()
        for g in ('g1','g2','g3'):
            self.reg.get(g).roles.add(Role.VERIFIER);self.kr.register(g)
        self.p=MilestonePayments('chain-A',self.reg,self.kr,100)
        self.p.fund('project',[20,30],('g1','g2','g3'),2,('op-alice',))
        self.a=MilestoneApproval('chain-A','project',0,20,'a'*64,10,20)
    def sigs(self,a=None):return {g:self.kr.sign(g,(a or self.a).message()) for g in ('g1','g2')}
    def refused(self,a=None,sigs=None,height=10):
        before=self.p.snapshot()
        with self.assertRaises(RuleViolation):self.p.release(a or self.a,sigs if sigs is not None else self.sigs(),height)
        self.assertEqual(before,self.p.snapshot())
    def test_valid_release_and_replay(self):
        self.assertEqual(self.p.release(self.a,self.sigs(),10),20);self.refused()
    def test_domain_amount_evidence_and_expiry_are_bound(self):
        for field,value in [('chain','chain-B'),('amount',30),('index',1),('evidence','b'*64),('expires',30)]:
            with self.subTest(field=field):self.refused(replace(self.a,**{field:value}))
        self.refused(height=9);self.refused(height=20)
    def test_count_alone_cannot_authorize(self):self.refused(sigs={'g1':self.sigs()['g1']})
    def test_forged_signature_cannot_authorize(self):self.refused(sigs={'g1':'forged','g2':self.sigs()['g2']})
    def test_operator_capture_rechecked(self):
        self.reg.get('g2').operator=self.reg.get('g1').operator;self.refused()
    def test_revoked_role_rechecked(self):
        self.reg.get('g1').roles.remove(Role.VERIFIER);self.refused()
    def test_suspended_verifier_rechecked(self):
        self.reg.get('g1').status=Status.SUSPENDED;self.refused()
    def test_returned_snapshot_cannot_modify_escrow(self):
        snapshot=self.p.snapshot();snapshot.free=999;self.assertEqual(self.p.snapshot().free,50)

    def test_authorized_pause_blocks_signed_payment_until_expiry(self):
        self.reg.get('g3').roles.add(Role.SAFETY_COUNCIL)
        self.p.pause('g3','project',10,5,'investigation')
        self.refused(height=14)
        self.assertEqual(self.p.release(self.a,self.sigs(),15),20)
    def test_minority_verifier_policy_is_rejected(self):
        before=self.p.snapshot()
        with self.assertRaises(RuleViolation):
            self.p.fund('other',[10],('g1','g2','g3'),1,('op-alice',))
        self.assertEqual(before,self.p.snapshot())

class RecoveryAndEnvelope(unittest.TestCase):
    def test_recovery_rechecks_operator_capture(self):
        kr,r,km=world();set_guardians(km);new=km.new_key('alice');r.get('g2').operator=r.get('g1').operator
        sigs={g:km.sign_op('RECOVER','alice',f'{g}#1',new,'n') for g in ('g1','g2')}
        with self.assertRaises(RuleViolation):km.begin_recovery('alice',new,'n',sigs,10)
        self.assertIsNone(km.state['alice'].pending)
    def test_banned_owner_pending_rotation_does_not_activate(self):
        kr,r,km=world();new=km.new_key('alice')
        km.begin_rotation('alice',new,'n',km.sign_op('ROTATE','alice','alice#1',new,'n'),5)
        r.get('alice').status=Status.BANNED;km.tick(100)
        self.assertEqual(km.state['alice'].active,'alice#1');self.assertIsNone(km.state['alice'].pending)
    def test_duplicate_negative_and_boolean_caps_are_not_refinements(self):
        original=Envelope('o','r',(('money',100),))
        for caps in [(('money',-1),),(('money',True),),(('money',20),('money',30))]:
            self.assertFalse(amendment_is_refinement(original,Envelope('o','r',caps)))

    def test_recovery_rechecks_guardians_at_activation(self):
        kr,r,km=world();set_guardians(km);new=km.new_key('alice')
        sigs={g:km.sign_op('RECOVER','alice',f'{g}#1',new,'n') for g in ('g1','g2')}
        km.begin_recovery('alice',new,'n',sigs,10)
        r.get('g2').operator=r.get('g1').operator;km.tick(300)
        self.assertEqual(km.state['alice'].active,'alice#1');self.assertIsNone(km.state['alice'].pending)
