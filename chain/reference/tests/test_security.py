"""Malicious-input regressions from the security review; every refusal must be atomic."""
import copy
from dataclasses import replace
import unittest
from dagp_ref.comprehension import Submission, Verdict, grade_item_verdicts
from dagp_ref.ledger import Ledger
from dagp_ref.roles import Actor
from dagp_ref.session import Effects, Phase
from dagp_ref.treasury import CreditLedger, RuleViolation, Treasury
from tests.fixtures import MODULE, Society
from tests.test_keys import world, set_guardians

class MoneyAttacks(unittest.TestCase):
    def test_invalid_amounts_cannot_mint_credits(self):
        for method in ('spend','grant','penalize'):
            for amount in (-10,True,1.5):
                with self.subTest(method=method,amount=amount):
                    c=CreditLedger();c.grant('A',5);before=copy.deepcopy(c.__dict__)
                    with self.assertRaises(RuleViolation):getattr(c,method)('A',amount)
                    self.assertEqual(before,c.__dict__)
    def test_pause_cannot_be_bypassed_by_omitting_height(self):
        t=Treasury(100);t.reserve_and_grant('p',[50]);t.paused_until['p']=100;before=copy.deepcopy(t.__dict__)
        with self.assertRaises(RuleViolation):t.release_next('p',3,3)
        self.assertEqual(before,t.__dict__)
    def test_zero_attestation_threshold_cannot_release_money(self):
        t=Treasury(100);t.reserve_and_grant('p',[50])
        with self.assertRaises(RuleViolation):t.release_next('p',0,0)
        self.assertEqual(t.released['p'],0)
    def test_reserved_project_cannot_be_granted_twice(self):
        t=Treasury(100);t.reserve('p',40);before=copy.deepcopy(t.__dict__)
        with self.assertRaises(RuleViolation):t.reserve_and_grant('p',[20])
        self.assertEqual(before,t.__dict__)
    def test_invalid_tranches_cannot_consume_reservation(self):
        for tranches in ([],[True],[1.5],[-1],[0]):
            with self.subTest(tranches=tranches):
                t=Treasury(100);t.reserve('p',40);before=copy.deepcopy(t.__dict__)
                with self.assertRaises(RuleViolation):t.commit_reserved('p',tranches)
                self.assertEqual(before,t.__dict__)

class RecoveryAttacks(unittest.TestCase):
    def test_guardians_must_have_distinct_operators(self):
        kr,r,km=world();r.get('g2').operator=r.get('g1').operator
        with self.assertRaises(RuleViolation):set_guardians(km)
    def test_cancelled_recovery_cannot_be_replayed(self):
        kr,r,km=world();set_guardians(km);new=km.new_key('alice')
        sigs={g:km.sign_op('RECOVER','alice',f'{g}#1',new,'rn') for g in ('g1','g2')}
        km.begin_recovery('alice',new,'rn',sigs,10)
        km.cancel('alice','cancel',km.sign_op('CANCEL','alice','alice#1',new,'cancel'),20);before=copy.deepcopy(km.state)
        with self.assertRaises(RuleViolation):km.begin_recovery('alice',new,'rn',sigs,21)
        self.assertEqual(before,km.state)
    def test_unknown_session_key_refusal_does_not_burn_nonce(self):
        kr,r,km=world();m=km.session_msg('alice','unknown',{'VOTE'},60,'n');before=copy.deepcopy(km.state)
        with self.assertRaises(RuleViolation):km.grant_session('alice','unknown',{'VOTE'},60,'n',kr.sign('alice#1',m),5)
        self.assertEqual(before,km.state)
    def test_unknown_rotation_target_cannot_brick_identity(self):
        kr,r,km=world();sig=km.sign_op('ROTATE','alice','alice#1','unknown','n')
        with self.assertRaises(RuleViolation):km.begin_rotation('alice','unknown','n',sig,5)
        self.assertIsNone(km.state['alice'].pending)

