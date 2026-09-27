import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';import {resolve} from 'node:path';
const {importRows}=await import(process.argv[2]?pathToFileURL(resolve(process.argv[2])):new URL('./reference.mjs',import.meta.url));
const tests=[];const test=(name,fn)=>tests.push({name,fn});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const flush=async()=>{for(let i=0;i<50;i++)await Promise.resolve();};
const watch=promise=>{const state={status:'pending'};promise.then(value=>Object.assign(state,{status:'fulfilled',value}),error=>Object.assign(state,{status:'rejected',error}));return state;};
test('configuration and empty input invoke no callbacks',async()=>{
  for(const concurrency of [0,-1,1.5,NaN,Infinity,'2']){const s=watch(importRows([],{prepare:()=>assert.fail(),commit:()=>assert.fail(),concurrency}));await flush();assert.ok(s.error instanceof RangeError);}
  const s=watch(importRows([],{prepare:()=>assert.fail(),commit:()=>assert.fail(),concurrency:2}));await flush();assert.deepEqual(s.value,[]);
});
test('preparation refills while commit is pending; commits never overlap',async()=>{
  const p=Array.from({length:5},deferred),c=Array.from({length:5},deferred);const starts=[],commits=[];
  const s=watch(importRows([0,1,2,3,4],{concurrency:2,prepare:(x,i)=>{starts.push(i);return p[i].promise;},commit:(x,i)=>{commits.push([i,x]);return c[i].promise;}}));
  assert.deepEqual(starts,[0,1]);p[0].resolve('a');await flush();assert.deepEqual(starts,[0,1,2]);assert.deepEqual(commits,[[0,'a']]);
  p[1].resolve('b');p[2].resolve('c');await flush();assert.deepEqual(starts,[0,1,2,3,4]);assert.equal(commits.length,1);
  p[3].resolve('d');p[4].resolve('e');await flush();
  for(let i=0;i<5;i++){assert.equal(commits.length,i+1);c[i].resolve(i*10);await flush();}
  assert.deepEqual(s.value,[0,10,20,30,40]);assert.deepEqual(commits,[[0,'a'],[1,'b'],[2,'c'],[3,'d'],[4,'e']]);
});
test('later preparation failure still commits earlier prefix then waits for started tail',async()=>{
  const p=Array.from({length:4},deferred);const starts=[],commits=[];const error=new Error('index two');
  const s=watch(importRows([0,1,2,3,4],{concurrency:4,prepare:(x,i)=>{starts.push(i);return p[i].promise;},commit:(x,i)=>{commits.push(i);return x;}}));
  p[2].reject(error);await flush();assert.deepEqual(starts,[0,1,2,3]);assert.equal(s.status,'pending');
  p[1].resolve('one');p[0].resolve('zero');await flush();assert.deepEqual(commits,[0,1]);assert.equal(s.status,'pending');
  p[3].resolve('three');await flush();assert.equal(s.error,error);assert.deepEqual(commits,[0,1]);
});
test('earliest input failure wins rather than first rejection in time',async()=>{
  const p=Array.from({length:4},deferred);const earlier=new Error('earlier'),later=new Error('later');const commits=[];
  const s=watch(importRows([0,1,2,3],{concurrency:4,prepare:(x,i)=>p[i].promise,commit:(x,i)=>commits.push(i)}));
  p[3].reject(later);p[1].reject(earlier);p[2].resolve(2);p[0].resolve(0);await flush();
  assert.equal(s.error,earlier);assert.deepEqual(commits,[0]);
});
test('earlier commit failure overrides later preparation failure',async()=>{
  const p=Array.from({length:3},deferred),c=deferred();const ce=new Error('commit'),pe=new Error('prepare');const commits=[];
  const s=watch(importRows([0,1,2],{concurrency:3,prepare:(x,i)=>p[i].promise,commit:(x,i)=>{commits.push(i);return c.promise;}}));
  p[0].resolve(0);await flush();p[2].reject(pe);c.reject(ce);await flush();assert.equal(s.status,'pending');
  p[1].reject(new Error('middle'));await flush();assert.equal(s.error,ce);assert.deepEqual(commits,[0]);
});
test('commit failure stops new starts and consumes late preparation rejection',async()=>{
  const p=Array.from({length:3},deferred);const starts=[],commits=[];const error=new Error('commit failure');
  const s=watch(importRows([0,1,2,3],{concurrency:2,prepare:(x,i)=>{starts.push(i);return p[i].promise;},commit:(x,i)=>{commits.push(i);throw error;}}));
  p[0].resolve(0);await flush();assert.ok(starts.length===2||starts.length===3);const startedAtFailure=[...starts];assert.equal(s.status,'pending');
  p[1].reject(new Error('late'));p[2].resolve(2);await flush();assert.equal(s.error,error);assert.deepEqual(commits,[0]);assert.deepEqual(starts,startedAtFailure);
});
test('synchronous preparation throw settles through promises and preserves original error',async()=>{
  const starts=[];const error=new Error('sync');const s=watch(importRows([0,1,2],{concurrency:2,prepare:(x,i)=>{starts.push(i);if(i===0)throw error;return x;},commit:()=>assert.fail('no prefix')}));
  assert.deepEqual(starts,[0,1]);assert.equal(s.status,'pending');await flush();assert.equal(s.error,error);assert.deepEqual(starts,[0,1]);
});
test('all success preserves exact prepared values and commit output order',async()=>{
  const prepared=[false,0,undefined,null];const received=[];const rows=[{id:1},{id:2},{id:3},{id:4}];const before=structuredClone(rows);
  const s=watch(importRows(rows,{concurrency:3,prepare:(x,i)=>prepared[i],commit:(x,i)=>{received.push(x);return 'done'+i;}}));await flush();
  assert.deepEqual(received,prepared);assert.deepEqual(s.value,['done0','done1','done2','done3']);assert.deepEqual(rows,before);
});
test('independent imports launched synchronously from callbacks have separate state',async()=>{
  let nested;const s=watch(importRows([1,2],{concurrency:1,prepare:x=>{if(x===1)nested=watch(importRows([10,20],{concurrency:2,prepare:y=>y+1,commit:y=>y*2}));return x;},commit:x=>x+1}));
  await flush();assert.deepEqual(s.value,[2,3]);assert.deepEqual(nested.value,[22,42]);
});
let failed=0;for(const{name,fn}of tests){try{await fn();console.log(JSON.stringify({name,passed:true}));}catch(error){failed++;console.log(JSON.stringify({name,passed:false,error:error.stack}));}}
console.log(JSON.stringify({summary:{total:tests.length,passed:tests.length-failed,failed}}));process.exitCode=failed?1:0;
