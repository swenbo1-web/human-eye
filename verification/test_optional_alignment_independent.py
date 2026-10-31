"""Independent distance-only contracts and fresh write boundaries.

Analytical box intervals and supplied hole fixtures are the geometry oracle;
no live Blender, production state or model invocation is used.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SpatialAnomalySniffer
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, LIVE_MCP_TOOLS_SCHEMA
from human_eye_plugin.query_policy import validate_query
from verification.test_auto_router import action, box, observation, scene
from verification.test_complex_scene_quality import fixture
from verification.test_live_service import SelfLockingHost
from verification.test_observation_queries import ranking_scene
from verification.test_partial_observation import open_plane, partial_scene


PROBE = 'human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance'
EXACT = 'human_eye_plugin.auto_router.measure_pair_geometry'
NO_ALIGNMENT = {'alignment_evidence': False}
ALIGNMENT_FIELDS = ('axes_valid', 'axes_check', 'contact_normal_angle_deg',
                    'tangent_yaw_mismatch_deg', 'control_frame_trustworthy')


def facts(result):
    return json.loads(result['context_text'])


def box_distance(a, b):
    left, right = np.asarray(a['vertices']), np.asarray(b['vertices'])
    gap = np.maximum(np.maximum(left.min(0)-right.max(0), right.min(0)-left.max(0)), 0.)
    return math.sqrt(sum(float(value)**2 for value in gap))


class OptionalAlignmentIndependentTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, value=None, *, query=None, router=None, **changes):
        return (router or self.router).handle_event(observation(scene=value or scene(),
            include_image=False, query=copy.deepcopy(NO_ALIGNMENT if query is None else query), **changes))

    def assert_not_requested(self, record):
        for field in ALIGNMENT_FIELDS:
            self.assertIn(field, record)
            self.assertIsNone(record[field], (field, record))
        self.assertEqual(record['alignment_evidence'], {
            'status': 'not_requested', 'reason': 'explicit_distance_only_observation',
            'execution_authority': False})
        self.assertNotIn('alignment_state', record)
        self.assertNotIn('display_signed_clearance_m', record)
        self.assertNotIn('alignment_state', record.get('legacy_display', {}))

    def test_false_is_explicit_and_bad_types_never_normalize_to_a_boolean(self):
        query = validate_query(NO_ALIGNMENT)
        self.assertIs(query['alignment_evidence'], False)
        self.assertEqual(validate_query(query), query)
        self.assertIs(validate_query({'alignment_evidence': True}).get('alignment_evidence', True), True)
        for value in (None, 0, 1, '', 'false', [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_query({'alignment_evidence': value})

    def test_distance_only_never_runs_probe_and_never_fakes_convex_witnesses(self):
        value = scene()
        with patch(PROBE, side_effect=AssertionError('Distance-only ran display/alignment probe')):
            result = self.observe(value)
        self.assertEqual(result['route'], 'engine', result)
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['axes_valid'])
        measured = facts(result)['measurement']
        self.assert_not_requested(measured)
        self.assertAlmostEqual(measured['signed_clearance_m'], box_distance(*value['meshes']), places=14)
        self.assertTrue(measured['clearance_exact'])
        self.assertEqual(measured['measurement_kind'], 'exact')
        self.assertEqual(measured['signed_clearance_m'], measured['strict_geometry']['signed_clearance_m'])
        self.assertIsNone(measured['point_a_world'])
        self.assertIsNone(measured['point_b_world'])
        self.assertNotEqual(measured.get('witness_source'), 'current_original_full_mesh_surface_features')
        self.assertEqual(measured['rigid_frame'], facts(result)['rigid_frame'])

    def test_all_measured_nearest_pairs_skip_probe_but_keep_real_order(self):
        with patch(PROBE, side_effect=AssertionError('Extra pair ran alignment')), \
                patch(EXACT, wraps=measure_pair_geometry) as exact:
            result = self.observe(ranking_scene(), query={'mode': 'nearest', **NO_ALIGNMENT})
        self.assertEqual(result['query_result']['ranked_object_ids'], ['axial-B', 'diagonal-A', 'base'])
        self.assertEqual(exact.call_count, 3)
        for contact in facts(result)['scene_contacts']:
            self.assert_not_requested(contact)
            self.assertTrue(contact['measurement_valid'])

    def test_omitted_and_true_preserve_full_probe_and_finite_angles(self):
        for query in ({}, {'alignment_evidence': True}):
            with self.subTest(query=query), patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe:
                result = self.observe(query=query, router=HumanEyeAutoRouter(quad_size=64))
            self.assertGreaterEqual(probe.call_count, 1)
            measured = facts(result)['measurement']
            self.assertIsInstance(measured['axes_valid'], bool)
            self.assertTrue(math.isfinite(measured['contact_normal_angle_deg']))
            self.assertTrue(math.isfinite(measured['tangent_yaw_mismatch_deg']))

    def test_microgap_and_micro_penetration_keep_unrounded_signs(self):
        for z, expected in ((.25005, .00005), (.24995, -.00005)):
            value = scene()
            value['meshes'][1] = box('part', [0, 0, z], [.3, .2, .1], True)
            with self.subTest(z=z), patch(PROBE, side_effect=AssertionError('Rounded display probe used')):
                result = self.observe(value)
            measured = facts(result)['measurement']
            self.assertTrue(measured['measurement_valid'])
            self.assertAlmostEqual(measured['signed_clearance_m'], expected, places=13)
            self.assertEqual(measured['clearance_state'], 'positive_clearance' if expected > 0 else 'negative_clearance')
            self.assert_not_requested(measured)

    def test_penetration_stays_certified_escape_not_exact_or_false_flush(self):
        value = scene()
        value['meshes'][1] = box('part', [0, 0, .22], [.3, .2, .1], True)
        result = self.observe(value)
        measured = facts(result)['measurement']
        self.assertTrue(measured['is_penetrating'])
        self.assertLess(measured['signed_clearance_m'], 0)
        self.assertEqual(measured['measurement_kind'], 'certified_penetration')
        self.assertFalse(measured['clearance_exact'])
        self.assertIsNone(measured['point_a_world'])
        self.assertIsNone(measured['point_b_world'])
        self.assert_not_requested(measured)

    def test_unsupported_extra_is_still_unknown_and_not_actionable(self):
        result = self.observe(partial_scene(), query={'mode': 'nearest', **NO_ALIGNMENT})
        self.assertEqual(result['observation_status'], 'partial')
        self.assertIn('open', result['query_result']['unresolved_object_ids'])
        self.assertIn('open', result['scene_assessment']['unknown_object_ids'])
        self.assertIsNone(result['observation_id'])
        denied = self.router.handle_event(action(result))
        self.assertFalse(denied['allow_action'])

    def test_unsupported_reference_cannot_become_a_valid_distance(self):
        value = scene()
        value['meshes'][0] = open_plane('base', center=(0., 0., .1))
        with patch(PROBE, side_effect=AssertionError('Unsupported target reached probe')):
            result = self.observe(value)
        self.assertFalse(result.get('measurement_valid'))
        self.assertIn('reference_pair_geometry_unknown', result['reason_codes'])
        self.assertFalse(result.get('allow_action'))

    def test_orthogonal_hole_and_L_keep_actual_original_surface_witnesses(self):
        for name in ('square_hole', 'L_slot'):
            value = fixture(name)
            with self.subTest(name=name), patch(PROBE, side_effect=AssertionError('Orthogonal distance ran probe')):
                result = self.observe(value['scene'], focal_id=value['focal'], reference_id=value['reference'])
            measured = facts(result)['measurement']
            self.assertTrue(measured['measurement_valid'])
            self.assertEqual(measured['measurement_method'], 'exact_orthogonal_cell_union_sat')
            self.assertAlmostEqual(measured['signed_clearance_m'], value['oracle']['clearance_m'], places=12)
            self.assertEqual(measured['point_a_world'], measured['strict_geometry']['point_a_world'])
            self.assertEqual(measured['point_b_world'], measured['strict_geometry']['point_b_world'])
            self.assertAlmostEqual(math.dist(measured['point_a_world'], measured['point_b_world']), measured['signed_clearance_m'], places=12)
            self.assertEqual(measured['witness_source'], 'current_original_full_mesh_surface_features')
            self.assert_not_requested(measured)

    def test_invalid_host_frame_remains_invalid_even_with_exact_distance(self):
        value = scene()
        value['meshes'][1]['local_axes'] = [[1, 0, 0], [1, 0, 0], [0, 0, 1]]
        result = self.observe(value)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['rigid_frame_valid'])
        self.assertTrue(result['requires_reobserve'])
        self.assertIsNone(result['axes_valid'])
        denied = self.router.handle_event(action(result))
        self.assertFalse(denied['allow_action'])
        self.assertIn('unverified_geometry_or_frame', denied['reason_codes'])

    def test_full_none_full_pair_cache_cannot_launder_missing_angles(self):
        with patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe:
            full = self.observe(query={})
            count = probe.call_count
            distance = self.observe()
            self.assertEqual(probe.call_count, count)
            again = self.observe(query={})
        self.assertGreater(count, 0)
        self.assert_not_requested(facts(distance)['measurement'])
        self.assertIsNotNone(facts(full)['measurement']['contact_normal_angle_deg'])
        self.assertEqual(facts(full)['measurement'], facts(again)['measurement'])
        self.assertEqual(facts(distance)['measurement_cache']['misses'], 1)
        self.assertEqual(facts(again)['measurement_cache']['hits'], 1)

    def test_persisted_distance_only_observation_does_not_satisfy_full_query(self):
        self.observe()
        saved = self.router.export_state()
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(saved)
        with patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe:
            full = self.observe(query={}, router=restored)
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertFalse(full['cache_hit'])
        self.assertIsNotNone(facts(full)['measurement']['contact_normal_angle_deg'])

    def test_distance_only_top1_retains_query_proof_and_lower_bound_kinds(self):
        value = scene()
        value['meshes'].append(box('far', [4, 0, .35], [.2, .2, .2]))
        with patch(PROBE, side_effect=AssertionError('top1 ran display probe')):
            result = self.observe(value, query={'mode': 'top1', 'max_exact_pairs': 1, **NO_ALIGNMENT})
        query = result['query_result']
        self.assertEqual(query['status'], 'complete')
        self.assertEqual(query['top1']['nearest_object_ids'], ['base'])
        self.assertEqual(query['top1']['excluded_by_lower_bound_ids'], ['far'])
        far = next(item for item in facts(result)['scene_contacts'] if item['object_id'] == 'far')
        self.assertEqual(far['measurement_kind'], 'lower_bound')
        self.assertFalse(far['clearance_exact'])

    def test_image_true_false_alignment_and_bad_boolean_reject_before_kernels(self):
        for changes in ({'include_image': True, 'query': NO_ALIGNMENT},
                        {'include_image': False, 'query': {'alignment_evidence': 0}}):
            event = observation(**changes)
            with self.subTest(changes=changes), patch(PROBE, side_effect=AssertionError('Invalid request ran probe')), \
                    patch(EXACT, side_effect=AssertionError('Invalid request measured')):
                result = self.router.handle_event(event)
            self.assertNotEqual(result.get('route'), 'engine')
            self.assertFalse(result.get('measurement_valid'))
        # The existing top-level event type contract raises before routing.
        with patch(PROBE, side_effect=AssertionError('Invalid request ran probe')), \
                patch(EXACT, side_effect=AssertionError('Invalid request measured')), self.assertRaises(ValueError):
            self.router.handle_event(observation(include_image='false', query=NO_ALIGNMENT))

    def test_distance_only_before_action_still_runs_fresh_probe_and_full_obstacles(self):
        value = scene()
        value['meshes'].append(box('obstacle', [.5, 0, .35], [.2, .2, .2]))
        result = self.observe(value)
        with patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe, \
                patch.object(self.router.scene_cache, 'pair_measurement', side_effect=AssertionError('Write reused cached measurement')):
            checked = self.router.handle_event(action(result,
                action={'translation': [.5, 0, 0]}, query=NO_ALIGNMENT))
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['candidate_collision'])

    def test_after_action_ignores_distance_only_query_and_builds_fresh_full_evidence(self):
        value = scene()
        result = self.observe(value)
        allowed = self.router.handle_event(action(result, action={'translation': [0, 0, .05]}))
        self.assertTrue(allowed['allow_action'], allowed)
        pending = dict(self.router.export_state()['sessions'])['a']['pending']
        actual = copy.deepcopy(value)
        actual['revision'] = 'r2'
        actual['meshes'][1] = pending['candidate']
        with patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe:
            checked = self.router.handle_event(observation(scene=actual, event='after_action',
                include_image=False, query=NO_ALIGNMENT))
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertTrue(checked['measurement_valid'])
        self.assertIsNotNone(facts(checked)['measurement']['contact_normal_angle_deg'])

    def test_after_action_distance_only_argument_cannot_hide_changed_obstacle(self):
        value = scene()
        value['meshes'].append(box('obstacle', [2, 0, .4], [.2, .2, .2]))
        result = self.observe(value)
        allowed = self.router.handle_event(action(result, action={'translation': [0, 0, .05]}))
        self.assertTrue(allowed['allow_action'], allowed)
        pending = dict(self.router.export_state()['sessions'])['a']['pending']
        actual = copy.deepcopy(value)
        actual['revision'] = 'r2-external-obstacle-change'
        actual['meshes'][1] = pending['candidate']
        actual['meshes'][2] = box('obstacle', [0, 0, .4], [.2, .2, .2])
        checked = self.router.handle_event(observation(scene=actual, event='after_action',
            include_image=False, query=NO_ALIGNMENT))
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['host_collision_detected'])


class OptionalAlignmentServiceIndependentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = Path(temporary.name) / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='optional-alignment-independent')

    def rpc(self, arguments):
        return self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})['result']

    def test_schema_exposes_bounded_text_entry_without_changing_image_default(self):
        schema = next(item for item in LIVE_MCP_TOOLS_SCHEMA if item['name'] == 'human_eye_scene_observe')['inputSchema']
        self.assertEqual(schema['properties']['include_image']['type'], 'boolean')
        self.assertIs(schema['properties']['include_image']['default'], True)
        self.assertEqual(schema['properties']['query']['properties']['alignment_evidence']['type'], 'boolean')

    def test_mcp_text_entry_captures_fresh_twice_without_probe_or_image(self):
        args = {'focal_id': 'part', 'reference_id': 'base', 'include_image': False, 'query': NO_ALIGNMENT}
        with patch(PROBE, side_effect=AssertionError('MCP distance-only ran probe')), \
                patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', side_effect=AssertionError('Text MCP rendered')):
            first = self.rpc(args)
            second = self.rpc({**args, 'response_detail': 'brief'})
        for wire in (first, second):
            self.assertFalse(wire['isError'], wire)
            self.assertFalse(any(row['type'] == 'image' for row in wire['content']))
            result = json.loads(wire['content'][0]['text'])
            self.assertTrue(result.get('measurement_valid', result.get('routing', {}).get('measurement_valid')))
            self.assertFalse(result['scene_assessment'].get('execution_authority', False))
        self.assertEqual(self.host.captures, 2)
        self.assertEqual(self.host.calls, 0)

    def test_invalid_service_combination_never_contacts_host(self):
        for include_image, query in ((True, NO_ALIGNMENT), (1, NO_ALIGNMENT),
                                     (False, {'alignment_evidence': 'false'})):
            with self.subTest(include_image=include_image, query=query), self.assertRaises(ValueError):
                self.service.observe('s', focal_id='part', reference_id='base',
                    include_image=include_image, query=query)
        self.assertEqual(self.host.captures, 0)

    def test_invalid_mcp_combination_rejects_before_capture(self):
        for changes in ({'include_image': True, 'query': NO_ALIGNMENT},
                        {'query': NO_ALIGNMENT}, {'include_image': False, 'query': {'alignment_evidence': 1}}):
            with self.subTest(changes=changes):
                wire = self.rpc({'focal_id': 'part', 'reference_id': 'base', **changes})
            self.assertTrue(wire['isError'], wire)
        self.assertEqual(self.host.captures, 0)

    def test_explicit_angular_goal_still_evaluates_fresh_probe_separately(self):
        with patch(PROBE, wraps=SpatialAnomalySniffer.probe_closest_clearance) as probe:
            result = self.service.observe('s', focal_id='part', reference_id='base',
                include_image=False, query=NO_ALIGNMENT, goal={'max_contact_normal_angle_deg': .5})
        self.assertGreaterEqual(probe.call_count, 1)
        measured = facts(result['routing'])['measurement']
        self.assertIsNone(measured['contact_normal_angle_deg'])
        self.assertEqual(measured['alignment_evidence']['status'], 'not_requested')
        self.assertIsNotNone(result['goal_verification']['measurements']['contact_normal_angle_deg'])
        self.assertEqual(self.host.calls, 0)


if __name__ == '__main__':
    unittest.main()
