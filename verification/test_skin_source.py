"""Independent LBS packet assembly and source/correspondence attacks."""
import ast,copy,hashlib,io,math,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from human_eye_plugin import skin_source as s
from verification.test_rig_pose import packet as fk_packet,rehash as fk_rehash
from verification.run_skin_source_preflight import geometry
r=s.r


def rehash(v):fk_rehash(v['rig']);v['source_sha256']=s.source_digest(v);return v


def packet(*,neutral=False,unweighted=False,count=8,bones=2,influences=2,torus=False):
    rig=fk_packet(tuple(('Y',0 if neutral or i>1 else 90 if not i else -90) for i in range(bones)),parented=False)
    p=rig['payload'];raw=[dict(name=b['name'],basis=b['basis_matrix'],location=[0.,0.,0.],scale=[1.,1.,1.],mode=b['rotation_mode'],
        euler=b['rotation_euler'],quaternion=b['rotation_quaternion'],axis_angle=[0.,0.,1.,0.]) for b in p['bones']]
    vertices,faces=geometry(torus,max(0,count-8));weights=[[] if unweighted and not i else [[j,1./influences] for j in range(influences)] for i in range(len(vertices))]
    deformations=[np.array(b['pose_matrix'])@np.linalg.inv(np.array(b['rest_matrix'])) for b in p['bones']];evaluated=[]
    for v,ws in zip(vertices,weights):
        point=np.array([*v,1.]);evaluated.append(v if not ws else sum(weight*(deformations[g]@point) for g,weight in ws)[:3].tolist())
    mesh=dict(identity=dict(name='Skin',object_id='blender:'+r.digest(['','Skin']),object_instance='3',data_name='SkinData',data_instance='4'),
        object_matrix_world=np.eye(4).tolist(),basis_matrix=np.eye(4).tolist(),vertices=vertices,triangles=faces,weights=weights,groups=[b['name'] for b in p['bones']],
        evaluated_vertices=evaluated,evaluated_triangles=copy.deepcopy(faces),flags=dict(animation=False,drivers=False,object_parent=False,linked=False,shape_keys=False,constraints=0),
        modifier=dict(name='Skinning',type='ARMATURE',rig_id=rig['identity']['object_id'],rig_instance=rig['identity']['object_instance'],show_viewport=True,
            show_render=True,use_vertex_groups=True,use_bone_envelopes=False,use_deform_preserve_volume=False,use_multi_modifier=False,vertex_group='',invert_vertex_group=False,count=1))
    return rehash(dict(schema='skin-source-snapshot-v1',scene_sha256='f'*64,rig=rig,rig_object_basis=np.eye(4).tolist(),bone_channels=raw,
        deform_bones=[dict(use_deform=True,use_envelope_multiply=False) for _ in range(bones)],mesh=mesh,audit=copy.deepcopy(rig['audit'])))


