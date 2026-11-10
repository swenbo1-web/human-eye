"""Independent exact-rational certification of T1's actual saved mesh surfaces.

No product import, BVH, surface-distance library or production solver is used.
The mesh is certified against an analytic union of rectangular solids, rather
than compared with the generator's own list of vertices or triangles.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC_SHA = "b54110358c37dc7be1f47a201ef14b12156923f53729a723874ab902645a4ce2"
DEADLINE = 0


def need(condition, reason):
    if not condition:
        raise ValueError("T1_oracle_" + reason)


def check():
    need(time.perf_counter_ns() < DEADLINE, "original_deadline")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rational(value):
    need(type(value) in (int, float), "coordinate_type")
    return F(value)


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def twice_area(polygon):
    return sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(polygon, polygon[1:] + polygon[:1])) if len(polygon) >= 3 else F(0)


def clip(polygon, evaluate):
    if not polygon:
        return []
    result = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        fa, fb = evaluate(a), evaluate(b)
        if fa >= 0:
            result.append(a)
        if (fa < 0 <= fb) or (fb < 0 <= fa):
            parameter = fa / (fa - fb)
            result.append(tuple(a[axis] + parameter * (b[axis] - a[axis]) for axis in range(2)))
    return result


def rectangle_clip(polygon, lower, upper):
    for axis in range(2):
        polygon = clip(polygon, lambda point, axis=axis: point[axis] - lower[axis])
        polygon = clip(polygon, lambda point, axis=axis: upper[axis] - point[axis])
    return polygon


def triangle_intersection_area(left, right):
    sign = 1 if twice_area(right) > 0 else -1
    polygon = left
    for a, b in zip(right, right[1:] + right[:1]):
        polygon = clip(polygon, lambda point, a=a, b=b: sign * ((b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])))
    return abs(twice_area(polygon)) / 2


def rectangle_difference(lower, upper, cut_lower, cut_upper):
    lo = [max(lower[axis], cut_lower[axis]) for axis in range(2)]
    hi = [min(upper[axis], cut_upper[axis]) for axis in range(2)]
    if any(lo[axis] >= hi[axis] for axis in range(2)):
        return [(lower, upper)]
    pieces = [((lower[0], lower[1]), (lo[0], upper[1])),
              ((hi[0], lower[1]), (upper[0], upper[1])),
              ((lo[0], lower[1]), (hi[0], lo[1])),
              ((lo[0], hi[1]), (hi[0], upper[1]))]
    return [(a, b) for a, b in pieces if all(a[axis] < b[axis] for axis in range(2))]


def box_faces(box):
    lower, upper = [tuple(map(rational, box[key])) for key in ("lower", "upper")]
    result = []
    for axis in range(3):
        other = [index for index in range(3) if index != axis]
        for sign, plane in ((-1, lower[axis]), (1, upper[axis])):
            result.append((axis, plane, sign, tuple(lower[index] for index in other), tuple(upper[index] for index in other)))
    return result


def union_boundary(boxes):
    # Registered rectangular cells have disjoint interiors. Cancel shared
    # interfaces by exact rectangle subtraction, independently of cap topology.
    for index, left in enumerate(boxes):
        for right in boxes[index + 1:]:
            need(any(max(left["lower"][axis], right["lower"][axis]) >= min(left["upper"][axis], right["upper"][axis]) for axis in range(3)), "partition_interiors_overlap")
    faces = [face for box in boxes for face in box_faces(box)]
    result = []
    for axis, plane, sign, lower, upper in faces:
        pieces = [(lower, upper)]
        for other_axis, other_plane, other_sign, cut_lower, cut_upper in faces:
            if other_axis == axis and other_plane == plane and other_sign == -sign:
                pieces = [piece for a, b in pieces for piece in rectangle_difference(a, b, cut_lower, cut_upper)]
        result.extend((axis, plane, sign, a, b) for a, b in pieces)
    return result


def certify_mesh(row, role, spec):
    check()
    need(row["parent"] is None and not row["modifiers"] and not row["constraints"] and row["animation_data"] is False, "unsupported_dependencies")
    matrix = [tuple(map(rational, line)) for line in row["matrix_world"]]
    rotation = [tuple(map(rational, line)) for line in spec["common_rigid_rotation_rows"]]
    scale = F(*spec["coordinate_scale_m"])
    translation = tuple(rational(value) * scale for value in spec["common_translation_assembly_units"])
    need(matrix[3] == (0, 0, 0, 1), "affine_matrix")
    need([line[:3] for line in matrix[:3]] == rotation, "exact_rigid_rotation")
    need(dot(rotation[0], cross(rotation[1], rotation[2])) == 1, "orientation_preserving_rotation")
    need(all(dot(rotation[a], rotation[b]) == int(a == b) for a in range(3) for b in range(3)), "orthogonal_rotation")
    local = [tuple(map(rational, vertex)) for vertex in row["vertices_local"]]
    world = [tuple(dot(matrix[axis][:3], vertex) + matrix[axis][3] for axis in range(3)) for vertex in local]
    vertices = [tuple(sum(rotation[axis][column] * (vertex[axis] - translation[axis]) for axis in range(3)) / scale for column in range(3)) for vertex in world]
    need(len(set(vertices)) == len(vertices), "duplicate_positions")
    faces = row["faces"]
    expected = spec["expected_mesh_counts"][role]
    need(len(vertices) == expected["vertices"] and len(faces) == expected["triangles"], "pre_registered_counts")
    boxes = spec["target_solid_rectangular_partition"] if role == "target" else [spec["candidate_boxes"][role]]
    patches = union_boundary(boxes)
    totals = [F(0)] * len(patches)
    edges = Counter()
    directed = Counter()
    plane_triangles = defaultdict(list)
    details = []
    volume6 = F(0)
    for index, face in enumerate(faces):
        check()
        need(type(face) is list and len(face) == len(set(face)) == 3 and all(type(value) is int and 0 <= value < len(vertices) for value in face), "triangle_indices")
        a, b, c = [vertices[vertex] for vertex in face]
        normal = cross(sub(b, a), sub(c, a))
        axes = [axis for axis in range(3) if normal[axis]]
        need(len(axes) == 1, "not_axis_plane_or_degenerate")
        axis = axes[0]
        plane = a[axis]
        sign = 1 if normal[axis] > 0 else -1
        other = [value for value in range(3) if value != axis]
        triangle = [tuple(vertex[value] for value in other) for vertex in (a, b, c)]
        area = abs(twice_area(triangle)) / 2
        contributions = []
        for patch_index, (patch_axis, patch_plane, patch_sign, lower, upper) in enumerate(patches):
            if (axis, plane, sign) == (patch_axis, patch_plane, patch_sign):
                overlap = abs(twice_area(rectangle_clip(triangle, lower, upper))) / 2
                if overlap:
                    totals[patch_index] += overlap
                    contributions.append((patch_index, overlap))
        need(sum(value for _, value in contributions) == area, "triangle_not_wholly_on_oriented_analytic_boundary")
        plane_triangles[(axis, plane, sign)].append(triangle)
        for first, second in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((first, second)))] += 1
            directed[(first, second)] += 1
        volume6 += dot(a, cross(b, c))
        details.append({"triangle": index, "axis": axis, "plane": str(plane), "normal_sign": sign,
                        "area_assembly_units2": str(area), "patch_areas": [[patch, str(value)] for patch, value in contributions]})
    need(all(count == 2 for count in edges.values()) and all(directed[(a, b)] == directed[(b, a)] == 1 for a, b in edges), "closed_oriented_manifold_edges")
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited, stack = set(), [0]
    while stack:
        vertex = stack.pop()
        if vertex not in visited:
            visited.add(vertex)
            stack.extend(adjacency[vertex] - visited)
    need(len(visited) == len(vertices) and len(vertices) - len(edges) + len(faces) == 2, "connected_genus_zero_shell")
    overlap_checks = 0
    for triangles in plane_triangles.values():
        for index, left in enumerate(triangles):
            for right in triangles[index + 1:]:
                check()
                if any(max(min(point[axis] for point in left), min(point[axis] for point in right)) >= min(max(point[axis] for point in left), max(point[axis] for point in right)) for axis in range(2)):
                    continue
                overlap_checks += 1
                need(triangle_intersection_area(left, right) == 0, "overlapping_boundary_triangles")
    patch_records = []
    for index, (axis, plane, sign, lower, upper) in enumerate(patches):
        area = (upper[0] - lower[0]) * (upper[1] - lower[1])
        need(totals[index] == area, "analytic_boundary_patch_not_covered_exactly_once")
        patch_records.append({"axis": axis, "plane": str(plane), "normal_sign": sign,
            "lower": list(map(str, lower)), "upper": list(map(str, upper)), "area": str(area), "covered_area": str(totals[index])})
    volume = sum(F(box["upper"][0] - box["lower"][0]) * (box["upper"][1] - box["lower"][1]) * (box["upper"][2] - box["lower"][2]) for box in boxes)
    need(volume6 == 6 * volume, "oriented_volume")
    bounds = [[min(vertex[axis] for vertex in vertices), max(vertex[axis] for vertex in vertices)] for axis in range(3)]
    return {"name": row["name"], "vertices": len(vertices), "triangles": len(faces), "edges": len(edges),
        "euler": 2, "connected": True, "oriented_closed_shell": True,
        "boundary_equality_proved": True, "volume_assembly_units3": str(volume),
        "surface_area_assembly_units2": str(sum(totals)), "coplanar_overlap_checks": overlap_checks,
        "patches": patch_records, "triangle_boundary_coverage": details,
        "bounds_assembly_units": [[str(a), str(b)] for a, b in bounds]}, bounds


def inside_strict(point, box):
    return all(F(box["lower"][axis]) < point[axis] < F(box["upper"][axis]) for axis in range(3))


def margin(point, box):
    return min(min(point[axis] - box["lower"][axis], box["upper"][axis] - point[axis]) for axis in range(3))


def distance_squared_boxes(left, right):
    gaps = [max(F(0), F(left["lower"][axis]) - right["upper"][axis], F(right["lower"][axis]) - left["upper"][axis]) for axis in range(3)]
    return dot(gaps, gaps)


def point_on_boundary(point, patches):
    for axis, plane, _, lower, upper in patches:
        other = [index for index in range(3) if index != axis]
        if point[axis] == plane and all(lower[index] <= point[value] <= upper[index] for index, value in enumerate(other)):
            return True
    return False


def prove(spec, snapshot, snapshot_sha, asset_sha):
    need(snapshot["asset_sha256"] == asset_sha and snapshot["unit_scale_m"] == spec["unit_scale_m"] == 1
         and snapshot["frame"] == 1 and snapshot["read_only"] is True and snapshot["save_calls"] == snapshot["setter_calls"] == 0, "actual_source_contract")
    by_name = {row["name"]: row for row in snapshot["objects"]}
    need(len(snapshot["objects"]) == len(by_name) == 4 and set(by_name) == set(spec["names"].values()), "complete_object_coverage")
    certificates, bounds = {}, {}
    for role, name in spec["names"].items():
        certificates[role], bounds[role] = certify_mesh(by_name[name], role, spec)
    scale = F(*spec["coordinate_scale_m"])
    target_boxes = spec["target_solid_rectangular_partition"]
    target_patches = union_boundary(target_boxes)
    facts = {}
    for role, candidate in spec["candidate_boxes"].items():
        check()
        expected = spec["expected_facts_in_assembly_units"][role]
        if role == "penetrating":
            witness = tuple(map(rational, expected["strict_shared_interior_witness"]))
            intersections = [box for box in target_boxes if inside_strict(witness, box)]
            need(inside_strict(witness, candidate) and intersections, "strict_shared_interior_witness")
            strict_margin = min(margin(witness, candidate), max(margin(witness, box) for box in intersections))
            need(strict_margin >= F(*expected["strict_margin_at_least"]), "strict_shared_interior_margin")
            target_only = tuple(map(rational, expected["target_only_witness"]))
            candidate_only = tuple(map(rational, expected["candidate_only_witness"]))
            need(any(inside_strict(target_only, box) for box in target_boxes) and not inside_strict(target_only, candidate), "target_only_witness")
            need(inside_strict(candidate_only, candidate) and not any(inside_strict(candidate_only, box) for box in target_boxes), "candidate_only_witness")
            facts[role] = {"name": spec["names"][role], "relation": "penetrating", "separation_gap_m": None,
                "strict_common_interior_witness_assembly": list(map(str, witness)), "strict_margin_m": str(strict_margin * scale),
                "not_a_penetration_depth": True, "proof": "positive common-interior margin and points belonging only to each solid"}
        else:
            lower_squares = [distance_squared_boxes(box, candidate) for box in target_boxes]
            gap = F(*expected["gap"])
            need(min(lower_squares) == gap * gap > 0, "strict_separation_lower_bound")
            a = tuple(map(rational, expected["distance_witness_target"]))
            b = tuple(map(rational, expected["distance_witness_candidate"]))
            need(point_on_boundary(a, target_patches) and point_on_boundary(b, union_boundary([candidate])), "attained_surface_witness")
            need(dot(sub(a, b), sub(a, b)) == gap * gap, "attained_distance_equals_lower_bound")
            distance = gap * scale
            facts[role] = {"name": spec["names"][role], "relation": "separated", "separation_gap_m": str(distance),
                "distance_interval_m": [float(distance), float(distance)], "distance_mm": float(distance * 1000),
                "target_partition_distance_squared_assembly_units": list(map(str, lower_squares)),
                "attaining_target_witness_assembly": list(map(str, a)), "attaining_candidate_witness_assembly": list(map(str, b)),
                "proof": "every point pair is bounded by partition box distances, attained by certified actual boundary points"}
    separated = sorted((F(row["separation_gap_m"]), role) for role, row in facts.items() if row["relation"] == "separated")
    need(separated[0][0] < separated[1][0] and separated[0][1] == spec["unique_nearest_separated_role"], "unique_nearest_set")
    centers = {role: tuple((a + b) / 2 for a, b in value) for role, value in bounds.items()}
    centers_squared = {role: dot(sub(center, centers["target"]), sub(center, centers["target"])) for role, center in centers.items() if role != "target"}
    need(centers_squared["inner"] < centers_squared["outer"], "center_distance_does_not_mislead_as_registered")
    need(all(bounds["target"][axis][0] <= bounds[role][axis][0] < bounds[role][axis][1] <= bounds["target"][axis][1]
             for role in ("inner", "penetrating") for axis in range(3)), "AABB_false_positive_construction")
    truth = {"schema": "M1-T1-independent-truth-v1", "spec_sha256": SPEC_SHA,
        "snapshot_sha256": snapshot_sha, "asset_sha256": asset_sha,
        "target_name": spec["names"]["target"],
        "candidate_names_in_prompt_order": [spec["names"][role] for role in spec["prompt_candidate_order"]],
        "facts": [facts[role] for role in spec["prompt_candidate_order"]],
        "complete": True, "penetrating_names": [spec["names"]["penetrating"]],
        "nearest_separated_names": [spec["names"][separated[0][1]]],
        "nearest_separated_distance_m": float(separated[0][0]),
        "strict_rank_margin_m": str(separated[1][0] - separated[0][0]),
        "answer_tolerance_m": spec["answer_tolerance_m"], "product_solver_calls": 0, "model_calls": 0,
        "method": "Fraction from actual binary floats; oriented manifold and exact nonoverlapping boundary-patch coverage; analytic solid partition lower bounds and attained witnesses",
        "scope": "one frozen static saved frame, explicit target and three candidates; not all-scene diagnosis or damage"}
    oracle = {"schema": "M1-T1-independent-oracle-v1", "truth": truth,
        "mesh_certificates": certificates,
        "misleading_geometry": {"inner_and_penetrating_contained_by_target_AABB": True,
            "center_distance_squared_assembly_units": {role: str(value) for role, value in centers_squared.items()},
            "center_prefers_inner_but_surface_prefers_outer": True},
        "statistics": {"objects": 4, "vertices": sum(row["vertices"] for row in certificates.values()),
            "triangles": sum(row["triangles"] for row in certificates.values()),
            "potential_triangle_pairs": certificates["target"]["triangles"] * sum(certificates[role]["triangles"] for role in facts)},
        "arithmetic": "exact rational; all actual coordinates and transforms are dyadic, so certified intervals are singletons"}
    return oracle


def main():
    global DEADLINE
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-ns", type=int, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    DEADLINE = args.deadline_ns
    check()
    output = args.output.resolve()
    need(output.parent == HERE, "owned_output")
    spec_raw = (HERE / "SPEC.FROZEN.json").read_bytes()
    need(sha(spec_raw) == SPEC_SHA, "spec_pin")
    snapshot_raw = (output / "SNAPSHOT.json").read_bytes()
    snapshot = json.loads(snapshot_raw)
    asset = output / "scene.blend"
    asset_sha = sha(asset.read_bytes())
    need(not any(name.startswith(("human_eye_plugin", "human_eye_module1_operators")) for name in sys.modules), "production_import")
    started = time.perf_counter_ns()
    oracle = prove(json.loads(spec_raw), snapshot, sha(snapshot_raw), asset_sha)
    check()
    if args.replay:
        previous_raw = (output / "ORACLE.json").read_bytes()
        need(json.loads(previous_raw) == oracle and json.loads((output / "TRUTH.json").read_bytes()) == oracle["truth"], "replay_not_equal")
        outputs = {"ORACLE_REPLAY.json": {"schema": "M1-T1-independent-oracle-replay-v1", "passed": True,
            "oracle_sha256": sha(previous_raw), "truth_sha256": sha((output / "TRUTH.json").read_bytes()),
            "snapshot_sha256": sha(snapshot_raw), "asset_sha256": asset_sha,
            "oracle_script_sha256": sha(Path(__file__).read_bytes()), "elapsed_ns": time.perf_counter_ns() - started,
            "recomputed_all_boundary_coverage_and_geometry_facts": True, "production_calls": 0,
            "model_calls": 0, "scope": "fresh replay of the independent QA algorithm; not a second mathematically independent oracle"}}
    else:
        outputs = {"ORACLE.json": oracle, "TRUTH.json": oracle["truth"]}
    for name, value in outputs.items():
        check()
        need(sha(asset.read_bytes()) == asset_sha and (output / "SNAPSHOT.json").read_bytes() == snapshot_raw
             and sha((HERE / "SPEC.FROZEN.json").read_bytes()) == SPEC_SHA, "source_changed_before_publication")
        with (output / name).open("xb") as stream:
            stream.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        check()
    print(json.dumps({"passed": True, "replay": args.replay, "elapsed_ns": time.perf_counter_ns() - started,
                      "nearest_separated_names": oracle["truth"]["nearest_separated_names"]}))


if __name__ == "__main__":
    main()
