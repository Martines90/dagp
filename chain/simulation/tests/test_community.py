import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from community import Community
from community import MODULE, Role
from verify import verify

class CommunityStory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report,cls.events=Community(citizens=200,seed=7).run()
    def test_complete_institutional_lifecycle(self):
        r=self.report
        self.assertEqual(len(r['elections']),2)
        self.assertEqual(r['elections'][0]['credits']['Frontier'],0)
        by_title={s['title']:s for s in r['sessions'] if 'title' in s}
        self.assertEqual(by_title['Shared research library']['project_state'],'CLOSED_SUCCESS')
        self.assertEqual(by_title['Unbounded speculative compute']['outcome'],'FAILED')
        self.assertEqual(by_title['Optional archive migration']['outcome'],'NO_QUORUM')
        self.assertEqual(by_title['Undefined collective mission']['outcome'],'VOIDED')
        self.assertEqual(by_title['Storage availability dispute']['outcome'],'VOIDED')
        self.assertEqual(by_title['Faulty compute procurement']['project_state'],'CLOSED_FAILURE')
        self.assertEqual(by_title['Examiner cartel incident']['targeted_fraud_struck'],1)
        self.assertTrue(by_title['Silent certification board']['board_default'])
        point=by_title['Five-clause public infrastructure']
        self.assertEqual(point['outcome'],'PARTIAL')
        self.assertEqual(r['treasury']['released'][point['issue']],1800)
        self.assertEqual(r['model_parameters']['credit_step_bps'],400)
        events=[json.loads(line) for line in self.events.splitlines()]
        self.assertEqual([e['data']['month'] for e in events if e['kind']=='monthly-credit-reset'],[[2026,1],[2026,2],[2026,3]])
        self.assertEqual(r['treasury']['conserved_total'],100000)
        self.assertFalse(r['treasury']['reserved'])
    def test_reproducibility(self):
        report,events=Community(citizens=200,seed=7).run()
        self.assertEqual(report,self.report)
        self.assertEqual(events,self.events)
    def test_reference_rules_really_exclude_conflicts(self):
        events=[json.loads(line) for line in self.events.splitlines()]
        checks=[e['data']['check'] for e in events if e['kind']=='refused']
        self.assertTrue(any(c.startswith('proposer recusal') for c in checks))
        self.assertTrue(any(c.startswith('certification board cannot vote') for c in checks))
        self.assertIn('revoked token cannot vote',checks)
        self.assertIn('operator population cap blocks excess identities',checks)
        self.assertTrue(any(c.startswith('unattested release blocked') for c in checks))
        self.assertTrue(any(e['kind']=='elected-administrator' for e in events))
    def test_seed_changes_population_behavior(self):
        r,_=Community(citizens=200,seed=19).run()
        self.assertNotEqual(r['event_head'],self.report['event_head'])
    def test_executor_exclusion_even_with_verifier_role(self):
        c=Community(citizens=200);c.bootstrap();executor=c.leaders[0]
        c.reg.grant(MODULE,executor,Role.VERIFIER,c.height,stake=50)
        self.assertTrue(c.reg.can(executor,'VERIFY',c.height)[0])
        self.assertFalse(c.reg.can(executor,'VERIFY',c.height,{'executors':{executor}})[0])
    def export(self,directory):
        report=json.dumps({'runs':[self.report]}).encode()
        (directory/'report.json').write_bytes(report)
        (directory/'manifest.json').write_text(json.dumps(dict(report_sha256=hashlib.sha256(report).hexdigest(),
            runs=[{k:self.report[k] for k in ('seed','mode','events_sha256','event_head')}])) )
        (directory/'events-7-WEIGHTED.jsonl').write_bytes(self.events)
    def test_export_verification_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);self.export(directory)
            self.assertEqual(verify(directory),self.report['event_count'])
            event_path=directory/'events-7-WEIGHTED.jsonl'
            event_path.write_bytes(self.events.replace(b'community-founded',b'community-altered',1))
            with self.assertRaisesRegex(ValueError,'event file hash mismatch'):verify(directory)
            self.export(directory)
            report_path=directory/'report.json';report_path.write_bytes(report_path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'report hash mismatch'):verify(directory)

if __name__=='__main__':unittest.main()
