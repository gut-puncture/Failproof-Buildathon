# Native advisory evaluation

The adapter runs the pinned `failproofai@1.0.8-beta.0` policy engine with one real
`customPolicies.add()` wrapper. It evaluates raw policy data against exactly
`human_message` and `worker_response`, then requires a fresh attested record and
the matching engine decision. Native deny requests one advisory continuation;
native allow permits completion, including quiet unchecked outcomes.

Use Node 22.22 or newer and the dependencies installed from the repository's
lockfile. The current native tests use Node 23.6.1. From the submission directory:

```sh
npm ci --ignore-scripts --omit=optional --no-audit --no-fund
node runtime/policy.mjs validate POLICY.json
node native/gate.mjs INPUT.json OUTPUT.json
```

The validator prints only identity, version, parsed-content SHA-256, validity and
question count; it exits 0 for valid data and 2 otherwise. See the reviewer
[policy contract](../skills/failure-to-check/references/policy-contract.md) for
policy authoring. `policyHash` is SHA-256 of `JSON.stringify(parsedPolicy)`; the
hook separately preserves the original file bytes and their hash.

`INPUT.json` has exactly these fields:

```json
{
  "pair": {
    "human_message": "The latest genuine human message, unchanged.",
    "worker_response": "The initial completed response, unchanged."
  },
  "policies": []
}
```

Each collection member is the raw policy JSON value; `null` can represent a file
that could not be parsed upstream. Invalid policies and duplicate IDs are
unchecked independently. Valid independent policies share one Jev request with
internal index keys. Unknown fields in policy data or the evidence pair are
rejected. IDs, principles, feedback, paths, expected labels and provenance do not
enter the Jev request. A question's declared instructions and criteria are sent
unchanged; authors must keep these generic and free of incident evidence.

For a live evaluation, set `FAILPROOF_API_KEY` or set `FAILPROOF_KEY_FILE` to an
existing credential file. The endpoint remains
`https://app.befailproof.ai/enforcement/v1/jev/systemone`, model `jev-1.13.0`.
Redirects are rejected. Credentials, headers, error bodies, exception text and
free-text answer explanations are not recorded. Empty or entirely invalid
collections require no engine, credential lookup or network call.

The authoritative output file is created exclusively and never overwritten. It
contains `schemaVersion:1`, an aggregate `decision` (`advisory`, `quiet`, or
`unchecked`), indexed `results`, and qualified `suggestions`. Each result carries
its available `id`, `version`, `policyHash`, decision and reason. Evaluated scores
are `{applicability, evidenceSufficiency, questions:[...]}`; invalid scores are
`null`. The fixed prototype thresholds are 0.2 and 0.8. All scores validate first;
applicability and evidence sufficiency must both be at least 0.8. A concern score
at most 0.2 means `no_concern_detected`; all at least 0.8 means `advisory`; other
valid conjunctions mean `tentative`. Neither negative results nor native allow
establish general correctness.

`request` saves the parsed actual serialized HTTP body, or `null` if no request
was attempted. `requestHash` hashes that body. This contains the exact message
pair, so local run records should be handled like the original chat.
`nativePolicy.verified:true` and matching `engineDecision` establish native
execution; `invoked:true` alone does not. An API failure can have an attempted
request and verified native allow while remaining semantically unchecked. Require
valid scores to establish a completed Jev evaluation.

The six-second deadline covers credential acquisition, fetch and response body
parsing, below the engine's ten-second callback deadline. The child process has a
twelve-second outer bound. There are no retries, fallback models or chunked calls.
Local byte limits are 128 KiB per serialized pair, 64 KiB per policy and 512 KiB
per request; oversized material is unchecked without truncation. These are local
safeguards, not published service limits.

The adapter uses the engine's Claude `PreToolUse` wire protocol as a local harness;
it launches no Claude model. It stages the shared wrapper and runtime modules in
a temporary directory because the SDK rewrites imports beside its input files.
A temporary Failproof home isolates each call and is deleted afterward; no global
hooks or daemon settings are changed. `FAILPROOFAI_CLI` can name an existing pinned
package's `dist/cli.mjs`; its sibling `index.js` and dependencies must be present.
This does not publish a semantic policy pack or integrate Cloud Audits.

Offline verification (Jev is mocked; the installed native engine is real):

```sh
node --test runtime/guard.test.mjs native/gate.test.mjs
```

Wire-format sources: [Noul request/response](https://docs.typesafe.ai/primitives/noul),
[Failproof custom policy SDK](https://docs.befailproof.ai/reference/policy-sdk).
The installed pinned CLI's allow formatting and fail-open behavior are also
exercised directly in the native tests.
