"""Frozen analytic/independent counterexamples for the M3 pair candidate."""

import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from human_eye_plugin import surface_geometry as closed, surface_proximity as exact
from verification.test_surface_geometry import oracle as independent_intersection


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DESIGNED = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
EVIDENCE = {}


def mesh(raw):
    return types.SimpleNamespace(vertices=[tuple(point) for point in raw.get('vertices_world',raw.get('vertices'))],
        faces=[tuple(face) for face in raw.get('triangles',raw.get('faces'))])


def prepared(left,right):
    work = exact._Work(lambda stage:None,{})
    records,topology = exact._admit((left,right),work)
    origin,factor,triangles = exact._integer_frame(records,work)
    return records,topology,origin,factor,triangles


def frozen_reference():
    package = types.ModuleType('_m3_mechanism_old_kernel')
    package.__path__ = []
    sys.modules[package.__name__] = package
    manifest = json.loads((HERE/'baseline/MANIFEST.json').read_bytes())
    pins = {row['path']:row['sha256'] for row in manifest['source_manifest']}
    for name in ('surface_proximity','surface_geometry'):
        path = HERE/'baseline/product/human_eye_plugin'/(name+'.py')
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==pins['human_eye_plugin/'+name+'.py']
        module = types.ModuleType(package.__name__+'.'+name)
        module.__file__ = str(path)
        module.__package__ = package.__name__
        sys.modules[module.__name__] = module
        setattr(package,name,module)
        exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    package.surface_proximity.MAX_TRIANGLE_PAIRS = 1_000_000_000
    return package.surface_proximity


