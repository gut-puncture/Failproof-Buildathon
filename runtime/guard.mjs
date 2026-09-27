import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const ENDPOINT = 'https://app.befailproof.ai/enforcement/v1/jev/systemone';
const MODEL = 'jev-1.13.0';
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const text = value => typeof value === 'string' && value.trim().length > 0;
const probability = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
const fields = ['task','implementation','observation'];

async function environmentCredential() {
  if (text(process.env.FAILPROOF_API_KEY)) return process.env.FAILPROOF_API_KEY.trim();
  if (text(process.env.FAILPROOF_KEY_FILE)) return (await readFile(process.env.FAILPROOF_KEY_FILE, 'utf8')).trim();
  throw Error('credential_unavailable');
}

function prepare(check, state, mode, positive, negative) {
  if (!['paired','single'].includes(mode)) throw Error('invalid_mode');
  if (!probability(positive) || !probability(negative) || negative >= positive) throw Error('invalid_thresholds');
  if (!check || !text(check.id) || !['string','number'].includes(typeof check.version)) throw Error('invalid_check_identity');
  const required = check.requiredInputs;
  const optional = check.optionalInputs ?? [];
  if (!Array.isArray(required) || !required.includes('task') || !required.includes('implementation') ||
      !Array.isArray(optional) || [...required,...optional].some(k => !fields.includes(k))) throw Error('invalid_input_declarations');
  if (!state || required.some(k => !text(state[k]))) throw Error('missing_required_context');
  if (state.observation !== undefined && ![...required,...optional].includes('observation')) throw Error('undeclared_observation');
  const evidence = {};
  for (const key of new Set([...required,...optional])) {
    if (state[key] !== undefined) {
      if (!text(state[key])) throw Error('invalid_context');
      evidence[key] = state[key];
    }
  }
  const names = mode === 'paired' ? ['applicability','violation'] : ['single'];
  const questions = {};
  for (const name of names) {
    const q = check.questions?.[name];
    if (!q || (q.type !== undefined && q.type !== 'noul') || !text(q.instructions) ||
        !text(q.criteria?.true) || !text(q.criteria?.false) ||
        Object.keys(q).some(k => !['type','instructions','criteria'].includes(k)) ||
        Object.keys(q.criteria).some(k => !['true','false'].includes(k))) throw Error('invalid_question');
    questions[name] = {type:'noul', instructions:q.instructions, criteria:{true:q.criteria.true,false:q.criteria.false}};
  }
  return {model:MODEL,state:evidence,questions};
}

export function decide(scores, {mode='paired', positive=0.8, negative=0.2}={}) {
  if (!scores || typeof scores !== 'object' || !['paired','single'].includes(mode) || !probability(positive) || !probability(negative) || negative >= positive ||
      (mode === 'paired' && !probability(scores.applicability))) return {decision:'unchecked',reason:'invalid_scores_or_configuration'};
  if (mode === 'paired') {
    if (scores.applicability <= negative) return {decision:'not_applicable',reason:'applicability_negative'};
    if (scores.applicability < positive) return {decision:'unchecked',reason:'applicability_ambiguous'};
  }
  const value = scores[mode === 'paired' ? 'violation' : 'single'];
  if (!probability(value)) return {decision:'unchecked',reason:'invalid_violation_score'};
  if (value >= positive) return {decision:'violation_detected',reason:'violation_positive'};
  if (value <= negative) return {decision:'no_violation_detected',reason:'violation_negative'};
  return {decision:'unchecked',reason:'violation_ambiguous'};
}

