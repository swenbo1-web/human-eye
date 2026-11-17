"""Read saved fresh captures, verify sources and independently review metrics.

Ordinary CPython/NumPy only.  No product modules or Blender tools are imported.
The pre-query source_oracle.py remains frozen and is checked by SHA-256.
"""

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time

import numpy as np


OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
RUN = Path("D:/he_m4_real_asset_region_001/sessions")
FROZEN_IMPLEMENTATION = "f88636451853eff26bdac58385bbef208a7a20f02f99c57436c887589c13dae5"
ASSET_SHA = "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
COMPARISON_TOLERANCE_M = 1e-7


def read(path):
    return json.loads(Path(path).read_bytes())


def identity(path):
    path = Path(path).resolve()
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def digest(array, dtype):
    return hashlib.sha256(np.ascontiguousarray(array, dtype=dtype).tobytes()).hexdigest()


def world(local, matrix, scale):
    # Explicit scalar dot products independently reproduce the captured binary64
    # numeric contract, including its operation order.  No geometry solver is used.
    return [[(sum(matrix[axis][column] * point[column] for column in range(3)) + matrix[axis][3]) * scale
             for axis in range(3)] for point in local]


def box_certificate(vertices, faces):
    vertices = np.asarray(vertices, dtype=np.float64)
    assert vertices.shape == (8, 3)
    assert len(faces) == 12
    assert set(map(tuple, vertices)) == {(x, y, z) for x in (-1.0, 1.0)
                                        for y in (-1.0, 1.0) for z in (-1.0, 1.0)}
    coverage = {}
    for axis in range(3):
        for bound in (-1, 1):
            members = [row for row, face in enumerate(faces)
                       if all(vertices[vertex, axis] == bound for vertex in face)]
            assert len(members) == 2
            triangles = [tuple(faces[row]) for row in members]
            corners = set(triangles[0]) | set(triangles[1])
            common = set(triangles[0]) & set(triangles[1])
            assert len(corners) == 4 and len(common) == 2
            common = sorted(common)
            # Opposite rectangle corners have a diagonal with squared length 8.
            assert float(np.sum((vertices[common[0]] - vertices[common[1]]) ** 2)) == 8
            areas = [float(np.linalg.norm(np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a])) / 2)
                     for a, b, c in triangles]
            assert areas == [2.0, 2.0]
            coverage[f"{'xyz'[axis]}_{bound:+}"] = {"triangle_rows": members, "area_m2": 4.0,
                                                        "shared_diagonal_vertex_ids": common}
    assert sorted(row for face in coverage.values() for row in face["triangle_rows"]) == list(range(12))
    return {"exact_corners_m": [[-1, -1, -1], [1, 1, 1]], "six_face_coverage": coverage}


def nearest_inside_unit_box(vertices):
    vertices = np.asarray(vertices, dtype=np.float64)
    assert np.all(vertices >= -1) and np.all(vertices <= 1)
    bounds = np.vstack((vertices.min(axis=0), vertices.max(axis=0)))
    six = np.column_stack((bounds[0] + 1, 1 - bounds[1])).reshape(-1)
    winner = int(np.argmin(six))
    axis, positive = divmod(winner, 2)
    ordinal = int(np.argmax(vertices[:, axis]) if positive else np.argmin(vertices[:, axis]))
    source = vertices[ordinal].copy()
    reference = source.copy()
    reference[axis] = 1 if positive else -1
    assert float(np.linalg.norm(reference - source)) == six[winner]
    return {"distance_m": float(six[winner]), "six_lower_bounds_axis_min_max_m": six.tolist(),
            "region_bounds_m": bounds.tolist(), "region_vertex_ordinal": ordinal,
            "source_point_m": source.tolist(), "reference_point_m": reference.tolist(),
            "direction": ((reference - source) / six[winner]).tolist()}


