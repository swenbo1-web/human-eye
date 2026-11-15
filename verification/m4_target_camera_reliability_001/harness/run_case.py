"""Root-invoked owned Blender session through the installed public target entry."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import Budget, save
from extract_saved import extract


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load(path):
    return json.loads(Path(path).read_bytes())


def rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()] if Path(path).exists() else []


def request(target):
    return {"jsonrpc": "2.0", "id": "target_observation", "method": "tools/call",
            "params": {"name": "human_eye_scene_observe", "arguments": {
                "session_id": "m4-target-camera-reliability-001", "include_image": True,
                "response_detail": "full",
                "query": {"mode": "active_observation", "objects": [{"name": target}]}}}}


def request_sequence(target):
    return [request(target), {"jsonrpc": "2.0", "id": "after_active_ping", "method": "ping"},
            {"jsonrpc": "2.0", "id": "source_readback", "method": "tools/call",
             "params": {"name": "human_eye_scene_observe", "arguments": {
                 "session_id": "m4-target-camera-reliability-001", "include_image": False,
                 "query": {"mode": "task", "objects": [{"name": target}], "requested_facts": ["aabb"]}}}},
            {"jsonrpc": "2.0", "id": "after_readback_ping", "method": "ping"}]


def numeric_unknown(response, value):
    return (response.get("result", {}).get("isError") is True
            and value.get("status") == "unknown"
            and value.get("reason") == "active_observation_target_camera_numeric_insufficient"
            and value.get("observation_status") == "numeric_insufficient"
            and value.get("observation_mode") == "active_observation")


def producer_frames(value, output):
    frames = value.get("frames", [])
    if not isinstance(frames, list):
        raise ValueError("producer_frames_list_required")
    receipts = []
    for frame in frames:
        npz = Path(frame["arrays_path"]).resolve()
        png = Path(frame["image_path"]).resolve()
        if not npz.is_relative_to(output) or not png.is_relative_to(output):
            raise ValueError("producer_frame_paths_outside_owned_slot")
        if digest(npz) != frame["arrays_sha256"] or digest(png) != frame["image_sha256"]:
            raise ValueError("producer_frame_original_hash_mismatch")
        receipts.append({"view_name": frame["view_name"], "frame_identity": frame["frame_identity"],
                         "arrays_path": str(npz), "producer_arrays_sha256": frame["arrays_sha256"],
                         "image_path": str(png), "producer_image_sha256": frame["image_sha256"],
                         "host_binding_sha256": frame["host_binding_sha256"],
                         "source_revision": frame["source_revision"],
                         "source": "same first public full result; no extra observation or raster",
                         "pose": "not projected in public frames; bind same actual capture camera_plan separately"})
    return receipts


def verify_install(binding):
    root = Path(binding["install_root"])
    for row in binding["source_manifest"]:
        if digest(root / row["path"]) != row["sha256"]:
            raise ValueError("frozen_installed_product_source_changed")
    identity = {key: binding[key] for key in ("base_version", "implementation_revision")}
    identity["files"] = binding["source_manifest"]
    actual = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    if actual != binding["source_sha256"]:
        raise ValueError("installed_manifest_identity_changed")


def run(*, binding_path, asset, output, ledger, phase, label, variant, requests=None):
    output = Path(output).resolve()
    if not output.is_relative_to(Path("D:/he_m4_camera_001").resolve()):
        raise ValueError("owned_case_output_outside_batch")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    binding = load(binding_path)
    verify_install(binding)
    if digest(asset["asset"]) != asset["asset_sha256"]:
        raise ValueError("owned_asset_changed_before_start")
    input_plan = load(HERE.parent / "fixtures/INPUT_PLAN.json")
    legacy_config = input_plan["public_deadlines"]["source"]
    if digest(legacy_config["path"]) != legacy_config["sha256"]:
        raise ValueError("frozen_public_timeout_source_changed")
    public = input_plan["public_deadlines"]
    budget = Budget(ledger)
    claim = budget.reserve("Blender_start", label, phase)
    helper = module("_target_owned_native", HERE / "reused/owned_native.py")
    transport = module("_target_stdio", HERE / "reused/stdio_checks.py")
    process_proof = module("_target_process_proof", HERE / "reused/process_proof.py")
    native = client = None
    runtime_handle = None
    initialized_identity = None
    result = {"schema": "m4-target-camera-owned-case-v1", "label": label, "phase": phase, "variant": variant,
              "started_ns": started, "original_lifecycle_deadline_ns": deadline,
              "source_sha256": binding["source_sha256"], "binding_file": str(Path(binding_path).resolve()),
              "binding_sha256": digest(binding_path), "asset": asset,
              "start_budget_claim": claim, "requests": [], "errors": [], "passed": False,
              "model_calls": 0, "public_request_budget_s": public["request_budget_s"],
              "blender_timeout_s": public["blender_timeout_s"], "new_raster_limit_per_request": 6}
    try:
        native = helper.NativeSession.start(blender="D:/Tools/blender5.2/blender.exe", asset=asset["asset"],
            workspace=output / "native", deadline_ns=deadline, condition="P",
            expected_asset_sha256=asset["asset_sha256"], max_calls=128)
        config = {"schema_version": "1.0", "enabled": True, "observe_on_prompt": False,
                  "project_root": binding["install_root"], "state_file": str(output / "state.json"),
                  "audit_file": str(output / "audit.jsonl"),
                  "expected_identity": {"source_sha256": binding["source_sha256"]},
                  "request_budget_s": public["request_budget_s"],
                  "blender": {"host": native.host, "port": native.port, "timeout_s": public["blender_timeout_s"]}}
        save(output / "CONFIG.json", config)
        command = [binding.get("dependency_python", sys.executable), "-I", "-B", "-X", "utf8",
                   str(HERE / "mcp_entry.py"), "--binding", str(Path(binding_path).resolve()),
                   "--config", str(output / "CONFIG.json"), "--ledger", str(Path(ledger).resolve()),
                   "--evidence", str(output / "io_audit"), "--phase", phase]
        client = transport.StdioClient(command, output, output / "stdio", deadline)
        initialized = client.call({"jsonrpc": "2.0", "id": "initialize", "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "m4-target-engineering", "version": "001"}}})
        save(output / "INITIALIZE.json", initialized)
        initialized_identity = initialized["result"]["_meta"]["human_eye"]
        if (initialized_identity["source_sha256"] != binding["source_sha256"]
                or initialized_identity["source_kind"] != "installed_distribution"):
            raise ValueError("actual_public_runtime_identity_changed")
        client.call({"jsonrpc": "2.0", "method": "notifications/initialized"})
        save(output / "TOOLS.json", client.call({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"}))
        if client.call({"jsonrpc": "2.0", "id": "ping", "method": "ping"}).get("result") != {}:
            raise ValueError("public_startup_ping_failed")
        if rows(output / "native/WORKER_EVENTS.jsonl"):
            raise ValueError("metadata_unexpectedly_warmed_geometry")
        runtime = load(output / "io_audit/RUNTIME.json")
        if (runtime.get("pid") != client.process.pid
                or runtime.get("entry_sha256") != digest(HERE / "mcp_entry.py")
                or runtime.get("binding_sha256") != digest(binding_path)
                or runtime.get("source_sha256") != binding["source_sha256"]):
            raise ValueError("controlled_MCP_entry_identity_mismatch")
        proof, runtime_handle = process_proof._windows_runtime_proof(client.process, runtime["pid"], deadline)
        proof.update(before_stdin=False, scope="after metadata, before geometry; metadata made zero host RPCs")
        save(output / "RUNTIME_PROOF.json", proof)
        if proof.get("confirmed") is not True:
            raise ValueError("MCP_runtime_process_not_proved")
        result["setup_closed_ns"] = time.perf_counter_ns()
        fixed_requests = request_sequence(asset["target"]) if requests is None else requests
        for index, message in enumerate(fixed_requests, 1):
            save(output / f"REQUEST_{index:02}.json", message)
            began = time.perf_counter_ns()
            response = client.call(message)
            completed = time.perf_counter_ns()
            save(output / f"RESPONSE_{index:02}.json", response)
            common = {"index": index, "id": message.get("id"),
                      "client_call_started_ns": began, "client_call_completed_ns": completed,
                      "client_outer_including_recording_ns": completed - began,
                      "response_json_sha256": digest(output / f"RESPONSE_{index:02}.json"),
                      "raw_RX_bytes": client.records[-1].get("RX_bytes")}
            if message.get("method") == "ping":
                result["requests"].append(dict(common, result_kind="ping", ping_success=response.get("result") == {}))
                if response.get("result") != {}:
                    result["errors"].append({"stage": "post_main_ping", "request_id": message["id"],
                                              "message": "expected successful ping after main/readback"})
                continue
            content = response.get("result", {}).get("content", [])
            texts = [json.loads(block["text"]) for block in content if block.get("type") == "text"]
            if len(texts) != 1:
                raise ValueError("public_text_result_count")
            save(output / f"PUBLIC_{index:02}.json", texts[0])
            value = texts[0]
            if message.get("id") == "target_observation":
                typed_unknown = numeric_unknown(response, value)
                if response.get("result", {}).get("isError") is True:
                    if typed_unknown and asset["name"] == "extreme" and variant == "NEW":
                        result["main_outcome"] = "numeric_insufficient_unknown"
                    else:
                        result["main_outcome"] = "unexpected_product_error"
                        result["errors"].append({"stage": "main_public_result", "message": value})
                else:
                    result["main_outcome"] = "observation_completed_quality_pending"
                    if value.get("result_kind") != "active_observation" or "frames" not in value:
                        result["errors"].append({"stage": "main_public_result", "message": "full producer result required"})
                    try:
                        result["producer_frames"] = producer_frames(value, output)
                    except (KeyError, OSError, ValueError) as error:
                        result["errors"].append({"stage": "same_result_producer_receipt", "message": str(error)})
                result["numeric_unknown_is_error_preserved"] = typed_unknown
            elif response.get("result", {}).get("isError") is True or value.get("result_kind") != "task_query":
                result["errors"].append({"stage": "post_main_source_readback", "message": value})
            result["requests"].append({**common,
                "is_error": response.get("result", {}).get("isError"),
                "public_schema": texts[0].get("schema"),
                "image_blocks": sum(block.get("type") == "image" for block in content),
                "public_text_UTF8_bytes": sum(len(block["text"].encode("utf-8")) for block in content if block.get("type") == "text"),
                "result_kind": value.get("result_kind")})
        result["passed"] = True
    except BaseException as error:
        result["errors"].append({"stage": "case", "type": type(error).__name__, "message": str(error),
                                  "traceback": traceback.format_exc()})
    finally:
        cleanup_started = time.perf_counter_ns()
        if client is not None:
            try:
                result["stdio_close"] = client.finish()
                if runtime_handle is None:
                    result["MCP_runtime_exit"] = {"confirmed": None, "reason": "retained_runtime_handle_not_acquired",
                                                  "held_stdio_process_exit": result["stdio_close"].get("exit_code")}
                else:
                    result["MCP_runtime_exit"] = process_proof._runtime_exit(runtime_handle)
                    runtime_handle = None
                if (not result["stdio_close"].get("confirmed")
                        or result["MCP_runtime_exit"].get("confirmed") is False):
                    raise RuntimeError("MCP_close_or_runtime_exit_unconfirmed")
            except BaseException as error:
                result["errors"].append({"stage": "MCP_cleanup", "type": type(error).__name__, "message": str(error)})
        if runtime_handle is not None:
            result["MCP_runtime_exit_after_failure"] = process_proof._runtime_exit(runtime_handle)
        if native is not None:
            try:
                result["native_close"] = native.close()
                result["native_final"] = native.status()
                closed = result["native_final"]["closed"]
                if (result["native_close"].get("exit_code") != 0 or not result["native_close"].get("process_reaped")
                        or closed is None or closed.get("poisoned")
                        or closed["initial_geometry_fingerprint"] != closed["final_geometry_fingerprint"]):
                    raise RuntimeError("owned_Blender_cleanup_or_source_changed")
            except BaseException as error:
                result["errors"].append({"stage": "Blender_cleanup", "type": type(error).__name__, "message": str(error)})
        result["cleanup_started_ns"] = cleanup_started
        budget.settle_start(claim, pid=None if native is None else native.config["pid"],
                            spawn_status="unknown" if native is None else "spawned",
                            outcome="failed" if result["errors"] else "completed")
        result["session_closed_ns"] = time.perf_counter_ns()
        result["complete_session_ns"] = result["session_closed_ns"] - started
    try:
        result["io_audit"] = rows(output / "io_audit/MCP_IO.jsonl")
        result["worker_events"] = rows(output / "native/WORKER_EVENTS.jsonl")
        index_path = output / "native/WIRE/INDEX.json"
        result["host_wire_index"] = load(index_path) if index_path.exists() else None
        if native is not None and initialized_identity is not None:
            result["saved_capture_extraction"] = extract(output, asset, binding, initialized_identity)
        verify_install(binding)
        if digest(asset["asset"]) != asset["asset_sha256"]:
            raise ValueError("original_owned_asset_changed")
    except BaseException as error:
        result["errors"].append({"stage": "postrun_saved_evidence", "type": type(error).__name__,
                                  "message": str(error), "traceback": traceback.format_exc()})
    result["postrun_closed_ns"] = time.perf_counter_ns()
    result["postrun_validation_ns"] = result["postrun_closed_ns"] - result["session_closed_ns"]
    result["passed"] = result["passed"] and not result["errors"]
    result["quality_status"] = "not_graded; public error/schema/images retained for independent qualification"
    result["budget_snapshot"] = budget.snapshot()
    save(output / "RESULT.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--asset", choices=("extreme", "origin", "peripheral"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--phase", choices=("qualification", "formal"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--variant", choices=("OLD", "NEW"), required=True)
    parser.add_argument("--requests", type=Path)
    args = parser.parse_args()
    asset = next(row for row in load(args.assets)["inputs"] if row["name"] == args.asset)
    result = run(binding_path=args.binding, asset=asset, output=args.output, ledger=args.ledger,
                 phase=args.phase, label=args.label, variant=args.variant,
                 requests=None if args.requests is None else load(args.requests))
    print(json.dumps({"passed": result["passed"], "output": str(args.output), "errors": result["errors"]}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
