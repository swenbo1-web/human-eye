"""Independent task-coverage probe over finite mathematical source doubles.

This is neither a native Blender capture nor an external/production asset test.
The frozen baseline can be selected with --core-root before importing fixtures.
"""
import argparse,copy,hashlib,importlib.util,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BASELINE_SOURCE='df3c38ab011d57600e3e9ea3097740f18a57eea34e18484181549d7069865bb7'
MATRIX=[('isometric_omitted','all_isometric',(0.,0.,0.),128),
    ('normal_under_unknown','unknown_crowding',(0.,0.,0.),128),
    ('stretch_under_unknown','unknown_crowding',(0.,.1,.3),128),
    ('unknown_target','all_unweighted',(0.,0.,0.),128),
    ('normal_under_collapse','collapse_crowding',(0.,0.,0.),128)]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def mesh_inputs(kind,*,target=128,weights=(0.,0.,0.)):
    # Builder must not import the plugin package: Blender's Python deliberately
    # has no facade/Pillow dependency. Authored geometry and LBS are sufficient.
    from verification.run_skin_source_preflight import geometry
    vertices,triangles=geometry(torus=True)
    if kind=='all_isometric':groups=[[[0,1.],[1,0.]] for _ in range(128)]
    elif kind=='unknown_crowding' or kind=='all_unweighted':groups=[[] for _ in range(128)]
    elif kind=='collapse_crowding':groups=[[[0,.5],[1,.5]] for _ in range(128)]
    else:raise ValueError('probe_kind')
    if kind not in ('all_unweighted','all_isometric'):
        for vertex,weight in zip(triangles[target],weights):groups[vertex]=[[0,1.-weight],[1,weight]]
    evaluated=[]
    for point,influences in zip(vertices,groups):
        factor=1.-2*influences[1][1] if influences else 1.
        evaluated.append([factor*point[0],point[1],factor*point[2]])
    return dict(vertices=vertices,triangles=triangles,weights=groups,evaluated_vertices=evaluated)


def fixture(kind,*,target=128,weights=(0.,0.,0.)):
    """Fixed torus, fixed half-turn bone, analytically assembled LBS positions."""
    from verification.test_skin_source import packet,rehash
    value=packet(neutral=True,torus=True);mesh=value['mesh'];bone=value['rig']['payload']['bones'][1]
    basis=np.diag([-1.,1.,-1.,1.]);pose=np.array(bone['rest_matrix'])@basis
    bone.update(basis_matrix=basis.tolist(),pose_matrix=pose.tolist(),rotation_mode='QUATERNION',rotation_quaternion=[0.,0.,1.,0.],
        pose_head=(pose@np.array([0.,0.,0.,1.]))[:3].tolist(),pose_tail=(pose@np.array([0.,1.,0.,1.]))[:3].tolist())
    value['bone_channels'][1].update(basis=basis.tolist(),mode='QUATERNION',quaternion=[0.,0.,1.,0.])
    # Bone 0 is identity; bone 1 is an exact half-turn about local Y. This
    # authored closed form is independent of production LBS replay code.
    mesh.update(mesh_inputs(kind,target=target,weights=weights))
    return rehash(value)


def independent_target(packet,index):
    mesh=packet['mesh'];ids=mesh['triangles'][index];old=np.asarray([mesh['vertices'][i] for i in ids]);new=np.asarray([mesh['evaluated_vertices'][i] for i in ids])
    missing=[i for i in ids if not any(weight>0 for _,weight in mesh['weights'][i])]
    result=dict(triangle=index,vertices=ids[:],unweighted_vertices=missing)
    if missing:return dict(result,state='unknown',reason='unweighted_vertex_source',principal_stretches=None,area_ratio=None)
    a=(old[1:]-old[0]).T;b=(new[1:]-new[0]).T
    _,chart=np.linalg.qr(a,mode='reduced');gradient=np.linalg.solve(chart.T,b.T).T
    factors=np.linalg.svd(gradient,compute_uv=False);area=float(np.linalg.norm(np.cross(b[:,0],b[:,1]))/np.linalg.norm(np.cross(a[:,0],a[:,1])))
    return dict(result,state='measured',reason=None,principal_stretches=factors.tolist(),area_ratio=area)


