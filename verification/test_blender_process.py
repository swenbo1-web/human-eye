"""Exercise the process transport with real, isolated Python subprocesses."""
from __future__ import annotations

import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_process import BlenderProcessHost, HostRemoteError, HostTransportError


FAKE_WORKER = r'''
import json
import os
import sys
import time
mode = sys.argv[1]
def emit(request_id, result):
    print('HUMAN_EYE_RPC:' + json.dumps({'id': request_id, 'result': result}), flush=True)
print('Blender startup banner', flush=True)
for line in sys.stdin:
    request = json.loads(line)
    ident, command = request['id'], request['command']
    if command == 'capabilities':
        emit(ident, {'protocol_version': '9' if mode == 'version' else '1.0', 'blender_version': 'fake-test'})
    elif command == 'shutdown':
        emit(ident, {'closed': True})
        break
    elif mode == 'timeout':
        time.sleep(10)
    elif mode == 'crash':
        os._exit(3)
    elif mode == 'mismatch':
        emit(ident + 1, {})
    elif mode == 'boolean_id':
        emit(True, {})
    elif mode == 'nonfinite':
        print('HUMAN_EYE_RPC:{"id":' + str(ident) + ',"result":{"value":1e999}}', flush=True)
    elif mode == 'invalid':
        print('HUMAN_EYE_RPC:not-json', flush=True)
    elif mode == 'error' and command == 'capture':
        print('HUMAN_EYE_RPC:' + json.dumps({'id': ident, 'error': {'type':'ValueError', 'message':'unsupported mesh'}}), flush=True)
    elif mode == 'mutation_error' and command == 'apply':
        print('HUMAN_EYE_RPC:' + json.dumps({'id': ident, 'error': {'type':'ValueError', 'message':'assignment failed', 'mutation_uncertain':True}}), flush=True)
    else:
        if mode == 'chatter':
            for index in range(150):
                print('noise ' + str(index), flush=True)
                print('stderr noise ' + str(index), file=sys.stderr, flush=True)
        emit(ident, {'revision': 'r1', 'unit': 'm', 'coordinate_frame': 'world', 'meshes': [], 'echo': request['params']})
'''


class BlenderProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.blend = self.base / "scene with spaces.blend"
        self.blend.write_bytes(b"fake subprocess fixture only")
        self.fake_worker = self.base / "fake_worker.py"
        self.fake_worker.write_text(FAKE_WORKER, encoding="utf-8")
        self.original_popen = subprocess.Popen
        self.children = []
        self.commands = []

    def make_host(self, mode="normal", **kwargs):
        def launch(command, **popen_kwargs):
            self.commands.append((command, popen_kwargs.copy()))
            child = self.original_popen([sys.executable, str(self.fake_worker), mode], **popen_kwargs)
            self.children.append(child)
            return child

        with patch("human_eye_plugin.blender_process.subprocess.Popen", side_effect=launch):
            host = BlenderProcessHost(sys.executable, self.blend, startup_timeout=3.0, **kwargs)
        self.addCleanup(host.close)
        return host

    def test_capture_and_apply_use_explicit_file_and_typed_protocol(self):
        host = self.make_host()
        with host.transaction():
            self.assertEqual(host.capture_scene()["revision"], "r1")
            action = {"focal_id": "cube", "translation": [0.1, 0, 0]}
            result = host.apply_transform(action, "r1", "fingerprint")
        self.assertEqual(result["echo"], {"action": action, "expected_revision": "r1", "expected_fingerprint": "fingerprint"})
        command, kwargs = self.commands[0]
        self.assertIn(str(self.blend.resolve()), command)
        self.assertIn("--background", command)
        self.assertIn("--disable-autoexec", command)
        self.assertFalse(kwargs["shell"])
        self.assertFalse(host.capabilities().get("untrusted", False))
        changed = host.capabilities()
        changed["untrusted"] = True
        self.assertNotIn("untrusted", host.capabilities())

    def test_close_is_idempotent_and_reaps_only_owned_child(self):
        host = self.make_host()
        self.assertTrue(host.is_alive)
        host.close()
        host.close()
        self.assertFalse(host.is_alive)
        self.assertIsNotNone(self.children[0].poll())
        with self.assertRaises(HostTransportError):
            host.capture_scene()

    def test_stdout_and_stderr_chatter_is_bounded_and_does_not_corrupt_rpc(self):
        host = self.make_host("chatter")
        self.assertEqual(host.capture_scene()["revision"], "r1")
        self.assertLessEqual(len(host.diagnostics), 64)
        self.assertTrue(any("noise" in line for line in host.diagnostics))

    def test_definite_read_error_is_recoverable(self):
        host = self.make_host("error")
        for _ in range(2):
            with self.assertRaisesRegex(HostRemoteError, "unsupported mesh"):
                host.capture_scene()
        self.assertTrue(host.is_alive)

    def test_uncertain_mutation_error_invalidates_and_reaps_host(self):
        host = self.make_host("mutation_error")
        with self.assertRaisesRegex(HostTransportError, "mutation could not be verified"):
            host.apply_transform({}, "r1")
        self.assertFalse(host.is_alive)
        self.assertIsNotNone(self.children[0].poll())

    def test_timeout_exit_and_invalid_frames_fail_closed(self):
        for mode in ("timeout", "crash", "mismatch", "boolean_id", "nonfinite", "invalid"):
            with self.subTest(mode=mode):
                host = self.make_host(mode, timeout=0.2)
                with self.assertRaises(HostTransportError):
                    host.capture_scene()
                self.assertFalse(host.is_alive)
                self.assertIsNotNone(self.children[-1].poll())
                with self.assertRaises(HostTransportError):
                    host.capture_scene()

    def test_bad_handshake_cleans_up_child(self):
        with self.assertRaisesRegex(HostTransportError, "protocol version"):
            self.make_host("version")
        self.assertIsNotNone(self.children[-1].poll())

    def test_local_nonfinite_request_never_reaches_child(self):
        host = self.make_host()
        with self.assertRaises(ValueError):
            host.apply_transform({"translation": [math.nan, 0, 0]}, "r1")
        self.assertTrue(host.is_alive)
        self.assertEqual(host.capture_scene()["revision"], "r1")

    def test_oversized_request_is_rejected_before_blocking_pipe_write(self):
        host = self.make_host()
        with self.assertRaisesRegex(ValueError, "4096-character"):
            host.apply_transform({"focal_id": "x" * 5000}, "r1")
        self.assertEqual(host.capture_scene()["revision"], "r1")

    def test_missing_file_and_invalid_timeout_do_not_launch_child(self):
        with self.assertRaises(ValueError):
            BlenderProcessHost(sys.executable, self.base / "missing.blend")
        with self.assertRaises(ValueError):
            BlenderProcessHost(sys.executable, self.blend, timeout=math.inf)
        self.assertEqual(self.children, [])


if __name__ == "__main__":
    unittest.main()
