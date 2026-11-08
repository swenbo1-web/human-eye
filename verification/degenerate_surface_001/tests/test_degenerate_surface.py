"""Twelve preregistered groups; independent Fraction convex-QP oracle.

No production primitive participates in the oracle. For each pair of one-face
convex hulls, enumerate nonempty vertex supports and solve the constrained
quadratic stationarity system by exact Gaussian elimination. Singular supports
are discarded: a minimum has a minimal affinely independent support. The test
meshes remain unions of individual faces, never their global convex hull.
"""
from decimal import Decimal, localcontext
from fractions import Fraction as F
import itertools
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_proximity as surface
from human_eye_plugin import task_query
from human_eye_plugin.live_service import RequestBudgetError
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification.test_concave_geometry import entity

# Parent loads the exact entry test bytes before these bytes. Reuse that module
# instead of re-importing a second test file through the filesystem importer.
entry = sys.modules.get('surface_nearest_entry_tests')
if entry is None:
    raise ImportError('Run through the verified parent loader after surface_nearest_entry_tests')


METHOD = 'exact_binary64_triangle_surface_hulls_v3'
NORMAL_VERSION = 'task-surface-proximity-exact-aabb-v3'
RANK_VERSION = 'task-surface-proximity-exact-world-rank-v2'
EVIDENCE = {}


def rational_point(point):
    return tuple(F.from_float(float(value)) for value in point)


def squared_norm(vector):
    return sum(value * value for value in vector)


def solve_linear(matrix, target):
    """Independent exact Gaussian elimination, returning None if singular."""
    rows = [[F(value) for value in row] + [F(value)]
            for row, value in zip(matrix, target)]
    size = len(rows)
    for column in range(size):
        pivot = next((i for i in range(column, size) if rows[i][column]), None)
        if pivot is None:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scale = rows[column][column]
        rows[column] = [value / scale for value in rows[column]]
        for i in range(size):
            if i != column and rows[i][column]:
                scale = rows[i][column]
                rows[i] = [x - scale * y for x, y in zip(rows[i], rows[column])]
    return [row[-1] for row in rows]


def hull_oracle(left, right):
    """Return exact d² and attaining points for actual represented inputs."""
    left = list(dict.fromkeys(rational_point(point) for point in left))
    right = list(dict.fromkeys(rational_point(point) for point in right))
    answers = []
    for na in range(1, len(left) + 1):
        for nb in range(1, len(right) + 1):
            for a in itertools.combinations(left, na):
                for b in itertools.combinations(right, nb):
                    columns = list(a) + [tuple(-x for x in point) for point in b]
                    count = na + nb
                    constraints = [[F(i < na) for i in range(count)],
                                   [F(i >= na) for i in range(count)]]
                    matrix = []
                    for i in range(count):
                        matrix.append([2 * sum(x * y for x, y in zip(columns[i], columns[j]))
                                       for j in range(count)]
                                      + [row[i] for row in constraints])
                    matrix.extend([row + [F(0), F(0)] for row in constraints])
                    weights = solve_linear(matrix, [F(0)] * count + [F(1), F(1)])
                    if weights is None or any(value < 0 for value in weights[:count]):
                        continue
                    pa = tuple(sum(weights[i] * a[i][k] for i in range(na)) for k in range(3))
                    pb = tuple(sum(weights[na+i] * b[i][k] for i in range(nb)) for k in range(3))
                    answers.append((squared_norm(tuple(x-y for x, y in zip(pa, pb))), pa, pb))
    if not answers:
        raise AssertionError('Independent hull oracle found no feasible support')
    return min(answers)


def union_oracle(left, right):
    return min(hull_oracle(left.vertices[face_a], right.vertices[face_b])
               for face_a in left.faces for face_b in right.faces)


def exact_key_value(result):
    numerator, denominator, exponent = result['_exact_distance_sq']
    value = F(numerator, denominator)
    return value * (1 << exponent) if exponent >= 0 else value / (1 << -exponent)


def rounded_root(value):
    with localcontext() as context:
        context.prec = 150
        return float((Decimal(value.numerator) / Decimal(value.denominator)).sqrt())


def triangle(identity, vertices):
    return entity(identity, vertices, [[0, 1, 2]])


def point(identity, value):
    return triangle(identity, [value] * 3)


def segment(identity, start, end, third=None):
    return triangle(identity, [start, end, start if third is None else third])


