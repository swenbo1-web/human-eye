"""Original-author finite source QA; product code is never used as its oracle.

Factory-only scene changes are test author operations. The product transport
observes pinned files and has no frame, geometry, save or arbitrary-code command.
"""
import argparse,copy,hashlib,importlib.util,json,math,os,runpy,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'verification/fixes/20261102_m4_b3b_product'
REGISTRATION=EVIDENCE/'CASES_PREREGISTERED.json'
ORIGINAL=ROOT/'verification/fixes/20261102_m4_task_qualification/external_assets/RiggedSimple/derived_test_snapshot.blend'
HELDOUT=ROOT/'verification/fixes/20261102_m4_b3_source_qualification/heldout_frame25_r1/fixture.blend'
GLB=ORIGINAL.with_name('RiggedSimple.glb')
NEGATIVE={
    'active_nla':('unsupported','small_skin_active_nla'),
    'bezier_interval':('unknown','small_skin_curve_interpolation'),
    'driver':('unsupported','small_skin_driver'),
    'constraint':('unsupported','small_skin_constraint'),
    'DQ':('unsupported','small_skin_DQ'),
    'envelopes':('unsupported','small_skin_envelopes'),
    'nonrigid_parent':('unsupported','small_skin_nonrigid_matrix'),
    'vertices257':('unsupported','small_skin_vertex_limit'),
    'action_blend':('unsupported','small_skin_action_blend'),
}
PROFILE_NEGATIVE={
    'scene_pin':({'scene_sha256':'0'*64},'unavailable','small_skin_scene_pin'),
    'binary_pin':({'blender_sha256':'0'*64},'unavailable','small_skin_binary_pin'),
    'mesh_role':({'mesh_name':'MissingMesh'},'unsupported','small_skin_roles'),
    'rig_role':({'rig_name':'MissingRig'},'unsupported','small_skin_roles'),
    'fixed_frame':({'expected_frame':{'number':2,'subframe':0.}},'unavailable','small_skin_fixed_frame'),
    'fixed_unit':({'unit_scale_m':.001},'unavailable','small_skin_fixed_unit'),
}


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_bytes())
def curves(action):return [f for layer in action.layers for strip in layer.strips for bag in strip.channelbags for f in bag.fcurves]
def catalog():
    return dict(schema='small-source-native-preregistered-v1',normal=dict(frame1=dict(file=str(ORIGINAL),frame=1),frame25=dict(file=str(HELDOUT),frame=25)),
        missing_weights=dict(removed_vertex=0,expected_source_unweighted=[0],geometry='incident requested face unknown/unweighted_vertex_source'),
        negative={name:dict(status=status,reason=reason) for name,(status,reason) in NEGATIVE.items()},
        source_change=dict(future_key='last noncurrent location key +.125',parent_inverse='inverse*T(+.125), basis=T(-.125)*basis',
            expected_status='unavailable',expected_reason='small_skin_stale_source',current_eval_coordinates_identical=True),
        oracle='raw original GLB accessor/node/IBM/SLERP witness; complete raw packet -> independent NumPy QR/SVD for reported geometry; no production answers',
        position_atol=2e-5,metric_atol=1e-9,formal_model_trials=0,scope='one external author testing sample / two static frames; negative copies are QA derivatives, not new asset coverage')


def contract_catalog():
    return dict(schema='small-source-native-contract-preregistered-v1',
        profile_negative={name:dict(changes=changes,status=status,reason=reason) for name,(changes,status,reason) in PROFILE_NEGATIVE.items()},
        protocol=dict(expanded_deadline='small_skin_original_window',edit_command='small_skin_readonly_command',
            rejected_commands_consume_slots=True,total_slots=16,valid_reads_after_two_rejections=14,worker_exit_code=0),
        host_request_17=dict(status='unavailable',reason='small_skin_request_lifetime'),
        source_actor=dict(future_key='small_skin_stale_source',parent_inverse='small_skin_stale_source',
            expected_status='unavailable',current_coordinates_byte_equal=True,file_unchanged=True),
        no_product_setters=True,no_product_saves=True)


