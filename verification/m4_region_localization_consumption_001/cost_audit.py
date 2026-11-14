"""Recount sealed, saved evidence only. No product imports or workload calls."""

import ast
import base64
import hashlib
import io
import json
import statistics
import struct
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
FORMAL = Path("D:/he_loc_001/formal")
ORDER = ("N1", "P1", "P2", "N2", "N3", "P3")
SEAL_SHA256 = "6b5000de0ff44d67dce5d6e006471787921c1dd90cef74476f254abd89444c55"
INPUTS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = digest(data)
    return data


def read_json(path):
    return json.loads(read_bytes(path).decode("utf-8-sig"))


def checked_interval(value, start, end, elapsed):
    assert type(value[start]) is int and type(value[end]) is int
    assert value[end] >= value[start]
    assert value[elapsed] == value[end] - value[start]
    return {"started_ns": value[start], "closed_ns": value[end], "elapsed_ns": value[elapsed]}


def numpy_payload(data):
    """Read NPY metadata and raw payload length using the documented file header."""
    assert data[:6] == b"\x93NUMPY"
    major = data[6]
    header_size_bytes = 2 if major == 1 else 4
    header_length = int.from_bytes(data[8:8 + header_size_bytes], "little")
    offset = 8 + header_size_bytes + header_length
    header = ast.literal_eval(data[8 + header_size_bytes:offset].decode("latin1"))
    shape = header["shape"]
    count = 1
    for extent in shape:
        count *= extent
    item_size = int(header["descr"][2:])
    assert count * item_size == len(data) - offset
    return {"dtype": header["descr"], "shape": list(shape), "nbytes": len(data) - offset,
            "raw_sha256": digest(data[offset:])}


def frame_receipt(frame):
    png = read_bytes(frame["PNG"])
    npz = read_bytes(frame["NPZ"])
    assert len(png) == frame["PNG_bytes"] and digest(png) == frame["PNG_sha256"]
    assert len(npz) == frame["NPZ_bytes"] and digest(npz) == frame["NPZ_sha256"]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (512, 512)
    with zipfile.ZipFile(io.BytesIO(npz)) as archive:
        arrays = {Path(name).stem: numpy_payload(archive.read(name)) for name in archive.namelist()}
    assert set(arrays) == {"color", "depth", "owners", "triangle_ids"}
    payload = sum(row["nbytes"] for row in arrays.values())
    assert payload == frame["array_payload_bytes"] == frame["raster_returned_array_payload_bytes"]
    return {"view_name": frame["view_name"], "attempt_id": frame["attempt_id"],
            "global_attempt": frame["global_attempt"], "origin": frame["origin"],
            "started_ns": frame["started_ns"], "render_started_ns": frame["render_started_ns"],
            "render_closed_ns": frame["render_closed_ns"], "completed_ns": frame["completed_ns"],
            "raster_ns": frame["render_closed_ns"] - frame["render_started_ns"],
            "frame_total_ns": frame["completed_ns"] - frame["started_ns"],
            "PNG_bytes": len(png), "NPZ_bytes": len(npz), "array_payload_bytes": payload,
            "PNG_sha256": digest(png), "NPZ_sha256": digest(npz), "arrays": arrays,
            "source_capture_sha256": frame["source_capture_sha256"],
            "source_scene_sha256": frame["source_scene_sha256"]}


def native_images(c):
    rows = []
    for call in c["tool_calls"]:
        assert call["type"] == "item.completed"
        item = call["item"]
        for block_index, block in enumerate((item.get("result") or {}).get("content", [])):
            if block.get("type") != "image":
                continue
            png = base64.b64decode(block["data"], validate=True)
            assert block["mimeType"] == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", png[16:24]) == (512, 512)
            rows.append({"tool_item_id": item["id"], "block_index": block_index,
                         "received_ns": call["perf_ns"], "PNG_bytes": len(png),
                         "base64_chars": len(block["data"]), "PNG_sha256": digest(png)})
    assert len(rows) == c["public_image_count"]
    assert sum(row["PNG_bytes"] for row in rows) == c["public_image_bytes"]
    assert [(r["PNG_sha256"], r["PNG_bytes"]) for r in rows] == [
        (r["PNG_sha256"], r["PNG_bytes"]) for r in c["image_deliveries"]]
    return rows


