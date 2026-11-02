"""Reproducible M4-A2 factory assets, read-only native capture and independent truth.

--builder is the only Blender writer, restricted to a new verification folder.
--capture only observes the already loaded file; it has no pose/frame/save command.
--controller runs fixed capture subprocesses with 30s whole-case timeouts.
"""
import argparse,hashlib,json,math,subprocess,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from verification import rig_evaluation_contract as e
r=e.r


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def builder(args):
    import bpy
    r.require(bpy.app.background and args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes'),
        'owned_builder_output')
    args.output.mkdir(exist_ok=False);rows=[]
    copy_names=['cr_zero','cr_target65','cr_target_minus40','cr_parent30','cr_world20_parent30','cr_roll30','cr_frame12',
        'cr_same_output_dependency','cr_partial','cr_muted','cr_local_space','cr_offset_mix','cr_axis_off','cr_invert',
        'cr_missing','cr_nonuniform_target','cr_nonuniform_rig','cr_parented_target','cr_bone_target','cr_two_constraints',
        'cr_target_animation_f1','cr_target_animation_f6','cr_target_animation_f11','cr_target_driver_a','cr_target_driver_b',
        'cr_rig_driver','cr_same_names_rebuilt']
    ik_names=['ik_reach_right','ik_reach_left','ik_reach_middle','ik_opposite_pole','ik_unreachable','ik_full_extension',
        'ik_zero_distance','ik_near_zero','ik_collinear_pole','ik_stretch','ik_one_link']
    admitted=set(copy_names[:8]+['cr_same_names_rebuilt'])
    if args.bent_extension:
        copy_names=[];ik_names=['ik_bent_right','ik_bent_left','ik_bent_middle','ik_bent_opposite_pole',
            'ik_bent_unreachable','ik_bent_full_extension','ik_straight_no_pole']
    for name in copy_names+ik_names:
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');obj=bpy.data.objects.new('Rig',data);scene.collection.objects.link(obj)
        target=bpy.data.objects.new('Target',None);scene.collection.objects.link(target)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        root=data.edit_bones.new('Root');root.head=(0,0,0);root.tail=(0,1,0)
        tip=data.edit_bones.new('Tip');tip.head=(0,1,0);tip.tail=(0,2,0);tip.parent=root;tip.use_connect=True
        if name.startswith('ik_bent_'):tip.tail=(math.sin(math.radians(12)),1+math.cos(math.radians(12)),0)
        roll=30. if name=='cr_roll30' else 0.;tip.roll=math.radians(roll)
        bpy.ops.object.mode_set(mode='OBJECT');root=obj.pose.bones['Root'];tip=obj.pose.bones['Tip']
        root.rotation_mode='XYZ';tip.rotation_mode='XYZ';obj.rotation_mode='XYZ';target.rotation_mode='XYZ'
        oracle=dict(family='copy' if name in copy_names else 'ik',eligible=name in admitted,frame=dict(number=1,subframe=0.),
            input_tip_deg=20.,parent_deg=0.,rig_deg=0.,target_deg=65.,rest_roll_deg=roll,
            truth='authored angles and analytic reach constraints, independent of candidate output')
        if name in copy_names:
            tip.rotation_euler.z=math.radians(20);target.rotation_euler.z=math.radians(65)
            if name=='cr_zero':oracle['target_deg']=0.;target.rotation_euler.z=0
            if name=='cr_target_minus40':oracle['target_deg']=-40.;target.rotation_euler.z=math.radians(-40)
            if name in ('cr_parent30','cr_world20_parent30'):oracle['parent_deg']=30.;root.rotation_euler.z=math.radians(30)
            if name=='cr_world20_parent30':oracle['rig_deg']=20.;obj.rotation_euler.z=math.radians(20)
            if name=='cr_same_output_dependency':target['unrelated_registered_source']=1.
            c=tip.constraints.new('COPY_ROTATION');c.target=target;c.owner_space='WORLD';c.target_space='WORLD';c.mix_mode='REPLACE'
            if name=='cr_partial':c.influence=.5
            if name=='cr_muted':c.mute=True
            if name=='cr_local_space':c.owner_space='LOCAL'
            if name=='cr_offset_mix':c.mix_mode='OFFSET'
            if name=='cr_axis_off':c.use_z=False
            if name=='cr_invert':c.invert_z=True
            if name=='cr_missing':c.target=None
            if name=='cr_nonuniform_target':target.scale=(2,1,.5)
            if name=='cr_nonuniform_rig':obj.scale=(2,1,.5)
            if name=='cr_parented_target':
                parent=bpy.data.objects.new('TargetParent',None);scene.collection.objects.link(parent);target.parent=parent
            if name=='cr_bone_target':c.target=obj;c.subtarget='Root'
            if name=='cr_two_constraints':
                c2=tip.constraints.new('LIMIT_ROTATION');c2.use_limit_z=True;c2.min_z=-.2;c2.max_z=.2
            if name.startswith('cr_target_animation'):
                for frame,deg in ((1,10.),(11,70.)):
                    target.rotation_euler.z=math.radians(deg);target.keyframe_insert(data_path='rotation_euler',index=2,frame=frame)
                for fc in e.curves(target.animation_data.action):
                    for p in fc.keyframe_points:p.interpolation='LINEAR'
                frame=int(name.rsplit('f',1)[1]);oracle['frame']['number']=frame;oracle['target_deg']=10.+(frame-1)*6
                scene.frame_set(frame)
            if name in ('cr_target_driver_a','cr_target_driver_b','cr_rig_driver'):
                target['angle']=.3 if name!='cr_target_driver_b' else .7
                owner=root if name=='cr_rig_driver' else target
                fc=owner.driver_add('rotation_euler',2);driver=fc.driver;driver.type='SCRIPTED';driver.expression='angle'
                var=driver.variables.new();var.name='angle';var.type='SINGLE_PROP';var.targets[0].id=target;var.targets[0].data_path='["angle"]'
                if name=='cr_rig_driver':oracle['parent_deg']=math.degrees(.3)
                else:oracle['target_deg']=math.degrees(target['angle'])
            if name=='cr_frame12':scene.frame_set(12,subframe=.25);oracle['frame']=dict(number=12,subframe=.25)
        else:
            oracle['input_tip_deg']=0.;target.location=(1,1,0)
            if name in ('ik_reach_left','ik_bent_left'):target.location=(-1,1,0)
            if name in ('ik_reach_middle','ik_bent_middle'):target.location=(.2,1.4,0)
            if name in ('ik_unreachable','ik_stretch','ik_bent_unreachable'):target.location=(0,3,0)
            if name in ('ik_full_extension','ik_bent_full_extension'):target.location=(0,2,0)
            if name=='ik_zero_distance':target.location=(0,0,0)
            if name=='ik_near_zero':target.location=(1e-7,0,0)
            pole=bpy.data.objects.new('Pole',None);scene.collection.objects.link(pole);pole.location=(2,0,0)
            if name in ('ik_opposite_pole','ik_bent_opposite_pole'):pole.location=(-2,0,0)
            if name=='ik_collinear_pole':pole.location=(2,2,0)
            c=tip.constraints.new('IK');c.target=target;c.pole_target=pole;c.chain_count=1 if name=='ik_one_link' else 2
            if name=='ik_straight_no_pole':c.pole_target=None
            c.use_stretch=name=='ik_stretch';c.iterations=500
            oracle.update(target=list(target.location),pole=list(pole.location),lengths=[1.,1.],
                rest_tip_bend_deg=12. if name.startswith('ik_bent_') else 0.,
                endpoint_truth=name not in ('ik_zero_distance','ik_near_zero','ik_collinear_pole','ik_stretch','ik_one_link'),
                orientation_truth=False,ambiguous=name in ('ik_full_extension','ik_bent_full_extension','ik_zero_distance','ik_near_zero','ik_collinear_pole'))
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        # Confirm persisted actual controls/modes and constraint settings, not just setter intent.
        bpy.ops.wm.open_mainfile(filepath=str(path));obj=bpy.context.scene.objects['Rig'];target=bpy.context.scene.objects['Target']
        assert obj.pose.bones['Root'].rotation_mode==obj.pose.bones['Tip'].rotation_mode=='XYZ'
        assert dict(number=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe)==oracle['frame']
        oracle['persisted_tip_channel_z']=float(obj.pose.bones['Tip'].rotation_euler.z)
        oracle['persisted_target_z']=float(target.rotation_euler.z)
        save(folder/'ORACLE.json',oracle);rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),oracle=oracle))
    save(args.output/'CASES.json',dict(rows=rows));print(json.dumps(dict(built=len(rows))))


