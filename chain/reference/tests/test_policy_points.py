from dataclasses import replace
from datetime import datetime,timezone
import unittest
from tests.legacy_params import Params
from dagp_ref.roles import Actor
from dagp_ref.election import allocate_credits
from dagp_ref.policy import MonthlyCredits,ParameterGovernance,validate_changes
from dagp_ref.review import ProposalReview,BillPoint,Milestone
from dagp_ref.session import Phase,ELECTION
from dagp_ref.tally import Kind,Outcome,Ballot,tally,tally_bill
from dagp_ref.treasury import Treasury,CreditLedger,RuleViolation
from tests import test_review
from tests.fixtures import Society

def timestamp(year,month,day=1):return int(datetime(year,month,day,tzinfo=timezone.utc).timestamp())
def fixture():
    f=test_review.Review();f.setUp();f.r.p=replace(f.r.p,quorum_bps=2000,bill_mode='INDEPENDENT');f.soc.p=f.r.p
    return f

def reviewed(f,draft,kind=Kind.ORDINARY,treasury=None):
    r=ProposalReview('A','prop1','c0','Owners',{'Owners':{'c0'},'Others':{'c1'}},
        ('c27','c28','c29'),draft,f.r,f.kr,50,60)
    f.rev=r;f.approve();f.approve('c28');f.lock()
    template=f.soc.session(height=70,kind=kind)
    session=r.open_vote(treasury,kind=kind,board=template.board,bank=template.bank,
        attempts=f.soc.attempts,beacon=template.beacon,open_height=70,windows=template.w,pool=f.soc.examiners)
    session.keys=template.keys
    return session

class CurrentThresholds(unittest.TestCase):
    def test_27_percent_gets_five_credits(self):self.assertEqual(allocate_credits({'A':27,'B':73},100,Params())['A'],5)
    def test_20_percent_is_minimum_headcount_quorum(self):
        p=Params();ballots=[Ballot(str(n),'Y',3) for n in range(20)]
        self.assertEqual(tally(ballots,100,Kind.ORDINARY,p).outcome,Outcome.PASSED)
        self.assertEqual(tally(ballots[:-1],100,Kind.ORDINARY,p).outcome,Outcome.NO_QUORUM)
        with self.assertRaises(ValueError):Params(quorum_bps=1999)
    def test_exact_66_percent_for_parameter_updates(self):
        ballots=[Ballot(str(n),'Y' if n<66 else 'N',3) for n in range(100)]
        self.assertEqual(tally(ballots,500,Kind.PARAMETER,Params()).outcome,Outcome.PASSED)
        self.assertEqual(tally(ballots,501,Kind.PARAMETER,Params()).outcome,Outcome.NO_QUORUM)
        ballots[65]=Ballot('65','N',3)
        self.assertEqual(tally(ballots,500,Kind.PARAMETER,Params()).outcome,Outcome.FAILED)
    def test_constitution_exact_66_approval_and_50_turnout(self):
        ballots=[Ballot(str(n),'Y' if n<33 else 'N',3) for n in range(50)]
        self.assertEqual(tally(ballots,100,Kind.CONSTITUTIONAL,Params()).outcome,Outcome.PASSED)
        ballots[32]=Ballot('32','N',3)
        self.assertEqual(tally(ballots,100,Kind.CONSTITUTIONAL,Params()).outcome,Outcome.FAILED)
        all_yes=[Ballot(str(n),'Y',3) for n in range(49)]
        self.assertEqual(tally(all_yes,100,Kind.CONSTITUTIONAL,Params()).outcome,Outcome.NO_QUORUM)
        self.assertEqual(tally(all_yes,100,Kind.CORE,Params()).outcome,Outcome.NO_QUORUM)
        with self.assertRaises(ValueError):Params(constitutional_quorum_bps=4999)
        with self.assertRaises(RuleViolation):validate_changes(Params(),(('constitutional_quorum_bps',2000),))
    def test_constitution_higher_general_quorum_and_per_point_floor(self):
        ballots=[Ballot(str(n),'Y',3) for n in range(50)]
        self.assertEqual(tally(ballots,100,Kind.CONSTITUTIONAL,Params(quorum_bps=6000)).outcome,Outcome.NO_QUORUM)
        self.assertEqual(tally_bill([ballots,ballots[:-1]],100,Kind.CONSTITUTIONAL,Params()).point_outcomes,
                         (Outcome.PASSED,Outcome.NO_QUORUM))
    def test_no_automatic_credits_below_five_percent(self):
        self.assertEqual(set(allocate_credits({str(n):4 for n in range(25)},100,Params()).values()),{0})
    def test_unapproved_constants_and_security_floors_cannot_change(self):
        for changes in ((('quorum_bps',1000),),(('parameter_approval_bps',1),),(('credit_step_bps',0),),(([],1),)):
            with self.assertRaises(RuleViolation):validate_changes(Params(),changes)

