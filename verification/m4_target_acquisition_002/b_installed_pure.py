"""Run frozen B pure checks with ordinary installed imports before fixtures."""

import ast
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


def module_from_file(name, path):
    read(path)
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    failure = None
    checks = []
    origins = {}
    parity_count = 0
    try:
        binding = json.loads(read(HERE / 'build_B/RUN_BINDING.json'))
        installed = Path(binding['install_root']).resolve()
        for row in binding['source_manifest']:
            local, packaged = read(ROOT / row['path']), read(installed / row['path'])
            if local != packaged or hashlib.sha256(packaged).hexdigest() != row['sha256']:
                raise AssertionError('source/installation parity ' + row['path'])
            parity_count += 1
        sys.path[:0] = [str(installed), binding['dependency_root'], str(HERE), str(ROOT)]
        from human_eye_plugin import blender_host, active_observation, active_observation_host, live_service, live_spatial_mcp
        import human_eye_hook
        from human_eye_plugin.read_context import ReadContext
        for name, function in {
            'capture_active_observation': blender_host.BlenderSceneHost.capture_active_observation,
            'outside_xy_viewports': blender_host._observation_outside_xy_viewports,
            'camera': blender_host._observation_target_cameras,
            'geometry': active_observation.geometry,
            'source_binding': active_observation_host.source_binding,
            'error_result': live_spatial_mcp.LiveSpatialMCPServer._error_result,
            'read_context_result': ReadContext.result,
            'hook_audit': human_eye_hook.write_audit_event,
        }.items():
            path = Path(function.__code__.co_filename).resolve()
            path.relative_to(installed)
            origins[name] = {'path': str(path), 'sha256': hashlib.sha256(read(path)).hexdigest()}

        # Reuse only the test-double definitions. The original fixture module
        # also loads a checkout host module, which is unnecessary for this run.
        fixture_source = read(ROOT / 'verification/test_blender_host_contracts.py').decode('utf8')
        fixture_tree = ast.parse(fixture_source)
        selected = {'FakeMatrix', 'matrix', 'FakeMesh', 'FakeObject'}
        fixture_definitions = [ast.get_source_segment(fixture_source, node) for node in fixture_tree.body
                               if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in selected]
        if len(fixture_definitions) != 4:
            raise AssertionError('expected four existing bpy-double definitions')
        with (HERE / 'installed_bpy_fixtures.py').open('x', encoding='utf8', newline='\n') as handle:
            handle.write('from types import SimpleNamespace as NS\n\n' + '\n\n'.join(fixture_definitions) + '\n')

        original = read(HERE / 'product_pure_checks.py').decode('utf8')
        import_line = 'from verification.test_blender_host_contracts import FakeObject, host_fixture, matrix, _module as host_module'
        if original.count(import_line) != 1:
            raise AssertionError('expected one explicit fake-host import')
        product_copy = original.replace(import_line, 'from installed_bpy_fixtures import FakeObject, matrix\nfrom human_eye_plugin import blender_host as host_module')
        setup = """graph = NS(object_instances=[])
    layer = NS(update=lambda: None, depsgraph=graph, objects=NS(active=None))
    scene = NS(objects=[], unit_settings=NS(scale_length=1.), frame_current=1, view_layers=[layer])
    graph.scene_eval = NS(original=scene)
    bpy = NS(context=NS(scene=scene, view_layer=layer, evaluated_depsgraph_get=lambda: graph))
    host = host_module.BlenderSceneHost(bpy)"""
        product_copy = product_copy.replace('host, _, _, _ = host_fixture()', setup)
        product_copy = product_copy.replace('import sys\n', 'import sys\nimport struct\n')
        product_copy = product_copy.replace('float(Fraction(value)) for value in point',
                                            "struct.unpack('f', struct.pack('f', float(Fraction(value))))[0] for value in point")
        product_copy = product_copy.replace("'PRODUCT_PURE_01.json'", "'B_INSTALLED_PRODUCT_PURE.json'")
        with (HERE / 'installed_product_pure_checks.py').open('x', encoding='utf8', newline='\n') as handle:
            handle.write(product_copy)
        cache_copy = read(HERE / 'cache_source_prediction_pure.py').decode('utf8').replace(
            "'CACHE_SOURCE_PREDICTION_PURE.json'", "'B_INSTALLED_CACHE_SOURCE_PREDICTION.json'")
        with (HERE / 'installed_cache_source_prediction_pure.py').open('x', encoding='utf8', newline='\n') as handle:
            handle.write(cache_copy)

        planned = [
            ('acquisition', 'installed_product_pure_checks.py', [], 'B_INSTALLED_PRODUCT_PURE.json'),
            ('target_public', 'target_public_pure_checks.py', ['B_INSTALLED_TARGET_PUBLIC.json'], 'B_INSTALLED_TARGET_PUBLIC.json'),
            ('source_cache', 'installed_cache_source_prediction_pure.py', [], 'B_INSTALLED_CACHE_SOURCE_PREDICTION.json'),
        ]
        for name, filename, arguments, output in planned:
            helper = module_from_file('installed_B_' + name, HERE / filename)
            if name == 'acquisition' and helper.host_module is not blender_host:
                raise AssertionError('acquisition helper did not bind installed host')
            saved = sys.argv
            stream = io.StringIO()
            try:
                sys.argv = [str(HERE / filename), *arguments]
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                    helper.main()
            finally:
                sys.argv = saved
            result = json.loads(read(HERE / output))
            checks.append({'id': name, 'passed': result['passed'], 'checks': len(result['checks']),
                           'output': str(HERE / output), 'stdout_stderr': stream.getvalue()})
            if not result['passed']:
                raise AssertionError('installed B pure failed ' + name)

        names = ['verification.test_active_observation_patches', 'verification.test_active_observation_patch_numerics',
                 'verification.test_active_observation_region_world']
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            legacy = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        checks.append({'id': 'legacy_full', 'passed': legacy.wasSuccessful(), 'checks': legacy.testsRun,
                       'modules': names, 'stdout_stderr': stream.getvalue()})
        if not legacy.wasSuccessful():
            raise AssertionError('installed legacy pure failed')
        leaks = []
        for name, module in list(sys.modules.items()):
            path = getattr(module, '__file__', None)
            if name.startswith('human_eye_') and path:
                try:
                    Path(path).resolve().relative_to(installed)
                except ValueError:
                    leaks.append({'module': name, 'path': path})
        if leaks:
            raise AssertionError('noninstalled product module ' + json.dumps(leaks))
        for pin in list(PINS.values()):
            if hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest() != pin['sha256']:
                raise AssertionError('input changed during installed checks ' + pin['path'])
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {'schema': 'm4-target-acquisition-002-B-installed-pure-v1', 'passed_checked_scope': failure is None,
              'candidate_commit': 'c309d7e4302518cd5f7d1c3966e7c7fa338ea128',
              'source_install_parity_count': parity_count, 'actual_function_origins': origins,
              'checks': checks, 'failure': failure,
              'test_setup_changes': ['Existing fake bpy definitions copied without the checkout host loader.',
                                     'Actual installed BlenderSceneHost constructed from the same test doubles.',
                                     'Local points explicitly binary32, retaining the frozen world geometry.',
                                     'Exclusive new output names preserve earlier evidence.'],
              'source_pins': sorted(PINS.values(), key=lambda pin: pin['path']),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0,
              'microbenchmarks_run': 0, 'prior_384_replays': 0}
    with (HERE / 'B_INSTALLED_PURE.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed_checked_scope': failure is None, 'groups': [
        {'id': row['id'], 'passed': row['passed'], 'checks': row['checks']} for row in checks],
        'source_install_parity_count': parity_count, 'failure': failure}))
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