def actor_wrapper():
    """Explicit native test author; outside the read-only product transport."""
    import bpy
    from mathutils import Matrix
    mode=os.environ['HE_SMALL_SOURCE_FAULT_MODE'];output=Path(os.environ['HE_SMALL_SOURCE_FAULT_OUTPUT'])
    base=sys.stdout;count=[0]
    def intercept(value):
        prefix=b'HUMAN_EYE_SMALL_SKIN:'
        if isinstance(value,str):value=value.encode('utf8')
        if not value.startswith(prefix):return
        wire=json.loads(value[len(prefix):])
        if wire.get('kind')!='snapshot':return
        count[0]+=1;save(output/('ACTOR_PACKET_%02d.json'%count[0]),wire['packet'])
        if count[0]!=1:return
        if mode=='future_key':
            action=bpy.data.actions['Anim_0'];curve=next(f for f in curves(action) if f.data_path.endswith('.location') and f.array_index==0)
            key=curve.keyframe_points[-1];before=list(key.co);assert key.co.x>bpy.context.scene.frame_current+1
            key.co.y+=.125;details=dict(path=curve.data_path,index=curve.array_index,before=before,after=list(key.co),RNA_setters=1)
        elif mode=='parent_inverse':
            obj=bpy.context.scene.objects['Cylinder'];inverse=obj.matrix_parent_inverse.copy();basis=obj.matrix_basis.copy()
            obj.matrix_parent_inverse=inverse@Matrix.Translation((.125,0.,0.));obj.matrix_basis=Matrix.Translation((-.125,0.,0.))@basis
            details=dict(object=obj.name,before_inverse=[list(v) for v in inverse],after_inverse=[list(v) for v in obj.matrix_parent_inverse],
                before_basis=[list(v) for v in basis],after_basis=[list(v) for v in obj.matrix_basis],RNA_setters=2)
        else:raise ValueError('unknown_test_actor_mode')
        bpy.context.view_layer.update();save(output/'TEST_ACTOR.json',dict(mode=mode,test_actor_only=True,no_geometry_coordinates_assigned=True,
            no_file_saved=True,shared_GUI=False,details=details))
    class Buffer:
        def write(self,value):
            result=base.buffer.write(value);intercept(value);return result
        def flush(self):return base.buffer.flush()
        def __getattr__(self,name):return getattr(base.buffer,name)
    class Output:
        buffer=Buffer()
        def write(self,value):
            result=base.write(value);intercept(value);return result
        def flush(self):return base.flush()
        def __getattr__(self,name):return getattr(base,name)
    sys.stdout=Output();runpy.run_path(os.environ['HE_SMALL_SOURCE_REAL_WORKER'],run_name='__main__')


