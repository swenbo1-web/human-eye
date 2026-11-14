"""Account for the six sealed routed-task runs using saved bytes and clocks only."""

import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import statistics
import struct
import zipfile


HERE = Path(__file__).resolve().parent
EXTERNAL = Path("D:/he_routed_001")
FORMAL = EXTERNAL / "formal"
SEAL_SHA256 = "989b117db6f45f82998a1eb51de984cd7f7dd0aa4101cc136e9f4bbd631dd530"
PRODUCT_SHA256 = "6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f"
ORDER = ("N1", "P1", "P2", "N2", "N3", "P3")
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


def interval(value, end="closed_ns", elapsed="elapsed_ns"):
    start, finish = value["started_ns"], value[end]
    require(type(start) is int and type(finish) is int and finish >= start, "saved_clock_order")
    require(value[elapsed] == finish - start, "saved_clock_difference")
    return {"started_ns": start, "closed_ns": finish, "elapsed_ns": finish - start,
            "scope": value.get("scope")}


def verify_quality():
    require(digest(raw(HERE / "QUALITY_SEAL.json")) == SEAL_SHA256, "sealed_quality_identity")
    seal = read(HERE / "QUALITY_SEAL.json")
    require(seal["cost_analysis_unlocked_after_this_seal"] and seal["quality_gate_passed"], "quality_before_cost")
    require(len(seal["inputs"]) == 24, "quality_24_file_denominator")
    for row in seal["inputs"]:
        require(digest(raw(HERE / row["path"])) == row["sha256"], "quality_file_unchanged")
    return seal


def npy_payload(data):
    require(data[:6] == b"\x93NUMPY", "saved_NPY_magic")
    length_size = 2 if data[6] == 1 else 4
    header_size = int.from_bytes(data[8:8 + length_size], "little")
    offset = 8 + length_size + header_size
    header = ast.literal_eval(data[8 + length_size:offset].decode("latin1"))
    description = header["descr"]
    require(isinstance(description, str), "simple_saved_dtype")
    kind, width = description[1], int(description[2:])
    item_bytes = 4 * width if kind == "U" else width
    count = 1
    for dimension in header["shape"]:
        count *= dimension
    require(count * item_bytes == len(data) - offset, "saved_array_payload_length")
    return {"dtype": description, "shape": list(header["shape"]), "nbytes": len(data) - offset,
            "raw_sha256": digest(data[offset:]), "fortran_order": header["fortran_order"]}


def frame_cost(frame):
    png, npz = raw(frame["PNG"]), raw(frame["NPZ"])
    require(digest(png) == frame["PNG_sha256"] and len(png) == frame["PNG_bytes"], "PNG_binding")
    require(digest(npz) == frame["NPZ_sha256"] and len(npz) == frame["NPZ_bytes"], "NPZ_binding")
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (512, 512), "512_PNG")
    with zipfile.ZipFile(io.BytesIO(npz)) as archive:
        arrays = {Path(name).stem: npy_payload(archive.read(name)) for name in archive.namelist()}
    owner_key = "patch_owners" if frame["origin"] == "product" else "triangle_ids"
    buffers = {"color", "depth", "owners", owner_key}
    require(buffers <= set(arrays), "common_four_buffer_scope")
    require(len(arrays) == (9 if frame["origin"] == "product" else 4), "saved_array_count")
    for name, array in arrays.items():
        metadata = frame["arrays"][name]
        require(array["nbytes"] == metadata["nbytes"] and array["shape"] == metadata["shape"]
                and array["raw_sha256"] == metadata["sha256"], "array_metadata_binding")
    four = sum(arrays[name]["nbytes"] for name in buffers)
    mapping = sum(value["nbytes"] for name, value in arrays.items() if name not in buffers)
    require(four == frame["raster_returned_array_payload_bytes"]
            and four + mapping == frame["array_payload_bytes"], "frame_payload_metric")
    return {key: frame[key] for key in ("attempt_id", "global_attempt", "origin", "view_name", "ref")} | {
        "PNG_bytes": len(png), "NPZ_bytes": len(npz), "PNG_sha256": digest(png), "NPZ_sha256": digest(npz),
        "arrays": arrays, "four_buffer_payload_bytes": four, "mapping_payload_bytes": mapping,
        "all_saved_array_payload_bytes": four + mapping,
        "intent_ns": frame["started_ns"], "render_started_ns": frame["render_started_ns"],
        "render_closed_ns": frame["render_closed_ns"], "registered_ns": frame["completed_ns"],
        "original_raster_call_ns": frame["render_closed_ns"] - frame["render_started_ns"],
        "intent_to_registration_ns": frame["completed_ns"] - frame["started_ns"],
        "scope": "Product frame registration follows the whole three-view producer. Its overlapping intent-to-registration windows are not summed."}


