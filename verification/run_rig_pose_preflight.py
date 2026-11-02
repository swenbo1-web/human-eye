"""Authored FK fixtures, independent angle truth and real read-only Blender QA."""
import argparse,copy,hashlib,importlib.util,json,math,os,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def builder(args):
    import bpy
    from mathutils import Quaternion
    assert bpy.app.background and args.output.resolve().is_relative_to(ROOT/'verification/fixes/20261102_m4_rig_pose')
    args.output.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_rig_fixture_schema',args.core_root/'human_eye_plugin/rig_pose.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
    names=['neutral','natural_bend','axial_twist','parent_only','rolled_rest','reflection','nonuniform_object','millimetres',
        'quaternion_positive','quaternion_negative','full_turn','singular_swing','twist_branch','angular_boundary',
        'constraint','animation','driver','inheritance','bone_scale','B_bone','subframe','limit64','limit65','wrong_policy','no_rules','object_parent','rest_display']
    rows=[]
    for name in names:
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');obj=bpy.data.objects.new('Rig',data);scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        count=64 if name=='limit64' else 65 if name=='limit65' else 2
        for i in range(count):
            bone=data.edit_bones.new('bone_%03d'%i);bone.head=(0,i,0);bone.tail=(0,i+1,0)
            if i:bone.parent=data.edit_bones['bone_%03d'%(i-1)];bone.use_connect=True
            if name=='rolled_rest':bone.roll=.7
        bpy.ops.object.mode_set(mode='OBJECT');target=obj.pose.bones['bone_%03d'%(count-1)];root=obj.pose.bones['bone_000']
        target.rotation_mode='XYZ';root.rotation_mode='XYZ';axis='Y';angle=95.;expected='violation';expected_twist=95.;expected_swing=0.
        if name in ('neutral','parent_only'):angle=0;expected='within';expected_twist=0.
        if name=='natural_bend':axis='X';angle=100;expected='within';expected_twist=0.;expected_swing=100.;root.rotation_euler.z=.6
        if name=='parent_only':root.rotation_euler.y=math.radians(120)
        if name=='rolled_rest':angle=35;expected='within';expected_twist=35.
        if name=='reflection':obj.scale=(-1,1,1);obj.location=(3,4,5);obj.rotation_euler.z=.3
        if name=='nonuniform_object':obj.scale=(2,.5,3);obj.location=(10,-20,30)
        if name=='millimetres':scene.unit_settings.scale_length=.001
        if name=='full_turn':angle=360;expected='within';expected_twist=0.
        if name=='singular_swing':axis='X';angle=180;expected='singular';expected_twist=None;expected_swing=180.
        if name=='twist_branch':angle=180;expected='branch';expected_twist=None
        if name=='angular_boundary':angle=45;expected='boundary';expected_twist=45.
        target.rotation_euler[{'X':0,'Y':1,'Z':2}[axis]]=math.radians(angle)
        if name in ('quaternion_positive','quaternion_negative'):
            target.rotation_mode='QUATERNION';q=Quaternion((0,1,0),math.radians(angle))
            target.rotation_quaternion=[-x for x in q] if name=='quaternion_negative' else q
        if name=='constraint':
            constraint=target.constraints.new('COPY_ROTATION');constraint.target=obj;constraint.subtarget='bone_000'
        if name=='animation':target.keyframe_insert(data_path='rotation_euler',frame=1)
        if name=='driver':target.driver_add('rotation_euler',1).driver.expression='0.2'
        if name=='inheritance':data.bones[target.name].inherit_scale='NONE'
        if name=='bone_scale':target.scale=(1,2,1)
        if name=='B_bone':data.bones[target.name].bbone_segments=4
        if name=='subframe':scene.frame_set(12,subframe=.25)
        if name=='object_parent':
            parent=bpy.data.objects.new('Parent',None);scene.collection.objects.link(parent);obj.parent=parent
        if name=='rest_display':data.pose_position='REST'
        if name in ('constraint','animation','driver','inheritance','bone_scale','B_bone','object_parent','rest_display'):expected='unsupported'
        if name in ('limit65','wrong_policy'):expected='unavailable'
        if name=='no_rules':expected='unassessed'
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir(exist_ok=False);path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        # Reopen our saved factory file so the rule fingerprint uses exactly
        # the persisted original rest data, not an edit-mode cache.
        bpy.ops.wm.open_mainfile(filepath=str(path));obj=bpy.context.scene.objects['Rig'];data=obj.data
        matrix=lambda v:[[float(x) for x in row] for row in v]
        bones=[dict(name=b.name,parent=b.parent.name if b.parent else None,rest_matrix=matrix(b.matrix_local),
            rest_head=list(b.head_local),rest_tail=list(b.tail_local),length=float(b.length),inherit_rotation=b.use_inherit_rotation,
            inherit_scale=b.inherit_scale,local_location=b.use_local_location,connected=b.use_connect,bbone_segments=int(b.bbone_segments)) for b in sorted(data.bones,key=lambda v:v.name)]
        fingerprint=r.rig_digest(dict(bones=bones));rule=dict(schema='rig-pose-orientation-rules-v1',rig_sha256='0'*64 if name=='wrong_policy' else fingerprint,
            provenance='authored factory orientation role; max Y twist 45 and swing 140, not human anatomy',
            rules=[dict(bone='bone_%03d'%(count-1),min_twist_deg=-45,max_twist_deg=45,max_swing_deg=140)])
        if name!='no_rules':save(folder/'POLICY.json',rule)
        target=obj.pose.bones['bone_%03d'%(count-1)];frame=dict(number=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe)
        oracle=dict(target_bone=target.name,expected=expected,twist_deg=expected_twist,swing_deg=expected_swing,
            root_rotation_deg=120. if name=='parent_only' else math.degrees(.6) if name=='natural_bend' else 0.,
            actual_root_rotation_mode=obj.pose.bones['bone_000'].rotation_mode,
            input_rotation_deg=angle,input_axis=axis,bones=count,frame=frame,world_unit_scale=bpy.context.scene.unit_settings.scale_length,
            rest_head=list(target.bone.head_local),rest_tail=list(target.bone.tail_local),
            actual_pose_head=list(target.head),actual_pose_tail=list(target.tail),rig_sha256=fingerprint,
            source_truth='independent authored rotation and direct RNA endpoints, not candidate angle output')
        save(folder/'ORACLE.json',oracle);rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),oracle=oracle,
            policy_file=None if name=='no_rules' else str(folder/'POLICY.json'),policy_sha256=None if name=='no_rules' else sha(folder/'POLICY.json')))
    save(args.output/'CASES.json',dict(rows=rows,source='new factory-owned FK scenes only'));print(json.dumps(dict(built=len(rows))))


