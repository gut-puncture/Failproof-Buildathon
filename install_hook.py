#!/usr/bin/env python3
"""Install an opt-in project-local Codex Stop hook. No global settings changes."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


def install(args):
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise ValueError('Project directory must exist')
    task, code, check = [Path(v).resolve() for v in [args.task, args.code, args.check]]
    if not task.is_file() or not check.is_file():
        raise ValueError('Explicit task and check files must exist')
    if not code.is_relative_to(project):
        raise ValueError('Candidate must be inside the selected project')
    config = project / '.jev-check/context.json'
    hooks = project / '.codex/hooks.json'
    if hooks.exists() or config.exists():
        raise ValueError('Refusing to overwrite existing hooks or Jev context; review and merge manually')
    command = [sys.executable, str(Path(__file__).resolve().parent / 'hooks/stop.py'), '--config', str(config)]
    definition = {'description': 'Explicit candidate Jev check through the native Failproof policy engine.',
                  'hooks': {'Stop': [{'hooks': [{'type':'command', 'command':shlex.join(command),
                    'commandWindows':subprocess.list2cmdline(command), 'timeout':60,
                    'statusMessage':'Checking configured candidate with Jev / Failproof'}]}]}}
    context = {'project':str(project), 'task':str(task), 'code':str(code), 'check':str(check), 'mode':'paired'}
    report = {'hookFile':str(hooks), 'contextFile':str(config), 'hooks':definition, 'context':context,
              'nextStep':'Start Codex in this trusted project, open /hooks, review and trust this Stop hook. Keep this package at its installed path. Configure FAILPROOF_API_KEY or FAILPROOF_KEY_FILE before starting Codex.',
              'documentation':'https://learn.chatgpt.com/docs/hooks', 'dryRun':args.dry_run}
    if not args.dry_run:
        config.parent.mkdir(parents=True, exist_ok=True)
        hooks.parent.mkdir(parents=True, exist_ok=True)
        with config.open('x', encoding='utf-8') as stream:
            json.dump(context, stream, indent=2)
        with hooks.open('x', encoding='utf-8') as stream:
            json.dump(definition, stream, indent=2)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['project','task','code','check']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--dry-run', action='store_true')
    try:
        print(json.dumps(install(parser.parse_args()), indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
