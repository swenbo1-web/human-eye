"""Portable checks against the loopback pump and actual relay pipes."""

from contextlib import contextmanager
from pathlib import Path
from queue import Queue
import socket
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_fast.blender_llm_bridge import Bridge, start


RELAY = Path(__file__).resolve().parents[1] / "human_eye_llm_stdio.py"
NOTICE = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'


class _Entry:
    def __init__(self, response=None):
        self.response = response
        self.frames = []
        self.close_count = 0

    def handle_line(self, frame):
        self.frames.append(frame)
        if frame == NOTICE:
            return None
        if self.response is not None and frame == b"large":
            return self.response
        return b"reply " + frame + b"\n"

    def close(self):
        self.close_count += 1


class _ShortWriter:
    """Limit each write while keeping reads and all written bytes on real TCP."""

    def __init__(self, connection):
        self._connection = connection

    def send(self, data):
        return self._connection.send(data[:4096])

    def recv(self, size):
        return self._connection.recv(size)

    def close(self):
        self._connection.close()


def _read_exact(read, length):
    data = bytearray()
    while len(data) < length:
        chunk = read(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _available(connection, data):
    while True:
        try:
            chunk = connection.recv(65536)
        except BlockingIOError:
            return False
        if not chunk:
            return True
        data.extend(chunk)


class BridgeTransportTests(unittest.TestCase):
    def _until(self, bridge, condition, timeout=8):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            bridge.pump()
            if condition():
                return
            sleep(0.001)
        self.fail("Timed out waiting for the real loopback pump")

    def test_fragmented_utf8_coalesced_notification_and_peer_eof(self):
        entries = []

        def factory():
            entry = _Entry()
            entries.append(entry)
            return entry

        bridge = Bridge(factory)
        self.addCleanup(bridge.stop)
        frame = '{"jsonrpc":"2.0","id":1,"text":"前😀"}'.encode("utf-8")
        tail = b'{"jsonrpc":"2.0","id":2}'
        cut = frame.index("😀".encode("utf-8")) + 2
        with socket.create_connection(bridge.address, timeout=4) as client:
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.sendall(frame[:cut])
            self._until(bridge, lambda: len(bridge._input) == cut)
            self.assertEqual(entries[0].frames, [])
            self.assertFalse(bridge._connection.getblocking())
            self.assertEqual(bridge._connection.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY), 1)
            # The first remainder, a no-result notification and a second
            # complete request can arrive in a single TCP read.
            client.sendall(frame[cut:] + b"\n" + NOTICE + b"\n" + tail + b"\nunfinished")
            client.shutdown(socket.SHUT_WR)
            client.setblocking(False)
            output = bytearray()
            self._until(bridge, lambda: _available(client, output))
        self.assertEqual(output, b"reply " + frame + b"\nreply " + tail + b"\n")
        self.assertEqual(entries[0].frames, [frame, NOTICE, tail])
        self.assertEqual(entries[0].close_count, 1)
        self.assertIsNone(bridge._entry)

        with socket.create_connection(bridge.address, timeout=4):
            self._until(bridge, lambda: len(entries) == 2)
            bridge.stop()
            bridge.stop()
            self.assertIsNone(bridge.pump())
        self.assertEqual([entry.close_count for entry in entries], [1, 1])

    def test_partial_send_over_real_tcp_applies_request_backpressure(self):
        large = b"x" * (64 * 1024) + b"\n"
        entry = _Entry(large)
        bridge = Bridge(lambda: entry)
        self.addCleanup(bridge.stop)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(4)
            client.connect(bridge.address)
            self._until(bridge, lambda: bridge._connection is not None)
            # Socket buffer hints cannot guarantee a short send on loopback.
            bridge._connection = _ShortWriter(bridge._connection)
            client.sendall(b"large\nsecond\n")
            client.shutdown(socket.SHUT_WR)
            self._until(bridge, lambda: bool(entry.frames))
            self.assertTrue(bridge._response is large, "Expected the original response to remain pending")
            self.assertGreater(bridge._send_offset, 0)
            self.assertLess(bridge._send_offset, len(large))
            for _ in range(4):
                bridge.pump()
            self.assertEqual(entry.frames, [b"large"])

            client.setblocking(False)
            output = bytearray()
            self._until(bridge, lambda: _available(client, output), timeout=18)
        self.assertTrue(output == large + b"reply second\n", "TCP reply bytes differed")
        self.assertEqual(entry.frames, [b"large", b"second"])
        self.assertEqual(entry.close_count, 1)

    def test_start_and_stop_own_only_the_registered_timer(self):
        callbacks = set()

        def register(callback, *, first_interval):
            self.assertEqual(first_interval, 0.0)
            callbacks.add(callback)

        timers = SimpleNamespace(register=register, unregister=callbacks.remove,
                                 is_registered=callbacks.__contains__)
        fake_bpy = SimpleNamespace(app=SimpleNamespace(timers=timers))
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            bridge = start(_Entry, interval=0.007)
        self.addCleanup(bridge.stop)
        callback, = callbacks
        self.assertEqual(callback(), 0.007)
        bridge.stop()
        self.assertFalse(callbacks)
        self.assertIsNone(bridge.pump())


@contextmanager
def _relay_peer():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        process = subprocess.Popen(
            [sys.executable, "-B", str(RELAY), "--port", str(listener.getsockname()[1])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
        )
        try:
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(5)
                yield process, peer
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


class RelayTransportTests(unittest.TestCase):
    def test_real_pipes_are_full_duplex_and_stdin_eof_drains_output(self):
        with _relay_peer() as (process, peer):
            process.stdin.write(NOTICE + b"\n")
            self.assertEqual(_read_exact(peer.recv, len(NOTICE) + 1), NOTICE + b"\n")
            # Output must flow while stdin is idle and still open.
            outbound = "服务器😀".encode("utf-8") + b"\x00\xff\r\n"
            received = Queue()
            Thread(target=lambda: received.put(_read_exact(process.stdout.read, len(outbound))),
                   daemon=True).start()
            peer.sendall(outbound[:3])
            peer.sendall(outbound[3:])
            self.assertEqual(received.get(timeout=5), outbound)

            inbound = "客户端😀".encode("utf-8") + b"\x00\xff\r\n"
            process.stdin.write(inbound[:5])
            process.stdin.write(inbound[5:])
            process.stdin.close()
            self.assertEqual(_read_exact(peer.recv, len(inbound)), inbound)
            self.assertEqual(peer.recv(1), b"")
            trailing = b"after half-close\x00\xff"
            peer.sendall(trailing)
            peer.shutdown(socket.SHUT_WR)
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertEqual(process.stdout.read(), trailing)
            self.assertEqual(process.stderr.read(), b"")

    def test_peer_eof_exits_even_with_host_stdin_still_open(self):
        with _relay_peer() as (process, peer):
            peer.sendall(b"peer finished\x00")
            peer.shutdown(socket.SHUT_WR)
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertFalse(process.stdin.closed)
            self.assertEqual(process.stdout.read(), b"peer finished\x00")
            self.assertEqual(process.stderr.read(), b"")


if __name__ == "__main__":
    unittest.main()