def cli_images(consumer):
    rows = []
    for call in consumer["tool_calls"]:
        for index, block in enumerate((call["item"].get("result") or {}).get("content", [])):
            if block.get("type") != "image":
                continue
            png = base64.b64decode(block["data"], validate=True)
            require(struct.unpack(">II", png[16:24]) == (512, 512), "CLI_image_size")
            rows.append({"tool_item_id": call["item"]["id"], "block_index": index,
                         "CLI_completed_ns": call["perf_ns"], "PNG_bytes": len(png), "PNG_sha256": digest(png),
                         "base64_chars": len(block["data"]),
                         "image_block_JSON_bytes": len(json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode())})
    require(len(rows) == consumer["public_image_count"], "actual_CLI_image_count")
    require(sum(row["PNG_bytes"] for row in rows) == consumer["public_image_bytes"], "actual_CLI_image_bytes")
    return rows


def tool_rows(folder, metrics, consumer):
    tools = []
    require(len(metrics["tools"]) == len(consumer["tool_calls"]), "all_business_tool_denominator")
    for row, call in zip(metrics["tools"], consumer["tool_calls"]):
        number = row["attempt"]
        path = folder / "o" / f"tool_{number:02}"
        request, response = read(path / "REQUEST.json"), read(path / "RESPONSE.json")
        require(call["item"]["tool"] == request["params"]["name"] == row["name"], "tool_name_binding")
        require(call["item"]["result"]["content"] == response["result"]["content"], "tool_content_binding")
        code = request["params"].get("arguments", {}).get("code")
        tools.append({"attempt": number, "name": row["name"], **interval(row),
                      "CLI_completed_ns": call["perf_ns"], "is_error": row["is_error"], "error": row["error"],
                      "content_metrics": row["content_metrics"], "compact_response_bytes": row["response_bytes"],
                      "request_file_bytes": (path / "REQUEST.json").stat().st_size,
                      "response_file_bytes": (path / "RESPONSE.json").stat().st_size,
                      "consumer_code_sha256": digest(code.encode()) if code is not None else None})
    require([row["attempt"] for row in tools] == list(range(1, len(tools) + 1)), "tool_sequence")
    require(all(a["closed_ns"] <= b["started_ns"] for a, b in zip(tools, tools[1:])), "sequential_tools")
    return tools


def product_cost(folder, tools, consumer):
    product = read(folder / "o/product_call_01/SERVICE_RESULT.json")
    call = read(folder / "o/product_call_01/CALL.json")
    delivery = call["delivery_audit"]
    response = read(folder / "o/tool_01/RESPONSE.json")
    text = response["result"]["content"][0]["text"]
    require(call["product_source_sha256"] == PRODUCT_SHA256 and len(text.encode()) == 44873, "current_product_text")
    require(product["work"]["result_cache_hit"] is False and product["work"]["frame_reuses"] == 0, "fresh_cold_product")
    require(product["work"]["prepare_calls"] == 1 and product["work"]["raster_attempts"] == 3, "cold_product_counts")
    parsed = json.loads(text)
    require(parsed["schema"] == "active-observation-brief-v4", "current_v4")
    require(tools[0]["started_ns"] <= call["started_ns"] <= product["stages"]["prepare"]["started_ns"]
            <= product["stages"]["prepare"]["closed_ns"] <= call["closed_ns"] <= tools[0]["closed_ns"],
            "product_preparation_inside_actual_tool_clock")
    first = consumer["tool_calls"][0]["perf_ns"]
    later = sum(row["elapsed_ns"] for row in tools[1:])
    return {"call_original": call, "work_original": product["work"], "generation_work_original": product["generation_work"],
            "stages_original": product["stages"], "generation_stages_original": product["generation_stages"],
            "per_frame_stages": [{"view_name": f["view_name"], "stages": f["stages"], "feedback_stages": f["feedback_stages"]} for f in product["frames"]],
            "public_JSON": {"UTF8_bytes": len(text.encode()), "sha256": digest(text.encode()), "schema": parsed["schema"],
                            "namespace_extra_serialization": False, "namespace_independent_dump_hash": None,
                            "namespace_assignment_CPU_ns": None, "json_loads_only_CPU_ns": None,
                            "tool2_parse_print_envelope_ns": tools[1]["elapsed_ns"],
                            "tool3_existing_table_query_ns": tools[2]["elapsed_ns"]},
            "scope_and_facts_ns": product["stages"]["scope_and_facts"]["elapsed_ns"],
            "MCP_projection_serialization_images_envelope_ns": delivery["elapsed_ns"],
            "standalone_projection_CPU_ns": None, "standalone_JSON_serialization_CPU_ns": None,
            "image_read_sum_ns": sum(row["read_ns"] for row in delivery["frames"]),
            "image_validate_sum_ns": sum(row["validate_ns"] for row in delivery["frames"]),
            "image_base64_sum_ns": sum(row["base64_ns"] for row in delivery["frames"]),
            "PNG_NPZ_publication_sum_ns": sum(f["stages"]["PNG_NPZ_publication"]["elapsed_ns"] for f in product["frames"]),
            "standalone_PNG_encoding_CPU_ns": None, "standalone_NPZ_compression_CPU_ns": None,
            "post_first_delivery": {"CLI_received_ns": first, "prompt_to_bundle_ns": first - consumer["prompt_submitted_ns"],
                                    "bundle_to_final_ns": consumer["final_received_ns"] - first,
                                    "later_tool_service_ns": later,
                                    "bundle_to_final_minus_later_tools_ns": consumer["final_received_ns"] - first - later,
                                    "first_task_sufficient_evidence_ns": None},
            "nested_scope": "prepare includes partition/index/world descriptions. Readability includes pixel localization. MCP envelope includes projection/serialization and image operations. Nested values are never added to outer time."}


