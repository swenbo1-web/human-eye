"""Run existing pure checks with the frozen installed product preloaded."""

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
PINS = {}


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    PINS[str(path)] = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw


def load_helper(name, path):
    read(path)
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    failure = None
    helper_results = []
    origins = {}
    parity_count = 0
    try:
        binding = json.loads(read(HERE / 'build/RUN_BINDING.json'))
        freeze = json.loads(read(HERE / 'SOURCE_FREEZE.json'))
        install = Path(binding['install_root']).resolve()
        for row in freeze['runtime_manifest']:
            source_bytes, installed_bytes = read(ROOT / row['path']), read(install / row['path'])
            if source_bytes != installed_bytes or hashlib.sha256(installed_bytes).hexdigest() != row['sha256']:
                raise AssertionError('frozen installation mismatch ' + row['path'])
            parity_count += 1
        sys.path[:0] = [str(install), binding['dependency_root'], str(ROOT)]
        # Ordinary installed-package imports bind its __path__ before fixtures
        # add their checkout location for test data and recorded source hashes.
        from human_eye_plugin import active_observation, active_observation_host, blender_host, live_spatial_mcp
        from human_eye_plugin.read_context import ReadContext
        functions = {
            'geometry': active_observation.geometry,
            'source_binding': active_observation_host.source_binding,
            'camera': blender_host._observation_target_cameras,
            'error_result': live_spatial_mcp.LiveSpatialMCPServer._error_result,
            'read_context_result': ReadContext.result,
        }
        for name, function in functions.items():
            path = Path(function.__code__.co_filename).resolve()
            path.relative_to(install)
            origins[name] = {'path': str(path), 'sha256': hashlib.sha256(read(path)).hexdigest()}

        planned = [
            ('mapping', 'error_mapping_pure_checks.py', ['--out', 'INSTALLED_ERROR_MAPPING.json']),
            ('target_public', 'target_public_pure_checks.py', ['INSTALLED_TARGET_PUBLIC.json']),
        ]
        original_cache = read(HERE / 'cache_source_prediction_pure.py')
        cache_copy = HERE / 'installed_cache_source_prediction_pure.py'
        old_output = b"'CACHE_SOURCE_PREDICTION_PURE.json'"
        if original_cache.count(old_output) != 1:
            raise AssertionError('expected one explicit cache output filename')
        with cache_copy.open('xb') as handle:
            handle.write(original_cache.replace(old_output, b"'INSTALLED_CACHE_SOURCE_PREDICTION_PURE.json'"))
        planned.append(('cache_source_prediction', cache_copy.name, []))
        for name, filename, arguments in planned:
            module = load_helper('installed_check_' + name, HERE / filename)
            saved_argv = sys.argv
            stream = io.StringIO()
            try:
                sys.argv = [str(HERE / filename), *arguments]
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                    module.main()
            finally:
                sys.argv = saved_argv
            output = {'mapping': 'INSTALLED_ERROR_MAPPING.json', 'target_public': 'INSTALLED_TARGET_PUBLIC.json',
                      'cache_source_prediction': 'INSTALLED_CACHE_SOURCE_PREDICTION_PURE.json'}[name]
            result = json.loads(read(HERE / output))
            helper_results.append({'id': name, 'passed': result['passed'], 'output': str(HERE / output),
                                   'count': result.get('case_count', len(result.get('checks', []))),
                                   'stdout_stderr': stream.getvalue()})
            if not result['passed']:
                raise AssertionError('installed helper failed ' + name)

        modules = ['verification.test_active_observation_patches', 'verification.test_active_observation_patch_numerics',
                   'verification.test_active_observation_region_world']
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        helper_results.append({'id': 'legacy_full', 'passed': result.wasSuccessful(), 'count': result.testsRun,
                               'modules': modules, 'stdout_stderr': stream.getvalue()})
        if not result.wasSuccessful():
            raise AssertionError('installed legacy pure failed')
        leaked = []
        for name, module in list(sys.modules.items()):
            filename = getattr(module, '__file__', None)
            if name.startswith('human_eye_') and filename:
                try:
                    Path(filename).resolve().relative_to(install)
                except ValueError:
                    leaked.append({'module': name, 'path': filename})
        if leaked:
            raise AssertionError('noninstalled product module ' + json.dumps(leaked))
        for pin in list(PINS.values()):
            if hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest() != pin['sha256']:
                raise AssertionError('input changed during installed checks ' + pin['path'])
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {'schema': 'm4-camera-installed-pure-review-v1', 'passed_checked_scope': failure is None,
              'candidate_commit': '691f7b78ed89ccf30df47847fc1e99ad51a1dc64',
              'installed_source141_sha256': '9f2c5ca150f968841b64f4d4eda89313069453853c877ba21b6a262999e29a61',
              'source_installation_parity_count': parity_count, 'actual_function_origins': origins,
              'checks': helper_results, 'failure': failure,
              'test_loading': 'Installed package normally imported first. Existing fixtures retain checkout data/hash locations. All loaded human_eye product modules checked under candidate installation.',
              'cache_helper_copy_change': 'Only output filename changed in a new test copy to preserve earlier evidence.',
              'source_pins': sorted(PINS.values(), key=lambda pin: pin['path']),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0,
              'microbenchmarks_run': 0}
    with (HERE / 'INSTALLED_PURE.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed_checked_scope': failure is None, 'helpers': helper_results,
                      'failure': failure, 'source_installation_parity_count': parity_count}))
    if failure is not None:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
