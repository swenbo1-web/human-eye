"""Offline hard gates for the unique B candidate, no Blender processes."""
import hashlib
import itertools
from fractions import Fraction as F
from pathlib import Path
import time
import types
import unittest

from verification.test_m4_capture_001 import fixture, capture, row, m, NS

A_PATH = Path('D:/hefe/verification/fixes/20261107_m4_acquisition/review_qa_001/baseline_A/human_eye_plugin/blender_host.py')
A = types.ModuleType('frozen_initial_A');A.__file__ = str(A_PATH)
assert hashlib.sha256(A_PATH.read_bytes()).hexdigest() == 'ba83c5455f0e2a9a3e67443f04f4519fa064eabd6af108a6b94d3537783baa22'
exec(compile(A_PATH.read_bytes(),str(A_PATH),'exec',dont_inherit=True),A.__dict__)
A._READONLY_LOADED_HOST_SHA256 = hashlib.sha256(A_PATH.read_bytes()).hexdigest()


def both(host):
    initial = A.BlenderSceneHost(host.bpy, identity_metadata=True)
    before = initial.capture_nearest_candidates(host.object_id(host.scene.objects[0]),time.perf_counter_ns()+10**10,1_000_000)
    return before, capture(host)


def assert_pair(test,a,b):
    test.assertEqual(set(a),set(b))
    test.assertLessEqual(b['witness_upper_bound_m'] if b['witness_upper_bound_m'] is not None else float('inf'),
                         a['witness_upper_bound_m'] if a['witness_upper_bound_m'] is not None else float('inf'))
    ids = lambda p:{r['object_id'] for r in p['coverage'] if r['disposition']=='retained'}
    test.assertLessEqual(ids(b),ids(a))
    source={mesh['object_id']:mesh for mesh in b['capture']['meshes']}
    for item in b['coverage']:
        w=item['witness']
        if w is None:continue
        old=next(r['witness'] for r in a['coverage'] if r['object_id']==item['object_id'])
        test.assertEqual(set(w),set(old))
        indices=old['triangle_vertex_indices']
        test.assertIn(w['triangle_vertex_indices'],[indices[i:]+indices[:i] for i in range(3)])
        def normal(points):
            e=[[F(points[j][k])-F(points[0][k]) for k in range(3)] for j in (1,2)]
            return [e[0][i]*e[1][j]-e[0][j]*e[1][i] for i,j in ((1,2),(2,0),(0,1))]
        test.assertEqual(normal(w['triangle_world_m']),normal(old['triangle_world_m']))
        test.assertEqual(w['point_world_m'],w['triangle_world_m'][0])
        if item['object_id'] in source:
            mesh=source[item['object_id']]
            test.assertEqual([mesh['vertices'][i] for i in w['triangle_vertex_indices']],w['triangle_world_m'])


class NinePairGates(unittest.TestCase):
    def test_loose_and_all_cyclic_orders(self):
        for rotations in itertools.product(range(3),repeat=3):
            host,objects=fixture((0.,0.,2.))
            objects[1].data.vertices=[NS(co=p) for p in ((10.,0.,0.),(.01,1.,0.),(.01,0.,1.))]
            objects[1].bound_box=list(itertools.product((.01,10.),(0.,1.),(0.,1.)))
            for obj,n in zip(objects,rotations):
                face=[0,1,2];face=face[n:]+face[:n]
                obj.data.polygons=[NS(vertices=face)];obj.data.loop_triangles=[NS(vertices=face)]
            a,b=both(host);assert_pair(self,a,b)
            self.assertLess(b['witness_upper_bound_m'],.011)
            self.assertEqual(b['work']['expanded_objects'],2)
            self.assertEqual(b['upper_seed_id'],host.object_id(objects[1]))
            if rotations==(0,0,0):self.assertEqual(a['work']['expanded_objects'],3)
            focal=row(b,host,objects[0])['witness']['triangle_world_m']
            candidates=[r['witness']['triangle_world_m'] for r in b['coverage'] if r['object_id']!=b['focal_id'] and r['witness']]
            exact=min(sum(abs(F(x[k])-F(y[k])) for k in range(3)) for tri in candidates for x in focal for y in tri)
            self.assertGreaterEqual(F(b['witness_upper_bound_m']),exact)

    def test_zero_tie_and_no_extra_reads(self):
        for xs in ((0.,0.,0.,100.),(0.,2.,2.),(0.,0.,0.,0.)):
            host,objects=fixture(xs)
            a,b=both(host);assert_pair(self,a,b)
            self.assertEqual([o.eval_calls for o in objects],[2]*len(objects))
            self.assertEqual(host.updates,2)
            if xs[1]==0:self.assertEqual(b['witness_upper_bound_m'],0.)

    def test_missing_or_degenerate_witness(self):
        for object_index in (0,2):
            host,objects=fixture()
            objects[object_index].data.vertices[2].co=(0.,2.,0.)
            a,b=both(host);assert_pair(self,a,b)
            self.assertIsNone(row(b,host,objects[object_index])['witness'])
            if object_index==0:self.assertIsNone(b['witness_upper_bound_m'])

    def test_extreme_nonfinite_upper_is_unknown(self):
        host,objects=fixture((-1e308,1e308))
        a,b=both(host);assert_pair(self,a,b)
        self.assertIsNone(a['witness_upper_bound_m'])
        self.assertIsNone(b['witness_upper_bound_m'])
        self.assertEqual(b['work']['expanded_objects'],2)

    def test_subset_with_bad_bounds(self):
        host,objects=fixture()
        objects[2].bound_box=None
        a,b=both(host);assert_pair(self,a,b)
        self.assertEqual(row(b,host,objects[2])['disposition'],'retained')


if __name__=='__main__':unittest.main()
