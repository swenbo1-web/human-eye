"""Sixteen bounded groups with analytic and fixed independent geometry truth.

The parent executes these exact bytes through the verified product loader.
This file does not launch Blender, models, external processes or sockets.
"""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import surface_geometry as closed
from human_eye_plugin import surface_proximity as surface
from human_eye_plugin import task_query
from human_eye_plugin import geometry_safety as legacy
from human_eye_plugin.live_service import RequestBudgetError
from verification.test_concave_geometry import box, entity, ring
from verification import test_task_complete_001 as previous


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / 'verification/fixes/perf_integrated_001/run_01/author/assembly/author_mesh_snapshots.json'
TRUTH = ROOT / 'verification/fixes/perf_integrated_001/run_02/author/assembly/TRUTH.json'
SNAPSHOT_SHA = '5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14'
TRUTH_SHA = 'd01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff'
EVIDENCE = {}


def clone(mesh, identity=None, *, vertices=None, faces=None):
    return entity(identity or mesh.object_id, mesh.vertices if vertices is None else vertices,
                  mesh.faces if faces is None else faces)


def moved(mesh, shift, identity=None):
    return clone(mesh, identity, vertices=mesh.vertices + np.asarray(shift, dtype=float))


def joined(left, right, identity='invalid-union'):
    return entity(identity, np.vstack((left.vertices, right.vertices)),
                  np.vstack((left.faces, right.faces + len(left.vertices))))


def snapshot_meshes(state):
    raw = SNAPSHOT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA:
        raise AssertionError('Original accepted assembly snapshot changed')
    snapshot = json.loads(raw)[state]
    result = {}
    for obj in snapshot['objects']:
        matrix = obj['matrix_world']; scale = snapshot['unit_scale_m']
        vertices = [[(sum(matrix[r][k] * p[k] for k in range(3)) + matrix[r][3]) * scale
                     for r in range(3)] for p in obj['vertices_local']]
        if vertices != obj['world_vertices']:
            raise AssertionError('Original local/matrix/current-host world correspondence changed')
        result[obj['name']] = entity(obj['name'], vertices, obj['faces'])
    return result


