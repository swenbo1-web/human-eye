"""Recompute the fixed nine-cell ledger from sealed originals, using stdlib only.

This program performs file reads, assertions and local report writes. It starts
no process, consumer, model, Blender instance or product service.
"""

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
CELLS = ("N1", "O1", "C1", "O2", "C2", "N2", "C3", "N3", "O3")
SEAL_SHA256 = "c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb"
PLAN_SHA256 = "ef73d9a91d237141f7c90da4685a8207bdaf99fee82e05c19edd4a1af71193f5"
SOURCES = {}
CHECKS = 0


def need(condition, reason):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(reason)


def raw(path):
    data = path.read_bytes()
    try:
        name = path.relative_to(BATCH).as_posix()
    except ValueError:
        name = str(path)
    SOURCES[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return data


def read(path):
    return json.loads(raw(path))


def rows(path):
    return [json.loads(line) for line in raw(path).splitlines() if line]


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def ratio(first, second):
    exact = Fraction(first, second)
    return {"numerator": exact.numerator, "denominator": exact.denominator, "value": float(exact)}


def sum_fields(items, fields):
    return {field: sum(item[field] for item in items) for field in fields}


def classify_stderr(folder):
    data = raw(folder / "stderr.raw.bin")
    received = rows(folder / "stderr_lines.jsonl")
    need(len(received) == len(data.splitlines()), folder.name + " stderr line count")
    lines = []
    for index, line in enumerate(data.splitlines(keepends=True), 1):
        need(received[index - 1]["text"].encode("utf-8") == line, folder.name + " stderr raw/received equality")
        text = line.decode("utf-8", errors="strict").rstrip("\r\n")
        category = "other"
        if "codex_models_manager::model_info" in text and "fallback model metadata" in text:
            category = "metadata_fallback_warn"
        elif "codex_core::shell_snapshot" in text and "Shell snapshot not supported" in text:
            category = "shell_snapshot_warn"
        elif "codex_models_manager::manager" in text and "failed to refresh available models" in text:
            category = "model_refresh_timeout_error"
        elif "codex_analytics::client" in text and "failed to send events request" in text:
            category = "analytics_transport_warn"
        elif "codex_core::responses_retry" in text and "stream disconnected" in text:
            category = "response_stream_retry_warn"
        lines.append({"line": index, "category": category, "text": text,
                      "received_perf_ns": received[index - 1]["perf_ns"],
                      "raw_line_bytes": len(line), "raw_line_including_newline_sha256": hashlib.sha256(line).hexdigest()})
    return {"raw_bytes": len(data), "counts": dict(Counter(line["category"] for line in lines)), "lines": lines,
            "scope": "CLI stderr diagnostics. Metadata refresh child-exit timeouts and analytics transport errors do not attest provider reasoning/API request failure; no per-error blocking span measured."}


def collect_cell(cell, answer):
    folder = BATCH / "cells" / cell
    consumer = read(folder / "CONSUMER.json")
    events = rows(folder / "events.jsonl")
    timing = read(folder / "CELL_FINAL_TIMING.json")
    publication = read(folder / "CELL_TIMING_PUBLICATION.json")
    owner = read(folder / "OWNER_FINISH.json")
    tools = read(folder / "owner" / "TOOLS.json")
    native_events = rows(folder / "owner" / "native" / "WORKER_EVENTS.jsonl")
    identity = read(folder / "owner" / "IDENTITY.json")
    native_close = owner["close"]["native_close"]
    start = timing["cell_started_ns"]
    end = timing["business_receipts_closed_ns"]
    need(timing["full_cell_wall_ns"] == end - start, cell + " full duration")
    need(start <= consumer["started_ns"] <= consumer["popen_ns"] <= consumer["prompt_submitted_ns"]
         <= consumer["final_received_ns"] <= consumer["turn_completed_ns"] <= consumer["process_exit_ns"]
         <= consumer["cleanup_end_ns"] <= owner["close"]["ended_ns"] <= end,
         cell + " inclusive lifecycle order")
    need(publication["business_receipts_closed_ns"] == end, cell + " publication anchor")
    need(publication["timing_receipt_publication_started_ns"] >= end, cell + " publication start")
    need(publication["timing_receipt_publication_ns"] == publication["timing_receipt_publication_closed_ns"]
         - publication["timing_receipt_publication_started_ns"], cell + " publication span")
    need(consumer["wall_ns"] == consumer["cleanup_end_ns"] - consumer["started_ns"], cell + " consumer wall")
    need(consumer["pre_consumer_setup_ns"] == consumer["started_ns"] - start, cell + " setup wall")
    need(consumer["total_task_wall_ns"] < timing["full_cell_wall_ns"], cell + " prefix is shorter")
    need(owner["confirmed"] and timing["owner_cleanup_confirmed"], cell + " owner closure")
    need(consumer["process_reaped"] and consumer["readers_stopped"], cell + " consumer closure")
    need(consumer["bridge_cleanup"]["confirmed"] is None, cell + " thin EXIT remains unknown")
    need(consumer["bridge_cleanup"]["missing_exit_count"] == 1, cell + " one missing EXIT")
    need(native_close["process_reaped"] and native_close["exit_code"] == 0, cell + " native closure")
    need(timing["within_570s"] and end <= start + 570_000_000_000, cell + " original full-cell budget")

    usage_events = [row for row in events if "usage" in row["event"]]
    need(len(usage_events) == 1, cell + " exactly one cumulative turn usage")
    need(usage_events[-1]["event"]["type"] == "turn.completed", cell + " final cumulative usage type")
    usage = usage_events[-1]["event"]["usage"]
    need(usage == consumer["usage"], cell + " raw cumulative usage equality")
    need([row["event"]["usage"] for row in usage_events] == consumer["usage_rows"], cell + " usage rows")
    need(usage["input_tokens"] >= usage["cached_input_tokens"] >= 0, cell + " cached subset")
    need(usage["output_tokens"] >= usage["reasoning_output_tokens"] >= 0, cell + " reasoning subset")
    raw_threads = [row["event"]["thread_id"] for row in events if row["event"]["type"] == "thread.started"]
    need(raw_threads == [consumer["thread_id"]], cell + " raw thread identity")

    final = raw(folder / "PUBLIC_FINAL.txt")
    need(hashlib.sha256(final).hexdigest() == answer["final_sha256"], cell + " independent quality final")
    need(consumer["final"].encode("utf-8") == final, cell + " consumer final bytes")
    need(raw(folder / "final.txt") == final, cell + " CLI final file")

    started = {row["event"]["item"]["id"]: row["perf_ns"] for row in events
               if row["event"]["type"] == "item.started" and row["event"].get("item", {}).get("type") == "mcp_tool_call"}
    completed = [row for row in events if row["event"]["type"] == "item.completed"
                 and row["event"].get("item", {}).get("type") == "mcp_tool_call"]
    need(len(completed) == tools["attempts"] == len(tools["tools"]), cell + " complete attempt denominator")
    attempts = []
    seen_arguments = Counter()
    for index, event in enumerate(completed, 1):
        item = event["event"]["item"]
        tool_folder = folder / "owner" / ("tool_" + str(index).zfill(2))
        attempt = read(tool_folder / "ATTEMPT.json")
        request = read(tool_folder / "REQUEST.json")
        response = read(tool_folder / "RESPONSE.json")
        need(attempt == tools["tools"][index - 1], cell + " frozen attempt row")
        need(request["params"]["name"] == item["tool"], cell + " tool name")
        need(request["params"]["arguments"] == item["arguments"], cell + " tool arguments")
        owner_blocks = response.get("result", {}).get("content", [])
        cli_blocks = item.get("result", {}).get("content", [])
        need(owner_blocks == cli_blocks, cell + " result content projection")
        need(attempt["response_bytes"] == len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1,
             cell + " owner wire bytes")
        cli_text_bytes = sum(len(block.get("text", "").encode("utf-8")) for block in cli_blocks if block.get("type") == "text")
        image_blocks = sum(block.get("type") == "image" for block in cli_blocks)
        argument_sha256 = hashlib.sha256(json.dumps(item["arguments"], ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode("utf8")).hexdigest()
        argument_key = (item["tool"], argument_sha256)
        need(started[item["id"]] <= attempt["started_ns"] <= event["perf_ns"], cell + " tool time anchor")
        attempts.append({
            "attempt": index, "name": item["tool"], "cli_item_id": item["id"],
            "cli_started_ns": started[item["id"]], "cli_completed_ns": event["perf_ns"],
            "cli_interval_ns": event["perf_ns"] - started[item["id"]],
            "owner_elapsed_ns": attempt["elapsed_ns"], "owner_started_ns": attempt["started_ns"],
            "failed": bool(attempt["is_error"] or attempt["exception"]),
            "recorded_is_error": attempt["is_error"], "CLI_item_status": item.get("status"),
            "arguments_canonical_sha256": argument_sha256,
            "same_name_arguments_prior_calls": seen_arguments[argument_key],
            "exception": attempt["exception"], "recorded_result_text_utf8_bytes": cli_text_bytes,
            "image_blocks": image_blocks, "bridge_response_envelope_bytes": attempt["response_bytes"],
            "produced_response_envelope_bytes": attempt["produced_response_bytes"],
            "code_utf8_bytes": len(item["arguments"].get("code", "").encode("utf-8")),
            "arguments_canonical_utf8_bytes": encoded_size(item["arguments"]),
        })
        seen_arguments[argument_key] += 1
    for before, after in zip(attempts, attempts[1:]):
        need(before["cli_completed_ns"] <= after["cli_started_ns"], cell + " disjoint recorded tool intervals")
    need(sum(row["image_blocks"] for row in attempts) == consumer["public_image_count"], cell + " raw image-block count equals reported delivery")

    bridge_dirs = [path for path in (folder / "attachments").glob("bridge_*") if path.is_dir()]
    need(len(bridge_dirs) == 1, cell + " one actual bridge")
    bridge_calls = []
    for path in sorted(bridge_dirs[0].glob("[0-9][0-9][0-9]")):
        tx = raw(path / "TX.bin")
        request = json.loads(tx)
        rx = raw(path / "RX.bin") if (path / "RX.bin").exists() else b""
        need(bool(rx) == ("id" in request), cell + " RPC response accounting")
        bridge_calls.append({"sequence": int(path.name), "method": request["method"],
                             "business": request["method"] == "tools/call", "tx_bytes": len(tx), "rx_bytes": len(rx)})
    business_bridge = [row for row in bridge_calls if row["business"]]
    need([row["rx_bytes"] for row in business_bridge] == [row["bridge_response_envelope_bytes"] for row in attempts], cell + " bridge bytes")

    host_scripts = []
    snapshot_scripts = 0
    for worker in native_events:
        sequence = worker.get("sequence")
        script_path = folder / "owner" / "native" / ("call_" + str(sequence)) / "SCRIPT.py"
        if not script_path.exists():
            need(worker.get("status") == "unknown", cell + " close event unknown script status")
            continue
        script_file = raw(script_path)
        script = script_file.replace(b"\r\n", b"\n")
        need(hashlib.sha256(script).hexdigest() == worker["script_sha256"], cell + " LF-normalized host script hash")
        stdout_file = raw(script_path.parent / "stdout.txt")
        stderr_file = raw(script_path.parent / "stderr.txt")
        stdout = stdout_file.replace(b"\r\n", b"\n")
        stderr = stderr_file.replace(b"\r\n", b"\n")
        need(len(stdout) == worker["stdout_bytes"], cell + " LF-normalized returned host stdout bytes")
        need(len(stderr) == worker["stderr_bytes"], cell + " LF-normalized returned host stderr bytes")
        is_snapshot = sequence in (1, len(native_events) - 1)
        snapshot_scripts += int(is_snapshot)
        host_scripts.append({
            "sequence": sequence, "administrative_snapshot": is_snapshot,
            "started_ns": worker["started_ns"], "elapsed_ns": worker["elapsed_ns"],
            "status": worker["status"], "script_error": worker["script_error"],
            "script_utf8_bytes": len(script), "stored_script_file_bytes": len(script_file),
            "script_file_scope": "Windows text file CRLF normalized to LF, verified against worker's actual code SHA256",
            "returned_stdout_utf8_bytes": worker["stdout_bytes"],
            "returned_stderr_utf8_bytes": worker["stderr_bytes"],
            "stored_stdout_file_bytes": len(stdout_file), "stored_stderr_file_bytes": len(stderr_file),
            "stdout_file_sha256": hashlib.sha256(stdout_file).hexdigest(),
            "stderr_file_sha256": hashlib.sha256(stderr_file).hexdigest(),
            "script_sha256": worker["script_sha256"],
            "render_events_added": worker["render_events_after"] - worker["render_events_before"],
            "changed_or_new_png": worker["changed_or_new_PNG_files"],
        })
    need(snapshot_scripts == 2, cell + " two administration snapshots")
    need(len(native_events) == len(host_scripts) + 1, cell + " one native close")

    product = None
    if cell[0] in ("O", "C"):
        rpc = read(folder / "owner" / "plugin" / "RPC.json")
        for index, request in enumerate(rpc["requests"], 1):
            path = folder / "owner" / "plugin" / str(index).zfill(3)
            tx = raw(path / "TX.bin")
            need(len(tx) == request["sent_bytes"], cell + " product tx")
            rx = raw(path / "RX.bin") if (path / "RX.bin").exists() else b""
            need(len(rx) == request["received_bytes"], cell + " product rx")
        audit = rows(folder / "owner" / "audit.jsonl")
        observations = []
        for row in audit:
            if row.get("event") != "observe":
                continue
            work = row["task_work"]
            acquisition = work.get("acquisition_work", {})
            observations.append({
                "time_unix": row["time_unix"], "engine_invoked": row.get("engine_invoked"),
                "kernel_calls": work.get("kernel_calls"), "pair_calls": work.get("pair_calls"),
                "cache_hits": work.get("cache_hits"), "acquisition_work": acquisition,
                "cache_entries_before": work.get("measurement_cache_before", {}).get("measurement_entries"),
                "cache_entries_after": work.get("measurement_cache_after", {}).get("measurement_entries"),
            })
        product = {
            "rpc": rpc, "business_rpcs": sum(row["method"] == "tools/call" for row in rpc["requests"]),
            "administrative_rpcs": sum(row["method"] != "tools/call" for row in rpc["requests"]),
            "observations": observations,
            "trace_roots": [{"operation": row["trace"]["operation"], "duration_ns": row["trace"]["duration_ns"],
                             "outcome": row["trace"]["outcome"], "trace_delivery_timing": row["trace"]["trace_delivery_timing"]}
                            for row in audit if row.get("event") == "request_trace"],
            "close": owner["close"]["plugin_close"],
        }
        need(product["business_rpcs"] == sum(row["name"] == "human_eye_scene_observe" for row in attempts), cell + " product attempts")
        need(rpc["tx_bytes"] == sum(row["sent_bytes"] for row in rpc["requests"]), cell + " product tx sum")
        need(rpc["rx_bytes"] == sum(row["received_bytes"] for row in rpc["requests"]), cell + " product rx sum")
    else:
        need(not (folder / "owner" / "plugin").exists(), cell + " no N product process")

    lifecycle = {
        "before_consumer_ns": consumer["started_ns"] - start,
        "consumer_start_to_prompt_ns": consumer["prompt_submitted_ns"] - consumer["started_ns"],
        "prompt_to_final_inclusive_ns": consumer["final_received_ns"] - consumer["prompt_submitted_ns"],
        "final_to_consumer_cleanup_ns": consumer["cleanup_end_ns"] - consumer["final_received_ns"],
        "post_consumer_to_business_close_ns": end - consumer["cleanup_end_ns"],
    }
    need(sum(lifecycle.values()) == timing["full_cell_wall_ns"], cell + " exclusive lifecycle partitions")
    cli_tool_ns = sum(row["cli_interval_ns"] for row in attempts)
    need(cli_tool_ns <= lifecycle["prompt_to_final_inclusive_ns"], cell + " tool inclusive interval")
    observation_indices = [row["attempt"] for row in attempts if row["name"] == "human_eye_scene_observe"]
    return {
        "cell": cell, "anonymous_id": answer["anonymous_id"], "quality": answer["primary_classification"],
        "final_content_quality": answer["final_content_classification"],
        "consumer_valid_completion": consumer["valid_completion"],
        "retained_execution_errors": consumer["errors"],
        "group": cell[0], "round": int(cell[1]), "thread_id": consumer["thread_id"],
        "execution_status": consumer["status"], "full_cell_wall_ns": timing["full_cell_wall_ns"],
        "prefix_wall_ns": consumer["total_task_wall_ns"],
        "business_close_minus_prefix_ns": timing["full_cell_wall_ns"] - consumer["total_task_wall_ns"],
        "lifecycle_partitions_ns": lifecycle, "consumer_wall_ns": consumer["wall_ns"],
        "CLI_turn_interval_ns": consumer["turn_completed_ns"] - next(row["perf_ns"] for row in events if row["event"]["type"] == "turn.started"),
        "model_compute_interval_ns": None,
        "model_compute_interval_scope": "No provider-side active-compute interval is recorded. CLI turn and prompt-to-final intervals include provider, network and local handling.",
        "prompt_to_final_non_tool_remainder_ns": lifecycle["prompt_to_final_inclusive_ns"] - cli_tool_ns,
        "remainder_scope": "Observable prompt-to-final interval minus observed MCP intervals. Includes model/provider/network/CLI gaps; active model compute and service-side queue time unseparated.",
        "timing_publication": publication, "consumer_usage_final_cumulative": usage,
        "uncached_input_tokens": usage["input_tokens"] - usage["cached_input_tokens"],
        "total_input_plus_output_tokens": usage["input_tokens"] + usage["output_tokens"],
        "usage_row_count": len(usage_events), "usage_semantics": "One final cumulative turn usage; use once. Cached input is a subset of input, reasoning a subset of output. Zero cache-write field reported separately.",
        "attempts": attempts, "tool_attempts": len(attempts), "failed_tool_attempts": sum(row["failed"] for row in attempts),
        "tools_by_name": dict(Counter(row["name"] for row in attempts)),
        "repeated_same_name_arguments_attempts": sum(row["same_name_arguments_prior_calls"] > 0 for row in attempts),
        "native_calls_after_first_observe": sum(row["name"] == "execute_blender_code" and row["attempt"] > observation_indices[0]
                                                for row in attempts) if observation_indices else 0,
        "native_after_observe_scope": "Observed call order only. Mechanism evidence determines full-scene fallback, legitimate evidence completion or another purpose.",
        "owner_tool_elapsed_sum_ns": sum(row["owner_elapsed_ns"] for row in attempts),
        "CLI_tool_intervals_sum_ns": cli_tool_ns,
        "recorded_model_facing_tool_text_utf8_bytes": sum(row["recorded_result_text_utf8_bytes"] for row in attempts),
        "recorded_text_scope": "UTF-8 text in actual completed MCP result content in CLI events, verified equal owner result content. Provider-side actual context/tokenization/truncation not attested by this byte count.",
        "tool_response_envelope_bytes": sum(row["bridge_response_envelope_bytes"] for row in attempts),
        "prompt_utf8_bytes": consumer["input_text_bytes"], "final_utf8_bytes": len(final),
        "agent_public_text_utf8_bytes": consumer["public_text_bytes"], "CLI_stdout_bytes": consumer["stdout_bytes"],
        "CLI_stdout_scope": "Original consumer stdout byte counter. Parsed and timestamped events are retained, independent raw CLI stdout is unavailable.",
        "input_image_count": consumer["input_image_count"], "delivered_tool_image_count": consumer["public_image_count"],
        "delivered_tool_image_bytes": consumer["public_image_bytes"], "image_tokens": consumer["image_tokens"],
        "image_construction_observed": owner["close"]["image_construction"]["observed"],
        "image_scope": owner["close"]["image_construction"]["scope"],
        "bridge_rpcs": bridge_calls, "bridge_business_rpcs": len(business_bridge),
        "bridge_administrative_rpcs": len(bridge_calls) - len(business_bridge),
        "bridge_tx_bytes": sum(row["tx_bytes"] for row in bridge_calls),
        "bridge_rx_bytes": sum(row["rx_bytes"] for row in bridge_calls),
        "native_host_requests_including_close": len(native_events),
        "native_host_business_scripts": len(host_scripts) - snapshot_scripts,
        "native_host_administrative_requests": snapshot_scripts + 1,
        "native_host_scripts": host_scripts,
        "native_host_stdout_utf8_bytes_all_scripts": sum(row["returned_stdout_utf8_bytes"] for row in host_scripts),
        "native_host_stdout_utf8_bytes_business": sum(row["returned_stdout_utf8_bytes"] for row in host_scripts if not row["administrative_snapshot"]),
        "native_host_stderr_utf8_bytes_all_scripts": sum(row["returned_stderr_utf8_bytes"] for row in host_scripts),
        "native_host_stderr_utf8_bytes_business": sum(row["returned_stderr_utf8_bytes"] for row in host_scripts if not row["administrative_snapshot"]),
        "native_host_business_script_elapsed_sum_ns": sum(row["elapsed_ns"] for row in host_scripts if not row["administrative_snapshot"]),
        "native_host_close_event": native_events[-1],
        "native_host_wire_bytes": None,
        "native_authored_algorithm_vertex_reads_and_primitive_counts": None,
        "product": product, "owner_startup_ns": identity["startup_ns"],
        "closure": {"consumer_reaped": consumer["process_reaped"], "consumer_readers_stopped": consumer["readers_stopped"],
                    "owner_confirmed": owner["confirmed"], "native_reaped": native_close["process_reaped"],
                    "native_close_response": native_close["response"],
                    "product_runtime_exit": owner["close"].get("product_runtime_exit"),
                    "thin_client": consumer["bridge_cleanup"]},
        "provider_retry_observations": consumer["provider_retry_observations"],
        "provider_requests": consumer["provider_requests"], "fees": consumer["fees"],
        "requested_model": consumer["model"], "requested_effort": consumer["requested_effort"],
        "resolved_model_version": None, "resolved_effort": consumer["resolved_effort"],
        "CLI_error_items": [row["event"]["item"] for row in events if row["event"].get("item", {}).get("type") == "error"],
        "CLI_stderr": classify_stderr(folder),
        "recorded_error_events": [row for row in events if row["event"].get("type") == "error"],
        "reported_usage_coverage": "Final cumulative CLI turn report. Inclusion of abandoned or interrupted stream usage is unconfirmed without provider-level receipts.",
    }


def group_summary(cells, group):
    selected = [row for row in cells if row["group"] == group]
    metrics = (
        "full_cell_wall_ns", "prefix_wall_ns", "consumer_wall_ns", "total_input_plus_output_tokens",
        "uncached_input_tokens", "tool_attempts", "failed_tool_attempts", "owner_tool_elapsed_sum_ns",
        "repeated_same_name_arguments_attempts", "native_calls_after_first_observe",
        "CLI_tool_intervals_sum_ns", "recorded_model_facing_tool_text_utf8_bytes", "tool_response_envelope_bytes",
        "bridge_tx_bytes", "bridge_rx_bytes", "native_host_requests_including_close", "native_host_business_scripts",
        "native_host_administrative_requests", "native_host_stdout_utf8_bytes_all_scripts",
        "native_host_stdout_utf8_bytes_business", "native_host_stderr_utf8_bytes_all_scripts",
        "native_host_stderr_utf8_bytes_business", "native_host_business_script_elapsed_sum_ns", "CLI_stdout_bytes",
    )
    usage_fields = ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens")
    return {
        "cells": [row["cell"] for row in selected], "n": len(selected),
        "content_complete_correct": sum(row["final_content_quality"] == "complete_correct" for row in selected),
        "valid_complete_correct": sum(row["quality"] == "complete_correct" for row in selected),
        "primary_classifications": dict(Counter(row["quality"] for row in selected)),
        "sum": sum_fields(selected, metrics),
        "median": {field: statistics.median(row[field] for row in selected) for field in metrics},
        "usage_sum": sum_fields([row["consumer_usage_final_cumulative"] for row in selected], usage_fields),
        "usage_median": {field: statistics.median(row["consumer_usage_final_cumulative"][field] for row in selected)
                         for field in usage_fields},
    }


def comparison(cells, groups, reference):
    by_cell = {row["cell"]: row for row in cells}
    pairs = []
    for index in (1, 2, 3):
        candidate = by_cell["C" + str(index)]
        other = by_cell[reference + str(index)]
        pairs.append({
            "round": index, "candidate": candidate["cell"], "reference": other["cell"],
            "candidate_primary_quality": candidate["quality"], "reference_primary_quality": other["quality"],
            "candidate_final_content_quality": candidate["final_content_quality"],
            "reference_final_content_quality": other["final_content_quality"],
            "full_wall_ratio": ratio(candidate["full_cell_wall_ns"], other["full_cell_wall_ns"]),
            "full_wall_delta_ns": candidate["full_cell_wall_ns"] - other["full_cell_wall_ns"],
            "reported_token_ratio": ratio(candidate["total_input_plus_output_tokens"], other["total_input_plus_output_tokens"]),
        })
    exact_ratios = [Fraction(row["full_wall_ratio"]["numerator"], row["full_wall_ratio"]["denominator"]) for row in pairs]
    median_value = statistics.median(exact_ratios)
    quality_eligible = groups["C"]["valid_complete_correct"] == groups[reference]["valid_complete_correct"] == 3
    time_condition = median_value <= Fraction(7, 10) if reference == "N" else median_value < 1
    candidate_tokens = groups["C"]["sum"]["total_input_plus_output_tokens"]
    reference_tokens = groups[reference]["sum"]["total_input_plus_output_tokens"]
    token_condition = candidate_tokens <= reference_tokens
    return {
        "reference_group": reference, "fixed_pairs": pairs,
        "valid_complete_correct": {"C": groups["C"]["valid_complete_correct"], reference: groups[reference]["valid_complete_correct"]},
        "final_content_complete_correct": {"C": groups["C"]["content_complete_correct"], reference: groups[reference]["content_complete_correct"]},
        "formal_execution_quality_precondition": quality_eligible,
        "formal_gate_status": "passed" if quality_eligible and time_condition and token_condition else
                              "not_satisfied_execution_quality_precondition" if not quality_eligible else "numeric_condition_failed",
        "formal_gate_pass": quality_eligible and time_condition and token_condition,
        "descriptive_all_cells": {
            "median_paired_full_wall_ratio": ratio(median_value.numerator, median_value.denominator),
            "time_rule": "median(C_i/N_i) <= 0.70" if reference == "N" else "median(C_i/O_i) < 1",
            "time_numeric_condition": time_condition,
            "C_reported_input_plus_output": candidate_tokens,
            "reference_reported_input_plus_output": reference_tokens,
            "reported_token_ratio": ratio(candidate_tokens, reference_tokens),
            "token_numeric_condition": token_condition,
            "includes_all_error_cells": True,
            "network_duration_subtracted_ns": 0,
            "scope": "All three fixed pairs, including retained failed executions. These numerical conditions are descriptive and do not replace the formal validity prerequisite.",
        },
    }


def main():
    need(hashlib.sha256(raw(HERE / "inputs/COST_PLAN.md")).hexdigest() == PLAN_SHA256, "frozen cost plan SHA256")
    reuse = read(HERE / "REUSE.json")
    baseline = BATCH.parents[1] / reuse["baseline_path"]
    need(hashlib.sha256(raw(baseline)).hexdigest() == reuse["baseline_sha256"], "reused old-six helper source SHA256")
    seal_bytes = raw(HERE / "inputs/QUALITY_SEAL.json")
    need(hashlib.sha256(seal_bytes).hexdigest() == SEAL_SHA256, "quality seal SHA256")
    seal = json.loads(seal_bytes)
    need(seal["primary_counts"] == {"complete_correct": 7, "incomplete": 0, "incorrect": 0, "execution_failure": 2, "not_run": 0}, "frozen primary quality denominator")
    need(seal["content_counts"]["complete_correct"] == 9 and seal["matching_facts_correct"] == 639, "frozen content quality denominator")
    mapping = read(BATCH / "private/ANON_MAP.json")["rows"]
    need(tuple(row["cell"] for row in mapping) == CELLS, "fixed nine dispatch order")
    need(len({row["anonymous_id"] for row in mapping}) == 9, "nine unique anonymous IDs")
    answers = {row["anonymous_id"]: row for row in seal["answers"]}
    need(set(answers) == {row["anonymous_id"] for row in mapping}, "sealed anonymous mapping membership")
    cells = [collect_cell(slot["cell"], answers[slot["anonymous_id"]]) for slot in mapping]
    for cell, slot in zip(cells, mapping, strict=True):
        answer = answers[slot["anonymous_id"]]
        need(cell["execution_status"] == answer["execution_state"], cell["cell"] + " frozen execution state")
        need(cell["consumer_valid_completion"] is answer["consumer_valid_completion"], cell["cell"] + " valid completion")
        need(cell["group"] == slot["group"] and cell["round"] == slot["round"], cell["cell"] + " group round mapping")
        event_rows = rows(BATCH / "cells" / cell["cell"] / "events.jsonl")
        messages = [row["event"]["item"]["text"] for row in event_rows if row["event"].get("type") == "item.completed"
                    and row["event"].get("item", {}).get("type") == "agent_message"]
        need(messages[-1].encode("utf8") == raw(BATCH / "cells" / cell["cell"] / "final.txt"), cell["cell"] + " actual last model public message")
        cell["CLI_reconnect_error_events"] = [row for row in cell["recorded_error_events"] if "Reconnecting" in row["event"].get("message", "")]
        cell["reconnect_usage_inclusion_confirmed"] = None if cell["CLI_reconnect_error_events"] else "no reconnect event recorded"
    need(len({row["thread_id"] for row in cells}) == 9, "nine fresh model threads")
    need({row["cell"] for row in cells if row["quality"] == "execution_failure"} == {"N2", "O2"}, "two exact failed cells retained")
    groups = {group: group_summary(cells, group) for group in ("N", "O", "C")}
    need({group: row["valid_complete_correct"] for group, row in groups.items()} == {"N": 2, "O": 2, "C": 3}, "formal validity by group")
    comparisons = {"C_over_" + group: comparison(cells, groups, group) for group in ("N", "O")}
    for before, after in zip(cells, cells[1:]):
        need(before["timing_publication"]["timing_receipt_publication_closed_ns"] <=
             read(BATCH / "cells" / after["cell"] / "CELL_FINAL_TIMING.json")["cell_started_ns"], "serial business close before next cell")

    run = read(BATCH / "RUN_RESULT.json")
    formal = read(BATCH / "FORMAL_PROCESS.json")
    publication = read(BATCH / "FORMAL_PUBLICATION.json")
    preparation = read(BATCH / "PREPARATION_COST.json")
    packages = {"initial": read(BATCH / "private/PACKAGING_COST.json"),
                "final_r2": read(BATCH / "private/PACKAGING_COST_R2.json")}
    need(run["started_cells"] == 9 and run["stop"] is None and run["all_planned_dispatched"], "all nine original cells dispatched")
    need(formal["controller_error"] is None and formal["status"] == "terminal", "original controller terminal")
    need(formal["ended_ns"] - formal["started_ns"] > sum(row["full_cell_wall_ns"] for row in cells), "batch includes all cells")
    need(run["batch_ended_ns"] - run["batch_started_ns"] == run["batch_wall_ns"], "run batch interval")
    need(formal["ended_ns"] == publication["terminal_observed_ns"], "batch publication anchor")
    need(publication["publication_closed_ns"] - publication["publication_started_ns"] == publication["publication_ns"], "batch publication interval")
    r2_path = BATCH / "quality/SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip"
    need(hashlib.sha256(raw(r2_path)).hexdigest() == seal["r2_zip_sha256"], "sealed r2 ZIP")
    index = read(BATCH / "quality/public/INDEX.json")
    public_answers = {row["anonymous_id"]: row for row in index["answers"]}
    for cell in cells:
        item = public_answers[cell["anonymous_id"]]
        need(item["cell_execution_state"] == cell["execution_status"], cell["cell"] + " r2 execution state")
        need(item["answer_original_sha256"] == answers[cell["anonymous_id"]]["final_sha256"], cell["cell"] + " r2 final SHA")
    need(all(row["input_image_count"] == row["delivered_tool_image_count"] == row["delivered_tool_image_bytes"] == 0 for row in cells), "zero actual input/tool images")
    result = {
        "schema": "m4_surface_scan_compact_nine_cost_accounting_v1",
        "original_delivery_commit": seal["delivery_commit"], "preparation_commit": seal["preparation_commit"],
        "quality_seal_sha256": SEAL_SHA256,
        "cost_plan_sha256": PLAN_SHA256, "reused_helper_source": reuse,
        "scope": "Offline accounting of the fixed nine originals after quality seal. No new execution, sample, product change or network-delay subtraction.",
        "quality_primary_counts": seal["primary_counts"], "quality_content_counts": seal["content_counts"],
        "groups": groups, "comparisons": comparisons, "cells": cells,
        "formulas": {
            "paired_wall": "Median of three exact Fraction(CELL_FINAL_TIMING[C_i].full_cell_wall_ns / reference_i.full_cell_wall_ns)",
            "reported_tokens": "Final cumulative reported input_tokens+output_tokens once per cell, including both failed cells; cached/reasoning remain subsets.",
            "formal_precondition": "Both compared groups have three primary complete_correct cases under the frozen valid_completion rule.",
            "remaining_interval": "prompt-to-final wall minus disjoint observed CLI tool intervals; model/provider/network/CLI components unseparated.",
        },
        "shared_costs": {
            "formal_process": formal, "formal_publication": publication,
            "run_models_wall_ns": run["batch_wall_ns"], "formal_wall_ns": formal["ended_ns"] - formal["started_ns"],
            "sum_full_cells_ns": sum(row["full_cell_wall_ns"] for row in cells),
            "formal_minus_sum_full_cells_ns": formal["ended_ns"] - formal["started_ns"] - sum(row["full_cell_wall_ns"] for row in cells),
            "sum_cell_timing_receipt_publication_ns": sum(row["timing_publication"]["timing_receipt_publication_ns"] for row in cells),
            "preparation": preparation, "packaging": packages,
            "historical_install_scope": "Existing O/C installation timings are historical reuse records; no rebuild or per-arm amortization in this batch.",
            "unmeasured": ["complete coordinator/preparation wall and model cost", "admin redaction and post-archive verification wall", "review and Git delivery wall",
                           "physical disk fsync", "cash and subscription fees", "actual resolved model version/effort", "provider rendering and request count",
                           "abandoned-stream usage inclusion", "thin-client actual exit", "native TCP wire totals", "native authored primitive and vertex-read work"],
        },
        "non_additivity": "CLI, owner, host and product timings are nested. Response body, JSON envelopes and internal capture bytes are separate serialization layers.",
        "checks": CHECKS, "sources": [{"path": name, **value} for name, value in sorted(SOURCES.items())],
        "learning_binding": {"context_bound": False, "host_epoch": 5, "rebind_required": True},
        "new_Blender_model_API_runs": 0,
    }
    (HERE / "LEDGER.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    write_report(result)
    print(json.dumps({"checks": CHECKS, "sources": len(SOURCES), "valid_complete_correct":
                      {group: value["valid_complete_correct"] for group, value in groups.items()}, "comparisons": comparisons}, ensure_ascii=False))


def write_report(result):
    groups = result["groups"]
    lines = ["# 同九格原件的成本账本", "",
             "本批在根匿名质量 seal 后离线解封。最终内容九份均完整正确，冻结主分类保留七份 complete_correct、两份 execution_failure。N2、O2 的重连错误、全部耗时和 reported usage 留在原固定格中。", "",
             "N 为原生组，O 为旧扫描 OPT1，C 为 compact 展示候选。本次展示结构及真实工具描述一同变化，候选整体收益的归因范围由独立机制账本进一步核对。", "",
             "## 正式前提与描述性数值", "",
             "| 组 | 最终内容正确 | 有效完整正确 | 执行失败 |", "| --- | --- | --- | --- |"]
    for group, item in groups.items():
        lines.append(f"| {group} | {item['content_complete_correct']}/3 | {item['valid_complete_correct']}/3 | {item['primary_classifications'].get('execution_failure', 0)} |")
    lines.extend(["", "C/N 和 C/O 均缺少双方各 3/3 有效完整正确的原前提，两个正式门均未满足。以下数值包含九格全部成本，表示九份正确最终内容的描述性成本。", "",
                  "| 比较 | 完整配对比值中位 | 时间数值条件 | C reported token | 参照 reported token | token 数值条件 | 正式门 |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for key, item in result["comparisons"].items():
        d = item["descriptive_all_cells"]
        lines.append(f"| {key.replace('_over_', '/')} | {d['median_paired_full_wall_ratio']['value']:.12f} | {d['time_rule']}，{'满足' if d['time_numeric_condition'] else '未满足'} | {d['C_reported_input_plus_output']} | {d['reference_reported_input_plus_output']} | {'满足' if d['token_numeric_condition'] else '未满足'} | 前提不足，未通过 |")
    lines.extend(["", "| 固定配对 | C/参照完整墙钟 | 精确分数 | C−参照秒 |", "| --- | --- | --- | --- |"])
    for item in result["comparisons"].values():
        for p in item["fixed_pairs"]:
            r = p["full_wall_ratio"]
            lines.append(f"| {p['candidate']}/{p['reference']} | {r['value']:.12f} | {r['numerator']}/{r['denominator']} | {p['full_wall_delta_ns']/1e9:.7f} |")
    lines.extend(["", "全部比值由整数纳秒精确分数计算。每组三个原格和两个原错误格均保留，网络时长扣除为零。未以组总量比例替代配对中位。", "",
                  "## 九格完整时界", "", "| 格 | 执行 | 内容 | full 秒 | prefix 秒 | prefix后 ms | prompt→final 秒 | CLI工具区间秒 | 区间外余量秒 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['execution_status']} | {row['final_content_quality']} | {row['full_cell_wall_ns']/1e9:.7f} | {row['prefix_wall_ns']/1e9:.7f} | {row['business_close_minus_prefix_ns']/1e6:.4f} | {row['lifecycle_partitions_ns']['prompt_to_final_inclusive_ns']/1e9:.7f} | {row['CLI_tool_intervals_sum_ns']/1e9:.7f} | {row['prompt_to_final_non_tool_remainder_ns']/1e9:.7f} |")
    lines.extend(["", "full 使用原 CELL_FINAL_TIMING，覆盖输入检查、启动、工具、owned 清理与最后业务记录写入关闭。prefix 是原 driver 提前采样点。下一格在上一格关闭发布之后进入。区间外余量包括生成、provider、网络、CLI调度与回传，无法进一步分离。", "",
                  "| 组/统计 | full 秒 | input | cached input 子项 | uncached input | output | reasoning output 子项 | input+output |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for group, item in groups.items():
        for label, metrics, usage in (("总量", item["sum"], item["usage_sum"]), ("中位", item["median"], item["usage_median"])):
            lines.append(f"| {group}/{label} | {metrics['full_cell_wall_ns']/1e9:.7f} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {metrics['uncached_input_tokens']} | {usage['output_tokens']} | {usage['reasoning_output_tokens']} | {metrics['total_input_plus_output_tokens']} |")
    lines.extend(["", "累计 reported token 包含 cached 前缀在各轮请求中的累计计数，不能换算为峰值 context 或现金费用。C 相对 N/O 的 cached input 累计差额较大，uncached input 和 output 已分别列出。中位行逐列独立求中位，子项中位相加可能与总项中位不同。", "",
                  "## 实际 reported usage 与重连范围", "", "| 格 | input | cached input | uncached input | output | reasoning output | input+output | 重连 error 事件 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        u = row["consumer_usage_final_cumulative"]
        lines.append(f"| {row['cell']} | {u['input_tokens']} | {u['cached_input_tokens']} | {row['uncached_input_tokens']} | {u['output_tokens']} | {u['reasoning_output_tokens']} | {row['total_input_plus_output_tokens']} | {len(row['CLI_reconnect_error_events'])} |")
    lines.extend(["", "九格各有一个最终 turn.completed usage 事件，逐字段等于 CONSUMER.usage 和 usage_rows。只累计该最终报告一次，cache_write_input_tokens 均为零，cached input 和 reasoning output 作为重叠子项保留。", "",
                  "N2/O2 各记录一次 stream reconnect/response-body decoding error，后有 turn.completed、exit0 与原 final，valid_completion=false 保留。两错误格的全部 full 和最终 reported usage 均计入。记录没有逐 provider request 的 usage、弃流回执或重连期间单独计量，因此最终报告是否覆盖中断流的全部 token 未获确认。账本不将 reported 总量等同现金账单，也没有另加或扣除猜测 token。", "",
                  "## 工具、传输与内部工作", "", "| 格 | 工具尝试/失败 | observe/native | CLI记录正文 B | 业务MCP响应 B | 全MCP RX/TX B | host业务stdout B |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['tool_attempts']}/{row['failed_tool_attempts']} | {row['tools_by_name'].get('human_eye_scene_observe',0)}/{row['tools_by_name'].get('execute_blender_code',0)} | {row['recorded_model_facing_tool_text_utf8_bytes']} | {row['tool_response_envelope_bytes']} | {row['bridge_rx_bytes']}/{row['bridge_tx_bytes']} | {row['native_host_stdout_utf8_bytes_business']} |")
    lines.extend(["", "CLI记录正文按 completed MCP content.text 的 UTF-8 求和并核 owner 同内容，MCP 响应按实际薄客户端 RX.bin 长度计。全部 MCP 还含 initialize、initialized notification 和完整 tools/list。host stdout 是内部回执层，provider 最终输入呈现、截断与 tokenization 未获确认。各层字节单列。", "",
                  "| 格 | 工具失败 | 同名同参重复 | 首次observe后原生调用 | CLI turn秒 | owner工具和秒 | host业务脚本和秒 |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['failed_tool_attempts']} | {row['repeated_same_name_arguments_attempts']} | {row['native_calls_after_first_observe']} | {row['CLI_turn_interval_ns']/1e9:.7f} | {row['owner_tool_elapsed_sum_ns']/1e9:.7f} | {row['native_host_business_script_elapsed_sum_ns']/1e9:.7f} |")
    lines.extend(["", "各工具的 is_error 与 exception 失败计数均为零，业务拒绝和独立错误字段保留原件。原生调用是否构成全场回退或合理补证，由独立消费机制证据判定。CLI turn 与 prompt→final 都包含 provider、网络和本地处理，模型服务端纯计算区间未测。owner、host 和产品 trace 属于嵌套时界，未与 CLI 区间相加。", "",
                  "| 格 | host总请求 | 业务脚本/管理 | product业务/管理RPC | product RX/TX B |", "| --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        product = row["product"]
        calls = f"{product['business_rpcs']}/{product['administrative_rpcs']}" if product else "0/0"
        wire = f"{product['rpc']['rx_bytes']}/{product['rpc']['tx_bytes']}" if product else "0/0"
        lines.append(f"| {row['cell']} | {row['native_host_requests_including_close']} | {row['native_host_business_scripts']}/{row['native_host_administrative_requests']} | {calls} | {wire} |")
    lines.extend(["", "host 管理请求包含初末两次 QA 快照和 close。业务脚本包含消费者原生调用及插件内部采集。通用 close 事件保留 unknown 脚本状态，实际关闭回执和 owned 回收独立确认。九份 thin EXIT 保留 unknown。native TCP 实际完整信封未录制，账本留未测。", "",
                  "| 格/观察 | 新kernel | cache entries前/后 | source V/F | 实际resource读V/F | scan cache hit |", "| --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        if row["product"] is None:
            continue
        for index, observation in enumerate(row["product"]["observations"], 1):
            acq = observation["acquisition_work"]
            delta = acq.get("residency_delta", {})
            lines.append(f"| {row['cell']}/{index} | {observation['kernel_calls']} | {observation['cache_entries_before']}/{observation['cache_entries_after']} | {acq.get('source_vertices')}/{acq.get('source_faces')} | {delta.get('resource_vertices_read')}/{delta.get('resource_faces_read')} | {delta.get('scan_cache_hits')} |")
    lines.extend(["", "source/expanded V/F 是逻辑响应规模，实际读取采用 residency_delta。cache accounted bytes 是内部缓存记账，RSS 峰值未由它推算。各脚本保存字节与实际执行代码 SHA 分别核对，Windows CRLF 仅在对应 LF 执行代码摘要比较时归一化。原生消费者自写算法的统一 primitive/vertex work 未插桩。", "",
                  "输入图像、实际交付工具图像与图像字节均为零，image_tokens 回执不可得。渲染 hook 和 PNG 观测保留原范围。", "",
                  "## stdout、stderr 与诊断", "", "| 格 | CLI stdout计数 B | CLI stderr原件 B | host业务脚本stdout B | host全部脚本stdout B | host业务/全部脚本stderr B |", "| --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['CLI_stdout_bytes']} | {row['CLI_stderr']['raw_bytes']} | {row['native_host_stdout_utf8_bytes_business']} | {row['native_host_stdout_utf8_bytes_all_scripts']} | {row['native_host_stderr_utf8_bytes_business']}/{row['native_host_stderr_utf8_bytes_all_scripts']} |")
    lines.extend(["", "CLI stdout 为原消费者字节计数，原始流独立副本缺失，已留存带接收时点的解析事件。host stdout/stderr 均核对应文件，保存文件 CRLF 在与实际返回计数比较时归一化为 LF。宿主内部输出和对模型交付正文位于不同层。", "",
                  "| 格 | metadata fallback | shell snapshot WARN | model目录refresh ERROR | analytics WARN | response重连 WARN | 其他 |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in result["cells"]:
        d = row["CLI_stderr"]["counts"]
        lines.append(f"| {row['cell']} | {d.get('metadata_fallback_warn',0)} | {d.get('shell_snapshot_warn',0)} | {d.get('model_refresh_timeout_error',0)} | {d.get('analytics_transport_warn',0)} | {d.get('response_stream_retry_warn',0)} | {d.get('other',0)} |")
    lines.extend(["", "stderr 每行与接收记录逐字绑定，正文、行号、perf到达时间和 SHA 均在 LEDGER。stdout 重连错误单独保留。目录刷新和遥测诊断的阻塞时界缺失，其贡献没有由条数换算。", "", "## 共享准备与发布", ""])
    s = result["shared_costs"]
    lines.extend([
        f"九格 full 合计 {s['sum_full_cells_ns']/1e9:.7f} 秒，run_models 为 {s['run_models_wall_ns']/1e9:.7f} 秒，外层正式进程为 {s['formal_wall_ns']/1e9:.7f} 秒。外层与九格和的共享差额 {s['formal_minus_sum_full_cells_ns']/1e6:.4f} ms 整体保留。", "",
        f"九个 CELL_FINAL_TIMING 文件发布合计 {s['sum_cell_timing_receipt_publication_ns']/1e6:.4f} ms，FORMAL_PROCESS 文件发布 {s['formal_publication']['publication_ns']/1e6:.4f} ms。记录这些耗时的 publication 回执自身写入另属未测。", "",
        f"bootstrap 已测 {s['preparation']['bootstrap_elapsed_ns']/1e6:.4f} ms，总准备及前置协调未完整计时。既有安装复用耗时 O={s['preparation']['reused_install_elapsed_ns']['O']/1e9:.7f}s、C={s['preparation']['reused_install_elapsed_ns']['C']/1e9:.7f}s 是历史记录，本批重建0。", "",
        f"初始 ZIP 写入关闭 {s['packaging']['initial']['archive_creation_ns']/1e6:.4f} ms，r2 为 {s['packaging']['final_r2']['archive_creation_ns']/1e6:.4f} ms。行政 redaction、ZIP复核、回执、审核、交付及协调模型成本缺完整时界。", "",
        "费用、订阅扣费、实际模型版本/effort、provider输入及请求数、弃流usage涵盖、完整准备、明确到盘状态等均保留未测。没有拼接旧六格成本与本轮质量。", "",
        "## 复算材料", "",
        f"recompute.py 使用标准库离线读取 {len(result['sources'])} 份源文件，执行 {result['checks']} 项检查，生成 LEDGER.json 和本报告。它只核既有九格，新增 Blender、产品服务、模型和 API 运行均为零。REUSE.json 记录旧六格账本 helper 来源。", "",
        "本次全部描述性结果属于一个固定任务的三次重复，广域泛化和尾部稳定性另需证据。AL未绑定，host epoch5，未借其他聊天句柄。", "",
    ])
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf8", newline="\n")


if __name__ == "__main__":
    main()
