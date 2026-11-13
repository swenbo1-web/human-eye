"""Offline contracts for the engineering coordinator's six business messages."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest


spec = importlib.util.spec_from_file_location('_continuity_engineering_runner', Path(__file__).with_name('run_episodes.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerContract(unittest.TestCase):
    def test_c_ordinary_defaults_keep_one_session(self):
        requests = [runner.business_request('C', turn) for turn in runner.TURNS]
        self.assertEqual(len({row['id'] for row in requests}), 3)
        for row in requests:
            self.assertEqual(row['params']['name'], 'human_eye_scene_observe')
            self.assertEqual(row['params']['arguments'], {'session_id': 'continuity-engineering-C-001',
                'include_image': False, 'query': {'mode': 'surface_scan', 'threshold_m': .002}})

    def test_n_marker_is_created_once_and_required_afterwards(self):
        namespace = {'bpy': types.SimpleNamespace(context=types.SimpleNamespace(scene=types.SimpleNamespace(
            unit_settings=types.SimpleNamespace(scale_length=1.), objects=[])))}
        values = []
        for turn in runner.TURNS:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(runner.n_code(turn), '<synthetic-marker>', 'exec'), namespace)
            values.append(json.loads(output.getvalue()))
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[1], values[2])
        with self.assertRaises(AssertionError):
            exec(runner.n_code('BASE'), namespace)
        for turn in ('REPEAT', 'EDIT'):
            with self.assertRaises(KeyError):
                exec(runner.n_code(turn), {'bpy': namespace['bpy']})

    def test_backend_identity_detects_process_or_endpoint_replacement(self):
        keys = ('episode_id', 'owner_pid', 'native_pid', 'native_host', 'native_port', 'native_workspace',
                'product_launcher_pid', 'product_runtime_proof', 'session_id', 'worker_deadline_ns')
        original = dict.fromkeys(keys, 1)
        for key in keys:
            changed = dict(original)
            changed[key] = 2
            self.assertNotEqual(runner.backend_identity(original), runner.backend_identity(changed))


if __name__ == '__main__':
    unittest.main()
