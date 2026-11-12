"""Ordinary tool schema and service regression tests for full-scene scans."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import (
    LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, _validate_arguments,
)
from human_eye_plugin.query_policy import validate_query
from verification.m4_surface_scan_001.tests.test_surface_scan import packet_for, triangle


QUERY = dict(mode='surface_scan', threshold_m=1.)


class ScanHost:
    timeout_s = 10.

    def __init__(self, packet):
        self.packet = packet
        self.calls = []

    def capture_surface_scan(self, threshold, deadline, limit):
        self.calls.append((threshold, deadline, limit))
        return copy.deepcopy(self.packet)


class EntryTests(unittest.TestCase):
    def service(self, packet):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        config = root / 'live.json'
        config.write_text(json.dumps(dict(schema_version='1.0', enabled=True,
            project_root=str(root), state_file='state.json', audit_file='audit.jsonl',
            request_budget_s=10.)), encoding='utf8')
        host = ScanHost(packet)
        service = LiveSpatialService(config, host=host)
        events = []
        service.record_event = lambda event, **fields: events.append((event, fields))
        return service, host, events

    def call(self, server, arguments):
        response = server.handle_jsonrpc_message(dict(jsonrpc='2.0', id=17,
            method='tools/call', params=dict(name='human_eye_scene_observe', arguments=arguments)))
        self.assertNotIn('error', response, response)
        result = response['result']
        self.assertEqual([row['type'] for row in result['content']], ['text'])
        return result, json.loads(result['content'][0]['text'])

    def test_query_only_ordinary_entry_defaults_to_text_and_one_capture(self):
        service, host, events = self.service(packet_for([triangle('a', 0), triangle('b', 1)]))
        result, facts = self.call(LiveSpatialMCPServer(service), dict(query=QUERY))
        self.assertFalse(result['isError'])
        self.assertEqual(facts['result_kind'], 'surface_scan')
        self.assertEqual(facts['status'], 'complete')
        self.assertEqual(len(facts['matches']), 1)
        self.assertEqual(len(host.calls), 1)
        threshold, deadline, limit = host.calls[0]
        self.assertEqual(threshold, 1.)
        self.assertGreater(deadline, time.perf_counter_ns())
        self.assertEqual(limit, 64 * 1024 * 1024)
        work = next(fields['task_work'] for event, fields in events if event == 'observe')
        self.assertEqual(work['kernel_calls'], 1)
        self.assertEqual(len(work['dispositions']), 1)
        self.assertNotIn('dispositions', facts)
        self.assertNotIn('request_trace', facts)

    def test_static_repeat_has_fresh_capture_and_zero_new_solver_with_private_coverage(self):
        service, host, events = self.service(packet_for([triangle('a', 0), triangle('b', 1)]))
        server = LiveSpatialMCPServer(service)
        self.call(server, dict(query=QUERY))
        _, repeated = self.call(server, dict(query=QUERY))
        self.assertEqual(len(host.calls), 2)
        work = [fields['task_work'] for event, fields in events if event == 'observe'][-1]
        self.assertTrue(work['result_cache_hit'])
        self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(work['pair_calls'], 0)
        self.assertEqual(work['dispositions'][0]['status'], 'measured_match')
        self.assertEqual(repeated['coverage']['total_pairs'], 1)

    def test_warm_packet_is_validated_before_result_cache_lookup(self):
        service, host, _ = self.service(packet_for([triangle('a', 0), triangle('b', 1)]))
        service.observe('s', query=QUERY, include_image=False)
        host.packet['coverage'][0]['name'] = 'changed_without_rebinding'
        with self.assertRaisesRegex(ValueError, 'directory digest mismatch'):
            service.observe('s', query=QUERY, include_image=False)

    def test_scope_change_invalidates_same_union_result(self):
        service, host, _ = self.service(packet_for([triangle('a', 0), triangle('b', 1)]))
        service.observe('s', query=QUERY, include_image=False)
        host.packet['scope_issues'].append(dict(reason='new_instance'))
        result = service.observe('s', query=QUERY, include_image=False)
        self.assertEqual(result['status'], 'unknown')

    def test_threshold_switch_and_return_keeps_private_pair_diagnostics(self):
        meshes = [triangle('a', 0), triangle('b', 1)]
        service, host, events = self.service(packet_for(meshes))
        server = LiveSpatialMCPServer(service)
        self.call(server, dict(query=QUERY))
        host.packet = packet_for(meshes, threshold=1.5)
        self.call(server, dict(query=dict(mode='surface_scan', threshold_m=1.5)))
        host.packet = packet_for(meshes)
        self.call(server, dict(query=QUERY))
        work = [fields['task_work'] for event, fields in events if event == 'observe'][-1]
        self.assertFalse(work['result_cache_hit'])
        self.assertEqual(work['kernel_calls'], 0)
        self.assertEqual(work['cache_hits'], 1)
        self.assertEqual(len(work['dispositions']), 1)

    def test_scope_unknown_is_a_readonly_fact_and_keeps_unknown_status(self):
        service, _, _ = self.service(packet_for([], issues=[dict(reason='instance_not_in_scene')]))
        result, facts = self.call(LiveSpatialMCPServer(service), dict(query=QUERY))
        self.assertFalse(result['isError'])
        self.assertEqual(facts['status'], 'unknown')
        self.assertFalse(facts['coverage']['catalog_scope_confirmed'])
        self.assertFalse(facts['execution_authority'])

    def test_empty_scene_and_empty_union_reach_formal_service(self):
        for meshes in ([], [triangle('a', 0)], [triangle('a', 0), triangle('b', 10)]):
            with self.subTest(objects=len(meshes)):
                service, _, _ = self.service(packet_for(meshes))
                result, facts = self.call(LiveSpatialMCPServer(service), dict(query=QUERY))
                self.assertFalse(result['isError'])
                self.assertEqual(facts['status'], 'complete')
                self.assertEqual(facts['matches'], [])

    def test_unsupported_source_remains_partial(self):
        service, _, _ = self.service(packet_for([triangle('a', 0), triangle('b', 10)], unsupported=('b',)))
        result, facts = self.call(LiveSpatialMCPServer(service), dict(query=QUERY))
        self.assertFalse(result['isError'])
        self.assertEqual(facts['status'], 'partial')
        self.assertEqual(facts['coverage']['unknown'], 1)

    def test_runtime_arguments_reject_selectors_images_and_invalid_thresholds(self):
        for changes in (dict(focal_id='a'), dict(reference_id='b'), dict(goal={}),
                        dict(scene_delta={}), dict(include_image=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _validate_arguments('human_eye_scene_observe', dict(query=QUERY, **changes))
        for query in (dict(QUERY, objects=[]), dict(QUERY, requested_facts=[]),
                      dict(mode='surface_scan'), dict(QUERY, threshold_m=True)):
            with self.subTest(query=query), self.assertRaises(ValueError):
                validate_query(query)

    def test_schema_matches_new_and_existing_threshold_contracts(self):
        from jsonschema import Draft202012Validator
        schema = LIVE_MCP_TOOLS_SCHEMA[0]['inputSchema']
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for threshold in (0, 1e308):
            validator.validate(dict(query=dict(mode='surface_scan', threshold_m=threshold)))
        invalid = [dict(query=dict(QUERY, threshold_m=-1)), dict(query=dict(QUERY, objects=[])),
                   dict(query=QUERY, include_image=True), dict(query=QUERY, focal_id='a'),
                   dict(query=dict(mode='surface_scan'))]
        for arguments in invalid:
            self.assertTrue(list(validator.iter_errors(arguments)), arguments)
        query_schema = schema['properties']['query']
        old = Draft202012Validator(query_schema)
        self.assertTrue(list(old.iter_errors(dict(mode='mesh_surface', threshold_m=0))))
        self.assertTrue(list(old.iter_errors(dict(mode='mesh_surface', threshold_m=.02))))

    def test_threshold_mismatch_is_rejected_before_kernel(self):
        service, _, _ = self.service(packet_for([], threshold=2.))
        with self.assertRaisesRegex(ValueError, 'threshold_binding_mismatch'):
            service.observe('s', query=QUERY, include_image=False)

    def test_no_source_permission_or_action_ledger_is_created(self):
        service, _, _ = self.service(packet_for([]))
        self.call(LiveSpatialMCPServer(service), dict(query=QUERY))
        self.assertFalse(service.state_path.exists())
        self.assertFalse(service.state_path.with_name(service.state_path.name+'.lock').exists())


if __name__ == '__main__':
    unittest.main()
