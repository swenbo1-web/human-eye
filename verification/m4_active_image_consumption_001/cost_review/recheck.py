"""Offline evidence and cost recount. Imports only the Python standard library."""

import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
CHECKS = 0
INPUTS = {}


def check(value, reason):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(reason)


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


def interval(value, start, end, elapsed, label):
    check(value[start] <= value[end], label + " order")
    check(value[end] - value[start] == value[elapsed], label + " subtraction")


def cleanup(value, pid, label):
    interval(value, "started_ns", "closed_ns", "elapsed_ns", label)
    check(value["pid"] == pid and value["confirmed"] is True and value["reaped"] is True,
          label + " original PID reaped")
    check(value["process_handle_closed"] is True and value["exit_code"] == 0 and
          value["kill_requested"] is False and value["errors"] == [], label + " clean original handle")
    check(value["pipes_closed"] == {"stdin": True, "stdout": True, "stderr": True}, label + " pipes")


def block_counts(content, expected):
    counts = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0, text_UTF8_bytes=0)
    image_hashes = []
    refs = []
    previous_label = None
    for block in content:
        if block["type"] == "text":
            counts["text_UTF8_bytes"] += len(block["text"].encode("utf-8"))
            previous_label = block["text"]
        elif block["type"] == "image":
            check(set(block) == {"type", "data", "mimeType"} and block["mimeType"] == "image/png",
                  "standard public ImageContent")
            raw = base64.b64decode(block["data"], validate=True)
            image_sha = sha(raw)
            matches = [ref for ref, image in expected.items() if image["sha256"] == image_sha]
            check(len(matches) == 1, "image belongs to original opaque input")
            ref = matches[0]
            check(previous_label == ref + " (512x512, image/png)", "opaque label immediately precedes its image")
            check(raw == expected[ref]["raw"] and len(raw) == expected[ref]["PNG_bytes"], "unchanged PNG payload")
            check(raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (512, 512),
                  "PNG signature and 512 dimensions")
            check(base64.b64encode(raw).decode("ascii") == block["data"], "canonical original-byte base64")
            counts["image_blocks"] += 1
            counts["PNG_bytes"] += len(raw)
            counts["base64_chars"] += len(block["data"])
            counts["image_block_JSON_bytes"] += len(wire(block)) - 1
            image_hashes.append(image_sha)
            refs.append(ref)
            previous_label = None
        else:
            raise ValueError("unexpected public content type")
    return dict(counts, PNG_sha256=image_hashes), refs


def check_zip(path, expected_sha, expected_bytes, members, base, label):
    raw = read(path)
    check(sha(raw) == expected_sha and len(raw) == expected_bytes, label + " archive bytes/hash")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        check(len(names) == len(set(names)) and set(names) == set(members), label + " exact archive member inventory")
        for name, expected_hash in members.items():
            archived = archive.read(name)
            actual = read(base / name)
            check(archived == actual and sha(actual) == expected_hash, label + " original member " + name)
    return len(raw)


def construction_receipts(rows, expected, label):
    totals = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0,
                     total_ns=0, read_ns=0, validate_decode_ns=0, encode_ns=0)
    refs = []
    for receipt in rows:
        ref = receipt["ref"]
        image = expected[ref]
        check(receipt["constructed"] is True and receipt["PNG_sha256"] == image["sha256"] and
              receipt["PNG_bytes_read"] == image["PNG_bytes"], label + " constructed original bytes")
        interval(receipt, "started_ns", "closed_ns", "elapsed_ns", label + " construction")
        check(receipt["decoded"]["width"] == receipt["decoded"]["height"] == 512,
              label + " decoded dimensions")
        raw = image["raw"]
        encoded = base64.b64encode(raw).decode("ascii")
        block = {"type": "image", "data": encoded, "mimeType": "image/png"}
        check(receipt["base64_chars"] == len(encoded) and
              receipt["image_block_JSON_bytes"] == len(wire(block)) - 1, label + " measured encoding bytes")
        for stage, value in receipt["stages"].items():
            interval(value, "started_ns", "closed_ns", "elapsed_ns", label + " " + stage)
            check(receipt["started_ns"] <= value["started_ns"] <= value["closed_ns"] <= receipt["closed_ns"],
                  label + " nested construction stage")
            totals[stage + "_ns"] += value["elapsed_ns"]
        totals["total_ns"] += receipt["elapsed_ns"]
        totals["image_blocks"] += 1
        totals["PNG_bytes"] += len(raw)
        totals["base64_chars"] += len(encoded)
        totals["image_block_JSON_bytes"] += len(wire(block)) - 1
        refs.append(ref)
    check(refs == ["view-a", "view-b"], label + " image order")
    return dict(totals)


