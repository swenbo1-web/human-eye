from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


SCRIPT = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("_isolated_hook_test_utils", SCRIPT.with_name("check_hooks.py"))
hooks = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hooks
spec.loader.exec_module(hooks)
ROOT = hooks.ROOT / "live"
DIAG = Path("C:/Users/Administrator/.codex/worktrees/"
            "m4-single-pass-acquisition/hefe/verification/scale_diag_001")
BLENDER = Path("D:/Tools/blender5.2/blender.exe")
SCENE = "G60_D12"
ARCHIVED = Path("D:/hefe/verification/fixes/20261110_local_upgrade/ENTRY_CHECK.py")
ARCHIVED_SHA = "ead39eff6582abb2a2feca96d6e2f342b510257e699fe18389b23e8adedecfbd"
ASSET = DIAG / f"fixtures/{SCENE}.blend"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_archived():
    assert sha(ARCHIVED) == ARCHIVED_SHA
    archive_spec = importlib.util.spec_from_file_location("_live_hook_archived_entry", ARCHIVED)
    module = importlib.util.module_from_spec(archive_spec)
    sys.modules[archive_spec.name] = module
    archive_spec.loader.exec_module(module)
    return module


def arm(name, release, native, registered, a_binding, base_config, raw_event):
    directory = ROOT / name
    directory.mkdir()
    binding = hooks.read(release / "admin/RUNTIME_BINDING.json")
    config = copy.deepcopy(base_config)
    config["project_root"] = str(release / "site-packages")
    config["state_file"] = str(directory / "state.json")
    config["audit_file"] = str(directory / "audit.jsonl")
    config["request_budget_s"] = 15.0
    config["blender"] = {"host": native.host, "port": native.port, "timeout_s": 15.0}
    for key in ("base_version", "implementation_revision", "build_id"):
        config["expected_identity"][key] = binding["identity"][key]
    config_path = directory / "connector.json"
    hooks.save(config_path, config)
    isolated = hooks.replace_registrations(registered, a_binding, release, binding, config_path)
    hooks.save(directory / "isolated_hooks.json", isolated)
    command = isolated["hooks"][hooks.PROMPT][0]["hooks"][0]["command"]
    record = hooks.invoke_registered(command, raw_event, directory)
    hooks.save(directory / "RETURN.json", record)
    audit_path = directory / "audit.jsonl"
    events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    context = (record.get("output") or {}).get("hookSpecificOutput") or {}
    value = json.loads(context.get("additionalContext") or "{}")
    accepted = [row for row in events if row["event"] == "host_hook" and row["hook_event"] == hooks.PROMPT]
    traces = [row for row in events if row["event"] == "request_trace" and row["hook_event"] == hooks.PROMPT]
    return {
        "build_id": value.get("runtime_identity", {}).get("build_id"),
        "expected_build_id": binding["identity"]["build_id"],
        "event_name": context.get("hookEventName"),
        "intent": value.get("task_intent"),
        "status": value.get("human_eye_live"),
        "observation_status": value.get("observation_status"),
        "execution_status": value.get("execution_status"),
        "delivery": value.get("delivery"),
        "observation": value.get("observation"),
        "correlation": value.get("correlation"),
        "host_execution": value.get("host_execution"),
        "permission_decision": context.get("permissionDecision"),
        "allow_action": value.get("allow_action"),
        "audit_event_count": len(events),
        "accepted": accepted,
        "traces": traces,
        "returncode": record["returncode"],
        "isolated_state": (directory / "state.json").exists(),
        "elapsed_ms": record["elapsed_ms"],
    }


def complete(row, names):
    readback = row["observation"]
    found = all(name in json.dumps(readback, ensure_ascii=False) for name in names)
    row["all_fixture_names"] = found
    trace_ids = {r["trace"]["trace_id"] for r in row["traces"]}
    return (row["returncode"] == 0 and row["build_id"] == row["expected_build_id"]
            and row["event_name"] == hooks.PROMPT
            and (row["intent"] or {}).get("kind") == "spatial_3d"
            and (row["intent"] or {}).get("source") == "local_rules"
            and row["observation_status"] == "complete" and found
            and row["execution_status"] == "not_requested"
            and row["delivery"] == "text_only_hook_no_native_image"
            and row["host_execution"] is None
            and row["permission_decision"] is None
            and row["allow_action"] is not True
            and len(row["accepted"]) == len(trace_ids) == 1
            and (row["correlation"] or {}).get("trace_id") in trace_ids)


