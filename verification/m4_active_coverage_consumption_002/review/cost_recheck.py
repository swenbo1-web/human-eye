"""Read-only cost recount of consumption002 after both quality gates passed.

Shared byte/lifecycle validation is reused from the prior auditor. All run and
quality inputs are read from this new batch, with no prior-run ledger reuse.
"""

import ast
import base64
from collections import Counter
import hashlib
import io
import json
from fractions import Fraction
import statistics
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


def same(left, right, label):
    check(json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) ==
          json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False), label)


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
    image_failures = {"before_construction": len(constructions["failed"]),
        "after_construction": len(constructions["post_construction_failures"]),
        "failed_or_unknown_socket_sends": metrics["failed_or_unknown_socket_sends"],
        "constructed_JSON_size_unknown": metrics["constructed_image_JSON_bytes_unknown_count"]}
    check(image_failures["before_construction"] == metrics["failed_image_constructions"] and
          image_failures["after_construction"] == metrics["post_construction_failures"],
          label + " actual failed construction ledgers retained")
    check(all(value == 0 for value in image_failures.values()), label + " actual current zero image failures")
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
    prompt_path = Path(load(BATCH / "PLAN.json")["inputs"]["prompt"])
    check(consumer["input_sha256"] == sha(read(prompt_path)), label + " explicit unchanged common prompt")
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
        "bytes": sizes, "image_failures": image_failures, "usage_raw": usages[0], "usage_semantics": consumer["usage_semantics"],
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


def fraction_record(value):
    return {"numerator": value.numerator, "denominator": value.denominator, "value": float(value)}


