"""Compact task entry contracts over existing real kernels and offline hosts.

The parent runner supplies the verified current product package. No final
nearest result is mocked. Legacy fixture modules are read, never rewritten.
"""
import copy
from contextlib import ExitStack
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import live_service as ls, live_spatial_mcp as mcp, task_query
from verification import test_blender_host_contracts as host_contracts
from human_eye_plugin import blender_host

# Existing capture doubles must call the same guarded product module as the
# service, not the fixture's separately named descriptor import.
host_contracts._module = blender_host
host_contracts.BlenderSceneHost = blender_host.BlenderSceneHost
host_contracts.BlenderHostError = blender_host.BlenderHostError

from verification.surface_nearest_entry_001.tests.test_surface_nearest_entry import (
    ActualCandidateHost, add_retained_exact_bit_budget_face,
)
from verification.arch_read_context_001.test_resident_task import TokenSelectedHost
from verification.arch_read_context_001.test_resident_nearest import Host as TokenNearestHost
from verification.nearest_integration_001.tests.test_integration import packet_for, yz

ROOT = Path(__file__).resolve().parents[3]
NEAREST = 'human_eye_surface_nearest'
RELATIONS = 'human_eye_spatial_relations'
EVIDENCE = {}


def forbidden(*args, **kwargs):
    raise AssertionError('unexpected action-state access or external operation')


def without_trace(value):
    return {key: item for key, item in value.items() if key != 'trace_id'}


def recorded_rejection(batch, cell):
    owner = ROOT/'verification'/batch/'cells'/cell/'owner'
    errors = [directory for directory in sorted(owner.glob('tool_*'))
              if json.loads((directory/'ATTEMPT.json').read_bytes())['is_error']]
    if len(errors) != 1:
        raise AssertionError('expected one original rejection in this frozen cell')
    return json.loads((errors[0]/'REQUEST.json').read_bytes())['params']['arguments']


class CompactTaskEntryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory(prefix='m1-task-entry-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.config = self.folder/'config.json'
        self.config.write_text(json.dumps({
            'schema_version': '1.0', 'enabled': True, 'project_root': str(ROOT),
            'state_file': 'actions.json', 'audit_file': 'audit.jsonl',
            'quad_size': 64, 'max_sessions': 4,
        }), encoding='utf8')
        self.use_host(ActualCandidateHost())

    def use_host(self, host):
        self.host = host
        self.service = ls.LiveSpatialService(self.config, host=host)
        self.server = mcp.LiveSpatialMCPServer(
            self.service, default_session_id='m1-trusted-default', spatial_task_only=True)
        self.legacy = mcp.LiveSpatialMCPServer(
            self.service, default_session_id='m1-trusted-default')

    @staticmethod
    def rpc(server, name, arguments, request_id=7):
        return server.handle_jsonrpc_message({
            'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments},
        })['result']

    def nearest(self, selector=None, **extra):
        arguments = {'target': {'name': 'O0'} if selector is None else selector, **extra}
        result = self.rpc(self.server, NEAREST, arguments)
        return result, json.loads(result['content'][0]['text'])

    def legacy_nearest(self, selector):
        result = self.rpc(self.legacy, 'human_eye_scene_observe', {
            'session_id': self.legacy.default_session_id, 'include_image': False,
            'query': {'mode': 'surface_nearest', 'objects': [selector]},
        })
        return result, json.loads(result['content'][0]['text'])

    def relations(self, arguments=None):
        arguments = arguments or {
            'target': {'id': 'a'},
            'candidates': [{'id': identity} for identity in ('b', 'c', 'd')],
        }
        result = self.rpc(self.server, RELATIONS, arguments)
        return result, json.loads(result['content'][0]['text'])

    def test_catalogues_preserve_originals_and_only_two_compact_tools(self):
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
        tools = self.server.handle_jsonrpc_message(request)['result']['tools']
        self.assertEqual([tool['name'] for tool in tools], [RELATIONS, NEAREST])
        ordinary = self.legacy.handle_jsonrpc_message(request)['result']['tools']
        frozen = json.loads((ROOT/'verification/native_plugin_complex_005/C_schemas.stdout.json').read_bytes())
        self.assertEqual(ordinary, frozen['tools_list']['result']['tools'])
        original_relations = json.loads((ROOT/'verification/spatial_task_entry_001/dedicated_schema.json').read_bytes())
        self.assertEqual(tools[0]['inputSchema'], original_relations)
        schema = tools[1]['inputSchema']
        self.assertEqual(schema['required'], ['target'])
        self.assertEqual(set(schema['properties']), {'target'})
        self.assertFalse(schema['additionalProperties'])
        sample, _ = json.JSONDecoder().raw_decode(tools[1]['description'].split('Example: ', 1)[1])
        self.assertEqual(sample, {'target': {'name': 'Bracket'}})
        mcp._validate_arguments(NEAREST, sample)
        tools[1]['inputSchema']['properties'].clear()
        self.assertEqual(set(mcp.SPATIAL_TASK_TOOLS_SCHEMA[1]['inputSchema']['properties']), {'target'})
        self.assertEqual(self.host.candidate_calls, [])

    def test_new_minimum_and_name_id_results_equal_legacy_full_facts(self):
        arguments = {'target': {'name': 'O0'}}
        original = copy.deepcopy(arguments)
        with patch.object(self.service, 'observe', wraps=self.service.observe) as observed:
            compact = self.rpc(self.server, NEAREST, arguments)
        self.assertEqual(arguments, original)
        self.assertFalse(compact['isError'])
        self.assertEqual(len(compact['content']), 1)
        self.assertEqual(observed.call_count, 1)
        self.assertEqual(observed.call_args.args, ('m1-trusted-default',))
        self.assertIs(observed.call_args.kwargs['include_image'], False)
        self.assertEqual(observed.call_args.kwargs['query'],
                         {'mode': 'surface_nearest', 'objects': [{'name': 'O0'}]})
        current = json.loads(compact['content'][0]['text'])
        legacy_result, legacy = self.legacy_nearest({'name': 'O0'})
        by_id_result, by_id = self.nearest({'id': self.host.focal_id})
        self.assertEqual(without_trace(current), without_trace(legacy))
        self.assertEqual(without_trace(current), without_trace(by_id))
        self.assertEqual((legacy_result['isError'], by_id_result['isError']), (False, False))
        self.assertEqual(current['distance_m'], 2.)
        self.assertEqual(current['nearest_objects'], [self.host.object(1)])
        self.assertFalse(current['execution_authority'])
        self.assertEqual((self.host.scene_calls, self.host.selected_calls,
                          self.host.name_calls, self.host.calls), (0, 0, 0, 0))
        self.assertEqual(len(self.host.candidate_calls), 3)

    def test_recorded_004_005_bad_shapes_remain_legacy_rejections(self):
        cases = [('native_plugin_complex_004', '04'),
                 ('native_plugin_complex_005', '03'),
                 ('native_plugin_complex_005', '11'),
                 ('native_plugin_complex_005', '18')]
        for batch, cell in cases:
            with self.subTest(batch=batch, cell=cell):
                args = recorded_rejection(batch, cell)
                saved = copy.deepcopy(args)
                old = self.rpc(self.legacy, 'human_eye_scene_observe', args)
                self.assertTrue(old['isError'])
                new = self.rpc(self.server, NEAREST, args)
                self.assertTrue(new['isError'])
                self.assertEqual(args, saved)
        self.assertEqual(self.host.candidate_calls, [])
        self.assertEqual(self.host.calls, 0)

    def test_hidden_fields_and_invalid_selectors_fail_before_host_capture(self):
        for field, value in [('session_id', 'chosen'), ('include_image', False),
                ('mode', 'surface_nearest'), ('requested_facts', ['nearest_witness']),
                ('query', {}), ('reference_id', 'other'), ('goal', {}), ('scene_delta', {})]:
            with self.subTest(field=field):
                result, _ = self.nearest(**{field: value})
                self.assertTrue(result['isError'])
        for target in (None, {}, [], 'O0', {'name': ''}, {'name': ' '}, {'name': True},
                {'name': 'O0', 'id': 'x'}, {'name': 'O0', 'extra': True}, {'name': '界'*86}):
            with self.subTest(target=target):
                result = self.rpc(self.server, NEAREST, {'target': target})
                self.assertTrue(result['isError'])
        self.assertTrue(self.rpc(self.server, NEAREST, {})['isError'])
        for name in (RELATIONS, NEAREST):
            self.assertTrue(self.rpc(self.legacy, name, {'target': {'name': 'O0'}})['isError'])
        for name in [row['name'] for row in mcp.LIVE_MCP_TOOLS_SCHEMA]:
            self.assertTrue(self.rpc(self.server, name, {})['isError'])
        self.assertEqual(self.host.candidate_calls, [])
        self.assertEqual(self.host.calls, 0)

    def test_complete_partial_and_unknown_preserve_legacy_payload_and_flags(self):
        for expected, xs in [('complete', (0., 2., 100.)),
                             ('partial', (0., 2., 100.)), ('unknown', (0., 100.))]:
            with self.subTest(expected=expected):
                self.use_host(ActualCandidateHost(xs))
                if expected != 'complete':
                    add_retained_exact_bit_budget_face(self.host.objects[-1])
                old_result, old = self.legacy_nearest({'name': 'O0'})
                result, body = self.nearest()
                self.assertEqual(body['status'], expected)
                self.assertEqual(result['isError'], old_result['isError'])
                self.assertEqual(without_trace(body), without_trace(old))
                self.assertEqual(result['isError'], expected == 'unknown')
                if expected != 'complete':
                    self.assertIsNone(body['nearest_objects'])
                    self.assertIsNone(body['distance_m'])
                    self.assertEqual(body['coverage']['unresolved'], 1)
                    self.assertEqual(body['unresolved'][0]['reason'], 'surface_exact_bit_budget')
                EVIDENCE[expected] = copy.deepcopy(body)

    def test_missing_ambiguous_and_explicit_id_use_current_capture(self):
        for target, reason in [({'name': 'missing'}, 'acquisition_selector_not_found'),
                               ({'id': 'missing-id'}, 'acquisition_selector_not_found')]:
            result, body = self.nearest(target)
            self.assertTrue(result['isError'])
            self.assertIn(reason, body['error'])
        self.assertTrue(all(obj.mesh_calls == 0 for obj in self.host.objects))
        self.host.objects[1].name = self.host.objects[0].name
        result, body = self.nearest()
        self.assertTrue(result['isError'])
        self.assertIn('acquisition_selector_ambiguous', body['error'])
        self.assertTrue(all(obj.mesh_calls == 0 for obj in self.host.objects))
        result, body = self.nearest({'id': self.host.focal_id})
        self.assertFalse(result['isError'])
        self.assertEqual(body['focal']['id'], self.host.focal_id)
        self.assertEqual(body['distance_m'], 2.)

    def test_relations_keeps_analytic_facts_and_original_contract(self):
        self.use_host(TokenSelectedHost())
        result, body = self.relations()
        self.assertFalse(result['isError'])
        self.assertEqual(body['schema_version'], 'spatial-relations-v1')
        self.assertEqual(body['sets']['penetrating'], {'complete': True, 'candidate_indices': [1]})
        self.assertEqual(body['sets']['nearest_separated'],
                         {'complete': True, 'candidate_indices': [0, 2], 'distance_m': 2.})
        self.assertEqual([row['closed_solid_relation']['value'] for row in body['candidates']],
                         ['separated', 'penetrating', 'separated'])
        raw = self.service.observe(self.server.default_session_id, include_image=False, query={
            'mode': 'task', 'target': {'id': 'a'},
            'candidates': [{'id': value} for value in ('b', 'c', 'd')],
            'requested_facts': ['closed_solid_relation', 'surface_proximity'],
        })
        for compact, pair in zip(body['candidates'], raw['pairs']):
            for field in ('closed_solid_relation', 'surface_proximity', 'separation_gap'):
                reconstructed = {**body['measurement_contracts'].get(field, {}), **compact[field]}
                expected = pair[field] if field == 'separation_gap' else pair['facts'][field]
                self.assertEqual(reconstructed, expected)
        self.assertEqual(body['context']['runtime_source_sha256'], self.service._identity['source_sha256'])
        self.assertEqual(self.host.calls, 0)

    def test_relations_partial_keeps_missing_and_ambiguous_rows(self):
        self.use_host(TokenSelectedHost())
        self.host.scene['meshes'][2]['name'] = 'b'
        self.host.capture_revision += 1
        result, body = self.relations({'target': {'id': 'a'},
            'candidates': [{'name': 'b'}, {'id': 'd'}]})
        self.assertFalse(result['isError'])
        self.assertEqual(body['status'], 'partial')
        self.assertEqual(len(body['candidates']), 2)
        self.assertEqual(body['candidates'][0]['reason'], 'object_name_ambiguous')
        self.assertEqual(body['candidates'][1]['closed_solid_relation']['value'], 'separated')
        self.assertFalse(body['sets']['nearest_separated']['complete'])
        missing_result, missing = self.relations({'target': {'id': 'missing'}, 'candidates': [{'id': 'd'}]})
        self.assertTrue(missing_result['isError'])
        self.assertEqual(missing['status'], 'unknown')
        self.assertEqual(missing['target']['reason'], 'object_not_found')
        self.assertEqual(missing['candidates'][0]['object_id'], 'd')
        self.assertEqual(self.host.calls, 0)
        EVIDENCE['relations_partial'] = copy.deepcopy(body)
        EVIDENCE['relations_missing_target'] = copy.deepcopy(missing)

    def test_default_session_does_not_touch_opaque_action_journal(self):
        for kind, host in [(NEAREST, ActualCandidateHost()), (RELATIONS, TokenSelectedHost())]:
            with self.subTest(tool=kind):
                self.use_host(host)
                payload = b'{opaque prior pending/committed action bytes\x00'
                self.service.state_path.write_bytes(payload)
                with ExitStack() as stack:
                    for method in ('_locked', '_save', '_runtime'):
                        stack.enter_context(patch.object(self.service, method, side_effect=forbidden))
                    spy = stack.enter_context(patch.object(self.service, 'observe', wraps=self.service.observe))
                    for _ in range(2):
                        result, _ = self.nearest() if kind == NEAREST else self.relations()
                        self.assertFalse(result['isError'])
                self.assertEqual([call.args[0] for call in spy.call_args_list],
                                 [self.server.default_session_id]*2)
                self.assertEqual(self.service.state_path.read_bytes(), payload)
                self.service.state_path.unlink()

    def test_new_trace_is_observe_without_image_under_actual_rpc_id(self):
        self.nearest()
        rows = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        traces = [row['trace'] for row in rows if row.get('event') == 'request_trace']
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]['operation'], 'mcp.observe')
        annotation = traces[0]['annotations']
        self.assertEqual(traces[0]['correlation']['session_id'], self.server.default_session_id)
        self.assertIs(annotation['include_image'], False)
        self.assertEqual(annotation['mcp_request_id'], 7)
        self.assertEqual(annotation['mcp_native_image_block_count'], 0)
        EVIDENCE['nearest_trace'] = copy.deepcopy(traces[0])

    def test_current_token_and_source_generation_keep_cache_bound(self):
        self.use_host(TokenNearestHost())
        first_result, first = self.nearest({'name': 'f'})
        self.assertFalse(first_result['isError'])
        with patch.object(task_query, 'surface_nearest_result', side_effect=forbidden):
            _, warm = self.nearest({'name': 'f'})
        self.assertEqual(without_trace(first), without_trace(warm))
        self.assertEqual(self.host.captures, 2)
        for field, value in [('revision', 2), ('epoch', 2), ('instance_id', 'new-instance'),
                             ('selection_key', 'new-selection')]:
            self.host.token[field] = value
            with patch.object(ls, '_validated_scene', wraps=ls._validated_scene) as normalize:
                result, current = self.nearest({'name': 'f'})
            self.assertFalse(result['isError'])
            self.assertEqual(normalize.call_count, 1)
            self.assertEqual(current['distance_m'], 2.)
        self.host.packet = packet_for(yz('f', 0.), [yz('b', 3.)])
        self.host.token['revision'] += 1
        _, moved = self.nearest({'name': 'f'})
        self.assertEqual(moved['distance_m'], 3.)
        self.assertEqual(first['distance_m'], 2.)
        self.service._identity = copy.deepcopy(self.service._identity)
        self.service._identity['source_sha256'] = 'f'*64
        with patch.object(task_query, 'surface_nearest_result', wraps=task_query.surface_nearest_result) as compute:
            _, rebound = self.nearest({'name': 'f'})
        self.assertEqual(compute.call_count, 1)
        self.assertEqual(rebound['binding']['runtime_source_sha256'], 'f'*64)

    def test_bad_loaded_source_and_capture_binding_fail_before_math(self):
        rejected = {'status': 'runtime_identity_mismatch', 'runtime_identity': {'compatible': False},
                    'reason_codes': ['source_digest_mismatch']}
        with patch.object(self.service, '_read_source_identity', return_value=(rejected, None)):
            result, body = self.nearest()
        self.assertTrue(result['isError'])
        self.assertEqual(body['status'], rejected['status'])
        self.assertEqual(self.host.candidate_calls, [])
        def corrupt():
            self.host.last_packet['binding']['host_source_sha256'] = '0'*64
        self.host.after_capture = corrupt
        with patch.object(task_query, '_surface_pair_measurement', side_effect=forbidden):
            result, body = self.nearest()
        self.assertTrue(result['isError'])
        self.assertIn('source binding', body['error'])
        self.host.after_capture = None
        result, body = self.nearest()
        self.assertFalse(result['isError'])
        self.assertEqual(body['distance_m'], 2.)

    def test_original_request_deadline_survives_new_alias_encoding(self):
        original = mcp._tool_result
        observed = []
        def encode(*args, **kwargs):
            if not kwargs.get('is_error'):
                budget = ls._REQUEST_BUDGET.get()
                self.assertIsNotNone(budget)
                observed.append(id(budget))
                budget['deadline'] = time.monotonic()-1
            return original(*args, **kwargs)
        with patch.object(mcp, '_tool_result', side_effect=encode):
            result, body = self.nearest()
        self.assertEqual(len(observed), 1)
        self.assertTrue(result['isError'])
        self.assertEqual(body['status'], 'expired')
        self.assertNotIn('nearest_objects', body)

    def test_stdio_recovers_and_keeps_one_process_default_session(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
             'params': {'name': NEAREST, 'arguments': {'target': {'name': 'O0'}, 'session_id': 'untrusted'}}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
             'params': {'name': NEAREST, 'arguments': {'target': {'name': 'O0'}}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
             'params': {'name': NEAREST, 'arguments': {'target': {'id': self.host.focal_id}}}},
        ]
        output = io.StringIO()
        with patch.object(self.service, 'observe', wraps=self.service.observe) as observe:
            mcp.run_stdio_mcp_server(self.service,
                io.StringIO(''.join(json.dumps(row)+'\n' for row in requests)), output,
                spatial_task_only=True)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(responses), 4)
        self.assertTrue(responses[0]['result']['isError'])
        self.assertFalse(responses[1]['result']['isError'])
        self.assertEqual(responses[2]['result'], {})
        self.assertFalse(responses[3]['result']['isError'])
        self.assertEqual(observe.call_count, 2)
        sessions = [call.args[0] for call in observe.call_args_list]
        self.assertEqual(sessions[0], sessions[1])
        self.assertTrue(sessions[0].startswith('mcp-'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
