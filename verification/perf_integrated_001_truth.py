"""Author-only independent truth for the two PERF-INTEGRATED-001 tasks.

Uses standard-library planar polygon boundaries and extrusion intervals.
Reads actual Blender mesh/matrix snapshots before any model answer. It never
imports the fixture builder, Human Eye, NumPy, or a product scoring function.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path

ANSWER_DISTANCE_TOLERANCE_M = 1e-6
EPSILON = 1e-12
ULP_ONE = math.ulp(1.0)
# All fixed coordinates and matrix entries lie in [-2,2]. A 3D affine
# component has sum-of-absolute-terms <= 16 and fewer than 128 operations,
# including rounded ideal constants and the norm calculation. Decimal's
# correctly rounded 80-digit square root contributes less than 1e-70m.
# The 8192-ulp allowance additionally covers the permitted affine readback
# residual, its Euclidean norm and binary64 subtraction/norm roundoff.
GEOMETRY_ARITHMETIC_BOUND_M = 8192 * ULP_ONE * 16
AFFINE_READBACK_BOUND_M = 1024 * ULP_ONE * 16
# Every reference boundary edge is at least .02m. Use .019 as a strict,
# construction-derived lower bound, independent of the observed deviation.
# For |coordinate|<=2, dot/length errors are bounded by 256 ulps. Clamped
# projection is nonexpansive, and its quotient error is <=1024 ulps/L^2.
# The factor 32768 covers projection, distance norm, caps and minima.
MIN_REFERENCE_EDGE_M = 0.019
ORACLE_ARITHMETIC_BOUND_M = 32768 * ULP_ONE / MIN_REFERENCE_EDGE_M ** 2
ROTATION = [[1 / 3, 2 / 3, -2 / 3, 0],
            [2 / 3, 1 / 3, 2 / 3, 0],
            [2 / 3, -2 / 3, -1 / 3, 0], [0, 0, 0, 1]]
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0],
            [0, 0, 1, 0], [0, 0, 0, 1]]
BOX_TRIANGLES = [[0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7],
                 [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                 [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]


def require(value, reason):
    if not value:
        raise ValueError(reason)


def rectangle(x0, x1, y0, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def extruded(polygon, z0, z1):
    return [[x, y, z] for z in (z0, z1) for x, y in polygon]


def construction(case, state):
    require(case in ("control", "assembly") and state in ("initial", "changed"), "Fixed case/state")
    changed = state == "changed"
    if case == "control":
        outer = rectangle(-0.05, 0.065 if changed else 0.05, -0.05, 0.05)
        probe = rectangle(0.06, 0.08, -0.01, 0.01)
        meshes = {"Object_01": (extruded(outer, -0.05, 0.05), BOX_TRIANGLES, IDENTITY),
                  "Object_02": (extruded(probe, -0.01, 0.01), BOX_TRIANGLES, IDENTITY)}
        witnesses = {"Object_02": [0.0625, 0, 0]} if changed else {}
        return meshes, outer, [], (-0.05, 0.05), {"Object_02": (probe, -0.01, 0.01)}, witnesses

    # Decimal's correctly rounded radical avoids an assumed libm trig bound.
    with localcontext() as context:
        context.prec = 80
        root = Decimal(3).sqrt()
        tangent = float(Decimal(2) - root)
        diagonal = float(root - Decimal(1))
    outer = [[1, tangent], [diagonal, diagonal], [tangent, 1],
             [-tangent, 1], [-diagonal, diagonal], [-1, tangent],
             [-1, -tangent], [-diagonal, -diagonal], [-tangent, -1],
             [tangent, -1], [diagonal, -diagonal], [1, -tangent]]
    inner = [[0.6 * x, 0.6 * y] for x, y in outer]
    if changed:
        inner[0][0] = 0.58
        inner[11][0] = 0.58
    target_points = [[x, y, z] for z in (-0.1, 0.1)
                     for polygon in (outer, inner) for x, y in polygon]
    target_faces = []
    for i in range(12):
        j = (i + 1) % 12
        for face in ([i, j, j + 24, i + 24], [i + 12, i + 36, j + 36, j + 12],
                     [j, i, i + 12, j + 12], [i + 24, j + 24, j + 36, i + 36]):
            target_faces.extend([[face[0], face[1], face[2]], [face[0], face[2], face[3]]])
    a = rectangle(0.55, 0.59, -0.02, 0.02)
    b_local = rectangle(-0.02, 0.02, -0.01, 0.01)
    b = [[-0.605 + 0.6 * x - 0.8 * y, 0.8 * x + 0.6 * y] for x, y in b_local]
    c = rectangle(-0.025, 0.025, 1.04, 1.08)
    b_matrix = [[2.2 / 3, 0.4 / 3, -2 / 3, -0.605 / 3],
                [2 / 3, -1 / 3, 2 / 3, -1.21 / 3],
                [-0.4 / 3, -2.8 / 3, -1 / 3, -1.21 / 3], [0, 0, 0, 1]]
    meshes = {"Object_01": (target_points, target_faces, ROTATION),
              "Object_02": (extruded(a, -0.025, 0.025), BOX_TRIANGLES, ROTATION),
              "Object_03": (extruded(b_local, -0.025, 0.025), BOX_TRIANGLES, b_matrix),
              "Object_04": (extruded(c, -0.025, 0.025), BOX_TRIANGLES, ROTATION)}
    witnesses = {"Object_03": [-0.61, 0, 0]}
    if changed:
        witnesses["Object_02"] = [0.585, 0, 0]
    probes = {"Object_02": (a, -0.025, 0.025), "Object_03": (b, -0.025, 0.025),
              "Object_04": (c, -0.025, 0.025)}
    return meshes, outer, inner, (-0.1, 0.1), probes, witnesses


def edges(polygon):
    return zip(polygon, polygon[1:] + polygon[:1])


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def point_segment_sq(point, a, b):
    delta = [b[0] - a[0], b[1] - a[1]]
    length = delta[0] ** 2 + delta[1] ** 2
    require(length > 0, "Zero-length reference boundary")
    t = max(0, min(1, sum((point[k] - a[k]) * delta[k] for k in range(2)) / length))
    return sum((point[k] - a[k] - t * delta[k]) ** 2 for k in range(2))


def strictly_inside(point, polygon):
    if any(point_segment_sq(point, a, b) <= EPSILON ** 2 for a, b in edges(polygon)):
        return False
    inside = False
    for a, b in edges(polygon):
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                inside = not inside
    return inside


def proper_crossing(a, b, c, d):
    return (cross(a, b, c) * cross(a, b, d) < -EPSILON ** 2
            and cross(c, d, a) * cross(c, d, b) < -EPSILON ** 2)


def material_contains(point, outer, inner):
    if not strictly_inside(point, outer):
        return False
    return not inner or (not strictly_inside(point, inner)
                        and all(point_segment_sq(point, a, b) > EPSILON ** 2
                                for a, b in edges(inner)))


def planar_relation(probe, outer, inner):
    boundaries = [outer] + ([inner] if inner else [])
    overlaps = (any(material_contains(point, outer, inner) for point in probe)
                or any(strictly_inside(point, probe) for polygon in boundaries for point in polygon)
                or any(proper_crossing(a, b, c, d) for a, b in edges(probe)
                       for polygon in boundaries for c, d in edges(polygon)))
    if overlaps:
        return True, 0.0
    squared = min(min(point_segment_sq(a, c, d), point_segment_sq(b, c, d),
                      point_segment_sq(c, a, b), point_segment_sq(d, a, b))
                  for a, b in edges(probe) for polygon in boundaries for c, d in edges(polygon))
    return False, math.sqrt(max(0, squared))


def transformed(points, matrix):
    return [[sum(matrix[axis][k] * point[k] for k in range(3)) + matrix[axis][3]
             for axis in range(3)] for point in points]


def close_rows(actual, expected, reason, tolerance=AFFINE_READBACK_BOUND_M):
    require(len(actual) == len(expected), reason + " row count")
    require(all(len(a) == len(b) and all(type(x) in (int, float) and math.isfinite(x)
                and abs(x - y) <= tolerance for x, y in zip(a, b))
                for a, b in zip(actual, expected)), reason)


def verify_snapshot(case, state, snapshot, expected):
    require(snapshot["schema"] == "perf-integrated-001-mesh-readback-v1"
            and snapshot["case"] == case and snapshot["state"] == state
            and snapshot["unit_scale_m"] == 1, "Snapshot identity/units")
    rows = {row["name"]: row for row in snapshot["objects"]}
    require(len(rows) == len(snapshot["objects"]) and set(rows) == set(expected), "Fixed object set")
    certificates = {}
    for name, (points, faces, matrix) in expected.items():
        actual = rows[name]
        for field, reference in (("vertices_local", points), ("matrix_world", matrix),
                                 ("world_vertices", points)):
            value = actual[field]
            require(type(value) is list and len(value) == len(reference)
                    and all(type(row) is list and len(row) == len(ideal)
                            and all(type(x) in (int, float) and math.isfinite(x)
                                    and abs(x) <= 2 for x in row)
                            for row, ideal in zip(value, reference)),
                    name + " finite fixed dimensions/domain " + field)
        require(actual["matrix_world"][3] == [0, 0, 0, 1], name + " affine matrix row")
        require(actual["faces"] == faces, name + " fixed original triangulation")
        close_rows(actual["world_vertices"], transformed(actual["vertices_local"], actual["matrix_world"]),
                   name + " affine readback")
        counts = Counter((face[i], face[(i + 1) % 3]) for face in actual["faces"] for i in range(3))
        require(all(value == 1 and counts[(b, a)] == 1 for (a, b), value in counts.items()),
                name + " closed oriented edge incidence")
        ideal_world = transformed(points, matrix)
        deviation = max(math.dist(point, ideal) for point, ideal in
                        zip(actual["world_vertices"], ideal_world))
        certificates[name] = dict(observed_max_vertex_error_m=deviation,
            construction_arithmetic_bound_m=GEOMETRY_ARITHMETIC_BOUND_M,
            rho_m=deviation + GEOMETRY_ARITHMETIC_BOUND_M,
            correspondence="same ordered vertices and exact oriented triangle list",
            boundary_bound="barycentric interpolation gives bidirectional boundary Hausdorff bound")
    return rows, certificates


def boundary_margin(point, polygons, z0, z1):
    side = min(math.sqrt(point_segment_sq(point[:2], a, b))
               for polygon in polygons for a, b in edges(polygon))
    return min(side, point[2] - z0, z1 - point[2])


def control_axis_certificate(actual, state):
    boxes = {}
    for name, row in actual.items():
        require(row["matrix_world"] == IDENTITY, "Control actual identity matrix")
        points = row["vertices_local"]
        levels = [sorted(set(point[axis] for point in points)) for axis in range(3)]
        require(all(len(values) == 2 for values in levels)
                and {tuple(point) for point in points} ==
                {(x, y, z) for x in levels[0] for y in levels[1] for z in levels[2]},
                "Control actual Cartesian axis-aligned box")
        boxes[name] = levels
    a, b = boxes["Object_01"], boxes["Object_02"]
    overlap = [min(a[k][1], b[k][1]) - max(a[k][0], b[k][0]) for k in range(3)]
    require(overlap[1] > 0 and overlap[2] > 0, "Control strict transverse overlap")
    gap = b[0][0] - a[0][1]
    if state == "initial":
        require(gap > 0, "Control separated +X planes")
    else:
        require(all(value > 0 for value in overlap), "Control strict actual box overlap")
    return dict(direction="+X" if state == "initial" else None,
                exact_identity_and_cartesian_boxes=True, actual_positive_x_gap_m=max(0, gap),
                actual_x_overlap_m=max(0, -gap), actual_axis_overlaps_m=overlap,
                scope="actual control parallel planes and transverse overlap")


def aabb_overlap(left, right):
    return all(min(p[axis] for p in left) <= max(p[axis] for p in right)
               and min(p[axis] for p in right) <= max(p[axis] for p in left) for axis in range(3))


def truth_for_state(case, state, snapshot):
    meshes, outer, inner, target_z, probes, witnesses = construction(case, state)
    actual, certificates = verify_snapshot(case, state, snapshot, meshes)
    target = "Object_01"
    answers = {}
    for name, (polygon, z0, z1) in probes.items():
        require(all(math.dist(a, b) >= MIN_REFERENCE_EDGE_M
                    for boundary in [outer, polygon] + ([inner] if inner else [])
                    for a, b in edges(boundary)), "Fixed reference boundary conditioning")
        planar_overlap, planar_gap = planar_relation(polygon, outer, inner)
        z_overlap = min(target_z[1], z1) - max(target_z[0], z0)
        penetrating = planar_overlap and z_overlap > EPSILON
        gap = math.hypot(planar_gap, max(0, -z_overlap))
        relation = "penetrating" if penetrating else "separated" if gap > EPSILON else "touching"
        row = dict(relation=relation, minimum_gap_m=None if penetrating else gap,
                   world_aabb_overlap=aabb_overlap(actual[target]["world_vertices"], actual[name]["world_vertices"]))
        error = certificates[target]["rho_m"] + certificates[name]["rho_m"] + ORACLE_ARITHMETIC_BOUND_M
        require(error < ANSWER_DISTANCE_TOLERANCE_M, name + " exhausted answer error budget")
        row["distance_error_bound_m"] = error
        row["oracle_arithmetic_bound_m"] = ORACLE_ARITHMETIC_BOUND_M
        if not penetrating:
            require(gap > error, name + " separation interval includes zero")
            row["distance_interval_m"] = [gap - error, gap + error]
        if penetrating:
            point = witnesses[name]
            require(material_contains(point[:2], outer, inner) and strictly_inside(point[:2], polygon)
                    and max(target_z[0], z0) < point[2] < min(target_z[1], z1), "Strict shared interior witness")
            row["shared_interior_point_assembly_m"] = point
            row["shared_interior_point_world_m"] = transformed([point], IDENTITY if case == "control" else ROTATION)[0]
            target_margin = boundary_margin(point, [outer] + ([inner] if inner else []), *target_z)
            probe_margin = boundary_margin(point, [polygon], z0, z1)
            require(target_margin > certificates[target]["rho_m"] + ORACLE_ARITHMETIC_BOUND_M
                    and probe_margin > certificates[name]["rho_m"] + ORACLE_ARITHMETIC_BOUND_M,
                    name + " witness crosses a possible perturbed boundary")
            row["shared_interior_margins_m"] = dict(target=target_margin, probe=probe_margin)
            row["certified_witness"] = True
            row["witness_proof"] = "same-topology vertex homotopy stays farther from witness than boundary displacement"
        answers[name] = row
    expected = ({"Object_02": ("penetrating", None) if state == "changed" else ("separated", 0.01)}
                if case == "control" else {
                    "Object_02": ("penetrating", None) if state == "changed" else ("separated", 0.01),
                    "Object_03": ("penetrating", None), "Object_04": ("separated", 0.04)})
    for name, (relation, gap) in expected.items():
        require(answers[name]["relation"] == relation, name + " independent relation disagrees with frozen construction")
        if gap is not None:
            require(abs(answers[name]["minimum_gap_m"] - gap) < EPSILON, name + " independent gap")
    separated = [name for name, row in answers.items() if row["relation"] == "separated"]
    nearest = min(separated, key=lambda name: answers[name]["minimum_gap_m"]) if separated else None
    if nearest:
        require(all(answers[nearest]["distance_interval_m"][1] < answers[name]["distance_interval_m"][0]
                    for name in separated if name != nearest), "Nearest separation intervals overlap")
    if case == "assembly":
        require(answers["Object_04"]["world_aabb_overlap"] and
                (state == "changed" or answers["Object_02"]["world_aabb_overlap"]), "Frozen AABB traps")
    return dict(target=target, probes=answers, nearest_separated_probe=nearest,
                mesh_inputs_verified=True, object_error_certificates=certificates,
                direction_certificate=control_axis_certificate(actual, state) if case == "control" else None,
                answer_rule="abs(answer-d0)+distance_error_bound_m <= 1e-6",
                penetration_metric="strict shared interior, global minimum escape not requested")


def minimal_checks():
    meshes, *_ = construction("control", "initial")
    rows = [dict(name=name, vertices_local=points, matrix_world=matrix,
                 world_vertices=transformed(points, matrix), faces=faces)
            for name, (points, faces, matrix) in meshes.items()]
    snapshot = dict(schema="perf-integrated-001-mesh-readback-v1", case="control", state="initial",
                    unit_scale_m=1, objects=rows)
    truth_for_state("control", "initial", snapshot)
    excessive = copy.deepcopy(snapshot)
    probe = excessive["objects"][1]
    for point in probe["vertices_local"]:
        point[0] += .002
    probe["world_vertices"] = transformed(probe["vertices_local"], probe["matrix_world"])
    broken = copy.deepcopy(snapshot)
    broken["objects"][0]["vertices_local"].pop()
    broken["objects"][0]["world_vertices"].pop()
    checks = (("excessive_geometry_error", excessive, "exhausted answer error budget"),
              ("broken_correspondence", broken, "finite fixed dimensions/domain"))
    for name, value, expected_reason in checks:
        try:
            truth_for_state("control", "initial", value)
        except ValueError as exc:
            require(expected_reason in str(exc), "Unexpected rejection path " + name)
            continue
        raise ValueError("Required certificate rejection missing " + name)
    return dict(positive=1, excessive_geometry_error_rejected=1, broken_correspondence_rejected=1,
                product_calls=0, model_answers=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("control", "assembly"))
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        result = minimal_checks()
    else:
        require(args.case is not None and args.snapshots is not None, "Case and snapshots required")
        source = json.loads(args.snapshots.read_bytes())
        initial = truth_for_state(args.case, "initial", source["initial"])
        changed = truth_for_state(args.case, "changed", source["changed"])
        result = dict(schema="perf-integrated-001-independent-truth-v2", case=args.case,
                  states=dict(initial=initial, unchanged=initial, changed=changed),
                  geometry_arithmetic_bound_m=GEOMETRY_ARITHMETIC_BOUND_M,
                  oracle_arithmetic_bound_m=ORACLE_ARITHMETIC_BOUND_M,
                  answer_distance_tolerance_m=ANSWER_DISTANCE_TOLERANCE_M,
                  input_snapshot_sha256=hashlib.sha256(args.snapshots.read_bytes()).hexdigest(),
                  truth_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  product_solver_calls=0, model_answers=0,
                  method="corresponding-world vertex displacement certificate, fixed planar distances and all-boundary interior margins")
    allowed = (Path(__file__).resolve().parents[1] / "verification/fixes/perf_integrated_001/run_02").resolve()
    require(args.output.resolve().is_relative_to(allowed), "Truth output outside owned batch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
