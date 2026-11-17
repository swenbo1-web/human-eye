"""Verify projection contracts while forbidding solve, raster and image encoding."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--binding', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    guard = None
    if args.binding:
        binding = json.loads(args.binding.read_bytes())
        sys.path.insert(0, binding['dependency_root'])
        loader = ROOT / 'verification/m4_source_region_display_001/harness/reused/verified_bootstrap.py'
        spec = importlib.util.spec_from_file_location('_regression_source_bootstrap', loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        guard = module.bootstrap(binding)
    import numpy as np
    from PIL import Image
    from human_eye_plugin import live_spatial_mcp as mcp
    began = time.perf_counter_ns()
    output = io.StringIO()
    forbidden = AssertionError('New solve/raster/PNG_NPZ encoding forbidden in pure projection regression')
    with patch.object(Image.Image, 'save', side_effect=forbidden) as png, \
            patch.object(np, 'savez_compressed', side_effect=forbidden) as npz, \
            patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=forbidden) as raster, \
            patch('human_eye_plugin.surface_proximity.measure_surface_proximity', side_effect=forbidden) as solve:
        suite = unittest.defaultTestLoader.discover(str(HERE / 'tests'), pattern='test_facts_projection.py')
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
        counts = dict(PNG_encoding=png.call_count, NPZ_encoding=npz.call_count,
                      raster=raster.call_count, product_solve=solve.call_count)
    assert not any(counts.values())
    if guard:
        guard.verify_loaded()
    raw = output.getvalue().encode()
    path = HERE / 'tests' / ('REGRESSIONS_' + args.label)
    path.with_suffix('.log').write_bytes(raw)
    record = {'status': 'passed' if result.wasSuccessful() else 'failed', 'tests': result.testsRun,
        'failures': [{'test': str(t), 'traceback': e} for t, e in result.failures],
        'errors': [{'test': str(t), 'traceback': e} for t, e in result.errors],
        'guarded_operations': counts, 'installed_guard': guard is not None, 'actual_import': mcp.__file__,
        'started_ns': began, 'closed_ns': time.perf_counter_ns(), 'log_sha256': hashlib.sha256(raw).hexdigest()}
    path.with_suffix('.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': record['status'], 'tests': result.testsRun, 'guard_counts': counts}))
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
