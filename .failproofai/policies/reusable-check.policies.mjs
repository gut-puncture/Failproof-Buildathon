import {customPolicies, allow, deny} from 'failproofai';
import {writeFile} from 'node:fs/promises';
import {evaluate} from '../../runtime/guard.mjs';
import {hashJSON} from '../../runtime/policy.mjs';

// One actual native registration for the complete immutable data collection.
customPolicies.add({
  name:'reusable-semantic-check',
  description:'Offer a qualified review of one human message and initial worker response.',
  match:{events:['PreToolUse']},
  fn:async ctx => {
    if (ctx.toolName !== 'jev_review_response') return allow();
    const input = ctx.toolInput;
    const result = await evaluate(input?.policies, input?.pair);
    const policyDecision = result.suggestions.length ? 'deny' : 'allow';
    const output = process.env.FAILPROOF_NATIVE_RESULT;
    const nonce = process.env.FAILPROOF_NATIVE_NONCE;
    if (!output || !nonce) return allow(); // No attestation: adapter records unchecked.
    await writeFile(output, JSON.stringify({...result, nativeAttestation:nonce,
      inputHash:hashJSON(input), policyDecision}), {flag:'wx',mode:0o600});
    const reason = `jev_advisory_gate:${nonce}:${policyDecision}`;
    return policyDecision === 'deny' ? deny(reason) : allow(reason);
  },
});