def without_source(report):
    result=copy.deepcopy(report)
    # Remove both complete provenance containers; do not silently discard
    # aggregate counts or unknown reasons just to obtain an equality claim.
    result.pop('source');result.pop('source_sha256');return result


def run(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(args.core_root.resolve()))
    from human_eye_plugin import surface_deformation as d
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    identity=runtime_identity();assert identity['source_sha256']==BASELINE_SOURCE and check_source_drift()['compatible']
    args.output.mkdir(exist_ok=False);rows=[];reports={}
    for name,kind,weights,target in MATRIX:
        packet=fixture(kind,target=target,weights=weights);deadline=time.perf_counter_ns()+5_000_000_000
        report=d.analyze(packet,deadline_ns=deadline);oracle=independent_target(packet,target)
        assert report['triangles_total']==256 and report['source_summary']['vertices_total']==128
        visible={r['triangle'] for r in report['triangles']};assert len(visible)==16 and target not in visible
        if name=='stretch_under_unknown':assert oracle['principal_stretches'][0]>4.5 and oracle['area_ratio']>4.18
        if name in ('isometric_omitted','normal_under_unknown','normal_under_collapse'):
            np.testing.assert_allclose(oracle['principal_stretches'],[1.,1.],atol=1e-12);assert abs(oracle['area_ratio']-1)<1e-12
        if name=='unknown_target':assert oracle['reason']=='unweighted_vertex_source' and oracle['principal_stretches'] is None
        folder=args.output/name;folder.mkdir();save(folder/'SOURCE_PACKET.json',packet);save(folder/'REPORT.json',report);save(folder/'INDEPENDENT_TARGET.json',oracle)
        row=dict(case=name,target=target,target_present=False,oracle=oracle,reported_triangle_ids=sorted(visible),
            triangles_measured=report['triangles_measured'],triangles_collapsed=report['triangles_collapsed'],triangles_unknown=report['triangles_unknown'])
        rows.append(row);reports[name]=report
    a=reports['normal_under_unknown'];b=reports['stretch_under_unknown']
    assert a['source_sha256']!=b['source_sha256'] and without_source(a)==without_source(b)
    summary=dict(schema='deformation-task-coverage-baseline-v1',source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        cases=rows,missing_targets=5,source_only_difference_pair=['normal_under_unknown','stretch_under_unknown'],
        reports_equal_after_removing_complete_source=True,scope='source-valid mathematical torus double; not native, external or production asset',
        result='bounded overview cannot answer explicit omitted-triangle task, including normal, stretched and unknown requested targets',
        model_benefit_proven=False,formal_model_trials=0,geometry_setters=0)
    save(args.output/'RESULT.json',summary);print(json.dumps(dict(passed=True,baseline_gap_reproduced=True,missing_targets=5,
        normal_vs_stretch_same_overview=True,oracle_stretch=rows[2]['oracle']['principal_stretches'],oracle_area=rows[2]['oracle']['area_ratio'])))