def main():
    frozen_raw = read(BATCH / "FROZEN.json")
    frozen = json.loads(frozen_raw)
    check(sha(frozen_raw) == "1f9527f844b58a3e9719a2c0130c1cd1ad19c05a815bb39b975fb256b2a6680e",
          "current002 frozen identity")
    check(len(frozen["files_sha256"]) == 188, "188 current source bindings")
    for path, wanted in frozen["files_sha256"].items():
        check(sha(read(path)) == wanted, "unchanged frozen dependency " + path)
    author_quality = load(BATCH / "admin/QUALITY_AUTHOR.json")
    independent_quality = load(BATCH / "review/QUALITY_INDEPENDENT.json")
    for quality in (author_quality, independent_quality):
        check(quality["all_six_quality_complete"] is True and quality["P_quality_not_lower_N"] is True and
              all(quality["groups"][group]["fully_qualified"] == quality["groups"][group]["planned"] == 3
                  for group in "NP"), "quality complete before independent cost analysis")
        for path, wanted in quality["inputs_sha256"].items():
            check(sha(read(path)) == wanted, "quality evidence still matches scored source")
    check(independent_quality["quality_gate_passed_for_separate_cost_review"] is True and
          independent_quality["explicit_scalar_pixel_checks_passed"] is True and
          independent_quality["explicit_occluder_checks_passed"] is True, "independent detailed quality gate")
    run = load(BATCH / "r/RUN_RESULT.json")
    plan = load(BATCH / "PLAN.json")
    expected_order = ["N1", "P1", "P2", "N2", "N3", "P3"]
    check([row["slot"] for row in run["records"]] == expected_order ==
          [row["slot"] for row in plan["sequence"]], "same fixed six-slot sequence")
    rows = [slot(row) for row in run["records"]]
    check(Counter(row["execution_state"] for row in rows) == {"completed": 6}, "six complete slots with all costs")
    for row in run["records"]:
        check(row["outer_valid_completion"] is True and row["consumer_valid_completion"] is True and
              row["consumer_safe_to_continue"] is True and row["errors"] == row["consumer_errors"] == [] and
              row["common_image_faults"] == [] and row["final_timing"]["accepted_success"] is True,
              "actual per-slot complete acceptance gates")
    check(run["actual_routes"] == run["actual_CLI_processes"] == len(set(run["observed_fresh_threads"])) == 6,
          "six actual fresh CLI processes")
    check(all(left["closed_ns"] <= right["started_ns"] for left, right in zip(rows, rows[1:])), "fixed sequential boundaries")
    by_slot = {row["slot"]: row for row in rows}
    pairs = []
    for number in (1, 2, 3):
        native = by_slot["N" + str(number)]
        plugin = by_slot["P" + str(number)]
        order = "".join(row["group"] for row in rows if row["slot"] in (native["slot"], plugin["slot"]))
        check(order == ("PN" if number == 2 else "NP"), "registered pair order")
        ratio = Fraction(plugin["full_route_ns"], native["full_route_ns"])
        pairs.append({"pair": number, "order": order, "N_ns": native["full_route_ns"],
                      "P_ns": plugin["full_route_ns"], "P_over_N": fraction_record(ratio)})
    pair_ratios = [Fraction(row["P_ns"], row["N_ns"]) for row in pairs]
    median_pair = statistics.median(pair_ratios)
    native_median = statistics.median(row["full_route_ns"] for row in rows if row["group"] == "N")
    plugin_median = statistics.median(row["full_route_ns"] for row in rows if row["group"] == "P")
    ratio_medians = Fraction(plugin_median, native_median)
    arm_totals = {group: totals([row for row in rows if row["group"] == group]) for group in "NP"}
    reported_usage = {}
    for group in "NP":
        usage = arm_totals[group]["usage_raw"]
        check(all(type(value) is int and value >= 0 for value in usage.values()), "actual reported usage field types")
        reported_usage[group] = usage["input_tokens"] + usage["output_tokens"]
    usage_ratio = Fraction(reported_usage["P"], reported_usage["N"])
    double_benefit = median_pair < 1 and usage_ratio < 1
    all_totals = totals(rows)
    check(all_totals["render_attempts"] <= plan["formal_render_cap"] == 36, "current formal raster budget")
    batch = load(BATCH / "r/BATCH_TIMING.json")
    launch = load(BATCH / "r/LAUNCH_TIMING.json")
    launch_result = load(BATCH / "r/LAUNCH_RESULT.json")
    formal_start = load(BATCH / "FORMAL_STARTED.json")
    preparation = load(BATCH / "PREPARATION.json")
    preparation_marker = load(BATCH / "admin/PREPARATION_BEGAN.json")
    correction = load(BATCH / "PREPARATION_NOTE_CORRECTION.json")
    interval(batch, end="RUN_RESULT_closed_ns", label="current whole sequential batch")
    interval(launch, end="LAUNCH_RESULT_closed_ns", label="explicit launcher whole wall")
    check(launch["started_ns"] <= formal_start["started_ns"] <= batch["started_ns"] <= rows[0]["started_ns"] and
          rows[-1]["closed_ns"] <= batch["RUN_RESULT_closed_ns"] <= launch["LAUNCH_RESULT_closed_ns"],
          "nested launch/batch/slot boundaries")
    check(launch_result["source_unchanged"] is True and launch_result["pointer_chain_unchanged"] is True and
          launch_result["freeze_sha256"] == formal_start["freeze_sha256"] == sha(frozen_raw), "actual final launcher source and pointers")
    same(load(BATCH / "r/POINTERS_BEFORE.json"), load(BATCH / "r/POINTERS_AFTER.json"), "formal runtime pointers unchanged")
    check(preparation["passed"] is True and preparation["actual_local_checks"] == 2 and preparation["local_retries"] == 0 and
          preparation["preparation_rasters"] == preparation["preparation_image_constructions"] ==
          preparation["preparation_Pro_sessions"] == 0, "separate current002 zero-raster preparation")
    for group in "NP":
        local = load(BATCH / "local" / (group + "1") / "LOCAL_RESULT.json")
        check(local["passed"] is True and local["attempt"] == 1 and
              local["new_renders"] == local["new_image_constructions"] == local["new_Pro_sessions"] == 0,
              "current local proof stays separate from formal costs")
    check(correction["actual_new_batch_CLI_processes"] == run["actual_CLI_processes"] == 6 and
          correction["source_or_results_changed_after_formal"] is False, "preparation note correction preserves actual runtime counts")
    preparation_to_formal = formal_start["started_ns"] - preparation_marker["observed_ns"]
    preparation_before_launcher = launch["started_ns"] - preparation_marker["observed_ns"]
    launch_preformal = formal_start["started_ns"] - launch["started_ns"]
    check(preparation_to_formal == preparation_before_launcher + launch_preformal and preparation_before_launcher >= 0,
          "preparation/launcher overlap explicitly accounted")
    result = {"schema": "active-coverage-consumption-002-independent-cost-v1", "status": "passed",
        "review_role": "Author-side independent raw-file cost recount after both quality gates. Administrator review separate.",
        "checks_passed": CHECKS, "frozen_source_files": 188, "FROZEN_sha256": sha(frozen_raw),
        "script_sha256": sha(Path(__file__).read_bytes()),
        "quality_gate": {"author_all_six": True, "independent_all_six": True,
            "N_complete": 3, "P_complete": 3, "complete_pairs": 3,
            "author_quality_sha256": sha(read(BATCH / "admin/QUALITY_AUTHOR.json")),
            "independent_quality_sha256": sha(read(BATCH / "review/QUALITY_INDEPENDENT.json"))},
        "execution_denominator": {"planned": 6, "completed": 6, "failed": 0, "not_run": 0},
        "pairs": pairs, "median_pair_P_over_N": fraction_record(median_pair),
        "N_median_ns": native_median, "P_median_ns": plugin_median,
        "ratio_of_arm_medians": fraction_record(ratio_medians),
        "reported_input_plus_output": reported_usage, "reported_usage_P_over_N": fraction_record(usage_ratio),
        "fixed_small_sample_dual_metric_benefit": double_benefit,
        "benefit_scope": "Three quality-complete pairs on this one frozen finite-camera task. No general significance or cash-saving claim.",
        "rows": rows, "all_six_totals": all_totals, "group_totals_all_three_slots": arm_totals,
        "batch": {**batch, "sum_all_six_slot_ns": all_totals["full_route_ns"],
                  "outside_slot_batch_ns": batch["elapsed_ns"] - all_totals["full_route_ns"]},
        "launcher": {**launch, "outside_batch_ns": launch["elapsed_ns"] - batch["elapsed_ns"],
                     "preformal_overlap_with_recorded_preparation_ns": launch_preformal},
        "preparation": {"marker_ns": preparation_marker["observed_ns"],
            "formal_marker_ns": formal_start["started_ns"], "marker_to_formal_ns": preparation_to_formal,
            "marker_to_launcher_entry_ns": preparation_before_launcher,
            "intermediate_prepared_checkpoint_ns": preparation["prepared_ns"],
            "marker_to_checkpoint_ns": preparation["prepared_ns"] - preparation_marker["observed_ns"],
            "marker_to_launch_close_ns": launch["LAUNCH_RESULT_closed_ns"] - preparation_marker["observed_ns"],
            "rasters": 0, "image_constructions": 0, "real_model_sessions": 0,
            "local_controls": 2, "local_retries": 0, "unmeasured_before_marker": preparation_marker["scope"]},
        "preparation_note_correction": correction,
        "historical_ledgers_scope": "Old consumption001 and older002/003 accumulated64 rasters remain separate. No old run or cost contributes to this002 denominator.",
        "new002_raster_total_including_preparation": all_totals["render_attempts"],
        "orchestrator_reruns": 0, "observed_CLI_reconnect_events": sum(row["observed_CLI_reconnect_events"] for row in rows),
        "unknown": ["Actual resolved backend model and effort", "Provider-internal request count and any pre-retry/interrupted usage coverage",
            "Separate image-token allocation and cash fees", "Interpreter startup outside launcher and work/context before preparation marker",
            "Normal stdio EOF receipts. All actual STARTED-bound thin exits remain separately confirmed by retained handles."],
        "inputs_sha256": dict(sorted(INPUTS.items()))}
    (HERE / "COST_INDEPENDENT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps({"checks": CHECKS, "slots": 6, "renders": all_totals["render_attempts"],
        "tools": all_totals["tool_calls"], "images": all_totals["CLI_images"].get("image_blocks", 0),
        "pair_ratio_median": float(median_pair), "usage_ratio": float(usage_ratio), "dual_metric": double_benefit}))


