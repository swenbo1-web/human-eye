"""Nine focused groups for private same-query exact boundary witness reuse.

Only the parent verified loader executes this module. No Blender, process,
socket, model, live session, or original-asset mutation occurs here.
"""
from fractions import Fraction
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_geometry as closed
from human_eye_plugin import surface_proximity as surface
from human_eye_plugin import task_query
from human_eye_plugin.live_service import RequestBudgetError
from verification.test_concave_geometry import box, entity
from verification.test_task_complete_001 import CurrentTaskEvidenceTests
from verification.perf030_002_cases import triangle_truth


EVIDENCE = {}
FACTS = ('closed_solid_relation', 'surface_proximity')


def clone(mesh, identity=None, vertices=None):
    return entity(identity or mesh.object_id,
                  mesh.vertices if vertices is None else vertices, mesh.faces)


def cross_pair():
    # A nonempty open cuboid belongs to both solids, and their boundaries cross.
    return (box((0, 0, 0), (2, 2, 2), 'a'),
            box((.5, .25, .125), (2, 2, 2), 'b'))


def prepare(left, right, holder=None):
    holder = {} if holder is None else holder
    result = closed.classify_closed_solids(left, right, lambda stage: None,
                                          prepared_holder=holder)
    return result, holder


def assert_no_contact_payload(test, value):
    """Private geometry references must never reach a public or cached result."""
    if isinstance(value, dict):
        for key, item in value.items():
            test.assertNotIn(key, ('pair', 'boundary_contact', 'triangles',
                                   '_prepared_pair', '_boundary_contact'))
            assert_no_contact_payload(test, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_no_contact_payload(test, item)


def rational_triangle_contains(point, triangle):
    """Independent exact barycentric membership on original binary64 vertices."""
    a, b, c = [tuple(Fraction.from_float(float(x)) for x in row)
               for row in triangle]
    sub = lambda x, y: tuple(p-q for p, q in zip(x, y))
    dot = lambda x, y: sum(p*q for p, q in zip(x, y))
    ab, ac, ap = sub(b, a), sub(c, a), sub(point, a)
    aa, bb, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac)
    determinant = aa*cc-bb*bb
    if determinant <= 0:
        return False
    u = (dot(ap, ab)*cc-dot(ap, ac)*bb)/determinant
    v = (dot(ap, ac)*aa-dot(ap, ab)*bb)/determinant
    residual = tuple(ap[k]-u*ab[k]-v*ac[k] for k in range(3))
    return not any(residual) and u >= 0 and v >= 0 and u+v <= 1