def exact_triangle_memberships(point, vertices, faces):
    """Exact binary-rational plane and barycentric half-space checks."""
    p = tuple(map(Fraction, point))

    def subtract(a, b):
        return tuple(x - y for x, y in zip(a, b))

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    result = []
    for row, face in enumerate(faces):
        a, b, c = [tuple(map(Fraction, vertices[index])) for index in face]
        normal = cross(subtract(b, a), subtract(c, a))
        if not any(normal) or dot(subtract(p, a), normal) != 0:
            continue
        sides = [dot(cross(subtract(end, start), subtract(p, start)), normal)
                 for start, end in ((a, b), (b, c), (c, a))]
        if all(value >= 0 for value in sides):
            result.append(row)
    return result


def wire_captures(session):
    resources, captures = {}, []
    for path in sorted((RUN / session / "native/WIRE").glob("*/RESPONSE.bin")):
        envelope = read(path)
        message = envelope.get("result", {}).get("result")
        if not isinstance(message, str) or not message.startswith("HUMAN_EYE_BLENDER_MCP:"):
            continue
        result = json.loads(message.split(":", 1)[1]).get("result", {})
        if not isinstance(result, dict) or "capture" not in result:
            continue
        for resource in result["resources"]:
            resources[resource["id"]] = resource
        capture = result["capture"]
        ordered_rows, objects = [], {}
        for item in capture["meshes"]:
            reference = item["_scene_resource"]
            resource = resources[reference["id"]]
            assert resource["revision"] == reference["revision"]
            positions = world(resource["vertices_local"], reference["matrix"], reference["scale"])
            instance = capture["host_identity"]["object_instances"][item["object_id"]]
            ordered_rows.append({"host_id": item["object_id"], "instance_id": instance,
                                 "vertices": positions, "faces": resource["faces"]})
            objects[item["name"]] = {"host_id": item["object_id"], "instance_id": instance,
                                      "vertices_local": resource["vertices_local"], "faces": resource["faces"],
                                      "matrix": reference["matrix"], "scale": reference["scale"], "world": positions}
        payload = json.dumps(ordered_rows, default=str, sort_keys=True, separators=(",", ":")).encode()
        captures.append({"wire": identity(path), "capture": capture, "objects": objects,
                         "ordered_geometry_sha256": hashlib.sha256(payload).hexdigest()})
    return captures


