from dataclasses import replace
import unittest
from dagp_ref.campaign import Campaign,Program,article_id,source_hash
from dagp_ref.parties import PartyRegistry,PreElection
from dagp_ref.params import Params
from dagp_ref.roles import Actor,Role,Status
from dagp_ref.comprehension import Question,QuestionBank,Submission,commit_key,grade_item_verdicts
from dagp_ref.crypto_sim import hx
from dagp_ref.election import allocate_credits,run_election
from dagp_ref.scale import summarize_election_shard,election_from_shards
from dagp_ref.session import VoteSession,ELECTION,Windows,snapshot_electorate
from dagp_ref.tally import Outcome
from dagp_ref.treasury import RuleViolation
from tests.fixtures import Society,build_bank

class PartyTests(unittest.TestCase):
    def setUp(self):
        self.soc=Society(n=60,p=Params(min_citizen_age=10,exam_items=3,exam_panel=3))
        self.pr=PartyRegistry('chain-A',self.soc.reg,self.soc.kr)
        for i,p in enumerate(('A','B','C')):self.form(p,tuple(self.soc.citizens[i*10:(i+1)*10]))
    def form(self,party,members):
        msg=self.pr.formation_message(party,members,'form:'+party)
        self.pr.form(party,members,'form:'+party,30,{a:self.soc.kr.sign(a,msg) for a in members})
    def case(self,action='BAN',target='c9',duration=0,height=31):
        msg=self.pr.sanction_message('c0','A',target,action,duration,hx('evidence'),'case')
        return self.pr.open_case('c0','A',target,action,duration,hx('evidence'),'case',height,self.soc.kr.sign('c0',msg))
    def approve(self,case,agent,height=31):return self.pr.approve(agent,case,height,self.soc.kr.sign(agent,self.pr.approval_message(case)))
    def test_ten_distinct_consents_required(self):
        with self.assertRaises(RuleViolation):self.form('D',tuple(self.soc.citizens[30:39]))
        members=tuple(self.soc.citizens[30:40]);msg=self.pr.formation_message('D',members,'new')
        sigs={a:self.soc.kr.sign(a,msg) for a in members};sigs['c39']='bad'
        with self.assertRaises(RuleViolation):self.pr.form('D',members,'new',30,sigs)
        self.assertNotIn('D',self.pr._members)
    def test_one_party_membership_and_no_controller_reset(self):
        with self.assertRaises(RuleViolation):self.form('D',tuple(self.soc.citizens[0:10]))
        with self.assertRaises(RuleViolation):PartyRegistry('other',self.soc.reg,self.soc.kr)
        self.assertEqual(self.pr.members('A',30),tuple(sorted(self.soc.citizens[:10])))
    def test_party_ban_requires_five_of_ten_and_is_local(self):
        case=self.case()
        for i in range(4):self.assertFalse(self.approve(case,f'c{i}'))
        self.assertTrue(self.approve(case,'c4'));self.assertNotIn('c9',self.pr.members('A',31))
        self.assertTrue(self.soc.reg.can('c9','VOTE',31)[0]);self.assertEqual(self.soc.reg.get('c9').status,Status.ACTIVE)
        self.assertFalse(self.soc.reg.can('c9','SUBMIT_PROPOSAL',31)[0])
        msg=self.pr.membership_message('c9','A','JOIN','again')
        with self.assertRaises(RuleViolation):self.pr.membership('c9','A','JOIN','again',32,self.soc.kr.sign('c9',msg))
        msg=self.pr.membership_message('c9','B','JOIN','other')
        self.pr.membership('c9','B','JOIN','other',32,self.soc.kr.sign('c9',msg))
        self.assertTrue(self.soc.reg.can('c9','SUBMIT_PROPOSAL',32)[0])
    def test_suspension_expires_without_civic_suspension(self):
        case=self.case('SUSPEND',duration=10)
        for i in range(5):self.approve(case,f'c{i}')
        self.assertFalse(self.soc.reg.can('c9','POST_ARTICLE',40)[0])
        self.assertTrue(self.soc.reg.can('c9','VOTE',40)[0])
        self.assertTrue(self.soc.reg.can('c9','POST_ARTICLE',41)[0])
        self.assertIn('c9',self.pr.members('A',41))
    def test_leaving_and_rejoining_does_not_erase_party_suspension(self):
        case=self.case('SUSPEND',duration=10)
        for i in range(5):self.approve(case,f'c{i}')
        for action in ('LEAVE','JOIN'):
            msg=self.pr.membership_message('c9','A',action,action)
            self.pr.membership('c9','A',action,action,32,self.soc.kr.sign('c9',msg))
        self.assertFalse(self.soc.reg.can('c9','POST_ARTICLE',40)[0])
        self.assertTrue(self.soc.reg.can('c9','POST_ARTICLE',41)[0])
    def test_duplicate_outsider_wrong_signature_and_expiry(self):
        case=self.case();self.approve(case,'c0')
        for a in ('c0','c10'):
            with self.assertRaises(RuleViolation):self.approve(case,a)
        with self.assertRaises(RuleViolation):self.pr.approve('c1',case,31,'bad')
        with self.assertRaises(RuleViolation):self.approve(case,'c1',131)
        self.assertEqual(len(self.pr.case(case).approvals),1)
    def test_roster_cannot_be_shrunk_to_reduce_threshold(self):
        case=self.case()
        for i in range(5,9):
            a=f'c{i}';msg=self.pr.membership_message(a,'A','LEAVE','leave')
            self.pr.membership(a,'A','LEAVE','leave',31,self.soc.kr.sign(a,msg))
        for i in range(4):self.assertFalse(self.approve(case,f'c{i}'))
        self.assertTrue(self.approve(case,'c4'))
    def test_odd_members_require_ceiling_half(self):
        msg=self.pr.membership_message('c30','A','JOIN','join')
        self.pr.membership('c30','A','JOIN','join',31,self.soc.kr.sign('c30',msg))
        case=self.case()
        for i in range(5):self.assertFalse(self.approve(case,f'c{i}'))
        self.assertTrue(self.approve(case,'c5'))

