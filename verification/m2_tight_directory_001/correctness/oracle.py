"""Independent affine-coordinate bounds from raw evaluated vertices."""

from fractions import Fraction
import hashlib
import itertools
import json
import math
import sys


def existing_object_id(name_full, library_path=""):
    raw = json.dumps([library_path, name_full], sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode()
    return "blender:" + hashlib.sha256(raw).hexdigest()


def tight_bounds(vertices, matrix, scale):
    if not vertices or not math.isfinite(scale) or scale <= 0:
        raise ValueError("oracle requires nonempty finite vertices and positive scale")
    q = lambda value: Fraction(float(value))
    s = q(scale)
    points = [[(sum(q(matrix[r][c]) * q(point[c]) for c in range(3)) + q(matrix[r][3])) * s
               for r in range(3)] for point in vertices]
    lower = [min(point[axis] for point in points) for axis in range(3)]
    upper = [max(point[axis] for point in points) for axis in range(3)]
    magnitude = max(float(sum(abs(q(matrix[r][c]) * q(point[c])) for c in range(3)) * s
                          + abs(q(matrix[r][3]) * s)) for point in vertices for r in range(3))
    return {"bbox_min": [float(value) for value in lower], "bbox_max": [float(value) for value in upper],
            "center": [float((a + b) / 2) for a, b in zip(lower, upper)],
            "rounding_bound_m": 64 * sys.float_info.epsilon * max(1e-6, magnitude),
            "oracle": "exact rational affine map of the stored binary coordinates; bounded float publication"}


def wrong_eight_corner_bounds(vertices, matrix, scale):
    lo = [min(point[axis] for point in vertices) for axis in range(3)]
    hi = [max(point[axis] for point in vertices) for axis in range(3)]
    corners = list(itertools.product(*zip(lo, hi)))
    return tight_bounds(corners, matrix, scale)


def assert_packet(test, packet, raw_objects, *, host_source_sha256=None):
    test.assertEqual(packet["result_kind"], "scene_directory")
    test.assertEqual(packet["schema"], "human-eye-directory-v1")
    test.assertEqual(packet["status"], "complete")
    test.assertIs(packet['execution_authority'], False)
    test.assertEqual((packet["unit"], packet["coordinate_frame"]), ("m", "world"))
    test.assertEqual(packet["coverage"], {"status": "complete", "mesh_objects": len(raw_objects), "measured_objects": len(raw_objects)})
    expected = {existing_object_id(row["name_full"], row.get("library_path", "")): row for row in raw_objects}
    test.assertEqual(len(packet["objects"]), len(expected))
    test.assertEqual({row["object_id"] for row in packet["objects"]}, set(expected))
    for row in packet["objects"]:
        test.assertEqual(set(row), {"object_id", "name", "bbox_min", "bbox_max", "center"})
        source = expected[row["object_id"]]
        truth = tight_bounds(source["vertices_local"], source["matrix_world"], source["unit_scale_m"])
        test.assertEqual(row["name"], source["name"])
        for field in ("bbox_min", "bbox_max", "center"):
            test.assertEqual(len(row[field]), 3)
            for value, reference in zip(row[field], truth[field]):
                test.assertTrue(math.isfinite(value))
                test.assertLessEqual(abs(value - reference), truth["rounding_bound_m"])
    test.assertEqual(packet["binding"]["host_identity"]["capture_scope"], "scene_directory")
    if host_source_sha256 is not None:
        test.assertEqual(packet["binding"]["host_source_sha256"], host_source_sha256)
    test.assertRegex(packet["directory_sha256"], r"^[0-9a-f]{64}$")
    for name in ("scene_revision", "revision", "scene_fingerprint", "scene_memory", "scene_capabilities",
                 "capture_capability", "resources", "meshes", "faces", "edges", "vertices", "image"):
        test.assertNotIn(name, packet)


def raw_rna_objects(host):
    graph = host.bpy.context.evaluated_depsgraph_get()
    rows = []
    for obj in host.bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            rows.append({"name": str(obj.name), "name_full": str(obj.name_full),
                "library_path": str(getattr(getattr(obj, "library", None), "filepath", "")),
                "vertices_local": [[float(value) for value in vertex.co] for vertex in mesh.vertices],
                "matrix_world": [[float(value) for value in values] for values in evaluated.matrix_world],
                "unit_scale_m": float(host.bpy.context.scene.unit_settings.scale_length)})
        finally:
            evaluated.to_mesh_clear()
    return rows
