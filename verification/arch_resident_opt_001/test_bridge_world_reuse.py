"""Exercise resident world reuse through both bridges, with no external process."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import ast
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.blender_process import (
    BlenderProcessHost, HostRemoteError, HostTransportError, SCENE_DELTA_PROTOCOL)
from human_eye_plugin.scene_residency import encode_capture
from verification.test_blender_mcp_host import _reply, _request_from_code

ROOT = Path(__file__).resolve().parents[2]


def sample(*, revision=1, resource_revision=1, instance='one-worker', epoch=1,
           translation=2, scale=0.5, x=1, name='Part', color=None):
    local = [[0, 0, 0], [x, 0, 0], [0, 1, 0]]
    # A quarter rotation followed by translation: independent expected formula.
    world = [[(translation-p[1])*scale, (3+p[0])*scale, (4+p[2])*scale] for p in local]
    matrix = [[0, -1, 0, translation], [1, 0, 0, 3], [0, 0, 1, 4], [0, 0, 0, 1]]
    resource = dict(resource_id='mesh:stable', revision=resource_revision,
                    vertices_local=local, faces=[[0, 1, 2]], edges=[[0, 1]])
    mesh = dict(object_id='part', name=name, color_rgb=color or [12, 34, 56],
                vertices=world, faces=[[0, 1, 2]], edges=[[0, 1]])
    scene = dict(unit='m', coordinate_frame='world', revision='r'+str(revision), meshes=[mesh],
                 capture_state=dict(instance_id=instance, epoch=epoch, revision=revision,
                                    selection_key='selection:'+str(revision)))
    return scene, {'part': (resource, matrix, scale)}


def transmitted_baseline(code):
    tree = ast.parse(code)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'capture_delta')
    return json.loads(ast.literal_eval(call.args[1].args[0]))


class Bridge:
    """Only the transport peer is fake; constructors and bridge decode are real."""
    def __init__(self, case, kind):
        self.kind = kind
        self.scene, self.bindings = sample()
        self.calls = []
        self.wires = []
        self.error = False
        self.override = None
        self.on_request = None
        if kind == 'MCP':
            self.host = BlenderMCPHost(ROOT)
            self.host._exchange = self.exchange
        else:
            temporary = tempfile.TemporaryDirectory(prefix='owned-world-reuse-')
            case.addCleanup(temporary.cleanup)
            blend = Path(temporary.name)/'isolated.blend'
            blend.write_bytes(b'not loaded: constructor transport is mocked')
            process = Mock(stdin=io.StringIO(), stdout=io.StringIO(), stderr=io.StringIO())
            process.poll.return_value = None
            process.wait.return_value = 0
            thread = Mock()
            thread.is_alive.return_value = False
            with patch('human_eye_plugin.blender_process.subprocess.Popen', return_value=process), \
                    patch('human_eye_plugin.blender_process.threading.Thread', return_value=thread), \
                    patch.object(BlenderProcessHost, '_request', return_value={
                        'protocol_version':'1.0', 'scene_delta_protocol':SCENE_DELTA_PROTOCOL}):
                self.host = BlenderProcessHost(sys.executable, blend,
                    worker_path=ROOT/'human_eye_plugin/blender_worker.py')
            self.host._request = self.owned_request
        case.addCleanup(self.host.close)

    def reply(self, command, params, baseline):
        if command == 'shutdown':return {'closed':True}
        # The complete baseline/read/decode sequence must stay in one RLock.
        if not self.host._lock._is_owned():
            raise AssertionError('bridge released its lock before capture response')
        self.calls.append((command, deepcopy(baseline)))
        if self.on_request:self.on_request(command, baseline)
        if self.error:raise HostRemoteError({'type':'ValueError','message':'read refused','mutation_uncertain':False})
        if self.override is not None:return deepcopy(self.override)
        packet = self.scene
        if command == 'capture_nearest_candidates':
            packet = dict(capture=self.scene, directory=[{'id':'part'}], focal_id='part',
                protocol='single-read-surface-candidates-v1', execution_authority=False,
                binding={'host_source_sha256':getattr(self.host,'_readonly_host_source_sha256','owned')})
        wire = encode_capture(packet, baseline, self.bindings)
        self.wires.append(deepcopy(wire))
        return wire

    def owned_request(self, command, params, **kwargs):
        return self.reply(command, params, params.get('_scene_baseline'))

    def exchange(self, payload):
        outer = json.loads(payload)
        request = _request_from_code(outer)
        try:
            result = self.reply(request['command'], request['params'],
                                transmitted_baseline(outer['params']['code']))
        except HostRemoteError as exc:
            return _reply(request, error=exc.error)
        return _reply(request, result)

    def update(self, **kwargs):
        self.scene, self.bindings = sample(**kwargs)

    def capture(self, mode='scene'):
        if mode == 'task':return self.host.capture_task_scene([{'id':'part'}])
        if mode == 'nearest':
            return self.host.capture_nearest_candidates('part', time.perf_counter_ns()+2_000_000_000, 100000)
        return self.host.capture_scene()


class BridgeWorldReuseTests(unittest.TestCase):
    def assert_work(self, decoder, transforms, vertices):
        self.assertEqual(decoder.work_totals(), {'world_transforms':transforms,
                                                'transformed_vertices':vertices})

    def test_decoder_lives_across_capture_modes_but_never_across_connections(self):
        for kind in ('MCP','owned'):
            with self.subTest(kind=kind):
                bridge = Bridge(self, kind)
                self.assertIsInstance(bridge.host._lock, type(threading.RLock()))
                cold = bridge.capture()
                decoder = bridge.host._scene_decoder
                self.assert_work(decoder, 1, 3)
                original_apply = decoder.apply
                def locked_apply(packet):
                    self.assertTrue(bridge.host._lock._is_owned())
                    # Taking the public transaction inside decode proves the
                    # production lock is reentrant, not merely held at send.
                    with bridge.host.transaction():return original_apply(packet)
                decoder.apply = locked_apply
                cold['meshes'][0]['vertices'][0][0] = 999
                bridge.update(revision=2, name='Renamed', color=[255,0,0])
                task = bridge.capture('task')
                nearest = bridge.capture('nearest')
                self.assertIs(bridge.host._scene_decoder, decoder)
                self.assertEqual(task, bridge.scene)
                self.assertEqual(nearest['capture'], bridge.scene)
                self.assertEqual(bridge.wires[1]['resources'], [])
                self.assertEqual(bridge.wires[2]['resources'], [])
                self.assert_work(decoder, 1, 3)
                fresh = Bridge(self, kind)
                self.assertEqual(fresh.capture(), fresh.scene)
                self.assertIsNone(fresh.calls[0][1])
                self.assertIsNot(fresh.host._scene_decoder, decoder)
                self.assert_work(fresh.host._scene_decoder, 1, 3)

    def test_pose_resource_scale_epoch_and_instance_changes_recompute_exact_world(self):
        for kind in ('MCP','owned'):
            with self.subTest(kind=kind):
                bridge = Bridge(self, kind)
                bridge.capture()
                cases = [dict(revision=2, translation=5),
                         dict(revision=3, translation=5, resource_revision=2, x=2),
                         dict(revision=4, translation=5, resource_revision=2, x=2, scale=0.25),
                         dict(revision=5, epoch=2), dict(revision=1, instance='replacement')]
                for number, args in enumerate(cases, 2):
                    bridge.update(**args)
                    self.assertEqual(bridge.capture(), bridge.scene)
                    self.assert_work(bridge.host._scene_decoder, number, number*3)
                self.assertEqual(bridge.wires[1]['resources'], [])
                self.assertEqual(len(bridge.wires[2]['resources']), 1)
                self.assertEqual(bridge.wires[3]['resources'], [])

    def test_definite_read_error_preserves_confirmed_cache(self):
        for kind in ('MCP','owned'):
            with self.subTest(kind=kind):
                bridge = Bridge(self, kind)
                bridge.capture()
                decoder = bridge.host._scene_decoder
                before = decoder.baseline()
                bridge.error = True
                with self.assertRaises(HostRemoteError):bridge.capture('task')
                self.assertEqual(decoder.baseline(), before)
                self.assertFalse(bridge.host._poisoned)
                self.assert_work(decoder, 1, 3)
                bridge.error = False
                self.assertEqual(bridge.capture('task'), bridge.scene)
                self.assertIs(bridge.host._scene_decoder, decoder)
                self.assert_work(decoder, 1, 3)

    def test_partial_decode_failure_cannot_publish_new_world_or_baseline(self):
        for kind in ('MCP','owned'):
            with self.subTest(kind=kind):
                bridge = Bridge(self, kind)
                bridge.capture()
                decoder = bridge.host._scene_decoder
                before = decoder.baseline()
                bridge.update(revision=2, translation=9)
                bad = encode_capture(bridge.scene, before, bridge.bindings)
                missing = deepcopy(bad['capture']['meshes'][0])
                missing['object_id'] = 'missing'
                missing['_scene_resource']['id'] = 'not-supplied'
                bad['capture']['meshes'].append(missing)
                bridge.override = bad
                with self.assertRaises(HostTransportError):bridge.capture()
                self.assertTrue(bridge.host._poisoned)
                self.assertEqual(decoder.baseline(), before)
                self.assert_work(decoder, 1, 3)
                with self.assertRaises(HostTransportError):
                    # Owned's real transport live check is bypassed by its fake
                    # peer, so use the real local validity gate here.
                    bridge.host._ensure_live()
                if kind == 'owned':self.assertIsNone(bridge.host._scene_decoder)
                # Inspect the retained old decoder offline; do not reuse the
                # poisoned product connection or pretend it recovered.
                original, bindings = sample()
                self.assertEqual(decoder.apply(encode_capture(original, before, bindings)), original)
                self.assert_work(decoder, 1, 3)
                self.assertEqual(decoder.apply(encode_capture(bridge.scene, decoder.baseline(), bridge.bindings)), bridge.scene)
                # A failed staged pose must be computed on its first later
                # successful use, rather than retained as a hidden cache hit.
                self.assert_work(decoder, 2, 6)

    def test_lock_spans_baseline_rpc_and_apply_for_concurrent_callers(self):
        for kind in ('MCP','owned'):
            with self.subTest(kind=kind):
                bridge = Bridge(self, kind)
                entered = threading.Event()
                release = threading.Event()
                second_ready = threading.Event()
                def first_request(command, baseline):
                    if len(bridge.calls) == 1:
                        entered.set()
                        if not release.wait(2):raise AssertionError('test release not delivered')
                bridge.on_request = first_request
                def second_call():
                    second_ready.set()
                    return bridge.capture('task')
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(bridge.capture)
                    try:
                        self.assertTrue(entered.wait(2))
                        second = pool.submit(second_call)
                        self.assertTrue(second_ready.wait(2))
                        acquired = bridge.host._lock.acquire(blocking=False)
                        if acquired:bridge.host._lock.release()
                        self.assertFalse(acquired)
                        self.assertEqual(len(bridge.calls), 1)
                    finally:release.set()
                    self.assertEqual(first.result(timeout=2), bridge.scene)
                    self.assertEqual(second.result(timeout=2), bridge.scene)
                self.assertIsNone(bridge.calls[0][1])
                self.assertEqual(bridge.calls[1][1]['resources'], {'mesh:stable':1})
                self.assert_work(bridge.host._scene_decoder, 1, 3)


if __name__ == '__main__':unittest.main()
