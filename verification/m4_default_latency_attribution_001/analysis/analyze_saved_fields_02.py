"""Analyze the one frozen four-session profiler matrix from saved records only."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
MEASURES = (
    "entry_elapsed_ns", "Peer_elapsed_ns", "trace_duration_ns", "host_capture_ns",
    "trace_outside_host_ns", "entry_outside_trace_ns", "content_encode_inclusive_ns",
    "worker_elapsed_ns", "QA_before_probe_ns", "QA_after_probe_ns", "profile_scope_inclusive_ns",
    "verification_elapsed_ns", "request_with_checks_ns",
)
RESIDENCY = ("to_mesh", "triangulations", "resource_builds", "world_transforms")
KERNEL = ("exact_pair_count", "closed_solid_pair_count", "surface_pair_count", "pair_calls", "rank_calls")
VERSION_SHA = {
    "baseline": "53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732",
    "candidate": "9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504",
}
VERSION_ROLE = {"B": "baseline", "C": "candidate"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def critical_commit_matches(frozen_commit, bindings, root):
    actual = {name: sha((root / name).read_bytes()) for name in bindings["critical_git_paths"]}
    return frozen_commit["files_sha256"] == actual


def warm_recorded_work_matches(task, successful_hash_count):
    return successful_hash_count == 0 and task['result_cache_hit'] is True and all(
        task[key] == 0 for key in ('exact_pair_count', 'closed_solid_pair_count', 'surface_pair_count'))


def distribution(values):
    return {"count": len(values), "minimum": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "maximum": max(values) if values else None, "raw_samples": values}


def metrics(rows):
    return {field: distribution([row["measurements"][field] for row in rows
                                if row["measurements"].get(field) is not None]) for field in MEASURES}


def summarize_session(rows):
    paired = [row for row in rows if row["phase"] == "warm"]
    pairs = []
    for pair_index in sorted({row["pair_index"] for row in paired}):
        selected = [row for row in paired if row["pair_index"] == pair_index]
        if len(selected) != 2 or {row["profile_enabled"] for row in selected} != {False, True}:
            continue
        by_profile = {row["profile_enabled"]: row for row in selected}
        differences = {field: by_profile[True]["measurements"][field] - by_profile[False]["measurements"][field]
            for field in MEASURES if all(row["measurements"].get(field) is not None for row in selected)}
        pairs.append({"pair_index": pair_index, "order": [row["profile_enabled"] for row in selected],
                      "labels": [row["label"] for row in selected], "ON_minus_OFF": differences})
    return {
        "ON": metrics([row for row in paired if row["profile_enabled"]]),
        "OFF": metrics([row for row in paired if not row["profile_enabled"]]),
        "cold": metrics([row for row in rows if row["phase"] == "cold"]),
        "warmup": metrics([row for row in rows if row["phase"] == "warmup"]),
        "pair_differences": pairs,
        "paired_ON_minus_OFF": {field: distribution([pair["ON_minus_OFF"][field] for pair in pairs
            if field in pair["ON_minus_OFF"]]) for field in MEASURES},
        "position": {profile: {str(position): metrics([row for row in paired
            if row["profile_enabled"] == enabled and row["pair_position"] == position])
            for position in (1, 2)} for profile, enabled in (("ON", True), ("OFF", False))},
        "previous_profile": {profile: {previous: metrics([row for row in paired
            if row["profile_enabled"] == enabled and row["previous_profile_enabled"] == prior])
            for previous, prior in (("ON", True), ("OFF", False), ("unknown", None))}
            for profile, enabled in (("ON", True), ("OFF", False))},
    }


def version_comparisons(sessions):
    comparisons = {"independent_unit": "session", "required_sessions_each_version": 2,
                   "actual_session_counts": {}, "session_medians": {}, "matched_blocks": []}
    for version in ("baseline", "candidate"):
        selected = [session for session in sessions if session["role"] == version]
        comparisons["actual_session_counts"][version] = len(selected)
        comparisons["session_medians"][version] = {
            profile: {field: [session["summary"][profile][field]["median"] for session in selected]
                      for field in MEASURES} for profile in ("ON", "OFF")}
    if len(sessions) != 4:
        comparisons["interpretation"] = "incomplete matrix; all observed samples retained"
        return comparisons
    for baseline_index, candidate_index in ((0, 1), (3, 2)):
        baseline, candidate = sessions[baseline_index], sessions[candidate_index]
        contrast = {}
        for field in MEASURES:
            values = {version: {profile: session["summary"][profile][field]["median"] for profile in ("ON", "OFF")}
                      for version, session in (("baseline", baseline), ("candidate", candidate))}
            if any(value is None for row in values.values() for value in row.values()):
                continue
            contrast[field] = {
                "C_minus_B_ON": values["candidate"]["ON"] - values["baseline"]["ON"],
                "C_minus_B_OFF": values["candidate"]["OFF"] - values["baseline"]["OFF"],
                "interaction": (values["candidate"]["ON"] - values["candidate"]["OFF"])
                               - (values["baseline"]["ON"] - values["baseline"]["OFF"]),
            }
        comparisons["matched_blocks"].append({"baseline_session": baseline["case"].get("id"),
            "candidate_session": candidate["case"].get("id"), "contrasts": contrast})
    comparisons["equal_weight_version_difference"] = {
        profile: {field: statistics.mean(comparisons["session_medians"]["candidate"][profile][field])
                  - statistics.mean(comparisons["session_medians"]["baseline"][profile][field])
                  for field in MEASURES if all(value is not None for version in ("baseline", "candidate")
                      for value in comparisons["session_medians"][version][profile][field])}
        for profile in ("ON", "OFF")}
    comparisons["interpretation"] = "two sessions per version; condition and interaction contrasts are descriptive"
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-run", required=True, type=Path)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    entry = arguments.entry_run.resolve()
    assert entry.is_relative_to((BATCH / "entry").resolve())
    assert Path(arguments.output).name == arguments.output and arguments.output not in (".", "..")
    destination = HERE / arguments.output
    destination.mkdir(exist_ok=False)
    checks, inputs = [], {}

    def read(path):
        raw = path.read_bytes()
        inputs[str(path.resolve())] = sha(raw)
        return json.loads(raw)

    def read_events(path):
        raw = path.read_bytes()
        inputs[str(path.resolve())] = sha(raw)
        return [json.loads(line) for line in raw.splitlines() if line]

    def check(name, passed, details=None):
        checks.append({"check": name, "passed": bool(passed), "details": details})

    def save(name, value):
        with (destination / name).open("x", encoding="utf8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")

    try:
        rules = read(HERE / "ANALYSIS_RULES.json")
        schedule = read(BATCH / "SCHEDULE.json")
        batch = read(entry / "RESULTS.json")
        bindings = read(BATCH / "preparation/INPUT_BINDINGS.json")
        frozen_commit = read(entry / "FROZEN_COMMIT.json")
        validated_inputs = read(entry / "VALIDATED_INPUTS.json")
        check("complete_terminal_four_sessions", len(batch.get("cases", [])) == 4 and batch.get("passed") is True)
        source_checks = {name: sha((ROOT / name).read_bytes()) == digest
                         for name, digest in bindings["source_files_sha256"].items()}
        check("frozen_input_source_pins", bool(source_checks) and all(source_checks.values()))
        check("executed_commit_source_binding", critical_commit_matches(frozen_commit, bindings, ROOT))
        check("runtime_terminal_source_checks", bool(batch.get("source_checks")) and all(batch["source_checks"].values())
              and bool(batch.get("installed_checks")) and all(batch["installed_checks"].values()))
        sessions = []
        for ordinal, case in enumerate(batch.get("cases", []), 1):
            case_meta = case.get("case", {"id": case.get("id"), "version": case.get("version")})
            case_id = case_meta["id"]
            folder = entry / case_id
            check(case_id + ":raw_case_matches_batch", read(folder / "RESULTS.json") == case)
            check(case_id + ":raw_case_passed", case.get("passed") is True, case.get("errors"))
            worker_path = folder / "native/WORKER_EVENTS.jsonl"
            worker_available = worker_path.is_file()
            check(case_id + ":worker_records_available", worker_available)
            all_worker = read_events(worker_path) if worker_available else []
            check(case_id + ":raw_worker_records_match", worker_available and all_worker == case.get("all_worker_events"))
            expected = rules["fixed_sessions"][ordinal - 1]
            role = VERSION_ROLE[case_meta["version"]]
            expected_schedule = schedule["sessions"][ordinal - 1]
            check(case_id + ":fixed_version_order", case_meta["version"] == expected["version"]
                  and role == expected["role"] and case_id == expected_schedule["id"])
            raw_rows = case["rows"]
            check(case_id + ":twenty_two_relations", len(raw_rows) == 22 and all(row.get("phase") in ("cold", "warmup", "warm") for row in raw_rows))
            runtime_proof_path = folder / "PRODUCT_RUNTIME_PROOF.json"
            runtime_proof = read(runtime_proof_path) if runtime_proof_path.is_file() else {}
            check(case_id + ":actual_product_PID_proof", runtime_proof.get("confirmed") is True)
            rows, previous, reference = [], None, None
            for index, row in enumerate(raw_rows):
                label = case_id + "/" + row["label"]
                requested = row["profile_enabled"]
                phase = "cold" if index == 0 else "warmup" if index == 1 else "warm"
                pair_index = None if index < 2 else (index - 2) // 2 + 1
                position = None if index < 2 else (index - 2) % 2 + 1
                first_on = expected["first_pair"][0] == "ON"
                pair_first = first_on if pair_index is None or pair_index % 2 else not first_on
                expected_profile = False if index < 2 else pair_first if position == 1 else not pair_first
                check(label + ":schedule_metadata", row["phase"] == phase and requested is expected_profile
                      and row.get("pair_index") == pair_index and row.get("pair_position") == position
                      and row.get("previous_profile_enabled") is previous)
                planned = expected_schedule["business"][index]
                check(label + ":exact_frozen_schedule_row", all(row.get(key) == planned[key]
                      for key in ("phase", "pair_index", "pair_position", "profile_enabled", "previous_profile_enabled"))
                      and row["label"] == planned["request_id"])
                completed = row.get("status") == "completed"
                check(label + ":business_completed", completed, row.get("status"))
                if not completed:
                    rows.append({"label": row["label"], "phase": phase, "pair_index": pair_index,
                        "pair_position": position, "profile_enabled": requested, "previous_profile_enabled": previous,
                        "measurements": {field: None for field in MEASURES}, "raw_incomplete_record": row})
                    continue
                check(label + ":entry_clock", row["ended_ns"] - row["started_ns"] == row["entry_elapsed_ns"])
                wire = read(folder / (row["label"] + ".RESPONSE.json"))
                request = read(folder / (row["label"] + ".REQUEST.json"))
                check(label + ":identical_frozen_business_request", request.get("id") == planned["request_id"]
                    and {key: value for key, value in request.items() if key != "id"} == schedule["request_template"])
                body = json.loads(wire["result"]["content"][0]["text"])
                check(label + ":raw_result_matches", body == row["body"] and not wire["result"]["isError"])
                check(label + ":precise_source_and_no_geometry", body["context"]["runtime_source_sha256"] == VERSION_SHA[role] and "geometry" not in body)
                core = {key: value for key, value in body.items() if key != "trace_id"}
                if reference is None:
                    reference = core
                check(label + ":same_generation_and_facts", core == reference)
                worker = row["worker_received_events"]
                interval_events = [event for event in all_worker if type(event.get("started_ns")) is int
                    and row["started_ns"] <= event["started_ns"] <= row["ended_ns"]]
                check(label + ":exact_received_RPC_attribution", interval_events == worker)
                check(label + ":one_worker_RPC", row["worker_received_RPC_count"] == len(worker) == 1)
                work = worker[0]["qa_work"]
                check(label + ":profile_state_binding", work["worker_sequence"] == worker[0]["sequence"]
                    and work["profile_enabled"] is requested and work["previous_profile_enabled"] is previous
                    and work["profile_initial_present"] is False and work["profile_restored_to_initial"] is True
                    and work["profile_install_attempted"] is requested and work["profile_actual_enabled"] is requested
                    and not work["errors"])
                check(label + ":callback_count_collection", all(isinstance(work[key], dict) if requested else work[key] is None
                    for key in ("python_calls", "C_calls", "C_returns", "C_exceptions")))
                if requested:
                    check(label + ":profiled_capture_calls", all(work["python_calls"].get(key) == 1
                        for key in ("capture_task_scene", "_capture", "_resident_capture")))
                check(label + ":same_existing_resource_work", isinstance(work["host_residency_delta"], dict)
                    and all(type(work["host_residency_delta"].get(key)) is int
                    and work["host_residency_delta"][key] == (4 if index == 0 else 0) for key in RESIDENCY))
                task = row["task_work"]
                if index == 0:
                    check(label + ":cold_existing_kernel_work", row["successful_normalize_hash_spans"] == 1
                        and task["result_cache_hit"] is False
                        and {key: task[key] for key in KERNEL} == {
                            "exact_pair_count": 0, "closed_solid_pair_count": 3,
                            "surface_pair_count": 3, "pair_calls": 3, "rank_calls": 1})
                else:
                    check(label + ":warm_no_hash_or_kernel", warm_recorded_work_matches(
                        task, row["successful_normalize_hash_spans"]))
                trace = row["request_trace"]
                check(label + ":trace_PID_matches_owned_runtime", trace["pid"] == runtime_proof.get("runtime_pid"))
                host_spans = [span for span in trace["spans"] if span["name"] == "host.capture"]
                encodes = [span for span in trace["spans"] if span["name"] == "mcp.content_encode"]
                check(label + ":one_host_and_encode_span", len(host_spans) == len(encodes) == 1)
                host_ns = sum(span["duration_ns"] for span in host_spans)
                measurements = {"entry_elapsed_ns": row["entry_elapsed_ns"], "Peer_elapsed_ns": row["stdio"]["elapsed_ns"],
                    "trace_duration_ns": trace["duration_ns"], "host_capture_ns": host_ns,
                    "trace_outside_host_ns": trace["duration_ns"] - host_ns,
                    "entry_outside_trace_ns": row["entry_elapsed_ns"] - trace["duration_ns"],
                    "content_encode_inclusive_ns": sum(span["duration_ns"] for span in encodes),
                    "worker_elapsed_ns": worker[0]["elapsed_ns"], "QA_before_probe_ns": work["before_probe_elapsed_ns"],
                    "QA_after_probe_ns": work["after_probe_elapsed_ns"], "profile_scope_inclusive_ns": work["profile_scope_ns"],
                    "verification_elapsed_ns": row.get("verification_elapsed_ns"),
                    "request_with_checks_ns": row.get("request_with_checks_ns")}
                rows.append({"label": row["label"], "phase": phase, "pair_index": pair_index,
                    "pair_position": position, "profile_enabled": requested, "previous_profile_enabled": previous,
                    "measurements": measurements, "raw_work": work, "task_work": task,
                    "additional_task_counter_status": {key: 'reported' if key in task else
                        'not_emitted_on_cache_hit' if task['result_cache_hit'] else 'not_emitted'
                        for key in ('pair_calls', 'rank_calls')},
                    "lifetime_product_peak_rss": trace.get("peak_rss")})
                previous = requested
            received = [event for event in all_worker if type(event.get("started_ns")) is int and type(event.get("sequence")) is int]
            check(case_id + ":all_twenty_three_worker_sequences", [event["sequence"] for event in received] == list(range(1, 24)))
            close_events = [event for event in received if event["sequence"] == 23]
            if len(close_events) == 1:
                close_work = close_events[0]["qa_work"]
                check(case_id + ":close_profile_state", close_work["profile_enabled"] is False
                    and close_work["previous_profile_enabled"] is previous and not close_work["errors"]
                    and close_work["profile_initial_present"] is False and close_work["profile_restored_to_initial"] is True)
            product_close = case.get("product_close") or {}
            product_exit = case.get("product_runtime_exit") or {}
            native_close = case.get("native_close") or {}
            closed = case.get("worker_closed") or {}
            check(case_id + ":owned_cleanup_and_original_asset", product_close.get("confirmed") is True
                and all(product_exit.get(key) is True for key in ("confirmed", "exited", "handle_closed"))
                and product_exit.get("exit_code") == 0
                and native_close.get("process_reaped") is True and native_close.get("exit_code") == 0
                and (native_close.get("response") or {}).get("status") == "closed" and native_close.get("error") is None
                and native_close.get("source_file_unchanged") is True and native_close.get("protected_files_unchanged") is True
                and closed.get("poisoned") is False
                and closed.get("final_geometry_fingerprint") == closed.get("initial_geometry_fingerprint"))
            rpc_path = folder / "product/RPC.json"
            rpc_available = rpc_path.is_file()
            check(case_id + ":product_transport_records_available", rpc_available)
            rpc = read(rpc_path) if rpc_available else {"requests": [], "tx_bytes": None, "rx_bytes": None}
            check(case_id + ":fixed_metadata_and_business_stdio", [request["method"] for request in rpc["requests"][:4]] == schedule["metadata_stdio_per_session"]
                and len(rpc["requests"]) == 26 and all(request["method"] == "tools/call" for request in rpc["requests"][4:]))
            sessions.append({"case": case_meta, "role": role, "raw_session_passed": case.get("passed"), "rows": rows,
                "summary": summarize_session(rows), "session_wall_ns": case["session_wall_ns"],
                "all_received_worker_RPC": len(received) if worker_available else None, "all_worker_events": all_worker,
                "all_product_stdio_records": len(rpc["requests"]), "product_stdio_tx_bytes": rpc["tx_bytes"],
                "product_stdio_rx_bytes": rpc["rx_bytes"],
                "lifecycle_and_control": {key: value for key, value in case.items() if key not in ("rows", "all_worker_events")},
                "product_close": case.get("product_close"), "native_close": case.get("native_close"),
                "worker_closed": case.get("worker_closed")})
        check("saved_inputs_unchanged", all(sha(Path(path).read_bytes()) == digest for path, digest in inputs.items()))
        source_checks_after = {name: sha((ROOT / name).read_bytes()) == digest
                               for name, digest in bindings["source_files_sha256"].items()}
        check("frozen_source_pins_unchanged_after_analysis", all(source_checks_after.values()))
        failed = [row for row in checks if not row["passed"]]
        save("RESULTS.json", {"cycle_id": rules["cycle_id"], "passed": not failed,
            "checks": checks, "check_count": len(checks), "failed_checks": failed,
            "sessions": sessions, "version_comparisons": version_comparisons(sessions),
            "batch_lifecycle_and_control": {key: value for key, value in batch.items() if key != "cases"},
            "all_received_worker_RPC_observed": sum(session["all_received_worker_RPC"] for session in sessions
                if session["all_received_worker_RPC"] is not None),
            "sessions_with_unmeasured_worker_RPC": [session["case"]["id"] for session in sessions
                if session["all_received_worker_RPC"] is None],
            "sum_session_wall_ns": sum(session["session_wall_ns"] for session in sessions),
            "rules": rules, "input_sha256": inputs, "analysis_source_sha256": sha(Path(__file__).read_bytes()),
            "validated_installation_inputs": validated_inputs,
            "full_admission": False, "conclusion": "requires root interpretation of this one controlled matrix",
            "limits": ["two independent sessions per version", "all samples remain instrumented by outer QA",
                       "callback-only overhead is not isolated by profile_scope; natural ON/OFF count representation and publication are part of the measured mode chain",
                       "new before probe includes profile installation/checks and after probe includes restoration/checks; inclusive profile scope begins with state creation and overlaps probes",
                       "same-name probe intervals differ from the previous sealed run and are not subtracted across experiments",
                       "timing_stages.verification is already part of business_loop; stage values are not mutually exclusive costs",
                       "no stable p95 or significance estimate",
                       "prior sealed regression is retained", "no model-task quality or net-benefit measurement"],
            "new_runtime_measurements": 0, "model_consumers": 0, "Blender_sessions_started_by_analyzer": 0})
        print(json.dumps({"passed": not failed, "checks": len(checks), "failures": len(failed), "sessions": len(sessions)}))
        return 0 if not failed else 1
    except BaseException:
        (destination / "ANALYZER_EXCEPTION.txt").write_text(traceback.format_exc(), encoding="utf8")
        save("PARTIAL_CHECKS.json", {"checks": checks, "input_sha256": inputs})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
