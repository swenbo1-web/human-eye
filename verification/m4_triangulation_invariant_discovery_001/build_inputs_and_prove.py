"""Construct fixed subdivisions and prove their surfaces using rational cells.

This program imports no discovery, coverage, rendering, model or product code.
The verifier recovers grid coordinates from the actual emitted mesh and checks
each cell, oriented edge incidence and its exact filled area independently.
"""
from collections import defaultdict
import argparse
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "verification/m4_active_coverage_003"
ORACLE = ROOT / "verification/m4_active_coverage_001/oracle"
ROTATION = ((Fraction(1), Fraction(0), Fraction(0)),
            (Fraction(0), Fraction(3, 5), Fraction(-4, 5)),
            (Fraction(0), Fraction(4, 5), Fraction(3, 5)))
HOLE_CELL = (1, 1)
SOURCE_SHA = {}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode("utf-8")


def fingerprint(value):
    raw = json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_source(path):
    raw = path.read_bytes()
    SOURCE_SHA[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw), raw


def save_new(path, value):
    raw = encoded(value)
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def vector(values):
    return tuple(Fraction(value) for value in values)


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def scale(a, multiplier):
    return tuple(value * multiplier for value in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def canonical_cycle(points):
    first = min(range(len(points)), key=lambda index: points[index])
    return tuple(points[first:] + points[:first])


def canonical_triangle(points):
    return min(tuple(points[index:] + points[:index]) for index in range(3))


def rotate(point):
    return tuple(dot(row, point) for row in ROTATION)


def make_grid(quad, segments, alternating, permuted, removed_cell=None):
    q0, q1, _, q3 = quad
    u, v = subtract(q1, q0), subtract(q3, q0)
    vertices = [add(q0, add(scale(u, Fraction(i, segments)), scale(v, Fraction(j, segments))))
                for j in range(segments + 1) for i in range(segments + 1)]
    faces = []
    for j in range(segments):
        for i in range(segments):
            if removed_cell == (i, j):
                continue
            a = j * (segments + 1) + i
            b, c = a + 1, a + segments + 1
            d = c + 1
            if alternating and (i + j) % 2:
                faces.extend(((a, b, c), (b, d, c)))
            else:
                faces.extend(((a, b, d), (a, d, c)))
    if permuted:
        new_to_old = list(reversed(range(len(vertices))))
        old_to_new = {old: new for new, old in enumerate(new_to_old)}
        vertices = [vertices[index] for index in new_to_old]
        order = list(range(1, len(faces), 2)) + list(range(0, len(faces), 2))
        remapped = []
        for position, index in enumerate(order):
            face = tuple(old_to_new[value] for value in faces[index])
            shift = position % 3
            remapped.append(face[shift:] + face[:shift])
        faces = remapped
    return {"vertices": [[str(value) for value in point] for point in vertices],
            "triangles": [list(face) for face in faces]}


def expected_boundary(segments, removed_cell):
    edges = set()
    for step in range(segments):
        edges.update((((step, 0), (step + 1, 0)), ((segments, step), (segments, step + 1)),
                      ((step + 1, segments), (step, segments)), ((0, step + 1), (0, step))))
    if removed_cell is not None:
        i, j = removed_cell
        a, b, c, d = (i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)
        edges.update(((b, a), (d, b), (c, d), (a, c)))
    return edges


def prove_grid(source, quad, segments, alternating, removed_cell=None):
    """Certify an emitted mesh from its physical coordinates and cell support."""
    q0, q1, q2, q3 = quad
    u, v = subtract(q1, q0), subtract(q3, q0)
    normal = cross(u, v)
    assert dot(u, u) > 0 and dot(v, v) > 0 and dot(u, v) == 0
    assert q2 == add(q0, add(u, v)) and dot(normal, normal) > 0
    squared_area = dot(normal, normal)
    numerator, denominator = math.isqrt(squared_area.numerator), math.isqrt(squared_area.denominator)
    assert numerator * numerator == squared_area.numerator and denominator * denominator == squared_area.denominator
    physical_area = Fraction(numerator, denominator)
    vertices = tuple(vector(point) for point in source["vertices"])
    assert len(vertices) == (segments + 1) ** 2 and len(set(vertices)) == len(vertices)
    labels = []
    observed_values = list(u) + list(v) + list(normal)
    for point in vertices:
        relative = subtract(point, q0)
        assert dot(relative, normal) == 0
        alpha, beta = dot(relative, u) / dot(u, u), dot(relative, v) / dot(v, v)
        assert point == add(q0, add(scale(u, alpha), scale(v, beta)))
        i, j = alpha * segments, beta * segments
        assert i.denominator == j.denominator == 1
        assert 0 <= i <= segments and 0 <= j <= segments
        labels.append((int(i), int(j)))
        observed_values.extend(point + (alpha, beta))
    assert set(labels) == {(i, j) for i in range(segments + 1) for j in range(segments + 1)}
    cells = defaultdict(list)
    edge_incidence = defaultdict(list)
    referenced = set()
    signed_parameter_area = Fraction(0)
    faces = source["triangles"]
    expected_cells = {(i, j) for i in range(segments) for j in range(segments)}
    if removed_cell is not None:
        assert 0 < removed_cell[0] < segments - 1 and 0 < removed_cell[1] < segments - 1
        expected_cells.remove(removed_cell)
    assert len(faces) == 2 * len(expected_cells)
    for face in faces:
        assert len(face) == len(set(face)) == 3
        assert all(type(index) is int and 0 <= index < len(vertices) for index in face)
        referenced.update(face)
        points = [vertices[index] for index in face]
        triangle_normal = cross(subtract(points[1], points[0]), subtract(points[2], points[0]))
        assert triangle_normal == scale(normal, Fraction(1, segments ** 2))
        coordinates = [labels[index] for index in face]
        twice_area = Fraction((coordinates[1][0] - coordinates[0][0]) * (coordinates[2][1] - coordinates[0][1])
                              - (coordinates[1][1] - coordinates[0][1]) * (coordinates[2][0] - coordinates[0][0]), segments ** 2)
        assert twice_area == Fraction(1, segments ** 2)
        signed_parameter_area += twice_area / 2
        cell = (min(point[0] for point in coordinates), min(point[1] for point in coordinates))
        assert max(point[0] for point in coordinates) - cell[0] == 1
        assert max(point[1] for point in coordinates) - cell[1] == 1
        cells[cell].append(canonical_triangle(coordinates))
        for a, b in zip(coordinates, coordinates[1:] + coordinates[:1]):
            edge_incidence[tuple(sorted((a, b)))].append((a, b))
    assert referenced == set(range(len(vertices))) and set(cells) == expected_cells
    certificates = []
    for i, j in sorted(expected_cells):
        a, b, c, d = (i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)
        pair = ((a, b, c), (b, d, c)) if alternating and (i + j) % 2 else ((a, b, d), (a, d, c))
        expected_pair = sorted(canonical_triangle(list(face)) for face in pair)
        assert sorted(cells[(i, j)]) == expected_pair
        certificates.append({"cell": [i, j], "triangles": expected_pair,
                             "parameter_area": str(Fraction(1, segments ** 2))})
    boundary = set()
    for directed in edge_incidence.values():
        assert len(directed) in (1, 2)
        if len(directed) == 2:
            assert directed[0] == tuple(reversed(directed[1]))
        else:
            boundary.add(directed[0])
    assert boundary == expected_boundary(segments, removed_cell)
    expected_area = Fraction(len(expected_cells), segments ** 2)
    assert signed_parameter_area == expected_area
    euler = len(vertices) - len(edge_incidence) + len(faces)
    assert euler == (0 if removed_cell is not None else 1)
    observed_values.append(signed_parameter_area)
    return {"passed": True, "vertices_verified": len(vertices), "triangles_verified": len(faces),
            "cells_verified": len(expected_cells), "each_triangle_parameter_area": str(Fraction(1, 2 * segments ** 2)),
            "each_cell_parameter_area": str(Fraction(1, segments ** 2)),
            "original_physical_area_m2": str(physical_area),
            "each_triangle_physical_area_m2": str(physical_area / (2 * segments ** 2)),
            "each_cell_physical_area_m2": str(physical_area / segments ** 2),
            "filled_physical_area_m2": str(physical_area * expected_area),
            "filled_parameter_area": str(signed_parameter_area), "filled_area_fraction_of_original": str(expected_area),
            "oriented_area_vector": [str(value * expected_area) for value in normal],
            "unique_edges": len(edge_incidence), "boundary_edges": len(boundary),
            "boundary_loops": 2 if removed_cell is not None else 1, "euler_characteristic": euler,
            "outer_boundary_vertices_retained": 4 * segments,
            "outer_collinear_noncorner_points_retained": 4 * (segments - 1),
            "per_cell_certificate_sha256": fingerprint(certificates),
            "all_shared_edges_oppositely_oriented": True, "all_referenced_points_coplanar": True,
            "front_unchanged": True, "surface_equals_expected_quad": removed_cell is None,
            "max_input_certificate_numerator_bits": max(abs(value.numerator).bit_length() for value in observed_values),
            "max_input_certificate_denominator_bits": max(value.denominator.bit_length() for value in observed_values),
            "bit_scope": "Input coordinates and explicit certificate values. No constant-time claim or exhaustive arithmetic-intermediate profile."}


def counts(scene):
    return {"objects": len(scene["objects"]),
            "vertices": sum(len(row["vertices"]) for row in scene["objects"]),
            "triangles": sum(len(row["triangles"]) for row in scene["objects"])}


def verify_existing():
    """Read-only replay of the independent construction certificates."""
    manifest = json.loads((HERE / "INPUT_MANIFEST.json").read_bytes())
    assert manifest["source_code_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path, expected in manifest["sources_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
    for field in ("expected", "proof", "camera"):
        record = manifest[field]
        assert hashlib.sha256((HERE / record["path"]).read_bytes()).hexdigest() == record["sha256"]
    expected = json.loads((HERE / manifest["expected"]["path"]).read_bytes())
    proof = json.loads((HERE / manifest["proof"]["path"]).read_bytes())
    original = json.loads((HERE / manifest["scenes"]["original"]["path"]).read_bytes())
    targets = {row["object_index"]: row for row in expected["canonical_regions"]}
    boxes = [index for index in range(len(original["objects"])) if index not in targets]
    verified = 0
    for name, record in manifest["scenes"].items():
        path = HERE / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        scene = json.loads(path.read_bytes())
        assert counts(scene) == record["counts"]
        assert all(scene["objects"][index] == original["objects"][index] for index in boxes)
        descriptor = proof["reports"][name]
        for index, target in targets.items():
            assert scene["objects"][index]["name"] == target["object_name"]
            quad = tuple(vector(point) for point in target["vertices"])
            actual = prove_grid(scene["objects"][index], quad, descriptor["segments"], descriptor["alternating"])
            assert actual == descriptor["objects"][target["object_name"]]
            verified += 1
    seed = tuple(vector(point) for point in targets[0]["vertices"])
    for name, record in manifest["controls"].items():
        path = HERE / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        scene = json.loads(path.read_bytes())
        quad = canonical_cycle([rotate(point) for point in seed]) if name == "rotated_grid4" else seed
        actual = prove_grid(scene["objects"][0], quad, 4, True, None if name == "rotated_grid4" else HOLE_CELL)
        assert actual == proof["reports"][name]
        verified += 1
    print(json.dumps({"verified": True, "independent_surface_certificates": verified,
                      "new_discovery_renderer_model_calls": 0, "files_written": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_only:
        verify_existing()
        return
    inputs, proof = HERE / "inputs", HERE / "proof"
    inputs.mkdir(exist_ok=False)
    proof.mkdir(exist_ok=False)
    scene, original_raw = read_source(OLD / "inputs/SCENE_GEOMETRY_RATIONAL.json")
    cameras, camera_raw = read_source(OLD / "inputs/CAMERAS.json")
    oracle, _ = read_source(ORACLE / "ADMIN_ORACLE.json")
    camera_check, _ = read_source(ORACLE / "CAMERA_CHECK.json")
    accepted, _ = read_source(OLD / "runs/main_p01_A/RESULT.json")
    read_source(ROOT / "verification/m4_active_coverage_001/oracle/PUBLIC_SUMMARY.json")
    assert camera_check["passed"] and not oracle["mismatches"]
    names = {row["object_id"] for row in oracle["targets"]}
    canonical = []
    for row in accepted["index"]["regions"]:
        quad = tuple(vector(point) for point in row["vertices"])
        assert quad == canonical_cycle(list(quad))
        normal = cross(subtract(quad[1], quad[0]), subtract(quad[3], quad[0]))
        assert normal == vector(row["normal"])
        assert row["roi_id"] == "roi_" + fingerprint(quad)[:24]
        assert scene["objects"][row["object_index"]]["name"] == row["object_name"]
        canonical.append({"roi_id": row["roi_id"], "object_index": row["object_index"],
                          "object_name": row["object_name"], "vertices": quad, "normal": normal})
    canonical.sort(key=lambda row: row["roi_id"])
    assert {row["object_name"] for row in canonical} == names and len(canonical) == 6
    targets = {row["object_index"]: row for row in canonical}
    boxes = [index for index in range(len(scene["objects"])) if index not in targets]
    assert len(boxes) == 22 and counts(scene) == {"objects": 28, "vertices": 200, "triangles": 276}
    (inputs / "scene_original.json").write_bytes(original_raw)
    (inputs / "CAMERAS.json").write_bytes(camera_raw)
    definitions = [
        ("original", 1, False, False), ("grid4_uniform", 4, False, False),
        ("grid4_permuted_alternating", 4, True, True),
        ("grid16_uniform", 16, False, False), ("grid16_permuted_alternating", 16, True, True),
    ]
    scene_expected, reports = {}, {}
    for name, segments, alternating, permuted in definitions:
        path = inputs / ("scene_" + name + ".json")
        if name == "original":
            current = json.loads(path.read_bytes())
        else:
            current = copy.deepcopy(scene)
            for index, target in targets.items():
                current["objects"][index].update(make_grid(target["vertices"], segments, alternating, permuted))
            save_new(path, current)
        loaded = json.loads(path.read_bytes())
        assert all(loaded["objects"][index] == scene["objects"][index] for index in boxes)
        object_reports, regions = {}, []
        for index, target in targets.items():
            object_reports[target["object_name"]] = prove_grid(loaded["objects"][index], target["vertices"], segments, alternating)
            regions.append(dict(target, triangle_indices=list(range(len(loaded["objects"][index]["triangles"])))))
        expected_count = {1: (200, 276), 4: (326, 456), 16: (1910, 3336)}[segments]
        actual_count = counts(loaded)
        assert (actual_count["vertices"], actual_count["triangles"]) == expected_count
        reports[name] = {"passed": True, "objects": object_reports, "unchanged_opaque_boxes": len(boxes),
                         "counts": actual_count, "segments": segments, "alternating": alternating, "permuted": permuted}
        scene_expected[name] = {"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "counts": actual_count, "expected_regions": regions}
    columns = tuple(tuple(ROTATION[row][column] for row in range(3)) for column in range(3))
    assert all(dot(a, b) == (1 if i == j else 0) for i, a in enumerate(columns) for j, b in enumerate(columns))
    determinant = dot(ROTATION[0], cross(ROTATION[1], ROTATION[2]))
    assert determinant == 1
    seed = targets[0]
    rotated_quad = canonical_cycle([rotate(point) for point in seed["vertices"]])
    rotated_normal = cross(subtract(rotated_quad[1], rotated_quad[0]), subtract(rotated_quad[3], rotated_quad[0]))
    assert rotated_normal == rotate(seed["normal"])
    controls = {}
    for name, quad, hole in (("rotated_grid4", rotated_quad, None), ("hole_grid4", seed["vertices"], HOLE_CELL)):
        current = copy.deepcopy(scene)
        source = {"name": "RotatedPanel" if hole is None else "HolePanel"}
        source.update(make_grid(quad, 4, True, True, hole))
        current["objects"] = [source]
        path = inputs / ("control_" + name + ".json")
        save_new(path, current)
        report = prove_grid(json.loads(path.read_bytes())["objects"][0], quad, 4, True, hole)
        reports[name] = report
        regions = [] if hole is not None else [{"roi_id": "roi_" + fingerprint(rotated_quad)[:24],
            "object_index": 0, "object_name": source["name"], "vertices": rotated_quad, "normal": rotated_normal,
            "triangle_indices": list(range(len(source["triangles"])))}]
        controls[name] = {"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "expected_regions": regions, "expected_region_count": len(regions),
                          "removed_internal_cell": hole, "counts": counts(current)}
    views = [row["name"] for row in cameras["views"]]
    geometry_by_view = {view: {} for view in views}
    by_name = {row["object_name"]: row for row in canonical}
    for row in oracle["matrix"]:
        region = by_name[row["target"]]
        complete = bool(row["front_facing"] and row["full_interior_visible"])
        status = "complete" if complete else "back_facing" if not row["front_facing"] else "positive_area_occlusion"
        if status == "positive_area_occlusion":
            assert row["positive_area_blockers"]
        geometry_by_view[row["direction"]][region["roi_id"]] = {
            "complete": complete, "status": status, "front_facing": row["front_facing"],
            "positive_area_blockers": row["positive_area_blockers"]}
    assert all(len(rows) == 6 for rows in geometry_by_view.values())
    masks = {view: sum(1 << index for index, row in enumerate(canonical)
                       if geometry_by_view[view][row["roi_id"]]["complete"]) for view in views}
    assert masks == accepted["index"]["view_masks"]
    expected = {"schema": "triangulation-invariant-discovery-001-expected-v1", "administrator_only": True,
        "canonical_regions": canonical, "views": views, "geometry_by_view": geometry_by_view,
        "view_masks": masks, "scenes": scene_expected, "controls": controls,
        "visibility_inheritance": "Each legal grid is exactly the same oriented filled rectangle, with all22 opaque objects and camera bytes unchanged. Continuous front/frustum/shadow answers therefore inherit the independently accepted36 matrix. Actual raster pixels must be measured anew.",
        "sources_sha256": SOURCE_SHA}
    expected_sha = save_new(proof / "EXPECTED.json", expected)
    all_reports = {"schema": "triangulation-invariant-discovery-001-rational-proof-v1", "passed": True,
        "reports": reports, "proper_rotation": {"matrix": ROTATION, "orthogonal_exact": True, "determinant": determinant},
        "hole_control": {"removed_cell": HOLE_CELL, "expected_full_rectangle_discovery": False},
        "method": "Actual emitted vertices are independently projected onto the known original orthogonal edge basis. Every cell's oriented triangle pair, Fraction area, reverse shared edges and exact external/hole boundary are verified. This is a construction certificate, not a discovery implementation.",
        "new_discovery_coverage_renderer_model_calls": 0, "sources_sha256": SOURCE_SHA}
    proof_sha = save_new(proof / "PROOF.json", all_reports)
    manifest = {"schema": "triangulation-invariant-discovery-001-input-manifest-v1",
        "scenes": {name: {key: value for key, value in row.items() if key != "expected_regions"}
                   for name, row in scene_expected.items()},
        "controls": {name: {key: value for key, value in row.items() if key != "expected_regions"}
                     for name, row in controls.items()},
        "camera": {"path": "inputs/CAMERAS.json", "sha256": hashlib.sha256(camera_raw).hexdigest(),
                   "scope": "Exact source bytes, including original seed provenance metadata."},
        "fixed_benchmark_scene": "grid16_permuted_alternating",
        "fixed_observation_scenes": ["grid4_permuted_alternating", "grid16_permuted_alternating"],
        "transform_rules": {"grid": "q0+u*i/n+v*j/n; all(n+1)^2 vertices retained",
            "uniform_diagonal": "lower-left to upper-right",
            "alternation": "other diagonal exactly when(i+j)odd",
            "vertex_permutation": "reverse full vertex list, remap all indices",
            "triangle_permutation": "odd original face positions followed by even positions; rotate each face cyclically by new_position%3",
            "box_rule": "All22 other object dictionaries unchanged",
            "hole": "Remove exactly internal cell(1,1) of4x4, retain remaining mesh points"},
        "proof": {"path": "proof/PROOF.json", "sha256": proof_sha},
        "expected": {"path": "proof/EXPECTED.json", "sha256": expected_sha},
        "source_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources_sha256": SOURCE_SHA, "candidate_results_seen": False,
        "new_discovery_coverage_renderer_model_calls": 0}
    save_new(HERE / "INPUT_MANIFEST.json", manifest)
    print(json.dumps({"passed": True, "scenes": len(scene_expected), "controls": len(controls),
                      "grid4_counts": scene_expected["grid4_uniform"]["counts"],
                      "grid16_counts": scene_expected["grid16_uniform"]["counts"],
                      "new_discovery_renderer_model_calls": 0}))


if __name__ == "__main__":
    main()
