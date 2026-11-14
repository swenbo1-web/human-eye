"""Saved-only accounting for the single consumable-observation result."""

import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

HERE = Path(__file__).resolve().parent
EXTERNAL = Path("D:/he_consume_001")
FORMAL = EXTERNAL / "formal"
SLOT = FORMAL / "P1"
SEAL_SHA256 = "510a7817f754c883d86082c4dabf54a84cfea516d53502839640b6b2645d4977"
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
    launch = read(FORMAL / "LAUNCH_TIMING.json")
    launch_result = read(FORMAL / "LAUNCH_RESULT.json")
    run = read(FORMAL / "RUN_RESULT.json")
    route = read(SLOT / "RESULT.json")
    route_time = read(SLOT / "FINAL_TIMING.json")
    consumer = read(SLOT / "c/CONSUMER.json")
    consumer_time = read(SLOT / "c/FINAL_TIMING.json")
    metrics = read(SLOT / "o/METRICS.json")
    observations = read(SLOT / "o/OBSERVATIONS.json")
    product = read(SLOT / "o/product_call_01/SERVICE_RESULT.json")
    product_call = read(SLOT / "o/product_call_01/CALL.json")
    constructions = read(SLOT / "o/IMAGE_CONSTRUCTIONS.json")
    transports = read(SLOT / "o/TRANSPORT.json")
    contracts = read(SLOT / "c/BUSINESS_SOURCE_BINDING.json")
    runtime_binding = read(SLOT / "c/RUNTIME_BINDING.json")
    preparation = read(HERE / "PREPARATION_QUALIFICATION.json")
    plan = read(HERE / "PLAN.json")
    frozen = read(HERE / "FROZEN.json")
    read(HERE / "inputs/SOURCES.json")
    read(SLOT / "o/CLOSE.json")
    require(len(frozen["files_sha256"]) == 1746, "accepted_1746_source_closure")
    for path, wanted in frozen["files_sha256"].items():
        require(digest(raw(path)) == wanted, "frozen_execution_source_changed")
    require(parent["exit_code"] == 0 and launch_result["launcher_succeeded"], "actual_launcher_completion")
    require(consumer["valid_completion"] and route_time["accepted_success"], "actual_completed_route")
    require(seal["requirements"]["direct_consumption_efficiency"] == "fail", "retain_efficiency_failure")
    require((SLOT / "c/PUBLIC_FINAL.txt").exists(), "actual_final_artifact")
    raw(SLOT / "c/PUBLIC_FINAL.txt")
    clocks = {"parent": interval(parent),
              "launch": interval(launch, end="launch_results_closed_ns"),
              "route": interval(route_time, end="result_closed_ns"),
              "consumer": interval(consumer_time, end="consumer_record_closed_ns", elapsed="full_turn_wall_ns")}
    require(clocks["parent"]["started_ns"] <= clocks["launch"]["started_ns"] <= clocks["route"]["started_ns"]
            <= clocks["consumer"]["started_ns"] <= clocks["consumer"]["closed_ns"] <= clocks["route"]["closed_ns"]
            <= clocks["launch"]["closed_ns"] <= clocks["parent"]["closed_ns"], "four_nested_clock_order")
    require(route_time["original_deadline_ns"] == clocks["route"]["started_ns"] + 450_000_000_000,
            "original_450_second_absolute_deadline")
    tools = []
    for row, call in zip(metrics["tools"], consumer["tool_calls"]):
        number = row["attempt"]
        folder = SLOT / "o" / f"tool_{number:02}"
        request, response = read(folder / "REQUEST.json"), read(folder / "RESPONSE.json")
        require(call["item"]["tool"] == request["params"]["name"] == row["name"], "tool_request_binding")
        require(call["item"]["result"]["content"] == response["result"]["content"], "tool_result_content_binding")
        tools.append({"attempt": number, "name": row["name"], **interval(row),
            "CLI_completed_ns": call["perf_ns"], "is_error": row["is_error"], "error": row["error"],
            "content_metrics": row["content_metrics"], "compact_response_bytes": row["response_bytes"],
            "request_file_bytes": (folder / "REQUEST.json").stat().st_size,
            "response_file_bytes": (folder / "RESPONSE.json").stat().st_size,
            "request_sha256": INPUTS[str((folder / "REQUEST.json").resolve())],
            "response_sha256": INPUTS[str((folder / "RESPONSE.json").resolve())]})
    require(len(tools) == len(metrics["tools"]) == len(consumer["tool_calls"]) == 7, "seven_business_attempts")
    require([row["attempt"] for row in tools] == list(range(1, 8)), "tool_attempt_sequence")
    require([row["attempt"] for row in tools if row["is_error"]] == [5], "preserve_one_recovered_ValueError")
    require(not contracts["binding_errors"] and len(contracts["result_contracts"]) == 7
            and all(row["matched"] for row in contracts["result_contracts"]), "saved_result_contracts")
    require(all(a["closed_ns"] <= b["started_ns"] for a, b in zip(tools, tools[1:])), "sequential_tool_windows")
    frames = [frame_cost(frame) for frame in observations["frames"]]
    require(len(frames) == len(observations["render_attempts"]) == 4, "four_actual_rasters")
    require([(frame["origin"], frame["view_name"]) for frame in frames]
            == [("product", "SCENE"), ("product", "BACK"), ("product", "LEFT"), ("native", "SCENE")],
            "actual_three_product_one_duplicate_SCENE")
    require(frames[3]["PNG_sha256"] == frames[0]["PNG_sha256"], "duplicate_SCENE_image_identity")
    intents = [read(path) for path in sorted((EXTERNAL / "raster_budget").glob("attempt_*/INTENT.json"))]
    require([row["global_attempt"] for row in intents] == list(range(1, 5))
            and all(row["phase"] == "formal" for row in intents), "four_durable_intents")
    for intent, frame in zip(intents, frames):
        require(intent["attempt_id"] == frame["attempt_id"] and intent["view_name"] == frame["view_name"]
                and intent["origin"] == frame["origin"], "intent_frame_binding")
    images = cli_images(consumer)
    require(len(images) == metrics["constructed_image_blocks"] == metrics["server_socket_sent_image_blocks"] == 4,
            "four_constructed_sent_received_images")
    require(sum(row["PNG_bytes"] for row in images) == metrics["constructed_PNG_bytes"]
            == metrics["server_socket_sent_PNG_bytes"], "four_image_byte_binding")
    require(not constructions["failed"] and not constructions["post_construction_failures"], "image_failure_state")
    wire = []
    for row in consumer["MCP_wire_files"]:
        path = SLOT / "c" / row["path"]
        data = raw(path)
        require(digest(data) == row["sha256"] and len(data) == row["bytes"], "stdio_byte_identity")
        wire.append({"path": str(path), "direction": path.stem, "bytes": len(data), "sha256": digest(data)})
    for direction in ("TX", "RX"):
        require(sum(row["bytes"] for row in wire if row["direction"] == direction)
                == consumer["MCP_stdio_" + direction + "_bytes"], "stdio_byte_sum")
    stdout, stderr = raw(SLOT / "c/stdout.raw.bin"), raw(SLOT / "c/stderr.raw.bin")
    require(len(stdout) == consumer["stdout_raw_bytes"] and digest(stdout) == consumer["stdout_raw_sha256"],
            "raw_CLI_stdout_identity")
    raw(SLOT / "c/events.jsonl")
    raw(HERE / "FORMAL_PROCESS_STDOUT.bin")
    raw(HERE / "FORMAL_PROCESS_STDERR.bin")
    raw(SLOT / "o/product_audit.jsonl")
    replays = []
    for replay in observations["replays"]:
        data = raw(replay["path"])
        require(digest(data) == replay["sha256"] and len(data) == replay["bytes"], "replay_copy_bytes")
        replays.append(dict(replay, elapsed_ns=replay["closed_ns"] - replay["started_ns"]))
    require(len(replays) == len(observations["active"]) == 1, "one_product_one_replay")
    archives = {"outer": zip_receipt(route["originals"]["path"], route["originals"]["sha256"]),
                "consumer": zip_receipt(consumer["archive"]["archive"], consumer["archive"]["archive_sha256"])}
    require(archives["outer"]["members_sha256"] == route["originals"]["members_sha256"], "outer_ZIP_members")
    require(archives["consumer"]["members_sha256"] == consumer["archive"]["source_files_sha256"], "consumer_ZIP_members")
    external = read(HERE / "EXTERNAL_ARCHIVE.json")
    for row in external["files"]:
        original, saved = raw(row["original_path"]), raw(HERE / row["archive_path"])
        require(original == saved and len(saved) == row["bytes"] and digest(saved) == row["sha256"], "external_archive_pair")
    require(len(external["files"]) == 289, "external_289_files")
    first_response = read(SLOT / "o/tool_01/RESPONSE.json")
    text = first_response["result"]["content"][0]["text"]
    text_bytes = len(text.encode("utf8"))
    require(text_bytes == product_call["delivery_audit"]["public_text_bytes"]
            == preparation["public_text_UTF8_bytes"], "actual_public_JSON_bytes")
    require(text_bytes - preparation["same_state_legacy_v3_UTF8_bytes"]
            == preparation["public_text_added_UTF8_bytes"] == 2824, "same_state_v3_byte_delta")
    require(len(consumer["raw_usage_events"]) == len(consumer["usage_rows"]) == 1, "one_saved_usage_event")
    usage = consumer["usage"]
    require(usage == consumer["raw_usage_events"][0] == consumer["usage_rows"][0], "usage_original_binding")
    require(0 <= usage["cached_input_tokens"] <= usage["input_tokens"]
            and 0 <= usage["reasoning_output_tokens"] <= usage["output_tokens"], "usage_subset_semantics")
    service_sum = sum(row["elapsed_ns"] for row in tools)
    first_bundle = tools[0]["CLI_completed_ns"]
    prompt, final, process_exit = (consumer[key] for key in ("prompt_submitted_ns", "final_received_ns", "process_exit_ns"))
    delivery = product_call["delivery_audit"]
    product_four = sum(row["four_buffer_payload_bytes"] for row in frames if row["origin"] == "product")
    native_four = sum(row["four_buffer_payload_bytes"] for row in frames if row["origin"] == "native")
    mapping_bytes = sum(row["mapping_metadata_payload_bytes"] for row in frames)
    require(product_four + native_four + mapping_bytes == metrics["common"]["array_payload_bytes"], "array_payload_metric")
    body = {
        "schema": "consumable-observation-saved-single-slot-cost-v1", "task": plan["task"],
        "quality_seal_sha256": SEAL_SHA256, "quality_sealed_files_verified": len(seal["inputs"]),
        "quality": {"task_complete": True, "requirements": seal["requirements"],
                    "overall_consumption_mechanism_qualified": False, "denominator": 1},
        "scope": "One completed explicit-consumption slot with efficiency failure. No old/new task ratio or benefit calculation.",
        "source": {"frozen_file_count": len(frozen["files_sha256"]), "all_1746_hashes_rechecked": True,
                   "product_source_sha256": product_call["product_source_sha256"],
                   "candidate_source_Git": preparation["candidate_source_git"]},
        "configuration": {key: plan[key] for key in ("requested_model", "requested_reasoning_effort", "requested_service_tier", "authentication")},
        "counts": {"formal_CLI_sessions": 1, "user_turns": 1, "outer_retries": 0,
                   "received_tools": 7, "admitted_business_tools": 7, "tool_guard_rejections": 0,
                   "actual_rasters": 4, "product_rasters": 3, "native_duplicate_SCENE_rasters": 1,
                   "preparation_rasters": 0, "product_calls": 1, "prepare_calls": product["work"]["prepare_calls"],
                   "capture_replays": 1, "Blender_capture_calls": 0, "Blender_processes": 0,
                   "constructed_image_blocks": 4, "socket_sent_image_blocks": 4, "CLI_received_image_blocks": 4,
                   "ordinary_error_attempts": [5], "recovery_attempts": [6], "provider_requests": None},
        "time": {"saved_nested_intervals": clocks,
            "launch_route_call_wrapper": {"started_ns": launch["route_started_ns"], "closed_ns": launch["route_closed_ns"],
                                          "elapsed_ns": launch["route_elapsed_ns"]},
            "wrapper_minus_original_route_ns": launch["route_elapsed_ns"] - clocks["route"]["elapsed_ns"],
            "original_deadline_ns": route_time["original_deadline_ns"], "deadline_seconds": 450,
            "deadline_remaining_at_route_close_ns": route_time["original_deadline_ns"] - clocks["route"]["closed_ns"],
            "parent_before_launch_ns": clocks["launch"]["started_ns"] - clocks["parent"]["started_ns"],
            "parent_after_launch_ns": clocks["parent"]["closed_ns"] - clocks["launch"]["closed_ns"],
            "launch_before_route_ns": clocks["route"]["started_ns"] - clocks["launch"]["started_ns"],
            "launch_after_route_ns": clocks["launch"]["closed_ns"] - clocks["route"]["closed_ns"],
            "CLI_clocks": {key: consumer[key] for key in ("started_ns", "popen_ns", "prompt_write_started_ns", "prompt_submitted_ns", "final_received_ns", "turn_completed_ns", "process_exit_ns", "cleanup_end_ns")},
            "owner_tool_service_sum_ns": service_sum, "prompt_to_final_ns": final - prompt,
            "prompt_to_final_minus_owner_tools_ns": final - prompt - service_sum,
            "turn_completed_to_process_exit_ns": process_exit - consumer["turn_completed_ns"],
            "post_exit_to_consumer_record_close_ns": clocks["consumer"]["closed_ns"] - process_exit,
            "residual_scope": "Model/provider service, transport, event handling and unseparated local work. No pure-thinking attribution.",
            "nesting": "Parent contains launch, route and consumer. Wrapper route elapsed surrounds the original route clock. Tool/product/raster/encode stages are included and never added to outer wall time."},
        "public_JSON_and_reuse": {"actual_UTF8_bytes": text_bytes, "actual_text_sha256": digest(text.encode("utf8")),
            "recorded_same_state_v3_UTF8_bytes": preparation["same_state_legacy_v3_UTF8_bytes"],
            "added_UTF8_bytes": text_bytes - preparation["same_state_legacy_v3_UTF8_bytes"],
            "byte_comparison_scope": "Actual v4 byte count checked against the preserved same-state offline v3 qualification. No new projection or timing trial.",
            "namespace_publication": "Original public text object assigned after successful socket send; no additional public JSON serialization.",
            "namespace_independent_runtime_dump_or_hash": None, "namespace_assignment_CPU_ns": None,
            "tool2_parse_and_inspection_ns": tools[1]["elapsed_ns"], "tool3_existing_JSON_query_ns": tools[2]["elapsed_ns"],
            "json_loads_only_CPU_ns": None,
            "query_scope": "Tool2 parses last_observation_json then prints keys, image/observation tables, all cameras and input summaries. Tool3 converts existing rows to dictionaries and prints targets/remaining reasons. Neither interval isolates JSON parsing alone."},
        "post_first_product_delivery": {"CLI_received_ns": first_bundle,
            "prompt_to_product_bundle_ns": first_bundle - prompt,
            "receipt_to_final_ns": final - first_bundle, "receipt_to_CLI_exit_ns": process_exit - first_bundle,
            "later_tool_service_sum_ns": sum(row["elapsed_ns"] for row in tools[1:]),
            "receipt_to_final_minus_later_owner_tools_ns": final - first_bundle - sum(row["elapsed_ns"] for row in tools[1:]),
            "earliest_task_sufficient_evidence_ns": None},
        "duplicate_and_verification": {"duplicate_SCENE_tool4_ns": tools[3]["elapsed_ns"],
            "duplicate_original_raster_call_ns": frames[3]["original_raster_call_ns"],
            "failed_identity_mapping_tool5_ns": tools[4]["elapsed_ns"],
            "recovered_product_region_guided_fullmesh_mapping_tool6_ns": tools[5]["elapsed_ns"],
            "whole_SCENE_pixel_boundary_verification_and_table_tool7_ns": tools[6]["elapsed_ns"],
            "all_three_identity_and_pixel_verification_tools_ns": sum(row["elapsed_ns"] for row in tools[4:]),
            "scope": "The model uses existing product regions to map source faces and verifies one SCENE full frame. It does not rediscover all regions or recompute six-view geometric occlusion. Duplicate SCENE remains the sealed efficiency failure."},
        "product": {"work_original": product["work"], "generation_work_original": product["generation_work"],
            "stages_original": product["stages"], "generation_stages_original": product["generation_stages"],
            "scope_and_facts_ns": product["stages"]["scope_and_facts"]["elapsed_ns"],
            "scope_and_facts_scope": "Whole existing scope/short-facts stage, including the new inspection/witness fields. It is not an isolated incremental-field timing.",
            "per_frame_stages": [{"view_name": frame["view_name"], "stages": frame["stages"], "feedback_stages": frame["feedback_stages"]} for frame in product["frames"]],
            "delivery_audit_original": delivery,
            "MCP_projection_serialization_and_image_envelope_ns": delivery["elapsed_ns"],
            "standalone_public_projection_CPU_ns": None, "standalone_public_JSON_serialization_CPU_ns": None,
            "image_read_sum_ns": sum(row["read_ns"] for row in delivery["frames"]),
            "image_validate_sum_ns": sum(row["validate_ns"] for row in delivery["frames"]),
            "image_base64_sum_ns": sum(row["base64_ns"] for row in delivery["frames"]),
            "PNG_NPZ_publication_sum_ns": sum(frame["stages"]["PNG_NPZ_publication"]["elapsed_ns"] for frame in product["frames"]),
            "standalone_PNG_encoding_CPU_ns": None, "standalone_NPZ_compression_CPU_ns": None,
            "nesting": "prepare includes partition/index/world descriptions; result_lookup contains cold observation. Readability includes pixel_localization. MCP envelope includes projection/serialization and image read/validate/base64. No nested stage sums are called total independent work."},
        "tools": tools, "frames": frames, "durable_raster_intents": intents,
        "startup_and_replay": {"startup_stages_original": observations["stages"], "replays": replays,
            "scope": "Startup combines input/dependency/native setup and service construction. Replay is current saved-capture deepcopy and byte-copy publication, not Blender acquisition."},
        "bytes": {"generated_PNG": sum(frame["PNG_bytes"] for frame in frames), "generated_NPZ": sum(frame["NPZ_bytes"] for frame in frames),
            "product_four_buffer_payload": product_four, "native_four_buffer_payload": native_four,
            "all_four_buffer_payload": product_four + native_four, "product_mapping_metadata_payload": mapping_bytes,
            "all_saved_NPZ_array_payload": product_four + native_four + mapping_bytes,
            "owner_metric_array_payload_original": metrics["common"]["array_payload_bytes"],
            "product_work_array_payload_original": product["work"]["array_payload_bytes"],
            "product_geometry_array_payload_original": product["work"]["geometry_array_payload_bytes"],
            "CLI_PNG": sum(row["PNG_bytes"] for row in images), "CLI_base64_chars": sum(row["base64_chars"] for row in images),
            "CLI_image_block_JSON": sum(row["image_block_JSON_bytes"] for row in images),
            "stdio_TX": consumer["MCP_stdio_TX_bytes"], "stdio_RX": consumer["MCP_stdio_RX_bytes"],
            "tool_request_files": sum(row["request_file_bytes"] for row in tools), "tool_response_files": sum(row["response_file_bytes"] for row in tools),
            "CLI_stdout_raw": len(stdout), "CLI_stderr_raw": len(stderr), "prompt_text": consumer["input_text_bytes"],
            "agent_public_text": consumer["public_text_bytes"], "final_text": consumer["output_text_bytes"],
            "capture_copy": sum(row["bytes"] for row in replays),
            "scope": "Saved array payloads are cumulative, with five mapping arrays counted per product NPZ. Geometry bytes are separate. PNG/base64/JSON/stdout/ZIP are nested representations, not additive network or memory allocation."},
        "CLI_images": images, "image_constructions": constructions,
        "actor_metrics_original": {key: value for key, value in metrics.items() if key not in ("tools", "common")},
        "actor_common_metrics_original": metrics["common"], "transport_records_original": transports, "stdio_wire_files": wire,
        "usage": {"reported": usage, "raw_usage_events": consumer["raw_usage_events"], "usage_rows": consumer["usage_rows"],
            "reported_input_plus_output": usage["input_tokens"] + usage["output_tokens"],
            "reported_uncached_input": usage["input_tokens"] - usage["cached_input_tokens"],
            "scope": consumer["usage_semantics"], "aggregation": consumer["usage_aggregation"],
            "subset_rule": "Cached input is included in input; reasoning output is included in output. Neither is added again.",
            "raw_event_count": len(consumer["raw_usage_events"]), "provider_request_count": None,
            "image_tokens": consumer.get("image_tokens"), "cash_fees": consumer.get("fees"),
            "provider_observation_records_original": consumer["provider_retry_observations"],
            "metadata_warning_scope": "The saved unknown-model fallback-metadata warning is retained. It does not establish a provider retry or resolved provider model change."},
        "lifecycle": {"CLI_exit_code": consumer["exit_code"], "actor_exit_code": route["owner_process_cleanup"]["exit_code"],
            "launcher_exit_code": parent["exit_code"], "CLI_cleanup": route["consumer_process_cleanup"],
            "actor_cleanup": route["owner_process_cleanup"], "thin_held_exit": route["runtime_exit"],
            "thin_EXIT_receipt": route["bridge_cleanup"], "runtime_binding": runtime_binding,
            "launch_terminal_errors": launch["terminal_errors"], "launch_publication_errors": launch["publication_errors"],
            "scope": "CLI/actor/launcher exited 0. Thin held handle confirms exit 1 and closure, while EXIT/EOF receipt is missing/unknown. Those separate states are preserved."},
        "archives": archives, "external_archive": {key: value for key, value in external.items() if key != "files"},
        "unknowns": {"provider_internal_requests": None, "provider_resolved_model_effort_tier": None,
            "peak_RSS": None, "total_Python_NumPy_temporaries": None, "retained_warm_cache_bytes": None,
            "namespace_independent_runtime_dump_or_hash": None, "json_loads_only_CPU_ns": None,
            "namespace_assignment_CPU_ns": None, "first_task_sufficient_evidence_ns": None,
            "total_authoring_and_root_review_cost": None,
            "cache_scope": "Saved cold work reports result_cache_hit=false and frame_reuses=0. No warm request or total cache footprint was measured. Named pixel-localization temporary arrays have only their original restricted scope."},
        "audit_operations": {"new_models": 0, "new_product_calls": 0, "new_rasters": 0, "new_tests": 0,
            "new_timing_samples": 0, "source_script_sha256": digest(raw(__file__)),
            "saved_arrays": "Standard-library NPY headers/payload hashes, including Unicode mapping dtype width; no product or renderer import."}}
    verify_seal()
    body["inputs_sha256"] = dict(sorted(INPUTS.items()))
    return body


