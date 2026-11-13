"""Independent read-only cost recount of the single frozen six-slot batch."""

import ast
import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
CHECKS = 0
INPUTS = {}


def check(value, label):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    INPUTS[str(path)] = sha(raw)
    return raw


def load(path):
    return json.loads(read(path))


def wire(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def interval(value, start="started_ns", end="closed_ns", elapsed="elapsed_ns", label="interval"):
    check(value[start] <= value[end] and value[end] - value[start] == value[elapsed], label)


def held_cleanup(value, pid, label):
    interval(value, label=label + " time")
    check(value["pid"] == pid and value["confirmed"] is True and value["reaped"] is True,
          label + " held original process")
    check(value["exit_code"] == 0 and value["kill_requested"] is False and value["errors"] == [] and
          value["process_handle_closed"] is True and
          value["pipes_closed"] == {"stdin": True, "stdout": True, "stderr": True}, label + " handle/pipes")


def content_counts(content):
    counters = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0, text_UTF8_bytes=0)
    hashes = []
    for block in content:
        if block["type"] == "text":
            counters["text_UTF8_bytes"] += len(block["text"].encode("utf-8"))
        elif block["type"] == "image":
            check(block["mimeType"] == "image/png", "image MIME")
            raw = base64.b64decode(block["data"], validate=True)
            check(raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (512, 512), "PNG dimensions")
            counters["image_blocks"] += 1
            counters["PNG_bytes"] += len(raw)
            counters["base64_chars"] += len(block["data"])
            counters["image_block_JSON_bytes"] += len(wire(block)) - 1
            hashes.append(sha(raw))
        else:
            raise ValueError("unexpected content type")
    return dict(counters, PNG_sha256=hashes)


def add_counts(total, values):
    total.update({key: value for key, value in values.items() if type(value) is int})


def zip_originals(path, digest, size, members, original_directory, label):
    raw = read(path)
    check(sha(raw) == digest and len(raw) == size, label + " ZIP hash/size")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        check(len(names) == len(set(names)) and set(names) == set(members), label + " ZIP inventory")
        for name, wanted in members.items():
            original = read(original_directory / name)
            check(archive.read(name) == original and sha(original) == wanted, label + " preserved " + name)


def verify_npz(raw, expected, label):
    total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        check(sorted(archive.namelist()) == ["color.npy", "depth.npy", "owners.npy"], label + " members")
        for name, entry in expected.items():
            data = archive.read(name + ".npy")
            check(data[:6] == b"\x93NUMPY", label + " npy magic")
            width = 2 if data[6:8] == b"\x01\x00" else 4
            length = struct.unpack("<H" if width == 2 else "<I", data[8:8 + width])[0]
            header_end = 8 + width + length
            header = ast.literal_eval(data[8 + width:header_end].decode("utf-8"))
            payload = data[header_end:]
            check(header["fortran_order"] is False and list(header["shape"]) == entry["shape"] and
                  header["descr"] == entry["dtype_str"], label + " dtype/shape/order")
            check(len(payload) == entry["nbytes"] and sha(payload) == entry["sha256"] and
                  len(payload) == math.prod(header["shape"]) * int(header["descr"][2:]), label + " raw array payload")
            total += len(payload)
    return total


