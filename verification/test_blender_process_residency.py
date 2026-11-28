"""Resident owned capture contracts, without starting Blender."""
from collections import deque
from copy import deepcopy
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_process import (
    BlenderProcessHost, HostRemoteError, HostTransportError, SCENE_DELTA_PROTOCOL)
from human_eye_plugin.scene_residency import encode_capture
from human_eye_plugin import blender_worker


def fixture(*, instance='owned-a', epoch=1, revision=1, resource_revision=1,
            offset=0, selection='all'):
    local = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    matrix = [[1, 0, 0, offset], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    resource = dict(resource_id='a' * 64, revision=resource_revision,
                    vertices_local=local, faces=[[0, 1, 2]], edges=[[0, 1]])
    mesh = dict(object_id='part', name='Part',
                vertices=[[p[0] + offset, p[1], p[2]] for p in local],
                faces=[[0, 1, 2]], edges=[[0, 1]], transform='metadata')
    scene = dict(revision=str(revision), unit='m', coordinate_frame='world', meshes=[mesh],
                 capture_state=dict(instance_id=instance, epoch=epoch, revision=revision,
                                    selection_key=selection))
    return scene, {'part': (resource, matrix, 1)}


def client(*, resident=True):
    host = object.__new__(BlenderProcessHost)
    host._lock = threading.RLock()
    host._capabilities = {'scene_delta_protocol': SCENE_DELTA_PROTOCOL} if resident else {}
    host._scene_decoder = None
    host.timeout = 30
    host._closed = host._poisoned = False
    host._diagnostics = deque(maxlen=64)
    host._terminate_child = lambda: None
    return host


class OwnedResidentCaptureTests(unittest.TestCase):
    def test_resource_delta_preserves_full_public_capture_and_fresh_pose(self):
        host = client()
        current = [fixture()]
        requests = []
        wires = []

        def request(command, params, **kwargs):
            requests.append((command, deepcopy(params)))
            scene, bindings = current[0]
            packet = dict(capture=scene, directory=[{'id': 'part'}], focal_id='part') \
                if command == 'capture_nearest_candidates' else scene
            wire = encode_capture(packet, params['_scene_baseline'], bindings)
            wires.append(wire)
            return wire

        host._request = request
        cold = host.capture_scene()
        self.assertEqual(cold, current[0][0])
        self.assertEqual(len(wires[-1]['resources']), 1)
        cold['meshes'][0]['vertices'][0][0] = 900
        warm = host.capture_task_scene([{'id': 'part'}])
        self.assertEqual(warm, current[0][0])
        self.assertEqual(wires[-1]['resources'], [])
        self.assertEqual(requests[-1][0], 'capture_task')
        self.assertEqual(requests[-1][1]['selectors'], [{'id': 'part'}])

        current[0] = fixture(revision=2, offset=3, selection='nearest:part')
        nearest = host.capture_nearest_candidates('part', time.perf_counter_ns()+1_000_000_000, 100000)
        self.assertEqual(nearest['capture'], current[0][0])
        self.assertEqual(nearest['directory'], [{'id': 'part'}])
        self.assertEqual(wires[-1]['resources'], [])
        self.assertEqual(nearest['capture']['meshes'][0]['vertices'][0], [3, 0, 0])

        current[0] = fixture(revision=3, resource_revision=2)
        self.assertEqual(host.capture_scene(), current[0][0])
        self.assertEqual(len(wires[-1]['resources']), 1)
        current[0] = fixture(epoch=2, revision=4)
        host.capture_scene()
        self.assertEqual(len(wires[-1]['resources']), 1)
        current[0] = fixture(instance='owned-b')
        host.capture_scene()
        self.assertEqual(len(wires[-1]['resources']), 1)

    def test_legacy_and_native_evidence_do_not_receive_resource_baseline(self):
        host = client(resident=False)
        calls = []
        host._request = lambda command, params, **kwargs: calls.append((command, params)) or {'legacy': True}
        self.assertEqual(host.capture_scene(), {'legacy': True})
        self.assertEqual(calls[-1], ('capture', {}))
        host._capabilities['scene_delta_protocol'] = SCENE_DELTA_PROTOCOL
        self.assertEqual(host.capture_evidence(), {'legacy': True})
        self.assertEqual(calls[-1], ('capture_evidence', {}))

    def test_read_refusal_preserves_baseline_but_invalid_delta_poison_clears_it(self):
        host = client()
        scene, bindings = fixture()
        host._request = lambda command, params, **kwargs: encode_capture(scene, params['_scene_baseline'], bindings)
        host.capture_scene()
        baseline = host._scene_decoder.baseline()
        def refused(*args, **kwargs):
            raise HostRemoteError({'type': 'ValueError', 'message': 'unsupported capture'})
        host._request = refused
        with self.assertRaises(HostRemoteError):
            host.capture_scene()
        self.assertEqual(host._scene_decoder.baseline(), baseline)
        self.assertFalse(host._poisoned)
        bad = encode_capture(scene, None, bindings)
        bad['resources'] = []
        bad['capture']['capture_state']['epoch'] = 9
        host._request = lambda *args, **kwargs: bad
        with self.assertRaisesRegex(HostTransportError, 'resident capture'):
            host.capture_scene()
        self.assertTrue(host._poisoned)
        self.assertIsNone(host._scene_decoder)

    def test_nearest_input_deadline_clamp_and_postdecode_expiry(self):
        host = client(resident=False)
        host.timeout = 1
        calls = []
        host._request = lambda command, params, **kwargs: calls.append((command, params, kwargs)) or {}
        with patch('human_eye_plugin.blender_process.time.perf_counter_ns', return_value=1000):
            host.capture_nearest_candidates(None, 9_000_000_000, 100, selector={'name': 'Part'})
        command, params, kwargs = calls[-1]
        self.assertEqual(command, 'capture_nearest_candidates')
        self.assertEqual(params['deadline_ns'], 1_000_001_000)
        self.assertEqual(params['selector'], {'name': 'Part'})
        self.assertEqual(kwargs['timeout'], 1)
        calls.clear()
        invalid = [('', 5000, 100, None), ('part', True, 100, None),
                   ('part', 5000, True, None), ('part', 5000, 0, None),
                   ('part', 5000, 100, {'name': 'Part'}), (None, 5000, 100, {'name': ''})]
        for focal, deadline, size, selector in invalid:
            with self.subTest(focal=focal, deadline=deadline, size=size, selector=selector):
                with patch('human_eye_plugin.blender_process.time.perf_counter_ns', return_value=1000):
                    with self.assertRaises(ValueError):
                        host.capture_nearest_candidates(focal, deadline, size, selector=selector)
        self.assertEqual(calls, [])
        with patch('human_eye_plugin.blender_process.time.perf_counter_ns', side_effect=[1000, 5000]):
            with self.assertRaisesRegex(ValueError, 'deadline_exceeded'):
                host.capture_nearest_candidates('part', 5000, 100)
        self.assertFalse(host._poisoned)

    def test_256_resource_manifest_uses_capture_allowance_only(self):
        host = client()
        host._sequence = 0
        host._responses = queue.Queue()
        host._process = SimpleNamespace(stdin=io.StringIO(), poll=lambda: None)
        baseline = dict(instance_id='owned-a', epoch=1,
                        resources={format(i, '064x'): 1 for i in range(256)})
        host._responses.put(('response', {'id': 1, 'result': {'accepted': True}}))
        params = {'selectors': [{'id': 'part'}], '_scene_baseline': baseline}
        self.assertEqual(BlenderProcessHost._request(host, 'capture_task', params), {'accepted': True})
        delivered = host._process.stdin.getvalue()
        self.assertGreater(len(delivered), 4096)
        self.assertLess(len(delivered), 65536)
        self.assertEqual(json.loads(delivered)['params']['_scene_baseline'], baseline)
        before = delivered
        with self.assertRaisesRegex(ValueError, '4096-character'):
            BlenderProcessHost._request(host, 'apply', params)
        with self.assertRaisesRegex(ValueError, '65536-character'):
            BlenderProcessHost._request(host, 'capture', {'_scene_baseline': 'x'*65536})
        self.assertEqual(host._process.stdin.getvalue(), before)


FAKE_HOST = '''
from human_eye_plugin.scene_residency import encode_capture
from verification.test_blender_process_residency import fixture
constructed = 0
class BlenderSceneHost:
    def __init__(self, **kwargs):
        global constructed
        constructed += 1
        self.calls=[]
    def capture_scene(self):
        self.calls.append('capture')
        return fixture()[0]
    def capture_task_scene(self, selectors):
        self.calls.append(('task', selectors))
        return fixture(selection='task')[0]
    def capture_nearest_candidates(self, focal_id, deadline_ns, max_response_bytes, selector=None):
        self.calls.append(('nearest', focal_id, selector))
        return dict(capture=fixture(selection='nearest')[0], directory=[{'id':'part'}])
    def capture_surface_scan(self, threshold_m, deadline_ns, max_response_bytes):
        self.calls.append(('scan', threshold_m))
        return dict(capture=fixture(selection='scan')[0], pairs=[{'disposition':'retained'}])
    def capture_delta(self, packet, known=None):
        return encode_capture(packet, known, fixture()[1])
    def capture_evidence(self):
        return {'evidence':'raw', 'calls':self.calls}
'''


class ResidentWorkerTests(unittest.TestCase):
    def run_worker(self, commands, *, material=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'human_eye_plugin').mkdir()
            (root/'human_eye_plugin'/'blender_host.py').write_text(FAKE_HOST, encoding='utf8')
            requests = [dict(id=i, command=c, params=p) for i,(c,p) in enumerate(commands, 1)]
            output = io.StringIO()
            bpy = SimpleNamespace(app=SimpleNamespace(version_string='fake, no Blender'))
            with patch.dict(sys.modules, {'bpy': bpy}), patch.object(sys, 'stdin', io.StringIO(
                    ''.join(json.dumps(r)+'\n' for r in requests))), patch.object(sys, 'stdout', output):
                blender_worker.run_worker(root, material_readview_only=material)
                module = sys.modules['human_eye_blender_host_worker']
        return [json.loads(line[len(blender_worker.RPC_PREFIX):])
                for line in output.getvalue().splitlines()], module

    def test_one_resident_host_and_internal_delta_for_all_capture_commands(self):
        baseline = dict(instance_id='owned-a', epoch=1, resources={'a'*64: 1})
        replies, module = self.run_worker([
            ('capabilities', {}), ('capture', {'_scene_baseline': None}),
            ('capture_task', {'selectors':[{'id':'part'}], '_scene_baseline':baseline}),
            ('capture_nearest_candidates', dict(focal_id='part', deadline_ns=time.perf_counter_ns()+10_000_000_000,
                max_response_bytes=100000, _scene_baseline=baseline)),
            ('capture_evidence', {}), ('shutdown', {})])
        self.assertEqual(module.constructed, 1)
        self.assertEqual(replies[0]['result']['scene_delta_protocol'], SCENE_DELTA_PROTOCOL)
        self.assertEqual(len(replies[1]['result']['resources']), 1)
        self.assertEqual(replies[2]['result']['resources'], [])
        self.assertEqual(replies[3]['result']['resources'], [])
        self.assertEqual(replies[3]['result']['capture']['directory'], [{'id':'part'}])
        self.assertEqual(replies[4]['result']['evidence'], 'raw')
        self.assertNotIn('schema', replies[4]['result'])
        self.assertEqual(replies[4]['result']['calls'], ['capture', ['task', [{'id':'part'}]], ['nearest','part',None]])
        self.assertTrue(replies[-1]['result']['closed'])

    def test_invalid_capture_arguments_recover_and_material_worker_cannot_capture(self):
        replies, _ = self.run_worker([('capture_task', {'selectors':[], 'extra':True}),
                                      ('capture', {}), ('shutdown', {})])
        self.assertEqual(replies[0]['error']['type'], 'ValueError')
        self.assertFalse(replies[0]['error'].get('mutation_uncertain', False))
        self.assertIn('meshes', replies[1]['result'])
        replies, _ = self.run_worker([('capabilities', {}), ('capture', {}), ('shutdown', {})], material=True)
        self.assertIsNone(replies[0]['result']['scene_delta_protocol'])
        self.assertIn('no setter or general capture', replies[1]['error']['message'])
        self.assertTrue(replies[-1]['result']['closed'])

    def test_surface_scan_dispatch_delta_and_strict_fields(self):
        baseline = dict(instance_id='owned-a', epoch=1, resources={'a'*64:1})
        params = dict(threshold_m=.01, deadline_ns=time.perf_counter_ns()+10_000_000_000,
                      max_response_bytes=100000, _scene_baseline=baseline)
        replies, module = self.run_worker([('capture_surface_scan', dict(params, extra=True)),
            ('capture_surface_scan', params), ('shutdown', {})])
        self.assertIn('Invalid surface scan', replies[0]['error']['message'])
        self.assertEqual(replies[1]['result']['resources'], [])
        self.assertEqual(replies[1]['result']['capture']['pairs'], [{'disposition':'retained'}])
        self.assertEqual(module.constructed, 1)


if __name__ == '__main__':
    unittest.main()