def controller(args):
    sys.path.insert(0,str(args.core_root))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_rig_preflight_fixed',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
        assert Path(proof['module_root'])==args.core_root.resolve();identity,_=entry.verify_imported_runtime(proof)
    else:
        from human_eye_plugin.runtime_identity import runtime_identity
        identity=runtime_identity()
    from human_eye_plugin import rig_pose as r
    from human_eye_plugin.rig_pose_process import RigPoseProcess
    output=args.output;output.mkdir(exist_ok=False);rows=[];binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary)
    cases=json.loads((args.fixtures/'CASES.json').read_bytes())['rows']
    for case in cases:
        folder=output/case['name'];folder.mkdir();profile=dict(schema='rig-pose-operator-profile-v1',blender_executable=str(binary),
            blender_sha256=binary_sha,scene_file=case['scene'],scene_sha256=case['scene_sha256'],object_name='Rig',
            expected_frame=case['oracle']['frame'],runtime_source_sha256=identity['source_sha256'],
            policy_file=case['policy_file'],policy_sha256=case['policy_sha256'])
        save(folder/'PROFILE.json',profile);actor=None;error=None;first=None;second=None;report=None;started=time.perf_counter_ns()
        try:
            actor=RigPoseProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect()
            assert first['source_sha256']==second['source_sha256'] and first['audit']==second['audit']
            report=r.analyze(second,actor.policy,deadline_ns=actor.deadline_ns)
        except Exception as exc:error=str(exc)
        finally:
            if actor is not None:actor.close()
        oracle=case['oracle'];expected=oracle['expected'];facts={v['bone']:v for v in report['bones']} if report else {}
        if expected=='unavailable':assert report is None and error,(case['name'],report,error)
        else:
            assert report is not None,(case['name'],error)
            assert report['geometry_setters']==0 and report['original_file_saved'] is False
            assert report['damage_classification']=='not_inferred'
            assert report['rule_bones_total']==(0 if case['policy_file'] is None else 1)
            assert report['unruled_bones_total']==oracle['bones']-report['rule_bones_total']
            if oracle['target_bone'] in facts:assert facts[oracle['target_bone']]['rule_registered']==(case['policy_file'] is not None)
            if expected=='unsupported':assert report['status']=='unsupported' and report['unknown_rules_total']==3
            else:
                fact=facts[oracle['target_bone']]
                if 'bone_000' in facts:assert abs(facts['bone_000']['rotation_deg']-oracle['root_rotation_deg'])<r.ANGLE_GUARD_DEG,(case['name'],'root did not receive intended rotation',facts['bone_000'])
                if oracle['twist_deg'] is None:assert fact['twist_deg'] is None
                else:assert abs(fact['twist_deg']-oracle['twist_deg'])<r.ANGLE_GUARD_DEG,(case['name'],fact)
                assert abs(fact['swing_deg']-oracle['swing_deg'])<r.ANGLE_GUARD_DEG,(case['name'],fact)
                if expected=='violation':assert report['violations_total']==1 and report['violations'][0]['bone']==oracle['target_bone']
                if expected=='within':assert report['violations_total']==report['unknown_rules_total']==0
                if expected=='boundary':assert report['violations_total']==0 and report['unknown_rules_total']==1
                if expected=='singular':assert report['violations_total']==1 and report['unknown_rules_total']==2
                if expected=='branch':assert report['violations_total']==0 and report['unknown_rules_total']==2
                if expected=='unassessed':assert report['assessment']=='unassessed_no_rules' and report['rules_total']==0
        if case['name']=='axial_twist':
            assert oracle['rest_head']==oracle['actual_pose_head'] and oracle['rest_tail']==oracle['actual_pose_tail']
            assert abs(facts[oracle['target_bone']]['twist_deg']-95)<.001
        if case['name']=='parent_only':
            assert abs(facts[oracle['target_bone']]['rotation_deg'])<.001
            assert abs(facts['bone_000']['twist_deg']-120)<.001
        if case['name']=='limit64':assert report['bones_total']==64 and report['bones_omitted']==48
        assert sha(Path(case['scene']))==case['scene_sha256']
        row=dict(case=case['name'],expected=expected,report=report,error=error,first=first,second=second,
            complete_case_elapsed_ns=time.perf_counter_ns()-started,original_file_unchanged=True)
        save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=case['name'],passed=True,status=report['status'] if report else 'unavailable')),flush=True)
    # Wrong frame must be refused; the reader has no frame_set command.
    case=next(v for v in cases if v['name']=='subframe');folder=output/'wrong_frame';folder.mkdir();profile=dict(profile,
        scene_file=case['scene'],scene_sha256=case['scene_sha256'],expected_frame=dict(number=13,subframe=0.),
        policy_file=case['policy_file'],policy_sha256=case['policy_sha256'])
    save(folder/'PROFILE.json',profile);actor=RigPoseProcess(folder/'PROFILE.json')
    try:
        try:actor.inspect()
        except ValueError as exc:assert 'wrong_current_frame' in str(exc);save(folder/'RESULT.json',dict(refused=True,reason=str(exc)))
        else:raise AssertionError('reader changed current frame or accepted stale frame')
    finally:actor.close()
    assert sha(Path(case['scene']))==case['scene_sha256']
    save(output/'RESULT.json',dict(runtime_source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        cases=rows,wrong_frame_refused=True,formal_model_trials=0,images_delivered=0,shared_GUI=False))


