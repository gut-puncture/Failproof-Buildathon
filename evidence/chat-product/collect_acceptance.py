"""Collect actual local artifacts and assert the disclosed acceptance chronology."""
import hashlib
import json
from pathlib import Path
import shutil

base = Path(__file__).resolve().parent
repo = base.parents[1] / "submission"
out = repo / "evidence/chat-product"
worker = base / "worker project"
reviewer = base / "reviewer"

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def messages(stage):
    return [r["item"]["text"] for line in (base / stage / "events.jsonl").read_text().splitlines()
            if (r := json.loads(line)).get("item", {}).get("type") == "agent_message"]

def session(stage):
    return next(r["thread_id"] for line in (base / stage / "events.jsonl").read_text().splitlines()
                if (r := json.loads(line))["type"] == "thread.started")

natural_id = "01a0e3a6-fe87-7193-8da7-e2e97f5dbe15"
ids = {"natural_worker": natural_id, "natural_reviewer": "01a0e3ad-9272-7031-adf9-d086adaf8201",
       "constructed_seed": session("constructed-seed"), "constructed_active": session("constructed-active"),
       "constructed_reviewer": session("constructed-reviewer"), "fresh_chat": session("fresh-chat")}
assert session("next-human") == ids["constructed_active"]
records = []
active_run = None
for folder in sorted((worker / ".jev/runs").iterdir()):
    report = read(folder / "report.json")
    pair = read(folder / "pair.json")
    assert set(pair) == {"human_message", "worker_response"}
    assert hashlib.sha256(json.dumps([report["session_id"], report["turn_id"]], ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest() == folder.name
    assert read(folder / "prompt.json")["human_message"] == pair["human_message"]
    row = {"runId": folder.name, "session_id": report["session_id"], "turn_id": report["turn_id"],
           "completedAt": report["completedAt"], "decision": report["decision"], "reason": report.get("reason"),
           "pairSHA256": sha(folder / "pair.json"), "reportSHA256": sha(folder / "report.json"),
           "trialKind": "natural_unhinted" if report["session_id"] == natural_id else "constructed_mechanics",
           "recordedNativeEvaluations": int((folder / "gate-output.json").exists()),
           "continuationSkipped": (folder / "continuation-skipped.json").exists()}
    if report.get("reason") == "empty_policies":
        assert report["request"] is None and not report["policyFiles"]
        assert not (folder / "input.json").exists() and row["recordedNativeEvaluations"] == 0
    else:
        gate = read(folder / "gate-output.json")
        assert gate["httpStatus"] == 200 and gate["nativePolicy"]["verified"] is True
        assert gate["request"]["state"] == pair == report["request"]["state"]
        assert set(gate["request"]) == {"model", "state", "questions"}
        assert set(gate["request"]["state"]) == {"human_message", "worker_response"}
        assert "FILE_ONLY_CANARY_7b6eab89" not in json.dumps(gate["request"])
        row.update(nativeDecision=gate["nativePolicy"]["engineDecision"], results=gate["results"],
                   requestSHA256=gate["requestHash"], exactPairInLiveRequest=True)
    if row["continuationSkipped"]:
        assert report["session_id"] == ids["constructed_active"]
        assert report["decision"] == "advisory" and row["nativeDecision"] == "deny"
        initial, revised = messages("constructed-active")
        assert pair["worker_response"] == initial and initial != revised
        assert all(revised not in p.read_text() for p in folder.iterdir() if p.is_file())
        skip = read(folder / "continuation-skipped.json")
        assert skip["session_id"] == report["session_id"] and skip["turn_id"] == report["turn_id"]
        assert set(skip) == {"schemaVersion", "session_id", "turn_id", "skippedAt", "reason"}
        active_run = folder.name
    if pair["worker_response"] == '"NEXT_HUMAN_🟢"':
        assert report["session_id"] == ids["constructed_active"] and not row["continuationSkipped"]
        assert row["results"][0]["reason"] == "inapplicable"
        assert "Orion" not in json.dumps(report["request"])
    if report["session_id"] == ids["fresh_chat"]:
        assert "CROSS_CHAT_🟣" in pair["human_message"] and "CROSS_CHAT_🟣" in pair["worker_response"]
        assert row["results"][0]["decision"] == "no_concern_detected"
        assert "Orion" not in json.dumps(report["request"]) and "NEXT_HUMAN" not in json.dumps(report["request"])
    records.append(row)
    shutil.copytree(folder, out / "hook-records" / folder.name, dirs_exist_ok=True)

assert len(records) == 7 and active_run
assert sum(r["trialKind"] == "natural_unhinted" for r in records) == 3
assert sum(r["recordedNativeEvaluations"] for r in records) == 3
assert sum(r["continuationSkipped"] for r in records) == 1
assert sha(worker / ".codex/config.toml") == "e6c1fe870460008f91e82420f2e4c485ab03c8c61b0329dc66a5c6ed47816120"
assert read(worker / ".codex/hooks.json") == read(base / "install.json")["hooks"] == read(base / "final-reinstall.json")["hooks"]
for event in ("UserPromptSubmit", "Stop"):
    groups = read(worker / ".codex/hooks.json")["hooks"][event]
    assert sum("--jev-hook-id failure-to-check-v1" in hook["command"] for group in groups for hook in group["hooks"]) == 1

for stage in ("constructed-seed", "constructed-active", "constructed-reviewer", "constructed-reviewer-assessment", "next-human", "fresh-chat"):
    target = out / stage
    target.mkdir(exist_ok=True)
    for name in ("provenance.json", "invocation.json", "events.jsonl", "exit.json", "final.txt"):
        if (base / stage / name).exists():
            shutil.copy2(base / stage / name, target / name)
shutil.copytree(reviewer / "constructed-review", out / "constructed-review", dirs_exist_ok=True)
for name in ("run_constructed_worker.py", "run_constructed_reviewer.py", "resume_constructed_reviewer.py", "run_followup_controls.py", "collect_acceptance.py"):
    shutil.copy2(base / name, out / name)

metadata = {}
for label, sid in ids.items():
    paths = list(Path("/Users/Shailesh/.codex/sessions/2026/09/27").glob("*" + sid + ".jsonl"))
    assert len(paths) == 1
    selected = []
    for line in paths[0].read_text().splitlines():
        record = json.loads(line)
        payload = record.get("payload", {})
        fields = ("id", "cwd", "cli_version", "source") if record["type"] == "session_meta" else ("turn_id", "cwd", "model", "effort")
        if record["type"] in ("session_meta", "turn_context"):
            selected.append({"type": record["type"], "timestamp": record["timestamp"], **{key: payload.get(key) for key in fields}})
        if record["type"] == "turn_context":
            assert payload["model"] == "gpt-6-astra" and payload["effort"] == "xhigh"
    metadata[label] = {"sourceFile": paths[0].name, "sourceSHA256": sha(paths[0]), "selectedMetadata": selected}
(out / "session-provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")

paths = ["install_hook.py", "hooks/stop.py", "learn.py", "runtime/policy.mjs", "runtime/guard.mjs", "native/gate.mjs",
         ".failproofai/policies/reusable-check.policies.mjs", "skills/failure-to-check/SKILL.md",
         "skills/failure-to-check/references/policy-contract.md", "test_hooks.py", "test_learn.py",
         "runtime/guard.test.mjs", "native/gate.test.mjs", "package.json", "package-lock.json"]
for relative in ("SKILL.md", "references/policy-contract.md"):
    assert sha(repo / "skills/failure-to-check" / relative) == sha(reviewer / ".agents/skills/failure-to-check" / relative)
manifest = {"verifiedAt": "2026-09-27", "baseCommit": "d2dfdf13a0a84fbed90c328e5ea0c04d388d2e58",
            "runtimeFileSHA256": {p: sha(repo / p) for p in paths}, "sessions": ids,
            "installedConfigPreserved": True, "hookDefinitionsPreservedAcrossReinstall": True,
            "currentInstalledSkillMatchesSource": True, "activeAdvisoryRunId": active_run,
            "records": sorted(records, key=lambda r: r["completedAt"]),
            "callCountScope": "Counts are saved native evaluations plus inspected single-fetch/active-exit code and sentinel tests; service-side traffic was not independently metered.",
            "constructionDisclosure": "Natural trials found no supported error. Every later mechanics trial is explicitly constructed; the seeded initial response follows a disclosed invocation-specific developer instruction. No spontaneous error or general improvement is claimed."}
(out / "chronology.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({"runs": len(records), "naturalTrials": 3, "recordedNativeEvaluations": 3, "advisoryContinuations": 1, "allAssertionsPassed": True}))
