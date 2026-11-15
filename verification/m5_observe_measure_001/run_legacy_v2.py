"""Run saved namespace-only fixtures and original non-raster regressions."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, 'D:/he_anchor_001/venv/Lib/site-packages')


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def run(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        result = unittest.TextTestRunner(stream=capture, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(module))
    return {'source': pin(path), 'passed_checked_scope': result.wasSuccessful(),
        'tests_run': result.testsRun, 'errors': [{'test': str(test), 'traceback': trace}
            for test, trace in result.errors], 'failures': [{'test': str(test), 'traceback': trace}
            for test, trace in result.failures], 'skipped': result.skipped,
        'log': capture.getvalue()}


def main():
    original = ROOT / 'verification/test_active_observation_service.py'
    # Retain the exact old fixture result before adapting the private callback.
    initial = run(original, 'original_m5_active_service')
    save(HERE / 'LEGACY_SERVICE_V2_INITIAL.json', initial)
    fixture = original.read_text(encoding='utf-8')
    signature = 'def compute(self, capture, output_directory, *, include_image, construction_callback, check_budget):'
    assert fixture.count(signature) == 1
    fixture = fixture.replace(signature,
        'def compute(self, capture, output_directory, *, include_image, construction_callback, check_budget, _geometry_ids_callback=None):')
    site = '        self.compute_calls += 1\n'
    assert fixture.count(site) == 1
    fixture = fixture.replace(site, site +
        "        if _geometry_ids_callback is not None:\n"
        "            _geometry_ids_callback(tuple('synthetic-geometry-' + row['object_id'] for row in capture['meshes']))\n")
    adapted_dir = HERE / 'legacy_v2_source'
    adapted_dir.mkdir(exist_ok=False)
    adapted = adapted_dir / original.name
    with adapted.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(fixture)
    results = [run(adapted, 'adapted_m5_active_service'),
        run(ROOT / 'verification/test_active_observation_brief.py', 'm5_legacy_active_brief'),
        run(ROOT / 'verification/test_task_query.py', 'm5_legacy_task_query')]
    baseline = json.loads((HERE / 'product_v1_pure_01/MAIN_SERVICE_RESULT.json').read_text(encoding='utf-8'))
    candidate = json.loads((HERE / 'product_v2_pure_01/MAIN_SERVICE_RESULT.json').read_text(encoding='utf-8'))
    parity = {key: baseline[key] == candidate[key] for key in ('binding', 'facts', 'task_result')}
    output = {'schema': 'm5-legacy-v2-nonraster-regression-v1',
        'passed_checked_scope': all(row['passed_checked_scope'] for row in results) and all(parity.values()),
        'tests_run': sum(row['tests_run'] for row in results), 'suites': results,
        'original_fixture_result': pin(HERE / 'LEGACY_SERVICE_V2_INITIAL.json'),
        'fixture_adaptation': 'Only the synthetic observe_capture stub signature and callback emission were adapted. All existing assertions are unchanged. The original fixture result is retained.',
        'v1_v2_synthetic_semantic_parity': parity,
        'source_pins': [pin(ROOT / name) for name in (
            'human_eye_plugin/active_observation_host.py', 'human_eye_plugin/live_service.py')],
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'scene_rasters': 0, 'models': 0},
        'scope': 'Service algorithm is stubbed. Brief tests create fixed RGB PNG fixtures without scene rasterization. Task-only suite uses synthetic pure geometry.'}
    save(HERE / 'LEGACY_V2.json', output)
    print(json.dumps({'passed': output['passed_checked_scope'], 'tests_run': output['tests_run'],
        'original_service_tests': initial['tests_run'], 'original_service_errors': len(initial['errors']),
        'synthetic_semantic_parity': parity}))
    if not output['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
