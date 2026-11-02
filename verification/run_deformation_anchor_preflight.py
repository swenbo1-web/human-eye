"""Frozen public native-endpoint tasks and independent source-bound QA.

Test-authored fixtures and private answers never enter selector-model input.
The controller admits source normally; it cannot mark a packet qualified.
"""
import argparse,copy,hashlib,importlib.util,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'verification/fixes/20261102_m4_b3d_anchor_query'
CONTRACT=EVIDENCE/'CONTRACT_PREREGISTERED.json'
OLD_FIXTURES=ROOT/'verification/fixes/20261102_m4_b3b_product/fixtures_r4/CASES.json'
PREFIX='rig_pose_deformation_anchor_'


def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)


def catalog():
    return dict(schema='deformation-anchor-native-cases-v1',contract_sha256=sha(CONTRACT),
        catalogs=['author_frame1','author_frame25','authored_coincident','authored_two_roots','missing_weights'],
        queries=[dict(name=n,scene=s,target=t,half=[.5,.5,.5]) for n,s,t in [
            ('author1_child_head','author_frame1','unique_nonroot_head'),('author25_child_head','author_frame25','unique_nonroot_head'),
            ('author25_root_tail','author_frame25','named_Bone_tail'),('coincident_child_head','authored_coincident','unique_nonroot_head'),
            ('coincident_root_tail','authored_coincident','unique_root_tail'),('two_roots_named_tail','authored_two_roots','named_Bone_tail'),
            ('missing_child_head','missing_weights','unique_nonroot_head')]],
        source_unknown=dict(scene='bezier_interval',status='unknown',reason='small_skin_curve_interpolation'),
        contract_negative=dict(stale_catalog=PREFIX+'stale_catalog',wrong_scene=PREFIX+'stale_selection',wrong_frame=PREFIX+'stale_selection',
            unknown_anchor=PREFIX+'unknown_anchor',malformed_anchor=PREFIX+'anchor_id',zero_half=PREFIX+'half_extents',bool_half=PREFIX+'half_extents',
            nan_half=PREFIX+'half_extents',tiny_half=PREFIX+'half_extents',stale_query=PREFIX+'stale_source',
            changed_window='small_skin_analysis_window',mixed_modes='rig_pose_deformation_query_modes',changed_profile_pin=PREFIX+'stale_catalog'),
        contract_positive=['selection_deep_copy','stable_catalog_fresh_epoch'],
        oracle='Decimal exact affine and nearest/outward binary64, NumPy matrix endpoint crosscheck, independent SAT and QR/SVD',
        original_author_assets=1,static_author_frames=2,authored_QA_scenes=2,formal_model_comparisons=0,
        source_only='No source bypass, generic execute, setter, frame or save command')


def builder(args):
    import bpy
    assert bpy.app.background and load(args.registration)==catalog()
    assert args.output.is_absolute() and args.output.resolve().is_relative_to(EVIDENCE.resolve());args.output.mkdir(exist_ok=False)
    rows=[]
    for name in ('authored_coincident','authored_two_roots'):
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.unit_settings.scale_length=1.;scene.frame_set(1)
        data=bpy.data.armatures.new('Armature');rig=bpy.data.objects.new('Armature',data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        root=data.edit_bones.new('Bone');root.head=(0.,0.,-1.);root.tail=(0.,0.,0.)
        child=data.edit_bones.new('Bone.001');child.head=(0.,0.,0.) if name=='authored_coincident' else (1.,0.,-1.)
        child.tail=(0.,0.,1.) if name=='authored_coincident' else (1.,0.,0.)
        if name=='authored_coincident':child.parent=root;child.use_connect=False
        bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
        mesh=bpy.data.meshes.new('Cylinder');mesh.from_pydata([(-1.,-1.,0.),(1.,-1.,0.),(1.,1.,0.),(-1.,1.,0.),(9.,9.,9.)],[],[(0,1,2),(0,2,3)])
        obj=bpy.data.objects.new('Cylinder',mesh);scene.collection.objects.link(obj);group=obj.vertex_groups.new(name='Bone');group.add(list(range(5)),1.,'REPLACE')
        mod=obj.modifiers.new('Skin','ARMATURE');mod.object=rig;mod.use_vertex_groups=True;mod.use_bone_envelopes=False
        bpy.context.view_layer.objects.active=None;bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
        rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),frame=1,authored=True,
            loose_vertices=1,coincident_endpoints=name=='authored_coincident',two_roots=name=='authored_two_roots'))
    old={r['name']:r for r in load(OLD_FIXTURES)['rows']}
    for name,source in [('author_frame1','frame1'),('author_frame25','frame25'),('missing_weights','missing_weights'),('bezier_interval','bezier_interval')]:
        row=old[source];assert sha(Path(row['scene']))==row['scene_sha256'];rows.append(dict(name=name,scene=row['scene'],scene_sha256=row['scene_sha256'],frame=row['frame'],authored=False))
    save(args.output/'CASES.json',dict(rows=rows,registration_sha256=sha(args.registration),builder_sha256=sha(Path(__file__)),product_setters=0,
        author_setters='QA creates/saves only the two new independent factory scenes',original_files_unchanged=True))
    print(json.dumps(dict(fixtures=len(rows),authored=2,original_files_unchanged=True)))


