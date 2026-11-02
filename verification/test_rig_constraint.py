"""Independent matrix truth, source attacks and fixed read-only transport."""
import ast,copy,hashlib,io,math,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from human_eye_plugin import rig_constraint as c
from verification.test_rig_pose import packet as fk_packet,rotation,rehash as fk_rehash
r=c.r


def rehash(v):
    fk_rehash(v['rig']);v['source_sha256']=c.source_digest(v);return v


def packet(count=2,owner=1,axis='Y',deg=95,parent_deg=0,world_deg=0):
    rig=fk_packet(tuple(('Z',parent_deg if i==0 else 20 if i==owner else 0) for i in range(count)))
    p=rig['payload'];world=rotation('X',world_deg);p['object_matrix_world']=world.tolist();p['flags']['constraints']=1
    poses=[];rest=[]
    for i,b in enumerate(p['bones']):
        rm=np.array(b['rest_matrix']);basis=np.array(b['basis_matrix']);pm=rm@basis if not i else poses[-1]@np.linalg.inv(rest[-1])@rm@basis
        if i==owner:pm[:3,:3]=world[:3,:3].T@rotation(axis,deg)[:3,:3]
        b['pose_matrix']=pm.tolist();b['pose_head']=(pm@np.array([0,0,0,1]))[:3].tolist();b['pose_tail']=(pm@np.array([0,1,0,1]))[:3].tolist()
        poses.append(pm);rest.append(rm)
    target=dict(name='Target',object_id='blender:'+r.digest(['','Target']),object_instance='77',object_type='EMPTY',
        matrix_world=rotation(axis,deg).tolist(),basis_matrix=rotation(axis,deg).tolist(),animation=False,drivers=False,
        object_parent=False,constraints=0,linked=False,channels=dict(rotation_mode='XYZ'))
    for key,n in c.CHANNEL_FIELDS.items():target['channels'][key]=[0.]*n
    target['channels']['scale']=target['channels']['delta_scale']=[1.,1.,1.]
    target['channels']['rotation_quaternion']=target['channels']['delta_rotation_quaternion']=[1.,0,0,0]
    target['channels']['rotation_euler'][{'X':0,'Y':1,'Z':2}[axis]]=math.radians(deg)
    constraint=dict(bone='bone_%03d'%owner,index=0,name='Copy Rotation',type='COPY_ROTATION',target_id=target['object_id'],target_instance='77',
        owner_space='WORLD',target_space='WORLD',space_object=None,space_subtarget='',subtarget='',mute=False,enabled=True,
        show_expanded=True,active=True,influence=1.,is_valid=True,use_x=True,use_y=True,use_z=True,invert_x=False,invert_y=False,invert_z=False,
        euler_order='AUTO',mix_mode='REPLACE',use_offset=False)
    raw=[dict(name=b['name'],basis=b['basis_matrix'],location=[0.,0.,0.],scale=[1.,1.,1.],mode=b['rotation_mode'],
        euler=b['rotation_euler'],quaternion=b['rotation_quaternion'],axis_angle=[0.,0.,1.,0.]) for b in p['bones']]
    return rehash(dict(schema='rig-constraint-snapshot-v1',scene_sha256='f'*64,rig=rig,bone_channels=raw,rig_object_basis=world.tolist(),target=target,
        constraint=constraint,audit=copy.deepcopy(rig['audit'])))


