"""Freeze independent command-exit controls for the M6-041 S2 Hook experiment."""
import argparse
import base64
import json
from pathlib import Path
import socket
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_s2 as stage
from win_process import invoke

PLAN = HERE / "PLAN.json"
CASE = "prompt_unrelated"
ORDER = "ABDC"
BAD_OPTION = "--m6-041-invalid-hook-option"


def freeze():
    s2 = stage.read(stage.PLAN)
    template = s2["inputs"][CASE]
    plan = {
        "schema": "m6-041-s2-error-control-v1",
        "parent_plan": stage.artifact(stage.PLAN),
        "parent_summary": stage.artifact(HERE.parent / "formal/SUMMARY.json"),
        "parent_results": stage.artifact(HERE.parent / "RESULTS.json"),
        "program": stage.artifact(Path(__file__)),
        "stdin": template["input_040"][0],
        "slots": [{"condition": case, "arm": arm} for case in ("unknown_option", "missing_connector") for arm in ORDER],
        "conditions": {
            "unknown_option": {
                "sole_input_difference": "Append one unsupported Hook option to the actual bound command's inner argv.",
                "option": BAD_OPTION,
                "stdout": "exactly zero bytes",
                "stderr": "same nonempty usage plus one argparse rejection under all four arms",
                "exit": 2,
                "audit_rows": 0,
            },
            "missing_connector": {
                "sole_input_difference": "Leave the exact isolated --config path absent rather than writing the normal per-slot connector.",
                "stdout": "exactly b'{}\\r\\n'",
                "stderr": "exactly zero bytes",
                "exit": 0,
                "audit_rows": 0,
            },
        },
        "common_contract": "Original stdin byte identity; exact launcher/real wrapper; no audit/state/lock, Blender/other connection, or active owned PID after completion.",
        "purpose": "Independent command-exit control; no timing qualification, no new scored slots, no desktop Codex consumption, trust or in-flight host behavior.",
        "receipt": {"stage": "S2-error-control", "approved_control_slots": 8},
    }
    stage.save(PLAN, plan)
    print(json.dumps(stage.artifact(PLAN), ensure_ascii=False), flush=True)