def review_source(session, state, region, saved_raw):
    source_path = RUN / session / f"SOURCE_{state}.json"
    oracle_path = RUN / session / f"ORACLE_{state}.json"
    snapshot, oracle = read(source_path), read(oracle_path)
    assert snapshot["source_sha256"] == region["source_sha256"] == ASSET_SHA
    assert snapshot["state"] == state and snapshot["unit_scale"] == 1
    assert snapshot["unit_settings"]["system"] == "METRIC"
    assert oracle["status"] == "passed" and oracle["implementation"]["sha256"] == FROZEN_IMPLEMENTATION
    assert identity(source_path) == oracle["inputs"]["snapshot"]
    objects = {item["name"]: item for item in snapshot["objects"]}
    target, cube = objects[region["object_name"]], objects["Cube"]
    assert not [item for item in snapshot["objects_inventory"] if item["type"] == "ARMATURE"]
    assert target["modifiers"] == [] and target["animation"] is None
    expected_matrix = np.asarray(region["matrix_world"], dtype=float)
    if state == "moved":
        expected_matrix[0, 3] += 0.25
    assert np.array_equal(target["matrix_world"], expected_matrix)
    assert target["native"]["vertices"] == target["evaluated"]["vertices"] == saved_raw["vertices_object"]
    assert target["native"]["triangles"] == target["evaluated"]["triangles"] == saved_raw["triangles"]
    assert target["native"]["triangle_polygons"] == target["evaluated"]["triangle_polygons"] == saved_raw["polygon_ids_by_triangle"]
    assert len(target["native"]["polygons"]) == 29073
    selected_rows, selected_vertices = region["source_triangle_ids"], region["source_vertex_ids"]
    for ordinal, row in enumerate(selected_rows):
        expected_vertices = [selected_vertices[index] for index in region["triangles_local"][ordinal]]
        assert target["native"]["triangles"][row] == expected_vertices
        assert target["native"]["triangle_polygons"][row] == region["source_polygon_ids"][ordinal]
        mapping = oracle["source_correspondence"]["triangle_mapping"][ordinal]
        assert mapping["historical_source_triangle_row"] == mapping["native_triangle_row"] == mapping["evaluated_triangle_row"] == row
        assert mapping["native_vertex_ids"] == mapping["evaluated_vertex_ids"] == expected_vertices
        assert mapping["native_polygon_index"] == mapping["evaluated_polygon_index"] == region["source_polygon_ids"][ordinal]
    host_world = np.asarray(target["evaluated"]["vertices_world_m"])
    ideal_world = world(target["evaluated"]["vertices"], target["matrix_world"], 1.0)
    expected_readback = np.asarray(saved_raw["vertices_world"], dtype=float)
    if state == "moved":
        expected_readback[:, 0] += 0.25
    assert np.array_equal(host_world, expected_readback)
    assert np.array_equal(host_world, target["native"]["vertices_world_m"])
    for ordinal, vertex in enumerate(selected_vertices):
        mapping = oracle["source_correspondence"]["vertex_mapping"][ordinal]
        assert mapping["historical_native_vertex_id"] == mapping["fresh_native_vertex_id"] == mapping["fresh_evaluated_vertex_id"] == vertex
        assert mapping["native_local"] == mapping["evaluated_local"] == region["vertices_object"][ordinal]
        assert mapping["native_world_m"] == mapping["evaluated_world_m"] == host_world[vertex].tolist()
    cube_native, cube_evaluated = cube["native"], cube["evaluated"]
    assert cube_native == cube_evaluated
    assert len(cube_native["polygons"]) == 6 and cube["display"]["hide_render"] is True
    coverage = box_certificate(cube_evaluated["vertices_world_m"], cube_evaluated["triangles"])
    readback_answer = nearest_inside_unit_box(host_world[selected_vertices])
    ideal_answer = nearest_inside_unit_box(np.asarray(ideal_world)[selected_vertices])
    assert oracle["distance_oracle"]["distance_m"] == readback_answer["distance_m"] == 0.3701171875
    assert oracle["float64_matrix_distance_comparison"]["distance_m"] == ideal_answer["distance_m"]
    assert oracle["distance_oracle"]["certificate"]["lower_bound_m"] == readback_answer["distance_m"]
    assert oracle["distance_oracle"]["certificate"]["attained_upper_bound_m"] == readback_answer["distance_m"]
    assert oracle["ordered_region_arrays"]["world_vertices_m"]["sha256"] == digest(host_world[selected_vertices], "<f8")
    report = {"session": session, "state": state, "status": "passed", "source": identity(source_path),
              "frozen_oracle": identity(oracle_path), "process_id": snapshot["process_id"],
              "native_evaluated_complete_point_count": len(host_world), "native_polygon_count": 29073,
              "native_evaluated_complete_triangle_count": len(target["native"]["triangles"]),
              "all_native_evaluated_local_vertices_and_triangle_polygon_rows_equal_saved": True,
              "all_native_evaluated_readback_world_points_follow_prescribed_state": True,
              "selected_triangle_mappings_checked": len(selected_rows),
              "selected_vertex_mappings_checked": len(selected_vertices),
              "reference_triangle_mappings_checked": len(cube_evaluated["triangles"]),
              "reference_display": cube["display"], "reference_box_certificate": coverage,
              "readback_domain_answer": readback_answer, "binary64_matrix_domain_answer": ideal_answer,
              "binary64_minus_readback_distance_m": ideal_answer["distance_m"] - readback_answer["distance_m"],
              "full_readback_vs_binary64_matrix_max_coordinate_error_m": float(np.max(np.abs(host_world - ideal_world)))}
    return snapshot, report