def observations(directory):
    observation = load(directory / "OBSERVATIONS.json")
    trace_raw = read(directory / "TRACE.jsonl")
    trace = [json.loads(line) for line in trace_raw.splitlines()]
    check([row["sequence"] for row in trace] == list(range(1, len(trace) + 1)), "trace exact sequence")
    intents = [row for row in trace if row["event"] == "render_attempt"]
    check(len(intents) == len(observation["render_attempts"]) == observation["metrics"]["render_attempts"],
          "all durable render attempts")
    check(len({row["view_name"] for row in intents}) == len(intents) <= 6, "unique bounded views")
    png = npz = array_bytes = metadata = pixel_metadata = 0
    for attempt, intent in zip(observation["render_attempts"], intents):
        check(attempt["attempt_id"] == intent["attempt_id"] and attempt["view_name"] == intent["view_name"] and
              attempt["status"] == "completed" and attempt["intent_ns"] == intent["monotonic_ns"] <=
              attempt["render_started_ns"] <= attempt["render_closed_ns"] <= attempt["completed_ns"],
              "render intent and completion")
        raw_png = read(attempt["PNG"])
        raw_npz = read(attempt["NPZ"])
        raw_metadata = read(attempt["metadata_path"])
        check(len(raw_png) == attempt["PNG_bytes"] and sha(raw_png) == attempt["PNG_sha256"], "actual generated PNG")
        check(len(raw_npz) == attempt["NPZ_bytes"] and sha(raw_npz) == attempt["NPZ_sha256"], "actual generated NPZ")
        check(len(raw_metadata) == attempt["metadata_bytes"] and sha(raw_metadata) == attempt["metadata_sha256"],
              "actual frame metadata")
        check(verify_npz(raw_npz, attempt["arrays"], attempt["ref"]) == attempt["array_payload_bytes"], "array sum")
        png += len(raw_png)
        npz += len(raw_npz)
        array_bytes += attempt["array_payload_bytes"]
        metadata += len(raw_metadata)
        if attempt.get("pixels_path"):
            pixel_raw = read(attempt["pixels_path"])
            check(len(pixel_raw) == attempt["pixels_bytes"] and sha(pixel_raw) == attempt["pixels_sha256"], "pixel metadata")
            pixel_metadata += len(pixel_raw)
    check(png == observation["metrics"]["PNG_bytes"] and npz == observation["metrics"]["NPZ_bytes"] and
          array_bytes == observation["metrics"]["array_payload_bytes"], "observation byte totals")
    stages = Counter()
    for stage in observation["stages"]:
        interval(stage, label="actual stage clock")
        stages[stage["name"]] += stage["elapsed_ns"]
    return observation, {"generated_PNG_bytes": png, "generated_NPZ_bytes": npz,
        "array_payload_bytes": array_bytes, "FRAME_JSON_bytes": metadata, "PIXELS_JSON_bytes": pixel_metadata,
        "OBSERVATIONS_JSON_bytes": len(read(directory / "OBSERVATIONS.json")), "TRACE_bytes": len(trace_raw)}, dict(stages)


