"""Verify all fixed normal/paired focus requests without a prediction gate."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
from interfaces import TaskPerception, source_ids_digest, fixed_target_ids


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def same_bits(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def main():
    started, cpu = time.perf_counter(), time.process_time()
    index = {row["alias"]: row for row in json.loads((HERE / "INPUT_INDEX.json").read_bytes())["cases"]}
    if not (HERE / "FOCUS_TASKS.json").exists():
        fixed = json.loads((HERE / "TASKS.json").read_bytes())
        request = next(row["request_text"] for row in fixed["tasks"] if row["entrypoint"] == "focus")
        focus_rows = []
        for pair in fixed["focus_pairs"]:
            with np.load(HERE / index[pair["normal_alias"]]["input"]["path"], allow_pickle=False) as normal:
                F = normal["F_source_ids"].astype(np.int64)
                target = fixed_target_ids(normal["faces"], F)
            protected = np.setdiff1d(F, target)
            for field in ("normal_alias", "damaged_alias"):
                focus_rows.append(dict(id="f" + str(len(focus_rows) + 1).zfill(2), alias=pair[field], pair_group=pair["roi_alias"],
                                       target_ids=target.tolist(), protected_ids=protected.tolist(), request_text=request))
        write_json(HERE / "FOCUS_TASKS.json", dict(cases=focus_rows, selection=fixed["focus_target_rule"],
            source_tasks_sha256=hashlib.sha256((HERE / "TASKS.json").read_bytes()).hexdigest()))
    tasks = json.loads((HERE / "FOCUS_TASKS.json").read_bytes())["cases"]
    if len(tasks) != 16:
        raise ValueError("fixed_16_focus_case_denominator_required")
    prototype = TaskPerception()

    def unexpected_prediction(*args, **kwargs):
        raise AssertionError("focus_must_not_read_feature_or_model_prediction")

    prototype._features = unexpected_prediction
    prototype._prediction = unexpected_prediction
    checks, failures, results = [], [], []
    groups = defaultdict(list)

    def check(name, passed, case=None):
        row = dict(name=name, passed=bool(passed), case=case)
        checks.append(row)
        if not passed:
            failures.append(row)

    for number, task in enumerate(tasks, 1):
        alias = task["alias"]
        request_id = task.get("id", "q" + str(number).zfill(2))
        target = np.sort(np.asarray(task["target_ids"], dtype=np.int64))
        protected = np.sort(np.asarray(task["protected_ids"], dtype=np.int64))
        with np.load(HERE / index[alias]["input"]["path"], allow_pickle=False) as source:
            vertices, faces = source["vertices"], source["faces"]
            F = source["F_source_ids"].astype(np.int64)
        triangle = vertices[faces]
        cross = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
        area = np.zeros(len(vertices), dtype=np.float64)
        normal_sum = np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(area, faces[:, corner], np.linalg.norm(cross, axis=1) / 6)
            np.add.at(normal_sum, faces[:, corner], cross)
        normal_norm = np.linalg.norm(normal_sum, axis=1)
        normals = np.divide(normal_sum, normal_norm[:, None], out=np.zeros_like(normal_sum), where=normal_norm[:, None] > 0)
        expected_area = float(area[target].sum())
        expected_centroid = np.sum(vertices[target] * area[target, None], axis=0) / expected_area
        average_normal = np.sum(normals[target] * area[target, None], axis=0)
        normal_magnitude = float(np.linalg.norm(average_normal))
        expected_normal = average_normal / normal_magnitude if normal_magnitude else None
        report = prototype.focus(alias, target, protected, request=task.get("request_text", "read the explicitly specified target"))
        target_ref = report["target"]["reference"]
        resolved = prototype.resolve(target_ref)
        actual_ids = np.asarray(resolved["source_ids"], dtype=np.int64)
        actual_points = np.asarray(resolved["current_positions_native"], dtype=np.float64)
        facts = report["target"]["geometry"]
        check("target_readable_without_anomaly_threshold", report["anomaly_threshold_applied"] is False and not report["learned_output_used"], request_id)
        check("no_model_call_no_cached_prediction", report["cost"]["model_called_in_this_request"] is False and not report["cached_prediction_used"], request_id)
        check("exact_requested_target_source_IDs", same_bits(target, actual_ids), request_id)
        check("exact_current_target_coordinates", same_bits(vertices[target], actual_points), request_id)
        check("actual_lumped_area_exact", facts["lumped_area_native"] == expected_area, request_id)
        check("actual_area_weighted_centroid_exact", same_bits(np.asarray(facts["centroid_native"]), expected_centroid), request_id)
        check("actual_bbox_exact", same_bits(np.asarray(facts["bbox_native"]["min"]), vertices[target].min(axis=0))
              and same_bits(np.asarray(facts["bbox_native"]["max"]), vertices[target].max(axis=0)), request_id)
        check("actual_mean_normal_exact", facts["mean_normal"] is None if expected_normal is None else same_bits(np.asarray(facts["mean_normal"]), expected_normal), request_id)
        check("current_vertex_topology_mapping_bound", resolved["identity"]["current_vertices_sha256"] == hashlib.sha256(np.ascontiguousarray(vertices).tobytes()).hexdigest()
              and resolved["identity"]["topology_sha256"] == hashlib.sha256(np.ascontiguousarray(faces.astype(np.int64)).tobytes()).hexdigest()
              and resolved["identity"]["F_source_ids_sha256"] == source_ids_digest(F), request_id)
        check("physical_units_unknown", facts["physical_unit"] == "unknown" and facts["area_unit"] == "source_native_squared", request_id)
        background = prototype.resolve(report["background"]["reference"])
        protected_result = prototype.resolve(report["protected"]["reference"])
        check("background_roles_preserved", background["identity"]["kind"] == "observable_background"
              and np.array_equal(np.asarray(background["source_ids"]), np.setdiff1d(F, target)), request_id)
        check("protection_roles_preserved_and_readable", protected_result["identity"]["kind"] == "protected_from_editing"
              and np.array_equal(np.asarray(protected_result["source_ids"]), protected), request_id)
        check("editable_target_excludes_protected", np.array_equal(report["editable_target_source_ids"], np.setdiff1d(target, protected)), request_id)
        context = prototype.read_more(target_ref, ring_hops=1)
        context_resolved = prototype.resolve(context["context"]["reference"])
        edges = np.unique(np.sort(np.concatenate((faces[:,[0,1]], faces[:,[1,2]], faces[:,[2,0]])),axis=1),axis=0)
        incident = edges[np.isin(edges, target).any(axis=1)]
        expected_context = np.unique(np.r_[target, incident.ravel()])
        check("one_ring_context_exact_and_readable", np.array_equal(context_resolved["source_ids"], expected_context), request_id)
        check("background_observable_editing_unauthorized", context["background_observation_allowed"] and not context["editing_authorized"], request_id)
        fresh = TaskPerception()
        rebound = fresh.resolve(target_ref)
        check("reference_persists_across_interface_instance", rebound["identity"] == resolved["identity"] and rebound["source_ids"] == resolved["source_ids"], request_id)
        declared_sha = prototype.cases[alias]["input"]["sha256"]
        prototype.cases[alias]["input"]["sha256"] = "0" * 64
        rejected = False
        try:
            prototype.resolve(target_ref)
        except ValueError as error:
            rejected = str(error) == "current_input_version_changed"
        finally:
            prototype.cases[alias]["input"]["sha256"] = declared_sha
        check("changed_input_version_rejected_despite_cached_geometry", rejected, request_id)
        check("current_geometry_file_unchanged", hashlib.sha256((HERE / index[alias]["input"]["path"]).read_bytes()).hexdigest() == declared_sha, request_id)
        groups[task["pair_group"]].append(dict(alias=alias,target_digest=source_ids_digest(target),protected_digest=source_ids_digest(protected)))
        path = HERE / "private/focus_reports" / (request_id + ".json")
        write_json(path,dict(task_id=request_id,report=report,target_resolution=resolved,context=context))
        results.append(dict(id=request_id,alias=alias,pair_group=task["pair_group"],target_reference=target_ref,
                            report_path=path.relative_to(HERE).as_posix(),target_points=len(target),protected_points=len(protected)))
    for group, members in groups.items():
        check("two_observations_same_explicit_target", len(members)==2 and len({row["target_digest"] for row in members})==1
              and len({row["protected_digest"] for row in members})==1, group)
    check("all8_validation_ROI_pairs_covered", len(groups)==8)
    normal_cases = sum(index[task["alias"]].get("state") == "normal" for task in tasks)
    damaged_cases = sum(index[task["alias"]].get("state") == "damaged" for task in tasks)
    if normal_cases + damaged_cases == len(tasks):
        check("8normal8damaged_focus_requests", normal_cases == damaged_cases == 8)
    write_json(HERE / "FOCUS_QA.json",dict(status="passed" if not failures else "failed",request_count=len(tasks),paired_ROIs=len(groups),
        cases=results,checks=checks,check_count=len(checks),failures=failures,
        model_calls=0,feature_or_prediction_reads=0,scope="explicit source-point binding, current measurements, readable protected context and stable references",
        normal_cases=normal_cases,damaged_cases=damaged_cases,
        limitations="target part semantics and artistic refinement quality untested, original geometry unchanged",
        wall_s_before_write=time.perf_counter()-started,CPU_s_before_write=time.process_time()-cpu))
    print("focus QA",len(tasks),"requests",len(checks),"checks","failures",len(failures),flush=True)


if __name__=="__main__":
    main()
