"""Verify the dependency-free embedded-host router transport and cleanup."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "human_eye_plugin" / "router_process.py"
SPEC = importlib.util.spec_from_file_location("router_process_standalone_tests", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ExternalRouterProcess = MODULE.ExternalRouterProcess
RouterProcessError = MODULE.RouterProcessError


FAKE_WORKER = r'''
import json,os,sys,time
mode = sys.argv[1]
if mode == 'no_read': time.sleep(10)
for line in sys.stdin:
 request=json.loads(line)
 ident=request['id']
 if mode=='timeout': time.sleep(10)
 elif mode=='crash': os._exit(3)
 elif mode=='mismatch': print(json.dumps({'id':ident+1,'result':{}}),flush=True)
 elif mode=='bool_id': print(json.dumps({'id':True,'result':{}}),flush=True)
 elif mode=='nonfinite': print('{"id":'+str(ident)+',"result":{"bad":1e999}}',flush=True)
 elif mode=='invalid': print('not JSON',flush=True)
 elif mode=='ambiguous': print(json.dumps({'id':ident,'result':{},'error':{}}),flush=True)
 elif mode=='error': print(json.dumps({'id':ident,'error':{'message':'rejected event'}}),flush=True)
 else:
  if mode=='stderr':
   for index in range(150): print('diagnostic '+str(index),file=sys.stderr,flush=True)
  print(json.dumps({'id':ident,'result':{'route':'native','echo':request['payload']}}),flush=True)
'''


class RouterProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.worker = Path(self.temp.name) / "worker.py"
        self.worker.write_text(FAKE_WORKER, encoding="utf-8")
        self.original_popen = subprocess.Popen
        self.children = []
        self.commands = []

    def make_router(self, mode="normal", **kwargs):
        def launch(command, **popen_kwargs):
            self.commands.append((command, popen_kwargs.copy()))
            child = self.original_popen([sys.executable, str(self.worker), mode], **popen_kwargs)
            self.children.append(child)
            return child
        with patch.object(MODULE.subprocess, "Popen", side_effect=launch):
            router = ExternalRouterProcess(sys.executable, ROOT, **kwargs)
        self.addCleanup(router.close)
        return router

    def test_launch_and_persistent_requests_preserve_payload(self):
        router = self.make_router()
        for index in range(2):
            event = {"event":"before_model", "session_id":"中文", "sequence":index}
            self.assertEqual(router.handle_event(event)["echo"], event)
        command, kwargs = self.commands[0]
        self.assertIn("--readback-atol-m", command)
        self.assertIn("-B", command)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(Path(kwargs["cwd"]), ROOT)
        self.assertEqual(len(self.children), 1)

    def test_close_reaps_child_and_is_idempotent(self):
        router = self.make_router()
        router.handle_event({})
        router.close()
        router.close()
        self.assertFalse(router.is_alive)
        self.assertIsNotNone(self.children[0].poll())
        with self.assertRaises(RouterProcessError):
            router.handle_event({})

    def test_stderr_tail_is_bounded_without_corrupting_evidence(self):
        router = self.make_router("stderr")
        self.assertEqual(router.handle_event({})["route"], "native")
        self.assertLessEqual(len(router.diagnostics), 64)
        self.assertTrue(any("diagnostic" in line for line in router.diagnostics))

    def test_response_errors_and_ambiguous_ids_invalidate_child(self):
        for mode in ("crash", "mismatch", "bool_id", "nonfinite", "invalid", "ambiguous", "error", "timeout"):
            with self.subTest(mode=mode):
                router = self.make_router(mode, timeout_s=0.2)
                with self.assertRaises(RouterProcessError):
                    router.handle_event({})
                self.assertFalse(router.is_alive)
                self.assertIsNotNone(self.children[-1].poll())

    def test_timeout_covers_blocked_large_scene_pipe_write(self):
        router = self.make_router("no_read", timeout_s=0.2)
        with self.assertRaisesRegex(RouterProcessError, "timed out while writing"):
            router.handle_event({"mesh_payload":"x" * 1_000_000})
        self.assertFalse(router.is_alive)
        self.assertIsNotNone(self.children[-1].poll())

    def test_invalid_local_input_does_not_invalidate_process(self):
        router = self.make_router()
        for invalid in ([], {"bad":math.nan}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    router.handle_event(invalid)
        self.assertEqual(router.handle_event({})["route"], "native")

    def test_bounds_are_checked_before_launch(self):
        for kwargs in ({"timeout_s":math.inf}, {"quad_size":True}, {"quad_size":63},
                       {"readback_atol_m":-1}, {"readback_atol_m":math.nan}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ExternalRouterProcess(sys.executable, ROOT, **kwargs)

    def test_direct_source_import_needs_no_engine_dependencies(self):
        expression = ("import importlib.util,sys; "
                      f"spec=importlib.util.spec_from_file_location('standalone_router', {str(SOURCE)!r}); "
                      "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
                      "assert 'numpy' not in sys.modules; assert 'PIL' not in sys.modules")
        completed = subprocess.run([sys.executable, "-I", "-c", expression], capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_real_router_native_event_requires_no_model_api(self):
        with ExternalRouterProcess(sys.executable, ROOT, timeout_s=20) as router:
            result = router.handle_event({"event":"before_model", "session_id":"process-native-test",
                                          "task_kind":"image_qa", "task_instruction":"Read image."})
            self.assertEqual(result["route"], "native")
            self.assertFalse(result["engine_invoked"])


if __name__ == "__main__":
    unittest.main()
