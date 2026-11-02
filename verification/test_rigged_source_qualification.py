"""Independent tiny authored packets; no private assets needed for unit tests."""
import copy,time,unittest
from unittest.mock import patch
import numpy as np
from verification import rigged_source_qualification as q


def identity(name,kind='OBJECT',uid=1):return dict(name=name,id_type=kind,linked=False,session_uid=uid)
def ident4():return np.eye(4).tolist()
def object_row(name,kind,parent=None,uid=1):
    return dict(name=name,type=kind,identity=identity(name,uid=uid),data_identity=None if kind=='EMPTY' else identity(name+'Data',kind,uid+10),
        parent=parent,parent_identity=None if parent is None else identity(parent,uid={'Root':1,'Rig':2}[parent]),parent_type='OBJECT',parent_bone='',
        matrix_basis=ident4(),matrix_local=ident4(),matrix_parent_inverse=ident4(),matrix_world=ident4(),
        object_linked=False,data_linked=False,object_override=False,data_override=False,constraints=[],animation=dict(object=None,data=None),
        location=[0.,0.,0.],scale=[1.,1.,1.],rotation_mode='QUATERNION',rotation_euler=[0.,0.,0.],rotation_quaternion=[1.,0.,0.,0.],rotation_axis_angle=[0.,0.,0.,1.],
        delta_location=[0.,0.,0.],delta_scale=[1.,1.,1.],delta_rotation_euler=[0.,0.,0.],delta_rotation_quaternion=[1.,0.,0.,0.])


def rehash(packet):
    a=packet['audit'];a['before_sha256']=a['after_sha256']=q.digest(packet['inputs']);a['independent_before_sha256']=a['independent_after_sha256']=q.digest(dict(authored_independent_audit=True))
    packet['source_sha256']=q.source_digest(packet);return packet


def fixture(animated=False):
    objects=[object_row('Root','EMPTY'),object_row('Rig','ARMATURE','Root',2),object_row('Mesh','MESH','Rig',3)]
    bone=dict(name='Bone',parent=None,rest_matrix=ident4(),basis_matrix=ident4(),pose_matrix=ident4(),rest_head=[0.,0.,0.],rest_tail=[0.,1.,0.],pose_head=[0.,0.,0.],pose_tail=[0.,1.,0.],length=1.,
        location=[0.,0.,0.],scale=[1.,1.,1.],rotation_mode='QUATERNION',rotation_euler=[0.,0.,0.],rotation_quaternion=[1.,0.,0.,0.],rotation_axis_angle=[0.,0.,0.,1.],
        inherit_rotation=True,inherit_scale='FULL',local_location=True,connected=False,bbone_segments=1,use_deform=True,use_envelope_multiply=False,constraints=[],custom_shape=None)
    settings=dict(use_deform_preserve_volume=False,use_bone_envelopes=False,use_multi_modifier=False,invert_vertex_group=False,vertex_group='',use_vertex_groups=True,show_render=True,show_viewport=True)
    mesh=dict(name='Mesh',data_name='MeshData',vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],triangles=[[0,1,2]],edges=[[0,1],[1,2],[0,2]],weights=[[[0,1.]]]*3,groups=['Bone'],shape_keys=None,
        modifier=[dict(name='Skin',type='ARMATURE',object='Rig',object_identity=objects[1]['identity'].copy(),settings=settings)])
    inputs=dict(closure=objects,rig=dict(name='Rig',data_name='RigData',pose_position='POSE',bones=[bone]),mesh=mesh,actions=[],frame=dict(number=1,subframe=0.),unit_scale_m=1.,
        context=dict(mode='OBJECT',active_object='Mesh',selected_objects=['Mesh']),scene=dict(name='Scene',fps=24,fps_base=1.,objects=[{k:copy.deepcopy(o[k]) for k in ('name','type','identity','data_identity')} for o in objects]))
    if animated:
        aid=identity('Motion','ACTION',4);slot=dict(handle=7,identifier='OBRig',name='Rig',target_id_type='OBJECT',users=[objects[1]['identity'].copy()])
        curve=dict(data_path='pose.bones["Bone"].location',array_index=0,driver=None,modifiers=[],mute=False,is_valid=True,sampled_points=[],extrapolation='CONSTANT',
            keys=[dict(co=[0.,0.],interpolation='LINEAR'),dict(co=[2.,0.],interpolation='LINEAR')])
        inputs['actions']=[dict(name='Motion',identity=aid,linked=False,override=False,is_action_layered=True,is_action_legacy=False,use_cyclic=False,use_frame_range=False,
            slots=[slot],layers=[dict(name='Layer',strips=[dict(type='KEYFRAME',channelbags=[dict(slot_handle=7,fcurves=[curve])])])])]
        objects[1]['animation']['object']=dict(drivers=[],use_tweak_mode=False,use_nla=True,nla_tracks=[],action='Motion',action_id=aid,
            action_slot_handle=7,action_slot={k:slot[k] for k in ('handle','identifier','target_id_type')},action_blend_type='REPLACE',action_influence=1.,action_extrapolation='HOLD')
    return rehash(dict(schema='b3-source-probe-v1',identity=dict(document_epoch='a'*32,scene_sha256='1'*64,profile_sha256='2'*64,probe_sha256='3'*64,binary_sha256='4'*64),
        inputs=inputs,evaluated=dict(rig_matrix_world=ident4(),mesh_matrix_world=ident4(),bones=[{k:copy.deepcopy(bone[k]) for k in ('name','parent','pose_matrix','pose_head','pose_tail')}],
            vertices=copy.deepcopy(mesh['vertices']),triangles=copy.deepcopy(mesh['triangles']),original_links_verified=True),
        audit={},capture_id='b'*32,source_sha256=''))


