"""Owned constraint fixtures and independent NumPy matrix acceptance."""
import argparse,hashlib,importlib.util,json,math,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def builder(args):
    import bpy
    from mathutils import Euler
    assert bpy.app.background and args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes')
    args.output.mkdir(exist_ok=False);rows=[]
    positive=['target_x','target_y','target_z','target_combo','parent_combo','world_parent_combo','rolled_rest','root_constraint',
        'descendant','limit64','quaternion_negative','subframe','millimetres','object_translation','singular_swing']
    negative=['partial','muted','disabled','axis_off','inverted','offset','local_space','euler_order','missing_target','two_constraints',
        'target_constraint','object_constraint','target_parent','rig_parent','target_scale','rig_scale','bone_scale','bone_translation',
        'inheritance','B_bone','animation','driver','target_animation','target_driver','REST','IK','limit65','objects33']
    for name in positive+negative:
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');obj=bpy.data.objects.new('Rig',data);scene.collection.objects.link(obj)
        target=bpy.data.objects.new('Target',None);scene.collection.objects.link(target)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        count=64 if name=='limit64' else 65 if name=='limit65' else 3 if name=='descendant' else 2
        owner=0 if name=='root_constraint' else 31 if name=='limit64' else 1
        rolls=[30. if name=='rolled_rest' and i==owner else 0. for i in range(count)]
        for i in range(count):
            bone=data.edit_bones.new('bone_%03d'%i);bone.head=(0,i,0);bone.tail=(0,i+1,0);bone.roll=math.radians(rolls[i])
            if i:bone.parent=data.edit_bones['bone_%03d'%(i-1)];bone.use_connect=True
        bpy.ops.object.mode_set(mode='OBJECT');obj.rotation_mode='XYZ';target.rotation_mode='XYZ'
        inputs=[[0.,0.,0.] for _ in range(count)];inputs[owner]=[0.,0.,20.]
        if name in ('parent_combo','world_parent_combo'):inputs[0]=[25.,15.,-35.]
        if name=='descendant':inputs[2]=[15.,0.,0.]
        for i,values in enumerate(inputs):
            b=obj.pose.bones['bone_%03d'%i];b.rotation_mode='XYZ';b.rotation_euler=[math.radians(v) for v in values]
        angles=[65.,0.,0.] if name=='target_x' else [0.,95.,0.] if name=='target_y' else [0.,0.,65.] if name=='target_z' else [180.,0.,0.] if name=='singular_swing' else [35.,-50.,70.]
        target.rotation_euler=[math.radians(v) for v in angles];world=[20.,-10.,40.] if name=='world_parent_combo' else [0.,0.,0.]
        obj.rotation_euler=[math.radians(v) for v in world]
        if name=='object_translation':obj.location=(3,4,5);target.location=(-7,4,8)
        if name=='quaternion_negative':
            target.rotation_mode='QUATERNION';target.rotation_quaternion=[-v for v in Euler([math.radians(v) for v in angles],'XYZ').to_quaternion()]
        b=obj.pose.bones['bone_%03d'%owner];c=b.constraints.new('IK' if name=='IK' else 'COPY_ROTATION');c.target=target
        if name!='IK':c.owner_space='WORLD';c.target_space='WORLD';c.mix_mode='REPLACE'
        if name=='partial':c.influence=.5
        if name=='muted':c.mute=True
        if name=='disabled':c.enabled=False
        if name=='axis_off':c.use_z=False
        if name=='inverted':c.invert_x=True
        if name=='offset':c.use_offset=True
        if name=='local_space':c.owner_space='LOCAL'
        if name=='euler_order':c.euler_order='ZYX'
        if name=='missing_target':c.target=None
        if name=='two_constraints':b.constraints.new('LIMIT_ROTATION')
        if name=='target_constraint':target.constraints.new('LIMIT_ROTATION')
        if name=='object_constraint':obj.constraints.new('LIMIT_ROTATION')
        if name in ('target_parent','rig_parent'):
            parent=bpy.data.objects.new('Parent',None);scene.collection.objects.link(parent)
            (target if name=='target_parent' else obj).parent=parent
        if name=='target_scale':target.scale=(2,1,.5)
        if name=='rig_scale':obj.scale=(2,1,.5)
        if name=='bone_scale':b.scale=(1,2,1)
        if name=='bone_translation':b.location.y=.001
        if name=='inheritance':data.bones[b.name].inherit_scale='NONE'
        if name=='B_bone':data.bones[b.name].bbone_segments=4
        if name in ('animation','target_animation'):(b if name=='animation' else target).keyframe_insert(data_path='rotation_euler',frame=1)
        if name in ('driver','target_driver'):(b if name=='driver' else target).driver_add('rotation_euler',1).driver.expression='0.2'
        if name=='REST':data.pose_position='REST'
        if name=='objects33':
            for i in range(31):scene.collection.objects.link(bpy.data.objects.new('extra_%02d'%i,None))
        if name=='subframe':scene.frame_set(12,subframe=.25)
        if name=='millimetres':scene.unit_settings.scale_length=.001
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True);bpy.ops.wm.open_mainfile(filepath=str(path))
        assert all(v.rotation_mode=='XYZ' for v in bpy.context.scene.objects['Rig'].pose.bones)
        oracle=dict(supported=name in positive,bones=count,owner=owner,rolls=rolls,inputs_deg=inputs,target_deg=angles,
            object_deg=world,object_location=[3.,4.,5.] if name=='object_translation' else [0.,0.,0.],
            frame=dict(number=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe),unit=.001 if name=='millimetres' else 1.,
            truth='authored independent rest and Euler composition, never candidate angle output')
        save(folder/'ORACLE.json',oracle);rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),oracle=oracle))
    save(args.output/'CASES.json',dict(rows=rows));print(json.dumps(dict(built=len(rows))))


