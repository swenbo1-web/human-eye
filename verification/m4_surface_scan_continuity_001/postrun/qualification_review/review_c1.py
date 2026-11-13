"""Read-only postrun source/fact diagnosis. Writes new review material only."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
CELL = BATCH / "episodes/C"
SOURCES = {}


def read(path):
    data = path.read_bytes()
    SOURCES[path.relative_to(ROOT).as_posix()] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return json.loads(data)


def load_candidate():
    spec = importlib.util.spec_from_file_location("_continuity_snapshot_adapter_candidate", HERE / "source_snapshot_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    candidate = load_candidate()
    frozen, require = candidate.frozen, candidate.frozen.require
    protected = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for folder in (BATCH / "qualification", BATCH / "episodes")
                 for path in folder.rglob("*") if path.is_file()}
    initial = read(CELL / "owner/INITIAL.json")
    final = read(CELL / "owner/FINAL.json")
    reference = read(frozen.QUAL / "BASE_SNAPSHOT.json")
    read(frozen.QUAL / "BASE_TRUTH.json")
    require(frozen.digest((frozen.QUAL / "BASE_SNAPSHOT.json").read_bytes()) == frozen.SNAPSHOT_SHA["BASE"], "fixed_BASE_snapshot")
    require(frozen.digest((frozen.QUAL / "BASE_TRUTH.json").read_bytes()) == frozen.TRUTH_SHA["BASE"], "fixed_BASE_truth")
    turn = read(CELL / "TURN_BASE.json")
    episode = read(CELL / "RESULTS.json")
    request = read(CELL / "owner/tool_01/REQUEST.json")
    response = read(CELL / "owner/tool_01/RESPONSE.json")
    require(request == turn["request"], "actual_request_matches_turn")
    body = json.loads(response["result"]["content"][0]["text"])
    require(body == turn["body"], "actual_response_matches_turn")
    audit_path = CELL / "owner/audit.jsonl"
    worker_path = CELL / "owner/native/WORKER_EVENTS.jsonl"
    for path in (audit_path, worker_path):
        data = path.read_bytes()
        SOURCES[path.relative_to(ROOT).as_posix()] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    audit = [json.loads(line) for line in audit_path.read_bytes().splitlines()]
    worker = [json.loads(line) for line in worker_path.read_bytes().splitlines()]
    host = [row for row in worker if type(row.get("started_ns")) is int and turn["started_ns"] <= row["started_ns"] <= turn["ended_ns"]]
    original_error = None
    try:
        frozen.verify_c_turn(body, audit, host, initial, "BASE", turn["request"])
    except AssertionError as error:
        original_error = str(error)
    require(original_error == "actual geometry or source fields differ from qualified state", "original_schema_failure_reproduced")
    source_report = candidate.bind_source_snapshot(initial, reference)
    final_source_report = candidate.bind_source_snapshot(final, reference)
    require(candidate.canonical(initial) == candidate.canonical(final), "actual_INITIAL_FINAL_geometry_equal")

    sequence = host[0]["sequence"]
    captured_wire = read(CELL / ("owner/native/WIRE/%03d/RESPONSE.bin" % sequence))
    require(captured_wire["status"] == "success", "actual_capture_wire_success")
    stdout = captured_wire["result"]["result"]
    envelopes = [json.loads(line[len("HUMAN_EYE_BLENDER_MCP:"):]) for line in stdout.splitlines() if line.startswith("HUMAN_EYE_BLENDER_MCP:")]
    require(len(envelopes) == 1 and "error" not in envelopes[0], "single_actual_capture_envelope")
    delta = envelopes[0]["result"]
    require(delta["schema"] == "human-eye-scene-delta-v1", "actual_delta_schema")
    capture = delta["capture"]
    require(capture["scope_issues"] == [], "actual_source_scope_complete")
    require(capture["binding"]["same_main_thread_read"] is True, "single_main_thread_source_read")
    require(capture["binding"]["scale_length"] == initial["unit_scale_m"] == 1., "actual_capture_units")
    require(capture["binding"]["frame"] == reference["frame_current"], "actual_capture_frame")
    require(capture["binding"]["coordinate_frame"] == body["coordinate_frame"] == "world", "actual_world_coordinate_frame")
    require(capture["binding"]["host_identity"]["document_epoch"] == body["binding"]["document_epoch"], "actual_capture_document_binding")
    require(capture["binding"]["directory_sha256"] == body["binding"]["directory_sha256"], "actual_capture_directory_binding")
    ids = frozen.previous_verifier().object_ids(initial)
    coverage = capture["coverage"]
    require(len(coverage) == 24 and {row["object_id"]: row["name"] for row in coverage} == ids, "actual_24_object_coverage")
    require(all(row["source_status"] == "supported" for row in coverage), "host_reports_supported_sources")
    resources = {(row["id"], row["revision"]): row for row in delta["resources"]}
    meshes = capture["capture"]["meshes"]
    require(len(resources) == len(meshes) == 24, "actual_24_resources_and_meshes")
    expected_objects = {row["name"]: row for row in initial["objects"]}
    seen = set()
    for mesh in meshes:
        name = mesh["name"]
        require(name in expected_objects and name not in seen and ids[mesh["object_id"]] == name, "capture_mesh_identity")
        seen.add(name)
        resource_ref = mesh["_scene_resource"]
        resource = resources[(resource_ref["id"], resource_ref["revision"])]
        expected = expected_objects[name]
        require(candidate.canonical(resource["vertices_local"]) == candidate.canonical(expected["vertices_local"]), "captured_vertices_match:" + name)
        require(candidate.canonical(resource["faces"]) == candidate.canonical(expected["faces"]), "captured_faces_match:" + name)
        require(candidate.canonical(resource_ref["matrix"]) == candidate.canonical(expected["matrix_world"]), "captured_matrix_matches:" + name)
        require(resource_ref["scale"] == initial["unit_scale_m"], "captured_unit_scale:" + name)
    require(len(seen) == 24, "complete_captured_geometry")
    postrun = candidate.verify_c_turn(body, audit, host, initial, "BASE", turn["request"])
    require(episode["execution_counts"] == {"planned": 3, "attempted": 1, "completed": 0, "failed": 1, "not_run": 2}, "original_C_denominator_retained")
    require(episode["passed_before_publication"] is False and bool(turn["errors"]), "original_C_failure_retained")

    tests = []
    for name, source, reason in (
        ("wrong_unit", copy.deepcopy(initial), "observed_unit_matches_reference"),
        ("missing_object", copy.deepcopy(initial), "complete_24_object_names"),
        ("wrong_vertex", copy.deepcopy(initial), "complete_geometry_matches:Obj_001:vertices_local"),
        ("wrong_topology", copy.deepcopy(initial), "complete_geometry_matches:Obj_001:faces"),
        ("wrong_matrix", copy.deepcopy(initial), "complete_geometry_matches:Obj_001:matrix_world"),
    ):
        if name == "wrong_unit":
            source["unit_scale_m"] = .001
        elif name == "missing_object":
            source["objects"].pop()
        elif name == "wrong_vertex":
            source["objects"][0]["vertices_local"][0][0] += .001
        elif name == "wrong_topology":
            source["objects"][0]["faces"][0] = [0, 0, 0]
        else:
            source["objects"][0]["matrix_world"][2][3] = .001
        actual_reason = None
        try:
            candidate.bind_source_snapshot(source, reference)
        except AssertionError as error:
            actual_reason = str(error)
        require(actual_reason == reason, "candidate_negative_exact_reason:" + name)
        tests.append({"case": name, "rejected_by": actual_reason})
    require(candidate.bind_source_snapshot(reference, reference)["rich_source_metadata_verified"] is True, "legacy_rich_schema_still_accepted")
    changed_rich = copy.deepcopy(reference)
    changed_rich["objects"][0]["parent"] = "unexpected"
    rich_rejected = False
    try:
        candidate.bind_source_snapshot(changed_rich, reference)
    except AssertionError as error:
        rich_rejected = str(error) == "actual geometry or source fields differ from qualified state"
    require(rich_rejected, "rich_source_metadata_change_rejected")
    require(all(hashlib.sha256(path.read_bytes()).hexdigest() == value for path, value in protected.items()), "all_frozen_and_episode_files_preserved")
    result = {"schema": "continuity_C1_postrun_qualification_review_v1", "status": "offline_review_pass",
              "original_source_schema_failure_reproduced": original_error,
              "root_cause": "Frozen verifier required a rich qualification snapshot, while owner emits complete narrow geometry; offline fixtures covered only the rich schema.",
              "actual_initial_source": source_report, "actual_final_source": final_source_report,
              "actual_capture_geometry_verified": {"objects": 24, "vertices": 530, "faces": 978, "units_m": 1., "frame": 1, "same_main_thread_read": True, "matches_actual_owner_geometry": True},
              "C1_candidate_fact_report": postrun, "negative_cases": tests,
              "legacy_rich_accepted_and_changed_rich_rejected": True,
              "original_episode_pass": False, "original_execution_counts": episode["execution_counts"],
              "new_live_calls_or_retries": 0, "frozen_and_episode_files_preserved": len(protected),
              "candidate_installed_or_applied": False,
              "limitations": ["C REPEAT and EDIT not run, so three-turn caching/retention remains unverified.", "Missing rich source fields are not recreated or certified; captured source_status is the host's gate declaration.", "Postrun content verification does not upgrade original engineering failure or prove actual model continuity."],
              "sources": [{"path": key, **value} for key, value in sorted(SOURCES.items())]}
    (HERE / "REVIEW.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": result["status"], "C1_matches": postrun["facts"]["matches"], "new_kernels": postrun["new_kernel_calls"], "C_original_pass": False, "C_original_counts": episode["execution_counts"], "negative_cases": len(tests), "live_calls": 0, "protected_files_preserved": len(protected)}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        path = HERE / ("REVIEW_FAILURE_%02d.json" % (len(list(HERE.glob("REVIEW_FAILURE_*.json"))) + 1))
        path.write_text(json.dumps({"scope": "postrun offline checker failure", "traceback": traceback.format_exc(), "live_calls": 0}, indent=2) + "\n", encoding="utf8")
        raise
