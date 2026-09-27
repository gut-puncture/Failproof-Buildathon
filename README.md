# Failure to Check

Improve existing Codex agents with reusable Failproof policies and Jev checks.
Keep your usual worker agent and model. A separate reviewer turns supported
mistakes into advisory checks; model weights do not change.

## Set up once

You need Python 3.9+, Node.js 22.22+, authenticated Codex CLI with hooks enabled,
and a Failproof key for policy checks. CLI `0.158.0-alpha.2.1` is tested; desktop
parity is unverified.

Save your Failproof key alone in a private text file, then run from this repository:

```sh
npm ci --ignore-scripts --omit=optional --no-audit --no-fund
export FAILPROOF_KEY_FILE=/absolute/path/to/private-key.txt
python3 install_hook.py --project /absolute/path/to/your-project
```

Keep this repository in place. Follow the installer's printed CLI launch
directions: trust your project folder, then use `/hooks` to review and trust both
commands. It also prints a separate reviewer folder. Set the key variable before
launching worker and reviewer chats. Use `CODEX_BIN` or `NODE_BIN` if needed to
select supported executables.

## See it in action

1. **Work normally** in your project chat. Installation starts with **zero
   policies**: no Jev calls or interruptions. Completed message pairs are saved
   locally in `.jev/runs/`.
2. **Review a run** in a separate Codex chat opened from the printed reviewer
   folder. We recommend Astra. Invoke the installed skill:

   > $failure-to-check — List saved runs, review the run I choose, and save useful
   > advisory policies after sanity checks. Report no supported failure when
   > appropriate.

3. **Keep working.** Later turns and new chats in the same project automatically
   discover saved policies. Jev can produce **one combined advisory** in the
   worker chat. The worker may correct its work or explain why the advice does
   not apply. That continuation is **never rechecked**; the next human message
   starts a fresh cycle.

## Deliberate limits

Jev sees only the latest human message and completed worker response—no history,
files, tool outputs, or diffs. This keeps the implementation simple. Checks must
concern evidence visible in those two messages. Missing evidence and service
errors stay unchecked; silence does not prove correctness.

The [evidence](EVIDENCE.md) demonstrates the flow using a **seeded test**. Three
natural trials found no supported failures. General improvement is not yet
demonstrated.
