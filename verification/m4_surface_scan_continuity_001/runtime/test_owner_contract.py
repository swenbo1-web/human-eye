"""Offline lifecycle and real thin-client boundary checks with a synthetic broker."""

import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import types
import unittest


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


actor = load('_continuity_test_actor', HERE / 'actor.py')
transport = load('_continuity_test_transport', HERE / 'consumer_transport.py')


class FakeNative:
    def __init__(self, folder, initial):
        self.config = {'pid': 999}
        self.workspace = folder
        self.host = '127.0.0.1'
        self.port = 12345
        self.geometry = copy.deepcopy(initial)
        self.advance_calls = 0
        self.close_calls = 0

    def qa_advance(self, *, timeout_s):
        self.advance_calls += 1
        self.geometry = actor.expected_edit_snapshot(self.geometry)
        return {'response': {'status': 'success', 'result': {'stage': 1}}, 'timeout_s': timeout_s}

    def run(self, code, *, timeout_s):
        return {'response': {'status': 'success', 'result': {'result': 'marker'}}, 'timeout_s': timeout_s}

    def close(self):
        self.close_calls += 1
        return {'process_reaped': True, 'exit_code': 0}

    def status(self):
        return {'closed': {'final_geometry_fingerprint': 'accepted', 'accepted_geometry_fingerprint': 'accepted',
                           'qa_patch_applied': self.advance_calls == 1, 'poisoned': False}}


class OwnerContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.owner = actor.Owner.__new__(actor.Owner)
        self.owner.out = self.folder
        self.asset = self.folder / 'asset.blend'
        self.asset.write_bytes(b'synthetic asset fixture')
        self.owner.config = {'episode_id': 'N-001', 'worker_deadline_ns': time.perf_counter_ns() + 60_000_000_000,
                             'asset': str(self.asset), 'asset_sha256': actor.sha(self.asset)}
        self.owner.episode_id = 'N-001'
        self.owner.active_turn = None
        self.owner.completed_turns = []
        self.owner.control_events = []
        self.owner.edit_attempted = False
        self.owner.edit_verified = False
        self.owner.expected_final = None
        self.owner.close_record = None
        self.owner.calls = 0
        self.owner.bytes = 0
        self.owner.logs = []
        self.owner.peer = None
        self.owner.runtime_handle = None
        self.owner.started = time.perf_counter_ns()
        self.owner.image_construction_violation = False
        self.owner.observed_product_sessions = set()
        self.owner.read_names = frozenset()
        self.owner.initial = {'unit_scale_m': 1.0, 'objects': [{'name': 'Obj_008', 'vertices_local': [[0, 0, 0]],
            'faces': [], 'matrix_world': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}]}
        self.owner.native = FakeNative(self.folder, self.owner.initial)
        self.owner.snapshot = types.MethodType(lambda owner, name: copy.deepcopy(owner.native.geometry), self.owner)
        self.owner.image_construction_status = lambda: {'observed': False, 'status': 'not_observed_in_recorded_scope'}

    def tearDown(self):
        self.temp.cleanup()

    def control(self, operation, **fields):
        return self.owner.handle({'jsonrpc': '2.0', 'id': len(self.owner.control_events) + 1,
                                  'method': 'continuity/' + operation,
                                  'params': {'episode_id': 'N-001', **fields}})['result']

    def begin(self, turn):
        return self.control('begin_turn', turn_id=turn, deadline_ns=self.owner.config['worker_deadline_ns'])

    def finish_two(self):
        for turn in ('BASE', 'REPEAT'):
            self.begin(turn)
            self.control('end_turn', turn_id=turn)

    def test_fixed_order_rejects_repeat_first(self):
        with self.assertRaisesRegex(ValueError, 'fixed_turn_order'):
            self.begin('REPEAT')

    def test_wrong_episode_rejected(self):
        with self.assertRaisesRegex(ValueError, 'continuity_episode_binding'):
            self.owner.handle({'id': 1, 'method': 'continuity/status', 'params': {'episode_id': 'other'}})

    def test_deadline_cannot_extend_episode(self):
        with self.assertRaisesRegex(ValueError, 'turn_original_deadline'):
            self.control('begin_turn', turn_id='BASE', deadline_ns=self.owner.config['worker_deadline_ns'] + 1)

    def test_duplicate_begin_rejected(self):
        self.begin('BASE')
        with self.assertRaisesRegex(ValueError, 'turn_already_active'):
            self.begin('BASE')

    def test_end_wrong_turn_rejected(self):
        self.begin('BASE')
        with self.assertRaisesRegex(ValueError, 'active_turn_binding'):
            self.control('end_turn', turn_id='REPEAT')

    def test_edit_requires_two_closed_turns(self):
        self.begin('BASE')
        with self.assertRaisesRegex(ValueError, 'registered_edit_barrier'):
            self.control('qa_advance')
        self.assertEqual(self.owner.native.advance_calls, 0)

    def test_edit_turn_requires_verified_barrier(self):
        self.finish_two()
        with self.assertRaisesRegex(ValueError, 'edit_barrier_not_verified'):
            self.begin('EDIT')

    def test_registered_pose_is_exact_and_one_attempt(self):
        self.finish_two()
        result = self.control('qa_advance')
        self.assertEqual(result['snapshot'], actor.expected_edit_snapshot(self.owner.initial))
        self.assertTrue(result['status']['edit_verified'])
        with self.assertRaisesRegex(ValueError, 'registered_edit_no_replay'):
            self.control('qa_advance')
        self.assertEqual(self.owner.native.advance_calls, 1)

    def test_prior_unexpected_edit_blocks_action(self):
        self.finish_two()
        self.owner.native.geometry['unit_scale_m'] = 2
        with self.assertRaisesRegex(ValueError, 'unexpected_pre_edit_geometry'):
            self.control('qa_advance')
        self.assertEqual(self.owner.native.advance_calls, 0)
        self.assertTrue(self.owner.edit_attempted)

    def test_third_turn_completes_without_close(self):
        self.finish_two()
        self.control('qa_advance')
        self.begin('EDIT')
        status = self.control('end_turn', turn_id='EDIT')
        self.assertEqual([r['turn_id'] for r in status['completed_turns']], ['BASE', 'REPEAT', 'EDIT'])
        self.assertFalse(status['owner_close_called'])
        self.assertEqual(self.owner.native.close_calls, 0)

    def test_business_requires_active_turn(self):
        with self.assertRaisesRegex(ValueError, 'business_requires_active_turn'):
            self.owner.handle({'id': 1, 'method': 'tools/call', 'params': {'name': 'execute_blender_code', 'arguments': {'code': 'print(1)'}}})
        self.assertEqual(self.owner.calls, 0)

    def test_business_attached_to_one_turn(self):
        self.begin('BASE')
        result = self.owner.handle({'id': 10, 'method': 'tools/call', 'params': {'name': 'execute_blender_code', 'arguments': {'code': 'print(1)'}}})
        self.assertFalse(result['result']['isError'])
        status = self.control('end_turn', turn_id='BASE')
        self.assertEqual(status['completed_turns'][0]['business_attempts'], 1)

    def test_close_accepts_registered_edit_and_is_idempotent(self):
        self.finish_two()
        self.control('qa_advance')
        self.begin('EDIT')
        self.control('end_turn', turn_id='EDIT')
        result = self.owner.close()
        self.assertFalse(result['geometry_unchanged'])
        self.assertTrue(result['expected_terminal_geometry_matches'])
        self.assertTrue(result['accepted_worker_geometry_matches'])
        self.assertTrue(result['confirmed'])
        self.assertIs(self.owner.close(), result)
        self.assertEqual(self.owner.native.close_calls, 1)

    def test_bad_terminal_snapshot_still_closes_worker(self):
        self.owner.native.geometry['unit_scale_m'] = 2
        result = self.owner.close()
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.owner.native.close_calls, 1)

    def test_snapshot_failure_still_closes_worker(self):
        def fail(name):
            raise ValueError('synthetic snapshot failure')
        self.owner.snapshot = fail
        result = self.owner.close()
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.owner.native.close_calls, 1)


