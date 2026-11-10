"""Independent, post-run scoring of the frozen SCALE-DIAG-001 directory.

No Blender, product module, measured Native implementation or oracle code is
imported.  The final oracle's outward L/U bounds, never its midpoint error
field, are used.  Missing and surplus records cannot change the denominator.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
STATIC=(('G_low','G60_D12','G'),('G_mid','G508','G'),('G_high','G4092','G'),
        ('D_low','G60_D12','D'),('D_mid','D48','D'),('D_high','D192','D'))


def decode(value):
    # Reject duplicate JSON keys instead of accepting the last apparent row.
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_json_key:'+key)
            result[key]=value
        return result
    return json.loads(value,object_pairs_hook=unique,
                      parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite_json:'+value)))


def load(path):return decode(Path(path).read_bytes())


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_chains():
    return [(name+'_'+group,scene,mode,group,3) for name,scene,mode in STATIC for group in ('N','P')]+[
        ('T_round_%d_%s'%(round_,group),'D48','T',group,7) for round_ in range(3) for group in ('N','P')]


def receipt_payload(value):
    response=value['response']
    if response.get('status')!='success' or response['result'].get('executed') is not True:
        raise ValueError('receipt_not_successful_execution')
    result=response['result']['result']
    if not isinstance(result,str):raise ValueError('receipt_json_text_required')
    return decode(result)


def product_payload(value):
    if value.get('jsonrpc')!='2.0' or 'error' in value:raise ValueError('jsonrpc_error_or_wrong_version')
    envelope=value['result'];content=envelope['content']
    if len(content)!=1 or content[0].get('type')!='text':raise ValueError('one_product_text_payload_required')
    payload=decode(content[0]['text'])
    if envelope.get('isError') and payload.get('status') in ('complete','observed'):
        raise ValueError('success_payload_in_error_envelope')
    return payload


def distance_score(value,lower,upper,tolerance):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        return {'correct':False,'reason':'finite_nonnegative_distance_required','reported_m':value}
    # For every possible true value inside the outward interval, this remains
    # within tolerance.  The frozen midpoint/half-width field is unused.
    error=max(abs(value-lower),abs(value-upper))
    return {'correct':error<=tolerance,'reported_m':value,'oracle_lower_m':lower,
            'oracle_upper_m':upper,'worst_case_error_m':error}


def logical_ids(names,objects):
    if not isinstance(names,list) or len(set(names))!=len(names):raise ValueError('winner_names_not_unique_list')
    table={}
    for obj in objects:
        if obj['name'] in table:raise ValueError('ambiguous_actual_object_name')
        table[obj['name']]=obj['logical_id']
    if any(name not in table for name in names):raise ValueError('winner_not_in_actual_complete_directory')
    return sorted(table[name] for name in names)


def answer_score(row,group,mode,fixture,oracle,freeze):
    result=row.get('result');exc=row.get('exception')
    if exc:
        kind='timeout' if 'timeout' in (str(exc.get('type',''))+' '+str(exc.get('message',''))).lower() or 'timed out' in str(exc.get('message','')).lower() else 'error'
        return {'outcome':kind,'task_success':False,'exception':exc}
    if result is None:return {'outcome':'error','task_success':False,'reason':'no_result_or_exception'}
    payload=result if group=='N' else product_payload(result)
    status=payload.get('status');complete=(status=='complete') if mode!='G' else status in ('complete','observed')
    if status=='expired' and payload.get('code')=='live_request_expired':
        return {'outcome':'timeout','task_success':False,'reported_status':status,
            'timeout_kind':'cooperative_entry_deadline_expired','budget_stage':payload.get('budget_stage'),
            'code':payload['code'],'tool_outcome':payload.get('tool_outcome'),'error':payload.get('error')}
    if status=='error':return {'outcome':'error','task_success':False,'reported_status':status,'error':payload.get('error')}
    output={'reported_status':status,'task_success':False}
    if group=='P':
        binding=payload.get('binding',{}) if mode!='G' else payload.get('context',{})
        output['result_source_binding_valid']=binding.get('runtime_source_sha256')==freeze['source_canonical']
    else:output['result_source_binding_valid']=True
    if mode=='G':
        peer=fixture['peer_id'];pair=next(p for p in oracle['pairs'] if p['candidate']==peer)
        if group=='N':
            surface_valid=status=='complete';distance=payload.get('distance_m');solid=payload.get('solid') or {}
            names=payload.get('nearest_names',[]);relation=solid.get('relation');solid_valid=solid.get('status')=='measured'
        else:
            candidates=payload.get('candidates',[])
            if len(candidates)!=1:raise ValueError('G_requires_one_explicit_candidate')
            candidate=candidates[0];surface=candidate.get('surface_proximity',{});solid=candidate.get('closed_solid_relation',{})
            surface_valid=surface.get('status')=='measured';distance=(surface.get('value') or {}).get('distance_m')
            names=[candidate['name']];relation=solid.get('value');solid_valid=solid.get('status')=='measured'
            output['surface_reason']=surface.get('reason');output['solid_reason']=solid.get('reason')
        output['logical_winner_ids']=logical_ids(names,fixture['objects']);identity_ok=output['logical_winner_ids']==[peer]
        surface=distance_score(distance,pair['distance_lower_m'],pair['distance_upper_m'],freeze['accuracy_m'])
        surface['correct']=surface_valid and pair['surface_distance_qualified'] and surface['correct'] and identity_ok
        output['surface']=surface
        output['solid']={'reported':relation,'oracle':pair.get('solid_relation'),
            'correct':solid_valid and pair['relation_qualified'] and relation==pair['solid_relation'] and identity_ok}
        output['task_success']=complete and surface['correct'] and output['solid']['correct'] and output['result_source_binding_valid']
    else:
        expected=oracle['global_nearest_unsigned'];names=payload.get('nearest_names',[]) if group=='N' else [obj['name'] for obj in payload.get('nearest_objects',[])]
        output['logical_winner_ids']=logical_ids(names,fixture['objects'])
        output['winner_correct']=expected['complete'] and output['logical_winner_ids']==sorted(expected['nearest_ids'])
        n=len(fixture['objects'])-1
        if group=='N':coverage_ok=payload.get('work',{}).get('directory_objects')==n+1
        else:
            coverage=payload.get('coverage',{});output['coverage']=coverage
            coverage_ok=(coverage.get('targets_excluding_focal')==n and coverage.get('unresolved')==0
                and coverage.get('distance_valid',-1)>=0 and coverage.get('strictly_excluded',-1)>=0
                and coverage.get('distance_valid',-1)+coverage.get('strictly_excluded',-1)==n and payload.get('unresolved')==[])
            opaque=[o.get('id') for o in payload.get('nearest_objects',[])]
            coverage_ok=coverage_ok and bool(opaque) and all(isinstance(i,str) and i for i in opaque) and len(set(opaque))==len(opaque)
        output['complete_directory_claim_valid']=coverage_ok
        output['surface']=distance_score(payload.get('distance_m'),expected['distance_lower_m'],expected['distance_upper_m'],freeze['accuracy_m'])
        output['task_success']=complete and output['winner_correct'] and coverage_ok and output['surface']['correct'] and output['result_source_binding_valid']
    output['outcome']='correct' if output['task_success'] else ('unknown' if status=='unknown' else 'incomplete' if status in ('partial','incomplete') else 'incorrect')
    return output


def state_binding(directory,stem,fixture):
    path=directory/(stem+'.json');receipt=directory/(stem+'_RECEIPT.json')
    if not path.is_file() or not receipt.is_file():return {'valid':False,'reason':'missing_complete_state_or_receipt'}
    actual=load(path);wanted={key:fixture[key] for key in ('unit_scale_m','objects')}
    captured=receipt_payload(load(receipt))
    valid=actual==wanted and captured==actual
    return {'valid':valid,'strict_all_fields_equal':actual==wanted,'receipt_matches':captured==actual,
            'actual_sha256':sha(path),'receipt_sha256':sha(receipt),
            'scope':'complete ordered object list, names, logical identities, local/world vertices, matrices and oriented triangles; no coordinate tolerance'}


def source_identity(directory,group,freeze,cache):
    identity=load(directory/'IDENTITY.json')
    if group=='N':
        valid=identity.get('native_source_sha256')==freeze['files']['native_impl.py']
        return {'valid':valid,'native_source_sha256':identity.get('native_source_sha256')}
    config=load(directory/'CONFIG.json');root=Path(config['project_root']);rows=identity.get('source_files',[])
    failures=[];paths=[]
    for row in rows:
        name=row['path'];paths.append(name);path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):failures.append(name+':outside_distribution');continue
        if path not in cache:cache[path]=sha(path) if path.is_file() else None
        if cache[path]!=row['sha256']:failures.append(name+':source_hash_mismatch')
    valid=(identity.get('source_sha256')==freeze['source_canonical']
        and identity.get('source_kind')=='installed_distribution'
        and identity.get('build_id')=='sha256:'+freeze['source_canonical']
        and config.get('expected_identity',{}).get('source_sha256')==freeze['source_canonical']
        and len(paths)==137 and len(set(paths))==len(paths) and not failures)
    return {'valid':valid,'source_sha256':identity.get('source_sha256'),'verified_source_file_count':len(rows),'failures':failures}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE)
    parser.add_argument('--output',type=Path);args=parser.parse_args();root=args.root;measure=root/'measurements'
    if not (measure/'COMPLETE.json').is_file():raise SystemExit('formal COMPLETE.json required; partial data is not a final review')
    freeze=load(root/'FREEZE.json');oracle_data=load(root/'ORACLE.json');oracle={s['id']:s for s in oracle_data['snapshots']}
    fixtures={s['id']:load(root/'fixtures'/(s['id']+'.json')) for s in oracle_data['snapshots']}
    issues=[];frozen=[];cache={};rows=[];chains=[]
    for name,expected in freeze['files'].items():
        path=root/name;actual=sha(path) if path.is_file() else None
        frozen.append({'file':name,'valid':actual==expected,'expected_sha256':expected,'actual_sha256':actual})
    freeze_valid=all(row['valid'] for row in frozen)
    if not freeze_valid:issues.append('frozen_source_or_fixture_hash_mismatch')
    complete=load(measure/'COMPLETE.json');runs=load(measure/'RUNS.json');plan=expected_chains();expected_names={p[0] for p in plan}
    if complete.get('physical_chains')!=18 or complete.get('logical_expected')!=78 or complete.get('runs')!=runs:
        issues.append('completion_or_runs_contract_mismatch')
    run_names=[]
    for run in runs:
        run_names.append(run['cell']+'_'+run['group'])
    if len(runs)!=18 or len(set(run_names))!=18 or set(run_names)!=expected_names:issues.append('surplus_missing_or_duplicate_physical_chain')
    actual_names={p.name for p in measure.iterdir() if p.is_dir()}
    if actual_names!=expected_names:issues.append('unexpected_or_missing_measurement_directory')
    for name,scene,mode,group,count in plan:
        directory=measure/name;chain_info={'id':name,'expected_rows':count};chain_errors=[]
        try:
            chain=load(directory/'CHAIN.json');run=next(r for r in runs if r['cell']+'_'+r['group']==name)
            if any(chain.get(k)!=v or run.get(k)!=v for k,v in (('group',group),('mode',mode),('scene',scene))):chain_errors.append('chain_identity_mismatch')
            identity=source_identity(directory,group,freeze,cache);chain_info['identity']=identity
            if not identity['valid']:chain_errors.append('source_identity_mismatch')
            initial=state_binding(directory,'INITIAL',fixtures[scene]);chain_info['initial_binding']=initial
            if not initial['valid']:chain_errors.append('initial_worldmesh_binding_failed')
            if chain.get('file_unchanged') is not True or chain.get('close',{}).get('source_file_unchanged') is not True:
                chain_errors.append('original_asset_changed_or_unproven')
            if chain.get('close',{}).get('process_reaped') is not True:chain_errors.append('owned_process_not_reaped')
            files=list(directory.glob('MEASUREMENT_*.json'));wanted={f'MEASUREMENT_{i}.json' for i in range(count)}
            extras=[p.name for p in files if p.name not in wanted]
            if extras:chain_errors.append('surplus_measurement_rows:'+','.join(extras))
            if chain.get('rows')!=len(files):chain_errors.append('chain_row_count_disagrees_with_records')
            chain_info.update(actual_rows=len(files),chain_error=chain.get('error'),run_exit_code=run.get('exit_code'))
        except (ValueError,KeyError,TypeError,OSError,StopIteration,IndexError,AttributeError) as exc:
            chain_errors.append(type(exc).__name__+':'+str(exc));chain={}
        chain_info['errors']=chain_errors;chains.append(chain_info)
        for index in range(count):
            row_info={'id':name+':'+str(index),'chain':name,'group':group,'mode':mode,'index':index,'cold':index==0,'task_success':False}
            path=directory/f'MEASUREMENT_{index}.json';fixture=fixtures['T'+str(index)] if mode=='T' else fixtures[scene]
            certificate=oracle[fixture['id']];binding=None
            if not path.is_file():
                poison=(directory/'native/POISONED.json').is_file()
                prev=load(directory/'MEASUREMENT_0.json') if (directory/'MEASUREMENT_0.json').is_file() else {}
                timeout=prev.get('exception',{}).get('type')=='TimeoutError' if prev.get('exception') else False
                allowed=name=='G_high_N' and index in (1,2) and poison and timeout
                row_info.update(outcome='not_attempted_session_poisoned' if allowed else 'not_attempted_missing',poisoned_marker=poison)
                if not allowed:issues.append('unexplained_missing_row:'+row_info['id'])
                rows.append(row_info);continue
            try:
                row=load(path);row_info['raw_sha256']=sha(path)
                if any(row.get(k)!=v for k,v in (('group',group),('mode',mode),('scene',scene),('repeat_or_step',index),('cold',index==0))):raise ValueError('logical_row_identity_mismatch')
                if mode=='T':binding=state_binding(directory,'STATE_'+str(index),fixture)
                row_info['state_binding']=binding
                if group=='N' and row.get('exception') is None:
                    if receipt_payload(load(directory/f'NATIVE_RECEIPT_{index}.json'))!=row.get('result'):raise ValueError('native_receipt_result_mismatch')
                if group=='P':
                    req=load(directory/f'REQUEST_{index}.json');params=req.get('params',{});query=params.get('arguments',{})
                    if mode=='G':
                        wanted={'target':{'name':next(o['name'] for o in fixture['objects'] if o['logical_id']==fixture['target_id'])},'candidates':[{'name':next(o['name'] for o in fixture['objects'] if o['logical_id']==fixture['peer_id'])}]}
                        if params.get('name')!='human_eye_spatial_relations' or query!=wanted:raise ValueError('explicit_pair_request_mismatch')
                    elif params.get('name')!='human_eye_scene_observe' or query.get('query')!={'mode':'surface_nearest','objects':[{'name':'Target'}]} or query.get('include_image') is not False:
                        raise ValueError('nearest_complete_directory_request_mismatch')
                row_info.update(answer_score(row,group,mode,fixture,certificate,freeze))
                row_info['entry_ns']=row.get('entry_ns')
                if not freeze_valid or chain_errors or binding is not None and not binding['valid']:
                    row_info['answer_outcome_before_binding']=row_info['outcome'];row_info.update(outcome='unverified_binding',task_success=False)
                    for field in ('surface','solid'):
                        if field in row_info:
                            row_info[field]['answer_correct_before_binding']=row_info[field]['correct'];row_info[field]['correct']=False
            except (ValueError,KeyError,TypeError,OSError,StopIteration,IndexError,AttributeError) as exc:
                row_info.update(outcome='error',reason=type(exc).__name__+':'+str(exc))
            rows.append(row_info)
    if len(rows)!=78 or len({r['id'] for r in rows})!=78:issues.append('fixed_78_denominator_or_unique_ids_broken')
    # Surplus input is an audit failure, never silently zipped away.  The fixed
    # rows remain in the report even when the audit itself is invalid.
    audit_valid=not issues and all(not chain['errors'] for chain in chains)
    if not audit_valid:
        for row in rows:
            if row['task_success']:
                row['answer_outcome_before_audit']=row['outcome'];row.update(outcome='unverified_audit',task_success=False)
    summary={}
    for group in ('N','P'):
        selected=[r for r in rows if r['group']==group]
        summary[group]={'denominator':39,'correct':sum(r['task_success'] for r in selected),'outcomes':dict(Counter(r['outcome'] for r in selected)),
            'G_surface_correct':sum(r.get('surface',{}).get('correct',False) for r in selected if r['mode']=='G'),
            'G_solid_correct':sum(r.get('solid',{}).get('correct',False) for r in selected if r['mode']=='G')}
    result={'schema':'scale-diag-independent-quality-review-v1','complete_input_required':True,'audit_valid':audit_valid,
        'denominator':78,'accuracy_m':freeze['accuracy_m'],'freeze_sha256':sha(root/'FREEZE.json'),
        'oracle_sha256':sha(root/'ORACLE.json'),'review_script_sha256':sha(Path(__file__)),
        'frozen_files':frozen,'issues':issues,'chains':chains,'summary':summary,'rows':rows,
        'scoring_notes':['G surface and solid are independent fields; G task completion requires both',
            'D/T require complete full-directory coverage, all correct logical winners, finite distance within accuracy',
            'only outward oracle L/U are used; the frozen midpoint/half-width field is not used',
            'strict full worldmesh equality includes oriented triangle order; no geometry tolerance or filtering',
            'two G_high_N warm cells remain not_attempted_session_poisoned after the cold timeout',
            'unknown, error, timeout and unattempted remain in the fixed denominator; no replacement samples'],
        'new_product_calls':0,'new_native_benchmark_calls':0,'new_Blender_runs':0,'model_calls':0}
    output=args.output or root/'QUALITY_REVIEW.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'output':str(output),'audit_valid':audit_valid,'summary':summary,'issues':issues}))


if __name__=='__main__':main()