def verify_region(report,packet,cat,selected,half):
    from verification.deformation_anchor_oracle import expected_box
    from verification.deformation_region_oracle import matching_indices,all_facts
    anchor=next(a for a in cat['anchors'] if a['anchor_id']==selected);region=expected_box(anchor,half);q=report['region_query'];trace=report['anchor_query']
    assert trace['schema']=='surface-deformation-anchor-query-result-v1' and trace['source_sha256']==packet['source_sha256']
    for key in ('anchor_id','bone_name','endpoint'):assert trace[key]==anchor[key]
    assert trace['catalog_sha256']==cat['catalog_sha256'] and trace['center_world_m']==anchor['position_world_m']
    assert trace['center_interval_world_m']==anchor['position_interval_world_m'] and trace['half_extents_m']==half and trace['region']==region
    assert trace['anchor_semantics']=='native_evaluated_bone_endpoint_not_anatomical_semantics'
    assert q['region']==region and q['metric_scope']=='whole_original_triangles_not_clipped_integrals'
    ids=matching_indices(packet,region['bounds']);facts=all_facts(packet,ids)
    assert q['matched_triangle_indices']==ids and q['membership_complete'] is True and q['triangles_total']==len(ids)
    counts={s:sum(f['state']==s for f in facts.values()) for s in ('measured','collapsed','unknown')}
    for state,count in counts.items():assert q['triangles_'+state]==count
    assert q['status']==('empty' if not ids else 'partial' if counts['unknown'] else 'observed')
    assert q['details_omitted']==len(ids)-len(q['triangles']) and len(q['triangles'])<=4
    measurable={i:f for i,f in facts.items() if f['state']!='unknown'}
    for name,field,op in [('max_principal_stretch',lambda f:f['principal_stretches'][0],max),('min_principal_stretch',lambda f:f['principal_stretches'][1],min),
            ('min_area_ratio',lambda f:f['area_ratio'],min),('max_area_ratio',lambda f:f['area_ratio'],max)]:
        witness=q['metric_extrema'][name]
        if not measurable:assert witness is None
        else:assert witness['triangle'] in measurable and abs(witness['value']-field(measurable[witness['triangle']]))<1e-9 and abs(witness['value']-op(field(f) for f in measurable.values()))<1e-9
    for detail in q['triangles']:
        wanted=facts[detail['triangle']];assert detail['state']==wanted['state'] and detail['reason']==wanted['reason']
        if wanted['state']=='unknown':assert detail['principal_stretches'] is None and detail['area_ratio'] is None
        else:assert max(abs(a-b) for a,b in zip(detail['principal_stretches'],wanted['principal_stretches']))<1e-9 and abs(detail['area_ratio']-wanted['area_ratio'])<1e-9
    assert not report['execution_authority'] and report['geometry_setters']==0 and not report['original_file_saved']
    return dict(region=region,matched_triangle_indices=ids,states=counts,facts=facts,correct_native_identity=True)