class QualificationTests(unittest.TestCase):
    def qualify(self,p,**kwargs):return q.qualify(p,deadline_ns=time.perf_counter_ns()+5_000_000_000,**kwargs)
    def rejected(self,p,reason):
        out=self.qualify(rehash(p));self.assertEqual(out['status'],'rejected',out);self.assertEqual(out['reasons'],[reason]);return out

    def test_authored_rigid_geometry_and_linear_currentframe_are_qualified(self):
        for animated in (False,True):
            p=fixture(animated);before=copy.deepcopy(p);out=self.qualify(p)
            self.assertEqual(out['status'],'qualified',out);self.assertEqual(out['numerical_replay']['LBS_maximum_error'],0.)
            self.assertEqual(out['animation_evaluation']['curves'],int(animated));self.assertEqual(p,before)
            self.assertFalse(out['product_support_certified']);self.assertFalse(out['execution_authority']);self.assertFalse(out['raw_values_modified'])

    def test_small_original_scale_noise_is_not_zeroed(self):
        p=fixture();b=p['inputs']['rig']['bones'][0];scale=1.+2**-23;b['scale'][0]=scale;b['basis_matrix'][0][0]=scale;b['pose_matrix'][0][0]=scale
        p['evaluated']['bones'][0]['pose_matrix'][0][0]=scale;p['evaluated']['vertices'][1][0]=scale;rehash(p)
        out=self.qualify(p);self.assertEqual(out['status'],'qualified');self.assertEqual(p['inputs']['rig']['bones'][0]['scale'][0],scale)
        self.assertEqual(out['numerical_replay']['maximum_raw_scale_deviation'],2**-23);self.assertFalse(out['numerical_replay']['raw_values_normalized_or_zeroed'])

    def test_parent_inverse_product_is_independently_checked(self):
        p=fixture();p['inputs']['closure'][0]['matrix_world'][0][3]=1.;self.rejected(p,'b3_matrix_replay_disagreement')

    def test_source_stale_even_if_geometry_unchanged(self):
        p=fixture();old=p['source_sha256'];p['inputs']['frame']['number']=2;rehash(p)
        out=self.qualify(p,expected_source_sha256=old);self.assertEqual(out['reasons'],['b3_stale_source'])

    def test_full_tail_vertex_and_triangle_are_validated(self):
        p=fixture();p['evaluated']['vertices'][2][0]=.01;self.rejected(p,'b3_LBS_replay_disagreement')
        p=fixture();p['inputs']['mesh']['triangles'][0][0]=False;self.rejected(p,'b3_triangles')

    def test_shape_modifier_and_direct_dependencies_have_exact_reasons(self):
        changes=[('b3_shape_keys',lambda p:p['inputs']['mesh'].update(shape_keys=['Basis'])),
            ('b3_DQ',lambda p:p['inputs']['mesh']['modifier'][0]['settings'].update(use_deform_preserve_volume=True)),
            ('b3_constraint',lambda p:p['inputs']['rig']['bones'][0]['constraints'].append({'type':'COPY_ROTATION'})),
            ('b3_linked_source',lambda p:p['inputs']['closure'][0].update(object_linked=True)),
            ('b3_driver',lambda p:p['inputs']['closure'][1]['animation']['object']['drivers'].append({'expression':'0'}))]
        for reason,change in changes:
            p=fixture(True);change(p)
            with self.subTest(reason=reason):self.rejected(p,reason)

    def test_active_curve_is_evaluated_not_only_LBS_pose(self):
        p=fixture(True);p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]['keys'][1]['co'][1]=.1
        out=self.rejected(p,'b3_animation_channel_disagreement');self.assertEqual(out['numerical_replay']['LBS_maximum_error'],0.)

    def test_unknown_interpolation_cannot_succeed(self):
        p=fixture(True);p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]['keys'][0]['interpolation']='BEZIER'
        out=self.qualify(rehash(p));self.assertEqual(out['status'],'unknown');self.assertEqual(out['reasons'],['b3_curve_interpolation'])

    def test_extreme_condition_is_unknown_without_inverse(self):
        p=fixture();p['inputs']['closure'][0]['matrix_basis'][0][0]=1e-8;out=self.qualify(rehash(p))
        self.assertEqual(out['status'],'unknown');self.assertEqual(out['reasons'],['b3_matrix_condition'])

    def test_deadline_entry_and_after_analysis_cannot_return_qualified(self):
        out=q.qualify(fixture(),deadline_ns=time.perf_counter_ns()-1);self.assertEqual(out['reasons'],['b3_original_deadline'])
        original=q.independent_matrices;clock=[0]
        def late(*args):value=original(*args);clock[0]=100;return value
        with patch.object(q,'independent_matrices',late),patch.object(q.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            out=q.qualify(fixture(),deadline_ns=100)
        self.assertEqual(out['status'],'unknown');self.assertEqual(out['reasons'],['b3_original_deadline'])

    def test_author_glb_axis_indices_and_named_weights_are_independent(self):
        from verification.test_deformation_asset_intake import fixture as author_fixture,glb
        doc,binary=author_fixture();doc['animations']=[];p=fixture();positions=[[0.,0.,0.],[1.,0.,0.],[0.,0.,1.]]
        p['inputs']['mesh'].update(vertices=copy.deepcopy(positions),groups=['Root','Tip'],weights=[[[0,.25],[1,.75]]]*3)
        p['evaluated']['vertices']=copy.deepcopy(positions)
        witness=q.gltf_witness(p,glb(doc,binary),fps=24,deadline_ns=time.perf_counter_ns()+5_000_000_000)
        self.assertEqual(witness['maximum_original_position_error'],0.);self.assertEqual(witness['maximum_named_weight_error'],0.)
        self.assertEqual(witness['maximum_evaluated_position_error'],0.);self.assertTrue(witness['triangles_same_order'])
        self.assertFalse(witness['product_support_certified'])

    def test_author_witness_rejects_wrong_native_weights_or_index_order(self):
        from verification.test_deformation_asset_intake import fixture as author_fixture,glb
        doc,binary=author_fixture();doc['animations']=[];p=fixture();positions=[[0.,0.,0.],[1.,0.,0.],[0.,0.,1.]]
        p['inputs']['mesh'].update(vertices=positions,groups=['Root','Tip'],weights=[[[0,.25],[1,.75]]]*3);p['evaluated']['vertices']=copy.deepcopy(positions)
        for mode,reason in (('weights','b3_gltf_weight_correspondence'),('triangles','b3_gltf_triangle_correspondence')):
            bad=copy.deepcopy(p)
            if mode=='weights':bad['inputs']['mesh']['weights'][2]=[[0,.5],[1,.5]]
            else:bad['inputs']['mesh']['triangles'][0].reverse()
            with self.subTest(mode=mode),self.assertRaisesRegex(q.Refusal,reason):q.gltf_witness(bad,glb(doc,binary),fps=24,deadline_ns=time.perf_counter_ns()+5_000_000_000)

    def test_existing_coordinate_and_world_bounds_are_not_lost(self):
        p=fixture();p['inputs']['mesh']['vertices'][2][0]=10.001;p['evaluated']['vertices'][2][0]=10.001;self.rejected(p,'b3_coordinate_bound')
        p=fixture();p['inputs']['closure'][0]['matrix_world'][0][3]=100.001;self.rejected(p,'b3_world_translation_bound')


if __name__=='__main__':unittest.main()