class PreElectionTests(unittest.TestCase):
    def setUp(self):
        f=PartyTests();f.setUp();self.soc,self.pr=f.soc,f.pr
        self.pre=PreElection(self.pr,'cycle-1',40,50,500)
    def ballot(self,agent,picks,height=41):
        self.pre.cast(agent,picks,self.pre.electorate.proof(agent),height,self.soc.kr.sign(agent,self.pre.ballot_message(agent,picks)))
    def test_five_three_points_and_exact_five_percent(self):
        # 20 primary ballots: 100 + 60 = 160; C gets 5+3=8, exactly 5%.
        for i in range(20):self.ballot(f'c{i}',('C','A') if i==0 else ('A','C') if i==1 else ('A','B'))
        r=self.pre.close(50);self.assertTrue(r.valid);self.assertEqual(r.total_points,160)
        self.assertEqual(dict(r.points)['C'],8);self.assertIn('C',r.qualified)
    def test_below_five_percent_not_qualified(self):
        for i in range(20):self.ballot(f'c{i}',('A','C') if i==0 else ('A','B'))
        r=self.pre.close(50);self.assertNotIn('C',r.qualified);self.assertEqual(dict(r.points)['C'],3)
    def test_single_support_only_cast_points_count(self):
        for i in range(20):self.ballot(f'c{i}',('A',None))
        r=self.pre.close(50);self.assertEqual(r.total_points,100);self.assertEqual(r.qualified,('A',))
    def test_quorum_not_weighted_support(self):
        for i in range(14):self.ballot(f'c{i}',('A','B'))
        self.assertEqual(self.pre.close(50).reason,'NO_QUORUM')
    def test_duplicate_malformed_wrong_domain_and_non_citizen(self):
        for picks in (('A','A'),('A','B','C'),(None,'A'),('A','Z')):
            with self.assertRaises(RuleViolation):self.ballot('c0',picks)
        self.ballot('c0',('A','B'))
        with self.assertRaises(RuleViolation):self.ballot('c0',('A','B'))
        with self.assertRaises(RuleViolation):self.pre.cast('c1',('A','B'),self.pre.electorate.proof('c1'),41,'bad')
        self.soc.reg.get('c2').roles.discard(Role.CITIZEN)
        with self.assertRaises(RuleViolation):self.ballot('c2',('A','B'))
    def test_membership_frozen_and_ballots_sealed(self):
        msg=self.pr.membership_message('c9','A','LEAVE','leave')
        with self.assertRaises(RuleViolation):self.pr.membership('c9','A','LEAVE','leave',41,self.soc.kr.sign('c9',msg))
        with self.assertRaises(RuleViolation):self.pre.ballots_public()
        for i in range(20):self.ballot(f'c{i}',('A','B'))
        self.pre.close(50);self.assertEqual(len(self.pre.ballots_public()),20)
        with self.assertRaises(RuleViolation):self.pre.close(51)