class SkinSourceTests(unittest.TestCase):
    def validate(self,v,**kw):return s.validate(v,deadline_ns=time.perf_counter_ns()+2_000_000_000,**kw)
    def analyze(self,v):return s.analyze(v,deadline_ns=time.perf_counter_ns()+2_000_000_000)
    def test_linear_blend_can_collapse_with_rigid_bones_and_valid_source(self):
        v=packet();out=self.analyze(v);self.assertEqual(out['correspondence'],'current_same_index_with_independent_LBS_replay')
        self.assertGreater(out['max_current_displacement_m'],.3)
        self.assertTrue(all(abs(v[0])+abs(v[2])<1e-12 for v in v['mesh']['evaluated_vertices']))
        self.assertEqual(out['damage_classification'],'not_inferred');self.assertIn('surface_stretch_or_collapse',out['not_checked'])
    def test_unweighted_is_partial_and_intent_unknown(self):
        out=self.analyze(packet(unweighted=True));self.assertEqual(out['status'],'partial');self.assertEqual(out['unweighted_vertices_total'],1)
        self.assertFalse(out['vertices'][0]['weighted']);self.assertEqual(out['vertices'][0]['vertex'],0)
    def test_same_counts_topology_do_not_prove_coordinate_correspondence(self):
        v=packet(neutral=True);v['mesh']['evaluated_vertices'][0],v['mesh']['evaluated_vertices'][1]=v['mesh']['evaluated_vertices'][1],v['mesh']['evaluated_vertices'][0];rehash(v)
        with self.assertRaisesRegex(ValueError,'same_index_LBS'):self.validate(v)
    def test_evaluated_indices_order_or_boolean_type_rejected(self):
        for mode in ('order','bool'):
            v=packet();tri=v['mesh']['evaluated_triangles'][0]
            if mode=='order':tri.reverse()
            else:tri[0]=False
            rehash(v)
            with self.assertRaisesRegex(ValueError,'topology_or_order'):self.validate(v)
    def test_equal_pose_different_weights_invalidates_cached_reference(self):
        old=packet(neutral=True);v=copy.deepcopy(old);v['mesh']['weights'][0]=[[0,.25],[1,.75]];rehash(v);self.validate(v)
        self.assertEqual(v['mesh']['evaluated_vertices'],old['mesh']['evaluated_vertices'])
        with self.assertRaisesRegex(ValueError,'stale_source'):self.validate(v,expected=old)
    def test_file_frame_instances_and_document_cannot_reuse_source(self):
        for mode in ('file','frame','epoch','mesh'):
            old=packet();v=copy.deepcopy(old)
            if mode=='file':v['scene_sha256']='e'*64
            if mode=='frame':v['rig']['payload']['frame']['number']=2
            if mode=='epoch':v['rig']['identity']['document_epoch']='e'*32
            if mode=='mesh':v['mesh']['identity']['data_instance']='99'
            rehash(v)
            with self.assertRaisesRegex(ValueError,'stale_source'):self.validate(v,expected=old)
    def test_wrong_modifier_target_refused_even_if_same_geometry(self):
        v=packet();v['mesh']['modifier']['rig_instance']='99';rehash(v)
        with self.assertRaisesRegex(ValueError,'modifier_binding'):self.validate(v)
    def test_nonunit_weights_unknown_and_nondeforming_groups_rejected(self):
        v=packet();v['mesh']['weights'][0]=[[0,.25],[1,.25]];rehash(v)
        with self.assertRaisesRegex(ValueError,'nonunit_weight_sum'):self.validate(v)
        v=packet();v['mesh']['groups'][1]='Unknown';rehash(v)
        with self.assertRaisesRegex(ValueError,'unknown_or_nondeform'):self.validate(v)
        v=packet();v['deform_bones'][1]['use_deform']=False;rehash(v)
        with self.assertRaisesRegex(ValueError,'unknown_or_nondeform'):self.validate(v)
    def test_bone_envelope_multiply_is_dependency_even_with_unchanged_pose(self):
        v=packet(neutral=True);v['deform_bones'][0]['use_envelope_multiply']=True;rehash(v)
        with self.assertRaisesRegex(ValueError,'bone_envelope_multiply'):self.validate(v)
    def test_duplicate_negative_or_boolean_weights_rejected(self):
        for ws in ([[0,.5],[0,.5]],[[0,-.5],[1,1.]],[[0,True],[1,0.]]):
            v=packet();v['mesh']['weights'][0]=ws;rehash(v)
            with self.assertRaises(ValueError):self.validate(v)
    def test_vertices_triangles_bones_and_influence_boundaries(self):
        out=self.analyze(packet(torus=True));self.assertEqual((out['vertices_total'],out['triangles_total'],out['vertices_omitted']),(128,256,112))
        self.validate(packet(bones=64));self.validate(packet(bones=8,influences=8))
        for v in (packet(count=129),packet(bones=65),packet(bones=9,influences=9)):
            with self.assertRaises(ValueError):self.validate(v)
        v=packet(torus=True);v['mesh']['triangles'].append([0,2,17]);v['mesh']['evaluated_triangles'].append([0,2,17]);rehash(v)
        with self.assertRaises(ValueError):self.validate(v)
    def test_DQ_envelopes_masks_and_future_settings_not_silently_admitted(self):
        for key,value in (('use_deform_preserve_volume',True),('use_bone_envelopes',True),('vertex_group','Mask'),('show_viewport',False),('use_multi_modifier',True),('show_render',1)):
            v=packet();v['mesh']['modifier'][key]=value;rehash(v)
            with self.assertRaisesRegex(ValueError,'unsupported_'):self.validate(v)
        v=packet();v['mesh']['modifier']['unknown_option']=True;rehash(v)
        with self.assertRaises(ValueError):self.validate(v)
    def test_shape_keys_parenting_drivers_and_nonrigid_objects_excluded(self):
        for key in ('shape_keys','object_parent','drivers','animation','linked'):
            v=packet();v['mesh']['flags'][key]=True;rehash(v)
            with self.assertRaisesRegex(ValueError,'unsupported_'):self.validate(v)
        v=packet();v['mesh']['object_matrix_world'][0][0]=2;rehash(v)
        with self.assertRaisesRegex(ValueError,'unsupported_'):self.validate(v)
    def test_original_raw_channels_and_FK_position_not_hidden_by_replay(self):
        v=packet();v['bone_channels'][0]['location'][0]=.01;rehash(v)
        with self.assertRaisesRegex(ValueError,'unsupported_skin_raw'):self.validate(v)
        v=packet();b=v['rig']['payload']['bones'][0];b['pose_matrix'][0][3]=.1;b['pose_head'][0]+=.1;b['pose_tail'][0]+=.1;rehash(v)
        with self.assertRaisesRegex(ValueError,'full_FK'):self.validate(v)
    def test_nonfinite_bytes_audit_and_original_deadline(self):
        v=packet();v['mesh']['vertices'][0][0]=float('nan')
        with self.assertRaises(ValueError):self.validate(v)
        v=packet();v['mesh']['identity']['name']='x'*r.MAX_BYTES
        with self.assertRaises(ValueError):self.validate(v)
        v=packet();v['audit']['after_sha256']='e'*64;rehash(v)
        with self.assertRaises(ValueError):self.validate(v)
        with self.assertRaises(ValueError):s.validate(packet(),deadline_ns=time.perf_counter_ns()-1)
        for blob in (b'{"a":0,"a":1}',b'{"a":Infinity}'):
            with self.assertRaises(ValueError):r.decode(blob)


