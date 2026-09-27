import {readFile} from 'node:fs/promises';
import {compileBatch, aggregate, hashJSON, text, object, NO, YES} from './policy.mjs';

export const ENDPOINT = 'https://app.befailproof.ai/enforcement/v1/jev/systemone';
export const DEADLINE_MS = 6000;
const probability = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;

async function environmentCredential() {
  if (text(process.env.FAILPROOF_API_KEY)) return process.env.FAILPROOF_API_KEY.trim();
  if (text(process.env.FAILPROOF_KEY_FILE)) return (await readFile(process.env.FAILPROOF_KEY_FILE, 'utf8')).trim();
  throw Error('credential_unavailable');
}

export function decide(scores) {
  // Validate before every shortcut. Invalid evidence is not semantic uncertainty.
  if (!object(scores) || !probability(scores.applicability) || !probability(scores.evidenceSufficiency) ||
      !Array.isArray(scores.questions) || !scores.questions.length || !scores.questions.every(probability)) {
    return {decision:'unchecked', reason:'invalid_scores'};
  }
  if (scores.applicability < YES) return {decision:'unchecked', reason:scores.applicability <= NO ? 'inapplicable' : 'applicability_uncertain'};
  if (scores.evidenceSufficiency < YES) return {decision:'unchecked', reason:scores.evidenceSufficiency <= NO ? 'insufficient_evidence' : 'evidence_uncertain'};
  if (scores.questions.some(value => value <= NO)) return {decision:'no_concern_detected', reason:'conjunction_negative'};
  if (scores.questions.every(value => value >= YES)) return {decision:'advisory', reason:'conjunction_positive'};
  return {decision:'tentative', reason:'conjunction_uncertain'};
}

export function initialResult(compiled) {
  return {schemaVersion:1, decision:['invalid_pair','pair_too_large','invalid_policies'].includes(compiled.reason)
    ? 'unchecked' : aggregate(compiled.results), results:compiled.results, suggestions:[], request:null,
    ...(compiled.reason ? {reason:compiled.reason} : {}), thresholds:{no:NO, yes:YES}};
}

export async function evaluate(policies, pair, options = {}) {
  const {timeoutMs=DEADLINE_MS, fetchImpl=globalThis.fetch, credentialProvider=environmentCredential} = options;
  const started = Date.now();
  const compiled = compileBatch(policies, pair);
  const result = initialResult(compiled);
  const finish = () => {
    result.decision = result.suggestions.length ? 'advisory' : result.results.length ? aggregate(result.results) : result.decision;
    result.elapsedMs = Date.now() - started;
    return result;
  };
  if (!compiled.request) return finish();
  const fail = reason => {
    result.reason = reason;
    result.suggestions = [];
    for (const entry of compiled.entries) Object.assign(result.results[entry.policyIndex], {decision:'unchecked', reason});
  };
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > DEADLINE_MS) { fail('invalid_timeout'); return finish(); }
  const controller = new AbortController();
  let timer;
  let accepting = true;
  try {
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => { accepting=false; controller.abort(); reject(Error('request_timeout')); }, timeoutMs);
    });
    const work = (async () => {
      let key;
      try { key = await credentialProvider(); }
      catch { throw Error('credential_unavailable'); }
      if (!accepting) return;
      if (!text(key)) throw Error('credential_unavailable');
      // Save the parsed actual serialized body, never headers or credentials.
      result.request = JSON.parse(compiled.serialized);
      result.requestHash = hashJSON(result.request);
      const response = await fetchImpl(ENDPOINT, {method:'POST', redirect:'error', signal:controller.signal,
        headers:{Authorization:`Bearer ${key}`, 'Content-Type':'application/json'}, body:compiled.serialized});
      if (!accepting) return;
      if (Number.isInteger(response.status)) result.httpStatus = response.status;
      if (!response.ok) { fail('api_error'); return; }
      const body = await response.json();
      if (!accepting) return;
      const answer = key => {
        const value = object(body?.answers) && Object.hasOwn(body.answers,key) ? body.answers[key] : null;
        return object(value) && (value.type === undefined || value.type === 'noul') && probability(value.noul) ? value.noul : null;
      };
      for (const entry of compiled.entries) {
        const scores = {applicability:answer(entry.keys.applicability), evidenceSufficiency:answer(entry.keys.evidenceSufficiency), questions:entry.keys.questions.map(answer)};
        const item = result.results[entry.policyIndex];
        Object.assign(item, {scores}, decide(scores));
        if (['advisory','tentative'].includes(item.decision)) result.suggestions.push({policyIndex:item.policyIndex,
          id:item.id, version:item.version, level:item.decision, feedback:entry.feedback});
      }
    })();
    await Promise.race([work, timeout]);
  } catch (error) {
    fail(!accepting ? 'request_timeout' : error?.message === 'credential_unavailable' ? 'credential_unavailable' : 'transport_or_response_error');
    // Never log service bodies, exception messages or answer free text.
  } finally { accepting=false; clearTimeout(timer); }
  return finish();
}
