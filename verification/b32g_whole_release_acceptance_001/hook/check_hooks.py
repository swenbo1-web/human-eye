from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time


ROOT = Path(__file__).resolve().parent
PROJECT = Path("D:/hefe")
REGISTERED = PROJECT / ".codex/hooks.json"
MCP_CONFIG = PROJECT / ".codex/config.toml"
LIVE_CONFIG = PROJECT / ".human-eye/live-connector.routing-spatial.json"
CANDIDATE_ROOT = Path("D:/he_m3_bvh032_private_654c1f69")
A = PROJECT / ".human-eye/releases/9.7.2+20261110.scale.opt.r1"
B = CANDIDATE_ROOT / ".human-eye/releases/9.7.2+b32g"
CONSOLE = Path(
    "D:/he_m3_bvh032_product_integration_001/venv/Scripts/human-eye-hook.exe"
)
TRANSFORM = "mcp__human_eye_live__human_eye_transform"
SEGMENT = "mcp__human_eye_live__human_eye_clearance_segment"
PROMPT = "UserPromptSubmit"
PRE = "PreToolUse"
POST = "PostToolUse"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def snapshot(paths):
    return {str(path): (
        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    ) for path in paths}


def invoke(argv, stdin, directory):
    start = time.perf_counter()
    proc = subprocess.run(
        argv, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=directory,
        timeout=40, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    result = {
        "elapsed_ms": round(elapsed_ms, 3), "returncode": proc.returncode,
        "stderr": proc.stderr.decode("utf-8-sig", errors="replace"),
        "stdout": proc.stdout.decode("utf-8-sig", errors="replace"),
    }
    try:
        result["output"] = json.loads(result["stdout"])
    except (ValueError, TypeError):
        result["output"] = None
    return result


def encode_invocation(command, replacements):
    parts = re.fullmatch(r"(.+?\s+-EncodedCommand\s+)([A-Za-z0-9+/=]+)", command)
    assert parts, command
    script = base64.b64decode(parts[2]).decode("utf-16-le")
    for old, new in replacements:
        assert script.count(old) == 1, (old, script)
        script = script.replace(old, new, 1)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return parts[1] + encoded


def invoke_registered(command, stdin, directory):
    argv = re.fullmatch(r"(\S+)\s+(.+)", command)
    assert argv, command
    return invoke([argv[1], *argv[2].split()], stdin, directory)


def replace_registrations(document, a_binding, release, binding, config_path):
    result = copy.deepcopy(document)
    replacements = [
        (str(Path(a_binding["dependency_python"])), str(Path(binding["dependency_python"]))),
        (str(A / "admin/target_runtime_entry.py"), str(release / "admin/target_runtime_entry.py")),
        (str(LIVE_CONFIG), str(config_path)),
    ]
    count = 0
    for groups in result["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                hook["command"] = encode_invocation(hook["command"], replacements)
                count += 1
    assert count == 5
    return result


def make_cases(directory):
    event_base = {
        "session_id": "whole-release-qualification",
        "cwd": str(directory),
        "transcript_path": str(directory / "session.jsonl"),
        "tool_use_id": "release-tool",
        "turn_id": "release-turn",
        "permission_mode": "default",
    }
    def payload(kind, **kw):
        return json.dumps(
            {**event_base, "hook_event_name": kind, **kw},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    action = {
        "action": {
            "translation": [0.0, 0.0, 0.01],
            "focal_id": "part", "reference_id": "base",
        }
    }
    return [
        ("prompt_unrelated", PROMPT, None, payload(
            PROMPT, prompt="Please summarize the following text in one paragraph."), "empty"),
        ("prompt_spatial_no_host", PROMPT, None, payload(
            PROMPT, prompt="Measure the distance between Cube and Sphere in the current Blender scene.",
            task_kind="spatial_3d"), "unavailable"),
        ("transform_pre_malformed", PRE, TRANSFORM, payload(
            PRE, tool_name=TRANSFORM, tool_input=[]), "deny"),
        ("transform_pre_no_host", PRE, TRANSFORM, payload(
            PRE, tool_name=TRANSFORM, tool_input=action), "deny"),
        ("segment_pre_malformed", PRE, SEGMENT, payload(
            PRE, tool_name=SEGMENT, tool_input=[]), "deny"),
        ("pre_wrong_event", PRE, TRANSFORM, payload(
            POST, tool_name=TRANSFORM, tool_input=action), "deny"),
        ("pre_invalid_json", PRE, TRANSFORM, b"{", "deny"),
        ("transform_post_no_duplicate", POST, TRANSFORM, payload(
            POST, tool_name=TRANSFORM, tool_input=action, tool_response={"status": "refused"}), "empty"),
        ("segment_post_no_duplicate", POST, SEGMENT, payload(
            POST, tool_name=SEGMENT, tool_input={}, tool_response={"status": "refused"}), "empty"),
    ]


def check_output(result, expected):
    if result["returncode"] != 0 or not isinstance(result["output"], dict):
        return False
    output = result["output"]
    if expected == "empty":
        return not output
    context = output.get("hookSpecificOutput", {})
    if expected == "deny":
        return context.get("permissionDecision") == "deny" and context.get("hookEventName") == PRE
    message = context.get("additionalContext", "")
    return (context.get("hookEventName") == PROMPT
            and "unavailable" in message.lower()
            and "host_observation_unavailable" in message.lower())


def arm(arm_id, release, other_release, base_config, document, a_binding, port):
    directory = ROOT / arm_id
    directory.mkdir()
    binding = read(release / "admin/RUNTIME_BINDING.json")
    other = read(other_release / "admin/RUNTIME_BINDING.json")
    entry_path = release / "admin/target_runtime_entry.py"
    python = str(Path(binding["dependency_python"]))
    identity = invoke(
        [python, "-I", "-B", str(entry_path), "identity"], None, directory,
    )
    save(directory / "identity.json", identity)
    runtime = identity["output"]["runtime_identity"]
    assert identity["returncode"] == 0
    for key, value in binding["identity"].items():
        assert runtime[key] == value, key
    config = copy.deepcopy(base_config)
    config["project_root"] = str(release / "site-packages")
    config["state_file"] = str(directory / "state.json")
    config["audit_file"] = str(directory / "audit.jsonl")
    config["blender"] = {"host": "127.0.0.1", "port": port, "timeout_s": 0.3}
    for key in ("base_version", "implementation_revision", "build_id"):
        config["expected_identity"][key] = binding["identity"][key]
    config_path = directory / "connector.json"
    save(config_path, config)
    wrong = copy.deepcopy(config)
    for key in ("base_version", "implementation_revision", "build_id"):
        wrong["expected_identity"][key] = other["identity"][key]
    wrong["audit_file"] = str(directory / "audit_wrong_pin.jsonl")
    wrong_path = directory / "wrong_pin.json"
    save(wrong_path, wrong)
    replay = replace_registrations(document, a_binding, release, binding, config_path)
    save(directory / "isolated_hooks.json", replay)

    def command(mode, tool, registrations):
        groups = registrations["hooks"][mode]
        if tool is not None:
            groups = [group for group in groups if re.fullmatch(group["matcher"], tool)]
        assert len(groups) == 1 and len(groups[0]["hooks"]) == 1
        return groups[0]["hooks"][0]["command"]

    cases = make_cases(ROOT)
    rows = {}
    for name, event, tool, stdin, expected in cases:
        (directory / (name + ".stdin")).write_bytes(stdin)
        result = invoke_registered(command(event, tool, replay), stdin, directory)
        result.update(expected=expected, passed=check_output(result, expected))
        rows[name] = result
    wrong_replay = replace_registrations(document, a_binding, release, binding, wrong_path)
    wrong_input = next(row[3] for row in cases if row[0] == "transform_pre_no_host")
    result = invoke_registered(command(PRE, TRANSFORM, wrong_replay), wrong_input, directory)
    result.update(expected="deny", passed=check_output(result, "deny"))
    rows["pre_opposite_release_pin"] = result

    if arm_id == "B":
        for name, event, tool, stdin, expected in cases:
            if name not in {"prompt_unrelated", "transform_pre_malformed", "segment_post_no_duplicate"}:
                continue
            result = invoke(
                [str(CONSOLE), "--agent", "codex", "--event", event,
                 "--config", str(config_path)], stdin, directory,
            )
            result.update(expected=expected, passed=check_output(result, expected))
            rows["console_" + name] = result

    save(directory / "HOOK_RESULTS.json", rows)
    audit_path = directory / "audit.jsonl"
    audits = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    versions = sorted({row["runtime_identity"]["build_id"] for row in audits
                       if isinstance(row.get("runtime_identity"), dict)
                       and isinstance(row["runtime_identity"].get("build_id"), str)})
    no_state = not (directory / "state.json").exists()
    return {
        "build_id": runtime["build_id"], "runtime_audit_build_ids": versions,
        "cases": len(rows), "passed": sum(result["passed"] for result in rows.values()),
        "failed": [name for name, result in rows.items() if not result["passed"]],
        "isolated_state_absent": no_state,
        "audit_events": sorted({row["event"] for row in audits}),
        "identical_registration_shape": all(
            tuple(group.get("matcher") for group in replay["hooks"][event])
            == tuple(group.get("matcher") for group in document["hooks"][event])
            for event in replay["hooks"]
        ),
    }


def main():
    base = read(LIVE_CONFIG)
    document = read(REGISTERED)
    a_binding = read(A / "admin/RUNTIME_BINDING.json")
    protected = [LIVE_CONFIG, MCP_CONFIG, REGISTERED,
                 LIVE_CONFIG.parent / base["state_file"]]
    before = snapshot(protected)
    save(ROOT / "protected_before.json", before)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
        rows = {
            "A": arm("A", A, B, base, document, a_binding, port),
            "B": arm("B", B, A, base, document, a_binding, port),
        }
    after = snapshot(protected)
    save(ROOT / "protected_after.json", after)
    results = {
        "arms": rows, "protected_equal": before == after, "Blender": 0,
        "host_auto_dispatch_tested": False, "reserved_port_had_listener": False,
    }
    save(ROOT / "RESULT.json", results)
    print(json.dumps(results))
    return int(before != after or any(row["failed"] or not row["isolated_state_absent"]
                                       or row["runtime_audit_build_ids"] != [row["build_id"]]
                                       for row in rows.values()))


if __name__ == "__main__":
    raise SystemExit(main())
