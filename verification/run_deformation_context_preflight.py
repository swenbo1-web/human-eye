"""Native fixed-core/context qualification with independent SAT/SVD answers.

Factory creation belongs to QA. Product source readers have no edit command.
No candidate is run until root freezes its runtime and isolated installation.
"""
import argparse,copy,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'verification/fixes/20261102_m4_b3e_context_quality'
CONTRACT=EVIDENCE/'CONTRACT_PREREGISTERED.json'
sys.path.insert(0,str(ROOT))
from verification.deformation_context_oracle import policy,selection,verify_context,payload


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def save(p,value):
    with Path(p).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def catalog():
    common=dict(core=[.25]*3,primary=[2.]*3,candidates=[[.5]*3,[1.5]*3],max_surplus_members=0)
    cases=[]
    for name,outcome in [('gain_islands','selected'),('empty_focus','focus_empty'),('unknown_focus','focus_all_unknown'),
            ('context_unknown','selected'),('boundary_contact','selected'),('collapsed_focus','selected')]:
        cases.append(dict(common,name=name,authored=True,expected=outcome))
    cases.append(dict(common,name='normal',authored=True,core=[.5]*3,primary=[.5]*3,candidates=[],expected='within_surplus_budget'))
    cases.append(dict(common,name='long_face',authored=True,candidates=[[1.]*3,[1.5]*3],expected='no_verified_gain'))
    for name in ('author_frame1','author_frame25'):
        cases.append(dict(common,name=name,authored=False,primary=[.5]*3,candidates=[[.25]*3],expected='verified_or_kept'))
    return dict(schema='deformation-context-native-cases-v1',contract_sha256=sha(CONTRACT),cases=cases,
        anchor='named Bone head in authored assets; named Bone.001 head in original author assets',
        original_author_assets=1,static_author_frames=2,authored_QA_assets=8,
        oracle='exact separating axes over full snapshot plus NumPy/SVD, actual full publication bytes including quality trace',
        operator_policy_only=True,formal_model_comparisons=0,
        policy_negative={k:'rig_pose_deformation_context_'+v for k,v in dict(cuts_core='candidate_core',enlarges_primary='candidate_primary',
            duplicate='candidate_duplicate',too_many='candidate_limit',bool_half='half_extents',tiny_saved_threshold='min_saved_bytes',
            excessive_budget='planning_budget_ms',bool_surplus='max_surplus_members',extra_field='policy_fields').items()},
        selection_negative={k:'rig_pose_deformation_context_'+v for k,v in dict(policy_sha='policy_binding',catalog='stale_catalog',scene='stale_selection',
            frame='stale_selection',anchor='policy_binding',untrusted_half='selection_fields').items()},
        direct_negative=dict(stale_query='rig_pose_deformation_context_stale_source',mixed_modes='rig_pose_deformation_query_modes',
            wrong_window='small_skin_analysis_window',duplicate_configure='rig_pose_deformation_context_policy_already_set',
            changed_policy='small_skin_context_policy_changed'),positive_contract=['selection_independence'])


def island(x,y,r=.1):return [(x-r,y-r,0.),(x+r,y-r,0.),(x,y+r,0.)]


def geometry(name):
    centers=[(-1.2,-1.2),(0.,-1.2),(1.2,-1.2),(-1.2,0.),(1.2,0.),(-1.2,1.2),(0.,1.2),(1.2,1.2)]
    points=[];faces=[];weights=[]
    def add(values,kind='root'):
        first=len(points);points.extend(values);faces.append([first,first+1,first+2]);weights.extend([kind]*3)
    if name=='long_face':
        add([(-8.,-8.,0.),(8.,-8.,0.),(0.,9.,0.)]);add(island(.75,0.,.05));return points,faces,weights
    if name!='empty_focus':
        values=[(.25,.25,0.),(.75,.25,0.),(.25,.75,0.)] if name=='boundary_contact' else island(0.,0.)
        kind='unweighted' if name=='unknown_focus' else 'blend' if name=='collapsed_focus' else 'root';add(values,kind)
    for x,y in centers:add(island(x,y),'unweighted' if name=='context_unknown' else 'root')
    return points,faces,weights


