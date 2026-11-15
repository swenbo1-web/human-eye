"""Fixed scalar/Fraction camera checks, without hosts, images or raster calls."""

import argparse
import ast
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE_GIT = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
VIEW_ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
U = Fraction(1, 2**53)
ETA = Fraction(1, 2**1074)
GAMMA6 = 6 * U / (1 - 6 * U)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def git_blob(relative):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE_GIT + ':' + relative])


def camera_namespace(raw, name):
    selected = {'BlenderHostError', '_vector', '_dot', '_cross', '_norm',
                '_observation_affine_interval', '_observation_target_cameras'}
    nodes = []
    for node in ast.parse(raw.decode('utf-8')).body:
        extra_exception = (isinstance(node, ast.ClassDef)
                           and any(isinstance(base, ast.Name) and base.id == 'BlenderHostError' for base in node.bases))
        if getattr(node, 'name', None) in selected or extra_exception:
            nodes.append(node)
    namespace = {'math': math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), name, 'exec'), namespace)
    return namespace


def coverage_core(raw):
    module = types.ModuleType('_frozen_camera_reliability_coverage_core')
    sys.modules[module.__name__] = module
    exec(compile(raw, BASELINE_GIT + ':active_observation.py', 'exec'), module.__dict__)
    return module


def exact_affine(matrix, point):
    return tuple(sum(Fraction(matrix[row][axis]) * point[axis] for axis in range(3))
                 + Fraction(matrix[row][3]) for row in range(3))


def affine_error(matrix, point, input_error):
    exact = exact_affine(matrix, point)
    errors = []
    for row in range(3):
        propagated = sum(abs(Fraction(matrix[row][axis])) * input_error[axis] for axis in range(3))
        magnitude = sum(abs(Fraction(matrix[row][axis])) * (abs(point[axis]) + input_error[axis])
                        for axis in range(3)) + abs(Fraction(matrix[row][3]))
        errors.append(propagated + GAMMA6 * magnitude + 6 * ETA)
    return exact, tuple(errors)


def rounded_affine(matrix, point, order, fused):
    if fused:
        return tuple(float(value) for value in exact_affine(matrix, tuple(map(Fraction, point))))
    values = []
    for row in range(3):
        value = 0.
        for axis in order:
            value += matrix[row][axis] * point[axis]
        values.append(value + matrix[row][3])
    return tuple(values)


def inspect_matrices(points, cameras):
    if cameras['schema'] != 'active-coverage-target-cameras-v1':
        raise ValueError('wrong target camera schema')
    if [pose['name'] for pose in cameras['views']] != list(VIEW_ORDER):
        raise ValueError('wrong fixed six-view order')
    views = []
    permutations = tuple(itertools.permutations(range(3)))
    for pose in cameras['views']:
        exact_values, lower, upper = [], [], []
        runtime_checked = 0
        runtime_inside = True
        for point in points:
            exact_point = tuple(map(Fraction, point))
            camera, error = affine_error(pose['view_matrix'], exact_point, (Fraction(0),) * 3)
            ndc, ndc_error = affine_error(pose['projection_matrix'], camera, error)
            exact_values.append(ndc)
            lower.append(tuple(value - uncertainty for value, uncertainty in zip(ndc, ndc_error)))
            upper.append(tuple(value + uncertainty for value, uncertainty in zip(ndc, ndc_error)))
            for first_order, second_order in itertools.product(permutations, repeat=2):
                for first_fused, second_fused in itertools.product((False, True), repeat=2):
                    cam = rounded_affine(pose['view_matrix'], point, first_order, first_fused)
                    projected = rounded_affine(pose['projection_matrix'], cam, second_order, second_fused)
                    runtime_checked += 1
                    runtime_inside &= all(math.isfinite(value) and -1 <= value <= 1 for value in projected) and cam[2] < 0
        exact_inside = all(all(-1 <= value <= 1 for value in point) for point in exact_values)
        bounded_inside = all(all(-1 <= lo and hi <= 1 for lo, hi in zip(a, b)) for a, b in zip(lower, upper))
        views.append({'name': pose['name'], 'exact_inside': exact_inside,
                      'runtime_gamma6_enclosure_inside': bounded_inside,
                      'scalar_runtime_variants_inside': bool(runtime_inside),
                      'scalar_runtime_sequences_checked': runtime_checked,
                      'exact_min_ndc': [str(min(point[axis] for point in exact_values)) for axis in range(3)],
                      'exact_max_ndc': [str(max(point[axis] for point in exact_values)) for axis in range(3)],
                      'gamma6_min_ndc': [str(min(point[axis] for point in lower)) for axis in range(3)],
                      'gamma6_max_ndc': [str(max(point[axis] for point in upper)) for axis in range(3)],
                      'span': pose['span']})
    return views


