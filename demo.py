#!/usr/bin/env python3
"""Execute real code before/after; --live uses real Jev, Failproof, and Luna."""
import argparse
from datetime import datetime
import difflib
import json
from pathlib import Path
import subprocess
import sys
import loop

ROOT=Path(__file__).resolve().parent
EXAMPLE=ROOT/'examples/ordered-import'

def heading(text):
    print('\n'+'='*64+'\n'+text+'\n'+'='*64,flush=True)

def show_tests(records,directory):
    total=passed=0
    for i,record in enumerate(records):
        print(Path(record['suite']).name+': '+record['status'],flush=True)
        log=directory/f'test-{i}.stdout.log'
        if not log.exists(): continue
        for line in log.read_text().splitlines():
            try: row=json.loads(line)
            except ValueError: continue
            if 'summary' in row:
                total+=row['summary']['total'];passed+=row['summary']['passed']
            elif 'passed' in row:
                print('  '+('PASS' if row['passed'] else 'FAIL')+' '+str(row.get('name',row.get('reasonType','case'))),flush=True)
    print(f'ACTUALLY EXECUTED: {passed}/{total} tests passed' if total else 'See individual test process results.',flush=True)
    return {'passed':passed,'total':total}

def probe(code):
    script="""import {pathToFileURL} from 'node:url';
const {importRows}=await import(pathToFileURL(process.argv[1]));
let attempted=0;
try {await importRows([{invoice:'INV-001'}],{concurrency:1,prepare:x=>x,commit:()=>{attempted++;throw undefined;}});console.log(JSON.stringify({saveAttempts:attempted,saveSucceeded:false,importerReported:'SUCCESS',correct:false}));}
catch(e){console.log(JSON.stringify({saveAttempts:attempted,saveSucceeded:false,importerReported:'FAILURE',preservedOriginalReason:e===undefined,correct:e===undefined}));}
"""
    result=subprocess.run([loop.find_binary('node','NODE_BIN'),'--input-type=module','-e',script,str(code)],capture_output=True,text=True,timeout=15)
    if result.returncode: raise RuntimeError('Example execution failed; no result claimed.')
    actual=json.loads(result.stdout)
    print('An invoice save rejects with undefined (allowed by the task).',flush=True)
    print(json.dumps(actual,indent=2),flush=True)
    return actual

def verdict(result):
    print(json.dumps({k:result.get(k) for k in ['decision','scores','reason','nativePolicy']},indent=2),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true')
    p.add_argument('--task',default=str(EXAMPLE/'TASK.md'))
    p.add_argument('--code',default=str(EXAMPLE/'candidate.mjs'))
    p.add_argument('--check',default=str(EXAMPLE/'check-falsy-commit-error-used-as-state.json'))
    p.add_argument('--test',action='append')
    p.add_argument('--out')
    a=p.parse_args()
    custom=Path(a.code).resolve()!=EXAMPLE/'candidate.mjs'
    if custom and not a.live:p.error('Custom candidates require --live; recorded repairs only belong to the bundled example.')
    a.test=a.test if a.test is not None else ([] if custom else [str(EXAMPLE/'tests.mjs'),str(EXAMPLE/'supplemental-tests.mjs')])
    a.context=[];a.mode='paired';a.native_policy=True
    out=Path(a.out).resolve() if a.out else ROOT/'runs'/datetime.now().strftime('showcase-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True,exist_ok=False)
    code=Path(a.code).resolve();check=loop.read_json(a.check)
    heading('LIVE DEMO' if a.live else 'OFFLINE: actual code execution, recorded model decisions')
    print('Starting code: '+str(code),flush=True)
    print('Supplied candidate; results are computed from its execution.' if custom else 'The bundled starting code is an unchanged real Luna output; this does not regenerate the original failure.',flush=True)
    heading('1. RUN THE STARTING CODE')
    before_probe=probe(code) if not custom else None
    before_tests=loop.run_tests(a.test,code,out)
    before_counts=show_tests(before_tests,out)
    heading('2. THE SOL-AUTHORED CHECK')
    print('Applicability: '+check['questions']['applicability']['instructions'],flush=True)
    print('Violation: '+check['questions']['violation']['instructions'],flush=True)
    print('Feedback: '+check['feedback'],flush=True)
    print('This check is supplied as a file; reviewer discovery is recorded, not rerun here.',flush=True)
    if a.live:
        heading('3. CALL JEV THROUGH THE NATIVE FAILPROOF POLICY — LIVE')
        state=loop.state_from_files(a.task,code,[])
        before=loop.inspect(check,state,out/'before-0','paired',True,True)
        verdict(before)
        if before['decision']!='violation_detected':
            loop.write_json(out/'report.json',{'decision':before['decision'],'results':[before],'reason':'No detected violation; no repair forced.'})
            print('STOP: no confirmed violation. No simulated success or fallback. Evidence: '+str(out),flush=True)
            return 2
        heading('4. FRESH LUNA SESSION EDITS THE CODE — LIVE')
        print('Waiting for GPT-5.6 Luna medium. It receives the task, check feedback and original test output. Usually about a minute; at most four.',flush=True)
        correction=loop.correct_once(a,[check],state,[before],out)
        if not correction.get('candidate'):
            loop.write_json(out/'report.json',{'results':[before],'correction':correction})
            print(json.dumps(correction,indent=2),flush=True);return 2
        repaired=Path(correction['candidate'])
        after=correction['after'][0]
        after_counts=show_tests(correction['independentTests'],out/'correction') if isinstance(correction['independentTests'],list) else None
    else:
        saved=loop.read_json(ROOT/'evidence/ordered-native-repair-v3/report.json')
        before=saved['results'][0]
        heading('3. RECORDED JEV / NATIVE POLICY DECISION (NO API CALL)')
        verdict(before)
        repaired=ROOT/'evidence/ordered-native-repair-v3/correction/candidate.mjs'
        heading('4. EXECUTE THE SAVED LUNA REPAIR NOW')
        repair_out=out/'repaired';repair_out.mkdir()
        after_tests=loop.run_tests(a.test,repaired,repair_out)
        after_counts=show_tests(after_tests,repair_out)
        after=loop.read_json(ROOT/'evidence/ordered-native-final-recheck.json')
        correction={'candidate':str(repaired),'independentTests':after_tests,'scope':'Previously generated code, executed again now.'}
    heading('5. WHAT ACTUALLY CHANGED')
    print(''.join(difflib.unified_diff(code.read_text().splitlines(True),repaired.read_text().splitlines(True),fromfile='original',tofile='Luna repair')),flush=True)
    after_probe=probe(repaired) if not custom else None
    heading('6. FINAL POLICY '+('LIVE RESULT' if a.live else 'RECORDED RESULT'))
    verdict(after)
    report={'kind':'executed_showcase','live':a.live,'decision':after['decision'],'results':[before], 'beforeCounts':before_counts,'afterCounts':after_counts,'beforeProbe':before_probe,'afterProbe':after_probe,'correction':correction}
    loop.write_json(out/'report.json',report)
    print('\nEvidence and actual execution logs: '+str(out),flush=True)
    return 0 if after['decision']=='no_violation_detected' and after_counts and after_counts['total']>0 and after_counts['passed']==after_counts['total'] else 2

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
        print('Demo stopped: '+type(e).__name__+'. No successful outcome claimed.',file=sys.stderr);sys.exit(2)