class ClosedSolidMathTests(unittest.TestCase):
    def measure(self, left, right, *, checkpoint=None, diagnostics=None):
        return closed.classify_closed_solids(left, right, checkpoint or (lambda stage: None),
                                            diagnostics=diagnostics)

    def assert_relation(self, left, right, expected, *, both=True):
        results = []
        variants = ((left, right), (right, left)) if both else ((left, right),)
        for a, b in variants:
            with self.subTest(order=(a.object_id, b.object_id), expected=expected):
                result = self.measure(a, b)
                self.assertTrue(result['measurement_valid'], result)
                self.assertEqual(result['relation'], expected, result)
                self.assertTrue(result.get('method'))
                self.assertIsInstance(result['work'], dict)
                results.append(result)
        return results[0]

    def assert_unknown(self, left, right, *, both=True):
        for a, b in (((left, right), (right, left)) if both else ((left, right),)):
            with self.subTest(order=(a.object_id, b.object_id)):
                result = self.measure(a, b)
                self.assertFalse(result['measurement_valid'], result)
                self.assertTrue(result.get('reason'), result)

    def test_g01_disjoint_boxes_have_exact_positive_gap(self):
        a = box((0, 0, 0), (2, 2, 2), 'a')
        b = box((4, 0, 0), (2, 2, 2), 'b')
        self.assertEqual(Fraction.from_float(float(b.bbox_min[0]))
                         - Fraction.from_float(float(a.bbox_max[0])), 2)
        result = self.assert_relation(a, b, 'separated')
        distance = surface.measure_surface_proximity(a, b, lambda stage: None)
        self.assertTrue(distance['measurement_valid'], distance)
        self.assertEqual(distance['distance_m'], 2.)
        EVIDENCE['g01_separated_work'] = result['work']

    def test_g02_positive_surface_gap_does_not_reject_containment(self):
        outer = box((0, 0, 0), (4, 4, 4), 'outer')
        inner = box((0, 0, 0), (1, 1, 1), 'inner')
        self.assert_relation(outer, inner, 'penetrating')
        distance = surface.measure_surface_proximity(outer, inner, lambda stage: None)
        self.assertEqual(distance['distance_m'], 1.5)
        # A contained box can touch the containing boundary and still have
        # positive-volume overlap; boundary contact alone is not "touching".
        self.assert_relation(outer, box((1.5, 0, 0), (1, 1, 1), 'inside-touch'), 'penetrating')

    def test_g03_through_hole_is_empty_but_material_wall_contains(self):
        target = ring()
        hole = box((0, 0, 0), (.01, .01, .01), 'hole')
        material = box((-.045, 0, 0), (.01, .01, .01), 'material')
        self.assert_relation(target, hole, 'separated')
        self.assert_relation(target, material, 'penetrating')
        # Axis bounds independently place the first probe inside the square
        # hole, and the second strictly between the inner and outer walls.
        self.assertLess(float(np.max(np.abs(hole.vertices[:, :2]))), .025)
        self.assertGreater(float(np.min(material.vertices[:, 0])), -.06)
        self.assertLess(float(np.max(material.vertices[:, 0])), -.025)

    def test_g04_crossing_solids_without_any_vertex_inside(self):
        a = box((0, 0, 0), (4, .5, .5), 'x-bar')
        b = box((0, 0, 0), (.5, 4, .5), 'y-bar')
        # Every A vertex lies outside B's x interval and vice versa for y.
        self.assertTrue(all(abs(float(p[0])) > .25 for p in a.vertices))
        self.assertTrue(all(abs(float(p[1])) > .25 for p in b.vertices))
        # Yet the open cube (-.25,.25)^3 is common interior.
        result = self.assert_relation(a, b, 'penetrating')
        EVIDENCE['g04_no_vertex_containment_work'] = result['work']

    def test_g05_face_edge_and_point_tangency_are_not_penetration(self):
        a = box((0, 0, 0), (2, 2, 2), 'a')
        for label, center in (('face', (2, 0, 0)), ('edge', (2, 2, 0)), ('point', (2, 2, 2))):
            with self.subTest(contact=label):
                self.assert_relation(a, box(center, (2, 2, 2), label), 'touching')

    def test_g06_coincident_boundaries_must_not_be_called_merely_touching(self):
        a = box((0, 0, 0), (2, 2, 2), 'a')
        variants = (clone(a, 'same'), clone(a, 'reverse', faces=a.faces[:, ::-1]))
        for b in variants:
            with self.subTest(other=b.object_id):
                result = self.measure(a, b)
                if result['measurement_valid']:
                    # The two solids have identical open interiors. An honest
                    # degeneracy refusal is allowed; a touching answer is not.
                    self.assertEqual(result['relation'], 'penetrating', result)
                else:
                    self.assertTrue(result.get('reason'), result)
        EVIDENCE['g06_policy'] = 'coincident -> certified penetrating or explicit unknown; never touching/separated'

    def test_g07_rotations_large_translations_swaps_and_global_winding(self):
        a = box((0, 0, 0), (2, 2, 2), 'a')
        pairs = ((box((4, 0, 0), (2, 2, 2), 'far'), 'separated'),
                 (box((.5, .25, .125), (2, 2, 2), 'overlap'), 'penetrating'))
        exact_rotation = np.array([[0, -1, 0], [0, 0, 1], [-1, 0, 0]], dtype=float)
        theta = .371
        rounded_rotation = np.array([[math.cos(theta), -math.sin(theta), 0],
                                     [math.sin(theta), math.cos(theta), 0], [0, 0, 1.]])
        for rotation, shift in ((exact_rotation, np.array([2.**30, -2.**30, 2.**30])),
                                (rounded_rotation, np.array([8., -16., 32.]))):
            for b, expected in pairs:
                with self.subTest(expected=expected, large_translation=float(shift[0])):
                    left = clone(a, vertices=a.vertices @ rotation.T + shift)
                    right = clone(b, vertices=b.vertices @ rotation.T + shift)
                    self.assert_relation(left, right, expected)
                    self.assert_relation(clone(left, faces=left.faces[:, ::-1]), right, expected)

    def test_g08_open_nonmanifold_inconsistent_orientation_and_multishell_unknown(self):
        base = box((0, 0, 0), (2, 2, 2), 'invalid')
        far = box((10, 0, 0), (1, 1, 1), 'far')
        flipped = base.faces.copy(); flipped[0] = flipped[0, ::-1]
        variants = (
            clone(base, faces=base.faces[:-1]),
            clone(base, faces=np.vstack([base.faces, base.faces[0]])),
            clone(base, faces=flipped),
            joined(base, moved(base, (5, 0, 0), 'second')),
        )
        for index, bad in enumerate(variants):
            with self.subTest(invalid_variant=index):
                self.assert_unknown(bad, far)

    def test_g09_self_intersection_is_rejected_before_early_pair_answer(self):
        base = box((0, 0, 0), (2, 2, 2), 'invalid')
        vertices = base.vertices.copy(); vertices[6] = (-2., -2., -2.)
        self_intersecting = clone(base, vertices=vertices)
        # Closed combinatorial incidence is retained, while incident triangles
        # pass through nonincident parts of the opposite cube boundary.
        far = box((20, 0, 0), (1, 1, 1), 'far')
        self.assert_unknown(self_intersecting, far)

    def test_g10_exact_subnanometre_overlap_and_gap_remain_distinct(self):
        a = box((0, 0, 0), (2, 2, 2), 'a'); epsilon = 2.**-40
        overlap = box((2-epsilon, 0, 0), (2, 2, 2), 'overlap')
        gap = box((2+epsilon, 0, 0), (2, 2, 2), 'gap')
        overlap_width = Fraction.from_float(float(a.bbox_max[0])) - Fraction.from_float(float(overlap.bbox_min[0]))
        gap_width = Fraction.from_float(float(gap.bbox_min[0])) - Fraction.from_float(float(a.bbox_max[0]))
        self.assertEqual(overlap_width, Fraction(1, 2**40))
        self.assertEqual(gap_width, Fraction(1, 2**40))
        self.assert_relation(a, overlap, 'penetrating')
        self.assert_relation(a, gap, 'separated')

    def test_g11_nonfinite_indices_bit_and_work_limits_remain_unknown(self):
        base = box((1, 1, 1), (2, 2, 2), 'bad'); far = box((10, 0, 0), (1, 1, 1), 'far')
        nonfinite = base.vertices.copy(); nonfinite[0, 0] = float('nan')
        negative = base.faces.copy(); negative[0, 0] = -1
        invalid_index = base.faces.copy(); invalid_index[0, 0] = len(base.vertices)
        tiny = base.vertices.copy(); tiny[0, 0] = math.ldexp(1., -1070)
        for label, bad in (('nonfinite', clone(base, vertices=nonfinite)),
                           ('negative_index', clone(base, faces=negative)),
                           ('large_index', clone(base, faces=invalid_index)),
                           ('exact_width', clone(base, vertices=tiny))):
            with self.subTest(invalid=label): self.assert_unknown(bad, far, both=False)
        faces = np.tile(base.faces, (closed.LIMITS['triangles']//len(base.faces)+1, 1))
        many = clone(base, faces=faces)
        result = self.measure(many, far)
        self.assertFalse(result['measurement_valid'], result)
        self.assertTrue('budget' in result.get('reason','') or 'limit' in result.get('reason',''), result)
        with patch.object(closed, 'CLOSED_SOLID_MAX_WORK', 1):
            limited = self.measure(base, far)
        self.assertFalse(limited['measurement_valid'], limited)
        self.assertTrue('budget' in limited.get('reason','') or 'limit' in limited.get('reason',''), limited)

    def test_g12_deadline_and_cancellation_are_not_geometry_unknown(self):
        a = box((0, 0, 0), (2, 2, 2), 'a'); b = box((.5, 0, 0), (2, 2, 2), 'b')
        for error in (RuntimeError('cancelled'), TimeoutError('deadline'), RequestBudgetError('expired','closed-solid')):
            seen = []
            def checkpoint(stage):
                seen.append(stage)
                if len(seen) == 2: raise error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)) as caught: self.measure(a, b, checkpoint=checkpoint)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(seen), 2)