def evaluate(namespace, core, case, role):
    try:
        cameras = namespace['_observation_target_cameras'](case['world_vertices'], case['world_bounds'])
    except ValueError as error:
        explicit = 'numeric_insufficient' in str(error)
        allowed = role == 'candidate' and case['id'] == 'reachable_binary32' and explicit
        return {'id': case['id'], 'passed': allowed, 'outcome': 'numeric_insufficient' if explicit else 'unexpected_rejection',
                'error_type': type(error).__name__, 'error': str(error),
                'capability_restored': False, 'cameras_returned': False}
    views = inspect_matrices(case['world_vertices'], cameras)
    classifications = None
    region_count = None
    if case['check_exact_coverage']:
        objects, triangles, identity = core.geometry({'objects': [{'name': case['id'],
            'vertices': case['world_vertices'], 'triangles': case['faces']}]})
        session = core.prepare_scene_from_parsed(objects, triangles, identity, cameras, target_object_index=0)
        classifications = session.index.classifications
        region_count = len(session.regions)
    valid = all(row['exact_inside'] and row['runtime_gamma6_enclosure_inside']
                and row['scalar_runtime_variants_inside'] for row in views)
    left = next(row for row in views if row['name'] == 'LEFT')
    if role == 'old' and case['id'] == 'reachable_binary32':
        passed = (region_count == 1 and list(classifications['LEFT'].values())[0]['status'] == 'outside_frustum'
                  and float(Fraction(left['exact_max_ndc'][1])) == 1.4452000066471393)
    else:
        passed = valid
        if case['check_exact_coverage']:
            passed &= region_count == 1 and list(classifications['LEFT'].values())[0]['complete'] is True
    return {'id': case['id'], 'passed': bool(passed), 'outcome': 'accepted_fitted' if valid else 'accepted_not_reliably_fitted',
            'cameras_returned': True, 'capability_restored': role == 'candidate' and case['id'] == 'reachable_binary32' and valid,
            'views': views, 'region_count': region_count, 'classifications': classifications,
            'camera_specification': cameras}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--role', choices=('old', 'candidate'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs_path = HERE / 'INPUTS.json'
    inputs = json.loads(inputs_path.read_bytes())
    freeze = json.loads((HERE / 'INPUT_FREEZE.json').read_bytes())
    assert sha(inputs_path.read_bytes()) == freeze['inputs_sha256']
    raw = args.source.read_bytes()
    core_raw = git_blob('human_eye_plugin/active_observation.py')
    assert sha(core_raw) == inputs['baseline_core_sha256']
    namespace = camera_namespace(raw, str(args.source))
    core = coverage_core(core_raw)
    records = [evaluate(namespace, core, case, args.role) for case in inputs['camera_cases']]
    result = {'schema': 'target-camera-reliability-numeric-v1', 'role': args.role,
              'source_path': str(args.source.resolve()), 'source_sha256': sha(raw),
              'input_sha256': freeze['inputs_sha256'], 'oracle_sha256': sha(Path(__file__).read_bytes()),
              'baseline_core_sha256': sha(core_raw), 'case_count': len(records),
              'records': records, 'passed': all(row['passed'] for row in records),
              'independent_oracle': 'Exact Fraction projection of the published matrices and gamma6 propagation for two binary64 affine stages, plus separate scalar sum-order/fused controls.',
              'counterexample_outcomes': 'accepted reliable fit and explicit numeric_insufficient are separate outcomes',
              'Blender_starts': 0, 'raster_calls': 0, 'model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'cases': len(records),
                      'outcomes': [{'id': row['id'], 'passed': row['passed'], 'outcome': row['outcome']} for row in records]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
