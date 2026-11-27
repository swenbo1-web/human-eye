"""Freeze and run one-command Windows Hook comparisons for 041 S2."""
import argparse
import base64
from collections import Counter
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from win_process import ARCHIVE, invoke

ROOT = HERE.parent
OLD041 = ROOT / "install/PINS.json"
ARCHIVED = Path("D:/HumanEye/runs/M3-BVH-DEEP-COMPARE-040")
OLD_RELEASE = Path("D:/he_m3_bvh032_private_654c1f69/.human-eye/releases/9.7.2+b32g")
CASE_HOME = ARCHIVED / "entry_runs/light_matrix_002/r1"
ARMS = {"A": ("032", "H0"), "B": ("r3", "H0"), "C": ("032", "H1"), "D": ("r3", "H1")}
CASES = {
    "prompt_unrelated": ("intent_general", "hook.prompt", "intent_general"),
    "transform_post_no_duplicate": ("tool_result_delivery_retained", "hook.readback", "duplicate_delivery_omitted"),
    "segment_post_no_duplicate": ("tool_result_delivery_retained", "hook.readback", "duplicate_delivery_omitted"),
}
ORDER = ("ABDC", "BCAD", "CDBA", "DACB")
PROTECTED = (Path("D:/hefe/.codex/hooks.json"),
             Path("D:/hefe/.codex/config.toml"),
             Path("D:/hefe/.human-eye/live-connector.json"))
PLAN = HERE / "PLAN.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def artifact(path):
    data = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(data), sha256=sha(data))


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, allow_nan=False, indent=2)
        file.write("\n")


def put(path, data):
    with path.open("xb") as file:
        file.write(data)


def verified(ref):
    path = Path(ref["path"])
    assert artifact(path) == ref, path
    return path


def hooks(registration, data):
    event = data["hook_event_name"]
    tool = data.get("tool_name")
    groups = [g for g in registration["hooks"][event] if tool is None or re.fullmatch(g["matcher"], tool)]
    assert len(groups) == len(groups[0]["hooks"]) == 1
    return groups[0]["hooks"][0]


def unpack_wrapper(command):
    prefix, sep, encoded = command.rpartition(" ")
    assert sep and prefix.split()[-1].lower() == "-encodedcommand"
    script = base64.b64decode(encoded, validate=True).decode("utf-16-le")
    match = re.fullmatch(r"& ((?:'[^']*' )*'[^']*'); exit \$LASTEXITCODE", script)
    assert match is not None
    raw_argv = re.findall(r"'([^']*)'", match[1])
    assert raw_argv[1:3] == ["-I", "-B"] and raw_argv[4:7] == ["hook", "--agent", "codex"]
    return prefix, script, raw_argv


def one_case(name):
    root = CASE_HOME / name
    wrapped, direct = root / "deep_hook", root / "direct"
    inputs = [artifact(wrapped / "INPUT.bin"), artifact(direct / "INPUT.bin")]
    assert inputs[0]["sha256"] == inputs[1]["sha256"]
    payload = read(wrapped / "INPUT.bin")
    registered = artifact(wrapped / "isolated_hooks.json")
    hook = hooks(read(registered["path"]), payload)
    assert hook["type"] == "command" and hook["timeout"] == 30
    pref, script, nested = unpack_wrapper(hook["command"])
    direct_ref = artifact(direct / "direct_argv.json")
    d_argv = read(direct_ref["path"])
    assert nested[:-1] == d_argv[:-1] and Path(nested[-1]) == wrapped / "connector.json"
    assert Path(d_argv[-1]) == direct / "connector.json"
    assert nested[7:10] == ["--event", payload["hook_event_name"], "--config"]
    config = artifact(wrapped / "connector.json")
    cfg_0, cfg_1 = read(config["path"]), read(direct / "connector.json")
    for a in (cfg_0, cfg_1):
        for k in ("state_file", "audit_file"):
            del a[k]
        del a["blender"]["port"]
    assert cfg_0 == cfg_1
    return {"input_040": inputs, "wrapped_040": registered, "direct_040": direct_ref,
            "config_040": config, "direct_config_040": artifact(direct / "connector.json"),
            "expected": dict(zip(("skip", "operation", "outcome"), CASES[name])),
            "registration_timeout_s": hook["timeout"], "event": payload["hook_event_name"],
            "exact_inner_argv_agrees_before_config_rebind": True,
            "wrapper_binary": artifact(Path(shutil.which(pref.split()[0]))),
            "original_script_sha256": sha(script.encode("utf-16-le"))}


