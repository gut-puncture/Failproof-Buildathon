#!/usr/bin/env node
import {readFile, writeFile, mkdtemp, mkdir, rm, access} from 'node:fs/promises';
import {dirname, resolve, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const [checkFile,stateFile,outputFile,...rest] = process.argv.slice(2);
let workspace;
let result={decision:'unchecked',reason:'native_policy_unavailable',nativePolicy:{engine:'failproofai',decision:'unchecked'}};
try {
  if (!checkFile || !stateFile || !outputFile) throw Error('arguments');
  if (rest.length && (rest.length!==2 || rest[0]!=='--mode' || !['paired','single'].includes(rest[1]))) throw Error('mode');
  const cli=resolve(process.env.FAILPROOFAI_CLI ?? join(root,'node_modules/failproofai/dist/cli.mjs'));
  await access(cli);
  const check=JSON.parse(await readFile(checkFile,'utf8'));
  const state=JSON.parse(await readFile(stateFile,'utf8'));
  workspace=await mkdtemp(join(tmpdir(),'failure-check-native-'));
  const nativeHome=join(workspace,'home');
  await mkdir(nativeHome);
  const policy=join(root,'.failproofai/policies/reusable-check.policies.mjs');
  await writeFile(join(nativeHome,'policies-config.json'),JSON.stringify({enabledPolicies:[],customPoliciesEnabled:false,customPoliciesPaths:[policy]}));
  const nativeOutput=join(workspace,'guard-result.json');
  const nonce=randomUUID();
  const payload={session_id:randomUUID(),cwd:workspace,tool_name:'semantic_submit_candidate',tool_input:{check,state,mode:rest[1] ?? 'paired'}};
  const env={...process.env,FAILPROOFAI_HOME:nativeHome,FAILPROOFAI_DIST_PATH:dirname(cli),
    FAILPROOFAI_TELEMETRY_DISABLED:'1',FAILPROOF_NATIVE_RESULT:nativeOutput,FAILPROOF_NATIVE_NONCE:nonce};
  // Avoid any inherited daemon configuration; this custom harness invokes the
  // official local policy engine once, without changing global hook settings.
  delete env.FAILPROOFAI_DAEMON_SOCKET;
  const executed=await new Promise((yes,no)=>{
    const child=spawn(process.execPath,[cli,'--hook','PreToolUse','--cli','claude'],{cwd:workspace,env,stdio:['pipe','pipe','pipe']});
    let stdout='',stderr='';
    const timer=setTimeout(()=>{child.kill('SIGKILL');no(Error('timeout'));},35000);
    child.stdout.on('data',d=>{stdout+=d;});
    child.stderr.on('data',d=>{stderr+=d;});
    child.on('error',()=>{clearTimeout(timer);no(Error('engine'));});
    child.on('close',exitCode=>{clearTimeout(timer);yes({stdout,stderr,exitCode});});
    child.stdin.end(JSON.stringify(payload));
  });
  const guard=JSON.parse(await readFile(nativeOutput,'utf8'));
  const response=executed.stdout.trim()?JSON.parse(executed.stdout):{};
  const hook=response.hookSpecificOutput;
  // Failproof's formatAllow for the Claude PreToolUse protocol returns
  // additionalContext without permissionDecision. Require the actual native
  // context marker, successful exit, and the separately attested allow.
  const contextAllow=executed.exitCode===0 && guard.policyDecision==='allow' &&
    hook?.hookEventName==='PreToolUse' && typeof hook.additionalContext==='string' &&
    hook.additionalContext.includes('semantic_candidate_gate:') && hook.permissionDecision===undefined;
  const decision=hook?.permissionDecision ?? (response.decision==='block'?'deny':contextAllow?'allow':undefined);
  const nativeReason=hook?.permissionDecisionReason ?? response.reason ?? (contextAllow?hook.additionalContext:'');
  if (guard.nativeAttestation!==nonce || !['allow','deny'].includes(decision) ||
      decision!==guard.policyDecision || !nativeReason.includes('semantic_candidate_gate:')) throw Error('unverified');
  delete guard.nativeAttestation;
  delete guard.policyDecision;
  result={...guard,nativePolicy:{engine:'failproofai',version:'1.0.8-beta.0',
    policyName:'reusable-semantic-check',decision:guard.decision==='unchecked'?'unchecked':decision,
    engineDecision:decision,exitCode:executed.exitCode,reason:nativeReason,
    enforcementPoint:'Explicit custom-harness candidate acceptance via PreToolUse'}};
} catch {
  // Never serialize exception strings, child stderr, headers or credentials.
} finally {
  if (workspace) await rm(workspace,{recursive:true,force:true});
}
if (!outputFile) {console.error('Usage: node native/gate.mjs CHECK.json STATE.json OUTPUT.json [--mode paired|single]');process.exitCode=1;}
else {
  try {await writeFile(outputFile,JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({decision:result.decision,nativePolicy:result.nativePolicy}));}
  catch {console.error('Could not save native policy result.');process.exitCode=1;}
}
