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
HOST_SOURCE_SHA = "9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9"
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


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf8")


def bind_source_snapshot(actual, reference):
    """Bind the complete owner geometry projection or the original rich packet.

    Rich metadata absent from an owner packet stays unrecorded. Every observed
    vertex, face index, matrix entry and unit is checked against frozen truth.
    """
    require(type(actual) is dict, "source_snapshot_object")
    narrow = set(actual) == {"unit_scale_m", "objects"}
    if not narrow:
        previous_verifier().bind_snapshot(actual, reference)
    scale = actual["unit_scale_m"]
    require(type(scale) is float and math.isfinite(scale), "source_finite_float_unit")
    require(canonical(scale) == canonical(reference["unit_scale_m"]), "source_unit_matches_reference")
    objects = actual["objects"]
    require(type(objects) is list and len(objects) == 24, "source_complete_24_objects")
    require(all(type(row) is dict and type(row.get("name")) is str for row in objects), "source_object_names")
    names = [row["name"] for row in objects]
    require(names == sorted(row["name"] for row in reference["objects"]), "source_unique_sorted_object_names")
    fields = {"name", "vertices_local", "matrix_world", "faces"}
    expected = {row["name"]: row for row in reference["objects"]}
    for row in objects:
        require((set(row) == fields) if narrow else fields <= set(row), "source_object_geometry_fields")
        vertices, faces, matrix = row["vertices_local"], row["faces"], row["matrix_world"]
        require(type(vertices) is list and bool(vertices), "source_vertices_list")
        require(all(type(vertex) is list and len(vertex) == 3 for vertex in vertices), "source_vertex_shape")
        require(all(type(value) is float and math.isfinite(value) for vertex in vertices for value in vertex), "source_finite_float_vertices")
        require(type(faces) is list and all(type(face) is list and len(face) == 3 for face in faces), "source_triangle_faces")
        require(all(type(index) is int and 0 <= index < len(vertices) for face in faces for index in face), "source_integer_face_indices")
        require(type(matrix) is list and len(matrix) == 4 and all(type(axis) is list and len(axis) == 4 for axis in matrix), "source_matrix_shape")
        require(all(type(value) is float and math.isfinite(value) for axis in matrix for value in axis), "source_finite_float_matrix")
        for field in ("vertices_local", "faces", "matrix_world"):
            require(canonical(row[field]) == canonical(expected[row["name"]][field]), "source_geometry_matches:" + row["name"] + ":" + field)
    projection = {"unit_scale_m": scale, "objects": [{field: row[field] for field in sorted(fields)} for row in objects]}
    return {"passed": True, "schema": "owner_complete_geometry_projection" if narrow else "qualified_rich_snapshot",
            "objects": len(objects), "vertices": sum(len(row["vertices_local"]) for row in objects),
            "faces": sum(len(row["faces"]) for row in objects),
            "observed_geometry_sha256": digest(canonical(projection)),
            "missing_rich_top_fields": sorted(set(reference) - set(actual)),
            "missing_rich_object_fields": sorted(set(reference["objects"][0]) - set(objects[0])),
            "rich_source_metadata_verified": not narrow,
            "scope": "complete observed geometry and units match frozen input; absent rich fields remain unrecorded"}


def read_capture(native_workspace, host_event):
    """Read this capture and the earlier resource deliveries in the same worker.

    Repeated captures may send zero resources. Their references must resolve to
    immutable resource bytes previously delivered in this worker's actual wire.
    """
    wire = Path(native_workspace) / "WIRE"
    sequence = host_event["sequence"]
    require(type(sequence) is int and 0 < sequence <= 128, "capture_sequence")
    index = json.loads((wire / "INDEX.json").read_bytes())
    sequences = [row["sequence"] for row in index]
    require(sequences == sorted(set(sequences)) and sequence in sequences, "capture_wire_index")
    resources, records, origins = {}, [], {}
    current = None
    origin = None
    current_script_sha = None
    for row in index:
        number = row["sequence"]
        if number > sequence:
            break
        folder = wire / str(number).zfill(3)
        request_raw = (folder / "REQUEST.bin").read_bytes()
        response_raw = (folder / "RESPONSE.bin").read_bytes()
        require(len(request_raw) == row["request_bytes"] and len(response_raw) == row["response_attempted_bytes"]
                and row["response_sendall_completed"] is True, "capture_wire_complete")
        request, response = json.loads(request_raw), json.loads(response_raw)
        stdout = response.get("result", {}).get("result", "")
        if type(stdout) is not str:
            continue
        lines = [line[len("HUMAN_EYE_BLENDER_MCP:"):] for line in stdout.splitlines() if line.startswith("HUMAN_EYE_BLENDER_MCP:")]
        if not lines:
            continue
        require(len(lines) == 1 and response["status"] == "success", "capture_single_success_envelope")
        envelope = json.loads(lines[0])
        require("error" not in envelope and type(envelope.get("result")) is dict, "capture_envelope_result")
        delta = envelope["result"]
        require(delta.get("schema") == "human-eye-scene-delta-v1", "capture_delta_schema")
        require(request.get("type") == "execute_code" and type(request.get("params", {}).get("code")) is str, "capture_executed_request")
        binding = delta["capture"]["binding"]
        identity = (binding["host_source_sha256"], binding["host_identity"]["document_epoch"])
        require(identity[0] == HOST_SOURCE_SHA and (origin is None or origin == identity), "capture_history_same_host_document")
        origin = identity
        sent = set()
        for resource in delta["resources"]:
            key = (resource["id"], resource["revision"])
            require(type(key[0]) is str and type(key[1]) is int and key[1] > 0 and key not in sent, "capture_resource_identity")
            require(key not in resources or canonical(resources[key]) == canonical(resource), "capture_resource_revision_immutable")
            sent.add(key)
            resources[key] = resource
            origins[key] = number
        records.append({"sequence": number, "request_sha256": digest(request_raw), "response_sha256": digest(response_raw)})
        if number == sequence:
            current = delta
            current_script_sha = digest(request["params"]["code"].encode("utf8"))
    require(current is not None, "current_capture_record_required")
    require(current_script_sha == host_event["script_sha256"], "capture_executed_script_binding")
    return {"sequence": sequence, "script_sha256": current_script_sha, "delta": current,
            "retained_resources": list(resources.values()),
            "resource_origins": [{"id": key[0], "revision": key[1], "sequence": origins[key]} for key in resources],
            "wire_sources": records, "scope": "current capture plus prior immutable resource deliveries in this worker"}


