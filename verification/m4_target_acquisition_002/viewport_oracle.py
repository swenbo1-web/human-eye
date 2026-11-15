"""Independent Fraction/rounding-tree oracle for the fixed viewport predicate."""

import argparse
import ast
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rounded_interval(low, high):
    try:
        a, b = float(low), float(high)
    except OverflowError:
        return None
    if not math.isfinite(a) or not math.isfinite(b):
        return None
    if F(a) > low:
        a = math.nextafter(a, -math.inf)
    if F(b) < high:
        b = math.nextafter(b, math.inf)
    return (F(a), F(b)) if math.isfinite(a) and math.isfinite(b) else None


def affine_tree(matrix, intervals):
    """Enclose all four-term sum trees, including exact products in each term."""
    output = []
    for row in matrix[:3]:
        terms = []
        for coefficient, (low, high) in zip(row[:3], intervals):
            values = (F(coefficient)*low, F(coefficient)*high)
            interval = rounded_interval(min(values), max(values))
            if interval is None:
                return None
            terms.append(interval)
        terms.append((F(row[3]), F(row[3])))
        bounds = {1 << index: interval for index, interval in enumerate(terms)}
        for size in (2, 3, 4):
            for mask in range(1, 16):
                if mask.bit_count() != size:
                    continue
                possibilities = []
                first = (mask - 1) & mask
                while first:
                    second = mask ^ first
                    if second and first < second:
                        left, right = bounds[first], bounds[second]
                        value = rounded_interval(left[0]+right[0], left[1]+right[1])
                        if value is None:
                            return None
                        possibilities.append(value)
                    first = (first - 1) & mask
                bounds[mask] = (min(row[0] for row in possibilities), max(row[1] for row in possibilities))
        output.append(bounds[15])
    return output


def projected_enclosure(bounds, pose):
    if bounds is None:
        return None
    try:
        if (len(bounds) != 2 or any(len(row) != 3 for row in bounds)
                or any(type(value) not in (int, float) or not math.isfinite(value) for row in bounds for value in row)
                or any(low > high for low, high in zip(*bounds))):
            return None
        initial = [(F(low), F(high)) for low, high in zip(*bounds)]
        camera = affine_tree(pose['view_matrix'], initial)
        if camera is None:
            return None
        ndc = affine_tree(pose['projection_matrix'], camera)
        return None if ndc is None else ndc[:2]
    except (ValueError, TypeError, IndexError, OverflowError):
        return None


def outside(bounds, cameras):
    rows = []
    for pose in cameras['views']:
        enclosure = projected_enclosure(bounds, pose)
        separated = enclosure is not None and any(high < -1 or low > 1 for low, high in enclosure)
        rows.append({'view': pose['name'], 'strict_separation': bool(separated),
                     'ndc_xy_enclosure': None if enclosure is None else [[str(a), str(b)] for a, b in enclosure]})
    return all(row['strict_separation'] for row in rows), rows


