"""Numerical regressions on this batch's actual damaged-file readback."""

import copy
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluate import evaluate_packets, packet
from quality import geometry_quality
from score import identity, score_packet
import facts_api
import numpy as np


def write(path, value):
    facts_api.write(path, value)


def world_from_native(value):
    matrix = value["matrix_world"]
    value["vertices"] = value["vertices_local"].astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    value["vertices_world"] = value["vertices"]


def main():
    started, cpu = time.perf_counter(), time.process_time()
    root = HERE / "private/quality_preflight"
    root.mkdir(parents=True, exist_ok=True)
    attempts = sorted(root.glob("attempt_*"))
    output = root / ("attempt_" + str(len(attempts) + 1).zfill(3))
    output.mkdir(exist_ok=False)
    result = dict(status="running", attempt=len(attempts) + 1, actual_Pro_calls=0, actual_Blender_calls=0,
        train_calls=0, paid_API_calls=0, output_directory=str(output), started_unix_s=time.time(), checks={})
    write(output / "ATTEMPT.json", result)
    checks = result["checks"]
    try:
        case = HERE / "private/cases/matched"
        initial_path = case / "initial.npz"
        target_path = HERE / "private/scoring/target.npz"
        initial, target = packet(initial_path), packet(target_path)
        spec = json.loads((case / "spec.json").read_bytes())
        scene = json.loads((case / "baseline_scene.json").read_bytes())
        def qa(value, *, exact=False):
            return geometry_quality(initial, value, initial, spec, scene, scene, check_intersections=exact)

        baseline = evaluate_packets(initial_path, initial_path, initial_path, case / "spec.json",
            before_state_path=case / "baseline_scene.json", after_state_path=case / "baseline_scene.json")
        write(output / "BASELINE.json", baseline)
        checks["actual_damaged_baseline_technical_pass"] = baseline["status"] == "pass"
        checks["fixed_domains_410_274"] = (len(initial["F_source_ids"]), len(initial["I_ids"])) == (410, 274)
        checks["gradient_normal_observation_only"] = not any("gradient" in key or "normal_change" in key for key in baseline["checks"])
        checks["fixed_restoration_budgets"] = spec["max_operation_displacement_m"] == spec["max_cumulative_displacement_m"] == 0.006893660855829761
        restored = copy.deepcopy(initial)
        I = initial["I_ids"]
        inverse = np.linalg.inv(initial["matrix_world"])
        local_clean = target["clean_vertices_world"] @ inverse[:3, :3].T + inverse[:3, 3]
        restored["vertices_local"][I] = local_clean[I].astype(np.float32)
        world_from_native(restored)
        restored_path = output / "restored_saved_precision_candidate.npz"
        np.savez_compressed(restored_path, **restored)
        correct = qa(restored, exact=True)
        write(output / "RESTORATION_TECHNICAL.json", correct)
        checks["clean_candidate_all_technical_checks_pass"] = correct["status"] == "pass"
        checks["clean_candidate_exact_contact_scan_executed"] = correct["geometry"]["self_intersection"]["exact_pair_scan_executed"]
        baseline_score = score_packet(initial_path, target_path, output / "BASELINE_SCORE.json")
        restored_score = score_packet(restored_path, target_path, output / "RESTORATION_SCORE.json")
        checks["unchanged_result_restoration_fails"] = baseline_score["restoration_quality_pass"] is False
        checks["unchanged_support_improvement_zero"] = baseline_score["metrics"]["support_47"]["RMSE_reduction_fraction"] == 0.
        checks["clean_candidate_restoration_quality_pass"] = restored_score["restoration_quality_pass"] is True
        checks["private_score_counts_47_363_227"] = tuple(restored_score["metrics"][key]["after"]["points"]
            for key in ("support_47", "normal_363", "normal_editable_227")) == (47, 363, 227)
        changes = {}
        outside = copy.deepcopy(initial)
        protected = int(np.setdiff1d(initial["source_ids"], I)[0])
        outside["vertices_local"][protected, 0] = np.nextafter(outside["vertices_local"][protected, 0], np.float32(np.inf))
        world_from_native(outside)
        changes["outside_one_bit"] = qa(outside)
        checks["outside_I_one_native_bit_fails"] = changes["outside_one_bit"]["checks"]["outside_I_local_float32_bitwise"] is False
        budget = copy.deepcopy(initial)
        budget["vertices_local"][int(I[0]), 1] += np.float32(.03)
        world_from_native(budget)
        changes["over_budget"] = qa(budget)
        checks["over_budget_fails"] = changes["over_budget"]["checks"]["cumulative_displacement_budget"] is False
        source = copy.deepcopy(initial)
        source["source_ids"][0], source["source_ids"][1] = source["source_ids"][1], source["source_ids"][0]
        changes["source_ID_change"] = qa(source)
        checks["source_mapping_change_fails"] = changes["source_ID_change"]["checks"]["source_vertex_ids"] is False
        topology = copy.deepcopy(initial)
        topology["poly_vertices"][0] += 1
        changes["native_topology_change"] = qa(topology)
        checks["native_topology_change_fails"] = changes["native_topology_change"]["checks"]["native_polygon_vertices"] is False
        matrix = copy.deepcopy(initial)
        matrix["matrix_world"][0, 3] += .001
        world_from_native(matrix)
        changes["matrix_change"] = qa(matrix)
        checks["source_matrix_change_fails"] = changes["matrix_change"]["checks"]["target_matrix"] is False
        scene_change = dict(scene, target_materials_sha256="changed_UV_material_or_image_metadata")
        changes["material_UV_change"] = geometry_quality(initial, initial, initial, spec, scene, scene_change)
        checks["UV_material_fingerprint_change_fails"] = changes["material_UV_change"]["checks"]["target_materials_sha256"] is False
        nonfinite = copy.deepcopy(initial)
        nonfinite["vertices_local"][int(I[0]), 0] = np.nan
        try:
            qa(nonfinite)
        except ValueError as error:
            checks["nonfinite_native_rejected"] = str(error) == "finite_native_float32_and_world_coordinates_required"
        write(output / "GUARD_MUTATIONS.json", changes)
        # This is a binding label for current-geometry facts, without a real consumer session.
        binding = output / "binding_fixture"
        state = dict(case_id="sample_05", version=0, current_npz=str(initial_path), initial_npz=str(initial_path), source_spec=str(case / "spec.json"))
        focused = facts_api.focus(binding, state)
        resolved = facts_api.resolve_ref(binding, state, focused["target"]["reference"])
        editable = facts_api.resolve_ref(binding, state, focused["editable"]["reference"])
        with np.load(resolved["geometry_packet"]["path"], allow_pickle=False) as observed:
            checks["focus_actual_damaged_positions"] = np.array_equal(observed["current_positions_world"], initial["vertices"][initial["F_source_ids"]])
            checks["focus_current_scope_410"] = np.array_equal(observed["source_ids"], initial["F_source_ids"])
        with np.load(editable["geometry_packet"]["path"], allow_pickle=False) as observed:
            checks["focus_current_editable_274"] = np.array_equal(observed["source_ids"], I)
        checks["resolve_default_arrays_are_descriptor"] = all(key not in resolved for key in ("source_ids", "current_positions_world", "current_vertex_normals", "lumped_area_world"))
        for label, other_binding, other_state in (("stale_reference_rejected", binding, dict(state, version=1)),
                                                  ("cross_binding_reference_rejected", output / "other_binding", state)):
            try:
                facts_api.resolve_ref(other_binding, other_state, focused["target"]["reference"])
            except ValueError as error:
                checks[label] = str(error) == "region_reference_outside_current_session_version"
        write(output / "FOCUS.json", focused)
        write(output / "RESOLVED.json", resolved)
        result.update(status="pass" if all(checks.values()) else "fail", passed=sum(checks.values()), total=len(checks),
            exact_contact_scans=2, skipped_contact_scope="Deliberate guard mutations only", actual_saved_candidate=False,
            candidate_scope="Native-float32 precision numerical feasibility control. Actual Blender save/read control is performed separately.")
    except BaseException as error:
        result.update(status="error", error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    result.update(wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
        resources=facts_api.FOCUS.process_resources(),
        sources=[identity(HERE / name) for name in ("quality.py", "evaluate.py", "facts_api.py", "score.py", "quality_preflight.py")])
    write(output / "ATTEMPT.json", result)
    summary = dict(attempts=[json.loads(path.read_bytes()) for path in sorted(root.glob("attempt_*/ATTEMPT.json"))])
    summary.update(status=result["status"], wall_s_total=sum(row["wall_s"] for row in summary["attempts"]),
        cpu_s_total=sum(row["cpu_s"] for row in summary["attempts"]), actual_Pro_calls=0, actual_Blender_calls=0)
    write(HERE / "QUALITY_PREFLIGHT.json", summary)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
