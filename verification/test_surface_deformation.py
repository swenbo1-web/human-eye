"""Independent QR/SVD geometry oracles and full-source, read-only boundaries.

Packets and callbacks below are mathematical doubles, not Blender capture or
human approval evidence. Expected metrics come from NumPy or closed forms.
"""
import copy,math,time,unittest
from unittest.mock import patch
import numpy as np
from human_eye_plugin import surface_deformation as d
from verification import test_skin_source as skin_fixture


UNIT=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]


def qr_svd_oracle(original,current):
    """Independent 3x2 deformation gradient via QR and an SVD, not Gram roots."""
    old=np.asarray(original,dtype=float);new=np.asarray(current,dtype=float)
    old_edges=(old[1:]-old[0]).T;new_edges=(new[1:]-new[0]).T
    tangent,upper=np.linalg.qr(old_edges,mode='reduced')
    gradient=np.linalg.solve(upper.T,new_edges.T).T
    left,stretches,right=np.linalg.svd(gradient,full_matrices=False)
    area=np.linalg.norm(np.cross(new_edges[:,0],new_edges[:,1]))/np.linalg.norm(np.cross(old_edges[:,0],old_edges[:,1]))
    return stretches,float(area),tangent,gradient,left,right


def matrix(axis,degrees,translation=(0.,0.,0.)):
    angle=math.radians(degrees);c=math.cos(angle);s=math.sin(angle);out=np.eye(4)
    i,j={'X':(1,2),'Y':(2,0),'Z':(0,1)}[axis]
    out[i,i]=out[j,j]=c;out[i,j]=-s;out[j,i]=s;out[:3,3]=translation
    return out


def replay_numpy(v):
    """Assemble expected evaluated coordinates independently from source replay."""
    mesh=v['mesh'];rig=v['rig']['payload'];into=np.linalg.inv(np.array(rig['object_matrix_world']))@np.array(mesh['object_matrix_world'])
    back=np.linalg.inv(into);deforms=[np.array(b['pose_matrix'])@np.linalg.inv(np.array(b['rest_matrix'])) for b in rig['bones']]
    evaluated=[]
    for point,weights in zip(mesh['vertices'],mesh['weights']):
        active=[(g,w) for g,w in weights if w>0]
        if not active:evaluated.append(point[:]);continue
        q=into@np.array([*point,1.]);total=sum(w for _,w in active)
        transformed=sum((w/total)*(deforms[g]@q) for g,w in active)
        evaluated.append((back@transformed)[:3].tolist())
    mesh['evaluated_vertices']=evaluated;return skin_fixture.rehash(v)


def one_triangle(*,original=None,weights=None,halfturn=False):
    v=skin_fixture.packet(neutral=True);mesh=v['mesh']
    mesh.update(vertices=copy.deepcopy(UNIT if original is None else original),triangles=[[0,1,2]],
        evaluated_triangles=[[0,1,2]],weights=copy.deepcopy([[[0,.5],[1,.5]]]*3 if weights is None else weights))
    if halfturn:
        bone=v['rig']['payload']['bones'][1];basis=np.diag([-1.,1.,-1.,1.]);pose=np.array(bone['rest_matrix'])@basis
        bone.update(basis_matrix=basis.tolist(),pose_matrix=pose.tolist(),rotation_mode='QUATERNION',rotation_quaternion=[0.,0.,1.,0.],
            pose_head=(pose@np.array([0.,0.,0.,1.]))[:3].tolist(),pose_tail=(pose@np.array([0.,1.,0.,1.]))[:3].tolist())
        v['bone_channels'][1].update(basis=basis.tolist(),mode='QUATERNION',quaternion=[0.,0.,1.,0.])
    return replay_numpy(v)


