"""Independent NumPy FK fixture assembly, rule semantics and corrupt sources."""
import ast,copy,hashlib,io,json,math,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from human_eye_plugin import rig_pose as r


def rotation(axis,degrees):
    a=math.radians(degrees);c=math.cos(a);s=math.sin(a);m=np.eye(4)
    i,j={'X':(1,2),'Y':(2,0),'Z':(0,1)}[axis]
    m[i,i]=m[j,j]=c;m[i,j]=-s;m[j,i]=s;return m


def packet(rotations=(('Y',95),),*,rest_roll=0,parented=True,unit=1.,object_matrix=None):
    bones=[];pose=[];rest=[]
    for i,(axis,degrees) in enumerate(rotations):
        local=np.eye(4);local[1,3]=1 if i and parented else i*2
        if rest_roll:local=local@rotation('Y',rest_roll)
        rm=(rest[i-1]@local) if i and parented else local
        basis=rotation(axis,degrees)
        pm=(pose[i-1]@np.linalg.inv(rest[i-1])@rm@basis) if i and parented else rm@basis
        rest.append(rm);pose.append(pm)
        transform=lambda m,p:(m@np.array([*p,1.]))[:3].tolist()
        bones.append(dict(name='bone_%03d'%i,parent='bone_%03d'%(i-1) if i and parented else None,
            rest_matrix=rm.tolist(),rest_head=transform(rm,[0,0,0]),rest_tail=transform(rm,[0,1,0]),length=1.,
            inherit_rotation=True,inherit_scale='FULL',local_location=True,connected=False,bbone_segments=1,
            pose_matrix=pm.tolist(),pose_head=transform(pm,[0,0,0]),pose_tail=transform(pm,[0,1,0]),
            basis_matrix=basis.tolist(),rotation_mode='XYZ',rotation_euler=[0.,0.,0.],rotation_quaternion=[1.,0.,0.,0.]))
    p=dict(object_name='Rig',data_name='RigData',frame=dict(number=1,subframe=0.),unit_scale_m=unit,
        object_matrix_world=np.eye(4).tolist() if object_matrix is None else object_matrix,
        context=dict(mode='OBJECT',active_object='Rig',selected_objects=['Rig']),
        source_kind='original_rest_and_evaluated_current_pose',flags=dict(constraints=0,animation=False,drivers=False,object_parent=False,pose_position='POSE'),bones=bones)
    identity=dict(document_epoch='a'*32,object_id='blender:'+r.digest(['','Rig']),object_instance='1',data_instance='2')
    value=dict(schema='rig-pose-snapshot-v1',identity=identity,payload=p,capture_id='c'*32,audit=dict(before_sha256='d'*64,after_sha256='d'*64))
    return rehash(value)


def rehash(v):
    v['source_sha256']=r.digest(dict(identity=v['identity'],payload=v['payload']));v['rig_sha256']=r.rig_digest(v['payload']);return v


def policy(v,*,minimum=-45,maximum=45,swing=140,all_bones=False):
    names=[b['name'] for b in v['payload']['bones']] if all_bones else [v['payload']['bones'][0]['name']]
    return dict(schema='rig-pose-orientation-rules-v1',rig_sha256=v['rig_sha256'],provenance='independent test role orientation rule, not anatomy',
        rules=[dict(bone=n,min_twist_deg=minimum,max_twist_deg=maximum,max_swing_deg=swing) for n in names])


