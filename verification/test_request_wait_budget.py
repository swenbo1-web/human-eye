"""Optional local precommit deadlines preserve serialization and uncertainty."""
from contextlib import contextmanager
import copy
import errno
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import agent_hooks
from human_eye_plugin.agent_hooks import _state_lock, StateLockTimeoutError
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError, StateBindingError
from human_eye_plugin.live_hooks import route_live_hook
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer


SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                 [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]])

def mesh(identity, center, size, focal=False):
    return MeshEntity3D(identity, '#'+identity, identity,
        SIGNS*np.array(size)/2+np.array(center), FACES, None, (70,140,210), focal,
        local_axes=np.eye(3), pivot_world=np.array(center, dtype=float)).to_dict()


class TestHost:
    def __init__(self):
        self.scene = dict(revision='r1', unit='m', coordinate_frame='world', source='budget_test',
            meshes=[mesh('base', [0,0,.1], [1,1,.2]), mesh('part', [0,0,.35], [.2,.3,.1], True)])
        self.captures = self.mutations = 0
        self.after_capture = self.after_mutation = lambda: None
        self.fail_mutation = False

    @contextmanager
    def transaction(self):
        yield

    def capture_scene(self):
        self.captures += 1
        result = copy.deepcopy(self.scene)
        self.after_capture()
        return result

    def apply_transform(self, action, expected_revision, expected_fingerprint=None):
        self.mutations += 1
        self.after_mutation()
        if self.fail_mutation:
            raise OSError('Unknown result after dispatch')
        target = next(item for item in self.scene['meshes'] if item['object_id'] == action['focal_id'])
        translation = action.get('translation', [0,0,0])
        target['vertices'] = (np.array(target['vertices']) + np.array(translation)).tolist()
        target['pivot_world'] = (np.array(target['pivot_world']) + np.array(translation)).tolist()
        self.scene['revision'] = 'r2'
        return {'revision': 'r2'}


class Clock:
    def __init__(self):
        self.value = 0.
    def monotonic(self):
        return self.value
    def time(self):
        return time.time()
    def expire(self):
        self.value = 1000.


HOLDER = """import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from human_eye_plugin.agent_hooks import _state_lock
with _state_lock(Path(sys.argv[2])):
 Path(sys.argv[3]).touch()
 deadline=time.monotonic()+10
 while not Path(sys.argv[4]).exists() and time.monotonic()<deadline:time.sleep(.01)
"""


class RequestWaitBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config_path = self.base/'connector.json'
        self.state_path = self.base/'state.json'
        self.config = dict(schema_version='1.0', project_root=str(Path(agent_hooks.__file__).resolve().parents[1]),
            state_file='state.json', audit_file='audit.jsonl', quad_size=64, max_sessions=4,
            request_budget_s=1.)
        self.host = TestHost()
        self.action = dict(focal_id='part', reference_id='base', translation=[0,0,.05])
        self.service = self.make_service()

    def make_service(self, **changes):
        self.config.update(changes)
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        return LiveSpatialService(self.config_path, host=self.host)

    def holder(self):
        ready, release = self.base/'ready', self.base/'release'
        worker = subprocess.Popen([sys.executable, '-I', '-B', '-c', HOLDER,
            str(Path(agent_hooks.__file__).resolve().parents[1]), str(self.state_path), str(ready), str(release)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            release.touch()
            try:
                worker.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                worker.terminate()
                worker.communicate(timeout=5)
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5
        while not ready.exists() and worker.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(ready.exists(), 'Isolated lock holder failed to start')
        return worker, release

    def assert_refusal(self, caught, kind):
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, 'live_request_'+kind)
        fields = error.to_error_fields()
        self.assertFalse(fields['executed'])
        self.assertFalse(fields['host_mutation_started'])
        self.assertFalse(fields['connector_state_write_attempted'])
        self.assertFalse(fields['retry_authorized'])
        self.assertEqual(self.host.mutations, 0)

    def test_opt_in_config_validation_and_default_compatibility(self):
        for value in (True, False, 0, -1, '1', [], {}, float('inf'), float('nan'), 10**400):
            with self.subTest(value=str(value)[:30]):
                with self.assertRaises(ValueError):
                    self.make_service(request_budget_s=value)
        self.make_service(request_budget_s=None).status()
        self.config.pop('request_budget_s')
        self.assertIsNone(self.make_service().request_budget_s)

    def test_real_cross_process_wait_is_busy_and_never_runs_late(self):
        service = self.make_service(request_budget_s=.06)
        worker, release = self.holder()
        started = time.monotonic()
        with self.assertRaises(RequestBudgetError) as caught:
            service.transform('s', self.action)
        elapsed = time.monotonic()-started
        self.assert_refusal(caught, 'busy')
        self.assertEqual(self.host.captures, 0)
        self.assertFalse(self.state_path.exists())
        self.assertLess(elapsed, 1.)
        release.touch()
        worker.communicate(timeout=5)
        self.assertEqual(worker.returncode, 0)
        time.sleep(.08)
        self.assertEqual(self.host.captures, 0)
        self.assertFalse(self.state_path.exists())

    def test_release_allows_a_new_request_with_fresh_budget(self):
        service = self.make_service(request_budget_s=.06)
        worker, release = self.holder()
        with self.assertRaises(RequestBudgetError):
            service.status()
        release.touch()
        worker.communicate(timeout=5)
        self.assertFalse(service.status()['inflight_operation'])
        service.request_budget_s = 2.
        result = service.transform('s', self.action)
        self.assertTrue(result['verified'], result)
        self.assertEqual(self.host.mutations, 1)

    def test_no_budget_retains_old_wait_instead_of_new_expiry(self):
        service = self.make_service(request_budget_s=None)
        worker, release = self.holder()
        timer = threading.Timer(.12, release.touch)
        timer.start()
        self.addCleanup(timer.join)
        started = time.monotonic()
        result = service.status()
        self.assertGreaterEqual(time.monotonic()-started, .1)
        self.assertFalse(result['inflight_operation'])
        worker.communicate(timeout=5)

    def test_lock_released_at_deadline_is_rechecked_before_state_read(self):
        clock = Clock()
        @contextmanager
        def late_lock(*args, **kwargs):
            with _state_lock(*args, **kwargs):
                clock.expire()
                yield
        with patch('human_eye_plugin.live_service.time', clock), patch('human_eye_plugin.live_service._state_lock', late_lock):
            with patch('human_eye_plugin.live_service._read_object') as read_state:
                with self.assertRaises(RequestBudgetError) as caught:
                    self.service.status()
        self.assert_refusal(caught, 'expired')
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'], 'after_state_lock')
        read_state.assert_not_called()
        self.assertEqual(self.host.captures, 0)

    def test_exact_deadline_boundary_is_expired(self):
        clock = Clock()
        with patch('human_eye_plugin.live_service.time', clock):
            with self.service._request_budget():
                clock.value = 1.
                with self.assertRaises(RequestBudgetError) as caught:
                    self.service._check_request_budget('boundary')
        self.assert_refusal(caught, 'expired')

    def test_budget_remaining_is_forwarded_without_extending_old_lock_limit(self):
        seen = []
        @contextmanager
        def measured_lock(path, *, timeout_s):
            if Path(path).resolve() == self.state_path.resolve():
                seen.append(timeout_s)
            with _state_lock(path, timeout_s=timeout_s):
                yield
        service = self.make_service(request_budget_s=30.)
        with patch('human_eye_plugin.live_service.time', Clock()), patch('human_eye_plugin.live_service._state_lock', measured_lock):
            service.status()
        self.assertEqual(seen, [20])
        seen.clear()
        service.request_budget_s = .25
        with patch('human_eye_plugin.live_service.time', Clock()), patch('human_eye_plugin.live_service._state_lock', measured_lock):
            service.status()
        self.assertEqual(seen, [.25])

    def test_expiry_preserves_existing_state_bytes(self):
        self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        before = self.state_path.read_bytes()
        clock = Clock()
        self.host.after_capture = clock.expire
        with patch('human_eye_plugin.live_service.time', clock):
            with self.assertRaises(RequestBudgetError):
                self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_budget_context_resets_after_a_refusal(self):
        clock = Clock()
        self.host.after_capture = clock.expire
        with patch('human_eye_plugin.live_service.time', clock):
            with self.assertRaises(RequestBudgetError):
                self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
            self.host.after_capture = lambda: None
            self.assertFalse(self.service.status()['inflight_operation'])

    def test_state_binding_error_is_not_relabelled_if_read_exceeds_budget(self):
        self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        state = json.loads(self.state_path.read_text())
        state['config_fingerprint'] = 'f'*64
        self.state_path.write_text(json.dumps(state))
        before = self.state_path.read_bytes()
        clock = Clock()
        original = agent_hooks._read_object
        def slow_read(path):
            value = original(path)
            clock.expire()
            return value
        with patch('human_eye_plugin.live_service.time', clock), patch('human_eye_plugin.live_service._read_object', slow_read):
            with self.assertRaises(StateBindingError):
                self.service.status()
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_state_write_failure_after_submit_retains_uncertainty(self):
        from human_eye_plugin.live_service import _atomic_write
        clock = Clock()
        self.host.after_mutation = clock.expire
        writes = []
        def fail_final(path, value, **kwargs):
            writes.append(copy.deepcopy(value))
            if len(writes) == 2:
                raise OSError(errno.EIO, 'Final state write failed')
            return _atomic_write(path, value, **kwargs)
        with patch('human_eye_plugin.live_service.time', clock), patch('human_eye_plugin.live_service._atomic_write', fail_final):
            with self.assertRaises(OSError):
                self.service.transform('s', self.action)
        self.assertEqual(self.host.mutations, 1)
        self.assertIsNotNone(json.loads(self.state_path.read_text())['inflight'])
        self.assertEqual(self.service.transform('later', self.action)['status'], 'host_quarantined')

    def test_initial_journal_write_failure_is_not_an_expiry(self):
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=OSError(errno.EIO, 'Cannot journal')):
            with self.assertRaises(OSError) as caught:
                self.service.transform('s', self.action)
        self.assertNotIsInstance(caught.exception, RequestBudgetError)
        self.assertEqual(self.host.mutations, 0)

    def test_export_overrun_cannot_commit_initial_journal(self):
        self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        before = self.state_path.read_bytes()
        clock = Clock()
        original_save = self.service._save
        def slow_export_save(value, runtime):
            original_export = runtime.export_state
            def slow_export():
                exported = original_export()
                clock.expire()
                return exported
            with patch.object(runtime, 'export_state', slow_export):
                return original_save(value, runtime)
        with patch('human_eye_plugin.live_service.time', clock), patch.object(self.service, '_save', slow_export_save):
            with patch('human_eye_plugin.live_service._atomic_write') as writer:
                with self.assertRaises(RequestBudgetError) as caught:
                    self.service.transform('s', self.action)
        self.assert_refusal(caught, 'expired')
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'], 'before_atomic_state_write')
        writer.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_size_encoding_overrun_cannot_commit_initial_journal(self):
        clock = Clock()
        original_dumps = json.dumps
        def slow_encode(value, *args, **kwargs):
            encoded = original_dumps(value, *args, **kwargs)
            if isinstance(value, dict) and value.get('inflight') is not None and 'config_fingerprint' in value:
                clock.expire()
            return encoded
        with patch('human_eye_plugin.live_service.time', clock), patch('human_eye_plugin.live_service.json.dumps', slow_encode):
            with patch('human_eye_plugin.live_service._atomic_write') as writer:
                with self.assertRaises(RequestBudgetError) as caught:
                    self.service.transform('s', self.action)
        self.assert_refusal(caught, 'expired')
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'], 'before_atomic_state_write')
        writer.assert_not_called()
        self.assertFalse(self.state_path.exists())

    def test_capture_overrun_stops_before_geometry_or_state_write(self):
        clock = Clock()
        self.host.after_capture = clock.expire
        with patch('human_eye_plugin.live_service.time', clock):
            with self.assertRaises(RequestBudgetError) as caught:
                self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        self.assert_refusal(caught, 'expired')
        self.assertEqual(self.host.captures, 1)
        self.assertFalse(self.state_path.exists())
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'], 'after_host_capture')

    def test_expired_preparation_cannot_write_journal_or_mutate(self):
        clock = Clock()
        original = self.service._prepare
        def late_prepare(*args, **kwargs):
            result = original(*args, **kwargs)
            clock.expire()
            return result
        with patch('human_eye_plugin.live_service.time', clock), patch.object(self.service, '_prepare', late_prepare):
            with self.assertRaises(RequestBudgetError) as caught:
                self.service.transform('s', self.action)
        self.assert_refusal(caught, 'expired')
        self.assertFalse(self.state_path.exists())

    def test_submitted_operation_outlives_budget_and_is_read_back(self):
        clock = Clock()
        self.host.after_mutation = clock.expire
        with patch('human_eye_plugin.live_service.time', clock):
            result = self.service.transform('s', self.action)
        self.assertTrue(result['verified'], result)
        self.assertEqual(self.host.mutations, 1)
        self.assertIsNone(json.loads(self.state_path.read_text())['inflight'])

    def test_unknown_submitted_operation_retains_durable_quarantine(self):
        clock = Clock()
        self.host.after_mutation = clock.expire
        self.host.fail_mutation = True
        with patch('human_eye_plugin.live_service.time', clock):
            result = self.service.transform('s', self.action)
        self.assertFalse(result['verified'])
        self.assertEqual(self.host.mutations, 1)
        self.assertIsNotNone(json.loads(self.state_path.read_text())['inflight'])
        self.assertEqual(self.service.transform('new', self.action)['status'], 'host_quarantined')

    def test_state_IO_and_binding_errors_are_not_busy(self):
        self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        before = self.state_path.read_bytes()
        with patch('human_eye_plugin.live_service._read_object', side_effect=OSError(errno.EIO, 'I/O failure')):
            with self.assertRaises(OSError):
                self.service.status()
        state = json.loads(before)
        state['config_fingerprint'] = 'f'*64
        self.state_path.write_text(json.dumps(state))
        with self.assertRaises(StateBindingError):
            self.service.status()

    def test_noncontention_lock_IO_is_not_busy_or_retried(self):
        target = 'msvcrt.locking' if sys.platform == 'win32' else 'fcntl.flock'
        with patch.object(self.service, 'record_event', return_value=False), patch(target, side_effect=OSError(errno.EIO, 'device failed')) as operation:
            with self.assertRaises(OSError) as caught:
                self.service.status()
        self.assertNotIsInstance(caught.exception, RequestBudgetError)
        self.assertEqual(operation.call_count, 1)
        self.assertEqual(self.host.captures, 0)

    def test_mcp_and_hook_keep_structured_budget_refusal(self):
        service = self.make_service(request_budget_s=.04)
        worker, release = self.holder()
        server = LiveSpatialMCPServer(service)
        response = server.handle_jsonrpc_message(dict(jsonrpc='2.0', id=9, method='tools/call',
            params=dict(name='human_eye_connection_status', arguments={})))
        self.assertTrue(response['result']['isError'])
        body = json.loads(response['result']['content'][0]['text'])
        self.assertEqual(body['code'], 'live_request_busy')
        self.assertFalse(body['connector_state_write_attempted'])
        event = dict(hook_event_name='PreToolUse', tool_name='mcp__human_eye_live__human_eye_transform',
            session_id='test', tool_input=dict(action=self.action))
        output = route_live_hook(event, service)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        body = json.loads(output['hookSpecificOutput']['additionalContext'])
        self.assertEqual(body['code'], 'live_request_busy')
        self.assertEqual(self.host.captures, 0)
        self.assertEqual(self.host.mutations, 0)
        release.touch()
        worker.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
