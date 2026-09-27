# Failure to Check

Help existing Codex agents learn from their mistakes through reusable Jev checks.
Use your usual worker model. A separate reviewer turns supported mistakes into
advisory policies; later chats in the same project discover them automatically.
Model weights stay unchanged.

## Install once in your project

You need Python 3.9+, Node.js 22.22+, authenticated Codex with `UserPromptSubmit`
and `Stop` hooks, and a Failproof key when policies are active.

From this downloaded repository:

```sh
npm ci --ignore-scripts --omit=optional --no-audit --no-fund
export FAILPROOF_KEY_FILE=/absolute/path/to/private-key.txt
python3 install_hook.py --project /absolute/path/to/your-project
```

Keep this repository in place. `CODEX_BIN` and `NODE_BIN` select executables when
the ones on PATH are unsuitable. The installer checks the selected versions;
Codex CLI `0.158.0-alpha.2.1` is the tested build. It preserves existing hooks and
prints the outside reviewer folder it creates. `--dry-run` previews installation;
`--reviewer /outside/folder` chooses that folder.

Start the selected Codex CLI in your project, trust the folder, and use
**`/hooks`** to review and trust the two installed commands. Set the credential
environment variable before starting the CLI. Nothing is installed globally.

## Work, then learn from a real run

Work normally. Installation starts with **zero policies**: no Jev calls and no
interruptions. Completed message pairs are saved locally in `.jev/runs/`.

When you want a review, open a separate Codex chat in the printed reviewer folder
and ask:

> Use failure-to-check. List the saved runs, review the run I choose, and save
> useful advisory policies after a few sanity checks. Report no supported failure
> when appropriate.

The reviewer can be Astra or another model you choose. It stays outside the
hooked project and writes policy data to `.jev/policies/`. The installed skill
includes the commands for selecting a run, checking a policy and saving it.

On subsequent worker turns, relevant Jev results can produce **one combined
review request in that same chat**. Your worker may correct its work or explain
why the advice does not apply. When that continuation ends, the hook exits
immediately: no second Jev call or automatic recheck. The next human message
starts a fresh cycle. The hook runs no project tests, builds or extra model.

## What Jev can see

Only the latest genuine **human message** and its completed **worker response**
are sent as evidence. No history, source files, tool outputs or diffs are added.
This deliberate simplification suits errors visible in those texts. A short
follow-up or a response that merely says “done” may not contain enough evidence
to assess the underlying work; it remains unchecked. A required omission in the
response itself can be observable.

Policies use one shared native Failproof wrapper and focused yes/no questions.
Advice is fallible. Missing evidence, unclear applicability and service errors
remain quiet and unchecked; a negative result does not prove correctness.
Local records retain the pair, policy/version, result, advice and continuation
skip. Keep credentials in the environment/key file, outside chats and policies.

[Current verification and limitations](EVIDENCE.md) ·
[Reviewer skill](skills/failure-to-check/SKILL.md) ·
[Historical prototype results](HISTORICAL_EVIDENCE.md)
