import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluate,decide,summarize} from './guard.mjs';
const q={type:'noul',instructions:'A narrow semantic question.',criteria:{true:'Present',false:'Absent'}};
const check={id:'test',version:1,requiredInputs:['task','implementation'],questions:{applicability:q,violation:q,single:q}};
const state={task:'Preserve independent identities.',implementation:'function demo() {}'};
const opts={credentialProvider:async()=>'mock-only-not-a-real-key'};
const response=answers=>({ok:true,status:200,json:async()=>({answers})});
test('paired batches independent questions in one request; single switches without changing package',async()=>{
  let calls=0;
  const fetchImpl=async(_,options)=>{
    calls++; const request=JSON.parse(options.body);
    if (request.questions.single) {assert.deepEqual(Object.keys(request.questions),['single']);return response({single:{noul:0.1}});}
    assert.deepEqual(Object.keys(request.questions),['applicability','violation']);
    return response({applicability:{noul:0.9},violation:{noul:0.95,reason:'Observed mismatch'}});
  };
  const paired=await evaluate(check,state,{...opts,fetchImpl});
  assert.equal(paired.decision,'violation_detected');assert.equal(calls,1);
  assert.equal(paired.reasons.violation,'Observed mismatch');assert.ok(paired.requestHash);
  const single=await evaluate(check,state,{...opts,fetchImpl,mode:'single'});
  assert.equal(single.decision,'no_violation_detected');assert.equal(calls,2);
});
test('applicability gates independently; ambiguous or invalid scores remain unchecked',()=>{
  assert.equal(decide({applicability:0.1,violation:0.99}).decision,'not_applicable');
  assert.equal(decide({applicability:0.5,violation:0.99}).decision,'unchecked');
  assert.equal(decide({applicability:0.9,violation:0.5}).decision,'unchecked');
  assert.equal(decide({applicability:0.9,violation:0.2}).decision,'no_violation_detected');
  assert.equal(decide({applicability:0.1,violation:NaN}).decision,'not_applicable');
  assert.equal(decide({applicability:0.9,violation:NaN}).decision,'unchecked');
});
test('negative applicability discards missing violation and package thresholds apply unless overridden',async()=>{
  const negative=await evaluate(check,state,{...opts,fetchImpl:async()=>response({applicability:{noul:0.1}})});
  assert.equal(negative.decision,'not_applicable');
  const configured={...check,thresholds:{positive:0.9,negative:0.1}};
  const fetchImpl=async()=>response({applicability:{noul:0.85},violation:{noul:0.95}});
  assert.equal((await evaluate(configured,state,{...opts,fetchImpl})).decision,'unchecked');
  assert.equal((await evaluate(configured,state,{...opts,fetchImpl,positive:0.8})).decision,'violation_detected');
});
test('missing context and undeclared observations perform no API call',async()=>{
  const fetchImpl=async()=>assert.fail('No API call should occur');
  assert.equal((await evaluate(check,{task:'x'},{...opts,fetchImpl})).reason,'missing_required_context');
  assert.equal((await evaluate(check,{...state,observation:'extra'},{...opts,fetchImpl})).reason,'undeclared_observation');
  const optional={...check,optionalInputs:['observation']};
  const result=await evaluate(optional,state,{...opts,fetchImpl:async()=>response({applicability:{noul:0.9},violation:{noul:0.1}})});
  assert.equal(result.decision,'no_violation_detected');
});
test('API error, malformed scores and timeout are unchecked without error body leakage',async()=>{
  const api=await evaluate(check,state,{...opts,fetchImpl:async()=>({ok:false,status:500,json:()=>assert.fail('Do not read error body')})});
  assert.equal(api.decision,'unchecked');assert.equal(api.reason,'api_error');
  const invalid=await evaluate(check,state,{...opts,fetchImpl:async()=>response({applicability:{noul:1},violation:{noul:5}})});
  assert.equal(invalid.decision,'unchecked');assert.equal(invalid.rawScores.violation,5);
  const timed=await evaluate(check,state,{...opts,timeoutMs:5,fetchImpl:()=>new Promise(()=>{})});
  assert.equal(timed.decision,'unchecked');assert.equal(timed.reason,'request_timeout');
  const thrown=await evaluate(check,state,{...opts,fetchImpl:async()=>{throw Error('private-error-content');}});
  assert.equal(thrown.decision,'unchecked');assert.ok(!JSON.stringify(thrown).includes('private-error-content'));
});
test('late response cannot mutate a timed-out result',async()=>{
  let release;
  const fetchImpl=()=>new Promise(resolve=>{release=resolve;});
  const result=await evaluate(check,state,{...opts,timeoutMs:5,fetchImpl});
  const snapshot=JSON.stringify(result);
  release(response({applicability:{noul:1},violation:{noul:1}}));
  await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(JSON.stringify(result),snapshot);
});
test('summary distinguishes misses, false alarms, abstentions and applicability',()=>{
  const make=(decision,expectedViolation,a)=>({decision,expectedViolation,mode:'paired',scores:{applicability:a},thresholds:{positive:.8,negative:.2}});
  const summary=summarize([make('not_applicable',true,.1),make('violation_detected',false,.9),make('unchecked',true,.5)]);
  assert.equal(summary.missedBugs,1);assert.equal(summary.falseAlarms,1);assert.equal(summary.unchecked,1);assert.equal(summary.notApplicable,1);
});
test('credential acquisition shares timeout and late credentials never initiate fetch', async()=>{
  let release; let calls=0;
  const provider = () => new Promise(resolve=>{release=resolve;});
  const result=await evaluate(check,state,{credentialProvider:provider,timeoutMs:5,
    fetchImpl:async()=>{calls++;return response({applicability:{noul:1},violation:{noul:0}});}});
  assert.equal(result.decision,'unchecked');
  assert.equal(result.reason,'request_timeout');
  release('mock-key');
  await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(calls,0);
});
test('invalid timeout and missing scores fail closed', async()=>{
  assert.equal(decide(null).decision,'unchecked');
  assert.equal(decide(undefined).decision,'unchecked');
  const result=await evaluate(check,state,{...opts,timeoutMs:0,fetchImpl:()=>assert.fail('must not request')});
  assert.equal(result.reason,'invalid_timeout');
});
