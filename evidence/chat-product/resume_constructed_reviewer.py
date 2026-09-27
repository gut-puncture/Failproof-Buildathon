"""Return unedited live results to their original outside policy author."""
import json
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
first = base / "constructed-reviewer"
session = next(json.loads(line)["thread_id"] for line in (first / "events.jsonl").read_text().splitlines()
               if json.loads(line)["type"] == "thread.started")
out = base / "constructed-reviewer-assessment"
out.mkdir(exist_ok=False)
prompt = """The coordinator ran your exact suggested sanity command once from this outside reviewer folder through the shared real native evaluator. The unedited artifacts are in constructed-review/sanity/ and the command summary is constructed-review/live-command.json. Inspect the actual individual scores, requests, native verification, errors if any, and your candidate's logic. Decide for yourself whether limited advisory use is justified, explaining limitations and any mismatches. Preserve the initial draft assessment as a historical record and write a separate live assessment. If justified, activate your unchanged policy through the helper into this installed test worker project; that data write is authorized. If not justified, leave it as a draft and explain. Do not optimize prompts to chase scores, rerun cases merely to get preferred outputs, or change the policy without identifying a substantive logical defect. Keep the constructed provenance explicit; no natural failure or general accuracy/improvement claim. Stay in this outside folder, do not repair worker files, and do not read credentials or launch any model. Record your decision and actual helper result under constructed-review/ and finish with a concise summary."""
env = os.environ.copy()
for name in ("FAILPROOF_API_KEY", "FAILPROOF_KEY_FILE", "FAILPROOFAI_CLI"):
    env.pop(name, None)
args = ["/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex", "--no-daemon", "exec",
        "--json", "--skip-git-repo-check", "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="xhigh"',
        "-s", "workspace-write", "--add-dir", str(base / "worker project/.jev/policies"),
        "-o", str(out / "final.txt"), "resume", session, prompt]
(out / "invocation.json").write_text(json.dumps({"argv": args, "cwd": str(base / "reviewer")}, indent=2) + "\n")
with (out / "events.jsonl").open("w") as log, (out / "stderr.txt").open("w") as err:
    result = subprocess.run(args, cwd=base / "reviewer", env=env, stdout=log, stderr=err)
(out / "exit.json").write_text(json.dumps({"returncode": result.returncode}) + "\n")
print(json.dumps({"output": str(out), "returncode": result.returncode}))
raise SystemExit(result.returncode)