def review_product(session, public, state, snapshot, source_report, captures, region):
    archive = public["producer_archive"]
    result_path = Path(archive["path"])
    result = read(result_path)
    assert identity(result_path)["sha256"] == archive["sha256"]
    binding = result["binding"]
    matching = [item for item in captures
                if item["capture"]["capture_state"] == binding["capture_state"]
                and item["capture"]["host_identity"]["document_epoch"] == binding["document_epoch"]
                and item["ordered_geometry_sha256"] == binding["ordered_geometry_sha256"]]
    assert matching
    capture = matching[0]
    native_objects = {item["name"]: item for item in snapshot["objects"]}
    for name, wire in capture["objects"].items():
        obj = native_objects[name]
        assert wire["instance_id"] == obj["instance_id"]
        assert wire["vertices_local"] == obj["evaluated"]["vertices"]
        assert wire["faces"] == obj["evaluated"]["triangles"]
        assert wire["matrix"] == obj["matrix_world"] and wire["scale"] == snapshot["unit_scale"]
    target = capture["objects"][region["object_name"]]
    cube = capture["objects"]["Cube"]
    selected_rows = region["source_triangle_ids"]
    selected_vertices = region["source_vertex_ids"]
    expected_faces = [target["faces"][row] for row in selected_rows]
    index_lookup = {vertex: ordinal for ordinal, vertex in enumerate(selected_vertices)}
    expected_submesh = [[index_lookup[vertex] for vertex in face] for face in expected_faces]
    for mapping in (result["source_mapping"], result["task_result"]["source_mapping"]["region"]):
        assert mapping["submesh_to_source_triangle_indices"] == selected_rows
        assert mapping["submesh_to_source_vertex_indices"] == selected_vertices
        assert mapping["triangles_source_vertices"] == expected_faces
        assert mapping["triangles_submesh_vertices"] == expected_submesh
    actual_region = result["facts"]["region"]
    assert actual_region["source_triangle_indices"] == selected_rows
    assert actual_region["source_vertex_indices"] == selected_vertices
    assert actual_region["vertices_world_m"] == [target["world"][vertex] for vertex in selected_vertices]
    assert actual_region["instance_id"] == target["instance_id"]
    assert actual_region["host_id"] == target["host_id"]
    reference = result["task_result"]["reference"]
    assert reference["instance_id"] == cube["instance_id"] and reference["object_id"] == cube["host_id"]
    expected = source_report["binary64_matrix_domain_answer"]
    fact = result["task_result"]["facts"]["surface_proximity"]
    value = fact["value"]
    assert fact["status"] == fact["witness_status"] == fact["direction_status"] == "measured"
    assert value["distance_m"] == expected["distance_m"]
    witness = value["nearest_witness"]
    assert witness["a"] == expected["source_point_m"] and witness["b"] == expected["reference_point_m"]
    assert witness["direction_a_to_b"] == expected["direction"] == [0.0, 0.0, 1.0]
    witness_vertex_ids = [vertex for vertex in selected_vertices if target["world"][vertex] == witness["a"]]
    assert witness_vertex_ids == [24331]
    exact_source_rows = [row for row in selected_rows if 24331 in target["faces"][row]]
    exact_reference_rows = exact_triangle_memberships(witness["b"], cube["world"], cube["faces"])
    mapping = result["task_result"]["source_mapping"]["nearest_witness"]
    assert mapping["a"]["exact_membership"] and mapping["b"]["exact_membership"]
    assert mapping["a"]["source_vertex_indices"] == witness_vertex_ids
    assert mapping["a"]["source_triangle_indices"] == exact_source_rows
    assert mapping["b"]["source_triangle_indices"] == exact_reference_rows
    assert mapping["b"]["source_vertex_indices"] == []
    return {"session": session, "state": state, "public_call_index": public["internal_public_call_index"],
            "producer_archive_index": public["producer_archive_index"], "status": "passed",
            "product_full_result": identity(result_path), "native_wire": capture["wire"],
            "binding": {key: binding[key] for key in ("document_epoch", "capture_state", "ordered_geometry_sha256", "binding_sha256")},
            "complete_resource_local_vertices_faces_matrices_units_instances_equal_fresh_export": True,
            "ordered_geometry_digest_recomputed_from_complete_wire_resources": True,
            "selected_mapping_triangles_checked": len(selected_rows), "selected_mapping_points_checked": len(selected_vertices),
            "distance_m": value["distance_m"], "distance_error_vs_independent_binary64_m": 0,
            "distance_error_vs_independent_host_readback_m": value["distance_m"] - source_report["readback_domain_answer"]["distance_m"],
            "nearest_witness": witness, "independently_checked_source_memberships": exact_source_rows,
            "independently_checked_reference_memberships": exact_reference_rows,
            "source_native_vertex_id": 24331, "read_only": result["read_only"],
            "execution_authority": result["execution_authority"]}


