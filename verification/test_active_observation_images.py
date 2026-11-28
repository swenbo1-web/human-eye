"""Targeted installed-API image feedback checks using synthetic test buffers.

The raster function is mocked. These temporary PNG/NPZ files are unit fixtures,
so the finite real-raster acceptance budget is reserved for the integration run.
"""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin.active_observation import prepare_scene
from human_eye_plugin.active_observation_images import ActiveObservationImages


def subdivided_scene():
    vertices = [[x, y, 0] for y in (-1, 0, 1) for x in (-1, 0, 1)]
    faces = []
    for row in range(2):
        for column in range(2):
            first = row * 3 + column
            faces.extend([[first, first + 1, first + 4], [first, first + 4, first + 3]])
    return {'objects': [{'name': 'Subdivided panel', 'vertices': vertices, 'triangles': faces}]}


def camera_pool():
    return {'views': [{
        'name': 'SCENE',
        'direction_rational': [0, 0, 1],
        'target_to_eye_unit': [0, 0, 1],
        'view_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]],
        'projection_matrix': [[.5, 0, 0, 0], [0, .5, 0, 0], [0, 0, .2, 0], [0, 0, 0, 1]],
        'size_px': [64, 64],
    }]}


def synthetic_buffers(count=16, contrast=True):
    color = np.empty((64, 64, 3), dtype=np.uint8)
    color[:] = (18, 22, 30)
    depth = np.full((64, 64), np.inf, dtype=np.float64)
    owners = np.full((64, 64), -1, dtype=np.int32)
    for index in range(count):
        row, column = 20 + index // 4, 20 + index % 4
        owners[row, column] = 0
        depth[row, column] = 2
        if contrast:
            color[row, column] = (180, 190, 205)
    return {'color': color, 'depth': depth, 'owners': owners}


def saved_frame(session, directory, buffers):
    image = Path(directory) / 'synthetic-unit.png'
    arrays = Path(directory) / 'synthetic-unit.npz'
    Image.fromarray(buffers['color'], mode='RGB').save(image)
    np.savez_compressed(arrays, **buffers)
    return {
        'scene_identity': session.scene_identity,
        'candidate_identity': session.candidate_identity,
        'view_name': 'SCENE',
        'image_path': str(image),
        'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
        'image_ref': 'synthetic-unit-frame',
        'arrays_path': str(arrays),
        'arrays_sha256': hashlib.sha256(arrays.read_bytes()).hexdigest(),
    }


class ActiveObservationImageTests(unittest.TestCase):
    def test_full_subdivision_and_repeated_frame_use_one_raster(self):
        session = prepare_scene(subdivided_scene(), camera_pool())
        buffers = synthetic_buffers()
        with tempfile.TemporaryDirectory() as directory:
            images = ActiveObservationImages(session, directory)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners'))) as raster:
                frame = images.render_next()
                self.assertEqual(len(images.meshes[0].vertices), 9)
                self.assertEqual(len(images.meshes[0].faces), 8)
                self.assertEqual(images.meshes[0].faces.tolist(), subdivided_scene()['objects'][0]['triangles'])
                first = images.observe_frame(frame)
                repeated = images.observe_frame(frame)
                self.assertIs(images.render_view('SCENE'), frame)
                prior_meshes = images.meshes
                self.assertFalse(session.rebind(subdivided_scene(), camera_pool()))
                self.assertIs(images.render_view('SCENE'), frame)
                self.assertIsNot(images.meshes, prior_meshes)
                self.assertEqual(raster.call_count, 1)
            self.assertEqual(len(first['update']['new_roi_ids']), 1)
            self.assertTrue(repeated['update']['reused'])
            self.assertEqual(session.summary()['state_updates'], 1)
            row = first['pixel_rows'][0]
            self.assertEqual(row['visible_surface_pixels'], 16)
            self.assertGreaterEqual(row['contrasting_boundary_pixels'], 4)
            self.assertTrue(row['front_facing'])
            self.assertTrue(row['readable'])
            self.assertEqual((row['source_vertices'], row['source_triangles']), (9, 8))
            self.assertEqual(first['receipt']['image_ref'], frame['image_ref'])
            facts = session.short_facts()
            pixel_fact = facts['observations'][0]['pixel_rows'][0]
            self.assertNotIn('triangle_indices', pixel_fact)
            self.assertEqual(pixel_fact['visible_surface_pixels'], 16)
            self.assertEqual(facts['regions'][0]['object_name'], 'Subdivided panel')
            self.assertIsNone(images.render_next())

    def test_saved_frame_replay_requires_actual_pixel_thresholds(self):
        for count, contrast in ((16, True), (15, True), (16, False)):
            with self.subTest(surface_pixels=count, contrast=contrast):
                session = prepare_scene(subdivided_scene(), camera_pool())
                with tempfile.TemporaryDirectory() as directory:
                    images = ActiveObservationImages(session, directory)
                    frame = saved_frame(session, directory, synthetic_buffers(count, contrast))
                    with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
                        result = images.observe_frame(frame)
                        raster.assert_not_called()
                    readable = count >= 16 and contrast
                    self.assertEqual(result['pixel_rows'][0]['readable'], readable)
                    self.assertEqual(len(result['update']['new_roi_ids']), int(readable))
                    self.assertEqual(result['receipt']['image_ref'], 'synthetic-unit-frame')

    def test_source_rebind_rejects_prior_frame_before_feedback(self):
        session = prepare_scene(subdivided_scene(), camera_pool())
        with tempfile.TemporaryDirectory() as directory:
            images = ActiveObservationImages(session, directory)
            frame = saved_frame(session, directory, synthetic_buffers())
            first = images.observe_frame(frame)
            changed = copy.deepcopy(subdivided_scene())
            for point in changed['objects'][0]['vertices']:
                point[2] += 1
            self.assertTrue(session.rebind(changed, camera_pool()))
            with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
                with self.assertRaisesRegex(ValueError, 'current_scene_camera_frame_required'):
                    images.observe_frame(frame)
                raster.assert_not_called()
            self.assertEqual(session.summary()['state_updates'], 0)
            self.assertEqual(session.summary()['covered_roi_ids'], [])
            with self.assertRaisesRegex(ValueError, 'actual_bound_image_receipt_required'):
                session.observe(first['receipt'])

    def test_saved_owner_and_in_process_buffer_must_match(self):
        session = prepare_scene(subdivided_scene(), camera_pool())
        with tempfile.TemporaryDirectory() as directory:
            images = ActiveObservationImages(session, directory)
            buffers = synthetic_buffers()
            frame = saved_frame(session, directory, buffers)
            frame['buffers'] = {key: values.copy() for key, values in buffers.items()}
            frame['buffers']['owners'][20, 20] = -1
            frame['buffers']['depth'][20, 20] = np.inf
            with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
                with self.assertRaisesRegex(ValueError, 'frame_array_payload_mismatch'):
                    images.observe_frame(frame)
                raster.assert_not_called()
            self.assertEqual(session.summary()['state_updates'], 0)


if __name__ == '__main__':
    unittest.main()