def slot(row):
    directory = Path(row["folder"])
    label = row["slot"]
    result = load(directory / "RESULT.json")
    timing = load(directory / "FINAL_TIMING.json")
    consumer = load(directory / "c/CONSUMER.json")
    consumer_timing = load(directory / "c/FINAL_TIMING.json")
    metrics = load(directory / "o/METRICS.json")
    observation, sizes, stages = observations(directory / "o")
    interval(timing, end="result_closed_ns", label=label + " full route")
    interval(consumer_timing, end="consumer_record_closed_ns", elapsed="full_turn_wall_ns", label=label + " consumer")
    deadline = row["started_ns"] + 450 * 10**9
    check(row["deadline_ns"] == timing["original_deadline_ns"] == consumer["deadline_ns"] ==
          consumer_timing["original_turn_deadline_ns"] == observation["deadline_ns"] == deadline,
          label + " same original deadline")
    check(timing == row["final_timing"] and timing["result_closed_ns"] < deadline and
          timing["started_ns"] == row["started_ns"], label + " full timing receipt")
    held_cleanup(row["owner_process_cleanup"], row["owner_pid"], label + " actor")
    held_cleanup(consumer["process_cleanup"], consumer["consumer_pid"], label + " CLI")
    binding = load(directory / "c/RUNTIME_BINDING.json")
    check(binding == consumer["runtime_binding"] == row["runtime_binding"] and binding["confirmed"] is True and
          binding["after_stdio_STARTED"] is True and binding["stdio_STARTED"]["pid"] == binding["runtime_pid"] and
          binding["launcher_pid"] == consumer["consumer_pid"] and
          binding["actual_executable"] == binding["expected_executable"] and
          binding["actual_executable_sha256"] == binding["expected_executable_sha256"], label + " live thin binding")
    parent_chain = binding["parent_chain"]
    check(parent_chain[0]["pid"] == binding["runtime_pid"] and
          parent_chain[-1]["pid"] == binding["launcher_pid"] and
          len(parent_chain) - 1 == binding["parent_edges"] <= binding["max_parent_edges"] and
          len({entry["pid"] for entry in parent_chain}) == len(parent_chain), label + " bounded original parent chain")
    check(all(child["parent_pid"] == parent["pid"] and
              child["created_filetime"] >= parent["created_filetime"]
              for child, parent in zip(parent_chain, parent_chain[1:])), label + " parent creation-time ordering")
    check(parent_chain[0]["created_filetime"] == binding["runtime_created_filetime"] and
          parent_chain[-1]["created_filetime"] == binding["launcher_created_filetime"] and
          consumer["popen_ns"] <= binding["stdio_STARTED"]["started_ns"] <= binding["observed_ns"] <=
          binding["proved_ns"] <= binding["actual_image_checked_ns"] <= consumer["process_exit_ns"],
          label + " actual STARTED before held live proof and CLI exit")
    exit_receipt = consumer["runtime_exit"]
    interval(exit_receipt, label=label + " retained thin exit clock")
    check(exit_receipt == row["runtime_exit"] and exit_receipt["confirmed"] is True and
          exit_receipt["exited"] is True and exit_receipt["handle_closed"] is True and
          exit_receipt["original_deadline_ns"] == deadline, label + " retained thin exit")
    check(consumer["process_exit_ns"] <= exit_receipt["started_ns"] <= exit_receipt["closed_ns"] <=
          consumer["cleanup_end_ns"] <= consumer_timing["consumer_record_closed_ns"] <=
          timing["result_closed_ns"], label + " retained thin exit inside complete publication window")
    check(row["owner_close_confirmed"] is True and metrics == row["owner_metrics"] and
          metrics["common"]["runtime_faults"] == [] and row["common_image_faults"] == [] and
          metrics["common"]["render_attempts"] == row["new_renders"] == observation["metrics"]["render_attempts"],
          label + " shared source and render ledger")
    raw_stdout = read(directory / "c/stdout.raw.bin")
    events = [json.loads(line) for line in raw_stdout.splitlines()]
    saved = [json.loads(line) for line in read(directory / "c/events.jsonl").splitlines()]
    check(len(raw_stdout) == consumer["stdout_bytes"] == consumer["stdout_raw_bytes"] and
          sha(raw_stdout) == consumer["stdout_raw_sha256"] and len(saved) == len(events),
          label + " literal raw stdout and archive count")
    for raw_line, event, archived in zip(raw_stdout.splitlines(keepends=True), events, saved):
        logged = archived["event"]
        if logged.get("item", {}).get("redacted"):
            check(logged["item"]["type"] == event["item"]["type"] and
                  logged["raw_sha256"] == sha(raw_line) and logged["raw_bytes"] == len(raw_line),
                  label + " redacted event raw digest and bytes")
        else:
            check(logged == event, label + " parsed event matches actual stdout")
    usages = [event["usage"] for event in events if event["type"] == "turn.completed"]
    check(len(usages) == 1 and usages == consumer["raw_usage_events"] == row["raw_usage_events"] and
          usages[0] == consumer["usage"], label + " complete raw usage retained")
    calls = [event["item"] for event in events if event["type"] == "item.completed" and
             event.get("item", {}).get("type") == "mcp_tool_call"]
    check(len(calls) == row["actual_tool_calls"] == metrics["tool_attempts"] <= 12, label + " exact tool count")
    tool_stats = load(directory / "o/TOOLS.json")
    check(len(tool_stats["tools"]) == len(calls), label + " all tool rows")
    owner_wire = 0
    mismatches = []
    python_errors = []
    python_code_bytes = 0
    intervals = []
    cli_images = Counter()
    image_events_bytes = 0
    public_tool_text = 0
    png_hashes = {frame["PNG_sha256"] for frame in observation["frames"]}
    png_sizes_by_hash = {frame["PNG_sha256"]: frame["PNG_bytes"] for frame in observation["frames"]}
    for index, (item, receipt) in enumerate(zip(calls, tool_stats["tools"]), 1):
        tool_folder = directory / "o" / ("tool_" + str(index).zfill(2))
        request = load(tool_folder / "REQUEST.json")
        response = load(tool_folder / "RESPONSE.json")
        check(item["tool"] == request["params"]["name"] == receipt["name"] and
              item["arguments"] == request["params"]["arguments"], label + " tool request arguments")
        counts = content_counts(response["result"]["content"])
        check(counts == receipt["content_metrics"] and receipt["response_bytes"] == len(wire(response)),
              label + " actual owner response bytes")
        interval(receipt, label=label + " tool clock")
        check(consumer["prompt_submitted_ns"] <= receipt["started_ns"] <= receipt["closed_ns"] <=
              consumer["final_received_ns"], label + " tool inside prompt/final window")
        intervals.append((receipt["started_ns"], receipt["closed_ns"]))
        owner_wire += len(wire(response))
        if item["tool"] == "execute_python":
            python_code_bytes += len(item["arguments"]["code"].encode("utf-8"))
            python_response = json.loads(response["result"]["content"][0]["text"])
            if python_response["error"] is not None:
                python_errors.append({"attempt": index, **python_response["error"]})
        if item.get("result") is None:
            mismatches.append({"attempt": index, "CLI_status": item["status"], "owner_isError": response["result"]["isError"],
                "owner_text_bytes": counts["text_UTF8_bytes"], "CLI_result": None})
        else:
            check(item["result"]["content"] == response["result"]["content"], label + " actual CLI content parity")
            if response["result"]["isError"] or item["status"] != "completed":
                mismatches.append({"attempt": index, "CLI_status": item["status"], "CLI_error": item.get("error"),
                    "owner_isError": response["result"]["isError"], "owner_text_bytes": counts["text_UTF8_bytes"],
                    "CLI_content_preserved": True, "frozen_binding_outcome": "CLI_result_differs_from_owner"})
            seen = content_counts(item["result"]["content"])
            add_counts(cli_images, seen)
            public_tool_text += seen["text_UTF8_bytes"]
            check(set(seen["PNG_sha256"]).issubset(png_hashes), label + " image generated in this slot")
            if seen["image_blocks"]:
                raw_event = next(raw for raw in raw_stdout.splitlines(keepends=True)
                    if json.loads(raw).get("type") == "item.completed" and
                    json.loads(raw).get("item", {}).get("id") == item["id"])
                image_events_bytes += len(raw_event)
    check(len(mismatches) == (1 if row["execution_state"] == "failed" else 0), label + " failed envelopes preserved")
    ordered = sorted(intervals)
    check(all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:])), label + " disjoint tool intervals")
    tool_ns = sum(end - start for start, end in intervals)
    gaps = []
    cursor = consumer["prompt_submitted_ns"]
    for start, end in ordered:
        gaps.append({"started_ns": cursor, "closed_ns": start, "elapsed_ns": start - cursor})
        cursor = end
    gaps.append({"started_ns": cursor, "closed_ns": consumer["final_received_ns"],
                 "elapsed_ns": consumer["final_received_ns"] - cursor})
    gap_ns = sum(gap["elapsed_ns"] for gap in gaps)
    check(gap_ns + tool_ns == consumer["prompt_to_final_ns"], label + " exact tool/outside-tool partition")

    constructions = load(directory / "o/IMAGE_CONSTRUCTIONS.json")
    constructed = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0)
    encoding_stages = Counter()
    for receipt in constructions["constructed"]:
        check(receipt["constructed"] is True, label + " monotonic actual construction")
        interval(receipt, label=label + " helper clock")
        constructed.update({"image_blocks": 1, "PNG_bytes": receipt["PNG_bytes_read"],
            "base64_chars": receipt["base64_chars"], "image_block_JSON_bytes": receipt["image_block_JSON_bytes"] or 0})
        check(receipt["PNG_sha256"] in png_hashes, label + " constructed current PNG")
        check(receipt["PNG_bytes_read"] == png_sizes_by_hash[receipt["PNG_sha256"]] and
              receipt["base64_chars"] == 4 * ((receipt["PNG_bytes_read"] + 2) // 3),
              label + " independently sized actual constructed PNG/base64")
        for stage, value in receipt["stages"].items():
            interval(value, label=label + " encoding " + stage)
            encoding_stages[stage] += value["elapsed_ns"]
    check(constructed["image_blocks"] == metrics["constructed_image_blocks"] and
          constructed["PNG_bytes"] == metrics["constructed_PNG_bytes"] and
          constructed["base64_chars"] == metrics["constructed_base64_chars"], label + " construction totals")
    check(cli_images["image_blocks"] == consumer["public_image_count"] == metrics["server_socket_sent_image_blocks"] and
          cli_images["PNG_bytes"] == consumer["public_image_bytes"] == metrics["server_socket_sent_PNG_bytes"] and
          cli_images["base64_chars"] == consumer["base64_bytes"] == metrics["server_socket_sent_base64_chars"],
          label + " sent and CLI actual image totals")
    stdio_tx = stdio_rx = tcp_tx = tcp_rx = 0
    for path in (directory / "c/attachments").glob("bridge_*/*/TX.bin"):
        stdio_tx += len(read(path))
    for path in (directory / "c/attachments").glob("bridge_*/*/RX.bin"):
        stdio_rx += len(read(path))
    transport = load(directory / "o/TRANSPORT.json")
    sent_counts = Counter()
    for number, record in enumerate(transport, 1):
        folder = directory / "o" / ("rpc_" + str(number).zfill(3))
        tx, rx = read(folder / "TCP_TX.bin"), read(folder / "TCP_RX.bin")
        request, reply = json.loads(tx), json.loads(rx)
        check(request["request_id"] == reply["request_id"] and reply["ok"] is True and
              record["send_confirmed"] is True and record["send_error"] is None, label + " actual TCP receipts")
        check(record["request_bytes"] == len(tx) and record["outer_TCP_JSON_bytes"] == len(rx), label + " TCP bytes")
        counts = content_counts(reply["result"].get("result", {}).get("content", []))
        check(counts == record["content_metrics"], label + " transport content count")
        add_counts(sent_counts, counts)
        tcp_tx += len(tx)
        tcp_rx += len(rx)
    check(stdio_tx == consumer["MCP_stdio_TX_bytes"] and stdio_rx == consumer["MCP_stdio_RX_bytes"] ==
          metrics["server_socket_sent_MCP_JSON_bytes"] and tcp_tx == metrics["server_socket_request_bytes"] and
          tcp_rx == metrics["server_socket_sent_outer_TCP_JSON_bytes"], label + " complete wire totals")
    check(sent_counts["image_blocks"] == cli_images["image_blocks"] and
          sent_counts["text_UTF8_bytes"] == metrics["server_socket_sent_text_UTF8_bytes"], label + " same layer counters")
    archive = load(directory / "c/ARCHIVE.json")
    zip_originals(archive["archive"], archive["archive_sha256"], archive["archive_bytes"],
                  archive["source_files_sha256"], directory / "c", label + " consumer")
    originals = result["originals"]
    zip_originals(originals["path"], originals["sha256"], originals["bytes"],
                  originals["members_sha256"], directory, label + " full route")
    errors = [event for event in events if event["type"] in ("error", "turn.failed")]
    stderr = read(directory / "c/stderr.raw.bin").decode("utf-8")
    warnings = [line for line in stderr.splitlines() if "fallback model metadata" in line]
    check(len(warnings) == 2, label + " fallback model metadata retained")
    check(consumer["input_sha256"] == sha(read(BATCH / "inputs/PROMPT.txt")), label + " common prompt")
    sizes.update({"stdout_raw_bytes": len(raw_stdout), "events_JSONL_bytes": len(read(directory / "c/events.jsonl")),
        "MCP_tool_response_JSON_bytes": owner_wire, "MCP_stdio_TX_bytes": stdio_tx, "MCP_stdio_RX_bytes": stdio_rx,
        "outer_TCP_TX_bytes": tcp_tx, "outer_TCP_RX_bytes": tcp_rx,
        "CLI_image_completed_event_bytes": image_events_bytes,
        "owner_sent_tool_text_bytes": sent_counts["text_UTF8_bytes"], "CLI_tool_text_bytes": public_tool_text,
        "agent_public_text_bytes": consumer["public_text_bytes"], "final_text_bytes": consumer["output_text_bytes"],
        "input_prompt_bytes": consumer["input_text_bytes"], "submitted_Python_code_bytes": python_code_bytes,
        "CONSUMER_JSON_bytes": len(read(directory / "c/CONSUMER.json")),
        "RESULT_JSON_bytes": len(read(directory / "RESULT.json")),
        "consumer_ZIP_bytes": archive["archive_bytes"], "route_ZIP_bytes": originals["bytes"]})
    return {"slot": label, "group": row["group"], "execution_state": row["execution_state"],
        "accepted_success": timing["accepted_success"], "full_route_ns": timing["elapsed_ns"],
        "started_ns": timing["started_ns"], "closed_ns": timing["result_closed_ns"],
        "consumer_full_ns": consumer_timing["full_turn_wall_ns"], "prompt_to_final_ns": consumer["prompt_to_final_ns"],
        "owner_tools_ns": tool_ns, "outside_owner_tools_prompt_to_final_ns": gap_ns, "outside_tool_gaps": gaps,
        "startup_to_prompt_ns": consumer["prompt_submitted_ns"] - row["started_ns"],
        "final_to_route_close_ns": timing["result_closed_ns"] - consumer["final_received_ns"],
        "stage_ns": stages, "encoding_stage_ns": dict(encoding_stages), "render_attempts": row["new_renders"],
        "tool_calls": len(calls), "constructed": dict(constructed), "CLI_images": dict(cli_images),
        "bytes": sizes, "usage_raw": usages[0], "usage_semantics": consumer["usage_semantics"],
        "failed_envelopes": mismatches, "ordinary_Python_errors": python_errors, "CLI_error_events": errors,
        "orchestrator_retries": 0, "observed_CLI_reconnect_events": sum("Reconnecting" in event.get("message", "") for event in errors),
        "lifecycle": {"actor_held_exit": True, "CLI_held_exit": True, "thin_live_bound": True,
            "thin_retained_exit": True, "thin_exit_code": exit_receipt["exit_code"],
            "normal_stdio_EXIT_receipt": consumer["bridge_cleanup"]["confirmed"]},
        "fallback_metadata_warning_count": len(warnings), "requested_model": consumer["model"],
        "requested_effort": consumer["requested_effort"], "resolved_effort": consumer["resolved_effort"],
        "provider_internal_requests": consumer["provider_requests"], "image_tokens": consumer["image_tokens"],
        "fees": consumer["fees"]}


def totals(rows):
    result = {"slots": len(rows), "full_route_ns": sum(row["full_route_ns"] for row in rows),
              "render_attempts": sum(row["render_attempts"] for row in rows),
              "tool_calls": sum(row["tool_calls"] for row in rows)}
    for field in ("usage_raw", "bytes", "constructed", "CLI_images", "stage_ns", "encoding_stage_ns"):
        count = Counter()
        for row in rows:
            count.update(row[field])
        result[field] = dict(count)
    result["outside_owner_tools_prompt_to_final_ns"] = sum(row["outside_owner_tools_prompt_to_final_ns"] for row in rows)
    result["owner_tools_ns"] = sum(row["owner_tools_ns"] for row in rows)
    return result


def main():
    frozen = load(BATCH / "FROZEN.json")
    for path, wanted in frozen["runtime_sources"].items():
        check(sha(read(path)) == wanted, "unchanged frozen source " + path)
    run = load(BATCH / "r/RUN_RESULT.json")
    plan = load(BATCH / "PLAN.json")
    expected_order = ["N1", "P1", "P2", "N2", "N3", "P3"]
    check([row["slot"] for row in run["records"]] == expected_order and run["actual_routes"] == 6,
          "all six in frozen order")
    rows = [slot(row) for row in run["records"]]
    check(Counter(row["execution_state"] for row in rows) == {"completed": 4, "failed": 2}, "original completion denominator")
    batch = load(BATCH / "r/BATCH_TIMING.json")
    interval(batch, end="RUN_RESULT_closed_ns", label="full sequential batch")
    check(batch["started_ns"] <= rows[0]["started_ns"] and rows[-1]["closed_ns"] <= batch["RUN_RESULT_closed_ns"],
          "batch contains every slot")
    check(all(left["closed_ns"] <= right["started_ns"] for left, right in zip(rows, rows[1:])), "sequential slot windows")
    author_quality = load(BATCH / "admin/QUALITY_AUTHOR.json")
    quality_by_slot = {row["slot_id"]: row for row in author_quality["slots"]}
    eligible = [number for number in (1, 2, 3) if all(quality_by_slot[group + str(number)]["fully_qualified"] for group in "NP")]
    check(eligible == [2] and author_quality["all_six_quality_complete"] is False, "strict three-pair gate remains closed")
    preparation = load(BATCH / "PREPARATION.json")
    preparation_began = load(BATCH / "admin/PREPARATION_BEGAN.json")
    preparation_window_ns = preparation["prepared_ns"] - preparation_began["observed_perf_counter_ns"]
    check(preparation_window_ns >= 0 and preparation["prepared_ns"] <= batch["started_ns"],
          "recorded preparation marker precedes formal batch")
    smoke_attempts = smoke_constructed = smoke_constructed_png_bytes = smoke_constructed_base64 = 0
    for group in "NP":
        obs, sizes, stages = observations(BATCH / "local" / ("render_" + group) / "o")
        metrics = load(BATCH / "local" / ("render_" + group) / "o/METRICS.json")
        smoke_attempts += len(obs["render_attempts"])
        smoke_constructed += metrics["constructed_image_blocks"]
        smoke_constructed_png_bytes += metrics["constructed_PNG_bytes"]
        smoke_constructed_base64 += metrics["constructed_base64_chars"]
    ledger = load(BATCH / "local_ledger/a01/RESULTS.json")
    check(smoke_attempts == preparation["actual_new_rasters"] == 4 and
          smoke_constructed + ledger["actual_constructed_blocks"] == preparation["actual_constructed_image_blocks"] == 8,
          "preparation render/encoding counts separately retained")
    all_totals = totals(rows)
    check(all_totals["render_attempts"] <= 36 and smoke_attempts <= 6 and
          all_totals["render_attempts"] + smoke_attempts <= 42, "formal/preparation raster caps")
    old = load(BATCH.with_name("m4_active_coverage_003") / "RESULTS.json")
    check(old["summary"]["cross_002_003_render_attempts"] == 64, "older 002/003 separate render ledger")
    largest = max(rows, key=lambda row: row["outside_owner_tools_prompt_to_final_ns"])
    result = {"schema": "active-coverage-consumption-001-independent-cost-v1", "status": "passed",
        "review_role": "Author-side independent offline cost and original-evidence recount. Administrator review separate.",
        "checks_passed": CHECKS, "frozen_source_files": len(frozen["runtime_sources"]),
        "FROZEN_sha256": sha(read(BATCH / "FROZEN.json")), "script_sha256": sha(Path(__file__).read_bytes()),
        "execution_denominator": {"planned": 6, "completed": 4, "failed": 2, "not_run": 0},
        "quality_source": {"path": str(BATCH / "admin/QUALITY_AUTHOR.json"), "sha256": sha(read(BATCH / "admin/QUALITY_AUTHOR.json")),
            "groups": author_quality["groups"], "fully_qualified_pair_numbers": eligible},
        "three_quality_complete_pair_gate": False, "paired_median": None, "arm_medians": None,
        "primary_pair_ratios": None, "efficiency_or_usage_win": "not_established",
        "rows": rows, "all_six_totals": all_totals,
        "group_totals_all_three_slots": {group: totals([row for row in rows if row["group"] == group]) for group in "NP"},
        "batch": {**batch, "sum_all_six_slot_ns": all_totals["full_route_ns"],
                  "outside_slot_batch_ns": batch["elapsed_ns"] - all_totals["full_route_ns"]},
        "preparation": {"raster_attempts": smoke_attempts, "smoke_constructed_blocks": smoke_constructed,
            "old_PNG_fault_control_constructed_blocks": ledger["actual_constructed_blocks"],
            "constructed_blocks": preparation["actual_constructed_image_blocks"], "sent_image_blocks": 0,
            "constructed_PNG_bytes": smoke_constructed_png_bytes + ledger["actual_constructed_PNG_bytes"],
            "smoke_constructed_base64_chars": smoke_constructed_base64,
            "old_PNG_fault_constructed_base64_chars": sum(
                case["metrics"]["constructed_base64_chars"] for case in ledger["cases"]),
            "recorded_wall_window": {"started_ns": preparation_began["observed_perf_counter_ns"],
                "prepared_ns": preparation["prepared_ns"], "elapsed_ns": preparation_window_ns,
                "unmeasured_before_marker": preparation_began["unmeasured_bootstrap"],
                "scope": "Recorded preparation wall time including implementation, local controls, review and coordination."},
            "real_model_sessions": 0, "timing_scope": preparation["controller_bootstrap_scope"]},
        "older_002_003_raster_attempts_separate": 64,
        "new_task_raster_attempts_including_preparation": all_totals["render_attempts"] + smoke_attempts,
        "orchestrator_reruns": 0, "observed_CLI_reconnect_events": sum(row["observed_CLI_reconnect_events"] for row in rows),
        "largest_observed_cost_window": {"slot": largest["slot"],
            "outside_owner_tools_prompt_to_final_ns": largest["outside_owner_tools_prompt_to_final_ns"],
            "owner_tools_ns": largest["owner_tools_ns"], "full_route_ns": largest["full_route_ns"],
            "interpretation": "Observed task round-trip/generation/transport interval outside owned tool execution. Internal provider or model latency is not separately measured."},
        "unknown": ["Actual resolved backend model and effort", "Provider-internal raw request count and interrupted-stream usage coverage",
            "Image-token breakdown, cash fees and initial controller bootstrap/freeze-check cost",
            "Normal EOF receipt for each thin client. Live held-handle binding and actual exit are separately confirmed."],
        "inputs_sha256": dict(sorted(INPUTS.items()))}
    (HERE / "COST_INDEPENDENT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report(result)
    print(json.dumps({"checks_passed": CHECKS, "slots": 6, "render_attempts": all_totals["render_attempts"],
        "tools": all_totals["tool_calls"], "images": all_totals["CLI_images"].get("image_blocks", 0),
        "quality_complete_pairs": eligible, "median_gate": False}))


def report(result):
    lines = ["# 六槽完整成本的独立复核", "",
        f"标准库离线复核通过 {result['checks_passed']} 项，冻结的 {result['frozen_source_files']} 份来源保持原字节。六槽全部计入，原执行口径为 4 completed、2 failed、0 not_run。作者质量记录中 N 为 1/3 完整合格，P 为 3/3，只有第 2 对完整合格。三对准入未成立，配对比值、中位数及收益结论留空。", "",
        "## 所有六槽的实际成本", "",
        "| 槽 | 原执行状态 | 完整秒 | prompt 到 final 秒 | 实际工具秒 | 工具外窗口秒 | render | tools | CLI 图片 | PNG 传输字节 | input | cached | output |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        usage = row["usage_raw"]
        lines.append(f"| {row['slot']} | {row['execution_state']} | {row['full_route_ns']/1e9:.7f} | {row['prompt_to_final_ns']/1e9:.7f} | {row['owner_tools_ns']/1e9:.7f} | {row['outside_owner_tools_prompt_to_final_ns']/1e9:.7f} | {row['render_attempts']} | {row['tool_calls']} | {row['CLI_images'].get('image_blocks',0)} | {row['CLI_images'].get('PNG_bytes',0)} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} |")
    total = result["all_six_totals"]
    lines += ["", f"完整顺序批次至 RUN_RESULT 写关为 {result['batch']['elapsed_ns']/1e9:.7f} 秒，六槽完整窗口之和为 {total['full_route_ns']/1e9:.7f} 秒，余下批次开销为 {result['batch']['outside_slot_batch_ns']/1e6:.4f} 毫秒。失败槽保留完整耗时、模型公开 usage、实际渲染及全部原件。", "",
        "每槽从启动前到 CLI、actor 和已绑定薄客户端实际结束、ZIP、输入/结果回读及写关。原始 450 秒绝对期限在各层一致。六个 CLI、六个 actor 持有原进程句柄清理确认，六个真实 STARTED 后绑定的薄客户端均通过创建时间、父链及基础解释器校验，并由保留句柄确认退出和关闭。薄客户端均以 exit1 结束，正常 EXIT/EOF 回执仍为 unknown。", "",
        "## 图片、数组与字节", "",
        f"正式实际渲染 {total['render_attempts']} 次、工具 {total['tool_calls']} 次。当前会话实际构造图片 {total['constructed']['image_blocks']} 块，CLI 收到 {total['CLI_images'].get('image_blocks',0)} 块，原 PNG 载荷 {total['CLI_images'].get('PNG_bytes',0)} 字节、base64 {total['CLI_images'].get('base64_chars',0)} 字符。N 使用实际生成的数组自行计算，三个 N 槽均未请求图片交付，生成图和原数组仍完整留档。", "",
        "| 槽 | 生成 PNG | NPZ | 原始数组载荷 | 工具回复 JSON | stdio TX | stdio RX | 外层 TCP TX | 外层 TCP RX | raw stdout | 图片完成事件字节 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        value = row["bytes"]
        lines.append(f"| {row['slot']} | {value['generated_PNG_bytes']} | {value['generated_NPZ_bytes']} | {value['array_payload_bytes']} | {value['MCP_tool_response_JSON_bytes']} | {value['MCP_stdio_TX_bytes']} | {value['MCP_stdio_RX_bytes']} | {value['outer_TCP_TX_bytes']} | {value['outer_TCP_RX_bytes']} | {value['stdout_raw_bytes']} | {value['CLI_image_completed_event_bytes']} |")
    lines += ["", "各传输层单列。CLI 图片事件按唯一完成事件计一次，原 stdout 按实际字节核验，JSONL 解析记录另存。全部 PNG、NPZ、数组原始载荷、帧元数据及两级 ZIP 的成员哈希已逐项回读。数组载荷是 ndarray 字节，进程 RSS 未测。", "",
        "准备阶段实际渲染 4 次、构造 8 块，其中旧 PNG 故障控制 4 块、新渲染烟测 4 块，网络图片发送 0、真实模型 0。本任务新增渲染合计 28/42。旧 002/003 累计 64 次沿原独立账本保留。", "",
        f"已登记准备墙钟为 {result['preparation']['recorded_wall_window']['elapsed_ns']/1e9:.7f} 秒，范围包含实现、本地控制、审查及协调。登记起点之前已有的上下文审查和编辑未计时。", "",
        "## 失败和成本窗口", "",
        "两次普通 Python 错误均由原工具正文中的 error 字段提取。", ""]
    for row in result["rows"]:
        for error in row["ordinary_Python_errors"]:
            lines += [f"{row['slot']} 第 {error['attempt']} 次工具返回 {error['type']}，消息为 `{error['message']}`。", ""]
    lines += ["原 MCP 返回 isError=true，CLI 将相应工具投影为 status=failed、error=null，并完整保留相同 content。冻结的业务原件绑定器随后记录不匹配，原失败结论保留。N3 另出现一次 CLI 内部 Reconnecting 事件，后续仍有最终回答和终止 usage。外层编排重跑为 0，provider 内部请求数及中断流 usage 覆盖仍未知。", ""]
    largest = result["largest_observed_cost_window"]
    lines += [f"最大的已测成本窗口在 {largest['slot']}。prompt 到最终回答期间，实际工具执行合计 {largest['owner_tools_ns']/1e9:.7f} 秒，其余工具外窗口合计 {largest['outside_owner_tools_prompt_to_final_ns']/1e9:.7f} 秒。原生路线分别提交多段独立发现、几何/像素计算代码，P 路线各用一次主动事实入口。当前最主要的任务成本落在这些工具外任务往返窗口，内部模型生成、provider 执行与网络部分尚无法单独拆分。", "",
        "实际 stage 时钟覆盖输入驻留、依赖、索引、各图渲染、PNG/NPZ、像素与观察，编码子阶段另列于 JSON。这些阶段与完整槽时间具有包含关系，汇总时保持各自口径。", "",
        "## 结论边界", "",
        "六槽原始 usage 全量照录，缓存、cache-write 与 reasoning 字段也保留。实际 resolved 模型/effort、provider 内部请求数、image tokens、现金费用及初始控制器启动和冻结检查未测。源码、提示词、阈值与失败结论保持冻结版本，独立成本复核与作者质量评分、管理员终审分别留存。", ""]
    (HERE / "COST_INDEPENDENT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
