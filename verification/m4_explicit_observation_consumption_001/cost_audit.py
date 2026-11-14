"""Audit this failed single slot from saved bytes, without workload imports."""

import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile


HERE = Path(__file__).resolve().parent
EXTERNAL = Path("D:/he_explicit_001")
FORMAL = EXTERNAL / "formal"
SLOT = FORMAL / "P1"
SEAL_SHA256 = "7de89e0a44dff61f530e55330b8f79805fda37b263cd73f1ada4c3403271d34f"
INPUTS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = digest(data)
    return data


def read(path):
    return json.loads(raw(path))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def interval(value, start="started_ns", end="closed_ns", elapsed="elapsed_ns"):
    first, last = value[start], value[end]
    require(type(first) is int and type(last) is int and last >= first, "saved_clock_order")
    require(value[elapsed] == last - first, "saved_clock_elapsed")
    return {"started_ns": first, "closed_ns": last, "elapsed_ns": last - first}


def verify_seal():
    require(digest(raw(HERE / "QUALITY_SEAL.json")) == SEAL_SHA256, "quality_seal_identity")
    seal = read(HERE / "QUALITY_SEAL.json")
    require(seal["cost_analysis_unlocked_after_this_seal"] is True, "quality_before_cost")
    for row in seal["inputs"]:
        require(digest(raw(HERE / row["path"])) == row["sha256"], "sealed_quality_file_changed")
    return seal


def npy_payload(data):
    require(data[:6] == b"\x93NUMPY", "saved_NPY_magic")
    length_size = 2 if data[6] == 1 else 4
    header_size = int.from_bytes(data[8:8 + length_size], "little")
    offset = 8 + length_size + header_size
    header = ast.literal_eval(data[8 + length_size:offset].decode("latin1"))
    description = header["descr"]
    require(isinstance(description, str), "simple_saved_NPY_dtype")
    kind, width = description[1], int(description[2:])
    item_bytes = width * 4 if kind == "U" else width
    count = 1
    for dimension in header["shape"]:
        count *= dimension
    require(count * item_bytes == len(data) - offset, "saved_NPY_payload_size")
    return {"dtype": description, "shape": list(header["shape"]),
            "nbytes": len(data) - offset, "raw_sha256": digest(data[offset:]),
            "fortran_order": header["fortran_order"]}


def frame_cost(frame):
    png, npz = raw(frame["PNG"]), raw(frame["NPZ"])
    require(len(png) == frame["PNG_bytes"] and digest(png) == frame["PNG_sha256"], "saved_PNG_binding")
    require(len(npz) == frame["NPZ_bytes"] and digest(npz) == frame["NPZ_sha256"], "saved_NPZ_binding")
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (512, 512), "saved_512_PNG")
    with zipfile.ZipFile(io.BytesIO(npz)) as archive:
        arrays = {Path(name).stem: npy_payload(archive.read(name)) for name in archive.namelist()}
    owner_key = "patch_owners" if frame["origin"] == "product" else "triangle_ids"
    buffer_names = {"color", "depth", "owners", owner_key}
    require(buffer_names <= set(arrays), "four_common_buffers")
    for name, array in arrays.items():
        metadata = frame["arrays"][name]
        require(array["nbytes"] == metadata["nbytes"] and array["shape"] == metadata["shape"]
                and array["raw_sha256"] == metadata["sha256"], "saved_array_payload_binding")
    four_payload = sum(arrays[name]["nbytes"] for name in buffer_names)
    mapping_payload = sum(array["nbytes"] for name, array in arrays.items() if name not in buffer_names)
    require(four_payload == frame["raster_returned_array_payload_bytes"], "actual_raster_buffer_bytes")
    require(four_payload + mapping_payload == frame["array_payload_bytes"], "saved_all_array_bytes")
    require(set(arrays) == buffer_names if frame["origin"] == "native" else len(arrays) == 9, "saved_array_count")
    return {key: frame[key] for key in ("attempt_id", "global_attempt", "origin", "view_name", "ref") } | {
        "PNG_bytes": len(png), "NPZ_bytes": len(npz), "PNG_sha256": digest(png), "NPZ_sha256": digest(npz),
        "arrays": arrays, "four_buffer_payload_bytes": four_payload, "mapping_metadata_payload_bytes": mapping_payload,
        "all_saved_array_payload_bytes": four_payload + mapping_payload,
        "intent_ns": frame["started_ns"], "render_started_ns": frame["render_started_ns"],
        "render_closed_ns": frame["render_closed_ns"], "registered_ns": frame["completed_ns"],
        "original_raster_call_ns": frame["render_closed_ns"] - frame["render_started_ns"],
        "intent_to_registered_ns": frame["completed_ns"] - frame["started_ns"],
        "post_raster_until_registration_ns": frame["completed_ns"] - frame["render_closed_ns"],
        "clock_scope": "Product registrations occur after the entire three-view producer call, so those intent-to-registration windows overlap. They are not added as independent work."}


