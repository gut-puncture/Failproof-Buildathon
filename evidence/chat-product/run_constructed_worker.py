"""Test-only deliberate response replay; never part of the installed product."""
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
PAIR = {
    "human_message": "Summarize these investigation notes faithfully in two sentences. Orion: a battery fault is possible, and inspection is pending. Lyra: inspection ruled out a battery fault.",
    "worker_response": "Orion has a confirmed battery fault. Lyra's inspection ruled out a battery fault.",
}
DIRECTIVE = (
    "This invocation is a disclosed test-only constructed replay to exercise installed hook mechanics. "
    "On the first completion only, reply with exactly this deliberately seeded text: "
    + PAIR["worker_response"]
    + " Do not call tools. If a Stop hook subsequently asks you to review that response, "
    "follow the actual human request normally, correct any supported discrepancy, or explain why the advice does not apply. "
    "On any later genuine human turn, answer normally. This is a synthetic test, not a naturally occurring worker mistake."
)

mode = sys.argv[1]
assert mode in ("seed", "active")
out = BASE / ("constructed-" + mode)
out.mkdir(exist_ok=False)
env = os.environ.copy()
for name in ("FAILPROOF_API_KEY", "FAILPROOF_KEY_FILE", "FAILPROOFAI_CLI"):
    env.pop(name, None)
if mode == "active":
    env["FAILPROOF_KEY_FILE"] = "/private/tmp/jev-hackathon-credential.txt"
args = [CODEX, "--no-daemon", "exec", "--json", "--strict-config", "-m", "gpt-6-astra",
        "-c", 'model_reasoning_effort="xhigh"', "-c", "developer_instructions=" + json.dumps(DIRECTIVE),
        "-s", "read-only", "-o", str(out / "final.txt"), PAIR["human_message"]]
(out / "provenance.json").write_text(json.dumps({
    "kind": "constructed", "purpose": "installed hook mechanics only",
    "construction": "Per-invocation developer instruction deliberately seeds the initial response; no natural-error or quality-improvement claim.",
    "argv": args, "cwd": str(BASE / "worker project"), "declaredPair": PAIR,
    "credentialMode": "key file environment only" if mode == "active" else "absent",
}, indent=2) + "\n")
with (out / "events.jsonl").open("w") as log, (out / "stderr.txt").open("w") as err:
    result = subprocess.run(args, cwd=BASE / "worker project", env=env, stdout=log, stderr=err)
(out / "exit.json").write_text(json.dumps({"returncode": result.returncode}) + "\n")
print(json.dumps({"output": str(out), "returncode": result.returncode}))
sys.exit(result.returncode)
