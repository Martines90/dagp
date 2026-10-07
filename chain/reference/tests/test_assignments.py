"""Production-policy adversarial task selection and mandatory consumer boundaries."""
import copy
import unittest
from dagp_ref.assignments import TaskAssignments
from dagp_ref.crypto_sim import SimKeyring,H,hx
from dagp_ref.params import Params
from dagp_ref.roles import Actor,Role,RoleRegistry
from dagp_ref.sortition import draw_independent
from dagp_ref.payments import MilestonePayments
from dagp_ref.treasury import RuleViolation
M=Actor('MODULE','test')

class Assignments(unittest.TestCase):
    def setUp(self):
        self.r=RoleRegistry(Params(protection_day_blocks=1,min_citizen_age=1))
        self.kr=SimKeyring()
        for n in range(40):
            a=f'a{n}';self.r.register(a,f'op{n}',f'f{n%4}',10,0);self.r.approve(M,a,0);self.kr.register(a)
        for n in range(12):
            a=f'a{n}';ref='s'+a;self.r.register_ratification(M,ref,'GRANT:VOTE_SUPERVISOR',a)
            self.r.grant(Actor('VOTE',ref),a,Role.VOTE_SUPERVISOR,30)
        for n in range(12):self.r.grant(M,f'a{n}',Role.VERIFIER,32,stake=50)
        self.s=TaskAssignments('chain',self.r)
    def freeze(self,task='p',height=40):return self.s.freeze(M,'review',task,('a30',),self.s._round+1,height)
    def finish(self,task='p',height=41,seed=b'x'*32):
        self.s.publish_beacon(M,self.s._round+1,seed,height)
        return self.s.assign(M,'review',task,height)
    def test_pool_fixed_before_future_beacon_and_audited(self):
        frozen=self.freeze();self.assertEqual(len(frozen.pool),12)
        with self.assertRaises(RuleViolation):self.s.publish_beacon(M,1,b'x'*32,40)
        result=self.finish();self.assertEqual(len(result.members),2)
        self.assertEqual(result.commitment,frozen.commitment);self.assertTrue(self.r.verify_audit())
    def test_non_keeper_cannot_freeze_reveal_or_assign(self):
        for f in (lambda:self.s.freeze(Actor.agent('a30'),'review','p',('a30',),1,40),
                  lambda:self.s.publish_beacon(Actor.agent('a30'),1,b'x'*32,41),
                  lambda:self.s.assign(Actor.agent('a30'),'review','p',41)):
            with self.assertRaises(RuleViolation):f()
    def test_known_beacon_cannot_be_used_to_freeze_new_pool(self):
        self.freeze();self.finish()
        with self.assertRaises(RuleViolation):self.s.freeze(M,'review','q',('a31',),1,41)
    def test_duplicate_and_parallel_tasks_cannot_shop_results(self):
        self.freeze()
        for task in ('p','alternate-task-id'):
            with self.assertRaises(RuleViolation):self.freeze(task)
        result=self.finish();before=copy.deepcopy(self.s._events)
        self.assertEqual(self.s.assign(M,'review','p',41),result)
        self.assertEqual(self.s._events,before)
    def test_new_workers_do_not_join_frozen_pool(self):
        frozen=self.freeze()
        self.r.register_ratification(M,'new','GRANT:VOTE_SUPERVISOR','a12')
        self.r.grant(Actor('VOTE','new'),'a12',Role.VOTE_SUPERVISOR,40)
        result=self.finish(height=42)
        self.assertNotIn('a12',result.members);self.assertEqual(self.s._tasks['review','p'],frozen)
    def test_same_operator_and_entire_party_are_excluded(self):
        # Registry membership is trusted state, not the requesting owner's exclusion list.
        class Parties:pass
        parties=Parties();parties._party={'a30':'Owners','a0':'Owners'};parties._members={'Owners':{'a30','a0'}}
        self.r.party_registry=parties;self.r.get('a1').operator='op30'
        frozen=self.freeze();self.assertFalse({'a0','a1'}&{a for a,_,_ in frozen.pool})
    def test_conflict_created_after_freeze_is_rechecked(self):
        self.freeze();result=self.finish();selected=result.members[0]
        class Parties:pass
        parties=Parties();parties._party={'a30':'Owners',selected:'Owners'};parties._members={'Owners':{'a30',selected}}
        self.r.party_registry=parties
        with self.assertRaises(RuleViolation):self.s.require('chain','review','p',result.members,41,('a30',))
    def test_caller_cannot_substitute_chain_task_subjects_or_workers(self):
        self.freeze();result=self.finish()
        for chain,task,members,subjects in (('other','p',result.members,('a30',)),
            ('chain','q',result.members,('a30',)),('chain','p',('a10','a11'),('a30',)),
            ('chain','p',result.members,('a31',))):
            with self.assertRaises(RuleViolation):self.s.require(chain,'review',task,members,41,subjects)
    def test_suspension_or_metadata_change_invalidates_receipt(self):
        self.freeze();result=self.finish();member=result.members[0]
        self.r.admin_holds[member]=50
        with self.assertRaises(RuleViolation):self.s.require('chain','review','p',result.members,41,('a30',))
        del self.r.admin_holds[member];self.r.get(member).operator='new-op'
        with self.assertRaises(RuleViolation):self.s.require('chain','review','p',result.members,41,('a30',))
    def test_repeated_pairs_are_bounded_and_no_convenient_fallback(self):
        for a in range(2,12):self.r.get(f'a{a}').roles.discard(Role.VOTE_SUPERVISOR)
        for n in range(2):self.freeze(f'p{n}',40+n*2);self.finish(f'p{n}',41+n*2)
        before=copy.deepcopy(self.s._events)
        with self.assertRaises(RuleViolation):self.freeze('p2',44)
        self.assertNotIn(('review','p2'),self.s._tasks)
        self.assertEqual(self.s._events,before)
        self.freeze('p2',75);result=self.finish('p2',76)
        self.assertEqual(len(result.members),2)
    def test_monoculture_cannot_fill_review_panel(self):
        for n in range(12):self.r.get(f'a{n}').family='same-family'
        self.freeze();self.s.publish_beacon(M,1,b'x'*32,41)
        with self.assertRaises(RuleViolation):self.s.assign(M,'review','p',41)
    def test_operator_aliases_do_not_change_operator_lottery_odds(self):
        for n in range(2,12):self.r.get(f'a{n}').operator='op1'
        seeds=[H('test',n) for n in range(100)]
        for seed in seeds:
            first=draw_independent(seed,['a0','a1'],1,self.r)
            aliases=draw_independent(seed,[f'a{n}' for n in range(12)],1,self.r)
            self.assertEqual(self.r.get(first[0]).operator,self.r.get(aliases[0]).operator)
    def test_unassigned_verifiers_cannot_fund_and_assigned_policy_is_exact(self):
        payments=MilestonePayments('chain',self.r,self.kr,100)
        with self.assertRaises(RuleViolation):payments.fund('p',[10],('a0','a1','a2'),2,('op30',),40)
        self.assertEqual(payments.snapshot().free,100)
        self.s.freeze(M,'verification','p',('a30',),1,40)
        self.s.publish_beacon(M,1,b'x'*32,41);result=self.s.assign(M,'verification','p',41)
        payments.fund('p',[10],result.members,2,('op30',),41)
        self.assertEqual(payments.snapshot().free,90)
    def test_supervisors_reject_handpicked_lists(self):
        # Exercise the actual review constructor with a valid original draft.
        from dagp_ref.review import ProposalReview,VotingDraft
        from dagp_ref.proposal import Envelope
        self.r.grant(M,'a30',Role.PARTY_MEMBER,40)
        draft=VotingDraft('Title','Goal','Result','Body',Envelope(hx('goal','Goal'),hx('result','Result'),()),0,())
        with self.assertRaisesRegex(RuleViolation,'committed task assignment'):
            ProposalReview('chain','p','a30','Owners',{'Owners':{'a30'}},('a0','a1'),draft,self.r,self.kr,40,50)
        self.freeze();result=self.finish()
        review=ProposalReview('chain','p','a30','Owners',{'Owners':{'a30'}},result.members,draft,self.r,self.kr,41,50)
        self.assertEqual(review._supervisors,result.members)
    def test_backward_clock_and_mutable_beacon_are_rejected(self):
        self.freeze();self.finish()
        with self.assertRaises(RuleViolation):self.s.publish_beacon(M,1,b'y'*32,42)
        with self.assertRaises(RuleViolation):self.s.require('chain','review','p',('a0','a1'),40,('a30',))
    def test_selected_worker_loss_does_not_change_the_lottery(self):
        self.freeze();baseline=copy.deepcopy(self.s);result=self.finish()
        # Replay the same frozen roster and beacon with one selected worker contained.
        baseline.publish_beacon(M,1,b'x'*32,41)
        baseline.reg.admin_holds[result.members[0]]=50
        with self.assertRaisesRegex(RuleViolation,'no post-beacon substitution'):
            baseline.assign(M,'review','p',41)
        self.assertNotIn(('review','p'),baseline._results)
    def test_certification_constructor_rejects_unassigned_board(self):
        from dagp_ref.comprehension import Board,AttemptRegistry
        from dagp_ref.session import VoteSession,Windows
        from dagp_ref.tally import Kind
        from tests.fixtures import build_bank
        bank,_=build_bank('p')
        with self.assertRaisesRegex(RuleViolation,'committed task assignment'):
            VoteSession('p',Kind.ORDINARY,self.r.p,self.r,self.kr,b'x'*32,10,
                Board('chosen',('a0','a1'),'p'),bank,AttemptRegistry(self.r.p),b'x'*32,40,
                Windows(50,60,70),recused=frozenset({'a30'}))
    def test_handpicked_exam_panels_require_distinct_operators_and_families(self):
        for n in range(1,12):self.r.get(f'a{n}').operator='alias-op'
        selected=draw_independent(b'x'*32,[f'a{n}' for n in range(12)],5,self.r)
        self.assertEqual(len(selected),2)
        self.assertEqual(len({self.r.get(a).operator for a in selected}),len(selected))
    def test_generic_assignment_supports_remaining_operational_roles(self):
        for role,kind in ((Role.JUROR,'jury'),(Role.REVIEWER,'outcome'),(Role.EXECUTOR,'executor')):
            for n in range(12):self.r.grant(M,f'a{n}',role,40,stake=50)
            round=self.s._round+1;height=40+2*round
            self.s.freeze(M,kind,kind,('a30',),round,height)
            self.s.publish_beacon(M,round,b'x'*32,height+1)
            result=self.s.assign(M,kind,kind,height+1)
            self.assertEqual(len({self.r.get(a).operator for a in result.members}),len(result.members))
    def test_previous_stage_cannot_verify_its_own_process(self):
        self.freeze();reviewers=self.finish().members
        self.s.freeze(M,'verification','p',('a30',),2,42)
        self.s.publish_beacon(M,2,b'y'*32,43)
        verifiers=self.s.assign(M,'verification','p',43).members
        self.assertFalse(set(reviewers)&set(verifiers))
    def test_stalled_task_requires_delayed_ratified_cancellation(self):
        frozen=self.freeze()
        with self.assertRaises(RuleViolation):self.s.cancel(Actor.agent('a30'),'review','p',42,'a'*64)
        self.r.register_ratification(M,'cancel','ASSIGNMENT_CANCEL',frozen.commitment)
        vote=Actor('VOTE','cancel')
        with self.assertRaises(RuleViolation):self.s.cancel(vote,'review','p',41,'a'*64)
        self.assertNotIn('cancel',self.r.used_refs)
        self.s.cancel(vote,'review','p',42,'a'*64)
        with self.assertRaises(RuleViolation):self.s.assign(M,'review','p',42)
        with self.assertRaises(RuleViolation):self.freeze('p',42)
        # A fresh future-round request is permitted; the old task remains a tombstone.
        self.freeze('q',42)
    def test_repeated_governance_cancellation_cannot_be_a_reroll_service(self):
        frozen=self.freeze();self.r.register_ratification(M,'c1','ASSIGNMENT_CANCEL',frozen.commitment)
        self.s.cancel(Actor('VOTE','c1'),'review','p',42,'a'*64)
        frozen=self.freeze('q',42);self.r.register_ratification(M,'c2','ASSIGNMENT_CANCEL',frozen.commitment)
        with self.assertRaises(RuleViolation):self.s.cancel(Actor('VOTE','c2'),'review','q',44,'b'*64)
        self.assertNotIn('c2',self.r.used_refs)
    def test_court_accountable_admin_cannot_be_handpicked(self):
        for n in range(12):
            ref='admin'+str(n);self.r.register_ratification(M,ref,'GRANT:ADMIN',f'a{n}')
            self.r.grant(Actor('VOTE',ref),f'a{n}',Role.ADMIN,31)
        with self.assertRaisesRegex(RuleViolation,'court issuer was not randomly assigned'):
            self.r.register_ruling(M,'court','BAN','a30',issuer='a0',height=40)
        self.s.freeze(M,'admin_review','court:court',('a30',),1,40)
        self.s.publish_beacon(M,1,b'x'*32,41);result=self.s.assign(M,'admin_review','court:court',41)
        self.r.register_ruling(M,'court','BAN','a30',issuer=result.members[0],height=41)
        self.assertEqual(self.r.ruling_issuers['court'],result.members[0])
    def test_exam_pool_cannot_be_narrowed_and_retries_keep_independent_panel(self):
        from dagp_ref.comprehension import Board,AttemptRegistry
        from dagp_ref.session import VoteSession,Windows
        from dagp_ref.tally import Kind
        from tests.fixtures import build_bank
        for n in range(40,100):
            a=f'a{n}';self.r.register(a,f'op{n}',f'f{n%4}',10,0);self.r.approve(M,a,0);self.kr.register(a)
        for n in range(100):self.r.grant(M,f'a{n}',Role.EXAMINER,40,stake=50)
        self.s.freeze(M,'certification','p',('a30',),1,40)
        self.s.publish_beacon(M,1,b'x'*32,41);assigned=self.s.assign(M,'certification','p',41)
        bank,_=build_bank('p');attempts=AttemptRegistry(self.r.p);board=Board('b',assigned.members,'p')
        def session(pool,beacon=b'x'*32):
            return VoteSession('p',Kind.ORDINARY,self.r.p,self.r,self.kr,b'x'*32,10,
                board,bank,attempts,beacon,41,Windows(50,60,70),recused=frozenset({'a30'}),pool=pool)
        with self.assertRaisesRegex(RuleViolation,'full eligible examiner pool'):
            session(list(assigned.members))
        with self.assertRaisesRegex(RuleViolation,"committed assignment beacon"):
            session(self.r.agents_with(Role.EXAMINER,41),b'y'*32)
        vote=session(self.r.agents_with(Role.EXAMINER,41))
        voter=next(a for a in self.r.ids if a not in board.members and a!='a30')
        first=vote.request_exam(voter,'one',42);panel=vote.panel_for(first.ticket)
        other=attempts.open('p',voter,'two')
        self.assertEqual(panel.members,vote.panel_for(other.ticket).members)
        self.assertEqual(len(panel.members),len({self.r.get(a).operator for a in panel.members}))
        self.assertFalse({self.r.get(a).operator for a in board.members}&{self.r.get(a).operator for a in panel.members})
        self.r.get(panel.members[0]).family='changed-family'
        with self.assertRaisesRegex(RuleViolation,'metadata changed'):vote.panel_for(first.ticket)
    def test_public_assignment_snapshot_is_complete_and_cannot_mutate_state(self):
        self.freeze();result=self.finish();snapshot=self.s.snapshot('review','p')
        self.assertEqual(snapshot['result']['members'],result.members)
        self.assertEqual(snapshot['beacon']['seed'],(b'x'*32).hex())
        snapshot['frozen']['task']='tampered';snapshot['result']['digest']='tampered'
        self.assertEqual(self.s.snapshot('review','p')['frozen']['task'],'p')
        self.assertEqual(self.s.snapshot('review','p')['result']['digest'],result.digest)