def markdown(report):
    clocks = report["time"]["saved_nested_intervals"]
    reuse, verify, usage = (report[key] for key in ("public_JSON_and_reuse", "duplicate_and_verification", "usage"))
    lines = ["# 可直接消费观察单槽成本", "", "原任务质量与产品事实采用通过，消费效率因重复SCENE失败，整体机制未通过。此处只列当前单槽已保存原值。", "",
             "| 嵌套时界 | 秒 |", "| --- | ---: |"]
    for key in ("parent", "launch", "route", "consumer"):
        lines.append(f"| {key} | {clocks[key]['elapsed_ns']/1e9:.7f} |")
    lines.extend(["", f"launcher的route调用包容时界为{report['time']['launch_route_call_wrapper']['elapsed_ns']/1e9:.7f}秒，与原route记录相差{report['time']['wrapper_minus_original_route_ns']}纳秒，口径分别保留。这四层和产品/工具子阶段均存在嵌套，不叠加为总耗时。", "",
        "实际7次工具请求均进入业务入口，没有guard拒绝。4次raster为产品3次和重复原生SCENE1次，4个PNG块实际构造、发送并到达CLI。重放1次、产品与prepare各1次，准备raster及Blender采集为0。", "",
        f"实际公开v4 JSON为{reuse['actual_UTF8_bytes']}字节，同状态已保存v3为{reuse['recorded_same_state_v3_UTF8_bytes']}字节，增加{reuse['added_UTF8_bytes']}字节。桥接仅绑定同一字符串，独立赋值CPU时间和实际namespace独立dump/hash未测。tool2包含json.loads及打印，包容时长{reuse['tool2_parse_and_inspection_ns']/1e9:.7f}秒；tool3已有JSON查询为{reuse['tool3_existing_JSON_query_ns']/1e9:.7f}秒，均没有被标成纯解析CPU。", "",
        f"重复SCENE的tool4为{verify['duplicate_SCENE_tool4_ns']/1e9:.7f}秒。tool5转换错误{verify['failed_identity_mapping_tool5_ns']/1e9:.7f}秒，tool6恢复后的已有region引导全网格身份核对{verify['recovered_product_region_guided_fullmesh_mapping_tool6_ns']/1e9:.7f}秒，tool7整幅SCENE像素/边界验证与表格输出{verify['whole_SCENE_pixel_boundary_verification_and_table_tool7_ns']/1e9:.7f}秒。本次没有重新发现所有区域或重算六相机遮挡。", "",
        f"产品scope_and_facts阶段为{report['product']['scope_and_facts_ns']/1e9:.7f}秒。MCP投影、公开序列化及图片处理的包容阶段为{report['product']['MCP_projection_serialization_and_image_envelope_ns']/1e9:.7f}秒；各自独立CPU未测。prepare/index、缓存标记、光栅、联合PNG/NPZ发布、图片read/validate/base64与像素反馈均保留原时界。", "",
        f"CLI原始usage记录input {usage['reported']['input_tokens']}、cached input {usage['reported']['cached_input_tokens']}、output {usage['reported']['output_tokens']}、reasoning output {usage['reported']['reasoning_output_tokens']}、cache write {usage['reported']['cache_write_input_tokens']}。cached和reasoning分别是input/output子集，未重复相加。仅一条usage事件不等于一次provider请求，turn/session聚合范围仍未确认。图像token、现金费用与provider内部请求未测。", "",
        "CLI、actor、launcher均exit0。thin持有句柄确认exit1并关闭，EXIT/正常EOF回执仍未知。未知模型metadata回退警告原样保留，未据此推断provider切换或重试。", "",
        f"1746份冻结来源、{report['quality_sealed_files_verified']}份质量文件及289份归档原件/副本已复核。无新模型、产品、测试、光栅或时钟采样，没有使用旧失败任务作收益分母。数组、PNG、base64、JSON、stdio和ZIP逐层列在COST.json，峰值内存与缓存总量保持未知。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    report = build()
    with (HERE / "COST.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with (HERE / "COST.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write(markdown(report))
    print(json.dumps({"tools": 7, "rasters": 4, "quality": report["quality"],
                      "parent_ns": report["time"]["saved_nested_intervals"]["parent"]["elapsed_ns"],
                      "inputs": len(report["inputs_sha256"])}))
