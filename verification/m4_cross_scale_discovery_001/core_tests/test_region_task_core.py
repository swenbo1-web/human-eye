"""Specific cross-scale regressions, with synthetic raster output only."""

import copy
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np

from human_eye_plugin import active_observation_host as host
from human_eye_plugin import active_observation_region_task as core
from human_eye_plugin.active_observation import Region, geometry, partition_regions


TASK = dict(area_min_m2=1/128, area_max_m2=1/32, normal_z_min=.75)


def capture():
    recipe = json.loads((ROOT / 'verification/m4_global_local_qualification_001/fixture/GEOMETRY.json').read_bytes())
    meshes = [dict(object_id='host-' + row['name'], name=row['name'],
        vertices=[[float(F(value)) for value in point] for point in row['vertices_world_m']],
        faces=row['triangles']) for row in recipe['objects']]
    return dict(unit='m', coordinate_frame='world', source='blender', revision='test:1',
        host_identity=dict(schema_version='1.0', document_epoch='a'*64, capture_scope='complete_scene_meshes',
            object_instances={mesh['object_id']: str(index+1) for index, mesh in enumerate(meshes)}),
        capture_state=dict(instance_id='unit-host', epoch=1, revision=1, selection_key='scene'), meshes=meshes)


def raster(meshes, view, projection, size, **options):
    color = np.empty((size, size, 3), dtype=np.uint8)
    color[:] = (18, 22, 30)
    depth = np.full((size, size), np.inf, dtype=np.float64)
    owners = np.full((size, size), -1, dtype=np.int32)
    triangles = np.full((size, size), -1, dtype=np.int32)
    candidates = []
    for index, mesh in enumerate(meshes):
        if len(mesh.vertices) == 4:
            center = mesh.vertices.mean(axis=0)
            projected = projection[:3, :3] @ (view[:3, :3] @ center + view[:3, 3]) + projection[:3, 3]
            candidates.append((float(np.linalg.norm(projected[:2])), index))
    local = projection[0, 0] > 1
    chosen = [min(candidates)[1]] if local else [index for _, index in candidates]
    offsets = np.cumsum([0] + [len(mesh.faces) for mesh in meshes])
    for ordinal, index in enumerate(chosen):
        first = 100 + ordinal*20
        last = first + (4 if local else 1)
        color[first:last, first:last] = (180, 190, 205)
        owners[first:last, first:last] = index
        triangles[first:last, first:last] = offsets[index]
        depth[first:last, first:last] = 1
    return color, depth, owners, triangles