def run_slot(slot, parent, installs, parent_plan):
    arm, condition = slot["arm"], slot["condition"]
    kernel, h = stage.ARMS[arm]
    release = installs[kernel]
    template = parent_plan["inputs"][CASE]
    stdin = stage.verified(parent["stdin"]).read_bytes()
    assert parent["stdin"] == template["input_040"][0]
    event = json.loads(stdin)
    folder = HERE / "run" / condition / arm
    folder.mkdir(parents=True, exist_ok=False)
    cfg_path, audit, state = (folder / x for x in ("connector.json", "audit.jsonl", "state.json"))
    cfg = stage.read(stage.verified(template["config_040"]))
    cfg.update(project_root=release["site"], audit_file=str(audit), state_file=str(state))
    for key in ("base_version", "implementation_revision", "build_id"):
        cfg["expected_identity"][key] = release["identity"][key]
    with socket.socket() as check:
        check.bind(("127.0.0.1", 0))
        check.listen()
        check.setblocking(False)
        cfg["blender"]["port"] = check.getsockname()[1]
        stage.save(folder / "intended_connector.json", cfg)
        if condition == "unknown_option":
            stage.save(cfg_path, cfg)
        initial_connector = stage.artifact(cfg_path) if cfg_path.is_file() else None

        _, wrapper, direct = stage.arm_command(template, release, cfg_path, event, h)
        hook = stage.hooks(wrapper, event)
        if condition == "unknown_option":
            prefix, script, equal = stage.unpack_wrapper(hook["command"])
            assert equal == direct and script.endswith("; exit $LASTEXITCODE")
            script = script.removesuffix("; exit $LASTEXITCODE") + " '" + BAD_OPTION + "'; exit $LASTEXITCODE"
            hook["command"] = prefix + " " + base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            direct.append(BAD_OPTION)
        assert stage.unpack_wrapper(hook["command"])[2] == direct
        argv = hook["command"].split() if h == "H0" else direct
        stage.save(folder / "isolated_hooks.json", wrapper)
        stage.save(folder / "argv.json", argv)
        stage.save(folder / "logical_inner_argv.json", direct)
        stage.put(folder / "INPUT.bin", stdin)
        result, output, error = invoke(argv, stdin, folder, timeout_s=template["registration_timeout_s"])
        connections = 0
        while True:
            try:
                conn, _ = check.accept()
                with conn:
                    connections += 1
            except BlockingIOError:
                break

    stage.put(folder / "STDOUT.bin", output)
    stage.put(folder / "STDERR.bin", error)
    owner_exe = template["wrapper_binary"]["path"] if h == "H0" else release["dependency_python"]
    end_connector = stage.artifact(cfg_path) if cfg_path.is_file() else None
    if condition == "unknown_option":
        reason = ("error: unrecognized arguments: " + BAD_OPTION).encode("ascii")
        expected_exit = result["returncode"] == 2 and output == b"" and error.startswith(b"usage: ") and error.splitlines()[-1].endswith(reason)
    else:
        expected_exit = result["returncode"] == 0 and output == b"{}\r\n" and error == b""
    clean = not any(p.exists() or p.with_name(p.name + ".lock").exists() for p in (audit, state))
    valid = (result["terminal"] == "completed" and Path(result["resolved_executable"]).resolve() == Path(owner_exe).resolve()
             and not result["pipe_errors"] and result["pipe_threads_joined"] and not result["job_pids_at_cleanup"]
             and result["job_accounting"]["active_processes"] == 0 and clean and connections == 0
             and end_connector == initial_connector and expected_exit)
    row = {**slot, **result, "kernel": kernel, "launcher": h, "valid": valid,
           "no_audit_state_or_locks": clean, "loopback_connections": connections,
           "connector_before": initial_connector, "connector_after": end_connector,
           "stdin": stage.artifact(folder / "INPUT.bin"),
           "stdout": stage.artifact(folder / "STDOUT.bin"), "stderr": stage.artifact(folder / "STDERR.bin")}
    stage.save(folder / "RESULT.json", row)
    print(condition, arm, result["returncode"], len(output), len(error), valid, flush=True)
    return row


def run(owner_receipt):
    control = stage.read(PLAN)
    assert stage.read(owner_receipt) == {**control["receipt"], "plan_sha256": stage.artifact(PLAN)["sha256"]}
    for key in ("parent_plan", "parent_summary", "parent_results", "program", "stdin"):
        stage.verified(control[key])
    parent = stage.read(stage.PLAN)
    releases = stage.validate_source(parent)["arms"]
    stage.save(HERE / "run" / "WINDOW.json", {"receipt": stage.artifact(owner_receipt), "plan": stage.artifact(PLAN)})
    rows = [run_slot(spec, control, releases, parent) for spec in control["slots"]]
    equal = {}
    for name in control["conditions"]:
        current = [r for r in rows if r["condition"] == name]
        equal[name] = (len(current) == 4
                       and all(len({r[key]["sha256"] for r in current}) == 1 for key in ("stdin", "stdout", "stderr")))
    stage.validate_source(parent)
    stage.verified(control["parent_summary"])
    stage.verified(control["parent_results"])
    pass_all = len(rows) == 8 and all(r["valid"] for r in rows) and all(equal.values())
    summary = {"status": "pass" if pass_all else "fail", "executed": len(rows), "valid": sum(r["valid"] for r in rows),
               "equal_raw_binary_by_condition": equal, "scored_slots_added": 0, "formal_S2_n": 84,
               "scope": control["purpose"], "rows": [stage.artifact(HERE / "run" / x["condition"] / x["arm"] / "RESULT.json") for x in rows]}
    stage.save(HERE / "run" / "SUMMARY.json", summary)
    return 0 if pass_all else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--window-receipt", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        return freeze()
    assert args.window_receipt is not None
    return run(args.window_receipt)


if __name__ == "__main__":
    raise SystemExit(main())