def audit(args):
    from unittest.mock import patch
    sys.path.insert(0,str(args.core_root))
    from human_eye_plugin.rig_pose_process import RigPoseProcess
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin import rig_pose as r
    output=args.output.resolve();assert output.is_relative_to(ROOT/'verification/fixes');output.mkdir(exist_ok=False)
    identity=runtime_identity();cases=json.loads((args.fixtures/'CASES.json').read_bytes())['rows']
    binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary);real_popen=subprocess.Popen;rows=[]
    for name in ('axial_twist','parent_only','quaternion_negative','bone_scale'):
        case=next(v for v in cases if v['name']==name);folder=output/name;folder.mkdir()
        profile=dict(schema='rig-pose-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],object_name='Rig',expected_frame=case['oracle']['frame'],
            runtime_source_sha256=identity['source_sha256'],policy_file=case['policy_file'],policy_sha256=case['policy_sha256'])
        save(folder/'PROFILE.json',profile)
        def launch(command,**kw):
            command=command[:];command[command.index('--python')+1]=str(ROOT/'verification/fixtures/rig_pose_rna_audit.py')
            kw['env']=dict(os.environ,HUMAN_EYE_RIG_AUDIT_OUTPUT=str(folder));return real_popen(command,**kw)
        actor=None
        try:
            with patch('human_eye_plugin.rig_pose_process.subprocess.Popen',side_effect=launch):actor=RigPoseProcess(folder/'PROFILE.json')
            first=actor.inspect();second=actor.inspect();assert first['source_sha256']==second['source_sha256']
            report=r.analyze(second,actor.policy,deadline_ns=actor.deadline_ns)
        finally:
            if actor is not None:actor.close()
        verdict=json.loads((folder/'INDEPENDENT_RNA_RESULT.json').read_bytes());assert verdict['identical']
        assert verdict['exact_product_worker_sha256']==sha(args.core_root/'human_eye_plugin/rig_pose_worker.py')
        assert sha(Path(case['scene']))==case['scene_sha256']
        rows.append(dict(case=name,identical=True,status=report['status'],test_wrapper_used=True));print(json.dumps(rows[-1]),flush=True)
    save(output/'RESULT.json',dict(cases=rows,raw_RNA_inputs_and_derived_pose_unchanged=True,runtime_source_sha256=identity['source_sha256']))


if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--builder',action='store_true');group.add_argument('--controller',action='store_true');group.add_argument('--audit',action='store_true')
    p.add_argument('--core-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--entry',type=Path)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=p.parse_args(argv);builder(args) if args.builder else audit(args) if args.audit else controller(args)
