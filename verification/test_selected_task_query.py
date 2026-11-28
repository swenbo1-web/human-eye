"""Selected task routing, binding and transport regression checks without Blender."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.task_query import bind_objects, task_result
from verification.test_blender_mcp_host import _reply, _server
from verification.test_host_runtime import mesh
from verification.test_live_service import SelfLockingHost
from verification import test_task_query as original_tests


ROOT = Path(__file__).resolve().parents[1]


class SelectedHost(SelfLockingHost):
    def __init__(self):
        super().__init__()
        self.instances = {'part': '11', 'base': '12'}
        self.document = 'document-1'
        self.selected_calls = []

    def capture_task_scene(self, selectors):
        self.selected_calls.append(copy.deepcopy(selectors))
        bound, rows, pair_reason = bind_objects(self.scene, selectors)
        selected = {item['object_id']: item for item in bound if item is not None}
        scene = {'unit': 'm', 'coordinate_frame': 'world', 'source': self.scene['source'],
            'capture_scope': 'selected_objects',
            'meshes': [copy.deepcopy(selected[key]) for key in sorted(selected)],
            'task_selection': {'selectors': copy.deepcopy(selectors), 'bindings': rows,
                'pair_reason': pair_reason, 'candidate_count': len(self.scene['meshes'])},
            'host_identity': {'schema_version': '1.0', 'capture_scope': 'selected_objects',
                'document_epoch': self.document,
                'object_instances': {key: self.instances[key] for key in selected}}}
        scene['revision'] = 'selected:' + hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest()
        return scene


class SelectedTaskQueryTests(unittest.TestCase):
    setUp = original_tests.TaskQueryTests.setUp
    query = original_tests.TaskQueryTests.query
    observe = original_tests.TaskQueryTests.observe
    pair = original_tests.TaskQueryTests.pair

    def use_selected_host(self):
        self.host = SelectedHost()
        self.service = LiveSpatialService(self.config, host=self.host)

    def test_service_uses_one_selected_capture_and_original_facts(self):
        legacy = self.pair(['aabb', 'center_delta', 'axis_gap', 'surface_clearance', 'solid_relation'])
        self.use_selected_host()
        with patch.object(self.host, 'capture_scene', side_effect=AssertionError('full capture')):
            result = self.pair(['aabb', 'center_delta', 'axis_gap', 'surface_clearance', 'solid_relation'])
        self.assertEqual(result['facts'], legacy['facts'])
        self.assertEqual(len(self.host.selected_calls), 1)
        self.assertEqual(result['binding']['capture_scope'], 'selected_objects')
        self.assertEqual(result['binding']['candidate_count'], 2)
        self.assertEqual(result['binding']['selected_count'], 2)
        self.assertFalse(result['execution_authority'])

    def test_name_and_id_keep_equal_facts_and_bind_raw_syntax(self):
        self.use_selected_host()
        name = self.observe()
        by_id = self.observe(objects=[{'id': 'part'}])
        self.assertEqual(name['facts'], by_id['facts'])
        self.assertNotEqual(name['binding']['scene_fingerprint'], by_id['binding']['scene_fingerprint'])

    def test_ambiguity_survives_zero_selected_meshes(self):
        self.use_selected_host()
        other = mesh('other', [4, 0, 0], [1, 1, 1])
        other['name'] = 'part'
        self.host.scene['meshes'].append(other)
        result = self.observe()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['binding']['objects'][0]['reason'], 'object_name_ambiguous')
        self.assertEqual(result['binding']['selected_count'], 0)
        self.assertEqual(result['binding']['candidate_count'], 3)
        self.assertEqual(result['facts']['aabb'][0]['reason'], 'selector_unresolved')

    def test_zero_candidates_and_two_missing_are_legal_partial(self):
        self.use_selected_host()
        self.host.scene['meshes'] = []
        result = self.pair(['aabb', 'surface_clearance'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['binding']['candidate_count'], 0)
        self.assertEqual(result['binding']['selected_count'], 0)
        self.assertEqual(result['facts']['surface_clearance']['reason'], 'selector_unresolved')

    def test_duplicate_selectors_capture_one_and_preserve_pair_unknown(self):
        self.use_selected_host()
        result = self.observe(['aabb', 'surface_clearance'], [{'id': 'base'}, {'name': 'base'}])
        self.assertEqual(result['binding']['selected_count'], 1)
        self.assertEqual(result['facts']['aabb'][0], result['facts']['aabb'][1])
        self.assertEqual(result['facts']['surface_clearance']['reason'], 'pair_selectors_resolve_to_same_object')

    def test_background_geometry_does_not_change_selected_fingerprint(self):
        self.use_selected_host()
        before = self.observe()
        self.host.scene['meshes'][0]['vertices'][0][0] += 1
        self.host.scene['revision'] = 'background-edited'
        after = self.observe()
        self.assertEqual(before['binding']['scene_revision'], after['binding']['scene_revision'])
        self.assertEqual(before['binding']['scene_fingerprint'], after['binding']['scene_fingerprint'])

    def test_target_geometry_instance_and_document_are_fresh(self):
        self.use_selected_host()
        previous = self.observe()['binding']['scene_fingerprint']
        changes = [lambda: self.host.scene['meshes'][1]['vertices'][0].__setitem__(0, -0.12),
                   lambda: self.host.instances.__setitem__('part', 'replacement'),
                   lambda: setattr(self.host, 'document', 'document-2')]
        for change in changes:
            change()
            current = self.observe()['binding']['scene_fingerprint']
            self.assertNotEqual(previous, current)
            previous = current

    def test_selected_requires_scope_identity_and_exact_binding_coverage(self):
        self.use_selected_host()
        capture = self.host.capture_task_scene([{'name': 'part'}])
        _validated_scene(capture, _task_capture=True)
        with self.assertRaisesRegex(ValueError, 'capture_scope'):
            _validated_scene(capture)
        bad = copy.deepcopy(capture)
        bad.pop('host_identity')
        with self.assertRaisesRegex(ValueError, 'host_identity'):
            _validated_scene(bad, _task_capture=True)
        bad = copy.deepcopy(capture)
        bad['task_selection']['bindings'][0]['name'] = 'different'
        with self.assertRaisesRegex(ValueError, 'binding'):
            _validated_scene(bad, _task_capture=True)
        bad = copy.deepcopy(capture)
        bad['task_selection']['bindings'][0] = {'status': 'unknown', 'selector': {'name': 'part'},
                                               'reason': 'object_not_found'}
        with self.assertRaisesRegex(ValueError, 'coverage'):
            _validated_scene(bad, _task_capture=True)

    def test_captured_selectors_cannot_be_reused_for_a_different_query(self):
        self.use_selected_host()
        captured = self.host.capture_task_scene([{'name': 'part'}])
        scene, meshes, fingerprint = _validated_scene(captured, _task_capture=True)
        with self.assertRaisesRegex(ValueError, 'selectors differ'):
            task_result(scene, meshes, fingerprint, self.query(objects=[{'id': 'part'}]), None, lambda _: None)

    def test_sdk_without_selected_method_keeps_complete_capture(self):
        result = self.observe()
        self.assertEqual(self.host.captures, 1)
        self.assertNotIn('capture_scope', result['binding'])


class SelectedTaskBridgeTests(unittest.TestCase):
    def test_fixed_command_one_rpc_and_document_recording(self):
        epoch = 'a' * 64
        result = {'revision': 'selected-1', 'host_identity': {'document_epoch': epoch}}
        with _server(lambda request: _reply(request, result=result)) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            with host.observation_transaction():
                self.assertEqual(host.capture_task_scene([{'name': 'part'}]), result)
            self.assertEqual(host._observation_document_epoch, epoch)
        self.assertEqual(len(requests), 1)
        command, request = requests[0]
        self.assertEqual(request['command'], 'capture_task')
        self.assertEqual(request['params'], {'selectors': [{'name': 'part'}]})
        self.assertIn("getattr(_host, 'capture_task_scene')(**_request['params'])", command['params']['code'])
        self.assertLessEqual(len(json.dumps(command,separators=(',',':')).encode()),1024*1024)

    def test_four_maximum_escaped_selectors_fit_new_bound_and_outer_transport(self):
        selectors = [{'name': 'A' + '\x01' * 255} for _ in range(4)]
        with _server(lambda request: _reply(request)) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            # The first resident install has a separate 1 MiB envelope budget.
            host._resident_ready=True
            host.capture_task_scene(selectors)
        command, request = requests[0]
        self.assertGreater(len(json.dumps(request, separators=(',', ':')).encode()), 4096)
        self.assertLessEqual(len(json.dumps(command, separators=(',', ':')).encode()), 64*1024)
        self.assertEqual(request['params']['selectors'], selectors)

    def test_original_native_command_limit_and_exact_argument_shape_remain(self):
        host = BlenderMCPHost(ROOT)
        with self.assertRaisesRegex(ValueError, '4096'):
            host._observation_code('last_readonly_native_audit', {'request_id': 'x' * 5000}, 'request')
        with self.assertRaisesRegex(ValueError, 'Invalid fixed'):
            host._observation_code('capture_task', {'selectors': [], 'extra': True}, 'request')
        with self.assertRaisesRegex(ValueError, '8192'):
            host._observation_code('capture_task', {'selectors': [{'name': 'x' * 9000}]}, 'request')


if __name__ == '__main__':
    unittest.main()