def normalized_cli(argv):
    normalized = []
    position = 0
    while position < len(argv):
        token = argv[position]
        if token in ("-C", "-o"):
            normalized.extend([token, "<route-local-path>"])
            position += 2
        elif token == "-c" and argv[position + 1].startswith("mcp_servers.arm_engine="):
            normalized.extend([token, "<route-MCP-endpoint-and-tools>"])
            position += 2
        else:
            normalized.append(token)
            position += 1
    return normalized


def recount_route(directory, expected, formal):
    result = load(directory / "RESULT.json")
    timing = load(directory / "FINAL_TIMING.json")
    consumer = load(directory / "c/CONSUMER.json")
    consumer_timing = load(directory / "c/FINAL_TIMING.json")
    metrics = load(directory / "o/METRICS.json")
    constructions = load(directory / "o/IMAGE_CONSTRUCTIONS.json")
    owner_close = load(directory / "o/CLOSE.json")
    identity = load(directory / "o/IDENTITY.json")
    endpoint = load(directory / "ENDPOINT.json")
    config = load(directory / "ACTOR_CONFIG.json")
    label = str(directory.relative_to(BATCH))
    route = result["group"]
    check(route == directory.name == identity["group"] == config["group"], label + " route binding")
    check(result["execution_kind"] == consumer["execution_kind"] == ("provider" if formal else "synthetic_local_process"),
          label + " execution kind")
    check(result["outer_valid_completion"] is True and result["errors"] == result["common_image_faults"] == [] and
          consumer["valid_completion"] is True and consumer["safe_to_continue"] is True and
          consumer["errors"] == consumer["unexpected_tool_deviations"] == consumer["bridge_protocol_errors"] == [],
          label + " recorded valid completion")
    deadline = result["deadline_ns"]
    check(deadline - result["started_ns"] == 450 * 10**9, label + " original 450 seconds")
    check(all(value == deadline for value in (
        timing["original_deadline_ns"], consumer["deadline_ns"], consumer["episode_deadline_ns"],
        consumer_timing["original_turn_deadline_ns"], consumer_timing["episode_deadline_ns"],
        config["worker_deadline_ns"], endpoint["chain_deadline_ns"], identity["worker_deadline_ns"])),
        label + " inherited absolute deadline")
    interval(timing, "started_ns", "result_closed_ns", "elapsed_ns", label + " full route")
    interval(consumer_timing, "started_ns", "consumer_record_closed_ns", "full_turn_wall_ns", label + " consumer close")
    check(timing["started_ns"] == result["started_ns"] and timing["accepted_success"] is True and
          result["started_ns"] <= consumer["started_ns"] <= consumer["popen_ns"] <=
          consumer["prompt_write_started_ns"] <= consumer["prompt_submitted_ns"] <= consumer["final_received_ns"] <=
          consumer["turn_completed_ns"] <= consumer["process_exit_ns"] <= consumer["cleanup_end_ns"] <=
          consumer_timing["consumer_record_closed_ns"] <= result["owner_process_cleanup"]["closed_ns"] <=
          timing["result_closed_ns"] < deadline, label + " complete chronological window")
    check(consumer["wall_ns"] == consumer["cleanup_end_ns"] - consumer["started_ns"] and
          consumer["prompt_to_final_ns"] == consumer["final_received_ns"] - consumer["prompt_submitted_ns"],
          label + " consumer time subtractions")
    cleanup(consumer["process_cleanup"], consumer["consumer_pid"], label + " CLI cleanup")
    owner_pid = result["owner_pid"]
    check(owner_pid == identity["actor_pid"] == endpoint["actor_pid"] == owner_close["actor_pid"],
          label + " original actor PID")
    cleanup(result["owner_process_cleanup"], owner_pid, label + " actor cleanup")
    check(owner_close["confirmed"] is True and owner_close["server_thread_stopped"] is True and
          owner_close["errors"] == [] and owner_close["metrics"] == metrics, label + " held owner close")

    event_bytes = read(directory / "c/events.jsonl")
    events = [json.loads(line) for line in event_bytes.splitlines()]
    check([row["perf_ns"] for row in events] == sorted(row["perf_ns"] for row in events), label + " event order")
    check(not any(row["event"].get("item", {}).get("redacted") for row in events), label + " no unretained event body")
    completed = [row for row in events if row["event"].get("type") == "item.completed" and
                 row["event"].get("item", {}).get("type") == "mcp_tool_call"]
    calls = [{"perf_ns": row["perf_ns"], **row["event"]} for row in completed]
    check(calls == consumer["tool_calls"], label + " CLI event tool projection")
    count = len(calls)
    check(count <= 4 and count == result["actual_tool_calls"] == metrics["tool_attempts"], label + " actual tool count")
    expected_names = (["read_image", "read_image"] if route == "N" else ["human_eye_image_observe"])
    if not formal:
        expected_names.insert(0, "execute_python")
    check([row["item"]["tool"] for row in calls] == expected_names, label + " actual native or observation outlet")
    tools = load(directory / "o/TOOLS.json")
    check(tools["calls"] == len(tools["tools"]) == count and tools["tools"] == metrics["tools"], label + " owner tool rows")
    owner_responses = {}
    image_order = []
    cli_counts = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0, text_UTF8_bytes=0)
    tool_wire_bytes = 0
    for number, (call, receipt) in enumerate(zip(calls, tools["tools"]), 1):
        folder = directory / "o" / ("tool_" + str(number).zfill(2))
        request = load(folder / "REQUEST.json")
        response = load(folder / "RESPONSE.json")
        copied = directory / "c/owner_turn" / folder.name
        for filename in ("REQUEST.json", "RESPONSE.json", "RECEIPT.json"):
            check(read(folder / filename) == read(copied / filename), label + " untouched business source copy")
        item = call["item"]
        check(item["status"] == "completed" and item["error"] is None and
              item["tool"] == request["params"]["name"] == receipt["name"] and
              item["arguments"] == request["params"]["arguments"] and
              item["result"]["content"] == response["result"]["content"] and
              item["result"]["structured_content"] is None and response["result"]["isError"] is False,
              label + " actual CLI/owner business binding")
        counts, refs = block_counts(item["result"]["content"], expected)
        check(counts == receipt["content_metrics"], label + " independent tool content counters")
        interval(receipt, "started_ns", "closed_ns", "elapsed_ns", label + " tool interval")
        check(receipt["response_bytes"] == len(wire(response)), label + " exact tool JSON wire length")
        for key, value in counts.items():
            if key != "PNG_sha256":
                cli_counts[key] += value
        image_order.extend(refs)
        owner_responses[response["id"]] = response
        tool_wire_bytes += len(wire(response))
    check(image_order == ["view-a", "view-b"] and cli_counts["image_blocks"] == 2 and
          cli_counts["PNG_bytes"] == 6699 and cli_counts["base64_chars"] == 8936,
          label + " identical actual image order/payload")
    check(consumer["public_image_count"] == 2 and consumer["public_image_bytes"] ==
          consumer["known_PNG_bytes"] == 6699 and consumer["base64_bytes"] == 8936 and
          consumer["unknown_image_payloads"] == 0, label + " consumer actual image receipt counters")
    image_events = [row for row in completed if any(
        block["type"] == "image" for block in row["event"]["item"]["result"]["content"])]
    image_event_ids = [row["event"]["item"]["id"] for row in image_events]
    check(len(image_event_ids) == len(set(image_event_ids)), label + " unique image-bearing CLI events")
    image_event_bytes = sum(len(wire(row["event"])) if formal else
        len((json.dumps(row["event"], ensure_ascii=False) + "\r\n").encode("utf-8")) for row in image_events)
    for delivery in consumer["image_deliveries"]:
        matching = [row for row in image_events if row["event"]["item"]["id"] == delivery["tool_item_id"]]
        check(len(matching) == 1, label + " image receipt bound to unique actual CLI event")
        event = matching[0]["event"]
        per_event_wire_bytes = len(wire(event)) if formal else len((json.dumps(event, ensure_ascii=False) + "\r\n").encode("utf-8"))
        check(delivery["CLI_completed_event_JSON_line_bytes"] == per_event_wire_bytes,
              label + " per-image event size observation")

    constructions_total = construction_receipts(constructions["constructed"], expected, label)
    check(constructions["failed"] == [] and metrics["failed_image_constructions"] == 0,
          label + " no failed constructions")
    for key, value in (("constructed_image_blocks", constructions_total["image_blocks"]),
                       ("constructed_PNG_bytes", constructions_total["PNG_bytes"]),
                       ("constructed_base64_chars", constructions_total["base64_chars"]),
                       ("constructed_image_block_JSON_bytes", constructions_total["image_block_JSON_bytes"])):
        check(metrics[key] == value, label + " construction metric " + key)
    transport = load(directory / "o/TRANSPORT.json")
    tcp_tx = tcp_rx = mcp_rx = 0
    sent_counts = Counter(image_blocks=0, PNG_bytes=0, base64_chars=0, image_block_JSON_bytes=0, text_UTF8_bytes=0)
    for number, row in enumerate(transport, 1):
        folder = directory / "o" / ("rpc_" + str(number).zfill(3))
        tx = read(folder / "TCP_TX.bin")
        rx = read(folder / "TCP_RX.bin")
        request = json.loads(tx)
        response = json.loads(rx)
        check(response["request_id"] == request["request_id"] and response["ok"] is True,
              label + " actual TCP request/reply")
        check(row["send_confirmed"] is True and row["send_error"] is None and
              row["request_bytes"] == len(tx) and row["outer_TCP_JSON_bytes"] == len(rx), label + " real socket counts")
        public = response["result"]
        counts, refs = block_counts(public.get("result", {}).get("content", []), expected)
        check(row["content_metrics"] == counts and row["MCP_JSON_bytes"] == len(wire(public)),
              label + " socket ImageContent and MCP byte count")
        if public["id"] in owner_responses:
            check(public == owner_responses[public["id"]], label + " owner actual TCP response")
        for key, value in counts.items():
            if key != "PNG_sha256":
                sent_counts[key] += value
        tcp_tx += len(tx)
        tcp_rx += len(rx)
        mcp_rx += len(wire(public))
    bridges = list((directory / "c/attachments").glob("bridge_*"))
    check(len(bridges) == 1, label + " one actual stdio bridge")
    bridge = bridges[0]
    stdio_tx = stdio_rx = 0
    stdio_tools = []
    for folder in sorted(path for path in bridge.iterdir() if path.is_dir()):
        tx = read(folder / "TX.bin")
        request = json.loads(tx)
        stdio_tx += len(tx)
        rx_path = folder / "RX.bin"
        if rx_path.exists():
            rx = read(rx_path)
            response = json.loads(rx)
            stdio_rx += len(rx)
            check(response["id"] == request["id"], label + " actual stdio reply identity")
            if request["method"] == "tools/call":
                check(response == owner_responses[response["id"]] and rx == wire(response),
                      label + " exact image-bearing stdio JSON response")
                stdio_tools.append(response["id"])
        else:
            check("id" not in request, label + " notification needs no response")
    check(len(stdio_tools) == count and set(stdio_tools) == set(owner_responses), label + " all actual stdio tool replies")
    check(stdio_tx == consumer["MCP_stdio_TX_bytes"] and stdio_rx == consumer["MCP_stdio_RX_bytes"] == mcp_rx,
          label + " stdio totals")
    for key, value in sent_counts.items():
        check(metrics["server_socket_sent_" + key] == value, label + " server sent metric " + key)
    check(metrics["server_socket_sent_outer_TCP_JSON_bytes"] == tcp_rx and
          metrics["server_socket_sent_MCP_JSON_bytes"] == mcp_rx and
          metrics["server_socket_request_bytes"] == tcp_tx and metrics["failed_or_unknown_socket_sends"] == 0,
          label + " all socket bytes and sends")
    check(dict(sent_counts) == dict(cli_counts), label + " server/CLI content counts exact parity")

    bridge_cleanup = consumer["bridge_cleanup"]
    check(result["bridge_cleanup"] == bridge_cleanup, label + " same preserved bridge state")
    exit_path = bridge / "EXIT.json"
    if formal:
        check(not exit_path.exists() and bridge_cleanup["confirmed"] is None and
              bridge_cleanup["receipt_status"] == "unknown" and bridge_cleanup["missing_exit_count"] == 1,
              label + " missing normal stdio EXIT preserved as unknown")
    else:
        exit_receipt = load(exit_path)
        check(exit_receipt["normal_exit"] is True and bridge_cleanup["confirmed"] is True,
              label + " local fake normal stdio EXIT")
    completed_usage = [row["event"]["usage"] for row in events if row["event"].get("type") == "turn.completed"]
    check(len(completed_usage) == 1 and completed_usage == consumer["raw_usage_events"] == consumer["usage_rows"],
          label + " actual completed usage event")
    check(consumer["usage"] == completed_usage[0], label + " raw observed usage fields")
    for value in consumer["usage"].values():
        check(type(value) is int and value >= 0, label + " nonnegative observed usage")
    messages = [row["event"]["item"]["text"] for row in events if row["event"].get("type") == "item.completed" and
                row["event"].get("item", {}).get("type") == "agent_message"]
    check(messages[-1] == consumer["final"] and read(directory / "c/final.txt").decode("utf-8") ==
          read(directory / "c/PUBLIC_FINAL.txt").decode("utf-8") == consumer["final"], label + " actual final text")
    check(consumer["public_text_bytes"] == sum(len(text.encode("utf-8")) for text in messages) and
          consumer["output_text_bytes"] == len(consumer["final"].encode("utf-8")), label + " public text bytes")
    rebuilt_stdout = sum(len(wire(row["event"])) for row in events) if formal else sum(
        len((json.dumps(row["event"], ensure_ascii=False) + "\r\n").encode("utf-8")) for row in events)
    check(rebuilt_stdout == consumer["stdout_bytes"], label + " stdout byte counter matches emitter JSON layout")
    if formal:
        check(consumer["argv"] == consumer["frozen_cli_argv"], label + " frozen requested CLI profile")
    else:
        check(consumer["argv"][1:3] == ["-I", "-B"] and
              Path(consumer["argv"][3]).resolve() == BATCH / "fake_cli.py" and
              consumer["argv"][4:] == consumer["frozen_cli_argv"][1:], label + " declared local fake command")
    stderr = read(directory / "c/stderr.raw.bin").decode("utf-8")
    warning_lines = stderr.splitlines()
    fallback = [line for line in warning_lines if "fallback model metadata" in line]
    if formal:
        check(len(fallback) == 2 and consumer["model"] == "gpt-6.1-sol" and
              consumer["requested_effort"] == "medium" and consumer["resolved_effort"] is None,
              label + " fallback metadata and unobserved resolution")
    archive = load(directory / "c/ARCHIVE.json")
    consumer_zip_bytes = check_zip(archive["archive"], archive["archive_sha256"], archive["archive_bytes"],
        archive["source_files_sha256"], directory / "c", label + " consumer ZIP")
    check(archive["business_binding_errors"] == [] and len(archive["owner_attempts"]) == count,
          label + " business archive correspondence")
    originals = result["originals"]
    route_zip_bytes = check_zip(originals["path"], originals["sha256"], originals["bytes"],
        originals["members_sha256"], directory, label + " route ZIP")
    for key in ("new_renders", "Blender_processes", "paid_API_calls"):
        check(result[key] == 0, label + " zero new engine/API action " + key)
    return {"route": route, "scope": "formal_model" if formal else "local_fake",
            "status": "completed", "tools": expected_names, "tool_calls": count,
            "constructed": constructions_total, "socket_sent_and_CLI_received": dict(cli_counts),
            "bytes": {"MCP_tool_response_JSON": tool_wire_bytes, "MCP_stdio_TX": stdio_tx,
                "MCP_stdio_RX": stdio_rx, "outer_TCP_TX": tcp_tx, "outer_TCP_RX": tcp_rx,
                "CLI_stdout_observed": consumer["stdout_bytes"], "CLI_events_archive": len(event_bytes),
                "CLI_image_completed_events_JSON": image_event_bytes,
                "CLI_stderr": len(stderr.encode("utf-8")), "public_messages_text": consumer["public_text_bytes"],
                "final_text": consumer["output_text_bytes"], "input_text": consumer["input_text_bytes"],
                "CONSUMER_JSON": len(read(directory / "c/CONSUMER.json")),
                "RESULT_JSON": len(read(directory / "RESULT.json")),
                "consumer_FINAL_TIMING_JSON": len(read(directory / "c/FINAL_TIMING.json")),
                "route_FINAL_TIMING_JSON": len(read(directory / "FINAL_TIMING.json")),
                "consumer_ZIP": consumer_zip_bytes, "route_ZIP": route_zip_bytes},
            "time_ns": {"route_full": timing["elapsed_ns"], "consumer_full": consumer_timing["full_turn_wall_ns"],
                "consumer_to_cleanup": consumer["wall_ns"], "prompt_to_final": consumer["prompt_to_final_ns"],
                "route_started": result["started_ns"], "route_closed": timing["result_closed_ns"],
                "original_deadline": deadline, "actual_tool_sum": sum(row["elapsed_ns"] for row in tools["tools"])},
            "usage_raw": completed_usage[0], "usage_semantics": consumer["usage_semantics"],
            "profile": {"requested_model": consumer["model"], "requested_effort": consumer["requested_effort"],
                "resolved_effort": consumer["resolved_effort"], "resolved_model": None,
                "normalized_cli": normalized_cli(consumer["argv"]), "fallback_metadata_warnings": fallback},
            "cleanup": {"CLI_held_handle": True, "actor_held_handle": True, "actor_listener": True,
                "stdio_normal_EXIT": bridge_cleanup["confirmed"], "stdio_receipt_status": bridge_cleanup.get("receipt_status"),
                "stdio_PID": load(bridge / "STARTED.json")["pid"]},
            "stderr_lines": warning_lines, "final": consumer["final"],
            "provider_internal_requests": consumer["provider_requests"], "image_tokens": consumer["image_tokens"],
            "fees": consumer["fees"], "provider_retry_observations": consumer["provider_retry_observations"],
            "quality_source_status": result["content_quality"]}


