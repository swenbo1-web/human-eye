"""Run bounded source and mocked-frame regressions for the first implementation."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
FILES = [HERE / 'test_region_task_core.py'] + [ROOT / 'verification' / name for name in (
    'test_active_observation_host.py', 'test_active_observation_images.py',
    'test_active_observation_patches.py', 'test_active_observation_patch_images.py',
    'test_active_observation_patch_numerics.py', 'test_active_observation_region_world.py')]


def main():
    suite = unittest.TestSuite()
    for index, path in enumerate(FILES):
        spec = importlib.util.spec_from_file_location('_cross_scale_core_' + str(index), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    stream = io.StringIO()
    outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    result = dict(passed=outcome.wasSuccessful(), tests=outcome.testsRun,
        failures=len(outcome.failures), errors=len(outcome.errors),
        actual_Blender_starts=0, actual_rasters=0, model_consumers=0,
        scope='Exact geometry, source and synthetic mocked-frame tests. Actual qualification is root-owned.',
        source_pins=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in FILES])
    (HERE / 'R0_CHECKS.stdout.txt').write_text(stream.getvalue(), encoding='utf8')
    (HERE / 'R0_CHECKS.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))
    if not outcome.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
