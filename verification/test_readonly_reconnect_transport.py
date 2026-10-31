"""Read-only reconnect preserves the ambiguity boundary and legacy wire format."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from human_eye_plugin.blender_mcp_host import (
    BlenderMCPHost, HostRemoteError, HostTransportError, _OBSERVATION_UNPROBED,
)
from verification.test_blender_mcp_host import _reply, _server
from verification.test_readonly_product_transport import capability


ROOT = Path(__file__).resolve().parents[1]
EPOCH_A, EPOCH_B = 'a' * 64, 'b' * 64


def capture(epoch=EPOCH_A):
    return {'revision': 'same-geometry-revision',
            'host_identity': {'document_epoch': epoch}}


class ReadonlyReconnectTransportTests(unittest.TestCase):
    def test_epoch_change_refreshes_once_and_warm_epoch_has_no_extra_rpc(self):
        epochs = iter([EPOCH_A, EPOCH_A, EPOCH_B, EPOCH_B])
        pids = iter([321, 654])
        def respond(req):
            value = (capability(next(pids)) if req['command'] == 'native_observation_capabilities'
                     else capture(next(epochs)))
            return _reply(req, value)
        with _server(respond, connections=6) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            for expected_pid in (321, 321, 654, 654):
                with host.observation_transaction():
                    host.capture_scene()
                    self.assertEqual(host.native_observation_capabilities()['process_id'], expected_pid)
            self.assertEqual([r[1]['command'] for r in requests], [
                'capture', 'native_observation_capabilities', 'capture',
                'capture', 'native_observation_capabilities', 'capture'])
            self.assertTrue(host.is_alive)

    def test_epoch_invalidates_a_capability_cached_before_first_scoped_capture(self):
        pids = iter([321, 654])
        def respond(req):
            return _reply(req, capability(next(pids)) if req['command'] == 'native_observation_capabilities'
                          else capture())
        with _server(respond, connections=3) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            self.assertEqual(host.native_observation_capabilities()['process_id'], 321)
            with host.observation_transaction():
                host.capture_scene()
                self.assertEqual(host.native_observation_capabilities()['process_id'], 654)
            self.assertEqual(len(requests), 3)

    def test_valid_epoch_change_invalidates_cached_unsupported(self):
        epochs = iter([EPOCH_A, EPOCH_A, EPOCH_B])
        capabilities = iter([{'supported': False}, capability(654)])
        def respond(req):
            return _reply(req, next(capabilities) if req['command'] == 'native_observation_capabilities'
                          else capture(next(epochs)))
        with _server(respond, connections=5) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            for _ in range(2):
                with host.observation_transaction():
                    host.capture_scene()
                    self.assertIsNone(host.native_observation_capabilities())
            with host.observation_transaction():
                host.capture_scene()
                self.assertEqual(host.native_observation_capabilities()['process_id'], 654)
            self.assertEqual([r[1]['command'] for r in requests], [
                'capture', 'native_observation_capabilities', 'capture',
                'capture', 'native_observation_capabilities'])

    def test_legacy_identity_absence_reprobes_and_does_not_pin_old_unsupported(self):
        capabilities = iter([{'supported': False}, capability(654)])
        def respond(req):
            return _reply(req, next(capabilities) if req['command'] == 'native_observation_capabilities'
                          else {'revision': 'legacy'})
        with _server(respond, connections=4) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            with host.observation_transaction():
                host.capture_scene()
                self.assertIsNone(host.native_observation_capabilities())
            with host.observation_transaction():
                host.capture_scene()
                self.assertEqual(host.native_observation_capabilities()['process_id'], 654)
            self.assertEqual([r[1]['command'] for r in requests],
                             ['capture', 'native_observation_capabilities',
                              'capture', 'native_observation_capabilities'])

    def test_unkeyed_legacy_identity_only_invalidates_cache_without_new_capture_admission_rule(self):
        for identity in (None, {}, {'document_epoch': 'legacy-text'},
                         {'document_epoch': 'A' * 64}, {'document_epoch': True}):
            with self.subTest(identity=identity):
                result = {'revision': 'legacy', 'host_identity': identity}
                with _server(lambda req: _reply(req, result)) as (port, requests):
                    host = BlenderMCPHost(ROOT, port=port)
                    host._native_observation_caps = None
                    with host.observation_transaction():
                        self.assertEqual(host.capture_scene(), result)
                    self.assertIs(host._native_observation_caps, _OBSERVATION_UNPROBED)
                    self.assertTrue(host.is_alive)
                    self.assertEqual(len(requests), 1)

    def test_capture_evidence_uses_its_nested_scene_epoch(self):
        def respond(req):
            return _reply(req, {'capture': capture()} if req['command'] == 'capture_evidence'
                          else capability())
        with _server(respond, connections=3) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            with host.observation_transaction():
                host.capture_evidence()
                host.native_observation_capabilities()
                host.capture_evidence()
                host.native_observation_capabilities()
            self.assertEqual(len(requests), 3)

    def test_preconnect_failure_fails_current_call_without_retry_then_next_scope_recovers(self):
        for failure in (ConnectionRefusedError('not listening'), TimeoutError('connect timeout')):
            with self.subTest(failure=type(failure).__name__):
                with _server(lambda req: _reply(req, capture() if req['command'] == 'capture'
                                               else capability(654)), connections=2) as (port, requests):
                    host = BlenderMCPHost(ROOT, port=port)
                    host._native_observation_caps = capability(321)
                    original_connect = host._connect
                    attempts = []
                    def connect(deadline):
                        attempts.append(deadline)
                        if len(attempts) == 1:
                            raise failure
                        return original_connect(deadline)
                    with patch.object(host, '_connect', side_effect=connect):
                        with host.observation_transaction():
                            with self.assertRaisesRegex(HostTransportError, 'before read-only request was sent'):
                                host.capture_scene()
                        self.assertTrue(host.is_alive)
                        self.assertEqual(len(attempts), 1)
                        self.assertEqual(requests, [])
                        self.assertIs(host._native_observation_caps, _OBSERVATION_UNPROBED)
                        with host.observation_transaction():
                            host.capture_scene()
                            self.assertEqual(host.native_observation_capabilities()['process_id'], 654)
                    self.assertEqual(len(attempts), 3)
                    self.assertEqual([r[1]['command'] for r in requests],
                                     ['capture', 'native_observation_capabilities'])

    def test_scoped_mutations_and_unknown_commands_are_rejected_before_connect(self):
        host = BlenderMCPHost(ROOT)
        operations = [
            lambda: host.apply_transform({'focal_id': 'part', 'translation': [0, 0, .001]}, 'rev'),
            lambda: host.begin_motion_goal('goal', 'part', 'base'),
            lambda: host.motion_goal_status('goal'),
            lambda: host.end_motion_goal('goal'),
            lambda: host._request('unrecognized', {}),
        ]
        with patch.object(host, '_connect') as connect:
            with host.observation_transaction():
                for operation in operations:
                    with self.assertRaisesRegex(ValueError, 'Only fixed read-only commands'):
                        operation()
            connect.assert_not_called()
        self.assertTrue(host.is_alive)

    def test_preconnect_capability_failure_is_not_cached_as_unsupported(self):
        with _server(lambda req: _reply(req, capability()), connections=1) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            with patch.object(host, '_connect', side_effect=ConnectionRefusedError('offline')) as connect:
                with host.observation_transaction():
                    with self.assertRaises(HostTransportError):
                        host.native_observation_capabilities()
                self.assertEqual(connect.call_count, 1)
                self.assertEqual(requests, [])
            self.assertIs(host._native_observation_caps, _OBSERVATION_UNPROBED)
            self.assertTrue(host.is_alive)
            with host.observation_transaction():
                self.assertEqual(host.native_observation_capabilities()['process_id'], 321)
            self.assertEqual(len(requests), 1)

    def test_nested_scope_unwinds_after_local_error_and_legacy_write_remains_available(self):
        host = BlenderMCPHost(ROOT)
        with self.assertRaises(ValueError):
            with host.observation_transaction():
                with host.observation_transaction():
                    host.end_motion_goal('goal')
        with patch.object(host, '_exchange', side_effect=ConnectionRefusedError('offline')) as exchange:
            with self.assertRaisesRegex(HostTransportError, 'outcome unknown'):
                host.end_motion_goal('goal')
            exchange.assert_called_once()
        self.assertFalse(host.is_alive)

    def test_direct_legacy_capture_and_write_preconnect_failures_still_poison(self):
        for operation in ('capture', 'apply'):
            with self.subTest(operation=operation):
                host = BlenderMCPHost(ROOT)
                with patch.object(host, '_connect', side_effect=ConnectionRefusedError('offline')) as connect:
                    with self.assertRaisesRegex(HostTransportError, 'outcome unknown'):
                        if operation == 'capture':
                            host.capture_scene()
                        else:
                            host.apply_transform({'focal_id': 'part', 'translation': [0, 0, .001]}, 'rev')
                    self.assertFalse(host.is_alive)
                    with host.observation_transaction():
                        with self.assertRaises(HostTransportError):
                            host.capture_scene()
                    self.assertEqual(connect.call_count, 1)

    def test_socket_returned_then_send_or_setup_failure_poison_and_never_retry(self):
        for stage in ('settimeout', 'sendall'):
            with self.subTest(stage=stage):
                host = BlenderMCPHost(ROOT)
                connection = MagicMock()
                connection.__enter__.return_value = connection
                getattr(connection, stage).side_effect = OSError('after connect')
                with patch.object(host, '_connect', return_value=connection) as connect:
                    with host.observation_transaction():
                        with self.assertRaises(HostTransportError):
                            host.capture_scene()
                    self.assertFalse(host.is_alive)
                    with host.observation_transaction():
                        with self.assertRaises(HostTransportError):
                            host.capture_scene()
                    self.assertEqual(connect.call_count, 1)

    def test_bad_responses_poison_permanently_even_inside_readonly_scope(self):
        cases = [
            lambda req: _reply(req, capture(), id='wrong-nonce'),
            lambda req: _reply(req, capture(), protocol_version='bad'),
            lambda req: b'{bad-json',
        ]
        for respond in cases:
            with self.subTest(response=respond):
                with _server(respond) as (port, requests):
                    host = BlenderMCPHost(ROOT, port=port, timeout_s=.5)
                    with host.observation_transaction():
                        with self.assertRaises(HostTransportError):
                            host.capture_scene()
                    self.assertFalse(host.is_alive)
                    with patch.object(host, '_connect') as connect:
                        with host.observation_transaction():
                            with self.assertRaises(HostTransportError):
                                host.capture_scene()
                        connect.assert_not_called()
                    self.assertEqual(len(requests), 1)

    def test_closed_scope_never_reopens_or_connects(self):
        host = BlenderMCPHost(ROOT)
        host.close()
        with patch.object(host, '_connect') as connect:
            with host.observation_transaction():
                with self.assertRaises(HostTransportError):
                    host.capture_scene()
            connect.assert_not_called()
        self.assertFalse(host.is_alive)

    def test_definite_readonly_remote_error_preserves_existing_behavior(self):
        error = {'type': 'BlenderHostError', 'message': 'render refused', 'mutation_uncertain': False}
        with _server(lambda req: _reply(req, error=error), connections=2) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            for _ in range(2):
                with host.observation_transaction():
                    with self.assertRaisesRegex(HostRemoteError, 'render refused'):
                        host.capture_scene()
                self.assertTrue(host.is_alive)
            self.assertEqual(len(requests), 2)


if __name__ == '__main__':
    unittest.main()