class ZeroWitnessMathTests(unittest.TestCase):
    def reused(self, left, right, holder, **options):
        with patch.object(surface, '_nearest',
                          side_effect=AssertionError('duplicate nearest traversal')) as nearest:
            result = surface.measure_surface_proximity(left, right,
                options.pop('checkpoint', lambda stage: None),
                _prepared_pair=holder['pair'],
                _boundary_contact=holder.get('boundary_contact'), **options)
        self.assertEqual(nearest.call_count, 0)
        self.assertTrue(result['measurement_valid'], result)
        self.assertEqual(result['distance_m'], 0.)
        self.assertTrue(result['work']['zero_witness_reused'])
        self.assertEqual(result['work']['triangle_pairs'], 0)
        self.assertEqual(result['direction_status'], 'not_applicable')
        self.assertEqual(result['direction_reason'], 'undefined_zero_distance')
        self.assertIsNone(result['direction_a_to_b'])
        assert_no_contact_payload(self, result)
        return result

    def test_g01_crossing_and_face_edge_point_contact_skip_nearest_in_both_orders(self):
        a, b = cross_pair()
        pairs = [(a, b, 'penetrating')]
        pairs.extend((a, box(center, (2, 2, 2), kind), 'touching')
                     for kind, center in (('face', (2, 0, 0)),
                                          ('edge', (2, 2, 0)),
                                          ('point', (2, 2, 2))))
        rows = []
        for left, right, relation in pairs:
            for x, y in ((left, right), (right, left)):
                with self.subTest(relation=relation, order=(x.object_id, y.object_id)):
                    solid, holder = prepare(x, y)
                    self.assertTrue(solid['measurement_valid'], solid)
                    self.assertEqual(solid['relation'], relation)
                    self.assertIs(holder['boundary_contact']['pair'], holder['pair'])
                    measured = self.reused(x, y, holder)
                    self.assertEqual(measured['witness_status'], 'measured', measured)
                    self.assertEqual(measured['point_a_world'], measured['point_b_world'])
                    for mesh in (x, y):
                        self.assertEqual(min(triangle_truth(measured['point_a_world'],
                            mesh.vertices[face])['distance_sq'] for face in mesh.faces), 0)
                    rows.append({'relation': relation, 'order': [x.object_id, y.object_id],
                                 'surface_work': measured['work']})
        EVIDENCE['g01_reuse'] = rows

    def test_g02_containment_positive_gap_and_stale_holder_are_not_zero(self):
        _, holder = prepare(*cross_pair())
        outer = box((0, 0, 0), (4, 4, 4), 'outer')
        inner = box((0, 0, 0), (1, 1, 1), 'inner')
        gap = box((6, 0, 0), (4, 4, 4), 'gap')
        for right, relation, expected in ((inner, 'penetrating', 1.5),
                                           (gap, 'separated', 2.)):
            with self.subTest(relation=relation):
                solid, holder = prepare(outer, right, holder)
                self.assertTrue(solid['measurement_valid'], solid)
                self.assertEqual(solid['relation'], relation)
                self.assertNotIn('boundary_contact', holder)
                with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
                    result = surface.measure_surface_proximity(outer, right, lambda stage: None,
                        _prepared_pair=holder['pair'], _boundary_contact=holder.get('boundary_contact'))
                self.assertEqual(nearest.call_count, 1)
                self.assertTrue(result['measurement_valid'], result)
                self.assertEqual(result['distance_m'], expected)
                self.assertFalse(result['work'].get('zero_witness_reused', False))

    def test_g03_unknown_coincident_solid_still_has_genuine_zero_surface_evidence(self):
        left = box((0, 0, 0), (2, 2, 2), 'a')
        right = clone(left, 'b')
        solid, holder = prepare(left, right)
        self.assertFalse(solid['measurement_valid'], solid)
        self.assertTrue(solid.get('reason'))
        result = self.reused(left, right, holder)
        self.assertEqual(result['witness_status'], 'measured')
        EVIDENCE['g03_unknown_solid'] = {'solid_reason': solid['reason'],
                                        'surface_distance_m': result['distance_m']}

    def test_g04_wrong_pair_frame_refs_and_tampered_point_fall_back_safely(self):
        left, crossing = cross_pair()
        _, old = prepare(left, crossing)
        right = box((4, 0, 0), (2, 2, 2), 'b')
        _, current = prepare(left, right)
        malformed = [
            {'pair': old['pair'], 'triangles': (0, 0), 'point': (0, 0, 0)},
            {'pair': current['pair'], 'triangles': (-1, 1000000), 'point': (0, 0, 0)},
            {'pair': current['pair'], 'triangles': (0, 0), 'point': (10**30,)*3},
            {'pair': current['pair'], 'triangles': (0, 0), 'point': (0., 0., 0.)},
        ]
        cases = [(left, right, current['pair'], contact, 2.) for contact in malformed]
        # Refusing the contact alone is insufficient: stale preparation must
        # also be discarded, or _nearest would measure the old crossing pair.
        cases += [(left, right, old['pair'], old['boundary_contact'], 2.),
                  (right, left, current['pair'], old['boundary_contact'], 2.)]
        for index, (a, b, pair, contact, expected) in enumerate(cases):
            with self.subTest(case=index):
                with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
                    result = surface.measure_surface_proximity(a, b, lambda stage: None,
                        _prepared_pair=pair, _boundary_contact=contact)
                self.assertEqual(nearest.call_count, 1)
                self.assertTrue(result['measurement_valid'], result)
                self.assertEqual(result['distance_m'], expected)
                self.assertFalse(result['work'].get('zero_witness_reused', False))

    def test_g05_large_world_exact_contact_keeps_zero_when_witness_cannot_publish(self):
        offset = 2.**30
        left = box((offset, offset, offset), (6, 6, 4), 'a')
        local = box((0, 0, 0), (1, 1, 1), 'b')
        transform = np.array([[3., 5., 0], [-5., 3., 0], [0., 0., 1.]])
        right = clone(local, vertices=local.vertices @ transform + offset)
        _, holder = prepare(left, right)
        # x=3 is A's boundary and 3*x+5*y=17 is B's boundary.
        # Their genuine intersection (3,8/5,0)+offset cannot round to binary64
        # within 1e-9 at this world magnitude; the exact scalar remains zero.
        point = (Fraction(int(offset))+3, Fraction(int(offset))+Fraction(8, 5),
                 Fraction(int(offset)))
        indices = tuple(next(i for i, face in enumerate(mesh.faces)
                             if rational_triangle_contains(point, mesh.vertices[face]))
                        for mesh in (left, right))
        origin, factor = holder['pair'][2:4]
        holder['boundary_contact'] = {'pair': holder['pair'], 'triangles': indices,
            'point': tuple((point[k]-origin[k])*factor for k in range(3))}
        result = self.reused(left, right, holder)
        self.assertEqual(result['witness_status'], 'unknown', result)
        self.assertEqual(result['witness_reason'], 'original_surface_witness_precision_exceeded')
        self.assertIsNone(result['point_a_world']); self.assertIsNone(result['point_b_world'])
        EVIDENCE['g05_large_world'] = {'analytic_world_point': [str(x) for x in point],
            'triangle_refs': list(indices), 'surface_result': result}

    def test_g06_cancellation_and_deadline_propagate_on_reuse_path(self):
        left, right = cross_pair(); _, holder = prepare(left, right)
        for error in (RuntimeError('cancelled'), TimeoutError('deadline'),
                      RequestBudgetError('expired', 'zero-witness')):
            seen = []
            def checkpoint(stage):
                seen.append(stage)
                if stage == 'surface_proximity_publish':
                    raise error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)) as caught:
                    self.reused(left, right, holder, checkpoint=checkpoint)
                self.assertIs(caught.exception, error)
                self.assertIn('surface_proximity_boundary_witness', seen)

    def test_g07_standalone_path_and_exact_zero_rank_contract(self):
        left, right = cross_pair(); _, holder = prepare(left, right)
        with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
            original = surface.measure_surface_proximity(left, right, lambda stage: None,
                                                        retain_exact_rank=True)
        self.assertEqual(nearest.call_count, 1)
        reused = self.reused(left, right, holder, retain_exact_rank=True)
        for result in (original, reused):
            self.assertEqual(result['_exact_distance_sq'], [0, 1, 0])
            self.assertEqual(result['distance_m'], 0.)
            self.assertEqual(result['topology'], original['topology'])
            self.assertEqual(result['method'], original['method'])
            json.dumps(result, allow_nan=False)


