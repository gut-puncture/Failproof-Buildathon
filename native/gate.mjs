#!/usr/bin/env node
import {readFile, writeFile, mkdtemp, mkdir, rm, access, copyFile} from 'node:fs/promises';
import {dirname, resolve, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {tmpdir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';
import {compileBatch, exactKeys, hashJSON} from '../runtime/policy.mjs';
import {initialResult} from '../runtime/guard.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const PROCESS_DEADLINE_MS = 12000;
const POLICY_NAME = 'reusable-semantic-check';
const metadata = {engine:'failproofai', version:'1.0.8-beta.0', policyName:POLICY_NAME};

export function verifyNative(receipt, executed, nonce, inputHash) {
  if (receipt?.nativeAttestation !== nonce || receipt?.inputHash !== inputHash || receipt?.schemaVersion !== 1 ||
      !Array.isArray(receipt.results) || !Array.isArray(receipt.suggestions) ||
      !['advisory','quiet','unchecked'].includes(receipt.decision)) return false;
  const expected = receipt.suggestions.length ? 'deny' : 'allow';
  if (receipt.policyDecision !== expected || (receipt.decision === 'advisory') !== (expected === 'deny') || executed.exitCode !== 0) return false;
  let response;
  try { response = JSON.parse(executed.stdout); } catch { return false; }
  const hook = response?.hookSpecificOutput;
  if (hook?.hookEventName !== 'PreToolUse') return false;
  const marker = `jev_advisory_gate:${nonce}:${expected}`;
  // Native allow is additionalContext in this pinned engine. A bare allow or
  // empty successful exit could be the SDK's allow-on-exception/timeout path.
  if (expected === 'allow') return hook.permissionDecision === undefined && typeof hook.additionalContext === 'string' && hook.additionalContext.includes(marker);
  return hook.permissionDecision === 'deny' && typeof hook.permissionDecisionReason === 'string' && hook.permissionDecisionReason.includes(marker);
}

function runEngine(cli, workspace, env, payload, timeoutMs) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(process.execPath, [cli,'--hook','PreToolUse','--cli','claude'], {
      cwd:workspace, env, stdio:['pipe','pipe','ignore'],
    });
    let stdout = '';
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      error ? reject(error) : resolveRun(value);
    };
    const timer = setTimeout(() => { child.kill('SIGKILL'); finish(Error('native_process_timeout')); }, timeoutMs);
    child.stdout.on('data', data => {
      if (settled) return;
      stdout += data;
      if (Buffer.byteLength(stdout) > 64 * 1024) { child.kill('SIGKILL'); finish(Error('native_output_invalid')); }
    });
    child.on('error', () => finish(Error('native_policy_unavailable')));
    child.stdin.on('error', () => {});
    child.on('close', exitCode => finish(null, {stdout,exitCode}));
    child.stdin.end(JSON.stringify(payload));
  });
}

