"""Raster coverage, depth occlusion and the actual tiny-yaw Blender regression."""
import copy
import json
from pathlib import Path
import unittest
import warnings
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SpatialAnomalySniffer
from human_eye_plugin.attention_policy import AttentionPolicy
from human_eye_plugin.attention_raster import rasterize_attention
from human_eye_plugin.attention_rendering import _attention_camera, _visible_witness
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.scene_rendering import _projection


def triangle(oid, vertices, color=(220, 80, 20), reverse=False):
    return MeshEntity3D(oid, '#' + oid, oid, np.array(vertices, dtype=float),
                        np.array([[0, 2, 1] if reverse else [0, 1, 2]]),
                        None, color, False)


def live_fixture():
    path = Path(__file__).parent / 'fixes/20261022_attention_cache/live_01/after_snapshot.json'
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    meshes = [MeshEntity3D.from_dict(value) for value in snapshot['meshes']]
    focal = next(mesh for mesh in meshes if mesh.is_focal_target)
    reference = next(mesh for mesh in meshes if mesh.name.endswith('_base'))
    probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
    exact = measure_pair_geometry(focal, reference, need_clearance=True)
    contacts = [{'object_id': reference.object_id, 'measurement_valid': exact['measurement_valid'],
                 'signed_clearance_m': exact['signed_clearance_m'],
                 'point_a_world': probe.point_a_world.tolist(), 'point_b_world': probe.point_b_world.tolist()}]
    def visible(plan):
        view, _, _, _ = _attention_camera(meshes, plan)
        return all(_visible_witness(point, meshes, view, plan['view_span_m'])
                   for point in plan['witness_points_world_m'])
    proposal = AttentionPolicy().propose(meshes, focal_id=focal.object_id, reference_id=reference.object_id,
        contacts=contacts, scene_fingerprint='captured_blender_tiny_yaw_regression',
        quad_size=384, now_s=1, candidate_visible=visible)
    return meshes, proposal


