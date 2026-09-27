import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {runNative,verifyNative} from './gate.mjs';
import {hashJSON} from '../runtime/policy.mjs';

const question={instructions:'Does the response contradict an explicit supplied constraint?',criteria:{true:'It contradicts the supplied constraint.',false:'It preserves the supplied constraint.'}};
const policy={schemaVersion:1,id:'preserve-constraints',version:1,principle:'Preserve explicit constraints.',applicability:question,
  evidenceSufficiency:question,questions:[question],feedback:'Review the supplied constraint and correct the response or explain the apparent mismatch.'};
const input={pair:{human_message:'Preserve two items.',worker_response:'One item.'},policies:[policy]};
const cleanEnv=()=>{
  const env={...process.env};
  delete env.FAILPROOF_API_KEY;delete env.FAILPROOF_KEY_FILE;delete env.FAILPROOFAI_CLI;delete env.NODE_OPTIONS;
  return env;
};

async function fixture(t) {
  const dir=await mkdtemp(join(tmpdir(),'jev-native-test-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  return dir;
}

test('bare SDK allows, stale attestation, mismatched input/decision, wrong event and nonzero exits never verify',()=>{
  const receipt={schemaVersion:1,decision:'quiet',results:[],suggestions:[],nativeAttestation:'nonce',inputHash:'hash',policyDecision:'allow'};
  const executed={exitCode:0,stdout:JSON.stringify({hookSpecificOutput:{hookEventName:'PreToolUse',additionalContext:'Note from failproofai: jev_advisory_gate:nonce:allow'}})};
  assert.equal(verifyNative(receipt,executed,'nonce','hash'),true);
  assert.equal(verifyNative(receipt,{exitCode:0,stdout:'{}'},'nonce','hash'),false);
  assert.equal(verifyNative(receipt,executed,'old','hash'),false);
  assert.equal(verifyNative(receipt,executed,'nonce','wrong'),false);
  assert.equal(verifyNative({...receipt,policyDecision:'deny'},executed,'nonce','hash'),false);
  assert.equal(verifyNative(receipt,{...executed,exitCode:1},'nonce','hash'),false);
  assert.equal(verifyNative(receipt,{...executed,stdout:executed.stdout.replace('PreToolUse','Stop')},'nonce','hash'),false);
});

test('empty, invalid and missing pairs do not invoke even an unavailable engine',async()=>{
  const options={cliPath:'/path/that/does/not/exist',environment:cleanEnv()};
  const empty=await runNative({...input,policies:[]},options);
  assert.equal(empty.decision,'quiet');assert.equal(empty.nativePolicy.invoked,false);
  const invalid=await runNative({...input,policies:[null]},options);
  assert.equal(invalid.decision,'unchecked');assert.equal(invalid.nativePolicy.invoked,false);
  const missing=await runNative({...input,pair:{human_message:'x'}},options);
  assert.equal(missing.decision,'unchecked');assert.equal(missing.nativePolicy.invoked,false);
  const extra=await runNative({...input,notes:'secret'},options);
  assert.equal(extra.reason,'invalid_input');assert.equal(extra.nativePolicy.invoked,false);
});

test('real installed engine attests quiet unchecked credential failure through native allow',async()=>{
  const result=await runNative(input,{environment:cleanEnv()});
  assert.equal(result.nativePolicy.verified,true,JSON.stringify(result));
  assert.equal(result.nativePolicy.engineDecision,'allow');
  assert.equal(result.decision,'unchecked');assert.equal(result.results[0].reason,'credential_unavailable');
  assert.equal(result.request,null);
});

test('real installed engine runs the maintained wrapper once, batches mocked Jev and attests native deny/allow',async(t)=>{
  const dir=await fixture(t);
  const preload=join(dir,'mock-fetch.mjs');
  const callLog=join(dir,'request-bodies.jsonl');
  const source=`import {appendFile} from 'node:fs/promises'; globalThis.fetch=async(url,options)=>{
    if(url!=='https://app.befailproof.ai/enforcement/v1/jev/systemone') throw Error('unexpected URL');
    const request=JSON.parse(options.body);
    await appendFile(process.env.TEST_REQUEST_LOG,JSON.stringify(request)+'\\n');
    return {ok:true,status:200,json:async()=>({answers:Object.fromEntries(Object.keys(request.questions).map(key=>[key,{type:'noul',noul:key.endsWith('_q0')?Number(process.env.TEST_CONCERN_SCORE):.9}]))})};
  };`;
  await writeFile(preload,source);
  const runtimeBefore=await readFile(resolve('runtime/guard.mjs'),'utf8');
  for(const [score,decision,native] of [[.9,'advisory','deny'],[.5,'advisory','deny'],[.1,'quiet','allow']]) {
    const result=await runNative({...input,policies:[policy,{...policy,id:'second-policy'}]}, {environment:{...cleanEnv(),
      FAILPROOF_API_KEY:'offline-placeholder',NODE_OPTIONS:`--import=${preload}`,TEST_CONCERN_SCORE:String(score),TEST_REQUEST_LOG:callLog}});
    assert.equal(result.nativePolicy.verified,true,JSON.stringify(result));
    assert.equal(result.nativePolicy.engineDecision,native);
    assert.equal(result.decision,decision);
    assert.deepEqual(result.request.state,input.pair);
    assert.equal(Object.keys(result.request.questions).length,6);
    assert.equal(result.requestHash,hashJSON(result.request));
    assert.equal(JSON.stringify(result).includes('offline-placeholder'),false);
    if(native==='deny') assert.equal(result.suggestions[0].level,score===.5?'tentative':'advisory');
  }
  const requests=(await readFile(callLog,'utf8')).trim().split('\n').map(line=>JSON.parse(line));
  assert.equal(requests.length,3); // Exactly one call for each two-policy run.
  assert.ok(requests.every(request=>hashJSON(request)===hashJSON(requests[0])));
  assert.equal(await readFile(resolve('runtime/guard.mjs'),'utf8'),runtimeBefore);
});

test('real installed SDK skipped/throw callbacks remain unverified despite allow-on-error',async(t)=>{
  const dir=await fixture(t);
  for(const [name,source] of [
    ['skipped',`import {customPolicies,allow} from 'failproofai'; customPolicies.add({name:'skip-test',match:{events:['PostToolUse']},fn:()=>allow()});`],
    ['throw',`import {customPolicies} from 'failproofai'; customPolicies.add({name:'throw-test',match:{events:['PreToolUse']},fn:()=>{throw Error('PRIVATE_EXCEPTION');}});`],
  ]) {
    const policyPath=join(dir,`${name}.policies.mjs`);await writeFile(policyPath,source);
    const result=await runNative(input,{policyPath,environment:cleanEnv()});
    assert.equal(result.nativePolicy.invoked,true);
    assert.equal(result.nativePolicy.verified,false,JSON.stringify(result));
    assert.equal(result.decision,'unchecked');assert.equal(result.reason,'native_result_unverified');
    assert.deepEqual(result.suggestions,[]);assert.equal(JSON.stringify(result).includes('PRIVATE_EXCEPTION'),false);
  }
});

test('outer native process deadline kills a stalled child and remains unchecked',async(t)=>{
  const dir=await fixture(t);const cliPath=join(dir,'stalled.mjs');
  await writeFile(cliPath,'setInterval(()=>{},1000);');
  const start=Date.now();
  const result=await runNative(input,{cliPath,environment:cleanEnv(),processTimeoutMs:50});
  assert.equal(result.reason,'native_process_timeout');assert.equal(result.nativePolicy.verified,false);
  assert.ok(Date.now()-start<1000);
});

test('CLI uses exclusive output creation and validator emits metadata only',async(t)=>{
  const dir=await fixture(t);const inputPath=join(dir,'input.json');const outputPath=join(dir,'output.json');
  await writeFile(inputPath,JSON.stringify({...input,policies:[]}));
  const run=()=>spawnSync(process.execPath,['native/gate.mjs',inputPath,outputPath],{encoding:'utf8',env:cleanEnv()});
  assert.equal(run().status,0);const before=await readFile(outputPath,'utf8');assert.equal(run().status,1);
  assert.equal(await readFile(outputPath,'utf8'),before);
  const policyPath=join(dir,'policy.json');await writeFile(policyPath,JSON.stringify(policy));
  const valid=spawnSync(process.execPath,['runtime/policy.mjs','validate',policyPath],{encoding:'utf8'});
  assert.equal(valid.status,0);assert.equal(JSON.parse(valid.stdout).policyHash,hashJSON(policy));
  assert.equal(valid.stdout.includes(policy.feedback),false);
  await writeFile(policyPath,'{');
  const invalid=spawnSync(process.execPath,['runtime/policy.mjs','validate',policyPath],{encoding:'utf8'});
  assert.equal(invalid.status,2);assert.equal(JSON.parse(invalid.stdout).valid,false);
});
