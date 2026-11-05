"""Reviewer-owned Blender oracle and held-out integration checks.

Run with Blender --background --factory-startup --python-exit-code 1 --python
verification/test_blender_acceptance.py. Does not touch an existing GUI process.
"""
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Matrix
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange


def new_mesh(name, vertices, faces):
    data = bpy.data.meshes.new(name + '_data')
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def lattice(seed=73187, side=7):
    rng = np.random.default_rng(seed)
    xy = np.stack(np.meshgrid(np.linspace(-.9, .8, side),
                              np.linspace(-.4, 1.1, side)), axis=-1).reshape(-1, 2)
    xyz = np.column_stack((xy, rng.normal(0, .035, len(xy))))
    triangles = []
    for j in range(side - 1):
        for i in range(side - 1):
            k = j * side + i
            triangles.extend(((k, k + 1, k + side),
                              (k + 1, k + side + 1, k + side)))
    return xyz.tolist(), triangles


def native_oracle(obj):
    """Independent scalar RNA reads; no candidate conversion helpers/bulk path."""
    graph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(graph)
    mesh = ev.to_mesh()
    try:
        scale = float(bpy.context.scene.unit_settings.scale_length)
        raw = np.array([tuple(v.co) for v in mesh.vertices], dtype=np.float64).reshape(-1, 3)
        matrix = np.array([tuple(row) for row in ev.matrix_world], dtype=np.float64)
        local = raw * scale
        # Explicit scalar sums rather than the candidate's vectorized transform.
        world = np.array([
            [scale * (sum(matrix[r, k] * vertex[k] for k in range(3)) + matrix[r, 3])
             for r in range(3)] for vertex in raw
        ], dtype=np.float64).reshape(-1, 3)
        mesh.calc_loop_triangles()
        tris = np.array([tuple(t.vertices) for t in mesh.loop_triangles], dtype=np.int32).reshape(-1, 3)
        poly_map = np.array([t.polygon_index for t in mesh.loop_triangles], dtype=np.int32)
        poly_mat = np.array([p.material_index for p in mesh.polygons], dtype=np.int32)
        matrix[:3, 3] *= scale
        return dict(local=local, world=world, triangles=tris, matrix=matrix,
                    polygon_map=poly_map, polygon_materials=poly_mat,
                    color=tuple(ev.color),
                    materials=tuple(None if s.material is None else
                                    (s.material.name, tuple(s.material.diffuse_color))
                                    for s in ev.material_slots))
    finally:
        ev.to_mesh_clear()


def assert_geometry(case, view, obj):
    expected = native_oracle(obj)
    for actual, key in ((view.local_m, 'local'), (view.world_m, 'world'),
                        (view.world_from_local, 'matrix')):
        np.testing.assert_allclose(actual, expected[key], rtol=1e-10, atol=1e-10)
    np.testing.assert_array_equal(view.triangles, expected['triangles'])
    case.assertFalse(view.local_m.flags.writeable)
    case.assertFalse(view.world_m.flags.writeable)
    case.assertFalse(view.triangles.flags.writeable)
    appearance = view.appearance
    case.assertEqual(appearance.object_color, expected['color'])
    case.assertEqual(appearance.material_slots, expected['materials'])
    np.testing.assert_array_equal(appearance.polygon_material_indices, expected['polygon_materials'])
    np.testing.assert_array_equal(appearance.triangle_polygon_indices, expected['polygon_map'])
    return expected


def add_materials(obj):
    for i, rgba in enumerate(((.2, .7, .4, 1.), (.8, .15, .4, .6))):
        material = bpy.data.materials.new(obj.name + '_mat_' + str(i))
        material.diffuse_color = rgba
        obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.material_index = poly.index % 2
    obj.color = (.13, .29, .83, .71)


