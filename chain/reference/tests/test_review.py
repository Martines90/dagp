import copy
from dataclasses import replace
import unittest
from dagp_ref.crypto_sim import H,hx
from dagp_ref.proposal import Envelope
from dagp_ref.review import ProposalReview,VotingDraft,Milestone
from dagp_ref.roles import Actor,Role
from dagp_ref.session import Phase
from dagp_ref.treasury import Treasury,RuleViolation
from tests.fixtures import Society,MODULE

class Review(unittest.TestCase):
    def setUp(self):
        self.soc=Society();self.r=self.soc.reg;self.kr=self.soc.kr
        for a in ('c0','c1'):self.r.grant(MODULE,a,Role.PARTY_MEMBER,20)
        for a in ('c27','c28','c29'):
            ref='supervisor-'+a;self.r.register_ratification(MODULE,ref,'GRANT:VOTE_SUPERVISOR',a)
            self.r.grant(Actor('VOTE',ref),a,Role.VOTE_SUPERVISOR,20)
        self.d=VotingDraft('Library','Build shared library','Independent library acceptance','Original implementation',
            Envelope(hx('goal','Build shared library'),hx('result','Independent library acceptance'),(('treasury',100),)),
            100,(Milestone('design',40,'Reviewed design'),Milestone('delivery',60,'Verified delivery')))
        self.rev=ProposalReview('A','prop1','c0','Owners',{'Owners':{'c0'},'Others':{'c1'}},
            ('c27','c28','c29'),self.d,self.r,self.kr,50,60)
    def approve(self,a='c27',height=52):
        note='Same goal and result; caps and acceptance remain coherent'
        self.rev.approve(a,note,height,self.kr.sign(a,H(self.rev.approval_message(),note)))
    def lock(self,height=60):return self.rev.lock('c0',height,self.kr.sign('c0',self.rev.lock_message()))
    def amend(self,d=None,height=51,signature=None):
        d=d or replace(self.d,body='Refined implementation')
        self.rev.amend('c0',d,'n',height,signature or self.kr.sign('c0',self.rev.amendment_message(d,'n')))
    def open(self,treasury):
        template=self.soc.session(height=70)
        s=self.rev.open_vote(treasury,kind=template.kind,board=template.board,bank=template.bank,
            attempts=self.soc.attempts,beacon=template.beacon,open_height=70,windows=template.w,pool=self.soc.examiners)
        s.keys=template.keys
        return s
    def test_party_comments_and_owner_replies_are_linked(self):
        m=self.rev.comment_message('c1','Others','Please add verification',None,'n1')
        parent=self.rev.comment('c1','Others','Please add verification',None,'n1',50,self.kr.sign('c1',m))
        m=self.rev.comment_message('c0','Owners','Verification retained',parent,'n2')
        self.rev.comment('c0','Owners','Verification retained',parent,'n2',50,self.kr.sign('c0',m))
        self.assertEqual(self.rev.snapshot()['comments'][1]['parent'],0)
    def test_new_version_requires_two_independent_approvals(self):
        self.amend();self.approve()
        with self.assertRaises(RuleViolation):self.lock()
        self.approve('c28');self.assertEqual(self.lock().body,'Refined implementation')
    def test_amendment_invalidates_old_version_signatures(self):
        self.approve();self.approve('c28');old=self.rev.approval_message()
        self.amend(height=53)
        self.assertNotEqual(old,self.rev.approval_message())
        with self.assertRaises(RuleViolation):self.lock()
    def test_goal_change_budget_increase_and_new_resource_rejected(self):
        for d in (replace(self.d,goal='Different goal'),replace(self.d,budget=101),
                  replace(self.d,envelope=replace(self.d.envelope,caps=(('treasury',100),('power',1))))):
            before=self.rev.snapshot()
            with self.assertRaises(RuleViolation):self.amend(d)
            self.assertEqual(before,self.rev.snapshot())
    def test_forged_owner_amendment_is_atomic(self):
        before=self.rev.snapshot()
        with self.assertRaises(RuleViolation):self.amend(signature='forged')
        self.assertEqual(before,self.rev.snapshot())
    def test_same_operator_approvals_cannot_count_twice(self):
        self.approve();self.approve('c28');self.r.get('c28').operator=self.r.get('c27').operator
        with self.assertRaises(RuleViolation):self.lock()
    def test_contained_supervisor_cannot_approve(self):
        self.r.admin_holds['c27']=100
        with self.assertRaises(RuleViolation):self.approve()
    def test_insufficient_common_budget_does_not_open_vote(self):
        self.approve();self.approve('c28');self.lock();t=Treasury(99)
        with self.assertRaises(RuleViolation):self.open(t)
        self.assertEqual(t.free,99);self.assertEqual(t.reserved,{})
    def test_passed_budget_commits_exact_milestones_and_releases_once(self):
        self.approve();self.approve('c28');self.lock();t=Treasury(200);s=self.open(t)
        self.assertEqual(t.free,100);self.assertEqual(t.reserved,{'prop1':100})
        for a in self.soc.citizens[1:26]:self.soc.vote(s,a,'Y',height=75)
        self.soc.run_to_final(s)
        self.assertEqual(t.escrow['prop1'],100);self.assertEqual(t.milestone_conditions['prop1'],self.d.milestones)
        self.assertEqual(t.release_next('prop1',3,3,220),40)
        self.assertEqual(t.release_next('prop1',3,3,220),60)
        with self.assertRaises(RuleViolation):t.release_next('prop1',3,3,220)
        t.assert_invariants()
    def test_no_quorum_releases_common_budget_reservation(self):
        self.approve();self.approve('c28');self.lock();t=Treasury(200);s=self.open(t);self.soc.run_to_final(s)
        self.assertEqual(t.free,200);self.assertEqual(t.escrow,{})
    def test_amendments_after_lock_and_duplicate_vote_open_rejected(self):
        self.approve();self.approve('c28');self.lock()
        with self.assertRaises(RuleViolation):self.amend(height=60)
        t=Treasury(200);self.open(t)
        with self.assertRaises(RuleViolation):self.open(t)
        self.assertEqual(t.reserved,{'prop1':100})
    def test_milestones_must_match_budget(self):
        with self.assertRaises(RuleViolation):self.amend(replace(self.d,milestones=(Milestone('wrong',99,'Evidence'),)))
    def test_reviewed_effects_cannot_be_changed_while_voting(self):
        self.approve();self.approve('c28');self.lock();s=self.open(Treasury(200));s.effects.tranches[:]=[1,99]
        with self.assertRaises(RuleViolation):s.request_exam('c1','n',75)
    def test_minimum_notice_after_late_amendment(self):
        self.amend(height=59);self.approve(height=59);self.approve('c28',59)
        with self.assertRaises(RuleViolation):self.lock(60)
        self.lock(64)

    def test_zero_budget_policy_vote_creates_no_escrow(self):
        d=replace(self.d,budget=0,milestones=(),envelope=replace(self.d.envelope,caps=()))
        self.amend(d);self.approve();self.approve('c28');self.lock();t=Treasury(200);s=self.open(t)
        for a in self.soc.citizens[1:26]:self.soc.vote(s,a,'Y',height=75)
        self.soc.run_to_final(s);self.assertEqual(s.outcome.value,'PASSED');self.assertEqual(t.free,200);self.assertEqual(t.reserved,{})
    def test_reduced_budget_only_reserves_approved_amount(self):
        d=replace(self.d,budget=80,milestones=(Milestone('delivery',80,'Verified delivery'),),
                  envelope=replace(self.d.envelope,caps=(('treasury',80),)))
        self.amend(d);self.approve();self.approve('c28');self.lock();t=Treasury(200);self.open(t)
        self.assertEqual(t.free,120);self.assertEqual(t.reserved,{'prop1':80})
    def test_comment_replay_and_forgery_leave_thread_unchanged(self):
        m=self.rev.comment_message('c1','Others','Comment',None,'n')
        self.rev.comment('c1','Others','Comment',None,'n',50,self.kr.sign('c1',m));before=self.rev.snapshot()
        with self.assertRaises(RuleViolation):self.rev.comment('c1','Others','Comment',None,'n',50,self.kr.sign('c1',m))
        with self.assertRaises(RuleViolation):self.rev.comment('c1','Owners','Comment',None,'x',50,'forged')
        self.assertEqual(before,self.rev.snapshot())
    def test_one_commenter_cannot_exhaust_discussion_capacity(self):
        for n in range(20):
            nonce=str(n);m=self.rev.comment_message('c1','Others','Comment',None,nonce)
            self.rev.comment('c1','Others','Comment',None,nonce,50,self.kr.sign('c1',m))
        with self.assertRaises(RuleViolation):self.rev.comment('c1','Others','Comment',None,'21',50,'forged')
        m=self.rev.comment_message('c0','Owners','Reply',0,'r')
        self.rev.comment('c0','Owners','Reply',0,'r',50,self.kr.sign('c0',m))
    def test_filing_credit_charged_once_and_refunded_once_without_quorum(self):
        from dagp_ref.treasury import CreditLedger
        credits=CreditLedger();credits.grant('Owners',2)
        self.rev=ProposalReview('A','prop1','c0','Owners',{'Owners':{'c0'},'Others':{'c1'}},
            ('c27','c28','c29'),self.d,self.r,self.kr,50,60,credits)
        self.assertEqual(credits.balance['Owners'],1)
        self.approve();self.approve('c28');self.lock();s=self.open(Treasury(200));self.soc.run_to_final(s)
        self.assertEqual(credits.balance['Owners'],2)
        with self.assertRaises(RuleViolation):s.finalize(s.w.challenge_end)
        self.assertEqual(credits.balance['Owners'],2)
    def test_self_supervision_is_rejected(self):
        with self.assertRaises(RuleViolation):ProposalReview('A','prop1','c0','Owners',{'Owners':{'c0'}},
            ('c0','c27'),self.d,self.r,self.kr,50,60)
    def test_old_approval_signature_cannot_approve_new_text(self):
        note='Assessment';old=self.kr.sign('c27',H(self.rev.approval_message(),note));self.amend()
        with self.assertRaises(RuleViolation):self.rev.approve('c27',note,52,old)
    def test_budget_overrides_are_refused(self):
        self.approve();self.approve('c28');self.lock();t=Treasury(200)
        with self.assertRaises(RuleViolation):self.rev.open_vote(t,effects=None,kind=self.soc.session().kind)
        self.assertEqual(t.free,200)

    def test_registrar_cannot_freeze_vote_supervisors_to_block_review(self):
        self.r.register_ratification(MODULE,'registrar','GRANT:REGISTRAR','c2')
        self.r.grant(Actor('VOTE','registrar'),'c2',Role.REGISTRAR,20)
        before=copy.deepcopy(self.r.__dict__)
        with self.assertRaises(RuleViolation):self.r.suspend(Actor.agent('c2'),'c27',50,55,'delay review')
        self.assertEqual(before,self.r.__dict__)