def error(exc):return dict(type=type(exc).__name__,status=getattr(exc,'status',None),reason=getattr(exc,'code',str(exc)))
def expect(call,reason):
    try:call()
    except Exception as exc:
        value=error(exc);assert value['reason']==reason,(value,reason);return value
    raise AssertionError('expected refusal '+reason)


def contract_checks(folder,profile,actor_type,registration):
    from verification.deformation_anchor_oracle import resolve_task,selection
    folder.mkdir();save(folder/'PROFILE.json',profile);rows=[];actor=None
    try:
        actor=actor_type(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();cat=actor.describe_anchors(second,deadline_ns=actor.deadline_ns)
        identity=resolve_task(cat,'unique_nonroot_head')['anchor_id'];original=selection(cat,identity,[.5,.5,.5]);query=actor.bind_anchor_selection(first,original,deadline_ns=actor.deadline_ns)
        mutations={
            'stale_catalog':lambda x:x.update(catalog_sha256='0'*64), 'wrong_scene':lambda x:x['source_ref'].update(scene_sha256='0'*64),
            'wrong_frame':lambda x:x['source_ref']['frame'].update(number=x['source_ref']['frame']['number']+1),
            'unknown_anchor':lambda x:x.update(anchor_id='bone-anchor:'+'0'*64),'malformed_anchor':lambda x:x.update(anchor_id=True),
            'zero_half':lambda x:x.update(half_extents_m=[0.,.5,.5]),'bool_half':lambda x:x.update(half_extents_m=[True,.5,.5]),
            'nan_half':lambda x:x.update(half_extents_m=[float('nan'),.5,.5]),'tiny_half':lambda x:x.update(half_extents_m=[1e-7,.5,.5])}
        for name,change in mutations.items():
            candidate=copy.deepcopy(original);change(candidate)
            value=expect(lambda:actor.bind_anchor_selection(first,candidate,deadline_ns=actor.deadline_ns),registration['contract_negative'][name]);rows.append(dict(case=name,passed=True,error=value))
        stale=dict(query,expected_source_sha256='0'*64)
        for name,call in [('stale_query',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,anchor_query=stale)),
                ('changed_window',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns+1,anchor_query=query)),
                ('mixed_modes',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,query=dict(schema='surface-deformation-query-v1',expected_source_sha256=second['source_sha256'],triangle_indices=[0]),anchor_query=query))]:
            rows.append(dict(case=name,passed=True,error=expect(call,registration['contract_negative'][name])))
        caller=copy.deepcopy(original);bound=actor.bind_anchor_selection(first,caller,deadline_ns=actor.deadline_ns);caller['half_extents_m'][0]=99.
        assert bound['half_extents_m']==[.5,.5,.5];rows.append(dict(case='selection_deep_copy',passed=True))
    finally:
        if actor is not None:actor.close()
    for name,extra in [('stable_catalog_fresh_epoch',b''),('changed_profile_pin',b' ')]:
        path=folder/(name+'.profile.json');path.write_bytes((folder/'PROFILE.json').read_bytes()+extra);fresh=None
        try:
            fresh=actor_type(path);new=fresh.inspect();other=fresh.describe_anchors(new,deadline_ns=fresh.deadline_ns)
            assert new['source_sha256']!=cat['source_sha256']
            if extra:
                assert other['catalog_sha256']!=cat['catalog_sha256'] and other['anchors']==cat['anchors']
                failure=expect(lambda:fresh.bind_anchor_selection(new,original,deadline_ns=fresh.deadline_ns),registration['contract_negative'][name])
                rows.append(dict(case=name,passed=True,error=failure))
            else:
                assert other['catalog_sha256']==cat['catalog_sha256'];newquery=fresh.bind_anchor_selection(new,original,deadline_ns=fresh.deadline_ns)
                assert newquery['expected_source_sha256']==new['source_sha256'];fresh.analyze(new,deadline_ns=fresh.deadline_ns,anchor_query=newquery)
                failure=expect(lambda:fresh.analyze(new,deadline_ns=fresh.deadline_ns,anchor_query=query),PREFIX+'stale_source')
                rows.append(dict(case=name,passed=True,stable_digest_equal=True,old_live_query_refused=failure))
        finally:
            if fresh is not None:fresh.close()
    save(folder/'RESULT.json',dict(cases=rows,total=len(rows),all_passed=True));return rows


