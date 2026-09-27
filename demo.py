#!/usr/bin/env python3
"""Replay real recorded evidence, or run a new Jev/native-policy/Luna repair."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live', action='store_true')
    p.add_argument('--out', help='New output directory for a live run')
    a = p.parse_args()
    example = ROOT / 'examples/ordered-import'
    if a.live:
        out = Path(a.out).resolve() if a.out else ROOT / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S')
        command = [sys.executable, str(ROOT/'loop.py'), 'check', '--task', str(example/'TASK.md'),
                   '--code', str(example/'candidate.mjs'), '--check', str(example/'check-falsy-commit-error-used-as-state.json'),
                   '--test', str(example/'tests.mjs'), '--test', str(example/'supplemental-tests.mjs'),
                   '--out', str(out), '--live', '--native-policy', '--correct']
        return subprocess.call(command)
    print('RECORDED REAL RUN — offline replay, no new model or API calls.\n')
    path = ROOT/'evidence/ordered-native-repair-v3/report.json'
    if not path.exists():
        path = ROOT/'evidence/ordered-live-repair-v1/report.json'
    report = json.loads(path.read_text())
    print('1. Luna wrote an importer that treats a falsy rejection reason as success.')
    print('2. Independent Sol review found the cause and authored a reusable yes/no check.')
    for result in report['results']:
        print('3. Jev:', result['decision'], result.get('scores', {}))
        print('   Native Failproof policy:', result.get('nativePolicy', {}).get('engineDecision', 'not used in this run'))
    correction = report.get('correction', {})
    print('4. One fresh Luna correction received the saved feedback and failing test evidence.')
    print('   Repaired test suites:', [t.get('status') for t in correction.get('independentTests', [])])
    print('   Recorded final status:', correction.get('outcome', 'not attempted'))
    recheck = ROOT/'evidence/ordered-native-final-recheck.json'
    if recheck.exists():
        r = json.loads(recheck.read_text())
        print('   Separate final recheck:', r.get('decision'), r.get('scores', {}), r.get('nativePolicy', {}).get('engineDecision'))
    print('\nFull evidence:', path)
    print('Other discovered failures and unsuccessful checks remain included. See EVIDENCE.md.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
