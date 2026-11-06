"""Frozen-source JSONL worker for the single PERF-030-002 sequence.

The controller compiles these pinned QA bytes in an isolated interpreter.
Imports below install both source finders before loading product or QA code.
"""
from __future__ import annotations

import time

WORKER_STARTED_NS = time.perf_counter_ns()

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib
import importlib.abc
import importlib.util
import io
import json
import math
from pathlib import Path, PurePosixPath
import sys
import traceback
import tracemalloc
import types
import unittest
from unittest.mock import patch


REGRESSION_MODULES = (
    'verification.test_concave_geometry',
    'verification.test_surface_scope_regression',
    'verification.test_strict_execution_collision',
    'verification.test_local_sat_safety',
    'verification.test_scene_cache',
    'verification.test_mesh_mutation_cache',
    'verification.test_task_query',
)


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def manifest_rows(path):
    blob = path.read_bytes()
    value = json.loads(blob)
    return (value if isinstance(value, list) else value['files']), sha256(blob)


class FrozenQaFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Compile only manifest-listed verification sources from pinned bytes."""

    def __init__(self, root, rows):
        self.root = root
        self.sources = {}
        self.executed = {}
        for row in rows:
            relative = row['path']
            part = PurePosixPath(relative)
            if (part.is_absolute() or part.as_posix() != relative or '..' in part.parts
                    or '\\' in relative or ':' in relative or relative in self.sources):
                raise ValueError('qa_source_path')
            path = root / relative
            if path.resolve() != path or not path.is_relative_to(root):
                raise ValueError('qa_source_path')
            blob = path.read_bytes()
            if sha256(blob) != row['sha256']:
                raise ValueError('qa_source_changed:' + relative)
            self.sources[relative] = blob

    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'verification' and not fullname.startswith('verification.'):
            return None
        stem = fullname.replace('.', '/')
        relative = stem + '/__init__.py'
        package = relative in self.sources
        if not package:
            relative = stem + '.py'
        if relative in self.sources:
            return importlib.util.spec_from_file_location(
                fullname, self.root / relative, loader=self,
                submodule_search_locations=[str(self.root / stem)] if package else None)
        if any(name.startswith(stem + '/') for name in self.sources):
            spec = importlib.util.spec_from_loader(fullname, self, is_package=True)
            spec.submodule_search_locations = [str(self.root / stem)]
            return spec
        raise ImportError('qa_source_unlisted:' + fullname)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        origin = module.__spec__.origin
        if origin is None:
            self.executed[id(module)] = (module, None)
            return
        relative = Path(origin).relative_to(self.root).as_posix()
        blob = self.sources[relative]
        self.executed[id(module)] = (module, relative)
        try:
            exec(compile(blob, origin, 'exec', dont_inherit=True), module.__dict__)
        except BaseException:
            self.executed.pop(id(module), None)
            raise

    def verify_loaded(self):
        for relative, blob in self.sources.items():
            if (self.root / relative).read_bytes() != blob:
                raise ValueError('qa_source_changed:' + relative)
        for name, module in list(sys.modules.items()):
            if name != 'verification' and not name.startswith('verification.'):
                continue
            witness = self.executed.get(id(module))
            if witness is None or witness[0] is not module:
                raise ValueError('qa_source_preloaded:' + name)
            if witness[1] is not None and Path(module.__file__).resolve() != self.root / witness[1]:
                raise ValueError('qa_source_origin:' + name)
        return True


def exception_record(exc):
    return {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}


def identity_failure(exc):
    return type(exc).__name__ == 'SourceBindingError' or str(exc).startswith(
        ('verified_source_', 'runtime_source_', 'qa_source_'))


def captured_call(call):
    started = time.perf_counter_ns()
    try:
        return {'value': call(), 'elapsed_ns': time.perf_counter_ns() - started}
    except Exception as exc:
        if identity_failure(exc):
            raise
        return {'exception': exception_record(exc), 'elapsed_ns': time.perf_counter_ns() - started}


def witnesses(guard):
    return [{'name': module.__name__, 'path': relative,
             'sha256': sha256(guard.sources[relative])}
            for module, relative in sorted(guard._executed.values(), key=lambda row: row[0].__name__)]


def external_dependencies(runtime_root, qa_root):
    rows = []
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path is None or '.' in name:
            continue
        origin = Path(path).resolve()
        if origin.is_relative_to(runtime_root) or origin.is_relative_to(qa_root):
            continue
        rows.append({'name': name, 'file': str(origin),
                     'version': str(getattr(module, '__version__', 'not_reported'))})
    return {'python': sys.version, 'executable': sys.executable, 'modules': rows}


def source_identity(state, checkpoint):
    state['guard'].verify_loaded()
    state['qa'].verify_loaded()
    for name in state['product_short_names']:
        if name in sys.modules:
            raise ValueError('verified_source_unlisted_short_name:' + name)
    state['identity_checkpoints'].append(checkpoint)
    return {'runtime': state['identity'], 'executed': witnesses(state['guard']),
            'worker_identity_checkpoints': list(state['identity_checkpoints']),
            'runtime_manifest_sha256': state['runtime_manifest_sha256']}


def qa_identity(state):
    return {'manifest_sha256': state['qa_manifest_sha256'],
            'input_sha256': state['input_sha256'], 'file_count': len(state['qa'].sources),
            'executed': [{'name': module.__name__, 'path': relative,
                          'sha256': sha256(state['qa'].sources[relative]) if relative else None}
                         for module, relative in sorted(state['qa'].executed.values(),
                                                        key=lambda row: row[0].__name__)]}


def initialize(args):
    runtime_root = Path(args.root).resolve()
    qa_root = Path(args.qa_root).resolve()
    runtime_rows, runtime_manifest_sha = manifest_rows(Path(args.runtime_manifest))
    qa_rows, qa_manifest_sha = manifest_rows(Path(args.qa_manifest))
    loader_relative = 'human_eye_plugin/verified_source_loader.py'
    loader_pin = next(row['sha256'] for row in runtime_rows if row['path'] == loader_relative)
    loader_path = runtime_root / loader_relative
    loader_blob = loader_path.read_bytes()
    if sha256(loader_blob) != loader_pin:
        raise ValueError('verified_source_loader_pin')
    helper = types.ModuleType('_perf030_002_source_bootstrap')
    helper.__file__ = str(loader_path)
    sys.modules[helper.__name__] = helper
    exec(compile(loader_blob, str(loader_path), 'exec', dont_inherit=True), helper.__dict__)
    guard = helper.install(runtime_root, runtime_rows, bootstrap_module=helper)
    product_short_names = {Path(row['path']).stem for row in runtime_rows
                           if '/' in row['path'] and Path(row['path']).stem != '__init__'}
    qa = FrozenQaFinder(qa_root, qa_rows)
    worker_path = Path(__file__).resolve()
    worker_relative = worker_path.relative_to(qa_root).as_posix()
    if worker_relative not in qa.sources:
        raise ValueError('qa_worker_unlisted')
    qa.executed[id(sys.modules[__name__])] = (sys.modules[__name__], worker_relative)
    sys.meta_path.insert(0, qa)
    input_path = Path(args.inputs)
    if not input_path.is_absolute() or input_path.resolve() != input_path:
        raise ValueError('qa_input_absolute_path_required')
    input_relative = input_path.relative_to(qa_root).as_posix()
    inputs = json.loads(qa.sources[input_relative])
    if len(inputs['cases']) != 12:
        raise ValueError('qa_input_case_count')
    from human_eye_module1_operators import MeshEntity3D
    from human_eye_plugin import geometry_safety, scene_cache
    from human_eye_plugin.runtime_identity import runtime_identity
    import numpy as np
    from verification import perf030_002_cases
    state = {'guard': guard, 'qa': qa, 'runtime_root': runtime_root, 'qa_root': qa_root,
             'runtime_manifest_sha256': runtime_manifest_sha, 'qa_manifest_sha256': qa_manifest_sha,
             'input_sha256': sha256(qa.sources[input_relative]), 'inputs': inputs,
             'identity': runtime_identity(), 'geometry': geometry_safety, 'cache': scene_cache,
             'product_short_names': product_short_names,
             'identity_checkpoints': [],
             'MeshEntity3D': MeshEntity3D, 'np': np, 'cases': perf030_002_cases, 'arm': args.arm,
             'probes_done': False, 'tests_done': False,
             'ledger': {'samples': 0, 'prime_calls': 0, 'object_ns': 0, 'modify_ns': 0,
                        'prime_ns': 0, 'kernel_ns': 0, 'process_ns': 0}}
    return state


def construct_pair(state, case):
    return [state['MeshEntity3D'].from_dict(value) for value in case['meshes']]


def vertex_digests(state, pair):
    hashes = []
    combined = hashlib.sha256()
    for mesh in pair:
        vertices = state['np'].ascontiguousarray(mesh.vertices, dtype=state['np'].float64)
        header = json.dumps({'shape': vertices.shape, 'dtype': vertices.dtype.str},
                            sort_keys=True).encode('ascii')
        blob = header + b'\0' + vertices.tobytes()
        hashes.append(sha256(blob))
        combined.update(blob)
    return combined.hexdigest(), hashes


def sample(state, request):
    started = time.perf_counter_ns()
    case = state['inputs']['cases'][request['case_index']]
    mode, entry = request['mode'], request['entry']
    if mode not in ('cold', 'pose_miss', 'geometry_miss', 'hot'):
        raise ValueError('unknown_sample_mode')
    if entry not in ('measure_pair_geometry', 'task_result'):
        raise ValueError('unknown_sample_entry')
    costs = {'object_ns': 0, 'modify_ns': 0, 'prime_ns': 0,
             'kernel_ns': 0, 'process_ns': 0, 'prime_calls': 0}
    result = {'case': case['name'], 'group': case['group'], 'mode': mode, 'entry': entry,
              'payload': None, 'diagnostics': {}, 'costs': costs}
    np, geometry = state['np'], state['geometry']
    try:
        stage = time.perf_counter_ns()
        original = construct_pair(state, case)
        pair = original if mode in ('cold', 'hot') else construct_pair(state, case)
        cache = state['cache'].SpatialSceneCache()
        costs['object_ns'] = time.perf_counter_ns() - stage
        if mode != 'cold':
            stage = time.perf_counter_ns()
            costs['prime_calls'] = 1
            try:
                if entry == 'task_result':
                    state['cases'].task_response(original, cache)
                else:
                    geometry.measure_pair_geometry(*original, need_clearance=True)
            finally:
                costs['prime_ns'] = time.perf_counter_ns() - stage
        stage = time.perf_counter_ns()
        transform = {'kind': mode}
        before = pair[0].vertices.copy()
        if mode == 'pose_miss':
            magnitude = float(np.max(np.abs(before)))
            step = max(.000001, 2 * float(np.spacing(magnitude)))
            pair[0] = pair[0].translated([0, 0, step])
            transform.update(requested_translation=[0., 0., step])
        elif mode == 'geometry_miss':
            value = pair[0].to_dict()
            vertices = np.asarray(value['vertices'])
            bottom, height = float(vertices[:, 2].min()), float(np.ptp(vertices[:, 2]))
            magnitude = float(np.max(np.abs(vertices)))
            factor = 1 + max(.0001, 4 * float(np.spacing(magnitude)) / height)
            vertices[:, 2] = bottom + (vertices[:, 2] - bottom) * factor
            value['vertices'] = vertices.tolist()
            pair[0] = state['MeshEntity3D'].from_dict(value)
            transform.update(anchor_z=bottom, scale_z=factor)
        costs['modify_ns'] = time.perf_counter_ns() - stage
        changed = not np.array_equal(pair[0].vertices, before)
        if mode in ('pose_miss', 'geometry_miss') and not changed:
            raise AssertionError('miss_must_change_represented_vertices')
        actual_delta = pair[0].vertices - before
        transform.update(actual_delta_min=actual_delta.min(axis=0).tolist(),
                         actual_delta_max=actual_delta.max(axis=0).tolist())
        digest, object_hashes = vertex_digests(state, pair)
        result['modified_input'] = {'sha256': digest, 'object_sha256': object_hashes,
                                    'vertices_changed': changed, 'transform': transform}
        result['support_attributes_present'] = [hasattr(mesh, '_certified_convex_shells') for mesh in pair]
        stage = time.perf_counter_ns()
        try:
            if entry == 'task_result':
                result['payload'], result['diagnostics'] = state['cases'].task_response(pair, cache)
            else:
                result['payload'] = geometry.measure_pair_geometry(*pair, need_clearance=True)
        finally:
            costs['kernel_ns'] = time.perf_counter_ns() - stage
    except Exception as exc:
        if identity_failure(exc):
            raise
        result['exception'] = exception_record(exc)
    costs['process_ns'] = time.perf_counter_ns() - started
    ledger = state['ledger']
    ledger['samples'] += 1
    for field in costs:
        ledger[field] += costs[field]
    return result


def independent_witness(state, value, pair, expected):
    distance, left, right = value
    minima = [min(state['cases'].triangle_truth(point, mesh.vertices[face])['distance_sq']
                  for face in mesh.faces) for point, mesh in zip((left, right), pair)]
    coordinate_distance = math.dist(left, right)
    return {'surface_distance_sq_exact': [str(value) for value in minima],
            'coordinate_distance': coordinate_distance,
            'passed': all(value <= 1e-18 for value in minima)
            and abs(coordinate_distance - distance) <= 1e-9 and abs(distance - expected) <= 1e-14}


def workload(state):
    np, geometry = state['np'], state['geometry']
    pair = construct_pair(state, state['inputs']['cases'][2])
    points = pair[0].vertices[np.unique(pair[0].faces)]
    triangles = pair[1].vertices[pair[1].faces]
    operations = []
    original_einsum, original_cross = np.einsum, np.cross

    def einsum(expression, *operands, **kwargs):
        operations.append({'op': 'einsum', 'signature': expression,
                           'shapes': [list(value.shape) for value in operands]})
        return original_einsum(expression, *operands, **kwargs)

    def cross(left, right, *args, **kwargs):
        operations.append({'op': 'cross', 'shapes': [list(left.shape), list(right.shape)]})
        return original_cross(left, right, *args, **kwargs)

    tracemalloc.start()
    started = time.perf_counter_ns()
    try:
        with patch.object(np, 'einsum', einsum), patch.object(np, 'cross', cross):
            call = captured_call(lambda: geometry._point_triangle_min_sq(points, triangles))
        current, peak = tracemalloc.get_traced_memory()
    finally:
        elapsed = time.perf_counter_ns() - started
        tracemalloc.stop()
    return {'case_index': 2, 'point_count': len(points), 'face_count': len(triangles),
            'leaf_kernel_calls': 1,
            'operations': operations, 'call': call, 'elapsed_ns': elapsed,
            'tracemalloc_current_bytes': current, 'tracemalloc_peak_bytes': peak,
            'traced_scope': 'instrumented leaf including operation-log allocations',
            'cumulative_allocation_count': 'not_measured'}


def probes(state):
    if state['probes_done']:
        raise ValueError('probes_already_run')
    state['probes_done'] = True
    geometry = state['geometry']
    leaves = state['cases'].leaf_cases()
    selected = leaves[:2] if state['arm'] == 'baseline' else leaves
    rows = []
    for case in selected:
        truth = state['cases'].triangle_truth(case['point'], case['triangle'])
        expected = float(truth['distance_sq'])
        row = {'name': case['name'], 'point': case['point'].tolist(),
               'triangle': case['triangle'].tolist(),
               'truth': {field: str(value) if field != 'inside' else value for field, value in truth.items()}}
        row['call'] = captured_call(lambda: geometry._point_triangle_min_sq(
            case['point'][None, :], case['triangle'][None, :, :]))
        actual = row['call'].get('value')
        row['passed'] = actual is not None and math.isfinite(actual) and abs(actual - expected) <= max(8 * math.ulp(expected), 1e-30)
        if truth['distance_sq'] > 0:
            row['passed'] = row['passed'] and actual is not None and actual > 0
        rows.append(row)
    pair = state['cases'].closed_counterexample()
    closed = {'expected_clearance_m': .25,
              'budget': captured_call(lambda: geometry.work_budget_status(pair)),
              'support': [captured_call(lambda mesh=mesh: geometry.solid_support_status(mesh)) for mesh in pair],
              'measurement': captured_call(lambda: geometry.measure_pair_geometry(*pair, need_clearance=True)),
              'task': captured_call(lambda: state['cases'].task_response(pair, state['cache'].SpatialSceneCache())),
              'scalar': captured_call(lambda: geometry._surface_distance(*pair)),
              'witness': captured_call(lambda: geometry._surface_distance_with_witness(*pair))}
    if 'value' in closed['witness']:
        closed['independent_witness'] = captured_call(
            lambda: independent_witness(state, closed['witness']['value'], pair, .25))
    closed['checks'] = {'scalar': False, 'witness': False}
    measurement = closed['measurement'].get('value', {})
    if measurement.get('measurement_valid') is True:
        closed['checks']['measurement'] = (measurement['is_penetrating'] is False
                                            and abs(measurement['signed_clearance_m'] - .25) <= 1e-14)
    if 'value' in closed['task']:
        response, diagnostics = closed['task']['value']
        fact = response['facts']['surface_clearance']
        if fact['status'] == 'measured':
            closed['checks']['task_clearance'] = abs(fact['value'] - .25) <= 1e-14
    if 'value' in closed['scalar']:
        closed['checks']['scalar'] = abs(closed['scalar']['value'] - .25) <= 1e-14
    if 'value' in closed.get('independent_witness', {}):
        closed['checks']['witness'] = closed['independent_witness']['value']['passed']
    reproduced_old_error = None
    if state['arm'] == 'baseline':
        reproduced_old_error = all(row['call'].get('value') == old for row, old in zip(rows, (1., 0.)))
        passed = len(rows) == 2
    else:
        passed = all(row['passed'] for row in rows) and all(closed['checks'].values())
    return {'passed': passed, 'reproduced_old_error': reproduced_old_error,
            'leaf_kernel_calls': len(rows), 'leaves': rows, 'closed': closed,
            'closed_gate': 'reachability and outcomes reported separately', 'workload': workload(state)}


def tests(state):
    if state['arm'] != 'candidate' or state['tests_done']:
        raise ValueError('tests_arm_or_repeat')
    state['tests_done'] = True
    state['qa'].verify_loaded()
    names = ('verification.test_perf030_002_pt_dual',) + REGRESSION_MODULES
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in names)
    log = io.StringIO()
    started = time.perf_counter_ns()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    source_identity(state, 'tests_complete')
    return {'passed': result.wasSuccessful() and result.testsRun == 159, 'tests_run': result.testsRun,
            'leaf_case_rechecks': 10,
            'expected_tests': 159, 'loader_errors': loader.errors,
            'failures': [{'test': str(test), 'traceback': detail} for test, detail in result.failures],
            'errors': [{'test': str(test), 'traceback': detail} for test, detail in result.errors],
            'skipped': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
            'log': log.getvalue(), 'elapsed_ns': time.perf_counter_ns() - started}


def json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {'nonfinite_float': repr(value)}
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def emit(value):
    blob = json.dumps(json_value(value), allow_nan=False, separators=(',', ':'))
    sys.stdout.write(blob + '\n')
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--qa-root', required=True)
    parser.add_argument('--runtime-manifest', required=True)
    parser.add_argument('--qa-manifest', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--arm', required=True, choices=('baseline', 'candidate'))
    args = parser.parse_args()
    startup_output = io.StringIO()
    try:
        with redirect_stdout(startup_output), redirect_stderr(startup_output):
            state = initialize(args)
            ready = {'event': 'ready', 'arm': args.arm, 'identity': source_identity(state, 'ready'),
                     'qa_identity': qa_identity(state),
                     'external_dependencies': external_dependencies(state['runtime_root'], state['qa_root']),
                     'costs': {'startup_ns': time.perf_counter_ns() - WORKER_STARTED_NS}}
        ready['captured_output'] = startup_output.getvalue()
        emit(ready)
    except Exception as exc:
        emit({'event': 'error', 'kind': 'source_identity_failure', 'exception': exception_record(exc),
              'captured_output': startup_output.getvalue()})
        return 1
    for line in sys.stdin:
        request = {}
        captured = io.StringIO()
        try:
            request = json.loads(line)
            operation = request['op']
            if operation == 'finish':
                result = {'identity': source_identity(state, 'finish'), 'qa_identity': qa_identity(state),
                          'ledger': state['ledger'],
                          'external_dependencies': external_dependencies(state['runtime_root'], state['qa_root']),
                          'costs': {'worker_lifetime_ns': time.perf_counter_ns() - WORKER_STARTED_NS}}
                emit({'event': 'finished', 'op': operation, 'request_id': request.get('request_id'), 'result': result})
                return 0
            with redirect_stdout(captured), redirect_stderr(captured):
                if operation == 'probes':
                    result = probes(state)
                elif operation == 'tests':
                    result = tests(state)
                elif operation == 'sample':
                    result = sample(state, request)
                else:
                    raise ValueError('unknown_worker_operation')
            if captured.getvalue():
                result['captured_output'] = captured.getvalue()
            emit({'event': 'result', 'op': operation, 'request_id': request.get('request_id'), 'result': result})
        except Exception as exc:
            emit({'event': 'error', 'op': request.get('op'), 'request_id': request.get('request_id'),
                  'kind': 'source_identity_failure' if identity_failure(exc) else 'operation_failure',
                  'exception': exception_record(exc), 'captured_output': captured.getvalue()})
            return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
