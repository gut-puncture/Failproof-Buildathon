#!/usr/bin/env python3
"""Install project-local Jev hooks and an outside reviewer workspace."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
HOOK_ID = 'failure-to-check-v1'
TESTED_CODEX = '0.158.0-alpha.2.1'
MIN_NODE = (22, 22, 0)


def safe_path(root, relative):
    """Installer-owned paths must not traverse existing symlinks."""
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f'Refusing symlink at {path}')
    return path


def read_object(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object in {path}')
    return value


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def executable(value, label):
    selected = shutil.which(value)
    if selected is None:
        raise ValueError(f'{label} executable not found: {value}')
    return str(Path(selected).resolve())


def probe(command, cwd, label):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'Could not verify {label}: {command[0]}') from error
    if result.returncode:
        raise ValueError(f'Could not verify {label}: {command[0]} (exit {result.returncode}). '
                         'Choose a working executable explicitly; no alternate was selected.')
    return result.stdout.strip()


def verify_tools(args, project):
    codex = executable(getattr(args, 'codex', None) or os.environ.get('CODEX_BIN') or 'codex', 'Codex')
    version = probe([codex, '--version'], project, 'Codex version')
    if not version:
        raise ValueError(f'No version returned by selected Codex: {codex}')
    features = probe([codex, 'features', 'list'], project, 'Codex hook support')
    hooks = next((line.split() for line in features.splitlines() if line.split()[:1] == ['hooks']), None)
    if not hooks or hooks[-1] != 'true' or 'removed' in hooks:
        raise ValueError(f'Selected Codex {codex} ({version}) does not report enabled hooks. '
                         f'Use --codex PATH or CODEX_BIN with a hooks-capable CLI. Tested: {TESTED_CODEX}; '
                         'no minimum Codex version is claimed. If hooks are supported but disabled, '
                         f'set hooks = true under [features] in {project / ".codex/config.toml"}; '
                         'merge with an existing [features] section rather than duplicating it, then rerun. '
                         'No settings were changed.')
    node = executable(os.environ.get('NODE_BIN') or 'node', 'Node')
    node_version = probe([node, '--version'], project, 'Node version')
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', node_version)
    if not match or tuple(map(int, match.groups())) < MIN_NODE:
        raise ValueError(f'Selected Node {node} reports {node_version!r}; Node >=22.22.0 is required. '
                         'Select a supported executable with NODE_BIN.')
    return {'codex': codex, 'codexVersion': version, 'hooksEnabled': True,
            'node': node, 'nodeVersion': node_version, 'testedCodexVersion': TESTED_CODEX}


def owned_hook(entry, project):
    if not isinstance(entry, dict) or entry.get('type') != 'command':
        return False
    try:
        parts = shlex.split(entry.get('command', ''))
        return (parts[parts.index('--jev-hook-id') + 1] == HOOK_ID
                and parts[parts.index('--project') + 1] == str(project))
    except (ValueError, IndexError, TypeError):
        return False


def merge_hooks(document, project):
    document = copy.deepcopy(document)
    events = document.setdefault('hooks', {})
    if not isinstance(events, dict):
        raise ValueError('Existing .codex/hooks.json hooks must be an object')
    command = [sys.executable, str(ROOT / 'hooks/stop.py'), '--project', str(project), '--jev-hook-id', HOOK_ID]
    for event in ('UserPromptSubmit', 'Stop'):
        existing = events.setdefault(event, [])
        if not isinstance(existing, list):
            raise ValueError(f'Existing {event} hooks must be a list')
        retained = []
        for group in existing:
            if isinstance(group, dict) and isinstance(group.get('hooks'), list):
                other = [item for item in group['hooks'] if not owned_hook(item, project)]
                if len(other) != len(group['hooks']):
                    if other:
                        retained.append({**group, 'hooks': other})
                    continue
            retained.append(group)
        retained.append({'hooks': [{'type': 'command', 'command': shlex.join(command),
                                   'commandWindows': subprocess.list2cmdline(command), 'timeout': 20,
                                   'statusMessage': 'Jev: capture prompt' if event == 'UserPromptSubmit'
                                   else 'Jev: evaluate learned advisory policies'}]})
        events[event] = retained
    return document


def merged_config(path, expected):
    current = read_object(path) if path.exists() else {}
    if current and (current.get('schemaVersion') != 1 or current.get('project') != expected['project']):
        raise ValueError(f'Existing configuration does not belong to this project: {path}')
    return {**current, **expected}


def install(args):
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError('Project directory must exist')
    reviewer = Path(getattr(args, 'reviewer', None) or project.with_name(project.name + '-jev-reviewer')).expanduser().resolve()
    if reviewer.is_relative_to(project):
        raise ValueError('Reviewer workspace must be outside the hooked project')
    if reviewer.exists() and not reviewer.is_dir():
        raise ValueError('Reviewer workspace must be a directory')
    selected = verify_tools(args, project)
    config = {'schemaVersion': 1, 'project': str(project), 'runtime': str(ROOT), 'node': selected['node']}
    hook_path = safe_path(project, '.codex/hooks.json')
    config_path = safe_path(project, '.jev/config.json')
    policies_path = safe_path(project, '.jev/policies')
    runs_path = safe_path(project, '.jev/runs')
    ignore_path = safe_path(project, '.jev/.gitignore')
    review_path = safe_path(reviewer, '.jev-review.json')
    skill_path = safe_path(reviewer, '.agents/skills/failure-to-check')
    definition = merge_hooks(read_object(hook_path) if hook_path.exists() else {}, project)
    worker_config = merged_config(config_path, config)
    review_config = merged_config(review_path, config)
    source = ROOT / 'skills/failure-to-check'
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Runtime reviewer skill is missing')
    skill_files = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Reviewer skill source contains a symlink: {path}')
        if path.is_file():
            target = safe_path(skill_path, path.relative_to(source))
            content = path.read_bytes()
            if target.exists() and target.read_bytes() != content and not review_path.exists():
                raise ValueError(f'Refusing to overwrite an existing unrelated reviewer skill: {target}')
            skill_files.append((target, content))
    ignored = ignore_path.read_text(encoding='utf-8') if ignore_path.exists() else ''
    for pattern in ('runs/', 'config.json'):
        if pattern not in ignored.splitlines():
            ignored += ('\n' if ignored and not ignored.endswith('\n') else '') + pattern + '\n'
    report = {'hookFile': str(hook_path), 'configFile': str(config_path), 'reviewer': str(reviewer),
              'reviewerConfigFile': str(review_path), 'reviewerSkill': str(skill_path), 'hooks': definition,
              'config': worker_config, 'selectedTools': selected, 'dryRun': args.dry_run,
              'nextStep': f'Keep the runtime at {ROOT}. Start {shlex.quote(selected["codex"])} in '
                          f'{project}, accept ordinary folder trust, then use /hooks to review and trust '
                          'both Jev commands. No trust or global settings were changed. '
                          'Set FAILPROOF_API_KEY or FAILPROOF_KEY_FILE before starting Codex when '
                          'policies are present; an empty collection needs no credentials.',
              'reviewerStep': f'Open a reviewer chat from {reviewer} and invoke $failure-to-check. '
                              'The installed skill reads .jev-review.json.',
              'documentation': 'https://learn.chatgpt.com/docs/hooks'}
    if not args.dry_run:
        policies_path.mkdir(parents=True, exist_ok=True)
        runs_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(config_path, json_bytes(worker_config))
        atomic_write(review_path, json_bytes(review_config))
        for target, content in skill_files:
            atomic_write(target, content)
        atomic_write(ignore_path, ignored.encode('utf-8'))
        atomic_write(hook_path, json_bytes(definition))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--reviewer')
    parser.add_argument('--codex', help='Codex executable; otherwise CODEX_BIN, then PATH')
    parser.add_argument('--dry-run', action='store_true')
    try:
        print(json.dumps(install(parser.parse_args()), indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
