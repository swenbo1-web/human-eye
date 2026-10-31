"""Adaptive visual evidence, scale fidelity, and legacy cache isolation."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, QuadCognitiveCanvasCompositor
from human_eye_plugin.scene_rendering import render_scene_canvas, _SceneRasterizer
from verification.test_auto_router import scene


def meshes(offset=(0, 0, 0), scale=1):
    result = []
    for item in scene()['meshes']:
        item['vertices'] = (np.asarray(item['vertices']) * scale + offset).tolist()
        if item.get('pivot_world') is not None:
            item['pivot_world'] = (np.asarray(item['pivot_world']) * scale + offset).tolist()
        result.append(MeshEntity3D.from_dict(item))
    return result


class SceneRenderingTests(unittest.TestCase):
    def test_translation_keeps_geometry_pixels_in_all_four_views(self):
        for offset in ((0, 0, 0), (3, 0, 0), (10, -9, 15), (100000, -50000, 10000)):
            with self.subTest(offset=offset):
                image, metadata = render_scene_canvas(meshes(offset), 64, focal_id='part', reference_id='base')
                self.assertEqual(image.size, (128, 128))
                self.assertTrue(all(view['geometry_depth_pixels'] > 10 for view in metadata['views']))
                self.assertTrue(all(view['geometry_pixels_unchanged_by_annotations'] > 10
                                    for view in metadata['views']))
                self.assertEqual(metadata['focus_scope'], 'target_pair_focus')

    def test_millimetres_and_buildings_keep_real_units_and_geometry_pixels(self):
        for scale in (.001, .01, 100, 10000):
            with self.subTest(scale=scale):
                _, metadata = render_scene_canvas(meshes(scale=scale), 64)
                self.assertFalse(metadata['geometry_scaled'])
                np.testing.assert_allclose(metadata['scene_bbox_max_m'], [.7 * scale, .6 * scale, .4 * scale])
                self.assertTrue(all(view['geometry_depth_pixels'] > 10 for view in metadata['views']))
                self.assertTrue(all(view['geometry_pixels_unchanged_by_annotations'] > 10
                                    for view in metadata['views']))
                self.assertEqual(metadata['unit'], 'm')

    def test_all_scene_vertices_fit_overview_camera_bounds(self):
        values = meshes((10, 20, 30), scale=100)
        _, metadata = render_scene_canvas(values, 64)
        points = np.c_[np.vstack([mesh.vertices for mesh in values]),
                       np.ones(sum(len(mesh.vertices) for mesh in values))]
        for camera in metadata['views'][:3]:
            clip = (np.asarray(camera['projection_matrix']) @ np.asarray(camera['view_matrix']) @ points.T).T
            ndc = clip[:, :3] / clip[:, 3:]
            self.assertLessEqual(float(np.max(np.abs(ndc[:, :2]))), 1.)
            self.assertTrue(np.all(ndc[:, 2] >= -1))
            self.assertTrue(np.all(ndc[:, 2] <= 1))

    def test_orthographic_scale_and_perspective_target_plane_scale_are_distinct(self):
        _, metadata = render_scene_canvas(meshes(), 128)
        for camera in metadata['views'][:2]:
            self.assertAlmostEqual(camera['m_per_pixel'] * 127, camera['view_span_m'])
            self.assertAlmostEqual(camera['scale_bar']['length_m'],
                                   camera['scale_bar']['pixels'] * camera['m_per_pixel'])
        for camera in metadata['views'][2:]:
            self.assertNotIn('m_per_pixel', camera)
            self.assertIn('target_plane_m_per_pixel', camera)
            self.assertNotIn('scale_bar', camera)

    def test_no_legacy_probe_or_quad_controller_is_invoked(self):
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance',
                   side_effect=AssertionError('No contact measurement belongs in rendering')):
            with patch.object(QuadCognitiveCanvasCompositor, 'render_quad_cognitive_canvas',
                              side_effect=AssertionError('No legacy controller')):
                _, metadata = render_scene_canvas(meshes(), 64)
        self.assertFalse(metadata['measurement_overlay'])
        self.assertFalse(metadata['action_prescription_overlay'])
        self.assertFalse(metadata['visibility_certified'])

    def test_scene_data_and_legacy_pool_matrices_are_unchanged(self):
        original = QuadCognitiveCanvasCompositor(64)
        old_top = original._v_top.copy()
        old_projection = original._p_ortho_top.copy()
        old_buffers = original._quad_rgb_scratch.copy()
        old_pool = {key: id(value) for key, value in QuadCognitiveCanvasCompositor._QUAD_RES_POOL.items()}
        values = meshes((10, 20, 30), scale=.001)
        before = [copy.deepcopy(value.to_dict()) for value in values]
        render_scene_canvas(values, 64)
        self.assertEqual([value.to_dict() for value in values], before)
        np.testing.assert_array_equal(original._v_top, old_top)
        np.testing.assert_array_equal(original._p_ortho_top, old_projection)
        np.testing.assert_array_equal(original._quad_rgb_scratch, old_buffers)
        self.assertEqual({key: id(value) for key, value in QuadCognitiveCanvasCompositor._QUAD_RES_POOL.items()}, old_pool)

    def test_private_rasterizer_scratch_buffers_do_not_alias(self):
        first, second = _SceneRasterizer(64), _SceneRasterizer(64)
        self.assertIsNot(first._px_centers, second._px_centers)
        for name in ('_f64_buf1', '_i32_buf1'):
            self.assertIsNot(getattr(first, name), getattr(second, name))
            self.assertIsNot(getattr(first, name), getattr(QuadCognitiveCanvasCompositor,
                                                         '_SHARED_F64_BUF1' if 'f64' in name else '_SHARED_I32_BUF1'))

    def test_independent_calls_keep_earlier_image_unchanged(self):
        first, _ = render_scene_canvas(meshes(), 64)
        before = np.asarray(first).copy()
        render_scene_canvas(meshes((100, -50, 20), 100), 64)
        np.testing.assert_array_equal(np.asarray(first), before)

    def test_single_object_focus_and_json_metadata(self):
        _, metadata = render_scene_canvas(meshes()[1:], 64, focal_id='part')
        self.assertEqual(metadata['focus_scope'], 'single_target_focus')
        self.assertEqual(metadata['views'][3]['target_object_ids'], ['part'])
        self.assertEqual(json.loads(json.dumps(metadata, allow_nan=False)), metadata)
        self.assertTrue(all(not view['labels_certify_visibility'] for view in metadata['views']))

    def test_unknown_identical_or_empty_targets_are_rejected(self):
        for kwargs in ({'focal_id': 'unknown'}, {'focal_id': 'part', 'reference_id': 'part'}):
            with self.assertRaises(ValueError):
                render_scene_canvas(meshes(), 64, **kwargs)
        with self.assertRaises(ValueError):
            render_scene_canvas([], 64)

    def test_size_and_type_budget_is_checked(self):
        for size in (True, 32, 513, 64.0):
            with self.assertRaises(ValueError):
                render_scene_canvas(meshes(), size)
        with self.assertRaises(TypeError):
            render_scene_canvas([{}], 64)

    def test_work_budget_is_checked_before_any_mesh_copy_or_raster(self):
        values = meshes()
        with patch('human_eye_plugin.scene_rendering.work_budget_status',
                   return_value={'within_budget': False}):
            with patch.object(MeshEntity3D, 'from_dict', side_effect=AssertionError('No allocation')):
                with self.assertRaisesRegex(ValueError, 'resource budget'):
                    render_scene_canvas(values, 64)

    def test_duplicate_faces_cannot_bypass_raster_scanline_memory_limit(self):
        value = meshes()[0]
        value.faces = np.tile(value.faces, (400, 1))
        with patch('human_eye_plugin.scene_rendering.work_budget_status',
                   return_value={'within_budget': True}):
            with patch.object(_SceneRasterizer, '_rasterize_meshes_zbuffer',
                              side_effect=AssertionError('No unbounded raster')):
                with self.assertRaisesRegex(ValueError, 'resource budget'):
                    render_scene_canvas([value], 128)


if __name__ == '__main__':
    unittest.main()
