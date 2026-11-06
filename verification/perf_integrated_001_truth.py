"""Author-only independent truth for the two PERF-INTEGRATED-001 tasks.

Uses standard-library planar polygon boundaries and extrusion intervals.
Reads actual Blender mesh/matrix snapshots before any model answer. It never
imports the fixture builder, Human Eye, NumPy, or a product scoring function.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

COORDINATE_TOLERANCE_M = 1e-7
ANSWER_DISTANCE_TOLERANCE_M = 1e-6
EPSILON = 1e-12
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

    # An independent trigonometric construction of the same dodecagons.
    radius = 1 / math.cos(math.pi / 12)
    outer = [[radius * math.cos((2 * i + 1) * math.pi / 12),
              radius * math.sin((2 * i + 1) * math.pi / 12)] for i in range(12)]
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


def close_rows(actual, expected, reason, tolerance=COORDINATE_TOLERANCE_M):
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
    for name, (points, faces, matrix) in expected.items():
        actual = rows[name]
        close_rows(actual["vertices_local"], points, name + " local vertices")
        close_rows(actual["matrix_world"], matrix, name + " matrix")
        require(actual["faces"] == faces, name + " fixed original triangulation")
        close_rows(actual["world_vertices"], transformed(points, matrix), name + " world vertices")
        close_rows(actual["world_vertices"], transformed(actual["vertices_local"], actual["matrix_world"]),
                   name + " affine readback", tolerance=1e-12)
        counts = Counter((face[i], face[(i + 1) % 3]) for face in actual["faces"] for i in range(3))
        require(all(value == 1 and counts[(b, a)] == 1 for (a, b), value in counts.items()),
                name + " closed oriented edge incidence")
    return rows


def aabb_overlap(left, right):
    return all(min(p[axis] for p in left) <= max(p[axis] for p in right)
               and min(p[axis] for p in right) <= max(p[axis] for p in left) for axis in range(3))


def truth_for_state(case, state, snapshot):
    meshes, outer, inner, target_z, probes, witnesses = construction(case, state)
    actual = verify_snapshot(case, state, snapshot, meshes)
    target = "Object_01"
    answers = {}
    for name, (polygon, z0, z1) in probes.items():
        planar_overlap, planar_gap = planar_relation(polygon, outer, inner)
        z_overlap = min(target_z[1], z1) - max(target_z[0], z0)
        penetrating = planar_overlap and z_overlap > EPSILON
        gap = math.hypot(planar_gap, max(0, -z_overlap))
        relation = "penetrating" if penetrating else "separated" if gap > EPSILON else "touching"
        row = dict(relation=relation, minimum_gap_m=None if penetrating else gap,
                   world_aabb_overlap=aabb_overlap(actual[target]["world_vertices"], actual[name]["world_vertices"]))
        if penetrating:
            point = witnesses[name]
            require(material_contains(point[:2], outer, inner) and strictly_inside(point[:2], polygon)
                    and max(target_z[0], z0) < point[2] < min(target_z[1], z1), "Strict shared interior witness")
            row["shared_interior_point_assembly_m"] = point
            row["shared_interior_point_world_m"] = transformed([point], IDENTITY if case == "control" else ROTATION)[0]
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
    if case == "assembly":
        require(answers["Object_04"]["world_aabb_overlap"] and
                (state == "changed" or answers["Object_02"]["world_aabb_overlap"]), "Frozen AABB traps")
    return dict(target=target, probes=answers, nearest_separated_probe=nearest,
                mesh_inputs_verified=True, penetration_metric="strict shared interior, global minimum escape not requested")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("control", "assembly"))
    parser.add_argument("--snapshots", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = json.loads(args.snapshots.read_bytes())
    initial = truth_for_state(args.case, "initial", source["initial"])
    changed = truth_for_state(args.case, "changed", source["changed"])
    result = dict(schema="perf-integrated-001-independent-truth-v1", case=args.case,
                  states=dict(initial=initial, unchanged=initial, changed=changed),
                  coordinate_tolerance_m=COORDINATE_TOLERANCE_M,
                  answer_distance_tolerance_m=ANSWER_DISTANCE_TOLERANCE_M,
                  input_snapshot_sha256=hashlib.sha256(args.snapshots.read_bytes()).hexdigest(),
                  truth_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  product_solver_calls=0, model_answers=0,
                  method="independent planar boundary predicates/distance plus extrusion intervals and strict interior witnesses")
    allowed = (Path(__file__).resolve().parents[1] / "verification/fixes/perf_integrated_001").resolve()
    require(args.output.resolve().is_relative_to(allowed), "Truth output outside owned batch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