def create_plan():
    cases = list(CASES)
    slots = []
    for k in range(7):
        for j in range(3):
            index = (j + k) % 3
            case = cases[index]
            for arm in ORDER[(index + k) % 4]:
                spec = {"block": k + 1, "event_case": case, "arm": arm}
                spec.update(kernel=ARMS[arm][0], launcher=ARMS[arm][1])
                slots.append(spec)
    assert len(slots) == 84 and set(Counter((s["event_case"], s["arm"]) for s in slots).values()) == {7}
    release_pins = read(OLD041)
    return {"schema": "m6-041-s2-frozen-v1", "purpose": "fixed command launch and exit; no automatic host claim",
            "controls": ["archive_unrepaired_040_diagnostic", "manual_preflight", "manual_deadline", "manual_cancel"],
            "kept_production_hashes": {str(p): artifact(p) if p.is_file() else None for p in PROTECTED},
            "inputs": {case: one_case(case) for case in cases}, "implementation": artifact(Path(__file__)),
            "process_supervision": artifact(HERE / "win_process.py"), "job_api": artifact(ARCHIVE),
            "job_api_common": artifact(ARCHIVE.with_name("common.py")),
            "release_pins": artifact(OLD041), "arms": ARMS, "runtime_digest": {k: v["source_sha256"] for k, v in release_pins["arms"].items()},
            "slots": slots, "replaced_parameters": ["same-bound interpreter", "isolated launcher", "isolated config"],
            "environment": {"dependency_environment": "original 032 dependency Python, same A/B/C/D",
                            "inherit_process_environment": "same parent for every arm; no external model",
                            "blender": "no Blender; same IPv4 loopback sentinel semantics and 0.3s connector budget on every arm",
                            "cache": "fresh process and state/audit per slot; OS file caches not flushed",
                            "sampling": "same Job 20ms target sampling and 5ms controller poll across all arms; sampling remains in measured T"},
            "timing": {"boundary": "full invocation to pipe and owned Job cleanup; preparation separate", "timeout_s": 30,
                       "manual_deadline_and_cancel_controls_not_scored": True},
            "gate": {"events": 3, "kernel_arms_independently": ["032", "r3"], "paired_blocks": 7,
                     "minimum_paired_median_reduction": [1, 10], "minimum_direct_faster": 5, "all_slots_semantic_pass": True},
            "automatic_dispatch": {"status": "NOT_RUN", "reason": "all new isolated commands have new hook hashes; no genuine prior Codex trust for those commands. No bypass, current config edit, paid provider or copied trust used. Manual registered commands and direct calls establish command invocation only.",
                "coverage_gaps": ["Codex-side automatic matching and exact hook approval", "host event delivery", "Codex stdout/stderr processing", "Codex timeout/cancel propagation"]}}


def protected(plan):
    for name, ref in plan["kept_production_hashes"].items():
        path = Path(name)
        assert (artifact(path) if path.is_file() else None) == ref, path


def validate_source(plan):
    for key in ("implementation", "release_pins", "process_supervision", "job_api", "job_api_common"):
        verified(plan[key])
    protected(plan)
    release_pins = read(OLD041)
    for row in release_pins["arms"].values():
        binding = read(verified(row["binding"]))
        assert binding["identity"] == row["identity"] and len(binding["source_files"]) == 143
        site = Path(binding["site_packages"])
        assert all(sha((site / x["path"]).read_bytes()) == x["sha256"] for x in binding["source_files"])
        verified(row["launcher"])
        verified(row["startup"])
        verified(row["wheel"])
    for data in plan["inputs"].values():
        for key in ("wrapped_040", "direct_040", "config_040", "direct_config_040", "wrapper_binary"):
            verified(data[key])
        for ref in data["input_040"]:
            verified(ref)
    return release_pins


def arm_command(templates, arm_pin, cfg, payload, launcher):
    registered = read(verified(templates["wrapped_040"]))
    hook = hooks(registered, payload)
    prefix, script, old_argv = unpack_wrapper(hook["command"])
    assert sha(script.encode("utf-16-le")) == templates["original_script_sha256"]
    direct = read(verified(templates["direct_040"]))
    assert old_argv[:-1] == direct[:-1]
    for index, value in ((0, arm_pin["dependency_python"]),
                         (3, str(verified(arm_pin["launcher"]))), (10, str(cfg))):
        old = old_argv[index]
        assert script.count(old) == 1 and "'" not in value
        script = script.replace(old, value)
        direct[index] = value
    hook["command"] = prefix + " " + base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    assert unpack_wrapper(hook["command"])[2] == direct
    return (hook["command"].split() if launcher == "H0" else direct), registered, direct


