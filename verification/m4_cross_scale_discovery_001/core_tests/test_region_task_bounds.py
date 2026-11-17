"""Pure published-matrix bounds and instrumented synthetic-frame regressions."""

from fractions import Fraction as F
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np
from human_eye_plugin import active_observation_host as host
from human_eye_plugin import active_observation_region_task as core
from human_eye_plugin.active_observation import Region, geometry, partition_regions

spec = importlib.util.spec_from_file_location('_cross_scale_initial_test_helpers', HERE / 'test_region_task_core.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def rectangle(x_low, x_high, y_low, y_high):
    points = ((F(x_low), F(y_low), F(0)), (F(x_high), F(y_low), F(0)),
              (F(x_high), F(y_high), F(0)), (F(x_low), F(y_high), F(0)))
    region = Region('test-region', 0, 'Panel', (0,1), points, (F(0), F(0), F(1)))
    objects = ((points, ((0,1,2),(0,2,3)), None, 'Panel'),)
    return region, objects


def pose():
    return dict(projection='orthographic', size_px=[512,512],
        view_matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,-2.],[0.,0.,0.,1.]],
        projection_matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,.25,0.],[0.,0.,0.,1.]])


class RegionTaskBoundTests(unittest.TestCase):
    def test_pixel_centers_just_below_sixteen_are_bounded(self):
        # Exactly three half-integer centres on each axis, with open room.
        lo, hi = 2*(100.1/511)-1, 2*(102.9/511)-1
        region, objects = rectangle(lo, hi, lo, hi)
        bound = core.pixel_center_upper_bound(region, objects, pose())
        self.assertEqual(bound['status'], 'bounded')
        self.assertEqual(bound['upper_bound'], 9)

    def test_sixteen_centers_and_half_integer_border_never_skip(self):
        for low, high in ((100.1,103.9), (100.5,103.5)):
            region, objects = rectangle(2*(low/511)-1, 2*(high/511)-1,
                                        2*(low/511)-1, 2*(high/511)-1)
            bound = core.pixel_center_upper_bound(region, objects, pose())
            self.assertEqual(bound['status'], 'bounded')
            self.assertGreaterEqual(bound['upper_bound'], 16)

    def test_clip_degenerate_and_nonstandard_matrices_fall_back(self):
        for region, objects in (rectangle(-1,0,-.1,.1), rectangle(0,2**-40,0,2**-40)):
            self.assertEqual(core.pixel_center_upper_bound(region, objects, pose())['status'], 'unknown')
        region, objects = rectangle(-.1,.1,-.1,.1)
        changed = pose()
        changed['projection_matrix'][3][0] = .1
        self.assertEqual(core.pixel_center_upper_bound(region, objects, changed)['status'], 'unknown')

    def test_all_source_faces_are_checked_for_slim_degenerate_piece(self):
        region, objects = rectangle(-.1,.1,-.1,.1)
        vertices = objects[0][0] + ((F(0), F(0), F(0)), (F(1,2**44), F(0), F(0)), (F(0), F(1,2**44), F(0)))
        objects = ((vertices, objects[0][1] + ((4,5,6),), None, 'Panel'),)
        region = Region(region.roi_id, 0, 'Panel', (0,1,2), region.vertices, region.normal)
        self.assertEqual(core.pixel_center_upper_bound(region, objects, pose())['status'], 'unknown')

    def test_fixed_scene_all_eighteen_include_tilted_and_subsixteen(self):
        objects, _, _ = geometry(host.scene_from_capture(helpers.capture()))
        regions, _ = partition_regions(objects)
        task = [region for region in regions if core.region_matches(region, helpers.TASK)]
        cameras = host.freeze_cameras(core._meshes_from_objects(objects))
        for region in task:
            for view in cameras['views']:
                bound = core.pixel_center_upper_bound(region, objects, view)
                self.assertEqual(bound['status'], 'bounded', (region.object_name, view['name'], bound))
                self.assertLess(bound['upper_bound'], 16)
                self.assertEqual(len(bound['source_triangles']), 2)
                self.assertTrue(all(row['accepted_exact_lambda_lower'] < -1e-10 for row in bound['source_triangles']))

    def test_skip_five_global_views_keeps_same_two_local_witnesses(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=helpers.raster) as raster:
            result = host.observe_capture(helpers.capture(), directory, region_task=helpers.TASK)
        self.assertEqual(raster.call_count, 3)
        self.assertEqual(result['work']['global_views_skipped'], 5)
        self.assertEqual(len(result['frames']), 3)
        self.assertEqual(len(result['constructed_frames']), 3)
        self.assertEqual([row['view_name'] for row in result['frames']], ['SCENE']*3)
        self.assertEqual(result['facts']['region_task']['summary']['observed_region_count'], 2)
        global_scope = result['scopes'][0]
        self.assertEqual(len(global_scope['facts']['observations']), 1)
        self.assertEqual(len(global_scope['skipped_views']), 5)
        self.assertTrue(all(not view['actual_observation'] for view in global_scope['skipped_views']))

    def test_other_large_task_region_keeps_its_needed_view(self):
        conditions = dict(area_min_m2=0, area_max_m2=500, normal_z_min=.75)
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=helpers.raster):
            result = host.observe_capture(helpers.capture(), directory, region_task=conditions)
        self.assertGreater(len(result['scopes'][0]['frame_refs']), 1)
        self.assertLessEqual(len(result['frames']), 6)
        delivered = {frame['frame_identity'] for frame in result['frames']}
        for row in result['facts']['region_task']['rows']:
            if row['complete_witness']:
                self.assertEqual(row['complete_witness']['selected_for_delivery'],
                                 row['complete_witness']['frame_identity'] in delivered)


if __name__ == '__main__':
    unittest.main()
