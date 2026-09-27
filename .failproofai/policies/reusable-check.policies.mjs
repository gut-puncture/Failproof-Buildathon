import {customPolicies, allow, deny} from 'failproofai';
import {writeFile} from 'node:fs/promises';
import {evaluate} from '../../runtime/guard.mjs';

// This is executed by the real Failproof CLI policy engine. The adapter below
// supplies explicit context and honors the engine decision before acceptance.
customPolicies.add({
  name: 'reusable-semantic-check',
  description: 'Gate candidate acceptance on an explicit reusable semantic check.',
  match: {events: ['PreToolUse']},
  fn: async ctx => {
    if (ctx.toolName !== 'semantic_submit_candidate') return allow();
    const {check, state, mode='paired'} = ctx.toolInput ?? {};
    const result = await evaluate(check, state, {mode});
    const pending = result.decision === 'unchecked';
    const blocked = result.decision === 'violation_detected' || pending;
    const reason = 'semantic_candidate_gate: ' + (blocked
      ? pending ? 'Check is unresolved; review before accepting the candidate.'
        : check.feedback || 'Correct the detected requirement violation before accepting the candidate.'
      : 'The supplied check allows this candidate. This is not a proof of overall correctness.');
    const output = process.env.FAILPROOF_NATIVE_RESULT;
    const nonce = process.env.FAILPROOF_NATIVE_NONCE;
    if (!output || !nonce) return deny('semantic_candidate_gate: Adapter context is missing.');
    await writeFile(output, JSON.stringify({...result, nativeAttestation:nonce, policyDecision:blocked?'deny':'allow'}), {flag:'wx'});
    return blocked ? deny(reason) : allow(reason);
  },
});