def rotation(values):
    import numpy as np
    result=np.eye(4)
    for axis,deg in enumerate(values):
        a=math.radians(deg);c=math.cos(a);s=math.sin(a);m=np.eye(4);i,j=((1,2),(2,0),(0,1))[axis]
        m[i,i]=m[j,j]=c;m[i,j]=-s;m[j,i]=s;result=m@result
    return result


def oracle_matrices(o):
    import numpy as np
    rest=[];poses=[];world=rotation(o['object_deg']);world[:3,3]=o['object_location'];target=rotation(o['target_deg'])
    for i in range(o['bones']):
        rm=rotation([0,o['rolls'][i],0]);rm[1,3]=i;basis=rotation(o['inputs_deg'][i])
        pm=rm@basis if not i else poses[-1]@np.linalg.inv(rest[-1])@rm@basis
        if i==o['owner']:pm[:3,:3]=world[:3,:3].T@target[:3,:3]
        rest.append(rm);poses.append(pm)
    return rest,poses,world


def controller(args):
    import numpy as np
    sys.path.insert(0,str(args.core_root))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_constraint_fixed_target',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
        assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin import rig_constraint as core
    from human_eye_plugin.rig_constraint_process import RigConstraintProcess
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity();r=core.r;args.output.mkdir(exist_ok=False);binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary);rows=[]
    for case in json.loads((args.fixtures/'CASES.json').read_bytes())['rows']:
        folder=args.output/case['name'];folder.mkdir();o=case['oracle']
        profile=dict(schema='rig-constraint-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],object_name='Rig',target_name='Target',constraint_bone='bone_%03d'%o['owner'],
            expected_frame=o['frame'],runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);actor=None;report=None;first=None;second=None;error=None;started=time.perf_counter_ns()
        try:
            actor=RigConstraintProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();report=core.analyze(second,deadline_ns=actor.deadline_ns)
        except Exception as exc:error=str(exc)
        finally:
            if actor is not None:actor.close()
        if o['supported']:
            assert report is not None,(case['name'],error)
            rest,poses,world=oracle_matrices(o)
            for i,b in enumerate(second['rig']['payload']['bones']):
                assert np.max(np.abs(np.array(b['rest_matrix'])-rest[i]))<2e-5,(case['name'],i,'rest')
                assert np.max(np.abs(np.array(b['pose_matrix'])-poses[i]))<6e-5,(case['name'],i,'pose',b['pose_matrix'],poses[i].tolist())
            for fact in report['bones']:
                i=int(fact['bone'].split('_')[1]);basis=rotation(o['inputs_deg'][i]);expected_angle=math.degrees(math.acos(max(-1.,min(1.,(np.trace(basis[:3,:3])-1)/2))))
                assert abs(fact['input_channel']['rotation_deg']-expected_angle)<.001
                relative=np.linalg.inv(rest[i])@poses[i] if not i else np.linalg.inv(np.linalg.inv(rest[i-1])@rest[i])@np.linalg.inv(poses[i-1])@poses[i]
                expected_angle=math.degrees(math.acos(float(np.clip((np.trace(relative[:3,:3])-1)/2,-1,1))))
                swing=math.degrees(math.acos(float(np.clip(relative[1,1],-1,1))))
                twist=math.degrees(math.atan2(relative[0,2]-relative[2,0],relative[0,0]+relative[2,2]))
                actual=fact['evaluated_local'];assert abs(actual['rotation_deg']-expected_angle)<.001 and abs(actual['swing_deg']-swing)<.001
                if swing>=179.999 or abs(abs(twist)-180)<=.001:assert actual['twist_deg'] is None
                else:assert actual['twist_deg'] is not None and abs(actual['twist_deg']-twist)<.001,(case['name'],fact,'twist truth',twist)
                endpoint=(world@poses[i]@np.array([0.,1.,0.,1.]))[:3]*o['unit']
                assert np.max(np.abs(endpoint-np.array(fact['world_tail_m'])))<2e-5
            assert report['bones_total']==o['bones'] and report['bones_omitted']==max(0,o['bones']-16)
            assert report['bones'][0]['constrained'] and report['geometry_setters']==0 and not report['original_file_saved']
            assert report['assessment']=='unassessed_no_rules' and report['damage_classification']=='not_inferred'
            assert first['source_sha256']==second['source_sha256']
        else:assert report is None and error and 'unsupported_' in error,(case['name'],report,error)
        assert sha(Path(case['scene']))==case['scene_sha256']
        row=dict(case=case['name'],supported=o['supported'],passed=True,first=first,second=second,report=report,error=error,
            elapsed_ns=time.perf_counter_ns()-started,original_file_unchanged=True)
        save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=case['name'],passed=True,supported=o['supported'])),flush=True)
    save(args.output/'RESULT.json',dict(cases=rows,total=len(rows),supported=sum(v['supported'] for v in rows),source_sha256=identity['source_sha256'],
        source_count=len(identity['source_files']),formal_model_trials=0,shared_GUI=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--core-root',type=Path,default=ROOT);p.add_argument('--entry',type=Path)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=p.parse_args(argv);builder(args) if args.builder else controller(args)