def builder(args):
    import bpy
    registration=load(args.registration);assert registration==catalog()
    assert args.output.is_absolute() and args.output.resolve().is_relative_to(EVIDENCE.resolve());args.output.mkdir(exist_ok=False);rows=[]
    for case in registration['cases']:
        if not case['authored']:continue
        name=case['name'];bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.unit_settings.scale_length=1.;scene.frame_set(1)
        data=bpy.data.armatures.new('Armature');rig=bpy.data.objects.new('Armature',data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        root=data.edit_bones.new('Bone');root.head=(0.,0.,0.);root.tail=(0.,1.,0.)
        if name=='collapsed_focus':
            flip=data.edit_bones.new('Flip');flip.head=(0.,0.,0.);flip.tail=(0.,1.,0.)
        bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
        if name=='collapsed_focus':
            bone=rig.pose.bones['Flip'];bone.rotation_mode='QUATERNION';bone.rotation_quaternion=(0.,0.,0.,1.)
        points,triangles,kinds=geometry(name);mesh=bpy.data.meshes.new('Cylinder');mesh.from_pydata(points,[],triangles);mesh.update()
        obj=bpy.data.objects.new('Cylinder',mesh);scene.collection.objects.link(obj);root_group=obj.vertex_groups.new(name='Bone')
        flip_group=obj.vertex_groups.new(name='Flip') if name=='collapsed_focus' else None
        for index,kind in enumerate(kinds):
            if kind=='root':root_group.add([index],1.,'REPLACE')
            elif kind=='blend':root_group.add([index],.5,'REPLACE');flip_group.add([index],.5,'REPLACE')
        mod=obj.modifiers.new('Skin','ARMATURE');mod.object=rig;mod.use_vertex_groups=True;mod.use_bone_envelopes=False
        bpy.context.view_layer.objects.active=None;bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
        rows.append(dict(case,scene=str(path),scene_sha256=sha(path),frame=1,mesh_vertices=len(points),mesh_triangles=len(triangles)))
    original=load(ROOT/'verification/fixes/20261102_m4_b3d_anchor_query/fixtures_r2/CASES.json')['rows']
    for case in registration['cases']:
        if case['authored']:continue
        old=next(r for r in original if r['name']==case['name']);assert sha(old['scene'])==old['scene_sha256']
        rows.append(dict(case,scene=old['scene'],scene_sha256=old['scene_sha256'],frame=old['frame']))
    save(args.output/'CASES.json',dict(rows=rows,registration_sha256=sha(args.registration),builder_sha256=sha(Path(__file__)),
        product_geometry_setters=0,scope='QA authors 8 new independent assets; original author files read only'))
    print(json.dumps(dict(fixtures=len(rows),authored=8,original_files_unchanged=True)))


def controller(args):
    sys.path.insert(0,str(args.core_root.resolve()))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_context_qa_binding',args.entry.with_name('target_runtime_entry.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        proof=module.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();module.verify_imported_runtime(proof)
    from human_eye_plugin.small_skin_source_process import SmallSkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    from verification.deformation_anchor_oracle import verify_catalog,anchor_id,selection as anchor_selection
    identity=runtime_identity();assert check_source_drift()['compatible'] and load(args.registration)==catalog()
    fixtures=load(args.fixtures/'CASES.json');assert fixtures['registration_sha256']==sha(args.registration) and fixtures['builder_sha256']==sha(Path(__file__))
    args.output.mkdir(exist_ok=False);binary=Path('D:/Tools/blender5.2/blender.exe');results=[];positive=None
    for case in fixtures['rows']:
        folder=args.output/case['name'];folder.mkdir();actor=None;started=time.perf_counter_ns()
        profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),scene_file=case['scene'],scene_sha256=case['scene_sha256'],
            mesh_name='Cylinder',rig_name='Armature',expected_frame=dict(number=case['frame'],subframe=0.),unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile)
        try:
            actor=SmallSkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();cat=actor.describe_anchors(second,deadline_ns=actor.deadline_ns)
            catalog_truth=verify_catalog(cat,second);target=anchor_id('Armature','Bone' if case['authored'] else 'Bone.001','head')
            baseline_recipe=actor.bind_anchor_selection(first,anchor_selection(cat,target,case['primary']),deadline_ns=actor.deadline_ns)
            primary=actor.analyze(second,deadline_ns=actor.deadline_ns,anchor_query=baseline_recipe)
            operation=policy(cat,target,case);save(folder/'POLICY.json',operation);policy_sha=sha(folder/'POLICY.json')
            actor.set_context_policy(folder/'POLICY.json',policy_sha)
            choice=selection(cat,target,policy_sha);query=actor.bind_context_selection(first,choice,deadline_ns=actor.deadline_ns)
            report=actor.analyze(second,deadline_ns=actor.deadline_ns,context_query=query);audit=json.loads(actor.context_audit_bytes)
            checked=verify_context(report,audit,second,cat,operation,primary)
            expected=case['expected']
            if expected=='selected':assert checked['selected'],(case['name'],report['context_quality'])
            elif expected!='verified_or_kept':assert not checked['selected'] and checked['reason']==expected,(case['name'],report['context_quality'])
            assert actor.sequence==2,'quality cannot add inspect requests'
            save(folder/'CATALOG.json',cat);save(folder/'INDEPENDENT_CATALOG.json',catalog_truth);save(folder/'SELECTION.json',choice);save(folder/'BOUND_QUERY.json',query)
            save(folder/'SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities));save(folder/'PRIMARY.json',primary);save(folder/'REPORT.json',report)
            save(folder/'CONTEXT_AUDIT.json',audit);save(folder/'INDEPENDENT.json',checked)
            if case['name']=='gain_islands':positive=folder
        finally:
            if actor is not None:actor.close()
        assert sha(case['scene'])==case['scene_sha256'] and actor.process.poll() is not None
        row=dict(case=case['name'],passed=True,decision=report['context_quality']['decision'],reason=checked['reason'],
            core_members=len(checked['core_members']),primary_members=len(checked['primary_members']),selected_members=len(checked['selected_members']),
            saved_bytes=checked['bytes']['saved_bytes'],candidates_evaluated=report['context_quality']['candidates_evaluated'],source_file_unchanged=True,
            product_geometry_setters=0,process_reaped=True,complete_QA_process_wall_ns=time.perf_counter_ns()-started)
        results.append(row);save(folder/'RESULT.json',row);print(json.dumps(row),flush=True)
    contract_rows=run_contract(args,positive,SmallSkinSourceProcess)
    cli=run_cli(args,positive);save(args.output/'RESULT.json',dict(schema='deformation-context-native-result-v1',all_passed=True,cases=results,total=len(results),
        contract_cases=contract_rows,contract_total=len(contract_rows),
        cli=cli,runtime_source_sha256=identity['source_sha256'],runtime_count=len(identity['source_files']),harness_sha256=sha(Path(__file__)),
        oracle_sha256=sha(ROOT/'verification/deformation_context_oracle.py'),registration_sha256=sha(args.registration),source_or_installed='installed' if args.entry else 'source',
        formal_model_comparisons=0,scope='8 QA assets + one author sample at two fixed frames; no extra inspections in quality call'))


def run_contract(args,positive,actor_type):
    """All failure reasons are frozen before candidate execution."""
    registration=load(args.registration);folder=args.output/'contract';folder.mkdir();profile=folder/'PROFILE.json';profile.write_bytes((positive/'PROFILE.json').read_bytes())
    actor=None;rows=[]
    def expected(name,call,reason):
        try:call()
        except Exception as exc:
            why=getattr(exc,'code',str(exc));assert why==reason,(name,why,reason)
            row=dict(case=name,passed=True,error=dict(reason=why,status=getattr(exc,'status',None),type=type(exc).__name__))
            rows.append(row);save(folder/(name+'.json'),row);return
        raise AssertionError('expected precise refusal: '+name)
    try:
        actor=actor_type(profile);first=actor.inspect();second=actor.inspect();cat=actor.describe_anchors(second,deadline_ns=actor.deadline_ns)
        original=load(positive/'POLICY.json');assert original['catalog_sha256']==cat['catalog_sha256']
        mutations=dict(cuts_core=lambda p:p['candidate_half_extents_m'].__setitem__(0,[.1]*3),
            enlarges_primary=lambda p:p['candidate_half_extents_m'].__setitem__(0,[3.]*3),
            duplicate=lambda p:p.update(candidate_half_extents_m=[[.5]*3,[.5]*3]),too_many=lambda p:p.update(candidate_half_extents_m=[[.5]*3,[1.]*3,[1.5]*3]),
            bool_half=lambda p:p['required_core_half_extents_m'].__setitem__(0,True),tiny_saved_threshold=lambda p:p.update(min_saved_bytes=255),
            excessive_budget=lambda p:p.update(planning_budget_ms=251),bool_surplus=lambda p:p.update(max_surplus_members=False),extra_field=lambda p:p.update(model_can_override=True))
        for name,mutation in mutations.items():
            value=copy.deepcopy(original);mutation(value);path=folder/(name+'.policy.json');save(path,value)
            expected(name,lambda:actor.set_context_policy(path,sha(path)),registration['policy_negative'][name])
        path=folder/'POLICY.json';path.write_bytes((positive/'POLICY.json').read_bytes());policy_sha=sha(path);actor.set_context_policy(path,policy_sha)
        choice=selection(cat,original['anchor_id'],policy_sha);query=actor.bind_context_selection(first,choice,deadline_ns=actor.deadline_ns)
        changes=dict(policy_sha=lambda s:s.update(policy_sha256='0'*64),catalog=lambda s:s.update(catalog_sha256='0'*64),
            scene=lambda s:s['source_ref'].update(scene_sha256='0'*64),frame=lambda s:s['source_ref']['frame'].update(number=2),
            anchor=lambda s:s.update(anchor_id='bone-anchor:'+'0'*64),untrusted_half=lambda s:s.update(half_extents_m=[.5]*3))
        for name,change in changes.items():
            caller=copy.deepcopy(choice);change(caller)
            expected(name,lambda:actor.bind_context_selection(first,caller,deadline_ns=actor.deadline_ns),registration['selection_negative'][name])
        expected('stale_query',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,context_query=dict(query,expected_source_sha256='0'*64)),registration['direct_negative']['stale_query'])
        expected('mixed_modes',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,context_query=query,anchor_query={}),registration['direct_negative']['mixed_modes'])
        expected('wrong_window',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns+1,context_query=query),registration['direct_negative']['wrong_window'])
        expected('duplicate_configure',lambda:actor.set_context_policy(path,policy_sha),registration['direct_negative']['duplicate_configure'])
        caller=copy.deepcopy(choice);frozen=actor.bind_context_selection(first,caller,deadline_ns=actor.deadline_ns);caller['source_ref']['frame']['number']=777
        assert frozen==query;report=actor.analyze(second,deadline_ns=actor.deadline_ns,context_query=frozen)
        assert report['context_quality']['policy_sha256']==policy_sha;rows.append(dict(case='selection_independence',passed=True))
        save(folder/'SELECTION_INDEPENDENCE_REPORT.json',report)
        before=path.read_bytes();(folder/'POLICY_BEFORE_MUTATION.bin').write_bytes(before);path.write_bytes(before+b' ')
        expected('changed_policy',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,context_query=query),registration['direct_negative']['changed_policy'])
        assert actor.sequence==2
    finally:
        if actor is not None:actor.close()
    assert actor.process.poll() is not None;save(folder/'RESULT.json',dict(all_passed=True,cases=rows,total=len(rows),process_reaped=True));return rows