def prepare():
    capture_path = Path('D:/he_m4_target_002/qualification/A_main/MAIN_CAPTURE_01.json')
    capture = json.loads(capture_path.read_bytes())
    cameras = capture['observation_target']['camera_plan']
    top = next(pose for pose in cameras['views'] if pose['name'] == 'TOP')
    boundary = float(F(1)/F(top['projection_matrix'][0][0])-F(top['view_matrix'][0][3]))
    far = next(row for row in capture['observation_target']['scene_directory'] if row['name'] == 'M4_Far_11')
    cases = [
        {'id': 'actual_Far11', 'bounds': far['bounds_world_m'], 'expected_outside': True,
         'reason': 'Independent frozen six-direction strict separation, actual A directory bounds.'},
        {'id': 'near_panel', 'bounds': [[1.1, .1, 2.1], [1.9, .9, 2.2]], 'expected_outside': False},
        {'id': 'rear_depth_only', 'bounds': [[1.1, .1, -1000.], [1.9, .9, -999.]], 'expected_outside': False},
        {'id': 'cross_viewport_triangle', 'bounds': [[-1., -2., 2.], [4., 3., 2.]],
         'triangle': [[-1., -2., 2.], [4., -2., 2.], [1.5, 3., 2.]], 'expected_outside': False},
        {'id': 'unsupported_triangle_occluder', 'bounds': [[1., 0., 2.1], [2., 1., 2.1]],
         'triangle': [[1., 0., 2.1], [2., 0., 2.1], [1., 1., 2.1]], 'expected_outside': False},
        {'id': 'unknown_bbox', 'bounds': None, 'expected_outside': False},
        {'id': 'nonfinite_bbox', 'bounds_kind': 'infinite', 'expected_outside': False},
        {'id': 'inverted_bbox', 'bounds': [[2., 2., 2.], [1., 1., 1.]], 'expected_outside': False},
        {'id': 'equal_depth_earlier', 'bounds': [[1., 0., 2.], [2., 1., 2.]], 'expected_outside': False},
        {'id': 'equal_depth_later', 'bounds': [[1., 0., 2.], [2., 1., 2.]], 'expected_outside': False},
    ]
    for name, x in (('touch_nearest_float', boundary), ('touch_plus_ulp', math.nextafter(boundary, math.inf)),
                    ('touch_minus_ulp', math.nextafter(boundary, -math.inf))):
        cases.append({'id': name, 'bounds': [[x, .25, 2.], [x+.125, .75, 2.]], 'expected_outside': False})
    local = [(0., 0., 0.), (2., 0., 0.), (0., 2., 0.)]
    rotated = [[.6*x-.8*y+2.16, .8*x+.6*y+.225, 2.] for x, y, z in local]
    cases.append({'id': 'rotated_nonbox', 'vertices_world': rotated,
                  'bounds': [[min(p[k] for p in rotated) for k in range(3)],
                             [max(p[k] for p in rotated) for k in range(3)]], 'expected_outside': False})
    for case in cases:
        bounds = [[math.inf, 0., 0.], [math.inf, 1., 1.]] if case.get('bounds_kind') == 'infinite' else case.get('bounds')
        actual, _ = outside(bounds, cameras)
        assert actual is case['expected_outside'], case['id']
    output = {'schema': 'target-002-fixed-viewport-inputs-v1', 'camera_source': str(capture_path),
              'camera_source_sha256': sha(capture_path), 'camera_plan': cameras, 'cases': cases,
              'geometry_sha256': sha(HERE / 'reference/FROZEN_GEOMETRY.json'),
              'oracle_source_sha256': sha(Path(__file__)),
              'scope': 'Fixed boundary controls. Equal-depth cases establish retention and original ordering, not a new raster test.'}
    with (HERE / 'B_NUMERIC_INPUTS.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.prepare:
        data = prepare()
        print(json.dumps({'prepared_cases': len(data['cases']), 'inputs_sha256': sha(HERE / 'B_NUMERIC_INPUTS.json')}))
        return
    data = json.loads((HERE / 'B_NUMERIC_INPUTS.json').read_bytes())
    raw = args.source.read_bytes()
    names = {'_observation_outside_xy_viewports', '_observation_affine_interval'}
    nodes = [node for node in ast.parse(raw).body if getattr(node, 'name', None) in names]
    namespace = {'math': math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(args.source), 'exec'), namespace)
    records = []
    for case in data['cases']:
        bounds = [[math.inf, 0., 0.], [math.inf, 1., 1.]] if case.get('bounds_kind') == 'infinite' else case.get('bounds')
        expected, proof = outside(bounds, data['camera_plan'])
        actual, tests = namespace['_observation_outside_xy_viewports'](bounds, data['camera_plan'])
        assert type(actual) is bool and type(tests) is int and 0 <= tests <= 6
        assert actual is expected is case['expected_outside'], case['id']
        if actual:
            assert tests == 6
        records.append({'case': case['id'], 'actual_outside': actual, 'actual_view_tests': tests,
                        'independent_rounding_tree_proof': proof, 'passed': True})
    output = {'schema': 'target-002-independent-viewport-check-v1', 'passed_checked_scope': True,
              'source_sha256': hashlib.sha256(raw).hexdigest(), 'input_sha256': sha(HERE / 'B_NUMERIC_INPUTS.json'),
              'oracle_source_sha256': sha(Path(__file__)), 'case_count': len(records), 'records': records,
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'cases': len(records)}))


if __name__ == '__main__':
    main()