class SkinTransportTests(unittest.TestCase):
    def actor(self):
        from human_eye_plugin.skin_source_process import SkinSourceProcess
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve();scene=root/'fixture.blend';scene.write_bytes(b'fixture')
        actor=SkinSourceProcess.__new__(SkinSourceProcess);actor.path=root/'PROFILE.json';actor.path.write_bytes(b'{}');actor.profile_bytes=b'{}';v=packet();v['scene_sha256']=hashlib.sha256(b'fixture').hexdigest();rehash(v)
        actor.profile=dict(scene_file=str(scene),scene_sha256=v['scene_sha256'],mesh_name='Skin',rig_name='Rig',expected_frame=dict(number=1,subframe=0.))
        actor.closed=False;actor.deadline_ns=time.perf_counter_ns()+2_000_000_000;actor.sequence=0;actor._gate=threading.Lock();actor.source=None
        actor.process=SimpleNamespace(stdin=io.BytesIO());actor.template=v;actor._next=lambda:dict(kind='snapshot',id=actor.sequence,snapshot=actor.template)
        p=patch('human_eye_plugin.skin_source_process.check_source_drift',return_value={'compatible':True});p.start();self.addCleanup(p.stop);return actor,root
    def test_sixteen_reads_without_new_deadline_then_refusal(self):
        actor,_=self.actor();deadline=actor.deadline_ns
        for _ in range(16):actor.inspect()
        blob=actor.process.stdin.getvalue()
        with self.assertRaises(ValueError):actor.inspect()
        self.assertEqual(blob,actor.process.stdin.getvalue());self.assertEqual(actor.deadline_ns,deadline)
    def test_disk_profile_and_runtime_drift_stop_before_send(self):
        for mode in ('profile','scene','runtime'):
            actor,root=self.actor()
            if mode=='profile':actor.path.write_bytes(b'{ }')
            if mode=='scene':(root/'fixture.blend').write_bytes(b'changed')
            with patch('human_eye_plugin.skin_source_process.check_source_drift',return_value={'compatible':mode!='runtime'}):
                with self.assertRaises(ValueError):actor.inspect()
            self.assertEqual(actor.process.stdin.getvalue(),b'')
    def test_single_flight_expiry_reply_and_role_checks(self):
        actor,_=self.actor();actor._gate.acquire()
        with self.assertRaises(ValueError):actor.inspect()
        actor._gate.release();actor.deadline_ns=time.perf_counter_ns()-1
        with self.assertRaises(ValueError):actor.inspect()
        for reply in (True,99):
            actor,_=self.actor();actor._next=lambda:dict(kind='snapshot',id=reply,snapshot=actor.template)
            with self.assertRaises(ValueError):actor.inspect()
        actor,_=self.actor();actor.profile['mesh_name']='Other'
        with self.assertRaises(ValueError):actor.inspect()
    def test_worker_has_no_RNA_write_or_temp_mesh_allocation(self):
        from human_eye_plugin import skin_source_worker
        tree=ast.parse(Path(skin_source_worker.__file__).read_text());stores=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store)]
        self.assertEqual(stores,['sys.dont_write_bytecode','package.__path__'])
        self.assertFalse({n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}&{'to_mesh','to_mesh_clear','frame_set','save_as_mainfile','mode_set','driver_add','keyframe_insert','from_pydata'})


if __name__=='__main__':unittest.main()