def records(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def verify_audit(rows, payload, expected, identity):
    if len(rows) != 2 or [row.get("event") for row in rows] != ["host_hook_skip", "request_trace"]:
        return False
    skip, trace_row = rows
    trace = trace_row.get("trace", {})
    match = dict(session_id="codex:" + payload["session_id"], turn_id=payload["turn_id"], tool_use_id=payload["tool_use_id"])
    return (skip.get("status") == expected["skip"] and skip.get("scene_read") is False and skip.get("engine_invoked") is False
            and all(row.get("hook_event") == payload["hook_event_name"] and row.get("invocation_source") == "hook_command"
                    and row.get("identity_check", {}).get("compatible") is True
                    and row.get("runtime_identity", {}).get("build_id") == identity["build_id"]
                    and all(row.get(k) == v for k, v in match.items()) for row in rows)
            and trace.get("operation") == expected["operation"] and trace.get("outcome") == expected["outcome"]
            and all(trace.get("correlation", {}).get(k) == v for k, v in match.items())
            and trace.get("annotations", {}).get("engine_invoked") is False
            and trace.get("annotations", {}).get("include_image") is False
            and isinstance(trace.get("duration_ns"), int) and trace["duration_ns"] >= 0
            and trace.get("spans") == [] and trace.get("image_events") == [])


def run_slot(folder, spec, plan, installs, *, control=None):
    folder.mkdir(parents=True, exist_ok=False)
    case, kernel, h = (spec[k] for k in ("event_case", "kernel", "launcher"))
    template = plan["inputs"][case]
    stdin = verified(template["input_040"][0]).read_bytes()
    payload = json.loads(stdin)
    arm_pin = installs[kernel]
    binding = verified(arm_pin["binding"])
    config = read(verified(template["config_040"]))
    cfg_path = folder / "connector.json"
    audit_path, state_path = folder / "audit.jsonl", folder / "state.json"
    config.update(project_root=arm_pin["site"], state_file=str(state_path), audit_file=str(audit_path))
    identity = arm_pin["identity"]
    for key in ("base_version", "implementation_revision", "build_id"):
        config["expected_identity"][key] = identity[key]
    with socket.socket() as health:
        health.bind(("127.0.0.1", 0))
        health.listen()
        health.setblocking(False)
        config["blender"]["port"] = health.getsockname()[1]
        save(cfg_path, config)
        argv, wrapped, direct = arm_command(template, arm_pin, cfg_path, payload, h)
        save(folder / "isolated_hooks.json", wrapped)
        save(folder / "argv.json", argv)
        save(folder / "logical_inner_argv.json", direct)
        put(folder / "INPUT.bin", stdin)
        limits = template["registration_timeout_s"]
        deadline = .05 if control == "deadline" else limits
        cancel = .05 if control == "cancel" else None
        status, stdout, stderr = invoke(argv, stdin, folder, timeout_s=deadline, cancellation_s=cancel)
        connected = 0
        while True:
            try:
                conn, _ = health.accept()
                with conn:
                    connected += 1
            except BlockingIOError:
                break
    put(folder / "STDOUT.bin", stdout)
    put(folder / "STDERR.bin", stderr)
    try:
        empty = json.loads(stdout.decode("utf-8-sig")) == {}
    except (ValueError, UnicodeDecodeError):
        empty = False
    audit = records(audit_path)
    state = state_path.exists() or state_path.with_name("state.json.lock").exists()
    bound = artifact(binding) == arm_pin["binding"] and artifact(Path(direct[3])) == arm_pin["launcher"]
    cleaned = status["job_accounting"]["active_processes"] == 0 and not status["job_pids_at_cleanup"] and status["pipe_threads_joined"]
    audit_ok = verify_audit(audit, payload, template["expected"], identity)
    exact_exec = str(Path(status["resolved_executable"]).resolve()).lower() == str(Path(template["wrapper_binary"]["path"] if h=="H0" else arm_pin["dependency_python"]).resolve()).lower()
    valid = (status["terminal"] == "completed" and status["returncode"] == 0 and not status["pipe_errors"] and not stderr
             and empty and audit_ok and bound and cleaned and exact_exec and connected == 0 and not state)
    if control:
        wanted = {"deadline": "expired_in_harness", "cancel": "cancelled_by_harness"}[control]
        valid = status["terminal"] == wanted and cleaned and exact_exec and bound and not state and connected == 0
    row = {**spec, **status, "control": control, "valid": valid, "empty_stdout_object": empty,
           "stdin": artifact(folder / "INPUT.bin"), "stdout": artifact(folder / "STDOUT.bin"), "stderr": artifact(folder / "STDERR.bin"),
           "binding": artifact(binding), "source_sha256": identity["source_sha256"],
           "only_authorized_inner_argv_difference": True, "exact_executable": exact_exec,
           "no_connection_or_state": connected == 0 and not state, "loopback_connections": connected,
           "state_or_state_lock_exists": state, "cleaned": cleaned, "audit_pass": audit_ok,
           "audit_events": [r.get("event") for r in audit], "audit": artifact(audit_path) if audit_path.is_file() else None,
           "time_limit_s": deadline, "cancellation_s": cancel}
    save(folder / "RESULT.json", row)
    print(spec["block"], case, spec["arm"], control, status["terminal"], valid, flush=True)
    return row


def check_preflight(plan, installs, tag):
    folder = HERE / tag
    folder.mkdir(exist_ok=False)
    spec = {"block": 0, "event_case": "prompt_unrelated"}
    cases = [(arm, None) for arm in ARMS] + [("A", "deadline"), ("D", "cancel")]
    rows = []
    for arm, control in cases:
        kernel, launcher = ARMS[arm]
        row = run_slot(folder / (arm + ("-" + control if control else "")),
                       {**spec, "arm": arm, "kernel": kernel, "launcher": launcher}, plan, installs, control=control)
        rows.append(dict(arm=arm, control=control, valid=row["valid"]))
    protected(plan)
    save(folder / 'SUMMARY.json', {"status": "pass" if all(r["valid"] for r in rows) else "fail", "cases": rows,
                                    "formal_count": 0, "purpose": "manual command and owned Job controls, not a host dispatch or scored slot"})


def summarize(rows, plan):
    metrics = {}
    for case in CASES:
        subset = [r for r in rows if r["event_case"] == case]
        for a, c in (("A", "C"), ("B", "D")):
            pairs = []
            for block in range(1, 8):
                lane = {r["arm"]: r for r in subset if r["block"] == block}
                assert set(lane) == set(ARMS)
                if not all(lane[k]["valid"] for k in (a,c)):
                    continue
                pairs.append((lane[a]["T_ns"], lane[c]["T_ns"]))
            gain = median([1-Fraction(d, w) for w,d in pairs]) if len(pairs) == 7 else None
            faster = sum(d < w for w,d in pairs)
            metrics[case + "/" + c + "_over_" + a] = {"valid_pairs": len(pairs), "paired_wrapped_direct_ns": pairs,
               "median_paired_reduction": float(gain) if gain is not None else None, "direct_faster": faster,
               "pass": bool(gain is not None and gain >= Fraction(1,10) and faster >= 5)}
    return {"status": "pass_manual_fixed_command" if all(x["pass"] for x in metrics.values()) else "fail_s2_gate",
            "metrics": metrics, "counts": {"attempted": len(rows), "planned": 84, "valid": sum(r["valid"] for r in rows)},
            "automatic_dispatch": plan["automatic_dispatch"], "provisionally_restricted": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight", "formal"))
    parser.add_argument("--tag", default="preflight_001")
    parser.add_argument("--window-receipt", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        plan = create_plan()
        save(PLAN, plan)
        validate_source(plan)
        print(artifact(PLAN))
        return
    plan = read(PLAN)
    installs = validate_source(plan)["arms"]
    if args.action == "preflight":
        assert re.fullmatch(r"preflight_[0-9]{3}", args.tag)
        check_preflight(plan, installs, args.tag)
        return
    assert args.window_receipt and args.window_receipt.is_file(), "the experiment owner must open an S2 window"
    permission = read(args.window_receipt)
    assert permission == {"stage": "S2", "plan_sha256": artifact(PLAN)["sha256"], "approved_frozen_slots": 84}
    folder = HERE / "formal"
    folder.mkdir(exist_ok=False)
    save(folder / "WINDOW.json", {"approval": artifact(args.window_receipt), "plan": artifact(PLAN)})
    rows = []
    for spec in plan["slots"]:
        target = folder / f'block{spec["block"]:02}' / spec["event_case"] / spec["arm"]
        row = run_slot(target, spec, plan, installs)
        rows.append(row)
        if not row["no_connection_or_state"] or not row["cleaned"]:
            save(folder / "STOP.json", {"status":"contract_stop", "completed_receipts":len(rows),
                                         "unrun":plan["slots"][len(rows):], "last":artifact(target/"RESULT.json")})
            raise RuntimeError("unexpected connection, state write or owned process")
    validate_source(plan)
    save(folder / "SUMMARY.json", summarize(rows, plan))


if __name__ == "__main__":
    main()