def archive_receipt(originals):
    data = read_bytes(originals["path"])
    assert digest(data) == originals["sha256"] and len(data) == originals["bytes"]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = {name: digest(archive.read(name)) for name in archive.namelist()}
    assert members == originals["members_sha256"]
    return {"path": originals["path"], "bytes": len(data), "sha256": digest(data),
            "members": len(members), "all_member_hashes_match": True}


def evidence_reference(slot, sources, consumer, tools):
    receipts = []
    for source in sources:
        assert digest(read_bytes(source["path"])) == source["sha256"]
        if source["kind"] == "tool_result":
            attempt = int(Path(source["path"]).parent.name.split("_")[1])
            call = consumer["tool_calls"][attempt - 1]
            receipts.append({"source_id": source["id"], "kind": source["kind"],
                             "attempt": attempt, "CLI_completed_ns": call["perf_ns"],
                             "owner_closed_ns": tools[attempt - 1]["closed_ns"]})
        else:
            receipts.append({"source_id": source["id"], "kind": source["kind"],
                             "artifact_creation_monotonic_ns": None})
    timed = [r["CLI_completed_ns"] for r in receipts if "CLI_completed_ns" in r]
    anchor = max(timed) if len(timed) == len(receipts) else None
    end = consumer["final_received_ns"]
    remaining_tools = [r for r in tools if anchor is not None and r["started_ns"] >= anchor]
    return {"slot": slot, "quality_bound_sources": receipts,
            "earliest_task_sufficient_evidence_ns": None,
            "earliest_time_status": "Not established by the saved quality provenance.",
            "latest_receipt_among_quality_bound_tool_sources_ns": anchor,
            "receipt_to_final_inclusive_ns": end - anchor if anchor is not None else None,
            "later_owner_tool_service_ns": sum(r["elapsed_ns"] for r in remaining_tools),
            "scope": "A conservative reference to the latest scored source receipt, not proof of the first sufficient instant. Interval includes model/service/transport and later tools. Cited artifact lacks a monotonic creation receipt."}


