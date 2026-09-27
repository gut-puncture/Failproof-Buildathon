"""Reviewer workflow tests. Native inference is mocked; policy validation is real."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import learn

RUNTIME = Path(__file__).resolve().parent
REAL_RUN = subprocess.run


def question(text):
    return {'instructions': text, 'criteria': {'true': 'The stated condition holds.',
                                             'false': 'The stated condition does not hold.'}}


class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.worker, self.reviewer = self.base / 'worker', self.base / 'reviewer'
        for path in (self.worker / '.jev/runs', self.worker / '.jev/policies', self.reviewer):
            path.mkdir(parents=True)
        self.node = Path(os.environ.get('NODE_BIN') or shutil.which('node') or '/missing-node').resolve()
        config = {'schemaVersion': 1, 'project': str(self.worker), 'runtime': str(RUNTIME), 'node': str(self.node)}
        learn.write_json(self.reviewer / '.jev-review.json', config)
        learn.write_json(self.worker / '.jev/config.json', config)
        self.old_cwd = Path.cwd()
        os.chdir(self.reviewer)
        self.addCleanup(os.chdir, self.old_cwd)
        self.ctx = learn.context()
        self.policy = {'schemaVersion': 1, 'id': 'preserve-source', 'version': 1,
                       'principle': 'Respect the requested source constraints.',
                       'applicability': question('Does human_message ask for a faithful source summary?'),
                       'evidenceSufficiency': question('Does human_message contain the source to compare with worker_response?'),
                       'questions': [question('Does worker_response contradict that source about the same subject?')],
                       'feedback': 'Check the possible contradiction. Jev may be mistaken; correct it if supported or explain why it is valid.'}
        self.policy_file = self.reviewer / 'candidate.json'
        learn.write_json(self.policy_file, self.policy)
        self.inputs = []

    def require_validator(self):
        self.assertTrue(self.node.is_file(), 'Node is required for the actual shared validator')
        self.assertTrue((RUNTIME / 'runtime/policy.mjs').is_file(), 'Shared validator must be implemented')

    def make_run(self, turn='turn-a', pair=None, complete=True):
        ids = ['session-a', turn]
        run_id = hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()
        folder = self.worker / '.jev/runs' / run_id
        folder.mkdir()
        pair = pair or {'human_message': 'Source: undecided. Summarize it.\n', 'worker_response': 'It is settled.\n'}
        learn.write_json(folder / 'pair.json', pair)
        if complete:
            learn.write_json(folder / 'report.json', {'schemaVersion': 1, 'session_id': ids[0], 'turn_id': ids[1],
                         'completedAt': '2026-09-27T12:00:00Z', 'evidenceScope': 'initial_response_before_advice',
                         'decision': 'advisory', 'diagnosis': 'Must not be exported as runtime evidence'})
        return run_id, pair

    def fake_native(self, command, **kwargs):
        if command[1].endswith('runtime/policy.mjs'):
            return REAL_RUN(command, **kwargs)
        self.assertTrue(command[1].endswith('native/gate.mjs'))
        self.assertEqual(kwargs['cwd'], self.reviewer)
        payload = learn.read_json(command[2])
        self.inputs.append(payload)
        policy = payload['policies'][0]
        # Deliberately a missed concern: activation must not impose perfect accuracy.
        result = {'schemaVersion': 1, 'decision': 'quiet', 'suggestions': [],
                  'request': {'state': payload['pair'], 'questions': {}},
                  'nativePolicy': {'verified': True, 'engineDecision': 'allow'},
                  'results': [{'policyIndex': 0, 'id': policy['id'], 'version': policy['version'],
                               'decision': 'no_concern_detected',
                               'scores': {'applicability': .95, 'evidenceSufficiency': .95,
                                          'questions': [.1] * len(policy['questions'])}}]}
        learn.write_json(command[3], result)
        return subprocess.CompletedProcess(command, 0, '', '')

    def make_sanity(self, suffix='one'):
        self.require_validator()
        cases = self.reviewer / ('cases-' + suffix + '.json')
        learn.write_json(cases, {'cases': [
            {'id': 'observed', 'pair': {'human_message': 'Source says possible.', 'worker_response': 'Confirmed.'},
             'provenance': {'kind': 'observed', 'runId': 'local-example'},
             'expected': {'decision': 'advisory'}, 'note': 'Independent expected label is local only.'},
            {'id': 'alternative', 'pair': {'human_message': 'Source says possible.', 'worker_response': 'Possible.'},
             'provenance': {'kind': 'constructed'}, 'expected': {'decision': 'no_concern_detected'}}]})
        out = self.reviewer / ('sanity-' + suffix)
        with patch('learn.subprocess.run', side_effect=self.fake_native):
            result = learn.sanity(self.ctx, self.policy_file, cases, out)
        self.assertEqual(result['evaluatedResponses'], 2)
        return out

    def assessment(self, value=True):
        path = self.reviewer / 'assessment.json'
        path.write_text(json.dumps({'advisorySuitable': value, 'reason': 'The boundary is useful despite a measured miss.',
                                    'limitations': ['This test uses mocked native outputs.']}))
        return path

    def test_outside_cwd_enforced_even_through_symlinks(self):
        alias = self.base / 'worker-alias'
        alias.symlink_to(self.worker, target_is_directory=True)
        os.chdir(alias)
        with self.assertRaisesRegex(ValueError, 'reviewer_must_run_outside'):
            learn.context(str(self.worker))

    def test_nested_reviewer_config_and_explicit_project(self):
        nested = self.reviewer / 'notes'
        nested.mkdir()
        os.chdir(nested)
        self.assertEqual(learn.context()['project'], self.worker)
        self.assertEqual(learn.context(str(self.worker))['runtime'], RUNTIME)

    def test_selects_actual_pair_and_separates_provenance(self):
        wanted, pair = self.make_run()
        self.make_run('other', {'human_message': 'Unrelated', 'worker_response': 'Other result'})
        self.make_run('in-progress', complete=False)
        self.assertEqual(len(learn.list_runs(self.ctx)['runs']), 2)
        out = self.reviewer / 'exported'
        learn.export_run(self.ctx, wanted, out)
        self.assertEqual(learn.read_json(out / 'pair.json'), pair)
        self.assertEqual(set(learn.read_json(out / 'pair.json')), {'human_message', 'worker_response'})
        provenance = learn.read_json(out / 'provenance.json')
        self.assertEqual(provenance['runId'], wanted)
        self.assertNotIn('diagnosis', provenance)
        with self.assertRaisesRegex(ValueError, 'review_artifacts_must'):
            learn.export_run(self.ctx, wanted, self.worker / 'export')

    def test_rejects_run_path_and_scope_substitution(self):
        with self.assertRaisesRegex(ValueError, 'invalid_run_id'):
            learn.selected_run(self.ctx, '../other')
        wanted, _ = self.make_run()
        path = self.worker / '.jev/runs' / wanted / 'report.json'
        report = learn.read_json(path)
        report['evidenceScope'] = 'revised_response'
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'run_provenance_mismatch'):
            learn.selected_run(self.ctx, wanted)

    def test_real_shared_validator_rejects_extra_fields(self):
        self.require_validator()
        self.policy['hiddenEvidence'] = 'A prior test failed'
        self.policy_file.write_text(json.dumps(self.policy))
        with self.assertRaisesRegex(ValueError, 'policy_rejected_by_shared_validator'):
            learn.validate_policy(self.ctx, self.policy_file)

    def test_only_policy_and_pair_enter_native_evaluation(self):
        out = self.make_sanity()
        self.assertEqual(len(self.inputs), 2)
        for payload in self.inputs:
            self.assertEqual(set(payload), {'pair', 'policies'})
            self.assertEqual(set(payload['pair']), {'human_message', 'worker_response'})
        report = learn.read_json(out / 'report.json')
        self.assertEqual(report['cases'][0]['expected']['decision'], 'advisory')
        self.assertEqual(report['cases'][0]['actual']['results'][0]['decision'], 'no_concern_detected')

    def test_imperfect_advisory_activation_and_explicit_version_update(self):
        out = self.make_sanity()
        first = learn.activate(self.ctx, self.policy_file, out, self.assessment())
        target = Path(first['policy'])
        self.assertEqual(learn.read_json(target)['version'], 1)
        with self.assertRaisesRegex(ValueError, 'active_policy_version_conflict'):
            learn.activate(self.ctx, self.policy_file, out, self.assessment())
        old_bytes = target.read_bytes()
        self.policy['version'] = 2
        self.policy['feedback'] += ' Compare the same subject.'
        self.policy_file.write_text(json.dumps(self.policy))
        revised = self.make_sanity('two')
        second = learn.activate(self.ctx, self.policy_file, revised, self.assessment())
        self.assertEqual(learn.read_json(target)['version'], 2)
        self.assertEqual((Path(second['reviewRecord']) / 'previous-policy.json').read_bytes(), old_bytes)
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ['preserve-source.json'])

    def test_changed_candidate_and_non_boolean_assessment_rejected(self):
        out = self.make_sanity()
        with self.assertRaisesRegex(ValueError, 'affirmative_reviewer_assessment_required'):
            learn.activate(self.ctx, self.policy_file, out, self.assessment('true'))
        self.policy['feedback'] += ' New wording requires its own sanity record.'
        self.policy_file.write_text(json.dumps(self.policy))
        with self.assertRaisesRegex(ValueError, 'policy_changed_or_sanity_mismatch'):
            learn.activate(self.ctx, self.policy_file, out, self.assessment())

    def test_all_failed_calls_do_not_qualify_as_evaluation(self):
        out = self.make_sanity()
        path = out / 'report.json'
        report = learn.read_json(path)
        for row in report['cases']:
            row['actual']['results'][0].pop('scores')
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'sanity_has_no_verified_jev_response'):
            learn.activate(self.ctx, self.policy_file, out, self.assessment())

    def test_malformed_scores_are_not_semantic_uncertainty(self):
        out = self.make_sanity()
        result = learn.read_json(out / 'report.json')['cases'][0]['actual']
        for invalid in (None, True, float('nan'), 2):
            changed = copy.deepcopy(result)
            changed['results'][0]['scores']['questions'] = [invalid]
            self.assertFalse(learn.valid_evaluation(changed, self.policy))
        result['results'][0]['decision'] = 'unchecked'
        result['results'][0]['scores']['applicability'] = .5
        self.assertTrue(learn.valid_evaluation(result, self.policy))


if __name__ == '__main__':
    unittest.main()
