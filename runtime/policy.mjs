import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export const MODEL = 'jev-1.13.0';
export const NO = 0.2;
export const YES = 0.8;
// Local transport safeguards, not claims about the service's context window.
export const MAX_PAIR_BYTES = 128 * 1024;
export const MAX_POLICY_BYTES = 64 * 1024;
export const MAX_REQUEST_BYTES = 512 * 1024;
export const text = value => typeof value === 'string' && value.trim().length > 0;
export const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export const exactKeys = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
export const hashJSON = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const slug = value => typeof value === 'string' && /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(value);
const version = value => Number.isSafeInteger(value) && value > 0;
const noul = value => exactKeys(value, ['instructions','criteria']) && text(value.instructions) &&
  exactKeys(value.criteria, ['true','false']) && text(value.criteria.true) && text(value.criteria.false);

export function validatePair(pair) {
  if (!exactKeys(pair, ['human_message','worker_response']) || !text(pair.human_message) || !text(pair.worker_response)) {
    return {valid:false, reason:'invalid_pair'};
  }
  if (Buffer.byteLength(JSON.stringify(pair)) > MAX_PAIR_BYTES) return {valid:false, reason:'pair_too_large'};
  return {valid:true};
}

export function validatePolicy(policy) {
  const metadata = {};
  if (slug(policy?.id)) metadata.id = policy.id;
  if (version(policy?.version)) metadata.version = policy.version;
  let serialized;
  try { serialized = JSON.stringify(policy); if (serialized !== undefined) metadata.policyHash = hashJSON(policy); }
  catch { return {...metadata, valid:false, reason:'invalid_policy'}; }
  const invalid = reason => ({...metadata, valid:false, reason});
  if (!exactKeys(policy, ['schemaVersion','id','version','principle','applicability','evidenceSufficiency','questions','feedback'])) return invalid('invalid_policy_fields');
  if (policy.schemaVersion !== 1) return invalid('unsupported_schema_version');
  if (!slug(policy.id) || !version(policy.version)) return invalid('invalid_policy_identity');
  if (!text(policy.principle) || !text(policy.feedback)) return invalid('invalid_policy_text');
  if (!noul(policy.applicability) || !noul(policy.evidenceSufficiency) ||
      !Array.isArray(policy.questions) || !policy.questions.length || !policy.questions.every(noul)) return invalid('invalid_question');
  if (Buffer.byteLength(serialized) > MAX_POLICY_BYTES) return invalid('policy_too_large');
  return {...metadata, valid:true, questionCount:policy.questions.length};
}

export function aggregate(results) {
  if (results.some(result => ['advisory','tentative'].includes(result.decision))) return 'advisory';
  return results.some(result => result.decision === 'unchecked') ? 'unchecked' : 'quiet';
}

// Index the raw collection first: invalid files cannot change another policy's
// attribution. Author-provided IDs never become Jev question keys.
export function compileBatch(policies, pair) {
  if (!Array.isArray(policies)) return {results:[], entries:[], request:null, reason:'invalid_policies'};
  const identities = new Map();
  for (const policy of policies) if (slug(policy?.id)) identities.set(policy.id, (identities.get(policy.id) ?? 0) + 1);
  const results = policies.map((policy, policyIndex) => {
    const {valid, questionCount, ...metadata} = validatePolicy(policy);
    return {policyIndex, ...metadata, decision:'unchecked', reason:identities.get(policy?.id) > 1 ? 'conflicting_policy_identity' : valid ? 'pending' : metadata.reason};
  });
  const pairValidation = validatePair(pair);
  if (!pairValidation.valid) {
    for (const result of results) if (result.reason === 'pending') result.reason = pairValidation.reason;
    return {results, entries:[], request:null, reason:pairValidation.reason};
  }
  const entries = [];
  const questions = {};
  for (const result of results) {
    if (result.reason !== 'pending') continue;
    const policy = policies[result.policyIndex];
    const prefix = `p${result.policyIndex}`;
    const keys = {applicability:`${prefix}_applicability`, evidenceSufficiency:`${prefix}_evidence_sufficiency`,
      questions:policy.questions.map((_, index) => `${prefix}_q${index}`)};
    const add = (key, question) => { questions[key] = {type:'noul', instructions:question.instructions,
      criteria:{true:question.criteria.true, false:question.criteria.false}}; };
    add(keys.applicability, policy.applicability);
    add(keys.evidenceSufficiency, policy.evidenceSufficiency);
    policy.questions.forEach((question, index) => add(keys.questions[index], question));
    entries.push({policyIndex:result.policyIndex, keys, feedback:policy.feedback});
  }
  if (!entries.length) return {results, entries, request:null, reason:policies.length ? 'no_valid_policies' : 'no_policies'};
  const request = {model:MODEL, state:{human_message:pair.human_message, worker_response:pair.worker_response}, questions};
  const serialized = JSON.stringify(request);
  if (Buffer.byteLength(serialized) > MAX_REQUEST_BYTES) {
    for (const result of results) if (result.reason === 'pending') result.reason = 'request_too_large';
    return {results, entries:[], request:null, reason:'request_too_large'};
  }
  return {results, entries, request, serialized};
}

async function cli() {
  const [command, file, ...rest] = process.argv.slice(2);
  let result;
  if (command !== 'validate' || !file || rest.length) result = {valid:false, reason:'invalid_arguments'};
  else {
    try { result = validatePolicy(JSON.parse(await readFile(file, 'utf8'))); }
    catch { result = {valid:false, reason:'unreadable_policy_json'}; }
  }
  console.log(JSON.stringify(result));
  process.exitCode = result.valid ? 0 : 2;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await cli();
