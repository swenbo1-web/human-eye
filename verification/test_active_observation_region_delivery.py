"""Region-location representation checks using the existing synthetic fixture.

The inherited fixture setup creates constant PNGs and source metadata. Tests
exercise delivery and mocked Host wiring without a raster or Blender call.
"""

import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import active_observation_host as host_core
from human_eye_plugin.live_spatial_mcp import _tool_result, project_active_observation_brief
from verification.test_active_observation_patch_delivery import ActiveObservationPatchDeliveryTests


WORLD_FIELDS = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
PIXEL_FIELDS = ('visible_pixel_bounds', 'visible_pixel_anchor')


class ActiveObservationRegionDeliveryTests(unittest.TestCase):
    def setUp(self):
        fixture = ActiveObservationPatchDeliveryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.value = copy.deepcopy(fixture.value)
        self.historical = copy.deepcopy(fixture.value)
        self.value['facts']['location_conventions'] = host_core._location_conventions(
            {'views': [{'size_px': [512, 512]}]})
        for index, region in enumerate(self.value['facts']['regions']):
            region.update(center_world_m=[0.5, 0.5, 1 if index == 0 else 0],
                half_edge_u_world_m=[0.5, 0, 0], half_edge_v_world_m=[0, 0.5, 0],
                front_direction_world=[0, 0, 1])
        for observation in self.value['facts']['observations']:
            observation['pixel_rows'][0].update(visible_pixel_bounds=[10, 20, 17, 23],
                                                visible_pixel_anchor=[13, 21])
            observation['pixel_rows'][1].update(visible_pixel_bounds=None, visible_pixel_anchor=None)

    def test_default_and_brief_v3_share_locations_and_full_preserves_evidence(self):
        snapshot = copy.deepcopy(self.value)
        default = _tool_result(self.value, is_error=False)
        explicit = _tool_result(self.value, is_error=False, response_detail='brief')
        full = _tool_result(self.value, is_error=False, response_detail='full')
        self.assertEqual(default, explicit)
        brief = json.loads(default['content'][0]['text'])
        complete = json.loads(full['content'][0]['text'])
        self.assertEqual(brief['schema'], 'active-observation-brief-v3')
        self.assertEqual(brief['regions']['columns'][-4:], list(WORLD_FIELDS))
        self.assertEqual(brief['regions']['rows'][0][-4:], [[0.5, 0.5, 1], [0.5, 0, 0], [0, 0.5, 0], [0, 0, 1]])
        self.assertEqual(brief['pixels']['columns'][-2:], list(PIXEL_FIELDS))
        self.assertEqual(brief['pixels']['rows'][0][-2:], [[10, 20, 17, 23], [13, 21]])
        self.assertEqual(brief['pixels']['rows'][1], [0, 1, True, 0, 0, False, None, None])
        self.assertEqual(brief['location_conventions'], complete['facts']['location_conventions'])
        self.assertEqual(complete['facts'], json.loads(json.dumps(self.value['facts'])))
        self.assertEqual(default['content'][1:], full['content'][1:])
        self.assertEqual(self.value, snapshot)

    def test_non_readable_visible_regions_retain_bounds_and_owned_anchor(self):
        pixel = self.value['facts']['observations'][0]['pixel_rows'][0]
        for front, boundary in ((False, 8), (True, 0)):
            with self.subTest(front_facing=front, boundary=boundary):
                pixel.update(front_facing=front, contrasting_boundary_pixels=boundary, readable=False)
                self.value['facts']['observations'][0]['readable_roi_ids'] = []
                self.value['facts']['regions'][0].update(status='unknown', reason='pixel_evidence_insufficient')
                self.value['facts']['coverage'].update(covered_roi_ids=[], unresolved_roi_ids=['roi-front', 'roi-back'])
                brief = project_active_observation_brief(self.value)
                self.assertEqual(brief['pixels']['rows'][0][-2:], [[10, 20, 17, 23], [13, 21]])
                self.assertFalse(brief['pixels']['rows'][0][5])

    def test_fraction_scalars_are_preserved_and_conflicting_location_fields_keep_full(self):
        self.value['facts']['regions'][0]['center_world_m'][0] = '1/2'
        brief = project_active_observation_brief(self.value)
        self.assertEqual(brief['regions']['rows'][0][-4][0], '1/2')
        mutations = (
            lambda value: value['facts']['regions'][0].pop('front_direction_world'),
            lambda value: value['facts']['regions'][0].update(front_direction_world=[0, '1/0', 1]),
            lambda value: value['facts']['observations'][0]['pixel_rows'][0].pop('visible_pixel_anchor'),
            lambda value: value['facts']['observations'][0]['pixel_rows'][0].update(visible_pixel_anchor=[9, 20]),
            lambda value: value['facts']['observations'][0]['pixel_rows'][1].update(visible_pixel_bounds=[0, 0, 0, 0]),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(self.value)
                mutate(value)
                self.assertIsNone(project_active_observation_brief(value))
                audit = {}
                result = _tool_result(value, is_error=False, active_delivery_audit=audit)
                full = _tool_result(value, is_error=False, response_detail='full')
                self.assertEqual(result, full)
                self.assertEqual(audit['projection_status'], 'unsupported_full')

    def test_historical_v2_representation_keeps_original_columns_and_native_images(self):
        result = _tool_result(self.historical, is_error=False)
        brief = json.loads(result['content'][0]['text'])
        self.assertEqual(brief['schema'], 'active-observation-brief-v2')
        self.assertEqual(brief['regions']['columns'], ['roi_id', 'object_index', 'status', 'reason', 'triangle_count'])
        self.assertEqual(len(brief['pixels']['columns']), 6)
        self.assertNotIn('location_conventions', brief)
        self.assertEqual(result['content'][1:], _tool_result(self.value, is_error=False)['content'][1:])

    def test_prediction_and_zero_roi_keep_world_or_unknown_scope_with_empty_pixels(self):
        value = copy.deepcopy(self.value)
        value.update(status='predicted', observation_status='prediction_only', frames=[])
        facts = value['facts']
        facts['observations'] = []
        facts['coverage'].update(observed_views=[], covered_roi_ids=[],
            unresolved_roi_ids=['roi-front', 'roi-back'], state_updates=0)
        for region in facts['regions']:
            region.update(status='unknown', reason='pending_observation')
        value['work'].update(raster_attempts=0)
        value['image_delivery'].update(local_verified_image_count=0,
            mcp_content_constructed_image_count=0, new_raster_attempts=0)
        brief = project_active_observation_brief(value)
        self.assertEqual(brief['schema'], 'active-observation-brief-v3')
        self.assertIn('center_world_m', brief['regions']['columns'])
        self.assertNotIn('pixels', brief)
        self.assertNotIn('images', brief)
        session = copy.deepcopy(self.fixture.session)
        session.regions = ()
        for row in session.index.patch_scope:
            count = row['source_triangle_count']
            row.update(supported_triangle_count=0, supported_triangle_indices=(),
                unsupported_triangle_count=count, unsupported_components=(
                    {'triangle_indices': tuple(range(count)), 'reason': 'not_rectangle'},))
        facts.update(regions=[], scope=host_core._patch_scope_facts(session, value['binding']))
        facts['coverage'].update(unresolved_roi_ids=[], candidate_pool_uncovered_roi_ids=[])
        value.update(status='unknown', observation_status='no_supported_regions')
        empty = project_active_observation_brief(value)
        self.assertEqual(empty['schema'], 'active-observation-brief-v3')
        self.assertNotIn('regions', empty)
        self.assertEqual(empty['scope']['objects_without_supported_roi']['rows'], [[0, 'unknown'], [1, 'unknown']])

    def test_host_copies_world_clock_and_declares_one_shared_coordinate_contract(self):
        session = self.fixture.session
        session.cameras = {'views': [{'size_px': [512, 512]}]}
        world_clock = dict(started_ns=10, closed_ns=20, elapsed_ns=10)
        session.diagnostics['stages']['world_descriptions'] = world_clock
        initial = copy.deepcopy(self.value['facts'])
        initial['observations'] = []
        initial['coverage'].update(observed_views=[], covered_roi_ids=[],
            unresolved_roi_ids=['roi-front', 'roi-back'], state_updates=0)
        for region in initial['regions']:
            region.update(status='unknown', reason='pending_observation')
        meshes = [SimpleNamespace(vertices=np.asarray(obj[0]), faces=np.asarray(obj[1]),
                                  edges=np.empty((0, 2), dtype=np.int32)) for obj in session.objects]
        with (
            patch.object(session, 'short_facts', create=True, return_value=initial) as facts,
            patch.object(host_core, 'source_binding', return_value=copy.deepcopy(self.value['binding'])),
            patch.object(host_core, 'scene_from_capture', return_value={'objects': []}),
            patch.object(host_core, 'geometry', return_value=(session.objects, tuple(range(6)), 'geometry')),
            patch.object(host_core, '_meshes_from_objects', return_value=meshes),
            patch.object(host_core, 'freeze_cameras', return_value=session.cameras),
            patch.object(host_core, 'prepare_scene_from_parsed', return_value=session) as prepare,
            patch.object(host_core, 'ActiveObservationImages') as images,
        ):
            result = host_core.observe_capture({}, self.fixture.directory, include_image=False)
        images.assert_not_called()
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(facts.call_count, 1)
        self.assertEqual(result['stages']['world_descriptions'], world_clock)
        self.assertIsNot(result['stages']['world_descriptions'], world_clock)
        self.assertEqual(result['facts']['location_conventions']['image_size_px'], [512, 512])
        self.assertEqual(result['facts']['location_conventions']['pixel_axis_order'], ['x', 'y'])
        self.assertEqual(result['facts']['regions'][0]['center_world_m'], [0.5, 0.5, 1])


if __name__ == '__main__':
    unittest.main()
