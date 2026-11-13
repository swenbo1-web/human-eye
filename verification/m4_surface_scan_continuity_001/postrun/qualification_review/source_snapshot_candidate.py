"""Uninstalled minimal snapshot-adapter candidate for offline review only.

The frozen original remains unchanged. This candidate retains all request/fact
checks and replaces only the assumption that every source packet is rich.
"""

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
SOURCE = BATCH / "qualification/verify_continuity.py"
spec = importlib.util.spec_from_file_location("_continuity_frozen_qualification", SOURCE)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
frozen.require(frozen.digest(SOURCE.read_bytes()) == "b92ec978d739ee0311144316d7e606a8ab8de2b7970bf8b01d2d8af074b9aa55", "frozen_qualification_bytes")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf8")


def bind_source_snapshot(actual, reference):
    """Validate an explicit complete geometry projection or the old rich schema.

    Missing rich fields are reported, never copied into the observed packet.
    Complete names, vertices, topology, matrices and units must match exactly.
    """
    require = frozen.require
    narrow = set(actual) == {"unit_scale_m", "objects"}
    if not narrow:
        frozen.previous_verifier().bind_snapshot(actual, reference)
    require(type(actual["unit_scale_m"]) is float, "observed_unit_float")
    require(actual["unit_scale_m"] == reference["unit_scale_m"], "observed_unit_matches_reference")
    objects = actual["objects"]
    names = [row["name"] for row in objects]
    expected_names = sorted(row["name"] for row in reference["objects"])
    require(len(names) == 24 and names == expected_names and len(set(names)) == 24, "complete_24_object_names")
    required_object_fields = {"name", "vertices_local", "matrix_world", "faces"}
    if narrow:
        require(all(set(row) == required_object_fields for row in objects), "explicit_geometry_projection_fields")
    expected = {row["name"]: row for row in reference["objects"]}
    for row in objects:
        for field in ("vertices_local", "matrix_world", "faces"):
            require(canonical(row[field]) == canonical(expected[row["name"]][field]), "complete_geometry_matches:" + row["name"] + ":" + field)
    projection = {"unit_scale_m": actual["unit_scale_m"],
                  "objects": [{field: row[field] for field in sorted(required_object_fields)} for row in objects]}
    missing_top = sorted(set(reference) - set(actual))
    missing_object = sorted(set(reference["objects"][0]) - set(objects[0]))
    return {"passed": True, "schema": "owner_complete_geometry_projection" if narrow else "qualified_rich_snapshot",
            "objects": len(objects), "vertices": sum(len(row["vertices_local"]) for row in objects),
            "faces": sum(len(row["faces"]) for row in objects),
            "observed_geometry_sha256": frozen.digest(canonical(projection)),
            "missing_rich_top_fields": missing_top, "missing_rich_object_fields": missing_object,
            "rich_source_metadata_verified": not narrow,
            "scope": "all recorded geometry and units equal the frozen reference; absent provenance fields remain unproved"}


def verify_c_turn(result, audit_rows, host_events, source_snapshot, turn, request):
    """Original frozen C checks with the explicit source-schema adapter above."""
    require = frozen.require
    require(turn in frozen.TURNS, "fixed_turn")
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
    truth = frozen.fixed_json(frozen.QUAL / (state + "_TRUTH.json"), frozen.TRUTH_SHA[state])
    reference = frozen.fixed_json(frozen.QUAL / (state + "_SNAPSHOT.json"), frozen.SNAPSHOT_SHA[state])
    source_report = bind_source_snapshot(source_snapshot, reference)
    previous = frozen.previous_verifier()
    facts = previous.verify_facts(result, work, truth, source_snapshot, frozen.SOURCE_SHA, compact=True)
    require(facts["matches"] == frozen.EXPECTED_MATCHES[turn], "registered_match_count")
    require(type(work["kernel_calls"]) is int and work["kernel_calls"] == frozen.EXPECTED_KERNELS[turn], "registered_new_kernel_count")
    require(result.get("display_encoding") == "surface-scan-task-table-v1", "compact_default_encoding")
    require(observed[0]["pid"] == traces[0]["pid"], "audit_runtime_pid_agrees")
    return {
        "passed": True, "turn": turn, "truth_state": state, "truth_sha256": frozen.TRUTH_SHA[state],
        "verified_pair_dispositions": facts["all_pair_partitions_verified"],
        "matches": facts["matches"], "new_kernel_calls": work["kernel_calls"],
        "trace_id": trace_id, "session_id": arguments["session_id"],
        "runtime_pid": observed[0]["pid"], "binding": result["binding"],
        "actual_host_capture_count": 1, "host_sequence": host["sequence"],
        "acquisition_work": work["acquisition_work"],
        "measurement_cache_before": work["measurement_cache_before"],
        "measurement_cache_after": work["measurement_cache_after"],
        "facts": facts, "source_report": source_report,
        "scope": "offline C1 content/evidence recheck using new source adapter; original engineering failure retained",
    }
