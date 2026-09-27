#!/usr/bin/env python3
"""Local reviewer helpers: inspect runs, check policy data, and install advisory policies."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

MAX_BYTES = 5_000_000


def fail(reason):
    raise ValueError(reason)


def inside(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def read_json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        fail('missing_or_oversized_artifact')
    def invalid_constant(_):
        fail('invalid_json_number')
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=invalid_constant)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def context(project=None):
    cwd = Path.cwd().resolve()
    if project:
        target = Path(project).resolve()
        config = read_json(target / '.jev/config.json')
    else:
        config_file = next((p / '.jev-review.json' for p in [cwd, *cwd.parents]
                            if (p / '.jev-review.json').is_file()), None)
        if config_file is None:
            fail('reviewer_config_missing_use_outside_folder_or_project')
        config = read_json(config_file)
        target = None
    if not isinstance(config, dict) or type(config.get('schemaVersion')) is not int or config['schemaVersion'] != 1:
        fail('invalid_reviewer_config')
    if any(not isinstance(config.get(k), str) or not Path(config[k]).is_absolute()
           for k in ('project', 'runtime', 'node')):
        fail('invalid_reviewer_config')
    configured = Path(config['project']).resolve()
    if target is not None and target != configured:
        fail('project_config_mismatch')
    if not configured.is_dir() or inside(cwd, configured):
        fail('reviewer_must_run_outside_worker_project')
    for relative in ('.jev', '.jev/runs', '.jev/policies'):
        original = configured / relative
        if original.is_symlink() or not inside(original.resolve(), configured):
            fail('project_storage_must_remain_inside_project')
    return {'project': configured, 'runtime': Path(config['runtime']).resolve(),
            'node': Path(config['node']).resolve(), 'cwd': cwd}


def outside_output(ctx, path):
    path = Path(path).resolve()
    if inside(path, ctx['project']):
        fail('review_artifacts_must_stay_outside_worker_project')
    path.mkdir(parents=True, exist_ok=False)
    return path


def pair_shape(pair):
    return (isinstance(pair, dict) and set(pair) == {'human_message', 'worker_response'}
            and all(isinstance(value, str) and value.strip() for value in pair.values()))


def selected_run(ctx, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'[0-9a-f]{64}', run_id):
        fail('invalid_run_id')
    path = ctx['project'] / '.jev/runs' / run_id
    if path.is_symlink() or not inside(path.resolve(), ctx['project'] / '.jev/runs'):
        fail('invalid_run_path')
    if any((path / name).is_symlink() for name in ('pair.json', 'report.json')):
        fail('invalid_run_path')
    pair, report = read_json(path / 'pair.json'), read_json(path / 'report.json')
    if not pair_shape(pair) or not isinstance(report, dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion'] != 1:
        fail('incomplete_or_invalid_run')
    ids = [report.get('session_id'), report.get('turn_id')]
    if any(not isinstance(value, str) or not value for value in ids):
        fail('incomplete_or_invalid_run')
    expected = hashlib.sha256(json.dumps(ids, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if expected != run_id or report.get('evidenceScope') != 'initial_response_before_advice':
        fail('run_provenance_mismatch')
    return path, pair, report


def list_runs(ctx):
    rows, skipped = [], 0
    for path in sorted((ctx['project'] / '.jev/runs').glob('*')):
        if not path.is_dir():
            continue
        try:
            _, pair, report = selected_run(ctx, path.name)
            rows.append({'runId': path.name, 'session_id': report['session_id'],
                         'turn_id': report['turn_id'], 'completedAt': report.get('completedAt'),
                         'humanPreview': pair['human_message'][:120]})
        except (OSError, ValueError, TypeError):
            skipped += 1
    return {'runs': rows, 'skippedIncompleteOrInvalid': skipped}


def export_run(ctx, run_id, destination):
    path, pair, report = selected_run(ctx, run_id)
    out = outside_output(ctx, destination)
    write_json(out / 'pair.json', pair)
    provenance = {key: report.get(key) for key in
                  ('session_id', 'turn_id', 'capturedAt', 'completedAt', 'evidenceScope')}
    provenance.update(schemaVersion=1, kind='observed', runId=run_id,
                      project=str(ctx['project']), sourcePairHash=digest(path / 'pair.json'),
                      sourceReportHash=digest(path / 'report.json'))
    write_json(out / 'provenance.json', provenance)
    return {'exported': str(out), 'runId': run_id}


def validate_policy(ctx, filename):
    path = Path(filename).resolve()
    policy = read_json(path)
    proc = subprocess.run([str(ctx['node']), str(ctx['runtime'] / 'runtime/policy.mjs'),
                           'validate', str(path)], cwd=ctx['cwd'], capture_output=True,
                          text=True, timeout=15)
    try:
        summary = json.loads(proc.stdout)
    except (ValueError, TypeError):
        fail('shared_validator_unavailable_or_invalid')
    if proc.returncode != 0 or not isinstance(summary, dict) or summary.get('valid') is not True:
        fail('policy_rejected_by_shared_validator')
    if not isinstance(policy, dict) or summary.get('id') != policy.get('id') or summary.get('version') != policy.get('version'):
        fail('shared_validator_identity_mismatch')
    return policy, summary


def candidate_bytes(filename, policy):
    content = Path(filename).read_bytes()
    if json.loads(content) != policy:
        fail('policy_changed_during_operation')
    return content


def cases_from(filename):
    manifest = read_json(filename)
    if not isinstance(manifest, dict) or set(manifest) != {'cases'} or not isinstance(manifest['cases'], list) or not manifest['cases']:
        fail('cases_must_be_nonempty')
    seen = set()
    for case in manifest['cases']:
        if not isinstance(case, dict) or set(case) - {'id', 'pair', 'provenance', 'expected', 'note'}:
            fail('invalid_sanity_case')
        name, provenance = case.get('id'), case.get('provenance')
        if not isinstance(name, str) or not name.strip() or name in seen or not pair_shape(case.get('pair')):
            fail('invalid_sanity_case')
        if not isinstance(provenance, dict) or provenance.get('kind') not in ('observed', 'constructed'):
            fail('case_provenance_required')
        if 'expected' in case and not isinstance(case['expected'], dict):
            fail('expected_labels_must_be_object')
        if 'note' in case and not isinstance(case['note'], str):
            fail('invalid_sanity_note')
        seen.add(name)
    return manifest


def sanity(ctx, policy_file, cases_file, destination):
    policy, summary = validate_policy(ctx, policy_file)
    content = candidate_bytes(policy_file, policy)
    manifest = cases_from(cases_file)
    out = outside_output(ctx, destination)
    (out / 'policy.json').write_bytes(content)
    write_json(out / 'cases.json', manifest)
    report = {'schemaVersion': 1, 'kind': 'policy_sanity', 'createdAt': now(),
              'project': str(ctx['project']), 'policy': summary,
              'policyBytesHash': digest(out / 'policy.json'), 'cases': []}
    for index, case in enumerate(manifest['cases']):
        folder = out / ('case-%03d' % index)
        folder.mkdir()
        write_json(folder / 'input.json', {'pair': case['pair'], 'policies': [policy]})
        actual = {'schemaVersion': 1, 'decision': 'unchecked', 'reason': 'native_evaluation_unavailable',
                  'results': [], 'suggestions': [], 'request': None}
        try:
            proc = subprocess.run([str(ctx['node']), str(ctx['runtime'] / 'native/gate.mjs'),
                                   str(folder / 'input.json'), str(folder / 'output.json')],
                                  cwd=ctx['cwd'], capture_output=True, text=True, timeout=45)
            if proc.returncode == 0:
                result = read_json(folder / 'output.json')
                if isinstance(result, dict) and type(result.get('schemaVersion')) is int and result['schemaVersion'] == 1:
                    actual = result
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            pass
        report['cases'].append({**{k: v for k, v in case.items() if k != 'pair'}, 'actual': actual})
    write_json(out / 'report.json', report)
    return {'sanity': str(out), 'cases': len(report['cases']),
            'evaluatedResponses': sum(valid_evaluation(row['actual'], policy) for row in report['cases'])}


def valid_evaluation(actual, policy):
    if not isinstance(actual, dict) or not isinstance(actual.get('nativePolicy'), dict):
        return False
    if actual['nativePolicy'].get('verified') is not True or not isinstance(actual.get('request'), dict):
        return False
    results = actual.get('results')
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        return False
    row, scores = results[0], results[0].get('scores')
    if row.get('id') != policy['id'] or row.get('version') != policy['version'] or not isinstance(scores, dict):
        return False
    questions = scores.get('questions')
    if not isinstance(questions, list) or len(questions) != len(policy['questions']):
        return False
    return all(type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1
               for value in [scores.get('applicability'), scores.get('evidenceSufficiency'), *questions])


def activate(ctx, policy_file, sanity_dir, assessment_file):
    policy, summary = validate_policy(ctx, policy_file)
    content = candidate_bytes(policy_file, policy)
    checked = Path(sanity_dir).resolve()
    if inside(checked, ctx['project']):
        fail('review_artifacts_must_stay_outside_worker_project')
    report, assessment = read_json(checked / 'report.json'), read_json(assessment_file)
    if (not isinstance(assessment, dict) or set(assessment) != {'advisorySuitable', 'reason', 'limitations'}
            or assessment.get('advisorySuitable') is not True
            or not isinstance(assessment.get('reason'), str) or not assessment['reason'].strip()
            or not isinstance(assessment.get('limitations'), list)
            or any(not isinstance(value, str) or not value.strip() for value in assessment['limitations'])):
        fail('affirmative_reviewer_assessment_required')
    expected_hash = hashlib.sha256(content).hexdigest()
    if (not isinstance(report, dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion'] != 1 or report.get('kind') != 'policy_sanity'
            or report.get('project') != str(ctx['project']) or report.get('policyBytesHash') != expected_hash
            or digest(checked / 'policy.json') != expected_hash):
        fail('policy_changed_or_sanity_mismatch')
    rows = report.get('cases')
    if not isinstance(rows, list) or not any(isinstance(row, dict) and valid_evaluation(row.get('actual'), policy) for row in rows):
        fail('sanity_has_no_verified_jev_response')
    policies = ctx['project'] / '.jev/policies'
    policies.mkdir(exist_ok=True)
    target = policies / (policy['id'] + '.json')
    lock = policies / '.activation.lock'
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        fail('policy_activation_in_progress')
    temporary = None
    try:
        os.close(lock_fd)
        previous = None
        for existing in policies.glob('*.json'):
            if existing.is_symlink():
                fail('active_policy_symlink_not_supported')
            try:
                value = read_json(existing)
            except (ValueError, OSError):
                if existing == target:
                    fail('active_policy_conflict')
                continue
            if isinstance(value, dict) and value.get('id') == policy['id']:
                if previous is not None or existing != target or type(value.get('version')) is not int or value['version'] >= policy['version']:
                    fail('active_policy_version_conflict')
                previous = existing.read_bytes()
            elif existing == target:
                fail('active_policy_conflict')
        activation = checked / ('activation-' + policy['id'] + '-v' + str(policy['version']))
        activation.mkdir(exist_ok=False)
        if previous is not None:
            (activation / 'previous-policy.json').write_bytes(previous)
        write_json(activation / 'assessment.json', assessment)
        write_json(activation / 'record.json', {'schemaVersion': 1, 'createdAt': now(), 'project': str(ctx['project']),
                   'policy': summary, 'policyBytesHash': expected_hash, 'sanityReportHash': digest(checked / 'report.json')})
        fd, name = tempfile.mkstemp(prefix='.policy-', suffix='.tmp', dir=policies)
        temporary = Path(name)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        return {'activated': True, 'id': policy['id'], 'version': policy['version'],
                'policy': str(target), 'reviewRecord': str(activation)}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--project', help='Explicit installed worker project; invoke from outside it')
    commands = result.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List complete saved initial-response runs')
    export = commands.add_parser('export', help='Export a selected actual pair and separate provenance')
    export.add_argument('run_id')
    export.add_argument('--out', required=True)
    validate = commands.add_parser('validate', help='Use the shared strict policy validator')
    validate.add_argument('policy')
    check = commands.add_parser('sanity', help='Send declared pairs to Jev through the shared native evaluator')
    check.add_argument('policy')
    check.add_argument('--cases', required=True)
    check.add_argument('--out', required=True)
    save = commands.add_parser('activate', help='Install reviewed advisory data; no perfect-score requirement')
    save.add_argument('policy')
    save.add_argument('--sanity', required=True)
    save.add_argument('--assessment', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        ctx = context(args.project)
        if args.command == 'list':
            result = list_runs(ctx)
        elif args.command == 'export':
            result = export_run(ctx, args.run_id, args.out)
        elif args.command == 'validate':
            _, result = validate_policy(ctx, args.policy)
        elif args.command == 'sanity':
            result = sanity(ctx, args.policy, args.cases, args.out)
        else:
            result = activate(ctx, args.policy, args.sanity, args.assessment)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        # Never print child output or raw exceptions; only our static local reasons.
        reason = str(error) if type(error) is ValueError and re.fullmatch(r'[a-z_]+', str(error)) else 'reviewer_operation_failed'
        print(json.dumps({'error': reason}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
