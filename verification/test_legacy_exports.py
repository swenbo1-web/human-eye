"""Compatibility imports must preserve class identity without duplicate code."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LegacyExportTests(unittest.TestCase):
    def test_compositor_direct_script_from_package_and_unrelated_directory(self):
        script = ROOT / 'human_eye_module1_operators/submodule_1_6_quad_compositor.py'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as temporary:
            for directory in (script.parent, Path(temporary)):
                with self.subTest(cwd=str(directory)):
                    process = subprocess.run([sys.executable, '-B', str(script)], cwd=directory,
                                             env=env, capture_output=True, text=True,
                                             encoding='utf-8', timeout=45)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    results = json.loads(process.stdout)
                    self.assertEqual(results['total_operators'], 30)
                    self.assertEqual(results['max_pixel_diff'], 0)
                    self.assertLess(results['epipolar_max_3d_err_m'], 1e-12)

    def test_fresh_process_import_orders_and_star_exports(self):
        for first in ("human_eye_foveated_renderer", "human_eye_module1_operators", "native_3d_spatial_scratchpad",
                      "module_2_low_token_mcp_scene_bridge", "module_3_1_mcp_protocol_ipc_engine",
                      "module_3_2_vlm_grounding_closed_loop_agent", "module_3_3_closed_loop_control_engine"):
            script = """import importlib,json
importlib.import_module(FIRST)
import human_eye_foveated_renderer as core
import human_eye_module1_operators as package
from human_eye_module1_operators import submodule_1_4_spatial_sniffer as sniffer
from human_eye_module1_operators import submodule_1_5_alignment_verifier as verifier
from human_eye_module1_operators import submodule_1_6_quad_compositor as compositor
names=('MeshEntity3D','SpatialClearanceProbeResult','ClosedLoopRecheckReport',
       'SubFrustumMathEngine','SE3AlignmentMath','SpatialAnomalySniffer',
       'SpatialAlignmentVerifier','QuadCognitiveCanvasCompositor')
for name in names:
    assert getattr(core,name) is getattr(package,name),name
assert core.LBVHMortonTree is sniffer.LBVHMortonTree
for name in core._REEXPORT_1_5:
    assert getattr(core,name) is getattr(verifier,name),name
for name in core._REEXPORT_1_6:
    assert getattr(core,name) is getattr(compositor,name),name
namespace={}
exec('from human_eye_foveated_renderer import *',namespace)
for name in (*names,*core._REEXPORT_1_6,*core._REEXPORT_1_5):
    if not name.startswith('_'):assert namespace[name] is getattr(core,name),name
print(json.dumps({'passed':True,'first':FIRST}))
""".replace("FIRST", repr(first))
            process = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                                     env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1"),
                                     capture_output=True, text=True, encoding="utf-8", timeout=20)
            with self.subTest(first=first):
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertTrue(json.loads(process.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