class TriangleDeformationTests(unittest.TestCase):
    def facts(self,original,current,**kwargs):
        return d.triangle_facts(copy.deepcopy(original),copy.deepcopy(current),deadline_ns=time.perf_counter_ns()+5_000_000_000,**kwargs)

    def assert_metrics(self,original,current,expected=None):
        report=self.facts(original,current);self.assertEqual(report['state'],'measured',report)
        stretches,area,*_=qr_svd_oracle(original,current)
        if expected is not None:np.testing.assert_allclose(stretches,expected,atol=2e-12,rtol=2e-12)
        np.testing.assert_allclose(report['principal_stretches'],stretches,atol=3e-12,rtol=3e-12)
        np.testing.assert_allclose(report['engineering_strains'],stretches-1,atol=3e-12,rtol=3e-12)
        self.assertAlmostEqual(report['area_ratio'],area,places=11)
        self.assertAlmostEqual(math.prod(report['principal_stretches']),area,places=11)
        return report

    def test_isotropic_and_anisotropic_stretch_compression_closed_forms(self):
        for x,y in ((2.,2.),(2.,.5),(.5,.25),(1.2,.8),(1.,1.)):
            with self.subTest(x=x,y=y):
                current=[[0.,0.,0.],[x,0.,0.],[0.,y,0.]]
                report=self.assert_metrics(UNIT,current,sorted([x,y],reverse=True))
                self.assertAlmostEqual(report['area_ratio'],x*y,places=12)

    def test_shear_has_two_principal_stretches_and_unit_area(self):
        shear=.75;current=[[0.,0.,0.],[1.,0.,0.],[shear,1.,0.]]
        root=math.sqrt(shear*shear+4);expected=[(root+shear)/2,(root-shear)/2]
        report=self.assert_metrics(UNIT,current,expected)
        self.assertAlmostEqual(report['area_ratio'],1.,places=12);self.assertTrue(report['change_detectable'])

    def test_principal_directions_match_independent_svd_up_to_sign(self):
        original=[[.2,-.3,.4],[1.2,.2,.6],[.3,.8,1.]]
        current=(np.array(original)@np.array([[1.6,.25,.1],[.2,.7,.05],[.1,0.,1.2]]).T).tolist()
        report=self.assert_metrics(original,current)
        _s,_a,tangent,_gradient,left,right=qr_svd_oracle(original,current)
        self.assertIsNotNone(report['principal_directions'])
        for index,axes in enumerate(report['principal_directions']):
            old_axis=np.array(axes['original_local_axis']);new_axis=np.array(axes['current_local_axis'])
            self.assertAlmostEqual(abs(float(old_axis@(tangent@right[index]))),1.,places=10)
            self.assertAlmostEqual(abs(float(new_axis@left[:,index])),1.,places=10)

    def test_rigid_rotation_translation_and_triangle_vertex_permutations(self):
        old=np.array([[.1,.2,.3],[1.1,.3,.5],[.3,1.2,.4]])
        rigid=matrix('Z',73,(3.,-2.,1.))@matrix('X',-31)
        new=(rigid@np.column_stack([old,np.ones(3)]).T).T[:,:3]
        for order in ((0,1,2),(2,0,1),(0,2,1)):
            report=self.assert_metrics(old[list(order)].tolist(),new[list(order)].tolist(),[1.,1.])
            self.assertFalse(report['change_detectable']);self.assertIsNone(report['principal_directions'])

    def test_folded_two_triangle_isometry_does_not_infer_surface_stretch(self):
        before=[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]]
        # Fold around the shared diagonal, an isometry of each triangular face.
        axis=np.array([1.,1.,0.])/math.sqrt(2);p=np.array(before[3]);angle=math.radians(112)
        folded=p*math.cos(angle)+np.cross(axis,p)*math.sin(angle)+axis*(axis@p)*(1-math.cos(angle))
        after=copy.deepcopy(before);after[3]=folded.tolist()
        for tri in ((0,1,2),(0,2,3)):
            report=self.assert_metrics([before[i] for i in tri],[after[i] for i in tri],[1.,1.])
            self.assertFalse(report['change_detectable'])

    def test_seeded_oblique_affine_cases_use_independent_qr_svd(self):
        random=np.random.default_rng(74321)
        for index in range(32):
            with self.subTest(index=index):
                old=np.array([[.2,.1,-.3],[1.2,.2,-.1],[.4,1.1,.3]])
                old=old@matrix('Y',float(random.uniform(-140,140)))[:3,:3].T
                transform=np.eye(3)+random.normal(0,.15,(3,3))
                new=old@transform.T+random.uniform(-1.,1.,3)
                self.assert_metrics(old.tolist(),new.tolist())

    def test_original_zero_current_zero_and_both_zero_are_distinct(self):
        line=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        oldzero=self.facts(line,UNIT);self.assertEqual(oldzero['reason'],'original_zero_area')
        self.assertEqual(oldzero['current_geometry'],'nonzero_area');self.assertIsNone(oldzero['area_ratio'])
        newzero=self.facts(UNIT,line);self.assertEqual(newzero['state'],'collapsed')
        self.assertEqual(newzero['reason'],'current_zero_area');self.assertEqual(newzero['area_ratio'],0.)
        self.assertEqual(newzero['principal_stretches'][1],0.);self.assertTrue(newzero['change_detectable'])
        both=self.facts(line,line);self.assertEqual(both['reason'],'original_zero_area');self.assertEqual(both['current_geometry'],'zero_area')

    def test_exact_binary_rational_collapse_is_zero_despite_float_cancellation(self):
        tiny=2.**-52;current=[[tiny,3*tiny,7*tiny],[.5,1.5,3.5],[1.,3.,7.]]
        report=self.facts(UNIT,current)
        self.assertEqual(report['state'],'collapsed');self.assertEqual(report['current_geometry'],'zero_area')
        self.assertEqual(report['principal_stretches'][1],0.);self.assertEqual(report['area_ratio'],0.)

    def test_near_collapse_is_unknown_not_exact_collapse_or_normal(self):
        report=self.facts(UNIT,[[0.,0.,0.],[1.,0.,0.],[0.,1e-5,0.]])
        self.assertEqual(report['state'],'unknown');self.assertEqual(report['reason'],'current_near_degenerate')
        self.assertEqual(report['current_geometry'],'nonzero_area');self.assertIsNone(report['principal_stretches'])

    def test_unweighted_source_reports_unknown_not_zero_strain(self):
        report=self.facts(UNIT,UNIT,unweighted=[12])
        self.assertEqual(report['reason'],'unweighted_vertex_source');self.assertEqual(report['unweighted_vertices'],[12])
        self.assertIsNone(report['area_ratio']);self.assertIsNone(report['change_detectable'])

    def test_original_ill_conditioned_and_coordinate_resolution_are_separate(self):
        skinny=[[0.,0.,0.],[1.,0.,0.],[1.,2.**-24,0.]]
        report=self.facts(skinny,skinny);self.assertEqual(report['reason'],'reference_ill_conditioned')
        unresolved=[[1.,1.,1.],[1.+1e-9,1.,1.],[1.,1.+1e-9,1.]]
        report=self.facts(unresolved,unresolved);self.assertEqual(report['reason'],'reference_below_coordinate_resolution')

    def test_tiny_origin_triangle_can_be_reliable_but_subnormal_cannot(self):
        for scale in (1e-12,1e-30,1e-35):
            with self.subTest(scale=scale):
                points=(np.array(UNIT)*scale).tolist();self.assert_metrics(points,points,[1.,1.])
        points=(np.array(UNIT)*1e-43).tolist();report=self.facts(points,points)
        self.assertEqual(report['state'],'unknown');self.assertEqual(report['reason'],'reference_below_coordinate_resolution')

    def test_detectability_does_not_claim_changes_below_precision_margin(self):
        tiny=self.facts(UNIT,[[0.,0.,0.],[1.+1e-8,0.,0.],[0.,1.,0.]])
        clear=self.facts(UNIT,[[0.,0.,0.],[1.01,0.,0.],[0.,1.,0.]])
        self.assertFalse(tiny['change_detectable']);self.assertTrue(clear['change_detectable'])

    def test_conditioning_budget_and_near_collapse_thresholds_fail_closed(self):
        # Both first triangles are mathematically unchanged. Only the thicker
        # one supports the declared precision budget for its narrow direction.
        reliable=[[0.,0.,0.],[1.,0.,0.],[0.,.004,0.]]
        unresolved=[[0.,0.,0.],[1.,0.,0.],[0.,.003,0.]]
        self.assert_metrics(reliable,reliable,[1.,1.])
        report=self.facts(unresolved,unresolved)
        self.assertEqual(report['state'],'unknown');self.assertEqual(report['reason'],'metric_resolution_insufficient')
        for height,state in ((.0001,'unknown'),(.001,'measured')):
            with self.subTest(height=height):
                current=[[0.,0.,0.],[1.,0.,0.],[0.,height,0.]]
                report=self.facts(UNIT,current);self.assertEqual(report['state'],state)
                if state=='unknown':self.assertEqual(report['reason'],'current_near_degenerate')

    def test_bad_triangle_inputs_are_rejected_for_shape(self):
        for points in ([[0,0,0]],[[0,0,0],[1,0,0],[0,True,0]],[[0,0,0],[1,0,0],[0,float('nan'),0]]):
            with self.assertRaisesRegex(ValueError,'deformation_triangle_shape'):self.facts(points,UNIT)

    def test_expiry_after_exact_work_blocks_every_early_and_success_return(self):
        line=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]
        cases=[(line,UNIT,()),(UNIT,UNIT,(0,)),(UNIT,UNIT,()),(UNIT,line,()),
            ([[0.,0.,0.],[1.,0.,0.],[1.,2.**-24,0.]],UNIT,())]
        original=d.exact_zero
        for old,new,missing in cases:
            with self.subTest(old=old,missing=missing):
                clock=[0];calls=[0]
                def exact(*args):
                    value=original(*args);calls[0]+=1
                    if calls[0]==2:clock[0]=100
                    return value
                with patch.object(d,'exact_zero',exact),patch('human_eye_plugin.rig_pose.time.perf_counter_ns',side_effect=lambda:clock[0]):
                    with self.assertRaisesRegex(ValueError,'original_deadline'):
                        d.triangle_facts(old,new,unweighted=missing,deadline_ns=100)


