"""Certify the unchanged first T1 asset, retaining actual evaluated transforms.

The first QA oracle rejected Blender's small Euler-reconstruction error. It and
its failure remain intact. This revision certifies actual affine solids and
outward distance intervals; it does not edit the asset, spec or raw snapshot.
"""
from __future__ import annotations
import argparse
import copy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC_SHA = "b54110358c37dc7be1f47a201ef14b12156923f53729a723874ab902645a4ce2"
ASSET_SHA = "e123b5578dbb1629778a72d889509ff986328724b463a7db0fc8ea9d470b5630"
SNAPSHOT_SHA = "0aab174aa37e7e662234c7f0cdf7bb1fd1e0a747d597e891f2155b504ab11d5b"
QA = None


def need(condition, reason):
    if not condition:
        raise ValueError("T1_interval_" + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inverse(matrix):
    det = QA.dot(matrix[0], QA.cross(matrix[1], matrix[2]))
    need(det > 0, "positive_actual_determinant")
    columns = [QA.cross(matrix[1], matrix[2]), QA.cross(matrix[2], matrix[0]), QA.cross(matrix[0], matrix[1])]
    inv = [tuple(columns[column][row] / det for column in range(3)) for row in range(3)]
    need(all(sum(matrix[row][index] * inv[index][column] for index in range(3)) == int(row == column) for row in range(3) for column in range(3)), "exact_inverse")
    return inv, det


def matvec(matrix, vector):
    return tuple(QA.dot(row, vector) for row in matrix)


def endpoint(value, upper):
    result = float(value)
    rounded_inward = F(result) < value if upper else F(result) > value
    if rounded_inward:
        result = math.nextafter(result, math.inf if upper else -math.inf)
    return result


def certify(spec, snapshot, snapshot_sha):
    QA.check()
    need(snapshot["asset_sha256"] == ASSET_SHA and snapshot["unit_scale_m"] == spec["unit_scale_m"] == 1
         and snapshot["frame"] == 1 and snapshot["read_only"] is True
         and snapshot["save_calls"] == snapshot["setter_calls"] == 0, "actual_source_contract")
    by_name = {row["name"]: row for row in snapshot["objects"]}
    need(len(snapshot["objects"]) == len(by_name) == 4 and set(by_name) == set(spec["names"].values()), "complete_object_coverage")
    scale = F(*spec["coordinate_scale_m"])
    rotation = [tuple(map(F, row)) for row in spec["common_rigid_rotation_rows"]]
    translation = tuple(F(value) * scale for value in spec["common_translation_assembly_units"])
    target = by_name[spec["names"]["target"]]
    actual = [tuple(map(F, row[:3])) for row in target["matrix_world"][:3]]
    inv, determinant = inverse(actual)
    target_translation = tuple(F(row[3]) for row in target["matrix_world"][:3])
    need(target_translation == translation, "actual_target_origin")
    certificates, shifts, radii, actual_bounds, actual_centers, origins, translations = {}, {}, {}, {}, {}, {}, {}
    for role, name in spec["names"].items():
        QA.check()
        row = by_name[name]
        matrix = [tuple(map(F, line)) for line in row["matrix_world"]]
        need(matrix[3] == (0, 0, 0, 1) and [line[:3] for line in matrix[:3]] == actual, "common_actual_affine_rotation")
        origin = (F(0),) * 3 if role == "target" else tuple((F(a) + F(b)) / 2 for a, b in zip(spec["candidate_boxes"][role]["lower"], spec["candidate_boxes"][role]["upper"]))
        origins[role] = origin
        translations[role] = tuple(line[3] for line in matrix[:3])
        expected_translation = tuple(translation[axis] + scale * value for axis, value in enumerate(matvec(rotation, origin)))
        need(tuple(line[3] for line in matrix[:3]) == expected_translation, "actual_origin_preserved")
        # This explicit reference is a proof device. The actual source matrices
        # are preserved below and never replaced in Blender or the input packet.
        reference = copy.deepcopy(row)
        reference["matrix_world"] = [[float(value) for value in rotation[axis]] + [float(expected_translation[axis])] for axis in range(3)] + [[0, 0, 0, 1]]
        cert, _ = QA.certify_mesh(reference, role, spec)
        radius = F(0)
        actual_world = []
        for vertex_raw in row["vertices_local"]:
            local = tuple(map(F, vertex_raw))
            point = tuple(value + matrix[axis][3] for axis, value in enumerate(matvec(actual, local)))
            ideal = tuple(value + expected_translation[axis] for axis, value in enumerate(matvec(rotation, local)))
            radius = max(radius, sum(abs(a - b) for a, b in zip(point, ideal)))
            actual_world.append(point)
        shift = tuple(value / scale - origin[axis] for axis, value in enumerate(matvec(inv, tuple(line[3] - target_translation[axis] for axis, line in enumerate(matrix[:3])))))
        actual_bounds[role] = [(min(point[axis] for point in actual_world), max(point[axis] for point in actual_world)) for axis in range(3)]
        actual_centers[role] = tuple((a + b) / 2 for a, b in actual_bounds[role])
        cert.update(reference_role="analytic reference boundary only; actual affine correspondence separately certified",
            local_boundary_reconstruction="actual vertices_local / frozen coordinate_scale + exact per-object analytic origin; ideal R is exactly orthogonal, no approximate inverse or normalized actual matrix",
            actual_matrix_world=[[str(value) for value in line] for line in matrix],
            actual_determinant=str(determinant), actual_affine_bijection_preserves_closed_shell=True,
            corresponding_triangle_vertex_L1_displacement_bound_m=str(radius),
            surface_Hausdorff_bound_m=str(radius), common_target_frame_translation_shift=list(map(str, shift)),
            actual_bounds_world_m=[[str(a), str(b)] for a, b in actual_bounds[role]])
        certificates[role], shifts[role], radii[role] = cert, shift, radius
    target_boxes = spec["target_solid_rectangular_partition"]
    facts, intervals = {}, {}
    for role, original in spec["candidate_boxes"].items():
        shifted = {key: [F(value) + shifts[role][axis] for axis, value in enumerate(original[key])] for key in ("lower", "upper")}
        expected = spec["expected_facts_in_assembly_units"][role]
        if role == "penetrating":
            witness = tuple(map(F, expected["strict_shared_interior_witness"]))
            members = [box for box in target_boxes if QA.inside_strict(witness, box)]
            need(members and QA.inside_strict(witness, shifted), "actual_common_interior")
            margin = min(QA.margin(witness, shifted), max(QA.margin(witness, box) for box in members))
            inverse_norm = max(sum(abs(value) for value in row) for row in inv)
            world_margin = margin * scale / inverse_norm
            target_only = tuple(map(F, expected["target_only_witness"]))
            candidate_only = tuple(F(value) + shifts[role][axis] for axis, value in enumerate(expected["candidate_only_witness"]))
            need(any(QA.inside_strict(target_only, box) for box in target_boxes) and not QA.inside_strict(target_only, shifted), "actual_target_only")
            need(QA.inside_strict(candidate_only, shifted) and not any(QA.inside_strict(candidate_only, box) for box in target_boxes), "actual_candidate_only")
            world_witness = tuple(value + target_translation[axis] for axis, value in enumerate(matvec(actual, tuple(value * scale for value in witness))))
            inverse_points = {}
            for witness_role in ("target", role):
                inverse_points[witness_role] = tuple(value / scale + origins[witness_role][axis]
                    for axis, value in enumerate(matvec(inv, QA.sub(world_witness, translations[witness_role]))))
            need(any(QA.inside_strict(inverse_points["target"], box) for box in target_boxes)
                 and QA.inside_strict(inverse_points[role], original), "one_world_witness_actual_inverse_membership")
            facts[role] = {"name": spec["names"][role], "relation": "penetrating", "separation_gap_m": None,
                "strict_common_interior_witness_world_m": list(map(str, world_witness)),
                "same_world_point_actual_inverse_assembly_coordinates": {key: list(map(str, value)) for key, value in inverse_points.items()},
                "strict_interior_world_radius_lower_bound_m": str(world_margin),
                "actual_candidate_box_in_target_affine_frame": {key: list(map(str, values)) for key, values in shifted.items()},
                "not_a_penetration_depth": True, "proof": "exact common affine inverse gives a strictly positive shared interior and points belonging only to each solid"}
        else:
            lower_squared = [QA.distance_squared_boxes(box, shifted) for box in target_boxes]
            need(min(lower_squared) > 0, "actual_solids_not_disjoint")
            nominal = F(*expected["gap"]) * scale
            radius = radii["target"] + radii[role]
            lower, upper = nominal - radius, nominal + radius
            need(lower > 0 and radius < F(1, 1000000), "distance_not_certifiable_in_frozen_tolerance")
            # Recheck the independent nominal lower bound and attained witness.
            need(min(QA.distance_squared_boxes(box, original) for box in target_boxes) * scale**2 == nominal**2, "nominal_lower_bound")
            a, b = [tuple(map(F, expected[key])) for key in ("distance_witness_target", "distance_witness_candidate")]
            need(QA.point_on_boundary(a, QA.union_boundary(target_boxes)) and QA.point_on_boundary(b, QA.union_boundary([original]))
                 and QA.dot(QA.sub(a, b), QA.sub(a, b)) * scale**2 == nominal**2, "nominal_attained_boundary_witness")
            intervals[role] = (lower, upper)
            facts[role] = {"name": spec["names"][role], "relation": "separated",
                "separation_gap_m": str(nominal), "separation_gap_is_exact": False,
                "distance_m": float(nominal), "distance_mm": float(nominal * 1000),
                "distance_interval_m": [endpoint(lower, False), endpoint(upper, True)],
                "distance_interval_fraction_m": [str(lower), str(upper)],
                "distance_error_bound_m": endpoint(radius, True),
                "actual_partition_distance_squared_target_frame": list(map(str, lower_squared)),
                "proof": "actual solids disjoint in the common affine inverse; reference exact gap plus per-triangle barycentric Hausdorff bounds certifies the actual distance",
                "distance_semantics": "nominal value is an approximation to actual saved/evaluated geometry; the outward interval is authoritative"}
    winner = spec["unique_nearest_separated_role"]
    other = next(role for role in intervals if role != winner)
    need(intervals[winner][1] < intervals[other][0], "actual_unique_nearest_not_certified")
    center_squared = {role: QA.dot(QA.sub(actual_centers[role], actual_centers["target"]), QA.sub(actual_centers[role], actual_centers["target"])) for role in spec["candidate_boxes"]}
    need(center_squared["inner"] < center_squared["outer"], "actual_center_counterexample")
    need(all(actual_bounds["target"][axis][0] <= actual_bounds[role][axis][0] < actual_bounds[role][axis][1] <= actual_bounds["target"][axis][1] for role in ("inner", "penetrating") for axis in range(3)), "actual_AABB_counterexample")
    truth = {"schema": "M1-T1-independent-truth-v2-actual-affine-interval", "spec_sha256": SPEC_SHA,
        "asset_sha256": ASSET_SHA, "snapshot_sha256": snapshot_sha, "target_name": spec["names"]["target"],
        "candidate_names_in_prompt_order": [spec["names"][role] for role in spec["prompt_candidate_order"]],
        "facts": [facts[role] for role in spec["prompt_candidate_order"]], "complete": True,
        "penetrating_names": [spec["names"]["penetrating"]], "nearest_separated_names": [spec["names"][winner]],
        "nearest_separated_distance_m": float(F(*spec["expected_facts_in_assembly_units"][winner]["gap"]) * scale),
        "nearest_separated_distance_interval_m": [endpoint(intervals[winner][0], False), endpoint(intervals[winner][1], True)],
        "strict_rank_margin_lower_bound_m": str(intervals[other][0] - intervals[winner][1]),
        "answer_tolerance_m": spec["answer_tolerance_m"], "product_solver_calls": 0, "model_calls": 0,
        "distance_rule": "evaluate answers against the entire certified actual interval; nominal values are not exact actual distances",
        "preparation_variance": "fresh Blender evaluation reconstructs a common matrix A differing slightly from the requested exact R; raw source unchanged and exact affine/interval proof replaces the failed singleton assertion",
        "first_preparation_failure_preserved": True,
        "method": "Fraction of actual floats; reference boundary equality, actual common affine inverse, exact solid intersection and outward Hausdorff distance intervals"}
    return {"schema": "M1-T1-independent-oracle-v2-actual-affine-interval", "truth": truth,
        "actual_common_affine_matrix": [[str(value) for value in row] for row in actual],
        "actual_common_affine_inverse": [[str(value) for value in row] for row in inv],
        "actual_determinant": str(determinant), "mesh_certificates": certificates,
        "misleading_geometry": {"inner_and_penetrating_contained_by_target_AABB": True,
            "actual_center_distance_squared_m": {role: str(value) for role, value in center_squared.items()},
            "center_prefers_inner_but_surface_prefers_outer": True},
        "statistics": {"objects": len(certificates), "vertices": sum(row["vertices"] for row in certificates.values()),
            "triangles": sum(row["triangles"] for row in certificates.values()),
            "potential_triangle_pairs": certificates["target"]["triangles"] * sum(certificates[role]["triangles"] for role in spec["candidate_boxes"])},
        "scope": "same first asset and raw snapshot; no regeneration, source normalization, product preflight or model feedback"}


def main():
    global QA
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-ns", type=int, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    need(output.parent == HERE, "output_scope")
    spec_raw = (HERE / "SPEC.FROZEN.json").read_bytes()
    need(sha(spec_raw) == SPEC_SHA, "spec_pin")
    freeze = json.loads((HERE / "SOURCE_FREEZE.json").read_bytes())
    old_pin = next(row["sha256"] for row in freeze["files"] if row["path"] == "oracle.py")
    need(sha((HERE / "oracle.py").read_bytes()) == old_pin, "original_oracle_preserved")
    loader = importlib.util.spec_from_file_location("T1_original_independent_QA_oracle", HERE / "oracle.py")
    QA = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(QA)
    QA.DEADLINE = args.deadline_ns
    QA.check()
    need(sha((output / "scene.blend").read_bytes()) == ASSET_SHA, "first_asset_pin")
    snapshot_raw = (output / "SNAPSHOT.json").read_bytes()
    need(sha(snapshot_raw) == SNAPSHOT_SHA, "first_actual_snapshot_pin")
    need(not any(name.startswith(("human_eye_plugin", "human_eye_module1_operators")) for name in sys.modules), "production_import")
    started = time.perf_counter_ns()
    value = certify(json.loads(spec_raw), json.loads(snapshot_raw), sha(snapshot_raw))
    QA.check()
    if args.replay:
        previous = (output / "ORACLE.json").read_bytes()
        need(json.loads(previous) == value and json.loads((output / "TRUTH.json").read_bytes()) == value["truth"], "full_replay_mismatch")
        outputs = {"ORACLE_REPLAY.json": {"schema": "M1-T1-independent-oracle-replay-v2", "passed": True,
            "asset_sha256": ASSET_SHA, "snapshot_sha256": sha(snapshot_raw), "oracle_sha256": sha(previous),
            "truth_sha256": sha((output / "TRUTH.json").read_bytes()), "elapsed_ns": time.perf_counter_ns() - started,
            "oracle_source_sha256": sha(Path(__file__).read_bytes()), "production_calls": 0, "model_calls": 0,
            "scope": "fresh complete replay of the independent QA oracle; not a second mathematically independent method"}}
    else:
        outputs = {"ORACLE.json": value, "TRUTH.json": value["truth"]}
    for name, report in outputs.items():
        QA.check()
        need(sha((output / "scene.blend").read_bytes()) == ASSET_SHA
             and (output / "SNAPSHOT.json").read_bytes() == snapshot_raw, "source_changed_before_publish")
        with (output / name).open("xb") as stream:
            stream.write((json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        QA.check()
    print(json.dumps({"passed": True, "replay": args.replay, "elapsed_s": (time.perf_counter_ns() - started) / 1e9}))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
