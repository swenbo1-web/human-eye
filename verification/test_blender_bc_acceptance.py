"""Parent-owned native RB-B -> BC integration, isolated Blender process only."""
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Matrix
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange
from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance


def cube(name):
    vertices = [(x, y, z) for z in (-.5, .5) for y in (-.5, .5) for x in (-.5, .5)]
    quads = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
             (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))
    faces = [(q[0], q[1], q[2]) for q in quads] + [(q[0], q[2], q[3]) for q in quads]
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def check_witness(case, result, a, b):
    for point, face_id, mesh in ((result.point_a, result.triangle_a, a),
                                 (result.point_b, result.triangle_b, b)):
        case.assertGreaterEqual(face_id, 0)
        case.assertLess(face_id, len(mesh.triangles))
        triangle = mesh.world_m[mesh.triangles[face_id]]
        origin = triangle[0]
        scale = max(np.linalg.norm(triangle - origin, axis=1).max(), 1e-30)
        matrix = np.vstack(((triangle - origin).T / scale, np.ones(3)))
        rhs = np.append((np.asarray(point) - origin) / scale, 1.)
        weights = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
        np.testing.assert_allclose(matrix @ weights, rhs, atol=1e-10, rtol=1e-10)
        case.assertGreaterEqual(weights.min(), -1e-10)
    np.testing.assert_allclose(np.linalg.norm(np.subtract(result.point_a, result.point_b)),
                               result.distance_m, atol=1e-10, rtol=1e-10)


class NativeClearance(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.a, self.b = cube('A'), cube('B')
        self.modifier = self.a.modifiers.new('displacement', 'DISPLACE')
        self.modifier.direction = 'X'
        self.modifier.mid_level = 0.
        self.bridge = BlenderResidentBridge()

    def capture(self):
        graph = bpy.context.evaluated_depsgraph_get()
        scale = bpy.context.scene.unit_settings.scale_length
        flags = MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.UNITS
        return tuple(self.bridge.capture(key, obj, graph, scale, flags)
                     for key, obj in (('A', self.a), ('B', self.b)))

    def test_real_modifier_units_reflection_and_index_refit(self):
        indexes = None
        for scale, sx, displacement in ((.001, 2., .2), (1., -2., .11), (.01, 1.25, -.1)):
            bpy.context.scene.unit_settings.scale_length = scale
            self.a.matrix_world = Matrix(((sx,0,0,-1.), (0,.7,0,0),
                                           (0,0,.6,0), (0,0,0,1)))
            self.b.matrix_world = Matrix(((.75,0,0,2.), (0,1.3,0,0),
                                           (0,0,1.1,0), (0,0,0,1)))
            self.modifier.strength = displacement
            a, b = self.capture()
            if indexes is None:
                indexes = (SurfaceIndex(a.world_m, a.triangles), SurfaceIndex(b.world_m, b.triangles))
            else:
                indexes[0].update(a.world_m)
                indexes[1].update(b.world_m)
            result = surface_distance(*indexes)
            # Separate analytic boxes: x gap is unique axis of separation.
            expected = ((2. - .75 / 2) - (-1. + sx * displacement + abs(sx) / 2)) * scale
            # Native Blender coordinates and properties are float32 before RB capture.
            np.testing.assert_allclose(result.distance_m, expected, rtol=1e-6, atol=1e-9)
            check_witness(self, result, a, b)
            reverse = surface_distance(indexes[1], indexes[0])
            np.testing.assert_allclose(reverse.distance_m, result.distance_m, rtol=1e-10, atol=1e-10)
            check_witness(self, reverse, b, a)

    def test_native_loose_vertex_is_not_surface(self):
        bpy.context.scene.unit_settings.scale_length = 1.
        self.modifier.strength = 0.
        self.a.location.x = .5
        self.b.location.x = 2.5
        # Original A occupies x=[0,1]; insert loose vertex at B's left surface.
        source = self.a.data
        source.vertices.add(1)
        source.vertices[-1].co = (1.5, 0, 0)
        source.update()
        a, b = self.capture()
        result = surface_distance(SurfaceIndex(a.world_m, a.triangles),
                                  SurfaceIndex(b.world_m, b.triangles))
        np.testing.assert_allclose(result.distance_m, 1., atol=1e-12, rtol=1e-12)
        check_witness(self, result, a, b)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NativeClearance))
    if not result.wasSuccessful():
        raise RuntimeError('Native RB-B -> BC checks failed')
