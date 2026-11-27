"""Check final project commands and 042 preflight evidence without launching a host."""

import base64
import hashlib
import json
import math
import subprocess
import tomllib
from pathlib import Path


AUTHOR = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe")
ROOT = Path("D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001")
REG = ROOT / "registration"
CONFIG = ROOT / "direct/CONFIG.json"
COMMIT = "462318268437a33587ce620630d066e721764d5f"
PARENT = "74a8e9f7a1194e82afed4fb5bfd92557315acf01"
INDEX_SHA = "72dd9a05920f8a0d8cd72c452d687938f43a78929cd82140a1ae4632a40d0ab4"
PROTOCOL_SHA = "087e0306fb2fe97e226249dddb45c895a24e58ef23909da0156ea3d10a1d6fe6"
SOURCE_SHA = "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e"
PREVIOUS = Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK")
TOOL = "human_eye_connection_status"
MATCHER = "^mcp__human_eye_live__human_eye_connection_status$"
EVENTS = ("UserPromptSubmit", "PostToolUse")


def check(condition, description):
    if not condition:
        raise ValueError(description)


def read(path):
    return json.loads(path.read_bytes())


def messages(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def digest(body):
    return hashlib.sha256(body).hexdigest()


def verify_archive():
    def git(*args):
        return subprocess.check_output(["git", "-C", str(AUTHOR), *args])

    check(git("rev-parse", COMMIT + "^").decode().strip() == PARENT, "implementation parent")
    delta = git("diff", "--name-status", PARENT, COMMIT).decode().splitlines()
    for row in delta:
        kind, path = row.split("\t")
        check(kind == "A" and path.startswith("verification/m6_entry_warm_region_042/entry_final/"), path)
        check((AUTHOR / path).read_bytes() == git("cat-file", "blob", COMMIT + ":" + path), path)
    manifest_file = ROOT / "RAW_FINAL_INDEX.json"
    check(digest(manifest_file.read_bytes()) == INDEX_SHA, "manifest pin")
    manifest = read(manifest_file)
    check(Path(manifest["root"]) == ROOT, "manifest root")
    files = manifest["files"]
    check(len({f["path"] for f in files}) == len(files) == manifest["count"], "unique members")
    for row in files:
        path = (ROOT / row["path"]).resolve()
        check(path.is_relative_to(ROOT), row["path"])
        body = path.read_bytes()
        check(len(body) == row["bytes"] and digest(body) == row["sha256"], row["path"])
    total = sum(f["bytes"] for f in files)
    check(total == manifest["bytes"], "byte denominator")
    return {"commit": COMMIT, "added_git_files": len(delta), "raw_files": len(files),
            "raw_bytes": total, "raw_index_sha256": INDEX_SHA}


def verify_registration(protocol):
    bindings = read(PREVIOUS / "delivery/install/PINS.json")["arms"]["r3"]
    for pin in (bindings["launcher"], bindings["binding"]):
        check(digest(Path(pin["path"]).read_bytes()) == pin["sha256"], "041 runtime binding")
    check(bindings["identity"]["source_sha256"] == SOURCE_SHA, "041 R3 source")
    expected_tail = ["-I", "-B", bindings["launcher"]["path"]]
    cfg = read(CONFIG)
    check(digest(CONFIG.read_bytes()) == "1a416026a191a6b6f535fcd25c1acf55a2168cf8ca72aba98a7c7947f512ea2e",
          "connector pin")
    check((cfg["blender"]["host"], cfg["blender"]["port"]) == ("127.0.0.1", 48142)
          and cfg["expected_identity"]["source_sha256"] == SOURCE_SHA, "finite endpoint")
    check(digest((REG / "REGISTRATION.json").read_bytes()) ==
          "cf09e6c3b00874fe4282d280de1b8e7f6c0380b67ea4e165768d87e8c6f2ae9c", "registration pin")
    commands = {}
    configs = set()
    definitions = {}
    for arm in ("H0", "H1", "OFF"):
        settings = REG / "workspaces" / arm / ".codex"
        body = (settings / "config.toml").read_bytes()
        configs.add(digest(body))
        settings_toml = tomllib.loads(body.decode())
        check(set(settings_toml) == {"mcp_servers"} and
              set(settings_toml["mcp_servers"]) == {"human_eye_live"}, "single project MCP")
        server = settings_toml["mcp_servers"]["human_eye_live"]
        check(server["enabled"] and server["enabled_tools"] == [TOOL] and
              server["command"] == bindings["dependency_python"] and
              server["args"] == expected_tail + ["serve", "--config", str(CONFIG)], "status-only project MCP")
        hooks = read(settings / "hooks.json")["hooks"]
        check(set(hooks) == (set() if arm == "OFF" else set(EVENTS)), "exact event inventory")
        for event, groups in hooks.items():
            check(len(groups) == 1 and len(groups[0]["hooks"]) == 1, "single handler")
            group = groups[0]
            check(group.get("matcher") == (MATCHER if event == "PostToolUse" else None), "event scope")
            handler = group["hooks"][0]
            check(set(handler) == {"command", "type", "timeout"} and
                  handler["type"] == "command" and handler["timeout"] == 30, "handler options")
            argv = [bindings["dependency_python"], *expected_tail, "hook", "--agent", "codex",
                    "--event", event, "--config", str(CONFIG)]
            command = handler["command"]
            if arm == "H0":
                prefix = r"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -NonInteractive -EncodedCommand "
                check(command.startswith(prefix), "PowerShell executable and options")
                script = base64.b64decode(command[len(prefix):], validate=True).decode("utf-16-le")
                check(script == "& " + " ".join("'" + a + "'" for a in argv) + "; exit $LASTEXITCODE",
                      "decoded H0 argv")
            else:
                check(command == subprocess.list2cmdline(argv), "direct H1 argv")
            commands[arm, event] = command
        definitions[arm] = list(hooks)
    check(len(configs) == 1 and protocol["mcp"]["regex"] == MATCHER, "identical project MCP configurations")
    metadata = []
    for folder in sorted(REG.glob("metadata_*")):
        arm = folder.name.split("_")[-1]
        project = folder.name.startswith("metadata_project_")
        tx = messages(folder / "TX.bin")
        check([t["method"] for t in tx] ==
              ["initialize", "initialized", "hooks/list", "config/read", "mcpServerStatus/list"], "discovery only")
        rx = messages(folder / "RX.bin")
        replies = {row["id"]: row["result"] for row in rx if "id" in row}
        check(not replies[4]["data"], "no active test MCP in this metadata probe")
        inventory = replies[2]["data"]
        check(len(inventory) == 1, "one workspace in inventory")
        discovered = inventory[0]["hooks"]
        if project:
            workspace = REG / "workspaces" / arm
            check(Path(inventory[0]["cwd"]) == workspace and not discovered, "pending project trust")
            check(any(row.get("method") == "configWarning" and str(workspace) in row["params"]["summary"]
                      and "until the project is trusted" in row["params"]["summary"] for row in rx),
                  "workspace-specific host warning")
        else:
            check(len(discovered) == 2, "two mirror handlers")
            for event in EVENTS:
                h, = [h for h in discovered if h["eventName"].casefold() == event.casefold()]
                check(h["enabled"] and h["source"] == "user" and h["trustStatus"] == "untrusted"
                      and Path(h["sourcePath"]) == folder / "isolated_home/hooks.json"
                      and h["command"] == commands[arm, event]
                      and h["matcher"] == (MATCHER if event == "PostToolUse" else None), "mirror definition")
        closed = read(folder / "RESULT.json")["cleanup"]
        check(closed["accounting"]["active_processes"] == 0 and closed["readers_joined"], "metadata process exit")
        metadata.append({"scope": "project" if project else "user_mirror", "arm": arm,
                         "effective_hook_count": len(discovered)})
    check(len(metadata) == 5, "metadata denominator")
    return {"project_definitions_on_disk": definitions, "metadata": metadata,
            "mcp_config_sha256": configs.pop(), "visible_project_handlers_at_probe": 0}


def verify_preflight(protocol):
    root = ROOT / "direct/preflight_02"
    scenes, pids = [], []
    for name in ("session_1", "session_2"):
        slot = root / name
        host = read(slot / "native/READY.json")
        check(not host["background"] and host["port"] == 48142 and host["host"] == "127.0.0.1",
              "ordinary Blender with the fixed endpoint")
        check(digest(Path(host["asset_copy"]).read_bytes()) == protocol["endpoint"]["native_blend_sha256"],
              "G60 source")
        check(read(slot / "native/qa_wire/001.TX.bin") == {"type": "ping"}
              and read(slot / "native/qa_wire/001.RX.bin")["result"] == {"pong": True}, "native ping")
        identity = read(slot / "stdio/001.RX.bin")["result"]["_meta"]["human_eye"]
        check(identity["production_mode"] and identity["source_sha256"] == SOURCE_SHA and
              identity["source_file_count"] == 143, "production stdio identity")
        check(read(slot / "stdio/004.TX.bin")["params"] == {"name": TOOL, "arguments": {}}, "actual status call")
        status = read(slot / "stdio/004.RX.bin")["result"]
        check(not status["isError"] and json.loads(status["content"][0]["text"])["host_connectivity_checked"] is False,
              "typed status, native ping measured separately")
        before, after = (read(slot / filename) for filename in ("BEFORE.json", "AFTER.json"))
        check(before["pid"] == after["pid"] == host["pid"] and before["geometry"] == after["geometry"], "source state")
        scenes.append(before["geometry"])
        pids.append(host["pid"])
        terminal = read(slot / "native/TERMINAL_OWNERSHIP.json")
        check(terminal["pid"] == host["pid"] and terminal["process_reaped"] and terminal["exit_code"] == 0
              and not terminal["released_port"]["any_listener"] and terminal["source_unchanged"], "owned GUI cleanup")
        closed = read(slot / "stdio/CLOSE.json")
        check(closed["exit_code"] == 0 and closed["method"] == "eof", "stdio close")
    check(len(set(pids)) == 2 and scenes[0] == scenes[1], "independent host reopen")
    first = root / "session_1"
    request = read(first / "stdio/005.TX.bin")["params"]
    oracle = protocol["short_direct_oracle"]
    check(request == {"name": oracle["tool"], "arguments": oracle["args"]}, "frozen geometry request")
    result = json.loads(read(first / "stdio/005.RX.bin")["result"]["content"][0]["text"])
    archived = read(PREVIOUS / "s1/warm_diagnostic/cells/G60_1_r3/first_nearest.json")["value"]
    for field in set(result) | set(archived):
        if field not in {"binding", "trace_id", "request_trace", "correlation"}:
            check(result[field] == archived[field], "041 public geometry: " + field)
    witness, = result["best_known_evidence"]
    check(result["nearest_objects"] == [witness["candidate"]] and witness["candidate"]["name"] == "Peer_000"
          and result["coverage"]["distance_valid"] == 11 and not result["unresolved"], "nearest and coverage")
    check(math.isclose(math.dist(witness["point_a_world"], witness["point_b_world"]), result["distance_m"],
                       rel_tol=1e-12), "distance from public points")
    positive = first / "manual_positive"
    check(read(positive / "INPUT.json")["prompt"] == protocol["related_prompt"], "final related prompt")
    context = json.loads(read(positive / "STDOUT.bin")["hookSpecificOutput"]["additionalContext"])
    request_id = context["correlation"]["request_id"]
    events = messages(positive / "AUDIT_APPEND.jsonl")
    check(request_id and request_id not in protocol["related_prompt"] and
          [e["event"] for e in events] == ["observe", "host_hook", "request_trace"] and
          all(e["request_id"] == request_id for e in events), "manual observation link")
    check({o["name"] for o in context["observation"]["objects"]} == set(scenes[0]) and len(scenes[0]) == 12,
          "returned names match actual native snapshot")
    check(read(positive / "RESULT.json")["command"][-1] == "--probe", "manual positive scope")
    for arm in ("H0", "H1"):
        slot = ROOT / "manual_post_01" / arm
        tool_event = read(slot / "INPUT.json")
        check(tool_event["tool_response"] == read(first / "stdio/004.RX.bin")["result"]
              and tool_event["tool_name"] == protocol["mcp"]["canonical"] and tool_event["tool_input"] == {},
              "actual status reply supplied as manual event")
        check(read(slot / "STDOUT.bin") == {}, "no duplicate content")
        skipped, trace = messages(slot / "AUDIT_APPEND.jsonl")
        check(skipped["event"] == "host_hook_skip" and skipped["status"] == "tool_result_delivery_retained"
              and not skipped["scene_read"] and trace["trace"]["outcome"] == "duplicate_delivery_omitted"
              and skipped["tool_use_id"] == trace["tool_use_id"] == tool_event["tool_use_id"], "deduplication event")
        proc = read(slot / "PROCESS.json")
        check(proc["returncode"] == 0 and proc["job_accounting"]["active_processes"] == 0, "manual command exit")
    rejected = read(ROOT / "direct/preflight_01/session_1/stdio/005.RX.bin")["result"]
    check(rejected["isError"] and "requires session_id" in rejected["content"][0]["text"], "first rejected request")
    return {"successful_gui_pids": pids, "nearest": witness["candidate"]["name"], "distance_m": result["distance_m"],
            "valid_candidates": 11, "manual_prompt_observations": 1, "mesh_names": len(scenes[0]),
            "manual_post_checks": 2, "additional_scene_reads_in_manual_posts": 0}


if __name__ == "__main__":
    archived = verify_archive()
    protocol_file = ROOT / "FORMAL_PROTOCOL_03.json"
    check(digest(protocol_file.read_bytes()) == PROTOCOL_SHA, "final protocol pin")
    protocol = read(protocol_file)
    print(json.dumps({"archive": archived, "registration": verify_registration(protocol),
                      "direct_preflight": verify_preflight(protocol),
                      "decision": "prepared_for_native_user_review",
                      "formal_host_turns": 0, "formal_inflight_cancels": 0}, indent=2))
