"""Permutation-invariant reliability and independent short-direction oracles.

This suite uses NumPy QR/SVD and authored coordinate perturbations as truth;
it does not use the production estimate to construct expected metrics.
"""
import copy,itertools,math,time,unittest
import numpy as np
from human_eye_plugin import surface_deformation as d

ORDERS=tuple(itertools.permutations(range(3)))


def qr_svd(original,current):
    old=np.asarray(original,dtype=float);new=np.asarray(current,dtype=float)
    old_edges=(old[1:]-old[0]).T;new_edges=(new[1:]-new[0]).T
    _orthogonal,chart=np.linalg.qr(old_edges,mode='reduced')
    gradient=np.linalg.solve(chart.T,new_edges.T).T
    factors=np.linalg.svd(gradient,compute_uv=False)
    area=np.linalg.norm(np.cross(new_edges[:,0],new_edges[:,1]))/np.linalg.norm(np.cross(old_edges[:,0],old_edges[:,1]))
    return factors,float(area)


def skinny(height):return [[0.,0.,0.],[1.,0.,0.],[0.,height,0.]]


class DeformationPrecisionTests(unittest.TestCase):
    def facts(self,old,new,**kwargs):
        return d.triangle_facts(copy.deepcopy(old),copy.deepcopy(new),deadline_ns=time.perf_counter_ns()+2_000_000_000,**kwargs)

    def permutations(self,old,new):
        return [self.facts([old[i] for i in order],[new[i] for i in order]) for order in ORDERS]

    def assert_reliability_equal(self,rows):
        fields=('state','reason','reference_geometry','current_geometry','estimated_stretch_error',
            'estimated_area_ratio_error','change_detectable','principal_stretches','area_ratio')
        for row in rows[1:]:
            for field in fields:self.assertEqual(row[field],rows[0][field],field)

    def test_original_skinny_counterexample_is_unknown_for_all_six_orders(self):
        old=skinny(1e-4);rows=self.permutations(old,old)
        self.assert_reliability_equal(rows)
        self.assertTrue(all(row['state']=='unknown' and row['reason']=='metric_resolution_insufficient' for row in rows))
        self.assertGreater(rows[0]['estimated_stretch_error'],d.MAX_STRETCH_ERROR)
        # Reordering alone can pick a tiny first edge whose corresponding
        # height is one, recreating the old optimistic error estimate.
        per_coordinate=8*2**-24
        old_optimistic=32*(2*per_coordinate)/1.
        self.assertLess(old_optimistic,d.MAX_STRETCH_ERROR)

    def test_short_edge_perturbation_does_not_change_reliability_by_vertex_order(self):
        old=skinny(1e-4);new=copy.deepcopy(old);new[2][1]+=1e-7
        for order in ORDERS:
            factors,_=qr_svd([old[i] for i in order],[new[i] for i in order])
            np.testing.assert_allclose(factors,[1.001,1.],atol=2e-12)
        rows=self.permutations(old,new);self.assert_reliability_equal(rows)
        self.assertTrue(all(row['state']=='unknown' for row in rows))

    def test_resolution_and_precision_threshold_sides_are_invariant_and_conservative(self):
        for height,state in ((7e-6,'unknown'),(.003,'unknown'),(.0031,'unknown'),(.004,'measured'),(.005,'measured')):
            with self.subTest(height=height):
                old=skinny(height);rows=self.permutations(old,old);self.assert_reliability_equal(rows)
                self.assertTrue(all(row['state']==state for row in rows))
                if state=='measured':np.testing.assert_allclose(rows[0]['principal_stretches'],[1.,1.],atol=2e-12)

    def test_precision_boundary_adjacent_floats_do_not_split_vertex_permutations(self):
        # Search only establishes an input close to either fixed public error
        # gate; each order then must return the identical conservative answer.
        lo,hi=.003,.004
        for _ in range(60):
            mid=(lo+hi)/2;row=self.facts(skinny(mid),skinny(mid))
            if row['state']=='measured':hi=mid
            else:lo=mid
        for height in (lo,hi,math.nextafter(lo,0.),math.nextafter(hi,math.inf)):
            with self.subTest(height=height):
                rows=self.permutations(skinny(height),skinny(height));self.assert_reliability_equal(rows)
                value=max(rows[0]['estimated_stretch_error']/d.MAX_STRETCH_ERROR,
                    rows[0]['estimated_area_ratio_error']/d.MAX_AREA_ERROR)
                self.assertLess(abs(value-1.),1e-10)

    def test_centered_reference_scale_matches_independent_svd_across_shapes_and_scales(self):
        random=np.random.default_rng(20261102)
        for height in (1e-9,1e-5,.01,.3,1.):
            for scale in (1e-30,1e-12,1.,3.):
                points=np.asarray(skinny(height))*scale
                q,_r=np.linalg.qr(random.normal(size=(3,3)));points=points@q
                center=points.mean(axis=0);reference=(points-center).T
                expected=np.linalg.svd(reference,compute_uv=False)[1]
                lengths=[np.linalg.norm(points[(i+1)%3]-points[i]) for i in range(3)]
                area=float(np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0])))
                actual=d.reference_minimum_scale(points.tolist(),max(lengths),area)
                with self.subTest(height=height,scale=scale):
                    self.assertAlmostEqual(actual/expected,1.,delta=3e-7 if height<1e-8 else 1e-10)

    def test_single_anchor_singular_value_is_not_used_as_an_invariant(self):
        points=np.asarray(skinny(1e-4));anchored=[]
        for order in ((0,1,2),(1,2,0),(2,0,1)):
            value=points[list(order)];anchored.append(np.linalg.svd((value[1:]-value[0]).T,compute_uv=False)[1])
        self.assertGreater(max(anchored)/min(anchored),1.4)
        rows=self.permutations(points.tolist(),points.tolist());self.assert_reliability_equal(rows)

    def test_adversarial_short_direction_coordinate_errors_fit_the_reported_envelope(self):
        old=np.asarray(skinny(.012));new=old@np.array([[1.1,.15,0.],[0.,.75,0.],[0.,0.,1.]]).T
        row=self.facts(old.tolist(),new.tolist());self.assertEqual(row['state'],'measured')
        nominal,nominal_area=qr_svd(old,new)
        _left,_scales,right=np.linalg.svd((old-old.mean(axis=0)).T,full_matrices=False)
        # Coordinate budgets come from the documented binary32 model, not the
        # production estimate. Noise aligned with the reference short mode
        # tests the direction that the old first-edge-height rule could miss.
        q0=8*(2**-24*np.max(np.abs(old))+2**-149);q1=8*(2**-24*np.max(np.abs(new))+2**-149)
        random=np.random.default_rng(591491)
        variations=[(random.uniform(-q0,q0,old.shape),random.uniform(-q1,q1,new.shape)) for _ in range(96)]
        for sign in (-1.,1.):
            reference_noise=np.outer(right[1],np.array([0.,1.,0.]))
            reference_noise*=q0/np.max(np.abs(reference_noise))
            current_noise=np.outer(right[1],np.array([1.,-1.,0.]))
            current_noise*=q1/np.max(np.abs(current_noise))
            variations.append((sign*reference_noise,-sign*current_noise))
        for index,(a,b) in enumerate(variations):
            with self.subTest(index=index):
                actual,area=qr_svd(old+a,new+b)
                self.assertLessEqual(float(np.max(np.abs(actual-nominal))),row['estimated_stretch_error'])
                self.assertLessEqual(abs(area-nominal_area),row['estimated_area_ratio_error'])

    def test_short_direction_error_is_exercised_rather_than_only_long_edge_noise(self):
        old=np.asarray(skinny(.012));new=old.copy();row=self.facts(old.tolist(),new.tolist())
        self.assertEqual(row['state'],'measured')
        _left,_scales,right=np.linalg.svd((old-old.mean(axis=0)).T,full_matrices=False)
        changes=[]
        for index,direction in ((0,[1.,0.,0.]),(1,[0.,1.,0.])):
            noise=np.outer(right[index],direction);noise*=1e-7/np.max(np.abs(noise))
            factors,_area=qr_svd(old,new+noise);changes.append(float(np.max(np.abs(factors-1))))
        self.assertGreater(changes[1],20*changes[0]);self.assertLess(changes[1],row['estimated_stretch_error'])

    def test_exact_degenerate_states_and_source_unknown_are_not_weakened(self):
        unit=skinny(1.);line=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        for old,new,reason in ((line,unit,'original_zero_area'),(unit,line,'current_zero_area')):
            rows=self.permutations(old,new);self.assert_reliability_equal(rows)
            self.assertTrue(all(row['reason']==reason for row in rows))
        self.assertEqual(self.facts(unit,unit,unweighted=[12])['reason'],'unweighted_vertex_source')

    def test_reliable_affine_metrics_and_inputs_remain_unchanged_under_permutations(self):
        old=np.asarray([[.1,.2,-.1],[1.1,.3,.2],[.2,1.2,.4]])
        new=old@np.array([[1.3,.2,0.],[0.,.8,.1],[.1,0.,1.1]]).T
        original=old.tolist();current=new.tolist();before=copy.deepcopy((original,current))
        rows=self.permutations(original,current);self.assert_reliability_equal(rows)
        factors,area=qr_svd(original,current)
        self.assertEqual(rows[0]['state'],'measured');np.testing.assert_allclose(rows[0]['principal_stretches'],factors,atol=2e-12)
        self.assertAlmostEqual(rows[0]['area_ratio'],area,places=12);self.assertEqual((original,current),before)


if __name__=='__main__':unittest.main()