def slot_cost(slot, normalized):
    folder = FORMAL / slot
    result = read_json(folder / "RESULT.json")
    outer = read_json(folder / "FINAL_TIMING.json")
    c = read_json(folder / "c/CONSUMER.json")
    ct = read_json(folder / "c/FINAL_TIMING.json")
    metrics = read_json(folder / "o/METRICS.json")
    observation = read_json(folder / "o/OBSERVATIONS.json")
    binding = read_json(folder / "c/BUSINESS_SOURCE_BINDING.json")
    runtime_binding = read_json(folder / "c/RUNTIME_BINDING.json")
    assert result["outer_valid_completion"] is True and outer["accepted_success"] is True
    assert c["valid_completion"] is True and c["safe_to_continue"] is True
    assert not result["errors"] and not result["common_image_faults"] and not c["errors"]
    assert result["input_readback_unchanged"] is True
    assert runtime_binding["confirmed"] is True and runtime_binding["after_stdio_STARTED"] is True
    for key in ("consumer_process_cleanup", "owner_process_cleanup"):
        cleanup = result[key]
        assert cleanup["confirmed"] is True and cleanup["exit_code"] == 0
        assert cleanup["reaped"] is True and cleanup["process_handle_closed"] is True
    thin = result["runtime_exit"]
    assert thin["confirmed"] is True and thin["exited"] is True and thin["handle_closed"] is True
    assert thin["exit_code"] == 1
    assert result["bridge_cleanup"]["confirmed"] is None
    assert result["bridge_cleanup"]["missing_exit_count"] == 1
    assert result["owner_close_confirmed"] is True
    full = checked_interval(outer, "started_ns", "result_closed_ns", "elapsed_ns")
    consumer_full = checked_interval(ct, "started_ns", "consumer_record_closed_ns", "full_turn_wall_ns")
    assert outer["original_deadline_ns"] == full["started_ns"] + 450_000_000_000
    assert full["closed_ns"] <= outer["original_deadline_ns"]
    tools = metrics["tools"]
    assert len(tools) == len(c["tool_calls"]) == metrics["tool_attempts"] == result["actual_tool_calls"]
    assert [r["attempt"] for r in tools] == list(range(1, len(tools) + 1))
    assert len(binding["result_contracts"]) == len(tools) and not binding["binding_errors"]
    assert all(r["matched"] is True for r in binding["result_contracts"])
    for tool in tools:
        checked_interval(tool, "started_ns", "closed_ns", "elapsed_ns")
    assert all(a["closed_ns"] <= b["started_ns"] for a, b in zip(tools, tools[1:]))
    frames = [frame_receipt(frame) for frame in observation["frames"]]
    common = metrics["common"]
    assert len(frames) == len(observation["render_attempts"]) == common["render_attempts"] == 6
    assert len({row["view_name"] for row in frames}) == 6
    assert not observation["active"] and common["product_observation_calls"] == 0
    assert common["capture_replay_calls"] == common["actual_Blender_capture_calls"] == 0
    assert all(row["origin"] == "native" for row in frames)
    images = native_images(c)
    assert len(images) == metrics["constructed_image_blocks"] == metrics["server_socket_sent_image_blocks"]
    assert sum(row["PNG_bytes"] for row in images) == metrics["constructed_PNG_bytes"] == metrics["server_socket_sent_PNG_bytes"]
    assert all(row["PNG_sha256"] in {f["PNG_sha256"] for f in frames} for row in images)
    assert all(not metrics[key] for key in ("failed_image_constructions", "post_construction_failures", "failed_or_unknown_socket_sends"))
    wire_files = []
    for wire in c["MCP_wire_files"]:
        path = folder / "c" / wire["path"]
        data = read_bytes(path)
        assert len(data) == wire["bytes"] and digest(data) == wire["sha256"]
        wire_files.append({"path": str(path), "direction": path.name.split(".")[0], "bytes": len(data), "sha256": digest(data)})
    stdout = read_bytes(folder / "c/stdout.raw.bin")
    stderr = read_bytes(folder / "c/stderr.raw.bin")
    assert len(stdout) == c["stdout_raw_bytes"] and digest(stdout) == c["stdout_raw_sha256"]
    usage = c["usage"]
    assert len(c["raw_usage_events"]) == len(c["usage_rows"]) == 1
    assert usage == c["raw_usage_events"][0] == c["usage_rows"][0]
    assert 0 <= usage["cached_input_tokens"] <= usage["input_tokens"]
    assert 0 <= usage["reasoning_output_tokens"] <= usage["output_tokens"]
    scratch = []
    for root in (folder / "o/scratch", folder / "w"):
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    data = read_bytes(path)
                    scratch.append({"path": str(path), "bytes": len(data), "sha256": digest(data)})
    requests = []
    responses = []
    errors = []
    for tool in tools:
        tool_folder = folder / "o" / ("tool_%02d" % tool["attempt"])
        request = read_bytes(tool_folder / "REQUEST.json")
        response = read_bytes(tool_folder / "RESPONSE.json")
        requests.append({"attempt": tool["attempt"], "bytes": len(request), "sha256": digest(request)})
        responses.append({"attempt": tool["attempt"], "bytes": len(response), "sha256": digest(response)})
        if tool["is_error"]:
            errors.append({"attempt": tool["attempt"], "name": tool["name"],
                           "elapsed_ns": tool["elapsed_ns"], "response_sha256": digest(response),
                           "binding_classification": binding["result_contracts"][tool["attempt"] - 1]["classification"],
                           "scope": "Recoverable business error retained in original tool body and total cost."})
    clock_keys = ("started_ns", "popen_ns", "prompt_write_started_ns", "prompt_submitted_ns", "final_received_ns",
                  "turn_completed_ns", "process_exit_ns", "cleanup_end_ns")
    clocks = {key: c[key] for key in clock_keys}
    service = sum(row["elapsed_ns"] for row in tools)
    tool_window = c["final_received_ns"] - c["prompt_submitted_ns"]
    assert all(c["prompt_submitted_ns"] <= row["started_ns"] <= row["closed_ns"] <= c["final_received_ns"] for row in tools)
    timings = {"full_outer": full, "full_outer_scope": outer["scope"], "consumer_full": consumer_full,
               "consumer_full_scope": ct["scope"], "CLI_clocks": clocks,
               "prompt_to_final_ns": tool_window, "owner_tool_service_sum_ns": service,
               "prompt_to_final_minus_owner_service_ns": tool_window - service,
               "residual_scope": "Model/service/transport and unseparated local work. No pure-thinking attribution.",
               "CLI_turn_completed_to_process_exit_ns": c["process_exit_ns"] - c["turn_completed_ns"],
               "consumer_post_exit_to_record_close_ns": ct["consumer_record_closed_ns"] - c["process_exit_ns"],
               "outer_before_consumer_ns": c["started_ns"] - outer["started_ns"],
               "outer_after_consumer_record_ns": outer["result_closed_ns"] - ct["consumer_record_closed_ns"],
               "owner_cleanup": result["owner_process_cleanup"],
               "CLI_cleanup": result["consumer_process_cleanup"], "thin_held_cleanup": thin,
               "original_deadline_ns": outer["original_deadline_ns"],
               "FINAL_TIMING_receipt_own_publication_ns": None,
               "publication_scope": "Outer clock ends at RESULT close/readback. FINAL_TIMING receipt writing itself has no independent per-slot closing clock; controller return includes it."}
    return {"slot": slot, "group": slot[0], "pair": int(slot[1:]), "fully_qualified": True,
            "thread_id_sha256": digest(c["thread_id"].encode()), "fresh_context": True,
            "active_entry_calls": 0, "product_prepare_calls": 0, "product_index_calls": 0,
            "source_capture_replay_host_calls": common["capture_replay_calls"],
            "lifecycle": {"CLI_pid": result["consumer_pid"], "actor_pid": result["owner_pid"],
                          "runtime_binding": runtime_binding, "bridge_EXIT_receipt": result["bridge_cleanup"],
                          "CLI_exit_code": result["consumer_process_cleanup"]["exit_code"],
                          "actor_exit_code": result["owner_process_cleanup"]["exit_code"],
                          "thin_exit_code": thin["exit_code"], "all_held_handles_closed": True,
                          "normal_thin_EOF_proven": False},
            "timing": timings, "shared_startup_stages": observation["stages"],
            "usage": usage, "raw_usage_events": c["raw_usage_events"], "usage_semantics": c["usage_semantics"],
            "usage_aggregation_original": c["usage_aggregation"],
            "reported_input_plus_output": usage["input_tokens"] + usage["output_tokens"],
            "reported_uncached_input": usage["input_tokens"] - usage["cached_input_tokens"],
            "model_request": {"model": c["model"], "effort": c["requested_effort"], "resolved_effort": c["resolved_effort"]},
            "provider_retry_observations": c["provider_retry_observations"], "CLI_errors": c["errors"],
            "interrupted_stream_usage_coverage_original": c["summary"].get("interrupted_stream_usage_coverage"),
            "tools": tools, "tool_attempts": len(tools), "ordinary_business_errors": errors,
            "source_requests": requests, "source_responses": responses,
            "request_file_bytes": sum(row["bytes"] for row in requests),
            "response_file_bytes": sum(row["bytes"] for row in responses),
            "consumer_text_bytes": {key: c[key] for key in ("input_text_bytes", "public_text_bytes", "output_text_bytes", "bridge_public_text_bytes")},
            "prompt_sha256": c["input_sha256"],
            "image_constructed_sent_metrics": {key: value for key, value in metrics.items() if key not in ("tools", "common")},
            "images_CLI_completed": images, "images_CLI_completed_count": len(images),
            "images_CLI_PNG_bytes": sum(row["PNG_bytes"] for row in images),
            "frames": frames, "native_work": common,
            "frame_raster_sum_ns": sum(row["raster_ns"] for row in frames),
            "frame_total_sum_ns": sum(row["frame_total_ns"] for row in frames),
            "frame_non_raster_sum_ns": sum(row["frame_total_ns"] - row["raster_ns"] for row in frames),
            "array_bytes_scope": "Cumulative generated four-array payload. Retained cache/scratch footprint is partial; peak RSS and Python/NumPy temporaries unmeasured.",
            "scratch_files": scratch, "scratch_file_bytes": sum(row["bytes"] for row in scratch),
            "MCP_wire_files": wire_files, "stdio_TX_bytes": c["MCP_stdio_TX_bytes"], "stdio_RX_bytes": c["MCP_stdio_RX_bytes"],
            "raw_stdout_bytes": len(stdout), "raw_stdout_sha256": digest(stdout), "raw_stderr_bytes": len(stderr),
            "archives": {"outer": archive_receipt(result["originals"]), "consumer": {
                "bytes": len(read_bytes(folder / "c.raw.zip")), "sha256": INPUTS[str((folder / "c.raw.zip").resolve())]}},
            "sufficient_evidence": evidence_reference(slot, normalized[slot]["sources"], c, tools)}


