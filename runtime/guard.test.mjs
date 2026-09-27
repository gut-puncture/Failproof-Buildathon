import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluate, decide, ENDPOINT} from './guard.mjs';
import {validatePolicy, validatePair, compileBatch, hashJSON, MAX_PAIR_BYTES, MAX_POLICY_BYTES} from './policy.mjs';

const question = {instructions:'Does the response remove an explicit uncertainty from the supplied source?',
  criteria:{true:'The same source uncertainty is stated as settled.',false:'The uncertainty is retained or resolved explicitly by the source.'}};
const policy = {schemaVersion:1, id:'preserve-uncertainty', version:1, principle:'Preserve explicit source uncertainty.',
  applicability:question, evidenceSufficiency:question, questions:[question,question],
  feedback:'If the response overstates a supplied source, preserve that uncertainty or explain why it is resolved.'};
const pair = {human_message:'  Summarize this:\nThe launch may move. 🟢\n',worker_response:'The launch will move.\n '};
const response = answers => ({ok:true,status:200,json:async () => ({answers})});
const opts = {credentialProvider:async () => 'test-placeholder'};
const answersFor = (request, value=0.9) => Object.fromEntries(Object.keys(request.questions).map(key => [key,{type:'noul',noul:value}]));
const noAccess = {credentialProvider:() => assert.fail('credentials must not be accessed'),fetchImpl:() => assert.fail('network must not be accessed')};

test('strict policy schema excludes executable/legacy fields and accepts any nonempty concern count within byte limit', () => {
  assert.equal(validatePolicy(policy).valid,true);
  assert.equal(validatePolicy({...policy,questions:Array(7).fill(question)}).questionCount,7);
  const invalid = [null,[],{}, {...policy,schemaVersion:2},{...policy,id:'UpperCase'}, {...policy,version:1.2},
    {...policy,version:0},{...policy,feedback:' '},{...policy,extra:true},{...policy,questions:[]},
    {...policy,applicability:{...question,type:'noul'}},{...policy,questions:[{...question,criteria:{...question.criteria,maybe:'?'}}]},
    {...policy,questions:[{instructions:'x',criteria:{true:'yes',false:''}}]}];
  for (const item of invalid) assert.equal(validatePolicy(item).valid,false);
  assert.equal(validatePolicy({...policy,feedback:'x'.repeat(MAX_POLICY_BYTES)}).reason,'policy_too_large');
  assert.equal(validatePolicy(policy).policyHash,hashJSON(policy));
});

test('exact pair serialization preserves all text and excludes provenance and metadata from one indexed batch', async () => {
  let count=0;
  const policies=[null,policy,{...policy,id:'other-principle',version:3}];
  const result=await evaluate(policies,pair,{...opts,fetchImpl:async (url,options) => {
    count++;
    assert.equal(url,ENDPOINT); assert.equal(options.redirect,'error');
    const request=JSON.parse(options.body);
    assert.deepEqual(Object.keys(request),['model','state','questions']);
    assert.deepEqual(request.state,pair);
    assert.deepEqual(Object.keys(request.questions),['p1_applicability','p1_evidence_sufficiency','p1_q0','p1_q1',
      'p2_applicability','p2_evidence_sufficiency','p2_q0','p2_q1']);
    assert.equal(options.body.includes(policy.id),false); assert.equal(options.body.includes(policy.feedback),false);
    return response(answersFor(request));
  }});
  assert.equal(count,1); assert.equal(result.decision,'advisory');
  assert.equal(result.results[0].decision,'unchecked');
  assert.deepEqual(result.suggestions.map(item=>item.policyIndex),[1,2]);
  assert.deepEqual(result.request.state,pair); assert.equal(result.requestHash,hashJSON(result.request));
  assert.equal(JSON.stringify(result).includes('test-placeholder'),false);
});

test('empty, invalid, conflicting, or missing/oversized evidence performs no credential or network work', async () => {
  assert.equal((await evaluate([],pair,noAccess)).decision,'quiet');
  assert.equal((await evaluate([null],pair,noAccess)).results[0].decision,'unchecked');
  assert.equal((await evaluate([policy,{...policy,version:2}],pair,noAccess)).results[0].reason,'conflicting_policy_identity');
  for (const input of [null,{...pair,notes:'extra'}, {...pair,worker_response:' '},{human_message:'x'}]) {
    assert.equal(validatePair(input).valid,false);
    assert.equal((await evaluate([policy],input,noAccess)).reason,'invalid_pair');
  }
  assert.equal((await evaluate([policy],{...pair,human_message:'x'.repeat(MAX_PAIR_BYTES)},noAccess)).reason,'pair_too_large');
  const large={...policy,questions:[{...question,instructions:'x'.repeat(50000)}]};
  const collection=Array.from({length:11},(_,index)=>({...large,id:`policy-${index}`}));
  assert.equal((await evaluate(collection,pair,noAccess)).reason,'request_too_large');
});

test('conflicting identities are isolated while an independent policy is evaluated',async () => {
  const result=await evaluate([policy,{...policy,version:2},{...policy,id:'independent'}],pair,{...opts,fetchImpl:async(_,options)=>{
    const request=JSON.parse(options.body);
    assert.ok(Object.keys(request.questions).every(key=>key.startsWith('p2_')));
    return response(answersFor(request));
  }});
  assert.deepEqual(result.results.map(row=>row.decision),['unchecked','unchecked','advisory']);
});

