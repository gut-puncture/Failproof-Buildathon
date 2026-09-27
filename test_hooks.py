"""Offline installer and exact-turn hook tests; no model or Jev calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('installer', ROOT / 'install_hook.py')
hook = load('stop_hook', ROOT / 'hooks/stop.py')
TOOLS = {'codex': '/mock/codex', 'codexVersion': 'codex-cli test', 'hooksEnabled': True,
         'node': sys.executable, 'nodeVersion': 'v22.22.0', 'testedCodexVersion': installer.TESTED_CODEX}


def advisory(feedback='Check this concern.'):
    return {'schemaVersion': 1, 'decision': 'advisory', 'results': [
        {'policyIndex': 0, 'id': 'example', 'version': 1, 'decision': 'advisory', 'reason': 'concern'}],
        'suggestions': [{'policyIndex': 0, 'id': 'example', 'version': 1,
                         'level': 'advisory', 'feedback': feedback}],
        'request': {'state': {'human_message': 'test', 'worker_response': 'test'}},
        'nativePolicy': {'verified': True, 'engineDecision': 'deny', 'decision': 'deny'}}


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / 'ordinary project'
        self.project.mkdir()
        self.args = argparse.Namespace(project=str(self.project), reviewer=None, codex=None, dry_run=False)
        self.tools = patch.object(installer, 'verify_tools', return_value=TOOLS)
        self.tools.start()
        self.addCleanup(self.tools.stop)

    def test_dry_run_and_idempotent_preservation(self):
        hooks_path = self.project / '.codex/hooks.json'
        hooks_path.parent.mkdir()
        original = {'description': 'Existing setup', 'extra': {'keep': 1}, 'hooks': {
            'Stop': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': 'echo existing', 'timeout': 3}]}],
            'SessionStart': [{'hooks': [{'type': 'command', 'command': 'echo session'}]}]}}
        hooks_path.write_text(json.dumps(original))
        self.args.dry_run = True
        report = installer.install(self.args)
        self.assertEqual(json.loads(hooks_path.read_text()), original)
        self.assertFalse((self.project / '.jev').exists())
        self.assertFalse(Path(report['reviewer']).exists())
        self.args.dry_run = False
        report = installer.install(self.args)
        installed = json.loads(hooks_path.read_text())
        self.assertEqual(installed['hooks']['Stop'][0], original['hooks']['Stop'][0])
        self.assertEqual(installed['hooks']['SessionStart'], original['hooks']['SessionStart'])
        self.assertEqual(installed['extra'], original['extra'])
        self.assertEqual(installed['description'], original['description'])
        self.assertEqual(list((self.project / '.jev/policies').iterdir()), [])
        self.assertEqual((self.project / '.jev/.gitignore').read_text(), 'runs/\nconfig.json\n')
        review = Path(report['reviewer'])
        self.assertFalse(review.is_relative_to(self.project))
        self.assertEqual(json.loads((review / '.jev-review.json').read_text())['project'], str(self.project))
        self.assertTrue((review / '.agents/skills/failure-to-check/SKILL.md').is_file())
        before = hooks_path.read_bytes()
        (self.project / '.jev/policies/user-policy.json').write_text('{"keep":true}')
        installer.install(self.args)
        self.assertEqual(hooks_path.read_bytes(), before)
        self.assertEqual((self.project / '.jev/policies/user-policy.json').read_text(), '{"keep":true}')
        self.assertEqual(len(installed['hooks']['UserPromptSubmit']), 1)
        self.assertEqual(len(installed['hooks']['Stop']), 2)
        for name in ('UserPromptSubmit', 'Stop'):
            parts = __import__('shlex').split(installed['hooks'][name][-1]['hooks'][0]['command'])
            self.assertEqual(parts[parts.index('--project') + 1], str(self.project))

    def test_preserves_other_commands_in_our_group(self):
        definition = installer.merge_hooks({}, self.project)
        extra = {'type': 'command', 'command': 'echo keep'}
        definition['hooks']['Stop'][0]['hooks'].append(extra)
        merged = installer.merge_hooks(definition, self.project)
        self.assertEqual(merged['hooks']['Stop'][0]['hooks'], [extra])
        self.assertEqual(sum(installer.owned_hook(item, self.project)
                             for group in merged['hooks']['Stop'] for item in group['hooks']), 1)

    def test_rejects_inside_or_symlinked_reviewer_and_state(self):
        self.args.reviewer = str(self.project / 'reviewer')
        with self.assertRaisesRegex(ValueError, 'outside'):
            installer.install(self.args)
        external = self.base / 'external'
        external.mkdir()
        reviewer_link = self.base / 'reviewer-link'
        reviewer_link.symlink_to(self.project, target_is_directory=True)
        self.args.reviewer = str(reviewer_link)
        with self.assertRaisesRegex(ValueError, 'outside'):
            installer.install(self.args)
        self.args.reviewer = str(external)
        (self.project / '.jev').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            installer.install(self.args)
        self.assertEqual(list(external.iterdir()), [])

    def test_invalid_existing_hooks_not_overwritten(self):
        location = self.project / '.codex/hooks.json'
        location.parent.mkdir()
        location.write_text('{bad json')
        with self.assertRaises(ValueError):
            installer.install(self.args)
        self.assertEqual(location.read_text(), '{bad json')
        self.assertFalse((self.project / '.jev').exists())

    def test_configuration_extras_and_custom_ignore_preserved(self):
        installer.install(self.args)
        location = self.project / '.jev/config.json'
        value = json.loads(location.read_text())
        value['customSetting'] = {'preserve': True}
        location.write_text(json.dumps(value))
        (self.project / '.jev/.gitignore').write_text('# personal\nother-file\n')
        installer.install(self.args)
        self.assertEqual(json.loads(location.read_text())['customSetting'], {'preserve': True})
        self.assertEqual((self.project / '.jev/.gitignore').read_text(), '# personal\nother-file\nruns/\nconfig.json\n')


class ToolVerificationTests(unittest.TestCase):
    def test_selection_checks_versions_and_hook_feature(self):
        args = argparse.Namespace(codex='/chosen/codex')
        with patch.object(installer, 'executable', side_effect=lambda value, _label: value), \
             patch.dict(os.environ, {'CODEX_BIN': '/wrong/codex', 'NODE_BIN': '/chosen/node'}), \
             patch.object(installer, 'probe', side_effect=['codex-cli 0.158.0-alpha.2.1', 'hooks stable true', 'v23.6.1']) as probe:
            result = installer.verify_tools(args, ROOT)
        self.assertEqual(result['codex'], '/chosen/codex')
        self.assertEqual(result['node'], '/chosen/node')
        self.assertEqual(probe.call_args_list[1].args[0], ['/chosen/codex', 'features', 'list'])

    def test_unsupported_codex_and_node_fail_without_fallback(self):
        args = argparse.Namespace(codex=None)
        with patch.object(installer, 'executable', side_effect=lambda value, _label: value), \
             patch.dict(os.environ, {'CODEX_BIN': '/selected/codex'}), \
             patch.object(installer, 'probe', side_effect=['codex-cli old', 'hooks stable false']) as probe:
            with self.assertRaisesRegex(ValueError, 'does not report enabled hooks'):
                installer.verify_tools(args, ROOT)
            self.assertEqual(probe.call_count, 2)
        with patch.object(installer, 'executable', side_effect=lambda value, _label: value), \
             patch.object(installer, 'probe', side_effect=['codex-cli new', 'hooks stable true', 'v20.19.5']):
            with self.assertRaisesRegex(ValueError, 'Node >=22.22.0'):
                installer.verify_tools(args, ROOT)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name).resolve()
        (self.project / '.jev/policies').mkdir(parents=True)
        self.config = {'schemaVersion': 1, 'project': str(self.project), 'runtime': str(ROOT), 'node': sys.executable}
        (self.project / '.jev/config.json').write_text(json.dumps(self.config))
        self.cwd_patch = patch.object(hook.Path, 'cwd', return_value=self.project)
        self.cwd_patch.start()
        self.addCleanup(self.cwd_patch.stop)

    def event(self, name='Stop', session='session', turn='turn', **extra):
        value = {'hook_event_name': name, 'session_id': session, 'turn_id': turn, 'cwd': str(self.project)}
        if name == 'Stop':
            value.update(stop_hook_active=False, last_assistant_message='Initial worker response')
        else:
            value['prompt'] = 'Human prompt'
        return {**value, **extra}

    def send(self, event):
        return hook.handle(self.project, event)

    def capture(self, **extra):
        event = self.event('UserPromptSubmit', **extra)
        self.assertEqual(self.send(event), {})
        return event

    def directory(self, event=None):
        return self.project / '.jev/runs' / hook.run_id(event or self.event())

    def report(self, event=None):
        return json.loads((self.directory(event) / 'report.json').read_text())

    def test_empty_collection_preserves_exact_initial_pair_without_runtime(self):
        prompt, answer = '  exact human\nΩ emoji: 🐕\n', '\n exact worker\t❤️  '
        self.capture(prompt=prompt)
        with patch.object(hook, 'evaluate', side_effect=AssertionError('No native call')), \
             patch.object(hook.subprocess, 'run', side_effect=AssertionError('No process')):
            self.assertEqual(self.send(self.event(last_assistant_message=answer)), {})
        self.assertEqual(json.loads((self.directory() / 'pair.json').read_text()),
                         {'human_message': prompt, 'worker_response': answer})
        self.assertEqual(self.report()['reason'], 'empty_policies')
        self.assertEqual(self.report()['request'], None)

    def test_immediate_active_exit_before_any_config_or_policy_read(self):
        self.capture()
        self.send(self.event())
        with patch.object(hook, 'load_context', side_effect=AssertionError('No config read')), \
             patch.object(hook, 'policy_snapshot', side_effect=AssertionError('No policy read')), \
             patch.object(hook, 'evaluate', side_effect=AssertionError('No evaluator')):
            self.assertEqual(self.send(self.event(stop_hook_active=True, last_assistant_message='Revised')), {})
        self.assertTrue((self.directory() / 'continuation-skipped.json').exists())
        self.assertEqual(json.loads((self.directory() / 'pair.json').read_text())['worker_response'], 'Initial worker response')
        (self.project / '.jev/config.json').unlink()
        self.assertEqual(self.send(self.event(stop_hook_active=True)), {})

    def test_strict_events_and_stop_boolean(self):
        for active in (None, 0, 1, 'false', 'true', [], {}):
            with self.subTest(active=active):
                self.assertEqual(self.send(self.event(stop_hook_active=active)), {})
        for extra in ({'session_id': ''}, {'turn_id': 4}, {'session_id': '  '}, {'turn_id': '\n'},
                      {'hook_event_name': 'stop'}, {'cwd': str(self.project.parent)}):
            self.assertEqual(self.send(self.event(**extra)), {})
        self.assertFalse((self.project / '.jev/runs').exists())

    def test_missing_turn_never_falls_back_to_previous_prompt(self):
        self.capture(turn='previous')
        with patch.object(hook, 'evaluate', side_effect=AssertionError('No fallback')):
            self.assertEqual(self.send(self.event(turn='new')), {})
        event = self.event(turn='new')
        self.assertEqual(json.loads((self.directory(event) / 'invalid-stop.json').read_text())['reason'],
                         'missing_turn_evidence')
        self.assertFalse((self.directory(event) / 'report.json').exists())
        self.assertFalse((self.directory(event) / 'pair.json').exists())

    def test_malformed_stop_does_not_consume_valid_turn(self):
        self.capture(prompt=' Exact human prompt\n')
        (self.project / '.jev/policies/example.json').write_text('{"id":"example"}')
        with patch.object(hook, 'evaluate', return_value=advisory()) as evaluate:
            self.assertEqual(self.send(self.event(last_assistant_message=None)), {})
            self.assertEqual(json.loads((self.directory() / 'invalid-stop.json').read_text())['reason'],
                             'missing_turn_evidence')
            self.assertFalse((self.directory() / 'report.json').exists())
            self.assertFalse((self.directory() / 'claim.json').exists())
            self.assertFalse((self.directory() / 'pair.json').exists())
            evaluate.assert_not_called()
            self.assertEqual(self.send(self.event(last_assistant_message=' Valid response\n'))['decision'], 'block')
            self.assertEqual(self.send(self.event()), {})
        evaluate.assert_called_once()
        self.assertTrue((self.directory() / 'claim.json').exists())
        self.assertEqual(json.loads((self.directory() / 'pair.json').read_text()),
                         {'human_message': ' Exact human prompt\n', 'worker_response': ' Valid response\n'})
        self.assertEqual(self.report()['decision'], 'advisory')

    def test_conflicting_prompt_keeps_first_but_checks_neither(self):
        event = self.capture(prompt='First genuine prompt')
        self.capture(prompt='Conflicting delivery')
        with patch.object(hook, 'evaluate', side_effect=AssertionError('Conflict is unchecked')):
            self.assertEqual(self.send(self.event()), {})
        self.assertEqual(json.loads((self.directory(event) / 'prompt.json').read_text())['human_message'], 'First genuine prompt')
        self.assertEqual(json.loads((self.directory() / 'invalid-stop.json').read_text())['reason'],
                         'conflicting_prompt_delivery')
        self.assertFalse((self.directory() / 'report.json').exists())
        self.assertFalse((self.directory() / 'pair.json').exists())

    def test_concurrent_duplicate_stop_and_prompt_replay_cannot_recheck(self):
        self.capture()
        (self.project / '.jev/policies/example.json').write_text('{"id":"example"}')
        result = advisory()
        result['suggestions'].append({'policyIndex': 1, 'id': 'second', 'version': 1,
                                      'level': 'tentative', 'feedback': 'Check the second concern.'})
        with patch.object(hook, 'evaluate', return_value=result) as evaluate:
            with ThreadPoolExecutor(max_workers=6) as workers:
                responses = list(workers.map(lambda _: self.send(self.event()), range(12)))
            self.capture()  # Duplicate UserPromptSubmit must not reset the Stop claim.
            self.assertEqual(self.send(self.event()), {})
        self.assertEqual(evaluate.call_count, 1)
        blocks = [value for value in responses if value.get('decision') == 'block']
        self.assertEqual(len(blocks), 1)
        self.assertIn('Check this concern.', blocks[0]['reason'])
        self.assertIn('Tentative concern: Check the second concern.', blocks[0]['reason'])
        self.assertIn('explain why', blocks[0]['reason'])

    def test_dynamic_sorted_policy_snapshot_and_invalid_sibling(self):
        collection = self.project / '.jev/policies'
        bad = b'{broken'
        good = b'{ "id": "good", "version": 2 }\n'
        (collection / 'z-good.json').write_bytes(good)
        (collection / 'a-invalid.json').write_bytes(bad)
        self.capture()
        with patch.object(hook, 'evaluate', return_value=advisory()) as evaluate:
            self.send(self.event())
        self.assertEqual(evaluate.call_args.args[-1], [None, {'id': 'good', 'version': 2}])
        files = self.report()['policyFiles']
        self.assertEqual([item['path'] for item in files], ['.jev/policies/a-invalid.json', '.jev/policies/z-good.json'])
        self.assertEqual(files[1]['sha256'], hashlib.sha256(good).hexdigest())
        self.assertEqual(__import__('base64').b64decode(files[1]['rawBase64']), good)
        (collection / 'z-good.json').write_text('{"id":"new"}')
        self.capture(turn='second')
        with patch.object(hook, 'evaluate', return_value=advisory()) as evaluate:
            self.send(self.event(turn='second'))
        self.assertEqual(evaluate.call_args.args[-1][1], {'id': 'new'})

    def test_oversized_and_symlinked_policy_become_null_without_reading_target(self):
        collection = self.project / '.jev/policies'
        (collection / 'large.json').write_bytes(b'x' * (hook.MAX_POLICY_BYTES + 1))
        (collection / 'link.json').symlink_to(self.project / '.jev/config.json')
        policies, records = hook.policy_snapshot(self.project)
        self.assertEqual(policies, [None, None])
        self.assertEqual(records[0]['parseError'], 'oversized_policy_json')
        self.assertTrue(all(item['rawBase64'] is None for item in records))

    def test_sessions_and_turns_remain_isolated(self):
        events = [self.event(session='chat-a', turn='same'), self.event(session='chat-b', turn='same'),
                  self.event(session='chat-a', turn='next')]
        for index, event in enumerate(events):
            self.capture(session=event['session_id'], turn=event['turn_id'], prompt=f'prompt {index}')
        for index, event in reversed(list(enumerate(events))):
            self.send({**event, 'last_assistant_message': f'answer {index}'})
            self.assertEqual(json.loads((self.directory(event) / 'pair.json').read_text()),
                             {'human_message': f'prompt {index}', 'worker_response': f'answer {index}'})
        self.assertEqual(len({self.directory(event) for event in events}), 3)

    def test_unsafe_state_and_cwd_rejected(self):
        outside = self.project / 'outside-placeholder'
        outside.mkdir()
        (self.project / '.jev/runs').symlink_to(outside, target_is_directory=True)
        self.capture()
        self.assertEqual(list(outside.iterdir()), [])
        (self.project / '.jev/runs').unlink()
        with patch.object(hook.Path, 'cwd', return_value=self.project.parent):
            self.assertEqual(self.send(self.event('UserPromptSubmit')), {})
        self.assertFalse((self.project / '.jev/runs').exists())

    def test_runtime_failure_is_quiet_and_durable(self):
        self.capture()
        (self.project / '.jev/policies/example.json').write_text('{}')
        with patch.object(hook, 'evaluate', side_effect=subprocess.TimeoutExpired('native', 15)) as evaluate:
            self.assertEqual(self.send(self.event()), {})
            self.assertEqual(self.send(self.event()), {})
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(self.report()['decision'], 'unchecked')
        self.assertEqual(self.report()['reason'], 'native_runtime_unavailable')

    def test_real_hook_process_empty_and_active_smoke(self):
        for event in [self.event('UserPromptSubmit'), self.event(), self.event(stop_hook_active=True)]:
            result = subprocess.run([sys.executable, str(ROOT / 'hooks/stop.py'), '--project', str(self.project)],
                                    cwd=self.project, input=json.dumps(event), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
        self.assertTrue((self.directory() / 'pair.json').exists())
        self.assertTrue((self.directory() / 'continuation-skipped.json').exists())

    def test_native_process_contract_and_unverified_advice_rejected(self):
        fake = self.project / 'fake-runtime/native'
        fake.mkdir(parents=True)
        # Python acts as the selected executable for a local gate fixture, never Jev.
        gate = fake / 'gate.mjs'
        gate.write_text('import json, pathlib, sys\n'
                        'data=json.loads(pathlib.Path(sys.argv[1]).read_text())\n'
                        'out=' + repr(advisory()) + '\n'
                        'out["request"]={"state":data["pair"]}\n'
                        'pathlib.Path(sys.argv[2]).write_text(json.dumps(out))\n')
        config = {**self.config, 'runtime': str(fake.parent)}
        self.capture()
        pair = {'human_message': ' Human\n', 'worker_response': '\nWorker '}
        outcome = hook.evaluate(config, self.directory(), pair, [None, {'id': 'fixture'}])
        self.assertEqual(outcome['request']['state'], pair)
        self.assertEqual(json.loads((self.directory() / 'input.json').read_text()),
                         {'pair': pair, 'policies': [None, {'id': 'fixture'}]})
        (self.directory() / 'gate-output.json').unlink()
        gate.write_text(gate.read_text().replace("'verified': True", "'verified': False"))
        with self.assertRaisesRegex(ValueError, 'Unverified native advisory'):
            hook.evaluate(config, self.directory(), pair, [])


if __name__ == '__main__':
    unittest.main()
