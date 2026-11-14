"""Patch scope and delivery checks with synthetic metadata and constant PNGs.

All geometry preparation and image construction at the host entry are mocked.
These checks perform no actual raster or Blender operation.
"""

import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin import active_observation_host as host_core
from human_eye_plugin.live_spatial_mcp import _tool_result, project_active_observation_brief


class ActiveObservationPatchDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.objects = (
            (((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
              (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
              (2, 0, 0), (3, 0, 0), (2, 1, 0)),
             ((0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (8, 9, 10)), (), 'Joined'),
            (((4, 0, 0), (5, 0, 0), (4, 1, 0)), ((0, 1, 2),), (), 'Triangle'),
        )
        self.regions = (
            SimpleNamespace(roi_id='roi-front', object_index=0, triangle_indices=(0, 1)),
            SimpleNamespace(roi_id='roi-back', object_index=0, triangle_indices=(2, 3)),
        )
        partitions = (
            dict(object_index=0, source_triangle_count=5, supported_triangle_count=4,
                supported_triangle_indices=(0, 1, 2, 3), unsupported_triangle_count=1,
                unsupported_components=({'triangle_indices': (4,), 'reason': 'insufficient_faces'},)),
            dict(object_index=1, source_triangle_count=1, supported_triangle_count=0,
                supported_triangle_indices=(), unsupported_triangle_count=1,
                unsupported_components=({'triangle_indices': (0,), 'reason': 'insufficient_faces'},)),
        )
        host_objects = [dict(object_index=index, host_id='host-' + str(index),
            instance_id='instance-' + str(index), object_name=obj[3]) for index, obj in enumerate(self.objects)]
        self.binding = dict(schema='active-observation-host-source-v1', objects=host_objects,
            scene_revision='source', document_epoch='document', capture_scope='complete_scene_meshes',
            unit='m', coordinate_frame='world', source='blender', capture_state=None,
            source_binding_sha256='source-binding', geometry_identity='geometry', camera_identity='cameras',
            binding_sha256='host-binding', runtime_source_sha256='runtime', source_status='loaded_generation',
            disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
        clocks = {name: dict(started_ns=0, closed_ns=1, elapsed_ns=1) for name in ('discovery', 'coverage')}
        self.session = SimpleNamespace(objects=self.objects, regions=self.regions,
            index=SimpleNamespace(patch_scope=partitions), cameras={'views': []},
            scene_identity='geometry', candidate_identity='cameras', diagnostics={'stages': clocks})
        stream = io.BytesIO()
        Image.new('RGB', (512, 512), (20, 50, 100)).save(stream, format='PNG')
        png = stream.getvalue()
        image = self.directory / 'unit.png'
        image.write_bytes(png)
        frame = dict(scene_identity='geometry', candidate_identity='cameras', view_name='SCENE',
            host_binding_sha256='host-binding', source_revision='source', image_ref='unit-patch-image',
            image_path=str(image), image_sha256=hashlib.sha256(png).hexdigest(), PNG_bytes=len(png),
            patch_mapping_version='active-patch-owner-v1', patch_roi_ids=['roi-front', 'roi-back'],
            patch_mapping_identity='a' * 64, patch_owner_array_bytes=1048576, patch_mapping_array_bytes=44)
        facts_regions = [dict(host_objects[0], roi_id=region.roi_id,
            status='covered' if index == 0 else 'unknown',
            reason='observed_readable' if index == 0 else 'finite_camera_pool_uncovered')
            for index, region in enumerate(self.regions)]
        pixels = [dict(roi_id=region.roi_id, object_index=0, object_name='Joined', host_id='host-0',
            view='SCENE', front_facing=True, visible_surface_pixels=32 if index == 0 else 0,
            contrasting_boundary_pixels=8 if index == 0 else 0, readable=index == 0,
            minimum_surface_pixels=16, minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24)
            for index, region in enumerate(self.regions)]
        self.value = dict(status='complete', result_kind='active_observation',
            observation_status='locally_observed', session_id='unit', binding=self.binding,
            read_only=True, execution_authority=False, frames=[frame],
            work=dict(raster_attempts=1, frame_reuses=0), generation_work=dict(raster_attempts=1),
            facts=dict(scene_identity='geometry', candidate_identity='cameras', regions=facts_regions,
                observations=[dict(view_name='SCENE', image_ref=frame['image_ref'],
                    image_path=frame['image_path'], image_sha256=frame['image_sha256'],
                    readable_roi_ids=['roi-front'], pixel_rows=pixels)],
                scope=host_core._patch_scope_facts(self.session, self.binding),
                coverage=dict(observed_views=['SCENE'], covered_roi_ids=['roi-front'],
                    unresolved_roi_ids=['roi-back'], candidate_pool_uncovered_roi_ids=['roi-back'],
                    state_updates=1, scope='registered finite camera pool'),
                image_delivery_scope='local_core_validation'),
            image_delivery=dict(local_verified_image_count=1, mcp_content_constructed_image_count=1,
                consumer_read_status='unconfirmed', frame_reuses=0, new_raster_attempts=1))

    def test_host_scope_has_complete_denominators_and_partial_unknown_components(self):
        scope = self.value['facts']['scope']
        support = scope['patch_support']
        self.assertEqual(scope['supported_roi_object_count'], 1)
        self.assertEqual(support['objects'][0]['source_triangle_count'], 5)
        self.assertEqual(support['objects'][0]['supported_triangle_count'], 4)
        self.assertEqual(support['objects'][0]['unsupported_triangle_count'], 1)
        self.assertEqual(support['objects'][0]['support_status'], 'partially_supported')
        self.assertEqual(support['objects'][0]['unsupported_components'][0]['status'], 'unknown')
        self.assertEqual(support['objects'][1]['support_status'], 'unsupported')
        self.assertTrue(support['all_triangles_participate_in_occlusion'])
        self.assertEqual(support['regions'][1],
            {'roi_id': 'roi-back', 'object_index': 0, 'triangle_indices': [2, 3]})
        self.assertEqual(scope['objects_without_supported_roi'][0]['host_id'], 'host-1')
        support['objects'][0]['supported_triangle_indices'] = ()
        self.assertEqual(self.session.index.patch_scope[0]['supported_triangle_indices'], (0, 1, 2, 3))

    def test_host_rejects_incomplete_or_overlapping_partition(self):
        for field, value in (('source_triangle_count', 4), ('supported_triangle_indices', (0, 1, 2, 4))):
            with self.subTest(field=field):
                session = copy.deepcopy(self.session)
                session.index.patch_scope[0][field] = value
                with self.assertRaises(ValueError):
                    host_core._patch_scope_facts(session, self.binding)

    def test_default_brief_v2_preserves_multiple_roi_pixels_and_full_maps(self):
        original = copy.deepcopy(self.value)
        default = _tool_result(self.value, is_error=False)
        explicit = _tool_result(self.value, is_error=False, response_detail='brief')
        full = _tool_result(self.value, is_error=False, response_detail='full')
        self.assertEqual(default, explicit)
        brief = json.loads(default['content'][0]['text'])
        diagnostic = json.loads(full['content'][0]['text'])
        self.assertEqual(brief['schema'], 'active-observation-brief-v2')
        self.assertEqual(brief['regions']['columns'][-1], 'triangle_count')
        self.assertEqual(brief['regions']['rows'][1],
            ['roi-back', 0, 'unknown', 'finite_camera_pool_uncovered', 2])
        self.assertEqual(brief['pixels']['rows'], [[0, 0, True, 32, 8, True], [0, 1, True, 0, 0, False]])
        support = brief['scope']['patch_support']
        self.assertEqual(support['object_support']['rows'],
            [[0, 5, 4, 1, 'partially_supported'], [1, 1, 0, 1, 'unsupported']])
        self.assertEqual(support['unsupported_components']['rows'][0],
            [0, 0, 1, 'insufficient_faces', 'unknown', [[4, 4]]])
        self.assertEqual(brief['images']['rows'][0][-1], 'a' * 64)
        self.assertEqual(brief['patch_mapping_version'], 'active-patch-owner-v1')
        self.assertNotIn('patch_roi_ids', brief)
        self.assertEqual(diagnostic['facts']['scope'], json.loads(json.dumps(self.value['facts']['scope'])))
        self.assertEqual(diagnostic['frames'][0]['patch_roi_ids'], ['roi-front', 'roi-back'])
        self.assertEqual(diagnostic['frames'][0]['patch_owner_array_bytes'], 1048576)
        self.assertEqual(default['content'][1:], full['content'][1:])
        self.assertEqual(self.value, original)

    def test_zero_roi_keeps_full_unknown_geometry_scope_and_no_image_claim(self):
        self.session.regions = ()
        for partition in self.session.index.patch_scope:
            count = partition['source_triangle_count']
            partition.update(supported_triangle_count=0, supported_triangle_indices=(),
                unsupported_triangle_count=count,
                unsupported_components=({'triangle_indices': tuple(range(count)), 'reason': 'not_rectangle'},))
        self.value.update(status='unknown', observation_status='no_supported_regions', frames=[])
        facts = self.value['facts']
        facts.update(regions=[], observations=[], scope=host_core._patch_scope_facts(self.session, self.binding))
        facts['coverage'].update(observed_views=[], covered_roi_ids=[], unresolved_roi_ids=[],
            candidate_pool_uncovered_roi_ids=[], state_updates=0)
        self.value['work'].update(raster_attempts=0)
        self.value['generation_work'].update(raster_attempts=0)
        self.value['image_delivery'].update(local_verified_image_count=0,
            mcp_content_constructed_image_count=0, new_raster_attempts=0)
        brief = project_active_observation_brief(self.value)
        self.assertEqual(brief['schema'], 'active-observation-brief-v2')
        self.assertEqual(brief['status'], 'unknown')
        self.assertNotIn('images', brief)
        self.assertEqual(brief['scope']['objects_without_supported_roi']['rows'], [[0, 'unknown'], [1, 'unknown']])
        self.assertEqual(brief['scope']['patch_support']['unsupported_components']['rows'][0][-1], [[0, 4]])

    def test_conflicting_face_maps_or_patch_order_keep_full(self):
        for mutate in (
            lambda value: value['facts']['scope']['patch_support']['objects'][0].update(source_triangle_count=6),
            lambda value: value['facts']['scope']['patch_support']['regions'][1].update(triangle_indices=[0, 1]),
            lambda value: value['frames'][0]['patch_roi_ids'].reverse(),
        ):
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(self.value)
                mutate(value)
                self.assertIsNone(project_active_observation_brief(value))
                audit = {}
                default = _tool_result(value, is_error=False, active_delivery_audit=audit)
                full = _tool_result(value, is_error=False, response_detail='full')
                self.assertEqual(default, full)
                self.assertEqual(audit['projection_status'], 'unsupported_full')

    def test_normal_host_entry_text_request_keeps_patch_scope_without_images(self):
        session = self.session
        initial_facts = copy.deepcopy(self.value['facts'])
        initial_facts['observations'] = []
        initial_facts['coverage'].update(covered_roi_ids=[], unresolved_roi_ids=['roi-front', 'roi-back'],
            observed_views=[], state_updates=0)
        for region in initial_facts['regions']:
            region.update(status='unknown', reason='pending_observation')
        session.short_facts = lambda: copy.deepcopy(initial_facts)
        meshes = [SimpleNamespace(vertices=np.asarray(obj[0]), faces=np.asarray(obj[1]),
                                  edges=np.empty((0, 2), dtype=np.int32)) for obj in self.objects]
        capture = {'unit': 'm', 'source': 'blender', 'coordinate_frame': 'world', 'revision': 'source'}
        with patch.object(host_core, 'source_binding', return_value=copy.deepcopy(self.binding)):
            with patch.object(host_core, 'geometry', return_value=(self.objects, tuple(range(6)), 'geometry')):
                with patch.object(host_core, '_meshes_from_objects', return_value=meshes):
                    with patch.object(host_core, 'freeze_cameras', return_value=session.cameras):
                        with patch.object(host_core, 'prepare_scene_from_parsed', return_value=session) as prepare:
                            with patch.object(host_core, 'scene_from_capture', return_value={'objects': []}):
                                with patch.object(host_core, 'ActiveObservationImages') as images:
                                    result = host_core.observe_capture(capture, self.directory, include_image=False)
        images.assert_not_called()
        self.assertTrue(prepare.call_args.kwargs['diagnostics'])
        self.assertEqual(result['work']['raster_attempts'], 0)
        self.assertEqual(result['facts']['scope']['patch_support']['objects'][0]['supported_triangle_count'], 4)
        self.assertIn('partition', result['stages'])
        self.assertIn('index', result['stages'])


if __name__ == '__main__':
    unittest.main()
