"""Independent scalar checks of target-camera and conservative viewport helpers.

This file never constructs a host, scene observer, image, or raster.  The oracle
treats stored binary64 inputs as exact rationals and separately exercises the
two affine floating-point stages used by the existing renderer.
"""

import argparse
import copy
from fractions import Fraction
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VIEW_ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
DIRECTIONS = ((4, -4, 3), (0, 0, 1), (-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1))
IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def corners(bounds):
    return tuple(itertools.product(*zip(bounds[0], bounds[1])))


def exact_affine(matrix, point):
    return tuple(sum(Fraction(matrix[row][axis]) * Fraction(point[axis]) for axis in range(3))
                 + Fraction(matrix[row][3]) for row in range(3))


def exact_project(bounds, pose):
    values = [exact_affine(pose['projection_matrix'], exact_affine(pose['view_matrix'], point))
              for point in corners(bounds)]
    return [[min(point[axis] for point in values) for axis in range(2)],
            [max(point[axis] for point in values) for axis in range(2)]]


def float_affine(matrix, point, permutation, fused):
    values = []
    for row in range(3):
        if fused:
            value = float(sum(Fraction(matrix[row][axis]) * Fraction(point[axis]) for axis in range(3))
                          + Fraction(matrix[row][3]))
        else:
            value = 0.
            for axis in permutation:
                value += matrix[row][axis] * point[axis]
            value += matrix[row][3]
        values.append(value)
    return values


def enclosure_check(bounds, pose, actual):
    if actual is None:
        return {'status': 'unknown_retained', 'exact_points': 8}
    assert len(actual) == 2 and all(len(row) == 2 for row in actual)
    assert all(math.isfinite(value) for row in actual for value in row)
    exact = exact_project(bounds, pose)
    for axis in range(2):
        assert Fraction(actual[0][axis]) <= exact[0][axis]
        assert Fraction(actual[1][axis]) >= exact[1][axis]
    variants = 0
    for point in corners(bounds):
        for permutation in itertools.permutations(range(3)):
            for fused in (False, True):
                intermediate = float_affine(pose['view_matrix'], point, permutation, fused)
                projected = float_affine(pose['projection_matrix'], intermediate, permutation, fused)
                if all(math.isfinite(value) for value in projected):
                    assert all(actual[0][axis] <= projected[axis] <= actual[1][axis] for axis in range(2))
                    variants += 1
    return {'status': 'enclosed', 'exact_points': 8, 'float_sequences_checked': variants,
            'oracle_xy': [[str(value) for value in row] for row in exact], 'actual_xy': actual}


def synthetic_cameras():
    return {'schema': 'active-coverage-target-cameras-v1', 'views': [
        {'name': name, 'view_matrix': copy.deepcopy(IDENTITY), 'projection_matrix': copy.deepcopy(IDENTITY),
         'size_px': [512, 512], 'direction_rational': list(direction)}
        for name, direction in zip(VIEW_ORDER, DIRECTIONS)]}


def projected_cases():
    identity = synthetic_cameras()['views'][0]
    rotated = copy.deepcopy(identity)
    rotated['view_matrix'] = [[.6, -.8, 0., 17.], [.8, .6, 0., -23.],
                              [0., 0., 1., 4.], [0., 0., 0., 1.]]
    rotated['projection_matrix'] = [[.125, 0., 0., .25], [0., .125, 0., -.5],
                                    [0., 0., .01, 0.], [0., 0., 0., 1.]]
    cancellation = copy.deepcopy(rotated)
    cancellation['view_matrix'][0] = [1., -1., 0., math.nextafter(1., math.inf)]
    cancellation['view_matrix'][1] = [1., 1., -2., -1.]
    return [
        ('identity_regular', [[-2., -3., -4.], [5., 6., 7.]], identity),
        ('identity_touching', [[1., -.5, 0.], [2., .5, 0.]], identity),
        ('one_ulp_outside', [[math.nextafter(1., math.inf), -.5, 0.], [2., .5, 0.]], identity),
        ('one_ulp_inside', [[math.nextafter(1., -math.inf), -.5, 0.], [2., .5, 0.]], identity),
        ('rotated_nonbox_enclosure', [[-2., -.25, 0.], [1., 3., .125]], rotated),
        ('large_cancellation', [[2.**48, 2.**48, 2.**48], [2.**48 + 1, 2.**48 + 2, 2.**48 + 4]], cancellation),
        ('tiny_coordinates', [[-2.**-1020, 0., -2.**-1020], [2.**-1020, 2.**-1020, 0.]], rotated),
        ('subnormal_coordinates', [[0., 0., 0.], [math.ulp(0.), math.ulp(0.), math.ulp(0.)]], identity),
        ('very_large_finite', [[-2.**900, -2.**900, -2.**900], [2.**900, 2.**900, 2.**900]], identity),
    ]


