import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

installer = load('installer', ROOT / 'install_hook.py')
hook = load('stop_hook', ROOT / 'hooks/stop.py')

class HookTests(unittest.TestCase):
    def test_install_dry_run_refusal_and_stop_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project/'TASK.md').write_text('Preserve values.')
            (project/'candidate.mjs').write_text('export const x = 1;')
            (project/'check.json').write_text('{"feedback":"Preserve values."}')
            args = argparse.Namespace(project=tmp,task=str(project/'TASK.md'),code=str(project/'candidate.mjs'),check=str(project/'check.json'),dry_run=True)
            installer.install(args)
            self.assertFalse((project/'.codex').exists())
            args.dry_run=False
            installed=installer.install(args)
            config=installed['contextFile']
            with self.assertRaises(ValueError):
                installer.install(args)
            with patch.object(hook.loop,'inspect',return_value={'decision':'violation_detected','nativePolicy':{'engine':'failproofai','decision':'deny'}}):
                result=hook.handle(config,{'session_id':'test','turn_id':'one','last_assistant_message':'Done'})
                self.assertEqual(result['decision'],'block')
                self.assertNotIn('decision',hook.handle(config,{'session_id':'test','turn_id':'one'}))
            with patch.object(hook.loop,'inspect',side_effect=AssertionError('active hook must not call native')):
                self.assertNotIn('decision',hook.handle(config,{'stop_hook_active':True}))
            with patch.object(hook.loop,'inspect',return_value={'decision':'unchecked','reason':'native_policy_unavailable'}):
                self.assertIn('unchecked',hook.handle(config,{'turn_id':'two'})['systemMessage'])
            with patch.object(hook.loop,'inspect',return_value={'decision':'no_violation_detected','nativePolicy':{'engine':'failproofai','decision':'allow'}}):
                self.assertEqual(hook.handle(config,{'turn_id':'three'}),{})
            smoke=subprocess.run([sys.executable,str(ROOT/'hooks/stop.py'),'--config',config],input='{"stop_hook_active":true,"last_assistant_message":"done"}',capture_output=True,text=True)
            self.assertEqual(smoke.returncode,0)
            self.assertNotIn('decision',json.loads(smoke.stdout))
            self.assertTrue(list((project/'.jev-check/runs').glob('*/report.json')))

if __name__ == '__main__':
    unittest.main()
