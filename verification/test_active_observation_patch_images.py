"""Patch feedback regressions with synthetic buffers and mocked raster calls.

All PNG/NPZ files in these tests are synthetic fixture publications. The real
attention raster is never invoked by a test in this module.
"""

import ast
import copy
import inspect
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.active_observation import prepare_scene
from human_eye_plugin.active_observation_images import (
    ActiveObservationImages, PATCH_MAPPING_VERSION, _aggregate_patch_pixels,
)
from human_eye_plugin import attention_raster
from verification.test_active_observation_images import camera_pool, saved_frame, synthetic_buffers, subdivided_scene


def joined_scene():
    return {'objects': [{'name': 'Parallel patches and unsupported triangle',
                         'vertices': [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0],
                                      [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
                                      [2, 0, 0], [3, 0, 0], [2, 1, 0]],
                         'triangles': [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [8, 9, 10]]}]}


def winner_buffers(session):
    front = next(index for index, region in enumerate(session.regions)
                 if all(point[2] == 1 for point in region.vertices))
    values = synthetic_buffers()
    values['depth'][values['owners'] >= 0] = 1
    values['patch_owners'] = np.full((64, 64), -1, dtype=np.int32)
    values['patch_owners'][values['owners'] >= 0] = front
    return values


class ActiveObservationPatchImageTests(unittest.TestCase):
    def test_same_object_visible_patch_cannot_credit_hidden_patch(self):
        session = prepare_scene(joined_scene(), camera_pool())
        self.assertEqual(len(session.regions), 2)
        buffers = winner_buffers(session)
        with tempfile.TemporaryDirectory() as folder:
            images = ActiveObservationImages(session, folder)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners', 'patch_owners'))) as raster:
                frame = images.render_view('SCENE')
                feedback = images.observe_frame(frame)
                self.assertIs(images.render_view('SCENE'), frame)
                self.assertEqual(raster.call_count, 1)
                self.assertTrue(raster.call_args.kwargs['return_owner'])
                self.assertTrue(raster.call_args.kwargs['return_patch_owner'])
                self.assertEqual(raster.call_args.kwargs['face_patch_ids'][0][-1], -1)
            by_id = {row['roi_id']: row for row in feedback['pixel_rows']}
            for region in session.regions:
                expected = 16 if all(point[2] == 1 for point in region.vertices) else 0
                self.assertEqual(by_id[region.roi_id]['visible_surface_pixels'], expected)
                self.assertEqual(by_id[region.roi_id]['readable'], expected == 16)
            self.assertEqual(frame['patch_mapping_version'], PATCH_MAPPING_VERSION)
            self.assertEqual(frame['patch_owner_array_bytes'], 64 * 64 * 4)
            self.assertGreater(frame['patch_mapping_array_bytes'], 0)
            self.assertEqual(frame['array_payload_bytes'], sum(row['nbytes'] for row in frame['arrays'].values()))
            with np.load(frame['arrays_path'], allow_pickle=False) as stored:
                self.assertTrue(np.array_equal(stored['patch_owners'], buffers['patch_owners']))
                self.assertEqual(stored['patch_mapping_identity'].item(), frame['patch_mapping_identity'])
                self.assertEqual(stored['patch_roi_ids'].tolist(), frame['patch_roi_ids'])

    def test_shared_boundary_counts_true_patch_contrast_and_no_internal_seams(self):
        colors = np.full((64, 64, 3), 100, dtype=np.uint8)
        owners = np.full((64, 64), -1, dtype=np.int32)
        owners[20:24, 20:24] = 0
        owners[20:24, 24:28] = 1
        colors[20:24, 24:28] = 200
        result = _aggregate_patch_pixels(colors, owners, 2)
        self.assertEqual(result['visible_surface_pixels'].tolist(), [16, 16])
        self.assertEqual(result['contrasting_boundary_pixels'][0], 4)
        self.assertGreaterEqual(result['contrasting_boundary_pixels'][1], 4)
        # A high-contrast colour seam inside the same patch has no ownership
        # boundary and cannot become readability evidence.
        owners[20:24, 24:28] = 0
        result = _aggregate_patch_pixels(colors, owners, 2)
        self.assertEqual(result['visible_surface_pixels'].tolist(), [32, 0])
        colors[:] = 100
        result = _aggregate_patch_pixels(colors, owners, 2)
        self.assertEqual(result['contrasting_boundary_pixels'].tolist(), [0, 0])
        owners[:] = 0
        colors[:, 32:] = 200
        result = _aggregate_patch_pixels(colors, owners, 2)
        self.assertEqual(result['contrasting_boundary_pixels'].tolist(), [0, 0])

    def test_pixel_feedback_aggregates_once_and_keeps_negative_rows(self):
        session = prepare_scene(joined_scene(), camera_pool())
        buffers = winner_buffers(session)
        with tempfile.TemporaryDirectory() as folder:
            images = ActiveObservationImages(session, folder)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners', 'patch_owners'))):
                frame = images.render_view('SCENE')
            with patch('human_eye_plugin.active_observation_images._aggregate_patch_pixels',
                       wraps=_aggregate_patch_pixels) as aggregate:
                feedback = images.observe_frame(frame)
                self.assertEqual(aggregate.call_count, 1)
            self.assertEqual(len(feedback['pixel_rows']), 2)
            self.assertEqual(sum(row['visible_surface_pixels'] == 0 for row in feedback['pixel_rows']), 1)

    def test_face_order_change_invalidates_saved_mapping_and_cache(self):
        scene = joined_scene()
        session = prepare_scene(scene, camera_pool())
        buffers = winner_buffers(session)
        with tempfile.TemporaryDirectory() as folder:
            images = ActiveObservationImages(session, folder)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners', 'patch_owners'))):
                first = images.render_view('SCENE')
                first_observation = images.observe_frame(first)
                self.assertFalse(first_observation['update']['reused'])
                self.assertEqual(session.summary()['state_updates'], 1)
                self.assertIsNone(session.next_view())
                changed = copy.deepcopy(scene)
                changed['objects'][0]['triangles'].reverse()
                self.assertFalse(session.rebind(changed, camera_pool()))
                self.assertEqual(session.summary()['observed_views'], [])
                self.assertEqual(session.summary()['covered_roi_ids'], [])
                self.assertEqual(session.summary()['state_updates'], 0)
                with self.assertRaisesRegex(ValueError, 'patch_mapping'):
                    session.observe(first_observation['receipt'])
                select = session.next_view

                def select_after_synchronization():
                    self.assertNotEqual(images._patch_mapping_identity, first['patch_mapping_identity'])
                    self.assertEqual(session.state.patch_mapping_identity, images._patch_mapping_identity)
                    return select()

                with patch.object(session, 'next_view', side_effect=select_after_synchronization):
                    second = images.render_next()
                self.assertIsNotNone(second)
                second_observation = images.observe_frame(second)
                self.assertFalse(second_observation['update']['reused'])
                self.assertEqual(session.summary()['observed_views'], ['SCENE'])
                self.assertEqual(session.summary()['state_updates'], 1)
                self.assertEqual(len(session.summary()['covered_roi_ids']), 1)
                with self.assertRaisesRegex(ValueError, 'patch_mapping'):
                    session.observe(first_observation['receipt'])
            self.assertNotEqual(first['patch_mapping_identity'], second['patch_mapping_identity'])
            self.assertNotEqual(first['image_ref'], second['image_ref'])
            self.assertEqual(first['image_sha256'], second['image_sha256'])
            with self.assertRaisesRegex(ValueError, 'saved_patch_mapping_mismatch'):
                images.observe_frame(first)

    def test_saved_owner_mapping_and_frame_identity_are_checked(self):
        session = prepare_scene(joined_scene(), camera_pool())
        buffers = winner_buffers(session)
        with tempfile.TemporaryDirectory() as folder:
            images = ActiveObservationImages(session, folder)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners', 'patch_owners'))):
                frame = images.render_view('SCENE')
            changed = dict(frame, patch_mapping_identity='0' * 64)
            with self.assertRaisesRegex(ValueError, 'current_patch_mapping_frame_required'):
                images.observe_frame(changed)
            changed = dict(frame)
            changed['buffers'] = {key: value.copy() for key, value in frame['buffers'].items()}
            changed['buffers']['patch_owners'][20, 20] = -1
            with self.assertRaisesRegex(ValueError, 'frame_array_payload_mismatch'):
                images.observe_frame(changed)

    def test_legacy_three_buffers_only_support_whole_object_single_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            simple = prepare_scene(subdivided_scene(), camera_pool())
            frame = saved_frame(simple, folder, synthetic_buffers())
            result = ActiveObservationImages(simple, folder).observe_frame(frame)
            self.assertEqual(result['pixel_rows'][0]['visible_surface_pixels'], 16)
        with tempfile.TemporaryDirectory() as folder:
            multiple = prepare_scene(joined_scene(), camera_pool())
            frame = saved_frame(multiple, folder, synthetic_buffers())
            with self.assertRaisesRegex(ValueError, 'patch_owner_frame_required'):
                ActiveObservationImages(multiple, folder).observe_frame(frame)

    def test_existing_raster_return_contract_and_same_winner_assignment(self):
        signature = inspect.signature(attention_raster.rasterize_attention)
        self.assertFalse(signature.parameters['return_owner'].default)
        self.assertFalse(signature.parameters['return_patch_owner'].default)
        self.assertIsNone(signature.parameters['face_patch_ids'].default)
        tree = ast.parse(inspect.getsource(attention_raster._raster_triangle))
        assignments = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript):
                source = ast.unparse(node.targets[0])
                if source.startswith(('section[', 'owners[', 'patch_owners[')):
                    assignments[source.split('[', 1)[0]] = ast.unparse(node.targets[0].slice)
        self.assertEqual(assignments, {'section': 'nearer', 'owners': 'nearer', 'patch_owners': 'nearer'})


if __name__ == '__main__':
    unittest.main()