class PointVoting(unittest.TestCase):
    def setUp(self):self.f=fixture()
    def draft(self,dependencies=False):
        points=tuple(BillPoint(f'p{i}',f'Clause {i}',20,(Milestone(f'm{i}',20,f'Accepted clause {i}'),),
                              ('p4',) if dependencies and i==0 else ()) for i in range(5))
        return replace(self.f.d,points=points,milestones=tuple(m for p in points for m in p.milestones))
    def test_three_of_five_approve_and_only_sixty_units_funded(self):
        t=Treasury(200);s=reviewed(self.f,self.draft(),treasury=t)
        for a in self.f.soc.citizens[1:26]:self.f.soc.vote(s,a,('Y','Y','Y','N','N'),height=75)
        self.assertEqual(self.f.soc.run_to_final(s),Outcome.PARTIAL)
        self.assertEqual(s.effective_points,('p0','p1','p2'));self.assertEqual(t.granted['prop1'],60)
        self.assertEqual(t.free,140);self.assertEqual([m.label for m in t.milestone_conditions['prop1']],['m0','m1','m2'])
        t.assert_invariants()
    def test_one_approved_point_can_survive_four_rejected(self):
        t=Treasury(200);s=reviewed(self.f,self.draft(),treasury=t)
        for a in self.f.soc.citizens[1:26]:self.f.soc.vote(s,a,('Y','N','N','N','N'),height=75)
        self.assertEqual(self.f.soc.run_to_final(s),Outcome.PARTIAL);self.assertEqual(t.granted['prop1'],20)
    def test_failed_dependency_blocks_approved_dependent_and_its_money(self):
        t=Treasury(200);s=reviewed(self.f,self.draft(True),treasury=t)
        for a in self.f.soc.citizens[1:26]:self.f.soc.vote(s,a,('Y','Y','Y','N','N'),height=75)
        self.f.soc.run_to_final(s)
        self.assertEqual(s.effective_points,('p1','p2'));self.assertEqual(t.granted['prop1'],40)
    def test_per_point_quorum_and_skips(self):
        t=Treasury(200);s=reviewed(self.f,self.draft(),treasury=t)
        for n,a in enumerate(self.f.soc.citizens[1:26]):self.f.soc.vote(s,a,('Y','Y','Y','N','Y' if n==0 else None),height=75)
        self.f.soc.run_to_final(s)
        self.assertEqual(s.result.point_outcomes[4],Outcome.NO_QUORUM);self.assertEqual(t.granted['prop1'],60)
    def test_malformed_vector_and_duplicate_identity_rejected(self):
        s=reviewed(self.f,self.draft(),treasury=Treasury(200));a='c1';att,tok,_=self.f.soc.get_token(s,a,height=75)
        with self.assertRaises(RuleViolation):s.cast_ballot(a,('Y',),tok,'sec',att.n,s.electorate.proof(a),75)
        s.cast_ballot(a,('Y',)*5,tok,'sec',att.n,s.electorate.proof(a),75)
        with self.assertRaises(RuleViolation):s.cast_ballot(a,('N',)*5,tok,'sec',att.n,s.electorate.proof(a),75)
    def test_dependency_cycles_rejected_before_credit_or_money(self):
        d=self.draft();ps=list(d.points);ps[0]=replace(ps[0],requires=('p1',));ps[1]=replace(ps[1],requires=('p0',))
        with self.assertRaises(RuleViolation):reviewed(self.f,replace(d,points=tuple(ps)),treasury=Treasury(200))

    def test_rejected_funding_leaves_approved_unfunded_clause_effective(self):
        d=self.draft();points=list(d.points)
        points[0]=replace(points[0],budget=0,milestones=())
        points[4]=replace(points[4],budget=40,milestones=(replace(points[4].milestones[0],amount=40),))
        d=replace(d,points=tuple(points),milestones=tuple(m for p in points for m in p.milestones))
        t=Treasury(200);s=reviewed(self.f,d,treasury=t)
        for a in self.f.soc.citizens[1:26]:self.f.soc.vote(s,a,('Y','N','N','N','N'),height=75)
        self.assertEqual(self.f.soc.run_to_final(s),Outcome.PARTIAL)
        self.assertEqual(s.effective_points,('p0',));self.assertEqual(t.free,200);self.assertFalse(t.granted)
    def test_upheld_challenge_blocks_all_partial_effects_and_funding(self):
        t=Treasury(200);s=reviewed(self.f,self.draft(),treasury=t)
        for a in self.f.soc.citizens[1:26]:self.f.soc.vote(s,a,('Y','Y','Y','N','N'),height=75)
        s.close(s.w.vote_end)
        for m in s.board.members:s.certify(m,self.f.kr.sign(m,s.certificate_message()),s.w.vote_end)
        s.advance(s.w.vote_end);s.challenge('c26','Invalid evidence',s.w.vote_end)
        with self.assertRaises(RuleViolation):s.finalize(s.w.challenge_end)
        self.f.r.register_ruling(Actor('MODULE','bootstrap'),'challenge','CHALLENGE','prop1:0')
        s.rule(Actor('COURT','challenge'),0,True,s.w.vote_end)
        self.assertEqual(s.finalize(s.w.challenge_end),'VOIDED')
        self.assertFalse(s.effective_points);self.assertEqual(t.free,200);self.assertFalse(t.granted)
    def test_old_month_no_quorum_refund_does_not_inflate_new_allowance(self):
        credits=CreditLedger();credits.month=(2026,10);credits.grant('Owners',5)
        self.f.r.p=self.f.soc.p
        r=ProposalReview('A','prop1','c0','Owners',{'Owners':{'c0'},'Others':{'c1'}},
            ('c27','c28','c29'),self.f.d,self.f.r,self.f.kr,50,60,credits=credits)
        self.f.rev=r;self.f.approve();self.f.approve('c28');self.f.lock()
        template=self.f.soc.session(height=70)
        s=r.open_vote(Treasury(200),kind=Kind.ORDINARY,board=template.board,bank=template.bank,
            attempts=self.f.soc.attempts,beacon=template.beacon,open_height=70,windows=template.w,pool=self.f.soc.examiners)
        credits.month=(2026,11);credits.balance={'Owners':5}
        self.assertEqual(self.f.soc.run_to_final(s),Outcome.NO_QUORUM)
        self.assertEqual(credits.balance['Owners'],5)

