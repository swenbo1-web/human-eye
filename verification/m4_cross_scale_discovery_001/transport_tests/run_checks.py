"""Run bounded synthetic transport and existing representation regressions."""

import hashlib
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE), 'D:/he_anchor_001/venv/Lib/site-packages']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    options = parser.parse_args()
    if options.baseline:
        sys.path.insert(0, 'D:/he_m5_observe_measure_001/B/product')
    started = time.perf_counter_ns()
    paths = [HERE / 'test_transport.py', ROOT / 'verification/test_query_policy.py',
        ROOT / 'verification/test_active_observation_brief.py',
        ROOT / 'verification/test_active_observation_patch_delivery.py',
        ROOT / 'verification/test_active_observation_region_delivery.py',
        ROOT / 'verification/m5_observe_measure_001/legacy_v2_source/test_active_observation_service.py']
    if options.baseline:
        paths = paths[1:]
    else:
        paths = [path for path in paths if path.name not in
                 ('test_active_observation_patch_delivery.py', 'test_active_observation_region_delivery.py')]
    suite = unittest.TestSuite()
    for index, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location('_cross_transport_checks_' + str(index), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    output = io.StringIO()
    counts = dict(production_raster_calls=0, mocked_core_raster_calls=0, PIL_image_save_calls=0)
    def profile(frame, event, argument):
        if event != 'call':
            return
        filename, name = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
        if filename.endswith('/attention_raster.py') and name == 'rasterize_attention':
            counts['production_raster_calls'] += 1
        if filename.endswith('/core_tests/test_region_task_core.py') and name == 'raster':
            counts['mocked_core_raster_calls'] += 1
        if filename.endswith('/PIL/Image.py') and name == 'save':
            counts['PIL_image_save_calls'] += 1
    sys.setprofile(profile)
    try:
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    finally:
        sys.setprofile(None)
    stem = 'BASELINE_LEGACY_CHECKS' if options.baseline else 'R0_CHECKS'
    (HERE / (stem + '.stdout.txt')).write_text(output.getvalue(), encoding='utf8', newline='\n')
    record = dict(schema='cross-scale-transport-checks-v1', passed=result.wasSuccessful(),
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        actual_Blender=0, execution_counts=counts, mocked_raster_outputs=True, paid_model_calls=0,
        baseline_installed_product=options.baseline,
        input_pins=[dict(path=str(path), bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths],
        source_pins=[dict(path=str(path), bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in [
                ROOT / 'human_eye_plugin/query_policy.py', ROOT / 'human_eye_plugin/live_service.py',
                ROOT / 'human_eye_plugin/live_spatial_mcp.py', Path(__file__).resolve()]],
        started_ns=started, closed_ns=time.perf_counter_ns())
    (HERE / (stem + '.json')).write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=record['passed'], tests=result.testsRun, errors=record['errors'], failures=record['failures'])))
    if not result.wasSuccessful() and not options.baseline:
        print(output.getvalue())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
