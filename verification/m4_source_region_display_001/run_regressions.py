"""Run bounded source-only regressions and meter synthetic encoding separately."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
os.environ.pop('HUMAN_EYE_TEST_BLENDER', None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--binding', type=Path)
    args = parser.parse_args()
    guard = None
    if args.binding is not None:
        binding = json.loads(args.binding.read_bytes())
        sys.path.insert(0, binding['dependency_root'])
        path = HERE / 'harness/reused/verified_bootstrap.py'
        spec = importlib.util.spec_from_file_location('_regression_source_guard', path)
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        guard = bootstrap.bootstrap(binding)
    import numpy as np
    from PIL import Image
    modules = [
        'verification.m4_source_region_display_001.tests.test_display_images',
        'verification.m4_source_region_display_001.tests.test_service_delivery',
        'verification.test_source_region_display_host', 'verification.test_blender_host_contracts',
        'verification.test_host_identity_contract', 'verification.test_surface_scan_host',
        'verification.test_blender_process_residency', 'verification.test_blender_native_evidence',
        'verification.test_m4_capture_001', 'verification.test_blender_mcp_host',
        'verification.test_blender_process', 'verification.test_surface_owned_task',
        'verification.test_scene_delta', 'verification.test_source_identity_cost',
        'verification.test_request_wait_budget', 'verification.test_nonplanar_cancellation',
        'verification.test_verified_source_loading',
        'verification.m4_m5_source_region_001.core_tests.test_fresh_payload',
    ]
    output = HERE / 'tests' / ('REGRESSIONS_' + args.label + '.json')
    if output.exists():
        raise FileExistsError('retain_existing_test_result')
    counters = {'PNG_encodes': 0, 'PNG_encode_ns': 0, 'NPZ_encodes': 0, 'NPZ_encode_ns': 0}
    save_image, save_npz = Image.Image.save, np.savez_compressed

    def encode_png(image, *values, **options):
        began = time.perf_counter_ns()
        try:
            return save_image(image, *values, **options)
        finally:
            counters['PNG_encodes'] += 1
            counters['PNG_encode_ns'] += time.perf_counter_ns() - began

    def encode_npz(*values, **options):
        began = time.perf_counter_ns()
        try:
            return save_npz(*values, **options)
        finally:
            counters['NPZ_encodes'] += 1
            counters['NPZ_encode_ns'] += time.perf_counter_ns() - began

    began = time.perf_counter_ns()
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    with patch('human_eye_plugin.active_observation_images.rasterize_attention',
               side_effect=AssertionError('live raster forbidden in source-only regression')) as raster_guard:
        with patch.object(Image.Image, 'save', encode_png), patch.object(np, 'savez_compressed', encode_npz):
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                result = unittest.TextTestRunner(stream=log, verbosity=1).run(suite)
    if guard is not None:
        guard.verify_loaded()
    text = log.getvalue().encode('utf8')
    output.with_suffix('.log').write_bytes(text)
    record = {'status': 'passed' if result.wasSuccessful() else 'failed', 'tests': result.testsRun,
        'failures': [{'test': str(test), 'traceback': error} for test, error in result.failures],
        'errors': [{'test': str(test), 'traceback': error} for test, error in result.errors],
        'skipped': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
        'modules': modules, 'elapsed_ns': time.perf_counter_ns() - began,
        'synthetic_encoding': counters, 'outer_real_raster_guard_calls': raster_guard.call_count,
        'owned_Blender': 0, 'model_consumers': 0,
        'installed_source_guard': args.binding is not None,
        'source_import': __import__('human_eye_plugin.source_region', fromlist=['__file__']).__file__,
        'log_sha256': hashlib.sha256(text).hexdigest()}
    output.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: record[key] for key in ('status', 'tests', 'synthetic_encoding', 'outer_real_raster_guard_calls')}))
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
