"""Scoped live results through real service/runtime/MCP, without a Blender call.

The host double applies the requested transform and independently stores scene
state. These checks exercise composition boundaries, not copies of the helper.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from verification.test_host_runtime import MutableHost, mesh


PAIR_SCOPE = 'known_mesh_pair_clearance_alignment_and_world_pivot'


class CapturedHost(MutableHost):
    """Like the existing real mutable fixture, with an explicit host capability."""

    def __init__(self):
        super().__init__()
        self.scene['host_execution'] = {
            'schema_version': '1.0', 'operation': 'rigid_transform',
            'supported': True, 'scope': 'independent_static_rigid_meshes', 'reasons': [],
        }

    def capture_scene(self):
        if self.in_transaction:
            return super().capture_scene()
        with self.transaction():
            return super().capture_scene()


class FlowResultContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config_path = self.directory / 'live.json'
        config = {'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'enabled': True, 'quad_size': 64, 'max_sessions': 4,
            'state_file': 'state.json', 'audit_file': 'events.jsonl'}
        self.config_path.write_text(json.dumps(config), encoding='utf-8')
        self.host = CapturedHost()
        self.service = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='contract')
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    @staticmethod
    def goal(target=.1):
        return {'target_clearance_m': target, 'clearance_tolerance_m': 1e-7}

    def observe(self, **changes):
        options = {'focal_id': 'part', 'reference_id': 'base',
                   'task_instruction': 'Measure the part clearance.'}
        options.update(changes)
        return self.service.observe('contract', **options)

    def call(self, name='human_eye_scene_observe', arguments=None):
        request = {'jsonrpc': '2.0', 'id': 17, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments or {
                'focal_id': 'part', 'reference_id': 'base',
                'task_instruction': 'Measure the part clearance.'}}}
        response = self.server.handle_jsonrpc_message(request)
        self.assertNotIn('error', response, response)
        result = response['result']
        texts = [block['text'] for block in result['content'] if block['type'] == 'text']
        self.assertEqual(len(texts), 1)
        return result, json.loads(texts[0])

    def add_far_open_surface(self):
        surface = mesh('open_surface', [20, 0, .2], [.6, .4, .02])
        surface['faces'] = surface['faces'][:2]
        surface['edges'] = None
        self.host.scene['meshes'].append(surface)
        self.host.scene['revision'] = 'r2'

    def deny_nonuniform_transform(self):
        reason = {'object_id': 'part', 'object_name': 'part',
                  'reason': 'nonrigid_or_nonuniform_world_frame'}
        self.host.scene['host_execution'].update(supported=False, reasons=[reason])
        self.host.scene['revision'] = 'r2'
        return reason

    def assert_contract(self, value):
        self.assertEqual(value['result_contract_version'], '1.1')
        self.assertIn(value['observation_status'],
                      {'complete', 'partial', 'unavailable', 'not_requested'})
        self.assertEqual(value['pair_goal']['scope'], PAIR_SCOPE)
        self.assertIn(value['pair_goal']['status'],
            {'not_requested', 'satisfied', 'not_satisfied', 'not_evaluated', 'unknown', 'error'})
        self.assertIn(value['execution_status'],
                      {'not_requested', 'not_executed', 'executed_verified', 'execution_uncertain'})
        self.assertEqual(value['scene_assessment']['scope'], 'all_scene_objects')
        self.assertIn(value['scene_assessment']['status'], {'unknown', 'not_evaluated'})
        self.assertIn(value['action_eligibility']['status'],
                      {'not_evaluated', 'blocked', 'eligible_preview'})
        self.assertIsInstance(value['reason_codes'], list)
        json.dumps(value, allow_nan=False)

    def assert_no_registered_authority(self):
        state = json.loads((self.directory / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['runtime']['sessions'], [])

    def test_complete_observation_does_not_claim_scene_clear_or_execution(self):
        value = self.observe(goal=self.goal())
        self.assert_contract(value)
        self.assertEqual(value['observation_status'], 'complete')
        self.assertEqual(value['scene_assessment']['status'], 'not_evaluated')
        self.assertEqual(value['action_eligibility']['status'], 'not_evaluated')
        self.assertEqual(value['execution_status'], 'not_requested')
        self.assertEqual(self.host.calls, 0)

    def test_goal_success_is_explicitly_bound_to_pair_and_same_snapshot(self):
        value = self.observe(goal=self.goal())
        self.assert_contract(value)
        goal = value['pair_goal']
        self.assertEqual(goal['status'], 'satisfied')
        self.assertTrue(goal['satisfied'])
        self.assertEqual((goal['focal_id'], goal['reference_id']), ('part', 'base'))
        self.assertEqual(goal['scene_revision'], value['routing']['scene_revision'])
        self.assertEqual(goal['evaluation_status'], 'goal_satisfied')
        self.assertTrue(value['task_succeeded'])
        self.assertEqual(value['task_succeeded_scope'], PAIR_SCOPE)

    def test_omitted_goal_never_becomes_goal_success(self):
        value = self.observe()
        self.assert_contract(value)
        self.assertEqual(value['pair_goal']['status'], 'not_requested')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertIsNone(value['task_succeeded_scope'])
        self.assertIsNot(value.get('task_succeeded'), True)

    def test_text_only_complete_observation_is_not_unavailable(self):
        value = self.observe(include_image=False, goal=self.goal())
        self.assert_contract(value)
        self.assertEqual(value['observation_status'], 'complete')
        self.assertEqual(value['pair_goal']['status'], 'satisfied')
        self.assertIsNone(value['routing']['image'])

    def test_nonfocal_open_surface_preserves_pair_goal_and_partial_facts(self):
        self.add_far_open_surface()
        value = self.observe(goal=self.goal())
        self.assert_contract(value)
        self.assertEqual(value['status'], 'partial')
        self.assertEqual(value['observation_status'], 'partial')
        self.assertEqual(value['pair_goal']['status'], 'satisfied')
        self.assertTrue(value['task_succeeded'])
        self.assertEqual(value['task_succeeded_scope'], PAIR_SCOPE)
        self.assertEqual(value['scene_assessment']['status'], 'unknown')
        self.assertIn('open_surface', value['scene_assessment']['unknown_object_ids'])
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        route = value['routing']
        self.assertEqual(route['route'], 'engine')
        self.assertIsNone(route['observation_id'])
        self.assertFalse(route['allow_action'])
        self.assertTrue(route['requires_reobserve'])
        facts = json.loads(route['context_text'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .1)
        self.assertIn('open_surface', {obj['object_id'] for obj in facts['objects']})
        self.assertIsNotNone(route['image'])
        self.assert_no_registered_authority()

    def test_partial_without_goal_remains_not_requested_and_not_authorized(self):
        self.add_far_open_surface()
        value = self.observe()
        self.assert_contract(value)
        self.assertEqual(value['observation_status'], 'partial')
        self.assertEqual(value['pair_goal']['status'], 'not_requested')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertIsNot(value.get('task_succeeded'), True)
        self.assert_no_registered_authority()

    def test_partial_mcp_is_successful_data_delivery_with_one_native_png(self):
        self.add_far_open_surface()
        result, value = self.call(arguments={'focal_id': 'part', 'reference_id': 'base',
            'goal': self.goal()})
        self.assertFalse(result['isError'], value)
        self.assert_contract(value)
        self.assertEqual(value['observation_status'], 'partial')
        self.assertEqual(value['pair_goal']['status'], 'satisfied')
        images = [block for block in result['content'] if block['type'] == 'image']
        self.assertEqual(len(images), 1)
        with Image.open(io.BytesIO(base64.b64decode(images[0]['data'], validate=True))) as picture:
            picture.load()
            self.assertEqual(picture.size, (128, 128))
            self.assertEqual(picture.format, 'PNG')
        self.assertNotIn(images[0]['data'], json.dumps(value))

    def test_partial_cold_and_warm_observations_never_register_action_authority(self):
        self.add_far_open_surface()
        first = self.observe()
        second = self.observe()
        self.assertEqual(first['observation_status'], 'partial')
        self.assertEqual(second['observation_status'], 'partial')
        self.assertTrue(second['routing']['cache_hit'])
        self.assertEqual(first['routing']['image'], second['routing']['image'])
        for value in (first, second):
            self.assertIsNone(value['routing']['observation_id'])
            self.assertFalse(value['routing']['allow_action'])
            self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assert_no_registered_authority()

    def test_former_complete_observation_cannot_authorize_after_partial_scene_change(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64, require_execution_capability=True)
        options = {'session_id': 's', 'task_instruction': 'Measure clearance.',
            'focal_id': 'part', 'reference_id': 'base', 'messages': [], 'include_image': False}
        old = runtime.before_model(**options)['routing']
        self.assertIsNotNone(old['observation_id'])
        self.add_far_open_surface()
        partial = runtime.before_model(**options)['routing']
        self.assertEqual(partial['observation_status'], 'partial')
        self.assertIsNone(partial['observation_id'])
        refused = runtime.execute_action(session_id='s', action=self.action,
                                         observation_id=old['observation_id'])
        self.assertFalse(refused['verified'])
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(runtime.export_state()['sessions'], [])

    def test_partial_transform_is_refused_and_keeps_the_preparation_reason(self):
        self.add_far_open_surface()
        value = self.service.transform('contract', self.action, goal=self.goal())
        self.assert_contract(value)
        self.assertFalse(value['verified'])
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertEqual(value['pair_goal']['status'], 'not_evaluated')
        self.assertEqual(value['pair_goal']['evaluation_status'], 'not_evaluated')
        self.assertEqual(value['goal_evaluation'], 'not_evaluated')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertTrue(value['reason_codes'])
        self.assertTrue(set(value['routing']['reason_codes']).issubset(value['reason_codes']))
        self.assertEqual(self.host.calls, 0)

    def test_restored_service_does_not_turn_persisted_partial_into_permission(self):
        self.add_far_open_surface()
        self.observe()
        self.observe()
        other = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        value = other.preview_action('contract', self.action)
        self.assert_contract(value)
        self.assertFalse(value['allow_action'])
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertEqual(self.host.calls, 0)
        self.assert_no_registered_authority()

    def test_nonuniform_capability_rejection_keeps_specific_object_reason(self):
        reason = self.deny_nonuniform_transform()
        value = self.service.transform('contract', self.action)
        self.assert_contract(value)
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertIn('host_execution_capability_required', value['reason_codes'])
        self.assertIn(reason['reason'], value['reason_codes'])
        self.assertIn(reason, value['host_execution']['reasons'])
        self.assertEqual(self.host.calls, 0)

    def test_readable_nonuniform_observation_explains_why_actions_are_blocked(self):
        reason = self.deny_nonuniform_transform()
        value = self.observe(goal=self.goal())
        self.assert_contract(value)
        self.assertEqual(value['observation_status'], 'complete')
        self.assertEqual(value['pair_goal']['status'], 'satisfied')
        self.assertIsNotNone(value['routing']['image'])
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertIn(reason['reason'], value['reason_codes'])
        self.assertIn(reason['reason'], value['action_eligibility']['reason_codes'])
        self.assertIn(reason, value['host_execution']['reasons'])
        self.assertEqual(self.host.calls, 0)

    def test_untrusted_axes_do_not_hide_captured_nonuniform_capability_reasons(self):
        reason = self.deny_nonuniform_transform()
        self.host.scene['meshes'][1].update(axes_confidence='ambiguous',
                                           axes_source='unverified_imported_frame')
        for operation in (self.service.preview_action, self.service.transform):
            with self.subTest(operation=operation.__name__):
                captures = self.host.captures
                value = operation('contract', self.action)
                self.assert_contract(value)
                self.assertEqual(value['action_eligibility']['status'], 'blocked')
                self.assertIn(reason['reason'], value['reason_codes'])
                self.assertIn(reason, value['host_execution']['reasons'])
                self.assertEqual(self.host.calls, 0)
                self.assertEqual(self.host.captures, captures + 1)

    def test_capability_refusal_preserves_requested_but_unevaluated_goal_scope(self):
        reason = self.deny_nonuniform_transform()
        self.host.scene['meshes'][1].update(axes_confidence='ambiguous',
                                           axes_source='unverified_imported_frame')
        with patch('human_eye_plugin.host_runtime.evaluate_spatial_goal') as evaluate:
            value = self.service.transform('contract', self.action, goal=self.goal())
        evaluate.assert_not_called()
        self.assert_contract(value)
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assertEqual(value['pair_goal']['status'], 'not_evaluated')
        self.assertEqual(value['pair_goal']['evaluation_status'], 'not_evaluated')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertEqual(value['task_succeeded_scope'], PAIR_SCOPE)
        self.assertIn(reason['reason'], value['reason_codes'])
        self.assertIn(reason, value['host_execution']['reasons'])
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 1)

    def test_missing_observation_is_an_explicit_action_rejection(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64, require_execution_capability=True)
        value = runtime.execute_action(session_id='none', action=self.action)
        self.assert_contract(value)
        self.assertEqual(value['status'], 'observation_required')
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertIn('observation_required', value['reason_codes'])
        self.assertEqual(self.host.calls, 0)

    def test_invalid_action_is_an_explicit_rejection_without_host_write(self):
        invalid = {**self.action, 'scale': [1, 2, 1]}
        value = self.service.transform('contract', invalid)
        self.assert_contract(value)
        self.assertEqual(value['status'], 'invalid_action')
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertIn('invalid_action', value['reason_codes'])
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assertEqual(self.host.calls, 0)

    def test_invalid_goal_is_an_explicit_rejection_without_host_write(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64, require_execution_capability=True)
        runtime.before_model(session_id='s', task_instruction='Measure clearance.',
            focal_id='part', reference_id='base', messages=[], include_image=False)
        value = runtime.execute_action(session_id='s', action=self.action,
                                       goal={'not_a_goal': True})
        self.assert_contract(value)
        self.assertEqual(value['status'], 'invalid_goal')
        self.assertEqual(value['pair_goal']['status'], 'error')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertEqual(value['action_eligibility']['status'], 'blocked')
        self.assertIn('invalid_goal', value['reason_codes'])
        self.assertEqual(self.host.calls, 0)

    def test_nonuniform_capability_is_explained_in_mcp_error_metadata(self):
        reason = self.deny_nonuniform_transform()
        result, value = self.call('human_eye_transform', {'action': self.action})
        self.assertTrue(result['isError'])
        self.assert_contract(value)
        self.assertIn(reason['reason'], value['reason_codes'])
        self.assertIn(reason, value['host_execution']['reasons'])
        self.assertEqual(self.host.calls, 0)

    def test_verified_execution_with_unsatisfied_goal_stays_verified(self):
        value = self.service.transform('contract', self.action, goal=self.goal(.1))
        self.assert_contract(value)
        self.assertTrue(value['executed'])
        self.assertTrue(value['verified'])
        self.assertTrue(value['execution_verified'])
        self.assertEqual(value['execution_status'], 'executed_verified')
        self.assertEqual(value['pair_goal']['status'], 'not_satisfied')
        self.assertFalse(value['pair_goal']['satisfied'])
        self.assertFalse(value['task_succeeded'])
        self.assertEqual(value['task_succeeded_scope'], PAIR_SCOPE)
        self.assertEqual(self.host.calls, 1)

    def test_mcp_verified_execution_is_not_a_tool_error_when_pair_goal_fails(self):
        result, value = self.call('human_eye_transform',
            {'action': self.action, 'goal': self.goal(.1)})
        self.assertFalse(result['isError'], value)
        self.assertEqual(value['execution_status'], 'executed_verified')
        self.assertEqual(value['pair_goal']['status'], 'not_satisfied')
        self.assertEqual(self.host.calls, 1)

    def test_no_goal_after_verified_execution_does_not_invent_task_success(self):
        value = self.service.transform('contract', self.action)
        self.assert_contract(value)
        self.assertEqual(value['execution_status'], 'executed_verified')
        self.assertEqual(value['pair_goal']['status'], 'not_requested')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertIsNot(value.get('task_succeeded'), True)
        self.assertIsNone(value['task_succeeded_scope'])

    def test_goal_evaluator_error_does_not_reclassify_verified_mutation(self):
        with patch('human_eye_plugin.host_runtime.evaluate_spatial_goal',
                   side_effect=RuntimeError('optional evaluator unavailable')):
            value = self.service.transform('contract', self.action, goal=self.goal(.15))
        self.assert_contract(value)
        self.assertEqual(value['execution_status'], 'executed_verified')
        self.assertTrue(value['executed'])
        self.assertTrue(value['verified'])
        self.assertEqual(value['pair_goal']['status'], 'error')
        self.assertIsNone(value['pair_goal']['satisfied'])
        self.assertEqual(self.host.calls, 1)

    def test_noop_can_satisfy_pair_goal_without_claiming_execution(self):
        command = {**self.action, 'translation': [0, 0, 0]}
        value = self.service.transform('contract', command, goal=self.goal())
        self.assert_contract(value)
        self.assertEqual(value['status'], 'no_op')
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assertEqual(value['pair_goal']['status'], 'satisfied')
        self.assertFalse(value['executed'])
        self.assertEqual(self.host.calls, 0)

    def test_uncertain_host_mutation_never_claims_success_or_safe_retry(self):
        self.host.mode = 'partial_failure'
        value = self.service.transform('contract', self.action, goal=self.goal(.15))
        self.assert_contract(value)
        self.assertEqual(value['execution_status'], 'execution_uncertain')
        self.assertIsNone(value['executed'])
        self.assertFalse(value['verified'])
        self.assertIsNot(value['pair_goal']['satisfied'], True)
        self.assertEqual(self.host.calls, 1)
        other = self.service.transform('other', self.action)
        self.assertFalse(other['verified'])
        self.assertEqual(self.host.calls, 1)

    def test_execution_and_readback_failures_remain_uncertain_in_scoped_results(self):
        modes = [('partial_failure', 'host_execution_uncertain'),
                 ('readback_failure', 'host_readback_uncertain'),
                 ('incorrect', 'host_readback_rejected')]
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        for mode, expected_status in modes:
            with self.subTest(mode=mode):
                folder = self.directory / mode
                folder.mkdir()
                path = folder / 'live.json'
                path.write_text(json.dumps(config), encoding='utf-8')
                host = CapturedHost()
                host.mode = mode
                service = LiveSpatialService(path, host=host, production_mode=True)
                value = service.transform('s', self.action, goal=self.goal(.15))
                self.assert_contract(value)
                self.assertEqual(value['status'], expected_status)
                self.assertEqual(value['execution_status'], 'execution_uncertain')
                self.assertEqual(value['action_eligibility']['status'], 'blocked')
                self.assertIsNone(value['executed'])
                self.assertIsNot(value['pair_goal']['satisfied'], True)
                self.assertEqual(host.calls, 1)

    def test_mcp_exception_after_actual_write_never_claims_not_executed(self):
        real_transform = self.service.transform

        def completed_then_delivery_error(*args, **kwargs):
            value = real_transform(*args, **kwargs)
            self.assertTrue(value['verified'])
            raise RuntimeError('simulated response-layer failure after verified mutation')

        with patch.object(self.service, 'transform', side_effect=completed_then_delivery_error):
            result, value = self.call('human_eye_transform', {'action': self.action})
        self.assertTrue(result['isError'])
        self.assertEqual(self.host.calls, 1)
        self.assertNotEqual(value.get('execution_status'), 'not_executed')
        self.assertIsNot(value.get('executed'), False)

    def test_successful_final_image_is_from_readback_even_if_prepare_policy_changes(self):
        value = self.service.transform('contract', self.action, goal=self.goal(.15))
        self.assertEqual(value['execution_status'], 'executed_verified')
        self.assertIsNotNone(value['routing']['image'])
        facts = json.loads(value['routing']['context_text'])
        self.assertEqual(facts['scene_revision'], value['actual_scene_revision'])
        self.assertEqual(value['pair_goal']['scene_revision'], value['actual_scene_revision'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .15)


if __name__ == '__main__':
    unittest.main()