class RegionTaskCoreTests(unittest.TestCase):
    def test_exact_area_normal_thresholds_and_negative_sign(self):
        up = Region('u', 0, '', (0, 1),
            ((F(0), F(0), F(0)), (F(1), F(0), F(0)), (F(1), F(1), F(0)), (F(0), F(1), F(0))), (0,0,1))
        down = Region('d', 0, '', (0, 1), tuple(reversed(up.vertices)), (0,0,-1))
        self.assertTrue(core.region_matches(up, dict(area_min_m2=1, area_max_m2=1, normal_z_min=1)))
        self.assertFalse(core.region_matches(up, dict(area_min_m2=1.00001, area_max_m2=2, normal_z_min=1)))
        self.assertFalse(core.region_matches(up, dict(area_min_m2=0, area_max_m2=.99999, normal_z_min=1)))
        self.assertTrue(core.region_matches(down, dict(area_min_m2=1, area_max_m2=1, normal_z_min=-1)))
        self.assertFalse(core.region_matches(down, dict(area_min_m2=1, area_max_m2=1, normal_z_min=-.999)))
        self.assertTrue(core.region_matches(up, dict(area_min_m2=1, area_max_m2=1, normal_z_min=-.5)))

    def test_fixed_geometry_filters_three_without_object_selector(self):
        parsed, _, _ = geometry(host.scene_from_capture(capture()))
        regions, _ = partition_regions(parsed)
        selected = [region for region in regions if core.region_matches(region, TASK)]
        self.assertEqual({row.object_name for row in selected}, {'Obj_02', 'Obj_06', 'Obj_09'})
        self.assertTrue(all(row.triangle_indices == (0,1) for row in selected))

    def test_tilted_exact_threshold_sides(self):
        parsed, _, _ = geometry(host.scene_from_capture(capture()))
        regions, _ = partition_regions(parsed)
        tilted = next(region for region in regions if region.object_name == 'Obj_09')
        self.assertTrue(core.region_matches(tilted, dict(area_min_m2=.01235, area_max_m2=.01236, normal_z_min=.9486)))
        self.assertFalse(core.region_matches(tilted, dict(area_min_m2=.01236, area_max_m2=.01237, normal_z_min=.9486)))
        self.assertFalse(core.region_matches(tilted, dict(area_min_m2=.01235, area_max_m2=.01236, normal_z_min=.9487)))

    def test_single_geometry_preparation_shared_meshes_and_source_bound_scopes(self):
        original = capture()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(core, 'geometry', wraps=geometry) as parse, \
                    patch.object(core, '_meshes_from_objects', wraps=core._meshes_from_objects) as convert, \
                    patch('human_eye_plugin.active_observation.partition_regions', wraps=partition_regions) as partition, \
                    patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=raster) as renders:
                result = host.observe_capture(original, directory, region_task=TASK)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(convert.call_count, 1)
            self.assertEqual(partition.call_count, 1)
            self.assertEqual(renders.call_count, 8)
            mesh_ids = [id(call.args[0]) for call in renders.call_args_list]
            self.assertEqual(len(set(mesh_ids)), 1)
            self.assertTrue(all(len(call.args[0]) == 9 for call in renders.call_args_list))
            self.assertEqual(result['work']['partition_calls'], 1)
            self.assertEqual(result['work']['local_camera_calls'], 2)
            self.assertEqual(result['work']['index_calls'], 3)
            self.assertEqual(len(result['frames']), 3)
            self.assertEqual(len(result['constructed_frames']), 8)
            self.assertEqual([row['view_name'] for row in result['frames']], ['SCENE']*3)
            self.assertEqual(len({row['frame_identity'] for row in result['frames']}), 3)
            self.assertEqual(len({row['camera_identity'] for row in result['frames']}), 3)
            rows = result['facts']['region_task']['rows']
            self.assertEqual(sum(row['status'] == 'covered' for row in rows), 2)
            covered = next(row for row in rows if row['object_name'] == 'Obj_06')
            self.assertEqual(covered['reason'], 'positive_area_occlusion_all_front_views')
            self.assertIsNone(covered['complete_witness'])
            for row in rows:
                self.assertEqual(row['source']['parent_binding_sha256'], result['binding']['binding_sha256'])
                self.assertEqual(row['source_triangle_indices'], [0,1])
                if row['complete_witness']:
                    self.assertTrue(row['complete_witness']['selected_for_delivery'])
            for scope in result['scopes'][1:]:
                self.assertEqual(scope['binding']['parent_binding_sha256'], result['binding']['binding_sha256'])
                self.assertEqual(scope['binding']['objects'], result['binding']['objects'])
                self.assertEqual(scope['facts']['scope']['source_triangle_count'], 56)
        self.assertEqual(original, capture())

    def test_text_only_has_no_claimed_pixel_witness(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention') as renders:
            result = host.observe_capture(capture(), directory, region_task=TASK, include_image=False)
        renders.assert_not_called()
        self.assertEqual(result['status'], 'predicted')
        self.assertEqual(len(result['scopes']), 1)
        self.assertEqual(result['frames'], [])
        self.assertTrue(all(row['complete_witness'] is None for row in result['facts']['region_task']['rows']))

    def test_cancel_before_raster_retains_attempt_and_original_deadline(self):
        def check(phase):
            if phase == 'active_observation_before_raster':
                raise TimeoutError('original request cancelled')
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention') as renders:
            with self.assertRaises(TimeoutError) as caught:
                host.observe_capture(capture(), directory, region_task=TASK, check_budget=check)
        renders.assert_not_called()
        self.assertEqual(caught.exception.active_observation_work['raster_attempts'], 0)

    def test_local_numeric_insufficiency_preserves_six_constructed_global_frames(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=raster), \
                patch.object(core, '_observation_target_cameras', side_effect=ValueError('active_observation_target_camera_numeric_insufficient')):
            with self.assertRaisesRegex(ValueError, 'numeric_insufficient') as caught:
                host.observe_capture(capture(), directory, region_task=TASK)
        self.assertEqual(caught.exception.active_observation_work['raster_attempts'], 6)
        self.assertEqual(caught.exception.active_observation_work['raster_completed'], 6)

    def test_corrupted_raster_fails_after_attempt_without_readable_success(self):
        def bad(*arguments, **keywords):
            values = list(raster(*arguments, **keywords))
            values[3] = np.full((512,512), -1, dtype=np.int32)
            return tuple(values)
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=bad):
            with self.assertRaisesRegex(ValueError, 'triangle_owner') as caught:
                host.observe_capture(capture(), directory, region_task=TASK)
        self.assertEqual(caught.exception.active_observation_work['raster_attempts'], 1)
        self.assertEqual(caught.exception.active_observation_work['raster_completed'], 0)

    def test_rename_or_source_revision_rebinds_same_geometry(self):
        first = capture()
        second = copy.deepcopy(first)
        second['revision'] = 'test:2'
        second['capture_state']['revision'] = 2
        second['meshes'][1]['name'] = 'Rename'
        with tempfile.TemporaryDirectory() as directory, \
                patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=raster):
            before = host.observe_capture(first, directory, region_task=TASK)
            after = host.observe_capture(second, directory, region_task=TASK)
        self.assertEqual(before['facts']['scene_identity'], after['facts']['scene_identity'])
        self.assertNotEqual(before['binding']['binding_sha256'], after['binding']['binding_sha256'])
        self.assertNotEqual(before['frames'][1]['image_ref'], after['frames'][1]['image_ref'])


if __name__ == '__main__':
    unittest.main()