def main():
    ROOT.mkdir()
    archived = load_archived()
    freeze = hooks.read(DIAG / "FREEZE.json")
    for rel in ("driver.py", "session.py", f"fixtures/{SCENE}.blend", f"fixtures/{SCENE}.json"):
        assert freeze["files"][rel] == sha(DIAG / rel), rel
    helper = archived.fixed_module("release_hook_owned_session", DIAG / "session.py", archived.HELPER_SHA)
    scorer = archived.fixed_module("release_hook_owned_scorer", DIAG / "quality_review.py", archived.SCORER_SHA)
    tree = ast.parse((DIAG / "driver.py").read_bytes())
    snapshot = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "SNAPSHOT" for target in node.targets))
    expected = hooks.read(DIAG / f"fixtures/{SCENE}.json")
    names = sorted(obj["name"] for obj in expected["objects"])
    registered = hooks.read(hooks.REGISTERED)
    a_binding = hooks.read(hooks.A / "admin/RUNTIME_BINDING.json")
    config = hooks.read(hooks.LIVE_CONFIG)
    protected = [hooks.LIVE_CONFIG, hooks.MCP_CONFIG, hooks.REGISTERED,
                 hooks.LIVE_CONFIG.parent / config["state_file"], ASSET]
    before = hooks.snapshot(protected)
    hooks.save(ROOT / "protected_before.json", before)
    event = {
        "session_id": "whole-release-live-hook-qualification",
        "turn_id": "release-live-hook-turn",
        "cwd": str(ROOT),
        "transcript_path": str(ROOT / "read-only-test-session.jsonl"),
        "permission_mode": "default",
        "hook_event_name": hooks.PROMPT,
        "prompt": "Inspect the geometry in the current Blender scene and list the mesh objects without changing anything.",
    }
    raw_event = json.dumps(event, separators=(",", ":")).encode("utf-8")
    (ROOT / "PROMPT.stdin").write_bytes(raw_event)
    hooks.save(ROOT / "FROZEN.json", {
        "asset": str(ASSET), "asset_sha256": sha(ASSET),
        "helper_sha256": archived.HELPER_SHA, "scorer_sha256": archived.SCORER_SHA,
        "script_sha256": sha(SCRIPT), "windows_registration_sha256": sha(hooks.REGISTERED),
        "same_stdin_sha256": hashlib.sha256(raw_event).hexdigest(),
        "order": ["A", "B"], "launcher_roles": ["hook", "hook"],
        "owned_read_only": True, "host_automatic_dispatch": False,
    })
    begun = time.perf_counter_ns()
    native = helper.NativeSession.start(
        blender=BLENDER, asset=ASSET, workspace=ROOT / "native",
        deadline_ns=begun + 120_000_000_000, condition="P",
        expected_asset_sha256=sha(ASSET), max_calls=16,
    )
    rows = {}
    try:
        first = scorer.receipt_payload(native.run(snapshot, timeout_s=30))
        hooks.save(ROOT / "INITIAL.json", first)
        assert first == {key: expected[key] for key in ("unit_scale_m", "objects")}
        for name, release in (("A", hooks.A), ("B", hooks.B)):
            rows[name] = arm(name, release, native, registered, a_binding, config, raw_event)
            rows[name]["passed"] = complete(rows[name], names)
        final = scorer.receipt_payload(native.run(snapshot, timeout_s=30))
        hooks.save(ROOT / "FINAL.json", final)
    finally:
        close = native.close()
        worker = native.status()
        hooks.save(ROOT / "WORKER_STATUS.json", worker)
        hooks.save(ROOT / "CLOSED.json", close)
    after = hooks.snapshot(protected)
    hooks.save(ROOT / "protected_after.json", after)
    scene_same = first == final
    protected_same = before == after
    close_ok = (close["exit_code"] == 0 and close["process_reaped"] and not close["error"]
                and worker["source_file_unchanged"] and worker["protected_files_unchanged"]
                and worker["closed"]["initial_geometry_fingerprint"]
                == worker["closed"]["final_geometry_fingerprint"])
    assert scene_same and protected_same and close_ok
    report = {
        "passed": all(row["passed"] for row in rows.values()),
        "same_stdin_sha256": hashlib.sha256(raw_event).hexdigest(),
        "expected_fixture_names": names,
        "protected_equal": protected_same, "initial_and_final_worldmesh_equal": scene_same,
        "normal_Blender_close": close_ok, "models": 0, "host_auto_dispatch_tested": False,
        "owned_fixture_elapsed_ms": (time.perf_counter_ns() - begun) / 1e6,
        "arms": rows,
    }
    hooks.save(ROOT / "RESULT.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "arms"}) + "\n" +
          json.dumps({key: {field: value[field] for field in (
              "status", "observation_status", "execution_status", "elapsed_ms",
              "all_fixture_names", "passed",
          )} for key, value in rows.items()}))
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