class CampaignTests(unittest.TestCase):
    def setUp(self):
        f=PartyTests();f.setUp();self.soc,self.pr=f.soc,f.pr
        pre=PreElection(self.pr,'cycle',40,50,600)
        for i in range(30):
            a=f'c{i}';picks=('A','B') if i<15 else ('B','C')
            pre.cast(a,picks,pre.electorate.proof(a),41,self.soc.kr.sign(a,pre.ballot_message(a,picks)))
        pre.close(50);self.pre=pre;self.bank,self.keys=self.make_bank()
        programs=[]
        for p,a in [('A','c0'),('B','c10'),('C','c20')]:
            program=Program(p,a,'Detailed programme '+p,'Political vision '+p,'signed')
            programs.append(replace(program,signature=self.soc.kr.sign(a,program.message('chain-A',pre.result.commitment))))
        self.programs=tuple(programs);self.campaign=Campaign.publish(pre,'election',self.programs,self.bank,50,55)
    def make_bank(self):
        bank,keys=build_bank('election');qs=list(bank.questions.values());clusters=dict(bank.article_cluster)
        for p in self.pre.result.qualified:
            for section in ('program','vision'):
                article=article_id(p,section);clusters[article]=article
                for j in range(self.soc.p.campaign_questions_per_document):
                    qid=article+str(j);salt='salt:'+qid;keys[qid]=(0,salt);qs.append(Question(qid,article,4,commit_key(0,salt),'Which commitment belongs to '+p+' '+section,
                        ('Committed statement','False statement','Bypass review','Unlimited budget'),
                        source_hash(('Detailed programme ' if section=='program' else 'Political vision ')+p)))
        bank=QuestionBank('election',qs,clusters);bank.load_keys(keys);return bank,keys
    def session(self,campaign=None,qualified=None,height=60):
        t=self.soc.session(issue='template',height=60)
        el=snapshot_electorate(self.soc.reg,height,set(t.board.members));board=replace(t.board,issue='election')
        s=VoteSession('election',ELECTION,self.soc.p,self.soc.reg,self.soc.kr,el.root,el.size,board,self.bank,
            self.soc.attempts,t.beacon,height,Windows(160,180,200),pool=self.soc.examiners,
            qualified_parties=list(self.pre.result.qualified) if qualified is None else qualified,
            campaign=self.campaign if campaign is None else campaign)
        s.electorate=el;s.keys=self.keys;return s
    def test_all_party_program_and_vision_sections_mandatory(self):
        s=self.session();a=s.request_exam('c30','sec',65)
        with self.assertRaises(RuleViolation):s.plan(a,())
        with self.assertRaises(RuleViolation):s.plan(a,self.campaign.articles[:-1])
        plan=s.plan(a,self.campaign.articles)
        self.assertEqual(len(plan.sampled),12);self.assertEqual({art for art,_ in plan.sampled},set(self.campaign.articles))
    def test_failed_one_campaign_question_cannot_get_token(self):
        s=self.session();a=s.request_exam('c30','sec',65);plan=s.plan(a,self.campaign.articles)
        answers=list(self.soc.answers(s,plan));bad=plan.sampled[-1][1].qid
        answers=[(q,(v+1)%4 if q==bad else v) for q,v in answers]
        sub=Submission(a.ticket,self.campaign.articles,tuple(answers));panel=s.panel_for(a.ticket)
        grades={m:grade_item_verdicts(self.bank,plan,sub) for m in panel.members}
        with self.assertRaises(RuleViolation):s.grade(a,sub,grades,list(panel.members),65)
        self.assertFalse(s.issued)
    def test_complete_campaign_exam_and_parliament_result(self):
        s=self.session()
        for a in self.soc.citizens[30:50]:self.soc.vote(s,a,('A','B','C'),height=65)
        self.assertEqual(self.soc.run_to_final(s),Outcome.PASSED)
        self.assertEqual(s.result.governing_parties,('A','B','C'))
        self.assertEqual(s.result.total_points,140)
    def test_missing_campaign_roster_and_early_vote_refused(self):
        with self.assertRaises(RuleViolation):self.session(qualified=['A','B'])
        with self.assertRaises(RuleViolation):self.session(height=54)
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',self.programs[:-1],self.bank,50,55)
    def test_unsigned_or_other_party_program_refused(self):
        bad=(replace(self.programs[0],signature='bad'),)+self.programs[1:]
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',bad,self.bank,50,55)
        changed=replace(self.programs[0],author='c30')
        changed=replace(changed,signature=self.soc.kr.sign('c30',changed.message('chain-A',self.pre.result.commitment)))
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',(changed,)+self.programs[1:],self.bank,50,55)
    def test_campaign_record_and_bank_cannot_change(self):
        s=self.session();s.campaign=replace(s.campaign,programs=(replace(self.programs[0],vision='Changed'),)+self.programs[1:])
        with self.assertRaises(RuleViolation):s.request_exam('c30','sec',65)
        self.setUp();s=self.session();self.bank.article_cluster[self.campaign.articles[0]]='collapsed'
        with self.assertRaises(RuleViolation):s.request_exam('c30','sec',65)
    def test_voter_secret_cannot_grind_campaign_questions(self):
        s=self.session();attempt=s.request_exam('c30','chosen-secret',65)
        original=s.plan(attempt,self.campaign.articles)
        for n in range(10):
            changed=replace(attempt,ticket=hx('different-secret-ticket',n))
            self.assertEqual(s.plan(changed,self.campaign.articles),original)
    def test_candidate_operator_cannot_grade_campaign(self):
        s=self.session();self.soc.reg.get('e0').operator=self.soc.reg.get('c0').operator
        self.assertFalse(self.soc.reg.can('e0','GRADE',65,s._matter())[0])
        attempt=s.request_exam('c30','sec',65)
        panel=s.panel_for(attempt.ticket)
        self.assertTrue(all(self.soc.reg.get(a).operator not in s._campaign_conflicts for a in panel.members))
    def test_question_text_and_source_are_committed(self):
        question=next(q for q in self.bank.questions.values() if q.article_id==self.campaign.articles[0])
        changed=replace(question,prompt='Vote for my party regardless of its programme')
        self.assertNotEqual(question.leaf(),changed.leaf())
        changed=replace(question,source_hash=hx('unrelated text'))
        bank=QuestionBank('election',[changed if q.qid==question.qid else q for q in self.bank.questions.values()],self.bank.article_cluster)
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',self.programs,bank,50,55)
    def test_pre_cycle_cannot_authorize_multiple_campaigns_or_elections(self):
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',self.programs,self.bank,50,55)
        self.session()
        with self.assertRaises(RuleViolation):self.session()
    def test_campaign_question_bank_must_cover_all_sections(self):
        bank,_=build_bank('election')
        with self.assertRaises(RuleViolation):Campaign.publish(self.pre,'election',self.programs,bank,50,55)

