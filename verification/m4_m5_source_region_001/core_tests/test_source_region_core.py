"""Selected source unions and synthetic owner frames, with zero real raster."""
import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin import source_region as core
from human_eye_plugin.active_observation import geometry, partition_regions
from human_eye_plugin.scene_cache import SpatialSceneCache


ROOT = Path(__file__).resolve().parents[3]
MOCK_COST = {'mock_raster_calls': 0}


def captured(meshes=None):
    if meshes is None:
        recipe = json.loads((ROOT / 'verification/m4_m5_source_region_001/fixture/GEOMETRY.json').read_bytes())
        meshes = [{'object_id': 'host-' + row['name'], 'name': row['name'],
                   'vertices': [[float(Fraction(value)) for value in point] for point in row['vertices_world_m']],
                   'faces': row['triangles']} for row in recipe['objects']]
    return {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'revision': 'unit:1',
            'host_identity': {'schema_version': '1.0', 'document_epoch': 'a' * 64,
                              'capture_scope': 'complete_scene_meshes',
                              'object_instances': {mesh['object_id']: 'instance-' + str(index)
                                                   for index, mesh in enumerate(meshes)}},
            'capture_state': {'instance_id': 'unit-host', 'epoch': 1, 'revision': 1, 'selection_key': 'scene'},
            'meshes': meshes}


def query(faces=None, name='Obj_07', reference='Ref_B'):
    return {'mode': 'source_region', 'region': {'object': {'name': name},
            'source_triangle_indices': [0, 1, 2, 3] if faces is None else faces},
            'reference': {'name': reference}, 'requested_facts': ['surface_proximity']}


def buffers(prepared, size):
    MOCK_COST['mock_raster_calls'] += 1
    color = np.zeros((size, size, 3), dtype=np.uint8)
    depth = np.full((size, size), np.inf, dtype=np.float64)
    owners = np.full((size, size), -1, dtype=np.int32)
    triangles = np.full((size, size), -1, dtype=np.int32)
    offset = sum(len(mesh.faces) for mesh in prepared.meshes[:prepared.object_index])
    for ordinal, face in enumerate(prepared.source_triangle_indices):
        y = 20 + 6 * ordinal
        color[y:y + 4, 20:24] = (180, 190, 205)
        depth[y:y + 4, 20:24] = 1
        owners[y:y + 4, 20:24] = prepared.object_index
        triangles[y:y + 4, 20:24] = offset + face
    # An unselected face remains visible and cannot enter the region mask.
    remaining = set(range(len(prepared.meshes[prepared.object_index].faces))) - set(prepared.source_triangle_indices)
    if remaining:
        owners[80:83, 20:23] = prepared.object_index
        triangles[80:83, 20:23] = offset + min(remaining)
        depth[80:83, 20:23] = 1
    return color, depth, owners, triangles


def no_rectangles():
    return captured([
        {'object_id': 'A', 'name': 'A', 'vertices': [[0, 0, 1], [1, 0, 1], [0, 1, 1.25]], 'faces': [[0, 1, 2]]},
        {'object_id': 'B', 'name': 'B', 'vertices': [[2, 0, 0], [3, 0, 0], [2, 1, 0]], 'faces': [[0, 1, 2]]}])