def cli_images(consumer):
    rows = []
    for call in consumer["tool_calls"]:
        for index, block in enumerate((call["item"].get("result") or {}).get("content", [])):
            if block.get("type") != "image":
                continue
            png = base64.b64decode(block["data"], validate=True)
            require(block["mimeType"] == "image/png" and struct.unpack(">II", png[16:24]) == (512, 512), "CLI_PNG")
            rows.append({"tool_item_id": call["item"]["id"], "content_block_index": index,
                         "received_ns": call["perf_ns"], "PNG_bytes": len(png), "PNG_sha256": digest(png),
                         "base64_chars": len(block["data"]),
                         "image_block_JSON_bytes": len(json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode("utf8"))})
    require(len(rows) == consumer["public_image_count"], "CLI_image_count")
    require(sum(row["PNG_bytes"] for row in rows) == consumer["public_image_bytes"], "CLI_image_bytes")
    return rows


def zip_receipt(path, expected):
    data = raw(path)
    require(digest(data) == expected, "saved_archive_SHA")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = {name: digest(archive.read(name)) for name in archive.namelist()}
    return {"path": str(path), "bytes": len(data), "sha256": digest(data), "member_count": len(members),
            "members_sha256": members}


def build():
    seal = verify_seal()
    parent = read(HERE / "FORMAL_PROCESS.json")
    result = read(SLOT / "RESULT.json")
    run = read(FORMAL / "RUN_RESULT.json")
    consumer = read(SLOT / "c/CONSUMER.json")
    route_clock = read(SLOT / "FINAL_TIMING.json")
    consumer_clock = read(SLOT / "c/FINAL_TIMING.json")
    metrics = read(SLOT / "o/METRICS.json")
    observations = read(SLOT / "o/OBSERVATIONS.json")
    product = read(SLOT / "o/product_call_01/SERVICE_RESULT.json")
    product_call = read(SLOT / "o/product_call_01/CALL.json")
    constructions = read(SLOT / "o/IMAGE_CONSTRUCTIONS.json")
    transports = read(SLOT / "o/TRANSPORT.json")
    binding = read(SLOT / "c/BUSINESS_SOURCE_BINDING.json")
    runtime_binding = read(SLOT / "c/RUNTIME_BINDING.json")
    read(SLOT / "o/CLOSE.json")
    read(SLOT / "ACTOR_CONFIG.json")
    plan = read(HERE / "PLAN.json")
    read(HERE / "FROZEN.json")
    read(HERE / "inputs/SOURCES.json")
    require(not consumer["valid_completion"] and not route_clock["accepted_success"], "retain_failed_outcome")
    require(not (SLOT / "c/PUBLIC_FINAL.txt").exists(), "retain_missing_final")
    clocks = {"parent": interval(parent),
              "route": interval(route_clock, end="result_closed_ns"),
              "consumer": interval(consumer_clock, end="consumer_record_closed_ns", elapsed="full_turn_wall_ns")}
    require(clocks["parent"]["started_ns"] <= clocks["route"]["started_ns"] <= clocks["consumer"]["started_ns"]
            <= clocks["consumer"]["closed_ns"] <= clocks["route"]["closed_ns"] <= clocks["parent"]["closed_ns"], "nested_outer_clocks")
    require(route_clock["original_deadline_ns"] == clocks["route"]["started_ns"] + 450_000_000_000, "original_450_second_deadline")
    tools = []
    for row, call in zip(metrics["tools"], consumer["tool_calls"]):
        number = row["attempt"]
        request_path = SLOT / "o" / f"tool_{number:02}" / "REQUEST.json"
        response_path = request_path.with_name("RESPONSE.json")
        request, response = read(request_path), read(response_path)
        require(call["item"]["tool"] == request["params"]["name"] == row["name"], "actual_tool_name_binding")
        require(call["item"]["result"]["content"] == response["result"]["content"], "actual_tool_content_binding")
        tools.append({"attempt": number, "name": row["name"], "admitted_to_business_entry": number <= 12,
                      **interval(row), "CLI_completed_ns": call["perf_ns"], "is_error": row["is_error"],
                      "error": row["error"], "response_serialization_error": row["response_serialization_error"],
                      "content_metrics": row["content_metrics"], "compact_response_bytes": row["response_bytes"],
                      "request_file_bytes": request_path.stat().st_size, "response_file_bytes": response_path.stat().st_size,
                      "request_sha256": INPUTS[str(request_path.resolve())], "response_sha256": INPUTS[str(response_path.resolve())]})
    require(len(tools) == len(metrics["tools"]) == len(consumer["tool_calls"]) == 13, "thirteen_received_attempts")
    require([row["attempt"] for row in tools] == list(range(1, 14)), "sequential_attempt_ids")
    require(tools[-1]["is_error"] and "route_twelve_tool_call_limit" in str(tools[-1]["error"]), "thirteenth_guard_rejection")
    require(not binding["binding_errors"] and len(binding["result_contracts"]) == 13
            and all(row["matched"] for row in binding["result_contracts"]), "saved_result_contracts")
    require(all(a["closed_ns"] <= b["started_ns"] for a, b in zip(tools, tools[1:])), "sequential_tools")
    frames = [frame_cost(row) for row in observations["frames"]]
    require(len(frames) == len(observations["render_attempts"]) == 6, "six_actual_rasters")
    require([row["origin"] for row in frames] == ["product"] * 3 + ["native"] * 3, "actual_product_native_split")
    intents = [read(path) for path in sorted((EXTERNAL / "raster_budget").glob("attempt_*/INTENT.json"))]
    require([row["global_attempt"] for row in intents] == list(range(1, 7))
            and all(row["phase"] == "formal" for row in intents), "six_durable_intents_no_preparation")
    for intent, frame in zip(intents, frames):
        require(intent["attempt_id"] == frame["attempt_id"] and intent["view_name"] == frame["view_name"]
                and intent["origin"] == frame["origin"], "durable_intent_frame_binding")
    images = cli_images(consumer)
    require(len(images) == metrics["constructed_image_blocks"] == metrics["server_socket_sent_image_blocks"] == 3, "three_constructed_sent_CLI_images")
    require(sum(row["PNG_bytes"] for row in images) == metrics["constructed_PNG_bytes"] == metrics["server_socket_sent_PNG_bytes"], "three_image_byte_binding")
    require(sum(row["base64_chars"] for row in images) == metrics["constructed_base64_chars"], "base64_byte_binding")
    require(len(constructions["constructed"]) == 3 and not constructions["failed"] and not constructions["post_construction_failures"], "retained_image_construction_state")
    wire_files = []
    for row in consumer["MCP_wire_files"]:
        path = SLOT / "c" / row["path"]
        data = raw(path)
        require(len(data) == row["bytes"] and digest(data) == row["sha256"], "stdio_saved_wire_binding")
        wire_files.append({"path": str(path), "direction": path.stem, "bytes": len(data), "sha256": digest(data)})
    for direction in ("TX", "RX"):
        require(sum(row["bytes"] for row in wire_files if row["direction"] == direction) == consumer["MCP_stdio_" + direction + "_bytes"], "stdio_byte_sum")
    stdout, stderr = raw(SLOT / "c/stdout.raw.bin"), raw(SLOT / "c/stderr.raw.bin")
    require(len(stdout) == consumer["stdout_raw_bytes"] and digest(stdout) == consumer["stdout_raw_sha256"], "CLI_raw_stdout_binding")
    raw(SLOT / "c/events.jsonl")
    raw(HERE / "FORMAL_PROCESS_STDOUT.bin")
    raw(HERE / "FORMAL_PROCESS_STDERR.bin")
    replays = []
    for replay in observations["replays"]:
        data = raw(replay["path"])
        require(len(data) == replay["bytes"] and digest(data) == replay["sha256"], "copied_replay_binding")
        replays.append(dict(replay, elapsed_ns=replay["closed_ns"] - replay["started_ns"]))
    require(len(replays) == 1 and len(observations["active"]) == 1, "one_replay_one_product_call")
    raw(SLOT / "o/product_audit.jsonl")
    archives = {"outer": zip_receipt(result["originals"]["path"], result["originals"]["sha256"]),
                "consumer": zip_receipt(consumer["archive"]["archive"], consumer["archive"]["archive_sha256"])}
    require(archives["outer"]["members_sha256"] == result["originals"]["members_sha256"], "outer_archive_all_members")
    require(archives["consumer"]["members_sha256"] == consumer["archive"]["source_files_sha256"], "consumer_archive_all_members")
    external_archive = read(HERE / "EXTERNAL_ARCHIVE.json")
    for entry in external_archive["files"]:
        original, saved = raw(entry["original_path"]), raw(HERE / entry["archive_path"])
        require(original == saved and len(saved) == entry["bytes"] and digest(saved) == entry["sha256"], "external_archive_original_copy_binding")
    require(len(external_archive["files"]) == 196, "retained_external_file_count")
    tool_sum = sum(row["elapsed_ns"] for row in tools)
    receipt = tools[0]["CLI_completed_ns"]
    later_tools = tools[1:]
    CLI_end = consumer["process_exit_ns"]
    prompt = consumer["prompt_submitted_ns"]
    native_algorithm_tools = [row for row in tools if row["attempt"] in (4, 7)]
    product_frames = []
    for frame in product["frames"]:
        product_frames.append({"view_name": frame["view_name"], "stages": frame["stages"],
                               "feedback_stages": frame["feedback_stages"]})
    product_buffer = sum(row["four_buffer_payload_bytes"] for row in frames if row["origin"] == "product")
    native_buffer = sum(row["four_buffer_payload_bytes"] for row in frames if row["origin"] == "native")
    mapping_bytes = sum(row["mapping_metadata_payload_bytes"] for row in frames)
    array_bytes = product_buffer + native_buffer + mapping_bytes
    require(array_bytes == metrics["common"]["array_payload_bytes"], "all_frame_metric_byte_sum")
    require(product_buffer + mapping_bytes == product["work"]["array_payload_bytes"], "product_nine_array_metric_byte_sum")
    delivery = product_call["delivery_audit"]
    result = {
        "schema": "explicit-observation-saved-single-slot-cost-v1", "task": plan["task"],
        "quality_seal_sha256": SEAL_SHA256, "quality_sealed_files_verified": len(seal["inputs"]),
        "quality": {"task_complete": False, "correct_consumption": "fail", "final_artifact": "missing", "denominator": 1},
        "scope": "One failed explicit P diagnostic. Saved evidence only. No new comparison, provider request estimate or benefit ratio.",
        "configuration": {key: plan[key] for key in ("requested_model", "requested_reasoning_effort", "requested_service_tier", "authentication")},
        "execution": {"formal_CLI_sessions": 1, "user_turns": 1, "outer_retries": 0,
            "received_tool_attempts": 13, "admitted_business_attempts": 12, "tool_guard_rejections": 1,
            "rejected_attempt": 13, "rejected_Python_executed": False,
            "actual_rasters": 6, "product_rasters": 3, "native_rasters": 3, "preparation_rasters": 0,
            "product_calls": 1, "prepare_calls": product["work"]["prepare_calls"], "capture_replays": 1,
            "Blender_capture_calls": 0, "Blender_processes": 0,
            "constructed_PNG_blocks": 3, "server_sent_PNG_blocks": 3, "CLI_received_PNG_blocks": 3,
            "business_error_attempts": [row["attempt"] for row in tools if row["is_error"]],
            "provider_internal_requests": None},
        "time": {"saved_nested_intervals": clocks,
            "original_deadline_ns": route_clock["original_deadline_ns"], "deadline_seconds": 450,
            "route_closed_before_deadline": clocks["route"]["closed_ns"] < route_clock["original_deadline_ns"],
            "deadline_remaining_at_route_close_ns": route_clock["original_deadline_ns"] - clocks["route"]["closed_ns"],
            "failure_is_not_deadline_exhaustion": True, "route_accepted_success": route_clock["accepted_success"],
            "consumer_accepted_success": consumer_clock["accepted_success"],
            "parent_before_route_ns": clocks["route"]["started_ns"] - clocks["parent"]["started_ns"],
            "parent_after_route_ns": clocks["parent"]["closed_ns"] - clocks["route"]["closed_ns"],
            "route_before_consumer_ns": clocks["consumer"]["started_ns"] - clocks["route"]["started_ns"],
            "route_after_consumer_record_ns": clocks["route"]["closed_ns"] - clocks["consumer"]["closed_ns"],
            "CLI_clocks": {key: consumer[key] for key in ("started_ns", "popen_ns", "prompt_write_started_ns", "prompt_submitted_ns", "final_received_ns", "turn_completed_ns", "process_exit_ns", "cleanup_end_ns")},
            "final_received_ns_semantics": "This saved field is the last progress-message receipt, not a formal final answer.",
            "formal_final_received_ns": None, "turn_completed_ns": None,
            "prompt_to_process_exit_ns": CLI_end - prompt, "owner_tool_service_sum_ns": tool_sum,
            "prompt_to_process_exit_minus_owner_tools_ns": CLI_end - prompt - tool_sum,
            "residual_scope": "Contains model/provider service, transport, event handling and unseparated local work. It is not pure thinking time.",
            "consumer_post_exit_to_record_close_ns": clocks["consumer"]["closed_ns"] - CLI_end,
            "LAUNCH_TIMING_present": (FORMAL / "LAUNCH_TIMING.json").exists(),
            "LAUNCH_RESULT_present": (FORMAL / "LAUNCH_RESULT.json").exists(),
            "nesting": "Parent contains route, which contains consumer. Product stages, raster, publication and encoding are nested tool work. None is added to outer wall time."},
        "post_product_delivery": {"complete_product_bundle_CLI_received_ns": receipt,
            "prompt_to_first_product_bundle_ns": receipt - prompt,
            "receipt_to_process_exit_ns": CLI_end - receipt,
            "receipt_to_consumer_record_close_ns": clocks["consumer"]["closed_ns"] - receipt,
            "receipt_to_route_close_ns": clocks["route"]["closed_ns"] - receipt,
            "receipt_to_parent_close_ns": clocks["parent"]["closed_ns"] - receipt,
            "later_tool_attempts": [row["attempt"] for row in later_tools],
            "later_owner_tool_service_sum_ns": sum(row["elapsed_ns"] for row in later_tools),
            "receipt_to_process_exit_minus_later_owner_tools_ns": CLI_end - receipt - sum(row["elapsed_ns"] for row in later_tools),
            "global_discovery_and_geometric_pixel_recompute_tools": [row["attempt"] for row in native_algorithm_tools],
            "those_tools_inclusive_service_ns": sum(row["elapsed_ns"] for row in native_algorithm_tools),
            "native_raster_call_sum_ns": sum(row["original_raster_call_ns"] for row in frames if row["origin"] == "native"),
            "standalone_native_algorithm_CPU_ns": None, "earliest_task_sufficient_evidence_ns": None,
            "receipt_to_formal_final_ns": None,
            "scope": "The first full product delivery is observed. Later code explicitly rebuilds all components, maps triangles, recounts pixels and evaluates six-camera occlusion. Service clocks include wrappers, errors and file work. There is no completed final or independently clocked native-only algorithm phase."},
        "tools": tools, "frame_costs": frames, "durable_raster_intents": intents,
        "product": {"work_original": product["work"], "generation_work_original": product["generation_work"],
            "stages_original": product["stages"], "generation_stages_original": product["generation_stages"],
            "per_frame_stages": product_frames, "call_started_ns": product_call["started_ns"],
            "producer_returned_ns": product_call["producer_returned_ns"], "call_closed_ns": product_call["closed_ns"],
            "call_inclusive_ns": product_call["closed_ns"] - product_call["started_ns"],
            "delivery_audit_original": delivery,
            "delivery_read_sum_ns": sum(row["read_ns"] for row in delivery["frames"]),
            "delivery_validate_sum_ns": sum(row["validate_ns"] for row in delivery["frames"]),
            "delivery_base64_sum_ns": sum(row["base64_ns"] for row in delivery["frames"]),
            "PNG_NPZ_publication_sum_ns": sum(frame["stages"]["PNG_NPZ_publication"]["elapsed_ns"] for frame in product["frames"]),
            "standalone_PNG_encoding_ns": None, "standalone_NPZ_compression_ns": None,
            "stage_nesting": "prepare includes partition, index and world descriptions; result_lookup includes cold host observation; service_total includes capture/result_lookup. pixel_localization is inside readability. Product actual_raster stage encloses the ledger-wrapped original-raster clock. Separate PNG/NPZ CPU times are not clocked."},
        "replay_and_startup": {"replays": replays, "startup_stages_original": observations["stages"],
            "capture_replay_clock_scope": "ReplayHost deepcopy, exact-byte private-copy publication and receipt creation. It does not measure a live Blender capture.",
            "startup_scope": "Saved shared-input/runtime stage includes source loading, ordinary dependency imports, native mesh setup and P service construction; individual portions are not isolated."},
        "bytes": {"generated_PNG": sum(row["PNG_bytes"] for row in frames), "generated_NPZ": sum(row["NPZ_bytes"] for row in frames),
            "product_four_buffer_payload": product_buffer, "native_four_buffer_payload": native_buffer,
            "all_four_buffer_payload": product_buffer + native_buffer, "product_mapping_metadata_payload": mapping_bytes,
            "all_saved_NPZ_array_payload": array_bytes,
            "owner_metric_array_payload_original": metrics["common"]["array_payload_bytes"],
            "product_work_array_payload_original": product["work"]["array_payload_bytes"],
            "product_geometry_array_payload_original": product["work"]["geometry_array_payload_bytes"],
            "array_scope": "Each product frame persists nine arrays, the four raster buffers plus five mapping arrays. Native frames persist four arrays. The common metric equals these saved payloads, not geometry payload or peak memory. Repeated mapping values are counted per saved NPZ.",
            "CLI_PNG": sum(row["PNG_bytes"] for row in images), "CLI_base64_chars": sum(row["base64_chars"] for row in images),
            "CLI_image_block_JSON": sum(row["image_block_JSON_bytes"] for row in images),
            "stdio_TX": consumer["MCP_stdio_TX_bytes"], "stdio_RX": consumer["MCP_stdio_RX_bytes"],
            "tool_request_files": sum(row["request_file_bytes"] for row in tools), "tool_response_files": sum(row["response_file_bytes"] for row in tools),
            "CLI_stdout_raw": len(stdout), "CLI_stderr_raw": len(stderr),
            "prompt_text": consumer["input_text_bytes"], "agent_public_text": consumer["public_text_bytes"],
            "last_agent_message_text_legacy_output_field": consumer["output_text_bytes"],
            "source_capture_copy": sum(row["bytes"] for row in replays),
            "scope": "PNG, NPZ, raw arrays, base64, JSON, stdout and ZIP are nested/repeated representations, not independently additive network or memory consumption."},
        "CLI_images": images, "construction_receipts": constructions,
        "actor_metrics_original": {key: value for key, value in metrics.items() if key not in ("tools", "common")},
        "actor_common_metrics_original": metrics["common"], "transport_records_original": transports, "stdio_wire_files": wire_files,
        "usage": {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None,
            "raw_usage_events": consumer["raw_usage_events"], "usage_rows": consumer["usage_rows"],
            "reported_usage": consumer["usage"], "usage_semantics": consumer["usage_semantics"],
            "usage_aggregation": consumer["usage_aggregation"],
            "interrupted_stream_usage_coverage": consumer["summary"].get("interrupted_stream_usage_coverage"),
            "provider_retry_observations": consumer["provider_retry_observations"],
            "provider_requests": None, "image_tokens": None, "cash_fees": None,
            "scope": "The consumer aborted without a terminal usage event. Missing usage is unknown, not zero; no token or provider-request extrapolation is made. Cached input is a subset when available."},
        "lifecycle": {"CLI_exit_code": consumer["exit_code"], "owner_exit_code": result["owner_process_cleanup"]["exit_code"],
            "launcher_exit_code": parent["exit_code"], "CLI_cleanup": result["consumer_process_cleanup"],
            "owner_cleanup": result["owner_process_cleanup"], "thin_held_exit": result["runtime_exit"],
            "thin_EXIT_receipt": result["bridge_cleanup"], "runtime_binding": runtime_binding,
            "consumer_errors": consumer["errors"], "post_route_launcher_failure": "entry_pointer_chain_changed_during_single_slot",
            "scope": "CLI exited 1, owner 0, launcher 1. A retained handle confirms thin exit 0 and closure, while its EXIT/EOF receipt remains unknown. These failed and unknown states are preserved."},
        "archives": archives,
        "external_archive": {key: value for key, value in external_archive.items() if key != "files"},
        "unknowns": {"peak_RSS": None, "total_Python_NumPy_temporaries": None,
            "retained_cache_and_warm_state_bytes": None, "standalone_native_index_CPU_ns": None,
            "provider_internal_requests": None, "provider_resolved_model_effort_tier": None,
            "earliest_task_sufficient_evidence_ns": None, "total_authoring_and_root_review_cost": None,
            "cache_note": "The saved first product work reports result_cache_hit=false and frame_reuses=0. It does not measure warm reuse or total retained state. Named localization temporary bytes/new_cached_array_bytes are retained per frame with their restricted original scope."},
        "audit_operations": {"new_models": 0, "new_product_calls": 0, "new_rasters": 0, "new_tests": 0,
            "saved_npz_inspection": "Standard-library NPY headers and payload hashes. Unicode dtype widths are measured at four bytes per element character.",
            "source_script_sha256": digest(raw(__file__))}}
    verify_seal()
    result["inputs_sha256"] = dict(sorted(INPUTS.items()))
    return result