class PairScalabilityTests(unittest.TestCase):
    def test_plane_bound_strict_sides_crossing_degenerate_and_max_bits(self):
        for case in DESIGNED['plane_bound_cases']:
            with self.subTest(case=case['id']):
                if 'other_z' in case:
                    distances = case['other_z']
                    squared = sum(value*value for value in case['normal'])
                else:
                    distances = [int(case['projection_gap'])]*3
                    squared = int(case['normal_squared'])
                best = tuple(case['best_squared'])
                same_side = all(value>0 for value in distances) or all(value<0 for value in distances)
                independent = bool(squared and same_side and F(min(map(abs,distances))**2,squared)>F(*best))
                self.assertEqual(independent,case['prune'])
                self.assertIs(exact._plane_exceeds_best(distances,squared,best),independent)
                EVIDENCE[case['id']] = {'distances':distances,'normal_squared':squared,'best':best,'prune':independent}

    def test_projection_cache_keeps_original_intersection_and_avoids_reprojection(self):
        case = next(row for row in DESIGNED['shared_simplex_cases'] if row['id']=='no_shared_index_crossing')
        left = mesh({'vertices':case['vertices'],'faces':[case['faces'][0]]})
        right = mesh({'vertices':case['vertices'],'faces':[case['faces'][1]]})
        pair = prepared(left,right)
        a,b = pair[4][0][0],pair[4][1][0]
        budget = closed._ClosedWork(lambda stage:None,{},exact)
        da = exact._plane_distances(b[0],a[0][0],a[1],budget)
        db = exact._plane_distances(a[0],b[0][0],b[1],budget)
        self.assertEqual(budget.counts['plane_projection_tests'],6)
        with patch.object(exact,'_plane_distances',wraps=exact._plane_distances) as projection:
            points = exact._intersection(a[0],b[0],a[1],b[1],budget,plane_distances=(da,db))
        projection.assert_not_called()
        expected = independent_intersection(a[0],b[0])
        self.assertEqual(set(points),expected)
        EVIDENCE['cached_projection'] = {'points':points,'independent_points':sorted(expected),'work':budget.counts}

    def test_shared_simplex_precheck_never_excludes_forbidden_intersection(self):
        for case in DESIGNED['shared_simplex_cases']:
            with self.subTest(case=case['id']):
                left = mesh({'vertices':case['vertices'],'faces':[case['faces'][0]]})
                right = mesh({'vertices':case['vertices'],'faces':[case['faces'][1]]})
                pair = prepared(left,right)
                a,b = pair[4][0][0],pair[4][1][0]
                shared = sorted(set(case['faces'][0])&set(case['faces'][1]))
                budget = closed._ClosedWork(lambda stage:None,{},exact)
                excluded,projections = closed._closed_precheck(a,b,budget,shared=shared,faces=case['faces'])
                points = independent_intersection(a[0],b[0])
                self.assertTrue(points)
                vertices = {index:point for face,row in zip(case['faces'],(a,b)) for index,point in zip(face,row[0])}
                legal = closed._closed_legal_contact(points,shared,vertices,budget)
                self.assertIs(legal,case['legal_contact'])
                self.assertFalse(excluded and not legal)
                if case['id'] in ('shared_edge_noncoplanar','shared_edge_opposite_coplanar'):
                    self.assertTrue(excluded)
                if not legal:
                    self.assertFalse(excluded)
                EVIDENCE[case['id']] = {'cheap_excluded':excluded,'independent_points':sorted(points),
                    'legal_contact':legal,'cached_projections':projections,'work':budget.counts}

    def test_cube12_and_cube192_same_boundary_match_original_leaf_reference(self):
        reference = frozen_reference()
        for name in ('cube12','cube192_same_world_boundary'):
            with self.subTest(fixture=name):
                left,right = map(mesh,DESIGNED[name])
                original = reference.measure_surface_proximity(left,right,lambda stage:None)
                value = exact.measure_surface_proximity(left,right,lambda stage:None)
                self.assertTrue(original['measurement_valid'],original)
                self.assertTrue(value['measurement_valid'],value)
                self.assertEqual(original['distance_m'],1.)
                self.assertEqual(value['distance_m'],1.)
                self.assertEqual(value['witness_status'],'measured')
                EVIDENCE[name] = {'original_reference':original,'candidate':value}

    def test_surface_work_and_narrow_limits_refuse_after_last_admissible_unit(self):
        self.assertEqual((exact.MAX_WORK_UNITS,exact.MAX_NARROW_PHASE_PAIRS,exact.LINEAR_PAIR_LIMIT),(1179648,16384,256))
        work = exact._Work(lambda stage:None,{})
        work.counts['work_units'] = 1179647
        work.consume(1,'fixed_boundary')
        self.assertEqual(work.counts['work_units'],1179648)
        with self.assertRaisesRegex(exact._DomainError,'^surface_work_budget$'):
            work.consume(1,'fixed_boundary')
        work = exact._Work(lambda stage:None,{})
        work.counts['narrow_phase_pairs'] = 16383
        work.narrow_pair()
        self.assertEqual(work.counts['narrow_phase_pairs'],16384)
        with self.assertRaisesRegex(exact._DomainError,'^surface_pair_budget$'):
            work.narrow_pair()
        left,right = map(mesh,DESIGNED['cube12'])
        original_init = exact._Work.__init__
        for field,limit,reason in (('work_units',1179648,'surface_work_budget'),('narrow_phase_pairs',16384,'surface_pair_budget')):
            with self.subTest(field=field):
                def exhausted(instance,*args,**kwargs):
                    original_init(instance,*args,**kwargs)
                    instance.counts[field] = limit
                with patch.object(exact._Work,'__init__',exhausted):
                    value = exact.measure_surface_proximity(left,right,lambda stage:None)
                self.assertIs(value['measurement_valid'],False)
                self.assertEqual(value['reason'],reason)
                EVIDENCE['exhausted_'+field] = value

    def test_closed_original_work_pair_and_ray_boundaries(self):
        self.assertEqual((closed.CLOSED_SOLID_MAX_WORK,closed.CLOSED_SOLID_MAX_PAIR_TESTS,closed.CLOSED_SOLID_MAX_RAY_TESTS),
            (262144,16384,16384))
        work = closed._ClosedWork(lambda stage:None,{},exact)
        work.counts['work_units'] = 262143
        work.consume(1,'fixed_boundary')
        self.assertEqual(work.counts['work_units'],262144)
        with self.assertRaisesRegex(closed._ClosedDomain,'^closed_solid_work_budget$'):
            work.consume(1,'fixed_boundary')
        work = closed._ClosedWork(lambda stage:None,{},exact)
        work.counts['pair_tests'] = 16383
        work.pair('self_pair_tests')
        self.assertEqual(work.counts['pair_tests'],16384)
        with self.assertRaisesRegex(closed._ClosedDomain,'^closed_solid_pair_budget$'):
            work.pair('cross_pair_tests')
        left = mesh({'vertices':[[0,0,0],[1,0,0],[0,1,0]],'faces':[[0,1,2]]})
        triangle = prepared(left,left)[4][0][0]
        shell = {'triangles':[triangle]}
        for used in (16383,16384):
            work = closed._ClosedWork(lambda stage:None,{},exact)
            work.counts['ray_tests'] = used
            with patch.object(closed,'_closed_point_candidates',return_value=iter(())),\
                    patch.object(closed,'_closed_ray_candidates',return_value=iter((0,))):
                if used==16383:
                    self.assertEqual(closed._closed_location((-10,-10,-10),shell,work),'outside')
                else:
                    with self.assertRaisesRegex(closed._ClosedDomain,'^closed_solid_ray_budget$'):
                        closed._closed_location((-10,-10,-10),shell,work)
            EVIDENCE['closed_ray_boundary_'+str(used)] = dict(work.counts)

    def test_cancel_deadline_propagate_during_surface_tree_node_and_leaf(self):
        left,right = map(mesh,DESIGNED['cube192_same_world_boundary'])
        for stage in ('surface_proximity_surface_bvh_build','surface_proximity_node_pair_visits','surface_proximity_narrow_phase_pairs'):
            for exception in (RuntimeError('frozen cancellation'),TimeoutError('original deadline')):
                with self.subTest(stage=stage,error=type(exception).__name__):
                    seen = []
                    def checkpoint(value):
                        if value==stage:
                            seen.append(value)
                            raise exception
                    with self.assertRaises(type(exception)) as raised:
                        exact.measure_surface_proximity(left,right,checkpoint)
                    self.assertIs(raised.exception,exception)
                    self.assertEqual(seen,[stage])

    def test_optional_integer_candidate_guard_falls_back_but_never_swallows_cancel(self):
        left,right = map(mesh,DESIGNED['cube192_same_world_boundary'])
        pair = prepared(left,right)
        for exception in (exact._DomainError('surface_exact_bit_budget'),RuntimeError('frozen cancellation'),
                          closed._ClosedDomain('closed_solid_work_budget')):
            budget = closed._ClosedWork(lambda stage:None,{},exact)
            shells = [closed._closed_topology(record[0],record[1],triangles,budget)
                for record,triangles in zip(pair[0],pair[4])]
            with patch.object(exact,'_dot',side_effect=exception):
                if type(exception) is exact._DomainError:
                    closed._closed_candidate_trees(shells,budget)
                    self.assertEqual(budget.counts['candidate_frame_fallbacks'],1)
                    self.assertTrue(all('candidate_bounds' not in shell for shell in shells))
                else:
                    with self.assertRaises(type(exception)) as raised:
                        closed._closed_candidate_trees(shells,budget)
                    self.assertIs(raised.exception,exception)
            EVIDENCE['optional_guard_'+type(exception).__name__] = {'work':budget.counts,
                'scope':'forced exact guard branch, separate from the frozen genuine max-bit comparator cases'}

    def test_same_pair_tree_reuse_and_foreign_pair_frame_are_bound(self):
        left,right = map(mesh,DESIGNED['cube192_same_world_boundary'])
        holder = {}
        relation = closed.classify_closed_solids(left,right,lambda stage:None,prepared_holder=holder)
        self.assertIn('pair',holder)
        self.assertIn('trees',holder)
        with patch.object(exact,'_integer_frame',wraps=exact._integer_frame) as integer_frame:
            value = exact.measure_surface_proximity(left,right,lambda stage:None,_prepared_pair=holder['pair'],_prepared_trees=holder['trees'])
        integer_frame.assert_not_called()
        self.assertTrue(value['measurement_valid'],value)
        self.assertEqual(value['distance_m'],1.)
        self.assertIs(value['work']['shared_trees'],True)
        self.assertEqual(value['work']['tree_builds'],0)
        planar = DESIGNED['pair_frame_independence']
        target = mesh({'vertices':planar['target_vertices'],'faces':planar['faces']})
        comparisons = []
        for z in planar['candidate_z']:
            candidate = mesh({'vertices':[[p[0],p[1],z] for p in planar['target_vertices']],'faces':planar['faces']})
            fresh = prepared(target,candidate)
            with patch.object(exact,'_integer_frame',wraps=exact._integer_frame) as integer_frame:
                result = exact.measure_surface_proximity(target,candidate,lambda stage:None,
                    _prepared_pair=holder['pair'],_prepared_trees=holder['trees'])
            self.assertEqual(integer_frame.call_count,1)
            self.assertTrue(result['measurement_valid'],result)
            self.assertEqual(result['distance_m'],z)
            self.assertIs(result['work']['shared_trees'],False)
            comparisons.append({'factor':fresh[3],'result':result})
        self.assertNotEqual(comparisons[0]['factor'],comparisons[1]['factor'])
        EVIDENCE['pair_tree_binding'] = {'closed':relation,'shared_surface':value,'foreign_pairs':comparisons}

    def test_closed_foreign_prepare_cannot_change_containment_or_keep_old_holder(self):
        left,right = map(mesh,DESIGNED['cube12'])
        holder = {}
        first = closed.classify_closed_solids(left,right,lambda stage:None,prepared_holder=holder)
        self.assertTrue(first['measurement_valid'],first)
        foreign = holder['pair']
        # The frozen old containment control uses concentric boxes of sizes 1 and 4.
        inner = mesh({'vertices':[[(p[k]-(10. if k==0 else 0.))*.5 for k in range(3)] for p in DESIGNED['cube12'][0]['vertices']],
            'faces':DESIGNED['cube12'][0]['faces']})
        outer = mesh({'vertices':[[(p[k]-(10. if k==0 else 0.))*2 for k in range(3)] for p in DESIGNED['cube12'][0]['vertices']],
            'faces':DESIGNED['cube12'][0]['faces']})
        result = closed.classify_closed_solids(inner,outer,lambda stage:None,prepared_pair=foreign,prepared_holder=holder)
        self.assertTrue(result['measurement_valid'],result)
        self.assertEqual(result['relation'],'penetrating')
        self.assertIsNot(holder['pair'],foreign)
        self.assertIs(holder['pair'][0][0][0],inner)
        empty = types.SimpleNamespace(vertices=(),faces=())
        refused = closed.classify_closed_solids(empty,outer,lambda stage:None,prepared_holder=holder)
        self.assertFalse(refused['measurement_valid'])
        self.assertNotIn('pair',holder)
        self.assertNotIn('trees',holder)
        self.assertNotIn('boundary_contact',holder)
        EVIDENCE['closed_foreign_binding'] = {'contained':result,'early_refusal':refused}

    def test_g508_frozen_three_pairs_independent_intervals_and_complete_relations(self):
        path = ROOT/DESIGNED['g508']['snapshot']
        expected = DESIGNED['source_files'][str(path.relative_to(ROOT))]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected)
        snapshot = json.loads(path.read_bytes())
        objects = {row['name']:row for row in snapshot['objects']}
        truth = json.loads((ROOT/DESIGNED['g508']['truth']).read_bytes())
        bounds = {row['candidate_name']:(row['distance_lower_m'],row['distance_upper_m']) for row in truth['pairs']}
        for name in DESIGNED['g508']['candidates']:
            with self.subTest(candidate=name):
                left,right = mesh(objects['Target']),mesh(objects[name])
                holder = {}
                relation = closed.classify_closed_solids(left,right,lambda stage:None,prepared_holder=holder)
                value = exact.measure_surface_proximity(left,right,lambda stage:None,
                    _prepared_pair=holder.get('pair'),_prepared_trees=holder.get('trees'))
                self.assertTrue(relation['measurement_valid'],relation)
                self.assertEqual(relation['relation'],'separated')
                self.assertTrue(value['measurement_valid'],value)
                self.assertLessEqual(bounds[name][0]-1e-6,value['distance_m'])
                self.assertLessEqual(value['distance_m'],bounds[name][1]+1e-6)
                self.assertEqual(value['witness_status'],'measured')
                if name=='Peer_000':
                    self.assertLessEqual(value['work']['narrow_phase_pairs'],9395)
                EVIDENCE['g508_'+name] = {'closed':relation,'surface':value,'interval':bounds[name]}

    def test_g60_frozen_three_pair_control_retains_closed_and_surface(self):
        raw = json.loads((ROOT/DESIGNED['g60']['fixture']).read_bytes())
        objects = {row['logical_id']:row for row in raw['objects']}
        source = json.loads((ROOT/DESIGNED['g60']['truth']).read_bytes())
        truth = next(row for row in source['snapshots'] if row['id']==DESIGNED['g60']['truth_fixture_id'])
        bounds = {row['candidate']:(row['distance_lower_m'],row['distance_upper_m']) for row in truth['pairs']}
        for name in DESIGNED['g60']['candidates']:
            with self.subTest(candidate=name):
                left,right = mesh(objects['target']),mesh(objects[name])
                holder = {}
                relation = closed.classify_closed_solids(left,right,lambda stage:None,prepared_holder=holder)
                value = exact.measure_surface_proximity(left,right,lambda stage:None,
                    _prepared_pair=holder.get('pair'),_prepared_trees=holder.get('trees'))
                self.assertTrue(relation['measurement_valid'],relation)
                self.assertEqual(relation['relation'],'separated')
                self.assertTrue(value['measurement_valid'],value)
                self.assertLessEqual(bounds[name][0]-1e-6,value['distance_m'])
                self.assertLessEqual(value['distance_m'],bounds[name][1]+1e-6)
                EVIDENCE['g60_'+name] = {'closed':relation,'surface':value,'interval':bounds[name]}
