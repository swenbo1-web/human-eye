"""Offline engineering checks for the fixed three-turn BASE/REPEAT/EDIT scope.

The existing independent exact-truth verifier is reused without product imports.
No function starts a process, edits geometry, or calls Blender or a model.
"""

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUAL = ROOT / "verification/m4_surface_scan_001/qualification"
PREVIOUS = ROOT / "verification/m4_surface_scan_compact_facts_001/engineering/run_candidate.py"
SOURCE_SHA = "4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6"
PREVIOUS_SHA = "7e7c75172190681ea138465c9bc3a777a953d9ae0d91c7bb51f2cb164e3321cc"
TRUTH_SHA = {
    "BASE": "a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7",
    "EDIT": "ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91",
}
SNAPSHOT_SHA = {
    "BASE": "f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b",
    "EDIT": "beb4e441b1898c6aedbe633828b1a93948f1d5be172ded9e1a884c8bdebffd80",
}
TURNS = ("BASE", "REPEAT", "EDIT")
EXPECTED_MATCHES = {"BASE": 71, "REPEAT": 71, "EDIT": 72}
EXPECTED_KERNELS = {"BASE": 112, "REPEAT": 0, "EDIT": 10}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def fixed_json(path, expected_sha):
    raw = path.read_bytes()
    require(digest(raw) == expected_sha, "fixed_input_sha256:" + path.name)
    return json.loads(raw)