def aggregate(slots, group):
    selected = [row for row in slots if row["group"] == group]
    usage = {key: sum(row["usage"][key] for row in selected) for key in selected[0]["usage"]}
    return {"slots": len(selected), "full_outer_ns": sum(row["timing"]["full_outer"]["elapsed_ns"] for row in selected),
            "median_full_outer_ns": statistics.median(row["timing"]["full_outer"]["elapsed_ns"] for row in selected),
            "usage": usage, "reported_input_plus_output": usage["input_tokens"] + usage["output_tokens"],
            "tool_attempts": sum(row["tool_attempts"] for row in selected),
            "native_rasters": sum(row["native_work"]["render_attempts"] for row in selected),
            "CLI_image_blocks": sum(row["images_CLI_completed_count"] for row in selected)}


def build():
    assert digest(read_bytes(HERE / "QUALITY_SEAL.json")) == SEAL_SHA256
    seal = read_json(HERE / "QUALITY_SEAL.json")
    assert seal["quality_complete"] == seal["denominator"] == 6
    assert seal["cost_analysis_unlocked_after_this_seal"] is True
    for entry in seal["inputs"]:
        candidate = Path(entry["path"])
        if not candidate.is_absolute():
            candidate = HERE / candidate
        assert digest(read_bytes(candidate)) == entry["sha256"]
    normalized = {row["slot_id"]: row for row in read_json(HERE / "admin/NORMALIZED.json")["slots"]}
    source_audit = read_json(HERE / "review/SOURCE_PROCESS_AUDIT.json")
    preparation = read_json(HERE / "PREPARATION.json")
    read_json(HERE / "PREPARATION_QUALIFICATION.json")
    plan = read_json(HERE / "PLAN.json")
    frozen = read_json(HERE / "FROZEN.json")
    manifest_path = Path(plan["inputs"]["input_manifest"])
    manifest = read_json(manifest_path)
    shared_sources = {}
    for name in ("scene", "cameras", "capture", "product_binding"):
        row = manifest[name]
        path = Path(row["path"]) if "path" in row else manifest_path.parent / row["file"]
        data = read_bytes(path)
        assert digest(data) == row["sha256"]
        shared_sources[name] = {"path": str(path), "bytes": len(data), "sha256": digest(data)}
    prompt = read_bytes(plan["inputs"]["prompt"])
    assert digest(prompt) == plan["expected_prompt_sha256"]
    intents = [read_json(path) for path in sorted(Path("D:/he_loc_001/raster_budget").glob("attempt_*/INTENT.json"))]
    assert [row["global_attempt"] for row in intents] == list(range(1, 41))
    assert sum(row["phase"] == "formal" for row in intents) == 36
    assert sum(row["phase"] == "preparation" for row in intents) == 4
    run = read_json(FORMAL / "RUN_RESULT.json")
    controller = read_json(HERE / "FORMAL_PROCESS.json")
    batch_clock = read_json(FORMAL / "BATCH_TIMING.json")
    launch_clock = read_json(FORMAL / "LAUNCH_TIMING.json")
    launch = read_json(FORMAL / "LAUNCH_RESULT.json")
    slots = [slot_cost(slot, normalized) for slot in ORDER]
    assert [row["slot"] for row in run["records"]] == list(ORDER)
    assert run["actual_CLI_processes"] == run["actual_routes"] == 6
    assert len({row["thread_id_sha256"] for row in slots}) == 6
    assert all(row["prompt_sha256"] == digest(prompt) for row in slots)
    assert [row["images_CLI_completed_count"] for row in slots] == [2, 0, 6, 2, 2, 6]
    assert sum(row["tool_attempts"] for row in slots) == 50
    assert sum(row["native_work"]["render_attempts"] for row in slots) == 36
    assert source_audit["P_advertisement_and_adoption"]["formal_P_active_observation_calls"] == 0
    assert launch["source_unchanged"] is True
    groups = {group: aggregate(slots, group) for group in ("N", "P")}
    pairs = []
    for pair in (1, 2, 3):
        n = next(row for row in slots if row["slot"] == "N" + str(pair))
        p = next(row for row in slots if row["slot"] == "P" + str(pair))
        pairs.append({"pair": pair, "N_full_outer_ns": n["timing"]["full_outer"]["elapsed_ns"],
                      "P_full_outer_ns": p["timing"]["full_outer"]["elapsed_ns"],
                      "P_over_N_time": p["timing"]["full_outer"]["elapsed_ns"] / n["timing"]["full_outer"]["elapsed_ns"],
                      "N_reported_input_plus_output": n["reported_input_plus_output"],
                      "P_reported_input_plus_output": p["reported_input_plus_output"],
                      "P_over_N_reported_input_plus_output": p["reported_input_plus_output"] / n["reported_input_plus_output"]})
    total_slot_ns = sum(row["timing"]["full_outer"]["elapsed_ns"] for row in slots)
    assert controller["elapsed_ns"] == controller["closed_ns"] - controller["started_ns"]
    result = {
        "schema": "region-localization-saved-cost-audit-v1", "task": "M4-REGION-LOCALIZATION-CONSUMPTION-001",
        "quality_seal_sha256": SEAL_SHA256, "quality_complete": 6,
        "frozen_source_identity": {"FROZEN_sha256": INPUTS[str((HERE / "FROZEN.json").resolve())],
            "frozen_file_count": len(frozen["files_sha256"]), "product_source_sha256": frozen["product_source_sha256"],
            "source_process_audit_sha256": INPUTS[str((HERE / "review/SOURCE_PROCESS_AUDIT.json").resolve())],
            "scope": "Uses the already sealed independent source/process audit. No product source execution or repeated source qualification."},
        "shared_input_bytes": {"prompt_bytes_per_slot": len(prompt), "prompt_sha256": digest(prompt),
            "sources": shared_sources, "scope": "Source bytes resident in each fresh actor. These file sizes are separate from model-visible text and tool-response bytes."},
        "requested_configuration": {key: plan[key] for key in ("requested_model", "requested_reasoning_effort", "requested_service_tier", "authentication")},
        "durable_raster_intents": intents,
        "source_process_review_passed": source_audit["passed"],
        "scope": "Single sealed six-context batch, source-capture replay, current-session native computation and raster. Saved-only accounting.",
        "execution_denominators": {"actual_CLI_sessions": 6, "fresh_context_hashes": 6, "formal_tool_attempts": 50,
            "formal_native_rasters": 36, "preparation_rasters": preparation["total_preparation_rasters"],
            "whole_task_new_rasters": 36 + preparation["total_preparation_rasters"], "whole_task_hard_cap": 44,
            "formal_CLI_image_blocks": sum(row["images_CLI_completed_count"] for row in slots),
            "formal_CLI_exit0": 6, "formal_actor_exit0": 6, "formal_thin_exit1": 6,
            "formal_thin_EXIT_receipt_unknown": 6, "formal_thin_held_exit_confirmed_and_handle_closed": 6,
            "ordinary_business_tool_errors": sum(len(row["ordinary_business_errors"]) for row in slots)},
        "adoption": {"P_active_entry_calls": 0, "P_contexts": 3, "formal_product_observation_calls": 0,
            "formal_product_prepare_or_index_calls": 0, "formal_capture_replay_host_calls": 0,
            "P_advertisement": source_audit["P_advertisement_and_adoption"],
            "interpretation": "P denotes availability of an additional entry. All six executed native algorithms and six raw views. Causal product-algorithm benefit is unmeasured."},
        "slots": slots, "groups": groups, "pairs": pairs,
        "availability_cohort_comparison": {
            "paired_median_P_over_N_full_time": statistics.median(row["P_over_N_time"] for row in pairs),
            "total_P_over_N_full_time": groups["P"]["full_outer_ns"] / groups["N"]["full_outer_ns"],
            "paired_median_P_over_N_reported_input_plus_output": statistics.median(row["P_over_N_reported_input_plus_output"] for row in pairs),
            "total_P_over_N_reported_input_plus_output": groups["P"]["reported_input_plus_output"] / groups["N"]["reported_input_plus_output"],
            "interpretation": "Descriptive availability-cohort ratios on three fixed pairs. Zero P entry adoption prevents attribution to active-observation algorithms. No significance or full R&D net benefit claim."},
        "whole_formal_timing": {"parent_process": controller, "batch": batch_clock, "launch": launch_clock,
            "sum_slot_full_outer_ns": total_slot_ns,
            "batch_minus_sum_slot_ns": batch_clock["elapsed_ns"] - total_slot_ns,
            "parent_minus_sum_slot_ns": controller["elapsed_ns"] - total_slot_ns,
            "nesting": "Parent contains launch, launch contains batch, batch contains sequential slots. Nested and residual clocks are not added to parent again."},
        "preparation": preparation,
        "totals": {"generated_PNG_bytes": sum(r["native_work"]["PNG_bytes"] for r in slots),
            "generated_NPZ_bytes": sum(r["native_work"]["NPZ_bytes"] for r in slots),
            "generated_array_payload_bytes": sum(r["native_work"]["array_payload_bytes"] for r in slots),
            "constructed_and_CLI_received_PNG_bytes": sum(r["images_CLI_PNG_bytes"] for r in slots),
            "constructed_base64_chars": sum(r["image_constructed_sent_metrics"]["constructed_base64_chars"] for r in slots),
            "stdio_TX_bytes": sum(r["stdio_TX_bytes"] for r in slots), "stdio_RX_bytes": sum(r["stdio_RX_bytes"] for r in slots),
            "actor_tool_MCP_JSON_bytes": sum(r["image_constructed_sent_metrics"]["server_socket_sent_MCP_JSON_bytes"] for r in slots),
            "actor_tool_outer_TCP_JSON_bytes": sum(r["image_constructed_sent_metrics"]["server_socket_sent_outer_TCP_JSON_bytes"] for r in slots),
            "constructed_image_block_JSON_bytes": sum(r["image_constructed_sent_metrics"]["constructed_image_block_JSON_bytes"] for r in slots),
            "actor_socket_request_bytes": sum(r["image_constructed_sent_metrics"]["server_socket_request_bytes"] for r in slots),
            "actor_sent_text_UTF8_bytes": sum(r["image_constructed_sent_metrics"]["server_socket_sent_text_UTF8_bytes"] for r in slots),
            "raw_stdout_bytes": sum(r["raw_stdout_bytes"] for r in slots),
            "tool_request_file_bytes": sum(r["request_file_bytes"] for r in slots),
            "tool_response_file_bytes": sum(r["response_file_bytes"] for r in slots),
            "owner_tool_service_ns": sum(r["timing"]["owner_tool_service_sum_ns"] for r in slots),
            "native_frame_raster_ns": sum(r["frame_raster_sum_ns"] for r in slots),
            "native_frame_total_ns": sum(r["frame_total_sum_ns"] for r in slots),
            "shared_startup_ns": sum(stage["elapsed_ns"] for r in slots for stage in r["shared_startup_stages"]),
            "scratch_file_bytes": sum(r["scratch_file_bytes"] for r in slots),
            "byte_scope": "PNG/base64/JSON/stdout/archive and payload figures describe nested representations. They are not summed as independent network or memory allocations."},
        "unknowns": {"provider_internal_raw_requests": None, "provider_internal_tool_definitions": None,
            "provider_resolved_model_effort_tier": None, "image_tokens": None, "cash_fees": None,
            "peak_RSS": None, "all_Python_temporaries_and_retained_warm_state_bytes": None,
            "model_native_algorithm_index_time_separated_from_tools": None,
            "first_complete_sufficient_evidence_monotonic_time": None,
            "total_source_authoring_and_root_review_R_and_D_cost": None,
            "usage_scope": "CLI labels turn/session scope unconfirmed and aggregation null. One recorded usage event per fresh one-user context. Cached input is a subset of input and reasoning output a subset of output; neither is added again.",
            "reconnect_scope": "No retry observations or top-level CLI errors in these six records. Raw provider request coverage remains unobserved; interrupted-stream usage coverage retains the original unknown value.",
            "encoding_scope": "Bytes are measured. Standalone encode/decode CPU time is not independently clocked; it is nested in tool/frame/outer intervals."},
        "next_direction": "Validate actual routing into the available production active-observation entry on the next authorized task, then verify its returned facts are used. Keep native computation as the shared baseline.",
        "audit_scope": {"new_product_calls": 0, "new_model_calls": 0, "new_rasters": 0, "new_tests": 0,
            "saved_only_audit_prepublication_corrections": [{"error": "AttributeError: 'list' object has no attribute 'items'", "location": "quality seal input iteration", "correction": "Iterate the actual sealed list of path/sha256 rows. No formal input changed."}],
            "saved_arrays_inspection": "Standard-library NPZ/NPY headers and payload hashes only; no product import or geometry evaluation.",
            "source_script_sha256": digest(Path(__file__).read_bytes())},
        "inputs_sha256": dict(sorted(INPUTS.items()))}
    return result