def main():
    started = time.perf_counter()
    baseline = read(ROOT / "BASELINE.json")
    asset = identity(baseline["asset"]["path"])
    assert asset["sha256"] == ASSET_SHA
    assert identity(OUT / "source_oracle.py")["sha256"] == FROZEN_IMPLEMENTATION
    region = read(ROOT / "inputs/ARM_REGION.json")
    saved_raw = read(ROOT / "inputs/raw_selected.json")
    sources, snapshots, products, copies = [], {}, [], []
    for session, states in (("main", ("initial",)), ("state", ("initial", "moved", "restored"))):
        copy = identity(RUN / session / "native/input.blend")
        assert copy["sha256"] == ASSET_SHA
        copies.append(copy)
        for state in states:
            snapshot, source = review_source(session, state, region, saved_raw)
            snapshots[(session, state)] = snapshot, source
            sources.append(source)
        captures = wire_captures(session)
        public_requests = [json.loads(line) for line in (RUN / session / "PUBLIC_REQUESTS.jsonl").read_text(encoding="utf8").splitlines()]
        for public in public_requests:
            if public["producer_archive_index"] is None:
                continue
            state = "initial" if session == "main" else {1: "initial", 3: "moved", 5: "restored"}[public["internal_public_call_index"]]
            snapshot, source = snapshots[(session, state)]
            products.append(review_product(session, public, state, snapshot, source, captures, region))
    initial = snapshots[("state", "initial")][0]
    restored = snapshots[("state", "restored")][0]
    assert initial["objects"] == restored["objects"]
    assert initial["process_id"] == restored["process_id"]
    report = {"schema": "real-asset-fresh-source-metric-review-v1", "status": "passed",
              "scope": "Saved fresh owned exports and all five successful actual public calls",
              "review_implementation": identity(__file__), "frozen_prequery_oracle": identity(OUT / "source_oracle.py"),
              "original_asset_current": asset, "owned_asset_copies_current": copies,
              "fresh_snapshots_checked": len(sources), "successful_public_calls_checked": len(products),
              "source_correspondence": "passed", "surface_metric_and_witness_and_direction": "passed",
              "restored_all_source_object_data_equal_initial": True,
              "unit": "m", "comparison_tolerance_m": COMPARISON_TOLERANCE_M,
              "product_metric_domain": "binary64 world geometry reconstructed from complete native wire resources",
              "host_readback_distance_m": 0.3701171875,
              "binary64_matrix_product_distance_m": 0.37011719389236364,
              "binary64_minus_host_readback_distance_m": 6.392363638418885e-09,
              "sources": sources, "products": products, "elapsed_seconds": time.perf_counter() - started,
              "new_Blender_processes": 0, "new_product_calls": 0, "new_raster_calls": 0,
              "product_geometry_solver_imports": 0}
    path = OUT / "FRESH_REVIEW.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "sources": len(sources), "products": len(products),
                      "elapsed_seconds": report["elapsed_seconds"], "output": str(path)}))


if __name__ == "__main__":
    main()
