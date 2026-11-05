"""Independent native oracle and lifecycle tests for the RB-B Blender bridge."""

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest
import weakref

import numpy as np

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange
from human_eye_fast.resident_bridge import ResidentMesh


_ARRAY_FIELDS = ("local_m", "world_m", "triangles", "world_from_local")
_FLOAT_FIELDS = ("local_m", "world_m", "world_from_local")


@dataclass(frozen=True)
class _NativeAppearance:
    object_color: tuple
    material_slots: tuple
    polygon_material_indices: np.ndarray
    triangle_polygon_indices: np.ndarray


def native_oracle(obj, depsgraph, scale_length):
    """Read Blender's evaluated float32 values without the bridge's bulk path."""
    evaluated = obj.evaluated_get(depsgraph)
    matrix = np.array([list(row) for row in evaluated.matrix_world], dtype=np.float64)
    temporary = evaluated.to_mesh()
    try:
        vertices = np.array([tuple(vertex.co) for vertex in temporary.vertices], dtype=np.float64)
        vertices = vertices.reshape(-1, 3)
        temporary.calc_loop_triangles()
        triangles = np.array(
            [tuple(triangle.vertices) for triangle in temporary.loop_triangles], dtype=np.int32,
        ).reshape(-1, 3)
        appearance = _NativeAppearance(
            tuple(evaluated.color),
            tuple(
                None if slot.material is None else (slot.name, tuple(slot.material.diffuse_color))
                for slot in evaluated.material_slots
            ),
            np.fromiter((face.material_index for face in temporary.polygons), dtype=np.int32),
            np.fromiter(
                (triangle.polygon_index for triangle in temporary.loop_triangles), dtype=np.int32,
            ),
        )
    finally:
        evaluated.to_mesh_clear()

    homogeneous = np.column_stack((vertices, np.ones(len(vertices))))
    world_m = scale_length * np.einsum("ij,vj->vi", matrix, homogeneous)[:, :3]
    matrix[:3, 3] *= scale_length
    return ResidentMesh(vertices * scale_length, world_m, triangles, matrix, appearance)


def assert_matches_oracle(mesh, expected):
    """Check every output field and report numerical differences in float fields."""
    errors = {}
    for field in _FLOAT_FIELDS:
        actual_array = getattr(mesh, field)
        expected_array = getattr(expected, field)
        np.testing.assert_equal(actual_array.dtype, np.dtype(np.float64), err_msg=field)
        np.testing.assert_equal(actual_array.shape, expected_array.shape, err_msg=field)
        np.testing.assert_allclose(
            actual_array, expected_array, rtol=1e-10, atol=1e-10, err_msg=field,
        )
        errors[field] = float(np.max(np.abs(actual_array - expected_array), initial=0.0))
    np.testing.assert_array_equal(mesh.triangles, expected.triangles)
    np.testing.assert_equal(np.issubdtype(mesh.triangles.dtype, np.integer), True)
    actual = mesh.appearance
    reference = expected.appearance
    np.testing.assert_equal(actual.object_color, reference.object_color)
    np.testing.assert_equal(actual.material_slots, reference.material_slots)
    np.testing.assert_array_equal(actual.polygon_material_indices, reference.polygon_material_indices)
    np.testing.assert_array_equal(actual.triangle_polygon_indices, reference.triangle_polygon_indices)
    np.testing.assert_array_equal(
        actual.polygon_material_indices[actual.triangle_polygon_indices],
        reference.polygon_material_indices[reference.triangle_polygon_indices],
    )
    return errors


_VERTICES = [
    (0.1, 0.0, -0.2), (2.0, 0.1, 0.25), (2.4, 1.7, -0.5), (0.0, 1.5, 0.7),
]
_FACES = [(0, 1, 2), (0, 2, 3)]