class ZeroWitnessTaskTests(unittest.TestCase):
    setUp = CurrentTaskEvidenceTests.setUp
    set_pair = CurrentTaskEvidenceTests.set_pair
    work = CurrentTaskEvidenceTests.work

    def observe(self, facts=FACTS):
        return self.service.observe('zero-witness-test', include_image=False, query={
            'mode': 'task', 'objects': [{'id': 'a'}, {'id': 'b'}],
            'requested_facts': list(facts)})

    def assert_zero(self, result):
        self.assertEqual(result['facts']['closed_solid_relation']['value'], 'penetrating')
        self.assertEqual(result['facts']['surface_proximity']['value']['distance_m'], 0.)
        assert_no_contact_payload(self, result)
        for encoded, elapsed in self.service._perception_cache._measurements.values():
            assert_no_contact_payload(self, json.loads(encoded))

    def test_g08_mixed_cold_hot_and_changed_geometry_reuse_only_same_query(self):
        left, right = cross_pair(); self.set_pair(left, right)
        with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
            cold = self.observe(); cold_work = self.work()
            hot = self.observe(); hot_work = self.work()
            self.set_pair(left, clone(right, vertices=right.vertices + [.125, 0, 0]), 'r2')
            changed = self.observe(); changed_work = self.work()
        self.assertEqual(nearest.call_count, 0)
        for result in (cold, hot, changed): self.assert_zero(result)
        self.assertEqual(cold['facts'], hot['facts'])
        for work in (cold_work, changed_work):
            self.assertEqual(work['closed_solid_pair_count'], 1)
            self.assertEqual(work['surface_pair_count'], 1)
            self.assertTrue(work['surface_work']['zero_witness_reused'])
        self.assertEqual(hot_work['closed_solid_pair_count'], 0)
        self.assertEqual(hot_work['surface_pair_count'], 0)
        EVIDENCE['g08_cache'] = {'cold': cold_work, 'hot': hot_work, 'changed': changed_work}

    def test_g09_mixed_cache_hits_never_recreate_or_serialize_private_witness(self):
        self.set_pair(*cross_pair())
        self.observe(('closed_solid_relation',))
        with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
            result = self.observe(); work = self.work()
            hot = self.observe()
        self.assertEqual(nearest.call_count, 1)
        self.assert_zero(result); self.assert_zero(hot)
        self.assertTrue(work['closed_solid_pair_cache_hit'])
        self.assertEqual(work['closed_solid_pair_count'], 0)
        self.assertFalse(work['surface_pair_cache_hit'])
        self.assertEqual(work['surface_pair_count'], 1)
        self.assertFalse(work['surface_work'].get('zero_witness_reused', False))
        closed_hit_work = work
        # A distinct geometry pair starts the opposite cache combination.
        left, right = cross_pair()
        self.set_pair(clone(left, vertices=left.vertices + [4, 0, 0]),
                      clone(right, vertices=right.vertices + [4, 0, 0]), 'r2')
        with patch.object(surface, '_nearest', wraps=surface._nearest) as nearest:
            first = self.observe(('surface_proximity',))
            mixed = self.observe(); work = self.work()
            mixed['facts']['surface_proximity']['value']['distance_m'] = 99.
            hot = self.observe()
        self.assertEqual(nearest.call_count, 1)
        self.assert_zero(hot)
        self.assertEqual(first['facts']['surface_proximity'], hot['facts']['surface_proximity'])
        self.assertFalse(work['closed_solid_pair_cache_hit'])
        self.assertEqual(work['closed_solid_pair_count'], 1)
        self.assertTrue(work['surface_pair_cache_hit'])
        self.assertEqual(work['surface_pair_count'], 0)
        EVIDENCE['g09_mixed_cache'] = {'closed_hit_surface_miss': closed_hit_work,
                                      'closed_miss_surface_hit': work}


if __name__ == '__main__':
    unittest.main()
