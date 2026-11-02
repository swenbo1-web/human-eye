"""Fixed-coordinate native region QA with SAT/NumPy independent answers.

No task box is derived from a target triangle ID or the product overview.
Native captures remain one author's two static samples, not broad coverage.
"""
import argparse,copy,hashlib,importlib.util,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'verification/fixes/20261102_m4_b3c_region_query'
CONTRACT=EVIDENCE/'CONTRACT_PREREGISTERED.json'
OLD_FIXTURES=ROOT/'verification/fixes/20261102_m4_b3b_product/fixtures_r4/CASES.json'
ERROR_PREFIX='rig_pose_deformation_region_'


def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
def json_bytes(v):return len(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())


def catalog():
    contract=load(CONTRACT)
    return dict(schema='deformation-region-native-cases-v1',contract_sha256=sha(CONTRACT),
        normal=[dict(name=frame+'_'+region,fixture=frame,region=region) for frame in ('frame1','frame25') for region in contract['regions']],
        source_cases=[dict(name='missing_weights_whole',fixture='missing_weights',region='whole_mesh'),
            dict(name='bezier_source_unknown',fixture='bezier_interval',expected_status='unknown',expected_reason='small_skin_curve_interpolation')],
        negative=dict(wrong_coordinate_space=ERROR_PREFIX+'region_kind',invalid_extent=ERROR_PREFIX+'region_extent',
            wrong_scene=ERROR_PREFIX+'stale_selection',wrong_frame=ERROR_PREFIX+'stale_selection',wrong_rig=ERROR_PREFIX+'stale_selection',
            wrong_mesh=ERROR_PREFIX+'stale_selection',stale_capture=ERROR_PREFIX+'stale_source',mixed_modes='rig_pose_deformation_query_modes',
            changed_analysis_window='small_skin_analysis_window'),
        positive_contract=['selection_deep_copy'],
        oracle='exact Fraction 13-axis SAT and independent NumPy QR/SVD/centered singular-scale error model; no production selector or metric answers',
        metric_atol=1e-9,original_file_unchanged=True,no_product_setters=True,no_product_saves=True,
        task_scope='explicit world-coordinate whole-triangle retrieval; no semantic localization, clipped integral, damage or model-benefit claim')


