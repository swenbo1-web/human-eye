"""Public authored sources exercise production binding and independent replay."""
import copy,dataclasses,time,unittest
from unittest.mock import patch
import numpy as np
from human_eye_plugin import small_skin_source as s
from verification.test_rigged_source_qualification import fixture as authored


def rehash(packet):
    audit=packet['audit'];audit['before_sha256']=audit['after_sha256']=s.r.digest(packet['inputs'])
    packet['source_sha256']=s.source_digest(packet);return packet


def packet(animated=False):
    """Complete Blender-5.2-shaped leaf fields over an authored unit triangle."""
    p=authored(animated);p['schema']=s.SCHEMA
    p['identity']=dict(zip(s.PIN_FIELDS,('1'*64,'2'*64,'3'*64,'4'*64,'5'*64,'6'*64,'7'*64)),document_epoch='a'*32,process_id=1234)
    settings=p['inputs']['mesh']['modifier'][0]['settings']
    for key in s.MOD_SETTINGS-settings.keys():settings[key]=False
    settings.update(name='Skin',type='ARMATURE',execution_time=0.,persistent_uid=77,is_active=True)
    if animated:
        action=p['inputs']['actions'][0];action.update(frame_start=0.,frame_end=2.,frame_range=[0.,2.],curve_frame_range=[0.,2.])
        data=p['inputs']['closure'][1]['animation']['object'];data.update(last_slot_identifier='OBRig',action_tweak_storage=None,
            action_tweak_storage_id=None,action_slot_handle_tweak_storage=0,use_pin=False)
        curve=action['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0];curve['auto_smoothing']='NONE'
        for key in curve['keys']:
            key.update(handle_left=key['co'][:],handle_right=key['co'][:],easing='AUTO',type='KEYFRAME',amplitude=0.,back=0.,period=0.,handle_left_type='VECTOR',handle_right_type='VECTOR')
    return rehash(p)


def binding(p,**changes):
    i=p['inputs'];objects={o['name']:o for o in i['closure']}
    role=lambda n:{key:copy.deepcopy(objects[n][key]) for key in ('identity','data_identity')}
    values={key:p['identity'][key] for key in s.PIN_FIELDS}
    values.update(process_id=p['identity']['process_id'],mesh_name=i['mesh']['name'],rig_name=i['rig']['name'],
        expected_frame=(i['frame']['number'],i['frame']['subframe']),unit_scale_m=i['unit_scale_m'],document_epoch=p['identity']['document_epoch'],
        mesh_identity=role(i['mesh']['name']),rig_identity=role(i['rig']['name']))
    values.update(changes);return s.ExternalBinding(**values)


class SmallSkinSourceTests(unittest.TestCase):
    def validate(self,p,b=None,**kwargs):return s.validate(p,deadline_ns=time.perf_counter_ns()+5_000_000_000,expected_bindings=binding(p) if b is None else b,**kwargs)
    def refused(self,p,code,status='unsupported',b=None):
        with self.assertRaises(s.SmallSourceError) as caught:self.validate(rehash(p),b)
        self.assertEqual(caught.exception.code,'small_skin_'+code);self.assertEqual(caught.exception.status,status)

    def test_authored_static_and_linear_sources_preserve_all_input_values(self):
        for animated in (False,True):
            p=packet(animated);prior=copy.deepcopy(p);out=self.validate(p)
            self.assertEqual(out['original'],p['inputs']['mesh']['vertices']);self.assertEqual(out['current'],out['original'])
            self.assertEqual(out['max_replay_error'],0.);self.assertEqual(out['animation_curves_checked'],int(animated))
            self.assertFalse(out['execution_authority']);self.assertEqual(p,prior)
            self.assertEqual(out['source']['source_kind'],s.SCHEMA);self.assertIn('mesh_instances',out['source'])

    def test_external_binding_is_typed_frozen_and_deeply_immutable(self):
        p=packet();b=binding(p)
        self.assertIs(type(b.mesh_identity),bytes)
        with self.assertRaises(dataclasses.FrozenInstanceError):b.process_id=8
        self.refused(p,'external_binding_required','unavailable',b=dataclasses.asdict(b))
        for changes in (dict(process_id=True),dict(expected_frame=(True,0.)),dict(unit_scale_m=True),dict(document_epoch='x'*32)):
            with self.subTest(changes=changes),self.assertRaises(s.SmallSourceError):binding(p,**changes)

    def test_self_consistent_wrong_pin_cannot_become_external_evidence(self):
        for key in (*s.PIN_FIELDS,'document_epoch','process_id'):
            p=packet();external=binding(p);p['identity'][key]=99 if key=='process_id' else 'b'*32 if key=='document_epoch' else 'f'*64
            self.refused(p,'external_binding_mismatch','unavailable',b=external)
        p=packet();p['qualified']=True;self.refused(p,'packet_fields')

    def test_fixed_frame_unit_roles_and_instances_are_external_expectations(self):
        for kind,code in (('frame','fixed_frame'),('unit','fixed_unit'),('instance','role_instance_changed')):
            p=packet();external=binding(p)
            if kind=='frame':p['inputs']['frame']['number']=2
            elif kind=='unit':p['inputs']['unit_scale_m']=.001
            else:
                obj=p['inputs']['closure'][2];obj['identity']['session_uid']=99
                next(o for o in p['inputs']['scene']['objects'] if o['name']=='Mesh')['identity']['session_uid']=99
            self.refused(p,code,'unavailable',b=external)

    def test_full_tail_evaluated_point_and_topology_are_verified(self):
        p=packet();p['evaluated']['vertices'][-1][0]+=.01;self.refused(p,'LBS_replay_disagreement')
        p=packet();p['inputs']['mesh']['triangles'][0][0]=True;p['evaluated']['triangles'][0][0]=True;self.refused(p,'triangles')

    def test_deform_values_are_not_cleaned_to_make_source_acceptable(self):
        p=packet();b=p['inputs']['rig']['bones'][0];epsilon=2**-23
        b['scale'][0]+=epsilon;b['basis_matrix'][0][0]+=epsilon;b['pose_matrix'][0][0]+=epsilon
        p['evaluated']['bones'][0]['pose_matrix'][0][0]+=epsilon;p['evaluated']['vertices'][1][0]+=epsilon;rehash(p)
        prior=copy.deepcopy(p);out=self.validate(p);self.assertEqual(out['max_replay_error'],0.);self.assertEqual(p,prior)
        p=packet();b=p['inputs']['rig']['bones'][0];b['basis_matrix'][0][0]=1.01;self.refused(p,'nonrigid_matrix')

    def test_real_translation_replays_without_normalizing_raw_location(self):
        p=packet();b=p['inputs']['rig']['bones'][0];b['location'][0]=.125
        for key in ('basis_matrix','pose_matrix'):b[key][0][3]=.125
        b['pose_head'][0]=b['pose_tail'][0]=.125
        p['evaluated']['bones'][0].update({k:copy.deepcopy(b[k]) for k in ('pose_matrix','pose_head','pose_tail')})
        for v in p['evaluated']['vertices']:v[0]+=.125
        out=self.validate(rehash(p));self.assertEqual(out['max_replay_error'],0.);self.assertEqual(b['location'][0],.125)

    def test_source_and_audit_mismatch_cannot_be_overridden(self):
        p=packet();p['source_sha256']='0'*64
        with self.assertRaisesRegex(s.SmallSourceError,'source_digest'):self.validate(p)
        p=packet();p['audit']['before_sha256']='0'*64;p['source_sha256']=s.source_digest(p)
        with self.assertRaisesRegex(s.SmallSourceError,'RNA_changed'):self.validate(p)

    def test_future_key_change_invalidates_old_source_with_identical_geometry(self):
        p=packet(True);old=p['source_sha256'];p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]['keys'].append(
            dict(p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]['keys'][-1],co=[5.,.2]))
        rehash(p);self.validate(p)
        with self.assertRaisesRegex(s.SmallSourceError,'stale_source'):self.validate(p,expected_source=old)

    def test_parent_inverse_compensation_keeps_geometry_but_changes_source(self):
        p=packet();old=p['source_sha256'];mesh=p['inputs']['closure'][2]
        mesh['matrix_parent_inverse'][0][3]=.125;mesh['matrix_basis'][0][3]=-.125;mesh['location'][0]=-.125;rehash(p)
        self.validate(p)
        with self.assertRaisesRegex(s.SmallSourceError,'stale_source'):self.validate(p,expected_source=old)

    def test_geometry_and_dependent_world_matrices_cannot_self_cancel(self):
        p=packet();p['evaluated']['mesh_matrix_world'][0][3]=1.;p['evaluated']['rig_matrix_world'][0][3]=1.
        self.refused(p,'evaluated_world_binding','unavailable')
        p=packet();p['inputs']['closure'][0]['matrix_world'][0][3]=1.;self.refused(p,'parent_matrix_disagreement')

    def test_unknown_source_never_returns_a_geometry_proof(self):
        p=packet(True);curve=p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]
        curve['keys'][0]['interpolation']='BEZIER';self.refused(p,'curve_interpolation','unknown')
        p=packet();p['inputs']['closure'][0]['matrix_basis'][0][0]=0.;self.refused(p,'matrix_condition','unknown')

    def test_dependency_refusals_are_precise(self):
        cases=[('DQ',lambda p:p['inputs']['mesh']['modifier'][0]['settings'].update(use_deform_preserve_volume=True)),
            ('envelopes',lambda p:p['inputs']['mesh']['modifier'][0]['settings'].update(use_bone_envelopes=True)),
            ('shape_keys',lambda p:p['inputs']['mesh'].update(shape_keys={})),
            ('constraint',lambda p:p['inputs']['rig']['bones'][0]['constraints'].append({'type':'COPY_ROTATION'})),
            ('driver',lambda p:p['inputs']['closure'][1]['animation']['object']['drivers'].append({'expression':'0'})),
            ('action_blend',lambda p:p['inputs']['closure'][1]['animation']['object'].update(action_blend_type='ADD')),
            ('action_slot',lambda p:p['inputs']['actions'][0]['slots'][0].update(handle=8))]
        for code,change in cases:
            with self.subTest(code=code):
                p=packet(True);change(p);self.refused(p,code)

    def test_bounded_counts_and_current_coordinate_resolution_domain(self):
        p=packet();p['inputs']['mesh']['vertices']*=86;self.refused(p,'vertex_limit')
        p=packet();p['inputs']['mesh']['vertices'][-1][0]=10.001;self.refused(p,'coordinate_bound')
        p=packet();p['inputs']['closure'][0]['matrix_world'][0][3]=100.01;self.refused(p,'world_translation_bound')
        p=packet(True);curve=p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]
        curve['keys']=[dict(curve['keys'][0],co=[float(i),0.]) for i in range(257)];self.refused(p,'curve_key_limit')

    def test_unweighted_vertices_are_source_gaps_not_health_claims(self):
        p=packet();p['inputs']['mesh']['weights'][2]=[];out=self.validate(rehash(p));self.assertEqual(out['unweighted'],[2]);self.assertFalse(out['execution_authority'])

    def test_original_deadline_applies_to_entry_and_final_proof_copy(self):
        p=packet();external=binding(p)
        with self.assertRaisesRegex(s.SmallSourceError,'original_deadline'):s.validate(p,deadline_ns=time.perf_counter_ns()-1,expected_bindings=external)
        clock=[0];real=copy.deepcopy
        def late(value):
            result=real(value);clock[0]=100;return result
        with patch.object(s.copy,'deepcopy',late),patch.object(s.r.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(s.SmallSourceError,'original_deadline'):s.validate(p,deadline_ns=100,expected_bindings=external)

    def test_public_current_scalar_linear_constant_and_exact_bezier_keys(self):
        for mode,first,last,frame,translation in (('LINEAR',0.,2.,1,1.),('CONSTANT',0.,2.,1,0.),('BEZIER',0.,2.,0,0.)):
            with self.subTest(mode=mode):
                p=packet(True);curve=p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]
                curve['keys'][0].update(co=[0.,first],interpolation=mode);curve['keys'][1]['co']=[2.,last];p['inputs']['frame']['number']=frame
                b=p['inputs']['rig']['bones'][0];b['location'][0]=translation
                for key in ('basis_matrix','pose_matrix'):b[key][0][3]=translation
                b['pose_head'][0]=b['pose_tail'][0]=translation
                p['evaluated']['bones'][0].update({k:copy.deepcopy(b[k]) for k in ('pose_matrix','pose_head','pose_tail')})
                for point in p['evaluated']['vertices']:point[0]+=translation
                out=self.validate(rehash(p));self.assertEqual(out['animation_curves_checked'],1);self.assertEqual(out['max_replay_error'],0.)

    def test_public_quaternion_interpolation_and_two_bone_parent_world_composition(self):
        import math
        def rotation(axis,degrees,translation=(0.,0.,0.)):
            angle=math.radians(degrees);c=math.cos(angle);sn=math.sin(angle);m=np.eye(4);i,j={'X':(1,2),'Y':(2,0),'Z':(0,1)}[axis]
            m[i,i]=m[j,j]=c;m[i,j]=-sn;m[j,i]=sn;m[:3,3]=translation
            q=[math.cos(angle/2),0.,0.,0.];q['XYZ'.index(axis)+1]=math.sin(angle/2);return m,q
        p=packet();objects=p['inputs']['closure']
        for obj,axis,degrees,translation in zip(objects,('Z','X','Y'),(30.,20.,-15.),((.3,-.2,.1),(.1,.2,0.),(-.2,.1,.25))):
            m,q=rotation(axis,degrees,translation);obj.update(rotation_quaternion=q,location=list(translation),matrix_basis=m.tolist())
        parent_inverse,_=rotation('Y',-12.,(.125,0.,-.125));objects[1]['matrix_parent_inverse']=parent_inverse.tolist()
        for obj in objects:
            basis=np.array(obj['matrix_basis']);local=basis if obj['parent'] is None else np.array(obj['matrix_parent_inverse'])@basis
            parent=next((o for o in objects if o['name']==obj['parent']),None)
            world=local if parent is None else np.array(parent['matrix_world'])@local
            obj.update(matrix_local=local.tolist(),matrix_world=world.tolist())
        b0=p['inputs']['rig']['bones'][0];basis0,q0=rotation('X',17.);b0.update(rotation_quaternion=q0,basis_matrix=basis0.tolist(),pose_matrix=basis0.tolist(),
            pose_head=(basis0@np.array([0.,0.,0.,1.]))[:3].tolist(),pose_tail=(basis0@np.array([0.,1.,0.,1.]))[:3].tolist())
        b1=copy.deepcopy(b0);rest=np.eye(4);rest[1,3]=2.;basis1,q1=rotation('Z',-35.,(.125,0.,0.));pose1=basis0@rest@basis1
        b1.update(name='Tip',parent='Bone',rest_matrix=rest.tolist(),rest_head=[0.,2.,0.],rest_tail=[0.,3.,0.],location=[.125,0.,0.],
            rotation_quaternion=q1,basis_matrix=basis1.tolist(),pose_matrix=pose1.tolist(),pose_head=(pose1@np.array([0.,0.,0.,1.]))[:3].tolist(),
            pose_tail=(pose1@np.array([0.,1.,0.,1.]))[:3].tolist())
        p['inputs']['rig']['bones'].append(b1);mesh=p['inputs']['mesh'];mesh['groups'].append('Tip');mesh['weights']=[[[0,1.]],[[0,.2],[1,.8]],[[1,1.]]]
        ev=p['evaluated'];ev['bones']=[{k:copy.deepcopy(b[k]) for k in ('name','parent','pose_matrix','pose_head','pose_tail')} for b in (b0,b1)]
        ev['rig_matrix_world']=copy.deepcopy(objects[1]['matrix_world']);ev['mesh_matrix_world']=copy.deepcopy(objects[2]['matrix_world'])
        into=np.linalg.solve(np.array(ev['rig_matrix_world']),np.array(ev['mesh_matrix_world']));back=np.linalg.inv(into)
        transforms=[np.array(b['pose_matrix'])@np.linalg.inv(np.array(b['rest_matrix'])) for b in (b0,b1)];points=[]
        for point,weights in zip(mesh['vertices'],mesh['weights']):
            q=into@np.array([*point,1.]);mixed=sum(weight*(transforms[group]@q) for group,weight in weights);points.append((back@mixed)[:3].tolist())
        ev['vertices']=points;out=self.validate(rehash(p));self.assertLess(out['max_replay_error'],1e-12)
        np.testing.assert_allclose(out['current'],points,atol=1e-12);self.assertEqual(out['bones_total'],2)

    def test_booleans_cannot_impersonate_object_or_slot_instances(self):
        for change in (lambda p:p['inputs']['closure'][1]['parent_identity'].update(session_uid=True),
            lambda p:p['inputs']['actions'][0]['slots'][0]['users'][0].update(session_uid=True),
            lambda p:p['inputs']['closure'][1]['animation']['object']['action_slot'].update(handle=True)):
            p=packet(True);change(p)
            with self.assertRaises(s.SmallSourceError):self.validate(rehash(p))

    def test_unknown_leaf_fields_are_not_silently_accepted(self):
        for change,code in ((lambda p:p['inputs']['closure'][0].update(hidden_dependency=True),'object_fields'),
            (lambda p:p['inputs']['actions'][0]['layers'][0].update(influence=.5),'action_shape'),
            (lambda p:p['inputs']['mesh']['modifier'][0]['settings'].update(new_setting=0),'modifier_settings_fields')):
            p=packet(True);change(p);self.refused(p,code)


if __name__=='__main__':unittest.main()