test('fixed thresholds gate applicability and evidence, then AND; every score validates before a shortcut', () => {
  const scores=(questions,applicability=.8,evidenceSufficiency=.8)=>({applicability,evidenceSufficiency,questions});
  assert.equal(decide(scores([.8,1])).decision,'advisory');
  assert.equal(decide(scores([.8,.21])).decision,'tentative');
  assert.equal(decide(scores([.8,.2])).decision,'no_concern_detected');
  assert.equal(decide(scores([.2,.5])).decision,'no_concern_detected');
  assert.equal(decide(scores([1],.2)).reason,'inapplicable');
  assert.equal(decide(scores([1],.79)).reason,'applicability_uncertain');
  assert.equal(decide(scores([1],1,.2)).reason,'insufficient_evidence');
  assert.equal(decide(scores([1],1,.79)).reason,'evidence_uncertain');
  for (const bad of [undefined,null,NaN,Infinity,-.1,1.1,'1']) {
    assert.equal(decide(scores([.1,bad],.1)).reason,'invalid_scores');
    assert.equal(decide(scores([.1,bad])).reason,'invalid_scores');
  }
  assert.equal(decide(null).decision,'unchecked');
  assert.equal(decide(scores([])).decision,'unchecked');
});

test('partial/malformed answers invalidate only affected policy even if another answer is a definite no',async () => {
  const result=await evaluate([policy,{...policy,id:'independent'}],pair,{...opts,fetchImpl:async(_,options)=>{
    const answers=answersFor(JSON.parse(options.body));
    answers.p0_applicability.noul=.1;
    delete answers.p0_q1;
    answers.p1_q0.noul=.5;
    return response(answers);
  }});
  assert.equal(result.results[0].reason,'invalid_scores');
  assert.equal(result.results[1].decision,'tentative');
  assert.equal(result.suggestions[0].level,'tentative');
  assert.equal(result.decision,'advisory');
  for (const value of [true,'1',2,-1,null]) {
    const invalid=await evaluate([policy],pair,{...opts,fetchImpl:async(_,options)=>{
      const answers=answersFor(JSON.parse(options.body)); answers.p0_q1.noul=value; return response(answers);
    }});
    assert.equal(invalid.results[0].reason,'invalid_scores');
  }
});

test('API/transport errors and malicious free text do not leak into saved result',async () => {
  const failed=await evaluate([policy],pair,{...opts,fetchImpl:async()=>({ok:false,status:500,json:()=>assert.fail('do not read errors')})});
  assert.equal(failed.reason,'api_error'); assert.equal(failed.requestHash,hashJSON(failed.request));
  const thrown=await evaluate([policy],pair,{...opts,fetchImpl:async()=>{throw Error('SECRET_ERROR_BODY');}});
  assert.equal(thrown.reason,'transport_or_response_error');
  assert.equal(JSON.stringify(thrown).includes('SECRET_ERROR_BODY'),false);
  const freeText=await evaluate([policy],pair,{...opts,fetchImpl:async(_,options)=>{
    const answers=answersFor(JSON.parse(options.body)); answers.p0_q0.explanation='SECRET_ERROR_BODY';return response(answers);
  }});
  assert.equal(JSON.stringify(freeText).includes('SECRET_ERROR_BODY'),false);
});

test('credential, fetch and body parsing share a deadline; late completions cannot mutate or start fetch',async () => {
  let releaseCredential;
  const credential=await evaluate([policy],pair,{timeoutMs:15,credentialProvider:()=>new Promise(resolve=>{releaseCredential=resolve;}),fetchImpl:noAccess.fetchImpl});
  assert.equal(credential.reason,'request_timeout'); assert.equal(credential.request,null);
  releaseCredential('late-key');
  await new Promise(resolve=>setTimeout(resolve,5));
  for (const phase of ['fetch','body']) {
    let release;
    const fetchImpl=phase==='fetch' ? ()=>new Promise(resolve=>{release=resolve;}) : async()=>({ok:true,status:200,json:()=>new Promise(resolve=>{release=resolve;})});
    const result=await evaluate([policy],pair,{...opts,timeoutMs:15,fetchImpl});
    const saved=JSON.stringify(result);
    assert.equal(result.reason,'request_timeout');
    release(phase==='fetch'?response({}):{answers:{}});
    await new Promise(resolve=>setTimeout(resolve,5));
    assert.equal(JSON.stringify(result),saved);
  }
  const aborting=await evaluate([policy],pair,{...opts,timeoutMs:15,fetchImpl:(_,options)=>new Promise((_,reject)=>{
    options.signal.addEventListener('abort',()=>reject(new Error('aborted')));
  })});
  assert.equal(aborting.reason,'request_timeout');
});

test('timeouts cannot exceed the native callback budget; rejected credentials are quiet',async () => {
  for(const timeoutMs of [0,-1,6001,NaN]) assert.equal((await evaluate([policy],pair,{...noAccess,timeoutMs})).reason,'invalid_timeout');
  const result=await evaluate([policy],pair,{credentialProvider:async()=>{throw Error('PRIVATE_FILE_PATH');},fetchImpl:noAccess.fetchImpl});
  assert.equal(result.reason,'credential_unavailable'); assert.equal(result.request,null);
  assert.equal(JSON.stringify(result).includes('PRIVATE_FILE_PATH'),false);
});