def slot_cost(slot):
    folder = FORMAL / slot
    outer_original = read(FORMAL / "slot_records" / slot / "SLOT_TIMING.json")
    slot_result = read(FORMAL / "slot_records" / slot / "SLOT_RESULT.json")
    route = read(folder / "RESULT.json")
    route_time = read(folder / "FINAL_TIMING.json")
    consumer = read(folder / "c/CONSUMER.json")
    consumer_time = read(folder / "c/FINAL_TIMING.json")
    metrics, observations = read(folder / "o/METRICS.json"), read(folder / "o/OBSERVATIONS.json")
    constructions, transports = read(folder / "o/IMAGE_CONSTRUCTIONS.json"), read(folder / "o/TRANSPORT.json")
    contracts = read(folder / "c/BUSINESS_SOURCE_BINDING.json")
    read(folder / "o/CLOSE.json")
    raw(folder / "c/PUBLIC_FINAL.txt")
    clocks = {"outer": interval(outer_original, end="SLOT_RESULT_closed_ns"),
              "route": interval(route_time, end="result_closed_ns"),
              "consumer": interval(consumer_time, end="consumer_record_closed_ns", elapsed="full_turn_wall_ns")}
    require(clocks["outer"]["started_ns"] <= clocks["route"]["started_ns"] <= clocks["consumer"]["started_ns"]
            <= clocks["consumer"]["closed_ns"] <= clocks["route"]["closed_ns"] <= clocks["outer"]["closed_ns"], "slot_nested_clocks")
    require(route_time["original_deadline_ns"] == clocks["route"]["started_ns"] + 450_000_000_000, "original_450_second_deadline")
    require(outer_original["route_invoked"] and not outer_original["publication_errors"] and slot_result["source_unchanged"], "outer_publication_source")
    require(route_time["accepted_success"] and consumer["valid_completion"] and route["outer_valid_completion"], "all_slots_completed")
    require(not contracts["binding_errors"] and all(r["matched"] for r in contracts["result_contracts"]), "original_tool_result_binding")
    tools = tool_rows(folder, metrics, consumer)
    require(len(tools) == metrics["tool_attempts"] <= 12, "business_guard_limit")
    frames = [frame_cost(frame) for frame in observations["frames"]]
    require(len(frames) == len(observations["render_attempts"]) == metrics["new_renders"] <= 6, "raster_denominator")
    images = cli_images(consumer)
    require(len(images) == metrics["constructed_image_blocks"] == metrics["server_socket_sent_image_blocks"], "constructed_sent_received_images")
    require(not constructions["failed"] and not constructions["post_construction_failures"], "no_image_failures")
    replays = []
    for replay in observations["replays"]:
        data = raw(replay["path"])
        require(digest(data) == replay["sha256"] and len(data) == replay["bytes"], "replay_bytes")
        replays.append(dict(replay, elapsed_ns=replay["closed_ns"] - replay["started_ns"]))
    wire = []
    for row in consumer["MCP_wire_files"]:
        path = folder / "c" / row["path"]
        data = raw(path)
        require(digest(data) == row["sha256"] and len(data) == row["bytes"], "stdio_original_bytes")
        wire.append({"path": str(path), "direction": path.stem, "bytes": len(data), "sha256": digest(data)})
    for direction in ("TX", "RX"):
        require(sum(row["bytes"] for row in wire if row["direction"] == direction) == consumer["MCP_stdio_" + direction + "_bytes"], "stdio_sum")
    stdout, stderr = raw(folder / "c/stdout.raw.bin"), raw(folder / "c/stderr.raw.bin")
    require(digest(stdout) == consumer["stdout_raw_sha256"], "CLI_stdout_original")
    usage = consumer["usage"]
    complete_usage = (isinstance(usage, dict) and len(consumer["raw_usage_events"]) == len(consumer["usage_rows"]) == 1
                      and usage == consumer["raw_usage_events"][0] == consumer["usage_rows"][0])
    require(complete_usage, "same_saved_usage_records")
    require(all(type(v) is int and v >= 0 for v in usage.values())
            and usage["cached_input_tokens"] <= usage["input_tokens"]
            and usage["reasoning_output_tokens"] <= usage["output_tokens"], "usage_subsets")
    four = sum(f["four_buffer_payload_bytes"] for f in frames)
    mapping = sum(f["mapping_payload_bytes"] for f in frames)
    require(four + mapping == metrics["common"]["array_payload_bytes"], "common_array_metric_scope")
    tool_ns = sum(t["elapsed_ns"] for t in tools)
    body = {"slot": slot, "group": slot[0], "qualified_completed": True,
            "clocks": clocks, "outer_original": outer_original,
            "original_deadline_ns": route_time["original_deadline_ns"],
            "deadline_remaining_at_route_close_ns": route_time["original_deadline_ns"] - clocks["route"]["closed_ns"],
            "outer_before_route_ns": clocks["route"]["started_ns"] - clocks["outer"]["started_ns"],
            "outer_after_route_ns": clocks["outer"]["closed_ns"] - clocks["route"]["closed_ns"],
            "CLI_clocks": {key: consumer[key] for key in ("started_ns", "popen_ns", "prompt_write_started_ns", "prompt_submitted_ns", "final_received_ns", "turn_completed_ns", "process_exit_ns", "cleanup_end_ns")},
            "owner_tool_service_sum_ns": tool_ns,
            "prompt_to_final_ns": consumer["final_received_ns"] - consumer["prompt_submitted_ns"],
            "prompt_to_final_minus_tools_ns": consumer["final_received_ns"] - consumer["prompt_submitted_ns"] - tool_ns,
            "residual_scope": "Includes provider service, transport, local handling and unseparated work. It is not pure thinking time.",
            "tools": tools, "frames": frames, "startup_stages_original": observations["stages"], "replays": replays,
            "counts": {"received_tool_requests": len(tools), "admitted_business_tools": len(tools), "guard_rejections": 0,
                       "ordinary_business_errors": [r["attempt"] for r in tools if r["is_error"]],
                       "ordinary_business_error_count": sum(r["is_error"] for r in tools),
                       "rasters": len(frames), "product_rasters": sum(f["origin"] == "product" for f in frames),
                       "native_rasters": sum(f["origin"] == "native" for f in frames),
                       "constructed_sent_CLI_image_blocks": len(images), "product_calls": len(observations["active"]),
                       "capture_replays": len(replays), "Blender_capture_calls": metrics["common"]["actual_Blender_capture_calls"]},
            "bytes": {"generated_PNG": sum(f["PNG_bytes"] for f in frames), "generated_NPZ": sum(f["NPZ_bytes"] for f in frames),
                      "four_buffer_payload": four, "product_mapping_payload": mapping, "all_saved_array_payload": four + mapping,
                      "common_array_metric_original": metrics["common"]["array_payload_bytes"],
                      "CLI_PNG": sum(r["PNG_bytes"] for r in images), "CLI_base64_chars": sum(r["base64_chars"] for r in images),
                      "CLI_image_block_JSON": sum(r["image_block_JSON_bytes"] for r in images),
                      "stdio_TX": consumer["MCP_stdio_TX_bytes"], "stdio_RX": consumer["MCP_stdio_RX_bytes"],
                      "tool_request_files": sum(r["request_file_bytes"] for r in tools), "tool_response_files": sum(r["response_file_bytes"] for r in tools),
                      "CLI_stdout_raw": len(stdout), "CLI_stderr_raw": len(stderr), "prompt_text": consumer["input_text_bytes"],
                      "public_agent_text": consumer["public_text_bytes"], "final_text": consumer["output_text_bytes"],
                      "capture_copy": sum(r["bytes"] for r in replays)},
            "CLI_images": images, "image_constructions_original": constructions, "transport_original": transports,
            "stdio_wire_files": wire, "actor_metrics_original": {k: v for k, v in metrics.items() if k not in ("tools", "common")},
            "common_metrics_original": metrics["common"],
            "usage": {"reported": usage, "raw_events": consumer["raw_usage_events"], "usage_rows": consumer["usage_rows"],
                      "input_plus_output": usage["input_tokens"] + usage["output_tokens"],
                      "uncached_input": usage["input_tokens"] - usage["cached_input_tokens"],
                      "semantics": consumer["usage_semantics"], "aggregation": consumer["usage_aggregation"],
                      "raw_event_count": len(consumer["raw_usage_events"]), "provider_requests": None,
                      "image_tokens": consumer.get("image_tokens"), "cash_fees": consumer.get("fees"),
                      "provider_retry_observations_original": consumer["provider_retry_observations"]},
            "CLI_configuration": {"argv": consumer["argv"], "model": consumer["model"], "requested_effort": consumer["requested_effort"],
                                  "resolved_effort": consumer["resolved_effort"], "valid_completion": consumer["valid_completion"]},
            "lifecycle": {"actor": route["owner_process_cleanup"], "CLI": route["consumer_process_cleanup"],
                          "thin_held_handle": route["runtime_exit"], "thin_EXIT_receipt": route["bridge_cleanup"],
                          "owner_close_confirmed": route["owner_close_confirmed"],
                          "runtime_binding": route["runtime_binding"]},
            "visible_CLI_warning_lines": [line for line in stderr.decode("utf-8", errors="replace").splitlines()
                                          if "warn" in line.lower()],
            "warning_scope": "Visible CLI diagnostics do not establish provider retries or resolved backend settings."}
    if slot[0] == "P":
        body["product"] = product_cost(folder, tools, consumer)
        if slot == "P1":
            body["supplementary_work"] = {"tool4_component_discovery_and_duplicate_SCENE_ns": tools[3]["elapsed_ns"],
                                          "tool5_all_face_join_and_target_query_ns": tools[4]["elapsed_ns"],
                                          "tool6_SCENE_pixel_check_and_coverage_record_ns": tools[5]["elapsed_ns"],
                                          "duplicate_SCENE_delivered": False}
        elif slot == "P2":
            body["supplementary_work"] = {"tool4_duplicate_SCENE_and_delivery_ns": tools[3]["elapsed_ns"],
                                          "tool5_product_guided_fullmesh_mapping_ns": tools[4]["elapsed_ns"],
                                          "tool6_whole_SCENE_pixel_check_ns": tools[5]["elapsed_ns"],
                                          "duplicate_SCENE_delivered": True}
        else:
            body["supplementary_work"] = {"tool4_current_JSON_target_summary_ns": tools[3]["elapsed_ns"],
                                          "tool5_current_JSON_artifact_formatting_ns": tools[4]["elapsed_ns"],
                                          "duplicate_SCENE_delivered": False}
        body["supplementary_work"]["six_pool_native_occlusion_recomputed"] = False
    else:
        body["native_error_and_recovery"] = {
            "missing_shapely_tool2_ns": tools[1]["elapsed_ns"],
            "all_error_and_recovery_cost_retained": True}
        if slot == "N3":
            body["native_error_and_recovery"].update({
                "tool6_wrong_all_remaining_backfacing_assertion_ns": tools[5]["elapsed_ns"],
                "tool7_diagnose_occluded_front_facing_remainder_ns": tools[6]["elapsed_ns"],
                "tool11_tail_coverage_rows_reprint_ns": tools[10]["elapsed_ns"]})
    return body


