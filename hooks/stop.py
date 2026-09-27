#!/usr/bin/env python3
"""Capture exact Codex turn pairs and deliver at most one advisory continuation."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCHEMA_VERSION = 1
HOOK_ID = 'failure-to-check-v1'
MAX_POLICY_BYTES = 64 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def valid_ids(event):
    return all(isinstance(event.get(key), str) and event[key].strip() and len(event[key]) <= 512
               and not any(ord(char) < 32 for char in event[key])
               for key in ('session_id', 'turn_id'))


def run_id(event):
    encoded = json.dumps([event['session_id'], event['turn_id']], ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def safe_path(root, relative):
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError('Unsafe local state path')
    return path


def read_json(path):
    if path.is_symlink():
        raise ValueError('Unsafe local state file')
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def write_json(path, value, exclusive=False):
    if path.is_symlink():
        raise ValueError('Unsafe local state file')
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
        else:
            os.replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def skip_continuation(project_arg, event):
    """No config, policies, credentials or revised response on this path."""
    try:
        if event.get('hook_event_name') != 'Stop' or not valid_ids(event):
            return
        project = Path(project_arg).resolve()
        directory = safe_path(project, Path('.jev/runs') / run_id(event))
        if directory.is_dir():
            write_json(directory / 'continuation-skipped.json',
                       {'schemaVersion': 1, 'session_id': event['session_id'],
                        'turn_id': event['turn_id'], 'skippedAt': now(),
                        'reason': 'stop_hook_active'}, exclusive=True)
    except (OSError, ValueError, TypeError):
        pass


def load_context(project_arg, event):
    project = Path(project_arg).resolve()
    cwd = event.get('cwd')
    if not project.is_dir() or not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError('Missing project cwd')
    if not Path(cwd).resolve().is_relative_to(project) or not Path.cwd().resolve().is_relative_to(project):
        raise ValueError('Hook cwd outside project')
    config = read_json(safe_path(project, '.jev/config.json'))
    if (not isinstance(config, dict) or config.get('schemaVersion') != 1
            or config.get('project') != str(project)):
        raise ValueError('Invalid project configuration')
    runs = safe_path(project, '.jev/runs')
    runs.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = safe_path(project, Path('.jev/runs') / run_id(event))
    directory.mkdir(mode=0o700, exist_ok=True)
    return project, config, directory


def capture_prompt(directory, event):
    prompt = event.get('prompt')
    if not isinstance(prompt, str) or not prompt:
        return
    record = {'schemaVersion': 1, 'session_id': event['session_id'], 'turn_id': event['turn_id'],
              'capturedAt': now(), 'human_message': prompt}
    path = directory / 'prompt.json'
    if not write_json(path, record, exclusive=True):
        previous = read_json(path)
        if (not isinstance(previous, dict) or previous.get('human_message') != prompt
                or previous.get('session_id') != event['session_id']
                or previous.get('turn_id') != event['turn_id']):
            write_json(directory / 'prompt-conflict.json',
                       {'reason': 'conflicting_prompt_delivery', 'recordedAt': now()}, exclusive=True)


def policy_snapshot(project):
    collection = safe_path(project, '.jev/policies')
    policies, records = [], []
    if not collection.exists():
        return policies, records
    for path in sorted(collection.glob('*.json')):
        record = {'path': str(path.relative_to(project)), 'sha256': None, 'rawBase64': None}
        value = None
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError('Policy is not a regular local file')
            record['sizeBytes'] = path.stat().st_size
            if record['sizeBytes'] > MAX_POLICY_BYTES:
                record['parseError'] = 'oversized_policy_json'
                policies.append(None)
                records.append(record)
                continue
            with path.open('rb') as stream:
                raw = stream.read(MAX_POLICY_BYTES + 1)
            if len(raw) > MAX_POLICY_BYTES:
                raise ValueError('Policy grew beyond size limit')
            record.update(sha256=hashlib.sha256(raw).hexdigest(),
                          rawBase64=base64.b64encode(raw).decode('ascii'))
            value = json.loads(raw.decode('utf-8'), parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
            if isinstance(value, dict):
                if isinstance(value.get('id'), str):
                    record['id'] = value['id']
                if type(value.get('version')) is int:
                    record['version'] = value['version']
        except (OSError, ValueError, UnicodeError):
            record['parseError'] = 'invalid_or_unreadable_policy_json'
        policies.append(value)
        records.append(record)
    return policies, records


def evaluate(config, directory, pair, policies):
    runtime_value, node_value = config.get('runtime'), config.get('node')
    if not isinstance(runtime_value, str) or not isinstance(node_value, str):
        raise ValueError('Missing runtime configuration')
    runtime, node = Path(runtime_value), Path(node_value)
    if not runtime.is_absolute() or not node.is_absolute():
        raise ValueError('Runtime paths must be absolute')
    runtime, node = runtime.resolve(), node.resolve()
    gate = runtime / 'native/gate.mjs'
    if not gate.resolve().is_relative_to(runtime) or not gate.is_file() or not node.is_file():
        raise ValueError('Runtime unavailable')
    input_path, output_path = directory / 'input.json', directory / 'gate-output.json'
    write_json(input_path, {'pair': pair, 'policies': policies}, exclusive=True)
    if output_path.exists() or output_path.is_symlink():
        raise ValueError('Unexpected existing native output')
    result = subprocess.run([str(node), str(gate), str(input_path), str(output_path)],
                            cwd=runtime, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=15, check=False)
    if result.returncode not in (0, 2):
        raise ValueError('Native runtime process failed')
    outcome = read_json(output_path)
    if (not isinstance(outcome, dict) or outcome.get('schemaVersion') != 1
            or outcome.get('decision') not in ('advisory', 'quiet', 'unchecked')
            or not isinstance(outcome.get('results'), list)
            or not isinstance(outcome.get('suggestions'), list)):
        raise ValueError('Invalid native runtime result')
    if outcome['decision'] == 'advisory':
        native = outcome.get('nativePolicy')
        if (not isinstance(native, dict) or native.get('verified') is not True
                or native.get('engineDecision') != 'deny'):
            raise ValueError('Unverified native advisory')
    return outcome


def combined_advice(outcome):
    suggestions = outcome.get('suggestions', [])
    if outcome.get('decision') != 'advisory' or not suggestions:
        return None
    lines = []
    for suggestion in suggestions:
        if (not isinstance(suggestion, dict) or suggestion.get('level') not in ('advisory', 'tentative')
                or not isinstance(suggestion.get('feedback'), str) or not suggestion['feedback'].strip()):
            raise ValueError('Invalid advisory suggestion')
        label = 'Tentative concern' if suggestion['level'] == 'tentative' else 'Possible concern'
        lines.append(f'- {label}: {suggestion["feedback"]}')
    return ('Jev reviewed only your latest human message and initial completed response. '
            'These learned checks are fallible advisory signals. Review the concerns below and '
            'make an appropriate correction, or explain why the advice does not apply.\n'
            + '\n'.join(lines))


def normal_stop(project, config, directory, event):
    claim = directory / 'claim.json'
    if claim.exists() or claim.is_symlink():
        return {}
    report = {'schemaVersion': 1, 'session_id': event['session_id'], 'turn_id': event['turn_id'],
              'completedAt': now(), 'evidenceScope': 'initial_response_before_advice',
              'decision': 'unchecked', 'reason': 'missing_turn_evidence', 'policyFiles': [],
              'results': [], 'suggestions': [], 'request': None}
    response = {}
    claimed = False
    try:
        prompt = read_json(directory / 'prompt.json')
        worker = event.get('last_assistant_message')
        if (not isinstance(prompt, dict) or prompt.get('schemaVersion') != 1
                or prompt.get('session_id') != event['session_id']
                or prompt.get('turn_id') != event['turn_id']
                or not isinstance(prompt.get('human_message'), str) or not prompt['human_message']
                or not isinstance(worker, str) or not worker.strip()):
            raise ValueError('Missing exact turn pair')
        report['capturedAt'] = prompt.get('capturedAt')
        if (directory / 'prompt-conflict.json').exists():
            report['reason'] = 'conflicting_prompt_delivery'
        else:
            pair = {'human_message': prompt['human_message'], 'worker_response': worker}
            # Only a complete, unambiguous pair consumes the durable evaluation claim.
            # This remains exclusive across concurrent deliveries and survives crashes.
            if not write_json(claim, {'claimedAt': now()}, exclusive=True):
                return {}
            claimed = True
            write_json(directory / 'pair.json', pair, exclusive=True)
            report['reason'] = 'policy_snapshot_unavailable'
            policies, records = policy_snapshot(project)
            report['policyFiles'] = records
            if not policies:
                report['reason'] = 'empty_policies'
            else:
                report['reason'] = 'native_runtime_unavailable'
                outcome = evaluate(config, directory, pair, policies)
                for key in ('decision', 'reason', 'results', 'suggestions', 'request', 'requestHash', 'nativePolicy'):
                    if key in outcome:
                        report[key] = outcome[key]
                if 'reason' not in outcome:
                    report.pop('reason', None)
                advice = combined_advice(outcome)
                if advice:
                    report['advice'] = advice
                    response = {'decision': 'block', 'reason': advice}
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        report['decision'] = 'unchecked'
        report['suggestions'] = []
        if report.get('reason') not in ('missing_turn_evidence', 'conflicting_prompt_delivery', 'policy_snapshot_unavailable'):
            report['reason'] = 'native_runtime_unavailable'
    if not claimed:
        # Rejected deliveries never create an authoritative run report or pair.
        write_json(directory / 'invalid-stop.json',
                   {'session_id': event['session_id'], 'turn_id': event['turn_id'],
                    'reason': report['reason']}, exclusive=True)
        return {}
    write_json(directory / 'report.json', report)
    return response


def handle(project_arg, event):
    if not isinstance(event, dict):
        return {}
    # Inspect this actual boolean before reading even the project configuration.
    if event.get('stop_hook_active') is True:
        skip_continuation(project_arg, event)
        return {}
    name = event.get('hook_event_name')
    if name not in ('UserPromptSubmit', 'Stop') or not valid_ids(event):
        return {}
    if name == 'Stop' and type(event.get('stop_hook_active')) is not bool:
        return {}
    try:
        project, config, directory = load_context(project_arg, event)
        if name == 'UserPromptSubmit':
            capture_prompt(directory, event)
            return {}
        return normal_stop(project, config, directory, event)
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--jev-hook-id', choices=[HOOK_ID], default=HOOK_ID)
    args = parser.parse_args()
    try:
        output = handle(args.project, json.load(sys.stdin))
    except (OSError, ValueError, TypeError):
        output = {}
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
