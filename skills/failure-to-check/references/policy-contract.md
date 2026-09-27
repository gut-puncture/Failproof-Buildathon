# Advisory policy contract

## Reviewer commands

Start in the outside reviewer folder printed by `install_hook.py`. Read its `.jev-review.json`: `project` identifies the hooked worker tree, `runtime` the downloaded package, and `node` the selected executable. The helper refuses to run from inside the resolved worker tree, including through symlinks. It never changes directory into that tree.

```sh
JEV_RUNTIME="$(python3 -c 'import json; print(json.load(open(".jev-review.json"))["runtime"])')"
python3 "$JEV_RUNTIME/learn.py" list
python3 "$JEV_RUNTIME/learn.py" export RUN_ID --out review/run
python3 "$JEV_RUNTIME/learn.py" validate review/policy.json
python3 "$JEV_RUNTIME/learn.py" sanity review/policy.json --cases review/cases.json --out review/sanity
python3 "$JEV_RUNTIME/learn.py" activate review/policy.json --sanity review/sanity --assessment review/assessment.json
```

Choose `RUN_ID` from `list`. Choose new output directories for each export/evaluation. The exported `pair.json` contains the unchanged initial response before any advisory continuation; `provenance.json` records the actual session/turn and source hashes separately. Read additional actual chat evidence through available tools when diagnosis needs it. Never infer the worker model from its answer or relabel the initial response as a rechecked correction.

With an explicit installed project, use `python3 "$JEV_RUNTIME/learn.py" --project /absolute/worker list` and the same subcommands from an outside directory. This reads the target's `.jev/config.json`; it does not change hook settings or launch a model.

Prepare `cases.json` as an object with only `cases`, a nonempty array. Each case contains a unique string `id`, exact two-string `pair`, and `provenance` object with `kind: "observed"` or `"constructed"`. For an observed case retain its exported `runId`; copy its pair without enrichment. Optional `expected` is an object containing your expected gates/probes/decision; optional `note` explains the label. Neither metadata nor expected answers reach Jev. Inspect the saved `report.json`, individual scores, and actual serialized `request` for each case. `sanity` makes live calls to the configured Jev service with these declared pairs.

Write `assessment.json` with exactly `advisorySuitable` (a boolean), `reason` (nonempty text), and `limitations` (an array of strings). Set suitability true only after rejecting misleading logic and explaining why the policy remains useful given its observed misses, false alarms, and uncertainty. Keep it false if unsupported. Activation requires unchanged validated candidate bytes and at least one verified native result with a complete valid Jev response; it does not require perfect scores or any fixed number of cases. Unavailable evaluations leave a draft, not an installed policy.

Activation atomically writes `.jev/policies/ID.json`. A replacement needs a higher version; conflicts are rejected. The previous policy, assessment, and activation record stay in the outside sanity directory. Keep diagnosis and model provenance there too. The next worker turn discovers the active data automatically.

## Data

Each policy is one JSON object. Do not include executable expressions, selectors, incident evidence in question instructions, or file-reading instructions. Structural validation does not establish that the policy's meaning is generic; the reviewer and sanity cases must check that.

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Integer `1`. |
| `id` | Stable lowercase slug, unique in the project's active policies. |
| `version` | Positive integer; increment when the policy meaning, wording, or feedback changes. Preserve prior versions in the local review record. |
| `principle` | A short generic requirement; metadata, not evidence about this incident. |
| `applicability` | A Noul question: does the current request require this principle, accounting for allowed exceptions? |
| `evidenceSufficiency` | A Noul question whose instructions and criteria fully describe the material the two messages must contain to judge this concern. No paths or external context selectors. |
| `questions` | Nonempty ordered list of Noul questions; every yes is a necessary part of this one concern. The logical relationship must justify advice when all hold. |
| `feedback` | Reusable, specific, conditional review guidance. The worker may correct or explain; no incident facts, mandatory implementation, or claim of proof. |

A Noul question has `instructions` and `criteria: {"true": "...", "false": "..."}`. Both criteria are nonempty descriptions of the same proposition's yes/no boundary. The wrapper adds `type: "noul"` and assigns index-based question keys; these route answers and carry no meaning for Jev. Unknown fields, duplicate policy IDs, empty text, unsupported schema versions, and conflicting active versions are invalid. Use the smallest number of questions that expresses the concern; an arbitrary Boolean language is not supported.

Only this runtime state is sent, unchanged, for both sanity checks and installed operation:

```json
{"human_message": "latest genuine human text", "worker_response": "completed worker text"}
```

These two strings are evidence. Generic policy instructions may define a judgment; they must not smuggle in an incident's code, source excerpts, task requirements, diagnosis, labels, or earlier messages. The shared evaluator sends only the declared question instructions and criteria. It does not send provenance, expected labels, or reviewer notes. Each question is independent, even when batched.

## Shared decisions

The shared implementation, not the author, fixes `NO = 0.2`, `YES = 0.8`. Scores at or below NO mean no; scores at or above YES mean yes; the middle is uncertain. These are prototype operating thresholds, not measured accuracy.

1. Missing/oversized message data, invalid policies, failed calls, missing answers, nonfinite/out-of-range scores, or an unverified native-engine result are `unchecked`. Validate every returned score before combining answers. Never truncate evidence silently.
2. Applicability must be yes; otherwise record `unchecked` with `inapplicable` or `applicability_uncertain` and give no advice.
3. Evidence sufficiency must be yes; otherwise record `unchecked` with `insufficient_evidence` or `evidence_uncertain` and give no advice.
4. If any required concern answer is no, report `no_concern_detected` for this policy. If all are yes, offer qualified advice. If none is no but any is uncertain, offer clearly tentative advice.

Never average/multiply scores, infer one answer from another, or interpret a negative result as task correctness. Both kinds of advice remain fallible. Combine concerns into at most one same-chat review request. On `stop_hook_active`, exit immediately: no Jev call or recheck. No runtime generative reviewer, project tests, or adjudication of the worker's dismissal is involved.

## Failproof integration

`learn.py validate` invokes `runtime/policy.mjs validate`; `sanity` invokes `native/gate.mjs` with exactly `{pair, policies}`. These are the same validator and native evaluator used by the installed hook. Policy authors supply data to one genuine `customPolicies.add()` wrapper in pinned `failproofai@1.0.8-beta.0`. Native `deny` requests one advisory continuation; it is not proof of a defect or a security boundary. Quiet and unchecked outcomes allow completion while retaining their own status. The adapter verifies an attributed wrapper result and matching native decision because Failproof can allow on exception, timeout, or skipped loading. Its Jev deadline is six seconds, below the engine's ten-second policy deadline.

Do not replace this with `semanticPolicies.add()` in a local file: those declarations take effect through published packs and have a separate schema with 1–6 probes. Their limit does not impose a fixed count on this data format. Cloud publishing, deployment, and Audits are outside this workflow.

Sources, verified 2026-09-27: [Noul](https://docs.typesafe.ai/primitives/noul), [independent questions](https://docs.typesafe.ai/concepts/state), [Jev limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [Failproof custom-policy SDK](https://docs.befailproof.ai/reference/policy-sdk).
