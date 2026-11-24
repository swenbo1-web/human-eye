from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import time


BASE = Path(__file__).resolve().parent
OUT = BASE / "verified"
DESKTOP = Path("D:/hefe").resolve()
PROJECT = OUT / "replica"
SERVER = Path(".codex/config.toml")
HOOKS = Path(".codex/hooks.json")
CONNECTOR = Path(".human-eye/live-connector.routing-spatial.json")
STATE = Path(".human-eye/live-state.routing-spatial.json")
EVENTS = Path(".human-eye/live-events.routing-spatial.jsonl")
RELEASES = {
    "A": DESKTOP / ".human-eye/releases/9.7.2+20261110.scale.opt.r1",
    "B": Path("D:/he_m3_bvh032_private_654c1f69/.human-eye/releases/9.7.2+b32g"),
}
EXPECTED = {
    "A": ("3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd",
          "e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2", 137),
    "B": ("0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241",
          "9d1c899abaaf199f4bc19e231d5232853baf7d353f3ff681080a7c20c4768cf6", 143),
}


def digest(raw):
    return sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def save(path, value):
    path.write_bytes(encode(value))


def registered(arm):
    script = (RELEASES[arm] / "admin/target_runtime_entry.py").resolve()
    binding = json.loads(script.with_name("RUNTIME_BINDING.json").read_bytes())
    source, sha, count = EXPECTED[arm]
    assert digest(script.read_bytes()) == sha
    assert binding["identity"]["build_id"] == "sha256:" + source
    assert len(binding["source_files"]) == count
    python = Path(binding["dependency_python"]).resolve()
    assert python.is_file()
    return [str(python), "-I", "-B", str(script)]


def run(name, argv, input_data=None, ok=True):
    start = time.perf_counter_ns()
    p = subprocess.run(argv, input=input_data, capture_output=True, cwd=PROJECT, timeout=45)
    (OUT / (name + ".stdout")).write_bytes(p.stdout)
    (OUT / (name + ".stderr")).write_bytes(p.stderr)
    save(OUT / (name + ".receipt.json"), {
        "exit": p.returncode, "ms": (time.perf_counter_ns() - start) / 1e6,
        "argv": argv, "stdout_sha256": digest(p.stdout), "stderr_sha256": digest(p.stderr),
    })
    assert (p.returncode == 0) == ok, (name, p.returncode, p.stderr.decode("utf-8", "replace"))
    return p


def load_admin():
    # The actual A module is used to relocate the fixture. All migrations use its CLI.
    entry = Path(registered("A")[-1])
    binding = json.loads(entry.with_name("RUNTIME_BINDING.json").read_bytes())
    script = entry.with_name("installed_release.py")
    assert digest(script.read_bytes()) == binding["admin_sha256"]
    sys.path.insert(0, str(RELEASES["A"] / "site-packages"))
    spec = importlib.util.spec_from_file_location("_release_rollback_admin", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def prepare():
    assert PROJECT.resolve().is_relative_to(OUT)
    PROJECT.mkdir()
    for part in (".human-eye", ".codex"):
        (PROJECT / part).mkdir()
    admin = load_admin()
    raw = (DESKTOP / SERVER).read_bytes()
    _, old_server = admin._load_server(raw, "codex")
    assert old_server["args"][:4] == [*registered("A")[1:], "serve"]
    assert Path(old_server["args"][5]).resolve() == DESKTOP / CONNECTOR
    assert Path(old_server["command"]).resolve() == Path(registered("A")[0]).resolve()
    relocated = deepcopy(old_server)
    relocated["args"][5] = str(PROJECT / CONNECTOR)
    relocated["cwd"] = str(PROJECT)
    (PROJECT / SERVER).write_bytes(admin._replace_toml_server(raw, old_server, relocated))
    hooks = json.loads((DESKTOP / HOOKS).read_bytes())
    hook_count = 0
    for event in admin.EVENTS:
        for group in hooks["hooks"].get(event, []):
            for hook in group["hooks"]:
                if not admin._suspected_engine_hook(hook, "windows", group.get("matcher")):
                    continue
                argv = admin._strict_hook_argv(hook, "windows", "codex")
                assert Path(argv[3]).resolve() == Path(registered("A")[-1]).resolve()
                pos = argv.index("--config") + 1
                assert Path(argv[pos]).resolve() == DESKTOP / CONNECTOR
                argv[pos] = str(PROJECT / CONNECTOR)
                new_hook, _ = admin._hook_spec(argv, "codex", "windows")
                hook.update({k: v for k, v in new_hook.items() if k != "timeout"})
                hook_count += 1
    assert hook_count == 5
    save(PROJECT / HOOKS, hooks)

    current = json.loads((DESKTOP / CONNECTOR).read_bytes())
    state_raw = (DESKTOP / STATE).read_bytes()
    admin._check_state(state_raw, current)
    config = deepcopy(current)
    config.update(state_file=STATE.name, audit_file=EVENTS.name)
    config["blender"]["port"] = 1
    save(PROJECT / CONNECTOR, config)
    (PROJECT / STATE).write_bytes(admin._state_binding_bytes(
        state_raw, admin._fingerprint(current), admin._fingerprint(config)
    ))
    (PROJECT / EVENTS).write_bytes((DESKTOP / EVENTS).read_bytes())


def state_data():
    state = json.loads((PROJECT / STATE).read_bytes())
    assert state.pop("config_fingerprint")
    return state


def actual_endpoint(name, arm):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "release-rollback-qualification", "version": "1"}
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "human_eye_connection_status", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "ping"},
    ]
    actual = registered(arm) + ["serve", "--config", str(PROJECT / CONNECTOR)]
    audit = PROJECT / EVENTS
    prior_audit = audit.read_bytes()
    p = run(name, actual, b"".join(encode(item).replace(b"\n", b"") + b"\n" for item in requests))
    messages = {m["id"]: m for m in map(json.loads, p.stdout.splitlines())}
    assert messages.keys() == {1, 2, 3, 4}
    assert all("result" in msg and "error" not in msg for msg in messages.values())
    status = json.loads(messages[3]["result"]["content"][0]["text"])
    assert status.get("reason_code") != "state_configuration_binding_mismatch", status
    config = json.loads((PROJECT / CONNECTOR).read_bytes())
    assert config["expected_identity"]["build_id"] == "sha256:" + EXPECTED[arm][0]
    after = audit.read_bytes()
    appended = after.splitlines(keepends=True)[-2:]
    for line in appended:
        record = json.loads(line)
        assert record["event"] == "request_trace"
        pinned = record["runtime_identity"]
        assert pinned["build_id"] == "sha256:" + EXPECTED[arm][0], pinned
    expected = prior_audit
    for line in appended:
        if len(expected) > 2 * 1024 * 1024:
            expected = b"\n".join(expected.splitlines()[-1000:]) + b"\n"
        expected += line
    assert after == expected, (name, "unexpected audit edits")
    save(OUT / (name + ".audit.json"), {
        "before": digest(prior_audit), "after": digest(after),
        "before_line_count": len(prior_audit.splitlines()), "after_line_count": len(after.splitlines()),
        "appended_request_traces": 2, "rollover_matches_source": True,
    })
    return status