def builder(args):
    import bpy
    assert bpy.app.background and load(args.registration)==catalog()
    assert args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
    rows=[];original_sha=sha(ORIGINAL);heldout_sha=sha(HELDOUT)
    for name,path,frame in (('frame1',ORIGINAL,1),('frame25',HELDOUT,25)):
        rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),frame=frame,accepted=True,original_author_geometry=True))
    for name in ('missing_weights',*NEGATIVE):
        bpy.ops.wm.open_mainfile(filepath=str(ORIGINAL));scene=bpy.context.scene;rig=scene.objects['Armature'];obj=scene.objects['Cylinder'];mod=obj.modifiers[0]
        assert scene.frame_current==1 and scene.frame_subframe==0
        details={}
        if name=='missing_weights':
            for group in obj.vertex_groups:group.remove([0])
            details=dict(removed_vertex=0)
        elif name=='active_nla':rig.animation_data.nla_tracks[0].mute=False
        elif name=='bezier_interval':
            curve=next(f for f in curves(rig.animation_data.action) if f.data_path.endswith('.location') and f.array_index==0)
            points=curve.keyframe_points;index=next(i for i in range(len(points)-1) if points[i].co.x<1<points[i+1].co.x)
            points[index].interpolation='BEZIER';details=dict(path=curve.data_path,index=curve.array_index,interval=[points[index].co.x,points[index+1].co.x],frame=1)
        elif name=='driver':rig.driver_add('location',0).driver.expression='0.0'
        elif name=='constraint':rig.pose.bones['Bone.001'].constraints.new('LIMIT_ROTATION')
        elif name=='DQ':mod.use_deform_preserve_volume=True
        elif name=='envelopes':mod.use_bone_envelopes=True
        elif name=='nonrigid_parent':scene.objects['Z_UP'].scale.x*=1.1
        elif name=='vertices257':obj.data.vertices.add(257-len(obj.data.vertices));obj.data.update()
        elif name=='action_blend':rig.animation_data.action_blend_type='ADD'
        else:raise AssertionError(name)
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        assert path.is_file() and sha(ORIGINAL)==original_sha
        rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),frame=1,accepted=name=='missing_weights',original_author_geometry=False,
            test_actor_changes=True,details=details))
    assert sha(ORIGINAL)==original_sha and sha(HELDOUT)==heldout_sha
    save(args.output/'CASES.json',dict(schema='small-source-native-cases-v1',rows=rows,registration_sha256=sha(args.registration),builder_sha256=sha(Path(__file__)),
        untouched_original_sha256=original_sha,untouched_heldout_sha256=heldout_sha,original_author_glb_sha256=sha(GLB)))
    print(json.dumps(dict(built=len(rows),unsupported=len(NEGATIVE),original_files_unchanged=True)))


def numeric_metric(original,current):
    import numpy as np
    a=np.asarray(original,dtype=float);b=np.asarray(current,dtype=float);old=(a[1:]-a[0]).T;new=(b[1:]-b[0]).T
    _q,upper=np.linalg.qr(old,mode='reduced');gradient=np.linalg.solve(upper.T,new.T).T
    factors=np.linalg.svd(gradient,compute_uv=False)
    area=float(np.linalg.norm(np.cross(new[:,0],new[:,1]))/np.linalg.norm(np.cross(old[:,0],old[:,1])))
    return factors,area


def target_face(packet):
    """Choose from reference geometry before looking at product diagnostics."""
    import numpy as np
    mesh=packet['inputs']['mesh'];rows=[]
    for index,tri in enumerate(mesh['triangles']):
        p=np.asarray([mesh['vertices'][i] for i in tri]);s=np.linalg.svd((p-p.mean(axis=0)).T,compute_uv=False)
        rows.append((s[1],-index,index))
    return max(rows)[2]


