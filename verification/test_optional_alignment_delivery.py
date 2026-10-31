"""Distance-only evidence crosses the local MCP boundary without hidden writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_module1_operators import SpatialAnomalySniffer
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer
from verification.test_host_runtime import mesh
from verification.test_live_service import SelfLockingHost


class OptionalAlignmentDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        config = self.folder / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SelfLockingHost()
        self.host.scene['meshes'].append(mesh('far', [10, 0, 0], [.2, .2, .2]))
        self.initial_scene = copy.deepcopy(self.host.scene)
        self.service = LiveSpatialService(config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='alignment-delivery')

    def call(self, arguments):
        response = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
        self.assertIn('result', response, response)
        wire = response['result']
        return wire, json.loads(wire['content'][0]['text'])

    def rpc(self, arguments):
        wire, metadata = self.call(arguments)
        self.assertFalse(wire['isError'], metadata)
        return wire, metadata

    @staticmethod
    def facts(metadata):
        if 'observation' in metadata:
            return metadata['observation']
        return json.loads(metadata['routing']['context_text'])

    @staticmethod
    def distance_args(**changes):
        arguments = {'focal_id': 'part', 'reference_id': 'base', 'include_image': False,
            'query': {'mode': 'top1', 'max_exact_pairs': 1, 'alignment_evidence': False}}
        arguments.update(changes)
        return arguments

    def assert_distance_fact(self, metadata):
        facts = self.facts(metadata)
        self.assertEqual(facts['unit'], 'm')
        self.assertEqual(facts['coordinate_frame'], 'world')
        self.assertEqual(facts['focal_id'], 'part')
        self.assertEqual(facts['reference_id'], 'base')
        measured = facts['measurement']
        self.assertTrue(measured['measurement_valid'])
        self.assertTrue(measured['clearance_exact'])
        self.assertEqual(measured['measurement_kind'], 'exact')
        self.assertAlmostEqual(measured['signed_clearance_m'], .1, places=12)
        self.assertEqual(facts['query']['alignment_evidence'], False)
        self.assertIsNot(measured.get('axes_valid'), True)
        for field in ['contact_normal_angle_deg', 'tangent_yaw_mismatch_deg']:
            self.assertIsNone(measured.get(field))
        return facts

    def assert_no_images(self, wire):
        self.assertEqual([item for item in wire['content'] if item['type'] == 'image'], [])

    def assert_read_only(self):
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.scene, self.initial_scene)

    def test_schema_declares_separate_boolean_image_and_alignment_controls(self):
        schema = next(item for item in LIVE_MCP_TOOLS_SCHEMA if item['name'] == 'human_eye_scene_observe')['inputSchema']
        image = schema['properties']['include_image']
        alignment = schema['properties']['query']['properties']['alignment_evidence']
        self.assertEqual(image['type'], 'boolean')
        self.assertTrue(image['default'])
        self.assertEqual(alignment['type'], 'boolean')
        self.assertNotIn('include_image', schema.get('required', []))
        self.assertNotIn('alignment_evidence', schema['properties']['query'].get('required', []))

    def test_full_and_brief_distance_only_keep_exact_facts_and_capture_fresh(self):
        arguments = self.distance_args()
        original = copy.deepcopy(arguments)
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance',
                   side_effect=AssertionError('distance-only observation ran legacy probe')) as probe, \
                patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',
                      side_effect=AssertionError('no-image observation rendered a canvas')) as render:
            full_wire, full = self.rpc(arguments)
            brief_wire, brief = self.rpc({**arguments, 'response_detail': 'brief'})
        probe.assert_not_called()
        render.assert_not_called()
        full_facts = self.assert_distance_fact(full)
        brief_facts = self.assert_distance_fact(brief)
        self.assertEqual(full_facts['measurement'], brief_facts['measurement'])
        self.assertEqual(full['query_result'], brief['query_result'])
        self.assertEqual(full['query_result']['top1']['nearest_object_ids'], ['base'])
        self.assertEqual(full['query_result']['top1']['excluded_by_lower_bound_ids'], ['far'])
        self.assert_no_images(full_wire)
        self.assert_no_images(brief_wire)
        self.assertEqual(arguments, original)
        self.assertEqual(self.host.captures, 2)
        self.assert_read_only()

    def test_default_still_returns_native_image_and_alignment_evidence(self):
        original = SpatialAnomalySniffer.probe_closest_clearance
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance', wraps=original) as probe:
            wire, metadata = self.rpc({'focal_id': 'part', 'reference_id': 'base'})
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertTrue([item for item in wire['content'] if item['type'] == 'image'])
        facts = self.facts(metadata)
        self.assertTrue(facts['measurement']['axes_valid'])
        self.assertIsNotNone(facts['measurement']['contact_normal_angle_deg'])
        self.assertEqual(self.host.captures, 1)
        self.assert_read_only()

    def test_no_image_alone_does_not_implicitly_disable_alignment(self):
        original = SpatialAnomalySniffer.probe_closest_clearance
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance', wraps=original) as probe:
            wire, metadata = self.rpc({'focal_id': 'part', 'reference_id': 'base', 'include_image': False})
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertTrue(self.facts(metadata)['measurement']['axes_valid'])
        self.assert_no_images(wire)
        self.assertEqual(self.host.captures, 1)
        self.assert_read_only()

    def test_invalid_boolean_flags_fail_in_mcp_before_capture(self):
        bad_values = [None, 0, 1, 'false', [], {}]
        cases = [{'focal_id': 'part', 'reference_id': 'base', 'include_image': value} for value in bad_values]
        cases += [{'focal_id': 'part', 'reference_id': 'base', 'include_image': False,
            'query': {'alignment_evidence': value}} for value in bad_values]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                wire, metadata = self.call(arguments)
                self.assertTrue(wire['isError'], metadata)
                self.assertEqual(metadata['status'], 'error')
        self.assertEqual(self.host.captures, 0)
        self.assert_read_only()

    def test_invalid_boolean_flags_fail_in_sdk_before_capture(self):
        for value in [None, 0, 1, 'false', [], {}]:
            with self.subTest(image=value), self.assertRaises(ValueError):
                self.service.observe('sdk', focal_id='part', reference_id='base', include_image=value)
            with self.subTest(alignment=value), self.assertRaises(ValueError):
                self.service.observe('sdk', focal_id='part', reference_id='base',
                    include_image=False, query={'alignment_evidence': value})
        self.assertEqual(self.host.captures, 0)
        self.assert_read_only()

    def test_false_alignment_with_requested_or_default_image_is_rejected_before_capture(self):
        for arguments in [self.distance_args(include_image=True),
                          {'focal_id': 'part', 'reference_id': 'base', 'query': {'alignment_evidence': False}}]:
            with self.subTest(arguments=arguments):
                wire, metadata = self.call(arguments)
                self.assertTrue(wire['isError'], metadata)
                self.assertEqual(metadata['status'], 'error')
        for changes in [{'include_image': True}, {}]:
            with self.subTest(sdk=changes), self.assertRaises(ValueError):
                self.service.observe('sdk', focal_id='part', reference_id='base',
                    query={'alignment_evidence': False}, **changes)
        self.assertEqual(self.host.captures, 0)
        self.assert_read_only()

    def test_no_pair_overview_with_no_image_does_not_invent_measurement(self):
        self.host.scene['meshes'] = [row for row in self.host.scene['meshes'] if row['object_id'] == 'part']
        self.initial_scene = copy.deepcopy(self.host.scene)
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance',
                   side_effect=AssertionError('single-object overview ran a pair probe')) as probe:
            wire, metadata = self.rpc({'include_image': False, 'query': {'alignment_evidence': False}})
        probe.assert_not_called()
        self.assertEqual(metadata['status'], 'overview')
        self.assertEqual(metadata['routing']['execution_scope'], 'scene_overview_only')
        self.assertIsNone(metadata['routing']['observation_id'])
        self.assert_no_images(wire)
        self.assertEqual(self.host.captures, 1)
        self.assert_read_only()

    def test_explicit_angular_goal_still_runs_its_own_probe(self):
        arguments = self.distance_args(goal={'max_contact_normal_angle_deg': 0.0})
        original = SpatialAnomalySniffer.probe_closest_clearance
        with patch('human_eye_plugin.task_verification.SpatialAnomalySniffer.probe_closest_clearance', wraps=original) as probe:
            wire, metadata = self.rpc(arguments)
        self.assertEqual(probe.call_count, 1)
        self.assert_distance_fact(metadata)
        verification = metadata['goal_verification']
        self.assertTrue(verification['checks']['contact_normal']['passed'])
        self.assertEqual(verification['measurements']['contact_normal_angle_deg'], 0.)
        self.assertTrue(verification['task_succeeded'])
        self.assert_no_images(wire)
        self.assertEqual(self.host.captures, 1)
        self.assert_read_only()

    def test_angular_probe_failure_cannot_be_hidden_by_distance_only_observation(self):
        arguments = self.distance_args(goal={'max_contact_normal_angle_deg': 0.0})
        with patch('human_eye_plugin.task_verification.SpatialAnomalySniffer.probe_closest_clearance',
                   side_effect=RuntimeError('angular evidence unavailable')) as probe:
            wire, metadata = self.rpc(arguments)
        self.assertEqual(probe.call_count, 1)
        self.assert_distance_fact(metadata)
        verification = metadata['goal_verification']
        self.assertFalse(verification['checks']['contact_normal']['passed'])
        self.assertFalse(verification['task_succeeded'])
        self.assertIn('angular_measurement_invalid', verification['reason_codes'])
        self.assertIsNone(verification['measurements']['contact_normal_angle_deg'])
        self.assert_no_images(wire)
        self.assertEqual(self.host.captures, 1)
        self.assert_read_only()

    def test_later_alignment_request_does_not_reuse_distance_only_pair_evidence(self):
        fast_wire, fast = self.rpc(self.distance_args())
        self.assert_distance_fact(fast)
        original = SpatialAnomalySniffer.probe_closest_clearance
        with patch('human_eye_plugin.auto_router.SpatialAnomalySniffer.probe_closest_clearance', wraps=original) as probe:
            full_wire, full = self.rpc({'focal_id': 'part', 'reference_id': 'base',
                'include_image': False, 'query': {'mode': 'top1', 'max_exact_pairs': 1, 'alignment_evidence': True}})
        self.assertEqual(probe.call_count, 1)
        self.assertTrue(self.facts(full)['measurement']['axes_valid'])
        self.assertFalse(full['routing']['cache_hit'])
        self.assert_no_images(fast_wire)
        self.assert_no_images(full_wire)
        self.assertEqual(self.host.captures, 2)
        self.assert_read_only()


if __name__ == '__main__':
    unittest.main()