def admin(name, arm, action, prior=None, plan=None, ok=True):
    argv = registered(arm) + ["admin", action, "--agent", "codex",
                              "--project", str(PROJECT),
                              "--expected-build", "sha256:" + EXPECTED[arm][0]]
    if prior:
        argv += ["--prior-launcher", registered(prior)[-1], EXPECTED[prior][1],
                 "sha256:" + EXPECTED[prior][0]]
    if plan:
        argv += ["--apply", "--plan-sha256", plan]
    journal = PROJECT / EVENTS
    journal_before = digest(journal.read_bytes())
    p = run(name, argv, ok=ok)
    assert digest(journal.read_bytes()) == journal_before
    return json.loads(p.stdout) if ok else p


def identity(name, arm):
    p = run(name, registered(arm) + ["identity"])
    value = json.loads(p.stdout)
    assert value["runtime_identity"]["source_sha256"] == EXPECTED[arm][0]
    return value


def same_ledger(expected):
    assert state_data() == expected


def main():
    OUT.mkdir()
    prepare()
    initial = state_data()
    event_hash = digest((PROJECT / EVENTS).read_bytes())
    for arm in RELEASES:
        identity("identity_" + arm, arm)
    admin("A_doctor_before", "A", "doctor")
    actual_endpoint("A_MCP_before", "A")
    plan = admin("forward_plan", "B", "plan", "A")
    same_ledger(initial)
    forward = admin("forward_apply", "B", "plan", "A", plan["plan_sha256"])
    same_ledger(initial)
    admin("B_doctor_after", "B", "doctor")
    actual_endpoint("B_MCP_after", "B")
    reverse = admin("reverse_plan_initial", "A", "plan", "B")
    updated = json.loads((PROJECT / STATE).read_bytes())
    updated["release_acceptance_ledger_marker"] = "retained latest isolated state"
    save(PROJECT / STATE, updated)
    latest = state_data()
    pins_before = {str(f): digest((PROJECT / f).read_bytes()) for f in (SERVER, HOOKS, CONNECTOR, STATE)}
    rejected = admin("reverse_stale_refused", "A", "plan", "B", reverse["plan_sha256"], ok=False)
    assert b"plan" in rejected.stderr.lower(), rejected.stderr
    assert {p: digest((PROJECT / p).read_bytes()) for p in pins_before} == pins_before
    fresh = admin("reverse_plan_latest", "A", "plan", "B")
    backward = admin("reverse_apply_latest", "A", "plan", "B", fresh["plan_sha256"])
    admin("A_doctor_after_rollback", "A", "doctor")
    actual_endpoint("A_MCP_after_rollback", "A")
    same_ledger(latest)
    after_event_hash = digest((PROJECT / EVENTS).read_bytes())
    save(OUT / "RESULT.json", {
        "passed": True, "isolated": True, "owned_hook_registrations": 5,
        "forward_changes": forward.get("changes"), "reverse_changes": backward.get("changes"),
        "stale_reverse_refused": True, "latest_state_retained": True,
        "desktop_state_sessions": len(initial.get("runtime", {}).get("sessions", {})),
        "desktop_goal_segments": len(initial.get("goal_segments", {}).get("records", {})),
        "initial_audit_sha256": event_hash, "final_audit_sha256": after_event_hash,
        "audit_preserved_by_admin": True, "MCP_request_traces_appended": 6,
        "MCP_audit_retention_replayed": True, "MCP_endpoints": 3,
    })


if __name__ == "__main__":
    main()
