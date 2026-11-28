"""Owned-pixel localization checks using synthetic buffers and mocked raster."""

import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.active_observation import prepare_scene
from human_eye_plugin.active_observation_images import (
    ActiveObservationImages, _aggregate_patch_pixels, _pixel_rows,
)
from human_eye_plugin.attention_rendering import _contrasting_boundaries
from verification.test_active_observation_images import camera_pool, subdivided_scene, synthetic_buffers


def buffers_for(points, *, contrast=True, region=0):
    patches = np.full((8, 8), -1, dtype=np.int32)
    color = np.empty((8, 8, 3), dtype=np.uint8)
    color[:] = (18, 22, 30)
    for x, y in points:
        patches[y, x] = region
        if contrast:
            color[y, x] = (180, 190, 205)
    return {'color': color, 'patch_owners': patches}


def pixel_row(buffers, normal=(0, 0, 1)):
    mesh = SimpleNamespace(vertices=[None] * 4, faces=[None] * 2)
    region = SimpleNamespace(roi_id='test_patch', object_index=0,
                             normal=normal, triangle_indices=(0, 1))
    return _pixel_rows((mesh,), {'name': 'SCENE', 'target_to_eye_unit': [0, 0, 1]},
                       buffers, (region,))[0]


class ActiveObservationRegionAnchorTests(unittest.TestCase):
    def assert_owned_location(self, buffers, bounds, anchor):
        result = _aggregate_patch_pixels(buffers['color'], buffers['patch_owners'], 1,
                                         include_locations=True)
        self.assertEqual(result['visible_pixel_bounds'][0], bounds)
        self.assertEqual(result['visible_pixel_anchor'][0], anchor)
        if anchor is not None:
            x, y = anchor
            self.assertEqual(buffers['patch_owners'][y, x], 0)
            ys, xs = np.nonzero(buffers['patch_owners'] == 0)
            expected = min(zip(xs.tolist(), ys.tolist()), key=lambda point: (
                (2 * point[0] - bounds[0] - bounds[2]) ** 2
                + (2 * point[1] - bounds[1] - bounds[3]) ** 2,
                point[1] * buffers['patch_owners'].shape[1] + point[0]))
            self.assertEqual(anchor, list(expected))
        return result

    def test_count_only_api_and_shared_boundary_are_preserved(self):
        buffers = buffers_for([(x, y) for y in range(2, 6) for x in range(2, 6)])
        old = _aggregate_patch_pixels(buffers['color'], buffers['patch_owners'], 1)
        self.assertEqual(set(old), {'visible_surface_pixels', 'contrasting_boundary_pixels'})
        with patch('human_eye_plugin.active_observation_images._contrasting_boundaries',
                   wraps=_contrasting_boundaries) as boundary:
            full = _aggregate_patch_pixels(buffers['color'], buffers['patch_owners'], 1,
                                           include_locations=True)
            self.assertEqual(boundary.call_count, 1)
        self.assertEqual(set(full), set(old) | {'visible_pixel_bounds', 'visible_pixel_anchor'})
        for key in old:
            np.testing.assert_array_equal(old[key], full[key])

    def test_hole_anchor_is_owned_instead_of_the_empty_center(self):
        points = [(x, y) for y in range(2, 5) for x in range(2, 5) if (x, y) != (3, 3)]
        self.assert_owned_location(buffers_for(points), [2, 2, 4, 4], [3, 2])

    def test_disjoint_visible_islands_keep_anchor_on_a_real_island(self):
        points = [(x, y) for y in (1, 2) for x in (1, 2)]
        points += [(x, y) for y in (5, 6) for x in (5, 6)]
        self.assert_owned_location(buffers_for(points), [1, 1, 6, 6], [2, 2])

    def test_equal_integer_distance_ties_use_row_major_order(self):
        self.assert_owned_location(buffers_for([(2, 1), (1, 2), (3, 2), (2, 3)]),
                                   [1, 1, 3, 3], [2, 1])

    def test_one_pixel_retains_location_below_readability_threshold(self):
        buffers = buffers_for([(7, 0)])
        self.assert_owned_location(buffers, [7, 0, 7, 0], [7, 0])
        row = pixel_row(buffers)
        self.assertEqual(row['visible_surface_pixels'], 1)
        self.assertFalse(row['readable'])
        self.assertEqual(row['visible_pixel_anchor'], [7, 0])

    def test_completely_hidden_patch_has_two_null_locations(self):
        buffers = buffers_for([])
        self.assert_owned_location(buffers, None, None)
        row = pixel_row(buffers)
        self.assertEqual(row['visible_surface_pixels'], 0)
        self.assertIsNone(row['visible_pixel_bounds'])
        self.assertIsNone(row['visible_pixel_anchor'])
        self.assertFalse(row['readable'])

    def test_back_facing_visible_pixels_keep_bounds_and_anchor(self):
        buffers = buffers_for([(x, y) for y in range(2, 6) for x in range(2, 6)])
        row = pixel_row(buffers, normal=(0, 0, -1))
        self.assertEqual(row['visible_surface_pixels'], 16)
        self.assertGreaterEqual(row['contrasting_boundary_pixels'], 4)
        self.assertFalse(row['front_facing'])
        self.assertFalse(row['readable'])
        self.assertEqual(row['visible_pixel_bounds'], [2, 2, 5, 5])
        self.assertEqual(row['visible_pixel_anchor'], [3, 3])

    def test_low_contrast_visible_pixels_keep_bounds_and_anchor(self):
        buffers = buffers_for([(x, y) for y in range(2, 6) for x in range(2, 6)], contrast=False)
        row = pixel_row(buffers)
        self.assertEqual(row['visible_surface_pixels'], 16)
        self.assertEqual(row['contrasting_boundary_pixels'], 0)
        self.assertTrue(row['front_facing'])
        self.assertFalse(row['readable'])
        self.assertEqual(row['visible_pixel_bounds'], [2, 2, 5, 5])
        self.assertEqual(row['visible_pixel_anchor'], [3, 3])

    def test_adapter_uses_one_aggregation_and_passes_locations_to_facts(self):
        session = prepare_scene(subdivided_scene(), camera_pool())
        buffers = synthetic_buffers()
        with tempfile.TemporaryDirectory() as folder:
            images = ActiveObservationImages(session, folder, _measure_stages=True)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=tuple(buffers[key] for key in ('color', 'depth', 'owners'))) as raster:
                frame = images.render_next()
                with patch('human_eye_plugin.active_observation_images._aggregate_patch_pixels',
                           wraps=_aggregate_patch_pixels) as aggregate:
                    feedback = images.observe_frame(frame)
                    self.assertEqual(aggregate.call_count, 1)
                    self.assertTrue(aggregate.call_args.kwargs['include_locations'])
                self.assertIs(images.render_view('SCENE'), frame)
                self.assertEqual(raster.call_count, 1)
            row = feedback['pixel_rows'][0]
            self.assertEqual(row['visible_pixel_bounds'], [20, 20, 23, 23])
            self.assertEqual(row['visible_pixel_anchor'], [21, 21])
            public = session.short_facts()['observations'][0]['pixel_rows'][0]
            self.assertEqual(public['visible_pixel_bounds'], row['visible_pixel_bounds'])
            self.assertEqual(public['visible_pixel_anchor'], row['visible_pixel_anchor'])
            stage = feedback['stages']['pixel_localization']
            outer = feedback['stages']['readability']
            self.assertGreaterEqual(stage['started_ns'], outer['started_ns'])
            self.assertLessEqual(stage['closed_ns'], outer['closed_ns'])
            self.assertEqual(stage['elapsed_ns'], stage['closed_ns'] - stage['started_ns'])
            self.assertGreater(stage['named_temporary_array_bytes'], 0)
            self.assertEqual(stage['new_cached_array_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