def build():
    seal = verify_quality()
    rules, plan, frozen = read(HERE / "DECISION_RULES.json"), read(HERE / "PLAN.json"), read(HERE / "FROZEN.json")
    require(len(frozen["files_sha256"]) == 1796, "frozen_1796_closure")
    for path, expected in frozen["files_sha256"].items():
        require(digest(raw(path)) == expected, "frozen_source_changed")
    source_review = read(HERE / "review/SOURCE_ENTRY_LIFECYCLE_ENTAILMENT.json")
    require(source_review["audit_passed"], "independent_source_lifecycle_audit")
    archive = read(HERE / "EXTERNAL_ARCHIVE.json")
    require(archive["file_count"] == len(archive["files"]) == 869, "869_archived_files")
    for row in archive["files"]:
        original, copy = raw(row["original_path"]), raw(HERE / row["archive_path"])
        require(original == copy and len(copy) == row["bytes"] and digest(copy) == row["sha256"], "external_archive_bytes")
    require(sum(r["bytes"] for r in archive["files"]) == archive["bytes"] == 13931769, "archive_byte_total")
    parent, batch = read(HERE / "FORMAL_PROCESS.json"), read(FORMAL / "BATCH_TIMING.json")
    run, launch = read(FORMAL / "RUN_RESULT.json"), read(FORMAL / "LAUNCH_RESULT.json")
    parent_clock, batch_clock = interval(parent), interval(batch, end="aggregate_results_closed_ns")
    require(parent["exit_code"] == 0 and not run["stop_remaining_reasons"] and not launch["terminal_errors"], "single_batch_success")
    slots = [slot_cost(slot) for slot in ORDER]
    require(all(a["clocks"]["outer"]["closed_ns"] <= b["clocks"]["outer"]["started_ns"] for a, b in zip(slots, slots[1:])), "fixed_serial_order")
    require(parent_clock["started_ns"] <= batch_clock["started_ns"] <= slots[0]["clocks"]["outer"]["started_ns"]
            and slots[-1]["clocks"]["outer"]["closed_ns"] <= batch_clock["closed_ns"] <= parent_clock["closed_ns"], "batch_parent_nesting")
    intents = [read(p) for p in sorted((EXTERNAL / "raster_budget").glob("attempt_*/INTENT.json"))]
    frames = sorted((f for slot in slots for f in slot["frames"]), key=lambda f: f["global_attempt"])
    require(len(frames) == len(intents) == 29 and [r["global_attempt"] for r in intents] == list(range(1, 30)), "29_rasters_including_duplicates")
    for intent, frame in zip(intents, frames):
        require(intent["global_attempt"] == frame["global_attempt"] and intent["attempt_id"] == frame["attempt_id"]
                and intent["view_name"] == frame["view_name"] and intent["origin"] == frame["origin"], "durable_intent_frame_identity")
    by_slot = {s["slot"]: s for s in slots}
    groups = {}
    for group in ("N", "P"):
        rows = [s for s in slots if s["group"] == group]
        usage = {key: sum(s["usage"]["reported"][key] for s in rows) for key in rows[0]["usage"]["reported"]}
        groups[group] = {"denominator": 3, "qualified_completed": len(rows),
                         "outer_sum_ns": sum(s["clocks"]["outer"]["elapsed_ns"] for s in rows),
                         "outer_median_ns": statistics.median(s["clocks"]["outer"]["elapsed_ns"] for s in rows),
                         "slowest_slot": max(rows, key=lambda s: s["clocks"]["outer"]["elapsed_ns"])["slot"],
                         "usage_sum": usage, "raw_input_plus_output_sum": usage["input_tokens"] + usage["output_tokens"],
                         "counts": {key: sum(s["counts"][key] for s in rows) for key in rows[0]["counts"] if key != "ordinary_business_errors"},
                         "bytes": {key: sum(s["bytes"][key] for s in rows) for key in rows[0]["bytes"]}}
    pairs = []
    for n, p in rules["paired_time"]["pairs"]:
        nt, pt = by_slot[n]["clocks"]["outer"]["elapsed_ns"], by_slot[p]["clocks"]["outer"]["elapsed_ns"]
        pairs.append({"N_slot": n, "P_slot": p, "N_outer_ns": nt, "P_outer_ns": pt,
                      "P_over_N": pt / nt, "N_over_P": nt / pt, "P_faster": pt < nt,
                      "P_minus_N_ns": pt - nt})
    ratios = [p["P_over_N"] for p in pairs]
    same_usage = (len({tuple(sorted(s["usage"]["reported"])) for s in slots}) == 1
                  and len({s["usage"]["semantics"] for s in slots}) == 1
                  and all(s["usage"]["aggregation"] is None and s["usage"]["raw_event_count"] == 1 for s in slots)
                  and len({s["CLI_configuration"]["argv"][0] for s in slots}) == 1
                  and all(s["CLI_configuration"]["model"] == plan["requested_model"]
                          and s["CLI_configuration"]["requested_effort"] == plan["requested_reasoning_effort"] for s in slots))
    median = statistics.median(ratios)
    faster = sum(pair["P_faster"] for pair in pairs)
    time_pass = median <= rules["paired_time"]["median_P_over_N_max"] and faster >= rules["paired_time"]["minimum_P_faster_pairs"]
    usage_pass = same_usage and groups["P"]["raw_input_plus_output_sum"] <= groups["N"]["raw_input_plus_output_sum"]
    decision = {"schema": "routed-task-preregistered-decision-v1", "quality_gate": seal["quality_gate_passed"],
                "same_source_complete_CLI_usage_comparable_for_limited_registered_scope": same_usage,
                "paired_outer_clock_qualified": True, "pairs": pairs,
                "median_P_over_N": median, "required_median_max": 0.9,
                "P_faster_pairs": faster, "required_faster_pairs": 2, "time_gate_pass": time_pass,
                "N_raw_input_plus_output": groups["N"]["raw_input_plus_output_sum"],
                "P_raw_input_plus_output": groups["P"]["raw_input_plus_output_sum"],
                "P_over_N_raw_usage": groups["P"]["raw_input_plus_output_sum"] / groups["N"]["raw_input_plus_output_sum"],
                "usage_gate_pass": usage_pass, "necessary_evidence_and_no_pre_timing_P_work": True,
                "useful_positive_signal_for_fixed_routed_task": bool(seal["quality_gate_passed"] and time_pass and usage_pass),
                "interpretation": "Finite engineering signal for this fixed explicitly routed task and same-source fresh-single-turn CLI reports. Provider turn/session aggregation remains unconfirmed. No cash, provider request count, statistical significance, causal algorithm-only or general-scene claim.",
                "reverse_pairs": [p for p in pairs if not p["P_faster"]], "extra_samples": 0, "threshold_or_prompt_changes": 0,
                "old_failed_or_prior_single_slot_denominators_used": False}
    prep = read(HERE / "preparation/N_READONLY/RESULT.json")
    prep_process = read(HERE / "preparation/N_READONLY/PROCESS.json")
    prep_metrics = read(HERE / "preparation/N_READONLY/o/METRICS.json")
    prep_obs = read(HERE / "preparation/N_READONLY/o/OBSERVATIONS.json")
    binding = read(HERE.parent / "m4_consumable_observation_001/inputs/PRODUCT_BINDING.json")
    outer_sum = sum(s["clocks"]["outer"]["elapsed_ns"] for s in slots)
    total_counts = {key: groups["N"]["counts"][key] + groups["P"]["counts"][key] for key in groups["N"]["counts"]}
    result = {"schema": "routed-task-six-slot-saved-cost-v1", "task": plan["task"],
              "quality_seal_sha256": SEAL_SHA256, "sealed_quality_files_verified": 24,
              "source": {"frozen_files_verified": 1796, "product_source_sha256": PRODUCT_SHA256,
                         "product_Git": frozen["product_git"], "preparation_Git": launch["preparation_git"],
                         "product_141_repo_and_install_verified_by_sealed_source_audit": True,
                         "product_binding_original": binding},
              "decision": decision, "groups": groups, "slots": slots,
              "batch": {"parent": parent_clock, "batch": batch_clock, "all_independent_slot_outer_sum_ns": outer_sum,
                        "batch_minus_slot_sums_ns": batch_clock["elapsed_ns"] - outer_sum,
                        "parent_minus_batch_ns": parent_clock["elapsed_ns"] - batch_clock["elapsed_ns"],
                        "between_slot_gaps_ns": [b["clocks"]["outer"]["started_ns"] - a["clocks"]["outer"]["closed_ns"] for a, b in zip(slots, slots[1:])],
                        "batch_before_first_slot_ns": slots[0]["clocks"]["outer"]["started_ns"] - batch_clock["started_ns"],
                        "batch_after_last_slot_ns": batch_clock["closed_ns"] - slots[-1]["clocks"]["outer"]["closed_ns"],
                        "launcher_exit_code": parent["exit_code"], "launch_result_original": launch,
                        "scope": "The paired metric is each independent identical slot wrapper. Batch and parent clocks are separate nested scopes, never total/6."},
              "counts": dict(total_counts, formal_slots=6, fresh_CLI_turns=6, outer_retries=0,
                             failed_slots=0, not_run_slots=0, preparation_model_calls=0, preparation_rasters=0,
                             product_prepare_calls=3, product_index_builds=3, duplicate_product_SCENE_rasters=2,
                             Blender_processes=0, provider_requests=None),
              "durable_intents_original": intents,
              "preparation": {"ordinary_Python_readonly_checks": 1, "passed": prep["passed"], "process_original": prep_process,
                              "owner_clock": {"started_ns": prep["owner_close"]["started_ns"], "closed_ns": prep["owner_close"]["ended_ns"],
                                              "elapsed_ns": prep["owner_close"]["ended_ns"] - prep["owner_close"]["started_ns"]},
                              "tool_clock_original": prep_metrics["tools"], "startup_stages_original": prep_obs["stages"],
                              "whole_preparation_parent_wall_ns": None, "models": 0, "product_observations": 0, "rasters": 0,
                              "new_install_in_this_batch": False, "reused_install_binding": binding,
                              "full_prior_install_R_and_D_human_coordination_and_audit_cost": None},
              "external_archive": {k: v for k, v in archive.items() if k != "files"},
              "usage_semantics": {"all_six_have_one_equal_raw_and_summary_event": True,
                                  "scope": "unconfirmed_turn_or_session_scope", "aggregation": None,
                                  "comparability": "Same CLI source/schema, requested settings, fresh process and one user turn per slot. This is the registered limited CLI consumption comparison, with provider aggregation unconfirmed.",
                                  "subsets": "cached input is within input; reasoning output is within output. Neither is added to input+output.",
                                  "provider_request_count": None, "provider_resolved_model_effort_tier": None,
                                  "image_tokens": None, "cash": None},
              "scope_limits": ["Explicit P routing and reusable product facts are included in this workflow comparison. It is not spontaneous adoption or isolated geometry-algorithm causality.",
                               "No sample or slow/error slot was dropped. Missing shapely in three N slots and N3 assertion recovery plus tail-table reprint remain fully charged.",
                               "P1 independently discovers source components and repeats SCENE. P2 performs product-guided full-mesh identity mapping and repeats SCENE. P3 consumes and formats JSON. No P slot recomputes six-pool visibility.",
                               "Every readable witness in this geometry is complete. Partial-readable and cross-scene generalization remain open.",
                               "Provider internals and independent namespace string dump are unobserved. CLI receipt is separately verified.",
                               "PNG/base64/JSON/stdio/ZIP and raw array bytes describe nested cumulative representations. They are not summed as network traffic or peak memory.",
                               "Thin handles confirm exit1 and closure while EXIT receipt is missing/unknown. Actor and CLI exits are0; launcher and parent exits are0.",
                               "All inner stages are nested. Tool-outside residuals include service/transport/local work and cannot be labelled pure thought.",
                               "Preparation script authoring, earlier install/R&D, root coordination and this audit lack complete metering."],
              "unknowns": {"peak_RSS": None, "total_NumPy_Python_temporaries": None, "total_warm_cache_bytes": None,
                           "namespace_independent_dump_or_hash": None, "provider_internal_requests": None,
                           "standalone_JSON_parse_or_assignment_CPU_ns": None, "standalone_PNG_NPZ_encode_CPU_ns": None,
                           "first_task_sufficient_evidence_ns": None},
              "audit_operations": {"new_models": 0, "new_product_calls": 0, "new_rasters": 0,
                                   "new_tests": 0, "new_timing_samples": 0,
                                   "NPZ_analysis": "Standard-library zip/NPY header and payload hashing only. No product/renderer import.",
                                   "script_sha256": digest(raw(__file__))}}
    verify_quality()
    result["inputs_sha256"] = dict(sorted(INPUTS.items()))
    return result


