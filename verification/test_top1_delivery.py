"""Explicit top1 crosses actual local MCP serialization without gaining writes."""
import json
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, LIVE_MCP_TOOLS_SCHEMA
from verification.test_live_service import SelfLockingHost
from verification.test_host_runtime import mesh


class Top1DeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = Path(temporary.name) / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SelfLockingHost()
        self.host.scene['meshes'].append(mesh('far', [10, 0, 0], [.2, .2, .2]))
        self.service = LiveSpatialService(config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='top1-delivery')

    def rpc(self, arguments):
        result = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})['result']
        self.assertFalse(result['isError'], result)
        return result, json.loads(result['content'][0]['text'])

    def test_declared_mode_and_full_brief_native_images_preserve_proof(self):
        schema = next(item for item in LIVE_MCP_TOOLS_SCHEMA if item['name'] == 'human_eye_scene_observe')
        self.assertIn('top1', schema['inputSchema']['properties']['query']['properties']['mode']['enum'])
        args = {'focal_id': 'part', 'reference_id': 'base', 'query': {'mode': 'top1', 'max_exact_pairs': 1}}
        full_wire, full = self.rpc(args)
        brief_wire, brief = self.rpc({**args, 'response_detail': 'brief'})
        self.assertEqual(full['query_result'], brief['query_result'])
        self.assertEqual(full['query_result']['top1']['nearest_object_ids'], ['base'])
        self.assertEqual(full['query_result']['top1']['excluded_by_lower_bound_ids'], ['far'])
        self.assertIsNone(full['query_result']['ranked_object_ids'])
        full_images = [item for item in full_wire['content'] if item['type'] == 'image']
        self.assertTrue(full_images)
        self.assertEqual(full_images, [item for item in brief_wire['content'] if item['type'] == 'image'])
        self.assertEqual(self.host.captures, 2)  # Each request still captures fresh host geometry.
        self.assertEqual(self.host.calls, 0)

    def test_missing_pair_has_explicit_unknown_top1(self):
        self.host.scene['meshes'] = [item for item in self.host.scene['meshes'] if item['object_id'] == 'part']
        _, value = self.rpc({'query': {'mode': 'top1'}})
        self.assertEqual(value['status'], 'overview')
        self.assertEqual(value['query_result']['status'], 'unknown')
        self.assertEqual(value['query_result']['top1']['status'], 'unknown')
        self.assertIsNone(value['query_result']['top1']['nearest_object_ids'])
        self.assertIn('query_pair_required', value['query_result']['reason_codes'])
        self.assertEqual(self.host.calls, 0)

    def test_invalid_top1_request_never_connects(self):
        for query in [{'mode': 'top1', 'max_exact_pairs': True},
                      {'mode': 'top1', 'object_ids': []},
                      {'mode': 'top1', 'comparison_guard_m': 1000}]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.service.observe('s', focal_id='part', reference_id='base', query=query)
        self.assertEqual(self.host.captures, 0)


if __name__ == '__main__':
    unittest.main()
