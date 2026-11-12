"""Recompute the fixed six-cell ledger from sealed originals, using stdlib only.

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
CELLS = ("N1", "P1", "P2", "N2", "N3", "P3")
SEAL_SHA256 = "1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f"
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

    usage_events = [row for row in events if "usage" in row["event"]]
    need(len(usage_events) == 1, cell + " exactly one cumulative turn usage")
    usage = usage_events[-1]["event"]["usage"]
    need(usage == consumer["usage"], cell + " raw cumulative usage equality")
    need([row["event"]["usage"] for row in usage_events] == consumer["usage_rows"], cell + " usage rows")
    need(usage["input_tokens"] >= usage["cached_input_tokens"] >= 0, cell + " cached subset")
    need(usage["output_tokens"] >= usage["reasoning_output_tokens"] >= 0, cell + " reasoning subset")
    raw_threads = [row["event"]["thread_id"] for row in events if row["event"]["type"] == "thread.started"]
    need(raw_threads == [consumer["thread_id"]], cell + " raw thread identity")

    final = raw(folder / "PUBLIC_FINAL.txt")
    need(hashlib.sha256(final).hexdigest() == answer["answer_sha256"], cell + " independent quality final")
    need(consumer["final"].encode("utf-8") == final, cell + " consumer final bytes")
    need(raw(folder / "final.txt") == final, cell + " CLI final file")

    started = {row["event"]["item"]["id"]: row["perf_ns"] for row in events
               if row["event"]["type"] == "item.started" and row["event"].get("item", {}).get("type") == "mcp_tool_call"}
    completed = [row for row in events if row["event"]["type"] == "item.completed"
                 and row["event"].get("item", {}).get("type") == "mcp_tool_call"]
    need(len(completed) == tools["attempts"] == len(tools["tools"]), cell + " complete attempt denominator")
    attempts = []
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
        need(started[item["id"]] <= attempt["started_ns"] <= event["perf_ns"], cell + " tool time anchor")
        attempts.append({
            "attempt": index, "name": item["tool"], "cli_item_id": item["id"],
            "cli_started_ns": started[item["id"]], "cli_completed_ns": event["perf_ns"],
            "cli_interval_ns": event["perf_ns"] - started[item["id"]],
            "owner_elapsed_ns": attempt["elapsed_ns"], "owner_started_ns": attempt["started_ns"],
            "failed": bool(attempt["is_error"] or attempt["exception"]),
            "exception": attempt["exception"], "recorded_result_text_utf8_bytes": cli_text_bytes,
            "image_blocks": image_blocks, "bridge_response_envelope_bytes": attempt["response_bytes"],
            "produced_response_envelope_bytes": attempt["produced_response_bytes"],
            "code_utf8_bytes": len(item["arguments"].get("code", "").encode("utf-8")),
            "arguments_canonical_utf8_bytes": encoded_size(item["arguments"]),
        })

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
            "script_sha256": worker["script_sha256"],
            "render_events_added": worker["render_events_after"] - worker["render_events_before"],
            "changed_or_new_png": worker["changed_or_new_PNG_files"],
        })
    need(snapshot_scripts == 2, cell + " two administration snapshots")
    need(len(native_events) == len(host_scripts) + 1, cell + " one native close")

    product = None
    if cell[0] == "P":
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
    return {
        "cell": cell, "anonymous_id": answer["anonymous_id"], "quality": answer["status"],
        "group": cell[0], "round": int(cell[1]), "thread_id": consumer["thread_id"],
        "execution_status": consumer["status"], "full_cell_wall_ns": timing["full_cell_wall_ns"],
        "prefix_wall_ns": consumer["total_task_wall_ns"],
        "business_close_minus_prefix_ns": timing["full_cell_wall_ns"] - consumer["total_task_wall_ns"],
        "lifecycle_partitions_ns": lifecycle, "consumer_wall_ns": consumer["wall_ns"],
        "CLI_turn_interval_ns": consumer["turn_completed_ns"] - next(row["perf_ns"] for row in events if row["event"]["type"] == "turn.started"),
        "prompt_to_final_non_tool_remainder_ns": lifecycle["prompt_to_final_inclusive_ns"] - cli_tool_ns,
        "remainder_scope": "Observable prompt-to-final interval minus observed MCP intervals. Includes model/provider/network/CLI gaps; active model compute and service-side queue time unseparated.",
        "timing_publication": publication, "consumer_usage_final_cumulative": usage,
        "uncached_input_tokens": usage["input_tokens"] - usage["cached_input_tokens"],
        "total_input_plus_output_tokens": usage["input_tokens"] + usage["output_tokens"],
        "usage_row_count": len(usage_events), "usage_semantics": "One final cumulative turn usage; use once. Cached input is a subset of input, reasoning a subset of output. Zero cache-write field reported separately.",
        "attempts": attempts, "tool_attempts": len(attempts), "failed_tool_attempts": sum(row["failed"] for row in attempts),
        "tools_by_name": dict(Counter(row["name"] for row in attempts)),
        "owner_tool_elapsed_sum_ns": sum(row["owner_elapsed_ns"] for row in attempts),
        "CLI_tool_intervals_sum_ns": cli_tool_ns,
        "recorded_model_facing_tool_text_utf8_bytes": sum(row["recorded_result_text_utf8_bytes"] for row in attempts),
        "recorded_text_scope": "UTF-8 text in actual completed MCP result content in CLI events, verified equal owner result content. Provider-side actual context/tokenization/truncation not attested by this byte count.",
        "tool_response_envelope_bytes": sum(row["bridge_response_envelope_bytes"] for row in attempts),
        "prompt_utf8_bytes": consumer["input_text_bytes"], "final_utf8_bytes": len(final),
        "agent_public_text_utf8_bytes": consumer["public_text_bytes"], "CLI_stdout_bytes": consumer["stdout_bytes"],
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
        "native_host_business_script_elapsed_sum_ns": sum(row["elapsed_ns"] for row in host_scripts if not row["administrative_snapshot"]),
        "native_host_close_event": native_events[-1],
        "native_host_wire_bytes": None,
        "native_authored_algorithm_vertex_reads_and_primitive_counts": None,
        "product": product, "owner_startup_ns": identity["startup_ns"],
        "closure": {"consumer_reaped": consumer["process_reaped"], "consumer_readers_stopped": consumer["readers_stopped"],
                    "owner_confirmed": owner["confirmed"], "native_reaped": native_close["process_reaped"],
                    "thin_client": consumer["bridge_cleanup"]},
        "provider_retry_observations": consumer["provider_retry_observations"],
        "provider_requests": consumer["provider_requests"], "fees": consumer["fees"],
        "requested_model": consumer["model"], "requested_effort": consumer["requested_effort"],
        "resolved_model_version": None, "resolved_effort": consumer["resolved_effort"],
        "CLI_error_items": [row["event"]["item"] for row in events if row["event"].get("item", {}).get("type") == "error"],
        "CLI_stderr": classify_stderr(folder),
    }


def main():
    global CHECKS
    seal_bytes = raw(HERE / "inputs" / "QUALITY_SEAL.json")
    need(hashlib.sha256(seal_bytes).hexdigest() == SEAL_SHA256, "independent seal SHA256")
    seal = json.loads(seal_bytes)
    need(seal["quality"]["complete_correct"] == 6, "quality complete denominator")
    mapping = read(BATCH / "private" / "ANON_MAP.json")
    answers = {row["anonymous_id"]: row for row in seal["answers"]}
    cell_answers = {row["cell"]: answers[row["anonymous_id"]] for row in mapping["rows"]}
    need(tuple(row["cell"] for row in mapping["rows"]) == CELLS, "frozen six dispatch order")
    cells = [collect_cell(cell, cell_answers[cell]) for cell in CELLS]
    need(len({row["thread_id"] for row in cells}) == 6, "six fresh threads")
    metrics = ["full_cell_wall_ns", "prefix_wall_ns", "consumer_wall_ns", "total_input_plus_output_tokens", "uncached_input_tokens",
               "tool_attempts", "failed_tool_attempts", "owner_tool_elapsed_sum_ns", "CLI_tool_intervals_sum_ns",
               "recorded_model_facing_tool_text_utf8_bytes", "tool_response_envelope_bytes", "bridge_tx_bytes", "bridge_rx_bytes",
               "native_host_requests_including_close", "native_host_business_scripts", "native_host_administrative_requests",
               "native_host_stdout_utf8_bytes_all_scripts", "native_host_stdout_utf8_bytes_business", "native_host_business_script_elapsed_sum_ns"]
    groups = {}
    for group in ("N", "P"):
        selected = [row for row in cells if row["group"] == group]
        groups[group] = {
            "cells": [row["cell"] for row in selected], "n": len(selected),
            "quality_complete_correct": sum(row["quality"] == "complete_correct" for row in selected),
            "sum": sum_fields(selected, metrics),
            "median": {field: statistics.median(row[field] for row in selected) for field in metrics},
            "usage_sum": sum_fields([row["consumer_usage_final_cumulative"] for row in selected],
                                    ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens")),
            "usage_median": {field: statistics.median(row["consumer_usage_final_cumulative"][field] for row in selected)
                             for field in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens")},
        }
    by_cell = {row["cell"]: row for row in cells}
    paired = [{"round": index, "N": "N" + str(index), "P": "P" + str(index),
               "full_cell_P_over_N": ratio(by_cell["P" + str(index)]["full_cell_wall_ns"], by_cell["N" + str(index)]["full_cell_wall_ns"])}
              for index in (1, 2, 3)]
    ratios = [Fraction(row["full_cell_P_over_N"]["numerator"], row["full_cell_P_over_N"]["denominator"]) for row in paired]
    median_ratio = sorted(ratios)[1]
    gate = {
        "quality_both_3_of_3": all(row["quality_complete_correct"] == 3 for row in groups.values()),
        "paired_full_wall_ratio_median": ratio(median_ratio.numerator, median_ratio.denominator),
        "paired_full_wall_limit": 0.70, "paired_full_wall_pass": median_ratio <= Fraction(7, 10),
        "P_input_plus_output_tokens": groups["P"]["sum"]["total_input_plus_output_tokens"],
        "N_input_plus_output_tokens": groups["N"]["sum"]["total_input_plus_output_tokens"],
        "token_pass": groups["P"]["sum"]["total_input_plus_output_tokens"] <= groups["N"]["sum"]["total_input_plus_output_tokens"],
    }
    gate["overall_pass"] = gate["quality_both_3_of_3"] and gate["paired_full_wall_pass"] and gate["token_pass"]
    root = read(BATCH / "cost" / "ROOT_RECONCILIATION.json")
    need(root["median_paired_full_wall_ratio"]["numerator"] == median_ratio.numerator, "root paired numerator")
    need(root["median_paired_full_wall_ratio"]["denominator"] == median_ratio.denominator, "root paired denominator")
    for group, group_result in groups.items():
        root_group = root["groups"][group]
        need(root_group["full_wall_sum_ns"] == group_result["sum"]["full_cell_wall_ns"], group + " independent full sum")
        need(root_group["full_wall_median_ns"] == group_result["median"]["full_cell_wall_ns"], group + " independent full median")
        need(root_group["input_plus_output_tokens"] == group_result["sum"]["total_input_plus_output_tokens"], group + " independent token sum")
    for original in root["six_original_cells"]:
        derived = by_cell[original["cell"]]
        need(original["full_cell_wall_ns"] == derived["full_cell_wall_ns"], derived["cell"] + " independent full")
        need(original["input_tokens"] == derived["consumer_usage_final_cumulative"]["input_tokens"], derived["cell"] + " independent input")
        need(original["output_tokens"] == derived["consumer_usage_final_cumulative"]["output_tokens"], derived["cell"] + " independent output")
        need(original["thread_id"] == derived["thread_id"], derived["cell"] + " independent thread")
    run = read(BATCH / "RUN_RESULT.json")
    formal = read(BATCH / "FORMAL_PROCESS.json")
    publication = read(BATCH / "FORMAL_PUBLICATION.json")
    preparation = read(BATCH / "PREPARATION_COST.json")
    package = read(BATCH / "private" / "PACKAGING_COST.json")
    need(formal["ended_ns"] - formal["started_ns"] > sum(row["full_cell_wall_ns"] for row in cells), "batch includes cells and setup")
    need(run["batch_ended_ns"] - run["batch_started_ns"] == run["batch_wall_ns"], "run batch span")
    need(formal["ended_ns"] == publication["terminal_observed_ns"], "batch publication anchor")
    need(publication["publication_closed_ns"] - publication["publication_started_ns"] == publication["publication_ns"], "batch publication span")
    result = {
        "schema": "m4_surface_scan_consumption_cost_accounting_v1", "original_delivery_commit": seal["delivery_commit"],
        "source_product_commit": seal["product_commit"], "quality_seal_sha256": SEAL_SHA256,
        "analysis_scope": "offline original evidence only; no product changes or new Blender/model/API executions",
        "formulas": {"pair_ratio": "CELL_FINAL_TIMING[P_i].full_cell_wall_ns / CELL_FINAL_TIMING[N_i].full_cell_wall_ns",
                     "wall_gate": "median of the fixed three exact pair ratios <= 7/10",
                     "token_gate": "sum_P(final cumulative input_tokens + output_tokens) <= sum_N(same)",
                     "units": "integer ns and UTF-8 bytes; reported tokens are actual final CLI usage fields"},
        "gate": gate, "paired": paired, "groups": groups, "cells": cells,
        "independent_root_reconciliation": "same fixed cell, group and paired-wall/token values verified",
        "shared_costs": {
            "formal_process": formal, "formal_publication": publication,
            "run_models_wall_ns": run["batch_wall_ns"],
            "formal_wall_ns": formal["ended_ns"] - formal["started_ns"],
            "sum_full_cells_ns": sum(row["full_cell_wall_ns"] for row in cells),
            "formal_minus_sum_full_cells_ns": formal["ended_ns"] - formal["started_ns"] - sum(row["full_cell_wall_ns"] for row in cells),
            "sum_cell_timing_receipt_publication_ns": sum(row["timing_publication"]["timing_receipt_publication_ns"] for row in cells),
            "preparation": preparation, "packaging": package,
            "reused_install_elapsed_ns_scope": "Historical existing isolated install preparation value. No rebuild during this consumer batch; reported without per-group amortization.",
            "unmeasured": ["preceding coordinator/model preparation cost", "total preparation wall", "post-archive verification and receipt publication", "review and Git delivery wall", "fees and subscription debits", "explicit fsync persistence", "thin-client actual exit", "actual resolved model version and effort", "provider request count and per-call generation time", "native TCP wire byte total", "native authored solver primitive/vertex read instrumentation"],
        },
        "non_additivity": "Parent spans include child work. Do not add CLI tool, owner, host and product durations to full task wall, or add UTF-8 serialization layers together as unique data.",
        "checks": CHECKS, "sources": [{"path": path, **record} for path, record in sorted(SOURCES.items())],
        "learning_binding": {"context_bound": False, "host_epoch": 5, "rebind_required": True, "task_write": "not attempted without hook-issued handle"},
    }
    (HERE / "LEDGER.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps({"checks": CHECKS, "source_files": len(SOURCES), "gate": gate}, ensure_ascii=False))


def write_report(result):
    lines = [
        "# 同原件成本复核账本", "",
        "本批固定为六个新 owned 进程与独立模型 thread 的消费格，按 N1/P1、P2/N2、N3/P3 的原顺序保留。冷态范围覆盖每格新引擎实例与本格场景缓存，provider cached input 实际非零。只执行离线文件核对与计算，新增 Blender、消费者和业务 API 执行均为 0。独立质量 seal 在成本解封前完成，双方各 3/3 complete_correct。", "",
        "## 原准入门", "",
        "| 项目 | 原门 | 实测 | 结果 |", "| --- | --- | --- | --- |",
        "| 最终质量 | 双方各 3/3 完整正确 | 双方各 3/3 | 通过 |",
        f"| 固定配对完整墙钟比值中位 | ≤ 0.70 | {result['gate']['paired_full_wall_ratio_median']['value']:.15f} | 未通过 |",
        f"| P 累计 input+output | ≤ N 的 {result['gate']['N_input_plus_output_tokens']} | {result['gate']['P_input_plus_output_tokens']} | 未通过 |", "",
        "本批整体准入未通过。质量封存后的成本结论保持原门。完整配对比值使用整数纳秒的精确分数计算。", "",
        "| 固定配对 | P/N | 精确分数 |", "| --- | --- | --- |",
    ]
    for pair in result["paired"]:
        value = pair["full_cell_P_over_N"]
        lines.append(f"| P{pair['round']}/N{pair['round']} | {value['value']:.15f} | {value['numerator']}/{value['denominator']} |")
    lines.extend([
        "", "## 每格时界", "",
        "所有秒数由整数纳秒除以 1e9。full 从初始输入检查前开始，覆盖 owner/消费者启动、工具和收尾、最终业务记录写入关闭、已启动后端的 owned 清理。prefix 截至原 driver 提前采样点。", "",
        "| 格 | full 秒 | prefix 秒 | prefix 后业务尾段 ms | prompt→final 秒 | CLI 工具区间合计秒 | 该区间外余量秒 | 计时回执发布 ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['full_cell_wall_ns']/1e9:.7f} | {row['prefix_wall_ns']/1e9:.7f} | {row['business_close_minus_prefix_ns']/1e6:.4f} | {row['lifecycle_partitions_ns']['prompt_to_final_inclusive_ns']/1e9:.7f} | {row['CLI_tool_intervals_sum_ns']/1e9:.7f} | {row['prompt_to_final_non_tool_remainder_ns']/1e9:.7f} | {row['timing_publication']['timing_receipt_publication_ns']/1e6:.4f} |")
    lines.extend([
        "", "prompt→final 覆盖工具调用。区间外余量混合模型生成、网络、provider、CLI 调度和事件回传，现有时间戳无法继续分离。它不能当成纯模型计算耗时。owner、host、product 的嵌套耗时保留在 JSON，避免与 full 重复相加。", "",
        "| 组 | full 总秒 | full 中位秒 | prompt→final 总秒 | 工具 owner 总秒 | 工具 CLI 总秒 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for group, record in result["groups"].items():
        selected = [row for row in result["cells"] if row["group"] == group]
        prompt_sum = sum(row["lifecycle_partitions_ns"]["prompt_to_final_inclusive_ns"] for row in selected)
        lines.append(f"| {group} | {record['sum']['full_cell_wall_ns']/1e9:.7f} | {record['median']['full_cell_wall_ns']/1e9:.7f} | {prompt_sum/1e9:.7f} | {record['sum']['owner_tool_elapsed_sum_ns']/1e9:.7f} | {record['sum']['CLI_tool_intervals_sum_ns']/1e9:.7f} |")
    lines.extend([
        "", "组中位数单列。原门使用上表三个配对比值的中位数。", "",
        "## 实际 usage", "",
        "每格 raw events.jsonl 只有一个带 usage 的 turn.completed。该终值逐字段核对 CONSUMER.usage 与 usage_rows，按最终累计使用一次。cached input 属于 input，reasoning output 属于 output。cache_write_input_tokens 六格均为 0。", "",
        "| 格 | input | cached input | uncached input | output | reasoning output | input+output |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        usage = row["consumer_usage_final_cumulative"]
        lines.append(f"| {row['cell']} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {row['uncached_input_tokens']} | {usage['output_tokens']} | {usage['reasoning_output_tokens']} | {row['total_input_plus_output_tokens']} |")
    lines.extend(["", "| 组与统计 | input | cached input | output | reasoning output | input+output |", "| --- | --- | --- | --- | --- | --- |"])
    for group, record in result["groups"].items():
        for label, usage, values in (("总和", record["usage_sum"], record["sum"]), ("中位", record["usage_median"], record["median"])):
            lines.append(f"| {group} {label} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['reasoning_output_tokens']} | {values['total_input_plus_output_tokens']} |")
    lines.extend([
        "", "只有整轮实际累计 usage，逐模型请求的输入、输出和重试次数缺少 provider 回执。可见 retry_observations 为空，provider_requests 与 fees 仍为 null。token 门不扣除 cached input，费用与订阅扣费未测。", "",
        "## 全部工具尝试和字节", "",
        "| 格 | 工具尝试/失败 | observe/native | 实际记录的工具文本 UTF-8 B | business MCP 响应包 B | 全部 MCP RX B | 全部 MCP TX B |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        lines.append(f"| {row['cell']} | {row['tool_attempts']}/{row['failed_tool_attempts']} | {row['tools_by_name'].get('human_eye_scene_observe',0)}/{row['tools_by_name'].get('execute_blender_code',0)} | {row['recorded_model_facing_tool_text_utf8_bytes']} | {row['tool_response_envelope_bytes']} | {row['bridge_rx_bytes']} | {row['bridge_tx_bytes']} |")
    lines.extend([
        "", "工具文本按真实 completed MCP 事件 result.content 中 text 的 UTF-8 字节求和，并逐条核对 owner 的同一 content。它表示宿主记录的实际模型侧接口内容。provider 最终上下文拼装、截断和实际模型阅读尚无消费证明。MCP 响应包是薄客户端 RX.bin 的原始长度，包含 JSON 转义、RPC 信封和换行。全部 MCP RX/TX 还包括 initialize、notifications/initialized 和 tools/list，每格 3 次管理请求。各序列化层字节分开列示。", "",
        "N 合计 11 次工具尝试、0 次失败，P 合计 15 次工具尝试、3 次失败。P 的失败保留在成本和中间事件中，最终六格全部完成。三次失败均有正常 MCP 错误响应，未触发本批替补或重跑。每格 stdout 还有 2 条 CLI error 类提示，分别为开发中开关和请求模型的本地 metadata fallback，完整文字保留在 JSON。stderr 的额外运行诊断按下表全部保留。provider 实际模型版本与 effort 没有独立解析证据。", "",
        "| 格 | stderr metadata fallback WARN | shell snapshot WARN | model refresh timeout ERROR | analytics transport WARN | 其他 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        counts = row["CLI_stderr"]["counts"]
        lines.append(f"| {row['cell']} | {counts.get('metadata_fallback_warn',0)} | {counts.get('shell_snapshot_warn',0)} | {counts.get('model_refresh_timeout_error',0)} | {counts.get('analytics_transport_warn',0)} | {counts.get('other',0)} |")
    lines.extend([
        "", "每条 stderr 原行、行号、含换行的原始字节长度与 SHA256 保存在 LEDGER.CLI_stderr。model refresh timeout 属于可用模型目录刷新，analytics 错误属于遥测发送，它们均保留在实际完整墙钟中。provider_retry_observations 为空仅描述该录制字段。各诊断的阻塞时间、是否与业务并行，以及对本批延迟差额的贡献尚无独立时界，未由日志条数推算耗时或推理 API 失败。", "",
        "## 宿主、内部采集与图片", "",
        "| 格 | native host 全请求 | 业务脚本/管理 | native host 业务 stdout UTF-8 B | P product RPC 业务/管理 | P product RX/TX B |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        product = row["product"]
        product_calls = f"{product['business_rpcs']}/{product['administrative_rpcs']}" if product else "0/0"
        product_bytes = f"{product['rpc']['rx_bytes']}/{product['rpc']['tx_bytes']}" if product else "0/0"
        lines.append(f"| {row['cell']} | {row['native_host_requests_including_close']} | {row['native_host_business_scripts']}/{row['native_host_administrative_requests']} | {row['native_host_stdout_utf8_bytes_business']} | {product_calls} | {product_bytes} |")
    lines.extend([
        "", "native host 包含每格两次管理快照和一次关闭请求。其余业务脚本包含消费者原生调用及 P 产品内部采集。close 的 worker 事件 status=unknown 反映这条管理请求没有 script 状态，独立 native close 回执确认关闭。六份薄客户端 EXIT 仍缺失，status=unknown、missing_exit_count=1，未用后端退出替代。", "",
        "P 每格第一次 scan 业务采集 stdout 为 147114 B，第二次为 90893 B。两次共 238007 B，三格共 714021 B。P native host 业务 stdout 总计 721214 B，含产品采集及消费者原生补查。N 对应总计 25564 B。这里按 WORKER_EVENTS 的实际返回 stdout 统计。native TCP 请求/响应信封总字节没有完整录制，保持未测。", "",
        "| P 格/观察序号 | engine_invoked | kernel_calls | cache_before/after | source V/F 逻辑规模 | delta 实际 resource V/F 读取 | delta scan_cache_hits |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in result["cells"]:
        if row["product"] is None:
            continue
        for index, observation in enumerate(row["product"]["observations"], 1):
            acquisition = observation["acquisition_work"]
            delta = acquisition.get("residency_delta", {})
            lines.append(f"| {row['cell']}/{index} | {observation['engine_invoked']} | {observation['kernel_calls']} | {observation['cache_entries_before']}/{observation['cache_entries_after']} | {acquisition.get('source_vertices')}/{acquisition.get('source_faces')} | {delta.get('resource_vertices_read')}/{delta.get('resource_faces_read')} | {delta.get('scan_cache_hits')} |")
    lines.extend([
        "", "source V/F、expanded V/F 等是响应逻辑规模。实际资源读取使用已记录 residency_delta，避免将缓存复用计成重新展开。native 消费者自己编写算法的循环、局部求值次数和 primitive tests 未统一插桩，保持未测。各实际执行脚本 SHA 与 worker 的 code SHA 核对，落盘 CRLF 先还原为 LF，原始文件长度另列。", "",
        "六格共同题面 405 B，输入图片 0，交付工具图片 0，图片交付字节 0。原生 helper 的 PNG 扫描和 render hooks 未观察到新图片，任意 Python 及瞬时行为超出该观测范围。独立 image_tokens 为 null，未据零图片推算专门的 token 回执。", "",
        "## 批次、准备与发布", "",
    ])
    shared = result["shared_costs"]
    lines.extend([
        f"六格 full 合计 {shared['sum_full_cells_ns']/1e9:.7f} 秒。run_models 总时界 {shared['run_models_wall_ns']/1e9:.7f} 秒。外层 FORMAL_PROCESS 总时界 {shared['formal_wall_ns']/1e9:.7f} 秒，包含六格及批次准备/收尾，较六格 full 合计多 {shared['formal_minus_sum_full_cells_ns']/1e6:.4f} ms。这一共享差额保留整体，不任意摊给组别。", "",
        f"六格 CELL_FINAL_TIMING 文件发布合计 {shared['sum_cell_timing_receipt_publication_ns']/1e6:.4f} ms。FORMAL_PROCESS 终态文件发布 {shared['formal_publication']['publication_ns']/1e6:.4f} ms。记录这两个发布耗时的 CELL_TIMING_PUBLICATION、FORMAL_PUBLICATION 文件自身写入及更后续协调成本仍未测。", "",
        f"本批 bootstrap 已测 {shared['preparation']['bootstrap_elapsed_ns']/1e6:.4f} ms，前置协调和总 preparation wall 未测。资产与 opt1.r1 隔离安装均复用已有来源，本批 installation_rebuilds=0。reused_install_elapsed_ns={shared['preparation']['reused_install_elapsed_ns']} 是历史安装准备耗时，不计入本批某一格，也未在组别间摊销。", "",
        f"公共 ZIP 打包写入关闭 {shared['packaging']['archive_creation_ns']/1e6:.4f} ms。后续 ZIP 核验、回执发布、审核、Git 推送及协调模型成本未被完整计时。费用和订阅扣费未测。持久化保持原缓冲写入关闭口径，fsync 到盘保障未测。", "",
        "## 可复算与保留项", "",
        f"recompute.py 使用 Python 标准库重新读取 {len(result['sources'])} 个证据文件，执行 {result['checks']} 个断言后生成 LEDGER.json 与本报告。LEDGER.sources 保存每个读取原件的字节与 SHA256。根独立账本的 full/token/配对结果另外交叉核对，检查结论一致。", "",
        "首次离线执行发现落盘 SCRIPT.py 使用 Windows CRLF，直接字节 SHA 不等于 worker 的原 code SHA。核明换行转换后，脚本对 CRLF→LF 的字节校验与 worker SHA 全部一致，原始文件保留。该核验工具修正没有变更六格输入或原件。", "",
        "实际模型版本、effort、provider 调用次数、生成区间细分、native 总线字节、原生算法统一工作量、准备总成本、费用、thin EXIT 和明确到盘状态均保留未知。六个样本属于同一固定任务的重复，广域泛化与尾部稳定性没有由本批建立。", "",
    ])
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