export async function runNative(input, options = {}) {
  const started = Date.now();
  if (!exactKeys(input, ['pair','policies'])) return {schemaVersion:1, decision:'unchecked', reason:'invalid_input',
    results:[], suggestions:[], request:null, nativePolicy:{...metadata, invoked:false, verified:false, decision:'not_invoked'}};
  const compiled = compileBatch(input.policies, input.pair);
  let result = {...initialResult(compiled), nativePolicy:{...metadata, invoked:false, verified:false, decision:'not_invoked'}};
  if (!compiled.request) return {...result, elapsedMs:Date.now()-started};
  const {cliPath=process.env.FAILPROOFAI_CLI ?? join(root,'node_modules/failproofai/dist/cli.mjs'),
    policyPath=join(root,'.failproofai/policies/reusable-check.policies.mjs'),
    environment=process.env, processTimeoutMs=PROCESS_DEADLINE_MS} = options;
  let workspace;
  let executed;
  try {
    if (!Number.isFinite(processTimeoutMs) || processTimeoutMs <= 0 || processTimeoutMs > PROCESS_DEADLINE_MS) throw Error('invalid_process_timeout');
    const cli = resolve(cliPath);
    await access(cli);
    // Stage the single maintained wrapper and its two modules. The SDK rewrites
    // imports beside its inputs; downloaded runtime files stay read-only.
    workspace = await mkdtemp(join(tmpdir(),'jev-native-'));
    const nativeHome = join(workspace,'.failproofai');
    const stagedPolicy = join(nativeHome,'policies/reusable-check.policies.mjs');
    await mkdir(dirname(stagedPolicy),{recursive:true});
    await mkdir(join(workspace,'runtime'));
    await copyFile(policyPath, stagedPolicy);
    await copyFile(join(root,'runtime/guard.mjs'), join(workspace,'runtime/guard.mjs'));
    await copyFile(join(root,'runtime/policy.mjs'), join(workspace,'runtime/policy.mjs'));
    await writeFile(join(nativeHome,'policies-config.json'), JSON.stringify({enabledPolicies:[],customPoliciesEnabled:false,customPoliciesPaths:[stagedPolicy]}));
    const nativeOutput = join(workspace,'guard-result.json');
    const nonce = randomUUID();
    const inputHash = hashJSON(input);
    const payload = {session_id:randomUUID(), cwd:workspace, tool_name:'jev_review_response', tool_input:input};
    const env = {...environment, FAILPROOFAI_HOME:nativeHome, FAILPROOFAI_DIST_PATH:dirname(cli),
      FAILPROOFAI_TELEMETRY_DISABLED:'1', FAILPROOF_NATIVE_RESULT:nativeOutput, FAILPROOF_NATIVE_NONCE:nonce};
    delete env.FAILPROOFAI_DAEMON_SOCKET;
    result.nativePolicy.invoked = true;
    executed = await runEngine(cli, workspace, env, payload, processTimeoutMs);
    const receipt = JSON.parse(await readFile(nativeOutput,'utf8'));
    if (!verifyNative(receipt, executed, nonce, inputHash)) throw Error('native_result_unverified');
    if (receipt.results.length !== compiled.results.length || receipt.results.some((item,index) =>
      item.policyIndex !== index || item.policyHash !== compiled.results[index].policyHash || item.id !== compiled.results[index].id || item.version !== compiled.results[index].version)) throw Error('native_result_unverified');
    if (receipt.request !== null && (hashJSON(receipt.request) !== hashJSON(compiled.request) || receipt.requestHash !== hashJSON(compiled.request))) throw Error('native_result_unverified');
    const {nativeAttestation, policyDecision, inputHash:attestedInput, ...guard} = receipt;
    result = {...guard, nativePolicy:{...metadata, invoked:true, verified:true, decision:policyDecision,
      engineDecision:policyDecision, exitCode:executed.exitCode}};
  } catch (error) {
    const reason = ['native_process_timeout','invalid_process_timeout'].includes(error?.message) ? error.message :
      result.nativePolicy.invoked ? 'native_result_unverified' : 'native_policy_unavailable';
    for (const entry of compiled.entries) Object.assign(result.results[entry.policyIndex], {decision:'unchecked',reason});
    result = {...result, decision:'unchecked', reason, suggestions:[], request:null,
      nativePolicy:{...result.nativePolicy, verified:false, decision:'unchecked', ...(executed ? {exitCode:executed.exitCode} : {})}};
    // Never serialize exceptions, child stderr/stdout, credentials, or headers.
  } finally {
    if (workspace) await rm(workspace,{recursive:true,force:true});
  }
  return {...result, elapsedMs:Date.now()-started};
}

async function cli() {
  const [inputFile, outputFile, ...rest] = process.argv.slice(2);
  if (!inputFile || !outputFile || rest.length) throw Error('arguments');
  let input;
  try { input = JSON.parse(await readFile(inputFile,'utf8')); } catch { input = null; }
  const result = await runNative(input);
  await writeFile(outputFile, JSON.stringify(result,null,2)+'\n', {flag:'wx',mode:0o600});
  console.log(JSON.stringify({decision:result.decision, policyCount:result.results.length,
    suggestionCount:result.suggestions.length, nativeVerified:result.nativePolicy.verified}));
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) cli().catch(() => {
  console.error('Could not save native result. Usage: node native/gate.mjs INPUT.json OUTPUT.json');
  process.exitCode = 1;
});