class RigPoseTests(unittest.TestCase):
    def analyze(self,v,p=None):return r.analyze(v,p,deadline_ns=time.perf_counter_ns()+2_000_000_000)
    def test_axial_twist_without_endpoint_change_is_located(self):
        v=packet();b=v['payload']['bones'][0];self.assertEqual(b['rest_head'],b['pose_head']);self.assertEqual(b['rest_tail'],b['pose_tail'])
        result=self.analyze(v,policy(v));self.assertAlmostEqual(result['bones'][0]['twist_deg'],95,places=9)
        self.assertEqual(result['violations_total'],1);self.assertEqual(result['violations'][0]['bone'],'bone_000')
        self.assertEqual(result['damage_classification'],'not_inferred')
    def test_no_policy_never_infers_damage_or_generic_bad_angle(self):
        result=self.analyze(packet());self.assertEqual(result['assessment'],'unassessed_no_rules');self.assertEqual(result['rules_total'],0)
    def test_rule_coverage_does_not_present_unruled_parent_as_checked(self):
        v=packet((('Y',120),('Y',0)));p=policy(v);p['rules'][0]['bone']='bone_001';result=self.analyze(v,p)
        facts={value['bone']:value for value in result['bones']}
        self.assertFalse(facts['bone_000']['rule_registered']);self.assertTrue(facts['bone_001']['rule_registered'])
        self.assertEqual(result['rule_bones_total'],1);self.assertEqual(result['unruled_bones_total'],1)
        self.assertEqual(result['assessment'],'within_registered_orientation_limits')
    def test_parent_motion_removed_and_child_bend_preserved(self):
        result=self.analyze(packet((('Y',120),('X',30),('Y',0))))
        facts={v['bone']:v for v in result['bones']}
        self.assertAlmostEqual(facts['bone_000']['twist_deg'],120,places=8)
        self.assertAlmostEqual(facts['bone_001']['swing_deg'],30,places=8)
        self.assertAlmostEqual(facts['bone_002']['rotation_deg'],0,places=8)
    def test_rolled_rest_axes_are_not_world_axis_twist(self):
        result=self.analyze(packet((('Y',35),('X',20)),rest_roll=47))
        facts={v['bone']:v for v in result['bones']};self.assertAlmostEqual(facts['bone_000']['twist_deg'],35,places=8)
        self.assertAlmostEqual(facts['bone_001']['swing_deg'],20,places=8)
    def test_quaternion_sign_and_full_turn_visual_orientation_equivalent(self):
        a=packet((('Y',0),));b=packet((('Y',360),));b['payload']['bones'][0]['rotation_quaternion']=[-1.,0,0,0];rehash(b)
        self.assertAlmostEqual(self.analyze(a)['bones'][0]['rotation_deg'],self.analyze(b)['bones'][0]['rotation_deg'],places=8)
        self.assertIn('rotation_winding',self.analyze(b)['not_checked'])
    def test_object_transform_units_and_reflection_do_not_change_local_rule(self):
        transform=rotation('Z',73);transform[:3,:3]=transform[:3,:3]@np.diag([-2.,3.,.5]);transform[:3,3]=[500,-300,100]
        v=packet(unit=.001,object_matrix=transform.tolist());result=self.analyze(v,policy(v))
        self.assertAlmostEqual(result['bones'][0]['twist_deg'],95,places=8);self.assertEqual(result['violations_total'],1)
        self.assertAlmostEqual(result['bones'][0]['world_head_m'][0],.5)
    def test_singular_swing_unknown_twist_not_zero(self):
        v=packet((('X',180),));result=self.analyze(v,policy(v));self.assertIsNone(result['bones'][0]['twist_deg'])
        self.assertEqual(result['unknown_rules_total'],2);self.assertEqual(result['violations_total'],1)
    def test_twist_branch_boundary_retains_sign_unknown(self):
        v=packet((('Y',180),));result=self.analyze(v,policy(v));self.assertIsNone(result['bones'][0]['twist_deg']);self.assertEqual(result['unknown_rules_total'],2)
    def test_angular_guard_band_does_not_assert_inside_or_outside(self):
        v=packet((('Y',45),));result=self.analyze(v,policy(v));self.assertEqual(result['violations_total'],0)
        self.assertEqual(result['unknown_rules_total'],1);self.assertEqual(result['assessment'],'unknown')
    def test_unsupported_domain_is_not_normal_or_zero_twist(self):
        for key,value in (('constraints',1),('animation',True),('drivers',True),('object_parent',True),('pose_position','REST')):
            v=packet();v['payload']['flags'][key]=value;rehash(v);result=self.analyze(v,policy(v))
            self.assertEqual(result['status'],'unsupported');self.assertEqual(result['unknown_rules_total'],3);self.assertIsNone(result['bones'][0]['twist_deg'])
    def test_inheritance_bbone_and_nonrigid_pose_remain_unsupported(self):
        for key,value in (('inherit_scale','NONE'),('inherit_rotation',False),('local_location',False),('bbone_segments',4)):
            v=packet();v['payload']['bones'][0][key]=value;rehash(v);self.assertEqual(self.analyze(v)['status'],'unsupported')
        v=packet();v['payload']['bones'][0]['basis_matrix'][0][0]*=2;rehash(v)
        self.assertEqual(self.analyze(v)['status'],'unsupported')
    def test_policy_different_rest_rig_missing_bone_duplicate_or_nan_denied(self):
        for change in (lambda p:p.__setitem__('rig_sha256','0'*64),lambda p:p['rules'][0].__setitem__('bone','missing'),
            lambda p:p['rules'].append(copy.deepcopy(p['rules'][0])),lambda p:p['rules'][0].__setitem__('max_swing_deg',float('nan')),
            lambda p:p['rules'][0].__setitem__('min_twist_deg',True)):
            v=packet();p=policy(v);change(p)
            with self.assertRaises(ValueError):self.analyze(v,p)
    def test_current_source_tampering_and_foreign_instance_refused(self):
        v=packet();old=copy.deepcopy(v['identity']);v['identity']['object_instance']='new';rehash(v)
        with self.assertRaises(ValueError):r.validate(v,deadline_ns=time.perf_counter_ns()+10**9,expected_source=old)
        v=packet();v['payload']['frame']['number']=2
        with self.assertRaises(ValueError):self.analyze(v)
    def test_cyclic_or_missing_parent_and_duplicate_names_refused(self):
        for kind in ('cycle','missing','duplicate'):
            v=packet((('Y',0),('Y',0)))
            if kind=='cycle':v['payload']['bones'][0]['parent']='bone_001'
            elif kind=='missing':v['payload']['bones'][0]['parent']='absent'
            else:v['payload']['bones'][1]['name']='bone_000'
            rehash(v)
            with self.assertRaises(ValueError):self.analyze(v)
    def test_64_complete_counts_16_delivery_and_65_refusal(self):
        v=packet(tuple(('Y',95) for _ in range(64)),parented=False);result=self.analyze(v,policy(v,all_bones=True))
        self.assertEqual(result['bones_total'],64);self.assertEqual(result['bones_omitted'],48)
        self.assertEqual(result['violations_total'],64);self.assertEqual(result['violations_omitted'],48)
        with self.assertRaises(ValueError):self.analyze(packet(tuple(('Y',95) for _ in range(65)),parented=False))
    def test_wrong_matrix_endpoint_basis_and_audit_rejected(self):
        for change in (lambda v:v['payload']['bones'][0]['pose_head'].__setitem__(0,.5),
            lambda v:v['payload']['bones'][0].__setitem__('basis_matrix',np.eye(4).tolist()),
            lambda v:v['audit'].__setitem__('after_sha256','e'*64)):
            v=packet();change(v);rehash(v)
            with self.assertRaises(ValueError):self.analyze(v)
    def test_nonfinite_boolean_matrices_bytes_and_expired_window_rejected(self):
        for bad in (float('nan'),float('inf'),True):
            v=packet();v['payload']['bones'][0]['pose_matrix'][0][0]=bad
            with self.assertRaises(ValueError):self.analyze(v)
        for blob in (b'{"a":1,"a":2}',b'{"a":NaN}',b' '* (r.MAX_BYTES+1)):
            with self.assertRaises(ValueError):r.decode(blob)
        with self.assertRaises(ValueError):r.validate(packet(),deadline_ns=time.perf_counter_ns()-1)
    def test_matrix_inverse_independent_numpy(self):
        a=rotation('X',37)@rotation('Y',-29);a[:3,3]=[.3,4,-2]
        np.testing.assert_allclose(r.inverse(a.tolist()),np.linalg.inv(a),atol=1e-14)