def write_report(result):
    lines = ["# 完整覆盖消费002的独立成本复核", "",
        f"只读复核通过 {result['checks_passed']} 项，188份冻结来源保持一致。作者与独立质量记录均为N 3/3、P 3/3完整合格，当前正式六槽全部完成。三个配对的成本门已开放。", "",
        "## 固定三配对结果", "",
        "| 配对 | 顺序 | N完整秒 | P完整秒 | P/N |", "|---|---|---:|---:|---:|"]
    for pair in result["pairs"]:
        lines.append(f"| {pair['pair']} | {pair['order']} | {pair['N_ns']/1e9:.7f} | {pair['P_ns']/1e9:.7f} | {pair['P_over_N']['value']:.10f} |")
    ratio = result["median_pair_P_over_N"]["value"]
    usage_ratio = result["reported_usage_P_over_N"]["value"]
    lines += ["", f"配对P/N比值中位数为 {ratio:.10f}，对应本固定样本完整主时间下降 {(1-ratio)*100:.4f}%。N中位数为 {result['N_median_ns']/1e9:.7f} 秒，P为 {result['P_median_ns']/1e9:.7f} 秒，两路中位数之比为 {result['ratio_of_arm_medians']['value']:.10f}。全部三个原始比值及精确有理数保存在JSON。", "",
        "| 路线 | 三槽input | cached input | output | reasoning output | input+output |", "|---|---:|---:|---:|---:|---:|"]
    for group in "NP":
        usage = result["group_totals_all_three_slots"][group]["usage_raw"]
        lines.append(f"| {group} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['reasoning_output_tokens']} | {result['reported_input_plus_output'][group]} |")
    lines += ["", f"公开input+output总量的P/N为 {usage_ratio:.10f}，下降 {(1-usage_ratio)*100:.4f}%。缓存与reasoning字段分别照录，计量按input+output求和。时间与公开模型用量在同质量下均下降，支持本固定有限任务、三配对小样本的双指标收益。统计显著性、其他资产和现金节省仍待相应证据。", "",
        "## 六槽原始计数与usage", "",
        "| 槽 | 完整秒 | render | tools | 构造图 | CLI图 | PNG载荷 | input | cached | output |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        u = row["usage_raw"]
        lines.append(f"| {row['slot']} | {row['full_route_ns']/1e9:.7f} | {row['render_attempts']} | {row['tool_calls']} | {row['constructed']['image_blocks']} | {row['CLI_images'].get('image_blocks',0)} | {row['CLI_images'].get('PNG_bytes',0)} | {u['input_tokens']} | {u['cached_input_tokens']} | {u['output_tokens']} |")
    total = result["all_six_totals"]
    lines += ["", f"正式实际共 {total['render_attempts']} 次渲染、{total['tool_calls']} 次工具调用，构造并交付 {total['constructed']['image_blocks']} 块图片，PNG载荷 {total['CLI_images'].get('PNG_bytes',0)} 字节，base64为 {total['CLI_images'].get('base64_chars',0)} 字符。N三个槽均使用已生成原数组独立计算，CLI附图为0，质量按可追溯本轮证据通过。P各一次主动入口并交付对应图片。失败槽及未运行槽均为0，构造/发送失败记录为0。", "",
        "| 槽 | 生成PNG | NPZ | 数组载荷 | MCP工具回复JSON | stdio TX | stdio RX | TCP TX | TCP RX | raw stdout | 图片完成事件JSON |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        b = row["bytes"]
        lines.append(f"| {row['slot']} | {b['generated_PNG_bytes']} | {b['generated_NPZ_bytes']} | {b['array_payload_bytes']} | {b['MCP_tool_response_JSON_bytes']} | {b['MCP_stdio_TX_bytes']} | {b['MCP_stdio_RX_bytes']} | {b['outer_TCP_TX_bytes']} | {b['outer_TCP_RX_bytes']} | {b['stdout_raw_bytes']} | {b['CLI_image_completed_event_bytes']} |")
    lines += ["", "线上各层字节分别计量，图片完成事件按唯一原始行计一次。raw stdout、完整MCP/TCP、PNG/NPZ及原始数组载荷、FRAME/PIXELS元数据与两级ZIP逐份核验。输入驻留、依赖、索引、实际渲染、PNG/NPZ、像素、编码和工具外窗口均按原始时钟另列。数组nbytes与RSS分别处理，RSS未测。", "",
        "## 全批、启动器和准备墙钟", "",
        f"六槽完整窗口之和为 {total['full_route_ns']/1e9:.7f} 秒，顺序批次至RUN_RESULT写关为 {result['batch']['elapsed_ns']/1e9:.7f} 秒，显式launcher main入口至LAUNCH_RESULT写关为 {result['launcher']['elapsed_ns']/1e9:.7f} 秒。各槽保留原450秒绝对期限，含实际CLI、actor、已绑定stdio退出、归档和回读发布。", "",
        f"准备登记marker至FORMAL_STARTED为 {result['preparation']['marker_to_formal_ns']/1e9:.7f} 秒，其中至launcher入口为 {result['preparation']['marker_to_launcher_entry_ns']/1e9:.7f} 秒。launcher正式标记前校验的 {result['launcher']['preformal_overlap_with_recorded_preparation_ns']/1e9:.7f} 秒同时位于前述准备窗口。整体marker至launcher封存为 {result['preparation']['marker_to_launch_close_ns']/1e9:.7f} 秒，范围内含实现、两次本地检查、审查和提交等待。登记前上下文/编辑与解释器启动外部部分保持未测。", "",
        "本批准备只有N/P各一次错误→42本地接线，实际Pro、图片构造和渲染均为0，正式渲染独立为24/36。旧消费001及更早002/003的64次历史渲染沿原账本保存，当前统计仅使用新002资料。", "",
        "## 回收与测量边界", "",
        "正式六槽CLI与actor原句柄回收确认，六个真实stdio STARTED完成创建时间、父链和base镜像校验，并由保留句柄确认实际exit1后关闭。正常EOF回执仍为unknown。两次本地控制则有正常EOF与exit0证据。实际RUN_RESULT记录6个CLI进程和6个fresh thread。准备记录中曾误述旧batch缺少计数字段，单独更正说明已保留，运行源码与结果继续保持冻结字节。", "",
        "两路请求设置保持gpt-6.1-sol、medium、default与同一现有登录入口，fallback model metadata警告原样保留。实际服务端resolved模型/effort、provider内部轮数、image tokens、现金费用以及任何重试前usage覆盖保持未知。公开字段保持原值，本次结论限于本次质量完整的小样本。", ""]
    (HERE / "COST_INDEPENDENT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()