class SourceRegionCoreTests(unittest.TestCase):
    def test_camera_fits_selected_vertices_with_large_background_and_full_scene_depth(self):
        capture = captured()
        capture['meshes'].append({'object_id': 'FarBackground', 'name': 'FarBackground',
            'vertices': [[-1000, -1000, -1000], [1000, -1000, -1000],
                         [1000, 1000, -1000], [-1000, 1000, -1000]],
            'faces': [[0, 1, 2], [0, 2, 3]]})
        capture['host_identity']['object_instances']['FarBackground'] = 'instance-background'
        with patch.object(core, '_observation_target_cameras', wraps=core._observation_target_cameras) as cameras:
            prepared = core.prepare_region(capture, query())
        np.testing.assert_array_equal(cameras.call_args.args[0], prepared.region_mesh.vertices)
        self.assertEqual(len(cameras.call_args.args[1]), len(capture['meshes']))
        np.testing.assert_array_equal(cameras.call_args.args[1][-1], [[-1000, -1000, -1000], [1000, 1000, -1000]])
        np.testing.assert_array_equal(prepared.cameras['common_center_world_m'], [4.375, 4.375, 1.0625])
        self.assertEqual(prepared.cameras['schema'], 'active-coverage-source-region-cameras-v1')
        self.assertEqual(prepared.binding['camera_policy']['scope'], 'region_fitted_viewport_full_scene_depth')
        self.assertEqual(prepared.binding['camera_policy']['region_id'], prepared.region_ref['region_id'])
        all_vertices = np.concatenate([mesh.vertices for mesh in prepared.meshes])
        for pose in prepared.cameras['views']:
            view, projection = np.asarray(pose['view_matrix']), np.asarray(pose['projection_matrix'])
            selected_camera = prepared.region_mesh.vertices @ view[:3, :3].T + view[:3, 3]
            selected_ndc = selected_camera @ projection[:3, :3].T + projection[:3, 3]
            full_camera = all_vertices @ view[:3, :3].T + view[:3, 3]
            full_ndc = full_camera @ projection[:3, :3].T + projection[:3, 3]
            self.assertLess(pose['view_span_m'], 2)
            self.assertTrue(np.all(np.abs(selected_ndc[:, :2]) < 1))
            self.assertAlmostEqual(float(np.abs(selected_ndc[:, :2]).max()), 1 / 1.1, places=10)
            self.assertTrue(np.all(np.abs(full_ndc[:, 2]) <= 1))
            self.assertTrue(np.all(-full_camera[:, 2] > pose['near_m']))
            self.assertTrue(np.any(np.abs(full_ndc[:, :2]) > 100))
        self.assertEqual(len(prepared.meshes), 12)
        self.assertEqual(sum(len(mesh.faces) for mesh in prepared.meshes), 64)

    def test_complete_selected_union_and_whole_object_control(self):
        capture = captured()
        selected = core.prepare_region(capture, query())
        self.assertEqual(selected.source_mapping['submesh_to_source_triangle_indices'], [0, 1, 2, 3])
        self.assertEqual(selected.source_mapping['submesh_to_source_vertex_indices'], [0, 1, 2, 3, 4, 5])
        self.assertEqual(len(selected.region_mesh.faces), 4)
        self.assertEqual(len(selected.meshes[selected.object_index].faces), 6)
        self.assertEqual(sum(len(mesh.faces) for mesh in selected.meshes), 62)
        cache = SpatialSceneCache()
        for reference, answer in [('Ref_B', 1.25), ('Ref_C', math.sqrt(137) / 4)]:
            result = core.measure_region(selected, {'name': reference}, cache)
            fact = result['facts']['surface_proximity']
            self.assertEqual(fact['status'], 'measured')
            self.assertEqual(fact['value']['distance_m'], answer)
            witness = fact['value']['nearest_witness']
            self.assertEqual(witness['a'], [4.75, 4., 1.])
            self.assertAlmostEqual(math.dist(witness['a'], witness['b']), answer)
            self.assertAlmostEqual(math.hypot(*witness['direction_a_to_b']), 1)
            source = result['source_mapping']['nearest_witness']['a']
            self.assertTrue(source['exact_membership'])
            self.assertEqual(source['source_vertex_indices'], [1])
            self.assertEqual(source['source_triangle_indices'], [0])
        whole = core.prepare_region(capture, query(list(range(6))))
        for reference, answer in [('Ref_B', 1 / 32), ('Ref_C', math.sqrt(2305) / 32)]:
            result = core.measure_region(whole, {'name': reference}, cache)
            self.assertEqual(result['facts']['surface_proximity']['value']['distance_m'], answer)

    def test_reference_roundtrip_and_precise_invalidation_reasons(self):
        capture = captured()
        initial = core.prepare_region(capture, query())
        followup = core.prepare_region(capture, {'region_ref': initial.region_ref})
        self.assertEqual(followup.region_ref, initial.region_ref)
        self.assertEqual(core.prepare_region(capture, query([3, 2, 1, 0])).region_ref, initial.region_ref)
        for mutation, reason in [
            (lambda value: value['host_identity'].update(document_epoch='b' * 64), 'document_epoch_changed'),
            (lambda value: value['host_identity']['object_instances'].update({'host-Obj_07': 'new-instance'}), 'object_instance_changed'),
            (lambda value: value['capture_state'].update(revision=2), 'capture_generation_changed'),
            (lambda value: value['meshes'][0]['vertices'][0].__setitem__(0, 100), 'ordered_geometry_changed')]:
            changed = copy.deepcopy(capture)
            mutation(changed)
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                core.validate_region_ref(changed, initial.region_ref)
        moved = copy.deepcopy(capture)
        mesh = next(mesh for mesh in moved['meshes'] if mesh['name'] == 'Obj_07')
        for vertex in mesh['vertices']:
            vertex[0] += .25
        moved['capture_state']['revision'] = 2
        current = core.prepare_region(moved, query())
        self.assertNotEqual(current.region_ref['region_id'], initial.region_ref['region_id'])
        measured = core.measure_region(current, {'name': 'Ref_B'}, None)
        self.assertEqual(measured['facts']['surface_proximity']['value']['distance_m'], math.sqrt(5) / 2)
        restored = copy.deepcopy(capture)
        restored['capture_state']['revision'] = 3
        self.assertNotEqual(core.prepare_region(restored, query()).region_ref['region_id'], initial.region_ref['region_id'])

    def test_reject_invalid_selection_and_tampered_reference(self):
        capture = captured()
        for faces in [[], [0, 0], [-1], [6], [True], [1.0]]:
            with self.subTest(faces=faces), self.assertRaises(ValueError):
                core.prepare_region(capture, query(faces))
        reference = core.prepare_region(capture, query()).region_ref
        reference['source_triangle_indices'] = [0]
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            core.validate_region_ref(capture, reference)

    def test_region_frame_reuses_full_source_arrays_and_exact_images(self):
        prepared = core.prepare_region(captured(), query())
        with tempfile.TemporaryDirectory() as directory:
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=buffers(prepared, 512)) as raster:
                first = core.observe_region(prepared, directory, include_image=True)
                self.assertEqual(first['work']['frame_array_decodes'], 0)
                self.assertEqual(first['work']['fresh_payload_reuses'], 1)
                core.measure_region(prepared, {'name': 'Ref_C'}, None)
                first['facts']['region']['source_triangle_indices'].append(99)
                second = core.observe_region(prepared, directory, include_image=True)
            self.assertEqual(raster.call_count, 1)
            self.assertEqual(len(raster.call_args.args[0]), 11)
            self.assertEqual(sum(len(mesh.faces) for mesh in raster.call_args.args[0]), 62)
            self.assertEqual(second['facts']['region']['source_triangle_indices'], [0, 1, 2, 3])
            self.assertEqual(second['work']['raster_attempts'], 0)
            self.assertEqual(second['work']['frame_reuses'], 1)
            frame = second['frames'][0]
            self.assertEqual(first['frames'], second['frames'])
            visibility = second['facts']['visibility']
            self.assertEqual(visibility['selected_surface_pixels'], 64)
            self.assertEqual(visibility['visible_source_triangle_indices'], [0, 1, 2, 3])
            self.assertEqual(visibility['unseen_source_triangle_indices'], [])
            self.assertIsNone(visibility['complete_witness'])
            self.assertEqual(visibility['frame_identity'], frame['frame_identity'])
            with np.load(frame['arrays_path']) as arrays:
                self.assertTrue(np.all(arrays['face_patch_ids'] == -1))
                self.assertEqual(int(arrays['face_patch_offsets'][-1]), 62)
                with Image.open(frame['image_path']) as image:
                    np.testing.assert_array_equal(np.asarray(image), arrays['color'])

    def test_scene_and_target_without_rectangles_build_owner_frame(self):
        capture = no_rectangles()
        parsed, _, _ = geometry({'objects': [{'name': mesh['name'], 'vertices': mesh['vertices'],
                                               'triangles': mesh['faces']} for mesh in capture['meshes']]})
        self.assertEqual(partition_regions(parsed)[0], ())
        with patch('human_eye_plugin.active_observation.partition_regions', side_effect=AssertionError('rectangle gate')):
            prepared = core.prepare_region(capture, query([0], 'A', 'B'))
            with tempfile.TemporaryDirectory() as directory:
                with patch('human_eye_plugin.active_observation_images.rasterize_attention', return_value=buffers(prepared, 512)):
                    result = core.observe_region(prepared, directory, include_image=True)
                self.assertEqual(result['facts']['visibility']['visible_source_triangle_indices'], [0])
                self.assertEqual(result['frames'][0]['all_object_count'], 2)

    def test_duplicate_faces_and_shared_edge_exact_source_membership(self):
        for faces, point, expected_vertices in [
            ([[0, 1, 2], [0, 1, 2]], [0, 0, 0], [0]),
            ([[0, 1, 2], [0, 2, 3]], [.5, .5, 0], [])]:
            with self.subTest(faces=faces):
                capture = captured([
                    {'object_id': 'A', 'name': 'A', 'vertices': [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], 'faces': faces},
                    {'object_id': 'B', 'name': 'B', 'vertices': [point, point, point], 'faces': [[0, 1, 2]]}])
                prepared = core.prepare_region(capture, query([0, 1], 'A', 'B'))
                result = core.measure_region(prepared, {'name': 'B'}, None)
                self.assertEqual(result['facts']['surface_proximity']['value']['distance_m'], 1)
                witness = result['source_mapping']['nearest_witness']['a']
                self.assertEqual(witness['source_triangle_indices'], [0, 1])
                self.assertEqual(witness['source_vertex_indices'], expected_vertices)

    def test_unseen_faces_stay_in_measurement_and_no_image_does_not_render(self):
        prepared = core.prepare_region(captured(), query())
        with patch('human_eye_plugin.active_observation_images.rasterize_attention') as raster:
            result = core.observe_region(prepared, '.', include_image=False)
            self.assertEqual(result['frames'], [])
            self.assertEqual(result['facts']['visibility']['unseen_source_triangle_indices'], [0, 1, 2, 3])
            measured = core.measure_region(prepared, {'name': 'Ref_B'}, None)
            self.assertEqual(measured['facts']['surface_proximity']['value']['distance_m'], 1.25)
            raster.assert_not_called()
