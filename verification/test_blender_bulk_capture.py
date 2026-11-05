"""Same-capture bulk RNA extraction regressions using explicit Blender doubles.

Real Blender storage qualification is recorded separately. These tests exercise
fallback precision, damaged bulk reads, cleanup and pre-allocation boundaries.
"""
from __future__ import annotations

from array import array
import json
import math
import struct
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from verification.test_blender_host_contracts import _module, host_fixture


class CountedCoordinates:
    def __init__(self, values):
        self.values = list(values)
        self.reads = 0

    def __getitem__(self, index):
        self.reads += 1
        return self.values[index]


class BulkCollection(list):
    def __init__(self, items, field, kind, values, mode="complete"):
        super().__init__(items)
        self.field, self.kind = field, kind
        self.values = list(values)
        self.mode = mode
        self.calls = 0

    def foreach_get(self, field, buffer):
        self.calls += 1
        if field != self.field:
            raise AssertionError("unexpected RNA field")
        if self.mode == "partial_raise":
            buffer[0] = self.values[0]
            raise RuntimeError("RNA stopped after a partial write")
        if self.mode == "incomplete_success":
            for index, value in enumerate(self.values[:-1]):
                buffer[index] = value
            return
        buffer[:] = array(self.kind, self.values)
        if self.mode == "resize_buffer":
            buffer.append(0)
        elif self.mode == "resize_collection":
            self.append(self[0])


class ReportedCollection(list):
    def __init__(self, items, reported_length):
        super().__init__(items)
        self.reported_length = reported_length
        self.calls = 0

    def __len__(self):
        return self.reported_length

    def foreach_get(self, field, buffer):
        self.calls += 1
        raise AssertionError("over-budget collection must never be read")


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def single_fixture():
    host, obj, _, graph = host_fixture()
    host.scene.objects = [obj]
    return host, obj, graph


def install_geometry(obj, *, bulk, points=None, faces=None, coordinate_mode="complete", triangle_mode="complete"):
    if points is None:
        points = [(-0., 0., 0.), (.1, 1. / 3., 0.), (0., 1., 0.), (0., 0., 1.)]
    if faces is None:
        faces = [(1, 2, 3), (0, 2, 1), (0, 1, 3), (0, 3, 2)]
    stored = [[f32(value) for value in point] if bulk else list(point) for point in points]
    vertices = [NS(co=CountedCoordinates(point)) for point in stored]
    triangles = [NS(vertices=tuple(face)) for face in faces]
    obj.data.polygons = [NS(vertices=tuple(face)) for face in faces]
    if bulk:
        obj.data.vertices = BulkCollection(vertices, "co", "f", [value for point in stored for value in point], coordinate_mode)
        obj.data.loop_triangles = BulkCollection(triangles, "vertices", "i", [value for face in faces for value in face], triangle_mode)
    else:
        obj.data.vertices, obj.data.loop_triangles = vertices, triangles
    return stored, faces


def enable_native(host, obj):
    host.execution_metadata = host.identity_metadata = True
    host.scene.session_uid = 11
    obj.session_uid = 22
    host.bpy.app = NS(driver_namespace={"_human_eye_document_epoch_v1": "a" * 32})
    host.bpy.data = NS(filepath="private-bulk-test.blend")