def previous_verifier():
    require(digest(PREVIOUS.read_bytes()) == PREVIOUS_SHA, "previous_independent_verifier_sha256")
    spec = importlib.util.spec_from_file_location("_continuity_previous_exact_verifier", PREVIOUS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_c_turn(result, audit_rows, host_events, source_snapshot, turn, request):
    """Check one real compact default scan and its request-local private evidence.

    host_events must be the worker events within this business call's recorded
    start/end interval, excluding separate QA. Lifecycle and thin-client boundary
    checks remain the runner's responsibility.
    """
    require(turn in TURNS, "fixed_turn")
    params = request.get("params", request)
    require(params.get("name") == "human_eye_scene_observe", "ordinary_observe_tool")
    arguments = params["arguments"]
    require("response_detail" not in arguments, "default_response_detail_required")
    require(arguments.get("include_image") is False, "zero_image_request")
    require(arguments.get("query") == {"mode": "surface_scan", "threshold_m": .002}, "fixed_surface_scan_query")
    require(isinstance(arguments.get("session_id"), str) and bool(arguments["session_id"]), "nonempty_session_id")
    trace_id = result["trace_id"]
    observed = [row for row in audit_rows if row.get("event") == "observe" and row.get("trace_id") == trace_id]
    traces = [row for row in audit_rows if row.get("event") == "request_trace" and row.get("trace_id") == trace_id]
    require(len(observed) == len(traces) == 1, "unique_request_observe_and_trace")
    work, trace = observed[0]["task_work"], traces[0]["trace"]
    require(len(host_events) == 1, "exactly_one_host_capture")
    host = host_events[0]
    require(host.get("status") == "completed" and host.get("script_error") is None, "host_capture_completed")
    require(host.get("terminal_geometry_and_file_checks_passed") is True, "host_terminal_protection")
    require(host.get("changed_or_new_PNG_files") == [], "no_PNG_created")
    require(host["render_events_before"] == host["render_events_after"], "no_render_event")
    captures = [span for span in trace["spans"] if span["name"] == "host.capture"]
    require(len(captures) == 1 and captures[0]["outcome"] == "completed", "one_completed_capture_span")
    require(trace["annotations"]["mcp_native_image_block_count"] == 0, "zero_delivered_images")
    state = "EDIT" if turn == "EDIT" else "BASE"
    truth = fixed_json(QUAL / (state + "_TRUTH.json"), TRUTH_SHA[state])
    reference = fixed_json(QUAL / (state + "_SNAPSHOT.json"), SNAPSHOT_SHA[state])
    previous = previous_verifier()
    previous.bind_snapshot(source_snapshot, reference)
    facts = previous.verify_facts(result, work, truth, source_snapshot, SOURCE_SHA, compact=True)
    require(facts["matches"] == EXPECTED_MATCHES[turn], "registered_match_count")
    require(type(work["kernel_calls"]) is int and work["kernel_calls"] == EXPECTED_KERNELS[turn], "registered_new_kernel_count")
    require(result.get("display_encoding") == "surface-scan-task-table-v1", "compact_default_encoding")
    require(observed[0]["pid"] == traces[0]["pid"], "audit_runtime_pid_agrees")
    return {
        "passed": True, "turn": turn, "truth_state": state, "truth_sha256": TRUTH_SHA[state],
        "verified_pair_dispositions": facts["all_pair_partitions_verified"],
        "matches": facts["matches"], "new_kernel_calls": work["kernel_calls"],
        "trace_id": trace_id, "session_id": arguments["session_id"],
        "runtime_pid": observed[0]["pid"], "binding": result["binding"],
        "actual_host_capture_count": 1, "host_sequence": host["sequence"],
        "acquisition_work": work["acquisition_work"],
        "measurement_cache_before": work["measurement_cache_before"],
        "measurement_cache_after": work["measurement_cache_after"],
        "facts": facts,
        "scope": "fixed request, full raw facts, exact frozen truth and request-local capture; lifecycle checked separately",
    }


def verify_c_sequence(rows):
    require([row["turn"] for row in rows] == list(TURNS), "three_fixed_C_turns")
    require(all(row["passed"] is True for row in rows), "all_C_turns_verified")
    require([row["matches"] for row in rows] == [71, 71, 72], "C_matches_71_71_72")
    require([row["new_kernel_calls"] for row in rows] == [112, 0, 10], "C_kernels_112_0_10")
    require(len({row["session_id"] for row in rows}) == 1, "same_C_session")
    require(len({row["runtime_pid"] for row in rows}) == 1, "same_C_runtime")
    require(len({row["trace_id"] for row in rows}) == 3, "distinct_C_request_traces")
    require(rows[0]["binding"] == rows[1]["binding"], "unchanged_state_binding_equal")
    require(rows[1]["binding"] != rows[2]["binding"], "edited_state_binding_invalidates")
    for field in ("document_epoch", "host_source_sha256", "runtime_source_sha256"):
        require(len({row["binding"][field] for row in rows}) == 1, "same_binding_origin:" + field)
    require(rows[1]["measurement_cache_before"]["measurement_entries"] == rows[0]["measurement_cache_after"]["measurement_entries"], "cache_survives_first_boundary")
    require(rows[2]["measurement_cache_before"]["measurement_entries"] == rows[1]["measurement_cache_after"]["measurement_entries"], "cache_survives_second_boundary")
    return {"passed": True, "matches": [71, 71, 72], "new_kernel_calls": [112, 0, 10],
            "binding_same_then_changed": True, "session_and_runtime_retained": True,
            "scope": "geometry/source/cache evidence; no model-memory or model-cost claim"}


def verify_n_sequence(rows):
    """Validate three namespace-marker stdout packets against frozen pose matrices."""
    require(len(rows) == 3, "three_fixed_N_turns")
    fields = {"marker_token", "marker_generation", "pid", "namespace_id", "unit_scale", "objects"}
    for index, row in enumerate(rows):
        require(set(row) == fields, "N_marker_exact_fields")
        require(row["marker_token"] == "continuity-engineering-N-001", "N_marker_token")
        require(type(row["marker_generation"]) is int and row["marker_generation"] == 1, "N_marker_generation")
        require(type(row["pid"]) is int and row["pid"] > 0, "N_process_id")
        require(type(row["namespace_id"]) is int and row["namespace_id"] > 0, "N_namespace_id")
        state = "EDIT" if index == 2 else "BASE"
        reference = fixed_json(QUAL / (state + "_SNAPSHOT.json"), SNAPSHOT_SHA[state])
        require(type(row["unit_scale"]) is float and row["unit_scale"] == reference["scale_length"], "N_unit_scale")
        objects = row["objects"]
        names = [obj["name"] for obj in objects]
        require(names == sorted(obj["name"] for obj in reference["objects"]), "N_all_24_objects_sorted_unique")
        expected = {obj["name"]: obj for obj in reference["objects"]}
        require(len({obj["session_uid"] for obj in objects}) == len(objects), "N_unique_session_uid")
        for obj in objects:
            require(set(obj) == {"name", "session_uid", "matrix_world"}, "N_object_exact_fields")
            require(type(obj["session_uid"]) is int and obj["session_uid"] > 0, "N_valid_session_uid")
            matrix = obj["matrix_world"]
            require(len(matrix) == 4 and all(len(axis) == 4 for axis in matrix), "N_matrix_shape")
            require(all(type(value) is float and math.isfinite(value) for axis in matrix for value in axis), "N_finite_float_matrix")
            require(matrix == expected[obj["name"]]["matrix_world"], "N_frozen_current_pose:" + obj["name"])
    require(len({row["pid"] for row in rows}) == 1, "same_N_process")
    require(len({row["namespace_id"] for row in rows}) == 1, "same_N_namespace")
    require(rows[0] == rows[1], "N_BASE_REPEAT_identical")
    for first, edited in zip(rows[0]["objects"], rows[2]["objects"]):
        require(first["session_uid"] == edited["session_uid"], "N_identity_survives_EDIT:" + first["name"])
    return {"passed": True, "marker_retained_across_three_turns": True,
            "same_process_and_namespace": True, "all_object_identities_retained": True,
            "all_24_current_matrices_match_frozen_BASE_REPEAT_EDIT": True,
            "registered_EDIT_object": "Obj_008", "registered_decimal_delta_m": -.00075,
            "qualified_actual_EDIT_matrix_z_m": -.000750000006519258,
            "scope": "engineering memory marker/current poses, without task solver or model memory"}