class NativeHeldOut(unittest.TestCase):
    def setUp(self):
        # Only this independent --factory-startup background process is modified.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.unit_settings.scale_length = 1.
        self.bridge = BlenderResidentBridge()

    def capture(self, name, obj, changes=MeshChange.NONE):
        return self.bridge.capture(name, obj, bpy.context.evaluated_depsgraph_get(),
                                   bpy.context.scene.unit_settings.scale_length, changes)

    def test_parent_reflection_modifier_and_units(self):
        obj = new_mesh('heldout_parented', *lattice())
        add_materials(obj)
        parent = bpy.data.objects.new('parent', None)
        bpy.context.scene.collection.objects.link(parent)
        parent.matrix_world = Matrix(((.8, .2, .1, 130.), (.1, -1.7, .3, -.003),
                                      (.0, .1, .7, 2.8), (0., 0., 0., 1.)))
        obj.parent = parent
        obj.location = (.23, -.78, .01)
        obj.scale = (.4, 1.3, 2.1)
        modifier = obj.modifiers.new('deform', 'SIMPLE_DEFORM')
        modifier.deform_method = 'TWIST'
        modifier.deform_axis = 'Z'
        modifier.angle = .73
        bpy.context.scene.unit_settings.scale_length = .0023
        first = self.capture('mesh', obj)
        expected = assert_geometry(self, first, obj)
        raw = np.array([tuple(v.co) for v in obj.data.vertices])
        self.assertGreater(float(np.max(np.abs(expected['local'] / .0023 - raw))), .001)
        old_local = first.local_m.copy()
        parent.location.x += 1.25
        bpy.context.scene.unit_settings.scale_length = 3.7
        changed = self.capture('mesh', obj, MeshChange.TRANSFORM | MeshChange.UNITS)
        self.assertIs(changed.local_m, first.local_m)
        assert_geometry(self, changed, obj)
        np.testing.assert_allclose(changed.local_m, old_local * (3.7 / .0023), rtol=1e-6)

    def test_same_counts_topology_and_quad_retessellation(self):
        verts, faces = lattice(seed=38221, side=4)
        obj = new_mesh('same_count', verts, faces)
        add_materials(obj)
        old = self.capture('mesh', obj)
        before = old.triangles.copy()
        # Equal counts, different index order and winding; no size heuristic is sufficient.
        obj.data.clear_geometry()
        obj.data.from_pydata(verts, [], [(a, c, b) for a, b, c in reversed(faces)])
        obj.data.update()
        new = self.capture('mesh', obj, MeshChange.TOPOLOGY)
        assert_geometry(self, new, obj)
        self.assertFalse(np.array_equal(before, new.triangles))
        np.testing.assert_array_equal(old.triangles, before)
        quad = new_mesh('quad', [(-1,-1,0), (1,-1,0), (1,1,0), (-1,1,0)], [(0,1,2,3)])
        cold_quad = self.capture('quad', quad)
        # No oracle or calc_loop_triangles has touched this mesh before capture.
        self.assertEqual(cold_quad.triangles.shape, (2, 3))
        assert_geometry(self, cold_quad, quad)
        quad.data.vertices[1].co = (-.2, .3, .1)
        quad.data.update()
        quad_view = self.capture('quad', quad, MeshChange.VERTICES | MeshChange.TOPOLOGY)
        assert_geometry(self, quad_view, quad)

    def test_cold_concave_ngon(self):
        ngon = new_mesh('cold_ngon', [(0,0,0), (2,0,0), (2,1,0),
                                     (1,.4,0), (1,2,0), (0,2,0)], [(0,1,2,3,4,5)])
        captured = self.capture('ngon', ngon)
        self.assertEqual(captured.triangles.shape, (4, 3))
        assert_geometry(self, captured, ngon)
        ngon.data.vertices[3].co = (.4, .7, .12)
        ngon.data.update()
        changed = self.capture('ngon', ngon, MeshChange.TOPOLOGY)
        assert_geometry(self, changed, ngon)

    def test_appearance_slot_reorder_and_face_assignment(self):
        obj = new_mesh('material_cases', *lattice(seed=2819, side=3))
        add_materials(obj)
        first = self.capture('a', obj)
        before = first.world_m.copy()
        a, b = obj.data.materials[:]
        obj.data.materials[0] = b
        obj.data.materials[1] = a
        b.diffuse_color = (.91, .12, .07, .44)
        obj.color = (.3, .1, .6, 1.)
        for p in obj.data.polygons:
            p.material_index = 1 - p.material_index
        obj.data.update()
        updated = self.capture('a', obj, MeshChange.APPEARANCE)
        assert_geometry(self, updated, obj)
        self.assertIs(first.local_m, updated.local_m)
        self.assertIs(first.triangles, updated.triangles)
        np.testing.assert_array_equal(before, updated.world_m)

    def test_evaluated_animation_and_mixed_change(self):
        obj = new_mesh('animated', *lattice(seed=99143, side=5))
        add_materials(obj)
        obj.shape_key_add(name='Basis')
        key = obj.shape_key_add(name='Deformation')
        for point in key.data:
            point.co.z += .07 * point.co.x + .13 * point.co.y
        key.value = 0.
        key.keyframe_insert('value', frame=1)
        key.value = 1.
        key.keyframe_insert('value', frame=9)
        previous = None
        for frame in (1, 3, 8, 4, 9):
            bpy.context.scene.frame_set(frame)
            obj.location.y = frame * .017
            obj.color[0] = frame / 10
            bpy.context.scene.unit_settings.scale_length = frame * .013
            view = self.capture('a', obj, MeshChange.VERTICES | MeshChange.TRANSFORM |
                                MeshChange.UNITS | MeshChange.APPEARANCE)
            assert_geometry(self, view, obj)
            if previous is not None:
                self.assertFalse(np.array_equal(previous, view.world_m))
            previous = view.world_m.copy()

    def test_object_isolation_and_owned_lifecycle(self):
        one = new_mesh('one', *lattice(seed=82, side=4))
        two = new_mesh('two', *lattice(seed=83, side=4))
        first = self.capture('one', one)
        second = self.capture('two', two)
        snapshot = second.world_m.copy()
        one.data.vertices[3].co.z += 1.7
        one.data.update()
        updated = self.capture('one', one, MeshChange.VERTICES)
        assert_geometry(self, updated, one)
        np.testing.assert_array_equal(second.world_m, snapshot)
        self.assertIs(self.capture('two', two), second)
        bpy.data.objects.remove(two, do_unlink=True)
        self.bridge.remove('two')
        np.testing.assert_array_equal(second.world_m, snapshot)
        retained = first.world_m.copy()
        self.bridge.clear()
        np.testing.assert_array_equal(first.world_m, retained)
        self.assertEqual(len(self.bridge), 0)

    def test_empty_topology_growth_and_shrink(self):
        obj = new_mesh('empty', [], [])
        empty = self.capture('empty', obj)
        assert_geometry(self, empty, obj)
        self.assertEqual(empty.world_m.shape, (0, 3))
        obj.data.from_pydata([(0,0,0), (1,0,0), (0,1,0)], [], [(0,1,2)])
        obj.data.update()
        grown = self.capture('empty', obj, MeshChange.TOPOLOGY)
        assert_geometry(self, grown, obj)
        self.assertEqual(grown.triangles.shape, (1, 3))
        obj.data.clear_geometry()
        obj.data.update()
        shrunk = self.capture('empty', obj, MeshChange.TOPOLOGY)
        assert_geometry(self, shrunk, obj)
        self.assertEqual(shrunk.world_m.shape, (0, 3))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeHeldOut)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun == 0:
        raise RuntimeError('Held-out Blender checks failed or were not populated')
