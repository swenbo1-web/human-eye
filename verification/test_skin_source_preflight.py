"""Independent preflight oracle checks; these are not native value trials."""
import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
from verification import run_skin_source_preflight as p


def surface_oracle(name):
    spec=p.surface_spec(name)
    return dict(**{key:copy.deepcopy(spec[key]) for key in ('vertices','triangles','weights','heads','rotations_deg','parents','rolls_deg','quaternions')},
        world=dict(rig_deg=[0.,0.,0.],mesh_deg=[0.,0.,0.],rig_location=[0.,0.,0.],mesh_location=[0.,0.,0.]),
        unit=1.,surface=spec,unweighted=sum(not row for row in spec['weights']))


class SkinSourcePreflightTests(unittest.TestCase):
    def test_original_49_and_all_four_combinations_preserved(self):
        self.assertEqual(len(p.LEGACY_POSITIVE),18);self.assertEqual(len(p.NEGATIVE_REASONS),31)
        self.assertEqual(len(set(p.LEGACY_POSITIVE+tuple(p.NEGATIVE_REASONS))),49)
        self.assertEqual(set(p.B1_COMBINATIONS),{'gradient_weights','rest_roll','parent_combo','distinct_rig_mesh_world'})
        self.assertEqual(len(p.B2_CASES),13)
    def test_each_negative_requires_its_exact_registered_reason(self):
        for name,reason in p.NEGATIVE_REASONS.items():
            exact='rig_pose_skin_reply:rig_pose_'+reason
            with self.subTest(case=name):
                p.verify_negative(name,None,exact)
                for error in (None,'unsupported_anything',exact+'_other','rig_pose_skin_reply:rig_pose_unsupported_skin_roles'):
                    with self.assertRaises(AssertionError):p.verify_negative(name,None,error)
                with self.assertRaises(AssertionError):p.verify_negative(name,dict(status='observed'),exact)
    def test_registration_rejects_modified_expectations(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'registration.json';path.write_text(json.dumps(p.catalog()))
            self.assertEqual(len(p.verify_registration(path)),64)
            changed=p.catalog();changed['legacy_negative']['DQ']='unsupported_other';path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'registration_changed'):p.verify_registration(path)
    def test_independent_LBS_applies_rest_roll_before_local_rotation(self):
        o=surface_oracle('surface_rigid_rotation');o.update(heads=[[0.,0.,0.]],rolls_deg=[90.],rotations_deg=[[90.,0.,0.]],
            vertices=[[1.,0.,0.]],weights=[[[0,1.]]])
        point,_=p.independent_LBS(o);np.testing.assert_allclose(point,[[0.,-1.,0.]],atol=1e-14)
        o['rolls_deg']=[0.];plain,_=p.independent_LBS(o);np.testing.assert_allclose(plain,[[1.,0.,0.]],atol=1e-14)
    def test_quaternion_half_turn_produces_authored_exact_collapse(self):
        o=surface_oracle('surface_collapsed');points,_=p.independent_LBS(o)
        self.assertEqual(points.tolist(),[[0.,0.,0.]]*3)
        truth=p.independent_surface(o['vertices'],points);self.assertEqual(truth,dict(stretches=[0.,0.],area_ratio=0.))
    def test_QR_SVD_matches_known_affine_stretches_and_area(self):
        for name,stretches,area in (
            ('surface_rigid_translation',[1.,1.],1.),('surface_stretch',[1.5,1.],1.5),
            ('surface_compress',[.8,.5],.4),('surface_shear',[(17**.5+1)/4,(17**.5-1)/4],1.)):
            o=surface_oracle(name);points,_=p.independent_LBS(o);truth=p.independent_surface(o['vertices'],points)
            with self.subTest(case=name):
                np.testing.assert_allclose(truth['stretches'],stretches,atol=1e-14);self.assertAlmostEqual(truth['area_ratio'],area,places=14)
    def test_rigid_rotation_translation_and_benign_hinge_are_isometries(self):
        for name in ('surface_rigid_rotation','surface_rigid_translation','surface_fold','surface_tiny_representable'):
            o=surface_oracle(name);points,_=p.independent_LBS(o)
            for tri in o['triangles']:
                truth=p.independent_surface([o['vertices'][i] for i in tri],[points[i] for i in tri])
                with self.subTest(case=name,triangle=tri):
                    np.testing.assert_allclose(truth['stretches'],[1.,1.],atol=1e-14);self.assertAlmostEqual(truth['area_ratio'],1.,places=14)
    def test_degenerate_unknown_causes_are_authored_independently(self):
        expected={'surface_original_zero':'original_zero_area','surface_near_original':'reference_ill_conditioned',
            'surface_tiny_offset':'reference_below_coordinate_resolution','surface_near_current':'current_near_degenerate',
            'surface_unweighted':'unweighted_vertex_source'}
        for name,reason in expected.items():self.assertEqual(p.surface_spec(name)['expected_diagnostics'],[dict(triangle=0,state='unknown',reason=reason)])
        self.assertIsNone(p.independent_surface(p.surface_spec('surface_original_zero')['vertices'],p.surface_spec('surface_original_zero')['vertices'])['stretches'])
    def test_native_report_checker_rejects_wrong_values_counts_and_region(self):
        oracle=surface_oracle('surface_stretch');packet=dict(source_sha256='a'*64)
        row=dict(triangle=0,vertices=[0,1,2],region_kind='original_triangle',state='measured',reason=None,
            principal_stretches=[1.5,1.],engineering_strains=[.5,0.],area_ratio=1.5,
            centroid_world_m=[.5,1/3,0.],bounds_world_m=[[0.,0.,0.],[1.5,1.,0.]])
        report=dict(assessment='geometric_facts_not_damage',damage_classification='not_inferred',execution_authority=False,
            source_sha256='a'*64,source_summary=dict(vertices_total=3,unweighted_vertices_total=0),triangles_total=1,
            triangles_omitted=0,triangles=[row],triangles_measured=1,triangles_collapsed=0,triangles_unknown=0,unknown_reasons={},status='observed')
        truth=p.verify_surface_report(report,packet,oracle);self.assertEqual(truth[0]['triangle'],0)
        np.testing.assert_allclose(truth[0]['stretches'],[1.5,1.],atol=1e-14);self.assertEqual(truth[0]['area_ratio'],1.5)
        for field,bad in (('principal_stretches',[1.,1.]),('engineering_strains',[0.,0.]),('area_ratio',1.),('vertices',[0,2,1]),
            ('state','collapsed'),('centroid_world_m',[0.,0.,0.])):
            changed=copy.deepcopy(report);changed['triangles'][0][field]=bad
            with self.subTest(field=field),self.assertRaises(AssertionError):p.verify_surface_report(changed,packet,oracle)
        changed=copy.deepcopy(report);changed['source_summary']['vertices_total']=16
        with self.assertRaises(AssertionError):p.verify_surface_report(changed,packet,oracle)


if __name__=='__main__':unittest.main()
