"""Ten fixed integration groups: authentic packet shape, real kernel, no host RPC.

Packet geometry is an offline fixture. Expected distances come from independent
Fraction/plane/corner constructions, never the integration function itself.
The parent runner executes product bytes through verified_source_loader.
"""
import copy
from fractions import Fraction as F
import hashlib
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import auto_router, surface_proximity as surface, task_query
from human_eye_plugin.live_service import RequestBudgetError
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification.test_concave_geometry import entity
from verification.test_task_complete_001 import large_world_pair


EVIDENCE = {}
NOOP = lambda stage: None


def triangle(identity, points):
    return entity(identity, points, [[0, 1, 2]])


def yz(identity, x):
    return triangle(identity, [(x, 0, 0), (x, 1, 0), (x, 0, 1)])


def corner(identity, x, y=0.):
    return triangle(identity, [(x, y, 0), (x+1, y, 0), (x, y+1, 0)])


def negative_focal():
    return triangle('f', [(0, 0, 0), (-1, 0, 0), (0, -1, 0)])


def far_with_late_line(late_x=100):
    return entity('far', [(100,0,0),(100,1,0),(100,0,1),
                          (late_x,2,0),(late_x,3,0),(late_x,4,0)], [[0,1,2],[3,4,5]])


def key_square(result):
    n, d, e = result['_exact_distance_sq']
    return F(n, d) * F(2) ** e


def full_box_oracle(left, right):
    corner_point = [F(float(v)) for v in np.max(right.vertices[:, :2], axis=0)]
    assert (np.min(left.vertices[:, :2], axis=0) > np.max(right.vertices[:, :2], axis=0)).all()
    assert max(min(left.vertices[:, 2]), min(right.vertices[:, 2])) <= min(max(left.vertices[:, 2]), max(right.vertices[:, 2]))
    polygon = [[F(float(v)) for v in row] for row in left.vertices[:4, :2]]
    squares = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        edge, offset = [y-x for x, y in zip(a, b)], [p-x for p, x in zip(corner_point, a)]
        t = max(F(0), min(F(1), sum(x*y for x, y in zip(offset, edge))/sum(x*x for x in edge)))
        squares.append(sum((x-t*y)**2 for x, y in zip(offset, edge)))
    return min(squares)


def upper_l1(left, right):
    total = 0.
    for a, b in zip(left, right):
        if a != b:
            total = math.nextafter(total + math.nextafter(abs(a-b), math.inf), math.inf)
    return total


