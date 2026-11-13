"""Independent read-only audit of existing replay inputs/results/ZIPs.
No author module, matcher, archive function or request code is executed.
"""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import zipfile

BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001')
OLD=BASE.parent/'m4_active_coverage_consumption_001'
OUT=Path(__file__).resolve().parent
FIX=BASE/'fixtures'
RUN=BASE/'offline/a01'
checks=[];inputs={};summaries=[]
def raw(p):
    p=Path(p);data=p.read_bytes();inputs[str(p)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};return data
def doc(p):return json.loads(raw(p))
def digest(b):return hashlib.sha256(b).hexdigest()
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail})
def equal(name,a,b):check(name,canon(a)==canon(b))

manifest=doc(BASE/'FIXTURE_MANIFEST.json');cases=doc(BASE/'CASES.json')['cases'];result=doc(RUN/'RESULTS.json')
records=manifest['records'];by_case={c['case_id']:c for c in result['cases']}
check('15_unique_original_transactions',len(records)==len({r['fixture_id'] for r in records})==15)
check('47_unique_registered_cases',len(cases)==len({c['case_id'] for c in cases})==47)
equal('registered_and_actual_order',[c['case_id'] for c in cases],[c['case_id'] for c in result['cases']])
equal('case_scope_counts',Counter(c['scope'] for c in cases),{'pipeline':45,'matcher':2})
equal('real_original_classes',Counter(r['expected_classification'] for r in records),{'success':13,'tool_error':2})
for row in records:
    ident=row['fixture_id'];request=doc(FIX/row['request']);response=doc(FIX/row['response'])
    line=raw(FIX/row['CLI_completed']);event=json.loads(line);item=event['item']
    stream=raw(row['CLI_stdout_source']);lines=stream.splitlines(keepends=True);n=row['CLI_raw_line_number']-1
    check(ident+'/raw_stdout_digest',digest(stream)==row['CLI_stdout_sha256'])
    check(ident+'/line_byte_offset',sum(len(x) for x in lines[:n])==row['CLI_raw_byte_offset'])
    check(ident+'/raw_line_exact',lines[n]==line and stream[row['CLI_raw_byte_offset']:row['CLI_raw_byte_offset']+len(line)]==line)
    check(ident+'/raw_line_digest',digest(line)==row['CLI_raw_line_sha256'])
    check(ident+'/actual_completed_tool',event['type']=='item.completed' and item['type']=='mcp_tool_call' and item['id']==row['CLI_item_id'])
    for key in ('request','response'):
        b=raw(FIX/row[key]);check(ident+'/'+key+'_sha',digest(b)==row[key+'_sha256'])
        check(ident+'/'+key+'_old_bytes',b==raw(OLD/'r'/row['slot']/'o'/('tool_'+str(row['attempt']).zfill(2))/(key.upper()+'.json')))
    equal(ident+'/request_response_ID',request['id'],response['id'])
    equal(ident+'/request_name',request['params']['name'],item['tool'])
    equal(ident+'/request_args',request['params']['arguments'],item['arguments'])
    check(ident+'/args_canonical_digest',digest(canon(request['params']['arguments']).encode())==row['arguments']['canonical_sha256'])
    equal(ident+'/content_preserved',response['result']['content'],item['result']['content'])
    check(ident+'/observed_projection',set(response['result'])=={'content','isError'} and set(item['result'])=={'content','structured_content'} and item['result']['structured_content'] is None and item['error'] is None)
    equal(ident+'/status_mapping',item['status'],'failed' if response['result']['isError'] else 'completed')
    equal(ident+'/fixture_classification',row['expected_classification'],'tool_error' if response['result']['isError'] else 'success')
    actual=next(r for r in result['real_fixture_results'] if r['fixture_id']==ident)
    check(ident+'/recorded_binding',actual['passed'] is True and actual['binding']['matched'] is True and actual['binding']['classification']==row['expected_classification'])

