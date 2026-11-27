"""Check each frozen PostToolUse command against an actual direct MCP result."""
from __future__ import annotations

import base64
from hashlib import file_digest
import importlib.util
import json
from pathlib import Path
import socket
import subprocess

ROOT = Path("D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001")
SUPERVISOR = Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK/s2/win_process.py")


def load(p):
    return json.loads(p.read_bytes())


def save(p, row):
    with p.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(row, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pin(p):
    with p.open("rb") as f:
        return {"path": str(p.resolve()), "bytes": p.stat().st_size, "sha256": file_digest(f, "sha256").hexdigest()}


def free_port(endpoint):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((endpoint["host"], endpoint["port"]))


def main():
    reg = load(ROOT / "registration/REGISTRATION.json")
    pre = ROOT / "direct/preflight_02/session_1"
    tool = load(pre / "STATUS.json")
    wire_id = tool["timing"]["id"]
    request_path = pre / "stdio" / (wire_id + ".TX.bin")
    response_path = pre / "stdio" / (wire_id + ".RX.bin")
    request, response = load(request_path), load(response_path)
    assert request["id"] == response["id"] == wire_id and not response["result"].get("isError")
    assert request["params"] == {"name": "human_eye_connection_status", "arguments": {}}
    config_path = Path(reg["connector_config"]["path"])
    assert pin(config_path) == reg["connector_config"]
    config = load(config_path)
    audit_path, state_path = Path(config["audit_file"]), Path(config["state_file"])
    spec = importlib.util.spec_from_file_location("_042_old_bounded_job", SUPERVISOR)
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    output = ROOT / "manual_post_01"
    output.mkdir()
    cases = []
    for arm in ("H0", "H1"):
        row, = [v for v in reg["workspaces"][arm]["commands"] if v["event"] == "PostToolUse"]
        logical = row["logical_argv"]
        assert logical[-1] == str(config_path) and logical[-3] == "PostToolUse"
        argv = row["command"].split() if arm == "H0" else logical
        if arm == "H0":
            assert len(argv) == 5 and argv[-2] == "-EncodedCommand"
            wrapped = base64.b64decode(argv[-1]).decode("utf-16-le")
            assert wrapped == "& " + " ".join("'" + arg + "'" for arg in logical) + "; exit $LASTEXITCODE"
        else:
            assert subprocess.list2cmdline(argv) == row["command"]
        folder = output / arm
        folder.mkdir()
        workspace = reg["workspaces"][arm]["workspace"]
        payload = {"hook_event_name": "PostToolUse", "cwd": workspace, "permission_mode": "default",
                   "session_id": "042-final-manual-post-" + arm, "turn_id": "manual-no-host-" + arm,
                   "tool_name": "mcp__human_eye_live__human_eye_connection_status", "tool_use_id": "manual-" + wire_id,
                   "tool_input": request["params"]["arguments"], "tool_response": response["result"]}
        save(folder / "INPUT.json", payload)
        save(folder / "ARGV.json", argv)
        free_port(reg["endpoint"])
        before = audit_path.read_bytes()
        state_before = pin(state_path) if state_path.exists() else None
        timing, stdout, stderr = supervisor.invoke(argv, (folder / "INPUT.json").read_bytes(), Path(workspace), timeout_s=30)
        (folder / "STDOUT.bin").write_bytes(stdout)
        (folder / "STDERR.bin").write_bytes(stderr)
        save(folder / "PROCESS.json", timing)
        after = audit_path.read_bytes()
        assert after.startswith(before)
        tail = after[len(before):]
        (folder / "AUDIT_APPEND.jsonl").write_bytes(tail)
        events = [json.loads(line) for line in tail.splitlines()]
        free_port(reg["endpoint"])
        assert timing["returncode"] == 0 and timing["terminal"] == "completed" and timing["pipe_threads_joined"]
        assert timing["job_accounting"]["active_processes"] == 0 and not timing["job_pids_at_cleanup"]
        assert json.loads(stdout) == {} and not stderr
        skip, = [item for item in events if item["event"] == "host_hook_skip"]
        trace, = [item for item in events if item["event"] == "request_trace"]
        assert len(events) == 2
        assert skip["status"] == "tool_result_delivery_retained" and skip["scene_read"] is False
        assert trace["trace"]["outcome"] == "duplicate_delivery_omitted"
        assert (pin(state_path) if state_path.exists() else None) == state_before
        cases.append({"arm": arm, "result": "pass", "scope": "direct command without Codex dispatch",
                      "skip": skip["status"], "outcome": trace["trace"]["outcome"],
                      "scene_reads": 0, "job_exit_verified": True, "unchanged_state": True,
                      "append": pin(folder / "AUDIT_APPEND.jsonl"), "process": pin(folder / "PROCESS.json")})
    save(output / "RESULT.json", {"status": "pass", "cases": cases, "actual_direct_tool_result": pin(response_path),
                                  "fixture_request": pin(request_path), "registration": pin(ROOT / "registration/REGISTRATION.json"),
                                  "scope": "manual delivery payload. Codex retention and automatic event dispatch remain untested.",
                                  "supervisor": pin(SUPERVISOR), "model_calls": 0, "host_dispatches": 0})


if __name__ == "__main__":
    main()
