"""Analyze frozen entry records only. Starts no product, worker or consumer."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import statistics

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
RESIDENCY=('to_mesh','triangulations','resource_builds','world_transforms')
CAPTURE=('capture_scene','capture_task_scene','_capture','_resident_capture')
KERNEL=('exact_pair_count','closed_solid_pair_count','surface_pair_count','pair_calls','rank_calls')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
checks=[]
pins={}


def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')


def read_raw(path):
    raw=path.read_bytes()
    pins[str(path.resolve())]=sha(raw)
    return raw


def read(path):return json.loads(read_raw(path))
def events(path):return [json.loads(line) for line in read_raw(path).splitlines() if line]


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def check(name,value,*,required=True,details=None):
    checks.append({'check':name,'status':'unmeasured' if value is None else 'pass' if value else 'fail',
      'required':required,'details':details})


def numbers(values):
    values=[value for value in values if type(value) in (int,float)]
    return {'count':len(values),'minimum':min(values) if values else None,
      'median':statistics.median(values) if values else None,'maximum':max(values) if values else None,
      'sum':sum(values) if values else None}


def counter_total(worker,field,key):
    total=0
    for event in worker:
        work=event.get('qa_work')
        if not isinstance(work,dict) or not isinstance(work.get(field),dict):return None
        value=work[field].get(key,0)
        if type(value) is not int or value<0:return None
        total+=value
    return total


def generation(worker):
    values=[]
    for event in worker:
        work=event.get('qa_work',{})
        for host in work.get('after',{}).get('hosts',[]):
            value=host.get('generation')
            if value is not None and value not in values:values.append(value)
    return values


def work_vector(row):
    worker=row.get('worker_received_events')
    if not isinstance(worker,list):return None
    work=row.get('task_work')
    if not isinstance(work,dict):return None
    result={'worker_received_RPC_count':len(worker),
      'successful_normalize_hash_spans':row.get('successful_normalize_hash_spans')}
    result.update({'capture_python.'+key:counter_total(worker,'python_calls',key) for key in CAPTURE})
    result.update({'host_residency.'+key:counter_total(worker,'host_residency_delta',key) for key in RESIDENCY})
    result.update({'task_work.'+key:work.get(key,0) for key in KERNEL})
    return result


def core(body):return {key:value for key,value in body.items() if key not in ('geometry','trace_id')}


def compare_work(label,left,right):
    left_work,right_work=left['work_vector'],right['work_vector']
    complete=left_work is not None and right_work is not None and all(value is not None for value in (*left_work.values(),*right_work.values()))
    check(label+':recorded_work_complete',complete)
    delta=None if not complete else {key:right_work[key]-left_work[key] for key in left_work}
    check(label+':all_additional_work_zero',None if delta is None else all(value==0 for value in delta.values()),details=delta)
    return {'left':left['label'],'right':right['label'],'delta':delta,
      'same_generation':left['host_generation']==right['host_generation']}


def row_record(case_id,row,folder,worker):
    label=case_id+'/'+row['label']
    start,end=row['started_ns'],row['ended_ns']
    elapsed=row.get('entry_elapsed_ns',end-start)
    elapsed_source='recorded' if 'entry_elapsed_ns' in row else 'difference_of_recorded_QA_start_end'
    check(label+':entry_clock',type(start) is int and type(end) is int and end>=start and elapsed==end-start)
    selected=[event for event in worker if type(event.get('started_ns')) is int and start<=event['started_ns']<=end]
    check(label+':worker_interval_exact',selected==row.get('worker_received_events') and len(selected)==row.get('worker_received_RPC_count'))
    result={'case_id':case_id,'label':row['label'],'kind':row['kind'],'mode':row.get('mode'),
      'entry_elapsed_ns':elapsed,'entry_elapsed_source':elapsed_source,'started_ns':start,'ended_ns':end,
      'worker_received_RPC_count':len(selected),'worker_sequences':[event.get('sequence') for event in selected],
      'host_generation':generation(selected),'work_vector':work_vector(row) if row['kind']=='relation' else None,
      'probe_before_ns':sum(event.get('qa_work',{}).get('before_probe_elapsed_ns',0) for event in selected),
      'probe_after_ns':sum(event.get('qa_work',{}).get('after_probe_elapsed_ns',0) for event in selected),
      'profile_scope_ns':sum(event.get('qa_work',{}).get('profile_scope_ns',0) for event in selected),
      'native_supplement_work':[event.get('qa_work',{}).get('native_supplement_work') for event in selected
        if event.get('qa_work',{}).get('native_supplement_work') is not None],
      'C_profile_observations':[{key:event.get('qa_work',{}).get(key) for key in ('C_calls','C_returns','C_exceptions')} for event in selected]}
    if row['kind']=='relation':
        response_path=folder/(row['label']+'.RESPONSE.json')
        response=read(response_path)
        text=response['result']['content'][0]['text'];body=json.loads(text)
        check(label+':raw_response_body',body==row['body'] and len(text.encode('utf8'))==row['text_utf8_bytes'])
        field_bytes={key:len(compact(value)) for key,value in body.items()}
        check(label+':field_value_byte_counts',field_bytes==row['per_field_compact_JSON_bytes'])
        trace=row.get('request_trace',{})
        spans=trace.get('spans',[])
        successful=sum(span.get('name')=='scene.hash' and span.get('outcome')=='completed' for span in spans)
        check(label+':successful_normalization_count',successful==row.get('successful_normalize_hash_spans'))
        encodes=[span for span in spans if span.get('name')=='mcp.content_encode' and span.get('outcome')=='completed']
        check(label+':one_content_encode_span',len(encodes)==1)
        check(label+':one_current_capture_call',None if result['work_vector'] is None else result['work_vector'].get('capture_python.capture_task_scene')==1)
        check(label+':lifetime_peak_scope',trace.get('peak_rss',{}).get('scope')=='process_lifetime_peak',required=False)
        result.update(body_utf8_bytes=len(text.encode('utf8')),response_compact_JSON_bytes=len(compact(response)),
          per_field_value_bytes=field_bytes,geometry_value_bytes=field_bytes.get('geometry',0),
          Peer_elapsed_ns=row.get('stdio',{}).get('elapsed_ns'),
          content_encode_inclusive_ns=encodes[0]['duration_ns'] if len(encodes)==1 else None,
          trace_duration_ns=trace.get('duration_ns'),
          host_capture_inclusive_ns=sum(span['duration_ns'] for span in spans if span.get('name')=='host.capture'),
          product_process_lifetime_peak_rss=trace.get('peak_rss'),
          result_cache_hit=row['task_work'].get('result_cache_hit'),
          current_source_context={key:body['context'].get(key) for key in
            ('scene_revision','scene_fingerprint','runtime_source_sha256','capture_scope','unit','coordinate_frame')},
          trace_spans=spans)
        for key in ('exact_pair_count','closed_solid_pair_count','surface_pair_count'):
            check(label+':kernel_counter_'+key,type(row['task_work'].get(key)) is int)
    elif row['kind']=='native_supplement':
        geometry=read(folder/(row['label']+'.GEOMETRY.json'))
        receipt=read(folder/(row['label']+'.RECEIPT.json'))
        native_text=receipt['response']['result']['result']
        check(label+':native_supplement_bytes',geometry==row['geometry'] and json.loads(native_text)==geometry
          and len(native_text.encode('utf8'))==row['body_utf8_bytes'])
        result.update(body_utf8_bytes=row['body_utf8_bytes'],native_envelope_utf8_bytes=row['native_envelope_utf8_bytes'],
          oracle_retained=row['oracle_retained'])
        if result['native_supplement_work']:
            actual=result['native_supplement_work'][0]
            check(label+':two_selected_native_meshes',actual.get('to_mesh')==2 and actual.get('triangulations')==2 and actual.get('world_preparations')==2)
        else:check(label+':native_supplement_work_available',None)
    return result


def analyze_case(case,folder,expected_source):
    case_id=case['case']['id']
    raw=read(folder/'RESULTS.json')
    check(case_id+':saved_case_equals_batch_record',raw==case)
    check(case_id+':raw_session_passed',case.get('passed') is True,details=case.get('errors'))
    worker=events(folder/'native/WORKER_EVENTS.jsonl')
    check(case_id+':worker_record_values_exact',worker==case.get('all_worker_events'))
    received=[event for event in worker if type(event.get('started_ns')) is int and type(event.get('sequence')) is int]
    check(case_id+':unique_worker_sequences',len(received)==len({event['sequence'] for event in received}))
    listing=read(folder/'ACTUAL_TOOLS.json')['result']['tools']
    schemas={tool['name']:len(compact(tool)) for tool in listing}
    check(case_id+':actual_schema_bytes',schemas==case['tool_schema_compact_JSON_bytes'])
    initialized=read(folder/'ACTUAL_INITIALIZE.json')['result']['_meta']['human_eye']
    check(case_id+':installed_identity',initialized.get('source_kind')=='installed_distribution')
    check(case_id+':installed_source_binding',initialized.get('source_sha256')==expected_source and
      initialized.get('source_file_count')==137 and initialized.get('identity_check',{}).get('compatible') is True)
    rows=[row_record(case_id,row,folder,worker) for row in case['rows']]
    by_label={row['label']:row for row in rows}
    check(case_id+':unique_row_labels',len(by_label)==len(rows))
    assigned={sequence for row in rows for sequence in row['worker_sequences']}
    membership={event['sequence']:sum(event['sequence'] in row['worker_sequences'] for row in rows) for event in received}
    check(case_id+':nonoverlapping_row_RPC_attribution',all(count<=1 for count in membership.values()))
    unassigned=[event for event in received if event['sequence'] not in assigned]
    check(case_id+':all_received_RPC_accounted',len(assigned)+len(unassigned)==len(received))
    original={row['label']:row for row in case['rows']}
    warm_comparisons=[]
    if case['case']['role']=='candidate':
        cycles=range(1,2 if case['case']['transformed'] else 6)
        for cycle in cycles:
            off=by_label['warm_'+str(cycle)+'_OFF']
            for mode in ('vertices','full'):
                current=by_label['warm_'+str(cycle)+'_'+mode]
                label=case_id+'/warm_'+str(cycle)+'_'+mode
                check(label+':same_generation_as_OFF',off['host_generation']==current['host_generation'])
                check(label+':same_relation_context_as_OFF',off['current_source_context']==current['current_source_context'])
                check(label+':relation_cache_hit',current['result_cache_hit'] is True)
                warm_comparisons.append(compare_work(label,off,current))
                check(label+':same_core_as_OFF',core(original[off['label']]['body'])==core(original[current['label']]['body']))
    engineering=[]
    if not case['case']['transformed']:
        for cycle in range(1,6):
            name='warm_'+str(cycle)+'_OFF'
            relation=by_label.get(name+'_comparison',by_label[name])
            native=by_label[name+'_supplement']
            check(case_id+'/'+name+':sequential_engineering_pair',relation['ended_ns']<=native['started_ns'])
            full=by_label.get('warm_'+str(cycle)+'_full')
            pair={'cycle':cycle,'relation_label':relation['label'],'supplement_label':native['label'],
              'same_fields':'world vertices and triangles for the same two objects',
              'sum_entry_elapsed_ns':relation['entry_elapsed_ns']+native['entry_elapsed_ns'],
              'pair_window_elapsed_ns':native['ended_ns']-relation['started_ns'],
              'worker_received_RPC_count':relation['worker_received_RPC_count']+native['worker_received_RPC_count'],
              'response_body_utf8_bytes':relation['body_utf8_bytes']+native['body_utf8_bytes'],
              'native_supplement_work':native['native_supplement_work'],
              'candidate_FULL_entry_elapsed_ns':None if full is None else full['entry_elapsed_ns'],
              'candidate_FULL_body_utf8_bytes':None if full is None else full['body_utf8_bytes']}
            if full is not None:
                pair['FULL_minus_sequential_entry_sum_ns']=full['entry_elapsed_ns']-pair['sum_entry_elapsed_ns']
                pair['FULL_minus_sequential_body_utf8_bytes']=full['body_utf8_bytes']-pair['response_body_utf8_bytes']
            engineering.append(pair)
    mutation=None
    if case['case']['mutation']:
        off=by_label['changed_OFF'];full=by_label['changed_full'];cold=by_label['cold']
        check(case_id+':changed_generation',off['host_generation']!=cold['host_generation'])
        check(case_id+':changed_relation_binding',off['current_source_context']['scene_revision']!=cold['current_source_context']['scene_revision'])
        check(case_id+':changed_OFF_recomputed',off['work_vector']['task_work.closed_solid_pair_count']>0 and
          off['work_vector']['task_work.surface_pair_count']>0 and off['work_vector']['successful_normalize_hash_spans']>0)
        check(case_id+':changed_FULL_same_generation',off['host_generation']==full['host_generation'])
        check(case_id+':changed_FULL_cache_hit',full['result_cache_hit'] is True)
        reused_keys=[key for key in full['work_vector'] if key.startswith(('host_residency.','task_work.')) or key=='successful_normalize_hash_spans']
        check(case_id+':changed_FULL_no_preparation_or_solving',all(full['work_vector'][key]==0 for key in reused_keys))
        check(case_id+':changed_FULL_same_RPC_and_capture',all(off['work_vector'][key]==full['work_vector'][key]
          for key in full['work_vector'] if key.startswith('capture_python.') or key=='worker_received_RPC_count'))
        mutation={'OFF':off,'FULL':full}
    relations=[row for row in rows if row['kind']=='relation']
    costs={}
    for phase,selected in (('cold',[by_label['cold']]),('warm_OFF',[row for row in relations if re.fullmatch(r'warm_\d+_OFF',row['label'])]),
            ('warm_vertices',[row for row in relations if row.get('mode')=='vertices']),
            ('warm_full',[row for row in relations if re.fullmatch(r'warm_\d+_full',row['label'])])):
        costs[phase]={field:numbers([row.get(field) for row in selected]) for field in
          ('entry_elapsed_ns','Peer_elapsed_ns','content_encode_inclusive_ns','body_utf8_bytes','geometry_value_bytes')}
    rpc=read(folder/'product/RPC.json')
    peaks=[row['product_process_lifetime_peak_rss'].get('bytes') for row in relations if row.get('product_process_lifetime_peak_rss')]
    return {'case':case['case'],'raw_session_passed':case['passed'],'schema_compact_JSON_bytes':schemas,
      'rows':rows,'warm_work_comparisons':warm_comparisons,'engineering_FULL_comparisons':engineering,'mutation':mutation,
      'costs':costs,'session_wall_ns':case['session_wall_ns'],
      'session_received_worker_RPC_total':len(received),'row_attributed_worker_RPC_total':len(assigned),
      'unassigned_control_worker_events':unassigned,
      'all_worker_record_count':len(worker),'product_stdio_all_record_count':len(rpc['requests']),
      'product_stdio_TX_bytes_all':rpc['tx_bytes'],'product_stdio_RX_bytes_all':rpc['rx_bytes'],
      'QA_oracle_rows':[row for row in rows if row['kind']=='native_supplement' and row.get('oracle_retained')],
      'registered_QA_change_rows':[row for row in rows if row['kind']=='registered_QA_change'],
      'sum_recorded_row_entry_elapsed_ns':sum(row['entry_elapsed_ns'] for row in rows if type(row.get('entry_elapsed_ns')) is int),
      'product_lifetime_peak_rss_max_bytes':max((value for value in peaks if type(value) is int),default=None)}


def default_latency_review(sessions):
    groups={'baseline':[],'candidate':[]}
    case_summaries=[]
    for session in sessions:
        if session['case']['transformed']:
            continue
        selected=[copy.deepcopy(row) for row in session['rows'] if re.fullmatch(r'warm_\d+_OFF',row['label'])]
        for row in selected:
            row['trace_outside_host_capture_ns']=row['trace_duration_ns']-row['host_capture_inclusive_ns']
            row['entry_outside_trace_ns']=row['entry_elapsed_ns']-row['trace_duration_ns']
            row['probe_before_plus_after_ns']=row['probe_before_ns']+row['probe_after_ns']
        groups[session['case']['role']].extend(selected)
        case_summaries.append({'case_id':session['case']['id'],'role':session['case']['role'],
          'entry_elapsed_ns':numbers([row['entry_elapsed_ns'] for row in selected])})
    fields=('entry_elapsed_ns','Peer_elapsed_ns','trace_duration_ns','host_capture_inclusive_ns',
      'trace_outside_host_capture_ns','entry_outside_trace_ns','probe_before_ns','probe_after_ns',
      'probe_before_plus_after_ns','profile_scope_ns','content_encode_inclusive_ns')
    summaries={role:{field:numbers([row[field] for row in rows]) for field in fields} for role,rows in groups.items()}
    deltas={field:summaries['candidate'][field]['median']-summaries['baseline'][field]['median'] for field in fields}
    base=summaries['baseline']['entry_elapsed_ns']['median']
    delta=deltas['entry_elapsed_ns']
    return {'status':'observed_default_warm_OFF_regression' if delta>0 else 'observed_default_warm_OFF_nonincrease',
      'default_latency_preservation':'not_demonstrated',
      'numeric_admission_tolerance':'not_defined_in_frozen_contract_no_posthoc_threshold_added',
      'baseline':summaries['baseline'],'candidate':summaries['candidate'],
      'median_candidate_minus_baseline_ns':deltas,'entry_median_change_percent':100*delta/base,
      'per_session':case_summaries,
      'interpretation':'Saved instrumented requests only. Inclusive host/profile spans overlap. Differences of medians are descriptive and do not add to a median end-to-end difference. Shared host source and prominent QA profiling do not establish the cause of the observed regression.',
      'selected_request_labels':{role:[row['case_id']+'/'+row['label'] for row in rows] for role,rows in groups.items()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entry-run',required=True,type=Path)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    entry=args.entry_run.resolve()
    assert entry.is_relative_to((BATCH/'entry').resolve())
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    destination=HERE/args.output;destination.mkdir(exist_ok=False)
    batch=read(entry/'RESULTS.json');bindings=read(entry/'FIXED_INPUTS.json')
    check('seven_terminal_raw_sessions',len(batch.get('cases',[]))==7 and batch.get('passed') is True)
    check('fixed_seven_case_order',[case['case'] for case in batch['cases']]==bindings['sessions'])
    source_checks={name:sha(read_raw(ROOT/name))==digest for name,digest in bindings['source_files_sha256'].items()}
    check('frozen_source_pins',all(source_checks.values()))
    sessions=[analyze_case(case,entry/case['case']['id'],bindings[case['case']['role']+'_source_sha256']) for case in batch['cases']]
    cold=[session for session in sessions if not session['case']['transformed']]
    check('two_cold_samples_per_fixed_mode',all(sum(session['case']['role']==role and session['case']['cold_mode']==mode for session in cold)==2
      for role,mode in (('baseline','OFF'),('candidate','OFF'),('candidate','full'))))
    cold_reference=cold[0]['rows'][0]
    cold_comparisons=[]
    for session in cold[1:]:
        cold_comparisons.append(compare_work(session['case']['id']+':cold_existing_work',cold_reference,session['rows'][0]))
    for session in sessions:
        rows=session['rows']
        for mode in ('vertices','full'):
            for row in rows:
                if row.get('mode')==mode:
                    check(session['case']['id']+'/'+row['label']+':geometry_value_bytes_present',row.get('geometry_value_bytes',0)>0)
    schemas={role:[session['schema_compact_JSON_bytes'] for session in sessions if session['case']['role']==role] for role in ('baseline','candidate')}
    check('same_schema_within_each_version',all(all(value==values[0] for value in values) for values in schemas.values()))
    schema_delta={name:schemas['candidate'][0][name]-schemas['baseline'][0][name] for name in schemas['baseline'][0]}
    check('nearest_schema_unchanged',schema_delta['human_eye_surface_nearest']==0)
    c_profile_visible=any(row.get('C_calls') for session in sessions for record in session['rows'] for row in record['C_profile_observations'])
    check('direct_C_profile_method_observability',True if c_profile_visible else None,required=False,
      details='Empty C-profile tables do not establish zero actual bpy C calls. Existing host counters and native explicit counters are retained.')
    check('source_and_raw_records_unchanged_during_analysis',all(sha(Path(path).read_bytes())==digest for path,digest in pins.items()))
    failed=[row for row in checks if row['status']=='fail']
    unknown=[row for row in checks if row['status']=='unmeasured']
    passed=not failed and not any(row['required'] for row in unknown)
    report={'cycle_id':'M4-RELATION-SELECTED-EVIDENCE-001','analysis_kind':'saved actual engineering count and cost analysis',
      'passed':passed,'raw_entry_sessions_passed':batch.get('passed'),
      'full_admission':'pending root independent geometry review and explicit latency tradeoff review',
      'checks':checks,'check_count':len(checks),'failed_check_count':len(failed),'unmeasured_checks':unknown,
      'candidate_commit':bindings['candidate_commit'],'baseline_source_sha256':bindings['baseline_source_sha256'],
      'candidate_source_sha256':bindings['candidate_source_sha256'],'session_count':len(sessions),
      'sessions':sessions,'cold_work_comparisons':cold_comparisons,'schema_descriptor_byte_delta':schema_delta,
      'default_latency_review':default_latency_review(sessions),
      'scope':{
        'cold':'First application geometry request in a fresh product/owned worker. OS caches retained. Two samples per original cold mode.',
        'warm':'Five fixed cycles per original candidate session and one transformed cycle. OFF pair uses the same cycle.',
        'native_comparison':'FULL versus OFF plus native world vertices and triangles. Vertices-only has no equal-field native comparison.',
        'timing_hierarchy':'Entry wrapper includes Peer and its final receipt/RPC publication. Peer elapsed is sampled before that final publication. Trace and content-encode spans are inclusive. Nested measures are not added.',
        'content_encode':'Existing mcp.content_encode includes relation display projection plus JSON/content preparation, not isolated json.dumps.',
        'native_pair':'sum_entry_elapsed adds sequential nonoverlapping OFF/native intervals. pair_window also includes the inter-call gap and native script preparation.',
        'peak':'Recorded product-process OS lifetime high-water RSS. It includes earlier requests/setup in that process and is not a per-request allocation delta.',
        'QA':'Cold and changed oracles, registered change and unassigned close/control RPC remain in session totals. QA before/after probes and profiling scope are recorded separately. Profiling callback overhead cannot be subtracted from its inclusive execution scope.'},
      'unmeasured':['Uninstrumented entry latency','Worker OS peak memory','Isolated per-request allocation peak',
        'Python profiling callback overhead alone','Pure JSON-only serialization time','Model token/cost or complete model-task benefit'],
      'analysis_external_processes':0,'analysis_Blender_sessions':0,'model_consumers':0,'new_images':0,
      'source_files_checked':source_checks,'input_sha256':pins,'analysis_script_sha256':sha(Path(__file__).read_bytes())}
    save(destination/'RESULTS.json',report)
    print(json.dumps({'passed':passed,'checks':len(checks),'failed':len(failed),'unmeasured':len(unknown),
      'sessions':len(sessions),'schema_delta':schema_delta,'output':str(destination)},ensure_ascii=False))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
