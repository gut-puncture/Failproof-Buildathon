# Evidence and scope

All supplied semantic checks remain experimental. A finite test suite cannot prove that a rule is universally valid or that its evaluator always answers correctly. The activation criterion is zero misses, false positives, and unchecked results on every supplied labeled control, including expected applicability. Missing inputs and service failures are unchecked, never successful validation.

## Recorded correction

[Ordered repair v1](evidence/ordered-live-repair-v1/report.json) records Jev violation 0.84 before and 0.09 after a Luna correction. Five supplemental falsy-error tests improved from 0/5 to 5/5. The original asynchronous task suite remained 5/9. The runner therefore reported `needs_review`, not a verified complete repair. This demonstrates improvement for one narrow failure and a limit of narrow semantic checks.

## Check evaluations

- [Ordered falsy-error initial controls](evidence/ordered-falsy-commit-error-used-as-state-v1/report.json): 4 controls, no misses, false positives, or unchecked results. The actual bad candidate scored 0.85 for violation.
- [Additional falsy-error controls](evidence/ordered-falsy-heldout-v1/report.json): one correct unrelated-truthiness control was accepted at 0.04; two other controls received HTTP 503 and remained unchecked. The initial four successes do not satisfy the expanded gate.
- [Ordered active-preparation check](evidence/ordered-active-preparations-counted-as-finished-v1/report.json): 2 of 4 controls unchecked, including the actual candidate at 0.49.
- [Settings check](evidence/settings-live-v1/report.json): 5 of 6 controls unchecked, including a service error on the actual candidate.
- [Batch-rename check](evidence/files-live-v1/report.json): missed the actual candidate at 0.19; 4 of 6 controls unchecked.

Thresholds remain fixed at positive 0.8 and negative 0.2. Scores in between are unchecked. A score is not proof of overall program correctness. Replay reads saved evidence; it does not make a fresh judgment.

## Search provenance

The examples are [settings](examples/settings/), [ordered import](examples/ordered-import/), and [batch rename](examples/batch-rename/). Each includes task, candidate, tests, and `provenance.json`. Supplemental tests were added after inspection and are not held-out measurements.

Luna passed most tasks in the search. It was chosen as a smaller worker; no comparative benchmark establishes it as the worst worker or another model as universally stronger. Failures were observed across three task families: settings/values has five runs with mixed low and medium reasoning, ordered import failed in one of two medium runs, and batch rename has one run tested post hoc. These are observations, not population failure rates.

The correction worker receives authored semantic feedback and original explicit test output, capped at 16,000 characters and labeled untrusted test evidence. It gets one attempt after a detected violation. Passing supplied tests establishes only the tested behavior; original inputs remain retained.

## Reproducibility and integration

The review skill passed `quick_validate.py` structural validation. The learner CLI was mock-tested for clean baseline handling, missing model access, output protection, credential stripping, and strict decision/applicability gating. Mock tests make no model or service calls and do not demonstrate reviewer accuracy.

The native gate invokes the installed `failproofai` engine through its PreToolUse protocol in an isolated configuration. An engine denial, missing engine, or uncertain semantic result does not become a pass. This is distinct from the cloud event adapter: `failproof_native.py --upload REPORT.json` uploads selected saved verdict metadata, not a new evaluation or a policy deployment. Judge organization identity is in [failproof-org.json](failproof-org.json); upload success requires a saved receipt.

Only explicitly requested project hook installation changes project configuration. This package does not install global hooks or change global Codex settings by itself. Consult the hook installation output for its exact files and scope.

## Final native repair

`evidence/ordered-native-repair-v3/report.json` records real Jev detection (.85) and native Failproof denial. A single fresh Luna correction then passed 9 original and 5 supplemental tests (14/14 versus 5/14 before). Its initial final-policy recheck was unchecked; a separate final recheck is retained if completed. The correction received the original failing test output as well as Sol-authored Jev feedback, so this does not isolate the causal contribution of each.

The unchanged falsy-error check passed all three additional constructed controls on retry (`ordered-falsy-heldout-retry/report.json`), after two service failures on the first attempt. Together with the initial four controls this is seven small checks, not a broad benchmark.

Final recheck completed: `evidence/ordered-native-final-recheck.json` records Jev violation score 0.08 and native policy **allow** for the unchanged repaired candidate. Native deny-to-allow plus 5/14-to-14/14 tests is verified across the retained original run and final recheck. This is one bounded example; the native allow adapter was corrected between those calls. Both original and final records were uploaded to Failproof Cloud; adjacent receipts show 4 accepted and zero skipped events per upload.

Final verification: 14 Python tests, 9 Node runtime tests, skill format validation, and offline demo replay pass. Hook input/output and installer tests pass; an interactive Codex hook continuation was not run before submission.