class ThinBoundary(unittest.TestCase):
    def test_three_real_client_eofs_preserve_synthetic_broker(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        listener.settimeout(0.1)
        stop = threading.Event()
        requests = []
        errors = []

        def serve():
            try:
                while not stop.is_set():
                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        raw = bytearray()
                        while True:
                            part = connection.recv(65536)
                            if not part:
                                break
                            raw.extend(part)
                        request = json.loads(raw)
                        message = request['args']['message']
                        requests.append(message)
                        response = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'synthetic_owner': 'unchanged'}}
                        connection.sendall(actor.encoded({'request_id': request['request_id'], 'ok': True, 'result': response}))
            except BaseException as exc:
                errors.append(repr(exc))

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                deadline = time.perf_counter_ns() + 30_000_000_000
                endpoint = {'host': '127.0.0.1', 'port': listener.getsockname()[1], 'chain_deadline_ns': deadline}
                messages = [{'id': index + 1, 'method': method} for index, method in enumerate(('initialize', 'tools/list', 'ping', 'tools/call'))]
                clients = []
                for turn in ('BASE', 'REPEAT', 'EDIT'):
                    row = transport.thin_turn(python=sys.executable, endpoint=endpoint, folder=Path(directory)/turn,
                                              requests=messages, deadline_ns=deadline)
                    self.assertTrue(row['confirmed'], row)
                    self.assertTrue(row['bridge_cleanup']['confirmed'])
                    self.assertFalse(row['bridge_cleanup']['instances'][0]['exit']['backend_close_requested'])
                    self.assertEqual([response['id'] for response in row['responses']], [1, 2, 3, 4])
                    clients.append(row['pid'])
                self.assertEqual(len(set(clients)), 3)
                self.assertEqual(len(requests), 12)
                self.assertTrue(thread.is_alive())
                self.assertEqual(errors, [])
        finally:
            stop.set()
            thread.join(timeout=2)
            listener.close()


if __name__ == '__main__':
    unittest.main()
