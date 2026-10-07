import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
class StarterBoundary(unittest.TestCase):
    def attempt(self,config,output_exists=False):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'config.json').write_text(json.dumps(config))
            output=path/'output'
            if output_exists:
                output.mkdir();(output/'evidence').write_text('preserve')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/start_society.py'),
                '--config',str(path/'config.json'),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertNotIn('Running ',result.stdout)
            if output_exists:self.assertEqual((output/'evidence').read_text(),'preserve')
            else:self.assertFalse(output.exists())
    def test_bad_configuration_cannot_start_or_write(self):
        config=json.loads((ROOT/'starter/society.json').read_text())
        for changes in ({'citizens':True},{'citizens':199},{'seeds':[7,7]},
                        {'seeds':[False]},{'modes':[{}]},{'modes':['WEIGHTED','WEIGHTED']},
                        {'arbitrary_command':'unsafe'}):
            with self.subTest(changes=changes):self.attempt(config|changes)
    def test_existing_evidence_cannot_be_overwritten(self):
        self.attempt(json.loads((ROOT/'starter/society.json').read_text()),True)
