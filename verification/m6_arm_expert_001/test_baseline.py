"""Analytic checks of the independent baseline; no product or training import."""
from copy import deepcopy
import math
import unittest

import numpy as np

from verification.m6_arm_expert_001.geometry_baseline import predict


def tube():
    rest = [[x,y,z] for z in (0.,1.,2.)
            for x,y in ((1.,0.),(0.,1.),(-1.,0.),(0.,-1.))]
    return dict(schema='arm-twist-patch-v1', rest_vertices=rest,
                current_vertices=deepcopy(rest), sections=[list(range(i,i+4)) for i in (0,4,8)])


class IndependentGeometryBaselineTests(unittest.TestCase):
    def test_rigid_three_dimensional_transform_and_reversed_sections(self):
        patch = tube()
        # (x,y,z) -> (z+7,x-5,y+11) is an exact proper rigid transform.
        patch['current_vertices'] = [[z+7,x-5,y+11] for x,y,z in patch['rest_vertices']]
        np.testing.assert_array_equal(predict(patch), np.zeros(3))
        patch['sections'] = [list(reversed(section)) for section in patch['sections']]
        np.testing.assert_array_equal(predict(patch), np.zeros(3))

    def test_known_radial_scale_is_area_squared_and_localizes_section(self):
        patch = tube()
        factors = (1.,0.5,0.)
        patch['current_vertices'] = [[x*factors[i//4], y*factors[i//4], z]
                                    for i,(x,y,z) in enumerate(patch['rest_vertices'])]
        np.testing.assert_array_equal(predict(patch), [0.,0.75,1.])

    def test_same_bone_angle_distinguishes_volume_preserving_twist_from_shrink(self):
        normal = tube()
        normal['bone_chain'] = [{'name':'child', 'twist_radians':2.1}]
        for i,(x,y,z) in enumerate(normal['rest_vertices']):
            angle=0.7*z;c=math.cos(angle);s=math.sin(angle)
            normal['current_vertices'][i] = [c*x-s*y,s*x+c*y,z]
        collapsed = deepcopy(normal)
        collapsed['current_vertices'] = [[0.5*x,0.5*y,z] for x,y,z in normal['current_vertices']]
        np.testing.assert_allclose(predict(normal), np.zeros(3), atol=1e-15, rtol=0)
        np.testing.assert_allclose(predict(collapsed), np.full(3,0.75), atol=1e-15, rtol=0)

    def test_reference_zero_area_is_unknown_and_expansion_is_not_shrink(self):
        patch = tube()
        patch['rest_vertices'][:4] = [[float(i),0.,0.] for i in range(4)]
        patch['current_vertices'][4:8] = [[2*x,2*y,z] for x,y,z in patch['rest_vertices'][4:8]]
        actual = predict(patch)
        self.assertTrue(math.isnan(actual[0]))
        np.testing.assert_array_equal(actual[1:], [0.,0.])

    def test_missing_correspondence_and_duplicate_or_boolean_indices_refuse(self):
        patch = tube()
        patch['current_vertices'].pop()
        with self.assertRaisesRegex(ValueError,'vertex_correspondence'):predict(patch)
        for bad in ([0,1,1,3], [False,1,2,3], [0,1,2,12]):
            patch = tube();patch['sections'][0] = bad
            with self.assertRaisesRegex(ValueError,'section_indices'):predict(patch)


if __name__ == '__main__':unittest.main()
