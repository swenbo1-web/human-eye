"""Targeted host-bridge checks with mocked raster and explicit unit images.

Frozen camera JSON is migration evidence read by tests. The product API uses
captured geometry directly. No Blender process or real raster is started here.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import active_observation_host as host_core
from human_eye_plugin.active_observation import geometry
from human_eye_plugin.active_observation_images import _meshes_from_objects


HERE = Path(__file__).resolve().parent


def panel_capture():
    return {
        'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'revision': 'unit-capture:1',
        'host_identity': {'schema_version': '1.0', 'document_epoch': 'a' * 64,
                          'capture_scope': 'complete_scene_meshes',
                          'object_instances': {'host-panel': '101'}},
        'capture_state': {'instance_id': 'unit-host', 'epoch': 1, 'revision': 1, 'selection_key': 'scene'},
        'meshes': [{'object_id': 'host-panel', 'name': 'Shared panel',
                    'vertices': [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
                    'faces': [[0, 1, 2], [0, 2, 3]]}],
    }


def synthetic_raster(events=None):
    if events is not None:
        events.append('mocked_raster')
    color = np.empty((512, 512, 3), dtype=np.uint8)
    color[:] = (18, 22, 30)
    depth = np.full((512, 512), np.inf, dtype=np.float64)
    owners = np.full((512, 512), -1, dtype=np.int32)
    color[250:254, 250:254] = (180, 190, 205)
    depth[250:254, 250:254] = 2
    owners[250:254, 250:254] = 0
    return color, depth, owners


class ActiveObservationHostTests(unittest.TestCase):
    def test_camera_formula_matches_frozen_full_scene(self):
        scene = json.loads((HERE / 'm4_active_coverage_003/inputs/SCENE_GEOMETRY_RATIONAL.json').read_bytes())
        expected = json.loads((HERE / 'm4_active_coverage_003/inputs/CAMERAS.json').read_bytes())
        objects, _, _ = geometry(scene)
        cameras = host_core.freeze_cameras(_meshes_from_objects(objects))
        self.assertEqual(cameras['views'], expected['views'])
        self.assertEqual(cameras['directions'], expected['directions'])
        self.assertEqual(cameras['common_center_world_m'], expected['common_center_world_m'])
        self.assertEqual(cameras['margin'], expected['margin'])

    def test_one_parse_and_one_shared_mesh_conversion(self):
        capture = panel_capture()
        events = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(host_core, 'geometry', wraps=geometry) as parse:
                with patch.object(host_core, '_meshes_from_objects', wraps=_meshes_from_objects) as convert:
                    with patch('human_eye_plugin.active_observation_images._meshes_from_objects',
                               side_effect=AssertionError('prepared meshes must be shared')) as duplicate:
                        with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                                   side_effect=lambda *args, **kwargs: synthetic_raster(events)) as raster:
                            result = host_core.observe_capture(
                                capture, directory,
                                construction_callback=lambda view: events.append('intent:' + view),
                            )
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(convert.call_count, 1)
            duplicate.assert_not_called()
            self.assertEqual(raster.call_count, 1)
            self.assertEqual(events, ['intent:SCENE', 'mocked_raster'])
            self.assertEqual(result['work']['geometry_parse_calls'], 1)
            self.assertEqual(result['work']['prepare_calls'], 1)
            self.assertEqual(result['work']['local_verified_images'], 1)
            self.assertEqual(len(result['facts']['coverage']['covered_roi_ids']), 1)
            pixel = result['facts']['observations'][0]['pixel_rows'][0]
            self.assertEqual(pixel['host_id'], 'host-panel')
            self.assertEqual(pixel['visible_surface_pixels'], 16)
            self.assertEqual((pixel['minimum_surface_pixels'], pixel['minimum_boundary_pixels'],
                              pixel['minimum_rgb_boundary_contrast']), (16, 4, 24))
            self.assertNotIn('triangle_indices', pixel)
            self.assertIn('actual_raster', result['frames'][0]['stages'])
            self.assertIn('readability', result['frames'][0]['feedback_stages'])

    def test_no_supported_roi_has_unknown_scope_and_no_raster(self):
        capture = panel_capture()
        capture['meshes'][0]['vertices'][3][2] = .125
        with tempfile.TemporaryDirectory() as directory:
            with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
                result = host_core.observe_capture(capture, directory)
            raster.assert_not_called()
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['observation_status'], 'no_supported_regions')
        self.assertEqual(result['frames'], [])
        self.assertEqual(result['work']['raster_attempts'], 0)
        self.assertEqual(result['facts']['scope']['supported_roi_object_count'], 0)
        self.assertEqual(result['facts']['scope']['objects_without_supported_roi'][0]['host_id'], 'host-panel')

    def test_text_only_keeps_coverage_unobserved(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
                result = host_core.observe_capture(panel_capture(), directory, include_image=False)
            raster.assert_not_called()
        self.assertEqual(result['status'], 'predicted')
        self.assertEqual(result['observation_status'], 'prediction_only')
        self.assertEqual(result['facts']['coverage']['covered_roi_ids'], [])
        self.assertEqual(result['facts']['coverage']['observed_views'], [])
        self.assertEqual(result['frames'], [])

    def test_rename_keeps_geometry_but_changes_source_and_image_reference(self):
        first = panel_capture()
        changed = copy.deepcopy(first)
        changed['revision'] = 'unit-capture:2'
        changed['capture_state']['revision'] = 2
        changed['meshes'][0]['name'] = 'Renamed panel'
        self.assertNotEqual(host_core.source_binding(first), host_core.source_binding(changed))
        with tempfile.TemporaryDirectory() as directory:
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       side_effect=lambda *args, **kwargs: synthetic_raster()):
                before = host_core.observe_capture(first, directory)
                after = host_core.observe_capture(changed, directory)
        self.assertEqual(before['facts']['scene_identity'], after['facts']['scene_identity'])
        self.assertEqual(before['facts']['candidate_identity'], after['facts']['candidate_identity'])
        self.assertEqual(before['frames'][0]['image_sha256'], after['frames'][0]['image_sha256'])
        self.assertNotEqual(before['frames'][0]['image_ref'], after['frames'][0]['image_ref'])
        self.assertNotEqual(before['frames'][0]['image_path'], after['frames'][0]['image_path'])
        self.assertEqual(after['facts']['regions'][0]['object_name'], 'Renamed panel')
        self.assertEqual(after['facts']['observations'][0]['image_ref'], after['frames'][0]['image_ref'])


if __name__ == '__main__':
    unittest.main()