class AttentionRasterTests(unittest.TestCase):
    def setUp(self):
        self.view = np.eye(4)
        self.projection = _projection('orthographic', 1, .08, 10)

    def test_constant_surface_depth_and_true_rgb_geometry(self):
        mesh = triangle('a', [[-2, -2, -2], [2, -2, -2], [0, 2, -2]])
        color, depth = rasterize_attention([mesh], self.view, self.projection, 64)
        self.assertEqual(color.dtype, np.uint8)
        self.assertEqual(depth.dtype, np.float64)
        self.assertEqual(color.shape, (64, 64, 3))
        self.assertAlmostEqual(depth[32, 32], 2)
        self.assertGreater(color[32, 32, 0], color[32, 32, 1])

    def test_sloping_surface_matches_independent_plane_depth(self):
        xy = np.array([[-2, -2], [2, -2], [0, 2]])
        mesh = triangle('sloped', np.c_[xy, -2 - .2 * xy[:, 0] - .3 * xy[:, 1]])
        _, depth = rasterize_attention([mesh], self.view, self.projection, 64)
        row, col = 30, 40
        x, y = 2 * (col + .5) / 63 - 1, 1 - 2 * (row + .5) / 63
        self.assertAlmostEqual(depth[row, col], 2 + .2 * x + .3 * y, places=12)

    def test_full_scene_occluder_wins_in_either_input_order(self):
        back = triangle('back', [[-2, -2, -2], [2, -2, -2], [0, 2, -2]], (0, 0, 255))
        front = triangle('front', [[-2, -2, -1], [2, -2, -1], [0, 2, -1]], (255, 0, 0))
        first_color, first_depth = rasterize_attention([front, back], self.view, self.projection, 64)
        second_color, second_depth = rasterize_attention([back, front], self.view, self.projection, 64)
        np.testing.assert_array_equal(first_color, second_color)
        np.testing.assert_array_equal(first_depth, second_depth)
        self.assertAlmostEqual(first_depth[32, 32], 1)
        self.assertEqual(first_color[32, 32, 2], 0)

    def test_triangles_clipped_before_huge_coordinates_are_integer_cast(self):
        mesh = triangle('huge', [[-1e12, -1, -2], [1e12, -1 + 1e-12, -2], [0, 1e12, -2]])
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            _, depth = rasterize_attention([mesh], self.view, self.projection, 64)
        self.assertEqual(depth[32, 32], 2)
        self.assertGreater(np.count_nonzero(np.isfinite(depth)), 3000)

    def test_near_and_far_planes_clip_partial_triangles(self):
        crossing = triangle('crossing', [[-2, -2, -.01], [2, -2, -2], [0, 2, -20]])
        _, depth = rasterize_attention([crossing], self.view, self.projection, 64)
        actual = depth[np.isfinite(depth)]
        self.assertGreater(len(actual), 10)
        self.assertGreaterEqual(float(actual.min()), .08 - 1e-10)
        self.assertLessEqual(float(actual.max()), 10 + 1e-10)
        for z in (-.01, -20, 1):
            outside = triangle('outside', [[-2, -2, z], [2, -2, z], [0, 2, z]])
            _, empty = rasterize_attention([outside], self.view, self.projection, 64)
            self.assertTrue(np.isinf(empty).all())

    def test_triangle_winding_does_not_enable_xray_or_drop_surfaces(self):
        vertices = [[-2, -2, -2], [2, -2, -2], [0, 2, -2]]
        normal = rasterize_attention([triangle('a', vertices)], self.view, self.projection, 64)
        reverse = rasterize_attention([triangle('a', vertices, reverse=True)], self.view, self.projection, 64)
        np.testing.assert_array_equal(normal[0], reverse[0])
        np.testing.assert_allclose(normal[1], reverse[1])

    def test_large_world_translation_with_equivalent_camera_preserves_depth(self):
        vertices = np.array([[-2, -2, -2], [2, -2, -2], [0, 2, -2]])
        offset = np.array([100000, -50000, 10000])
        changed_view = self.view.copy()
        changed_view[:3, 3] = -offset
        original = rasterize_attention([triangle('a', vertices)], self.view, self.projection, 64)
        shifted = rasterize_attention([triangle('a', vertices + offset)], changed_view, self.projection, 64)
        np.testing.assert_array_equal(original[0], shifted[0])
        np.testing.assert_array_equal(original[1], shifted[1])

    def test_equivalent_rotated_scene_and_camera_keep_metres(self):
        vertices = np.array([[-2, -2, -2], [2, -2, -2], [0, 2, -2]])
        angle = np.deg2rad(37)
        rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0],
                             [-np.sin(angle), 0, np.cos(angle)]])
        changed_view = np.eye(4)
        changed_view[:3, :3] = rotation.T
        original = rasterize_attention([triangle('a', vertices)], self.view, self.projection, 64)
        changed = rasterize_attention([triangle('a', vertices @ rotation.T)], changed_view, self.projection, 64)
        # World-fixed lighting may change; geometric depth must not.
        np.testing.assert_allclose(original[1], changed[1], atol=1e-12)

    def test_inputs_are_not_mutated_and_output_buffers_do_not_alias(self):
        mesh = triangle('a', [[-2, -2, -2], [2, -2, -2], [0, 2, -2]])
        before = copy.deepcopy(mesh.to_dict())
        first = rasterize_attention([mesh], self.view, self.projection, 64)
        snapshots = [value.copy() for value in first]
        second = rasterize_attention([mesh], self.view, self.projection, 64)
        self.assertEqual(mesh.to_dict(), before)
        for actual, snapshot, independent in zip(first, snapshots, second):
            np.testing.assert_array_equal(actual, snapshot)
            self.assertFalse(np.shares_memory(actual, independent))

    def test_budget_and_unsupported_projection_fail_without_partial_output(self):
        mesh = triangle('a', [[-2, -2, -2], [2, -2, -2], [0, 2, -2]])
        with patch('human_eye_plugin.attention_raster.MAX_PIXEL_SAMPLES', 1):
            with self.assertRaisesRegex(ValueError, 'pixel work budget'):
                rasterize_attention([mesh], self.view, self.projection, 64)
        perspective = _projection('perspective', None, .08, 10, 1)
        with self.assertRaises(ValueError):
            rasterize_attention([mesh], self.view, perspective, 64)
        for size in (True, 1, 513):
            with self.assertRaises(ValueError):
                rasterize_attention([mesh], self.view, self.projection, size)

    def test_real_blender_tiny_yaw_snapshot_has_both_witnesses_supported(self):
        meshes, proposal = live_fixture()
        self.assertEqual(proposal['decision'], 'propose', proposal)
        plan = proposal['camera_plan']
        view, projection, _, _ = _attention_camera(meshes, plan)
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            _, depth = rasterize_attention(meshes, view, projection, plan['quad_size'])
        points = np.asarray(plan['witness_points_world_m'])
        clip = (projection @ view @ np.c_[points, np.ones(2)].T).T
        pixels = (clip[:, :2] + 1) * (plan['quad_size'] - 1) / 2
        for index, point in enumerate(points):
            x = int(round(pixels[index, 0]))
            y = int(round(plan['quad_size'] - 1 - pixels[index, 1]))
            patch_depth = depth[y - 2:y + 3, x - 2:x + 3]
            expected = float(-view[2, :3] @ point - view[2, 3])
            tolerance = max(1e-8, 2 * plan['view_span_m'] / (plan['quad_size'] - 1))
            self.assertTrue(np.any(np.abs(patch_depth - expected) <= tolerance),
                            f'Live witness {index} lost from raster; expected depth {expected}')


if __name__ == '__main__':
    unittest.main()
