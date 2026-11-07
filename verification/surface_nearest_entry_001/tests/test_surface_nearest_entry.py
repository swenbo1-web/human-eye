"""Twelve preregistered offline entry groups; fake bpy is not Blender evidence.

The controlled parent runner binds test_blender_host_contracts._module and its
BlenderSceneHost/BlenderHostError aliases to the verified current host module
before importing this file. Every candidate packet below comes from that real
capture_nearest_candidates implementation, and every nearest result executes
the accepted summarizer and geometry kernel. No final nearest result is faked.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import live_spatial_mcp, task_query
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError, _REQUEST_BUDGET
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, _tool_result, _validate_arguments
from human_eye_plugin.query_policy import validate_query
from verification import test_m4_capture_001 as capture_fixture
from verification.bound_source_fix_001.test_source_validation import source_fixture, second_face
from verification.test_live_service import SelfLockingHost


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[2]
MODE = {'mode': 'surface_nearest'}
TOOL = 'human_eye_scene_observe'
EVIDENCE = {}


class ActualCandidateHost:
    """Service adapter around actual guarded host + legacy fake-RNA fixture."""

    timeout_s = 10.

    def __init__(self, xs=(0., 2., 100.)):
        self.backend, self.objects = source_fixture(xs)
        self.candidate_calls = []
        self.scene_calls = self.selected_calls = self.name_calls = self.calls = 0
        self.last_packet = None
        self.after_capture = None

    @property
    def focal_id(self):
        return self.backend.object_id(self.objects[0])

    def object(self, index):
        obj = self.objects[index]
        return {'id': self.backend.object_id(obj), 'name': obj.name}

    def transaction(self):
        return self.backend.transaction()

    def capture_nearest_candidates(self, focal_id, deadline_ns, max_response_bytes):
        self.candidate_calls.append({'focal_id': focal_id, 'deadline_ns': deadline_ns,
            'max_response_bytes': max_response_bytes, 'started_ns': time.perf_counter_ns()})
        self.last_packet = self.backend.capture_nearest_candidates(
            focal_id, deadline_ns, max_response_bytes)
        if self.after_capture is not None:
            self.after_capture()
        return self.last_packet

    def capture_scene(self):
        self.scene_calls += 1
        raise AssertionError('surface_nearest must not capture a complete scene')

    def capture_task_scene(self, selectors):
        self.selected_calls += 1
        raise AssertionError('surface_nearest must not use selected task capture')

    def list_objects(self):
        self.name_calls += 1
        raise AssertionError('names must come from the same retained capture')

    def apply_transform(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('surface_nearest is read-only')


def add_retained_degenerate_face(obj, world_x=1.):
    """First triangle remains at x=100; a late collinear face reaches x=1."""
    second_face(obj)
    local_x = world_x - float(obj.matrix_world[0][3])
    for vertex, y in zip(obj.data.vertices[3:], (2., 3., 4.)):
        vertex.co = (local_x, y, 0.)
    obj.bound_box = [(x, y, z) for x in (local_x, 0.)
        for y in (0., 4.) for z in (0., 1.)]


class SurfaceNearestEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='offline-entry-', dir=TESTS)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / 'live.json'
        self.config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
            'project_root': str(ROOT), 'quad_size': 64,
            'state_file': 'state.json', 'audit_file': 'audit.jsonl'}), encoding='utf8')
        self.use_host(ActualCandidateHost())

    def use_host(self, host):
        self.host = host
        self.service = LiveSpatialService(self.config, host=host)
        self.server = LiveSpatialMCPServer(self.service, 'surface-entry-tests')

    def args(self, **changes):
        return {'session_id': 'entry-read', 'focal_id': self.host.focal_id,
            'include_image': False, 'query': dict(MODE), **changes}

    def observe(self, **changes):
        return self.service.observe(**self.args(**changes))

    def audit_work(self):
        events = [json.loads(line) for line in self.service.audit_path.read_text(
            encoding='utf8').splitlines()]
        return [event['task_work'] for event in events if event['event'] == 'observe'][-1]

    def assert_only_candidate_capture(self, count=1):
        self.assertEqual(len(self.host.candidate_calls), count)
        self.assertEqual((self.host.scene_calls, self.host.selected_calls,
            self.host.name_calls, self.host.calls), (0, 0, 0, 0))
        self.assertTrue(all(obj.assignments == 0 for obj in self.host.objects))

    def test_01_explicit_mode_schema_and_mode_only_query(self):
        self.assertEqual(validate_query(MODE), MODE)
        self.assertIn('surface_nearest', live_spatial_mcp._QUERY_SCHEMA['properties']['mode']['enum'])
        _validate_arguments(TOOL, self.args())
        for extra in ({'objects': [{'name': 'O0'}]}, {'object_ids': ['x']},
                {'max_exact_pairs': 1}, {'alignment_evidence': False},
                {'native_visual': {'mode': 'projection'}}, {'focal_id': 'x'},
                {'packet': {}}, {'mode_alias': 'nearest'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_query({**MODE, **extra})
        self.assert_only_candidate_capture(0)

    def test_02_invalid_envelopes_fail_before_any_host_read(self):
        cases = ({'include_image': True}, {'focal_id': None}, {'focal_id': ''},
            {'focal_id': ' '}, {'focal_id': 1}, {'focal_id': 'x' * 257},
            {'reference_id': 'other'}, {'goal': {}}, {'scene_delta': {}},
            {'query': {**MODE, 'object_ids': ['other']}}, {'session_id': ''})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.observe(**changes)
        for missing in ('focal_id', 'session_id', 'include_image'):
            args = self.args()
            args.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.server._call_tool(TOOL, args)
        for changes in ({'reference_id': 'other'}, {'goal': {}}, {'scene_delta': {}},
                {'include_image': True}, {'query': {**MODE, 'objects': []}}):
            with self.subTest(mcp=changes), self.assertRaises(ValueError):
                self.server._call_tool(TOOL, self.args(**changes))
        self.assert_only_candidate_capture(0)

    def test_03_one_actual_packet_reaches_real_summary_and_no_history(self):
        original = task_query.surface_nearest_result
        packets = []
        def summarize(packet, *args, **kwargs):
            packets.append(packet)
            return original(packet, *args, **kwargs)
        with patch.object(task_query, 'surface_nearest_result', side_effect=summarize):
            result = self.observe()
        self.assertEqual(len(packets), 1)
        self.assertIs(packets[0], self.host.last_packet)
        self.assertIsInstance(self.host.backend, capture_fixture.m.BlenderSceneHost)
        self.assertEqual(result['result_kind'], 'surface_nearest')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['focal'], self.host.object(0))
        self.assertEqual(result['nearest_objects'], [self.host.object(1)])
        self.assertEqual(result['best_known_objects'], result['nearest_objects'])
        self.assertEqual(result['distance_m'], 2.)
        self.assertEqual(result['best_known_distance_m'], 2.)
        self.assertEqual(result['unit'], 'm')
        self.assertEqual(result['coverage'], {'targets_excluding_focal': 2,
            'distance_valid': 1, 'strictly_excluded': 1, 'unresolved': 0})
        self.assertEqual(result['unresolved'], [])
        self.assertFalse(result['execution_authority'])
        state = json.loads(self.service.state_path.read_text(encoding='utf8'))['runtime']
        self.assertEqual(state['sessions'], [])
        self.assertEqual(state['router']['scene_memory']['frames'], [])
        self.assert_only_candidate_capture()
        EVIDENCE['route'] = {'work': self.audit_work(), 'coverage': result['coverage'],
            'host_work': self.host.last_packet['work'], 'history_frames': 0}

    def test_04_named_exact_ties_are_stable_and_current(self):
        self.use_host(ActualCandidateHost((0., 2., 2., 100.)))
        for obj, name in zip(self.host.objects, ('焦点', '左候选', '右候选', '远处')):
            obj.name = obj.name_full = name
        result = self.observe()
        expected = sorted((self.host.object(1), self.host.object(2)), key=lambda row: row['id'])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['focal'], self.host.object(0))
        self.assertEqual(result['nearest_objects'], expected)
        self.assertEqual(result['best_known_objects'], expected)
        self.assertEqual(result['distance_m'], 2.)
        self.assertEqual(result['coverage']['distance_valid'], 2)
        self.assert_only_candidate_capture()

    def test_05_retained_degenerate_target_is_named_partial(self):
        add_retained_degenerate_face(self.host.objects[2])
        result = self.observe()
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['nearest_objects'])
        self.assertIsNone(result['distance_m'])
        self.assertEqual(result['best_known_objects'], [self.host.object(1)])
        self.assertEqual(result['best_known_distance_m'], 2.)
        self.assertEqual(result['unresolved'], [{**self.host.object(2),
            'reason': 'surface_degenerate_triangle'}])
        self.assertEqual(result['coverage'], {'targets_excluding_focal': 2,
            'distance_valid': 1, 'strictly_excluded': 0, 'unresolved': 1})
        self.assert_only_candidate_capture()
        EVIDENCE['partial'] = {'status': result['status'], 'work': self.audit_work(),
            'coverage': result['coverage'], 'reason': result['unresolved'][0]['reason']}

    def test_06_all_unknown_has_no_global_or_best_known_distance(self):
        self.use_host(ActualCandidateHost((0., 100.)))
        add_retained_degenerate_face(self.host.objects[1])
        result = self.observe()
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['nearest_objects'])
        self.assertIsNone(result['distance_m'])
        self.assertEqual(result['best_known_objects'], [])
        self.assertIsNone(result['best_known_distance_m'])
        self.assertEqual(result['unresolved'], [{**self.host.object(1),
            'reason': 'surface_degenerate_triangle'}])
        self.assertEqual(result['coverage']['unresolved'], 1)
        self.assert_only_candidate_capture()

    def test_07_current_capture_repeats_but_real_pair_measurement_hits_cache(self):
        first = self.observe()
        cold = self.audit_work()
        second = self.observe()
        warm = self.audit_work()
        self.assertEqual((cold['pair_calls'], cold['kernel_calls'], cold['cache_hits'],
            cold['exact_rank_calls']), (1, 1, 0, 1))
        self.assertEqual((warm['pair_calls'], warm['kernel_calls'], warm['cache_hits'],
            warm['exact_rank_calls']), (1, 0, 1, 1))
        for key in ('status', 'focal', 'nearest_objects', 'best_known_objects',
                'distance_m', 'best_known_distance_m', 'coverage', 'unresolved'):
            self.assertEqual(first[key], second[key])
        self.assert_only_candidate_capture(2)
        EVIDENCE['cache'] = {'cold': cold, 'warm': warm}

    def test_08_loaded_source_rejection_precedes_host_capture(self):
        self.service.production_mode = True
        rejected = {'compatible': False, 'check_complete': False,
            'status': 'unverified', 'reasons': ['runtime_executed_source_unverified']}
        with (patch('human_eye_plugin.live_service.check_task_source', return_value=rejected) as check,
                patch('human_eye_plugin.live_service.check_source_drift',
                    side_effect=AssertionError('must use existing read-only loaded-generation check'))):
            result = self.observe()
        check.assert_called_once_with()
        self.assertEqual(result['status'], 'implementation_mismatch')
        self.assertEqual(result['reason_codes'], ['runtime_executed_source_unverified'])
        self.assertFalse(result['allow_action'])
        self.assert_only_candidate_capture(0)

    def test_09_original_deadline_guards_before_and_after_actual_capture(self):
        self.service.request_budget_s = 20.
        with self.service._request_budget() as request:
            request['deadline'] = time.monotonic() - 1.
            with self.assertRaises(RequestBudgetError):
                self.observe()
        self.assert_only_candidate_capture(0)
        def expire():
            _REQUEST_BUDGET.get()['deadline'] = time.monotonic() - 1.
        self.host.after_capture = expire
        with patch.object(task_query, 'surface_nearest_result',
                side_effect=AssertionError('expired capture must not reach summary')):
            with self.assertRaises(RequestBudgetError):
                self.observe()
        self.assert_only_candidate_capture()
        call = self.host.candidate_calls[0]
        self.assertGreater(call['deadline_ns'], call['started_ns'])
        self.assertLessEqual(call['deadline_ns'] - call['started_ns'], 10_000_000_000)
        self.assertEqual(call['max_response_bytes'], 64 * 1024 * 1024)

    def test_10_mcp_keeps_original_deadline_through_encoding_and_publication(self):
        self.service.request_budget_s = 20.
        original = live_spatial_mcp._tool_result
        def expire(*args, **kwargs):
            request = _REQUEST_BUDGET.get()
            self.assertIsNotNone(request)
            request['deadline'] = time.monotonic() - 1.
            return original(*args, **kwargs)
        with patch.object(live_spatial_mcp, '_tool_result', side_effect=expire):
            with self.assertRaises(RequestBudgetError):
                self.server._call_tool(TOOL, self.args())
        self.assert_only_candidate_capture()

    def test_11_mcp_delivers_one_compact_text_body_without_private_payload(self):
        response = self.server._call_tool(TOOL, self.args())
        self.assertFalse(response['isError'])
        self.assertEqual(set(response), {'content', 'isError'})
        self.assertEqual(len(response['content']), 1)
        self.assertEqual(response['content'][0]['type'], 'text')
        text = response['content'][0]['text']
        result = json.loads(text)
        self.assertEqual(result['result_kind'], 'surface_nearest')
        self.assertEqual(result['nearest_objects'], [self.host.object(1)])
        self.assertNotIn(self.host.object(2)['id'], text)
        for key in ('excluded', 'nearest_ids', 'best_known_ids', 'focal_id',
                'capture', 'meshes', 'vertices', 'faces', '_exact_distance_sq',
                'routing', 'model_observation', 'structuredContent'):
            self.assertNotIn(key, result)
            self.assertNotIn('"' + key + '"', text)
        self.assertLess(len(text.encode('utf8')), 4096)
        original = json.dumps
        with (patch.object(live_spatial_mcp.json, 'dumps', wraps=original) as encode,
                patch.object(live_spatial_mcp.copy, 'deepcopy',
                    side_effect=AssertionError('compact result needs no diagnostic copy'))):
            again = _tool_result(result, is_error=False, response_detail='brief')
        self.assertEqual(encode.call_count, 1)
        self.assertEqual(json.loads(again['content'][0]['text']), result)
        self.assert_only_candidate_capture()
        EVIDENCE['mcp'] = {'content_blocks': 1, 'images': 0,
            'text_utf8_bytes': len(text.encode('utf8')), 'structuredContent': False}

    def test_12_legacy_nearest_top1_and_task_keep_their_existing_routes(self):
        host = SelfLockingHost()
        service = LiveSpatialService(self.config, host=host)
        for mode in ('nearest', 'top1'):
            result = service.observe('legacy-' + mode, focal_id='part',
                reference_id='base', include_image=False, query={'mode': mode})
            self.assertEqual(result['query_result']['mode'], mode)
            self.assertNotEqual(result.get('result_kind'), 'surface_nearest')
        task = service.observe('legacy-task', include_image=False,
            query={'mode': 'task', 'objects': [{'id': 'part'}], 'requested_facts': ['aabb']})
        self.assertEqual(task['result_kind'], 'task_query')
        self.assertEqual(task['facts']['aabb'][0]['status'], 'measured')
        self.assertEqual(host.captures, 3)
        self.assertEqual(host.calls, 0)
        self.assertEqual(validate_query(None), {'mode': 'overview', 'max_exact_pairs': 255})
        self.assert_only_candidate_capture(0)


if __name__ == '__main__':
    unittest.main()