def markdown(result):
    decision, groups = result["decision"], result["groups"]
    lines = ["# 固定路由任务完整成本与预登记判定", "",
             "六槽全部完成并通过已封存质量审核，N/P各3/3，P实际事实采用3/3。本固定任务达到预登记的有用正信号。", "",
             "| 配对 | N完整外层秒 | P完整外层秒 | P/N |", "| --- | ---: | ---: | ---: |"]
    for pair in decision["pairs"]:
        lines.append(f"| {pair['N_slot']}/{pair['P_slot']} | {pair['N_outer_ns']/1e9:.7f} | {pair['P_outer_ns']/1e9:.7f} | {pair['P_over_N']:.6f} |")
    lines.extend(["", f"配对P/N中位数为{decision['median_P_over_N']:.6f}，门限为0.90。3/3对P更快，逆向配对为0。最慢N槽为{groups['N']['slowest_slot']}，最慢P槽为{groups['P']['slowest_slot']}。每槽均使用检查前至SLOT_RESULT写入、fsync及关闭的同一独立wrapper，SLOT_TIMING自身发布在时界外。", "",
                  "| CLI原始usage合计 | N | P |", "| --- | ---: | ---: |"])
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "cache_write_input_tokens"):
        lines.append(f"| {key} | {groups['N']['usage_sum'][key]} | {groups['P']['usage_sum'][key]} |")
    lines.extend([f"| input+output | {decision['N_raw_input_plus_output']} | {decision['P_raw_input_plus_output']} |", "",
                  f"P/N原始input+output为{decision['P_over_N_raw_usage']:.6f}。六槽均为同CLI schema、fresh进程、单用户轮次，原始usage与summary逐项一致。turn/session聚合范围仍未确认，此处按预登记作同源CLI消费的有限判断。cached属于input、reasoning属于output，没有再加一次。现金、图像token和provider请求数未测。", "",
                  f"六槽独立outer合计{result['batch']['all_independent_slot_outer_sum_ns']/1e9:.7f}秒。batch为{result['batch']['batch']['elapsed_ns']/1e9:.7f}秒，额外协调及共同发布{result['batch']['batch_minus_slot_sums_ns']/1e9:.7f}秒。父周期{result['batch']['parent']['elapsed_ns']/1e9:.7f}秒。route、consumer及工具阶段嵌套保留，不叠加，也没有总周期除以6。", "",
                  f"实际49次业务工具、0 guard拒绝、29次raster，包含产品9次和原生20次。{result['counts']['constructed_sent_CLI_image_blocks']}个PNG块实际构造、发送并进入CLI，N1/N2/N3分别为0/2/0，P1/P2/P3分别为3/4/3。其它构造图使用数值缓冲及引用，没有逐图附给CLI。P1多构造的SCENE没有附图，P2重复SCENE附图，P3无重复。产品调用、prepare、index与重放各3次，Blender采集和进程均为0。", "",
                  "P1的独立组件发现、P2的产品region引导全网格映射及两次重复SCENE全部计入。P3只查询、派生及保存JSON。三个N槽缺少shapely的错误、N3错误断言恢复和尾部表格重印全部保留。没有将这些成本从结果中扣除，也没有把P补查描述为六池遮挡重算。", "",
                  "每个P公开v4 JSON为44,873字节，直接绑定原字符串。COST.json保留产品index/prepare、scope_and_facts、图片反馈及定位、MCP投影与序列化包容阶段、图片read/validate/base64、PNG/NPZ联合发布、每次工具和原始数组字节。独立JSON解析CPU、PNG编码CPU、峰值内存和完整缓存占用未测。", "",
                  "1796冻结来源、24质量文件和869份外部原件/副本已逐SHA复核。准备只有一次无图普通Python读取，模型、产品观察和光栅均0。安装复用既有隔离候选，前期研发、安装、人工协调与审计未完整计量。", "",
                  "此结果支持当前固定题、显式路由和同源CLI消费口径下的工程判断。三对样本没有统计显著性或普遍性能保证。所有readable行恰好完整，partial-readable与新场景仍未验收。provider内部、namespace独立dump仍未知。thin持有句柄确认exit1及关闭，EXIT回执缺失保持未知，actor/CLI/launcher均exit0。没有引用旧239秒或前批141秒作分母，没有增补同题样本或修改门限。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    report = build()
    for name, value in (("COST.json", report), ("DECISION_RESULT.json", report["decision"])):
        with (HERE / name).open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    with (HERE / "COST.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(markdown(report))
    print(json.dumps({"decision": report["decision"], "counts": report["counts"], "inputs": len(report["inputs_sha256"])}))