def run_cli(args,positive):
    """Actual publication bytes/sidecars, with the operator's already-pinned policy."""
    folder=args.output/'cli_publication';folder.mkdir();output=folder/'readback'
    cmd=[sys.executable,*(['-I'] if args.entry else []),'-B',*( [str(args.entry)] if args.entry else ['-m','human_eye_plugin.small_skin_source_process']),
        '--operator-profile',str(positive/'PROFILE.json'),'--output',str(output),'--context-query',str(positive/'SELECTION.json'),
        '--context-policy',str(positive/'POLICY.json'),'--context-policy-sha256',sha(positive/'POLICY.json')]
    started=time.perf_counter_ns();run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,timeout=40);wall=time.perf_counter_ns()-started
    (folder/'STDOUT.txt').write_bytes(run.stdout);(folder/'STDERR.txt').write_bytes(run.stderr)
    save(folder/'EXECUTION.json',dict(command=cmd,exit_code=run.returncode,complete_tool_wall_ns=wall,stdout_sha256=sha(folder/'STDOUT.txt'),actual_subprocess=True))
    assert run.returncode==0,run.stdout.decode('utf8','replace');report=load(output/'REPORT.json');assert run.stdout==payload(report) and run.stdout.isascii()
    assert report['context_quality']['decision']=='selected_context'
    audit=load(output/'CONTEXT_AUDIT.json');publication=load(output/'PUBLICATION.json')
    assert audit['published_publication_bytes']==len(run.stdout) and audit['published_publication_sha256']==hashlib.sha256(run.stdout).hexdigest()
    assert publication['payload_bytes']==len(run.stdout) and publication['payload_sha256']==hashlib.sha256(run.stdout).hexdigest()
    result=dict(passed=True,canonical_ascii_single_lf=True,stdout_bytes=len(run.stdout),stdout_sha256=hashlib.sha256(run.stdout).hexdigest(),publication=publication,
        actual_subprocess=True,complete_tool_wall_ns=wall)
    save(folder/'RESULT.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preregister',action='store_true');mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--registration',type=Path,default=EVIDENCE/'CASES_PREREGISTERED_R2.json')
    parser.add_argument('--fixtures',type=Path);parser.add_argument('--core-root',type=Path,default=ROOT);parser.add_argument('--entry',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.preregister:save(args.output,catalog());print(args.output)
    elif args.builder:builder(args)
    else:controller(args)