class DegenerateSurfaceTests(unittest.TestCase):
    def measure(self, left, right, *, checkpoint=None, diagnostics=None, retain_exact_rank=True):
        return surface.measure_surface_proximity(left, right, checkpoint or (lambda stage: None),
            diagnostics=diagnostics, retain_exact_rank=retain_exact_rank)

    def assert_pair(self, left, right, expected_sq=None, *, witness=True, both=True):
        oracle = union_oracle(left, right)
        if expected_sq is not None:
            self.assertEqual(oracle[0], F(expected_sq), 'analytic value and independent QP disagree')
        expected_sq = oracle[0]
        variants = ((left, right), (right, left)) if both else ((left, right),)
        results = []
        for a, b in variants:
            with self.subTest(order=(a.object_id, b.object_id)):
                result = self.measure(a, b)
                self.assertTrue(result['measurement_valid'], result)
                self.assertEqual(result['method'], METHOD)
                self.assertEqual(exact_key_value(result), expected_sq)
                self.assertEqual(result['distance_m'], rounded_root(expected_sq))
                if expected_sq == 0:
                    self.assertEqual(result['direction_status'], 'not_applicable')
                    self.assertIsNone(result['direction_a_to_b'])
                else:
                    self.assertGreater(result['distance_m'], 0)
                if witness:
                    self.assertEqual(result['witness_status'], 'measured', result)
                    pa, pb = result['point_a_world'], result['point_b_world']
                    self.assertTrue(all(math.isfinite(value) for p in (pa, pb) for value in p))
                    self.assertLessEqual(abs(math.dist(pa, pb) - result['distance_m']), 1e-9)
                    for p, mesh in ((pa, a), (pb, b)):
                        error_sq = min(hull_oracle([p], mesh.vertices[face])[0] for face in mesh.faces)
                        self.assertLessEqual(error_sq, F.from_float(1e-9) ** 2)
                results.append(result)
        return results[0]

    def test_g01_point_point_repetition_and_zero_direction(self):
        a = point('a', (1, 2, 3))
        b = point('b', (4, 6, 3))
        result = self.assert_pair(a, b, 25)
        self.assertEqual(result['work']['point_face_tests'], 0)
        self.assertEqual(result['work']['edge_edge_tests'], 0)
        self.assert_pair(a, point('b', (1, 2, 3)), 0)
        EVIDENCE['g01_point_work'] = result['work']

    def test_g02_point_segment_actual_hull_endpoints_all_vertex_orders(self):
        p = point('p', (2, 1, 0))
        vertices = [(0, 0, 0), (1, 0, 0), (3, 0, 0)]
        for order in itertools.permutations(vertices):
            with self.subTest(order=order):
                self.assert_pair(p, triangle('s', order), 1)
        for vertices in ([(0, 0, 0), (0, 0, 0), (3, 0, 0)],
                         [(3, 0, 0), (0, 0, 0), (3, 0, 0)]):
            self.assert_pair(point('p', (4, 1, 0)), triangle('s', vertices), 2)
        self.assert_pair(point('p', (2, 0, 0)), triangle('s', vertices), 0)

    def test_g03_point_triangle_interior_edge_vertex_and_zero(self):
        face = triangle('t', [(0, 0, 0), (2, 0, 0), (0, 2, 0)])
        for p, expected in (((.5, .5, 3), 9), ((1, -2, 0), 4),
                            ((-1, -1, 0), 2), ((.5, .5, 0), 0)):
            with self.subTest(point=p):
                self.assert_pair(point('p', p), face, expected)

    def test_g04_segment_segment_skew_parallel_crossing_and_collinear(self):
        a = segment('a', (-1, 0, 0), (1, 0, 0))
        cases = [
            (segment('b', (0, -1, 2), (0, 1, 2)), 4),
            (segment('b', (-2, 3, 0), (2, 3, 0)), 9),
            (segment('b', (0, -1, 0), (0, 1, 0)), 0),
            (segment('b', (0, 0, 0), (3, 0, 0)), 0),
            (segment('b', (1, 0, 0), (2, 0, 0)), 0),
            (segment('b', (3, 0, 0), (4, 0, 0)), 4),
        ]
        for b, expected in cases:
            with self.subTest(vertices=b.vertices.tolist()):
                self.assert_pair(a, b, expected)

    def test_g05_segment_pierces_face_interior_with_neither_endpoint_on_face(self):
        face = triangle('t', [(0, 0, 0), (2, 0, 0), (0, 2, 0)])
        for start, end in (((.5, .5, -1), (.5, .5, 1)),
                           ((-1, .5, -1), (2, .5, 1))):
            s = segment('s', start, end)
            self.assertGreater(hull_oracle([start], face.vertices)[0], 0)
            self.assertGreater(hull_oracle([end], face.vertices)[0], 0)
            result = self.assert_pair(s, face, 0)
            self.assertEqual(result['point_a_world'], result['point_b_world'])

    def test_g06_coplanar_crossing_and_parallel_offset_segment_face(self):
        face = triangle('t', [(0, 0, 0), (2, 0, 0), (0, 2, 0)])
        for z, expected in ((0, 0), (3, 9)):
            s = segment('s', (-1, .5, z), (3, .5, z))
            self.assertGreater(hull_oracle([s.vertices[0]], face.vertices)[0], 0)
            self.assertGreater(hull_oracle([s.vertices[1]], face.vertices)[0], 0)
            self.assert_pair(s, face, expected)
        self.assert_pair(segment('s', (-3, -1, 0), (-1, -1, 0)), face, 2)

    def test_g07_face_union_is_not_global_hull_and_normal_feature_work_is_unchanged(self):
        a = triangle('a', [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        b = triangle('b', [(0, 0, 1), (1, 0, 1), (0, 1, 1)])
        ordinary = self.assert_pair(a, b, 1)
        for key, expected in (('intersection_tests', 1), ('point_face_tests', 6),
                              ('point_edge_tests', 18), ('edge_edge_tests', 9)):
            self.assertEqual(ordinary['work'][key], expected)
        # Two separate retained point faces at x=-2,+2. Their mesh-wide convex
        # hull would contain p, but the original face union stays distance two.
        union = entity('u', [(-2, 0, 0)] * 3 + [(2, 0, 0)] * 3,
                       [[0, 1, 2], [3, 4, 5]])
        self.assert_pair(point('p', (0, 0, 0)), union, 4)
        # A late point face is retained: it lowers the first face's distance.
        mixed = entity('m', [(0, 0, 10), (1, 0, 10), (0, 1, 10),
                             (0, 0, 1), (0, 0, 1), (0, 0, 1)],
                       [[0, 1, 2], [3, 4, 5]])
        self.assert_pair(point('p', (0, 0, 0)), mixed, 1)
        EVIDENCE['g07_ordinary_work'] = ordinary['work']

    def test_g08_large_translation_and_rotation_use_actual_binary64_coordinates(self):
        base_a = np.array([(0, 0, 0), (2, 0, 0), (1, 0, 0)], dtype=float)
        base_b = np.array([(1, 1, 0)] * 3, dtype=float)
        # First matrix is five times an orthogonal rotation, exactly integral.
        transforms = [np.array([[3., 0, 4], [0, 5., 0], [-4., 0, 3.]]),
                      np.array([[math.cos(.71), -math.sin(.71), 0],
                                [math.sin(.71), math.cos(.71), 0], [0, 0, 1.]])]
        for transform, offset in ((transforms[0], np.array([2.**40, -2.**40, 2.**40])),
                                  (transforms[1], np.array([2.**25, -2.**25, 2.**25]))):
            a = triangle('a', base_a @ transform.T + offset)
            b = triangle('b', base_b @ transform.T + offset)
            # Rounding can make intended collinearity nonzero; the oracle
            # receives the actual arrays, with no rank snap or intended truth.
            expected = union_oracle(a, b)[0]
            result = self.assert_pair(a, b, expected, witness=False)
            EVIDENCE.setdefault('g08_actual_binary64', []).append(dict(
                left=a.vertices.tolist(), right=b.vertices.tolist(),
                squared_numerator=expected.numerator, squared_denominator=expected.denominator,
                witness_status=result['witness_status']))

    def test_g09_nearly_collinear_nonzero_face_and_tiny_positive_segment_gap(self):
        epsilon = 2.**-40
        skinny = triangle('t', [(0, 0, 0), (1, 0, 0), (0, epsilon, 0)])
        p = point('p', (.25, epsilon / 4, epsilon / 2))
        result = self.assert_pair(p, skinny, F.from_float(epsilon / 2) ** 2)
        self.assertGreater(result['work']['point_face_tests'], 0)
        for gap in (2.**-40, 2.**-600):
            a = segment('a', (0, 0, 0), (1, 0, 0))
            b = point('b', (.5, gap, 0))
            self.assert_pair(a, b, F.from_float(gap) ** 2)

    def test_g10_invalid_input_original_limits_and_checkpoint_errors_remain(self):
        p = point('p', (0, 0, 0))
        for malformed in (
                SimpleNamespace(vertices=np.array([(0., 0, 0)] * 3), faces=[(0, 1, -1)]),
                SimpleNamespace(vertices=np.array([(0., 0, 0)] * 3), faces=[(0, 1, True)]),
                SimpleNamespace(vertices=np.array([(math.nan, 0, 0)] * 3), faces=[(0, 1, 2)])):
            result = self.measure(p, malformed)
            self.assertFalse(result['measurement_valid'], result)
            self.assertIn(result['reason'], ('surface_invalid_triangle_indices', 'surface_nonfinite_vertex'))
        smallest, high = math.ldexp(1., -1074), math.ldexp(1., 1023)
        result = self.measure(point('a', (smallest, 0, 0)),
                              segment('b', (high, 0, 0), (high, 1, 0)))
        self.assertFalse(result['measurement_valid'], result)
        self.assertEqual(result['reason'], 'surface_exact_bit_budget')
        self.assertEqual((surface.MAX_BITS, surface.MAX_FACES, surface.MAX_TRIANGLE_PAIRS),
                         (4096, 4096, 16384))
        class CountOnlyFaces:
            def __len__(self):
                return 4097
            def __iter__(self):
                raise AssertionError('Over-budget face data expanded')
        refused = self.measure(p, SimpleNamespace(vertices=p.vertices, faces=CountOnlyFaces()))
        self.assertFalse(refused['measurement_valid'])
        self.assertEqual(refused['reason'], 'surface_geometry_work_limit')
        for error in (RuntimeError('cancelled'), TimeoutError('deadline'),
                      RequestBudgetError('expired', 'surface_proximity_pair')):
            def checkpoint(stage):
                if stage == 'surface_proximity_pair':
                    raise error
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)) as caught:
                self.measure(p, segment('s', (0, 1, 0), (2, 1, 0)), checkpoint=checkpoint)
            self.assertIs(caught.exception, error)

    def test_g11_original_t04_real_readonly_chain_ties_pruning_and_hot_rank_cache(self):
        # build_assets.py stores .004 in a Blender float32 Matrix; the mesh
        # vertices are exact zero/one. No engine result supplies this oracle.
        near = float(np.float32(.004))
        focal = segment('focal', (0, 0, 0), (0, 1, 0))
        target = triangle('near', [(near, 0, 0), (near, 1, 0), (near, 0, 1)])
        self.assert_pair(focal, target, F.from_float(near) ** 2)
        scenarios = [((0., near, 1., 2., 3.), True, 1, 4, 0),
                     ((0., near, near, 1.), True, 2, 3, 0),
                     ((0., 2., 2., 100.), False, 2, 2, 1)]
        for xs, degenerate, tie_count, valid_count, excluded in scenarios:
            with self.subTest(xs=xs, degenerate=degenerate):
                case = entry.SurfaceNearestEntryTests(methodName='runTest')
                with patch.object(entry, 'TESTS', Path(__file__).resolve().parent):
                    case.setUp()
                try:
                    host = entry.ActualCandidateHost(xs)
                    if degenerate:
                        host.objects[0].data.vertices[2].co = (0., 0., 0.)
                        host.objects[0].bound_box = list(itertools.product((0., 0.), (0., 1.), (0., 0.)))
                    for i, obj in enumerate(host.objects):
                        name = 'M4_Focal' if i == 0 else 'M4_Near' if i == 1 else 'M4_Far_%02d' % (i-2)
                        obj.name = obj.name_full = name
                    case.use_host(host)
                    cold = case.observe_selector({'name': 'M4_Focal'})
                    cold_work = case.audit_work()
                    hot = case.observe()
                    hot_work = case.audit_work()
                    case.assert_same_nearest(hot, cold)
                    self.assertEqual(cold['status'], 'complete', cold)
                    self.assertEqual(cold['distance_m'], xs[1])
                    self.assertEqual(cold['unit'], 'm')
                    self.assertEqual(len(cold['nearest_objects']), tie_count)
                    self.assertEqual(cold['unresolved'], [])
                    self.assertEqual(cold['coverage'], dict(targets_excluding_focal=len(xs)-1,
                        distance_valid=valid_count, strictly_excluded=excluded, unresolved=0))
                    self.assertEqual(cold_work['kernel_calls'], valid_count)
                    self.assertEqual(hot_work['kernel_calls'], 0)
                    self.assertEqual(hot_work['cache_hits'], valid_count)
                    self.assertEqual(hot_work['exact_rank_calls'], 1)
                    self.assertTrue(all(obj.assignments == 0 for obj in host.objects))
                    EVIDENCE.setdefault('g11_chain', []).append(dict(
                        xs=list(xs), focal_degenerate=degenerate, coverage=cold['coverage'],
                        cold_work=cold_work, hot_work=hot_work))
                finally:
                    case.doCleanups()

    def test_g12_cache_versions_normal_rank_isolation_and_witness_precision(self):
        a = point('a', (0, 0, 0))
        b = segment('b', (2, -1, 0), (2, 1, 0))
        cache = SpatialSceneCache()
        source = 'blender'
        base_parameters = dict(source=source, unit='m', coordinate_frame='world',
                               world_witness_tolerance_m=task_query.COLLISION_TOLERANCE_M)
        for rank, old in ((False, 'task-surface-proximity-exact-aabb-v2'),
                           (True, 'task-surface-proximity-exact-world-rank-v1')):
            parameters = dict(base_parameters)
            if rank:
                parameters['retain_exact_rank'] = True
            cache.pair_measurement(a, b, lambda: dict(measurement_valid=True, distance_m=999.),
                                   parameters=parameters, algorithm_version=old)
        original = SpatialSceneCache.pair_measurement
        versions = []
        def measured_cache(owner, left, right, compute, *, parameters=None, algorithm_version):
            versions.append(algorithm_version)
            return original(owner, left, right, compute, parameters=parameters, algorithm_version=algorithm_version)
        work_records = []
        with patch.object(SpatialSceneCache, 'pair_measurement', autospec=True, side_effect=measured_cache), \
             patch.object(task_query, 'measure_surface_proximity', wraps=surface.measure_surface_proximity) as measured:
            for rank in (False, True):
                results = []
                for iteration in range(2):
                    work = {}
                    result = task_query._surface_pair_measurement(a, b, cache, lambda stage: None,
                        source=source, diagnostics=work, retain_exact_rank=rank)
                    self.assertTrue(result['measurement_valid'], result)
                    self.assertEqual(result['method'], METHOD)
                    self.assertEqual(result['distance_m'], 2.)
                    self.assertEqual('_exact_distance_sq' in result, rank)
                    if rank:
                        self.assertEqual(exact_key_value(result), 4)
                    self.assertEqual(work['surface_pair_count'], int(iteration == 0))
                    self.assertEqual(work['surface_pair_cache_hit'], iteration == 1)
                    if iteration:
                        self.assertEqual(work['surface_work'], {})
                    results.append(result)
                    work_records.append(work)
                self.assertEqual(results[0], results[1])
            self.assertEqual(measured.call_count, 2)
        self.assertEqual(versions, [NORMAL_VERSION] * 2 + [RANK_VERSION] * 2)
        base = 2.**30
        p = point('p', (base+1, base+1, 0))
        s = segment('s', (base, base, 0), (base+1, base+3, 0),
                    (base+.5, base+1.5, 0))
        exact = union_oracle(p, s)[0]
        self.assertEqual(exact, F(2, 5))
        result = self.assert_pair(p, s, exact, witness=False)
        self.assertEqual(result['witness_status'], 'unknown', result)
        self.assertEqual(result['witness_reason'], 'original_surface_witness_precision_exceeded')
        self.assertIsNone(result['point_a_world'])
        self.assertIsNone(result['point_b_world'])
        self.assertTrue(result['measurement_valid'])
        fact = task_query._surface_proximity_fact(result)
        self.assertEqual(fact['status'], 'unknown')
        self.assertEqual(fact['value']['distance_m'], rounded_root(exact))
        EVIDENCE['g12_cache'] = dict(versions=versions, work=work_records,
            witness_distance_m=result['distance_m'], witness_status=result['witness_status'])


if __name__ == '__main__':
    unittest.main()