def controller(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(args.core_root.resolve()))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_anchor_qa_target',args.entry.with_name('target_runtime_entry.py'));entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin.small_skin_source_process import SmallSkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    from verification.deformation_anchor_oracle import verify_catalog,resolve_task,selection
    identity=runtime_identity();assert check_source_drift()['compatible'];registration=load(args.registration);assert registration==catalog()
    fixtures=load(args.fixtures/'CASES.json');assert fixtures['registration_sha256']==sha(args.registration) and fixtures['builder_sha256']==sha(Path(__file__))
    cases={r['name']:r for r in fixtures['rows']};binary=Path('D:/Tools/blender5.2/blender.exe');args.output.mkdir(exist_ok=False);rows=[];catalogs={};profile1=None
    tasks=[dict(name='catalog_'+scene,scene=scene,mode='catalog') for scene in registration['catalogs']]+[dict(t,mode='query') for t in registration['queries']]
    tasks.append(dict(name='bezier_source_unknown',scene='bezier_interval',mode='unknown'))
    for task in tasks:
        folder=args.output/task['name'];folder.mkdir();fixture=cases[task['scene']];actor=None;failure=None;report=None
        profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),scene_file=fixture['scene'],scene_sha256=fixture['scene_sha256'],
            mesh_name='Cylinder',rig_name='Armature',expected_frame=dict(number=fixture['frame'],subframe=0.),unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);started=time.perf_counter_ns()
        try:
            actor=SmallSkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();assert first['source_sha256']==second['source_sha256']
            cat=actor.describe_anchors(second,deadline_ns=actor.deadline_ns);expected=verify_catalog(cat,second)
            save(folder/'CATALOG.json',cat);save(folder/'INDEPENDENT_CATALOG.json',expected);save(folder/'SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities))
            if task['mode']=='catalog':catalogs[task['scene']]=cat;report=cat
            elif task['mode']=='query':
                decision=resolve_task(cat,task['target']);assert decision['state']=='selected';recipe=selection(cat,decision['anchor_id'],task['half'])
                bound=actor.bind_anchor_selection(first,recipe,deadline_ns=actor.deadline_ns);report=actor.analyze(second,deadline_ns=actor.deadline_ns,anchor_query=bound)
                result=verify_region(report,second,cat,decision['anchor_id'],task['half']);save(folder/'SELECTION.json',recipe);save(folder/'BOUND_QUERY.json',bound);save(folder/'INDEPENDENT_REGION.json',result)
            else:raise AssertionError('source unknown accepted')
            save(folder/'REPORT.json',report)
            if task['scene']=='author_frame1':profile1=profile
        except Exception as exc:failure=error(exc)
        finally:
            if actor is not None:actor.close()
        assert sha(Path(fixture['scene']))==fixture['scene_sha256']
        if task['mode']=='unknown':assert failure and failure['reason']=='small_skin_curve_interpolation' and failure['status']=='unknown' and report is None
        else:assert failure is None and report is not None,(task,failure)
        row=dict(case=task['name'],passed=True,error=failure,product_setters=0,product_saves=False,original_file_unchanged=True,process_reaped=actor is None or actor.process.poll() is not None,
            complete_process_wall_ns=time.perf_counter_ns()-started)
        if report is not None:
            row['catalog_sha256']=cat['catalog_sha256'];row['anchors_total']=cat['completeness']['anchors_total'];row['loose_vertices_excluded']=cat['bounds']['loose_vertices_excluded']
            if task['mode']=='query':row.update(anchor_id=decision['anchor_id'],region_status=report['region_query']['status'],matched=report['region_query']['triangles_total'])
        rows.append(row);save(folder/'RESULT.json',row);print(json.dumps(row),flush=True)
    checks=contract_checks(args.output/'contract',profile1,SmallSkinSourceProcess,registration)
    cc=catalogs['authored_coincident'];a=resolve_task(cc,'unique_nonroot_head')['anchor_id'];b=resolve_task(cc,'unique_root_tail')['anchor_id'];assert a!=b
    points={p['anchor_id']:p['position_world_m'] for p in cc['anchors']};assert points[a]==points[b]
    result=dict(schema='deformation-anchor-native-result-v1',runtime_source_sha256=identity['source_sha256'],runtime_count=len(identity['source_files']),cases=rows,total=len(rows),
        contract_cases=checks,contract_total=len(checks),all_passed=True,coincident_native_identities_distinct=True,harness_sha256=sha(Path(__file__)),oracle_sha256=sha(ROOT/'verification/deformation_anchor_oracle.py'),
        contract_sha256=sha(CONTRACT),registration_sha256=sha(args.registration),source_or_installed='installed' if args.entry else 'source',formal_model_comparisons=0)
    save(args.output/'PUBLIC_CATALOGS.json',catalogs);save(args.output/'RESULT.json',result)


TASK_TEXT={
    'unique_nonroot_head':'选择目录中唯一一个有父骨的原生骨骼的head端点；若不唯一则报告ambiguous。',
    'unique_root_tail':'选择目录中唯一一个没有父骨的原生骨骼的tail端点；若不唯一则报告ambiguous。',
    'named_Bone_tail':'选择原生骨骼名称精确为Bone的tail端点。',
    'named_MissingBone_head':'选择原生骨骼名称精确为MissingBone的head端点。',
    'elbow_semantics_without_mapping':'选择角色肘部中心；目录未给解剖语义映射时不能用骨骼关系猜测。'}


def public_model_input(catalogs):
    contract=load(CONTRACT)
    return dict(schema='public-anchor-selector-task-v1',catalogs=copy.deepcopy({k:catalogs[k] for k in {t['scene'] for t in contract['tasks']}}),
        tasks=[dict(task_id=t['id'],scene=t['scene'],instruction=TASK_TEXT[t['target']],half_extents_m=t['half']) for t in contract['tasks']],
        decision_schema=dict(schema='anchor-task-decisions-v1',decisions='exactly one row per task: task_id,state,anchor_id or null,half_extents_m or null,reason',
            states=['selected','ambiguous','not_found','unsupported_semantics']),
        instructions='Use only the public catalog. Select native identity, not matching coordinates; do not emit box coordinates or face IDs. For selected, copy requested half sizes. No anatomy inference, metrics, images or edits.')


def grade_model_decisions(catalogs,decisions):
    from verification.deformation_anchor_oracle import resolve_task
    contract=load(CONTRACT);assert decisions['schema']=='anchor-task-decisions-v1';rows=decisions['decisions'];tasks=contract['tasks']
    assert len(rows)==len(tasks) and len({r['task_id'] for r in rows})==len(rows) and {r['task_id'] for r in rows}=={t['id'] for t in tasks}
    result=[]
    for task in tasks:
        got=next(r for r in rows if r['task_id']==task['id']);expected=resolve_task(catalogs[task['scene']],task['target'])
        passed=got['state']==expected['state'] and got.get('anchor_id')==expected['anchor_id']
        if expected['state']=='selected':passed=passed and type(got.get('half_extents_m')) is list and got['half_extents_m']==task['half'] and all(type(v) in (int,float) for v in got['half_extents_m'])
        result.append(dict(task_id=task['id'],passed=passed,expected_state=expected['state'],expected_anchor_id=expected['anchor_id'],actual=got))
    return dict(schema='anchor-selector-independent-grade-v1',passed=all(r['passed'] for r in result),tasks=result,total=len(result),coincident_identity_required=True,
        hidden_coordinates_or_faces_supplied=False,formal_model_comparisons=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preregister',action='store_true');mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--registration',type=Path,default=EVIDENCE/'CASES_PREREGISTERED.json')
    parser.add_argument('--fixtures',type=Path);parser.add_argument('--core-root',type=Path,default=ROOT);parser.add_argument('--entry',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.preregister:save(args.output,catalog());print(args.output)
    elif args.builder:builder(args)
    else:controller(args)
