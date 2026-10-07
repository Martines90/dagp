"""Nested governance and bilateral imports through real reference exam/vote sessions."""
import copy
import unittest
from dataclasses import replace
from dagp_ref.assignments import TaskAssignments
from dagp_ref.comprehension import AttemptRegistry,Board
from dagp_ref.crypto_sim import SimKeyring,H
from dagp_ref.params import Params
from dagp_ref.roles import Role,RoleRegistry,Actor,Status
from dagp_ref.session import VoteSession,Windows,Effects
from dagp_ref.societies import SocietyTree,digest
from dagp_ref.mergers import SocietyMerger
from dagp_ref.scale import Electorate,summarize_shard,tally_sharded,shard_of
from dagp_ref.tally import Ballot,Kind,Outcome,tally
from dagp_ref.treasury import Treasury,RuleViolation
from tests.fixtures import Society as ExamHelper,build_bank
M=Actor('MODULE','test')

class World(ExamHelper):
    def __init__(self,chain='A',n=100):
        self.p=Params(protection_day_blocks=1,min_citizen_age=1,board_fail_den=10,
                      exam_items=3,exam_panel=3,sample_articles=2)
        self.kr,self.reg=SimKeyring(),RoleRegistry(self.p)
        self.citizens=[f'c{i:03}' for i in range(n)]
        self.examiners=[f'e{i:03}' for i in range(40)]
        for a in self.citizens+self.examiners:
            self.reg.register(a,'op'+a,'f'+str(int(a[1:])%4),10,0)
            self.reg.approve(M,a,0);self.kr.register(a)
            self.kr._secrets[a]=H("isolated fixture chain key",chain,a)
        for a in self.examiners:self.reg.grant(M,a,Role.EXAMINER,30,stake=50)
        for a in self.citizens[41:71]:
            self.reg.register_ratification(M,'s'+a,'GRANT:VOTE_SUPERVISOR',a)
            # Appointment budget spans two committed days.
            self.reg.grant(Actor('VOTE','s'+a),a,Role.VOTE_SUPERVISOR,30+(int(a[1:])-41)//20)
        self.service=TaskAssignments(chain,self.reg)
        self.tree=SocietyTree(chain,'root',self.reg,self.kr,Treasury(1000),(('rights','equal standing'),))

    def assign(self,reg,kind,task,subjects,height):
        service=getattr(reg,'assignments',None)
        if service is None:service=TaskAssignments(self.tree.chain+':'+reg.scope,reg)
        rnd=service._round+1
        service.freeze(M,kind,task,subjects,rnd,height)
        seed=H('future test beacon',task,rnd)
        service.publish_beacon(M,rnd,seed,height+1)
        result=service.assign(M,kind,task,height+1)
        return result,seed

    def approve(self,request,height):
        r=self.tree._requests[request]
        for authority in self.tree.ancestry(r.scope)[:-1]:
            reg=self.tree.view(authority)
            result,_=self.assign(reg,'hierarchy_review',request,r.subjects,height)
            for a in result.members:
                note='Compatible with ancestor rules; bounded obligations.'
                self.tree.approve(request,a,note,height+1,self.kr.sign(a,self.tree.review_message(request,note,authority)),authority)
        if r.stage=='PRE':self.tree.activate_preapproval(request,height+1)
        return result

    def institutional(self,mandate,height,vote=True):
        result,seed=self.assign(mandate.registry,'certification',mandate.issue,mandate.subjects,height-1)
        bank,keys=build_bank(mandate.issue)
        session=VoteSession(mandate.issue,mandate.kind,self.p,mandate.registry,self.kr,
            mandate.electorate.root,mandate.electorate.size,Board('b',result.members,mandate.issue),bank,
            AttemptRegistry(self.p),seed,height,Windows(height+3,height+4,height+5),
            recused=frozenset({'c000'}),pool=mandate.registry.agents_with(Role.EXAMINER,height),
            approved_record_hash=mandate.payload,institutional=mandate)
        session.electorate=mandate.electorate;session.keys=keys
        if vote:
            for a in mandate.electorate.ids:
                if a not in session.board.members and a!='c000':self.vote(session,a,'Y',height=height+1)
            self.run_to_final(session)
        return session

    def form(self,parent='root',child='town',members=None,height=40):
        members=members or tuple(sorted(self.citizens[:30]+self.examiners[:20]))
        charter=(('local','town services'),)
        message=self.tree.formation_message(parent,child,members,charter,'n')
        request=self.tree.propose_child(parent,child,members,charter,'n',height,height+100,
                                        {a:self.kr.sign(a,message) for a in members})
        self.approve(request,height)
        mandates=self.tree.formation_mandates(child,height+1)
        sessions=[self.institutional(m,height+8+6*i) for i,m in enumerate(mandates)]
        activated=max(s.w.challenge_end for s in sessions)+7
        self.tree.activate_child(child,activated)
        return self.tree.view(child),activated

class NestedSocieties(unittest.TestCase):
    def setUp(self):self.w=World()
    def test_dual_consensus_creates_child_and_grandchild(self):
        view,h=self.w.form()
        self.assertEqual(self.w.tree.ancestry('town'),('root','town'))
        self.assertIn(('rights','equal standing'),self.w.tree.inherited_rules('town'))
        # Local offices require local votes and delays; root offices do not flow down.
        self.assertFalse(view.agents_with(Role.VOTE_SUPERVISOR,h))
        for a in self.w.citizens[21:30]:
            view.register_ratification(M,'local'+a,'GRANT:VOTE_SUPERVISOR',a)
            view.grant(Actor('VOTE','local'+a),a,Role.VOTE_SUPERVISOR,h)
        # A smaller subset retains enough independent qualified experts for its process.
        members=tuple(sorted(self.w.citizens[:20]+self.w.examiners[:10]))
        district,end=self.w.form('town','district',members,h+35)
        self.assertEqual(self.w.tree.ancestry('district'),('root','town','district'))
        self.assertNotIn('c099',district.ids)
        self.assertFalse(district.can('c099','VOTE',end)[0])
        self.assertTrue(district.can('c002','VOTE',end)[0])
        view.get('c002').status=Status.BANNED
        self.assertFalse(district.can('c002','VOTE',end)[0])
        self.assertTrue(self.w.reg.can('c002','VOTE',end)[0])

    def test_forged_founder_or_conflicting_charter_refused_atomically(self):
        members=tuple(self.w.citizens[:10]);before=copy.deepcopy(self.w.tree.nodes)
        for charter in ((('rights','no rights'),),()):
            with self.assertRaises(RuleViolation):self.w.tree.propose_child('root','bad',members,charter,'n',40,140,{a:'forged' for a in members})
            self.assertEqual(self.w.tree.nodes,before)

    def test_pending_child_has_no_authority_or_view(self):
        members=tuple(self.w.citizens[:10]);message=self.w.tree.formation_message('root','town',members,(),'n')
        self.w.tree.propose_child('root','town',members,(),'n',40,140,{a:self.w.kr.sign(a,message) for a in members})
        with self.assertRaises(RuleViolation):self.w.tree.view('town')
        from dagp_ref.societies import ScopedRegistry
        with self.assertRaises(RuleViolation):ScopedRegistry(self.w.tree,'town')
        with self.assertRaises(RuleViolation):self.w.tree.formation_mandates('town',40)

    def test_parent_preapproval_exact_version_budget_and_expiry(self):
        view,h=self.w.form();tree=self.w.tree
        with self.assertRaises(RuleViolation):tree.require_preapproval('town','p','v',h)
        r=tree.request(M,'town','p','version',200,('c000',),h+35,h+90)
        self.w.approve(r,h+35)
        self.assertEqual(tree.treasury.free,800)
        for payload,budget in [('changed',200),('version',201)]:
            with self.assertRaises(RuleViolation):tree.require_preapproval('town','p',payload,h+36,budget)
        tree.require_preapproval('town','p','version',h+36,200)
        with self.assertRaises(RuleViolation):tree.expire('town','p',h+90)
        tree.expire('town','p',h+91);self.assertEqual(tree.treasury.free,1000)
        tree.treasury.assert_invariants()

    def test_root_sanction_masks_local_powers_without_local_power_over_root(self):
        view,h=self.w.form();view.get('c002').status=Status.BANNED
        self.assertTrue(self.w.reg.can('c002','VOTE',h)[0])
        self.w.reg.get('c003').status=Status.BANNED
        self.assertFalse(view.can('c003','VOTE',h)[0])
        view.register_ratification(M,'office','GRANT:VOTE_SUPERVISOR','c020')
        view.grant(Actor('VOTE','office'),'c020',Role.VOTE_SUPERVISOR,h)
        self.assertTrue(view.can('c020','SUPERVISE_VOTE',h+2)[0])
        self.w.reg.admin_holds['c020']=h+10
        self.assertFalse(view.can('c020','SUPERVISE_VOTE',h+2)[0])
        self.assertTrue(view.can('c020','VOTE',h+2)[0])

    def test_ancestor_change_invalidates_permissions(self):
        view,h=self.w.form();tree=self.w.tree
        r=tree.request(M,'town','p','v',0,('c000',),h+35,h+90);self.w.approve(r,h+35)
        tree.nodes['root']=replace(tree.nodes['root'],charter=(('rights','updated equal rights'),))
        with self.assertRaises(RuleViolation):tree.require_preapproval('town','p','v',h+36)

    def test_direct_local_session_cannot_bypass_parent(self):
        view,h=self.w.form()
        with self.assertRaisesRegex(RuleViolation,'preapproval'):
            view.validate_session('unapproved','h',h,None,None,None)
        with self.assertRaises(RuleViolation):view.validate_draft('p',type('Draft',(),{'parameter_changes':(('quorum_bps',0),)})(),h)

    def test_nonassigned_parent_supervisor_cannot_approve(self):
        view,h=self.w.form();tree=self.w.tree
        r=tree.request(M,'town','p','v',0,('c000',),h+35,h+90)
        with self.assertRaises(RuleViolation):tree.approve(r,'c001','note',h+35,self.w.kr.sign('c001',tree.review_message(r,'note')))
        self.assertEqual(tree.treasury.free,1000)

    def test_budget_revision_releases_difference_before_any_vote(self):
        view,h=self.w.form();tree=self.w.tree
        first=tree.request(M,'town','p','old',200,('c000',),h+35,h+100);self.w.approve(first,h+35)
        revision=tree.request(M,'town','p','new',100,('c000',),h+70,h+130);self.w.approve(revision,h+70)
        self.assertEqual(tree.treasury.free,900)
        with self.assertRaises(RuleViolation):tree.require_preapproval('town','p','old',h+71)
        tree.require_preapproval('town','p','new',h+71,100);tree.treasury.assert_invariants()

    def test_real_local_review_vote_final_parent_checks_and_milestone_escrow(self):
        self._funded_local(False)

    def test_partial_local_bill_reserves_whole_ceiling_and_only_funds_approved_points(self):
        self._funded_local(True)

    def _funded_local(self,partial):
        from dagp_ref.review import ProposalReview,VotingDraft,Milestone,BillPoint
        from dagp_ref.proposal import Envelope
        from dagp_ref.crypto_sim import hx
        from dagp_ref.parties import PartyRegistry
        view,h=self.w.form();tree=self.w.tree
        for a in self.w.citizens[20:30]:
            view.register_ratification(M,'local'+a,'GRANT:VOTE_SUPERVISOR',a)
            view.grant(Actor('VOTE','local'+a),a,Role.VOTE_SUPERVISOR,h)
        parties=PartyRegistry('A:town',view,self.w.kr);owners=tuple(self.w.citizens[:10])
        parties.form('Local',owners,'n',h+3,{a:self.w.kr.sign(a,parties.formation_message('Local',owners,'n')) for a in owners})
        milestone=Milestone('done',100,'Independent audit verifies service delivery')
        milestones=(Milestone('first',60,'Deliver first service'),Milestone('second',40,'Deliver second service')) if partial else (milestone,)
        points=(BillPoint('first','First service',60,(milestones[0],)),BillPoint('second','Second service',40,(milestones[1],))) if partial else ()
        draft=VotingDraft('Town service','Provide service','Service delivered','Bounded implementation',
              Envelope(hx('goal','Provide service'),hx('result','Service delivered'),(('treasury',100),)),100,milestones,points)
        with self.assertRaises(RuleViolation):ProposalReview('A:town','service','c000','Local',{'Local':owners},(),draft,view,self.w.kr,h+35,h+45)
        request=tree.request(M,'town','service',draft.digest(),100,owners,h+35,h+120)
        self.w.approve(request,h+35)
        panel,_=self.w.assign(view,'review','service',owners,h+37)
        review=ProposalReview('A:town','service','c000','Local',{'Local':owners},panel.members,draft,view,self.w.kr,h+38,h+45)
        for a in panel.members:
            note='Refinement and milestones are compatible.'
            review.approve(a,note,h+38,self.w.kr.sign(a,H(review.approval_message(),note)))
        review.lock('c000',h+45,self.w.kr.sign('c000',review.lock_message()))
        cert,seed=self.w.assign(view,'certification','service',owners,h+45)
        bank,keys=build_bank('service')
        session=review.open_vote(kind=Kind.ORDINARY,board=Board('board',cert.members,'service'),bank=bank,
                attempts=AttemptRegistry(self.w.p),beacon=seed,open_height=h+46,windows=Windows(h+49,h+50,h+51),
                pool=view.agents_with(Role.EXAMINER,h+46))
        session.keys=keys
        for a in session.electorate.ids:self.w.vote(session,a,('Y','N') if partial else 'Y',height=h+47)
        self.w.run_to_final(session)
        self.assertEqual(tree.treasury.escrow,{})
        amount=60 if partial else 100
        final=tree.request(M,'town','service',draft.digest(),amount,owners,h+71,h+110,stage='FINAL')
        with self.assertRaises(RuleViolation):tree.finalize_local(final,session,(amount,),h+71)
        self.w.approve(final,h+71)
        with self.assertRaises(RuleViolation):tree.finalize_local(final,session,(50,50),h+72)
        project=tree.finalize_local(final,session,(amount,),h+72)
        self.assertEqual(tree.treasury.escrow[project],amount)
        self.assertEqual(tree.treasury.milestone_conditions[project],milestones[:1])
        self.assertNotIn(Role.PARTY_MEMBER,self.w.reg.get('c000').roles)
        tree.treasury.assert_invariants()


    def test_local_parameters_credential_revocation_and_metadata_follow_root(self):
        view,h=self.w.form()
        with self.assertRaises(RuleViolation):view.p=replace(self.w.p,quorum_bps=3000)
        self.assertTrue(view.can('e000','GRADE',h)[0])
        self.w.reg.get('e000').roles.discard(Role.EXAMINER)
        self.assertFalse(view.can('e000','GRADE',h)[0])
        self.w.reg.get('c002').operator='new-controller'
        self.assertEqual(view.get('c002').operator,'new-controller')


    def test_unknown_requests_and_child_identifiers_fail_closed(self):
        for operation in (lambda:self.w.tree.approve('missing','c041','note',40,'fake'),
                          lambda:self.w.tree.activate_child('missing',40),
                          lambda:self.w.tree.formation_mandates('missing',40)):
            with self.assertRaises(RuleViolation):operation()


class InstitutionalThresholds(unittest.TestCase):
    def setUp(self):self.p=Params(weight_mode='FLAT')
    def ballots(self,yes,no,abst):return [Ballot(str(i),c,1) for i,c in enumerate(['Y']*yes+['N']*no+['A']*abst)]
    def test_merger_exact_boundary_and_missing_participation(self):
        self.assertEqual(tally(self.ballots(64,16,0),100,Kind.MERGER,self.p).outcome,Outcome.PASSED)
        self.assertEqual(tally(self.ballots(63,17,0),100,Kind.MERGER,self.p).outcome,Outcome.FAILED)
        self.assertEqual(tally(self.ballots(79,0,0),100,Kind.MERGER,self.p).outcome,Outcome.NO_QUORUM)
    def test_abstention_attack_and_weighted_minority(self):
        self.assertEqual(tally(self.ballots(1,0,79),100,Kind.MERGER,self.p).outcome,Outcome.FAILED)
        p=Params();ballots=[Ballot(str(i),'Y' if i<64 else 'N',3 if i<64 else 13) for i in range(80)]
        self.assertEqual(tally(ballots,100,Kind.MERGER,p).outcome,Outcome.FAILED)
        ballots=[Ballot(str(i),'Y' if i<20 else 'N',13 if i<20 else 3) for i in range(80)]
        self.assertEqual(tally(ballots,100,Kind.MERGER,p).outcome,Outcome.FAILED)
    def test_direct_and_sharded_structural_tallies_agree(self):
        for kind in (Kind.FORMATION,Kind.MERGER):
            for counts in ((64,16,0),(66,20,14),(1,0,99),(80,0,0)):
                ballots=self.ballots(*counts);groups=[[b for b in ballots if shard_of(b.voter,4)==s] for s in range(4)]
                summaries=[summarize_shard(i,4,groups[i],self.p) for i in range(4)]
                self.assertEqual(tally(ballots,100,kind,self.p),tally_sharded(summaries,4,100,kind,self.p)[0])

class Mergers(unittest.TestCase):
    def setUp(self):
        self.a,self.b=World('A'),World('B')
        mapping=tuple((a,'merge:'+digest(('A',a))) for a in sorted(self.a.citizens+self.a.examiners))
        self.merge=SocietyMerger(self.a.tree,self.b.tree,'union',mapping,40,180)
    def prepare(self):
        for w in (self.a,self.b):
            task,subjects=self.merge._assessment[w.tree.chain]
            result,_=w.assign(w.reg,'hierarchy_review',task,subjects,40)
            for a in result.members:
                note='Identity-only reviewed mapping, no assets or imported offices.'
                self.merge.assess(w.tree,a,note,41,w.kr.sign(a,self.merge.assessment_message(w.tree.chain,note)))
        mandates=self.merge.mandates(41)
        for w,m in zip((self.a,self.b),mandates):w.institutional(m,71)
        self.merge.prepare(M,106)
    def signatures(self,a,height=106):
        target=self.merge.plan.manifest[self.merge._index[a]][1]
        if target not in self.b.kr._secrets:self.b.kr.register(target)
        if self.merge.state=='CLAIMING' and a not in self.merge._deposits and target not in self.b.reg.ids:
            self.merge.record_admission_bond(M,a,'deposit:'+a,self.b.p.citizen_bond,height)
        message=self.merge.claim_message(a,'n',170)
        return self.a.kr.sign(a,message),self.b.kr.sign(target,message)
    def test_bilateral_vote_optin_preserves_history_without_offices(self):
        self.prepare();a='c001';s,d=self.signatures(a)
        target=self.merge.claim(a,'n',170,self.merge.proof(a),s,d,106)
        self.assertEqual(self.a.reg.get(a).status,Status.EXITED)
        self.assertEqual(self.b.reg.get(target).roles,{Role.CITIZEN})
        self.assertFalse(self.b.reg.can(target,'VOTE',108)[0]);self.assertTrue(self.b.reg.can(target,'VOTE',109)[0])
        self.assertEqual(self.a.reg.get('c002').status,Status.ACTIVE)
        self.assertEqual((self.a.tree.treasury.free,self.b.tree.treasury.free),(1000,1000))
        self.assertTrue(self.a.reg.verify_audit());self.assertTrue(self.b.reg.verify_audit())
    def test_no_claim_before_bilateral_decisions(self):
        s,d=self.signatures('c001')
        with self.assertRaises(RuleViolation):self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)
    def test_forged_replay_wrong_proof_and_expired_claim(self):
        self.prepare();s,d=self.signatures('c001');before=copy.deepcopy(self.b.reg.ids)
        for proof,ss,expiry in [(self.merge.proof('c002'),s,170),(self.merge.proof('c001'),'fake',170),(self.merge.proof('c001'),s,100)]:
            with self.assertRaises(RuleViolation):self.merge.claim('c001','n',expiry,proof,ss,d,106)
            self.assertEqual(self.b.reg.ids,before)
        self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)
        with self.assertRaises(RuleViolation):self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)
    def test_sanction_operator_change_and_admission_cap_fail_closed(self):
        self.prepare();a='c001';s,d=self.signatures(a)
        self.a.reg.get(a).status=Status.BANNED
        with self.assertRaises(RuleViolation):self.merge.claim(a,'n',170,self.merge.proof(a),s,d,106)
        self.a.reg.get(a).status=Status.ACTIVE;self.a.reg.get(a).operator='alias'
        with self.assertRaises(RuleViolation):self.merge.claim(a,'n',170,self.merge.proof(a),s,d,106)
        self.a.reg.get(a).operator='opc001'
        for i in range(3):
            name='duplicate'+str(i);self.b.reg.register(name,'opc001','f1',10,106)
            if i<2:self.b.reg.approve(M,name,106)
        before=copy.deepcopy(self.b.reg.ids)
        with self.assertRaises(RuleViolation):self.merge.claim(a,'n',170,self.merge.proof(a),s,d,106)
        self.assertEqual(self.b.reg.ids,before);self.assertFalse(self.merge._claimed)
    def test_shared_daily_lane_and_settlement_preserve_optouts(self):
        self.prepare();s,d=self.signatures('c001');self.merge._events=[106]*self.merge.plan.daily_limit
        with self.assertRaises(RuleViolation):self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)
        self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,107)
        with self.assertRaises(RuleViolation):self.merge.settle(Actor.agent('c001'),181)
        self.merge.settle(M,181);self.assertEqual(self.merge.state,'SETTLED')
        self.assertEqual(self.a.reg.get('c002').status,Status.ACTIVE)
    def test_dedup_requires_current_receiving_owner_consent(self):
        a,b=World('X'),World('Y');mapping=tuple((x,x) for x in sorted(a.citizens+a.examiners))
        merger=SocietyMerger(a.tree,b.tree,'dedup',mapping,40,180)
        self.assertEqual(len(merger.plan.manifest),140)
        with self.assertRaises(RuleViolation):SocietyMerger(a.tree,b.tree,'asset',mapping,40,180,assets=(100,))

    def test_early_prepare_wrong_vote_domain_and_mutated_inventory(self):
        with self.assertRaises(RuleViolation):self.merge.prepare(M,106)
        self.prepare()
        s,d=self.signatures('c001')
        self.merge.plan=replace(self.merge.plan,daily_limit=999999)
        with self.assertRaises(RuleViolation):self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)

    def test_single_society_approval_cannot_replace_other_societys_vote(self):
        for w in (self.a,self.b):
            task,subjects=self.merge._assessment[w.tree.chain]
            result,_=w.assign(w.reg,'hierarchy_review',task,subjects,40)
            for a in result.members:
                note='Reviewed plan'
                self.merge.assess(w.tree,a,note,41,w.kr.sign(a,self.merge.assessment_message(w.tree.chain,note)))
        mandates=self.merge.mandates(41)
        self.a.institutional(mandates[0],71)
        self.b.institutional(mandates[1],71,vote=False)
        with self.assertRaises(RuleViolation):self.merge.prepare(M,106)
        self.assertEqual(self.merge.state,'REVIEW')

    def test_bond_receipt_requires_payment_keeper_and_is_not_reusable(self):
        self.prepare()
        with self.assertRaises(RuleViolation):self.merge.record_admission_bond(Actor.agent('c001'),'c001','deposit',10,106)
        self.merge.record_admission_bond(M,'c001','deposit',10,106)
        with self.assertRaises(RuleViolation):self.merge.record_admission_bond(M,'c002','deposit',10,106)

    def test_independent_replay_of_votes_and_claim_has_same_audit_roots(self):
        self.prepare();s,d=self.signatures('c001')
        clone=copy.deepcopy(self.merge)
        self.merge.claim('c001','n',170,self.merge.proof('c001'),s,d,106)
        clone.claim('c001','n',170,clone.proof('c001'),s,d,106)
        self.assertEqual(self.merge.source.reg.audit,clone.source.reg.audit)
        self.assertEqual(self.merge.destination.reg.audit,clone.destination.reg.audit)

    def test_existing_members_deduplicate_and_keep_only_receiving_authority(self):
        self.a,self.b=World('X'),World('Y')
        mapping=tuple((a,a) for a in sorted(self.a.citizens+self.a.examiners))
        self.merge=SocietyMerger(self.a.tree,self.b.tree,'dedup',mapping,40,180)
        self.prepare();before=len(self.b.reg.ids);roles=set(self.b.reg.get('c041').roles)
        s,d=self.signatures('c041')
        self.merge.claim('c041','n',170,self.merge.proof('c041'),s,d,106)
        self.assertEqual(len(self.b.reg.ids),before);self.assertEqual(self.b.reg.get('c041').roles,roles)
        self.assertEqual(self.a.reg.get('c041').status,Status.EXITED)

    def test_known_source_key_cannot_create_a_duplicate_receiving_identity(self):
        a,b=World('X'),World('Y')
        b.kr._secrets['c001']=a.kr._secrets['c001']
        mapping=tuple((x,'merge:'+digest(('X',x))) for x in sorted(a.citizens+a.examiners))
        with self.assertRaises(RuleViolation):SocietyMerger(a.tree,b.tree,'duplicate',mapping,40,180)

    def test_malformed_mapping_is_rejected_before_plan_registration(self):
        a,b=World('X'),World('Y')
        mapping=tuple((x,[]) for x in sorted(a.citizens+a.examiners))
        with self.assertRaises(RuleViolation):SocietyMerger(a.tree,b.tree,'malformed',mapping,40,180)
        self.assertNotIn('malformed',a.tree._merge_plans)
        a.kr._secrets['c002']=a.kr._secrets['c001']
        mapping=tuple((x,'merge:'+digest(('X',x))) for x in sorted(a.citizens+a.examiners))
        with self.assertRaises(RuleViolation):SocietyMerger(a.tree,b.tree,'aliases',mapping,40,180)