def stable_selection(packet,region):
    digest=lambda name:'blender:'+hashlib.sha256(json.dumps(['',name],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    return dict(schema='surface-deformation-region-selection-v1',source_ref=dict(scene_sha256=packet['identity']['scene_sha256'],
        rig_object_id=digest(packet['inputs']['rig']['name']),mesh_object_id=digest(packet['inputs']['mesh']['name']),frame=copy.deepcopy(packet['inputs']['frame'])),
        region=copy.deepcopy(region))


def verify_report(report,packet,region,overview):
    import numpy as np
    from verification.deformation_region_oracle import matching_indices,all_facts,transformed_vertices
    expected=matching_indices(packet,region['bounds']);facts=all_facts(packet,expected);result=report['region_query']
    assert result['schema']=='surface-deformation-region-result-v1' and result['source_sha256']==packet['source_sha256']
    assert result['region']==region and result['membership_complete'] is True
    assert result['matched_triangle_indices']==expected and result['triangles_total']==len(expected)
    assert result['triangles_scanned']==len(packet['inputs']['mesh']['triangles']) and result['vertices_transformed']==len(packet['inputs']['mesh']['vertices'])
    assert result['coordinate_model']=='exact_rational_affine_from_binary_inputs' and result['selection_rule']=='closed_current_triangle_hull_intersects_box'
    assert result['metric_scope']=='whole_original_triangles_not_clipped_integrals' and result['extrema_scope']=='measured_and_collapsed_members_only'
    states={state:sum(row['state']==state for row in facts.values()) for state in ('measured','collapsed','unknown')}
    for state,count in states.items():assert result['triangles_'+state]==count,(state,result,count)
    reasons={r:sum(row['reason']==r for row in facts.values() if row['state']=='unknown') for r in sorted({v['reason'] for v in facts.values() if v['state']=='unknown'})}
    assert result['unknown_reasons']==reasons
    assert result['status']==('empty' if not expected else 'partial' if states['unknown'] else 'observed')
    assert result['all_members_measurable']==bool(expected and not states['unknown'])
    measurable={i:f for i,f in facts.items() if f['state'] in ('measured','collapsed')}
    extrema=result['metric_extrema'];assert set(extrema)=={'max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio'}
    detailed=[]
    for name,position,operation in [('max_principal_stretch',0,max),('min_principal_stretch',1,min),('min_area_ratio',None,min),('max_area_ratio',None,max)]:
        witness=extrema[name]
        if not measurable:assert witness is None;continue
        assert set(witness)=={'triangle','value'} and type(witness['triangle']) is int and witness['triangle'] in measurable
        field=lambda f:f['area_ratio'] if position is None else f['principal_stretches'][position]
        optimum=operation(field(f) for f in measurable.values())
        assert abs(witness['value']-optimum)<1e-9 and abs(witness['value']-field(measurable[witness['triangle']]))<1e-9
        if witness['triangle'] not in detailed:detailed.append(witness['triangle'])
    unknown=[i for i in expected if facts[i]['state']=='unknown']
    for index in ([unknown[0]] if unknown else [])+expected:
        if len(detailed)>=4:break
        if index not in detailed:detailed.append(index)
    assert [row['triangle'] for row in result['triangles']]==detailed
    assert result['details_omitted']==len(expected)-len(detailed)
    assert result['detail_policy']=='extrema_witnesses_then_smallest_unknown_then_remaining_ids'
    vertices=transformed_vertices(packet['evaluated']['vertices'],packet['evaluated']['mesh_matrix_world'],packet['inputs']['unit_scale_m'])
    for row in result['triangles']:
        wanted=facts[row['triangle']]
        for key in ('triangle','vertices','state','reason','unweighted_vertices','reference_geometry','current_geometry'):assert row[key]==wanted[key],(key,row,wanted)
        if wanted['state']=='unknown':assert row['principal_stretches'] is None and row['area_ratio'] is None
        else:
            np.testing.assert_allclose(row['principal_stretches'],wanted['principal_stretches'],atol=1e-9,rtol=0)
            assert abs(row['area_ratio']-wanted['area_ratio'])<1e-9
        points=np.asarray([[float(v) for v in vertices[i]] for i in wanted['vertices']])
        np.testing.assert_allclose(row['centroid_world_m'],points.mean(axis=0),atol=1e-10,rtol=0)
        np.testing.assert_allclose(row['bounds_world_m'],[points.min(axis=0),points.max(axis=0)],atol=1e-10,rtol=0)
    assert report['execution_authority'] is False and report['geometry_setters']==0 and report['original_file_saved'] is False
    assert report['damage_classification']=='not_inferred' and report['source']['source_kind']=='small-skin-source-snapshot-v1'
    assert report['triangles']==[] and report['triangles_omitted']==report['triangles_total']
    assert report['global_detail_scope']=='omitted_for_requested_region'
    expected_overview=copy.deepcopy(overview);expected_overview.update(triangles=[],triangles_omitted=overview['triangles_total'],global_detail_scope='omitted_for_requested_region')
    only_global=copy.deepcopy(report);only_global.pop('region_query');assert only_global==expected_overview
    return dict(matched_triangle_indices=expected,triangles_total=len(expected),states=states,unknown_reasons=reasons,
        extrema_independently_checked=True,detailed_triangle_indices=detailed,details_omitted=len(expected)-len(detailed),
        facts={str(k):v for k,v in facts.items()},numeric_extrema_tolerance=1e-9,
        witness_note='Identity choices near tied metrics may differ by floating rounding; every actual witness and extremum is independently checked within 1e-9.')


def error_value(exc):return dict(type=type(exc).__name__,status=getattr(exc,'status',None),reason=getattr(exc,'code',str(exc)))
def expect_error(call,reason):
    try:call()
    except Exception as exc:
        error=error_value(exc);assert error['reason']==reason,(error,reason);return error
    raise AssertionError('expected exact refusal: '+reason)


def run_contract(folder,profile,actor_type,registration,region):
    folder.mkdir();save(folder/'PROFILE.json',profile);rows=[];actor=None;old_query=None
    try:
        actor=actor_type(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect()
        selection=stable_selection(first,region);old_query=actor.bind_region_selection(first,selection,deadline_ns=actor.deadline_ns)
        changes={
            'wrong_coordinate_space':lambda s:s['region'].update(coordinate_space='reference_local'),
            'invalid_extent':lambda s:s['region']['bounds'].__setitem__(1,s['region']['bounds'][0][:]),
            'wrong_scene':lambda s:s['source_ref'].update(scene_sha256='0'*64),
            'wrong_frame':lambda s:s['source_ref']['frame'].update(number=s['source_ref']['frame']['number']+1),
            'wrong_rig':lambda s:s['source_ref'].update(rig_object_id='blender:'+'0'*64),
            'wrong_mesh':lambda s:s['source_ref'].update(mesh_object_id='blender:'+'0'*64),
        }
        for name,change in changes.items():
            value=copy.deepcopy(selection);change(value)
            error=expect_error(lambda:actor.bind_region_selection(first,value,deadline_ns=actor.deadline_ns),registration['negative'][name])
            row=dict(case=name,passed=True,error=error);rows.append(row);save(folder/(name+'.json'),row)
        for name,call in [
            ('mixed_modes',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns,query=dict(schema='surface-deformation-query-v1',expected_source_sha256=second['source_sha256'],triangle_indices=[0]),region_query=old_query)),
            ('changed_analysis_window',lambda:actor.analyze(second,deadline_ns=actor.deadline_ns+1,region_query=old_query))]:
            error=expect_error(call,registration['negative'][name]);row=dict(case=name,passed=True,error=error);rows.append(row);save(folder/(name+'.json'),row)
        caller=copy.deepcopy(selection);saved=copy.deepcopy(caller)
        bound=actor.bind_region_selection(first,caller,deadline_ns=actor.deadline_ns)
        caller['region']['bounds'][0][0]-=1
        assert bound['region']==saved['region'];before=copy.deepcopy(bound)
        report=actor.analyze(second,deadline_ns=actor.deadline_ns,region_query=bound)
        assert bound==before and report['region_query']['region']==saved['region']
        save(folder/'SELECTION_COPY_REPORT.json',report);rows.append(dict(case='selection_deep_copy',passed=True))
        save(folder/'OLD_QUERY.json',old_query)
    finally:
        if actor is not None:actor.close()
    assert actor.process.poll() is not None
    fresh=None;freshdir=folder/'fresh_capture';freshdir.mkdir();save(freshdir/'PROFILE.json',profile)
    try:
        fresh=actor_type(freshdir/'PROFILE.json');packet=fresh.inspect()
        assert packet['source_sha256']!=old_query['expected_source_sha256']
        error=expect_error(lambda:fresh.analyze(packet,deadline_ns=fresh.deadline_ns,region_query=old_query),registration['negative']['stale_capture'])
        row=dict(case='stale_capture',passed=True,error=error,new_source_sha256=packet['source_sha256'],old_source_sha256=old_query['expected_source_sha256'])
        rows.append(row);save(freshdir/'RESULT.json',row)
    finally:
        if fresh is not None:fresh.close()
    assert fresh.process.poll() is not None
    save(folder/'RESULT.json',dict(cases=rows,total=len(rows),all_passed=True,processes_reaped=True));return rows


def controller(args):
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(args.core_root.resolve()))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_region_qa_target',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
        assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin.small_skin_source_process import SmallSkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    assert check_source_drift()['compatible'];identity=runtime_identity();registration=load(args.registration);assert registration==catalog()
    contract=load(CONTRACT);fixtures={r['name']:r for r in load(OLD_FIXTURES)['rows']}
    tasks=registration['normal']+registration['source_cases'];args.output.mkdir(exist_ok=False);rows=[]
    binary=Path('D:/Tools/blender5.2/blender.exe');normal_profile=None
    for task in tasks:
        name=task['name'];case=fixtures[task['fixture']];folder=args.output/name;folder.mkdir();actor=None;error=None;report=None;first=None
        profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],mesh_name='Cylinder',rig_name='Armature',expected_frame=dict(number=case['frame'],subframe=0.),
            unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);started=time.perf_counter_ns();independent=None
        try:
            actor=SmallSkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect()
            assert first['source_sha256']==second['source_sha256']
            if 'region' in task:
                region=dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=copy.deepcopy(contract['regions'][task['region']]))
                selection=stable_selection(first,region);bound=actor.bind_region_selection(first,selection,deadline_ns=actor.deadline_ns)
                overview=actor.analyze(second,deadline_ns=actor.deadline_ns)
                report=actor.analyze(second,deadline_ns=actor.deadline_ns,region_query=bound)
                independent=verify_report(report,second,region,overview)
                assert json_bytes(report)<=contract['lifecycle']['report_bytes']
                save(folder/'SELECTION.json',selection);save(folder/'BOUND_QUERY.json',bound);save(folder/'OVERVIEW.json',overview)
                save(folder/'REPORT.json',report);save(folder/'INDEPENDENT.json',independent)
                save(folder/'SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities))
                if task['fixture']=='frame1':normal_profile=profile
        except Exception as exc:error=error_value(exc)
        finally:
            if actor is not None:actor.close()
        assert sha(Path(case['scene']))==case['scene_sha256']
        if 'expected_reason' in task:
            assert error and error['reason']==task['expected_reason'] and error['status']==task['expected_status'] and report is None,(name,error)
        else:assert error is None and report is not None,(name,error)
        row=dict(case=name,passed=True,error=error,original_file_unchanged=True,product_setters=0,product_saves=False,
            complete_process_wall_ns=time.perf_counter_ns()-started,process_reaped=actor is None or actor.process.poll() is not None)
        if report is not None:
            row.update(region_status=report['region_query']['status'],matched=len(independent['matched_triangle_indices']),
                measured=independent['states']['measured'],unknown=independent['states']['unknown'],collapsed=independent['states']['collapsed'],
                details=len(independent['detailed_triangle_indices']),details_omitted=independent['details_omitted'],
                default_report_json_bytes=json_bytes(overview),region_report_json_bytes=json_bytes(report))
        rows.append(row);save(folder/'RESULT.json',row);print(json.dumps(row),flush=True)
    region=dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=contract['regions']['center_slab'])
    checks=run_contract(args.output/'contract',normal_profile,SmallSkinSourceProcess,registration,region)
    result=dict(schema='deformation-region-native-result-v1',runtime_source_sha256=identity['source_sha256'],runtime_source_count=len(identity['source_files']),
        source_or_installed='installed' if args.entry else 'source',harness_sha256=sha(Path(__file__)),oracle_sha256=sha(ROOT/'verification/deformation_region_oracle.py'),
        contract_sha256=sha(CONTRACT),registration_sha256=sha(args.registration),cases=rows,total=len(rows),contract_cases=checks,contract_total=len(checks),all_passed=True,
        formal_model_comparisons=0,scope=registration['task_scope'],geometry_membership='independent SAT full input; no overview-derived selection')
    save(args.output/'RESULT.json',result);print(json.dumps(dict(all_passed=True,total=len(rows),contract=len(checks),runtime_source_sha256=identity['source_sha256'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preregister',action='store_true');mode.add_argument('--controller',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--registration',type=Path,default=EVIDENCE/'CASES_PREREGISTERED.json')
    parser.add_argument('--core-root',type=Path,default=ROOT);parser.add_argument('--entry',type=Path)
    args=parser.parse_args()
    if args.preregister:save(args.output,catalog());print(args.output)
    else:controller(args)