def outside_observer(bpy):
    """Separate explicit observer, not the probe's serialized input implementation."""
    graph=bpy.context.evaluated_depsgraph_get();rows=[]
    for obj in sorted(bpy.context.scene.objects,key=lambda v:v.name):
        ev=obj.evaluated_get(graph)
        row=dict(name=obj.name,world=e.mat(obj.matrix_world),evaluated_world=e.mat(ev.matrix_world),location=list(obj.location),
            euler=list(obj.rotation_euler),quaternion=list(obj.rotation_quaternion),scale=list(obj.scale),selected=obj.select_get(),
            parent=None if obj.parent is None else obj.parent.name,properties={k:e.scalar(v) for k,v in obj.items()})
        if obj.type=='ARMATURE':
            row['rest']=[dict(name=b.name,matrix=e.mat(b.matrix_local),head=list(b.head_local),tail=list(b.tail_local),
                parent=None if b.parent is None else b.parent.name) for b in obj.data.bones]
            row['pose']=[dict(name=b.name,mode=b.rotation_mode,location=list(b.location),scale=list(b.scale),
                euler=list(b.rotation_euler),quaternion=list(b.rotation_quaternion),axis_angle=list(b.rotation_axis_angle),basis=e.mat(b.matrix_basis),
                evaluated=e.mat(ev.pose.bones[b.name].matrix),head=list(ev.pose.bones[b.name].head),tail=list(ev.pose.bones[b.name].tail),
                constraints=[dict(type=c.type,name=c.name,mute=c.mute,influence=c.influence,
                    target=None if not hasattr(c,'target') or c.target is None else c.target.name) for c in b.constraints]) for b in obj.pose.bones]
        rows.append(row)
    return dict(frame=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe,objects=rows,mode=bpy.context.mode,
        active=None if bpy.context.view_layer.objects.active is None else bpy.context.view_layer.objects.active.name)