class ExamAttacks(unittest.TestCase):
    def attempt(self):
        soc=Society();s=soc.session();v=soc.citizens[0];att=s.request_exam(v,'secret',55)
        plan=s.plan(att,('a1','a2'));panel=s.panel_for(att.ticket)
        sub=Submission(att.ticket,('a1','a2'),soc.answers(s,plan,ok_art=False))
        truth=grade_item_verdicts(s.bank,plan,sub)
        return soc,s,v,att,sub,panel,{m:truth for m in panel.members}
    def test_rejected_grade_has_no_slash_or_scoreboard_side_effects(self):
        soc,s,v,att,sub,panel,verdicts=self.attempt();before=copy.deepcopy((s.slashed,s.scoreboard,s.issued,soc.reg.get(v).bond))
        with self.assertRaises(RuleViolation):s.grade(att,sub,verdicts,[],55)
        self.assertEqual(before,(s.slashed,s.scoreboard,s.issued,soc.reg.get(v).bond))
    def test_ticket_cannot_be_graded_twice(self):
        soc,s,v,att,sub,panel,verdicts=self.attempt();s.grade(att,sub,verdicts,list(panel.members),55)
        before=copy.deepcopy((s.slashed,s.issued,soc.reg.get(v).bond))
        with self.assertRaises(RuleViolation):s.grade(att,sub,verdicts,list(panel.members),56)
        self.assertEqual(before,(s.slashed,s.issued,soc.reg.get(v).bond))
    def test_cross_issue_attempt_is_not_a_grading_ticket(self):
        soc,s,v,att,sub,panel,verdicts=self.attempt()
        with self.assertRaises(RuleViolation):s.grade(replace(att,issue='other'),sub,verdicts,list(panel.members),55)
    def test_precast_correction_cannot_be_bypassed_with_old_token(self):
        soc=Society();s=soc.session();v=soc.citizens[0];att,tok,_=soc.get_token(s,v,declared=('a1','a2'),ok_art=False,hostile=2)
        s.audit(att.ticket,Verdict(True,0,True),56);s.cast_ballot(v,'Y',tok,'sec',att.n,s.electorate.proof(v),57)
        self.assertEqual(s._sealed[v][1],soc.p.base_weight)
    def test_audit_correction_updates_ballot_commitment(self):
        soc=Society();s=soc.session();v=soc.citizens[0];att,tok,_=soc.get_token(s,v,declared=('a1','a2'),ok_art=False,hostile=2)
        s.cast_ballot(v,'Y',tok,'sec',att.n,s.electorate.proof(v),55);before=s.commits[v]
        s.audit(att.ticket,Verdict(True,0,True),56);self.assertNotEqual(before,s.commits[v])
    def test_mutating_record_after_open_cannot_change_exam(self):
        soc=Society();s=soc.session();s.bank.article_cluster['a2']='a1'
        with self.assertRaises(RuleViolation):s.request_exam(soc.citizens[0],'sec',55)
    def test_auditor_cannot_inflate_read_weight(self):
        soc=Society();s=soc.session();att,tok,_=soc.get_token(s,soc.citizens[0],declared=())
        with self.assertRaises(RuleViolation):s.audit(att.ticket,Verdict(True,100,False),56)

class ProcessAttacks(unittest.TestCase):
    def test_partial_block_refusal_is_atomic(self):
        def apply(state,tx):
            state['n']+=1
            if tx['fail']:raise RuleViolation('refuse')
        l=Ledger(apply,{'n':0});before=copy.deepcopy((l.state,l.blocks,l.head))
        with self.assertRaises(RuleViolation):l.append([{'fail':False},{'fail':True}])
        self.assertEqual(before,(l.state,l.blocks,l.head))
    def test_returned_block_and_input_do_not_alias_history(self):
        l=Ledger(lambda s,t:s.update(n=t['n']),{'n':0});txs=[{'n':1}];block=l.append(txs);txs[0]['n']=99;block['txs'][0]['n']=77
        self.assertEqual(l.blocks[0]['txs'][0]['n'],1)
    def test_grant_effects_cannot_change_after_open(self):
        soc=Society();t=Treasury(100);effects=Effects(t,CreditLedger(),'p',40,[20,20],'A');s=soc.session(effects=effects)
        effects.tranches[0]=100;self.assertEqual(s.effects.tranches,[20,20])
    def test_failed_finalize_does_not_mark_final(self):
        soc=Society();t=Treasury(100);s=soc.session(effects=Effects(t,None,'p',40,[20,20],'A'))
        for v in soc.citizens[:25]:soc.vote(s,v,'Y')
        s.close(s.w.vote_end);s.advance(s.w.certify_end);s.effects.tranches=[50];before=copy.deepcopy((s.phase,s.outcome,t.__dict__))
        with self.assertRaises(RuleViolation):s.finalize(s.w.challenge_end)
        self.assertEqual(before,(s.phase,s.outcome,t.__dict__))
    def test_finalized_session_cannot_extend(self):
        soc=Society();s=soc.session();soc.run_to_final(s)
        with self.assertRaises(RuleViolation):s.extend(MODULE,10)
    def test_challenge_flood_is_bounded_per_identity(self):
        soc=Society();s=soc.session();s.close(s.w.vote_end);s.advance(s.w.certify_end);s.challenge('c0','complaint',s.w.certify_end)
        with self.assertRaises(RuleViolation):s.challenge('c0','new wording',s.w.certify_end)

