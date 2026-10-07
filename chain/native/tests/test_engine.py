import copy
import json
import unittest
from dagp_native.codec import encode,decode,canonical
from dagp_native.engine import World
from dagp_ref.comprehension import commit_key
from dagp_ref.campaign import article_id,source_hash
from dagp_ref.tally import Outcome
from dagp_ref.treasury import RuleViolation

NOW=1800000000

def charter(count=150):
    ids={f'a{i:03d}':dict(operator=f'op{i}',family=f'f{i%5}',citizen_since=NOW-40*86400,
         roles=['CITIZEN','EXAMINER','VERIFIER','JUROR','VOTE_SUPERVISOR','REGISTRAR']+(['ADMIN'] if i<50 else [])) for i in range(count)}
    return dict(identities=ids,common_budget=100000,balances={a:200 for a in ids},
        beacon=dict(public_key='00',genesis_time=NOW,period=1,scheme='pedersen-bls-unchained'),root='root',constraints=[])

def questions(issue,articles=None):
    qs=[];clusters={}
    def add(article,source='',count=2):
        for j in range(count):
            qs.append(dict(id=f'{article}:{j}',article=article,options=2,key_commit=commit_key(0,'salt'),
                prompt='Which action is described?',choices=['The stated action','Another action'],source_hash=source))
    add('__proposal__',count=5)
    for article,source in (articles or {}).items():add(article,source);clusters[article]=article
    return dict(questions=qs,clusters=clusters)

def project(points=False):
    d=dict(title='Public compute',goal='Improve shared compute',result='A working public service',body='Build and verify a service.',budget=100,
        milestones=[dict(label='delivery',amount=100,acceptance='Independent checks pass')],points=[],parameters=[],caps=[['treasury',100]])
    if points:
        d['budget']=500;d['caps']=[['treasury',500]]
        d['milestones']=[dict(label=f'm{i}',amount=100,acceptance=f'Validate item {i}') for i in range(5)]
        d['points']=[dict(id=f'p{i}',text=f'Item {i}',budget=100,milestones=[d['milestones'][i]],requires=[]) for i in range(5)]
    return d