def packet_for(focal, targets, *, unknown_bounds=(), unknown_witness=()):
    """One offline packet; mirrors current numeric/schema contract, no capture."""
    objects = [focal] + list(targets)
    dictionaries = {mesh.object_id: mesh.to_dict() for mesh in objects}
    rows = {}
    for mesh in objects:
        points = dictionaries[mesh.object_id]['vertices']
        bounds = None if mesh.object_id in unknown_bounds else [list(np.min(points, axis=0)), list(np.max(points, axis=0))]
        face = list(dictionaries[mesh.object_id]['faces'][0])
        vertices = [points[i] for i in face]
        edges = [[F(float(vertices[j][k]))-F(float(vertices[0][k])) for k in range(3)] for j in (1, 2)]
        normal = [edges[0][i]*edges[1][j]-edges[0][j]*edges[1][i] for i, j in ((0, 1), (0, 2), (1, 2))]
        witness = None if mesh.object_id in unknown_witness or not any(normal) else dict(
            point_world_m=list(vertices[0]), triangle_vertex_indices=face, triangle_world_m=copy.deepcopy(vertices))
        rows[mesh.object_id] = dict(object_id=mesh.object_id, bounds_world_m=bounds, witness=witness)
    seed, upper, offsets = None, math.inf, (0, 0)
    focal_witness = rows[focal.object_id]['witness']
    for target in targets:
        witness = rows[target.object_id]['witness']
        if focal_witness is not None and witness is not None:
            for fi, a in enumerate(focal_witness['triangle_world_m']):
                for ti, b in enumerate(witness['triangle_world_m']):
                    value = upper_l1(a, b)
                    if value < upper:
                        seed, upper, offsets = target.object_id, value, (fi, ti)
    if seed is not None:
        for oid, offset in ((focal.object_id, offsets[0]), (seed, offsets[1])):
            witness = rows[oid]['witness']
            for field in ('triangle_vertex_indices', 'triangle_world_m'):
                value = witness[field]; witness[field] = value[offset:] + value[:offset]
            witness['point_world_m'] = witness['triangle_world_m'][0]
    retained = []
    focal_bounds = rows[focal.object_id]['bounds_world_m']
    for mesh in objects:
        row = rows[mesh.object_id]; bounds = row['bounds_world_m']
        lower = (max(0., *(math.nextafter(focal_bounds[0][k]-bounds[1][k], -math.inf) for k in range(3)),
                     *(math.nextafter(bounds[0][k]-focal_bounds[1][k], -math.inf) for k in range(3)))
                 if bounds is not None and focal_bounds is not None else 0.)
        excluded = mesh.object_id not in (focal.object_id, seed) and row['witness'] is not None and lower > upper
        row.update(lower_bound_m=lower, disposition='excluded_strict_bound' if excluded else 'retained',
                   bounds_status='enclosed' if bounds is not None else 'unknown')
        if not excluded:
            retained.append(dictionaries[mesh.object_id])
    instances = {mesh.object_id: str(index+1) for index, mesh in enumerate(objects)}
    epoch = '1'*64
    host_identity = dict(schema_version='1.0', document_epoch=epoch, object_instances=instances,
                         capture_scope='complete_scene_meshes')
    capture_identity = dict(host_identity, object_instances={m['object_id']: instances[m['object_id']] for m in retained},
                            capture_scope='surface_nearest_candidates')
    coverage = list(rows.values())
    digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    capture = dict(revision='fixture:'+digest(retained), source='blender', unit='m', coordinate_frame='world',
                   capture_scope='surface_nearest_candidates', host_identity=capture_identity, meshes=retained)
    host_sha = next(r['sha256'] for r in runtime_identity()['source_files'] if r['path']=='human_eye_plugin/blender_host.py')
    return dict(protocol='single-read-surface-candidates-v1', capture=capture, focal_id=focal.object_id,
        coverage=coverage, scope='independent_static_triangle_meshes_current_evaluated_surfaces',
        bound_method='outward_evaluated_local_box_affine_linf', upper_method='outward_L1_real_triangle_vertex_pair',
        M3_qualification_performed=False, witness_upper_bound_m=upper if math.isfinite(upper) else None,
        upper_seed_id=seed, unresolved_bounds_ids=[r['object_id'] for r in coverage if r['bounds_status']=='unknown'],
        unresolved_witness_ids=[r['object_id'] for r in coverage if r['witness'] is None],
        binding=dict(host_source_sha256=host_sha, host_identity=host_identity, frame=1, scale_length=1.,
            coordinate_frame='world', unit='m', same_main_thread_read=True, external_edit_history_proven=False,
            directory_sha256=digest(coverage)),
        work=dict(directory_objects=len(objects), source_vertices=sum(len(m.vertices) for m in objects),
            source_faces=sum(len(m.faces) for m in objects), expanded_objects=len(retained),
            expanded_vertices=sum(len(m['vertices']) for m in retained), expanded_faces=sum(len(m['faces']) for m in retained)),
        result_kind='acquisition_only_not_nearest_result', execution_authority=False)


class NearestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(offline_capture_calls=0, pair_calls=0, kernel_calls=0, nearest_calls=0,
                       rank_calls=0, pair_records=[], kernel_records=[], observations=[])
        self.oracles = {}
        EVIDENCE[self._testMethodName] = self.row
        pair_original = task_query._surface_pair_measurement
        kernel_original = surface.measure_surface_proximity
        nearest_original, rank_original = surface._nearest, surface._rank_surface_results
        def pair(left, right, cache, checkpoint, **kwargs):
            self.row['pair_calls'] += 1
            self.assertIs(kwargs.get('retain_exact_rank'), True)
            result = pair_original(left, right, cache, checkpoint, **kwargs)
            self.row['pair_records'].append(dict(focal_id=left.object_id, target_id=right.object_id,
                cache_hit=kwargs['diagnostics']['surface_pair_cache_hit'],
                kernel_calls=kwargs['diagnostics']['surface_pair_count']))
            return result
        def measured(left, right, checkpoint, **kwargs):
            self.row['kernel_calls'] += 1
            result = kernel_original(left, right, checkpoint, **kwargs)
            oracle = self.oracles.get(right.object_id)
            if result['measurement_valid'] and oracle is not None:
                self.assertEqual(key_square(result), oracle)
            self.row['kernel_records'].append(dict(target_id=right.object_id, oracle_squared=str(oracle),
                result=copy.deepcopy(result)))
            return result
        def nearest(*args, **kwargs):
            self.row['nearest_calls'] += 1
            return nearest_original(*args, **kwargs)
        def rank(*args, **kwargs):
            self.row['rank_calls'] += 1
            before = self.row['nearest_calls']; result = rank_original(*args, **kwargs)
            self.assertEqual(self.row['nearest_calls'], before)
            return result
        targets = [(task_query, '_surface_pair_measurement', pair),
                   (task_query, 'measure_surface_proximity', measured),
                   (surface, 'measure_surface_proximity', measured),
                   (surface, '_nearest', nearest), (surface, '_rank_surface_results', rank)]
        if hasattr(task_query, '_rank_surface_results'):
            targets.append((task_query, '_rank_surface_results', rank))
        for owner, name, replacement in targets:
            manager=patch.object(owner, name, replacement);manager.start();self.addCleanup(manager.stop)

    def summarize(self, packet, *, cache=None, checkpoint=NOOP):
        cache = SpatialSceneCache() if cache is None else cache
        diagnostics = {}
        before = {k:self.row[k] for k in ('pair_calls','kernel_calls','nearest_calls','rank_calls')}
        result = task_query.surface_nearest_result(packet, cache, checkpoint, diagnostics=diagnostics)
        deltas = {k:self.row[k]-v for k,v in before.items()}
        self.assertEqual(deltas['rank_calls'], 1)
        self.assertEqual(deltas['pair_calls'], len(packet['capture']['meshes'])-1)
        self.assertLessEqual(deltas['nearest_calls'], deltas['kernel_calls'])
        self.assertEqual(cache.stats()['frames'], 0)
        self.assertFalse(result['execution_authority'])
        self.assertEqual(result['scope'], 'surface_nearest_candidates')
        self.assertNotIn('_exact_distance_sq', json.dumps(result))
        self.row['observations'].append(dict(result=copy.deepcopy(result), diagnostics=diagnostics, count_deltas=deltas))
        return result

    def test_g01_normal_unique_and_explicit_scope(self):
        packet = packet_for(yz('f', 0.), [yz('near', 2.)]);self.oracles={'near':F(4)}
        result = self.summarize(packet)
        self.assertEqual(result['status'], 'complete');self.assertEqual(result['nearest_ids'], ['near'])
        self.assertEqual(result['distance_m'], 2.)
        self.assertEqual(result['coverage'], dict(targets_excluding_focal=1,distance_valid=1,strictly_excluded=0,unresolved=0))
        scene, _, fingerprint = auto_router._validated_scene(packet['capture'], _surface_nearest_capture=True)
        self.assertEqual(scene['capture_scope'], 'surface_nearest_candidates')
        with self.assertRaises(ValueError):auto_router._validated_scene(packet['capture'])
        complete = copy.deepcopy(packet['capture']);complete['capture_scope']='complete_scene_meshes'
        complete['host_identity']['capture_scope']='complete_scene_meshes'
        _, _, full_fingerprint = auto_router._validated_scene(complete)
        self.assertNotEqual(fingerprint, full_fingerprint)

    def test_g02_exact_positive_and_zero_ties_stable_ids(self):
        focal = triangle('f', [(-2,-2,4),(4,-2,-2),(-2,4,-2)])
        a=triangle('a',[(0,0,1),(1,0,2),(0,1,2)]);z=triangle('z',[(0,0,1),(.5,0,1.5),(0,.5,1.5)])
        self.oracles={'a':F(1,3),'z':F(1,3)}
        result=self.summarize(packet_for(focal,[z,a]));self.assertEqual(result['nearest_ids'],['a','z'])
        focal=negative_focal();a=triangle('a',focal.vertices.tolist());z=triangle('z',[(0,0,0),(-.5,0,0),(0,-.5,0)])
        self.oracles={'a':F(0),'z':F(0)}
        result=self.summarize(packet_for(focal,[z,a]));self.assertEqual(result['nearest_ids'],['a','z'])
        self.assertEqual(result['distance_m'],0.)

    def test_g03_equal_published_float_exact_order(self):
        epsilon=2.**-27
        self.oracles={'a':F(1),'b':F(1)+F(epsilon)**2}
        result=self.summarize(packet_for(negative_focal(),[corner('b',1.,epsilon),corner('a',1.)]))
        self.assertEqual(result['nearest_ids'],['a']);self.assertEqual(result['distance_m'],1.)
        self.assertEqual({r['result']['distance_m'] for r in self.row['kernel_records']},{1.})

    def test_g04_cross_pair_scale_exact_world_order(self):
        epsilon=2.**-200
        a=corner('a',2.,epsilon);b=triangle('b',[(6,0,0),(0,6,0),(6,6,0)])
        self.oracles={'a':F(4)+F(epsilon)**2,'b':F(18)}
        result=self.summarize(packet_for(negative_focal(),[b,a]))
        self.assertEqual(result['coverage']['distance_valid'],2)
        self.assertEqual(result['nearest_ids'],['a'])

    def test_g05_excluded_far_late_degenerate_never_measured(self):
        far=far_with_late_line()
        packet=packet_for(yz('f',0.),[yz('near',2.),far]);self.oracles={'near':F(4)}
        self.assertEqual([r['object_id'] for r in packet['coverage'] if r['disposition']=='excluded_strict_bound'],['far'])
        result=self.summarize(packet)
        self.assertEqual(result['nearest_ids'],['near']);self.assertEqual(result['coverage']['strictly_excluded'],1)
        self.assertEqual(self.row['pair_records'][0]['target_id'],'near')
        self.assertEqual((self.row['kernel_calls'],self.row['nearest_calls']),(1,1))
        self.assertEqual(set(result['excluded'][0]),{'object_id','status','reason'})
        self.assertEqual(result['excluded'][0]['status'],'not_evaluated_pruned')
        self.assertNotIn('surface_degenerate_triangle',json.dumps(result['excluded']))

    def test_g06_retained_unknown_partial_unknown_and_zero_unknown_tie(self):
        far=far_with_late_line(1)
        self.oracles={'near':F(4)}
        result=self.summarize(packet_for(yz('f',0.),[yz('near',2.),far]))
        self.assertEqual(result['status'],'partial');self.assertIsNone(result['nearest_ids']);self.assertIsNone(result['distance_m'])
        self.assertEqual(result['best_known_ids'],['near']);self.assertEqual(result['unresolved'],{'far':'surface_degenerate_triangle'})
        focal=negative_focal();zero=triangle('zero',focal.vertices.tolist())
        bad=triangle('bad',[(0,0,0),(1,0,0),(2,0,0)]);self.oracles={'zero':F(0)}
        result=self.summarize(packet_for(focal,[zero,bad]))
        self.assertEqual(result['status'],'partial');self.assertIsNone(result['nearest_ids'])
        self.assertEqual(result['best_known_distance_m'],0.);self.assertIn('bad',result['unresolved'])
        result=self.summarize(packet_for(focal,[bad]));self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['nearest_ids']);self.assertEqual(result['best_known_ids'],[])

    def test_g07_unknown_bounds_or_witness_retained_full_measurement_completes(self):
        self.oracles={'near':F(4)}
        for kwargs in (dict(unknown_bounds={'near'}),dict(unknown_witness={'near'})):
            with self.subTest(unknown=list(kwargs)):
                packet=packet_for(yz('f',0.),[yz('near',2.)],**kwargs)
                result=self.summarize(packet)
                self.assertEqual(result['status'],'complete');self.assertEqual(result['nearest_ids'],['near'])
                self.assertEqual(result['coverage']['strictly_excluded'],0)

    def test_g08_valid_distance_with_unpublished_world_witness(self):
        focal,target=large_world_pair();self.oracles={target.object_id:full_box_oracle(focal,target)}
        result=self.summarize(packet_for(focal,[target]))
        self.assertEqual(result['status'],'complete');self.assertEqual(result['nearest_ids'],[target.object_id])
        self.assertEqual(result['measurement_notes'][target.object_id]['witness_status'],'unknown')
        self.assertEqual(self.row['nearest_calls'],1)

    def test_g09_directory_capture_identity_mismatches_reject_before_pairs(self):
        valid=packet_for(yz('f',0.),[yz('near',2.)]);variants=[]
        p=copy.deepcopy(valid);p['coverage'].append(copy.deepcopy(p['coverage'][0]));variants.append(('duplicate',p))
        p=copy.deepcopy(valid);p['binding']['host_identity']['object_instances']['extra']='3';variants.append(('missing_directory',p))
        p=copy.deepcopy(valid);p['capture']['meshes']=p['capture']['meshes'][:1];variants.append(('retained_set',p))
        p=copy.deepcopy(valid);p['capture']['host_identity']['document_epoch']='2'*64;variants.append(('epoch',p))
        p=copy.deepcopy(valid);p['capture']['host_identity']['object_instances']['near']='changed';variants.append(('instance',p))
        p=copy.deepcopy(valid);p['binding']['host_source_sha256']='0'*64;variants.append(('source',p))
        p=copy.deepcopy(valid);p['capture']['capture_scope']='complete_scene_meshes';variants.append(('scope',p))
        # Reuse group5 geometry, changing only the focal-envelope metadata.
        # A real unknown focal box forces host L=0, so an old strict exclusion
        # cannot remain a valid current proof even when all IDs still align.
        p=packet_for(yz('f',0.),[yz('near',2.),far_with_late_line()])
        focal_row=next(r for r in p['coverage'] if r['object_id']=='f')
        focal_row.update(bounds_status='unknown',bounds_world_m=None,lower_bound_m=0.)
        p['unresolved_bounds_ids']=['f']
        variants.append(('excluded_with_unknown_focal_envelope',p))
        for name,packet in variants:
            with self.subTest(mismatch=name):
                with self.assertRaises(ValueError):self.summarize(packet)
        self.assertEqual(self.row['pair_calls'],0);self.assertEqual(self.row['nearest_calls'],0)
        self.row['rejected_variants']=[name for name,_ in variants]

    def test_g10_cache_hits_and_before_after_hit_deadlines(self):
        packet=packet_for(yz('f',0.),[yz('near',2.)]);cache=SpatialSceneCache();self.oracles={'near':F(4)}
        self.summarize(packet,cache=cache);result=self.summarize(packet,cache=cache)
        self.assertEqual(result['nearest_ids'],['near'])
        self.assertEqual(self.row['observations'][-1]['count_deltas']['kernel_calls'],0)
        self.assertEqual(self.row['observations'][-1]['diagnostics']['cache_hits'],1)
        error=RequestBudgetError('expired','integration_hit_deadline');stages=[]
        threshold=self.row['pair_calls']+1
        def after_hit(stage):
            stages.append(stage)
            if self.row['pair_calls']>=threshold:raise error
        with self.assertRaises(RequestBudgetError) as caught:self.summarize(packet,cache=cache,checkpoint=after_hit)
        self.assertIs(caught.exception,error);self.assertTrue(self.row['pair_records'][-1]['cache_hit'])
        self.assertEqual((self.row['kernel_calls'],self.row['nearest_calls']),(1,1))
        before=self.row['pair_calls']
        def expired(stage):raise error
        with self.assertRaises(RequestBudgetError) as caught:self.summarize(packet,cache=cache,checkpoint=expired)
        self.assertIs(caught.exception,error);self.assertEqual(self.row['pair_calls'],before)
        self.row['after_hit_deadline_stages']=stages