def verify_geometry(report,packet,query_indices):
    import numpy as np
    mesh=packet['inputs']['mesh'];evaluated=packet['evaluated'];unit=packet['inputs']['unit_scale_m'];world=np.asarray(evaluated['mesh_matrix_world'])
    assert report['source_sha256']==packet['source_sha256'] and report['assessment']=='geometric_facts_not_damage'
    assert report['source']['source_kind']=='small-skin-source-snapshot-v1'
    assert report['triangles_total']==len(mesh['triangles']) and report['source_summary']['vertices_total']==len(mesh['vertices'])
    assert report['execution_authority'] is False and report['geometry_setters']==0 and report['original_file_saved'] is False
    assert report['damage_classification']=='not_inferred';seen={}
    rows=report['triangles']+report['task_query']['triangles']
    for row in rows:
        index=row['triangle'];tri=mesh['triangles'][index];assert row['vertices']==tri
        assert 0<=index<len(mesh['triangles']) and row['region_kind']=='original_triangle'
        if row['state'] in ('measured','collapsed'):
            expected,area=numeric_metric([mesh['vertices'][i] for i in tri],[evaluated['vertices'][i] for i in tri])
            np.testing.assert_allclose(row['principal_stretches'],expected,atol=1e-9,rtol=0.)
            assert abs(row['area_ratio']-area)<1e-9
        else:
            assert row['state']=='unknown' and row['principal_stretches'] is None and row['area_ratio'] is None
        points=np.asarray([evaluated['vertices'][i] for i in tri]);points=(world@np.column_stack((points,np.ones(3))).T).T[:,:3]*unit
        np.testing.assert_allclose(row['centroid_world_m'],points.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(row['bounds_world_m'],[points.min(axis=0),points.max(axis=0)],atol=1e-12)
        seen[index]=row
    task=report['task_query'];assert task['source_sha256']==packet['source_sha256']
    assert task['triangle_indices']==query_indices and [r['triangle'] for r in task['triangles']]==query_indices
    return seen


def error_value(exc):return dict(reason=getattr(exc,'code',str(exc)),status=getattr(exc,'status',None),type=type(exc).__name__)
def expect_error(callback,status,reason):
    try:callback()
    except Exception as exc:
        value=error_value(exc);assert value['reason']==reason and value['status']==status,(value,(status,reason));return value
    raise AssertionError('expected exact refusal '+reason)


def exercise_contract(args,profile,core,actor_type):
    from unittest.mock import patch
    from human_eye_plugin import small_skin_source_process as transport
    assert load(args.contract_registration)==contract_catalog()
    out=args.output/'contract';out.mkdir();rows=[]
    for name,(changes,status,reason) in PROFILE_NEGATIVE.items():
        folder=out/name;folder.mkdir();value=dict(profile,**changes);save(folder/'PROFILE.json',value)
        error=expect_error(lambda:actor_type(folder/'PROFILE.json'),status,reason)
        save(folder/'RESULT.json',dict(passed=True,error=error,no_report=True));rows.append(dict(case=name,passed=True,error=error))
    for mode in ('future_key','parent_inverse'):
        folder=out/mode;folder.mkdir();save(folder/'PROFILE.json',profile);real_popen=transport.subprocess.Popen;actor=None;started=time.perf_counter_ns()
        def spawn(command,**kwargs):
            cmd=list(command);index=cmd.index('--python')+1;worker=cmd[index];cmd[index]=str(Path(__file__).resolve())
            kwargs['env']=dict(os.environ,HE_SMALL_SOURCE_FAULT_MODE=mode,HE_SMALL_SOURCE_FAULT_OUTPUT=str(folder),HE_SMALL_SOURCE_REAL_WORKER=worker)
            return real_popen(cmd,**kwargs)
        try:
            with patch.object(transport.subprocess,'Popen',side_effect=spawn):actor=actor_type(folder/'PROFILE.json')
            first=actor.inspect();error=expect_error(actor.inspect,'unavailable','small_skin_stale_source');bindings=actor.bindings
            assert actor.sequence==2
        finally:
            if actor is not None:actor.close()
        assert actor.closed and actor.process.poll() is not None
        a=load(folder/'ACTOR_PACKET_01.json');b=load(folder/'ACTOR_PACKET_02.json')
        assert a==first and a['source_sha256']!=b['source_sha256'] and a['evaluated']['vertices']==b['evaluated']['vertices']
        historical_deadline=time.perf_counter_ns()+5_000_000_000
        core.validate(b,deadline_ns=historical_deadline,expected_bindings=bindings)
        stale=expect_error(lambda:core.validate(b,deadline_ns=historical_deadline,expected_bindings=bindings,expected_source=a),'unavailable','small_skin_stale_source')
        row=dict(case=mode,passed=True,error=error,independent_historical_stale_error=stale,fresh_source_valid=True,
            evaluated_coordinates_byte_equal=True,old_source_sha256=a['source_sha256'],new_source_sha256=b['source_sha256'],
            process_reaped=True,original_file_unchanged=sha(Path(profile['scene_file']))==profile['scene_sha256'],
            product_setters=0,test_actor=load(folder/'TEST_ACTOR.json'),complete_process_wall_ns=time.perf_counter_ns()-started,
            replay_note='Post-close validation is historical packet verification and grants no new live observation window.')
        assert row['original_file_unchanged'];save(folder/'RESULT.json',row);rows.append(row)
    # Use the actual native command parser: malformed windows and edit requests
    # consume the same finite slots as valid observations.
    folder=out/'wire_slots';folder.mkdir();save(folder/'PROFILE.json',profile);actor=None;wire=[];source=None
    try:
        actor=actor_type(folder/'PROFILE.json')
        for index in range(1,17):
            command='frame_set' if index==2 else 'inspect';deadline=actor.deadline_ns+1 if index==1 else actor.deadline_ns
            actor.process.stdin.write(core.r.encoded(dict(id=index,command=command,deadline_ns=deadline))+b'\n');actor.process.stdin.flush()
            value=actor._next();assert value['id']==index
            if index<=2:
                reason='small_skin_original_window' if index==1 else 'small_skin_readonly_command'
                assert value==dict(kind='error',id=index,reason=reason,geometry_setters=0)
                wire.append(value)
            else:
                assert value['kind']=='snapshot' and set(value)=={'kind','id','packet'}
                packet=value['packet'];core.validate(packet,deadline_ns=actor.deadline_ns,expected_bindings=actor.bindings,expected_source=source)
                if source is None:source=packet
                assert packet['source_sha256']==source['source_sha256'];wire.append(dict(kind='snapshot',id=index,source_sha256=packet['source_sha256']))
        actor.process.wait(timeout=3);assert actor.process.returncode==0 and len(wire)==16
    finally:
        if actor is not None:actor.close()
    row=dict(case='wire_slots',passed=True,rejected_commands=wire[:2],valid_reads=14,total_slots=16,worker_exit_code=0,process_reaped=True)
    save(folder/'WIRE.json',wire);save(folder/'RESULT.json',row);rows.append(row)
    folder=out/'host_slots';folder.mkdir();save(folder/'PROFILE.json',profile);actor=None
    try:
        actor=actor_type(folder/'PROFILE.json');first=None
        for _ in range(16):
            packet=actor.inspect()
            if first is None:first=packet
            assert packet['source_sha256']==first['source_sha256']
        error=expect_error(actor.inspect,'unavailable','small_skin_request_lifetime');assert actor.sequence==16
    finally:
        if actor is not None:actor.close()
    row=dict(case='host_slots',passed=True,valid_reads=16,request17=error,process_reaped=actor.process.poll() is not None)
    save(folder/'RESULT.json',row);rows.append(row);save(out/'RESULT.json',dict(cases=rows,total=len(rows),passed=True))
    return rows


def controller(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(args.core_root.resolve()))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_small_source_preflight_target',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
        assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin import small_skin_source as core
    from human_eye_plugin.small_skin_source_process import SmallSkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    from verification.rigged_source_qualification import gltf_witness
    identity=runtime_identity();assert check_source_drift()['compatible'] and load(args.registration)==catalog()
    fixtures=load(args.fixtures/'CASES.json');assert fixtures['registration_sha256']==sha(args.registration)
    assert fixtures['builder_sha256']==sha(Path(__file__))
    expected_names=['frame1','frame25','missing_weights',*NEGATIVE];assert [c['name'] for c in fixtures['rows']]==expected_names
    args.output.mkdir(exist_ok=False);rows=[];binary=Path('D:/Tools/blender5.2/blender.exe')
    for case in fixtures['rows']:
        name=case['name'];folder=args.output/name;folder.mkdir();profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],mesh_name='Cylinder',rig_name='Armature',expected_frame=dict(number=case['frame'],subframe=0.),
            unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);actor=None;first=second=report=witness=None;error=None;started=time.perf_counter_ns()
        try:
            actor=SmallSkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect()
            assert first['source_sha256']==second['source_sha256']
            geometry=core.validate(second,deadline_ns=actor.deadline_ns,expected_bindings=actor.bindings,expected_source=first)
            target=target_face(second)
            if name=='missing_weights':target=next(i for i,t in enumerate(second['inputs']['mesh']['triangles']) if 0 in t)
            overview=actor.analyze(second,deadline_ns=actor.deadline_ns)
            source=overview['source'];selection=dict(schema='surface-deformation-selection-v1',source_ref=dict(scene_sha256=profile['scene_sha256'],
                rig_object_id=source['object_id'],mesh_object_id=source['mesh_identity']['object_id'],frame=profile['expected_frame']),triangle_indices=[target])
            bound=actor.bind_selection(first,selection,deadline_ns=actor.deadline_ns)
            report=actor.analyze(second,deadline_ns=actor.deadline_ns,query=bound);verified=verify_geometry(report,second,[target])
            body=copy.deepcopy(report);body.pop('task_query');assert body==overview
            if name=='missing_weights':
                assert geometry['unweighted']==[0] and report['triangles_unknown']>0
                assert verified[target]['state']=='unknown' and verified[target]['reason']=='unweighted_vertex_source' and report['task_query']['status']=='partial'
            else:
                assert geometry['unweighted']==[] and verified[target]['state']=='measured' and report['task_query']['status']=='observed'
                witness=gltf_witness(second,GLB.read_bytes(),fps=second['inputs']['scene']['fps'],fps_base=second['inputs']['scene']['fps_base'],deadline_ns=actor.deadline_ns)
                assert witness['maximum_evaluated_position_error']<=2e-5 and witness['maximum_named_weight_error']==0 and witness['triangles_same_order']
            save(folder/'SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities));save(folder/'REPORT.json',report)
            save(folder/'SELECTION.json',selection);save(folder/'INDEPENDENT_GLTF.json',witness)
        except Exception as exc:error=error_value(exc)
        finally:
            if actor is not None:actor.close()
        if case['accepted']:assert error is None and report is not None,(name,error)
        else:
            status,reason=NEGATIVE[name];assert error is not None and error['reason']==reason and error['status']==status,(name,error,(status,reason))
            assert report is None
        assert sha(Path(case['scene']))==case['scene_sha256']
        row=dict(case=name,accepted=case['accepted'],passed=True,error=error,source_sha256=None if second is None else second['source_sha256'],
            original_file_unchanged=True,product_geometry_setters=0,product_file_saved=False,complete_process_wall_ns=time.perf_counter_ns()-started)
        if report is not None:
            row['geometry_summary']={key:report[key] for key in ('status','triangles_total','triangles_measured','triangles_unknown','triangles_collapsed','unknown_reasons')}
            row['requested_region']=dict(triangle=target,state=verified[target]['state'],principal_stretches=verified[target]['principal_stretches'],area_ratio=verified[target]['area_ratio'])
            row['independent_original_glb']=witness
        save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=name,passed=True,error=error)),flush=True)
    contract=exercise_contract(args,load(args.output/'frame1/PROFILE.json'),core,SmallSkinSourceProcess)
    save(args.output/'RESULT.json',dict(schema='small-source-native-preflight-v1',cases=rows,total=len(rows),accepted=3,precise_rejections=len(NEGATIVE),contract_cases=contract,
        runtime_source_sha256=identity['source_sha256'],runtime_source_count=len(identity['source_files']),scope='one external author sample two fixed frames plus deliberate QA derivatives',
        source_or_installed='installed' if args.entry else 'source',formal_model_trials=0,shared_GUI=False))


if __name__=='__main__':
    if os.environ.get('HE_SMALL_SOURCE_FAULT_MODE') and '--profile-sha256' in sys.argv:actor_wrapper();raise SystemExit(0)
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--preregister',action='store_true');mode.add_argument('--preregister-contract',action='store_true');mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--registration',type=Path,default=REGISTRATION);parser.add_argument('--fixtures',type=Path)
    parser.add_argument('--core-root',type=Path,default=ROOT);parser.add_argument('--entry',type=Path)
    parser.add_argument('--contract-registration',type=Path,default=EVIDENCE/'CONTRACT_PREREGISTERED.json')
    options=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if options.preregister:save(options.output,catalog());print(options.output)
    elif options.preregister_contract:save(options.output,contract_catalog());print(options.output)
    elif options.builder:builder(options)
    else:controller(options)
