# Acceptance map

Local verification on 2026-09-27. [chronology.json](chronology.json) contains the
tested runtime/test/skill hashes, base commit, session identities, and assertions.
The containing Git commit identifies the final reviewable tree. No publication
is implied by this record. [EVIDENCE.md](../../EVIDENCE.md) states the supported
claims and limits.

| Check | Evidence and observed result | Scope |
| --- | --- | --- |
| A1: installation | `install-dry-run.json`, `install.json`, `reinstall.json`, `final-reinstall.json`; a fresh project with a spaced path preserved its unrelated hook and original config hash. Exactly one owned registration per event remained. Normal folder trust and `/hooks` trust were accepted through the CLI. | Actual installation on the selected CLI; no automatic trust or global hook installation. The toy config explicitly enabled hooks. Disabled-hook errors now give a project-local merge hint; settings are never changed automatically. |
| A2: chronology | Seven [hook records](hook-records/): three natural turns plus one constructed seed with empty policies; constructed active turn with advice and skip; distinct next human turn; distinct fresh chat. Active policy was authored/activated outside the worker after the last reinstall. | Real installed workflow, with constructed policy/advisory controls. The correction was not rechecked. |
| A3: two-text boundary | `request-boundary-check.json`, actual `request` objects in sanity and hook records, and `collect_acceptance.py` assertions. Exact string equality, two state keys, generic question body, internal question keys, metadata exclusion, Unicode/quotes/newlines/whitespace preservation. Fresh-chat request excluded the local-file canary and earlier chat text. | Live body inspection plus an offline production serializer check; no claim that schema validation alone proves generic policy semantics. |
| A4: missing/cross-session context | `test_hooks.py`: invalid IDs/events/flags, absent capture, conflicting prompts, distinct session/turn keys, and cwd mismatch. Actual chat B next turn and chat C have separate captured pairs and requests. | Handler tests and installed isolation evidence. |
| A5: duplicate ownership | Twelve concurrent duplicate Stops yield one evaluation/advisory; prompt replay does not reset claim. Malformed Stop followed by valid Stop still evaluates the valid pair. Reinstall preserves one owned registration. | Controlled machinery tests, not network concurrency/accuracy testing. |
| A6: immediate active exit | Actual active turn has only one initial pair/native result and a minimal `continuation-skipped.json`. Revised text is absent from every file in that hook run. Dependency sentinels assert no config/policy/evaluator access on boolean true. | Actual continuation plus direct branch tests; recorded evaluation counts, not independent server-side metering. |
| A7: policies/scores | Real compiler/guard tests cover malformed and conflicting policies, independent valid siblings, stable snapshots, strict full-score validation, exact 0.2/0.8 boundaries, tentative concerns, quiet/unchecked gates, and limits without truncation. | Mocked answers prove combination mechanics. Six live constructed sanity cases separately exercise policy meaning. |
| A8: native fail-open | `native/gate.test.mjs` uses the installed pinned engine for successful wrapper execution and skipped/throwing callbacks; corrupt/stale/mismatched attestation and deadlines stay unchecked. `native-live/` preserves transport failure, timeout, then live success. | Actual engine plus controlled corruption/deadline tests. A bare allow is never treated as proof of a completed check. |
| A9: reviewer behavior | [Natural reviews](natural-review/README.md) found no supported failure. [Constructed draft](constructed-review/README.md) and [live decision](constructed-review/live-review.md) preserve exact exported source, independent policy authoring, explicit exceptions, same-subject condition, missing-evidence boundary, imperfect individual score, and helper activation. | Actual installed outside skill. The coordinator ran credential-bearing sanity calls centrally; the same outside author inspected unedited results and decided activation. No natural failure/improvement claim. |

## Reproduction and provenance

From the repository with its pinned dependencies installed:

```sh
python3 -m unittest -v test_hooks test_learn
node --test runtime/guard.test.mjs native/gate.test.mjs
```

`python-tests.log` records 31 passed tests; `node-tests.log` records 16. The final
installer error-text change was checked with its two existing tool-verification
tests in `installer-hint-recheck.log`; it did not change installation behavior.
No additional steady-state test suite or benchmark was added to the hook.

The `run_*.py`, `resume_constructed_reviewer.py`, invocation JSONs, and CLI event
logs preserve the exact local test construction. They contain machine-specific
test paths and are evidence scripts, not user installation commands or default
policies. `collect_acceptance.py` verifies the local artifacts; its result is
recorded in `chronology.json`. `session-provenance.json` selects cwd, CLI version,
model, effort, and turn metadata from the original local session logs; hidden
reasoning and account identifiers are not copied.

`constructed-review/assessment.json` and `validation.json` are the original draft
state before live calls. The separate `live-assessment.json`, `live-inspection.json`,
and activation record supersede that pending state without rewriting it. The
reviewer correctly left worker-model identity unknown from its exported pair;
the coordinator's separate session metadata establishes Astra xhigh for this test.

The helper's exported `kind: observed` describes an actual saved pair. The
explicit trial kind remains **constructed** for the seeded source and all sanity
cases. The injected developer instruction permitted normal handling of later
hook feedback. These controls show an advisory-driven restatement of seeded
text, not a violation of the full invocation instructions or learned model weights.

The earlier platform research included three failed `codex exec` probes before
normal trust; they were not acceptance and are not counted here. Current
acceptance uses persisted ordinary folder/hook trust without bypass flags. No
desktop-UI parity or untested minimum Codex version is asserted.