def exact_triangle_contains(triangle, point):
    def determinant(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1])
                - (b[1] - a[1]) * (c[0] - a[0]))
    signs = [determinant(triangle[index], triangle[(index + 1) % 3], point) for index in range(3)]
    return all(value >= 0 for value in signs) or all(value <= 0 for value in signs)


def analytic_reference_cases():
    big_triangle = ((Fraction(-3), Fraction(-3)), (Fraction(3), Fraction(-3)), (Fraction(0), Fraction(3)))
    small_square = tuple(itertools.product((Fraction(-1, 2), Fraction(1, 2)), repeat=2))
    assert all(exact_triangle_contains(big_triangle, point) for point in small_square)
    return [
        {'case': 'near_panel', 'target_z': 0, 'occluder_z': 1,
         'projected_target_square': ['-1/2', '1/2'], 'projected_panel_square': [-1, 1],
         'independent_answer': 'TOP has positive-area occlusion; the eye must be in front of both surfaces'},
        {'case': 'side_or_rear', 'independent_answer': 'retain whenever any viewport overlaps, regardless of relative depth'},
        {'case': 'cross_viewport_triangle', 'triangle_xy': [[str(value) for value in point] for point in big_triangle],
         'independent_answer': 'all three vertices are outside the unit viewport, yet its center and the target square are covered'},
        {'case': 'unsupported_target', 'geometry': 'one isolated nondegenerate triangle',
         'independent_answer': 'no rectangular target region, target status remains unknown'},
        {'case': 'unsupported_occluder', 'geometry': 'a nonrectangular triangle in front of the target',
         'independent_answer': 'the triangle continues to occlude, even though it creates no supported region'},
        {'case': 'self_occlusion', 'geometry': 'one target object with equal XY squares at z=0 and z=1',
         'independent_answer': 'the upper component occludes the lower component in TOP; only each current region own triangles are exempt'},
        {'case': 'equal_depth', 'geometry': 'two identical ordered triangles at the same depth',
         'independent_answer': 'earlier object and earlier local face retain the depth winner'},
    ]


