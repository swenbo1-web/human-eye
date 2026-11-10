"""Pure fake tests for owned cleanup and failure-attempt accounting.

No Owner/Peer constructor, Blender, serve, consumer, network, or subprocess is
started. The actual actor methods run against temporary files and fake peers.
"""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ACTOR_PATH = HERE / 'actor.py'
ACTOR_BYTES = ACTOR_PATH.read_bytes()
actor = types.ModuleType('complex004_lifecycle_actor')
actor.__file__ = str(ACTOR_PATH)
exec(compile(ACTOR_BYTES, str(ACTOR_PATH), 'exec'), actor.__dict__)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError('Pure wrapper test must not start a process or network')


class NativeFake:
    def __init__(self, order, run_error=None):
        self.order = order
        self.run_error = run_error
        self.run_calls = []

    def run(self, code, *, timeout_s):
        self.run_calls.append((code, timeout_s))
        if self.run_error is not None:
            raise self.run_error
        return {'response': {'status': 'success', 'result': {'result': 'fake native output'}}}

    def close(self):
        self.order.append('native.close')
        return {'process_reaped': True, 'exit_code': 0}

    def status(self):
        self.order.append('native.status')
        return {'closed': {'fixture': 'closed'}}


class PeerFake:
    def __init__(self, order, close_error=None):
        self.order = order
        self.close_error = close_error
        self.close_record = None
        self.call_requests = []

    def call(self, request, *, timeout_s):
        self.call_requests.append((request, timeout_s))
        return {'jsonrpc': '2.0', 'id': request['id'],
                'result': {'content': [{'type': 'text', 'text': 'fake read-only result'}],
                           'isError': False}}

    def close(self):
        self.order.append('peer.close')
        if self.close_error is not None:
            raise self.close_error
        self.close_record = {'confirmed': True}
        return self.close_record


class ActorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='complex004_wrapper_')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.asset = self.folder / 'fake-scene-bytes'
        self.asset.write_bytes(b'owned fake bytes; never opened in Blender')
        self.owner_index = 0

    def owner(self, *, snapshot_error=None, peer_close_error=None, native_run_error=None):
        self.owner_index += 1
        value = actor.Owner.__new__(actor.Owner)
        value.out = self.folder / ('owner_' + str(self.owner_index))
        value.out.mkdir()
        value.order = []
        value.config = {'asset': str(self.asset), 'asset_sha256': sha(self.asset.read_bytes())}
        value.started = time.perf_counter_ns()
        value.calls, value.bytes, value.logs = 0, 0, []
        value.initial = {'geometry': 'fixed fake snapshot'}
        value.peer = PeerFake(value.order, peer_close_error)
        value.native = NativeFake(value.order, native_run_error)

        def snapshot(name):
            self.assertEqual(name, 'FINAL.json')
            value.order.append('snapshot')
            if snapshot_error is not None:
                raise snapshot_error
            return dict(value.initial)

        value.snapshot = snapshot
        return value

    def assert_saved_close(self, owner, result, *, confirmed, errors):
        self.assertIs(result['confirmed'], confirmed)
        self.assertEqual([row['stage'] for row in result['errors']], errors)
        self.assertEqual(json.loads((owner.out / 'CLOSE.json').read_bytes()), result)
        self.assertEqual(owner.order, ['snapshot', 'peer.close', 'native.close', 'native.status'])
        self.assertTrue(result['native_close']['process_reaped'])
        self.assertTrue(result['worker_closed'])

    def test_normal_close_orders_snapshot_then_peer_then_native(self):
        owner = self.owner()
        self.assert_saved_close(owner, owner.close(), confirmed=True, errors=[])

    def test_failed_final_snapshot_still_closes_peer_and_native(self):
        owner = self.owner(snapshot_error=OSError('fake final snapshot failure'))
        self.assert_saved_close(owner, owner.close(), confirmed=False, errors=['final_snapshot'])

    def test_failed_peer_close_still_closes_native(self):
        owner = self.owner(peer_close_error=OSError('fake peer close failure'))
        self.assert_saved_close(owner, owner.close(), confirmed=False, errors=['product_close'])

    def test_failed_final_snapshot_and_peer_close_still_close_native(self):
        owner = self.owner(snapshot_error=OSError('fake final snapshot failure'),
                           peer_close_error=OSError('fake peer close failure'))
        self.assert_saved_close(owner, owner.close(), confirmed=False,
                                errors=['final_snapshot', 'product_close'])

    def request(self, name, arguments):
        return {'jsonrpc': '2.0', 'id': 'fake-tool-request', 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments}}

    def assert_attempt(self, owner, request, response, *, exception_type=None,
                       message=None, initial_wire_bytes=0):
        folder = owner.out / 'tool_01'
        self.assertEqual(json.loads((folder / 'REQUEST.json').read_bytes()), request)
        tools = json.loads((owner.out / 'TOOLS.json').read_bytes())
        self.assertEqual((tools['attempts'], tools['calls']), (1, 1))
        self.assertEqual(len(tools['tools']), 1)
        row = tools['tools'][0]
        self.assertEqual(json.loads((folder / 'ATTEMPT.json').read_bytes()), row)
        self.assertEqual(owner.logs, [row])
        self.assertEqual(row['name'], request['params']['name'])
        self.assertIs(type(row['started_ns']), int)
        self.assertIs(type(row['elapsed_ns']), int)
        self.assertGreaterEqual(row['elapsed_ns'], 0)
        self.assertIs(type(row['response_bytes']), int)
        expected_wire = 0 if response is None else len(actor.encoded(response))
        self.assertEqual(row['response_bytes'], expected_wire)
        self.assertEqual(tools['wire_tool_bytes'], initial_wire_bytes + expected_wire)
        if exception_type is None:
            self.assertIsNone(row['exception'])
            self.assertFalse(row['is_error'])
            self.assertEqual(json.loads((folder / 'RESPONSE.json').read_bytes()), response)
        else:
            self.assertEqual(row['exception']['type'], exception_type)
            self.assertEqual(row['exception']['message'], message)
            self.assertIn('Traceback', row['exception']['traceback'])
            self.assertTrue(row['is_error'])
            if response is not None:
                self.assertTrue(response['result']['isError'])
                self.assertEqual(json.loads((folder / 'ERROR_RESPONSE.json').read_bytes()), response)

    def test_native_oserror_is_recorded_with_request_time_and_error_response(self):
        owner = self.owner(native_run_error=OSError('fake native request failure'))
        request = self.request('execute_blender_code', {'code': 'print(1)'})
        response = owner.handle(request)
        self.assert_attempt(owner, request, response, exception_type='OSError',
                            message='fake native request failure')
        self.assertEqual(owner.native.run_calls, [('print(1)', 30)])

    def test_unknown_tool_is_recorded_without_touching_backend(self):
        owner = self.owner()
        request = self.request('not_an_available_tool', {})
        response = owner.handle(request)
        self.assert_attempt(owner, request, response, exception_type='ValueError',
                            message='tool_not_available')
        self.assertEqual(owner.native.run_calls, [])
        self.assertEqual(owner.peer.call_requests, [])

    def test_zero_image_rejections_are_recorded_without_forwarding(self):
        for arguments in ({}, {'include_image': True}, {'include_image': None}):
            with self.subTest(arguments=arguments):
                owner = self.owner()
                request = self.request('human_eye_scene_observe', arguments)
                response = owner.handle(request)
                self.assert_attempt(owner, request, response, exception_type='ValueError',
                    message='zero_image_budget_requires_explicit_include_image_false')
                self.assertEqual(owner.native.run_calls, [])
                self.assertEqual(owner.peer.call_requests, [])

    def test_successful_native_request_is_also_recorded(self):
        owner = self.owner()
        request = self.request('execute_blender_code', {'code': 'print(1)'})
        response = owner.handle(request)
        self.assert_attempt(owner, request, response)
        self.assertGreater(owner.logs[0]['produced_response_bytes'], 0)

    def test_undeliverable_oserror_still_records_finally_with_zero_response_bytes(self):
        owner = self.owner(native_run_error=OSError('fake native request failure'))
        owner.bytes = 1048576
        request = self.request('execute_blender_code', {'code': 'print(1)'})
        with self.assertRaisesRegex(OSError, '^fake native request failure$'):
            owner.handle(request)
        self.assert_attempt(owner, request, None, exception_type='OSError',
                            message='fake native request failure', initial_wire_bytes=1048576)


def main():
    with (HERE / 'WRAPPER_TESTS.txt').open('x', encoding='utf8', newline='\n') as stream:
        with patch.object(subprocess, 'Popen', side_effect=forbidden), \
                patch.object(socket, 'socket', side_effect=forbidden), \
                patch.object(socket, 'create_connection', side_effect=forbidden):
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(ActorLifecycleTests))
    unchanged = ACTOR_PATH.read_bytes() == ACTOR_BYTES
    value = {'schema': 'complex-004-wrapper-pure-tests-v1',
        'tests_run': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped),
        'passed': result.wasSuccessful() and unchanged,
        'actor_source_unchanged': unchanged, 'actor_sha256': sha(ACTOR_BYTES),
        'test_sha256': sha(Path(__file__).read_bytes()),
        'log_sha256': sha((HERE / 'WRAPPER_TESTS.txt').read_bytes()),
        'failure_ids': [test.id() for test, trace in result.failures],
        'error_ids': [test.id() for test, trace in result.errors],
        'Blender_runs': 0, 'serve_processes': 0, 'consumer_runs': 0,
        'performance_samples': 0, 'test_only_timing_not_performance_samples': True,
        'scope': 'Actual Owner.handle/close against fakes; Owner/Peer initialization not invoked.'}
    with (HERE / 'WRAPPER_TESTS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
