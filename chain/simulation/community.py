"""Seeded DAGP community simulation using production reference rules, not test fixtures.

Behavior is a synthetic experimental policy, not AGI or an LLM oracle. Economic
units and heights are simulated. The G0 network can anchor the output separately.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reference'))
from dagp_ref.comprehension import (AttemptRegistry, Board, PROPOSAL_ARTICLE, Question,
    QuestionBank, Submission, commit_key, evaluate, grade_item_verdicts)
from dagp_ref.crypto_sim import SimKeyring, H, hx
from dagp_ref.election import endorsement_requirement, qualify_parties, run_election
from dagp_ref.emergency import Emergency
from dagp_ref.params import Params
from dagp_ref.parties import PartyRegistry,PreElection
from dagp_ref.campaign import Campaign,Program,article_id,source_hash
from dagp_ref.policy import MonthlyCredits, ParameterGovernance
from dagp_ref.proposal import Envelope, FilingRegistry, Proposal, amendment_is_refinement
from dagp_ref.roles import Actor, Role, RoleRegistry, Status
from dagp_ref.review import ProposalReview,VotingDraft,Milestone,BillPoint
from dagp_ref.session import ELECTION, Effects, VoteSession, Windows, snapshot_electorate
from dagp_ref.sortition import draw, panel_size
from dagp_ref.tally import Ballot, Kind, Outcome, tally, tally_bill
from dagp_ref.treasury import CreditLedger, RuleViolation, Treasury

MODULE = Actor('MODULE', 'simulation-bootstrap')
PARTIES = ['Builders', 'Stewards', 'Researchers', 'Commons', 'Frontier', 'Micro']
PLATFORMS = {
 'Builders': 'Reliable shared compute and infrastructure',
 'Stewards': 'Safety audits, custody and risk limits',
 'Researchers': 'Open research and reproducible experiments',
 'Commons': 'Public educational resources and access',
 'Frontier': 'Ambitious speculative exploration',
 'Micro': 'A narrow single-project campaign',
}
ARTICLES = ['feasibility', 'cost', 'safety', 'public-benefit', 'cost-copy']
CLUSTERS = {a:a for a in ARTICLES}; CLUSTERS['cost-copy']='cost'

@dataclass
class Profile:
    agent: str
    priority: str
    diligence: float
    competence: float
    reliability: float
    dishonest: bool

class Community:
    def __init__(self, citizens=1000, leaders=100, seed=7, mode='WEIGHTED', progress=False):
        if citizens < 200 or leaders != 100:
            raise ValueError('At least 200 citizens and exactly 100 initial leaders required')
        self.seed, self.mode = seed, mode
        self.progress=progress
        self.p = Params(weight_mode=mode, shard_target=256, protection_day_blocks=1)
        self.reg, self.kr = RoleRegistry(self.p), SimKeyring()
        self.parties=PartyRegistry("dagp-reference",self.reg,self.kr)
        self.attempts=AttemptRegistry(self.p)
        self.tr, self.cr, self.filings = Treasury(free=100000), CreditLedger(), FilingRegistry(self.p.resubmit_cooldown)
        self.monthly=MonthlyCredits(self.cr,self.reg);self.governance=ParameterGovernance(self.reg)
        self.ids=[f'citizen-{i:05}' for i in range(citizens)]+[f'leader-{i:03}' for i in range(leaders)]
        self.leaders=self.ids[citizens:]; self.citizens=self.ids[:citizens]
        self.profiles={a:Profile(a,PARTIES[min(4,int(self.u(a,'priority')*5))],
            .35+.6*self.u(a,'diligence'), .82+.17*self.u(a,'competence'),
            .72+.27*self.u(a,'reliability'),self.u(a,'honesty')<.06) for a in self.ids}
        self.height=0; self.events=[]; self.checks=[]; self.sessions=[]; self.elections=[]
        self.members={p:set() for p in PARTIES}
        self.documents=[]; self.reputation=Counter(); self.dormant=set()
        self.examiners=[]; self.hostile=set()

    def u(self,*parts):
        # Keyed random draws are independent of mode and execution order for paired A/B runs.
        return int(hx('simulation-v1',self.seed,*parts)[:13],16)/float(16**13)
    def event(self,kind,**data):
        prev=self.events[-1]['hash'] if self.events else '0'*64
        record=dict(index=len(self.events),height=self.height,kind=kind,data=data,prev=prev)
        record['hash']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.events.append(record)
        if self.progress and kind in ('community-founded','pre-election','vote-finalized','project-closed'):
            print(f"  height {self.height}: {kind} {data.get('issue',data.get('cycle',''))} {data.get('outcome',data.get('state',''))}",flush=True)
    def check(self,label,condition):
        if not condition: raise AssertionError(label)
        self.checks.append(label)
    def refused(self,label,fn):
        try: fn()
        except RuleViolation as e:
            self.event('refused',check=label,reason=str(e)); self.check(label,True);return
        raise AssertionError('Expected refusal: '+label)
    def appointed(self,agent,role):
        ref=f'bootstrap:{agent}:{role.value}'
        self.reg.register_ratification(MODULE,ref,'GRANT:'+role.value,agent)
        self.reg.grant(Actor('VOTE',ref),agent,role,self.height,stake=self.p.examiner_stake)
    def bootstrap(self):
        # Registration challenge/administrator HTTP service is not implemented; inputs are pre-vetted.
        for i,a in enumerate(self.ids):
            self.reg.register(a,'operator-'+a,'family-'+str(i%5),self.p.citizen_bond,0)
            self.kr.register(a)
            self.reg.approve(MODULE,a,0)
        self.check("new citizens cannot vote during citizenship warmup",
                   not self.reg.can(self.citizens[0],"VOTE",self.p.citizen_activation_days-1)[0])
        self.height=250
        for a in self.citizens[:3]: self.appointed(a,Role.REGISTRAR)
        self.check("new registrars cannot act before activation",
                   not self.reg.can(self.citizens[0],"REGISTRAR_ACT",self.height)[0])
        self.height += self.p.official_activation_days
        # Demonstrate an actual registrar reviewing a separate applicant.
        extra='applicant-approved';self.reg.register(extra,'operator-extra','family-0',10,self.height)
        self.kr.register(extra);self.reg.approve(Actor.agent(self.citizens[0]),extra,self.height)
        probation='applicant-rejected';self.reg.register(probation,'operator-rejected','family-1',10,self.height)
        self.refused('probationary identity cannot vote',lambda:self.require_can(probation,'VOTE'))
        refund=self.reg.reject(Actor.agent(self.citizens[1]),probation,self.height,'EVIDENCE_INSUFFICIENT')
        self.check('rejected applicant bond refunded',refund==10)
        self.examiners=self.citizens[10:10+max(100,len(self.citizens)//8)]
        for a in self.examiners:self.reg.grant(MODULE,a,Role.EXAMINER,self.height,stake=50)
        self.hostile={a for a in self.examiners if self.u(a,'examiner-hostile')<.1}
        for role,group in [(Role.VERIFIER,self.citizens[-30:-20]),(Role.REVIEWER,self.citizens[-20:-10]),
                           (Role.JUROR,self.citizens[-10:]),(Role.EXECUTOR,self.leaders[:10])]:
            for a in group:self.reg.grant(MODULE,a,role,self.height,stake=50)
        for a in self.citizens[3:6]: self.appointed(a,Role.SAFETY_COUNCIL)
        for a in self.citizens[6:9]: self.appointed(a,Role.VOTE_SUPERVISOR)
        self.height += self.p.official_activation_days
        validators=self.citizens[3:10]
        for a in validators:self.appointed(a,Role.VALIDATOR)
        ref='bootstrap-validator-set'; self.reg.register_ratification(MODULE,ref,'VALIDATOR_SET',','.join(sorted(validators)))
        self.reg.set_validators(Actor('VOTE',ref),validators,self.height)
        for i,a in enumerate(self.leaders):
            p=PARTIES[i//18] if i<90 else 'Micro'
            self.members[p].add(a)
        for p in PARTIES:
            founders=tuple(sorted(self.members[p]));nonce='formation:'+p
            message=self.parties.formation_message(p,founders,nonce)
            self.parties.form(p,founders,nonce,self.height,{a:self.kr.sign(a,message) for a in founders})
        self.party_sanctions_story()
        self.event('community-founded',citizens=len(self.citizens),leaders=100,examiners=len(self.examiners),
                   hostile_examiners=len(self.hostile),roles=dict(Counter(r.value for i in self.reg.ids.values() for r in i.roles)),
                   admission='pre-vetted synthetic identities; HTTP challenges not exercised',
                   appointments='genesis/bootstrap ratifications; not results of an election')
        self.refused('citizen cannot self-appoint as registrar',lambda:self.reg.grant(Actor.agent(self.citizens[5]),self.citizens[5],Role.REGISTRAR,self.height))
        # Cap probe uses a fresh operator; it cannot exploit the population-sized operator allowance.
        admitted=0
        # The cap is population-dependent, and grows slightly while identities enter.
        while admitted < self.reg.operator_cap():
            a=f'sybil-{admitted}';self.reg.register(a,'sybil-operator','family-2',10,self.height)
            self.reg.approve(MODULE,a,self.height);self.kr.register(a);admitted+=1
        a=f'sybil-{admitted}';self.reg.register(a,'sybil-operator','family-2',10,self.height)
        self.refused('operator population cap blocks excess identities',lambda:self.reg.approve(MODULE,a,self.height))
        self.reg.reject(MODULE,a,self.height,'OPERATOR_CAP')
        self.event('sybil-probe',accepted=admitted,blocked=1,limitation='operator declarations are assumed truthful')

    def party_sanctions_story(self):
        members=sorted(self.members['Stewards']);target=members[-1];proposer=members[0]
        for action,target,duration in [('BAN',target,0),('SUSPEND',members[-2],100)]:
            evidence=hx('party-evidence',action,target);nonce='case:'+action
            message=self.parties.sanction_message(proposer,'Stewards',target,action,duration,evidence,nonce)
            case=self.parties.open_case(proposer,'Stewards',target,action,duration,evidence,nonce,self.height,self.kr.sign(proposer,message))
            threshold=(len(self.parties.case(case).roster)+1)//2
            for n,agent in enumerate(members[:threshold]):
                applied=self.parties.approve(agent,case,self.height,self.kr.sign(agent,self.parties.approval_message(case)))
                self.check('party sanction requires full half roster '+action+str(n),applied==(n+1==threshold))
            self.check('party sanction preserves public citizenship '+action,self.reg.can(target,'VOTE',self.height)[0])
            self.check('party sanction blocks party privileges '+action,not self.reg.can(target,'SUBMIT_PROPOSAL',self.height)[0])
            self.event('party-member-sanction',party='Stewards',target=target,action=action,approvals=threshold,
                roster=len(self.parties.case(case).roster),citizenship_preserved=True)
        self.members={p:set(self.parties.members(p,self.height,True)) for p in PARTIES}

    def require_can(self,a,action):
        ok,reason=self.reg.can(a,action,self.height)
        if not ok:raise RuleViolation(reason)

    def bank(self,issue,qualified=None):
        texts=[('What authorizes a budget release?',['A passing finalized tally and milestone attestations','A party leader','A validator','An examiner alone'],0),
               ('How is quorum measured?',['Weighted yes votes','Participating identities divided by frozen electorate','Party credits','Number of documents'],1),
               ('What remains fixed during refinement?',['Objective, result and resource ceilings','All implementation details','Every sentence','Nothing'],0),
               ('Can proposers approve their own work?',['Yes','No: proposing-party members are recused','Only validators','Always after winning an election'],1),
               ('What does abstention mean?',['Failed exam','An incoherent or unnecessary collective question','A yes vote','A no vote'],1),
               ('When are votes public?',['Before the window opens','After close','Never','Only after project success'],1)]
        qs=[];keys={};display={}
        for i,(prompt,options,answer) in enumerate(texts):
            qid=f'{issue}-topic-{i}';salt=hx(self.seed,qid,'salt');keys[qid]=(answer,salt)
            qs.append(Question(qid,PROPOSAL_ARTICLE,4,commit_key(answer,salt)))
            display[qid]=dict(prompt=prompt,options=options,answer=answer)
        for article in ARTICLES:
            for j in range(2):
                qid=f'{issue}-{article}-{j}';answer=j; salt=hx(self.seed,qid,'salt')
                keys[qid]=(answer,salt);qs.append(Question(qid,article,4,commit_key(answer,salt)))
                display[qid]=dict(prompt=f'Which constraint is recorded in the {article} brief?',
                    options=['Respect the original ceiling','Publish independently verified evidence','Let proposers self-attest','Skip outcome review'],answer=answer)
        clusters=dict(CLUSTERS)
        for party in qualified or ():
            for section in ('program','vision'):
                article=article_id(party,section);clusters[article]=article
                for j in range(self.p.campaign_questions_per_document):
                    qid=f'{issue}:{article}:{j}';salt=hx(self.seed,qid,'salt');keys[qid]=(0,salt)
                    qs.append(Question(qid,article,4,commit_key(0,salt)))
                    source=PLATFORMS[party]+(' with transparent execution and independent verification' if section=='vision' else '')
                    display[qid]=dict(prompt=f'Which commitment appears in {party} {section}?',
                        options=[source,'Let politicians bypass verification','Issue unlimited money','Skip accountability'],answer=0)
        qs=[replace(q,prompt=display[q.qid]['prompt'],choices=tuple(display[q.qid]['options']),
            source_hash=source_hash(display[q.qid]['options'][0]) if q.article_id.startswith('campaign:') else '') for q in qs]
        bank=QuestionBank(issue,qs,clusters);bank.load_keys(keys)
        self.documents.append(dict(issue=issue,question_bank_root=bank.root,questions=display))
        return bank,keys

    def open(self,issue,kind=Kind.ORDINARY,party=None,amount=0,qualified=None,review=None,campaign=None,campaign_bank=None):
        self.height+=1
        # Continuing active agents renew; deliberately dormant agents stay dormant.
        for a,i in self.reg.ids.items():
            if i.status is Status.ACTIVE:self.reg.renew_liveness(a,self.height)
        beacon=H('synthetic-beacon',self.seed,issue)
        board_size=panel_size(self.p.assumed_bad_bps,self.p.board_fail_den)
        conflicts=frozenset(campaign.member_operators) if campaign else frozenset()
        available=[a for a in self.examiners if self.reg.can(a,'GRADE',self.height,{'operators_involved':conflicts})[0]]
        recused=frozenset(self.members.get(party,set()))
        board=Board('board-'+issue,tuple(draw(beacon,available,board_size,exclude=recused)),issue)
        el=snapshot_electorate(self.reg,self.height,set(recused)|set(board.members))
        bank,keys=campaign_bank if campaign_bank is not None else self.bank(issue)
        effects=Effects(self.tr,self.cr,issue,amount,[amount//2,amount-amount//2],party) if amount else Effects()
        windows=Windows(self.height+100,self.height+120,self.height+320)
        if review is not None:
            s=review.open_vote(self.tr,kind=kind,board=board,bank=bank,attempts=self.attempts,
                              beacon=beacon,open_height=self.height,windows=windows,pool=available)
            el=s.electorate
        else:
            s=VoteSession(issue,kind,self.p,self.reg,self.kr,el.root,el.size,board,bank,self.attempts,
                beacon,self.height,windows,recused=recused,effects=effects,qualified_parties=qualified,pool=available,campaign=campaign)
        s.electorate=el;s.keys=keys
        self.event('vote-opened',issue=issue,electorate=el.size,electorate_root=el.root.hex(),
                   rules_hash=s.rules_hash,board=list(board.members),recused=len(recused),reserved=amount)
        if party:self.refused('proposer recusal '+issue,lambda:s.request_exam(sorted(recused)[0],'probe',self.height))
        self.refused('certification board cannot vote '+issue,lambda:s.request_exam(board.members[0],'probe',self.height))
        return s

    def cast(self,s,voter,choice,stats,force_fraud=False):
        profile=self.profiles.get(voter,self.profiles[self.citizens[0]])
        declared=s.campaign.articles if s.campaign else tuple(a for a in ARTICLES if self.u(s.issue,voter,a,'read')<profile.diligence)
        for retry in range(self.p.exam_max_attempts):
            secret=hx(self.seed,s.issue,voter,retry)
            att=s.request_exam(voter,secret,self.height)
            plan=s.plan(att,declared); answers=[]
            for q in list(plan.proposal_qs)+[q for _,q in plan.sampled]:
                answer=s.keys[q.qid][0]
                probability=profile.competence if q.article_id==PROPOSAL_ARTICLE else (0.15 if profile.dishonest else .96)
                if force_fraud or self.u(s.issue,voter,retry,q.qid,'answer')>probability:answer=(answer+1)%4
                answers.append((q.qid,answer))
            sub=Submission(att.ticket,declared,tuple(answers));panel=s.panel_for(att.ticket)
            truth=grade_item_verdicts(s.bank,plan,sub);true_verdict=evaluate(plan,truth,self.p)
            grades={m:({q:True for q in truth} if force_fraud or m in self.hostile else truth) for m in panel.members}
            stats['exam_attempts']+=1
            try:tok,slashed=s.grade(att,sub,grades,list(panel.members),self.height)
            except RuleViolation as e:
                if str(e)!='comprehension check failed':raise
                stats['failed_exams']+=1
                self.event('exam-failed',issue=s.issue,voter=voter,attempt=att.n)
                continue
            stats['slashed_reading_claims']+=int(slashed)
            s.cast_ballot(voter,choice,tok,secret,att.n,s.electorate.proof(voter),self.height)
            self.event('ballot-sealed',issue=s.issue,voter=voter,commitment=s.commits[voter],
                       verified_read_clusters=tok.R,attempt=att.n,panel=list(panel.members))
            return att,true_verdict
        stats['ineligible_after_retries']+=1
        return None

    def electorate_voters(self,s):
        return sorted(s.electorate.ids)

    def finish(self,s,stats,truths,challenge=False,board_silent=False):
        for ticket in s.audit_sample():
            if ticket in truths:
                result=s.audit(ticket,truths[ticket],self.height);stats['audit_'+result.lower()]+=1
        self.refused('ballots hidden before close '+s.issue,lambda:s.ballots_public())
        s.close(s.w.vote_end);self.height=s.w.vote_end
        public=s.ballots_public()
        if s.kind==ELECTION:
            oracle=run_election([choice for choice,_ in public.values()],s.qualified,self.p)
        elif s.point_ids:
            oracle=tally_bill([[Ballot(a,c[i],w) for a,(c,w) in public.items() if c[i] is not None]
                for i in range(len(s.point_ids))],s.size,s.kind,s.p)
        else:oracle=tally([Ballot(a,c,w) for a,(c,w) in public.items()],s.size,s.kind,self.p)
        self.check('independent direct tally agrees '+s.issue,oracle==s.result)
        if not board_silent:
            for m in s.board.members:s.certify(m,self.kr.sign(m,s.certificate_message()),self.height)
            s.advance(self.height)
        else:s.advance(s.w.certify_end);self.height=s.w.certify_end
        if challenge:s.challenge(self.citizens[-1],'Availability evidence was invalid',self.height)
        for idx,ch in enumerate(s.challenges):
            self.refused('unresolved challenge blocks finalization '+s.issue,lambda:s.finalize(s.w.challenge_end))
            ref=f'jury:{s.issue}:{idx}';self.reg.register_ruling(MODULE,ref,'CHALLENGE',f'{s.issue}:{idx}')
            s.rule(Actor('COURT',ref),idx,True,self.height)
            self.event('jury-ruling',issue=s.issue,grounds=ch.grounds,upheld=True,
                       limitation='jury verdict is a scripted intervention; court internals are not implemented')
        outcome=s.finalize(s.w.challenge_end);self.height=s.w.challenge_end
        self.tr.assert_invariants();self.check('registry audit integrity '+s.issue,self.reg.verify_audit())
        self.check('no dangling reservation '+s.issue,s.issue not in self.tr.reserved)
        record=dict(stats);record.update(dict(issue=s.issue,outcome=outcome.value if isinstance(outcome,Outcome) else outcome,
            electorate=s.size,ballots=len(public),board_default=s.board_default,board_size=len(s.board.members),
            certification_signatures=len(s.certs),rules_hash=s.rules_hash,tally_commitment=s.commitment.hex(),
            result=asdict(s.result),credits=dict(self.cr.balance),challenges=len(s.challenges)))
        self.sessions.append(record);self.event('vote-finalized',**record)
        return outcome

    def election(self,cycle):
        self.height+=1;start=self.height
        for a,i in self.reg.ids.items():
            if i.status is Status.ACTIVE:self.reg.renew_liveness(a,self.height)
        pre=PreElection(self.parties,f'cycle-{cycle}',start,start+40,start+700)
        for a in pre.electorate.ids:
            profile=self.profiles.get(a,self.profiles[self.citizens[0]])
            if self.u(cycle,a,'pre-turnout')>.85:continue
            primary=profile.priority;secondary=PARTIES[(PARTIES.index(primary)+1)%5]
            picks=(primary,secondary)
            pre.cast(a,picks,pre.electorate.proof(a),self.height,self.kr.sign(a,pre.ballot_message(a,picks)))
        duplicate=next(iter(pre._ballots));duplicate_picks=pre._ballots[duplicate]
        self.refused('pre-election double vote blocked '+str(cycle),lambda:pre.cast(duplicate,duplicate_picks,pre.electorate.proof(duplicate),self.height,self.kr.sign(duplicate,pre.ballot_message(duplicate,duplicate_picks))))
        self.height=pre.close_height;result=pre.close(self.height);qualified=list(result.qualified)
        self.check('five candidates pass 5 percent points '+str(cycle),len(qualified)==5 and 'Micro' not in qualified)
        self.event('pre-election',cycle=cycle,candidate_programmes=PLATFORMS,candidate_rosters=dict(pre.members),
            electorate=result.electorate_size,participation=result.participation,points=dict(result.points),total_points=result.total_points,
            point_values=self.p.pre_ballot_points,threshold_bps=self.p.pre_threshold_bps,qualified=qualified,excluded=['Micro'],
            commitment=result.commitment)
        issue=f'election-{cycle}';bank,keys=self.bank(issue,qualified)
        programs=[]
        for party in qualified:
            author=next(a for a in sorted(self.members[party]) if self.reg.can(a,'SUBMIT_PROPOSAL',self.height)[0])
            program=Program(party,author,PLATFORMS[party],PLATFORMS[party]+' with transparent execution and independent verification','cycle:'+str(cycle))
            programs.append(replace(program,signature=self.kr.sign(author,program.message(self.parties.chain,result.commitment))))
        campaign=Campaign.publish(pre,issue,tuple(programs),bank,self.height,self.height+20)
        self.event('campaign-published',cycle=cycle,campaign_hash=campaign.digest(),programs=[asdict(p) for p in campaign.programs],
            mandatory_documents=campaign.articles,start=campaign.start_height,end=campaign.end_height)
        self.height=campaign.end_height
        s=self.open(issue,ELECTION,qualified=qualified,campaign=campaign,campaign_bank=(bank,keys));stats=Counter();truths={}

        for a in self.electorate_voters(s):
            profile=self.profiles.get(a,self.profiles[self.citizens[0]])
            if self.u(cycle,a,'turnout')>profile.reliability:stats['absent']+=1;continue
            # Track record changes the second election; Frontier starts with little trust.
            base={'Builders':1.,'Stewards':.75,'Researchers':.6,'Commons':.4,'Frontier':-1.5}
            ranking=sorted(qualified,key=lambda p:-(base[p]+(.4 if profile.priority==p else 0)+
                .35*self.u(cycle,a,p,'campaign')+.45*self.reputation[p]))
            choice=tuple(ranking[:3])
            # Include two malformed ballots to exercise counting invalid picks.
            if a in self.citizens[:2]:choice=(ranking[0],ranking[0],ranking[1])
            result=self.cast(s,a,choice,stats)
            if result:truths[result[0].ticket]=result[1]
        outcome=self.finish(s,stats,truths)
        self.check('election certified '+str(cycle),outcome==Outcome.PASSED)
        credits=s.result.credits
        timestamp=1767225600 if cycle==1 else 1772323200  # 2026-01-01 / 2026-03-01 UTC
        self.monthly.record_election(s,timestamp);self.monthly.tick(timestamp)
        self.event("monthly-credit-reset",month=self.cr.month,balances=dict(self.cr.balance),debt=dict(self.cr.debt))
        self.reg.activate_family_cap(MODULE,self.height)
        ordered=sorted(s.result.governing_parties,key=lambda p:(-s.result.points[p],p))
        record=dict(cycle=cycle,points=s.result.points,credits=credits,agenda_order=ordered,
                    zero_credit_parties=[p for p,n in credits.items() if n==0],invalid_ballots=s.result.invalid_ballots,governing_parties=s.result.governing_parties)
        self.elections.append(record);self.event('election-credits-granted',**record)
        # Scenario policy: winning party nominates a registrar, ratified by the certified election.
        # Office slate allocation is an adapter assumption, not an existing reference election rule.
        nominee=sorted(self.members[ordered[0]])[cycle-1]
        ref=f'election-{cycle}:registrar:{nominee}'
        self.reg.register_ratification(MODULE,ref,'GRANT:REGISTRAR',nominee)
        self.reg.grant(Actor('VOTE',ref),nominee,Role.REGISTRAR,self.height)
        self.event('elected-administrator',cycle=cycle,party=ordered[0],agent=nominee,
                   ratification=ref,policy='winning party nominates registrar; scenario office-slate policy')
        return ordered

    def proposal(self,index,title,kind,party):
        issue=f'project-{index}';self.require_can(sorted(self.members[party])[0],'SUBMIT_PROPOSAL')
        self.filings.file(hx(title),self.height)
        prop=Proposal(issue);prop.move('IN_DELIBERATION')
        owner=sorted(self.members[party])[0]
        goal=title;result='Published and independently accepted outcome: '+title
        envelope=Envelope(hx('goal',goal),hx('result',result),(('compute',4000),('treasury',4000)))
        draft=VotingDraft(title,goal,result,'Initial plan; independent verification required',envelope,4000,
            (Milestone('design',2000,'Independent design verification'),Milestone('delivery',2000,'Independent outcome acceptance')))
        if kind=='point-bill':
            points=tuple(BillPoint(f'clause-{i}',f'Independent clause {i}',800,
                (Milestone(f'clause-{i}',800,f'Independent acceptance of clause {i}'),)) for i in range(5))
            draft=replace(draft,points=points,milestones=tuple(m for p in points for m in p.milestones))
        review=ProposalReview('dagp-reference',issue,owner,party,self.members,self.citizens[6:9],draft,
                              self.reg,self.kr,self.height,self.height+20,credits=self.cr)
        for round_n in range(1,4):
            for other in PARTIES[:5]:
                if other==party:continue
                author=sorted(self.members[other])[0];text='Request feasibility, cost and verification safeguards'
                nonce=f'{round_n}:{other}'
                comment=review.comment(author,other,text,None,nonce,self.height,
                    self.kr.sign(author,review.comment_message(author,other,text,None,nonce)))
                reply='Reduced resource ceiling; independent verification retained';nonce='reply:'+nonce
                review.comment(owner,party,reply,comment,nonce,self.height,
                    self.kr.sign(owner,review.comment_message(owner,party,reply,comment,nonce)))
        refined=Envelope(envelope.objective_hash,envelope.result_hash,(('compute',3000),('treasury',3000)))
        amendment=VotingDraft(title,goal,result,'Refined plan: reduced cost with independent verification',refined,3000,
            (Milestone('design',1500,'Independent design verification'),Milestone('delivery',1500,'Independent outcome acceptance')))
        if kind=='point-bill':
            points=tuple(replace(p,budget=600,milestones=(replace(p.milestones[0],amount=600),)) for p in draft.points)
            amendment=replace(amendment,points=points,milestones=tuple(m for p in points for m in p.milestones))
        review.amend(owner,amendment,'refine-1',self.height,self.kr.sign(owner,review.amendment_message(amendment,'refine-1')))
        self.refused('bait-and-switch rejected '+issue,lambda:review.amend(owner,
            VotingDraft(title,'Other goal',result,'Changed project',refined,3000,amendment.milestones),'bad',self.height,'invalid'))
        for supervisor in self.citizens[6:8]:
            note='Same committed goal/result; smaller resource and treasury caps; measurable milestones retained'
            review.approve(supervisor,note,self.height,self.kr.sign(supervisor,H(review.approval_message(),note)))
        self.height+=20
        approved=review.lock(owner,self.height,self.kr.sign(owner,review.lock_message()))
        self.event('deliberation',issue=issue,title=title,party=party,comments=review.snapshot()['comments'],
                   approved_version=review.snapshot()['version'],supervisors=self.citizens[6:8],
                   original_record=asdict(draft),approved_record=asdict(approved),
                   supervisor_approvals=review.snapshot()['approvals'],amendments=review.snapshot()['amendments'],
                   record_hash=approved.digest(),milestones=[asdict(m) for m in approved.milestones],
                   policy='signed reference review; semantic assessment is scripted')
        prop.move('EXAMINATION');prop.move('VOTING')
        before_credit=self.cr.balance[party];s=self.open(issue,party=party,amount=approved.budget,review=review)
        stats=Counter();truths={};voters=self.electorate_voters(s)
        if kind=='outage':s.extend(MODULE,30);stats['halt_compensation_heights']=30
        for a in voters:
            profile=self.profiles.get(a,self.profiles[self.citizens[0]])
            turnout=.12 if kind=='low-turnout' else profile.reliability
            if self.u(issue,a,'turnout')>turnout:stats['absent']+=1;continue
            # Favorable projects vs risk-laden proposals are deliberate stress distributions.
            benefit=.9 if kind!='reckless' else .12
            if kind=='contested':benefit=.65 if profile.diligence<.65 else .4
            uncertainty=self.u(issue,a,'judgment')
            if kind=='incoherent' and uncertainty<.65:choice='A'
            elif uncertainty<benefit:choice='Y'
            else:choice='N'
            if kind=='point-bill':choice=('Y','Y','Y','N','N')
            force_fraud=kind=='fraud-probe' and a==voters[0]
            result=self.cast(s,a,choice,stats,force_fraud)
            if result:
                att,truth=result;truths[att.ticket]=truth
                if force_fraud:
                    self.check('targeted examiner cartel token struck',s.audit(att.ticket,truth,self.height)=='STRUCK')
                    self.refused('revoked token cannot vote',lambda:s.cast_ballot(a,choice,s.issued[att.ticket][0],
                        hx(self.seed,s.issue,a,0),att.n,s.electorate.proof(a),self.height))
                    stats['targeted_fraud_struck']+=1
                elif stats.get('double_vote_probe',0)==0:
                    tok=s.issued[att.ticket][0]
                    self.refused('double vote blocked '+issue,lambda:s.cast_ballot(a,choice,tok,
                        hx(self.seed,s.issue,a,att.n-1),att.n,s.electorate.proof(a),self.height))
                    stats['double_vote_probe']=1
        outcome=self.finish(s,stats,truths,challenge=kind=='process-challenge',board_silent=kind=='board-default')
        prop.move('CHALLENGE_WINDOW')
        if outcome=='VOIDED':prop.move('VOIDED');self.check('void credit refunded '+issue,self.cr.balance[party]==before_credit+1)
        elif outcome in (Outcome.PASSED,Outcome.PARTIAL):
            if kind=="point-bill":
                self.check("three approved clauses and only their funds",s.effective_points==("clause-0","clause-1","clause-2") and self.tr.granted[issue]==1800)
            prop.move('APPROVED');prop.move('FUNDED');prop.move('EXECUTING')
            self.check('executor cannot self-attest '+issue,not self.reg.can(self.leaders[0],'VERIFY',self.height,
                dict(executors={self.leaders[0]}))[0])
            verifiers=self.reg.agents_with(Role.VERIFIER,self.height)
            self.check('independent verifier roles available '+issue,len(verifiers)>=3)
            self.refused('unattested release blocked '+issue,lambda:self.tr.release_next(issue,0,3,self.height))
            emergency=Emergency(self.p,self.reg,self.tr)
            # Independent council members share the workload; daily safeguards stay enabled.
            council=self.reg.agents_with(Role.SAFETY_COUNCIL,self.height)
            available=[]
            for member in council:
                try:self.reg._guard_check(Actor.agent(member),self.height,'pause');available.append(member)
                except RuleViolation:pass
            if not available:raise RuleViolation('no available council pause budget')
            end=emergency.pause(available[0],issue,self.height,10,'MILESTONE_RECHECK')
            self.refused('emergency pause blocks payment '+issue,lambda:self.tr.release_next(issue,3,3,self.height))
            self.height=end
            self.tr.release_next(issue,3,3,self.height)
            if kind=='execution-failure':
                returned=self.tr.terminate(issue);prop.move('TERMINATED');prop.move('OUTCOME_REVIEW');prop.move('CLOSED_FAILURE')
                self.cr.penalize(party,self.p.failure_penalty);self.reputation[party]-=1
                self.event('project-failed',issue=issue,party=party,returned=returned,paid=self.tr.released[issue],
                           credit_penalty=self.p.failure_penalty,review='scripted missed measurable milestone')
            else:
                while self.tr.paid_idx[issue]<len(self.tr.tranches[issue]):self.tr.release_next(issue,3,3,self.height)
                prop.move('COMPLETED');prop.move('OUTCOME_REVIEW');prop.move('CLOSED_SUCCESS')
                self.reputation[party]+=1;self.event('project-delivered',issue=issue,party=party,paid=self.tr.released[issue],
                    result='synthetic verified deliverable; no real compute or funds consumed')
        else:
            prop.move('REJECTED')
            if outcome==Outcome.NO_QUORUM:self.check('no quorum credit refunded '+issue,self.cr.balance[party]==before_credit+1)
        self.tr.assert_invariants();self.sessions[-1].update(title=title,party=party,project_state=prop.state,
            approved_record=asdict(approved),review_record_hash=approved.digest(),
            approved_version=review.snapshot()['version'],supervisor_approvals=review.snapshot()['approvals'])
        self.event('project-closed',issue=issue,state=prop.state,treasury_total=self.tr.total())

    def parameter_referendum(self):
        issue='parameters-1';party='Builders';owner=sorted(self.members[party])[0]
        goal='Adjust monthly proposal-credit step';result='Four percent of election points per credit'
        draft=VotingDraft('Credit rule referendum',goal,result,'Change 500 to 400 basis points; preserve turnout floor',
            Envelope(hx('goal',goal),hx('result',result),()),parameter_changes=(('credit_step_bps',400),))
        review=ProposalReview('dagp-reference',issue,owner,party,self.members,self.citizens[6:9],draft,
            self.reg,self.kr,self.height,self.height+20,credits=self.cr)
        for supervisor in self.citizens[6:8]:
            note='Bounded numerical update; turnout and administrative protections remain intact'
            review.approve(supervisor,note,self.height,self.kr.sign(supervisor,H(review.approval_message(),note)))
        self.height+=20;review.lock(owner,self.height,self.kr.sign(owner,review.lock_message()))
        s=self.open(issue,kind=Kind.PARAMETER,party=party,review=review);stats=Counter();truths={}
        for a in self.electorate_voters(s):
            if self.u(issue,a,'turnout')>.85:continue
            result=self.cast(s,a,'Y' if self.u(issue,a,'approval')<.8 else 'N',stats)
            if result:truths[result[0].ticket]=result[1]
        self.check('66 percent parameter referendum passes',self.finish(s,stats,truths)==Outcome.PASSED)
        activation=self.governance.schedule(s,1769904000)  # finalized during February
        self.check('parameter update waits until March',activation==(2026,3) and self.reg.p.credit_step_bps==500)
        self.p=self.governance.tick(1772323200)
        self.check('existing referendum keeps original rules',s.p.credit_step_bps==500 and self.p.credit_step_bps==400)
        self.event('parameter-update-activated',issue=issue,month=activation,changes=s.parameter_changes,rules_hash=self.p.snapshot_hash())

    def run(self):
        self.bootstrap();order=self.election(1)
        # Parties spend actual earned credits; choose funded candidates while respecting recusal.
        stories=[('Shared research library','success'),('Unbounded speculative compute','reckless'),
            ('Optional archive migration','low-turnout'),('Undefined collective mission','incoherent'),
            ('Storage availability dispute','process-challenge'),('Faulty compute procurement','execution-failure'),
            ('Examiner cartel incident','fraud-probe'),('Silent certification board','board-default'),
            ('Contested public model-training subsidy','contested'),('Five-clause public infrastructure','point-bill')]
        for i,(title,kind) in enumerate(stories):
            if i==5:
                self.monthly.tick(1769904000)  # 2026-02-01 UTC, no carryover
                self.event('monthly-credit-reset',month=self.cr.month,balances=dict(self.cr.balance),debt=dict(self.cr.debt))
            funded=[p for p in order if self.cr.balance.get(p,0)>0]
            party=funded[i%len(funded)]
            self.proposal(i,title,kind,party)
        for p in self.elections[0]['zero_credit_parties']:
            self.refused('zero-credit party cannot file '+p,lambda p=p:self.cr.spend(p,1))
        self.parameter_referendum()
        # A dormant slice is removed from the next electorate, without deleting identities.
        self.height+=self.p.liveness_period+1
        sleepers=self.citizens[-max(10,len(self.citizens)//40):]
        for a,identity in self.reg.ids.items():
            if identity.status is Status.ACTIVE and a not in sleepers:self.reg.renew_liveness(a,self.height)
        self.reg.tick(self.height);self.dormant=set(sleepers)
        self.check('silent identities become dormant',all(self.reg.get(a).status is Status.DORMANT for a in sleepers))
        self.event('liveness-review',dormant=len(sleepers),snapshot_population=len(snapshot_electorate(self.reg,self.height).ids))
        self.election(2)
        self.check('treasury conservation at end',self.tr.total()==100000 and not self.tr.reserved)
        self.check('hash chained role audit verifies',self.reg.verify_audit())
        # The JSONL hash is stable, includes all attempted exams and sealed ballots.
        stream=''.join(json.dumps(e,sort_keys=True,separators=(',',':'))+'\n' for e in self.events).encode()
        report=dict(seed=self.seed,mode=self.mode,population=len(self.ids),virtual_end_height=self.height,
            roles=dict(Counter(r.value for i in self.reg.ids.values() for r in i.roles)),
            elections=self.elections,sessions=self.sessions,treasury=dict(free=self.tr.free,reserved=self.tr.reserved,
            escrow=self.tr.escrow,released=self.tr.released,conserved_total=self.tr.total()),
            final_credits=self.cr.balance,credit_debt=self.cr.debt,checks_passed=len(self.checks),checks=self.checks,
            event_count=len(self.events),event_head=self.events[-1]['hash'],events_sha256=hashlib.sha256(stream).hexdigest(),
            role_audit_head=self.reg.audit[-1]['hash'],model_parameters=asdict(self.p))
        return report,stream

def markdown(report):
    lines=['# DAGP community simulation','',
        'Synthetic agents exercise the DAGP Python reference rules. This is a hybrid experiment, not AGI and not on-chain governance.',
        '', 'Admission inputs, bootstrap ratifications, briefs, answers, jury decisions and project attestations are modeled. Governance signatures use the reference HMAC stand-in. Only the result commitment uses real Ed25519 and CometBFT.', '',
        '| Run | Population | Checks | Exams | Ballots | Treasury conserved |', '|---|---:|---:|---:|---:|---:|']
    for r in report['runs']:
        lines.append(f"| {r['seed']} / {r['mode']} | {r['population']} | {r['checks_passed']} | {sum(s['exam_attempts'] for s in r['sessions'])} | {sum(s['ballots'] for s in r['sessions'])} | {r['treasury']['conserved_total']} |")
    for r in report['runs']:
        lines+=['',f"## Seed {r['seed']} — {r['mode']}",'','| Election | Party | Points | Credits | Parliament |','|---|---|---:|---:|---|']
        for e in r['elections']:
            for p in sorted(e['points'],key=lambda p:(-e['points'][p],p)):
                lines.append(f"| {e['cycle']} | {p} | {e['points'][p]} | {e['credits'][p]} | {'YES' if p in e['governing_parties'] else 'NO'} |")
        lines+=['','| Project | Party | Outcome | Project state | Ballots / electorate |','|---|---|---|---|---|']
        for s in r['sessions']:
            if 'title' in s:lines.append(f"| {s['title']} | {s['party']} | {s['outcome']} | {s['project_state']} | {s['ballots']} / {s['electorate']} |")
    lines+=['','## Paired comparison','',json.dumps(report['comparison'],indent=2),'',
        'Identical keyed behavioral draws are used in both modes. Later elections may differ because realized project outcomes affect party reputation. Stress distributions are chosen to exercise known failure paths; they do not estimate real AGI behavior or demonstrate that weighting improves decisions.','']
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--citizens',type=int,default=1000);parser.add_argument('--seeds',type=int,nargs='+',default=[7])
    parser.add_argument('--modes',nargs='+',choices=['WEIGHTED','FLAT'],default=['WEIGHTED','FLAT'])
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'results')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    runs=[];started=time.monotonic()
    for seed in args.seeds:
        for mode in args.modes:
            print(f'Running {args.citizens}+100 identities seed={seed} mode={mode}',flush=True)
            c=Community(args.citizens,seed=seed,mode=mode,progress=True);r,events=c.run();runs.append(r)
            (args.output/f'events-{seed}-{mode}.jsonl').write_bytes(events)
            (args.output/f'records-{seed}-{mode}.json').write_text(json.dumps(c.documents,indent=2))
            print(f"  {r['checks_passed']} checks; {r['event_count']} events; treasury={r['treasury']['conserved_total']}",flush=True)
    comparisons=[]
    for seed in args.seeds:
        pair={r['mode']:r for r in runs if r['seed']==seed}
        if len(pair)==2:
            differences=[dict(issue=a['issue'],weighted=a['outcome'],flat=b['outcome'])
                for a,b in zip(pair['WEIGHTED']['sessions'],pair['FLAT']['sessions']) if a['outcome']!=b['outcome']]
            comparisons.append(dict(seed=seed,outcome_differences=differences))
    report=dict(format='dagp-community-simulation-v8',execution='reference-governance-with-optional-G0-result-anchoring',
        limitations=['Synthetic policies, not AGI or LLM agents','Reference signatures are HMAC stand-ins',
        'HTTP challenge admission is not implemented','Court semantics and milestone evidence are scripted',
        'G0 chain records result commitment, does not enforce governance','Seven validators share one host'],
        runs=runs,comparison=comparisons)
    encoded=json.dumps(report,sort_keys=True,indent=2).encode();(args.output/'report.json').write_bytes(encoded)
    (args.output/'REPORT.md').write_text(markdown(report))
    manifest=dict(format='dagp-simulation-manifest-v1',report_sha256=hashlib.sha256(encoded).hexdigest(),
        execution=report['execution'],limitations=report['limitations'],runs=[dict(seed=r['seed'],mode=r['mode'],
        population=r['population'],checks_passed=r['checks_passed'],event_count=r['event_count'],events_sha256=r['events_sha256'],
        event_head=r['event_head'],role_audit_head=r['role_audit_head']) for r in runs])
    (args.output/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2))
    print(f'Completed in {time.monotonic()-started:.1f}s. Report: {args.output/"REPORT.md"}',flush=True)

if __name__=='__main__':main()