def run(module, phase):
    records = []

    def record(name, check, *, camera_safe=False):
        if phase == 'camera' and not camera_safe:
            records.append({'case': name, 'executed': False, 'passed': None,
                            'reason': 'selective B helper is outside the frozen A implementation'})
            return
        try:
            details = check()
            records.append({'case': name, 'executed': True, 'passed': True, 'details': details})
        except Exception as error:
            records.append({'case': name, 'executed': True, 'passed': False,
                            'error_type': type(error).__name__, 'error': str(error)})

    for name, bounds, pose in projected_cases():
        def affine_check(bounds=bounds, pose=pose):
            checked = 0
            for axis in range(3):
                coefficients = pose['view_matrix'][axis][:3]
                translation = pose['view_matrix'][axis][3]
                interval = module._observation_affine_interval(bounds, coefficients, translation)
                if interval is None:
                    continue
                exact = [exact_affine(pose['view_matrix'], point)[axis] for point in corners(bounds)]
                assert Fraction(interval[0]) <= min(exact)
                assert Fraction(interval[1]) >= max(exact)
                for point in corners(bounds):
                    for order in itertools.permutations(range(3)):
                        for fused in (False, True):
                            value = float_affine(pose['view_matrix'], point, order, fused)[axis]
                            if math.isfinite(value):
                                assert interval[0] <= value <= interval[1]
                                checked += 1
            return {'scalar_float_sequences_checked': checked,
                    'oracle': 'exact rational corner extrema plus separately rounded/fused scalar sums'}
        record('affine_' + name, affine_check, camera_safe=True)

    for name, bounds, pose in projected_cases():
        record('projection_' + name, lambda bounds=bounds, pose=pose:
               enclosure_check(bounds, pose, module._observation_viewport_bounds(bounds, pose)))

    cameras = synthetic_cameras()

    def retention(bounds):
        assert module._observation_outside_views(bounds, cameras) is False
        return {'outside_all_views': False}

    for name, bounds in [
        ('crossing_big_triangle_box', [[-3., -3., 0.], [3., 3., 0.]]),
        ('touching_right_edge', [[1., -.25, 0.], [2., .25, 0.]]),
        ('one_ulp_outside_uncertain', [[math.nextafter(1., math.inf), -.25, 0.], [2., .25, 0.]]),
        ('behind_with_xy_overlap', [[-.25, -.25, -1e100], [.25, .25, -1e99]]),
        ('unknown_bounds', None),
    ]:
        record('retain_' + name, lambda bounds=bounds: retention(bounds))

    def clear_separation():
        assert module._observation_outside_views([[2., 2., 0.], [3., 3., 0.]], cameras) is True
        return {'six_views_strictly_separated': True}

    record('exclude_only_six_strict_separations', clear_separation)

    def one_view_overlap():
        altered = copy.deepcopy(cameras)
        altered['views'][3]['view_matrix'][0][3] = -2.5
        altered['views'][3]['view_matrix'][1][3] = -2.5
        assert module._observation_outside_views([[2., 2., 0.], [3., 3., 0.]], altered) is False
        return {'overlapping_view': 'RIGHT', 'other_views_separated': 5}

    record('retain_one_of_six_viewports', one_view_overlap)

    regular_corners = [list(point) for point in corners([[-1., -1., 0.], [1., 1., 1.]])]
    unknown_boxes = [
        ('absent_box', []),
        ('incomplete_box', regular_corners[:-1]),
        ('unavailable_sentinel', [[-1., -1., -1.] for _ in range(8)]),
        ('nonfinite_box', [[math.nan, 0., 0.]] + regular_corners[1:]),
    ]
    for name, local_corners in unknown_boxes:
        def acquisition_unknown(local_corners=local_corners):
            assert module._acquisition_bounds(local_corners, IDENTITY, 1.) is None
            return {'coarse_bound_status': 'unknown'}
        record('acquisition_' + name, acquisition_unknown, camera_safe=True)
        def unknown_box(local_corners=local_corners):
            assert module._acquisition_bounds(local_corners, IDENTITY, 1.) is None
            assert module._observation_outside_views(None, cameras) is False
            return {'coarse_bound_status': 'unknown', 'object_retained': True}
        record('unknown_' + name, unknown_box)

    def projection_overflow():
        altered = copy.deepcopy(cameras)
        for pose in altered['views']:
            pose['projection_matrix'][0][0] = 4.
        extreme = [[sys.float_info.max / 2, 0., 0.], [sys.float_info.max, 1., 1.]]
        assert module._observation_viewport_bounds(extreme, altered['views'][0]) is None
        assert module._observation_outside_views(extreme, altered) is False
        return {'numeric_status': 'unknown', 'object_retained': True}

    record('overflow_is_unknown_and_retained', projection_overflow)

    def rotated_coarse_box():
        vertices = [[-2., -.25, 0.], [1., -.25, .125], [-.5, 3., 0.]]
        local = [[min(point[k] for point in vertices) for k in range(3)],
                 [max(point[k] for point in vertices) for k in range(3)]]
        matrix = [[.6, -.8, 0., 17.], [.8, .6, 0., -23.],
                  [0., 0., 1., 4.], [0., 0., 0., 1.]]
        actual = module._acquisition_bounds([list(point) for point in corners(local)], matrix, .125)
        assert actual is not None
        for vertex in vertices:
            exact = [value * Fraction(1, 8) for value in exact_affine(matrix, vertex)]
            assert all(Fraction(actual[0][axis]) <= exact[axis] <= Fraction(actual[1][axis]) for axis in range(3))
        return {'shape': 'nonbox triangle', 'true_vertices_enclosed': len(vertices),
                'tight_bounds_not_assumed': True}

    record('rotated_nonbox_coarse_bounds_cover_real_vertices', rotated_coarse_box, camera_safe=True)

    def fitted_camera():
        target = [[-1., -1., 0.], [1., -1., 0.], [1., 1., 0.], [-1., 1., 0.]]
        source_bounds = [[[-4., -5., -6.], [7., 8., 9.]], [[100., 100., 100.], [101., 101., 101.]]]
        actual = module._observation_target_cameras(target, source_bounds)
        assert actual['schema'] == 'active-coverage-target-cameras-v1'
        assert [pose['name'] for pose in actual['views']] == list(VIEW_ORDER)
        for pose, direction in zip(actual['views'], DIRECTIONS):
            assert pose['size_px'] == [512, 512]
            assert pose['direction_rational'] == list(direction)
            for point in target:
                camera = exact_affine(pose['view_matrix'], point)
                projected = exact_affine(pose['projection_matrix'], camera)
                assert all(-1 < projected[axis] < 1 for axis in range(2))
            for bounds in source_bounds:
                for point in corners(bounds):
                    depth = -exact_affine(pose['view_matrix'], point)[2]
                    assert depth > Fraction(pose['near']) and depth < Fraction(pose['far'])
            center = actual['common_center_world_m']
            half = max(abs(sum(Fraction(pose['view_matrix'][axis][index])
                               * (Fraction(point[index]) - Fraction(center[index])) for index in range(3)))
                       for point in target for axis in range(2))
            expected_span = float(half * Fraction(11, 5))
            assert math.isclose(pose['span'], expected_span, rel_tol=0,
                                abs_tol=max(128 * math.ulp(expected_span), 128 * math.ulp(pose['span'])))
        reversed_bounds = module._observation_target_cameras(target, list(reversed(source_bounds)))
        assert actual == reversed_bounds
        depth_changed = module._observation_target_cameras(target, [source_bounds[0]])
        assert depth_changed['common_center_world_m'] == actual['common_center_world_m']
        for first, second in zip(actual['views'], depth_changed['views']):
            assert first['span'] == second['span']
            assert [row[:3] for row in first['view_matrix'][:3]] == [row[:3] for row in second['view_matrix'][:3]]
        return {'view_count': 6, 'all_scene_depth_corners': 16,
                'target_fit_uses_target_vertices': True, 'bound_order_invariant': True,
                'scene_bounds_do_not_change_target_XY_fit': True}

    record('target_fit_scene_depth_and_bound_order', fitted_camera, camera_safe=True)

    def rotated_target_actual_vertex_fit():
        u, v = [1., 2., 0.], [-2., 1., 2.]
        target = [[first * u[k] + second * v[k] for k in range(3)]
                  for first, second in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        target_box = [[min(point[k] for point in target) for k in range(3)],
                      [max(point[k] for point in target) for k in range(3)]]
        actual = module._observation_target_cameras(target, [target_box])
        bbox_would_expand = []
        for pose in actual['views']:
            center = actual['common_center_world_m']
            def projected_half(points):
                return max(abs(sum(Fraction(pose['view_matrix'][axis][k])
                                   * (Fraction(point[k]) - Fraction(center[k])) for k in range(3)))
                           for point in points for axis in range(2))
            true_half = projected_half(target)
            bbox_half = projected_half(corners(target_box))
            expected_span = float(true_half * Fraction(11, 5))
            assert math.isclose(pose['span'], expected_span, rel_tol=0,
                                abs_tol=max(128 * math.ulp(expected_span), 128 * math.ulp(pose['span'])))
            if bbox_half > true_half:
                bbox_would_expand.append(pose['name'])
        assert bbox_would_expand
        return {'target': 'rotated rational rectangular patch',
                'AABB_substitution_changes_views': bbox_would_expand,
                'actual_vertices_used': len(target)}

    record('rotated_target_uses_actual_vertices_not_world_AABB', rotated_target_actual_vertex_fit, camera_safe=True)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'human_eye_plugin/blender_host.py')
    parser.add_argument('--phase', choices=('camera', 'selective'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    spec = importlib.util.spec_from_file_location('_target_numeric_host_helpers', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = run(module, args.phase)
    result = {'schema': 'm4-target-independent-numeric-checks-v1', 'host_source': str(source),
              'host_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'phase': args.phase, 'records': records,
              'passed': any(row['executed'] for row in records) and all(row['passed'] for row in records if row['executed']),
              'analytic_references': analytic_reference_cases(),
              'analytic_product_semantics_status': 'awaits saved actual qualification evidence',
              'oracle_limitations': ['Fraction validates the affine real-arithmetic enclosure.',
                                     'Scalar sum-order/fused simulations are directed numerical controls, not an exhaustive proof of every BLAS implementation.',
                                     'No raster, rendering, host construction, or scene observation is executed.'],
              'Blender_starts': 0, 'raster_calls': 0, 'model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'executed_cases': sum(row['executed'] for row in records),
                      'not_run_cases': sum(not row['executed'] for row in records),
                      'failures': [row for row in records if row['passed'] is False]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
