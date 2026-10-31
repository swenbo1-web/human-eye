"""Exercise the live-addon transport using isolated loopback TCP fixtures."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import json
import math
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_mcp_host import (
    BlenderMCPHost, HostRemoteError, HostTransportError, RPC_PREFIX,
)


ROOT = Path(__file__).resolve().parents[1]


def _request_from_code(command):
    code = command["params"]["code"]
    prefix = "_request = _json.loads("
    line = next(line for line in code.splitlines() if line.startswith(prefix))
    return json.loads(ast.literal_eval(line[len(prefix):-1]))


def _reply(request, result=None, error=None, **fields):
    envelope = {"protocol_version": "1.0", "id": request["id"]}
    if error is not None:
        envelope["error"] = error
    else:
        envelope["result"] = result if result is not None else {"revision": "r1"}
    envelope.update(fields)
    return {"status": "success", "result": {"executed": True,
            "result": RPC_PREFIX + json.dumps(envelope, separators=(",", ":")) + "\n"}}


@contextmanager
def _server(handler, *, connections=1):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(connections)
    server.settimeout(3)
    requests, errors = [], []

    def run():
        try:
            for _ in range(connections):
                client, _ = server.accept()
                with client:
                    client.settimeout(2)
                    received = bytearray()
                    while True:
                        chunk = client.recv(65536)
                        if not chunk:
                            raise ValueError("test client disconnected without request")
                        received.extend(chunk)
                        try:
                            command = json.loads(received)
                        except json.JSONDecodeError:
                            continue
                        break
                    request = _request_from_code(command)
                    requests.append((command, request))
                    response = handler(request)
                    if callable(response):
                        response(client)
                    elif isinstance(response, bytes):
                        client.sendall(response)
                    else:
                        client.sendall(json.dumps(response).encode())
        except BaseException as exc:
            errors.append(exc)
        finally:
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], requests
    finally:
        thread.join(timeout=4)
        server.close()
        if thread.is_alive():
            raise AssertionError("test TCP server did not stop")
        if errors:
            raise errors[0]


class BlenderMCPHostTests(unittest.TestCase):
    def test_capture_and_apply_fixed_protocol_with_fresh_nonce(self):
        with _server(lambda request: _reply(request, {"echo": request["params"]}), connections=2) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            action = {"focal_id": "cube\";raise RuntimeError('not code')", "translation": [0.1, 0, 0]}
            with host.transaction():
                self.assertEqual(host.capture_scene(), {"echo": {}})
                result = host.apply_transform(action, "r1", "fingerprint")
            self.assertEqual(result["echo"], {"action": action, "expected_revision": "r1",
                                             "expected_fingerprint": "fingerprint"})
            self.assertNotEqual(requests[0][1]["id"], requests[1][1]["id"])
            self.assertEqual(requests[0][0]["type"], "execute_code")
            for command, _ in requests:
                ast.parse(command["params"]["code"])
                self.assertIn(str(ROOT / "human_eye_plugin" / "blender_host.py"),
                              ast.literal_eval(next(line for line in command["params"]["code"].splitlines()
                                  if "_iu.spec_from_file_location" in line).split(", ", 1)[1][:-1]))
            self.assertTrue(host.is_alive)
            host.close()
            host.close()
            self.assertFalse(host.is_alive)
            with self.assertRaises(HostTransportError):
                host.capture_scene()

    def test_fragmented_utf8_json_is_read_before_eof(self):
        def response(request):
            outer = _reply(request, {"name": "三维场景"})
            envelope = json.loads(outer["result"]["result"][len(RPC_PREFIX):])
            outer["result"]["result"] = RPC_PREFIX + json.dumps(envelope, ensure_ascii=False) + "\n"
            payload = json.dumps(outer, ensure_ascii=False).encode()
            def send(client):
                for byte in payload:
                    client.sendall(bytes([byte]))
            return send
        with _server(response) as (port, _):
            self.assertEqual(BlenderMCPHost(ROOT, port=port).capture_scene()["name"], "三维场景")

    def test_definite_capture_error_does_not_invalidate_host(self):
        error = {"type": "BlenderHostError", "message": "unsupported geometry", "mutation_uncertain": False}
        with _server(lambda request: _reply(request, error=error), connections=2) as (port, _):
            host = BlenderMCPHost(ROOT, port=port)
            for _ in range(2):
                with self.assertRaisesRegex(HostRemoteError, "unsupported geometry"):
                    host.capture_scene()
                self.assertTrue(host.is_alive)

    def test_apply_error_invalidates_without_retry(self):
        error = {"type": "BlenderHostError", "message": "revision changed", "mutation_uncertain": False}
        with _server(lambda request: _reply(request, error=error)) as (port, requests):
            host = BlenderMCPHost(ROOT, port=port)
            with self.assertRaisesRegex(HostTransportError, "mutation could not be verified"):
                host.apply_transform({"focal_id": "cube", "translation": [1, 0, 0]}, "r1")
            self.assertFalse(host.is_alive)
            with self.assertRaises(HostTransportError):
                host.capture_scene()
            self.assertEqual(len(requests), 1)

    def test_mismatched_nonce_protocol_or_ambiguous_data_fail_closed(self):
        cases = [
            lambda r: _reply(r, id="unsolicited"),
            lambda r: _reply(r, protocol_version="99"),
            lambda r: _reply(r, error={"message": "invalid error"}),
            lambda r: _reply(r, result=[]),
            lambda r: {"status": "error", "message": "addon error"},
            lambda r: {"status": "success", "result": {"executed": 1, "result": "text"}},
            lambda r: {"status": "success", "result": {"executed": True, "result": "banner\n" + RPC_PREFIX + "{}\n"}},
            lambda r: json.dumps(_reply(r, {"bad": math.nan})).encode(),
            lambda r: b'{"status":"success","status":"success","result":{}}',
            lambda r: json.dumps(_reply(r)).encode()[:-1],
            lambda r: json.dumps(_reply(r)).encode() + b'{}',
            lambda r: b'not JSON',
            lambda r: json.dumps(_reply(r)).encode().replace(b'{"status":', b'{"bad":1e999,"status":'),
        ]
        for handler in cases:
            with self.subTest(handler=cases.index(handler)):
                with _server(handler) as (port, _):
                    host = BlenderMCPHost(ROOT, port=port, timeout_s=0.5)
                    with self.assertRaises(HostTransportError):
                        host.capture_scene()
                    self.assertFalse(host.is_alive)

    def test_response_budget_and_timeout_fail_closed(self):
        with _server(lambda request: _reply(request, {"text": "x" * 1024})) as (port, _):
            host = BlenderMCPHost(ROOT, port=port)
            with patch("human_eye_plugin.blender_mcp_host._MAX_RESPONSE_BYTES", 256):
                with self.assertRaisesRegex(HostTransportError, "size limit"):
                    host.capture_scene()
        def delayed(request):
            def send(client):
                time.sleep(0.15)
            return send
        with _server(delayed) as (port, _):
            host = BlenderMCPHost(ROOT, port=port, timeout_s=0.05)
            with self.assertRaises(HostTransportError):
                host.capture_scene()
            self.assertFalse(host.is_alive)

    def test_only_loopback_bounded_explicit_source_is_allowed(self):
        for kwargs in ({"host": "example.com"}, {"host": "192.168.1.1"},
                       {"host": "0.0.0.0"}, {"port": True}, {"port": 65536},
                       {"timeout_s": True}, {"timeout_s": math.nan}, {"timeout_s": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BlenderMCPHost(ROOT, **kwargs)
        with self.assertRaises(ValueError):
            BlenderMCPHost(ROOT / "not-a-project")
        self.assertEqual(BlenderMCPHost(ROOT, host="localhost").host, "127.0.0.1")
        self.assertEqual(BlenderMCPHost(ROOT, host="::1").host, "::1")

    def test_bad_local_request_never_connects_or_invalidates(self):
        host = BlenderMCPHost(ROOT)
        with patch("human_eye_plugin.blender_mcp_host.socket.create_connection") as connection:
            for action, revision, fingerprint in (([], "r1", None), ({}, "", None),
                    ({}, "r1", ""), ({"translation": [math.nan, 0, 0]}, "r1", None),
                    ({"text": "x" * 5000}, "r1", None)):
                with self.subTest(action=type(action).__name__), self.assertRaises(ValueError):
                    host.apply_transform(action, revision, fingerprint)
            connection.assert_not_called()
        self.assertTrue(host.is_alive)


if __name__ == "__main__":
    unittest.main()
