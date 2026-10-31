"""Read-only agent registration/evidence audit and an offline routing corpus.

No configured command, hook, model request, or Blender operation is executed.
Only the explicitly selected report path is written, using exclusive creation.
Protocol payload preparation and actual host activation remain separate axes.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = "mcp__human_eye_live__human_eye_transform"
_MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_MAX_LOG_BYTES = 64 * 1024 * 1024
_EXAMPLE_TOOLS = [TRANSFORM, "mcp__human_eye_live__human_eye_scene_observe",
    "mcp__human_eye_live__human_eye_connection_status", "mcp__blender__execute_blender_code",
    "mcp__blender__get_scene_info", "exec_command", "unclassified_future_geometry_tool"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_document(path):
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError("Document exceeds audit limit")
    value = tomllib.loads(raw.decode("utf-8-sig")) if path.suffix == ".toml" else json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected a document object")
    return value, digest(raw)


def registration(project, agent):
    """Inspect project files only; presence never means host loaded or trusted."""
    from human_eye_plugin.agent_setup import _command_argv
    project = Path(project).resolve()
    server_path = project / (".codex/config.toml" if agent == "codex" else ".mcp.json")
    hooks_path = project / (".codex/hooks.json" if agent == "codex" else ".claude/settings.json")
    result = {"agent": agent, "scope": "project_configuration_only",
        "server_registration": "not_registered", "hook_registration": "not_registered",
        "host_loaded": "unknown", "host_trust": "unknown", "files": {}, "hook_groups": []}
    if server_path.is_file():
        try:
            document, sha = read_document(server_path)
            result["files"][server_path.relative_to(project).as_posix()] = sha
            servers = document.get("mcp_servers" if agent == "codex" else "mcpServers", {})
            server = servers.get("human_eye_live") if isinstance(servers, dict) else None
            if isinstance(server, dict):
                command, arguments = server.get("command"), server.get("args", [])
                recognized = (isinstance(arguments, list) and all(isinstance(v, str) for v in arguments)
                    and (any(v.endswith("live_entry.py") for v in arguments) and "serve" in arguments
                         or any(v in {"human_eye_plugin.production_server", "human_eye_plugin.live_spatial_mcp"}
                                for v in arguments)))
                executable = Path(command).is_file() or shutil.which(command) is not None if isinstance(command, str) else False
                result.update(server_registration="registered_in_project_config",
                    configured_enabled=server.get("enabled", True), recognized_live_launcher=bool(recognized),
                    executable_found=executable, config_argument_present="--config" in arguments,
                    command_execution="not_performed")
        except (OSError, ValueError, TypeError) as exc:
            result.update(server_registration="invalid_configuration", error_type=type(exc).__name__)
    if hooks_path.is_file():
        try:
            document, sha = read_document(hooks_path)
            result["files"][hooks_path.relative_to(project).as_posix()] = sha
            hooks = document.get("hooks", {})
            groups = []
            for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
                for group in hooks.get(event, []):
                    for hook in group.get("hooks", []):
                        argv = _command_argv(hook, "windows" if os.name == "nt" else "posix")
                        if argv and any(v.endswith("live_entry.py") for v in argv) and "hook" in argv:
                            groups.append({"event": event, "matcher": group.get("matcher"),
                                "argv_recognized": True, "command_executed": False})
            result["hook_groups"] = groups
            result["hook_registration"] = "registered_in_project_config" if groups else "not_registered"
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result.update(hook_registration="invalid_configuration", hook_error_type=type(exc).__name__)
    return result


def tool_coverage(registration_result, names, *, inventory_source):
    groups = [group for group in registration_result["hook_groups"] if group["event"] == "PreToolUse"]
    rows = []
    for name in names:
        matched, errors = False, []
        for group in groups:
            try:
                matched |= group["matcher"] is None or re.search(group["matcher"], name) is not None
            except (re.error, TypeError):
                errors.append("invalid_hook_matcher")
        rows.append({"tool": name, "pre_hook_match": bool(matched),
            "inner_gate": "declared_in_human_eye_transform" if name == TRANSFORM else "unverified_or_bypass",
            "mutation_capability": "known_geometry_mutator" if name in {TRANSFORM,
                "mcp__blender__execute_blender_code", "exec_command"} else "requires_host_classification",
            "policy": "guarded_entry" if name == TRANSFORM else "coverage_unknown_do_not_claim_interception",
            "errors": errors})
    return {"inventory_source": inventory_source, "inventory_is_complete": False,
            "rows": rows, "unknown_tools_policy": "unclassified_not_implicitly_safe_or_globally_denied"}


def read_jsonl(path):
    """Snapshot selected logs; retain record hashes, never copy prompt bodies."""
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) > _MAX_LOG_BYTES:
        raise ValueError("Selected log exceeds audit limit")
    rows, invalid = [], 0
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("not an object")
            rows.append((line_number, digest(line + b"\n"), value))
        except (ValueError, UnicodeError):
            invalid += 1
    return rows, {"path": str(path.resolve()), "snapshot_sha256": digest(raw),
        "size_bytes": len(raw), "invalid_records": invalid,
        "scope": "read_snapshot_not_future_append_integrity"}


def codex_host_records(path):
    rows, source = read_jsonl(path)
    deliveries, tool_results = [], []
    for line, sha, record in rows:
        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("internal_chat_message_metadata_passthrough", {})
        # User/assistant messages containing copied hook JSON are not host events.
        kinds = metadata.get("content_item_kinds", []) if isinstance(metadata, dict) else []
        content = payload.get("content", [])
        if (record.get("type") == "response_item" and payload.get("role") == "developer"
                and isinstance(metadata, dict) and isinstance(kinds, list) and isinstance(content, list)
                and "hooks.additional_context" in kinds):
            for part in content:
                if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                    continue
                try:
                    value = json.loads(part["text"])
                    observation = value.get("observation", {})
                    if isinstance(observation, str):
                        observation = json.loads(observation)
                    if value.get("human_eye_live") is None or not isinstance(observation, dict):
                        continue
                except (ValueError, TypeError, AttributeError):
                    continue
                deliveries.append({"line": line, "record_sha256": sha,
                    "turn_id": metadata.get("turn_id"), "session_id": value.get("session_id"),
                    "scene_revision": observation.get("scene_revision"),
                    "status": value["human_eye_live"], "delivery": value.get("delivery"),
                    "implementation_revision": value.get("implementation_revision"),
                    "source": "actual_host_developer_hook_context"})
        item = payload.get("item", {})
        if (record.get("type") == "event_msg" and payload.get("type") == "item_completed"
                and isinstance(item, dict) and item.get("type") == "McpToolCall"
                and item.get("server") == "human_eye_live"):
            tool_results.append({"line": line, "record_sha256": sha, "tool": item.get("tool"),
                "tool_use_id": item.get("id"), "status": item.get("status"),
                "scope": "host_tool_completion_record_not_independent_geometry_readback"})
    return {"source": source, "hook_deliveries": deliveries, "tool_completion_records": tool_results}


def hook_evidence(audit_path, host_records=None):
    result = {"current_revision_activation": "unknown", "manual_probes_excluded": 0,
        "uncorrelated_hook_candidates": 0, "correlated_prompt_events": [],
        "duplicate_audit_candidates": 0,
        "pre_action_hook": "unknown", "post_action_hook": "unknown",
        "inner_execution_gate": "not_run_in_current_host",
        "independent_readback": "not_run_in_current_host"}
    if not Path(audit_path).is_file():
        return {**result, "audit_status": "not_available"}
    rows, source = read_jsonl(audit_path)
    result.update(audit_status="read", source=source)
    seen_host_events = set()
    for line, sha, item in rows:
        if item.get("event") != "host_hook":
            continue
        if item.get("invocation_source") != "hook_command":
            result["manual_probes_excluded"] += 1
            continue
        matches = []
        if item.get("hook_event") == "UserPromptSubmit" and item.get("turn_id"):
            matches = [event for event in (host_records or {}).get("hook_deliveries", [])
                if event.get("turn_id") == item["turn_id"]
                and event.get("session_id") == item.get("session_id")
                and event.get("scene_revision") and event["scene_revision"] == item.get("scene_revision")]
        if matches:
            key = (matches[0]["line"], matches[0]["record_sha256"])
            if key in seen_host_events:
                result["duplicate_audit_candidates"] += 1
                continue
            seen_host_events.add(key)
            result["correlated_prompt_events"].append({"audit_line": line, "audit_record_sha256": sha,
                "host_line": matches[0]["line"], "host_record_sha256": matches[0]["record_sha256"],
                "turn_id": item["turn_id"], "scope": "historical_or_unknown_revision_actual_host_trigger",
                "delivery": matches[0]["delivery"]})
        else:
            result["uncorrelated_hook_candidates"] += 1
    # Correlation cannot upgrade an event lacking implementation identity to the
    # newly loaded revision, or prove that a model consumed any native image.
    result["prompt_activation"] = "historical_host_correlated" if result["correlated_prompt_events"] else "unknown"
    return result


def native_payload_check():
    from PIL import Image
    from human_eye_plugin.agent_adapters import SUPPORTED_FORMATS, build_agent_observation
    buffer = io.BytesIO()
    Image.new("RGB", (7, 5), (23, 61, 129)).save(buffer, format="PNG")
    raw = buffer.getvalue()
    route = {"schema_version": "1.0", "route": "engine", "context_text": "offline byte-identity fixture",
             "reason_codes": [], "image": {"type": "image", "mimeType": "image/png",
             "data": base64.b64encode(raw).decode("ascii")}}
    rows = []
    for format in SUPPORTED_FORMATS:
        prepared = build_agent_observation(route, format=format)
        image = prepared["content"][1]
        if format == "openai_responses":
            encoded = image["image_url"].split(",", 1)[1]
        elif format == "openai_chat":
            encoded = image["image_url"]["url"].split(",", 1)[1]
        elif format == "anthropic":
            encoded = image["source"]["data"]
        elif format == "gemini":
            encoded = image["inline_data"]["data"]
        else:
            encoded = image["data"]
        decoded = base64.b64decode(encoded, validate=True)
        degraded = build_agent_observation(route, format=format, supports_images=False)
        rows.append({"format": format, "decoded_sha256": digest(decoded),
            "same_bytes": decoded == raw, "native_block_prepared": prepared["delivery"]["image_delivered"],
            "text_degradation_explicit": degraded["delivery"]["degraded_to_text"],
            "remote_send": "not_performed", "model_consumed_image": "unknown"})
    return {"scope": "offline_adapter_payload_only", "fixture_sha256": digest(raw), "rows": rows}


def fixture_scene():
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D
    signs = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])
    faces = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
        [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]])
    def box(oid, center, size, focal):
        return MeshEntity3D(oid, "#" + oid, oid, signs * np.array(size)/2 + center, faces, None,
            (90, 140, 210), focal, local_axes=np.eye(3), pivot_world=np.array(center)).to_dict()
    return {"revision": "offline-agent-routing-v1", "source": "offline_fixture",
            "unit": "m", "coordinate_frame": "world",
            "meshes": [box("base", [0,0,.1], [1,1,.2], False),
                       box("part", [0,0,.35], [.2,.3,.1], True)]}


def route_corpus(path):
    from human_eye_plugin.auto_router import HumanEyeAutoRouter
    corpus, sha = read_document(path)
    rows = corpus.get("rows", [])
    if len(rows) != 100 or len({row["id"] for row in rows}) != 100:
        raise ValueError("Preregistered corpus requires 100 distinct rows")
    scene, results, cohorts = fixture_scene(), [], {}
    for row in rows:
        event = {"event": "before_model", "session_id": "route-corpus:" + row["id"],
                 "task_instruction": row["instruction"], "include_image": False,
                 "focal_id": "part", "reference_id": "base"}
        if row["host_task_kind"] is not None:
            event["task_kind"] = row["host_task_kind"]
        if row["provide_scene"]:
            event["scene"] = scene
        result = HumanEyeAutoRouter(quad_size=64).handle_event(event)
        passed = result["route"] in row["expected_routes"]
        value = {"id": row["id"], "task_class": row["task_class"], "cohort": row["cohort"],
                 "expected_routes": row["expected_routes"], "actual_route": result["route"],
                 "reason_codes": result["reason_codes"], "business_expectation_met": passed,
                 "host_signal": {"task_kind": row["host_task_kind"], "scene_provided": row["provide_scene"]}}
        results.append(value)
        cohort = cohorts.setdefault(row["cohort"], {"count": 0, "matched": 0, "actual_routes": Counter()})
        cohort["count"] += 1
        cohort["matched"] += int(passed)
        cohort["actual_routes"][result["route"]] += 1
    return {"corpus_id": corpus["corpus_id"], "corpus_sha256": sha,
        "scope": "offline_router_business_expectations_not_model_or_actual_hook_test",
        "total": len(results), "matched": sum(row["business_expectation_met"] for row in results),
        "cohorts": cohorts, "rows": results,
        "all_required_expectations_met": all(row["business_expectation_met"] for row in results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--corpus", type=Path, default=ROOT / "verification/fixtures/agent_routes_v1.json")
    parser.add_argument("--codex-rollout", type=Path, help="Explicit actual host JSONL; no session directory scan")
    parser.add_argument("--tool-inventory", type=Path, help="JSON with names:list[str], source:str; report is incomplete by default")
    parser.add_argument("--report", type=Path, help="New evidence JSON; existing file is never overwritten")
    args = parser.parse_args(argv)
    # Run as a module or from the source workspace. No dynamic host command loads.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity()
    identity["source_file_count"] = len(identity.pop("source_files"))
    registrations = {agent: registration(args.project, agent) for agent in ("codex", "claude")}
    names, inventory_source = _EXAMPLE_TOOLS, "reference_names_not_observed_complete_host_inventory"
    if args.tool_inventory:
        supplied, _ = read_document(args.tool_inventory)
        if not isinstance(supplied.get("names"), list) or any(not isinstance(v, str) for v in supplied["names"]):
            raise ValueError("Tool inventory requires a string list")
        names, inventory_source = supplied["names"], str(supplied.get("source", "caller_supplied_unverified_inventory"))
    host = codex_host_records(args.codex_rollout) if args.codex_rollout else None
    report = {"schema_version": "1.0", "kind": "T05_readonly_preparation", "date_local": "2026-10-23",
        "runtime_identity": identity, "registrations": registrations,
        "tool_coverage": {agent: tool_coverage(value, names, inventory_source=inventory_source)
                          for agent, value in registrations.items()},
        "native_payload": native_payload_check(), "routing_corpus": route_corpus(args.corpus),
        "codex_hook_evidence": hook_evidence(Path(args.project) / ".human-eye/live-events.jsonl", host),
        "claude_actual_host": {"activation": "not_run", "native_payload": "offline_anthropic_adapter_only",
                               "execution_gate": "not_run", "independent_readback": "not_run"},
        "python_host": {"registration": "not_applicable_requires_caller_integration",
                        "payload": "offline_five_format_check_only", "model_call": "not_performed",
                        "execution_gate": "not_run_in_actual_host", "independent_readback": "not_run"},
        "runtime_probe": {"blender_connection": "not_probed", "registered_mcp_process_revision": "not_queried",
                          "current_revision_live_acceptance": "not_run"},
        "safety": {"configured_commands_executed": False, "hooks_invoked": False,
                   "provider_requests_sent": False, "runtime_config_or_state_modified": False,
                   "blender_scene_modified": False, "manual_hook_simulation_counted_as_actual": False},
        "limits": ["项目配置存在不等于宿主已加载、授权或实际执行。",
                   "新进程本地身份不能证明当前已注册MCP常驻进程使用相同版本。",
                   "图片同字节仅证明适配载荷，不能证明宿主发送或模型消费。",
                   "历史hook匹配不能升级为新版live执行验收；pre/post与独立回读仍须单独采集。"]}
    report["acceptance_status"] = ("offline_routing_failed_live_pending"
        if not report["routing_corpus"]["all_required_expectations_met"] else "offline_checks_passed_live_pending")
    report["evidence_collection_succeeded"] = True
    report["T05_completion_status"] = "incomplete"
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as output:
            output.write(text)
        print(json.dumps({"report": str(args.report.resolve()), "rows": report["routing_corpus"]["total"],
            "business_expectations_met": report["routing_corpus"]["matched"],
            "acceptance_status": report["acceptance_status"],
            "read_only_runtime": True}, ensure_ascii=False))
    else:
        print(text, end="")
    # Successful evidence collection does not turn unmet routing goals into a pass.
    return 0 if report["routing_corpus"]["all_required_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
