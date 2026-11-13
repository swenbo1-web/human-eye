"""Root-frozen offline protocol replay. Original request code is never called."""
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
BLOCKED_EVENTS = {"subprocess.Popen", "os.system", "socket.connect", "socket.bind"}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_candidate():
    specification = importlib.util.spec_from_file_location("_offline_error_contract_driver", HERE / "driver.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def verify_freeze(path):
    frozen = read(path)
    sources = frozen.get("files_sha256", frozen.get("runtime_sources"))
    if type(sources) is not dict or not sources:
        raise ValueError("frozen_source_map_required")
    required = {str((HERE / name).resolve()) for name in (
        "consumer.py", "driver.py", "result_contract.py", "replay.py", "CASES.json", "FIXTURE_MANIFEST.json")}
    normalized = {str(Path(name).resolve()): expected for name, expected in sources.items()}
    if not required.issubset(normalized):
        raise ValueError("candidate_cases_and_fixture_manifest_must_be_frozen")
    mismatches = [name for name, expected in normalized.items() if sha(name) != expected]
    if mismatches:
        raise ValueError("frozen_bytes_changed:" + repr(mismatches))
    return sha(path), normalized


def verify_originals(manifest):
    for path, expected in manifest["original_sources_sha256"].items():
        if sha(path) != expected:
            raise ValueError("historical_source_changed:" + path)
    for relative, expected in manifest["fixture_files_sha256"].items():
        if sha(FIXTURES / relative) != expected:
            raise ValueError("fixture_changed:" + relative)


def connection_checks(driver):
    consumer = driver.consumer
    pairs = [(consumer.consume_turn, consumer.legacy.consume_turn),
             (driver.run_route, driver.legacy.run_route), (driver.run_batch, driver.legacy.run_batch)]
    checks = {}
    for name, (candidate, original) in zip(("consume_turn", "run_route", "run_batch"), pairs):
        checks[name + "_code_defaults_closure"] = bool(candidate.__code__ is original.__code__
            and candidate.__defaults__ is original.__defaults__ and candidate.__closure__ is original.__closure__
            and candidate.__kwdefaults__ == original.__kwdefaults__
            and (original.__kwdefaults__ is None or candidate.__kwdefaults__ is not original.__kwdefaults__))
    checks.update({
        "archive_pointer": consumer.consume_turn.__globals__["archive_turn"] is consumer.archive_turn,
        "route_consumer_pointer": driver.run_route.__globals__["consumer"] is consumer,
        "route_check_pointer": driver.run_route.__globals__["common_image_faults"] is driver.common_image_faults,
        "batch_route_pointer": driver.run_batch.__globals__["run_route"] is driver.run_route,
        "safe_environment_unchanged": consumer.safe_environment is consumer.legacy.safe_environment,
        "outer_gate_unchanged": driver.outer_accepted is driver.legacy.outer_accepted,
        "terminal_gate_unchanged": driver.terminal_service_faults is driver.legacy.terminal_service_faults,
        "publication_unchanged": driver.publish_route is driver.legacy.publish_route,
        "old_archive_pointer_unchanged": consumer.legacy.consume_turn.__globals__["archive_turn"] is consumer.legacy.archive_turn,
        "old_route_consumer_unchanged": driver.legacy.run_route.__globals__["consumer"] is driver.legacy.consumer,
        "old_route_check_unchanged": driver.legacy.run_route.__globals__["common_image_faults"] is driver.legacy.common_image_faults,
        "old_batch_route_unchanged": driver.legacy.run_batch.__globals__["run_route"] is driver.legacy.run_route,
    })
    if not all(checks.values()):
        raise ValueError("actual_candidate_wiring_failed")
    return checks


def change_inputs(case, response, item, tools, calls, owner, target_index):
    """Apply one registered negative variable to an explicit baseline."""
    operation = case["mutation"]
    if operation == "none":
        return
    if operation == "flip_cli_status":
        item["status"] = "failed" if item["status"] == "completed" else "completed"
    elif operation == "flip_owner_flag":
        response["result"]["isError"] = not response["result"]["isError"]
    elif operation == "owner_flag_integer":
        response["result"]["isError"] = 1
    elif operation == "cli_error_nonnull":
        item["error"] = {"message": "registered_non_null_error"}
    elif operation == "cli_error_missing":
        del item["error"]
    elif operation == "cli_flag_integer":
        item["result"]["isError"] = 1
    elif operation == "flip_cli_flag":
        item["result"]["isError"] = not item["result"]["isError"]
    elif operation == "structured_nonnull":
        item["result"]["structured_content"] = {}
    elif operation == "cli_extra_result":
        item["result"]["unregistered_field"] = True
    elif operation == "owner_extra_result":
        response["result"]["unregistered_field"] = True
    elif operation == "owner_wrong_rpc":
        response["jsonrpc"] = "1.0"
    elif operation == "owner_top_error":
        response["error"] = {"code": -32603, "message": "registered_RPC_error"}
    elif operation == "cli_wrong_type":
        item["type"] = "function_call"
    elif operation == "change_text":
        next(block for block in item["result"]["content"] if block["type"] == "text")["text"] += "!"
    elif operation == "change_image_data":
        block = next(block for block in item["result"]["content"] if block["type"] == "image")
        block["data"] = ("A" if block["data"][0] != "A" else "B") + block["data"][1:]
    elif operation == "change_image_mime":
        next(block for block in item["result"]["content"] if block["type"] == "image")["mimeType"] = "image/jpeg"
    elif operation == "swap_content_order":
        content = item["result"]["content"]
        content[0], content[1] = content[1], content[0]
    elif operation == "owner_content_string":
        response["result"]["content"] = "registered_non_array"
    elif operation == "cli_content_string":
        item["result"]["content"] = "registered_non_array"
    elif operation == "owner_id_bool":
        response["id"] = True
    elif operation == "owner_id_object":
        response["id"] = {}
    elif operation == "cli_tool_name":
        item["tool"] = "scene_data"
    elif operation == "cli_arguments":
        item["arguments"]["code"] += "\n"
    elif operation == "swap_cli_order":
        calls[0], calls[1] = calls[1], calls[0]
    elif operation == "swap_owner_order":
        tools["tools"][0], tools["tools"][1] = tools["tools"][1], tools["tools"][0]
    elif operation == "owner_attempt_boolean":
        tools["tools"][0]["attempt"] = True
    elif operation == "drop_owner_last":
        tools["tools"].pop()
    elif operation == "drop_cli_last":
        calls.pop()
    elif operation == "extra_cli_last":
        calls.append(copy.deepcopy(calls[-1]))
    elif operation == "delete_owner_response":
        (owner / ("tool_" + str(target_index + 1).zfill(2)) / "RESPONSE.json").unlink()
    elif operation == "response_id_value":
        response["id"] += 1
    elif operation == "response_id_float":
        response["id"] = float(response["id"])
    else:
        raise ValueError("unknown_preregistered_mutation:" + operation)


def run_case(case, manifest, driver, output):
    started = time.perf_counter_ns()
    destination = output / "cases" / case["case_id"]
    destination.mkdir(parents=True, exist_ok=False)
    owner, archive_folder = destination / "owner", destination / "consumer"
    shutil.copytree(FIXTURES / "slots" / case["slot"] / "owner", owner)
    archive_folder.mkdir()
    fixtures = [row for row in manifest["records"] if row["slot"] == case["slot"]]
    calls = [{"perf_ns": row["CLI_perf_ns"], "type": "item.completed",
              "item": read(FIXTURES / row["CLI_completed"])["item"]} for row in fixtures]
    raw_lines = b"".join((FIXTURES / row["CLI_completed"]).read_bytes() for row in fixtures)
    (archive_folder / "ORIGINAL_CLI_COMPLETED_RAW.jsonl").write_bytes(raw_lines)
    tools = read(owner / "TOOLS.json")
    original_tools = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    target_index = next((index for index, row in enumerate(fixtures) if row["fixture_id"] == case["fixture_id"]), 0)
    target_fixture = fixtures[target_index]
    response_path = owner / ("tool_" + str(target_fixture["attempt"]).zfill(2)) / "RESPONSE.json"
    response = read(response_path)
    original_response = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    item = calls[target_index]["item"]
    if case["variant"] == "owner_style":
        # This derived control preserves the actual CLI content. It does not
        # replace the fifteen unmodified raw CLI fixture lines.
        item["result"] = {"content": copy.deepcopy(item["result"]["content"]),
                          "isError": response["result"]["isError"]}
    change_inputs(case, response, item, tools, calls, owner, target_index)
    response_changed = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != original_response
    if case["mutation"] != "delete_owner_response" and response_changed:
        save(response_path, response)
    if json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != original_tools:
        save(owner / "TOOLS.json", tools)
    save(archive_folder / "CANDIDATE_CLI_ITEMS.json", calls)
    save(archive_folder / "TRANSFORMATION.json", case)
    result = {"case_id": case["case_id"], "scope": case["scope"], "slot": case["slot"],
              "passed": False, "exception": None, "started_ns": started}
    if case["scope"] == "matcher":
        binding = driver.consumer.result_contract.bind_tool_result(response, item)
        result.update(matcher=binding, passed=binding["matched"] is False
                      and binding["classification"] == "protocol_mismatch"
                      and binding["reason"] == case["expected"]["matcher_reason"])
    else:
        archive = driver.consumer.archive_turn(archive_folder, {"audit_dir": str(owner)}, 1, calls)
        faults = driver.common_image_faults({"tool_calls": calls, "unknown_image_payloads": 0}, owner)
        bindings = archive["result_contracts"]
        errors = archive["business_binding_errors"]
        matched = not errors and not faults
        result.update(pipeline_matched=matched, archive_errors=errors, shared_faults=faults,
                      result_contracts=bindings, archive=archive)
        expected = case["expected"]
        passed = matched is expected["pipeline_matched"]
        if expected["primary_archive_reason"] is not None:
            passed = passed and bool(errors) and errors[0]["reason"] == expected["primary_archive_reason"]
        if expected["primary_shared_reason"] is not None:
            passed = passed and bool(faults) and faults[0]["reason"] == expected["primary_shared_reason"]
        if expected["matcher_reason"] is not None:
            binding = next(row for row in bindings if row["attempt"] == target_fixture["attempt"])
            passed = passed and binding["matched"] is False and binding["classification"] == "protocol_mismatch"
            passed = passed and binding["reason"] == expected["matcher_reason"]
        if expected["pipeline_matched"]:
            expected_classes = [row["expected_classification"] for row in fixtures]
            passed = passed and [row["classification"] for row in bindings] == expected_classes
            passed = passed and all(row["matched"] is True for row in bindings)
        result["passed"] = bool(passed)
    result["closed_ns"] = time.perf_counter_ns()
    result["elapsed_ns"] = result["closed_ns"] - started
    save(destination / "RESULT.json", result)
    return result


def state_invariants(manifest, driver):
    original = read(FIXTURES / "RUN_RESULT_ORIGINAL.json")
    rows = {row["slot"]: row for row in original["records"]}
    slots = []
    for state in manifest["slots"]:
        slot = state["slot"]
        root = FIXTURES / "slots" / slot
        consumer = read(root / "CONSUMER_ORIGINAL.json")
        events = [json.loads(line) for line in (root / "PUBLIC_EVENTS_ORIGINAL.jsonl").read_bytes().splitlines()]
        summary = driver.consumer.legacy.cli.summarize_turn(events, episode_id="active-coverage-" + slot,
            turn_index=1, expected_thread_id=None, exit_code=consumer["exit_code"])
        unchanged = bool(state["usage"] == consumer["usage"]
            and state["raw_usage_events"] == consumer["raw_usage_events"]
            and state["usage_semantics"] == consumer["usage_semantics"]
            and state["interrupted_stream_usage_coverage"] == consumer["summary"]["interrupted_stream_usage_coverage"]
            and state["original_execution_state"] == rows[slot]["execution_state"])
        slots.append({"slot": slot, "original_execution_state": rows[slot]["execution_state"],
                      "original_outer_accepted": driver.outer_accepted(rows[slot]),
                      "candidate_event_projection_only_valid": summary["valid_completion"],
                      "top_level_errors_preserved": state["top_level_errors"],
                      "raw_usage_objects_unchanged": unchanged,
                      "interrupted_stream_usage_coverage": state["interrupted_stream_usage_coverage"]})
    n1 = next(row for row in slots if row["slot"] == "N1")
    n3 = next(row for row in slots if row["slot"] == "N3")
    counts = Counter(row["original_execution_state"] for row in slots)
    passed = bool(all(row["raw_usage_objects_unchanged"] for row in slots)
        and counts == Counter({"completed": 4, "failed": 2})
        and n1["original_outer_accepted"] is False and n3["original_outer_accepted"] is False
        and n3["candidate_event_projection_only_valid"] is False and n3["top_level_errors_preserved"]
        and n3["interrupted_stream_usage_coverage"] == "unknown")
    return {"passed": passed, "slots": slots, "original_execution_counts": dict(counts),
            "scope": "Candidate protocol binding only. Historical outer acceptance and usage coverage remain unchanged."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--frozen", type=Path, default=HERE / "FROZEN.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE.resolve()):
        raise ValueError("new_namespace_output_required")
    freeze_sha, source_map = verify_freeze(args.frozen)
    manifest = read(HERE / "FIXTURE_MANIFEST.json")
    cases = read(HERE / "CASES.json")
    if len(cases["cases"]) != cases["case_count"] or len({row["case_id"] for row in cases["cases"]}) != cases["case_count"]:
        raise ValueError("complete_unique_preregistered_cases_required")
    verify_originals(manifest)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    save(output / "STARTED.json", {"started_ns": started, "freeze_sha256": freeze_sha,
                                   "case_count": cases["case_count"], "source_map": source_map})
    forbidden = []

    def audit(event, arguments):
        if event in BLOCKED_EVENTS:
            forbidden.append({"event": event})
            raise RuntimeError("offline_replay_forbidden_operation:" + event)

    sys.addaudithook(audit)
    driver = load_candidate()
    connections = connection_checks(driver)
    outcomes = []
    for case in cases["cases"]:
        try:
            outcome = run_case(case, manifest, driver, output)
        except BaseException as error:
            outcome = {"case_id": case["case_id"], "passed": False,
                       "exception": {"type": type(error).__name__, "message": str(error)}}
            save(output / "cases" / case["case_id"] / "RESULT.json", outcome)
        outcomes.append(outcome)
        save(output / "PROGRESS.json", {"cases": outcomes})
    real = []
    by_id = {row["case_id"]: row for row in outcomes}
    for fixture in manifest["records"]:
        case = by_id["real_slot_" + fixture["slot"]]
        binding = next((row for row in case.get("result_contracts", []) if row["attempt"] == fixture["attempt"]), None)
        real.append({"fixture_id": fixture["fixture_id"], "expected": fixture["expected_classification"], "binding": binding,
                     "passed": bool(binding and binding["matched"] and binding["classification"] == fixture["expected_classification"])})
    classification = Counter(row["binding"]["classification"] for row in real if row["binding"] is not None)
    invariants = state_invariants(manifest, driver)
    connections_after = connection_checks(driver)
    verify_originals(manifest)
    final_freeze, _ = verify_freeze(args.frozen)
    closed = time.perf_counter_ns()
    passed = bool(len(real) == 15 and all(row["passed"] for row in real)
        and classification == Counter({"success": 13, "tool_error": 2})
        and all(row["passed"] for row in outcomes) and invariants["passed"]
        and connections == connections_after and final_freeze == freeze_sha and not forbidden)
    result = {"schema": "consumer-error-contract-001-offline-replay-v1", "passed": passed,
              "case_count": len(outcomes), "case_counts": {"passed": sum(row["passed"] for row in outcomes),
                "failed": sum(not row["passed"] for row in outcomes), "not_run": 0},
              "real_fixture_results": real, "real_classifications": dict(classification),
              "connections": connections, "historical_invariants": invariants,
              "cases": outcomes, "freeze_sha256": freeze_sha,
              "started_ns": started, "closed_before_result_publication_ns": closed, "elapsed_ns": closed - started,
              "forbidden_operation_attempts": forbidden, "new_Pro_provider_CLI_actor_Blender_raster_calls": 0,
              "original_tool_code_executed": False,
              "scope": "Offline original JSON copies and actual candidate archive/common checks. No historical outcome or performance result is promoted."}
    save(output / "RESULTS.json", result)
    print(json.dumps({"passed": passed, "cases": len(outcomes), "real_classifications": dict(classification),
                      "new_online_or_renderer_calls": 0}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
