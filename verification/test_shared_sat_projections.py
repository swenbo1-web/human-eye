"""Analytical contracts for shared positive/zero tolerance SAT work."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import _single_convex_collision_and_zero
from human_eye_plugin import geometry_safety as geometry
from verification.test_concave_geometry import box, ring
from verification.test_complex_scene_quality import component_union


class SharedSatTests(unittest.TestCase):
    def pair(self,gap):
        return box((0,0,1+gap),(1,1,1),'a'),box((0,0,0),(1,1,1),'b')

    def test_subtolerance_overlap_keeps_two_distinct_answers(self):
        a,b=self.pair(-2e-10)
        measured,zero=_single_convex_collision_and_zero(a,b,1e-9)
        self.assertFalse(measured[0]);self.assertTrue(zero[0])
        actual=b.vertices[:,2].max()-a.vertices[:,2].min()
        self.assertEqual(zero[1],actual)
        result=geometry.measure_pair_geometry(a,b,need_clearance=True)
        self.assertTrue(result['measurement_valid']);self.assertFalse(result['is_penetrating'])
        self.assertEqual(result['signed_clearance_m'],-actual)

    def test_touch_and_positive_distance_keep_analytic_clearance(self):
        for gap in [0.,.004]:
            a,b=self.pair(gap)
            result=geometry.measure_pair_geometry(a,b,need_clearance=True)
            self.assertTrue(result['measurement_valid']);self.assertFalse(result['is_penetrating'])
            self.assertAlmostEqual(result['signed_clearance_m'],gap,places=14)

    def test_positive_volume_overlap_keeps_depth_and_separate_vectors(self):
        a,b=self.pair(-.01)
        measured,zero=_single_convex_collision_and_zero(a,b,1e-9)
        self.assertTrue(measured[0]);self.assertTrue(zero[0])
        self.assertAlmostEqual(measured[1],.01,places=14)
        self.assertEqual(measured[1],zero[1]);np.testing.assert_array_equal(measured[2],zero[2])
        self.assertFalse(np.shares_memory(measured[2],zero[2]))

    def test_no_clearance_and_zero_tolerance_keep_existing_path(self):
        a,b=self.pair(.004)
        with patch.object(geometry,'_single_convex_collision_and_zero',side_effect=AssertionError('unneeded double tolerance')):
            no_clearance=geometry.measure_pair_geometry(a,b,need_clearance=False)
            zero=geometry.measure_pair_geometry(a,b,need_clearance=True,collision_tolerance_m=0.)
        self.assertIsNone(no_clearance['signed_clearance_m'])
        self.assertAlmostEqual(zero['signed_clearance_m'],.004,places=14)

    def test_components_and_concavity_use_existing_general_evaluator(self):
        a=box((0,0,1.1),(1,1,1),'a')
        union=MeshEntity3D.from_dict(component_union('union',[((0,0,0),(1,1,1)),((2,0,0),(1,1,1))]))
        self.assertIsNone(_single_convex_collision_and_zero(a,union,1e-9))
        result=geometry.measure_pair_geometry(a,union,need_clearance=True)
        self.assertTrue(result['measurement_valid']);self.assertAlmostEqual(result['signed_clearance_m'],.1,places=14)
        self.assertIsNone(_single_convex_collision_and_zero(a,ring(),1e-9))

    def test_open_solid_remains_unknown_and_resource_limit_stops_before_sat(self):
        a,b=self.pair(.004);value=b.to_dict();value['faces']=value['faces'][:-1]
        opened=MeshEntity3D.from_dict(value)
        self.assertIsNone(_single_convex_collision_and_zero(a,opened,1e-9))
        self.assertFalse(geometry.measure_pair_geometry(a,opened,need_clearance=True)['measurement_valid'])
        with (patch.object(geometry,'work_budget_status',return_value={'within_budget':False}),
              patch.object(geometry,'_single_convex_collision_and_zero',side_effect=AssertionError('outside budget'))):
            self.assertEqual(geometry.measure_pair_geometry(a,b,need_clearance=True)['reason'],'geometry_resource_limit')

    def test_current_inputs_are_not_changed_and_reversing_pair_preserves_distance(self):
        a,b=self.pair(-.01);before=copy.deepcopy([a.to_dict(),b.to_dict()])
        first=geometry.measure_pair_geometry(a,b,need_clearance=True)
        second=geometry.measure_pair_geometry(b,a,need_clearance=True)
        self.assertEqual(first['signed_clearance_m'],second['signed_clearance_m'])
        self.assertEqual([a.to_dict(),b.to_dict()],before)


if __name__=='__main__':unittest.main()