class NativeStory(unittest.TestCase):
    def setUp(self):
        self.w=World('native-test',NOW,charter(),{f'a{i:03d}':f'{i:064x}' for i in range(150)})
        self.seq=0
    def act(self,actor,op,**args):
        self.seq+=1;out=self.w.execute(actor,op,args,str(self.seq),self.verified(op,args))
        # Persist and restore after every transaction, including cycles/shared banks.
        if getattr(self,'persist_each',True):self.w=decode(encode(self.w))
        return out
    def verified(self,op,args):
        return {'beacon_seed':f'{args["round"]:064x}'} if op=='beacon.publish' else {}
    def future_beacon(self):
        rel=self.w.assignments._round+1;absolute=self.w.rounds[rel]
        self.w.tick(self.w.beacon['genesis_time']+(absolute-1)*self.w.beacon['period'])
        return self.act('a149','beacon.publish',round=rel,absolute_round=absolute,signature='fixture')
    def form(self,party,start):
        members=[f'a{i:03d}' for i in range(start,start+10)]
        for a in members:self.act(a,'party.consent',party=party,members=members,nonce='formation',scope='root')
    def ballot(self,actor,issue,choice,declared=()):
        out=self.act(actor,'exam.request',issue=issue,secret=actor)
        ticket=out['ticket'];s=self.w.sessions[issue];plan=s.plan(self.w.attempts.records[ticket],tuple(declared))
        qids=[q.qid for q in plan.proposal_qs]+[q.qid for _,q in plan.sampled]
        self.act(actor,'exam.submit',issue=issue,ticket=ticket,declared=list(declared),answers={q:0 for q in qids})
        for member in out['panel'][:3]:self.act(member,'exam.grade',issue=issue,ticket=ticket,verdicts={q:True for q in qids})
        self.act(actor,'vote.cast',issue=issue,ticket=ticket,choice=choice,secret=actor)
    def finish(self,issue):
        s=self.w.sessions[issue];self.w.tick(s.w.vote_end);self.act('a149','vote.close',issue=issue)
        self.w.tick(s.w.certify_end);self.act('a149','vote.advance',issue=issue)
        self.w.tick(s.w.challenge_end);return self.act('a149','vote.finalize',issue=issue)
    def elect(self):
        self.form('alpha',0);self.form('beta',10)
        self.act('a000','pre.open',cycle='cycle',close=self.w.now+86400,deadline=self.w.now+80*86400,scope='root')
        count=len(self.w.registry.ids)//5
        for i in range(count):self.act(f'a{i:03d}','pre.vote',cycle='cycle',picks=['alpha','beta'])
        self.w.tick(self.w.now+86400);result=self.act('a149','pre.close',cycle='cycle')
        self.assertEqual(result['qualified'],('alpha','beta'))
        for party,actor in [('alpha','a000'),('beta','a010')]:self.act(actor,'campaign.program',cycle='cycle',party=party,program=party+' program',vision=party+' vision',nonce='program')
        articles={article_id(party,section):source_hash(party+' '+section) for party in ('alpha','beta') for section in ('program','vision')}
        self.act('a149','campaign.publish',cycle='cycle',issue='election',bank=questions('election',articles),end=self.w.now+7*86400)
        self.future_beacon();self.w.tick(self.w.now+7*86400)
        self.act('a149','election.open',issue='election',windows=[self.w.now+86400,self.w.now+2*86400,self.w.now+4*86400])
        s=self.w.sessions['election'];voters=[a for a in s.electorate.ids if a not in s.board.members][:count]
        for a in voters:self.ballot(a,'election',['alpha','beta'],list(articles))
        self.assertEqual(self.finish('election')['outcome'],'PASSED')
        self.assertEqual(self.w.credits.balance['alpha'],13)
        self.assertEqual(self.w.credits.balance['beta'],6)
    def test_complete_election_partial_project_and_milestone(self):
        self.elect();self.assertEqual(self.w.treasury.free,100000)
        issue='project';d=project(True);self.act('a000','proposal.prepare',issue=issue,party='alpha',draft=d,review_end=self.w.now+2*86400,scope='root',bank=questions(issue),kind='ORDINARY',effect=None)
        self.future_beacon();self.act('a000','proposal.begin',issue=issue)
        r=self.w.reviews[issue]
        for a in r._supervisors:self.act(a,'proposal.approve',issue=issue,note='The goals and budgets are consistent.',version=1,commitment=r._draft.digest())
        self.w.tick(self.w.now+2*86400);self.act('a000','proposal.lock',issue=issue,version=1,commitment=r._draft.digest())
        self.future_beacon();self.act('a000','proposal.open',issue=issue,windows=[self.w.now+86400,self.w.now+2*86400,self.w.now+4*86400],beneficiary='a000')
        s=self.w.sessions[issue];voters=[a for a in s.electorate.ids if a not in s.board.members][:20]
        for a in voters:self.ballot(a,issue,['YES','YES','YES','NO','NO'])
        self.assertEqual(self.finish(issue)['outcome'],'PARTIAL')
        self.assertEqual(self.w.treasury.escrow[issue],300)
        before=self.w.wallets['a000'];members=self.w.payments._policies[issue][0]
        args=dict(project=issue,index=0,amount=100,evidence='0'*64,valid_from=self.w.now,expires=self.w.now+86400)
        for m in members[:2]:result=self.act(m,'milestone.approve',**args)
        self.assertEqual(result['released'],100);self.assertEqual(self.w.wallets['a000'],before+100)
        self.w.assert_invariants()

    def test_expired_registrar_freeze_restores_professional_authority(self):
        with self.assertRaises(RuleViolation):self.act('a000','identity.freeze',target='a149',duration=60,evidence='e'*64)
        config=charter();config['identities']['a149']['roles']=['CITIZEN','EXAMINER']
        self.w=World('native-test',NOW,config,{f'a{i:03d}':f'{i:064x}' for i in range(150)})
        self.act('a000','identity.freeze',target='a149',duration=60,evidence='e'*64)
        self.assertTrue(self.w.registry.can('a149','VOTE',self.w.now)[0])
        self.assertFalse(self.w.registry.can('a149','GRADE',self.w.now)[0])
        self.w.tick(self.w.now+60)
        self.assertTrue(self.w.registry.can('a149','GRADE',self.w.now)[0])

    def test_real_parameter_vote_monthly_activation_preserves_open_council(self):
        from datetime import datetime,timezone
        self.elect()
        d=project();d.update(budget=0,milestones=[],caps=[],parameters=[['credit_step_bps',400]])
        issue='policy';self.act('a000','proposal.prepare',issue=issue,party='alpha',draft=d,review_end=self.w.now+2*86400,scope='root',bank=questions(issue),kind='PARAMETER',effect=None)
        self.future_beacon();self.act('a000','proposal.begin',issue=issue);r=self.w.reviews[issue]
        for reviewer in r._supervisors:self.act(reviewer,'proposal.approve',issue=issue,note='Bounded credit step update',version=1,commitment=r._draft.digest())
        self.w.tick(self.w.now+2*86400);self.act('a000','proposal.lock',issue=issue,version=1,commitment=r._draft.digest());self.future_beacon()
        self.act('a000','proposal.open',issue=issue,windows=[self.w.now+86400,self.w.now+2*86400,self.w.now+4*86400],beneficiary='a000')
        s=self.w.sessions[issue]
        voters=[a for a in s.electorate.ids if a not in s.board.members][:20]
        for voter in voters:self.ballot(voter,issue,'YES')
        self.assertEqual(self.finish(issue)['outcome'],'PASSED')
        year,month=self.w.policy.pending[0]
        activation=int(datetime(year,month,1,tzinfo=timezone.utc).timestamp())
        self.w.tick(activation-60)
        case=self.act('a000','admin.open',target='a001',evidence='a'*64)['case']
        roster=self.w.council._roster;version=self.w.council._version
        self.w.tick(activation)
        self.assertEqual(self.w.params.credit_step_bps,400)
        self.assertEqual(self.w.credits.balance['alpha'],16)
        self.assertEqual(self.w.council._roster,roster);self.assertEqual(self.w.council._version,version)
        for actor in [a for a in roster if a!='a001'][:25]:out=self.act(actor,'admin.approve',case=case)
        self.assertTrue(out['applied'])
    def test_codec_canonical_cycles_and_forbidden_classes(self):
        encoded=encode(self.w);self.assertEqual(canonical(encoded),canonical(encode(decode(encoded))))
        restored=decode(encoded);self.assertIs(restored.registry.assignments.reg,restored.registry)
        bad=copy.deepcopy(encoded);bad['nodes'][0]['class']='os.system'
        with self.assertRaises(ValueError):decode(bad)
    def test_unauthorized_actions_are_not_capabilities(self):
        for op in ('register_ratification','treasury.release_next','MODULE','role.grant','beacon.publish'):
            with self.assertRaises((RuleViolation,KeyError)):
                self.act('a000',op)

    def test_challenge_requires_funding_and_sponsorship_is_bounded(self):
        verified={'registration_key':'f'*64}
        before=self.w.treasury.free
        with self.assertRaises(RuleViolation):self.w.execute('new','identity.challenge',{'key':'f'*64},'unfunded',verified)
        self.assertNotIn('new',self.w.public_keys)
        for index in range(5):self.act('a000','wallet.transfer',to=f'new{index}',amount=11)
        with self.assertRaises(RuleViolation):self.act('a000','wallet.transfer',to='sixth',amount=11)
        with self.assertRaises(RuleViolation):self.act('a001','wallet.transfer',to='invalid/account',amount=11)
        result=self.w.execute('new0','identity.challenge',{'key':'f'*64},'funded',verified)
        self.assertEqual(self.w.wallets['new0'],10)
        self.assertEqual(self.w.treasury.free,before+1)
        self.w.tick(self.w.now+1)
        self.act('new0','identity.register',operator='newop',family='newfamily',key='f'*64,challenge=result['challenge'])
        self.future_beacon();registrar=self.w.members('admission','new0')[0]
        self.act(registrar,'identity.admit',target='new0',accept=True,reason='Challenge and identity reviewed')
        self.assertFalse(self.w.registry.can('new0','VOTE',self.w.now)[0])
        self.w.tick(self.w.now+3*86400)
        self.assertTrue(self.w.registry.can('new0','VOTE',self.w.now)[0])

    def test_paired_subsociety_formation_preserves_hierarchy_and_strips_offices(self):
        founders=[f'a{i:03d}' for i in range(10)]
        expires=self.w.now+60*86400
        for actor in founders:
            out=self.act(actor,'society.consent',parent='root',child='cell',members=founders,constraints=[],nonce='cell',expires=expires)
        request=out['request'];self.future_beacon()
        reviewers=self.w.members('hierarchy_review',request)
        for reviewer in reviewers:self.act(reviewer,'society.approve',request=request,authority='root',note='Compatible with parent charter')
        self.act('a149','society.preapprove',request=request)
        issues=self.act('a149','society.mandates',child='cell')['issues']
        with self.assertRaises(RuleViolation):self.act('a149','society.activate',child='cell')
        self.w.tick(self.w.now+7*86400)
        for issue in issues:
            self.act('a149','society.vote_prepare',issue=issue);self.future_beacon()
            self.act('a149','society.vote_open',issue=issue,bank=questions(issue),windows=[self.w.now+86400,self.w.now+2*86400,self.w.now+4*86400])
            session=self.w.sessions[issue]
            voters=[a for a in session.electorate.ids if a not in session.board.members][:session.size//2]
            for voter in voters:self.ballot(voter,issue,'YES')
            self.assertEqual(self.finish(issue)['outcome'],'PASSED')
        with self.assertRaises(RuleViolation):self.act('a149','society.activate',child='cell')
        self.w.tick(self.w.now+7*86400);self.act('a149','society.activate',child='cell')
        local=self.w.tree.view('cell')
        self.assertEqual(set(local.ids),set(founders))
        self.assertFalse(local.can('a000','ADMIN_VOTE',self.w.now)[0])
        # Small cells cannot replace the independent 51-person board with insiders.
        with self.assertRaises(RuleViolation):self.w.freeze('certification','unsafe-cell-vote',('a000',),local)

    def test_judicial_ban_requires_independent_two_stage_assignment(self):
        from dagp_ref.roles import Status
        result=self.act('a149','court.open',target='a000',action='BAN',duration=0,evidence='a'*64)
        cid=result['case']
        with self.assertRaises(RuleViolation):self.act('a000','court.apply',case=cid)
        self.future_beacon();jury=self.w.members('jury','court:'+cid)
        self.assertNotIn('a000',jury);self.assertNotIn('a149',jury)
        with self.assertRaises(RuleViolation):self.act('a000','court.judge',case=cid,upheld=True,evidence='b'*64)
        for juror in jury[:3]:self.act(juror,'court.judge',case=cid,upheld=True,evidence='b'*64)
        self.future_beacon();admins=self.w.members('admin_review','court:'+cid)
        self.assertFalse(set(jury)&set(admins))
        before=self.w.treasury.free;bond=self.w.registry.get('a000').bond+self.w.registry.get('a000').stake
        self.act(admins[0],'court.apply',case=cid)
        self.assertEqual(self.w.registry.get('a000').status,Status.BANNED)
        self.assertEqual(self.w.treasury.free,before+bond-self.w.registry.get('a000').bond)
        with self.assertRaises(RuleViolation):self.act(admins[0],'court.apply',case=cid)
        appeal=self.act('a000','court.appeal',evidence='c'*64)['case']
        self.future_beacon();newjury=self.w.members('jury','court:'+appeal)
        self.assertNotIn(admins[0],newjury)
        for juror in newjury[:3]:self.act(juror,'court.judge',case=appeal,upheld=True,evidence='d'*64)
        self.future_beacon();newadmins=self.w.members('admin_review','court:'+appeal)
        self.act(newadmins[0],'court.apply',case=appeal)
        self.assertEqual(self.w.registry.get('a000').status,Status.ACTIVE)
        self.assertFalse(self.w.registry.can('a000','ADMIN_VOTE',self.w.now)[0])

    def test_bilateral_merger_actual_supermajorities_exit_claim_and_failed_claim_recovery(self):
        from dagp_native.merger import exports,name
        from dagp_ref.roles import Role,Status
        # Host verification is a fixture here; Go tests verify actual checkpoint
        # signatures and export Merkle proofs independently.
        self.persist_each=False
        self.w=World('source',NOW,charter(300),{f'a{i:03d}':f'{i:064x}' for i in range(300)})
        other=NativeStory();other.setUp();other.persist_each=False
        other.w=World('destination',NOW,charter(300),{f'a{i:03d}':f'{i+1000:064x}' for i in range(300)})
        self.elect();other.elect()
        def link(story,peer_world,export_key,op,actor='a149',**args):
            args['peer']={}
            return story.w.execute(actor,op,args,'peer:'+str(story.seq),dict(peer_chain=peer_world.chain,peer_key=export_key,peer_value=json.dumps(exports(peer_world)[export_key])))
        snapshot=self.act('a149','merger.snapshot',id='cohort')
        manifest=dict(id='union',source='source',destination='destination',snapshot='cohort',root=snapshot['root'],size=snapshot['size'],expires=self.w.now+90*86400,policy='identity-only-citizen-warmup-v1')
        link(self,other.w,'society','merger.propose',manifest=manifest)
        link(other,self.w,'population/cohort','merger.propose',manifest=manifest)
        for story in (self,other):
            story.future_beacon();story.w.tick(story.w.now+30*86400)
            issue=story.w.mergers['union'].mandate.issue
            story.act('a149','merger.vote_open',id='union',bank=questions(issue),windows=[story.w.now+86400,story.w.now+2*86400,story.w.now+4*86400])
            session=story.w.sessions[issue]
            voters=[a for a in session.electorate.ids if a not in session.board.members][:240]
            self.assertEqual(len(voters),240)
            for voter in voters:story.ballot(voter,issue,'YES')
            self.assertEqual(story.finish(issue)['outcome'],'PASSED')
            with self.assertRaises(RuleViolation):story.w.mergers['union'].approved()
            story.w.tick(story.w.now+30*86400)
            story.w=decode(encode(story.w))
        link(self,other.w,'merger/union','merger.confirm',id='union')
        link(other,self.w,'merger/union','merger.confirm',id='union')
        for index in (0,1):
            actor=f'a{index:03d}';key=f'{9000+index:064x}'
            self.w.execute(actor,'merger.lock',dict(id='union',destination_key=key,proof='fixture',nonce='exit'),'exit:'+actor,{'new_key':key})
            self.assertEqual(self.w.registry.get(actor).status,Status.EXITED)
        destination=name('source','a000');key=f'{9000:064x}'
        other.act('a149','wallet.transfer',to=destination,amount=11)
        link(other,self.w,'identity/a000','merger.claim',actor=destination,id='union',source='a000',key=key)
        self.assertEqual(other.w.registry.get(destination).roles,{Role.CITIZEN})
        self.assertFalse(other.w.registry.can(destination,'VOTE',other.w.now)[0])
        with self.assertRaises(RuleViolation):link(other,self.w,'identity/a000','merger.claim',actor=destination,id='union',source='a000',key=key)
        for story in (self,other):story.w.tick(manifest['expires'])
        tree=other.w.mergers['union'].claim_tree()
        source_record=self.w.exported_identities['a001'];proof=[[h.hex(),right] for h,right in tree.proof(source_record['index'])]
        link(self,other.w,'merger/union','merger.restore',actor='a001',id='union',status_proof=proof)
        self.assertEqual(self.w.registry.get('a001').roles,{Role.CITIZEN})
        claimed=self.w.exported_identities['a000'];badproof=[[h.hex(),right] for h,right in tree.proof(claimed['index'])]
        with self.assertRaises(RuleViolation):link(self,other.w,'merger/union','merger.restore',actor='a000',id='union',status_proof=badproof)
        self.w.assert_invariants();other.w.assert_invariants()