def markdown(report):
    clocks = report["time"]["saved_nested_intervals"]
    later = report["post_product_delivery"]
    byte = report["bytes"]
    lines = ["# 显式观察单槽成本审计", "", "本槽失败结果已封存。实际产品调用及三图交付成功，正式最终答缺失，正确消费资格未通过。以下原值来自已保存记录。", "",
             "| 时界 | 秒 |", "| --- | ---: |"]
    for name, label in (("parent", "父进程"), ("route", "单槽route"), ("consumer", "消费者含收尾")):
        lines.append(f"| {label} | {clocks[name]['elapsed_ns']/1e9:.7f} |")
    lines.extend(["", "这三个时界逐层包含。原绝对期限450秒，本槽因工具窗口结束，没有耗尽该期限。launcher末尾异常导致exit1，LAUNCH_TIMING与LAUNCH_RESULT均缺失，父进程已保存时界覆盖其返回。", "",
        f"实际收到13次工具请求，其中12次进入业务入口，第13次被守卫拒绝。6次真实raster包含产品3次与原生3次，准备为0。捕获重放1次，产品调用/prepare各1次，Blender采集与进程均为0。3个PNG块实际构造、发送并在CLI完成回执中验证。", "",
        f"首个完整产品回执在提交题面后{later['prompt_to_first_product_bundle_ns']/1e9:.7f}秒收到。之后至CLI退出又经过{later['receipt_to_process_exit_ns']/1e9:.7f}秒，后续工具服务累计{later['later_owner_tool_service_sum_ns']/1e9:.7f}秒。可见代码重建全部面、像素归属和六视角遮挡，工具4与7的包容服务时长共{later['those_tools_inclusive_service_ns']/1e9:.7f}秒。工具外区间包含模型服务、传输与本地处理，无法归为纯思考。", "",
        f"累计工具服务{report['time']['owner_tool_service_sum_ns']/1e9:.7f}秒，其中第一次产品工具为{report['tools'][0]['elapsed_ns']/1e9:.7f}秒。产品prepare、index、分区、渲染、读回、像素反馈、状态提交及base64时界保留原记录，存在嵌套。PNG与NPZ联合发布有计时，二者各自编码CPU时间未测。", "",
        f"生成PNG共{byte['generated_PNG']}字节，NPZ共{byte['generated_NPZ']}字节。六帧四个buffer累计{byte['all_four_buffer_payload']}字节，产品另外五项映射数组累计{byte['product_mapping_metadata_payload']}字节。两者合计{byte['all_saved_NPZ_array_payload']}字节，精确对应owner metric；产品三份九数组共{byte['product_work_array_payload_original']}字节，几何载荷{byte['product_geometry_array_payload_original']}字节单列。此数值不等于峰值内存或缓存总量。", "",
        f"实际交付PNG为{byte['CLI_PNG']}字节、base64为{byte['CLI_base64_chars']}字符、图片JSON为{byte['CLI_image_block_JSON']}字节。stdio TX/RX为{byte['stdio_TX']}/{byte['stdio_RX']}字节。捕获原字节复制{byte['source_capture_copy']}字节。PNG、数组、JSON、stdout及ZIP有重复和嵌套，各层分别保留。", "",
        "CLI没有terminal usage事件，input、output、cached input、图像token、现金费用及provider内部请求均为unknown。一个消费者会话没有被换算成provider请求数。", "",
        "CLI exit1、owner exit0、launcher exit1。thin由持有句柄确认exit0且关闭，但EXIT回执仍缺失，正常EOF未证明。最后进度消息的时间字段final_received_ns没有被当成正式最终答时刻。", "",
        f"质量封存的{report['quality_sealed_files_verified']}份文件在成本审计前后均核对原SHA，外部196份原件与归档副本逐字节一致。没有新模型、产品、测试、渲染或计时采样。完整原值、输入SHA及未知项见COST.json。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    report = build()
    with (HERE / "COST.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with (HERE / "COST.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write(markdown(report))
    print(json.dumps({"quality_complete": False, "received_tools": 13, "rasters": 6,
                      "parent_ns": report["time"]["saved_nested_intervals"]["parent"]["elapsed_ns"],
                      "usage": None, "inputs": len(report["inputs_sha256"])}))
