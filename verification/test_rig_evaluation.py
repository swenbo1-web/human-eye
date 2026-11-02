"""Independent protocol, dependency and solved-vs-control semantic checks."""
import ast,copy,math,unittest
from pathlib import Path
from verification import rig_evaluation_contract as e
r=e.r


def rotation(degrees):
    a=math.radians(degrees);c=math.cos(a);s=math.sin(a)
    return [[c,-s,0.,0.],[s,c,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def rehash(packet):
    packet['audit']=dict(before_sha256=r.digest(packet['inputs']),after_sha256=r.digest(packet['inputs']))
    packet['source_sha256']=r.digest({k:v for k,v in packet.items() if k!='source_sha256'});return packet


def packet():
    rid=dict(name='Rig',type='Object',instance='1',library=None);tid=dict(name='Target',type='Object',instance='2',library=None)
    constraint=dict(type='COPY_ROTATION',is_valid=True,settings=dict(target=tid,subtarget='',mute=False,influence=1.,
        owner_space='WORLD',target_space='WORLD',mix_mode='REPLACE',use_x=True,use_y=True,use_z=True,invert_x=False,invert_y=False,invert_z=False))
    rest=dict(name='Bone',parent=None,matrix=rotation(0),head=[0.,0.,0.],tail=[0.,1.,0.],length=1.,
        inherit_rotation=True,inherit_scale='FULL',local_location=True,connected=False,bbone_segments=1)
    channel=dict(name='Bone',basis=rotation(20),constraints=[constraint])
    def obj(ident,kind):return dict(id=ident,type=kind,parent=None,matrix_world=rotation(0),matrix_basis=rotation(0),
        matrix_parent_inverse=rotation(0),animation=None,constraints=[],properties={})
    rig=obj(rid,'ARMATURE');rig.update(bones=[rest],channels=[channel],pose_position='POSE',data_animation=None)
    target=obj(tid,'EMPTY');target['matrix_world']=rotation(65)
    inputs=dict(frame=dict(number=1,subframe=0.),objects=[rig,target])
    pose=dict(name='Bone',parent=None,matrix=rotation(65),head=[0.,0.,0.],tail=[-math.sin(math.radians(65)),math.cos(math.radians(65)),0.])
    evaluated=[dict(id=rid,matrix_world=rotation(0),bones=[pose]),dict(id=tid,matrix_world=rotation(65))]
    return rehash(dict(schema=e.SCHEMA,document_epoch='a'*32,inputs=inputs,evaluated=evaluated,geometry_setters=0,
        original_file_saved=False,product_support=False))


class RigEvaluationTests(unittest.TestCase):
    def test_solved_orientation_is_not_input_basis(self):
        v=packet();result=e.copy_candidate(v)
        self.assertTrue(result['eligible']);self.assertFalse(result['product_support'])
        self.assertAlmostEqual(result['input_channel']['rotation_deg'],20)
        self.assertAlmostEqual(result['evaluated_local']['rotation_deg'],65)
        self.assertEqual(result['damage_classification'],'not_inferred')
    def test_dependency_without_output_change_invalidates_old_evidence(self):
        old=packet();new=copy.deepcopy(old);new['inputs']['objects'][1]['properties']['source_only']=1.;rehash(new)
        self.assertEqual(old['evaluated'],new['evaluated']);self.assertNotEqual(old['source_sha256'],new['source_sha256'])
        with self.assertRaisesRegex(ValueError,'probe_stale_evidence'):e.validate(new,expected=old)
    def test_missing_target_cannot_be_omitted_from_closure(self):
        v=packet();v['inputs']['objects'].pop();v['evaluated'].pop();rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_missing_dependency'):e.validate(v)
    def test_same_name_other_target_instance_is_not_same_source(self):
        old=packet();v=copy.deepcopy(old);v['document_epoch']='b'*32;rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_stale_evidence'):e.validate(v,expected=old)
        v=packet();v['inputs']['objects'][0]['channels'][0]['constraints'][0]['settings']['target']=dict(v['inputs']['objects'][1]['id'],instance='99');rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_missing_dependency'):e.validate(v)
    def test_omitted_bone_and_wrong_evaluated_parent_refused(self):
        v=packet();v['evaluated'][0]['bones']=[];rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_bone_correspondence'):e.validate(v)
        v=packet();v['evaluated'][0]['bones'][0]['parent']='absent';rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_evaluated_parent'):e.validate(v)
    def test_cycle_is_not_parent_cancellation(self):
        v=packet();v['inputs']['objects'][0]['bones'][0]['parent']='Bone';v['evaluated'][0]['bones'][0]['parent']='Bone';rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_parent_cycle'):e.validate(v)
    def test_endpoint_matrix_disagreement_refused_even_with_rehash(self):
        v=packet();v['evaluated'][0]['bones'][0]['tail'][0]+=.01;rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_endpoint_matrix'):e.validate(v)
    def test_changed_frame_cannot_reuse_previous_packet(self):
        old=packet();v=copy.deepcopy(old);v['inputs']['frame']['number']=2;rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_stale_evidence'):e.validate(v,expected=old)
        v['inputs']['frame']['number']=True;rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_frame'):e.validate(v)
    def test_mutation_and_audit_mismatch_refused(self):
        v=packet();v['inputs']['objects'][1]['properties']['x']=1
        with self.assertRaisesRegex(ValueError,'probe_source_digest'):e.validate(v)
        v=packet();v['audit']['after_sha256']='0'*64
        v['source_sha256']=r.digest({k:x for k,x in v.items() if k!='source_sha256'})
        with self.assertRaisesRegex(ValueError,'probe_input_audit'):e.validate(v)
    def test_ik_is_not_admitted_by_merely_using_evaluated_matrices(self):
        v=packet();v['inputs']['objects'][0]['channels'][0]['constraints'][0]['type']='IK';rehash(v)
        self.assertIn('constraint_type',e.copy_candidate(v)['reasons'])
    def test_partial_muted_or_nonboolean_status_excluded(self):
        for key,value in (('influence',.5),('influence',True),('mute',True),('mute',0)):
            v=packet();v['inputs']['objects'][0]['channels'][0]['constraints'][0]['settings'][key]=value;rehash(v)
            self.assertIn('inactive_or_partial',e.copy_candidate(v)['reasons'])
        v=packet();v['inputs']['objects'][0]['channels'][0]['constraints'][0]['is_valid']=1;rehash(v)
        self.assertFalse(e.copy_candidate(v)['eligible'])
    def test_spaces_axes_and_mix_require_new_semantics(self):
        for key,value in (('owner_space','LOCAL'),('mix_mode','OFFSET'),('use_z',False),('invert_z',True)):
            v=packet();v['inputs']['objects'][0]['channels'][0]['constraints'][0]['settings'][key]=value;rehash(v)
            self.assertFalse(e.copy_candidate(v)['eligible'])
    def test_constraint_order_count_not_silently_ignored(self):
        v=packet();cs=v['inputs']['objects'][0]['channels'][0]['constraints'];cs.append(copy.deepcopy(cs[0]));rehash(v)
        self.assertIn('one_pose_constraint_required',e.copy_candidate(v)['reasons'])
    def test_target_animation_and_driver_remain_outside_static_domain(self):
        for ad in (dict(drivers=[],curves=[dict()]),dict(drivers=[dict(driver=dict(variables=[]))],curves=[])):
            v=packet();v['inputs']['objects'][1]['animation']=ad;rehash(v)
            self.assertIn('animation_or_driver',e.copy_candidate(v)['reasons'])
    def test_nonrigid_target_not_interpreted_as_rigid_rotation(self):
        v=packet();v['inputs']['objects'][1]['matrix_world'][2][2]=2.;rehash(v)
        self.assertIn('nonrigid_object',e.copy_candidate(v)['reasons'])
    def test_output_cannot_claim_product_or_write_authority(self):
        for key,value in (('product_support',True),('geometry_setters',True),('geometry_setters',1),('original_file_saved',True)):
            v=packet();v[key]=value;rehash(v)
            with self.assertRaisesRegex(ValueError,'probe_no_authority'):e.validate(v)
    def test_oversized_and_nonfinite_source_refused(self):
        v=packet();v['inputs']['objects'][1]['properties']['padding']='x'*e.MAX_BYTES;rehash(v)
        with self.assertRaisesRegex(ValueError,'probe_size_epoch'):e.validate(v)
        v=packet();v['inputs']['objects'][1]['matrix_world'][0][0]=float('nan')
        with self.assertRaises(ValueError):e.validate(v)
    def test_probe_contains_no_RNA_write_or_save_api(self):
        tree=ast.parse(Path(e.__file__).read_text(encoding='utf8'))
        calls=[ast.unparse(v.func) for v in ast.walk(tree) if isinstance(v,ast.Call)]
        for name in calls:
            self.assertNotIn(name,('setattr','delattr'));self.assertFalse(name.startswith('bpy.ops.'))
            self.assertNotIn(name.rsplit('.',1)[-1],('frame_set','driver_add','keyframe_insert','save_as_mainfile','mode_set'))
        self.assertFalse(any(isinstance(v,(ast.Assign,ast.AugAssign,ast.AnnAssign)) and
            any(isinstance(t,ast.Attribute) for t in (v.targets if isinstance(v,ast.Assign) else [v.target])) for v in ast.walk(tree)))


if __name__=='__main__':unittest.main()