class ConstraintTests(unittest.TestCase):
    def validate(self,v,**kw):return c.validate(v,deadline_ns=time.perf_counter_ns()+2_000_000_000,**kw)
    def analyze(self,v):return c.analyze(v,deadline_ns=time.perf_counter_ns()+2_000_000_000)
    def test_axis_twist_endpoints_unchanged_input_and_output_separate(self):
        v=packet();out=self.analyze(v);b=out['bones'][0]
        self.assertAlmostEqual(b['input_channel']['rotation_deg'],20)
        self.assertAlmostEqual(b['evaluated_local']['twist_deg'],95)
        self.assertEqual(v['rig']['payload']['bones'][1]['rest_tail'],v['rig']['payload']['bones'][1]['pose_tail'])
        self.assertEqual(out['assessment'],'unassessed_no_rules');self.assertEqual(out['damage_classification'],'not_inferred')
    def test_parent_and_world_noncommuting_rotations_use_matrices(self):
        v=packet(axis='Z',deg=65,parent_deg=30,world_deg=20);out=self.analyze(v)
        b=v['rig']['payload']['bones'][1];p=v['rig']['payload']['bones'][0]
        expected=np.linalg.inv(np.array(b['rest_matrix']))@np.array(p['rest_matrix'])@np.linalg.inv(np.array(p['pose_matrix']))@np.array(b['pose_matrix'])
        np.testing.assert_allclose(c.delta(b,{x['name']:x for x in v['rig']['payload']['bones']}),expected,atol=1e-12)
        self.assertNotAlmostEqual(out['bones'][0]['evaluated_local']['rotation_deg'],35,places=2)
    def test_unconstrained_descendant_follows_solved_parent(self):
        out=self.analyze(packet(count=3));b=next(b for b in out['bones'] if b['bone']=='bone_002')
        self.assertAlmostEqual(b['evaluated_local']['rotation_deg'],0,places=10)
    def test_old_FK_still_reports_constraint_domain_unsupported(self):
        v=packet();self.assertEqual(r.analyze(v['rig'],deadline_ns=time.perf_counter_ns()+1_000_000_000)['status'],'unsupported')
    def test_64_65_and_complete_count_before_delivery(self):
        out=self.analyze(packet(count=64,owner=31));self.assertEqual((out['bones_total'],len(out['bones']),out['bones_omitted']),(64,16,48))
        self.assertTrue(out['bones'][0]['constrained']);self.assertEqual(out['unruled_bones_total'],64)
        with self.assertRaisesRegex(ValueError,'bone_limit'):self.validate(packet(count=65,owner=31))
    def test_capture_UUID_not_a_state_change(self):
        old=packet();v=copy.deepcopy(old);v['rig']['capture_id']='e'*32;rehash(v);self.validate(v,expected=old)
    def test_same_pose_changed_control_representation_invalidates_reference(self):
        old=packet();v=copy.deepcopy(old);v['target']['channels']['rotation_euler'][1]+=2*math.pi;rehash(v)
        self.validate(v)
        with self.assertRaisesRegex(ValueError,'stale_source'):self.validate(v,expected=old)
    def test_other_document_frame_instance_and_file_cannot_reuse_source(self):
        for mode in ('epoch','frame','target','file'):
            old=packet();v=copy.deepcopy(old)
            if mode=='epoch':v['rig']['identity']['document_epoch']='e'*32
            if mode=='frame':v['rig']['payload']['frame']['number']=2
            if mode=='target':v['target']['object_instance']=v['constraint']['target_instance']='88'
            if mode=='file':v['scene_sha256']='e'*64
            rehash(v)
            with self.assertRaisesRegex(ValueError,'stale_source'):self.validate(v,expected=old)
    def test_target_cannot_be_omitted_or_rebound_by_name_only(self):
        v=packet();del v['target']
        with self.assertRaises(ValueError):self.validate(v)
        v=packet();v['constraint']['target_instance']='99';rehash(v)
        with self.assertRaisesRegex(ValueError,'target_binding'):self.validate(v)
    def test_rehashed_output_cannot_ignore_target_rotation(self):
        v=packet();v['target']['matrix_world']=v['target']['basis_matrix']=rotation('Y',40).tolist();rehash(v)
        with self.assertRaisesRegex(ValueError,'world_rotation_disagrees'):self.validate(v)
    def test_unconstrained_FK_corruption_not_hidden_by_constraint(self):
        v=packet(count=3);b=v['rig']['payload']['bones'][2];b['basis_matrix']=rotation('X',25).tolist();v['bone_channels'][2]['basis']=b['basis_matrix'];rehash(v)
        with self.assertRaisesRegex(ValueError,'FK_or_position'):self.validate(v)
    def test_constraint_options_strict_and_all_semantic_settings_bound(self):
        for key,value in (('enabled',False),('enabled',1),('influence',True),('influence',.5),('mute',True),('use_z',False),('invert_x',True),
            ('use_offset',True),('euler_order','ZYX'),('owner_space','LOCAL'),('mix_mode','OFFSET'),('subtarget','Bone')):
            v=packet();v['constraint'][key]=value;rehash(v)
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'unsupported_'):self.validate(v)
    def test_extra_schema_and_nonfinite_or_boolean_matrix_refused(self):
        v=packet();v['constraint']['unknown_future_setting']=True;rehash(v)
        with self.assertRaisesRegex(ValueError,'settings_fields'):self.validate(v)
        for value in (True,float('inf'),float('nan')):
            v=packet();v['target']['matrix_world'][0][0]=value
            with self.assertRaises(ValueError):self.validate(v)
    def test_unsupported_dependencies_never_become_normal_pose(self):
        for key,value in (('animation',True),('drivers',True),('constraints',1),('object_parent',True),('linked',True)):
            v=packet();v['target'][key]=value;rehash(v)
            with self.assertRaisesRegex(ValueError,'unsupported_target'):self.validate(v)
        v=packet();v['rig']['payload']['flags']['constraints']=2;rehash(v)
        with self.assertRaisesRegex(ValueError,'unsupported_rig'):self.validate(v)
    def test_connected_bone_ignored_translation_still_outside_domain(self):
        v=packet();v['bone_channels'][1]['location'][1]=.001;rehash(v)
        with self.assertRaisesRegex(ValueError,'unsupported_raw_bone_translation'):self.validate(v)
    def test_ambiguous_twist_kept_unknown(self):
        out=self.analyze(packet(axis='X',deg=180));self.assertEqual(out['status'],'partial')
        self.assertIsNone(out['bones'][0]['evaluated_local']['twist_deg'])
    def test_packet_bytes_JSON_audit_and_original_deadline(self):
        v=packet();v['constraint']['name']='x'*r.MAX_BYTES
        with self.assertRaises(ValueError):self.validate(v)
        v=packet();v['audit']['after_sha256']='e'*64;rehash(v)
        with self.assertRaises(ValueError):self.validate(v)
        with self.assertRaisesRegex(ValueError,'original_deadline'):c.validate(packet(),deadline_ns=time.perf_counter_ns()-1)
        for blob in (b'{"x":0,"x":1}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):r.decode(blob)


class ConstraintTransportTests(unittest.TestCase):
    def actor(self):
        from human_eye_plugin.rig_constraint_process import RigConstraintProcess
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve();scene=root/'fixture.blend';scene.write_bytes(b'fixture')
        actor=RigConstraintProcess.__new__(RigConstraintProcess);actor.path=root/'PROFILE.json';actor.path.write_bytes(b'{}');actor.profile_bytes=b'{}'
        v=packet();v['scene_sha256']=hashlib.sha256(b'fixture').hexdigest();rehash(v)
        actor.profile=dict(scene_file=str(scene),scene_sha256=v['scene_sha256'],object_name='Rig',target_name='Target',constraint_bone='bone_001',expected_frame=dict(number=1,subframe=0.))
        actor.closed=False;actor.deadline_ns=time.perf_counter_ns()+2_000_000_000;actor.sequence=0;actor._gate=threading.Lock();actor.source=None
        actor.process=SimpleNamespace(stdin=io.BytesIO());actor.template=v;actor._next=lambda:dict(kind='snapshot',id=actor.sequence,snapshot=actor.template)
        p=patch('human_eye_plugin.rig_constraint_process.check_source_drift',return_value={'compatible':True});p.start();self.addCleanup(p.stop)
        return actor,root
    def test_exact_16_reads_then_refuse_without_renewal(self):
        actor,_=self.actor();deadline=actor.deadline_ns
        for _ in range(16):actor.inspect()
        blob=actor.process.stdin.getvalue()
        with self.assertRaisesRegex(ValueError,'lifetime'):actor.inspect()
        self.assertEqual(blob,actor.process.stdin.getvalue());self.assertEqual(actor.deadline_ns,deadline)
        self.assertTrue(all(json_line['deadline_ns']==deadline for json_line in map(r.decode,blob.splitlines())))
    def test_profile_runtime_and_disk_file_drift_stop_before_send(self):
        for mode in ('profile','scene','runtime'):
            actor,root=self.actor()
            if mode=='profile':actor.path.write_bytes(b'{ }')
            if mode=='scene':(root/'fixture.blend').write_bytes(b'changed')
            with patch('human_eye_plugin.rig_constraint_process.check_source_drift',return_value={'compatible':mode!='runtime'}):
                with self.assertRaises(ValueError):actor.inspect()
            self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_single_flight_expiry_and_wrong_reply(self):
        actor,_=self.actor();actor._gate.acquire()
        with self.assertRaisesRegex(ValueError,'single_flight'):actor.inspect()
        actor._gate.release();actor.deadline_ns=time.perf_counter_ns()-1
        with self.assertRaisesRegex(ValueError,'original_deadline'):actor.inspect()
        actor,_=self.actor();actor._next=lambda:dict(kind='snapshot',id=99,snapshot=actor.template)
        with self.assertRaisesRegex(ValueError,'constraint_reply'):actor.inspect()
    def test_explicit_target_bone_and_frame_profile_binding(self):
        for key,value in (('target_name','Other'),('constraint_bone','bone_000'),('expected_frame',dict(number=2,subframe=0.))):
            actor,_=self.actor();actor.profile[key]=value
            with self.assertRaisesRegex(ValueError,'fixed_roles_or_frame'):actor.inspect()
    def test_worker_has_no_RNA_setter_or_frame_save_command(self):
        from human_eye_plugin import rig_constraint_worker
        tree=ast.parse(Path(rig_constraint_worker.__file__).read_text())
        stores=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store)]
        self.assertEqual(stores,['sys.dont_write_bytecode','package.__path__'])
        self.assertFalse({n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}&{'frame_set','save_as_mainfile','mode_set','driver_add','keyframe_insert'})


if __name__=='__main__':unittest.main()
