"""Connection deadline, readiness and disposal boundaries without Blender IO."""
from __future__ import annotations

import errno
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_mcp_host as mod


PROJECT_ROOT = Path(mod.__file__).resolve().parents[1]


class ConnectionStub:
    """A socket ownership probe, not a transport response simulator."""

    def __init__(self, result=0, error=0):
        self.result = result
        self.error = error
        self.connect_addresses = []
        self.blocking_values = []
        self.timeouts = []
        self.option_reads = []
        self.close_count = 0
        self.sent = []

    def setblocking(self, value):
        self.blocking_values.append(value)

    def connect_ex(self, address):
        self.connect_addresses.append(address)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def getsockopt(self, level, option):
        self.option_reads.append((level, option))
        if isinstance(self.error, BaseException):
            raise self.error
        return self.error

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, value):
        self.sent.append(value)

    def close(self):
        self.close_count += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class LoopbackConnectTests(unittest.TestCase):
    def host(self, **kwargs):
        return mod.BlenderMCPHost(PROJECT_ROOT, **kwargs)

    def invoke(self, connection, *, host=None, now=100.0, ready=None):
        target = host or self.host()
        if ready is None:
            ready = ([], [connection], [])
        with patch.object(mod.socket, "socket", return_value=connection) as created, \
                patch.object(mod.time, "monotonic", return_value=now), \
                patch.object(mod.select, "select", return_value=ready) as selected:
            actual = target._connect(101.0)
        return actual, created, selected

    def test_immediate_success_returns_one_live_nonblocking_connection(self):
        connection = ConnectionStub()
        actual, created, selected = self.invoke(connection)
        self.assertIs(actual, connection)
        created.assert_called_once()
        self.assertEqual(connection.blocking_values, [False])
        self.assertEqual(connection.connect_addresses, [("127.0.0.1", 9876)])
        self.assertEqual(connection.close_count, 0)
        self.assertTrue(connection.timeouts)
        self.assertTrue(all(0 < value <= 1 for value in connection.timeouts))
        selected.assert_not_called()
        connection.close()

    def test_pending_success_requires_writable_and_zero_socket_error(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        actual, created, selected = self.invoke(connection)
        self.assertIs(actual, connection)
        selected.assert_called_once()
        readable, writable, exceptional, timeout = selected.call_args.args
        self.assertEqual(readable, [])
        self.assertEqual(writable, [connection])
        self.assertEqual(exceptional, [connection])
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 1)
        self.assertIn((socket.SOL_SOCKET, socket.SO_ERROR), connection.option_reads)
        self.assertEqual(connection.close_count, 0)
        connection.close()

    def test_platform_pending_codes_do_not_trigger_another_connect(self):
        for code in sorted({errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, 10035, 10036, 10037}):
            with self.subTest(code=code):
                connection = ConnectionStub(code)
                actual, created, selected = self.invoke(connection)
                self.assertIs(actual, connection)
                self.assertEqual(len(connection.connect_addresses), 1)
                created.assert_called_once()
                selected.assert_called_once()
                connection.close()

    def test_immediate_refusal_disposes_socket_without_select_or_retry(self):
        connection = ConnectionStub(errno.ECONNREFUSED)
        with patch.object(mod.socket, "socket", return_value=connection) as created, \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select") as selected:
            with self.assertRaises(OSError):
                self.host()._connect(101)
        created.assert_called_once()
        selected.assert_not_called()
        self.assertEqual(len(connection.connect_addresses), 1)
        self.assertEqual(connection.close_count, 1)
        self.assertEqual(connection.sent, [])

    def test_select_timeout_disposes_socket_without_second_attempt(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        with patch.object(mod.socket, "socket", return_value=connection) as created, \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [], [])) as selected:
            with self.assertRaises(TimeoutError):
                self.host()._connect(101)
        selected.assert_called_once()
        created.assert_called_once()
        self.assertEqual(connection.close_count, 1)
        self.assertEqual(connection.sent, [])

    def test_writable_with_socket_error_is_not_success(self):
        connection = ConnectionStub(errno.EINPROGRESS, errno.ECONNREFUSED)
        with patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [connection], [])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_exceptional_completion_reads_error_and_refuses(self):
        connection = ConnectionStub(errno.EINPROGRESS, errno.ECONNRESET)
        with patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [], [connection])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertIn((socket.SOL_SOCKET, socket.SO_ERROR), connection.option_reads)
        self.assertEqual(connection.close_count, 1)

    def test_exceptional_only_zero_error_still_is_not_writable_success(self):
        connection = ConnectionStub(errno.EINPROGRESS, 0)
        with patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [], [connection])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_writable_and_exceptional_requires_socket_error_check(self):
        connection = ConnectionStub(errno.EINPROGRESS, errno.ECONNREFUSED)
        with patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [connection], [connection])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertIn((socket.SOL_SOCKET, socket.SO_ERROR), connection.option_reads)
        self.assertEqual(connection.close_count, 1)

    def test_writable_and_exceptional_zero_error_is_still_refused(self):
        connection = ConnectionStub(errno.EINPROGRESS, 0)
        with patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.select, "select", return_value=([], [connection], [connection])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertIn((socket.SOL_SOCKET, socket.SO_ERROR), connection.option_reads)
        self.assertEqual(connection.close_count, 1)

    def test_expired_deadline_does_not_allocate_socket(self):
        with patch.object(mod.time, "monotonic", return_value=101), \
                patch.object(mod.socket, "socket") as created, \
                patch.object(mod.select, "select") as selected:
            with self.assertRaises(TimeoutError):
                self.host()._connect(101)
        created.assert_not_called()
        selected.assert_not_called()

    def test_deadline_exhausted_during_connect_does_not_poll_or_return_socket(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        clock = [100.0]
        original_connect = connection.connect_ex
        def connect(address):
            value = original_connect(address)
            clock[0] = 101.1
            return value
        connection.connect_ex = connect
        with patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select") as selected:
            with self.assertRaises(TimeoutError):
                self.host()._connect(101)
        selected.assert_not_called()
        self.assertEqual(connection.close_count, 1)

    def test_immediate_success_still_checks_elapsed_connection_budget(self):
        connection = ConnectionStub(0)
        clock = [100.0]
        def connect(address):
            connection.connect_addresses.append(address)
            clock[0] = 101.1
            return 0
        connection.connect_ex = connect
        with patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select") as selected:
            with self.assertRaises(TimeoutError):
                self.host()._connect(101)
        selected.assert_not_called()
        self.assertEqual(connection.close_count, 1)

    def test_deadline_exhausted_during_readiness_does_not_return_socket(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        clock = [100.0]
        def select(*args):
            clock[0] = 101.1
            return [], [connection], []
        with patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select", side_effect=select):
            with self.assertRaises(TimeoutError):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_success_sets_only_remaining_budget_not_new_full_timeout(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        clock = [100.0]
        def select(*args):
            clock[0] = 100.75
            return [], [connection], []
        with patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select", side_effect=select):
            actual = self.host(timeout_s=30)._connect(101)
        self.assertIs(actual, connection)
        self.assertAlmostEqual(connection.timeouts[-1], 0.25)
        connection.close()

    def test_connect_base_exception_closes_owned_socket(self):
        connection = ConnectionStub(KeyboardInterrupt())
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", return_value=connection):
            with self.assertRaises(KeyboardInterrupt):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_select_base_exception_closes_owned_socket(self):
        connection = ConnectionStub(errno.EINPROGRESS)
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_error_query_exception_closes_owned_socket(self):
        connection = ConnectionStub(errno.EINPROGRESS, OSError("socket error query failed"))
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", return_value=connection), \
                patch.object(mod.select, "select", return_value=([], [connection], [])):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_final_settimeout_exception_closes_owned_socket(self):
        connection = ConnectionStub()
        def fail(value):
            raise OSError("settimeout failed")
        connection.settimeout = fail
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", return_value=connection):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertEqual(connection.close_count, 1)

    def test_setblocking_exception_closes_owned_socket(self):
        connection = ConnectionStub()
        def fail(value):
            raise OSError("setblocking failed")
        connection.setblocking = fail
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", return_value=connection):
            with self.assertRaises(OSError):
                self.host()._connect(101)
        self.assertEqual(connection.connect_addresses, [])
        self.assertEqual(connection.close_count, 1)

    def test_socket_initialization_exception_does_not_retry(self):
        with patch.object(mod.time, "monotonic", return_value=100), \
                patch.object(mod.socket, "socket", side_effect=OSError("allocation failed")) as created:
            with self.assertRaises(OSError):
                self.host()._connect(101)
        created.assert_called_once()

    def test_ipv4_uses_ipv4_socket(self):
        connection = ConnectionStub()
        actual, created, selected = self.invoke(connection)
        self.assertEqual(created.call_args.args[0], socket.AF_INET)
        self.assertEqual(connection.connect_addresses[0], ("127.0.0.1", 9876))
        connection.close()

    def test_ipv6_loopback_uses_ipv6_socket(self):
        connection = ConnectionStub()
        actual, created, selected = self.invoke(connection, host=self.host(host="::1", port=4567))
        self.assertEqual(created.call_args.args[0], socket.AF_INET6)
        address = connection.connect_addresses[0]
        self.assertEqual(address[:2], ("::1", 4567))
        connection.close()

    def test_ipv6_scoped_loopback_keeps_scope(self):
        connection = ConnectionStub()
        actual, created, selected = self.invoke(connection, host=self.host(host="::1%1", port=4567))
        self.assertEqual(created.call_args.args[0], socket.AF_INET6)
        address = connection.connect_addresses[0]
        self.assertTrue((address[0] == "::1%1") or (address[0] == "::1" and len(address) >= 4 and address[3] == 1))
        self.assertEqual(address[1], 4567)
        connection.close()

    def test_ipv6_interface_name_resolves_to_scope_id(self):
        connection = ConnectionStub()
        with patch.object(mod.socket, "if_nametoindex", return_value=7) as resolve:
            actual, created, selected = self.invoke(connection, host=self.host(host="::1%local-interface"))
        resolve.assert_called_once_with("local-interface")
        self.assertEqual(connection.connect_addresses, [("::1", 9876, 0, 7)])
        connection.close()

    def test_ipv6_out_of_range_scope_never_allocates_socket(self):
        for host in ["::1%4294967296", "::1%local-interface"]:
            with self.subTest(host=host), \
                    patch.object(mod.socket, "if_nametoindex", return_value=-1), \
                    patch.object(mod.socket, "socket") as created, \
                    patch.object(mod.time, "monotonic", return_value=100):
                with self.assertRaises(ValueError):
                    self.host(host=host)._connect(101)
            created.assert_not_called()

    def test_ipv6_unknown_interface_never_allocates_socket(self):
        with patch.object(mod.socket, "if_nametoindex", side_effect=OSError("unknown interface")), \
                patch.object(mod.socket, "socket") as created, \
                patch.object(mod.time, "monotonic", return_value=100):
            with self.assertRaises(OSError):
                self.host(host="::1%missing-interface")._connect(101)
        created.assert_not_called()

    def test_localhost_alias_is_resolved_by_constructor_before_connection(self):
        connection = ConnectionStub()
        actual, created, selected = self.invoke(connection, host=self.host(host="localhost"))
        self.assertEqual(created.call_args.args[0], socket.AF_INET)
        self.assertEqual(connection.connect_addresses[0][0], "127.0.0.1")
        connection.close()

    def test_capture_connection_failure_poisons_instance_and_is_never_retried(self):
        host = self.host()
        connection = ConnectionStub(errno.ECONNREFUSED)
        with patch.object(mod.socket, "socket", return_value=connection) as created:
            with self.assertRaises(mod.HostTransportError):
                host.capture_scene()
            self.assertFalse(host.is_alive)
            with self.assertRaises(mod.HostTransportError):
                host.capture_scene()
        created.assert_called_once()
        self.assertEqual(len(connection.connect_addresses), 1)
        self.assertEqual(connection.close_count, 1)
        self.assertEqual(connection.sent, [])

    def test_exchange_checks_deadline_again_before_any_send(self):
        host = self.host(timeout_s=1)
        connection = ConnectionStub()
        clock = [100.0]
        def connect(deadline):
            self.assertAlmostEqual(deadline, 101)
            clock[0] = 101.1
            return connection
        with patch.object(mod.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(host, "_connect", side_effect=connect):
            with self.assertRaises(TimeoutError):
                host._exchange(b"frozen read request")
        self.assertEqual(connection.sent, [])
        self.assertEqual(connection.close_count, 1)


class LoopbackConnectRealSocketTests(unittest.TestCase):
    def test_real_ipv4_connect_to_owned_listening_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(1)
            host = mod.BlenderMCPHost(PROJECT_ROOT, port=listener.getsockname()[1])
            with host._connect(time.monotonic() + 1) as connection:
                accepted, _ = listener.accept()
                with accepted:
                    self.assertEqual(connection.getpeername()[1], listener.getsockname()[1])
                    self.assertGreater(connection.gettimeout(), 0)
                    self.assertLessEqual(connection.gettimeout(), 1)

    def test_real_ipv6_connect_to_owned_listening_socket(self):
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("::1", 0))
            except OSError as error:
                self.skipTest("Local IPv6 listener unavailable: " + str(error))
            listener.listen(1)
            listener.settimeout(1)
            host = mod.BlenderMCPHost(PROJECT_ROOT, host="::1", port=listener.getsockname()[1])
            with host._connect(time.monotonic() + 1) as connection:
                accepted, _ = listener.accept()
                with accepted:
                    self.assertEqual(connection.getpeername()[1], listener.getsockname()[1])

    def test_real_nonlistening_peer_never_returns_a_successful_connection(self):
        # Keep the port bound so another process cannot acquire a released port
        # between discovery and the connection attempt. Never execute payloads.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
            reserved.bind(("127.0.0.1", 0))
            host = mod.BlenderMCPHost(PROJECT_ROOT, port=reserved.getsockname()[1])
            with self.assertRaises(OSError) as caught:
                host._connect(time.monotonic() + 0.25)
        # A bound-but-not-listening Windows endpoint can leave refusal pending
        # until this short application deadline wins. Both are closed failures;
        # do not lengthen the deadline merely to force an errno observation.
        self.assertTrue(isinstance(caught.exception, TimeoutError)
                        or caught.exception.errno in {errno.ECONNREFUSED, 10061})

    def test_real_connected_peer_without_response_exhausts_request_budget(self):
        release = threading.Event()
        received = []
        errors = []
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(1)
            def peer():
                try:
                    accepted, _ = listener.accept()
                    with accepted:
                        accepted.settimeout(1)
                        received.append(accepted.recv(32768))
                        release.wait(timeout=1)
                except BaseException as exc:
                    errors.append(exc)
            thread = threading.Thread(target=peer, daemon=True)
            thread.start()
            host = mod.BlenderMCPHost(PROJECT_ROOT, port=listener.getsockname()[1], timeout_s=0.05)
            try:
                with self.assertRaises(mod.HostTransportError):
                    host.capture_scene()
                self.assertFalse(host.is_alive)
                with self.assertRaises(mod.HostTransportError):
                    host.capture_scene()
            finally:
                release.set()
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(received), 1)
            self.assertTrue(received[0])


if __name__ == "__main__":
    unittest.main()