@unittest.skipIf(bpy is None, "requires Blender's embedded Python")
class BlenderResidentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = BlenderResidentBridge()
        self.addCleanup(self.bridge.clear)
        self.scene = bpy.context.scene
        units = self.scene.unit_settings
        self.addCleanup(setattr, units, "scale_length", units.scale_length)
        self.addCleanup(self.scene.frame_set, self.scene.frame_current)
        units.scale_length = 0.125

    def mesh_data(self, vertices, faces):
        data = bpy.data.meshes.new("RB-B test mesh")
        self.addCleanup(bpy.data.meshes.remove, data)
        data.from_pydata(vertices, [], faces)
        data.update()
        return data

    def object(self, data=None):
        obj = bpy.data.objects.new("RB-B test object", data)
        name = obj.name
        self.scene.collection.objects.link(obj)

        def remove_if_present():
            if name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

        self.addCleanup(remove_if_present)
        return obj

    def paint(self, name, rgba):
        material = bpy.data.materials.new(name)
        material.diffuse_color = rgba
        self.addCleanup(bpy.data.materials.remove, material)
        return material

    def capture(self, key, obj, changes=MeshChange.NONE):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        scale = self.scene.unit_settings.scale_length
        expected = native_oracle(obj, depsgraph, scale)
        mesh = self.bridge.capture(key, obj, depsgraph, scale, changes)
        self.assertIsInstance(mesh, ResidentMesh)
        self.assertIs(mesh, self.bridge.get(key))
        assert_matches_oracle(mesh, expected)
        for field in _ARRAY_FIELDS:
            array = getattr(mesh, field)
            self.assertFalse(array.flags.writeable, field)
            with self.assertRaises(ValueError, msg=field):
                array.setflags(write=True)
        return mesh, expected

    def assert_same_arrays(self, current, previous):
        for field in _ARRAY_FIELDS:
            self.assertIs(getattr(current, field), getattr(previous, field), field)

    def test_evaluated_modifier_frames_and_reflected_parent_transform(self):
        parent = self.object()
        parent.scale = (-1.75, 0.5, 2.5)
        parent.rotation_euler = (0.2, 0.3, -0.5)
        parent.location = (7.2, -3.4, 0.8)

        obj = self.object(self.mesh_data(_VERTICES, _FACES))
        obj.parent = parent
        obj.rotation_euler = (0.1, -0.35, 0.6)
        obj.location = (0.2, 1.5, -0.3)
        modifier = obj.modifiers.new("Animated real displacement", "DISPLACE")
        modifier.direction = "Z"
        modifier.mid_level = 0.25
        modifier.strength = 0.375
        modifier.keyframe_insert(data_path="strength", frame=1)
        modifier.strength = -0.625
        modifier.keyframe_insert(data_path="strength", frame=2)

        other = self.object(self.mesh_data(_VERTICES, _FACES))
        other.location = (-0.8, 0.9, -1.5)
        self.scene.frame_set(1)
        first, _ = self.capture("scan", obj)
        isolated, isolated_expected = self.capture(17, other)
        self.assertEqual(len(self.bridge), 2)
        self.assertLess(np.linalg.det(first.world_from_local[:3, :3]), 0)
        base_m = np.asarray(_VERTICES) * self.scene.unit_settings.scale_length
        self.assertGreater(np.max(np.abs(first.local_m - base_m)), 0.01)
        frame1 = first.local_m.copy()

        self.scene.frame_set(2)
        second, _ = self.capture("scan", obj, MeshChange.VERTICES)
        self.assert_same_arrays(second, first)
        self.assertGreater(np.max(np.abs(second.local_m - frame1)), 0.01)
        self.scene.frame_set(1)
        returned, _ = self.capture("scan", obj, MeshChange.VERTICES)
        np.testing.assert_array_equal(returned.local_m, frame1)

        previous_world = returned.world_m.copy()
        parent.location.x += 0.75
        transformed, _ = self.capture("scan", obj, MeshChange.TRANSFORM)
        self.assert_same_arrays(transformed, first)
        np.testing.assert_array_equal(transformed.local_m, frame1)
        self.assertGreater(np.max(np.abs(transformed.world_m - previous_world)), 0.01)
        self.assertIs(self.bridge.get(17), isolated)
        assert_matches_oracle(isolated, isolated_expected)

    def test_appearance_only_no_change_and_combined_update(self):
        data = self.mesh_data(_VERTICES, _FACES)
        paint_a = self.paint("RB-B sky", (0.1, 0.25, 0.8, 1.0))
        paint_b = self.paint("RB-B orange", (0.8, 0.25, 0.1, 0.75))
        data.materials.append(paint_a)
        data.materials.append(paint_b)
        obj = self.object(data)
        obj.color = (0.3, 0.4, 0.5, 0.6)
        obj.location = (4.1, -2.6, 0.25)
        first, old_expected = self.capture("paint", obj)
        unchanged, _ = self.capture("paint", obj)
        self.assertIs(unchanged, first)

        obj.color = (0.15, 0.2, 0.25, 0.3)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = paint_b
        paint_b.name = "RB-B red"
        paint_b.diffuse_color = (0.875, 0.125, 0.5, 1.0)
        data.polygons[1].material_index = 1
        data.update()
        painted, _ = self.capture("paint", obj, MeshChange.APPEARANCE)
        self.assert_same_arrays(painted, first)
        self.assertNotEqual(painted.appearance.object_color, old_expected.appearance.object_color)
        self.assertNotEqual(painted.appearance.material_slots, old_expected.appearance.material_slots)
        np.testing.assert_array_equal(painted.appearance.polygon_material_indices, [0, 1])
        assert_matches_oracle(first, old_expected)

        self.scene.unit_settings.scale_length = 0.03
        scaled, _ = self.capture("paint", obj, MeshChange.UNITS)
        self.assert_same_arrays(scaled, first)
        np.testing.assert_allclose(scaled.local_m, old_expected.local_m * (0.03 / 0.125), rtol=1e-7)
        np.testing.assert_array_equal(
            scaled.world_from_local[:3, :3], old_expected.world_from_local[:3, :3],
        )

        local_before = scaled.local_m.copy()
        obj.data.vertices[0].co.x += 2.0
        obj.data.update()
        obj.location.y += 3.0
        obj.color = (0.5, 0.625, 0.75, 0.875)
        self.scene.unit_settings.scale_length = 0.75
        combined, _ = self.capture(
            "paint", obj,
            MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.APPEARANCE | MeshChange.UNITS,
        )
        self.assert_same_arrays(combined, first)
        self.assertGreater(np.max(np.abs(combined.local_m - local_before)), 0.01)
        self.assertNotEqual(combined.appearance.object_color, painted.appearance.object_color)

    def test_topology_replacement_size_and_combined_changes(self):
        obj = self.object(self.mesh_data(_VERTICES, _FACES))
        first, before = self.capture("topology", obj)
        material = self.paint("RB-B replacement", (0.3, 0.2, 0.1, 0.75))

        obj.data = self.mesh_data(_VERTICES, [(0, 1, 3), (1, 2, 3)])
        obj.data.materials.append(material)
        obj.location = (-2.0, 3.0, 4.0)
        obj.color = (0.125, 0.25, 0.375, 0.5)
        self.scene.unit_settings.scale_length = 0.2
        replaced, _ = self.capture(
            "topology", obj,
            MeshChange.TOPOLOGY | MeshChange.TRANSFORM | MeshChange.UNITS | MeshChange.APPEARANCE,
        )
        self.assertEqual(replaced.local_m.shape, first.local_m.shape)
        self.assertEqual(replaced.triangles.shape, first.triangles.shape)
        self.assertFalse(np.array_equal(replaced.triangles, first.triangles))
        for field in ("local_m", "world_m", "triangles"):
            self.assertFalse(np.shares_memory(getattr(first, field), getattr(replaced, field)))
        assert_matches_oracle(first, before)

        for vertices, faces, sizes in (
            (_VERTICES + [(1.5, 1.25, 2.0)], [(0, 1, 4), (1, 2, 4), (2, 3, 4)], (5, 3)),
            (_VERTICES[:3], [(0, 1, 2)], (3, 1)),
            ([], [], (0, 0)),
        ):
            obj.data = self.mesh_data(vertices, faces)
            current, _ = self.capture("topology", obj, MeshChange.TOPOLOGY)
            self.assertEqual((len(current.local_m), len(current.triangles)), sizes)
        assert_matches_oracle(first, before)

    def test_explicit_topology_for_deforming_concave_quad(self):
        first_vertices = [(3, 2, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)]
        second_vertices = [(0, 0, 0), (1, 2, 0), (4, 4, 0), (0, 4, 0)]
        obj = self.object(self.mesh_data(first_vertices, [(0, 1, 2, 3)]))
        first, before = self.capture("quad", obj)
        for vertex, position in zip(obj.data.vertices, second_vertices):
            vertex.co = position
        obj.data.update()
        second, _ = self.capture("quad", obj, MeshChange.VERTICES | MeshChange.TOPOLOGY)
        self.assertEqual(first.triangles.shape, (2, 3))
        self.assertEqual(second.triangles.shape, (2, 3))
        self.assertNotEqual(
            {frozenset(triangle) for triangle in first.triangles},
            {frozenset(triangle) for triangle in second.triangles},
        )
        np.testing.assert_array_equal(second.appearance.triangle_polygon_indices, [0, 0])
        assert_matches_oracle(first, before)

    def test_object_deleted_and_borrowers_keep_owned_arrays(self):
        source = self.mesh_data(_VERTICES, _FACES)
        obj = self.object(source)
        borrowed, expected = self.capture("removed", obj)
        second = self.object(self.mesh_data(_VERTICES, _FACES))
        discard, _ = self.capture("clear", second)
        refs = [weakref.ref(getattr(discard, field)) for field in _ARRAY_FIELDS]
        del discard

        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.evaluated_depsgraph_get()
        self.bridge.remove("removed")
        with self.assertRaises(KeyError):
            self.bridge.get("removed")
        self.assertEqual(len(self.bridge), 1)
        assert_matches_oracle(borrowed, expected)

        self.bridge.clear()
        self.assertEqual(len(self.bridge), 0)
        with self.assertRaises(KeyError):
            self.bridge.get("clear")
        self.assertTrue(all(ref() is None for ref in refs))
        assert_matches_oracle(borrowed, expected)


if __name__ == "__main__":
    result = unittest.main(argv=[__file__], verbosity=2, exit=False)
    if not result.result.wasSuccessful():
        raise RuntimeError("RB-B correctness tests failed")