def markdown(result):
    comparison = result["availability_cohort_comparison"]
    lines = ["# 空间定位消费批成本审计", "", "六槽质量已封存通过，覆盖828个面片判断和18项定位问题。P三槽实际主动观察调用为0，六槽都通过原生Python计算并构造六个原始视图。", "",
             "| 槽 | 完整外层秒 | input | output | cached input | 工具 | 新图 | CLI图像块 | 产品观察 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["slots"]:
        usage = row["usage"]
        lines.append(f"| {row['slot']} | {row['timing']['full_outer']['elapsed_ns']/1e9:.7f} | {usage['input_tokens']} | {usage['output_tokens']} | {usage['cached_input_tokens']} | {row['tool_attempts']} | 6 | {row['images_CLI_completed_count']} | 0 |")
    lines.extend(["", "| 配对 | P/N完整时间 | P/N input+output |", "|---|---:|---:|"])
    for pair in result["pairs"]:
        lines.append(f"| {pair['pair']} | {pair['P_over_N_time']:.9f} | {pair['P_over_N_reported_input_plus_output']:.9f} |")
    n, p = result["groups"]["N"], result["groups"]["P"]
    totals = result["totals"]
    lines.extend(["", f"P/N配对完整时间比中位数为{comparison['paired_median_P_over_N_full_time']:.9f}。N总时间{n['full_outer_ns']/1e9:.7f}秒，P为{p['full_outer_ns']/1e9:.7f}秒。input+output分别为{n['reported_input_plus_output']}和{p['reported_input_plus_output']}，总量比为{comparison['total_P_over_N_reported_input_plus_output']:.9f}。这些数值描述三个固定配对中的入口可用性分组。实际采用为零，当前证据无法归因产品算法收益，也未建立统计显著性。", "",
        "cached input已经包含在input中，reasoning output已经包含在output中。每个fresh单用户上下文保存一个usage事件，原CLI仍将turn/session用量语义标为未确认。图像token、现金费用、provider内部请求及resolved设置保持未测。", "",
        f"正式36次新raster，准备4次，共40次，整体硬上限44。正式生成PNG共{totals['generated_PNG_bytes']}字节，NPZ为{totals['generated_NPZ_bytes']}字节，四数组累计载荷{totals['generated_array_payload_bytes']}字节。实际构造、发送并在CLI完成事件验证18个PNG块，共{totals['constructed_and_CLI_received_PNG_bytes']}字节，base64共{totals['constructed_base64_chars']}字符。生成图和交付图分别计数，数组载荷没有峰值RSS含义。", "",
        f"工具服务累计{totals['owner_tool_service_ns']/1e9:.7f}秒，其中原生raster累计{totals['native_frame_raster_ns']/1e9:.7f}秒。帧创建累计{totals['native_frame_total_ns']/1e9:.7f}秒包含raster及文件发布。MCP工具JSON共{totals['actor_tool_MCP_JSON_bytes']}字节，stdio TX/RX分别{totals['stdio_TX_bytes']}/{totals['stdio_RX_bytes']}字节。JSON、base64、PNG、stdout与归档存在嵌套，报告保留各层原数。", "",
        "两次普通业务工具错误均保留并随后恢复。六个CLI与六个actor均exit0且原持有句柄关闭。六个thin运行时均由真实只读持有句柄确认exit1并关闭，六份stdio EXIT回执未知。原有验收根据真实held-exit证据接受收尾，未证明thin正常EOF。", "",
        f"完整正式父进程墙钟{result['whole_formal_timing']['parent_process']['elapsed_ns']/1e9:.7f}秒，覆盖顺序六槽、协调、归档与外层发布。六槽外层均从启动前输入检查计到CLI/actor/thin收尾、ZIP、来源回读及RESULT写关。FINAL_TIMING回执自身写入缺独立每槽终点，父进程返回范围包含它。准备可观测验证窗口{result['preparation']['recorded_validation_window']['elapsed_ns']/1e9:.7f}秒，研发编写和根审查总成本未完整测量。", "",
        "评分来源可定位到相应工具完成回执，报告给出这些来源中最后一份回执至final的包容区间。最早充分证据时刻仍未知，后续区间包含模型、服务、传输和可能的补查。P3引用本次scratch文件，其创建缺单独单调时钟。", "",
        "下一步优先验证真实路由能调用现有生产主动观察入口，并确认返回事实被实际采用，再对同质量任务核对收益。", "",
        "审计仅读取已保存JSON、原始stdio、ZIP及PNG/NPZ，不新增产品调用、模型会话、测试或光栅。完整原值、时界、来源SHA和未知项见COST_REPORT.json。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    report = build()
    (HERE / "COST_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "COST_REPORT.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"quality_complete": report["quality_complete"], "adoption": 0,
                      "slots": len(report["slots"]), "pairs": report["availability_cohort_comparison"]}))