def sum_fields(rows, field):
    total = Counter()
    for row in rows:
        total.update(row[field])
    return dict(total)


def main():
    frozen = load(BATCH / "FROZEN.json")
    plan = load(BATCH / "PLAN.json")
    manifest = load(BATCH / "inputs/IMAGES.json")
    check(len(frozen["runtime_sources"]) == 24, "24 frozen runtime and input sources")
    for path, expected_sha in frozen["runtime_sources"].items():
        check(sha(read(path)) == expected_sha, "unchanged frozen source " + path)
    expected = {}
    for image in manifest["images"]:
        raw = read(BATCH / "inputs" / image["file"])
        check(sha(raw) == image["sha256"] and len(raw) == image["PNG_bytes"], "original frozen PNG")
        expected[image["ref"]] = dict(image, raw=raw)
    check(list(expected) == plan["image_order"] == ["view-a", "view-b"], "shared opaque image order")
    formal_started = load(BATCH / "FORMAL_STARTED.json")
    check(formal_started["source_freeze_sha256"] == sha(read(BATCH / "FROZEN.json")), "formal frozen source binding")
    formal = [recount_route(BATCH / "r" / arm, expected, True) for arm in plan["sequence"]]
    local = [recount_route(BATCH / "local/a01" / arm, expected, False) for arm in plan["sequence"]]
    helper = load(BATCH / "LOCAL_HELPER_CHECK.json")
    check(helper["status"] == "passed", "direct helper preparation passed")
    helper_totals = construction_receipts(helper["images"], expected, "direct helper preparation")
    check(formal[0]["profile"]["normalized_cli"] == formal[1]["profile"]["normalized_cli"],
          "same requested CLI/model/service/authentication profile")
    prompt_raw = read(BATCH / "inputs/PROMPT.txt")
    for arm in plan["sequence"]:
        consumer = load(BATCH / "r" / arm / "c/CONSUMER.json")
        check(consumer["input_sha256"] == sha(prompt_raw) and consumer["input_text_bytes"] == len(prompt_raw),
              "same actual visible prompt")
    run_result = load(BATCH / "r/RUN_RESULT.json")
    check(run_result["actual_routes"] == run_result["planned_routes"] == run_result["planned_user_turns"] == 2,
          "formal denominator two")
    check(sum(row["tool_calls"] for row in formal) == 3 and
          sum(row["socket_sent_and_CLI_received"]["image_blocks"] for row in formal) == 4 and
          sum(row["socket_sent_and_CLI_received"]["PNG_bytes"] for row in formal) == 13398,
          "actual formal tool/image/PNG totals")
    formal_usage = Counter()
    for row in formal:
        formal_usage.update(row["usage_raw"])
    constructed_all = Counter(helper_totals)
    for row in formal + local:
        constructed_all.update(row["constructed"])
    sent_all = sum_fields(formal + local, "socket_sent_and_CLI_received")
    # This cost review leaves content quality to the independent blind review.
    results = {"schema": "active-image-consumption-001-cost-review-v1", "status": "passed",
        "review_kind": "author-side standard-library-only offline evidence and arithmetic audit",
        "administrator_review": "pending", "checks_passed": CHECKS, "source_count": 24,
        "source_freeze_sha256": sha(read(BATCH / "FROZEN.json")), "script_sha256": sha(Path(__file__).read_bytes()),
        "formal": formal, "local_fake": local, "direct_helper_preparation": helper_totals,
        "formal_totals": {"sessions": 2, "user_turns": 2, "completed": 2, "failed": 0, "not_run": 0,
            "tool_calls": sum(row["tool_calls"] for row in formal),
            "constructed": sum_fields(formal, "constructed"),
            "socket_sent_and_CLI_received": sum_fields(formal, "socket_sent_and_CLI_received"),
            "bytes": sum_fields(formal, "bytes"), "observed_completed_usage_fields_sum": dict(formal_usage),
            "route_full_intervals_ns": sum(row["time_ns"]["route_full"] for row in formal),
            "first_route_start_to_last_route_close_ns": formal[-1]["time_ns"]["route_closed"] - formal[0]["time_ns"]["route_started"],
            "prompt_to_final_sum_ns": sum(row["time_ns"]["prompt_to_final"] for row in formal)},
        "preparation_totals": {"real_provider_sessions": 0, "fake_sessions": 2,
            "tool_calls": sum(row["tool_calls"] for row in local),
            "constructed_image_blocks": helper_totals["image_blocks"] + sum(row["constructed"]["image_blocks"] for row in local),
            "constructed_PNG_bytes": helper_totals["PNG_bytes"] + sum(row["constructed"]["PNG_bytes"] for row in local),
            "socket_sent_and_fake_CLI_received": sum_fields(local, "socket_sent_and_CLI_received"),
            "local_route_full_intervals_ns": sum(row["time_ns"]["route_full"] for row in local)},
        "all_observed_constructions": dict(constructed_all), "all_observed_socket_sent": sent_all,
        "new_renders": 0, "Blender_processes": 0, "paid_API_calls": 0,
        "limitations": ["Formal thin stdio normal EXIT receipts are missing in both routes. CLI and actor held-handle cleanup are confirmed.",
            "Requested gpt-6.1-sol medium profile is equal. CLI reports fallback model metadata, actual resolved model and effort unobserved.",
            "Provider-internal request count, image-token breakdown and monetary fees unobserved.",
            "Observed usage sums preserve CLI turn.completed fields and their unconfirmed turn/session semantics.",
            "This two-route transmission qualification supplies no plugin-vs-native task-benefit or speed comparison.",
            "Content quality remains independently reviewed. This script verifies unchanged image-bearing content and records final text."],
        "inputs_sha256": dict(sorted(INPUTS.items()))}
    observation_path = BATCH / "EXIT_OBSERVATION.json"
    if observation_path.exists():
        results["postrun_process_snapshot"] = load(observation_path)
        results["inputs_sha256"] = dict(sorted(INPUTS.items()))
    (HERE / "RESULTS.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report(results)
    print(json.dumps({"status": "passed", "checks_passed": CHECKS,
        "formal_sessions": 2, "formal_tool_calls": 3, "formal_image_blocks": 4,
        "formal_PNG_bytes": 13398, "all_constructed_image_blocks": constructed_all["image_blocks"],
        "formal_stdio_EXIT": "unknown_both"}))


def report(results):
    totals = results["formal_totals"]
    lines = ["# 两路真实图片消费的独立成本复核", "",
        f"离线复核通过 {results['checks_passed']} 项，24 份冻结来源及两张 PNG 均保持原字节。此记录为作者侧成本与传输证据复核，管理员终审待完成。", "",
        "## 实际调用与图片交付", "",
        "正式执行为两个独立真实 CLI 会话、各一个用户轮次。N 实际调用 read_image 两次，P 实际调用 human_eye_image_observe 一次。两路 CLI 的完成事件均保留标准 image content，顺序为 view-a、view-b。每张图片从 helper 构造、服务端原始响应、stdio 原始响应到 CLI 工具事件逐字节绑定。", "",
        "| 范围 | 会话 | 工具调用 | 构造图片块 | 传输图片块 | PNG 载荷字节 | base64 字符 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in results["formal"]:
        count = row["socket_sent_and_CLI_received"]
        lines.append(f"| 正式 {row['route']} | 1 | {row['tool_calls']} | {row['constructed']['image_blocks']} | {count['image_blocks']} | {count['PNG_bytes']} | {count['base64_chars']} |")
    prep = results["preparation_totals"]
    lines += [f"| 准备期纯 helper | 0 | 0 | 2 | 0 | 6699 构造 | 8936 构造 |",
        f"| 准备期本地 fake CLI | 2 个合成会话 | {prep['tool_calls']} | 4 | 4 | 13398 | 17872 |", "",
        "正式合计 4 个图片块、13398 字节 PNG 和 17872 个 base64 字符。连同准备期，实际构造共 10 块，服务端确认发送共 8 块。纯 helper 的 2 块只在本地构造。所有阶段新增光栅、Blender 和付费 API 调用均为 0。", "",
        "## 字节与时界", "",
        "| 正式路线 | 工具回复 JSON | 全部 stdio TX | 全部 stdio RX | 外层 TCP TX | 外层 TCP RX | CLI stdout | 图片完成事件 JSON | 模型公开文字 | 最终文字 | 完整路线秒 | prompt 至最终秒 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in results["formal"]:
        size, timing = row["bytes"], row["time_ns"]
        lines.append(f"| {row['route']} | {size['MCP_tool_response_JSON']} | {size['MCP_stdio_TX']} | {size['MCP_stdio_RX']} | {size['outer_TCP_TX']} | {size['outer_TCP_RX']} | {size['CLI_stdout_observed']} | {size['CLI_image_completed_events_JSON']} | {size['public_messages_text']} | {size['final_text']} | {timing['route_full']/1e9:.7f} | {timing['prompt_to_final']/1e9:.7f} |")
    lines += ["", f"两路完整时界合计 {totals['route_full_intervals_ns']/1e9:.7f} 秒，从第一路启动前到第二路封存结束为 {totals['first_route_start_to_last_route_close_ns']/1e9:.7f} 秒。路线时界包含输入核对、actor/CLI 启动、实际工具、退出、原句柄清理、原始 ZIP、回读和 RESULT 写关。各路沿用启动前登记的原始 450 秒绝对期限，每路工具数均在 4 次以内。FINAL_TIMING 自发布在该回执时界外。", "",
        "helper 的读取、PNG 流验证、base64 编码和构造总时界逐项复算，保存在 RESULTS.json。线上 MCP JSON 字节来自实际 TX/RX 文件。CLI stdout 计数同时由保存事件按对应发出端 JSON 格式重建核对。图片完成事件按唯一 item 计数，P 两张图片共用一次 9393 字节事件。工具引用文字每路 54 字节，模型公开文字包含当路公开说明与最终回答。各传输层分别计量。RESULT、CONSUMER、时界回执及两级 ZIP 字节分别列账，ZIP 每个成员与原件逐一核对。", "",
        "## 公开 usage 和模型设置", "",
        "| 路线 | input_tokens | cached_input_tokens | output_tokens | cache_write_input_tokens | reasoning_output_tokens |", "|---|---:|---:|---:|---:|---:|"]
    for row in results["formal"]:
        usage = row["usage_raw"]
        lines.append(f"| {row['route']} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['cache_write_input_tokens']} | {usage['reasoning_output_tokens']} |")
    lines += ["", "这些字段逐项来自各路唯一 turn.completed 原始事件。缓存字段与 input 字段分别照录。事件字段合计另存，CLI 对 turn/session 口径的限制继续保留。", "",
        "两路请求设置均为 gpt-6.1-sol、medium、default 服务，使用同一 CLI、openai_http 和现有 ChatGPT 登录方式。两路各记录两条 fallback model metadata 警告。实际解析到的模型身份和推理强度没有公开回执，结果保留为未知。另有 PowerShell snapshot 和结束后 rollout flush 警告，原文全部留存。", "",
        "provider 内部原始请求数、独立 image tokens、费用均未测。两个单次路线的时长和 usage 用于交付成本记录，当前资格未建立任务收益比较分母。", "",
        "## 退出证据及回答范围", "",
        "本地 fake CLI 两路均有正常 stdio EXIT 回执。正式两路的 CLI 和 actor 持有原句柄均完成回收、三条管道关闭和句柄关闭，actor 监听线程关闭确认。正式 stdio bridge 的 STARTED 存在，EXIT 均缺失，原记录保留 confirmed=null 与 unknown。后验进程快照即使显示已不存在，也只能补充该时刻状态。", ""]
    for row in results["formal"]:
        lines += [f"{row['route']} 的实际最终回答如下。", "", "> " + row["final"], ""]
    lines += ["正式工具记录均为图片读取，未执行 Python 像素计算。当前复核确认服务端构造与 CLI 接收的真实图片内容，并保留回答供独立盲审。源码中的 content_quality 仍为 unscored。后续任务收益、一般视觉能力、其他场景和默认产品安装效果继续按对应任务验收。", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