class FullSourceDeformationTests(unittest.TestCase):
    def analyze(self,v):return d.analyze(v,deadline_ns=time.perf_counter_ns()+5_000_000_000)

    def test_valid_single_bone_large_displacement_is_rigid_not_damage(self):
        v=skin_fixture.packet(neutral=False,bones=1,influences=1);report=self.analyze(v)
        self.assertGreater(max(np.linalg.norm(np.array(a)-b) for a,b in zip(v['mesh']['vertices'],v['mesh']['evaluated_vertices'])),.3)
        self.assertEqual(report['triangles_unknown'],0);self.assertEqual(report['triangles_measured'],len(v['mesh']['triangles']))
        for row in report['triangles']:
            np.testing.assert_allclose(row['principal_stretches'],[1.,1.],atol=2e-12);self.assertFalse(row['change_detectable'])
        self.assertEqual(report['damage_classification'],'not_inferred');self.assertEqual(report['geometry_setters'],0)
        self.assertFalse(report['execution_authority']);self.assertFalse(report['original_file_saved'])

    def test_unit_scale_and_distinct_rigid_object_frames_preserve_metrics(self):
        v=skin_fixture.packet(neutral=True);mesh=v['mesh'];mesh_world=matrix('Z',39,(3.,-2.,1.));rig_world=matrix('X',-27,(-1.,2.,.5))
        mesh.update(object_matrix_world=mesh_world.tolist(),basis_matrix=mesh_world.tolist())
        v['rig']['payload']['object_matrix_world']=rig_world.tolist();v['rig_object_basis']=rig_world.tolist();replay_numpy(v)
        first=self.analyze(v);v['rig']['payload']['unit_scale_m']=.001;skin_fixture.rehash(v);second=self.analyze(v)
        old={row['triangle']:row for row in first['triangles']};new={row['triangle']:row for row in second['triangles']}
        self.assertEqual(set(old),set(new))
        for index,a in old.items():
            b=new[index];tri=mesh['triangles'][index];points=(mesh_world@np.column_stack([np.array(mesh['evaluated_vertices'])[tri],np.ones(3)]).T).T[:,:3]
            np.testing.assert_allclose(b['centroid_world_m'],points.mean(axis=0)*.001,atol=1e-15)
            np.testing.assert_allclose(b['bounds_world_m'],np.array([points.min(axis=0),points.max(axis=0)])*.001,atol=1e-15)
            np.testing.assert_allclose(a['principal_stretches'],b['principal_stretches'],atol=1e-14)

    def test_valid_source_exact_collapse_and_original_zero_have_separate_counts(self):
        collapsed=self.analyze(one_triangle(halfturn=True))
        self.assertEqual((collapsed['triangles_collapsed'],collapsed['triangles_unknown'],collapsed['original_zero_area_total']),(1,0,0))
        self.assertEqual(collapsed['triangles'][0]['area_ratio'],0.)
        originalzero=self.analyze(one_triangle(original=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]))
        self.assertEqual((originalzero['triangles_collapsed'],originalzero['triangles_unknown'],originalzero['original_zero_area_total']),(0,1,1))
        self.assertEqual(originalzero['unknown_reasons'],{'original_zero_area':1})

    def test_valid_varying_weights_can_generate_real_stretch_and_compression(self):
        original=[[1.,0.,0.],[2.,0.,0.],[1.,1.,0.]]
        for weights,expected in (([[[1,1.]],[[0,1.]],[[1,1.]]],[3.,1.]),
            ([[[0,1.]],[[0,.875],[1,.125]],[[0,1.]]],[1.,.5])):
            with self.subTest(expected=expected):
                v=one_triangle(original=original,weights=weights,halfturn=True);report=self.analyze(v);row=report['triangles'][0]
                oracle,area,*_=qr_svd_oracle(original,v['mesh']['evaluated_vertices'])
                np.testing.assert_allclose(oracle,expected,atol=1e-13);np.testing.assert_allclose(row['principal_stretches'],oracle,atol=1e-13)
                self.assertAlmostEqual(row['area_ratio'],area);self.assertEqual(report['damage_classification'],'not_inferred')

    def test_replay_abs_tolerance_is_conformance_not_coordinate_error_or_causal_proof(self):
        # A deliberately modified mathematical packet is not a native capture.
        # It demonstrates why passing an absolute LBS replay window alone is
        # not source authenticity or exact causal attribution. Metrics still
        # correctly describe the supplied evaluated coordinates themselves.
        original=(np.array(UNIT)*1e-12).tolist();v=one_triangle(original=original)
        v['mesh']['evaluated_vertices'][1][0]*=1.001;skin_fixture.rehash(v)
        proof=d.source.validate(v,deadline_ns=time.perf_counter_ns()+5_000_000_000)
        self.assertGreater(proof['max_replay_error'],0.)
        self.assertLess(proof['max_replay_error'],2e-15)
        report=self.analyze(v);row=report['triangles'][0]
        self.assertEqual(row['state'],'measured');self.assertTrue(row['change_detectable'])
        np.testing.assert_allclose(row['principal_stretches'],[1.001,1.],atol=1e-12)
        self.assertEqual(report['damage_classification'],'not_inferred')

    def test_analysis_does_not_mutate_verified_input_packet(self):
        v=skin_fixture.packet(neutral=False);before=copy.deepcopy(v)
        self.analyze(v);self.assertEqual(v,before)

    def test_full_128_vertex_256_face_source_is_analyzed_before_16_row_summary(self):
        v=skin_fixture.packet(neutral=True,torus=True);visited=[];original=d.triangle_facts
        def triangle(*args,**kwargs):visited.append(args[0]);return original(*args,**kwargs)
        with patch.object(d,'triangle_facts',triangle),patch.object(d.source,'analyze',side_effect=AssertionError('16-vertex summary forbidden')):
            report=self.analyze(v)
        self.assertEqual(len(visited),256);self.assertEqual(report['source_summary']['vertices_total'],128)
        self.assertEqual((report['triangles_total'],report['triangles_measured'],report['triangles_unknown'],report['triangles_omitted']),(256,256,0,240))
        self.assertEqual(len(report['triangles']),16)

    def test_unweighted_tail_vertex_is_located_even_beyond_summary(self):
        v=skin_fixture.packet(neutral=True,torus=True);v['mesh']['weights'][127]=[];skin_fixture.rehash(v)
        affected={i for i,tri in enumerate(v['mesh']['triangles']) if 127 in tri};self.assertTrue(affected)
        report=self.analyze(v);self.assertEqual(report['triangles_unknown'],len(affected))
        self.assertEqual(report['source_summary']['unweighted_vertices_total'],1)
        self.assertEqual(report['unknown_reasons'],{'unweighted_vertex_source':len(affected)})
        rows={row['triangle']:row for row in report['triangles']}
        self.assertTrue(affected.issubset(rows));self.assertTrue(any(i>16 for i in affected))
        for index in affected:self.assertEqual(rows[index]['unweighted_vertices'],[127]);self.assertIsNone(rows[index]['area_ratio'])

    def test_bad_tail_vertex_or_face_is_refused_before_any_metric(self):
        for mode,reason in (('vertex','same_index_LBS'),('face','unsupported_skin_triangle_limit_or_indices')):
            with self.subTest(mode=mode):
                v=skin_fixture.packet(neutral=True,torus=True)
                if mode=='vertex':v['mesh']['evaluated_vertices'][127][0]+=.1
                else:v['mesh']['triangles'][255][0]=True;v['mesh']['evaluated_triangles'][255][0]=True
                skin_fixture.rehash(v)
                with patch.object(d,'triangle_facts') as metric:
                    with self.assertRaisesRegex(ValueError,reason):self.analyze(v)
                metric.assert_not_called()

    def test_original_deadline_blocks_entry_and_final_report_publication(self):
        v=one_triangle()
        with self.assertRaisesRegex(ValueError,'original_deadline'):d.analyze(v,deadline_ns=time.perf_counter_ns()-1)
        original=d.triangle_facts;clock=[0]
        def late(*args,**kwargs):
            facts=original(*args,**kwargs);clock[0]=100;return facts
        with patch.object(d,'triangle_facts',late),patch('human_eye_plugin.rig_pose.time.perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):d.analyze(v,deadline_ns=100)


if __name__=='__main__':unittest.main()
