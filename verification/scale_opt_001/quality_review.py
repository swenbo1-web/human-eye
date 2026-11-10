"""Post-run independent O/C quality scoring; no product or host execution.

References the original frozen worldmesh/oracle and pure diagnostic scorer.
All input rows remain in the prescribed 78-cell denominator.  Successful
paired facts and arithmetic work are compared exactly, excluding provenance.
"""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
DIAG=HERE.parent/'scale_diag_001'
HELPER=DIAG/'quality_review.py'
HELPER_SHA='5f9193ffda1bc341f0e47f56fef4e629ba4f305c162fb0ebc7bbab047314f77e'
STATIC=(('G_low','G60_D12','G'),('G_mid','G508','G'),('G_high','G4092','G'),
        ('D_low','G60_D12','D'),('D_mid','D48','D'),('D_high','D192','D'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def helpers():
    if sha(HELPER)!=HELPER_SHA:raise ValueError('frozen_pure_scoring_helper_changed')
    spec=importlib.util.spec_from_file_location('scale_opt_pure_quality_helper',HELPER)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def expected_plan():
    blocks=list(STATIC)+[('T_round_'+str(i),'D48','T') for i in range(3)]
    result=[]
    for block,(cell,scene,mode) in enumerate(blocks):
        order=['O','C'] if block%2==0 else ['C','O']
        for position,group in enumerate(order):
            result.append({'index':len(result),'block':block,'position_in_block':position,
                'pair_order':order,'cell':cell,'scene':scene,'mode':mode,'group':group,
                'round':block-6 if mode=='T' else None,'logical_expected':7 if mode=='T' else 3})
    return result


def first_difference(a,b,path='$'):
    if type(a) is not type(b):return path+':type'
    if isinstance(a,dict):
        if set(a)!=set(b):return path+':keys'
        for key in sorted(a):
            found=first_difference(a[key],b[key],path+'.'+key)
            if found:return found
    elif isinstance(a,list):
        if len(a)!=len(b):return path+':length'
        for i,(x,y) in enumerate(zip(a,b)):
            found=first_difference(x,y,path+'['+str(i)+']')
            if found:return found
    elif a!=b:return path
    return None


def facts(row,mode,q):
    payload=q.product_payload(row['result'])
    if mode=='G':
        value={key:payload[key] for key in ('result_kind','schema_version','status','sets','coverage','measurement_contracts') if key in payload}
        value['target_name']=payload.get('target',{}).get('name')
        value['candidates']=[{key:c[key] for key in ('name','candidate_index','closed_solid_relation',
            'surface_proximity','separation_gap') if key in c} for c in payload.get('candidates',[])]
    else:
        value={key:payload[key] for key in ('result_kind','status','scope','distance_m','best_known_distance_m',
            'unit','coverage','unresolved','measurement_notes') if key in payload}
        value['focal_name']=payload.get('focal',{}).get('name')
        value['nearest_names']=[obj['name'] for obj in payload.get('nearest_objects',[])]
        value['best_known_names']=[obj['name'] for obj in payload.get('best_known_objects',[])]
    details=row.get('meter',{}).get('details',{})
    value['arithmetic_kernels']=[{key:kernel[key] for key in ('kind','faces','vertices','measurement_valid',
        'reason','relation','distance_m','work') if key in kernel} for kernel in details.get('kernels',[])]
    value['admission']=details.get('admission',[])
    value['capture_geometry_work']=[capture.get('work') for capture in details.get('captures',[])]
    return value


def file_bindings(mapping):
    result=[]
    for name,expected in mapping.items():
        path=Path(name);actual=sha(path) if path.is_file() else None
        result.append({'file':str(path),'expected_sha256':expected,'actual_sha256':actual,'valid':actual==expected})
    return result


def install_bindings(installs,q):
    if installs.get('passed') is not True or set(installs.get('versions',{}))!={'O','C'}:raise ValueError('passed_O_C_install_manifest_required')
    result={}
    for group,selected in installs['versions'].items():
        identity=selected['identity'];site=Path(selected['installed_root']);python=Path(selected['python'])
        if not python.is_absolute() or not site.is_absolute() or site.resolve()!=(python.parents[1]/'Lib/site-packages').resolve():raise ValueError('actual_venv_install_path_mismatch:'+group)
        entries=identity['source_files'];actual=[{'path':e['path'],'sha256':sha(site/e['path'])} for e in entries]
        if len(entries)!=137 or len({e['path'] for e in entries})!=137 or actual!=entries or actual!=selected['runtime_source_members']:
            raise ValueError('actual_137_installed_source_mismatch:'+group)
        if identity['source_kind']!='installed_distribution' or identity['source_sha256']!=selected['source_sha256']:raise ValueError('installed_identity_mismatch:'+group)
        digest_input={'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':actual}
        canonical=hashlib.sha256(json.dumps(digest_input,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf8')).hexdigest()
        if canonical!=selected['source_sha256'] or identity['build_id']!='sha256:'+canonical:raise ValueError('independent_installed_canonical_mismatch:'+group)
        result[group]={'valid':True,'source_sha256':canonical,'runtime_source_file_count':137,'installed_root':str(site)}
        if group=='C':
            wheel=Path(selected['wheel'])
            if sha(wheel)!=selected['wheel_sha256']:raise ValueError('candidate_actual_wheel_hash_mismatch')
            with zipfile.ZipFile(wheel) as archive:
                names=[p for p in archive.namelist() if p.endswith('.py')]
                if len(names)!=137 or len(set(names))!=137:raise ValueError('candidate_wheel_duplicate_or_surplus_runtime_members')
                wheel_py={p:hashlib.sha256(archive.read(p)).hexdigest() for p in names}
            if wheel_py!={e['path']:e['sha256'] for e in actual}:raise ValueError('candidate_wheel_runtime_source_mismatch')
            source=Path(selected['source_root'])
            if any(sha(source/name)!=entry['sha256'] for name,entry in selected['source_members'].items()):raise ValueError('candidate_source_snapshot_changed')
            result[group].update(wheel_sha256=sha(wheel),source_snapshot_valid=True)
    old,new=(installs['versions'][g]['identity'] for g in ('O','C'))
    if any(old[k]!=new[k] for k in ('base_version','implementation_revision','distribution_version','protocol_version')):raise ValueError('version_or_method_identity_changed')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE);parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=args.root.resolve();measure=root/'measurements';q=helpers()
    if not (measure/'COMPLETE.json').is_file():raise SystemExit('formal COMPLETE.json required; partial data is not final scoring')
    freeze=q.load(root/'FREEZE.json');installs=q.load(root/'INSTALLS.json');complete=q.load(measure/'COMPLETE.json')
    runs=q.load(measure/'RUNS.json');plan=q.load(measure/'PLAN.json');wanted=expected_plan();issues=[];chains=[];rows=[];raw_rows={};source_cache={}
    frozen=file_bindings(freeze['files_sha256']);shared=file_bindings(freeze['same_fixtures_and_oracle'])
    if not all(row['valid'] for row in frozen+shared):issues.append('frozen_source_or_shared_input_hash_mismatch')
    if freeze.get('accuracy_m')!=1e-6 or freeze.get('logical_cells')!=78:issues.append('frozen_accuracy_or_denominator_mismatch')
    if str(HELPER.resolve()) not in freeze['files_sha256'] or freeze['files_sha256'].get(str(HELPER.resolve()))!=HELPER_SHA:
        issues.append('pure_scoring_dependency_not_bound_by_freeze')
    installation=install_bindings(installs,q)
    if freeze.get('versions')!={g:s['source_sha256'] for g,s in installs['versions'].items()}:issues.append('frozen_installed_versions_mismatch')
    if freeze.get('order')!=wanted or plan.get('chains')!=wanted:issues.append('interleaving_plan_mismatch')
    freeze_sha=sha(root/'FREEZE.json');installs_sha=sha(root/'INSTALLS.json')
    if (plan.get('installs_sha256')!=installs_sha or plan.get('freeze_sha256')!=freeze_sha
            or plan.get('driver_sha256')!=sha(root/'driver.py') or plan.get('shared_inputs_sha256')!=freeze['same_fixtures_and_oracle']):issues.append('plan_input_binding_mismatch')
    if (complete.get('physical_chains')!=18 or complete.get('physical_chains_expected')!=18 or complete.get('logical_expected')!=78
            or complete.get('runs')!=runs or complete.get('stopped_reason') is not None):issues.append('formal_completion_contract_mismatch')
    if len(runs)!=18 or len({run.get('index') for run in runs})!=18:issues.append('duplicate_or_missing_physical_run')
    expected_names={entry['cell']+'_'+entry['group'] for entry in wanted}
    if {p.name for p in measure.iterdir() if p.is_dir()}!=expected_names:issues.append('unexpected_or_missing_chain_directory')
    oracle_data=q.load(DIAG/'ORACLE.json');oracles={s['id']:s for s in oracle_data['snapshots']}
    fixtures={key:q.load(DIAG/'fixtures'/(key+'.json')) for key in oracles}
    for entry in wanted:
        group=entry['group'];mode=entry['mode'];scene=entry['scene'];count=entry['logical_expected'];name=entry['cell']+'_'+group
        selected=installs['versions'][group];directory=measure/name;chain_info={'id':name,'expected_rows':count};errors=[]
        try:
            run=runs[entry['index']]
            if any(run.get(k)!=v for k,v in entry.items()):errors.append('run_does_not_match_frozen_order')
            chain=q.load(directory/'CHAIN.json');actor=q.load(measure/(name+'.actor.json'))
            if any(chain.get(k)!=v for k,v in (('group',group),('source_group','P'),('mode',mode),('scene',scene),('canonical',selected['source_sha256']))):errors.append('chain_version_or_task_mismatch')
            if (actor.get('group')!=group or actor.get('source_group')!='P' or actor.get('canonical')!=selected['source_sha256']
                    or actor.get('installs_sha256')!=installs_sha or actor.get('freeze_sha256')!=freeze_sha
                    or Path(actor['python']).resolve()!=Path(selected['python']).resolve()
                    or Path(actor['python_prefix']).resolve()!=Path(selected['venv']).resolve()
                    or actor.get('actor_os_pid')!=chain.get('actor_os_pid') or actor.get('actor_os_pid')!=run.get('actor_pid')):errors.append('actual_actor_installed_source_or_PID_mismatch')
            version_freeze={'source_canonical':selected['source_sha256'],'accuracy_m':freeze['accuracy_m']}
            identity=q.source_identity(directory,'P',version_freeze,source_cache);chain_info['identity']=identity
            if not identity['valid'] or q.load(directory/'IDENTITY.json')!=selected['identity']:errors.append('actual_source_identity_mismatch')
            if Path(q.load(directory/'CONFIG.json')['project_root']).resolve()!=Path(selected['installed_root']).resolve():errors.append('actual_installed_root_mismatch')
            initial=q.state_binding(directory,'INITIAL',fixtures[scene]);chain_info['initial_binding']=initial
            if not initial['valid']:errors.append('strict_initial_worldmesh_binding_failed')
            if chain.get('file_unchanged') is not True or chain.get('close',{}).get('source_file_unchanged') is not True:errors.append('original_asset_changed_or_unproven')
            if chain.get('close',{}).get('process_reaped') is not True:errors.append('owned_Blender_not_reaped')
            if chain.get('error') is not None:errors.append('physical_chain_error')
            paths=list(directory.glob('MEASUREMENT_*.json'));expected={f'MEASUREMENT_{i}.json' for i in range(count)}
            if {p.name for p in paths}!=expected:errors.append('surplus_or_missing_logical_records')
            if chain.get('rows')!=len(paths) or run.get('recorded_rows')!=len(paths):errors.append('raw_row_count_mismatch')
            chain_info.update(actual_rows=len(paths),actor_pid=actor['actor_os_pid'],venv_launcher_pid=run.get('venv_launcher_pid'),
                owned_blender_pid=chain.get('owned_blender_pid'),run_exit_code=run.get('exit_code'),chain_error=chain.get('error'))
        except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError) as exc:
            errors.append(type(exc).__name__+':'+str(exc));actor={}
        chain_info['errors']=errors;chains.append(chain_info)
        for index in range(count):
            row_id=name+':'+str(index);row_info={'id':row_id,'chain':name,'cell':entry['cell'],'group':group,'mode':mode,'index':index,'cold':index==0,'task_success':False}
            fixture=fixtures['T'+str(index)] if mode=='T' else fixtures[scene];path=directory/f'MEASUREMENT_{index}.json'
            if not path.is_file():
                rows.append(dict(row_info,outcome='not_attempted_missing'));continue
            try:
                row=q.load(path);raw_rows[(entry['cell'],group,index)]=row;row_info['raw_sha256']=sha(path)
                if any(row.get(k)!=v for k,v in (('group',group),('source_group','P'),('mode',mode),('scene',scene),('repeat_or_step',index),('cold',index==0),('canonical',selected['source_sha256']),('actor_os_pid',actor.get('actor_os_pid')))):
                    raise ValueError('logical_record_task_version_or_actor_mismatch')
                request=q.load(directory/f'REQUEST_{index}.json');params=request['params'];arguments=params['arguments']
                if mode=='G':
                    if params['name']!='human_eye_spatial_relations' or arguments!={'target':{'name':'Target'},'candidates':[{'name':'Peer_000'}]}:raise ValueError('explicit_pair_request_mismatch')
                elif params['name']!='human_eye_scene_observe' or arguments.get('query')!={'mode':'surface_nearest','objects':[{'name':'Target'}]} or arguments.get('include_image') is not False:
                    raise ValueError('complete_directory_nearest_request_mismatch')
                binding=q.state_binding(directory,'STATE_'+str(index),fixture) if mode=='T' else None;row_info['state_binding']=binding
                row_info.update(q.answer_score(row,'P',mode,fixture,oracles[fixture['id']],{'accuracy_m':freeze['accuracy_m'],'source_canonical':selected['source_sha256']}))
                row_info['entry_ns']=row.get('entry_ns')
                if errors or binding is not None and not binding['valid']:
                    row_info['answer_outcome_before_binding']=row_info['outcome'];row_info.update(outcome='unverified_binding',task_success=False)
            except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError,StopIteration) as exc:
                row_info.update(outcome='error',reason=type(exc).__name__+':'+str(exc))
            rows.append(row_info)
    if len(rows)!=78 or len({row['id'] for row in rows})!=78:issues.append('fixed_78_cell_denominator_broken')
    recorded=sum(chain.get('actual_rows',0) for chain in chains)
    if complete.get('logical_recorded')!=recorded or complete.get('logical_unexecuted')!=78-recorded:issues.append('recorded_vs_unexecuted_denominator_mismatch')
    by_id={(row['cell'],row['group'],row['index']):row for row in rows};comparisons=[]
    for entry in wanted:
        if entry['group']!='O':continue
        for index in range(entry['logical_expected']):
            cell=entry['cell'];old=by_id[(cell,'O',index)];new=by_id[(cell,'C',index)]
            comparison={'id':cell+':'+str(index),'O_outcome':old['outcome'],'C_outcome':new['outcome']}
            if (old['task_success'] and new['task_success']) or old['outcome']==new['outcome']=='unknown':
                a=facts(raw_rows[(cell,'O',index)],entry['mode'],q);b=facts(raw_rows[(cell,'C',index)],entry['mode'],q)
                difference=first_difference(a,b);comparison.update(comparable=True,scope='successful_facts' if old['task_success'] else 'unknown_reasons_and_work',equal=difference is None,first_difference=difference)
                comparison['O_fact_sha256']=hashlib.sha256(json.dumps(a,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
                comparison['C_fact_sha256']=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
            else:
                comparison.update(comparable=False,scope='completion_changed' if old['task_success']!=new['task_success'] else 'no_common_completed_answer',
                    C_completion_gain=not old['task_success'] and new['task_success'],C_completion_loss=old['task_success'] and not new['task_success'])
            comparisons.append(comparison)
    audit_valid=not issues and all(not chain['errors'] for chain in chains)
    if not audit_valid:
        for row in rows:
            if row['task_success']:row['answer_outcome_before_audit']=row['outcome'];row.update(outcome='unverified_audit',task_success=False)
    summary={}
    for group in ('O','C'):
        selected_rows=[r for r in rows if r['group']==group]
        summary[group]={'denominator':39,'correct':sum(r['task_success'] for r in selected_rows),'outcomes':dict(Counter(r['outcome'] for r in selected_rows)),
            'G_surface_correct':sum(r.get('surface',{}).get('correct',False) for r in selected_rows if r['mode']=='G'),
            'G_solid_correct':sum(r.get('solid',{}).get('correct',False) for r in selected_rows if r['mode']=='G')}
    differences=[c for c in comparisons if c.get('comparable') and not c['equal']]
    completion_losses=sum(c.get('C_completion_loss',False) for c in comparisons)
    value={'schema':'scale-opt-001-independent-quality-review-v1','audit_valid':audit_valid,'denominator':78,'recorded_rows':recorded,
        'quality_preserved':audit_valid and not differences and not completion_losses,
        'accuracy_m':freeze['accuracy_m'],'freeze_sha256':freeze_sha,'installs_sha256':installs_sha,'review_script_sha256':sha(__file__),
        'pure_scoring_dependency':{'path':str(HELPER),'sha256':sha(HELPER)},'shared_oracle':{'path':str(DIAG/'ORACLE.json'),'sha256':sha(DIAG/'ORACLE.json')},
        'frozen_files':frozen,'shared_inputs':shared,'installed_source_binding':installation,'issues':issues,'chains':chains,'summary':summary,'rows':rows,
        'equivalence':{'pairs':len(comparisons),'comparable_pairs':sum(c['comparable'] for c in comparisons),'differences':differences,
            'all_comparable_facts_equal':not differences,'C_completion_gains':sum(c.get('C_completion_gain',False) for c in comparisons),
            'C_completion_losses':completion_losses,'comparisons':comparisons},
        'notes':['No product implementation or oracle executable is imported as an answer',
            'Only original oracle outward L/U bounds are used; the midpoint error field is unused',
            'Unknown/expired/error/unattempted remain in the fixed denominator; no replacement runs',
            'Strict worldmesh/receipt equality includes ordered full objects, vertices, local/world matrices and oriented triangles',
            'Paired fact comparison preserves witnesses, reasons, contracts and arithmetic work; source/trace/document/opaque object IDs and timing are excluded',
            'O deadline without a result and C success is a completion gain, not a geometric-equivalence failure'],
        'new_product_calls':0,'new_native_benchmark_calls':0,'new_Blender_runs':0,'model_calls':0}
    output=args.output or root/'QUALITY_REVIEW.json';output.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'output':str(output),'audit_valid':audit_valid,'summary':summary,'issues':issues,
        'comparable_fact_differences':len(differences),'C_completion_gains':value['equivalence']['C_completion_gains']}))


if __name__=='__main__':main()