class BlenderBulkCaptureTests(unittest.TestCase):
    def test_absent_method_preserves_binary64_and_three_scalar_accesses(self):
        host, obj, _ = single_fixture()
        points, _ = install_geometry(obj, bulk=False)
        scene = host.capture_scene()
        expected = [[(sum(float(obj.matrix_world[r][c]) * point[c] for c in range(3))
                      + float(obj.matrix_world[r][3])) for r in range(3)] for point in points]
        self.assertEqual(scene["meshes"][0]["vertices"], expected)
        self.assertEqual(sum(vertex.co.reads for vertex in obj.data.vertices), 3 * len(points))
        self.assertNotEqual(points[1][0], f32(points[1][0]))
        self.assertEqual(obj.clears, 1)

    def test_bulk_bits_order_and_original_world_expression_match_scalar(self):
        host, obj, _ = single_fixture()
        points, faces = install_geometry(obj, bulk=True)
        angle = .37
        obj._matrix_world = [[math.cos(angle), -math.sin(angle), 0., 1e8],
                             [math.sin(angle), math.cos(angle), 0., -3.25],
                             [0., 0., 1., .125], [0., 0., 0., 1.]]
        host.scene.unit_settings.scale_length = .001
        scene = host.capture_scene()
        expected = [[(sum(obj.matrix_world[r][c] * point[c] for c in range(3))
                      + obj.matrix_world[r][3]) * .001 for r in range(3)] for point in points]
        self.assertEqual(scene["meshes"][0]["vertices"], expected)
        self.assertEqual(scene["meshes"][0]["faces"], [list(face) for face in faces])
        self.assertEqual(sum(vertex.co.reads for vertex in obj.data.vertices), 0)
        raw = _module._mesh_buffer(obj.data.vertices, "co", "f", len(points))
        self.assertEqual(struct.pack("<f", raw[0]), struct.pack("<I", 0x80000000))
        bulk_bytes = json.dumps(scene, sort_keys=True, allow_nan=False).encode()
        install_geometry(obj, bulk=False, points=points, faces=faces)
        self.assertEqual(json.dumps(host.capture_scene(), sort_keys=True, allow_nan=False).encode(), bulk_bytes)

    def test_native_evidence_preserves_original_independent_scalar_validation(self):
        host, obj, _ = single_fixture()
        points, faces = install_geometry(obj, bulk=True)
        enable_native(host, obj)
        bulk = host.capture_evidence()
        self.assertTrue(bulk["coherence"]["raw_original_mesh_verified"])
        self.assertEqual(sum(vertex.co.reads for vertex in obj.data.vertices), 3 * len(points))
        install_geometry(obj, bulk=False, points=points, faces=faces)
        scalar = host.capture_evidence()
        self.assertEqual(json.dumps(bulk, sort_keys=True, allow_nan=False), json.dumps(scalar, sort_keys=True, allow_nan=False))
        self.assertEqual(obj.assignments, 0)
        self.assertEqual(obj.clears, 2)

    def test_present_noncallable_method_is_rejected_without_scalar_fallback(self):
        for value in (None, 7, "foreach"):
            with self.subTest(value=value):
                host, obj, _ = single_fixture()
                install_geometry(obj, bulk=True)
                obj.data.vertices.foreach_get = value
                with self.assertRaises(_module.BlenderHostError):
                    host.capture_scene()
                self.assertEqual(sum(vertex.co.reads for vertex in obj.data.vertices), 0)
                self.assertEqual(obj.clears, 1)

    def test_partial_damaged_or_resized_reads_are_rejected_and_cleaned(self):
        for field in ("coordinates", "triangles"):
            for mode in ("partial_raise", "incomplete_success", "resize_buffer", "resize_collection"):
                with self.subTest(field=field, mode=mode):
                    host, obj, _ = single_fixture()
                    install_geometry(obj, bulk=True, coordinate_mode=mode if field == "coordinates" else "complete",
                                     triangle_mode=mode if field == "triangles" else "complete")
                    expected_error = RuntimeError if mode == "partial_raise" else _module.BlenderHostError
                    with self.assertRaises(expected_error):
                        host.capture_scene()
                    self.assertEqual(sum(vertex.co.reads for vertex in obj.data.vertices), 0)
                    self.assertEqual(obj.clears, 1)

    def test_nonfinite_bulk_coordinates_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                host, obj, _ = single_fixture()
                install_geometry(obj, bulk=True)
                obj.data.vertices.values[0] = value
                with self.assertRaises(_module.BlenderHostError):
                    host.capture_scene()
                self.assertEqual(obj.clears, 1)

    def test_bulk_indices_must_refer_to_existing_vertices(self):
        for value in (-1, 4, 2 ** 31 - 1):
            with self.subTest(value=value):
                host, obj, _ = single_fixture()
                install_geometry(obj, bulk=True)
                obj.data.loop_triangles.values[-1] = value
                with self.assertRaises(_module.BlenderHostError):
                    host.capture_scene()
                self.assertEqual(obj.clears, 1)

    def test_wrong_array_width_is_rejected_before_multiplication_or_read(self):
        host, obj, _ = single_fixture()
        install_geometry(obj, bulk=True)
        with patch.object(_module, "array", return_value=NS(itemsize=8)):
            with self.assertRaises(_module.BlenderHostError):
                host.capture_scene()
        self.assertEqual(obj.data.vertices.calls, 0)
        self.assertEqual(obj.clears, 1)

    def test_single_mesh_budget_is_checked_before_any_buffer_allocation(self):
        for field, limit in (("vertices", 500_001), ("loop_triangles", 1_000_001)):
            with self.subTest(field=field):
                host, obj, _ = single_fixture()
                install_geometry(obj, bulk=True)
                collection = ReportedCollection(getattr(obj.data, field), limit)
                setattr(obj.data, field, collection)
                with patch.object(_module, "array", side_effect=AssertionError("budget check must precede allocation")):
                    with self.assertRaisesRegex(_module.BlenderHostError, "geometry budget"):
                        host.capture_scene()
                self.assertEqual(collection.calls, 0)
                self.assertEqual(obj.clears, 1)

    def test_cumulative_budget_is_checked_before_second_mesh_buffer(self):
        for field, limit in (("vertices", 500_000), ("loop_triangles", 1_000_000)):
            with self.subTest(field=field):
                host, focal, reference, _ = host_fixture()
                ordered = sorted((focal, reference), key=host.object_id)
                for obj in ordered:
                    install_geometry(obj, bulk=True)
                collection = ReportedCollection(getattr(ordered[1].data, field), limit)
                setattr(ordered[1].data, field, collection)
                with patch.object(_module, "array", wraps=array) as factory:
                    with self.assertRaisesRegex(_module.BlenderHostError, "geometry budget"):
                        host.capture_scene()
                self.assertEqual(factory.call_count, 2)
                self.assertEqual(collection.calls, 0)
                self.assertEqual([obj.clears for obj in ordered], [1, 1])


if __name__ == "__main__":
    unittest.main()
