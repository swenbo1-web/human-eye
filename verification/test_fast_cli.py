"""Actual process/NPZ/JSONL integration of the standalone fast entry point."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from human_eye_fast.cli import demo_data

ROOT = Path(__file__).resolve().parents[1]


class FastCliTests(unittest.TestCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, "-B", "-m", "human_eye_fast", *args],
                              cwd=ROOT, input=input, text=True, capture_output=True, check=True)

    def test_demo_has_cross_frame_same_face_witness(self):
        report = json.loads(self.run_cli("demo").stdout)
        self.assertFalse(report["frames"]["rest"]["mixed"])
        self.assertTrue(report["frames"]["deformed"]["mixed"])
        self.assertTrue(report["witnesses"])
        self.assertEqual(set(report["witnesses"][0]["frames"]), {"rest", "deformed"})

    def test_npz_one_shot_and_persistent_update_agree(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.npz"
            data = demo_data()
            np.savez(path, **data)
            one = json.loads(self.run_cli("analyze", str(path)).stdout)
            commands = [dict(op="load", path=str(path)), dict(op="query"),
                        dict(op="update", label="deformed", vertices=data["reference"].tolist(),
                             changed_vertices=[0, 1, 2, 3]),
                        dict(op="query"), dict(op="rows", label="deformed", indices=[1]), dict(op="close")]
            result = self.run_cli("serve", input="".join(json.dumps(x) + "\n" for x in commands))
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(one, replies[1])
            self.assertFalse(replies[3]["frames"]["deformed"]["mixed"])
            np.testing.assert_allclose(replies[4][0]["stretches"], [1, 1])
            self.assertEqual(replies[-1], {"closed": True})

    def test_import_does_not_boot_legacy_runtime(self):
        code = "import sys,human_eye_fast; assert not any(x.startswith('human_eye_plugin') for x in sys.modules)"
        subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
