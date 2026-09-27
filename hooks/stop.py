#!/usr/bin/env python3
"""Codex Stop input/output contract: https://learn.chatgpt.com/docs/hooks"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import loop


def handle(config_path, event):
    config_path = Path(config_path).resolve()
    runs = config_path.parent / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    output = runs / uuid.uuid4().hex
    output.mkdir()
    report = {'decision':'unchecked', 'scope':'Only explicitly configured task/candidate/check files; one continuation maximum.',
              'lastAssistantMessagePresent':isinstance(event.get('last_assistant_message'), str)}
    if event.get('stop_hook_active'):
        report['reason'] = 'continuation_already_used_needs_review'
        loop.write_json(output / 'report.json', report)
        return {'systemMessage':f'Jev hook: continuation already used; needs review. Report: {output / "report.json"}'}
    try:
        config = loop.read_json(config_path)
        code = Path(config['code']).resolve()
        if not code.is_relative_to(Path(config['project']).resolve()):
            raise ValueError('Candidate outside configured project')
        check = loop.read_json(config['check'])
        state = loop.state_from_files(config['task'], code, [])
        result = loop.inspect(check, state, output / 'gate', config.get('mode','paired'), True, True)
        report.update(result)
        loop.write_json(output / 'report.json', report)
        if result['decision'] == 'violation_detected':
            session = str(event.get('session_id','')) + ':' + str(event.get('turn_id',''))
            marker = config_path.parent / ('continued-' + hashlib.sha256(session.encode()).hexdigest())
            try:
                with marker.open('x') as stream:
                    stream.write(str(output))
            except FileExistsError:
                return {'systemMessage':f'Jev hook: revision already requested; needs review. Report: {output / "report.json"}'}
            feedback = check.get('feedback')
            if not isinstance(feedback,str) or not feedback.strip():
                feedback = 'Review the configured candidate against the supplied task and detected semantic violation.'
            return {'decision':'block', 'reason':f'Jev / native Failproof detected a scoped violation in {code}. Make one focused correction using the task at {config["task"]}. Feedback: {feedback[:6000]} Do not change the hook or check. Report: {output / "report.json"}'}
        if result['decision'] == 'unchecked':
            return {'systemMessage':f'Jev hook unchecked: {result.get("reason","unknown")}. Report: {output / "report.json"}'}
        return {}
    except (OSError, ValueError, KeyError, TypeError):
        report['reason'] = 'hook_context_or_runtime_unavailable'
        loop.write_json(output / 'report.json', report)
        return {'systemMessage':f'Jev hook unchecked; inspect explicit context and native runtime. Report: {output / "report.json"}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        event = json.load(sys.stdin)
        if not isinstance(event,dict):
            raise ValueError('Invalid hook event')
        print(json.dumps(handle(args.config,event)))
    except (OSError, ValueError):
        print(json.dumps({'systemMessage':'Jev hook unchecked: event/configuration could not be read.'}))
