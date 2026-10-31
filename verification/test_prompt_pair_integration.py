"""Independent adversarial tests for observation-only current-scene pairing.

These exercise the public service, hook and MCP paths against fresh mutable
geometry; no user Blender or installed configuration is contacted.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.live_hooks import route_live_hook
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from verification.test_host_runtime import mesh
from verification.test_live_service import SelfLockingHost


NAMED = '检查 BluePart 与 GreyBase 的间隙，只观察，不移动。'
COLORED = '检查 Blender 测试场景中蓝色物体与灰色物体的间隙，只观察，不移动。'


class PromptPairIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config_path = self.base / 'config.json'
        self.config = {'schema_version': '1.0', 'project_root': str(Path(__file__).resolve().parents[1]),
                       'state_file': 'state.json', 'audit_file': 'events.jsonl',
                       'quad_size': 64, 'max_sessions': 8, 'enabled': True}
        self.host = SelfLockingHost()
        base, part = self.host.scene['meshes']
        base.update(name='GreyBase', mark_label='#B0001', color_rgb=[110, 110, 110], is_focal_target=False)
        part.update(name='BluePart', mark_label='#B0002', color_rgb=[20, 70, 230], is_focal_target=False)
        self.start = copy.deepcopy(self.host.scene)
        self.service = self.make_service()

    def make_service(self):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        return LiveSpatialService(self.config_path, host=self.host)

    def tearDown(self):
        self.assertEqual(self.host.calls, 0, 'An observation path called apply_transform')

    def observe(self, instruction=NAMED, **kwargs):
        return self.service.observe('s', task_instruction=instruction, include_image=False, **kwargs)

    def facts(self, result):
        return json.loads(result['routing']['context_text'])

    def assert_pair(self, result, focal='part', reference='base'):
        self.assertEqual(result['status'], 'observed', result.get('pair_resolution'))
        facts = self.facts(result)
        self.assertEqual((facts['focal_id'], facts['reference_id']), (focal, reference))
        self.assertTrue(facts['measurement']['measurement_valid'])
        self.assertIsNone(result['routing']['allow_action'])
        self.assertEqual(result['execution_status'], 'not_requested')
        self.assertEqual(self.host.calls, 0)
        return facts

    def assert_overview(self, result):
        self.assertEqual(result['status'], 'overview', result.get('pair_resolution'))
        facts = self.facts(result)
        self.assertTrue(facts['pair_required_for_clearance'])
        self.assertNotIn('measurement', facts)
        self.assertIsNone(result['routing']['observation_id'])
        self.assertIsNone(result['routing']['allow_action'])
        self.assertEqual(result['execution_status'], 'not_requested')
        return facts

    def test_exact_names_capture_once_and_keep_full_current_geometry(self):
        result = self.observe()
        facts = self.assert_pair(result)
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .1)
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.scene, self.start)

    def test_actual_host_colors_pair_without_relying_on_english_names(self):
        self.host.scene['meshes'][0]['name'] = 'Object.000'
        self.host.scene['meshes'][1]['name'] = 'Object.001'
        self.assert_pair(self.observe(COLORED))

    def test_names_do_not_supply_missing_color_evidence(self):
        self.host.scene['meshes'][1]['color_rgb'] = [230, 30, 30]
        self.assert_overview(self.observe(COLORED))

    def test_color_does_not_certify_part_or_base_class(self):
        for instruction in (
            '检查 Blender 测试场景中蓝色零件与灰色底座的间隙，只观察，不移动。',
            '检查蓝色底座与灰色零件的间隙。',
            'check the gap between the blue part and the gray base',
        ):
            with self.subTest(instruction=instruction):
                self.assert_overview(self.observe(instruction))

    def test_name_order_controls_display_focal_reference_without_motion(self):
        self.assert_pair(self.observe('检查 GreyBase 与 BluePart 的间隙。'), 'base', 'part')

    def test_whole_host_marks_and_full_ids_can_bind_current_pair(self):
        for instruction in ('检查 #B0002 与 #B0001 的间隙。', '检查 part 与 base 的间隙。'):
            with self.subTest(instruction=instruction):
                self.assert_pair(self.observe(instruction))

    def test_quoted_object_names_are_supported(self):
        self.assert_pair(self.observe('检查 "BluePart" 与 "GreyBase" 的间隙。'))

    def test_third_object_does_not_prevent_unique_pair_or_disappear(self):
        third = mesh('obstacle', [2, 2, 2], [.1, .1, .1])
        third.update(name='Obstacle', color_rgb=[20, 210, 20])
        self.host.scene['meshes'].append(third)
        facts = self.assert_pair(self.observe())
        self.assertEqual(len(self.host.scene['meshes']), 3)
        self.assertIn('obstacle', [o['object_id'] for o in facts['objects']])

    def test_duplicate_names_do_not_choose_first(self):
        third = mesh('other_part', [2, 2, 2], [.1, .1, .1])
        third.update(name='BluePart', color_rgb=[20, 210, 20])
        self.host.scene['meshes'].append(third)
        self.host.scene['meshes'][1]['is_focal_target'] = True
        self.assert_overview(self.observe())

    def test_duplicate_colors_do_not_choose_active_or_nearest(self):
        third = mesh('other_blue', [2, 2, 2], [.1, .1, .1])
        third.update(name='Other', color_rgb=[15, 60, 235])
        self.host.scene['meshes'].append(third)
        self.host.scene['meshes'][1]['is_focal_target'] = True
        self.assert_overview(self.observe(COLORED))

    def test_two_objects_alone_do_not_identify_a_pair(self):
        self.assert_overview(self.observe('检查当前场景的间隙。'))

    def test_unresolved_prompt_cannot_fall_back_to_active(self):
        self.host.scene['meshes'][1]['is_focal_target'] = True
        for instruction in ('检查 MissingPart 与 GreyBase 的间隙。', '检查当前场景。',
                            '检查左边蓝色零件与灰色底座的间隙。',
                            '检查红色 BluePart 与 GreyBase 的间隙。'):
            with self.subTest(instruction=instruction):
                self.assert_overview(self.observe(instruction))

    def test_unresolved_prompt_cannot_fall_back_to_configured_pair(self):
        self.config.update(focal_name='BluePart', reference_name='GreyBase')
        self.service = self.make_service()
        self.assert_overview(self.observe('检查 MissingPart 与 GreyBase 的间隙。'))

    def test_empty_instruction_keeps_existing_active_selection_contract(self):
        self.host.scene['meshes'][1]['is_focal_target'] = True
        self.assert_pair(self.observe(''))

    def test_explicit_complete_ids_remain_authoritative_for_observation(self):
        self.assert_pair(self.observe('这里的词语不提供自然语言配对。', focal_id='part', reference_id='base'))

    def test_explicit_partial_ids_must_agree_with_prompt(self):
        for field in ('focal_id', 'reference_id'):
            with self.subTest(field=field):
                self.assert_pair(self.observe(**{field: 'part' if field == 'focal_id' else 'base'}))
                self.assert_overview(self.observe(**{field: 'base' if field == 'focal_id' else 'part'}))

    def test_partial_explicit_id_does_not_complete_unknown_prompt_from_remaining(self):
        self.assert_overview(self.observe('检查当前间隙。', focal_id='part'))

    def test_unknown_explicit_id_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.observe(focal_id='deleted_object')

    def test_negation_quote_meta_and_ununderstood_attributes_do_not_measure(self):
        self.host.scene['meshes'][1]['is_focal_target'] = True
        prompts = [
            '不要检查 BluePart 与 GreyBase 的间隙。',
            '示例：检查 BluePart 与 GreyBase 的间隙。',
            '解释这句话：“检查 BluePart 与 GreyBase 的间隙。”',
            '“检查 BluePart 与 GreyBase 的间隙。”',
            '```\n检查 BluePart 与 GreyBase 的间隙。\n```',
            '如果有空，检查 BluePart 与 GreyBase 的间隙。',
            '检查 BluePart 左侧与 GreyBase 的间隙。',
            '检查不是 BluePart 的零件与 GreyBase 的间隙。',
            '检查 BluePart 与 GreyBase 的间隙，然后检查 GreyBase 与 BluePart 的间隙。',
            '检查 A 与 B 的间隙。',
        ]
        for instruction in prompts:
            with self.subTest(instruction=instruction):
                self.assert_overview(self.observe(instruction))

    def test_whole_names_do_not_match_prefixes(self):
        self.host.scene['meshes'][1]['name'] = 'BluePart.001'
        self.host.scene['meshes'][1]['object_id'] = 'part.001'
        self.assert_overview(self.observe())

    def test_same_object_cannot_fill_both_ends(self):
        self.assert_overview(self.observe('检查 BluePart 与 BluePart 的间隙。'))

    def test_current_capture_rebinds_color_after_scene_change(self):
        third = mesh('new_blue', [2, 2, 2], [.1, .1, .1])
        third.update(name='Other', color_rgb=[20, 210, 20])
        self.host.scene['meshes'].append(third)
        first = self.assert_pair(self.observe(COLORED))
        self.host.scene['meshes'][1]['color_rgb'] = [220, 30, 30]
        self.host.scene['meshes'][2]['color_rgb'] = [20, 70, 230]
        self.host.scene['revision'] = 'r2'
        second = self.assert_pair(self.observe(COLORED), 'new_blue', 'base')
        self.assertNotEqual(first['scene_revision'], second['scene_revision'])
        self.assertEqual(self.host.captures, 2)

    def test_unresolved_followup_invalidates_prior_pair_receipt(self):
        self.assert_pair(self.observe())
        self.host.scene['meshes'][1]['name'] = 'Renamed'
        self.host.scene['revision'] = 'r2'
        self.assert_overview(self.observe())
        state = json.loads((self.base / 'state.json').read_text(encoding='utf-8'))
        self.assertNotIn('s', [row[0] for row in state['runtime']['sessions']])

    def test_resolution_evidence_survives_hook_projection_without_permissions(self):
        result = route_live_hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'hook',
                                 'turn_id': 'test-turn', 'prompt': COLORED}, self.service,
                                invocation_source='manual_probe')
        output = result['hookSpecificOutput']
        self.assertNotIn('permissionDecision', output)
        summary = json.loads(output['additionalContext'])
        self.assertEqual(summary['human_eye_live'], 'observed')
        self.assertEqual(summary['delivery'], 'text_only_hook_no_native_image')
        facts = summary['observation']
        self.assertEqual((facts['focal_id'], facts['reference_id']), ('part', 'base'))
        self.assertIn('pair_resolution', facts)
        self.assertFalse(facts['pair_resolution']['execution_authority'])
        self.assertEqual(facts['pair_resolution']['scene_revision'], facts['scene_revision'])
        self.assertEqual(summary['execution_status'], 'not_requested')
        self.assertEqual(self.host.captures, 1)

    def test_resolution_evidence_survives_brief_and_png_is_not_reinterpreted(self):
        server = LiveSpatialMCPServer(self.service)
        responses = []
        for i, detail in enumerate(('full', 'brief')):
            response = server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': i + 1, 'method': 'tools/call',
                'params': {'name': 'human_eye_scene_observe', 'arguments':
                           {'session_id': 'mcp', 'task_instruction': NAMED, 'response_detail': detail}}})
            content = response['result']['content']
            self.assertFalse(response['result'].get('isError', False))
            metadata = json.loads(next(item['text'] for item in content if item['type'] == 'text'))
            image = next(item for item in content if item['type'] == 'image')
            facts = metadata.get('observation') or json.loads(metadata['routing']['context_text'])
            self.assertEqual(metadata['execution_status'], 'not_requested')
            self.assertEqual(metadata['pair_resolution'], facts['pair_resolution'])
            self.assertFalse(metadata['pair_resolution']['execution_authority'])
            self.assertEqual(metadata['pair_resolution']['scene_revision'], facts['scene_revision'])
            self.assertEqual(metadata['pair_resolution']['scene_fingerprint'], metadata['routing']['scene_fingerprint'])
            responses.append((metadata, facts, image))
        self.assertEqual(responses[1][0]['response_detail'], 'brief')
        self.assertEqual(responses[0][1]['measurement'], responses[1][1]['measurement'])
        self.assertEqual(responses[0][1]['unknown_objects'], responses[1][1]['unknown_objects'])
        self.assertEqual(responses[0][1]['canvas']['object_labels'], responses[1][1]['canvas']['object_labels'])
        self.assertEqual(responses[0][2], responses[1][2])
        self.assertEqual(self.host.captures, 2)


if __name__ == '__main__':
    unittest.main()