def capture(args):
    import bpy
    assert bpy.app.background and Path(bpy.data.filepath).resolve()==args.scene.resolve() and sha(args.scene)==args.scene_sha256
    assert args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
    started=time.perf_counter_ns();deadline=started+30_000_000_000;epoch=uuid.uuid4().hex
    before=outside_observer(bpy);first=e.capture(bpy,epoch,deadline);second=e.capture(bpy,epoch,deadline);after=outside_observer(bpy)
    assert before==after and first['source_sha256']==second['source_sha256'] and sha(args.scene)==args.scene_sha256
    e.validate(second,expected=first);report=e.copy_candidate(second)
    save(args.output/'PACKETS.json',dict(first=first,second=second));save(args.output/'OUTSIDE_BEFORE.json',before)
    save(args.output/'OUTSIDE_AFTER.json',after);save(args.output/'REPORT.json',report)
    save(args.output/'CAPTURE.json',dict(identical=True,scene_sha256=args.scene_sha256,process_elapsed_ns=time.perf_counter_ns()-started,
        binary=bpy.app.binary_path,blender_version=bpy.app.version_string,geometry_setters=0,original_file_saved=False,
        prototype_only=True,shared_GUI=False))
    print(json.dumps(dict(captured=True,eligible=report['eligible'])))


def rotation(axis,degrees):
    import numpy as np
    a=math.radians(degrees);c=math.cos(a);s=math.sin(a);v=np.eye(3);i,j={'Y':(2,0),'Z':(0,1)}[axis]
    v[i,i]=v[j,j]=c;v[i,j]=-s;v[j,i]=s;return v