def native_builder(args):
    import bpy
    sys.path.insert(0,str(ROOT));assert bpy.app.background and args.output.is_absolute()
    assert args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False);rows=[]
    for name,kind,weights,target in MATRIX:
        m=mesh_inputs(kind,target=target,weights=weights)
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');rig=bpy.data.objects.new('Rig',data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        for i in range(2):
            bone=data.edit_bones.new('bone_'+str(i));bone.head=(0.,0.,0.);bone.tail=(0.,1.,0.)
        bpy.ops.object.mode_set(mode='OBJECT')
        for i in range(2):
            bone=data.bones['bone_'+str(i)];bone.use_envelope_multiply=False
            pose=rig.pose.bones[bone.name];pose.rotation_mode='QUATERNION';pose.rotation_quaternion=(1.,0.,0.,0.) if i==0 else (0.,0.,1.,0.)
        mesh=bpy.data.meshes.new('SkinData');mesh.from_pydata(m['vertices'],[],m['triangles']);obj=bpy.data.objects.new('Skin',mesh);scene.collection.objects.link(obj)
        groups=[obj.vertex_groups.new(name='bone_'+str(i)) for i in range(2)]
        for index,values in enumerate(m['weights']):
            for group,weight in values:groups[group].add([index],weight,'REPLACE')
        mod=obj.modifiers.new('Skinning','ARMATURE');mod.object=rig;mod.use_vertex_groups=True;mod.use_bone_envelopes=False;mod.use_deform_preserve_volume=False
        marker=mesh.attributes.new('he_probe_vertex_id','INT','POINT')
        for i,item in enumerate(marker.data):item.value=i
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        bpy.ops.wm.open_mainfile(filepath=str(path));obj=bpy.context.scene.objects['Skin'];evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        native=dict(vertices=[list(v.co) for v in evaluated.data.vertices],triangles=[list(p.vertices) for p in evaluated.data.polygons],
            marker_ids=[v.value for v in evaluated.data.attributes['he_probe_vertex_id'].data],
            original_marker_ids=[v.value for v in obj.data.attributes['he_probe_vertex_id'].data])
        oracle=dict(vertices=m['vertices'],triangles=m['triangles'],weights=m['weights'],evaluated_vertices=m['evaluated_vertices'],
            target=target,target_facts=independent_target(dict(mesh=m),target),truth='fixed identity / exact Y half-turn analytic LBS plus independent NumPy QR/SVD')
        save(folder/'NATIVE_WITNESS.json',native);save(folder/'AUTHORED_ORACLE.json',oracle)
        rows.append(dict(name=name,scene=str(path),scene_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),target=target,
            kind=kind,authored_weights=list(weights)))
    save(args.output/'CASES.json',dict(schema='deformation-task-native-cases-v1',rows=rows,scope='authored factory assets, not external/production assets',builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(dict(built=len(rows))))


def selection(packet,indices):
    return dict(schema='surface-deformation-selection-v1',source_ref=dict(scene_sha256=packet['scene_sha256'],
        rig_object_id=packet['rig']['identity']['object_id'],mesh_object_id=packet['mesh']['identity']['object_id'],frame=copy.deepcopy(packet['rig']['payload']['frame'])),
        triangle_indices=list(indices))


def verify_requested(report,packet,indices):
    query=report['task_query'];assert query['schema']=='surface-deformation-query-result-v1' and query['source_sha256']==packet['source_sha256']
    assert query['triangle_indices']==indices and [v['triangle'] for v in query['triangles']]==indices
    expected_unknown=False
    for row,index in zip(query['triangles'],indices):
        oracle=independent_target(packet,index);assert row['vertices']==oracle['vertices'] and row['state']==oracle['state']
        if oracle['state']=='unknown':
            expected_unknown=True;assert row['reason']==oracle['reason'] and row['principal_stretches'] is None and row['area_ratio'] is None
        else:
            assert np.max(np.abs(np.asarray(row['principal_stretches'])-oracle['principal_stretches']))<5e-5
            assert abs(row['area_ratio']-oracle['area_ratio'])<5e-5
        assert row['region_kind']=='original_triangle'
        p=np.asarray([packet['mesh']['evaluated_vertices'][v] for v in row['vertices']]);world=np.asarray(packet['mesh']['object_matrix_world']);p=(world@np.column_stack((p,np.ones(3))).T).T[:,:3]*packet['rig']['payload']['unit_scale_m']
        np.testing.assert_allclose(row['centroid_world_m'],p.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(row['bounds_world_m'],[p.min(axis=0),p.max(axis=0)],atol=1e-12)
    assert query['status']==('partial' if expected_unknown else 'observed')


def native_controller(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(args.core_root.resolve()))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_task_query_target',args.entry.with_name('target_runtime_entry.py'));entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin import surface_deformation as d
    from human_eye_plugin.skin_source_process import SkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    identity=runtime_identity();assert check_source_drift()['compatible'];fixtures=json.loads((args.fixtures/'CASES.json').read_bytes())
    assert [c['name'] for c in fixtures['rows']]==[row[0] for row in MATRIX];args.output.mkdir(exist_ok=False)
    binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=hashlib.sha256(binary.read_bytes()).hexdigest();rows=[]
    for case in fixtures['rows']:
        folder=args.output/case['name'];folder.mkdir();oracle=json.loads((args.fixtures/case['name']/'AUTHORED_ORACLE.json').read_bytes())
        profile=dict(schema='skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],mesh_name='Skin',rig_name='Rig',expected_frame=dict(number=1,subframe=0.),runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);actor=None;started=time.perf_counter_ns()
        try:
            actor=SkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();target=case['target']
            assert first['source_sha256']==second['source_sha256'];overview=d.analyze(second,deadline_ns=actor.deadline_ns)
            assert target not in {r['triangle'] for r in overview['triangles']} and len(overview['triangles'])==16
            proposal=selection(first,[target]);bound=d.bind_selection(first,proposal,deadline_ns=actor.deadline_ns)
            report=d.analyze(second,deadline_ns=actor.deadline_ns,query=bound);verify_requested(report,second,[target])
            default_part=copy.deepcopy(report);default_part.pop('task_query');assert default_part==overview
            for key in ('geometry_setters','original_file_saved','execution_authority'):assert report[key]==(0 if key=='geometry_setters' else False)
            m=second['mesh'];assert m['triangles']==oracle['triangles'] and np.max(np.abs(np.asarray(m['evaluated_vertices'])-oracle['evaluated_vertices']))<=2e-5
            witness=json.loads((args.fixtures/case['name']/'NATIVE_WITNESS.json').read_bytes())
            assert witness['marker_ids']==list(range(128))==witness['original_marker_ids'];assert np.max(np.abs(np.asarray(witness['vertices'])-m['evaluated_vertices']))<2e-5
            wanted=oracle['target_facts'];got=report['task_query']['triangles'][0];assert got['state']==wanted['state']
            if wanted['state']=='measured':
                assert np.max(np.abs(np.asarray(got['principal_stretches'])-wanted['principal_stretches']))<5e-5 and abs(got['area_ratio']-wanted['area_ratio'])<5e-5
            save(folder/'SELECTION.json',proposal);save(folder/'SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities));save(folder/'REPORT.json',report);save(folder/'OVERVIEW.json',overview)
        finally:
            if actor is not None:actor.close()
        crossing=None
        if case['name']=='isometric_omitted':
            actor=None
            try:
                actor=SkinSourceProcess(folder/'PROFILE.json');fresh=actor.inspect();assert fresh['source_sha256']!=first['source_sha256']
                try:d.analyze(fresh,deadline_ns=actor.deadline_ns,query=bound)
                except ValueError as exc:stale_error=str(exc)
                else:raise AssertionError('old capture query accepted')
                rebound=d.bind_selection(fresh,proposal,deadline_ns=actor.deadline_ns);current=d.analyze(fresh,deadline_ns=actor.deadline_ns,query=rebound);verify_requested(current,fresh,[target])
                changed=copy.deepcopy(proposal);changed['source_ref']['scene_sha256']='e'*64
                try:d.bind_selection(fresh,changed,deadline_ns=actor.deadline_ns)
                except ValueError as exc:file_error=str(exc)
                else:raise AssertionError('different immutable-file reference accepted')
                crossing=dict(capture_changed=True,old_expected_source_refused=stale_error,new_stable_selection_accepted=True,changed_file_refused=file_error)
                save(folder/'FRESH_CAPTURE.json',dict(snapshot=fresh,report=current,checks=crossing))
            finally:
                if actor is not None:actor.close()
        assert hashlib.sha256(Path(case['scene']).read_bytes()).hexdigest()==case['scene_sha256']
        rows.append(dict(case=case['name'],target=target,default_omitted=True,explicit_query_correct=True,original_file_unchanged=True,
            target_state=got['state'],source_sha256=second['source_sha256'],fresh_capture_checks=crossing,full_process_wall_ns=time.perf_counter_ns()-started))
        print(json.dumps(dict(case=case['name'],passed=True,target_state=got['state'])),flush=True)
    save(args.output/'RESULT.json',dict(schema='deformation-task-query-native-result-v1',source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        total=len(rows),default_missing=5,explicit_correct=5,cases=rows,source_or_installed='installed' if args.entry else 'source',
        scope='authored factory assets; engineering task coverage only, not external production or model-benefit evidence',formal_model_trials=0,geometry_setters=0,shared_GUI=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group();m.add_argument('--builder',action='store_true');m.add_argument('--controller',action='store_true')
    p.add_argument('--core-root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--entry',type=Path)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=p.parse_args(argv)
    native_builder(args) if args.builder else native_controller(args) if args.controller else run(args)
