import base64
import copy
import hashlib
import unittest
from dagp_native.engine import World
from dagp_native.codec import encode,decode,canonical
from dagp_native.bootstrap import electorate,readiness
from dagp_ref.roles import Role,Status
from dagp_ref.treasury import RuleViolation

NOW=1800000000
def fixture():
    b=dict(public_key='',genesis_time=NOW,period=1,scheme='bootstrap-disabled')
    c=dict(identities={'founder':dict(operator='founder-op',family='family0',citizen_since=NOW,roles=['CITIZEN','ADMIN','REGISTRAR'])},
        common_budget=100000,balances={'founder':200},beacon=b,root='root',constraints=[],
        bootstrap=dict(founder='founder',validator_key='2'*64,budget=6000,expires=NOW+365*86400))
    return World('seed-test',NOW,c,{'founder':'1'*64})

class BootstrapTests(unittest.TestCase):
    def setUp(self):self.w=fixture();self.sequence=0
    def act(self,actor,operation,args,verified=None):
        self.sequence+=1
        # Model the host's atomic write set; refused attempts discard all changes.
        pending=decode(encode(self.w))
        result=pending.execute(actor,operation,args,str(self.sequence),verified or {})
        self.w=pending;return result
    def approve(self,cid):
        roster=self.w.bootstrap['proposals'][cid]['roster'];count=(2*len(roster)+2)//3
        for actor in roster[:count]:self.act(actor,'bootstrap.vote',{'case':cid})
        return self.act(roster[0],'bootstrap.apply',{'case':cid})
    def invite(self,name,operator=None):
        key=hashlib.sha256(name.encode()).hexdigest()
        request=dict(chain_id=self.w.chain,account=name,operator=operator or name+'-op',family='family'+str(len(self.w.registry.ids)%5),key=base64.b64encode(bytes.fromhex(key)).decode(),signature='host-fixture')
        cid=self.act('founder','bootstrap.propose',dict(action='INVITE',payload={'join':request}),{'join_key':key})['case']
        self.approve(cid);return request,key
    def join(self,name,operator=None):
        request,key=self.invite(name,operator)
        challenge=self.act(name,'identity.challenge',{'key':key},{'registration_key':key})
        self.w.tick(self.w.now+1)
        result=self.act(name,'identity.register',dict(operator=request['operator'],family=request['family'],key=key,challenge=challenge['challenge']))
        self.approve(result['case']);return name
    def test_one_founder_truthful_genesis_and_recruitment(self):
        self.assertEqual(self.w.registry.get('founder').activated,NOW)
        self.assertFalse(self.w.registry.can('founder','ADMIN_VOTE',NOW)[0])
        self.assertEqual(electorate(self.w),('founder',))
        before=self.w.treasury.free;self.join('alice')
        self.assertEqual(self.w.registry.get('alice').status,Status.ACTIVE)
        self.assertEqual(self.w.treasury.free,before-10)
        self.assertFalse(self.w.registry.can('alice','VOTE',self.w.now)[0])
        self.assertEqual(self.w.bootstrap['spent'],11)
        self.assertEqual(self.w.registry.get('alice').bond,10)
        self.w.tick(self.w.now+3*86400)
        self.assertTrue(self.w.registry.can('alice','VOTE',self.w.now)[0])
        self.assertEqual(len(electorate(self.w)),2)
        self.w.assert_invariants()
    def test_founder_loses_exclusive_admission_as_members_mature(self):
        self.join('alice');self.join('bob');self.w.tick(self.w.now+3*86400)
        request,key=self.invite_request('carol')
        cid=self.act('founder','bootstrap.propose',dict(action='INVITE',payload={'join':request}),{'join_key':key})['case']
        self.act('founder','bootstrap.vote',{'case':cid})
        before=canonical(encode(self.w))
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.apply',{'case':cid})
        self.assertEqual(before,canonical(encode(self.w)))
        self.act('alice','bootstrap.vote',{'case':cid});self.act('bob','bootstrap.apply',{'case':cid})
        self.assertIn('carol',self.w.bootstrap['invites'])
    def invite_request(self,name):
        key=hashlib.sha256(name.encode()).hexdigest()
        return dict(chain_id=self.w.chain,account=name,operator=name+'-op',family='family4',key=base64.b64encode(bytes.fromhex(key)).decode(),signature='fixture'),key
    def test_frozen_denominator_operator_dedup_and_duplicate_approval(self):
        self.join('alice');self.join('shadow',operator='founder-op');self.w.tick(self.w.now+3*86400)
        self.assertEqual(len(electorate(self.w)),2)
        request,key=self.invite_request('bob')
        cid=self.act('founder','bootstrap.propose',dict(action='INVITE',payload={'join':request}),{'join_key':key})['case']
        roster=self.w.bootstrap['proposals'][cid]['roster']
        self.act(roster[0],'bootstrap.vote',{'case':cid})
        with self.assertRaises(RuleViolation):self.act(roster[0],'bootstrap.vote',{'case':cid})
        self.assertEqual(self.w.bootstrap['proposals'][cid]['roster'],roster)
    def test_seed_allowlist_and_lifetime_budget(self):
        for op in ('proposal.prepare','admin.open','treasury.pause','merger.snapshot','beacon.publish'):
            with self.assertRaises(RuleViolation):self.act('founder',op,{})
        for action in ('BAN','TRANSFER','SET_PARAMS','RESET_BOOTSTRAP'):
            with self.assertRaises(RuleViolation):self.act('founder','bootstrap.propose',dict(action=action,payload={}))
        for index in range(5):self.invite('invited'+str(index))
        with self.assertRaises(RuleViolation):self.invite('sixth')
        self.w.tick(self.w.bootstrap['expires'])
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.propose',dict(action='ROLE',payload={'target':'founder','role':'EXAMINER'}))
    def test_candidate_consent_tenure_and_delayed_office(self):
        self.join('alice');self.w.tick(self.w.now+30*86400)
        cid=self.act('founder','bootstrap.propose',dict(action='ROLE',payload={'target':'alice','role':'ADMIN'}))['case']
        for actor in self.w.bootstrap['proposals'][cid]['roster']:self.act(actor,'bootstrap.vote',{'case':cid})
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.apply',{'case':cid})
        self.act('alice','bootstrap.consent',{'case':cid});self.act('founder','bootstrap.apply',{'case':cid})
        self.assertFalse(self.w.registry.can('alice','ADMIN_VOTE',self.w.now)[0])
        self.w.tick(self.w.now+2*86400)
        self.assertTrue(self.w.registry.can('alice','ADMIN_VOTE',self.w.now)[0])
    def test_no_uninvited_registration_or_relabeling(self):
        request,key=self.invite('alice')
        before=canonical(encode(self.w))
        with self.assertRaises(RuleViolation):self.act('alice','identity.challenge',{'key':'f'*64},{'registration_key':'f'*64})
        self.assertEqual(before,canonical(encode(self.w)))
        challenge=self.act('alice','identity.challenge',{'key':key},{'registration_key':key});self.w.tick(self.w.now+1)
        with self.assertRaises(RuleViolation):self.act('alice','identity.register',dict(operator='attacker',family=request['family'],key=key,challenge=challenge['challenge']))
        self.assertNotIn('alice',self.w.registry.ids)
    def test_graduation_refuses_small_or_understaffed_society(self):
        self.assertEqual(readiness(self.w)['missing']['citizens'],149)
        beacon=dict(public_key='3'*96,genesis_time=NOW,period=3,scheme='pedersen-bls-unchained')
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.propose',dict(action='GRADUATE',payload={'beacon':beacon}),{'beacon_configuration':'verified'})
    def test_successful_graduation_is_irreversible_and_preserves_ordinary_rules(self):
        # An explicitly mature population fixture tests transition logic, not
        # elapsed wall time or recruitment of 150 independently owned agents.
        from test_engine import charter
        self.w=World('seed-test',NOW,charter(),{f'a{i:03d}':f'{i:064x}' for i in range(150)})
        self.w.bootstrap=dict(founder='a000',created=NOW-40*86400,expires=NOW+365*86400,budget=6000,spent=0,
                              phase='SEED',proposals={},invites={},validators={})
        for i in range(7):
            agent=f'a{i:03d}';key=f'{1000+i:064x}'
            self.w.bootstrap['validators'][key]=dict(agent=agent,operator=f'op{i}')
            self.w.registry.get(agent).roles.add(Role.VALIDATOR)
        self.w.registry.validators=[f'a{i:03d}' for i in range(7)]
        self.assertEqual(readiness(self.w)['missing'],{})
        beacon=dict(public_key='3'*96,genesis_time=NOW,period=3,scheme='pedersen-bls-unchained')
        cid=self.act('a000','bootstrap.propose',dict(action='GRADUATE',payload={'beacon':beacon}),{'beacon_configuration':'verified'})['case']
        for index,actor in enumerate(self.w.bootstrap['proposals'][cid]['roster'][:100]):
            self.w.execute(actor,'bootstrap.vote',{'case':cid},'approval'+str(index),{})
        validators=list(self.w.registry.validators)
        self.w.registry.validators.pop()
        with self.assertRaises(RuleViolation):self.act('a000','bootstrap.apply',{'case':cid})
        self.w.registry.validators=validators
        self.act('a000','bootstrap.apply',{'case':cid})
        self.assertEqual(self.w.bootstrap['phase'],'GOVERNANCE')
        self.assertEqual(self.w.beacon,beacon)
        self.assertEqual(self.w.params.exam_panel,5)
        self.assertEqual(self.w.params.quorum_bps,2000)
        self.assertEqual(self.w.params.constitutional_quorum_bps,5000)
        self.w.assert_invariants()
        with self.assertRaises(RuleViolation):self.act('a000','bootstrap.propose',dict(action='ROLE',payload={'target':'a149','role':'ADMIN'}))
    def test_shared_operator_proposal_quota_and_expired_invitation_cleanup(self):
        self.join('alice')
        for index in range(4):
            self.act('founder','bootstrap.propose',dict(action='ROLE',payload={'target':'alice','role':'JUROR'}))
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.propose',dict(action='ROLE',payload={'target':'alice','role':'JUROR'}))
        self.w.tick(self.w.now+8*86400)
        self.w.bootstrap['invites']={str(i):dict(key=f'{i:064x}',expires=self.w.now-1) for i in range(32)}
        self.invite('bob')
        self.assertEqual(set(self.w.bootstrap['invites']),{'bob'})
    def test_fixed_budget_exhaustion_is_atomic(self):
        self.w.bootstrap['budget']=11
        self.invite('alice')
        request,key=self.invite_request('bob')
        cid=self.act('founder','bootstrap.propose',dict(action='INVITE',payload={'join':request}),{'join_key':key})['case']
        self.act('founder','bootstrap.vote',{'case':cid})
        before=canonical(encode(self.w))
        with self.assertRaises(RuleViolation):self.act('founder','bootstrap.apply',{'case':cid})
        self.assertEqual(before,canonical(encode(self.w)))
        self.assertNotIn('bob',self.w.wallets)
