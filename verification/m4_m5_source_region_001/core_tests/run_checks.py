"""Append-only offline regression runs, instrumenting synthetic PNG cost."""
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
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image
import human_eye_plugin.active_observation_images as image_core
import human_eye_plugin.source_region as region_core


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else 'R0_01'
    destination = HERE / 'runs' / run_id
    destination.mkdir(parents=True, exist_ok=False)
    files = [HERE / 'test_source_region_core.py', HERE / 'test_fresh_payload.py'] + [ROOT / 'verification' / name for name in (
        'test_active_observation_host.py', 'test_active_observation_images.py',
        'test_active_observation_patches.py', 'test_active_observation_patch_images.py',
        'test_active_observation_patch_numerics.py', 'test_active_observation_region_world.py')]
    files += [ROOT / 'verification/m4_cross_scale_discovery_001/core_tests' / name
              for name in ('test_region_task_core.py', 'test_region_task_bounds.py')]
    suite = unittest.TestSuite()
    stale_r0_assertions = {
        'test_local_numeric_insufficiency_preserves_six_constructed_global_frames',
        'test_single_geometry_preparation_shared_meshes_and_source_bound_scopes'}
    separate_legacy = len(sys.argv) > 2 and sys.argv[2] == '--current-r1'
    excluded = []
    modules = []
    for index, path in enumerate(files):
        spec = importlib.util.spec_from_file_location('_source_region_offline_' + str(index), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
        loaded = unittest.defaultTestLoader.loadTestsFromModule(module)
        for group in loaded:
            for test in group:
                if separate_legacy and test._testMethodName in stale_r0_assertions:
                    excluded.append(test.id())
                else:
                    suite.addTest(test)
    output = io.StringIO()
    png_cost = {'calls': 0, 'elapsed_ns': 0}
    original_save = Image.Image.save

    def save(image, fp, *args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original_save(image, fp, *args, **kwargs)
        finally:
            png_cost['calls'] += 1
            png_cost['elapsed_ns'] += time.perf_counter_ns() - started

    started = time.perf_counter_ns()
    with patch.object(Image.Image, 'save', save), patch.object(image_core, 'rasterize_attention',
            side_effect=AssertionError('actual raster disabled in offline suite')):
        outcome = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    elapsed = time.perf_counter_ns() - started
    products = [ROOT / 'human_eye_plugin' / name for name in
                ('source_region.py', 'active_observation_images.py', 'surface_proximity.py')]
    result = {'passed': outcome.wasSuccessful(), 'tests': outcome.testsRun,
              'failures': len(outcome.failures), 'errors': len(outcome.errors),
              'actual_Blender_starts': 0, 'actual_rasters': 0,
              'model_consumers': 0, 'training_calls': 0, 'paid_calls': 0,
              'elapsed_ns': elapsed, 'mock_PNG_encoding_and_publication': png_cost,
              'separately_verified_stale_R0_assertions': excluded,
              'legacy_baseline_evidence': 'runs/BASELINE_LEGACY_GUARDED_01/CHECKS.json' if excluded else None,
              'new_core_mock_counters': modules[0].MOCK_COST,
              'loaded_product_paths': {'source_region': region_core.__file__,
                                       'active_observation_images': image_core.__file__},
              'sys_path': sys.path,
              'source_pins': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                              for path in files + products]}
    (destination / 'stdout.txt').write_text(output.getvalue(), encoding='utf8')
    (destination / 'CHECKS.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(output.getvalue())
    print(json.dumps(result))
    if not outcome.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
