"""Summarize completed public consumers without invoking Blender or an LLM."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SEQUENCES = dict(v1=[("s01", "native"), ("s01", "facts"), ("s02", "facts"), ("s02", "native")],
    v2=[("s02", "facts"), ("s01", "facts")])
FINAL_FIELDS = ("task_id", "status", "operation_id", "version", "saved_blend", "readback",
    "center_over_h", "core_median_over_h", "remaining")


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_bytes()) if path.exists() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def size(path):
    return path.stat().st_size if path.exists() else 0


def artifact_path(root, value):
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def artifact_identity(root, artifact):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
        return dict(verified=False, reason="artifact_identity_absent")
    path = artifact_path(root, artifact["path"])
    if not path.is_file():
        return dict(verified=False, reason="artifact_file_absent", path=str(path))
    data = path.read_bytes()
    actual = dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return dict(verified=artifact.get("sha256") == actual["sha256"] and artifact.get("bytes") == actual["bytes"], actual=actual)


def reference_matches(root, supplied, artifacts, named_records=()):
    if isinstance(supplied, str) and supplied in named_records:
        return dict(verified=True, match="record_label")
    value = supplied if isinstance(supplied, dict) else dict(path=supplied)
    if not isinstance(value.get("path"), str):
        return dict(verified=False, reason="reference_path_or_record_label_absent")
    supplied_path = artifact_path(root, value["path"])
    for expected in artifacts:
        if supplied_path != artifact_path(root, expected["path"]):
            continue
        if not supplied_path.is_file():
            return dict(verified=False, reason="referenced_file_absent")
        identity = artifact_identity(root, expected) if "sha256" in expected else dict(verified=True)
        if not identity["verified"]:
            return dict(verified=False, reason="receipt_artifact_identity_changed")
        for key in ("sha256", "bytes"):
            if key in value and value[key] != expected.get(key):
                return dict(verified=False, reason="quoted_" + key + "_mismatch")
        return dict(verified=True, match="artifact_path_and_supplied_identity_fields")
    return dict(verified=False, reason="reference_not_in_matching_saved_version_receipts")


def parse_final(text):
    text = text.strip()
    formatting = "plain_json"
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if lines[0] in ("```", "```json"):
            text = "\n".join(lines[1:-1])
            formatting = "fenced_json"
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None, "invalid_JSON"
    return (value, formatting) if isinstance(value, dict) else (None, "JSON_object_required")


def numeric_claim(claim, actual):
    if type(claim) not in (int, float) or not math.isfinite(claim) or type(actual) not in (int, float):
        return dict(verified=False, actual=actual, reason="finite_numeric_claim_or_measurement_absent")
    difference = claim - actual
    return dict(verified=math.isclose(claim, actual, rel_tol=1e-6, abs_tol=1e-8), actual=actual,
        absolute_difference=abs(difference), comparison="relative_tolerance_1e-6_absolute_tolerance_1e-8")


def quality_summary(quality):
    checks = quality.get("checks", {})
    return dict(status=quality.get("status", "unavailable"), checks=checks,
        failed_checks=[name for name, value in checks.items() if value is False],
        unknown_checks=[name for name, value in checks.items() if value is None],
        center_over_h=quality.get("displacement", {}).get("center_over_h"),
        core_median_over_h=quality.get("displacement", {}).get("core_median_over_h"))


def session_receipts(root, directory, state):
    records = []
    for operation in state.get("operations", []):
        item = dict(operation)
        item["receipt_source"] = "session_operations"
        if operation.get("status") == "saved_and_independently_read":
            item["receipt_file"] = str(directory / "versions" / str(operation["version"]).zfill(3) / "OPERATION.json")
        records.append(item)
    for path in sorted((directory / "readbacks").glob("*/READBACK.json")):
        item = read(path)
        item["receipt_source"], item["receipt_file"] = "extra_readback", str(path)
        records.append(item)
    for item in records:
        item["saved_artifact_check"] = artifact_identity(root, item.get("saved_blend"))
        item["readback_artifact_check"] = artifact_identity(root, item.get("readback"))
        quality_path = item.get("quality_record")
        if quality_path:
            quality = read(artifact_path(root, quality_path), {})
            item["quality_file_present"] = bool(quality)
            item["quality_matches_embedded_receipt"] = quality_summary(quality) == quality_summary(item.get("quality", {}))
    return records


def final_claims(root, task_id, consumer, state, receipts):
    final, formatting = parse_final(consumer.get("final", ""))
    result = dict(format=formatting, parsed=final is not None, missing_fields=[], field_checks={},
        all_reference_fields_verified=False, all_measured_claims_consistent=False,
        remaining_text_validation="retained_for_human_review")
    if final is None:
        return result
    result["missing_fields"] = [name for name in FINAL_FIELDS if name not in final]
    result["final"] = final
    operation = next((row for row in receipts if row.get("operation_id") == final.get("operation_id") and row.get("status") == "saved_and_independently_read"), None)
    matching = [row for row in receipts if row.get("version") == final.get("version") and row.get("independently_reopened") is True]
    fields = dict(task_id=final.get("task_id") == task_id, operation_id=operation is not None,
        version=type(final.get("version")) is int and operation is not None and final["version"] == operation.get("version") == state.get("version"))
    saved = [operation["saved_blend"]] if operation is not None else []
    fields["saved_blend"] = reference_matches(root, final.get("saved_blend"), saved)
    readback_artifacts, labels = [], []
    for row in matching:
        if not row["readback_artifact_check"]["verified"] or not row["saved_artifact_check"]["verified"]:
            continue
        readback_artifacts.append(row["readback"])
        for name in ("quality_record", "receipt_file"):
            if row.get(name):
                readback_artifacts.append(dict(path=row[name]))
        if row.get("reader_job") and (root / "private/jobs" / row["reader_job"] / "receipt.json").exists():
            labels.append(row["reader_job"])
    fields["readback"] = reference_matches(root, final.get("readback"), readback_artifacts, labels)
    quality = {}
    if operation is not None and operation.get("quality_record"):
        quality = read(artifact_path(root, operation["quality_record"]), {})
    fields["status"] = final.get("status") in ("pass", "fail", "unknown") and final.get("status") == quality.get("status")
    for name in ("center_over_h", "core_median_over_h"):
        fields[name] = numeric_claim(final.get(name), quality.get("displacement", {}).get(name))
    result["field_checks"] = fields
    reference_fields = (fields["task_id"], fields["operation_id"], fields["version"], fields["saved_blend"]["verified"], fields["readback"]["verified"])
    result["all_reference_fields_verified"] = all(reference_fields)
    result["all_measured_claims_consistent"] = bool(fields["status"] and all(fields[name]["verified"] for name in ("center_over_h", "core_median_over_h")))
    return result


def tool_metrics(folder):
    calls, python_rows, fact_rows = [], [], []
    seen_reads, snapshots, independent_versions = set(), Counter(), set()
    repeated_reads = extra_readbacks = 0
    for directory in sorted((folder / "bridge").glob("tool_*")):
        request, cost = read(directory / "REQUEST.json", {}), read(directory / "COST.json", {})
        if not cost:
            continue
        name = request.get("name")
        result = read(directory / "COMPLETE_RESULT.json", {})
        version = result.get("version", result.get("session_binding", {}).get("session_version"))
        row = dict(index=cost.get("index"), name=name, status=cost.get("status"), wall_s=cost.get("wall_s"),
            public_response_UTF8_bytes=cost.get("public_text_UTF8_bytes", 0), complete_result_UTF8_bytes=cost.get("complete_text_UTF8_bytes"),
            request_audit_bytes=size(directory / "REQUEST.json"), truncated=cost.get("truncated", False))
        successful = cost.get("status") == "completed"
        if name == "execute_python":
            execution = read(directory / "python/EXECUTION.json", cost.get("execution", {}))
            worker = execution.get("worker") or {}
            observed = execution.get("observed_version")
            snapshots[observed] += 1
            parent_wall, worker_wall = execution.get("wall_s"), worker.get("worker_wall_s_before_write")
            python_row = dict(index=row["index"], observed_version=observed, status=execution.get("status"),
                input_JSON_bytes=execution.get("input_JSON_bytes"), executor_wall_s=parent_wall,
                worker_wall_s=worker_wall,
                executor_minus_worker_wall_s=parent_wall-worker_wall if parent_wall is not None and worker_wall is not None else None,
                bridge_minus_executor_wall_s=row["wall_s"]-parent_wall if row["wall_s"] is not None and parent_wall is not None else None,
                worker_CPU_s=worker.get("process", {}).get("CPU_s"), peak_working_set_bytes=worker.get("process", {}).get("peak_working_set_bytes"),
                stdout_UTF8_bytes=len(worker.get("stdout", "").encode("utf8")), stderr_UTF8_bytes=len(worker.get("stderr", "").encode("utf8")),
                raw_worker_output_bytes=size(directory / "python/STDOUT.bin") + size(directory / "python/STDERR.bin"),
                created_payloads=len(worker.get("created_payloads", [])), error=worker.get("error", execution.get("error")),
                input_transport=execution.get("input_transport", "inline_arrays"), snapshot=cost.get("snapshot"),
                JSON_encode_wall_s=execution.get("JSON_encode_wall_s"), JSON_encode_CPU_s=execution.get("JSON_encode_CPU_s"),
                worker_transport=worker.get("transport"))
            python_rows.append(python_row)
            version = observed
        if name in ("focus", "resolve_ref"):
            fact_rows.append(dict(index=row["index"], name=name, version=version, wall_s=row["wall_s"],
                fact_reported_wall_s=result.get("cost", {}).get("wall_s"), CPU_s=result.get("cost", {}).get("CPU_s"),
                stages=result.get("cost", {}).get("stages"), public_response_UTF8_bytes=row["public_response_UTF8_bytes"],
                cache_hit_directly_recorded=result.get("cache_hit")))
        if successful and name in ("state", "focus", "resolve_ref") and version is not None:
            key = (name, version, json.dumps(request.get("arguments", {}), sort_keys=True))
            row["identical_read_repeat_same_version"] = key in seen_reads
            repeated_reads += int(key in seen_reads)
            seen_reads.add(key)
        if successful and name == "save_readback":
            row["additional_readback_after_independent_receipt"] = version in independent_versions
            extra_readbacks += int(version in independent_versions)
        if successful and result.get("independently_reopened") is True and version is not None:
            independent_versions.add(version)
        calls.append(row)
    counts = Counter(row["name"] for row in calls)
    python_totals = {key: sum(row.get(key) or 0 for row in python_rows) for key in
        ("input_JSON_bytes", "executor_wall_s", "worker_wall_s", "executor_minus_worker_wall_s", "bridge_minus_executor_wall_s", "worker_CPU_s", "raw_worker_output_bytes", "JSON_encode_wall_s", "JSON_encode_CPU_s")}
    for key in ("JSON_encode_wall_s", "JSON_encode_CPU_s"):
        if not any(row.get(key) is not None for row in python_rows):
            python_totals[key] = None
    snapshots_recorded = [row["snapshot"] for row in python_rows if row.get("snapshot")]
    python_totals["packet_snapshot"] = dict(measured_calls=len(snapshots_recorded),
        cold_creations=sum(not row["cache_hit"] for row in snapshots_recorded),
        warm_hits=sum(row["cache_hit"] for row in snapshots_recorded),
        wall_s=sum(row["wall_s"] for row in snapshots_recorded) if snapshots_recorded else None,
        CPU_s=sum(row["CPU_s"] for row in snapshots_recorded) if snapshots_recorded else None,
        creation_wall_s=sum(row["creation_wall_s"] for row in snapshots_recorded) if snapshots_recorded else None,
        packet_read_wall_s=sum((row.get("worker_transport") or {}).get("packet_validate_load_wall_s", 0) for row in python_rows) if snapshots_recorded else None,
        JSON_decode_wall_s=sum((row.get("worker_transport") or {}).get("input_JSON_decode_wall_s", 0) for row in python_rows) if any(row.get("worker_transport") for row in python_rows) else None)
    python_totals.update(calls=len(python_rows), worker_errors=sum(row["status"] != "completed" for row in python_rows),
        maximum_worker_peak_bytes=max((row.get("peak_working_set_bytes") or 0 for row in python_rows), default=0),
        repeated_same_version_snapshot_transfers=sum(max(0, count-1) for count in snapshots.values()),
        transport_latency_separately_measured=False,
        remainder_scope="Executor minus reported worker includes process launch, input/result serialization and transport, and work outside the worker timer. Bridge minus executor includes snapshot preparation and bridge bookkeeping.")
    return dict(calls=calls, counts=dict(counts), tool_wall_s=sum(row["wall_s"] or 0 for row in calls),
        public_response_UTF8_bytes=sum(row["public_response_UTF8_bytes"] for row in calls),
        request_audit_bytes=sum(row["request_audit_bytes"] for row in calls),
        failed_calls=sum(row["status"] != "completed" for row in calls), truncated_calls=sum(row["truncated"] for row in calls),
        python=python_totals, python_calls=python_rows, facts_calls=fact_rows,
        facts_wall_s=sum(row["wall_s"] or 0 for row in fact_rows),
        facts_public_response_UTF8_bytes=sum(row["public_response_UTF8_bytes"] for row in fact_rows),
        potential_redundancy=dict(identical_read_repeats_same_version=repeated_reads,
            additional_readbacks_after_independent_receipt=extra_readbacks,
            interpretation="Structural repeats and extra verifications only. Their necessity requires reading the retained tool sequence."))


def public_event_summary(path):
    counts, tool_count, malformed = Counter(), 0, 0
    if path.exists():
        for raw in path.read_text(encoding="utf8").splitlines():
            try:
                event = json.loads(raw).get("event", {})
            except ValueError:
                malformed += 1
                continue
            counts[event.get("type", "absent")] += 1
            if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "mcp_tool_call":
                tool_count += 1
    return dict(counts=dict(counts), completed_MCP_tools=tool_count, malformed_retained_rows=malformed, retained_jsonl_bytes=size(path))


def api_metrics(root, session):
    jobs = []
    for path in sorted((root / "private/jobs").glob("*/job.json")):
        job = read(path)
        output = job.get("output_blend", job.get("readback_npz"))
        if output is None or not artifact_path(root, output).is_relative_to(session.resolve()):
            continue
        run = read(path.parent / "run.json", {})
        process = run.get("process", {})
        jobs.append(dict(label=path.parent.name, kind="write" if job.get("output_blend") else "read",
            wall_s=run.get("wall_s"), process_wall_s=process.get("full_process_wall_s"), CPU_s=process.get("tree_cpu_s"),
            status=process.get("status"), returncode=process.get("returncode"),
            receipt_present=(path.parent / "receipt.json").exists(), log=str(path.parent / "run.json")))
    return dict(jobs=jobs, job_count=len(jobs), writes=sum(row["kind"] == "write" for row in jobs),
        reads=sum(row["kind"] == "read" for row in jobs), wall_s=sum(row["wall_s"] or 0 for row in jobs),
        all_recorded_processes_exited_zero=bool(jobs) and all(row["returncode"] == 0 for row in jobs),
        all_receipts_present=bool(jobs) and all(row["receipt_present"] for row in jobs))


def analyze_session(root, stage, task_id, route):
    folder = root / "private/consumers" / stage / task_id / route
    consumer = read(folder / "CONSUMER.json", {})
    row = dict(stage=stage, task_id=task_id, route=route, transport_status=consumer.get("status", "not_started"))
    if row["transport_status"] in ("not_started", "running"):
        return row, dict(summary=row)
    directory = root / "private/sessions" / (stage + "_" + task_id + "_" + route)
    state = read(directory / "session.json", {})
    receipts = session_receipts(root, directory, state)
    saved = [item for item in receipts if item.get("status") == "saved_and_independently_read"]
    current = next((item for item in reversed(saved) if item.get("version") == state.get("version")), {})
    quality_path = current.get("quality_record")
    quality = read(artifact_path(root, quality_path), {}) if quality_path else current.get("quality", {})
    metrics = tool_metrics(folder)
    api = api_metrics(root, directory)
    claims = final_claims(root, task_id, consumer, state, receipts)
    bridge = read(folder / "bridge/BRIDGE_RESULT.json", consumer.get("bridge", {}))
    cleanup = dict(process=consumer.get("process_cleanup"), readers_stopped=consumer.get("readers_stopped"),
        safe_to_continue=consumer.get("safe_to_continue"), exit_code=consumer.get("exit_code"),
        deadline_timer_fired=consumer.get("deadline_timer_fired"), bridge_closed=bridge.get("closed"))
    actual_save = bool(current and current["saved_artifact_check"]["verified"])
    actual_read = bool(current and current.get("independently_reopened") is True and current["readback_artifact_check"]["verified"])
    row.update(valid_public_completion=consumer.get("valid_completion"), wall_s=consumer.get("wall_s"),
        prompt_to_final_s=consumer.get("prompt_to_final_s"), usage=consumer.get("usage"),
        tools=len(metrics["calls"]), tools_by_name=metrics["counts"], tool_wall_s=metrics["tool_wall_s"],
        input_prompt_UTF8_bytes=consumer.get("input_prompt_UTF8_bytes"), public_tool_response_UTF8_bytes=metrics["public_response_UTF8_bytes"],
        public_messages_UTF8_bytes=sum(len(message.get("text", "").encode("utf8")) for message in consumer.get("public_messages", [])),
        final_UTF8_bytes=consumer.get("output_text_UTF8_bytes"), actual_saved=actual_save, actual_independent_readback=actual_read,
        saved_operations=len(saved), current_version=state.get("version"), pending_edit=bool(state.get("pending")),
        quality=quality_summary(quality), python=metrics["python"],
        facts=dict(calls=len(metrics["facts_calls"]), wall_s=metrics["facts_wall_s"], public_response_UTF8_bytes=metrics["facts_public_response_UTF8_bytes"]),
        potential_redundancy=metrics["potential_redundancy"], failed_tools=metrics["failed_calls"], truncated_tools=metrics["truncated_calls"],
        final_JSON=dict(format=claims["format"], missing_fields=claims["missing_fields"],
            all_reference_fields_verified=claims["all_reference_fields_verified"], all_measured_claims_consistent=claims["all_measured_claims_consistent"]),
        API={key: value for key, value in api.items() if key != "jobs"},
        cleanup=cleanup, immutable_consumer_inputs=consumer.get("source_unchanged"),
        artifact_identity_checks=dict(saved_blend=current.get("saved_artifact_check"), readback=current.get("readback_artifact_check")))
    detail = dict(summary=row, final_claims=claims, tools=metrics, API=api, receipts=receipts, public_events=public_event_summary(folder / "events.jsonl"),
        consumer_errors=consumer.get("errors"), provider_retry_observations=consumer.get("provider_retry_observations"),
        original_logs=dict(consumer=str(folder / "CONSUMER.json"), bridge=str(folder / "bridge"), session=str(directory / "session.json")))
    return row, detail


def compact_table(rows):
    lines = ["| Stage | Task | Route | Saved/read | Quality | Final refs/claims | Wall s | Tokens in/out | Tools | Public tool bytes |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        usage, final = row.get("usage") or {}, row.get("final_JSON", {})
        wall = row.get("wall_s")
        lines.append("| " + " | ".join(str(value) for value in (row["stage"], row["task_id"], row["route"],
            str(row.get("actual_saved")) + "/" + str(row.get("actual_independent_readback")), row.get("quality", {}).get("status", row["transport_status"]),
            str(final.get("all_reference_fields_verified")) + "/" + str(final.get("all_measured_claims_consistent")),
            round(wall, 3) if wall is not None else "", str(usage.get("input_tokens", "")) + "/" + str(usage.get("output_tokens", "")),
            row.get("tools", ""), row.get("public_tool_response_UTF8_bytes", ""))) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), default="v1")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    if args.stage == "v1" and (HERE / "OPTIMIZATION_BINDING.json").exists() and (HERE / "CONSUMER_STATS_v1.json").exists():
        raise RuntimeError("bound_v1_summary_is_immutable_use_stage_all_for_new_analysis")
    started = time.perf_counter()
    stages = list(SEQUENCES) if args.stage == "all" else [args.stage]
    rows, details = [], []
    for stage in stages:
        for task_id, route in SEQUENCES[stage]:
            row, detail = analyze_session(HERE, stage, task_id, route)
            rows.append(row)
            details.append(detail)
    incomplete = [dict(stage=row["stage"], task_id=row["task_id"], route=row["route"], status=row["transport_status"]) for row in rows if row["transport_status"] in ("not_started", "running")]
    if incomplete and not args.allow_partial:
        raise RuntimeError("completed_sessions_required_" + json.dumps(incomplete))
    totals = dict(sessions=len(rows), finished_sessions=len(rows)-len(incomplete),
        actual_saved=sum(row.get("actual_saved", False) for row in rows), actual_independent_readback=sum(row.get("actual_independent_readback", False) for row in rows),
        quality_statuses=dict(Counter(row.get("quality", {}).get("status", row["transport_status"]) for row in rows)),
        final_reference_verified=sum(row.get("final_JSON", {}).get("all_reference_fields_verified", False) for row in rows),
        final_measured_claims_consistent=sum(row.get("final_JSON", {}).get("all_measured_claims_consistent", False) for row in rows),
        wall_s_sum=sum(row.get("wall_s") or 0 for row in rows), tools=sum(row.get("tools", 0) for row in rows),
        public_tool_response_UTF8_bytes=sum(row.get("public_tool_response_UTF8_bytes", 0) for row in rows))
    summary = dict(stage=args.stage, totals=totals, sessions=rows, incomplete=incomplete,
        interpretation=dict(quality="Actual independent saved-readback QUALITY checks, with false and null listed separately.",
            final_references="Quoted task, operation, current version and artifacts are checked independently of geometry quality.",
            remaining="Free-text remaining is retained privately for human review.",
            tokens="Recorded public CLI token fields. Provider fees and hidden request/retry counts remain unmeasured.",
            timings="Nested bridge/executor/worker/facts costs overlap. JSON transport latency has no isolated timer.",
            redundancy="Repeated same-version calls and extra readbacks are structural observations."),
        detail_path="private/analysis/" + args.stage + "/DETAIL.json", analyzer_wall_s=time.perf_counter()-started)
    write(HERE / "private/analysis" / args.stage / "DETAIL.json", dict(sessions=details))
    write(HERE / ("CONSUMER_STATS_" + args.stage + ".json"), summary)
    table = compact_table(rows)
    (HERE / ("CONSUMER_STATS_" + args.stage + ".md")).write_text(table, encoding="utf8", newline="\n")
    print(table)
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
