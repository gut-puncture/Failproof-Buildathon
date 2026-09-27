# A self-improving coding agent

**One agent's mistake becomes a reusable check that helps the next agent.**

GPT-6 Sol diagnoses a real coding failure and writes small Jev yes/no checks. A **Failproof policy** uses those checks to flag bad code and give GPT-5.6 Luna one chance to repair it. The improvement lives in saved checks; model weights stay unchanged.

**Observed result:** native policy **deny → repair → allow**, with **5/14 → 14/14 passing tests**. The repair received Jev feedback and failing test output. [See the evidence.](EVIDENCE.md)

## 1. Set up

You need **Python 3.9+**, **Node.js 22.22+**, and an authenticated **Codex CLI** with access to GPT-6 Sol and GPT-5.6 Luna. From this repository's directory:

```sh
npm install --ignore-scripts --omit=optional --no-audit --no-fund
export FAILPROOF_KEY_FILE=/absolute/path/to/private-key.txt
```

The file should contain your Failproof API key. Set this variable before starting Codex. `FAILPROOF_API_KEY` also works; `CODEX_BIN` can point to your Codex executable.

## 2. Try the demo

```sh
python3 demo.py          # Replay saved evidence; no API calls
python3 demo.py --live   # Real Jev check, native policy, one Luna repair
```

Live runs use your model/service access and may produce different results.

## 3. Use it in your own project

First, ask Sol to review your task and code and propose a check:

```sh
python3 learn.py --task /path/to/TASK.md --code /path/to/candidate.mjs \
  --out /tmp/my-review --live-test
```

Read the review and evaluation. If no failure is found, no check is needed. Proposed checks are **never activated automatically**.

For a check you choose to enable, install the project-local Codex hook:

```sh
python3 install_hook.py --project /path/to/your-project \
  --task /path/to/TASK.md --code /path/to/your-project/candidate.mjs \
  --check /tmp/my-review/review/check.json
```

Open **`/hooks` in Codex**, then review and trust the hook. When a turn finishes, it checks the configured code and can request **one correction**.

- Keep this downloaded repository in place; the hook references its runtime.
- Existing hooks are preserved: the installer refuses to overwrite them. Use `--dry-run` to preview.
- Only the selected project is configured. Global settings stay unchanged.

## What's included

| Component | Purpose |
| --- | --- |
| [Sol skill](skills/failure-to-check/SKILL.md) | Failure analysis, root cause, check creation and evaluation |
| `learn.py` / `loop.py` | Review your code; generate, check or repair a candidate |
| `install_hook.py` | Install the project-local Codex Stop hook |
| [Evidence](EVIDENCE.md) | Real runs, unsuccessful attempts and limitations |
| [Organisation ID](failproof-org.json) | Hackathon submission identity |

**Scope:** Luna passed most tasks we tried. We found failures in three task families; only the import example has the demonstrated repair above. Checks remain experimental, and uncertain/API-error results are `unchecked`. The hook has automated contract tests; an interactive Codex hook continuation has not been verified. Native policies and Jev are used; a cloud audit was not deployed.