export async function evaluate(check, state, options={}) {
  const {mode='paired',positive=check?.thresholds?.positive ?? 0.8,negative=check?.thresholds?.negative ?? 0.2,timeoutMs=20000,fetchImpl=globalThis.fetch,
    credentialProvider=environmentCredential}=options;
  const started=Date.now();
  const result={checkId:check?.id,version:check?.version,checkHash:hash(check ?? null),timestamp:new Date().toISOString(),
    mode,thresholds:{positive,negative},decision:'unchecked',scores:{},rawScores:{},reasons:{},
    scope:'One candidate semantic check; no claim that the entire implementation is correct.'};
  let request;
  try {
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw Error('invalid_timeout');
    request=prepare(check,state,mode,positive,negative);
  }
  catch(error) { return {...result,reason:error.message,elapsedMs:Date.now()-started}; }
  result.requestHash=hash(request);
  const controller=new AbortController();
  let timer;
  let accepting=true;
  try {
    const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{accepting=false;controller.abort();reject(Error('request_timeout'));},timeoutMs);});
    const work=(async()=>{
      const key=await credentialProvider();
      if (!accepting) return;
      if (!text(key)) throw Error('credential_unavailable');
      const response=await fetchImpl(ENDPOINT,{method:'POST',redirect:'error',signal:controller.signal,
        headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify(request)});
      if (!accepting) return;
      result.httpStatus=response.status;
      if (!response.ok) { result.reason='api_error'; return; }
      const body=await response.json();
      if (!accepting) return;
      for (const name of Object.keys(request.questions)) {
        const answer=body.answers?.[name];
        result.rawScores[name]=typeof answer?.noul==='number'?answer.noul:null;
        result.scores[name]=probability(answer?.noul)?answer.noul:null;
        for (const key of ['reason','explanation']) if (typeof answer?.[key]==='string') result.reasons[name]=answer[key];
      }
      Object.assign(result,decide(result.scores,{mode,positive,negative}));
    })();
    await Promise.race([work,timeout]);
  } catch(error) {
    result.decision='unchecked';
    result.reason=['request_timeout','credential_unavailable'].includes(error.message)?error.message:'transport_or_response_error';
    // Never serialize exception messages, response bodies, headers or credentials.
  } finally { accepting=false; clearTimeout(timer); result.elapsedMs=Date.now()-started; }
  return result;
}

export function summarize(results) {
  const summary={total:results.length,missedBugs:0,falseAlarms:0,unchecked:0,notApplicable:0,
    applicablePositive:0,applicableNegative:0,applicableAmbiguous:0,applicabilityMismatches:0};
  for (const r of results) {
    if (r.expectedViolation===true && ['no_violation_detected','not_applicable'].includes(r.decision)) summary.missedBugs++;
    if (r.expectedViolation===false && r.decision==='violation_detected') summary.falseAlarms++;
    if (r.decision==='unchecked') summary.unchecked++;
    if (r.decision==='not_applicable') summary.notApplicable++;
    if (r.mode==='paired' && probability(r.scores.applicability)) {
      const a=r.scores.applicability>=r.thresholds.positive?true:r.scores.applicability<=r.thresholds.negative?false:null;
      summary[a===true?'applicablePositive':a===false?'applicableNegative':'applicableAmbiguous']++;
      if (typeof r.expectedApplicable==='boolean' && a!==null && a!==r.expectedApplicable) summary.applicabilityMismatches++;
    }
  }
  return summary;
}

async function cli() {
  const [checkPath,inputPath,outputPath,...rest]=process.argv.slice(2);
  if (!checkPath || !inputPath || !outputPath) throw Error('Usage: node guard.mjs CHECK.json STATE_OR_MANIFEST.json OUTPUT.json [--mode paired|single] [--positive 0.8] [--negative 0.2]');
  const options={};
  for (let i=0;i<rest.length;i+=2) {
    const key=rest[i]; const value=rest[i+1];
    if (!['--mode','--positive','--negative'].includes(key) || value===undefined) throw Error('Invalid CLI option');
    options[key.slice(2)]=key==='--mode'?value:Number(value);
  }
  const check=JSON.parse(await readFile(checkPath,'utf8'));
  const input=JSON.parse(await readFile(inputPath,'utf8'));
  let output;
  if (Array.isArray(input.fixtures)) {
    const results=[];
    for (const fixture of input.fixtures) results.push({...await evaluate(check,fixture.state,options),fixtureId:fixture.id,
      expectedViolation:fixture.expectedViolation,expectedApplicable:fixture.expectedApplicable});
    output={results,summary:summarize(results)};
  } else output=await evaluate(check,input,options);
  await mkdir(dirname(resolve(outputPath)),{recursive:true});
  await writeFile(outputPath,JSON.stringify(output,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify(output.summary ?? {decision:output.decision,reason:output.reason,output:resolve(outputPath)}));
}
if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) cli().catch(()=>{
  console.error('Guard failed before saving output. Check local paths, schema and CLI arguments. No credential details logged.');process.exitCode=1;
});