class RigTransportTests(unittest.TestCase):
    def actor(self):
        from human_eye_plugin.rig_pose_process import RigPoseProcess
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve()
        actor=RigPoseProcess.__new__(RigPoseProcess);actor.path=root/'PROFILE.json';actor.path.write_bytes(b'{}');actor.profile_bytes=b'{}'
        actor.profile=dict(policy_file=None,policy_sha256=None,object_name='Rig',expected_frame=dict(number=1,subframe=0.))
        actor.closed=False;actor.deadline_ns=time.perf_counter_ns()+2_000_000_000;actor.sequence=0;actor._gate=threading.Lock();actor.source=None
        actor.process=SimpleNamespace(stdin=io.BytesIO());actor._next=lambda:dict(kind='snapshot',id=1,snapshot=packet())
        self.patch=patch('human_eye_plugin.rig_pose_process.check_source_drift',return_value={'compatible':True});self.patch.start();self.addCleanup(self.patch.stop)
        return actor,root
    def test_lifetime_budget_refuses_before_seventeenth_request(self):
        actor,_=self.actor();actor.sequence=16
        with self.assertRaises(ValueError):actor.inspect()
        self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_changed_profile_or_runtime_cannot_send_request(self):
        actor,_=self.actor();actor.path.write_bytes(b'{ }')
        with self.assertRaises(ValueError):actor.inspect()
        self.assertEqual(actor.process.stdin.getvalue(),b'')
        actor,_=self.actor()
        with patch('human_eye_plugin.rig_pose_process.check_source_drift',return_value={'compatible':False}):
            with self.assertRaises(ValueError):actor.inspect()
        self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_policy_pin_rechecked_not_silently_replaced(self):
        actor,root=self.actor();path=root/'POLICY.json';path.write_bytes(b'{}')
        actor.profile.update(policy_file=str(path),policy_sha256=hashlib.sha256(b'{}').hexdigest());path.write_bytes(b'{ }')
        with self.assertRaises(ValueError):actor.inspect()
        self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_current_frame_is_bound_without_frame_mutation(self):
        actor,_=self.actor();v=packet();v['payload']['frame']['number']=2;rehash(v);actor._next=lambda:dict(kind='snapshot',id=1,snapshot=v)
        with self.assertRaisesRegex(ValueError,'frame_binding'):actor.inspect()
        sent=r.decode(actor.process.stdin.getvalue());self.assertEqual(sent['command'],'inspect');self.assertEqual(set(sent),{'id','command','deadline_ns'})
    def test_foreign_document_and_reply_id_refused(self):
        actor,_=self.actor();actor.source=copy.deepcopy(packet()['identity']);v=packet();v['identity']['document_epoch']='e'*32;rehash(v)
        actor._next=lambda:dict(kind='snapshot',id=1,snapshot=v)
        with self.assertRaisesRegex(ValueError,'foreign_source'):actor.inspect()
        actor,_=self.actor();actor._next=lambda:dict(kind='snapshot',id=9,snapshot=packet())
        with self.assertRaisesRegex(ValueError,'snapshot_reply'):actor.inspect()
    def test_single_flight_and_original_deadline(self):
        actor,_=self.actor();actor._gate.acquire()
        with self.assertRaisesRegex(ValueError,'single_flight'):actor.inspect()
        actor._gate.release();actor.deadline_ns=time.perf_counter_ns()-1
        with self.assertRaisesRegex(ValueError,'original_deadline'):actor.inspect()
        self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_actual_rna_writer_operations_absent_from_fixed_reader(self):
        from human_eye_plugin import rig_pose_worker
        tree=ast.parse(Path(rig_pose_worker.__file__).read_text())
        writes=[ast.unparse(node) for node in ast.walk(tree) if isinstance(node,ast.Attribute) and isinstance(node.ctx,ast.Store)]
        self.assertEqual(writes,['sys.dont_write_bytecode'])
        forbidden={'frame_set','save_as_mainfile','mode_set','transform_apply','keyframe_insert','driver_add'}
        self.assertFalse({node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}&forbidden)
    def test_guarded_near_180_swing_is_unknown_with_float_precision(self):
        v=packet((('X',179.999999),));out=r.analyze(v,policy(v),deadline_ns=time.perf_counter_ns()+2_000_000_000)
        self.assertIsNone(out['bones'][0]['twist_deg']);self.assertEqual(out['unknown_rules_total'],2)


if __name__=='__main__':unittest.main()