def controller(args):
    import numpy as np
    args.output.mkdir(exist_ok=False);rows=[];binary=Path('D:/Tools/blender5.2/blender.exe');script=Path(__file__).resolve()
    pins={str(p):sha(p) for p in (binary,script,Path(e.__file__),Path(r.__file__))}
    source_folder=args.output/'SOURCES';source_folder.mkdir()
    for path in (script,Path(e.__file__),Path(r.__file__)):(source_folder/path.name).write_bytes(path.read_bytes())
    for case in json.loads((args.fixtures/'CASES.json').read_bytes())['rows']:
        folder=args.output/case['name'];started=time.perf_counter_ns()
        response=subprocess.run([str(binary),'--factory-startup','--disable-autoexec','--background',case['scene'],
            '--python-exit-code','11','--python',str(script),'--','--capture','--scene',case['scene'],'--scene-sha256',case['scene_sha256'],
            '--output',str(folder)],capture_output=True,timeout=30,check=False)
        r.require(len(response.stdout)+len(response.stderr)<=512*1024,'capture_stdio_budget')
        if not folder.exists():folder.mkdir()
        (folder/'STDOUT.txt').write_bytes(response.stdout);(folder/'STDERR.txt').write_bytes(response.stderr)
        assert response.returncode==0,(case['name'],response.returncode,response.stdout[-1200:],response.stderr[-1200:])
        packets=json.loads((folder/'PACKETS.json').read_bytes());packet=packets['second'];e.validate(packet,expected=packets['first'])
        report=json.loads((folder/'REPORT.json').read_bytes());oracle=case['oracle']
        assert report['eligible']==oracle['eligible'],(case['name'],report)
        assert packet['inputs']['frame']==oracle['frame']
        rig=next(v for v in packet['inputs']['objects'] if v['type']=='ARMATURE');channels={b['name']:b for b in rig['channels']}
        poses={b['name']:b for row in packet['evaluated'] if row['id']==rig['id'] for b in row['bones']}
        assert abs(channels['Tip']['euler'][2]-math.radians(oracle['input_tip_deg']))<2e-6
        checks=dict(eligibility=True,input_mode=True,unchanged_file=sha(Path(case['scene']))==case['scene_sha256'])
        if oracle['family']=='copy':
            if oracle['eligible'] or 'animation' in case['name'] or 'driver' in case['name']:
                expected_world=rotation('Z',oracle['target_deg']-oracle['rig_deg'])
                assert np.max(np.abs(np.array(poses['Tip']['matrix'])[:3,:3]-expected_world))<2e-5,(case['name'],'evaluated world angle')
                assert abs(channels['Root']['euler'][2]-math.radians(oracle['parent_deg']))<2e-6
                if oracle['eligible']:
                    expected=rotation('Y',-oracle['rest_roll_deg'])@rotation('Z',oracle['target_deg']-oracle['rig_deg']-oracle['parent_deg'])
                    assert np.max(np.abs(np.array(report['evaluated_delta'])[:3,:3]-expected))<2e-5,(case['name'],'independent local matrix')
                    assert abs(report['input_channel']['rotation_deg']-20.)<.001
                checks['independent_rotation_truth']=True
        else:
            head=np.array(poses['Root']['head']);joint=np.array(poses['Root']['tail']);tip_head=np.array(poses['Tip']['head']);end=np.array(poses['Tip']['tail'])
            target=np.array(oracle['target']);distance=float(np.linalg.norm(target));checks.update(target_distance=distance,
                actual_endpoint=end.tolist(),endpoint_error=float(np.linalg.norm(end-target)),orientation_truth=False,ambiguous=oracle['ambiguous'])
            if oracle['endpoint_truth']:
                expected=target*min(1.,2./distance)
                checks['root_and_connectivity_truth']=bool(np.linalg.norm(head)<2e-4 and np.linalg.norm(tip_head-joint)<2e-4)
                checks['segment_length_truth']=bool(abs(np.linalg.norm(joint-head)-1)<2e-4 and abs(np.linalg.norm(end-joint)-1)<2e-4)
                checks['analytic_endpoint_truth']=bool(np.linalg.norm(end-expected)<2e-4)
                checks['analytic_expected_endpoint']=expected.tolist()
                checks['analytic_endpoint_residual']=float(np.linalg.norm(end-expected))
            assert not report['eligible']
        assert checks['unchanged_file']
        passed=all(checks.get(k,True) for k in ('root_and_connectivity_truth','segment_length_truth','analytic_endpoint_truth'))
        row=dict(case=case['name'],passed=passed,eligible=report['eligible'],checks=checks,reasons=report['reasons'],
            whole_case_elapsed_ns=time.perf_counter_ns()-started,source_sha256=packet['source_sha256'])
        save(folder/'VERDICT.json',row);rows.append(row);print(json.dumps(row),flush=True)
    assert all(sha(Path(p))==h for p,h in pins.items())
    save(args.output/'RESULT.json',dict(cases=rows,total=len(rows),eligible=sum(v['eligible'] for v in rows),pins=pins,
        oracle_failures=[v['case'] for v in rows if not v['passed']],
        prototype_only=True,formal_model_trials=0,product_runtime_changed=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    for name in ('builder','capture','controller'):mode.add_argument('--'+name,action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--fixtures',type=Path)
    parser.add_argument('--scene',type=Path);parser.add_argument('--scene-sha256');parser.add_argument('--bent-extension',action='store_true')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=parser.parse_args(argv)
    builder(args) if args.builder else capture(args) if args.capture else controller(args)
