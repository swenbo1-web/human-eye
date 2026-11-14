"""Representation-only active facts checks using constant synthetic PNGs.

These fixtures perform no capture, geometry preparation, Blender or raster.
"""

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from human_eye_plugin.live_spatial_mcp import (
    LiveSpatialMCPServer, _tool_result, project_active_observation_brief,
)


class FixedService:
    def __init__(self, value):
        self.value = value
        self.events = []
        self.calls = []

    def observe(self, session_id, **arguments):
        self.calls.append((session_id, arguments))
        return copy.deepcopy(self.value)

    def _check_request_budget(self, stage):
        return None

    def record_event(self, event, **fields):
        self.events.append((event, copy.deepcopy(fields)))


class ActiveObservationBriefTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        objects = [dict(object_index=index, host_id='host-' + str(index),
                        instance_id='instance-' + str(index), object_name=name)
                   for index, name in enumerate(('中心物体', 'Hidden region', 'Occluder'))]
        regions = [dict(objects[index], roi_id='roi-' + str(index),
                        status='covered' if index == 0 else 'unknown',
                        reason='observed_readable' if index == 0 else 'finite_camera_pool_uncovered')
                   for index in range(2)]
        binding = dict(schema='active-observation-host-source-v1', source='blender', unit='m',
            coordinate_frame='world', scene_revision='source-revision', document_epoch='document',
            geometry_identity='geometry', camera_identity='cameras', binding_sha256='full-binding',
            source_binding_sha256='source-binding', runtime_source_sha256='runtime',
            capture_scope='complete_scene_meshes', source_status='loaded_generation',
            source_check_scope='bound_generation_identity', disk_status='disk_not_checked',
            capture_state=dict(instance_id='capture-session', epoch=1, revision=2, selection_key='selector-digest'),
            camera_policy={'order': ['SCENE', 'BACK']}, objects=objects)
        frames, observations = [], []
        for index, view in enumerate(('SCENE', 'BACK')):
            stream = io.BytesIO()
            Image.new('RGB', (512, 512), (40 + index, 80, 120)).save(stream, format='PNG')
            png = stream.getvalue()
            path = Path(directory.name) / (view + '.png')
            path.write_bytes(png)
            frame = dict(view_name=view, image_ref='image-' + str(index), image_path=str(path),
                image_sha256=hashlib.sha256(png).hexdigest(), PNG_bytes=len(png),
                scene_identity='geometry', candidate_identity='cameras',
                host_binding_sha256='full-binding', source_revision='source-revision',
                arrays_path=str(path.with_suffix('.npz')), arrays_sha256='arrays-' + str(index),
                array_payload_bytes=3932160, compressed_array_file_bytes=100,
                stages={'actual_raster': {'elapsed_ns': 123}}, feedback_stages={'readability': {'elapsed_ns': 4}})
            frames.append(frame)
            pixels = []
            for region_index, region in enumerate(regions):
                readable = index == 0 and region_index == 0
                pixels.append(dict(roi_id=region['roi_id'], object_index=region['object_index'],
                    object_name=region['object_name'], host_id=region['host_id'], view=view,
                    front_facing=index == 0, visible_surface_pixels=30 if readable else 0,
                    contrasting_boundary_pixels=8 if readable else 0, readable=readable,
                    minimum_surface_pixels=16, minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24))
            observations.append(dict(view_name=view, image_path=frame['image_path'],
                image_ref=frame['image_ref'], image_sha256=frame['image_sha256'],
                readable_roi_ids=['roi-0'] if index == 0 else [], pixel_rows=pixels))
        self.value = dict(status='complete', result_kind='active_observation',
            observation_status='locally_observed', session_id='session', read_only=True,
            execution_authority=False, binding=binding, frames=frames,
            facts=dict(scene_identity='geometry', candidate_identity='cameras', regions=regions,
                observations=observations, image_delivery_scope='local_core_validation',
                coverage=dict(covered_roi_ids=['roi-0'], unresolved_roi_ids=['roi-1'],
                    candidate_pool_uncovered_roi_ids=['roi-1'], observed_views=['SCENE', 'BACK'],
                    scope='registered finite camera pool', state_updates=2),
                scope=dict(capture_object_count=3, supported_roi_object_count=2,
                    domain='whole-object connected hole-free exact planar rectangles',
                    all_objects_participate_in_occlusion=True,
                    objects_without_supported_roi=[dict(objects[2], status='unknown')])),
            work=dict(raster_attempts=2, frame_reuses=0), generation_work=dict(raster_attempts=2),
            stages={'host_capture': {'elapsed_ns': 15}}, generation_stages={'prepare': {'elapsed_ns': 10}},
            image_delivery=dict(local_verified_image_count=2, mcp_content_constructed_image_count=2,
                consumer_read_status='unconfirmed', frame_reuses=0, new_raster_attempts=2))

    def test_pure_tables_preserve_negative_pixels_and_unknown_scope(self):
        original = copy.deepcopy(self.value)
        brief = project_active_observation_brief(self.value)
        self.assertEqual(brief['schema'], 'active-observation-brief-v1')
        self.assertEqual(brief['objects']['rows'][0], [0, 'host-0', 'instance-0', '中心物体'])
        self.assertEqual(brief['regions']['rows'][1], ['roi-1', 1, 'unknown', 'finite_camera_pool_uncovered'])
        self.assertEqual(brief['coverage']['candidate_pool_uncovered_region_indices'], [1])
        self.assertEqual(brief['scope']['objects_without_supported_roi']['rows'], [[2, 'unknown']])
        self.assertEqual(len(brief['pixels']['rows']), 4)
        self.assertEqual(brief['pixels']['rows'][3], [1, 1, False, 0, 0, False])
        self.assertEqual(brief['pixel_rules'], dict(minimum_surface_pixels=16,
            minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24))
        self.assertEqual(brief['binding']['disk_status'], 'disk_not_checked')
        self.assertNotIn('selection_key', brief['binding']['capture_state'])
        self.assertNotIn('work', brief)
        self.assertEqual(self.value, original)
        brief['objects']['rows'][0][3] = 'mutated'
        self.assertEqual(self.value, original)

    def test_default_and_explicit_brief_match_full_keeps_diagnostics_and_images(self):
        default = _tool_result(self.value, is_error=False)
        explicit = _tool_result(self.value, is_error=False, response_detail='brief')
        full = _tool_result(self.value, is_error=False, response_detail='full')
        self.assertEqual(default, explicit)
        self.assertEqual(default['content'][1:], full['content'][1:])
        text = json.loads(default['content'][0]['text'])
        diagnostic = json.loads(full['content'][0]['text'])
        self.assertEqual(text['images']['rows'][0][-1], 1)
        self.assertNotIn(self.value['frames'][0]['image_path'], default['content'][0]['text'])
        for key in ('work', 'generation_work', 'stages', 'generation_stages'):
            self.assertEqual(diagnostic[key], self.value[key])
        self.assertEqual(diagnostic['binding']['capture_state'], self.value['binding']['capture_state'])
        self.assertEqual(diagnostic['binding']['camera_policy'], self.value['binding']['camera_policy'])
        self.assertEqual(diagnostic['frames'], self.value['frames'])

    def test_table_indices_follow_frame_order_without_reordering_observations(self):
        self.value['frames'].reverse()
        brief = project_active_observation_brief(self.value)
        self.assertEqual(brief['images']['rows'][0][:2], ['BACK', 'image-1'])
        self.assertEqual(brief['observations']['rows'], [[1, [0]], [0, []]])
        self.assertEqual([row[:2] for row in brief['pixels']['rows']], [[1, 0], [1, 1], [0, 0], [0, 1]])

    def test_no_roi_and_prediction_remain_unknown_without_image_evidence(self):
        self.value.update(status='predicted', observation_status='prediction_only', frames=[])
        self.value['work'].update(raster_attempts=0, frame_reuses=0)
        self.value['generation_work']['raster_attempts'] = 0
        self.value['image_delivery'].update(local_verified_image_count=0,
            mcp_content_constructed_image_count=0, new_raster_attempts=0)
        facts = self.value['facts']
        facts['observations'] = []
        facts['coverage'].update(covered_roi_ids=[], unresolved_roi_ids=['roi-0', 'roi-1'],
                                 observed_views=[], state_updates=0)
        for region in facts['regions']:
            region['status'], region['reason'] = 'unknown', 'pending_observation'
        predicted = project_active_observation_brief(self.value)
        self.assertNotIn('covered_region_indices', predicted['coverage'])
        self.assertEqual(predicted['coverage']['unresolved_region_indices'], [0, 1])
        self.assertNotIn('images', predicted)
        self.assertNotIn('pixel_rules', predicted)
        self.value.update(status='unknown', observation_status='no_supported_regions')
        facts['regions'] = []
        facts['coverage'].update(unresolved_roi_ids=[], candidate_pool_uncovered_roi_ids=[])
        facts['scope']['supported_roi_object_count'] = 0
        facts['scope']['objects_without_supported_roi'] = [dict(obj, status='unknown')
                                                         for obj in self.value['binding']['objects']]
        empty = project_active_observation_brief(self.value)
        self.assertEqual(empty['status'], 'unknown')
        self.assertNotIn('regions', empty)
        self.assertEqual(len(empty['scope']['objects_without_supported_roi']['rows']), 3)

    def test_conflicting_duplicate_and_unresolved_references_keep_full(self):
        mutations = (
            lambda value: value['binding'].pop('disk_status'),
            lambda value: value['binding'].update(unrecognized_provenance='retain-full'),
            lambda value: value['binding']['objects'].append(copy.deepcopy(value['binding']['objects'][0])),
            lambda value: value['binding']['objects'][1].update(object_index=True),
            lambda value: value['facts']['regions'].append(copy.deepcopy(value['facts']['regions'][0])),
            lambda value: value['facts']['coverage']['unresolved_roi_ids'].append('absent-roi'),
            lambda value: value['frames'][1].update(image_ref=value['frames'][0]['image_ref']),
            lambda value: value['facts']['observations'][0]['pixel_rows'][0].update(host_id='wrong-host'),
            lambda value: value['facts']['observations'][1]['pixel_rows'].pop(),
            lambda value: value['facts']['observations'][1]['pixel_rows'][1].update(minimum_surface_pixels=17),
            lambda value: value['facts'].update(unrecognized_fact='retain-full'),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(self.value)
                mutate(value)
                self.assertIsNone(project_active_observation_brief(value))
                audit = {}
                default = _tool_result(value, is_error=False, active_delivery_audit=audit)
                full = _tool_result(value, is_error=False, response_detail='full')
                self.assertEqual(default, full)
                self.assertEqual(audit['projection_status'], 'unsupported_full')

    def test_mcp_forwarding_and_encoding_failure_retain_construction_cost(self):
        service = FixedService(self.value)
        server = LiveSpatialMCPServer(service)
        original = copy.deepcopy(self.value)
        encode = base64.b64encode
        count = 0

        def fail_second_image(raw):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError('injected image encoding failure')
            return encode(raw)

        def call(detail):
            arguments = {'query': {'mode': 'active_observation'}, 'response_detail': detail}
            return server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})['result']

        with patch('human_eye_plugin.live_spatial_mcp.base64.b64encode', side_effect=fail_second_image):
            failed = call('brief')
        self.assertTrue(failed['isError'])
        failure_audit = service.events[0][1]['image_delivery']
        self.assertEqual(failure_audit['native_blocks_constructed'], 1)
        self.assertFalse(failure_audit['mcp_content_ready'])
        full = call('full')
        brief = call('brief')
        self.assertIn('generation_work', json.loads(full['content'][0]['text']))
        self.assertEqual(json.loads(brief['content'][0]['text'])['schema'], 'active-observation-brief-v1')
        self.assertNotIn('response_detail', service.calls[-1][1])
        self.assertEqual(service.value, original)
        self.assertEqual(brief['content'][1:], full['content'][1:])


if __name__ == '__main__':
    unittest.main()