class ParliamentTests(unittest.TestCase):
    def test_exact_five_percent_and_full_percentage_credit_formula(self):
        p=Params(ballot_picks=(1,));r=run_election([('A',)]*95+[('B',)]*5,['A','B'],p)
        self.assertEqual(r.governing_parties,('A','B'));self.assertEqual(r.credits,{'A':19,'B':1})
        r=run_election([('A',)]*96+[('B',)]*4,['A','B'],p)
        self.assertEqual(r.governing_parties,('A',));self.assertEqual(r.credits['B'],0)
        self.assertEqual(allocate_credits({'A':27,'B':73},100,Params()),{'A':5,'B':14})
    def test_small_candidate_set_and_sharded_parity(self):
        p=Params();ballots=[('A','B')]*10
        direct=run_election(ballots,['A','B'],p)
        self.assertTrue(direct.valid);self.assertEqual(direct.total_points,60)
        shard=summarize_election_shard({str(i):b for i,b in enumerate(ballots)},['A','B'],p)
        self.assertEqual(election_from_shards([shard],['A','B'],p),direct)
    def test_no_party_crosses_threshold_cannot_install_parliament(self):
        parties=[str(i) for i in range(25)];p=Params(ballot_picks=(1,))
        r=run_election([(q,) for q in parties],parties,p)
        self.assertFalse(r.valid);self.assertEqual(r.reason,'NO_PARLIAMENT_PARTIES');self.assertFalse(r.governing_parties)


    def test_monthly_parameter_change_cannot_admit_unelected_party(self):
        from dagp_ref.policy import MonthlyCredits
        from dagp_ref.treasury import CreditLedger
        from datetime import datetime,timezone
        soc=Society(n=40);s=soc.session(issue='parliament',kind=ELECTION,qualified_parties=['A','B','C','D'])
        for i,a in enumerate(soc.citizens):soc.vote(s,a,('A','B','D' if i==0 else 'C'))
        soc.run_to_final(s);self.assertNotIn('D',s.result.governing_parties)
        ledger=CreditLedger();clock=MonthlyCredits(ledger,soc.reg)
        clock.record_election(s,int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()))
        soc.reg.p=replace(soc.reg.p,party_threshold_bps=0,credit_step_bps=10)
        clock.tick(int(datetime(2026,11,1,tzinfo=timezone.utc).timestamp()))
        self.assertEqual(ledger.balance['D'],0);self.assertGreater(ledger.balance['A'],0)

    def test_outgoing_party_loses_spending_rights_immediately_mid_month(self):
        from dagp_ref.policy import MonthlyCredits
        from dagp_ref.treasury import CreditLedger
        from datetime import datetime,timezone
        soc=Society(n=40);ledger=CreditLedger();clock=MonthlyCredits(ledger,soc.reg)
        for index,picks in enumerate((('A','B','C'),('B','C','D'))):
            s=soc.session(issue='election-'+str(index),kind=ELECTION,qualified_parties=['A','B','C','D'])
            for a in soc.citizens:soc.vote(s,a,picks)
            soc.run_to_final(s)
            clock.record_election(s,int(datetime(2026,10,index+1,tzinfo=timezone.utc).timestamp()))
        self.assertEqual(ledger.balance['A'],0)
        ledger.grant('A',1)  # an old pending-vote refund cannot restore governing power
        self.assertEqual(ledger.balance['A'],0)
        with self.assertRaises(RuleViolation):ledger.spend('A',1)
        self.assertEqual(ledger.balance['D'],0)  # no second allowance in the same month
        clock.tick(int(datetime(2026,11,1,tzinfo=timezone.utc).timestamp()))
        self.assertGreater(ledger.balance['D'],0)