def expected_inputs(case,slot_records):
    """Reconstruct the named single-field change on the captured source data."""
    owner={p.relative_to(FIX/'slots'/case['slot']/'owner').as_posix():doc(p)
           for p in (FIX/'slots'/case['slot']/'owner').rglob('*.json')}
    calls=[{'perf_ns':r['CLI_perf_ns'],'type':'item.completed','item':doc(FIX/r['CLI_completed'])['item']} for r in slot_records]
    i=next((i for i,r in enumerate(slot_records) if r['fixture_id']==case['fixture_id']),0)
    path='tool_'+str(slot_records[i]['attempt']).zfill(2)+'/RESPONSE.json'
    response=owner[path];item=calls[i]['item'];tools=owner['TOOLS.json'];op=case['mutation']
    if case['variant']=='owner_style':item['result']={'content':copy.deepcopy(item['result']['content']),'isError':response['result']['isError']}
    before=copy.deepcopy({'owner':owner,'calls':calls})
    if op=='none':pass
    elif op=='flip_cli_status':item['status']='failed' if item['status']=='completed' else 'completed'
    elif op=='flip_owner_flag':response['result']['isError']=not response['result']['isError']
    elif op=='owner_flag_integer':response['result']['isError']=1
    elif op=='cli_error_nonnull':item['error']={'message':'registered_non_null_error'}
    elif op=='cli_error_missing':del item['error']
    elif op=='cli_flag_integer':item['result']['isError']=1
    elif op=='flip_cli_flag':item['result']['isError']=not item['result']['isError']
    elif op=='structured_nonnull':item['result']['structured_content']={}
    elif op=='cli_extra_result':item['result']['unregistered_field']=True
    elif op=='owner_extra_result':response['result']['unregistered_field']=True
    elif op=='owner_wrong_rpc':response['jsonrpc']='1.0'
    elif op=='owner_top_error':response['error']={'code':-32603,'message':'registered_RPC_error'}
    elif op=='cli_wrong_type':item['type']='function_call'
    elif op=='change_text':next(b for b in item['result']['content'] if b['type']=='text')['text']+='!'
    elif op=='change_image_data':
        b=next(b for b in item['result']['content'] if b['type']=='image');b['data']=('A' if b['data'][0]!='A' else 'B')+b['data'][1:]
    elif op=='change_image_mime':next(b for b in item['result']['content'] if b['type']=='image')['mimeType']='image/jpeg'
    elif op=='swap_content_order':item['result']['content'][0],item['result']['content'][1]=item['result']['content'][1],item['result']['content'][0]
    elif op=='owner_content_string':response['result']['content']='registered_non_array'
    elif op=='cli_content_string':item['result']['content']='registered_non_array'
    elif op=='owner_id_bool':response['id']=True
    elif op=='owner_id_object':response['id']={}
    elif op=='cli_tool_name':item['tool']='scene_data'
    elif op=='cli_arguments':item['arguments']['code']+='\n'
    elif op=='swap_cli_order':calls[0],calls[1]=calls[1],calls[0]
    elif op=='swap_owner_order':tools['tools'][0],tools['tools'][1]=tools['tools'][1],tools['tools'][0]
    elif op=='owner_attempt_boolean':tools['tools'][0]['attempt']=True
    elif op=='drop_owner_last':tools['tools'].pop()
    elif op=='drop_cli_last':calls.pop()
    elif op=='extra_cli_last':calls.append(copy.deepcopy(calls[-1]))
    elif op=='delete_owner_response':del owner[path]
    elif op=='response_id_value':response['id']+=1
    elif op=='response_id_float':response['id']=float(response['id'])
    else:raise ValueError(op)
    return before,{'owner':owner,'calls':calls},i

zip_count=0;zip_members=0
for case in cases:
    cid=case['case_id'];dest=RUN/'cases'/cid;r=doc(dest/'RESULT.json');equal(cid+'/aggregate_record',r,by_case[cid])
    equal(cid+'/case_declaration',doc(dest/'consumer/TRANSFORMATION.json'),case)
    sr=[x for x in records if x['slot']==case['slot']]
    before,expected,target=expected_inputs(case,sr)
    actual_owner={p.relative_to(dest/'owner').as_posix():doc(p) for p in (dest/'owner').rglob('*.json')}
    actual_calls=doc(dest/'consumer/CANDIDATE_CLI_ITEMS.json')
    equal(cid+'/only_named_owner_change',actual_owner,expected['owner'])
    equal(cid+'/only_named_CLI_change',actual_calls,expected['calls'])
    check(cid+'/change_presence', (canon(before)!=canon(expected))==(case['mutation']!='none'))
    check(cid+'/raw_original_lines_retained',raw(dest/'consumer/ORIGINAL_CLI_COMPLETED_RAW.jsonl')==b''.join(raw(FIX/x['CLI_completed'])for x in sr))
    check(cid+'/recorded_success',r['passed'] is True and r['exception'] is None)
    check(cid+'/case_clock',r['closed_ns']-r['started_ns']==r['elapsed_ns'] and result['started_ns']<=r['started_ns']<=r['closed_ns']<=result['closed_before_result_publication_ns'])
    e=case['expected'];expect_reason=e['matcher_reason']
    if case['scope']=='matcher':
        check(cid+'/direct_mismatch',not r['matcher']['matched'] and r['matcher']['classification']=='protocol_mismatch' and r['matcher']['reason']==expect_reason)
    else:
        equal(cid+'/pipeline_outcome',r['pipeline_matched'],e['pipeline_matched'])
        if e['pipeline_matched']:
            check(cid+'/both_callers_accept',not r['archive_errors'] and not r['shared_faults'])
            equal(cid+'/actual_classes',[b['classification']for b in r['result_contracts']],[x['expected_classification']for x in sr])
        else:
            check(cid+'/archive_rejects',bool(r['archive_errors']) and r['archive_errors'][0]['reason']==e['primary_archive_reason'])
            check(cid+'/common_rejects',bool(r['shared_faults']) and r['shared_faults'][0]['reason']==e['primary_shared_reason'])
            if expect_reason:
                bind=next(x for x in r['result_contracts']if x['attempt']==sr[target]['attempt'])
                check(cid+'/nested_reason',not bind['matched'] and bind['classification']=='protocol_mismatch' and bind['reason']==expect_reason)
        a=r['archive'];zpath=Path(a['archive']);zraw=raw(zpath)
        check(cid+'/zip_byte_identity',len(zraw)==a['archive_bytes'] and digest(zraw)==a['archive_sha256'])
        with zipfile.ZipFile(zpath)as z:
            names=z.namelist();zip_count+=1;zip_members+=len(names)
            check(cid+'/zip_exact_members',len(names)==len(set(names))==a['original_file_count'] and set(names)==set(a['source_files_sha256']))
            for name in names:
                data=z.read(name);check(cid+'/zip:'+name,digest(data)==a['source_files_sha256'][name] and data==raw(dest/'consumer'/name))
        equal(cid+'/ARCHIVE_receipt',doc(dest/'consumer/ARCHIVE.json'),a)
    summaries.append(dict(case_id=cid,scope=case['scope'],variant=case['variant'],mutation=case['mutation'],recorded_pass=r['passed'],pipeline_matched=r.get('pipeline_matched'),matcher_reason=expect_reason))
