"""Public focus requests using the real PNG, depth and ordered source owners."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.observation_focus import select_triangle, validate_focus_delivery
from verification.test_active_observation_host import panel_capture
from verification.test_active_observation_patches import box_mesh


def set_display(capture, visible=True):
    snapshot = dict(schema='blender-viewport-display-v1', scope='active_view_layer', status='captured',
        view_layer={'name': 'Layer', 'instance_id': '100'},
        objects=[dict(host_id=m['object_id'], instance_id=capture['host_identity']['object_instances'][m['object_id']],
                      visible_get=visible) for m in capture['meshes']])
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    capture['display_snapshot'] = dict(snapshot, sha256=hashlib.sha256(raw).hexdigest())


class Capture:
    def __init__(self):
        self.data = panel_capture()
        cube = box_mesh()
        self.data['meshes'][0].update(name='Box', vertices=cube['vertices'], faces=cube['triangles'])
        self.calls = 0
        set_display(self.data)

    def capture_scene(self):
        self.calls += 1
        return copy.deepcopy(self.data)


class DirectedFocusTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        config = Path(root.name) / 'config.json'
        config.write_text(json.dumps(dict(schema_version='1.0', enabled=True, project_root=root.name,
                                         state_file='state.json', audit_file='audit.jsonl')))
        self.host = Capture()
        self.service = LiveSpatialService(config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='focus-test')
        self.query = dict(mode='active_observation', objects=[{'name': 'Box'}])
        self.rasters = []
        self.service.record_event = lambda event, **fields: (
            self.rasters.append(fields['view_name']) if event == 'active_observation_render_attempt' else None)

    def request(self, focus, *, image=True, extra=None, detail='brief'):
        args = dict(query=dict(self.query, focus=focus, **(extra or {})), include_image=image, response_detail=detail)
        return self.server.handle_jsonrpc_message(dict(jsonrpc='2.0', id=1, method='tools/call',
            params=dict(name='human_eye_scene_observe', arguments=args)))['result']

    def result(self, focus, **kwargs):
        reply = self.request(focus, **kwargs)
        self.assertFalse(reply['isError'], reply['content'][0])
        packet = json.loads(reply['content'][0]['text'])
        if packet['frames']:
            frame = packet['frames'][0]
            img = base64.b64decode(reply['content'][1]['data'], validate=True)
            self.assertEqual(img, Path(frame['image_path']).read_bytes())
            self.assertEqual(hashlib.sha256(img).hexdigest(), frame['image_sha256'])
        return packet

    def test_auto_missed_face_and_explicit_normal_hit_actual_owner(self):
        for policy in ('auto', {'normal_world': [0, 0, -3]}):
            with self.subTest(policy=policy):
                packet = self.result(policy, detail='full')
                focus = packet['facts']['focus']
                self.assertEqual(focus['region_ref']['source_triangle_indices'], [0])
                self.assertEqual([r['view_name'] for r in focus['views']], ['SCENE', 'FOCUS'])
                self.assertEqual(focus['views'][0]['verified_pixels'], 0)
                self.assertEqual(focus['stop_reason'], 'sample_target_met')
                self.assertEqual(focus['complete_surface_visibility'], 'unknown')
                self.assertEqual(packet['image_delivery']['local_verified_image_count'], 2)
                frame, sample = packet['frames'][0], focus['sample']
                pixel = sample['sampled_pixel']
                with np.load(frame['arrays_path'], allow_pickle=False) as saved:
                    mask = (saved['owners'] == 0) & (saved['triangle_ids'] == 0)
                    self.assertEqual(sample['selected_surface_pixels'], np.count_nonzero(mask))
                    self.assertTrue(mask[pixel['row'], pixel['column']])
                    self.assertTrue(np.isfinite(saved['depth'][pixel['row'], pixel['column']]))

    def test_plan_only_then_first_frame_enough_and_resume_after_another_focus(self):
        top = {'source_triangle_index': 2}
        plan = self.result(top, image=False)
        self.assertEqual(self.rasters, [])
        self.assertEqual((plan['frames'], plan['status']), ([], 'predicted'))
        first = self.result(top)
        self.assertEqual(self.rasters, ['SCENE'])
        self.result('auto')
        resumed = self.result(top)
        self.assertEqual(self.rasters, ['SCENE', 'SCENE', 'FOCUS'])
        self.assertEqual(first['frames'], resumed['frames'])
        self.assertEqual(plan['facts']['focus']['region_ref'], resumed['facts']['focus']['region_ref'])
        self.assertEqual(resumed['image_delivery']['new_raster_attempts'], 0)

    def test_interrupt_between_frames_resumes_same_generation(self):
        original = self.service._check_request_budget
        def interrupt(stage):
            if stage == 'focus_before_view' and self.rasters == ['SCENE']:
                raise ValueError('simulated_deadline_between_frames')
            return original(stage)
        with patch.object(self.service, '_check_request_budget', side_effect=interrupt):
            self.assertTrue(self.request('auto')['isError'])
        self.assertEqual(self.rasters, ['SCENE'])
        self.result({'source_triangle_index': 2})
        packet = self.result('auto')
        self.assertEqual(self.rasters, ['SCENE', 'SCENE', 'FOCUS'])
        self.assertEqual(packet['facts']['focus']['views'][0]['verified_pixels'], 0)
        self.assertEqual(packet['image_delivery']['new_raster_attempts'], 1)
        self.assertEqual(self.result('auto')['frames'], packet['frames'])

    def test_enclosed_no_gain_is_terminal_then_display_and_geometry_invalidate(self):
        outer = copy.deepcopy(self.host.data['meshes'][0])
        outer.update(object_id='shell', name='Shell', vertices=(3*np.array(outer['vertices'])).tolist())
        self.host.data['meshes'].append(outer)
        self.host.data['host_identity']['object_instances']['shell'] = '102'
        set_display(self.host.data)
        first = self.result('auto')
        self.assertEqual(first['status'], 'unknown')
        self.assertEqual([v['verified_pixels'] for v in first['facts']['focus']['views']], [0, 0])
        self.assertEqual(self.result('auto')['image_delivery']['new_raster_attempts'], 0)
        set_display(self.host.data, False)
        hidden = self.result('auto')
        self.assertEqual(hidden['facts']['focus']['stop_reason'], 'selected_object_not_displayed')
        self.assertEqual(hidden['frames'], [])
        self.assertEqual(len(self.rasters), 2)
        self.host.data['meshes'].pop()
        self.host.data['host_identity']['object_instances'].pop('shell')
        self.host.data['capture_state']['revision'] += 1
        set_display(self.host.data)
        fresh = self.result('auto')
        self.assertNotEqual(fresh['facts']['focus']['region_ref'], first['facts']['focus']['region_ref'])
        self.assertEqual(fresh['status'], 'complete')

    def test_oblique_rotated_face_steers_with_current_geometry(self):
        mesh = self.host.data['meshes'][0]
        rotation = np.array([[1, 0, 0], [0, .8, -.6], [0, .6, .8]])
        mesh['vertices'] = (np.array(mesh['vertices']) @ rotation.T).tolist()
        packet = self.result({'normal_world': [0, .6, -.8]}, detail='full')
        focus = packet['facts']['focus']
        self.assertIn(focus['sample']['sampled_pixel']['source_triangle_index'], (0, 1))
        self.assertEqual(focus['sample']['view_name'], 'FOCUS')
        frame = self.service.observe('focus-test', query=dict(self.query, focus={'normal_world': [0, .6, -.8]}))['frames'][0]
        self.assertEqual(frame['frame_identity'], focus['sample']['frame_identity'])
        np.testing.assert_allclose(frame['pose']['view_matrix'][2][:3], [0, .6, -.8], atol=1e-12)
        np.testing.assert_allclose(focus['sample']['target_to_eye_unit'], [0, .6, -.8], atol=1e-12)

    def test_reject_invalid_focus_before_host_and_mismatched_frame_at_delivery(self):
        for focus in ({}, False, {'normal_world': [0, 0, 0]}, {'normal_world': [True, 0, 0]},
                      {'source_triangle_index': -1}, {'normal_world': [0, 1, 0], 'source_triangle_index': 0}):
            self.assertTrue(self.request(focus)['isError'])
        self.assertTrue(self.request('auto', extra={'task_query': {}})['isError'])
        self.assertEqual(self.host.calls, 0)
        packet = self.service.observe('focus-test', query=dict(self.query, focus='auto'))
        packet['facts']['focus']['sample']['sampled_pixel']['source_triangle_index'] += 1
        with self.assertRaisesRegex(ValueError, 'pixel_binding'):
            validate_focus_delivery(packet, packet['frames'])

    def test_selection_numeric_range_ties_and_degenerate_target(self):
        mesh = self.host.data['meshes'][0]
        for exponent in (-800, 0, 800):
            test = dict(mesh, vertices=np.ldexp(np.array(mesh['vertices'], dtype=float), exponent).tolist())
            self.assertEqual(select_triangle(test, 'auto', lambda _: None), (0, [0, 0, -1]))
        mesh['faces'] = [[0, 0, 0]]
        result = self.result('auto')
        self.assertEqual(result['facts']['focus']['stop_reason'], 'no_matching_nondegenerate_source_triangle')
        self.assertEqual(self.rasters, [])

    def test_unverified_attempt_is_spent_and_unversioned_capture_does_not_restart(self):
        original = self.service._check_request_budget
        def interrupt(stage):
            if stage == 'source_region_after_frame':
                raise ValueError('simulated_interrupt_before_validation')
            return original(stage)
        with patch.object(self.service, '_check_request_budget', side_effect=interrupt):
            self.assertTrue(self.request('auto')['isError'])
            self.assertTrue(self.request('auto')['isError'])
        final = self.result('auto')
        self.assertEqual(final['status'], 'unknown')
        self.assertIsNone(final['facts']['focus']['sample'])
        self.assertEqual([v['verified_pixels'] for v in final['facts']['focus']['views']], [None, None])
        self.assertEqual(self.rasters, ['SCENE', 'FOCUS'])
        self.host.data.pop('capture_state')
        unversioned = self.result('auto')
        self.assertEqual(unversioned['facts']['focus']['stop_reason'], 'capture_generation_unavailable')
        self.assertEqual(self.rasters, ['SCENE', 'FOCUS'])