def bind_capture(captured, host_event, source_snapshot, reference, result):
    """Bind actual current poses and retained wire resources to observed geometry."""
    require(captured["sequence"] == host_event["sequence"] and captured["script_sha256"] == host_event["script_sha256"], "capture_host_event_binding")
    delta = captured["delta"]
    require(delta.get("schema") == "human-eye-scene-delta-v1", "capture_delta_schema")
    capture = delta["capture"]
    binding = capture["binding"]
    require(capture["scope_issues"] == [], "capture_scope_complete")
    require(binding["same_main_thread_read"] is True, "capture_single_main_thread")
    require(type(binding["scale_length"]) is float and canonical(binding["scale_length"]) == canonical(source_snapshot["unit_scale_m"]), "capture_unit_scale")
    require(type(binding["frame"]) is int and binding["frame"] == reference["frame_current"], "capture_fixed_frame")
    require(binding["coordinate_frame"] == result["coordinate_frame"] == "world" and binding["unit"] == "m", "capture_world_m_units")
    require(binding["host_source_sha256"] == result["binding"]["host_source_sha256"] == HOST_SOURCE_SHA, "capture_fixed_host_source")
    require(binding["host_identity"]["document_epoch"] == result["binding"]["document_epoch"], "capture_document_binding")
    require(binding["directory_sha256"] == result["binding"]["directory_sha256"], "capture_directory_binding")
    ids = previous_verifier().object_ids(source_snapshot)
    coverage = capture["coverage"]
    require(len(coverage) == 24 and {row["object_id"]: row["name"] for row in coverage} == ids, "capture_all_24_object_coverage")
    require(all(row["source_status"] == "supported" for row in coverage), "capture_host_supported_sources")
    resources = {(row["id"], row["revision"]): row for row in captured["retained_resources"]}
    require(len(resources) == len(captured["retained_resources"]), "capture_unique_retained_resources")
    meshes = capture["capture"]["meshes"]
    require(len(meshes) == 24, "capture_all_24_meshes")
    expected = {row["name"]: row for row in source_snapshot["objects"]}
    seen, referenced_ids = set(), set()
    for mesh in meshes:
        name = mesh["name"]
        require(name in expected and name not in seen and ids.get(mesh["object_id"]) == name, "capture_mesh_identity")
        seen.add(name)
        resource_ref = mesh["_scene_resource"]
        key = (resource_ref["id"], resource_ref["revision"])
        require(type(key[0]) is str and type(key[1]) is int and key in resources, "capture_resolved_resource_reference")
        resource = resources[key]
        referenced_ids.add(key[0])
        for field in ("vertices_local", "faces"):
            require(canonical(resource[field]) == canonical(expected[name][field]), "capture_geometry_matches:" + name + ":" + field)
        require(canonical(resource_ref["matrix"]) == canonical(expected[name]["matrix_world"]), "capture_geometry_matches:" + name + ":matrix_world")
        require(type(resource_ref["scale"]) is float and canonical(resource_ref["scale"]) == canonical(source_snapshot["unit_scale_m"]), "capture_mesh_unit_scale")
    live = delta["live_resources"]
    require(type(live) is list and len(live) == len(set(live)) == 24 and set(live) == referenced_ids, "capture_live_resource_set")
    return {"passed": True, "objects": 24, "vertices": sum(len(row["vertices_local"]) for row in expected.values()),
            "faces": sum(len(row["faces"]) for row in expected.values()), "sequence": captured["sequence"],
            "transmitted_resources_this_capture": len(delta["resources"]), "resolved_resource_count": len(referenced_ids),
            "resource_origins": captured["resource_origins"], "wire_sources": captured["wire_sources"],
            "host_source_sha256": binding["host_source_sha256"], "rich_source_metadata_verified": False,
            "source_status_scope": "fixed host static-source guard declaration; absent rich fields remain unrecorded"}


def verify_c_turn(result, audit_rows, host_events, source_snapshot, turn, request, *, capture):
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
    source_report = bind_source_snapshot(source_snapshot, reference)
    capture_report = bind_capture(capture, host, source_snapshot, reference, result)
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
        "source_report": source_report, "capture_report": capture_report,
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