class ParameterVoting(unittest.TestCase):
    def test_finalized_reviewed_referendum_changes_only_next_month(self):
        f=fixture();governance=ParameterGovernance(f.r)
        draft=replace(f.d,budget=0,milestones=(),parameter_changes=(('credit_step_bps',400),))
        s=reviewed(f,draft,Kind.PARAMETER)
        for a in f.soc.citizens[1:26]:f.soc.vote(s,a,'Y',height=75)
        f.soc.run_to_final(s)
        self.assertEqual(governance.schedule(s,timestamp(2026,10)),(2026,11))
        self.assertEqual(governance.tick(timestamp(2026,10,31)).credit_step_bps,500)
        self.assertEqual(governance.tick(timestamp(2026,11)).credit_step_bps,400)
        self.assertEqual(s.p.credit_step_bps,500)
        with self.assertRaises(RuleViolation):governance.schedule(s,timestamp(2026,11))
    def test_ordinary_vote_cannot_authorize_parameter_updates(self):
        f=fixture();draft=replace(f.d,budget=0,milestones=(),parameter_changes=(('credit_step_bps',400),))
        with self.assertRaises(RuleViolation):reviewed(f,draft,Kind.ORDINARY)

class MonthlyRenewal(unittest.TestCase):
    def setUp(self):
        self.soc=Society();self.ledger=CreditLedger();self.clock=MonthlyCredits(self.ledger,self.soc.reg)
        self.s=self.soc.session(issue='election',kind=ELECTION,qualified_parties=['A','B','C','D'])
        for a in self.soc.citizens[:25]:self.soc.vote(self.s,a,('A','B','C'))
        self.soc.run_to_final(self.s);self.clock.record_election(self.s,timestamp(2026,10))
    def test_monthly_reset_no_carryover_and_no_duplicate_renewal(self):
        self.ledger.spend('B',2);self.assertEqual(self.ledger.balance['B'],3)
        self.assertFalse(self.clock.tick(timestamp(2026,10,31)))
        self.assertTrue(self.clock.tick(timestamp(2026,11)));self.assertEqual(self.ledger.balance['B'],5)
        self.assertFalse(self.clock.tick(timestamp(2026,11)));self.assertEqual(self.ledger.balance['B'],5)
    def test_debt_survives_and_skipped_months_do_not_accumulate(self):
        self.ledger.penalize('B',7);self.assertEqual(self.ledger.debt['B'],2)
        self.clock.tick(timestamp(2027,1));self.assertEqual(self.ledger.balance['B'],3);self.assertEqual(self.ledger.debt['B'],0)
    def test_second_election_same_month_cannot_remint(self):
        self.ledger.spend('B',2)
        second=self.soc.session(issue='election-2',kind=ELECTION,qualified_parties=['A','B','C','D'])
        for a in self.soc.citizens[:25]:self.soc.vote(second,a,('B','A','C'))
        self.soc.run_to_final(second)
        self.assertFalse(self.clock.record_election(second,timestamp(2026,10,2)))
        self.assertEqual(self.ledger.balance['B'],3)
        self.clock.tick(timestamp(2026,11));self.assertEqual(self.ledger.balance['B'],10)
    def test_replayed_election_and_backdated_clock_rejected(self):
        with self.assertRaises(RuleViolation):self.clock.record_election(self.s,timestamp(2026,10))
        with self.assertRaises(RuleViolation):self.clock.tick(timestamp(2026,9))

