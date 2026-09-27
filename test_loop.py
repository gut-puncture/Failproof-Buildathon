import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('loop', Path(__file__).with_name('loop.py'))
loop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loop)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / 'task.txt').write_text('Implement an identity function.')
        (self.base / 'candidate.py').write_text('def identity(x): return x\n')
        (self.base / 'secret.txt').write_text('must not be collected')

    def args(self, *extra):
        return loop.parser().parse_args(['check', '--task', str(self.base / 'task.txt'),
            '--code', str(self.base / 'candidate.py'), '--out', str(self.base / 'run'), *extra])

    def test_no_checks_and_ambiguous_results_are_unchecked(self):
        self.assertEqual(loop.aggregate([]), 'unchecked')
        self.assertEqual(loop.aggregate([{'decision': 'unchecked'}, {'decision': 'no_violation_detected'}]), 'unchecked')
        self.assertEqual(loop.aggregate([{'decision': 'unexpected'}]), 'unchecked')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(loop.subprocess, 'run', side_effect=AssertionError('no process')):
            report = loop.run(self.args())
        self.assertEqual(report['decision'], 'unchecked')
        self.assertEqual(report['reason'], 'no_checks')

    def test_explicit_context_only(self):
        state = loop.state_from_files(self.base / 'task.txt', self.base / 'candidate.py', [])
        self.assertNotIn('must not be collected', json.dumps(state))
        self.assertEqual(state['implementation'], 'def identity(x): return x\n')

    def test_offline_check_cannot_launch_process(self):
        check = self.base / 'check.json'
        check.write_text('{"id":"example"}')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(loop.subprocess, 'run', side_effect=AssertionError('offline process')):
            report = loop.run(self.args('--check', str(check)))
        self.assertEqual(report['results'][0]['reason'], 'live_not_requested')

    def test_offline_replay_labels_saved_evidence(self):
        record = self.base / 'record.json'
        record.write_text('{"decision":"no_violation_detected"}')
        args = loop.parser().parse_args(['replay', '--record', str(record), '--out', str(self.base / 'replay')])
        with contextlib.redirect_stdout(io.StringIO()), patch.object(loop.subprocess, 'run', side_effect=AssertionError('offline process')):
            report = loop.run(args)
        self.assertEqual(report['decision'], 'unchecked')
        self.assertEqual(report['saved']['decision'], 'no_violation_detected')

    def test_missing_runtime_fails_closed(self):
        with patch.object(loop, 'find_binary', side_effect=RuntimeError('missing')):
            result = loop.inspect({}, {}, self.base / 'guard', 'paired', True)
        self.assertEqual(result['decision'], 'unchecked')

    def test_correction_requires_explicit_live_and_preserves_original(self):
        with self.assertRaises(ValueError):
            loop.run(self.args('--correct'))
        self.assertEqual((self.base / 'candidate.py').read_text(), 'def identity(x): return x\n')

    def test_empty_fixture_set_is_unchecked(self):
        (self.base / 'fixtures.json').write_text('{"fixtures":[]}')
        (self.base / 'check.json').write_text('{}')
        args = loop.parser().parse_args(['eval', '--check', str(self.base / 'check.json'), '--fixtures',
            str(self.base / 'fixtures.json'), '--out', str(self.base / 'evaluation')])
        with contextlib.redirect_stdout(io.StringIO()):
            report = loop.run(args)
        self.assertEqual(report['decision'], 'unchecked')

    def test_one_correction_uses_isolated_copy_and_rechecks(self):
        check = self.base / 'check.json'
        check.write_text('{"id":"example","feedback":"Preserve the input value."}')
        args = self.args('--check', str(check), '--live', '--correct')
        calls = []

        def worker(command, **kwargs):
            calls.append(command)
            workspace = Path(kwargs['cwd'])
            self.assertEqual(workspace, (self.base / 'run/correction').resolve())
            self.assertNotIn('FAILPROOF_API_KEY', kwargs['env'])
            (workspace / 'candidate.py').write_text('def identity(x): return x  # corrected\n')
            return argparse.Namespace(returncode=0, stdout='', stderr='')

        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(loop, 'inspect', side_effect=[{'decision':'violation_detected'}, {'decision':'no_violation_detected'}]), \
             patch.object(loop, 'find_binary', return_value='/mock/codex'), \
             patch.object(loop.subprocess, 'run', side_effect=worker):
            report = loop.run(args)
        self.assertEqual(len(calls), 1)
        self.assertIn('--ignore-user-config', calls[0])
        self.assertIn('gpt-5.6-luna', calls[0])
        self.assertEqual(report['correction']['decision'], 'no_violation_detected')
        self.assertEqual(report['correction']['outcome'], 'needs_review')
        self.assertEqual((self.base / 'candidate.py').read_text(), 'def identity(x): return x\n')

    def test_explicit_test_receives_candidate_path_and_logs_failure(self):
        suite = self.base / 'test_candidate.py'
        suite.write_text('import sys\nfrom pathlib import Path\nprint(Path(sys.argv[1]).name)\nsys.exit(3)\n')
        records = loop.run_tests([str(suite)], self.base / 'candidate.py', self.base)
        self.assertEqual(records[0]['exitCode'], 3)
        self.assertEqual(records[0]['status'], 'failed')
        self.assertEqual((self.base / 'test-0.stdout.log').read_text().strip(), 'candidate.py')

    def test_fresh_generation_is_explicit_and_remains_unchecked(self):
        args = loop.parser().parse_args(['generate', '--task', str(self.base / 'task.txt'),
                                       '--out', str(self.base / 'generated')])
        def worker(command, **kwargs):
            self.assertIn('gpt-5.6-luna', command)
            self.assertIn('Implement an identity function.', kwargs['input'])
            self.assertNotIn('must not be collected', kwargs['input'])
            (Path(kwargs['cwd']) / 'candidate.mjs').write_text('export const identity = x => x;')
            return argparse.Namespace(returncode=0, stdout='', stderr='')
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(loop, 'find_binary', return_value='/mock/codex'), \
             patch.object(loop.subprocess, 'run', side_effect=worker):
            report = loop.run(args)
        self.assertEqual(report['decision'], 'unchecked')
        self.assertTrue(Path(report['candidate']).is_file())

    def test_correction_success_requires_passing_tests(self):
        args = self.args('--live', '--correct', '--test', str(self.base / 'suite.py'))
        out = self.base / 'gating'
        out.mkdir()
        (out / 'test-0.stdout.log').write_text('observed failure\n' + 'X' * 20000)
        state = loop.state_from_files(args.task, args.code, [])
        with patch.object(loop, 'find_binary', return_value='/mock/codex'), \
             patch.object(loop.subprocess, 'run', return_value=argparse.Namespace(returncode=0, stdout='', stderr='')) as worker, \
             patch.object(loop, 'inspect', return_value={'decision': 'no_violation_detected'}), \
             patch.object(loop, 'run_tests', return_value=[{'exitCode':0}]):
            report = loop.correct_once(args, [{'feedback':'Preserve input.'}], state,
                                       [{'decision':'violation_detected'}], out)
        self.assertEqual(report['outcome'], 'repair_verified_for_supplied_tests')
        prompt = worker.call_args.kwargs['input']
        self.assertIn('observed failure', prompt)
        self.assertIn('TEST EVIDENCE', prompt)
        self.assertLessEqual(prompt.count('X'), 16000)
        self.assertNotIn('X' * 16001, prompt)

    def test_native_policy_denial_and_missing_proof_cannot_clear_candidate(self):
        cases = [
            ({'decision':'no_violation_detected', 'nativePolicy':{'engine':'failproofai','decision':'allow'}}, 'no_violation_detected'),
            ({'decision':'no_violation_detected', 'nativePolicy':{'engine':'failproofai','decision':'deny'}}, 'unchecked'),
            ({'decision':'violation_detected', 'nativePolicy':{'engine':'failproofai','decision':'deny'}}, 'violation_detected'),
            ({'decision':'no_violation_detected'}, 'unchecked'),
            ({'decision':'no_violation_detected', 'nativePolicy':{'engine':'failproofai','decision':'unchecked'}}, 'unchecked'),
        ]
        for i, (response, expected) in enumerate(cases):
            with self.subTest(i=i):
                def gate(command, **kwargs):
                    self.assertTrue(command[1].endswith('native/gate.mjs'))
                    Path(command[4]).write_text(json.dumps(response))
                    return argparse.Namespace(returncode=0, stdout='', stderr='')
                with patch.object(loop, 'find_binary', return_value='/mock/node'), \
                     patch.object(loop.subprocess, 'run', side_effect=gate):
                    result = loop.inspect({}, {}, self.base / f'native-{i}', 'paired', True, True)
                self.assertEqual(result['decision'], expected)

    def test_worker_isolation_and_partial_timeout_logs(self):
        with patch.object(loop, 'find_binary', return_value='/mock/codex'):
            command = loop.worker_command()
        for feature in ['memories', 'apps', 'plugins', 'multi_agent', 'hooks', 'browser_use', 'computer_use']:
            self.assertEqual(command[command.index(feature) - 1], '--disable')
        args = loop.parser().parse_args(['generate', '--task', str(self.base / 'task.txt'), '--out', str(self.base / 'timed')])
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(loop.os.environ, {'FAILPROOF_API_KEY':'mock-secret-123'}), \
             patch.object(loop, 'find_binary', return_value='/mock/codex'), \
             patch.object(loop.subprocess, 'run', side_effect=loop.subprocess.TimeoutExpired('codex', 240, output=b'partial mock-secret-123', stderr=b'timeout')):
            report = loop.run(args)
        self.assertEqual(report['decision'], 'unchecked')
        self.assertEqual((self.base / 'timed/generation/worker.stdout.log').read_text(), 'partial [REDACTED]')


if __name__ == '__main__':
    unittest.main()