class SortitionAttacks(unittest.TestCase):
    def test_chosen_secrets_and_retries_do_not_select_a_friendlier_panel(self):
        soc=Society();s=soc.session();v=soc.citizens[0]
        panels=[]
        for secret in ('chosen-1','chosen-2','chosen-3'):
            a=s.request_exam(v,secret,55);panels.append(s.panel_for(a.ticket).members)
        self.assertEqual(len(set(panels)),1)
    def test_same_operator_sibling_cannot_grade_owner(self):
        soc=Society();s=soc.session();v=soc.citizens[0]
        for e in s.pool[:3]:soc.reg.get(e).operator=soc.reg.get(v).operator
        a=s.request_exam(v,'s',55);panel=s.panel_for(a.ticket)
        self.assertTrue(all(soc.reg.get(m).operator!=soc.reg.get(v).operator for m in panel.members))
    def test_token_issued_without_successful_grade_is_not_accepted(self):
        from dagp_ref.comprehension import issue_token
        soc=Society();s=soc.session();v=soc.citizens[0];a=s.request_exam(v,'s',55);panel=s.panel_for(a.ticket)
        token=issue_token(panel,soc.kr,s.issue,a.ticket,Verdict(True,10,False),list(panel.members),55,soc.p)
        with self.assertRaises(RuleViolation):s.cast_ballot(v,'Y',token,'s',a.n,s.electorate.proof(v),55)

class SummaryAttacks(unittest.TestCase):
    def test_negative_shards_cannot_cancel_each_other(self):
        from dagp_ref.scale import ShardSummary, tally_sharded
        from dagp_ref.tally import Kind, Outcome
        soc=Society()
        shards=[ShardSummary(0,1,-3,0,0,b'x'*32),ShardSummary(1,1,9,0,0,b'y'*32)]
        result,_=tally_sharded(shards,2,2,Kind.ORDINARY,soc.p)
        self.assertEqual(result.outcome,Outcome.INVALID)
    def test_fabricated_election_points_are_rejected(self):
        from dagp_ref.scale import ElectionShard,election_from_shards
        soc=Society();qs=['A','B','C','D']
        shard=ElectionShard(tuple((q,100) for q in qs),0,1)
        self.assertFalse(election_from_shards([shard],qs,soc.p).valid)
    def test_unresolved_case_releases_reservation_after_grace(self):
        soc=Society();t=Treasury(100);s=soc.session(effects=Effects(t,None,'p',40,[20,20],'A'))
        s.close(s.w.vote_end);s.advance(s.w.certify_end);s.challenge('c0','complaint',s.w.certify_end)
        with self.assertRaises(RuleViolation):s.finalize(s.w.challenge_end)
        self.assertEqual(s.finalize(s.w.challenge_end+soc.p.challenge_resolution_grace),'VOIDED')
        self.assertEqual(t.free,100);self.assertNotIn('p',t.reserved)
    def test_changed_block_header_fails_verification(self):
        l=Ledger(lambda s,t:s.update(n=t['n']),{'n':0});l.append([{'n':1}]);l.blocks[0]['height']=99
        self.assertFalse(Ledger.verify(l.blocks,l.apply_fn,{'n':0}))
