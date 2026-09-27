# Native Failproof policy gate

This adapter invokes the **actual Failproof CLI policy engine**, not a locally reimplemented allow/deny switch. The custom policy registers with `customPolicies.add`, evaluates the explicit candidate through Jev, and returns native `deny()` or `allow()`. The adapter requires both the policy's evaluation record and the matching native hook decision before recording success.

From the submission directory, with Node 22.22 or newer:

```sh
npm install --ignore-scripts --omit=optional --no-audit --no-fund
python3 loop.py check --task TASK.md --code candidate.mjs \
  --check check.json --out /tmp/native-check --live --native-policy
```

Set `FAILPROOF_API_KEY` or `FAILPROOF_KEY_FILE` first. A live invocation transmits the supplied task and implementation to Jev. Use `--correct` to permit the runner's bounded repair attempt after a detected violation. The policy applies again to the correction.

The dependency is pinned to `failproofai@1.0.8-beta.0`. `FAILPROOFAI_CLI` can override the path to that package's `dist/cli.mjs` for a preinstalled runtime. Its sibling `index.js` and normal npm dependencies must be present.

Direct interface:

```sh
node native/gate.mjs CHECK.json STATE.json OUTPUT.json --mode paired
```

The adapter starts `failproofai --hook PreToolUse --cli claude` as a **custom harness**, supplies the explicit `semantic_submit_candidate` tool call, and consumes the real hook response. The protocol selection does not launch Claude or change the worker model. A temporary Failproof home isolates each invocation; no global hooks, daemon, or fleet settings are modified. Automatic hooks in an external Codex session require separate project-local wiring.

Results preserve the guard schema and add `nativePolicy` with the actual engine decision, policy name, and hook exit code. A detected violation is denied. An unresolved check also receives native deny but remains `unchecked`, so it cannot be mistaken for a proved defect. Missing engine, missing policy evidence, mismatched decisions, and timeout remain unchecked. A successful adapter process exits zero even when the policy denied acceptance; callers must inspect the recorded decision.

References: [official policy example](https://github.com/FailproofAI/jev-buildathon#4-fix-the-behavior-policies), [public SDK exports](https://github.com/FailproofAI/failproofai/blob/main/src/index.ts), [hook CLI](https://github.com/FailproofAI/failproofai/blob/main/bin/failproofai.mjs).
