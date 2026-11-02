"""Public analytic truths qualify the independent SAT and metric QA oracle."""
import itertools,math,unittest
from fractions import Fraction as F
from verification import deformation_region_oracle as q


class RegionOracleTests(unittest.TestCase):
    BOX=[[-1.,-1.,-1.],[1.,1.,1.]]
    def test_analytic_contact_and_separation(self):
        cases=[('inside',[[0,0,0],[.5,0,0],[0,.5,0]],True),
            ('outside',[[2,0,0],[3,0,0],[2,1,0]],False),
            ('vertices_and_centroid_outside_edge_crosses',[[-3,0,0],[3,0,0],[3,6,0]],True),
            ('interior_only',[[-6,-6,0],[6,-6,0],[0,6,0]],True),
            ('aabb_false_positive',[[0,3,0],[3,0,0],[3,3,0]],False),
            ('face_touch',[[1,0,0],[1,2,0],[1,0,2]],True),
            ('edge_touch',[[1,1,-2],[1,1,2],[2,2,0]],True),
            ('point_touch',[[1,1,1],[2,1,1],[1,2,1]],True),
            ('nextafter_separate',[[math.nextafter(1.,math.inf),0,0],[2,0,0],[2,1,0]],False)]
        for name,triangle,truth in cases:
            for permutation in itertools.permutations(triangle):
                with self.subTest(name=name,permutation=permutation):self.assertEqual(q.triangle_box_sat(permutation,self.BOX),truth)
    def test_degenerate_segments_and_points(self):
        for triangle,truth in [([[-2,0,0],[0,0,0],[2,0,0]],True),([[2,0,0],[3,0,0],[4,0,0]],False),
            ([[1,1,1]]*3,True),([[1,1,2]]*3,False),([[-2,2,0],[2,2,0],[0,2,0]],False)]:
            self.assertEqual(q.triangle_box_sat(triangle,self.BOX),truth)
    def test_exact_affine_unit_is_not_rounded_midway(self):
        matrix=[[0,-1,0,2],[1,0,0,3],[0,0,1,4],[0,0,0,1]]
        result=q.transformed_vertices([[1,2,3]],matrix,.001)
        self.assertEqual(result,[(F(0),F(.001)*4,F(.001)*7)])
    def test_known_rigid_and_affine_stretch(self):
        old=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
        rigid=[[3.,4.,5.],[3.,5.,5.],[2.,4.,5.]]
        r=q.independent_metric(old,rigid);self.assertEqual(r['state'],'measured');self.assertAlmostEqual(r['area_ratio'],1.)
        for actual,wanted in zip(r['principal_stretches'],[1.,1.]):self.assertAlmostEqual(actual,wanted)
        r=q.independent_metric(old,[[0.,0.,0.],[2.,0.,0.],[0.,.5,0.]])
        self.assertEqual(r['state'],'measured');self.assertAlmostEqual(r['area_ratio'],1.)
        for actual,wanted in zip(r['principal_stretches'],[2.,.5]):self.assertAlmostEqual(actual,wanted)
    def test_independent_unknown_and_collapse_reasons(self):
        old=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
        self.assertEqual(q.independent_metric(old,old,[0])['reason'],'unweighted_vertex_source')
        collinear=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        self.assertEqual(q.independent_metric(collinear,collinear)['reason'],'original_zero_area')
        r=q.independent_metric(old,collinear);self.assertEqual(r['state'],'collapsed');self.assertEqual(r['area_ratio'],0.)


if __name__=='__main__':unittest.main()
