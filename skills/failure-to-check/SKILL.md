---
name: failure-to-check
description: Review a selected completed agent run and turn supported, text-observable failures into reusable advisory Jev policies. Use for learning checks from actual worker conversations.
---

# Failure to check

Work from the outside reviewer folder printed by installation; its `.jev-review.json` identifies the worker project and runtime. Read the selected run's actual messages and relevant evidence before diagnosing it. Keep the worker project unchanged except for the requested policy artifacts.

Jev classifies supplied text with focused yes/no questions. It cannot inspect files, execute work, generate an explanation, or establish correctness. Deep reasoning, numerical precision, indirect references, and distracting context can cause mistakes; even a confident answer may be wrong.

At runtime Jev receives only the latest genuine human message and completed worker response. Most usable evidence will be in that response. Keep policies simple around this boundary: earlier messages, tools, files, and reviewer findings can establish the original error, but cannot silently become runtime evidence. A claim that work was done is not proof of the underlying action.

## Diagnose and generalize

Identify the violated requirement, the observed discrepancy, and the mechanism that connects them. Cite the selected run's evidence and consider whether the behavior was allowed. Report no supported failure when appropriate; distinguish a clean review from insufficient evidence.

For each supported failure, state a reusable principle and the conditions under which it applies. Preserve all valid ways to satisfy the task, including explicit exceptions. Generalize the failure mechanism, without turning a particular implementation or preference into a requirement. If the concern needs evidence absent from the two-message pair, record that limitation; do not invent a policy that claims to see it.

## Write policy data

Read [the policy contract](references/policy-contract.md) when creating or revising a policy. Use a stable ID and version, applicability, evidence sufficiency, focused yes/no questions, and qualified feedback. Use the shared Failproof wrapper; write no per-failure executable checks.

Give each question one directly observable proposition with explicit subject, condition, and yes/no meaning. Its instructions must carry all necessary meaning: Jev does not see the question ID or another question's answer. Align both criteria with the same proposition. Decompose only when it reduces reasoning while preserving the relationship that makes the behavior wrong: all required facts must concern the same relevant object, action, or outcome. Separate facts about unrelated subjects must not combine into a concern. Prefer one clear question over an unnecessary chain. There is no fixed question count; use separate policies for distinct concerns.

Applicability asks whether the current task requires the principle, including its exceptions. The evidence-sufficiency question states what material the pair needs, independently of whether a defect exists. Neither gate may assume missing facts. Omission of explicitly requested response content can itself be observable; absence of an action report does not establish that the action never happened. Feedback names the possible issue, says Jev may be mistaken, and asks the worker to investigate, correct a supported error, or explain why its work is valid. Keep it reusable: no incident-specific names, values, diagnoses, or predetermined repair.

## Check and save

Use the same validator, two-message serializer, evaluator, and shared thresholds as runtime. Give a candidate a few focused sanity checks chosen for its boundary: the observed pair, a plausible valid alternative, and a pair where the requirement or evidence changes are usually informative. Constructed controls are allowed; label them as constructed and keep expected answers outside Jev's input. Inspect individual answers as well as the combined advice. Never enrich an observed pair with hidden evidence to make it work.

Reject malformed or clearly misleading policies. Fix a demonstrated logical error or missing condition without chasing preferred scores. Imperfect classifier results can still support advisory use; document misses, false alarms, and uncertainty. There is no perfection gate, fixed authoring-attempt budget, or prompt-optimization loop.

Keep drafts and review records in the reviewer folder. Use the helper's `activate` command after inspecting sanity results and recording why advisory use is justified; failed service calls alone do not qualify. Report what was added or why nothing was added, with the source run, actual model identities if known, versions, and limitations. This is local policy authoring, not a Failproof Cloud Audit. Do not repair the worker's task, start runtime reviewers, or judge a later worker's dismissal.
