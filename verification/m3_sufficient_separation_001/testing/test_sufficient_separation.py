"""Frozen geometric and stopping counterexamples through the actual core API."""

import copy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin import surface_proximity as exact, surface_geometry as closed


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = json.loads((HERE/'FROZEN.json').read_bytes())
assert hashlib.sha256((HERE/'DESIGNED_CASES.json').read_bytes()).hexdigest()==FROZEN['designed_cases_sha256']
DESIGNED = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
EVIDENCE = {}


def mesh(raw):
    return SimpleNamespace(vertices=[tuple(point) for point in raw['vertices_world']],
        faces=[tuple(face) for face in raw['triangles']])


def indices(raw):
    return sorted({index for triangle in raw['triangles'] for index in triangle})


def primitive_from_public(surface):
    values = [F(float(b))-F(float(a)) for a,b in zip(surface['point_a_world'],surface['point_b_world'])]
    denominator = max(value.denominator for value in values)
    integers = [value.numerator*(denominator//value.denominator) for value in values]
    divisor = math.gcd(*integers)
    return tuple(value//divisor for value in integers) if divisor else None


def witness_oracle():
    path = ROOT/'verification/m3_pair_scalability_001/testing/witness_oracle.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='5302157b0c1196d1be8a800253b54820b6da99901d321f7eb6986489d79ccbce'
    spec = importlib.util.spec_from_file_location('_sufficient_independent_witness',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SufficientCoreTests(unittest.TestCase):
    def call(self,case,**options):
        work,holder = {},{}
        value = exact.measure_spatial_relation(mesh(case['left']),mesh(case['right']),lambda stage:None,
            diagnostics=work,prepared_holder=holder,**options)
        return value,work,holder

    def assert_distance_and_points(self,case,value):
        surface = value['surface']
        truth = case['independent_truth']
        self.assertTrue(surface['measurement_valid'],surface)
        if 'distance_m' in truth:
            self.assertEqual(surface['distance_m'],truth['distance_m'])
        elif 'distance_squared_rational' in truth:
            self.assertEqual(surface['distance_m'],math.sqrt(float(F(*truth['distance_squared_rational']))))
        self.assertEqual(surface['witness_status'],'measured',surface)
        proof = witness_oracle().certify_pair(surface['point_a_world'],surface['point_b_world'],surface['distance_m'],
            case['left'],case['right'],position_tolerance_m=1e-9,distance_tolerance_m=1e-6)
        self.assertTrue(proof['passed'],proof)
        return proof

    def assert_support(self,case,value,work):
        spatial = value['spatial']
        self.assertEqual(spatial['method'],'exact_sufficient_spatial_relation_v1')
        self.assertEqual(spatial['geometry_scope'],'referenced_triangle_unions_and_their_vertex_convex_hulls')
        self.assertEqual(spatial['certificate'],'strict_all_referenced_vertex_support')
        evidence = spatial['support_evidence']
        direction = primitive_from_public(value['surface'])
        self.assertEqual(evidence['primitive_direction'],list(direction))
        self.assertEqual(evidence['proposal'],'first_public_nearest_points_difference')
        origin = [F(*entry) for entry in evidence['origin']]
        factor = evidence['factor']
        projections = []
        for raw in (case['left'],case['right']):
            row = {}
            for index in indices(raw):
                local = [(F(float(v))-start)*factor for v,start in zip(raw['vertices_world'][index],origin)]
                self.assertTrue(all(value.denominator==1 for value in local))
                row[index] = sum(a*b for a,b in zip(direction,local))
            projections.append(row)
        left_max,right_min = max(projections[0].values()),min(projections[1].values())
        self.assertGreater(right_min,left_max)
        self.assertEqual(evidence['left_max'],left_max)
        self.assertEqual(evidence['right_min'],right_min)
        self.assertEqual(projections[0][evidence['left_vertex_index']],left_max)
        self.assertEqual(projections[1][evidence['right_vertex_index']],right_min)
        counts = [len(row) for row in projections]
        self.assertEqual(evidence['referenced_counts'],counts)
        support = work['support_work']
        self.assertEqual(support['support_direction_components'],3)
        self.assertEqual(support['support_source_vertices'],sum(counts))
        self.assertEqual(support['support_vertex_dots'],sum(counts))
        self.assertEqual(support['work_units_after']-support['work_units_before'],2*sum(counts)+3)
        self.assertEqual(work['closed_solid_pair_count'],0)
        self.assertEqual(work['closed_solid_work'],{})
        self.assertIsNone(value['closed'])

    def test_frozen_positive_convex_hull_scope_and_complete_vertex_support(self):
        for case in DESIGNED['analytic_pairs']:
            truth = case['independent_truth']
            if truth.get('relation')!='separated' or truth.get('support_expected') is False:
                continue
            with self.subTest(case=case['id']):
                with patch.object(closed,'classify_closed_solids',side_effect=AssertionError('support proof called closed')):
                    value,work,holder = self.call(case)
                self.assertTrue(value['measurement_valid'],value)
                self.assertEqual(value['spatial']['relation'],'separated')
                self.assertFalse(value['budget_stopped'])
                proof = self.assert_distance_and_points(case,value)
                self.assert_support(case,value,work)
                EVIDENCE[case['id']] = {'bundle':value,'diagnostics':work,'witness':proof,'holder_keys':sorted(holder)}

    def test_positive_surface_distance_or_zero_never_bypasses_required_fallback(self):
        for case in DESIGNED['analytic_pairs']:
            truth = case['independent_truth']
            if truth.get('relation')=='separated' and truth.get('support_expected') is not False:
                continue
            with self.subTest(case=case['id']):
                with patch.object(closed,'classify_closed_solids',wraps=closed.classify_closed_solids) as fallback:
                    value,work,holder = self.call(case)
                self.assertEqual(fallback.call_count,1)
                self.assertEqual(work['closed_solid_pair_count'],1)
                proof = self.assert_distance_and_points(case,value)
                if truth.get('new_expected')=='unknown':
                    self.assertFalse(value['spatial']['measurement_valid'])
                    self.assertIsNone(value['spatial']['relation'])
                else:
                    self.assertTrue(value['measurement_valid'],value)
                    self.assertEqual(value['spatial']['relation'],truth['relation'])
                EVIDENCE[case['id']] = {'bundle':value,'diagnostics':work,'witness':proof,'holder_keys':sorted(holder)}

    def test_remote_referenced_extremum_refutes_only_proposal_and_orphan_stays_outside_scope(self):
        for name,total in (('remote_referenced_vertex_refutes_only_direction',9),
                           ('unreferenced_point_excluded_from_scope',16),('collapsed_middle_source_vertex_retained',6)):
            case = next(row for row in DESIGNED['analytic_pairs'] if row['id']==name)
            value,work,_ = self.call(case)
            support = work['support_work']
            self.assertEqual(support['support_source_vertices'],total)
            self.assertEqual(support['support_vertex_dots'],total)
            self.assertEqual(support['work_units_after']-support['work_units_before'],2*total+3)
            if name.startswith('remote'):
                self.assertFalse(value['spatial']['measurement_valid'])
                self.assertEqual(support['reason'],'spatial_support_not_strictly_separated')
                self.assertEqual(work['closed_solid_pair_count'],1)
            else:
                self.assertEqual(value['spatial']['relation'],'separated')
                self.assertEqual(work['closed_solid_pair_count'],0)
            EVIDENCE['coverage_'+name] = {'bundle':value,'diagnostics':work}

    def test_swapping_objects_and_reordering_source_indices_preserves_proof(self):
        original = next(row for row in DESIGNED['analytic_pairs'] if row['id']=='rotated_overlapping_world_aabbs')
        for swap in (False,True):
            case = copy.deepcopy(original)
            if swap:
                case['left'],case['right'] = case['right'],case['left']
            for raw in (case['left'],case['right']):
                size = len(raw['vertices_world'])
                raw['vertices_world'].reverse()
                raw['triangles'] = [[size-1-index for index in face] for face in raw['triangles']]
            value,work,_ = self.call(case)
            self.assertTrue(value['measurement_valid'],value)
            self.assert_distance_and_points(case,value)
            self.assert_support(case,value,work)
            EVIDENCE['permuted_'+str(swap)] = {'bundle':value,'diagnostics':work}

    def test_surface_and_support_budget_stop_preserve_counts_without_fallback(self):
        raw = DESIGNED['simple_control']
        case = {'left':raw['left'],'right':raw['right']}
        original_init = exact._Work.__init__
        for kind in ('surface_total','surface_leaf','support_total'):
            with self.subTest(kind=kind):
                def seeded(instance,*args,**kwargs):
                    original_init(instance,*args,**kwargs)
                    if kind=='surface_total':
                        instance.counts['work_units'] = 1179648
                    if kind=='surface_leaf':
                        instance.counts['narrow_phase_pairs'] = 16384
                original_direction = exact._public_support_direction
                def exhaust_after_direction(surface,budget):
                    direction = original_direction(surface,budget)
                    if kind=='support_total':
                        budget.counts['work_units'] = 1179648
                    return direction
                with patch.object(exact._Work,'__init__',seeded),\
                     patch.object(exact,'_public_support_direction',exhaust_after_direction),\
                     patch.object(closed,'classify_closed_solids',side_effect=AssertionError('budget stop restarted closed')):
                    value,work,_ = self.call(case)
                self.assertTrue(value['budget_stopped'])
                self.assertFalse(value['measurement_valid'])
                self.assertFalse(value['spatial']['measurement_valid'])
                self.assertEqual(work['closed_solid_pair_count'],0)
                self.assertIsNone(value['closed'])
                self.assertGreaterEqual(work['surface_work']['work_units'],1179648 if kind!='surface_leaf' else 1)
                EVIDENCE['budget_'+kind] = {'bundle':value,'diagnostics':work}

    def test_original_cancel_deadline_propagate_from_support_without_fallback(self):
        control = DESIGNED['simple_control']
        for stage in ('support_direction_components','support_source_vertices','support_vertex_dots'):
            for exception in (RuntimeError('original cancellation'),TimeoutError('original deadline')):
                with self.subTest(stage=stage,exception=type(exception).__name__):
                    def checkpoint(actual):
                        if actual=='surface_proximity_'+stage:
                            raise exception
                    with patch.object(closed,'classify_closed_solids',side_effect=AssertionError('interruption used fallback')):
                        with self.assertRaises(type(exception)) as raised:
                            exact.measure_spatial_relation(mesh(control['left']),mesh(control['right']),checkpoint)
                    self.assertIs(raised.exception,exception)

    def test_optional_support_bit_failure_or_unavailable_point_falls_back_once(self):
        control = DESIGNED['simple_control']
        case = {'left':control['left'],'right':control['right']}
        for kind in ('optional_bit','unavailable_public'):
            with self.subTest(kind=kind):
                if kind=='optional_bit':
                    proposal = patch.object(exact,'_referenced_support_evidence',side_effect=exact._DomainError('surface_exact_bit_budget'))
                else:
                    proposal = patch.object(exact,'_public_support_direction',return_value=(None,'spatial_support_direction_unavailable'))
                with proposal,patch.object(closed,'classify_closed_solids',wraps=closed.classify_closed_solids) as fallback:
                    value,work,_ = self.call(case)
                self.assertEqual(fallback.call_count,1)
                self.assertTrue(value['measurement_valid'],value)
                self.assertEqual(value['spatial']['relation'],'separated')
                self.assertFalse(value['budget_stopped'])
                self.assertEqual(work['closed_solid_pair_count'],1)
                EVIDENCE[kind] = {'bundle':value,'diagnostics':work,'scope':'forced optional guard branch'}

    def test_same_pair_integer_preparation_is_reused_in_support_and_closed_fallback(self):
        for name in ('intersecting_hulls_separated_nonconvex_shells','fallback_intersecting_bars','fallback_full_containment'):
            case = next(row for row in DESIGNED['analytic_pairs'] if row['id']==name)
            with self.subTest(case=name):
                with patch.object(exact,'_integer_frame',wraps=exact._integer_frame) as integer_frame,\
                     patch.object(exact,'_admit',wraps=exact._admit) as admit:
                    value,work,holder = self.call(case)
                self.assertEqual(integer_frame.call_count,1)
                self.assertEqual(admit.call_count,1)
                self.assertTrue(value['measurement_valid'],value)
                self.assertTrue(work['closed_solid_work']['prepared_pair_reused'])
                self.assertEqual(work['closed_solid_pair_count'],1)
                EVIDENCE['reused_'+name] = {'bundle':value,'diagnostics':work,'holder_keys':sorted(holder)}