equal('45_archives',zip_count,45);equal('560_zip_members',zip_members,560)

old_run=doc(OLD/'r/RUN_RESULT.json');copied_run=doc(FIX/'RUN_RESULT_ORIGINAL.json');equal('old_run_copy',old_run,copied_run)
equal('old_four_completed_two_failed',Counter(r['execution_state']for r in old_run['records']),{'completed':4,'failed':2})
invariants={r['slot']:r for r in result['historical_invariants']['slots']}
for state in manifest['slots']:
    slot=state['slot'];c=doc(OLD/'r'/slot/'c/CONSUMER.json');copied=doc(FIX/'slots'/slot/'CONSUMER_ORIGINAL.json')
    equal(slot+'/consumer_copy',c,copied)
    for key in ('usage','raw_usage_events','usage_semantics'):equal(slot+'/'+key,state[key],c[key])
    check(slot+'/final_bytes',digest(raw(OLD/'r'/slot/'c/PUBLIC_FINAL.txt'))==state['final_sha256'])
    ev=[json.loads(line)for line in raw(FIX/'slots'/slot/'PUBLIC_EVENTS_ORIGINAL.jsonl').splitlines()]
    top=[r['event']for r in ev if r['event']['type']in ('error','turn.failed')]
    equal(slot+'/top_errors_preserved',top,state['top_level_errors'])
    equal(slot+'/historical_status_preserved',state['original_execution_state'],next(r['execution_state']for r in old_run['records']if r['slot']==slot))
    if slot=='N3':
        check('N3_reconnect_still_invalid',len(top)==1 and 'Reconnecting' in top[0]['message'] and invariants[slot]['candidate_event_projection_only_valid'] is False and invariants[slot]['original_outer_accepted'] is False)
        equal('N3_interrupted_usage_unknown',state['interrupted_stream_usage_coverage'],'unknown')

started=doc(RUN/'STARTED.json')
check('timed_window',started['started_ns']==result['started_ns'] and result['elapsed_ns']==result['closed_before_result_publication_ns']-result['started_ns']==4535146000)
check('freeze_binding',started['freeze_sha256']==result['freeze_sha256']==digest(raw(BASE/'FROZEN.json')))
check('no_forbidden_operations_recorded',result['forbidden_operation_attempts']==[] and result['new_Pro_provider_CLI_actor_Blender_raster_calls']==0 and result['original_tool_code_executed'] is False)
review=dict(author_commit='cb5c33a158a9dea06c8151248cc42d2b87c5697b',scope='Independent existing fixture/raw-line/single-variable case/ZIP/clock/state review; no author matcher/archive/replay imported or run.',
            checks_count=len(checks),passed=sum(c['passed']for c in checks),failed=[c for c in checks if not c['passed']],real_tools=15,case_count=47,pipeline_cases=45,direct_cases=2,ZIP_count=zip_count,ZIP_members=zip_members,
            actual_new_CLI_model_actor_Blender_renderer_calls=0,reviewer_parser_runs=2,author_offline_window_ns=result['elapsed_ns'],cases=summaries,
            unrun=['candidate matcher/archive/replay execution','new CLI/model/actor/server/renderer/Blender','independent live integration','full996/source and1323Git identity audit (root)'],checks=checks)
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in review.items()if k not in ('cases','checks')},ensure_ascii=False))