class ClosedSolidTaskTests(unittest.TestCase):
    setUp = previous.CurrentTaskEvidenceTests.setUp
    set_pair = previous.CurrentTaskEvidenceTests.set_pair
    work = previous.CurrentTaskEvidenceTests.work

    def observe(self, facts=('closed_solid_relation',)):
        return self.service.observe('closed-solid-test', include_image=False, query={
            'mode':'task', 'objects':[{'id':'a'},{'id':'b'}], 'requested_facts':list(facts)})

    def relation(self, result, expected):
        fact = result['facts']['closed_solid_relation']
        self.assertEqual(fact['status'], 'measured', fact)
        self.assertEqual(fact['value'], expected, fact)
        self.assertEqual(fact['relation_tolerance_m'], 0.)
        scope = fact['geometry_scope']
        self.assertTrue(all(word in scope for word in ('closed','connected','orientable','triangle')), scope)
        self.assertTrue('embedded' in scope or 'non_self_intersecting' in scope, scope)
        return fact

    def test_g13_task_new_fact_only_does_not_dispatch_legacy_solver(self):
        self.set_pair(box((0,0,0),(2,2,2),'a'),box((4,0,0),(2,2,2),'b'))
        with patch.object(task_query, 'measure_pair_geometry', side_effect=AssertionError('unrequested legacy solid solver')):
            result = self.observe()
        self.relation(result, 'separated')
        self.assertEqual(result['result_kind'], 'task_query')
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(self.work()['closed_solid_pair_count'], 1)
        self.assertEqual(self.work()['exact_pair_count'], 0)
        self.assertIn('runtime_source_sha256', result['binding'])

    def test_g14_current_geometry_cache_hits_and_unknown_is_not_memoized(self):
        a=box((0,0,0),(2,2,2),'a'); b=box((4,0,0),(2,2,2),'b'); self.set_pair(a,b)
        with patch.object(task_query, 'classify_closed_solids', wraps=closed.classify_closed_solids) as measured:
            cold=self.observe(); cold_work=self.work()
            hot=self.observe(); hot_work=self.work()
            self.host.scene['revision']='r2'; revised=self.observe(); revised_work=self.work()
            self.set_pair(a,moved(b,(-3,0,0)),'r3'); changed=self.observe(); changed_work=self.work()
            self.set_pair(clone(a,faces=a.faces[:-1]),b,'r4')
            unknown1=self.observe(); unknown_work1=self.work()
            unknown2=self.observe(); unknown_work2=self.work()
        self.assertEqual(measured.call_count,4)
        self.relation(cold,'separated'); self.relation(hot,'separated'); self.relation(revised,'separated'); self.relation(changed,'penetrating')
        self.assertEqual(cold['facts'],hot['facts']); self.assertEqual(hot['facts'],revised['facts'])
        self.assertNotEqual(hot['binding']['scene_fingerprint'],revised['binding']['scene_fingerprint'])
        self.assertNotEqual(revised['binding']['scene_fingerprint'],changed['binding']['scene_fingerprint'])
        for work in (cold_work,changed_work,unknown_work1,unknown_work2):
            self.assertEqual(work['closed_solid_pair_count'],1); self.assertFalse(work['closed_solid_pair_cache_hit'])
        for work in (hot_work,revised_work):
            self.assertEqual(work['closed_solid_pair_count'],0); self.assertTrue(work['closed_solid_pair_cache_hit'])
        for result in (unknown1,unknown2): self.assertEqual(result['facts']['closed_solid_relation']['status'],'unknown')
        EVIDENCE['g14_cache']={'cold':cold_work,'hot':hot_work,'revised':revised_work,'changed':changed_work,'unknown_first':unknown_work1,'unknown_second':unknown_work2}

    def test_g15_mixed_facts_share_preparation_and_preserve_old_contract(self):
        a=box((0,0,0),(2,2,2),'a'); b=box((4,0,0),(2,2,2),'b'); self.set_pair(a,b)
        old = legacy.measure_pair_geometry(a,b,need_relation_evidence=True)
        with patch.object(task_query, 'classify_closed_solids', wraps=closed.classify_closed_solids) as closed_calls, \
             patch.object(task_query, 'measure_surface_proximity', wraps=surface.measure_surface_proximity) as surface_calls:
            cold=self.observe(('closed_solid_relation','surface_proximity','solid_relation')); cold_work=self.work()
            hot=self.observe(('closed_solid_relation','surface_proximity','solid_relation')); hot_work=self.work()
        self.assertEqual(closed_calls.call_count,1); self.assertEqual(surface_calls.call_count,1)
        self.relation(cold,'separated')
        self.assertEqual(cold['facts']['solid_relation']['value'], 'penetrating' if old['is_penetrating'] else 'not_penetrating')
        self.assertEqual(cold['facts']['solid_relation']['tolerance_m'],legacy.COLLISION_TOLERANCE_M)
        self.assertEqual(cold['facts']['surface_proximity']['value']['distance_m'],2.)
        self.assertEqual(cold['facts'],hot['facts'])
        self.assertTrue(cold_work['surface_work']['shared_preparation'])
        self.assertEqual(cold_work['surface_work']['validated_faces'],0)
        self.assertEqual(cold_work['surface_work']['referenced_vertices'],0)
        self.assertEqual(hot_work['closed_solid_pair_count'],0); self.assertEqual(hot_work['surface_pair_count'],0)
        EVIDENCE['g15_shared_preparation']={'cold':cold_work,'hot':hot_work}

    def test_g16_original_assembly_all_candidates_three_states_and_fixed_truth(self):
        truth_raw=TRUTH.read_bytes()
        self.assertEqual(hashlib.sha256(truth_raw).hexdigest(),TRUTH_SHA)
        truth=json.loads(truth_raw)
        self.assertEqual(truth['schema'],'perf-integrated-001-independent-truth-v2')
        self.assertEqual(truth['input_snapshot_sha256'],SNAPSHOT_SHA)
        snapshots={state:snapshot_meshes(state) for state in ('initial','changed')}
        np.testing.assert_array_equal(snapshots['initial']['Object_01'].bbox_min,snapshots['changed']['Object_01'].bbox_min)
        np.testing.assert_array_equal(snapshots['initial']['Object_01'].bbox_max,snapshots['changed']['Object_01'].bbox_max)
        rows=[]
        with patch.object(task_query, 'classify_closed_solids', wraps=closed.classify_closed_solids) as measured, \
             patch.object(task_query, 'measure_pair_geometry', side_effect=AssertionError('new task did not request legacy tolerance solver')):
            for state in ('initial','unchanged','changed'):
                meshes=snapshots['changed' if state=='changed' else 'initial']; distances={}
                for candidate in ('Object_02','Object_03','Object_04'):
                    expected=truth['states'][state]['probes'][candidate]
                    self.set_pair(clone(meshes['Object_01'],'a'),clone(meshes[candidate],'b'),'assembly-'+state)
                    result=self.observe(('closed_solid_relation','surface_proximity'))
                    self.relation(result,expected['relation']); work=self.work()
                    gap=result['facts']['surface_proximity']['value']['distance_m']
                    if expected['relation']=='separated':
                        self.assertEqual(result['facts']['surface_proximity']['status'],'measured')
                        self.assertLessEqual(abs(gap-expected['minimum_gap_m'])+expected['distance_error_bound_m'],truth['answer_distance_tolerance_m'])
                        self.assertLessEqual(expected['distance_interval_m'][0],gap)
                        self.assertLessEqual(gap,expected['distance_interval_m'][1])
                        distances[candidate]=gap
                    rows.append(dict(state=state,candidate=candidate,relation=expected['relation'],surface_distance_m=gap,work=work))
                self.assertEqual(min(distances,key=distances.get),truth['states'][state]['nearest_separated_probe'])
        self.assertEqual(measured.call_count,6)
        self.assertTrue(all(row['work']['closed_solid_pair_cache_hit'] for row in rows if row['state']=='unchanged'))
        self.assertTrue(all(not row['work']['closed_solid_pair_cache_hit'] for row in rows if row['state']!='unchanged'))
        EVIDENCE['g16_original_three_state']=rows
        EVIDENCE['g16_independent_sources']={'snapshot_sha256':SNAPSHOT_SHA,'truth_sha256':TRUTH_SHA,
            'truth_rule':'abs(distance-d0)+distance_error_bound_m <= 1e-6 and original distance interval membership'}


if __name__ == '__main__': unittest.main()
