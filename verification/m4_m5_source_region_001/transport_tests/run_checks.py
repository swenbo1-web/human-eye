"""Record synthetic image work and current plus historical transport checks."""
import argparse
import hashlib
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


def pin(path):
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy-raw', action='store_true')
    options = parser.parse_args()
    paths = [ROOT / 'verification/test_query_policy.py', ROOT / 'verification/test_active_observation_brief.py',
        ROOT / 'verification/m5_observe_measure_001/legacy_v2_source/test_active_observation_service.py']
    if options.legacy_raw:
        paths.extend(ROOT / ('verification/' + name) for name in
            ('test_active_observation_patch_delivery.py', 'test_active_observation_region_delivery.py'))
    else:
        paths.extend((HERE / 'test_transport.py',
            ROOT / 'verification/m4_cross_scale_discovery_001/transport_tests/test_transport.py'))
    suite = unittest.TestSuite()
    for index, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location('_source_region_transport_' + str(index), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests = unittest.defaultTestLoader.loadTestsFromModule(module)
        for group in tests:
            for test in group:
                if (path.parent.name == 'transport_tests' and path.parent.parent.name == 'm4_cross_scale_discovery_001'
                        and test._testMethodName == 'test_current_core_mock_output_projects_brief_and_full'):
                    continue
                suite.addTest(test)
    counts = dict(production_attention_raster_calls=0, PIL_image_save_calls=0, PIL_image_new_calls=0,
                  public_native_png_validation_calls=0)
    def profile(frame, event, argument):
        if event != 'call':
            return
        filename, name = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
        if filename.endswith('/attention_raster.py') and name == 'rasterize_attention':
            counts['production_attention_raster_calls'] += 1
        if filename.endswith('/PIL/Image.py') and name == 'save':
            counts['PIL_image_save_calls'] += 1
        if filename.endswith('/PIL/Image.py') and name == 'new':
            counts['PIL_image_new_calls'] += 1
        if filename.endswith('/native_observation.py') and name == '_public_native_png':
            counts['public_native_png_validation_calls'] += 1
    output = io.StringIO()
    started = time.perf_counter_ns()
    sys.setprofile(profile)
    try:
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    finally:
        sys.setprofile(None)
    import human_eye_plugin.live_service as live_service
    import human_eye_plugin.live_spatial_mcp as live_spatial_mcp
    import human_eye_plugin.query_policy as query_policy
    import human_eye_plugin.read_context as read_context
    import human_eye_plugin.source_region as source_region
    stem = 'R0_LEGACY_RAW_CHECKS' if options.legacy_raw else 'R0_CHECKS'
    (HERE / (stem + '.stdout.txt')).write_text(output.getvalue(), encoding='utf8', newline='\n')
    record = dict(schema='source-region-transport-checks-v1', passed=result.wasSuccessful(),
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        failure_ids=[test.id() for test, details in result.failures],
        actual_Blender_processes=0, actual_live_requests=0, paid_model_calls=0,
        execution_counts=counts, synthetic_PNGs=True,
        superseded_assertions=[] if options.legacy_raw else [dict(
            input=str(ROOT / 'verification/m4_cross_scale_discovery_001/transport_tests/test_transport.py'),
            method='test_current_core_mock_output_projects_brief_and_full', original_expected_constructed_frames=8,
            accepted_R1_expected_constructed_frames=3,
            replacement='test_accepted_cross_scale_core_output_projects_brief_and_full',
            original_execution='R0_INITIAL_CHECKS.json')],
        input_pins=[pin(path) for path in paths],
        actual_import_pins=[pin(Path(module.__file__).resolve()) for module in
            (live_service, live_spatial_mcp, query_policy, read_context, source_region)],
        runner_pin=pin(Path(__file__).resolve()), started_ns=started, closed_ns=time.perf_counter_ns())
    (HERE / (stem + '.json')).write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=record['passed'], tests=result.testsRun, errors=record['errors'],
                         failures=record['failures'], execution_counts=counts)))
    if not result.wasSuccessful() and not options.legacy_raw:
        print(output.getvalue())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
