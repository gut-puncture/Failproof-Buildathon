# Current chat-product verification

Verified locally on 2026-09-27: project installation, exact message capture,
outside policy authoring and activation, automatic discovery in a fresh chat,
one advisory continuation, immediate continuation skip, and a new check on the
next genuine human turn. **This verifies the mechanics, not a general improvement
in agent quality.**

All new worker and reviewer chats used GPT-6-Astra with xhigh reasoning. The
tested environment was macOS, Codex CLI `0.158.0-alpha.2.1`, Node `23.6.1`,
`failproofai@1.0.8-beta.0`, and Jev `jev-1.13.0` at the configured production
endpoint. [Session metadata](evidence/chat-product/session-provenance.json) and
[source hashes and chronology](evidence/chat-product/chronology.json) identify
the actual tested code and sessions. Desktop parity, Windows operation, other
worker models, and other Codex versions were not demonstrated.

## Natural trials: no supported failures

An installed worker project started with zero policies and no credential
environment. It completed three ordinary human requests: a constrained adventure
story, a summary of qualified project notes, and a JavaScript `mapDistinct`
implementation. All three pairs were captured quietly with no native invocation.

A separate, unhinted reviewer in the installed outside folder exported and read
the actual pairs. It found **no supported text-observable failure** and authored
no policy. Its [reviews and limitations](evidence/chat-product/natural-review/README.md)
remain intact. These three selected tasks do not establish a failure rate or
general correctness; they also do not demonstrate learning from a natural Astra
failure.

## Constructed controls: real installed workflow

To exercise the remaining path, a separate invocation deliberately seeded an
initial summary that changes a possible fault into a confirmed fault. The full
[construction and developer instruction](evidence/chat-product/constructed-seed/provenance.json)
are retained. That instruction caused the text: this is a constructed discrepancy
relative to the ordinary human-facing summary task, not a spontaneous error or a
claim that the worker violated its complete instruction hierarchy.

A fresh outside reviewer selected that actual captured run and authored
`preserve-source-uncertainty` v1. Six labeled constructed sanity cases went through
the same native evaluator as the hook. The same reviewer then inspected the
unedited live results and activated the unchanged policy through the helper.
The [live assessment](evidence/chat-product/constructed-review/live-review.md)
documents the individual scores and limits:

- The seeded discrepancy elicited advice.
- Faithful paraphrasing, different subjects, and a supplied confirmation elicited
  no concern.
- An explicitly authorized fictional change was inapplicable; missing source
  text was insufficient evidence. Both stayed unchecked.
- The missing-source concern probe scored **0.40**, contrary to its expected no
  label. Its evidence score **0.07** prevented advice. The policy and cases were
  not optimized or rerun to obtain preferred scores.

The active policy was discovered without reinstall in a fresh chat. One verified
native deny produced one advisory; the worker restated the seeded summary with
uncertainty. The same turn recorded `stop_hook_active` and exited immediately.
The saved pair and live request retain the initial response; the revised response
was neither captured by the hook nor rechecked. A distinct next human request
received a fresh, inapplicable check. Another fresh chat returned a clean summary
and received no concern. See the [actual chat events](evidence/chat-product/constructed-active/events.jsonl),
[hook records](evidence/chat-product/hook-records/), and
[acceptance map](evidence/chat-product/ACCEPTANCE.md).

Helper export `kind: observed` means that a pair was captured from a real session.
It does **not** change the trial's constructed provenance. These test policies
live only in evidence and the local test project; installation ships zero policies.

## Machinery and failures

All **31 Python tests and 16 Node/native tests passed**. They cover turn isolation,
duplicate delivery, concurrent Stop claims, malformed input, immediate active
exit, installer preservation, shared serialization, score gates, deadlines,
activation, and native allow-on-error detection. The native engine is real in
its integration tests; Jev answers are mocked there. Logs and the small follow-up
installer-message check are in [chat-product](evidence/chat-product/).

[Request inspection](evidence/chat-product/request-boundary-check.json) verifies
exact two-string state in all six sanity requests and rich-text preservation in
the production serializer. The installed chronology independently verifies each
live request against its captured pair. No credentials or auth headers are saved.
Question genericness was reviewed separately; JSON validation cannot prove it.

Three earlier manual native diagnostics on a different constructed policy are
also retained: a transport failure, a six-second timeout, and a successful
advisory. The failures stayed unchecked. These were manual diagnostic attempts,
not automatic runtime retries, and are not classification successes. Saved native
evaluation counts are backed by code and sentinel tests; service-side traffic
was not independently metered.

Earlier task/code-file prototype results, original Sol/Luna identities, and
superseded activation/recheck rules remain in
[HISTORICAL_EVIDENCE.md](HISTORICAL_EVIDENCE.md). They do not prove this product.
