"""Active observation routing and image publication using synthetic fixtures.

The host algorithm is stubbed and PNGs come from constant unit-test RGB images.
These checks perform no actual scene raster or Blender operation.
"""

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import (
    LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, _tool_result, _validate_arguments,
)
from human_eye_plugin.query_policy import validate_query


def synthetic_frame(directory, number, size=512):
    stream = io.BytesIO()
    Image.new('RGB', (size, size), (40, 80, 120)).save(stream, format='PNG')
    path = Path(directory) / ('synthetic-' + str(number) + '-' + str(size) + '.png')
    path.write_bytes(stream.getvalue())
    return {'view_name': 'SCENE' if number == 0 else 'view-' + str(number),
        'image_path': str(path), 'image_sha256': hashlib.sha256(stream.getvalue()).hexdigest(),
        'image_ref': 'synthetic-frame-' + str(number)}


class CaptureHost:
    def __init__(self):
        self.captures = 0
        self.capture = {'revision': 'source-1', 'meshes': [{'object_id': 'panel', 'name': 'Panel'}],
            'capture_state': {'instance_id': 'host', 'epoch': 1, 'revision': 1, 'selection_key': 'all'}}

    def capture_scene(self):
        self.captures += 1
        return copy.deepcopy(self.capture)


class ActiveObservationServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        config = self.directory / 'live.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
            'project_root': str(self.directory), 'state_file': 'state.json', 'audit_file': 'audit.jsonl'}))
        self.host = CaptureHost()
        self.service = LiveSpatialService(config, host=self.host)
        self.events = []
        self.service.record_event = lambda event, **fields: self.events.append((event, fields))
        self.frames = [synthetic_frame(self.directory, index) for index in range(2)]
        self.compute_calls = 0
        self.no_regions = False

    @staticmethod
    def source_binding(capture, cameras=None):
        return {'scene_revision': capture['revision'], 'document_epoch': 'synthetic-document',
            'objects': [{'host_id': row['object_id'], 'object_name': row['name']} for row in capture['meshes']],
            'camera_policy': 'synthetic-fixed-pool'}

    def compute(self, capture, output_directory, *, include_image, construction_callback, check_budget):
        self.compute_calls += 1
        frames = copy.deepcopy(self.frames) if include_image and not self.no_regions else []
        for frame in frames:
            construction_callback(frame['view_name'])
        return {'result_kind': 'active_observation',
            'status': 'unknown' if self.no_regions else 'complete' if include_image else 'predicted',
            'binding': self.source_binding(capture),
            'facts': {'regions': [], 'coverage': {'covered_roi_ids': []},
                'names': [row['name'] for row in capture['meshes']]},
            'frames': frames, 'work': {'mapping_calls': 1, 'geometry_parse_calls': 1,
                'mesh_conversions': 1, 'camera_calls': 1, 'prepare_calls': 1,
                'raster_attempts': len(frames), 'local_verified_images': len(frames)},
            'stages': {}, 'read_only': True, 'execution_authority': False}

    def patches(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch('human_eye_plugin.active_observation_host.source_binding', side_effect=self.source_binding))
        stack.enter_context(patch('human_eye_plugin.active_observation_host.observe_capture', side_effect=self.compute))
        stack.enter_context(patch.object(self.service, '_locked', side_effect=AssertionError('write-service entry used')))
        stack.enter_context(patch('human_eye_plugin.live_service.render_scene_canvas', side_effect=AssertionError('old overview raster used')))
        return stack

    def observe(self, **options):
        return self.service.observe('unit', query={'mode': 'active_observation'}, **options)

    def test_mode_schema_and_arguments_are_explicit(self):
        self.assertEqual(validate_query({'mode': 'active_observation'}), {'mode': 'active_observation'})
        with self.assertRaises(ValueError):
            validate_query({'mode': 'active_observation', 'camera': 'SCENE'})
        _validate_arguments('human_eye_scene_observe', {'query': {'mode': 'active_observation'}, 'include_image': False})
        for extra in ({'focal_id': 'panel'}, {'goal': {}}, {'task_instruction': 'select panel'}, {'scene_delta': {}}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                _validate_arguments('human_eye_scene_observe', {'query': {'mode': 'active_observation'}, **extra})
        tool = next(row for row in LIVE_MCP_TOOLS_SCHEMA if row['name'] == 'human_eye_scene_observe')
        self.assertIn('active_observation', tool['inputSchema']['properties']['query']['properties']['mode']['enum'])

    def test_repeat_captures_source_and_rename_rebuilds_without_write_service(self):
        with self.patches():
            first = self.observe()
            hot = self.observe()
            self.assertEqual(self.host.captures, 2)
            self.assertEqual(self.compute_calls, 1)
            self.assertEqual((hot['work']['prepare_calls'], hot['work']['raster_attempts']), (0, 0))
            self.assertEqual(hot['work']['frame_reuses'], 2)
            self.assertEqual(hot['generation_work']['raster_attempts'], 2)
            self.assertEqual(hot['frames'], first['frames'])
            self.host.capture['meshes'][0]['name'] = 'Renamed panel'
            renamed = self.observe()
            self.assertEqual(self.compute_calls, 2)
            self.assertEqual(renamed['facts']['names'], ['Renamed panel'])
            self.assertFalse(renamed['work']['result_cache_hit'])
        self.assertEqual(len([row for row in self.events if row[0] == 'active_observation_render_attempt']), 4)
        self.assertFalse((self.directory / 'state.json').exists())

    def test_text_and_empty_roi_responses_have_zero_image_work(self):
        with self.patches():
            text = self.observe(include_image=False)
            self.assertEqual(text['status'], 'predicted')
            self.assertEqual(text['frames'], [])
            self.assertEqual(text['work']['raster_attempts'], 0)
            self.no_regions = True
            empty = self.observe(include_image=True)
            self.assertEqual(empty['status'], 'unknown')
            self.assertEqual(empty['frames'], [])
            result = _tool_result(empty, is_error=False)
            self.assertEqual([row['type'] for row in result['content']], ['text'])
            self.assertEqual(json.loads(result['content'][0]['text'])['image_delivery']['consumer_read_status'], 'unconfirmed')

    def test_active_images_allow_six_512_and_legacy_limits_stay_specific(self):
        frames = [synthetic_frame(self.directory, index) for index in range(6)]
        frames[0].update(pose={'view_matrix': [[1]]}, arrays={'depth': {'dtype': 'float64'}})
        value = {'result_kind': 'active_observation', 'frames': frames, 'work': {'raster_attempts': 6},
            'binding': {'camera_specification': {'views': ['private-matrices']}, 'camera_identity': 'cameras'},
            'steps': ['private-transition-history']}
        result = _tool_result(value, is_error=False)
        self.assertEqual(len(result['content']), 7)
        text = json.loads(result['content'][0]['text'])
        self.assertEqual(text['frames'][0]['image_ref'], frames[0]['image_ref'])
        self.assertNotIn('pose', text['frames'][0])
        self.assertNotIn('arrays', text['frames'][0])
        self.assertEqual(text['binding'], {'camera_identity': 'cameras'})
        self.assertNotIn('steps', text)
        self.assertIn('pose', value['frames'][0])
        self.assertIn('camera_specification', value['binding'])
        self.assertNotIn('"data":', result['content'][0]['text'])
        self.assertEqual(text['image_delivery']['mcp_content_constructed_image_count'], 6)
        raw = Path(synthetic_frame(self.directory, 10, 384)['image_path']).read_bytes()
        old = {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(raw).decode('ascii')}
        self.assertEqual(len(_tool_result({'routing': {'images': [old, old]}}, is_error=False)['content']), 3)
        with self.assertRaises(ValueError):
            _tool_result({'routing': {'images': [old, old, old]}}, is_error=False)
        with self.assertRaises(ValueError):
            _tool_result({'routing': {'images': [result['content'][1]]}}, is_error=False)

    def test_encoding_failure_preserves_cached_construction_and_ping(self):
        server = LiveSpatialMCPServer(self.service)
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': {'query': {'mode': 'active_observation'}}}}
        with self.patches():
            with patch('human_eye_plugin.live_spatial_mcp.base64.b64encode', side_effect=ValueError('injected encoding failure')):
                failed = server.handle_jsonrpc_message(request)
            self.assertTrue(failed['result']['isError'])
            self.assertIn('injected encoding failure', failed['result']['content'][0]['text'])
            ping = server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})
            self.assertEqual(ping['result'], {})
            success = server.handle_jsonrpc_message({**request, 'id': 3})
            self.assertFalse(success['result']['isError'])
        self.assertEqual(self.compute_calls, 1)
        self.assertEqual(self.host.captures, 2)
        metadata = json.loads(success['result']['content'][0]['text'])
        self.assertEqual(metadata['work']['raster_attempts'], 0)
        self.assertEqual(metadata['generation_work']['raster_attempts'], 2)
        charged = [row for row in self.events if row[0] == 'active_observation_render_attempt']
        self.assertEqual(len(charged), 2)
        delivery = [row[1]['image_delivery']['status'] for row in self.events if row[0] == 'active_observation_mcp_content']
        self.assertEqual(delivery, ['failed', 'constructed'])


if __name__ == '__main__':
    unittest.main()
