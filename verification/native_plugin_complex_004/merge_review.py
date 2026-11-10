"""Join sealed blind judgments with raw costs; never run a consumer or solver.

Default execution describes the interface without opening cost records.
Actual unblinding requires --run and explicit path/SHA pins for both reviews
and the analysis. Evidence adapters may be revised without changing judgments.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile

HERE=Path(__file__).resolve().parent
TASKS=('assembly','discovery');GROUPS=('N','O','C')
METRICS=('prompt_to_final_ns','cli_wall_ns','total_task_wall_ns','setup_ns','owner_finish_ns',
    'actor_startup_ns','owner_close_ns','tool_attempts','native_attempts','plugin_attempts','tool_errors',
    'tool_time_ns','physical_worker_requests','public_catalogue_rx_bytes','public_tool_rx_bytes',
    'public_tool_text_bytes','public_stdio_tx_bytes','public_stdio_rx_bytes','plugin_pipe_tx_bytes','plugin_pipe_rx_bytes')
TOKENS=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','total_tokens',
    'reasoning_tokens','reasoning_output_tokens')


def digest(raw):return hashlib.sha256(raw).hexdigest()
def file_sha(path):return digest(Path(path).read_bytes())
def dump_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate_json_key:'+key)
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite_JSON:'+x)))


def load(path):return decode(Path(path).read_bytes())


def sealed(path,expected,label):
    if not isinstance(expected,str) or len(expected)!=64 or file_sha(path)!=expected:raise ValueError(label+'_sealed_SHA_mismatch')
    return load(path)


def unique_rows(rows,key,expected,label):
    if not isinstance(rows,list) or len(rows)!=len(expected):raise ValueError(label+'_exact_row_count_required')
    result={}
    for row in rows:
        identity=row.get(key)
        if identity in result:raise ValueError(label+'_duplicate_'+key)
        result[identity]=row
    if set(result)!=set(expected):raise ValueError(label+'_missing_or_surplus_identity')
    return result


def bool_or_unknown(value,label):
    if value is None or type(value) is bool:return value
    raise ValueError(label+'_must_be_boolean_or_null_not_truthy_text')


def review_state(value,label):
    if value is None or type(value) is bool:return value
    # Candidate adapter for explicit authoritative status fields, never notes.
    if value in ('not_verified','receipt_unknown','unknown','pending','unverified'):return None
    if value in ('pass','verified','supported'):return True
    if value in ('fail','failed','unsupported'):return False
    raise ValueError('unrecognized_evidence_state_requires_adapter:'+label+':'+str(value))


def tri_and(values):
    if any(value is False for value in values):return False
    if any(value is None for value in values):return None
    return True


def review_inputs(document,label):
    entries=document.get('input_files',document.get('inputs'))
    if not isinstance(entries,list):raise ValueError(label+'_input_files_manifest_required')
    result={}
    for entry in entries:
        path=Path(entry['path']).resolve();expected=entry['sha256']
        if str(path) in result:raise ValueError(label+'_duplicate_input_path')
        if file_sha(path)!=expected:raise ValueError(label+'_input_file_changed:'+str(path))
        result[str(path)]=expected
    return result


def require_input(inputs,path,label):
    if inputs.get(str(Path(path).resolve()))!=file_sha(path):raise ValueError(label+'_required_input_not_bound:'+str(path))


def package_binding(root,evidence_inputs,evidence_sha,supplement_path=None,supplement_sha=None):
    index=root/'blind/TOOL_EVIDENCE_INDEX.json';provenance_path=root/'private/TOOL_EVIDENCE_PROVENANCE.json'
    provenance=load(provenance_path);published=provenance['published_files_sha256']
    rows=load(index)['answers'];ids=[row['answer_id'] for row in rows];subjects={}
    if len(ids)!=18 or len(set(ids))!=18:raise ValueError('tool_package_exact_18_unique_ids_required')
    for row in rows:
        if row['evidence']!='tools/'+row['answer_id']+'.json':raise ValueError('anonymous_packet_path_subject_mismatch')
        packet=load(root/'blind'/row['evidence'])
        if packet.get('answer_id')!=row['answer_id'] or packet.get('task_id')!=row['task_id']:raise ValueError('packet_header_subject_mismatch')
        subjects[row['answer_id']]=row['task_id']
    expected_paths={str(index.resolve())}|{str((root/'blind'/row['evidence']).resolve()) for row in rows}
    actual={str(Path(path).resolve()):value for path,value in published.items()}
    if set(actual)!=expected_paths:raise ValueError('tool_provenance_missing_or_surplus_packet')
    for path,expected in actual.items():
        if file_sha(path)!=expected:raise ValueError('anonymous_tool_packet_changed:'+path)
    mode=None
    if evidence_inputs.get(str(provenance_path.resolve()))==file_sha(provenance_path):mode='sealed_review_transitively_binds_private_provenance_and_all_19_public_members'
    elif all(evidence_inputs.get(path)==sha for path,sha in actual.items()):mode='sealed_review_directly_binds_all_19_public_members'
    if mode is None and supplement_path is not None:
        supplement=sealed(supplement_path,supplement_sha,'evidence_binding_supplement')
        if supplement.get('evidence_review_sha256')!=evidence_sha:raise ValueError('binding_supplement_review_mismatch')
        pins={str(Path(path).resolve()):value for path,value in supplement.get('files_sha256',{}).items()}
        if not all(pins.get(path)==sha for path,sha in actual.items()):raise ValueError('binding_supplement_does_not_bind_entire_package')
        mode='explicit_root_sealed_postprocess_binding_supplement; reviewer_content_unchanged'
    if mode is None:
        raise ValueError('evidence_review_has_no_complete_package_binding; provide a root-sealed supplement, do not assume index alone pins packet contents')
    return {'verified':True,'scope':mode,'public_members':19,'index_sha256':file_sha(index),
        'provenance_sha256':file_sha(provenance_path),'published_files_sha256':actual,'packet_task_subjects':subjects},set(ids)


def stats(values,denominator):
    known=[value for value in values if type(value) in (int,float) and math.isfinite(value) and value>=0]
    return {'denominator':denominator,'values':values,'known_n':len(known),'unknown_or_invalid_n':denominator-len(known),
        'median':statistics.median(known) if known else None,'min':min(known) if known else None,
        'max':max(known) if known else None,'observed_sum':sum(known) if known else None}


def additional_evidence_checks(row):
    states=[]
    for key in ('receipt_status','evidence_status','readonly_status','required_checks_passed','receipt_binding_passed'):
        if key in row:states.append(review_state(row[key],key))
    if 'required_checks' in row:
        if not isinstance(row['required_checks'],dict):raise ValueError('required_checks_must_be_explicit_state_mapping')
        states.extend(review_state(value,'required_checks.'+key) for key,value in row['required_checks'].items())
    return tri_and(states) if states else True


def quality_judgment(semantic_pass,supported,readonly,review_row):
    components=(semantic_pass,supported,readonly)
    if 'full_pass' in review_row:
        value=review_state(review_row['full_pass'],'root_quality_full_pass')
        if value is True and any(component is False for component in components):
            raise ValueError('root_full_pass_contradicts_explicitly_failed_quality_component')
        return value,'authoritative_sealed_root_evidence_full_pass'
    required=review_row.get('required_quality_checks',{})
    if not isinstance(required,dict):raise ValueError('required_quality_checks_must_be_explicit_mapping')
    values=[review_state(value,'required_quality_checks.'+key) for key,value in required.items()]
    return tri_and([*components,*values]),'explicit_postprocess_conjunction_of_quality_components_only; no strict_client_EXIT_gate'


def merge(root,semantic_path,semantic_sha,evidence_path,evidence_sha,analysis_path,analysis_sha,
          supplement_path=None,supplement_sha=None):
    root=Path(root).resolve()
    semantic=sealed(semantic_path,semantic_sha,'semantic_review')
    evidence_paths=list(evidence_path) if isinstance(evidence_path,(list,tuple)) else [evidence_path]
    evidence_shas=list(evidence_sha) if isinstance(evidence_sha,(list,tuple)) else [evidence_sha]
    if not evidence_paths or len(evidence_paths)!=len(evidence_shas):raise ValueError('each_evidence_review_requires_its_own_SHA')
    evidence_documents=[sealed(path,pin,'evidence_review') for path,pin in zip(evidence_paths,evidence_shas)]
    evidence_seals=[{'path':str(Path(path).resolve()),'sha256':pin} for path,pin in zip(evidence_paths,evidence_shas)]
    evidence_set_sha=digest(json.dumps(evidence_seals,sort_keys=True,separators=(',',':')).encode())
    # Both review seals are verified before opening raw cost values.
    sem_inputs=review_inputs(semantic,'semantic');ev_inputs={};combined_evidence_rows=[]
    for document in evidence_documents:
        pins=review_inputs(document,'evidence')
        for path,pin in pins.items():
            if path in ev_inputs and ev_inputs[path]!=pin:raise ValueError('evidence_reviews_conflicting_input_SHA')
            ev_inputs[path]=pin
        for row in document['answers']:
            combined_evidence_rows.append(row)
            # Both real root schemas seal individual packet hashes in rows,
            # even though their top-level input manifests are compact.
            binding=row.get('input_evidence') or ({'path':row['evidence_file'],'sha256':row['evidence_sha256']}
                if 'evidence_file' in row and 'evidence_sha256' in row else None)
            if binding:
                path=str(Path(binding['path']).resolve());pin=binding['sha256']
                if file_sha(path)!=pin:raise ValueError('sealed_evidence_row_packet_changed')
                if path in ev_inputs and ev_inputs[path]!=pin:raise ValueError('evidence_row_packet_pin_conflict')
                ev_inputs[path]=pin
    answers_path=root/'blind/ANSWERS.json';tasks_path=root/'blind/TASKS.json'
    require_input(sem_inputs,answers_path,'semantic');require_input(sem_inputs,tasks_path,'semantic')
    require_input(ev_inputs,answers_path,'evidence')
    package,packet_ids=package_binding(root,ev_inputs,evidence_set_sha,supplement_path,supplement_sha)
    answers=load(answers_path)['answers'];mapping=load(root/'private/BLIND_MAP.json');plan=load(root/'PLAN.json');run=load(root/'RUN_RESULT.json')
    sequence=plan['sequence'];expected_cells=[slot['cell'] for slot in sequence]
    if len(sequence)!=18 or len(set(expected_cells))!=18 or plan['denominator']!=18 or run['denominator']!=18 or not run.get('ended_ns'):
        raise ValueError('fixed_complete_18_plan_run_required')
    if plan.get('cycle_id')!=run.get('cycle_id'):raise ValueError('plan_run_cycle_mismatch')
    expected_keys={(task,group,round_) for task in TASKS for group in GROUPS for round_ in (1,2,3)}
    if {(s['task'],s['group'],s['round']) for s in sequence}!=expected_keys:raise ValueError('fixed_3_per_task_group_required')
    run_rows=unique_rows(run['cells'],'cell',expected_cells,'run')
    if mapping['plan_sha256']!=file_sha(root/'PLAN.json') or mapping['run_result_sha256']!=file_sha(root/'RUN_RESULT.json'):raise ValueError('private_blind_map_plan_run_binding_changed')
    answer_ids=list(mapping['answers']);anonymous=unique_rows(answers,'answer_id',answer_ids,'anonymous')
    if len(answer_ids)!=18 or set(answer_ids)!=packet_ids:raise ValueError('same_18_random_answer_ids_required')
    semantic_rows=unique_rows(semantic['answers'],'answer_id',answer_ids,'semantic')
    evidence_rows=unique_rows(combined_evidence_rows,'answer_id',answer_ids,'evidence')
    tasks=unique_rows(load(tasks_path)['tasks'],'task_id',TASKS,'blind_tasks')
    if load(tasks_path)['plan_sha256']!=file_sha(root/'PLAN.json'):raise ValueError('blind_tasks_new_PLAN_binding_changed')
    prompts=unique_rows(semantic['task_prompt_binding'],'task_id',TASKS,'semantic_task_prompt')
    rule_bytes=Path(plan['session_rules']).read_bytes()
    if digest(rule_bytes)!=plan['session_rules_sha256']:raise ValueError('registered_session_rules_changed')
    for task in TASKS:
        text=tasks[task]['text'].encode('utf8');expected=plan['tasks'][task]['model_input_sha256'];pin=prompts[task]
        prompt_bytes=Path(plan['tasks'][task]['prompt']).read_bytes()
        exact_marker=(pin.get('exact_reconstruction_matches') is True or pin.get('exact_reconstruction_matches')==['as_serialized'])
        if (digest(text)!=expected or tasks[task]['model_input_sha256']!=expected or pin.get('model_input_sha256')!=expected
            or pin.get('text_utf8_sha256')!=expected or pin.get('declared_input_hash_matches_frozen_binding') is not True
            or not exact_marker
            or digest(prompt_bytes)!=plan['tasks'][task]['prompt_sha256']
            or rule_bytes+b'\n'+prompt_bytes!=text or len(text)!=plan['tasks'][task]['model_input_bytes']):raise ValueError('exact_model_input_text_binding_failed:'+task)
    analysis=sealed(analysis_path,analysis_sha,'analysis');raw_rows=unique_rows(analysis['rows'],'cell',expected_cells,'analysis')
    if analysis.get('denominator')!=18:raise ValueError('analysis_denominator_changed')
    if analysis.get('cycle_id')!=plan.get('cycle_id'):raise ValueError('analysis_cycle_mismatch')
    inputs=analysis.get('inputs_sha256')
    if not isinstance(inputs,dict):raise ValueError('analysis_raw_input_hash_manifest_required')
    for path,expected in inputs.items():
        if file_sha(path)!=expected:raise ValueError('analysis_raw_input_changed:'+path)
    require_input(inputs,root/'PLAN.json','analysis');require_input(inputs,root/'RUN_RESULT.json','analysis')
    if analysis.get('script_sha256')!=file_sha(root/'analyze.py'):raise ValueError('analysis_producer_code_hash_changed')
    for key in ('provider_request_count','fees','resolved_effort'):
        if analysis.get(key) is not None:raise ValueError('unexposed_provider_fee_or_actual_effort_cannot_be_estimated:'+key)
    slots={slot['cell']:slot for slot in sequence};bound_cells=set();joined=[]
    for answer_id in answer_ids:
        hidden=mapping['answers'][answer_id];cell=hidden['cell']
        if cell in bound_cells or cell not in slots:raise ValueError('private_map_duplicate_or_foreign_cell')
        bound_cells.add(cell);slot=slots[cell];raw=raw_rows[cell];final=anonymous[answer_id];sem=semantic_rows[answer_id];ev=evidence_rows[answer_id]
        for candidate,label in ((hidden,'map'),(run_rows[cell],'run'),(raw,'analysis')):
            if any(candidate.get(k)!=slot[k] for k in ('task','round','group','cell')):raise ValueError(label+'_slot_binding_failed:'+cell)
        if final['task_id']!=slot['task'] or sem['task_id']!=slot['task'] or ev['task_id']!=slot['task'] or package['packet_task_subjects'][answer_id]!=slot['task']:raise ValueError('anonymous_review_task_mismatch')
        final_sha=None if final['text'] is None else digest(final['text'].encode('utf8'))
        if final_sha!=hidden['final_sha256'] or sem.get('answer_text_sha256')!=final_sha or raw.get('final_text_sha256')!=final_sha:
            raise ValueError('final_text_SHA_binding_failed:'+cell)
        if ev.get('answer_text_sha256',final_sha)!=final_sha:raise ValueError('evidence_review_final_SHA_mismatch')
        if (type(final['delivered']) is not bool or type(sem['delivered']) is not bool or type(hidden['valid_completion']) is not bool
            or sem['delivered']!=final['delivered'] or hidden['valid_completion']!=final['delivered']):
            raise ValueError('delivered_binding_failed')
        consumer=root/'cells'/cell/'CONSUMER.json'
        if hidden['consumer_sha256'] is not None:
            if file_sha(consumer)!=hidden['consumer_sha256']:raise ValueError('consumer_changed_after_blinding')
            require_input(inputs,consumer,'analysis')
        elif raw.get('recorded') is not False or consumer.exists():raise ValueError('missing_consumer_binding_inconsistent')
        for key in ('provider_request_count','fees','resolved_effort'):
            if raw.get(key) is not None:raise ValueError('row_unexposed_provider_fee_or_actual_effort_not_null:'+key)
        core=bool_or_unknown(sem.get('core_facts_correct'),'core_facts_correct');complete=bool_or_unknown(sem.get('requested_answer_complete'),'requested_answer_complete')
        sem_pass=tri_and((final['delivered'],core,complete))
        supported=review_state(ev.get('evidence_supported'),'evidence_supported');readonly=review_state(ev.get('readonly_current_state'),'readonly_current_state')
        review_checks=additional_evidence_checks(ev)
        protocol_complete=bool_or_unknown(raw.get('protocol_completed'),'protocol_completed')
        protocol_pass=bool_or_unknown(raw.get('protocol_audit_passed'),'protocol_audit_passed')
        source_plan_pass=bool_or_unknown(analysis.get('source_and_plan_audit_passed'),'source_and_plan_audit_passed')
        request_audit=bool_or_unknown(raw.get('recorded_request_outcomes_audit_passed'),'recorded_request_outcomes_audit_passed')
        backend_audit=bool_or_unknown(raw.get('owned_backend_cleanup_audit_passed'),'owned_backend_cleanup_audit_passed')
        operational_audit=bool_or_unknown(raw.get('operational_evidence_audit_passed'),'operational_evidence_audit_passed')
        full,quality_origin=quality_judgment(sem_pass,supported,readonly,ev)
        joined.append({**slot,'answer_id':answer_id,'delivered':final['delivered'],
            'semantic':{'core_facts_correct':core,'requested_answer_complete':complete,'semantic_pass':sem_pass,'sealed_review_row':sem},
            'evidence':{'evidence_supported':supported,'readonly_current_state':readonly,'additional_required_checks':review_checks,'sealed_review_row':ev},
            'protocol':{'completed':protocol_complete,'strict_protocol_pass':protocol_pass,
                'recorded_request_outcomes_audit_passed':request_audit,'owned_backend_cleanup_audit_passed':backend_audit,
                'operational_evidence_audit_passed':operational_audit,'source_and_plan_audit_passed':source_plan_pass,
                'checks':raw.get('checks',{}),'issues':raw.get('issues',[])},
            'quality_full_pass':full,'quality_full_pass_origin':quality_origin,
            'raw_metrics':{name:raw.get(name) for name in METRICS},'usage':raw.get('usage',{}),
            'provider_request_count':None,'fees':None,'resolved_effort':None})
    if bound_cells!=set(expected_cells) or len(joined)!=18:raise ValueError('all_18_cells_must_bind_once')
    joined.sort(key=lambda row:sequence.index(slots[row['cell']]))
    groups={}
    for task in TASKS:
        groups[task]={}
        for group in GROUPS:
            selected=sorted((row for row in joined if row['task']==task and row['group']==group),key=lambda row:row['round'])
            if len(selected)!=3:raise ValueError('fixed_task_group_denominator_not_3')
            passed=[row for row in selected if row['quality_full_pass'] is True]
            def aggregate(rows,denominator):
                return {'n':len(rows),'metrics':{key:stats([row['raw_metrics'].get(key) for row in rows],denominator) for key in METRICS},
                    'usage':{key:stats([row['usage'].get('observed_completed_turn_totals',{}).get(key) for row in rows],denominator) for key in TOKENS}}
            groups[task][group]={'denominator':3,'semantic_pass':sum(row['semantic']['semantic_pass'] is True for row in selected),
                'evidence_supported':sum(row['evidence']['evidence_supported'] is True for row in selected),
                'readonly_verified':sum(row['evidence']['readonly_current_state'] is True for row in selected),
                'protocol_completed':sum(row['protocol']['completed'] is True for row in selected),
                'strict_protocol_pass':sum(row['protocol']['strict_protocol_pass'] is True for row in selected),
                'recorded_request_outcomes_audit_passed':sum(row['protocol']['recorded_request_outcomes_audit_passed'] is True for row in selected),
                'owned_backend_cleanup_audit_passed':sum(row['protocol']['owned_backend_cleanup_audit_passed'] is True for row in selected),
                'operational_evidence_audit_passed':sum(row['protocol']['operational_evidence_audit_passed'] is True for row in selected),
                'quality_full_pass':sum(row['quality_full_pass'] is True for row in selected),'quality_full_fail':sum(row['quality_full_pass'] is False for row in selected),
                'quality_full_unknown':sum(row['quality_full_pass'] is None for row in selected),'all_samples':aggregate(selected,3),
                'quality_full_pass_subset':aggregate(passed,len(passed))}
    discovery=[row for row in joined if row['task']=='discovery']
    initial_false=[row for row in discovery if row['evidence']['sealed_review_row'].get('algorithm_review',{}).get('initial_false_zero_call') is not None]
    history={'scope':'counts of sealed reviewer facts; no rerun or new algorithm scoring',
        'initial_false_zero':len(initial_false),'recovered_before_final':sum(row['evidence']['sealed_review_row'].get('numerical_error_recovered') is True for row in initial_false),
        'unrecovered_final':sum(row['evidence']['sealed_review_row'].get('numerical_error_recovered') is False for row in initial_false),
        'all_47_enumerated':sum(row['evidence']['sealed_review_row'].get('coverage',{}).get('candidate_count')==47
            and row['evidence']['sealed_review_row'].get('coverage',{}).get('full_directory_enumeration_and_all_candidate_loop') is True for row in discovery),
        'attribution':'The preserved false-zero failures belong to model-authored Native geometry code, not returned product geometry calculations.',
        'sealed_reviewer_summaries':[document.get('summary') for document in evidence_documents]}
    return {'schema':'complex004-sealed-quality-cost-join-v1','denominator':18,'rows':joined,'groups':groups,'discovery_error_history':history,
        'seals':{'semantic_review':{'path':str(Path(semantic_path).resolve()),'sha256':semantic_sha},
            'evidence_reviews':evidence_seals,'evidence_review_set_sha256':evidence_set_sha,
            'analysis':{'path':str(Path(analysis_path).resolve()),'sha256':analysis_sha},
            'anonymous_answers_sha256':file_sha(answers_path),'blind_map_sha256':file_sha(root/'private/BLIND_MAP.json'),
            'review_package_binding':package,'postprocess_script_sha256':file_sha(__file__)},
        'provider_request_count':None,'fees':None,'resolved_effort':None,'requested_effort':plan.get('requested_effort'),
        'limits':['All 18 fixed slots remain; each task/group denominator is 3',
            'Root quality_full_pass remains separate from strict client-protocol and operational evidence; no new strict EXIT condition is added to root quality criteria',
            'Authoritative sealed root quality judgments are retained; absent one, only explicit quality components and required_quality_checks are conjoined',
            'receipt_unknown stays unknown in its own review/protocol field; it is not truthy and does not prove a dangling backend',
            'All-sample values include incorrect/unknown tasks; faster incorrect work is not a quality-adjusted benefit',
            'Full-pass subset is separately labelled n and cannot replace the full denominator',
            'Unknown numeric values stay null; no missing-value zero imputation or provider-price estimation',
            'Reported usage is CLI observed usage, not independently exposed provider-call count or invoice',
            'Inclusive time scopes and distinct wire byte scopes are retained; no p95/generalization from 3 samples'],
        'analysis_timing_scopes':analysis.get('timing_scopes'),'analysis_byte_scopes':analysis.get('byte_scopes'),
        'adapter_notes':['Root assembly uses input_files and evidence_file/evidence_sha256; discovery uses inputs and input_evidence path/sha256',
            'Root semantic exact_reconstruction_matches=[as_serialized] is accepted only together with exact byte reconstruction and all input hashes',
            'Both original root review files and SHA pins are retained; reviewer content and scores are never rewritten'],
        'new_model_calls':0,'new_product_calls':0,'new_Blender_runs':0,'new_scoring_calls':0}


def markdown(result):
    def seconds(value):return 'unknown' if value is None else f'{value/1e9:.3f}'
    lines=['Sealed quality and cost join. Fixed denominator: 18; three samples for every task/group.',
        '', '| Task | Group | Semantic | Evidence | Readonly | Strict protocol | Operational evidence | Quality full pass | All end-to-end median (s) | Quality subset n / median (s) |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for task in TASKS:
        for group in GROUPS:
            row=result['groups'][task][group];all_=row['all_samples'];passed=row['quality_full_pass_subset']
            lines.append(f"| {task} | {group} | {row['semantic_pass']}/3 | {row['evidence_supported']}/3 | {row['readonly_verified']}/3 | {row['strict_protocol_pass']}/3 | {row['operational_evidence_audit_passed']}/3 | {row['quality_full_pass']}/3 (+{row['quality_full_unknown']} unknown) | {seconds(all_['metrics']['total_task_wall_ns']['median'])} | {passed['n']} / {seconds(passed['metrics']['total_task_wall_ns']['median'])} |")
    lines+=['','All-sample latency includes incorrect and unknown tasks; these medians do not by themselves establish a benefit. JSON preserves every raw sample, range, tool/byte counter and observed usage, plus separately labelled full-pass subsets.',
        '', 'Fees, provider request counts and resolved actual effort are unknown. Requested effort is retained separately. No pricing or provider-call estimates are made.',
        '', 'Evidence review and semantic review are preserved separately. Strict client graceful-exit receipts are separate from request outcomes and owned-backend cleanup; no new strict EXIT condition is added to quality.',
        '', f"Discovery history: {result['discovery_error_history']['initial_false_zero']} initial false-zero results; {result['discovery_error_history']['recovered_before_final']} recovered before final; {result['discovery_error_history']['unrecovered_final']} remained wrong. All-47 enumeration was recorded for {result['discovery_error_history']['all_47_enumerated']}/9. These are model-authored Native calculation failures, not returned product calculations.",
        '', 'No model, product, Blender or new scoring was run by this join.']
    return '\n'.join(lines)+'\n'


def self_test():
    # Parser/aggregation tests are intentionally independent of real costs.
    assert review_state('receipt_unknown','test') is None and tri_and([True,None]) is None
    assert tri_and([False,True,None]) is False
    assert quality_judgment(True,True,True,{'full_pass':True,'receipt_status':'receipt_unknown'})[0] is True
    assert quality_judgment(True,True,None,{'required_quality_checks':{'receipt':'receipt_unknown'}})[0] is None
    try:quality_judgment(False,True,True,{'full_pass':True})
    except ValueError:pass
    else:raise AssertionError('wrong semantic final overridden by evidence')
    try:bool_or_unknown('not_verified','semantic')
    except ValueError:pass
    else:raise AssertionError('truthy text accepted')
    s=stats([1,None,9],3);assert s['known_n']==2 and s['median']==5 and s['values']==[1,None,9]
    assert stats([],0)['median'] is None and stats([None,None,None],3)['observed_sum'] is None
    for rows in ([{'id':'a'},{'id':'a'}],[{'id':'a'},{'id':'b'},{'id':'tail'}]):
        try:unique_rows(rows,'id',{'a','b'},'fake')
        except ValueError:pass
        else:raise AssertionError('duplicate or surplus row accepted')
    with tempfile.TemporaryDirectory(prefix='complex004-merge-fake-') as temp:
        root=Path(temp);(root/'blind/tools').mkdir(parents=True);(root/'private').mkdir()
        def save(path,value):path.write_bytes(dump_bytes(value))
        packets={};index=[]
        for i in range(18):
            name='answer'+str(i);p=root/'blind/tools'/(name+'.json');save(p,{'answer_id':name,'task_id':'assembly' if i<9 else 'discovery'})
            packets[str(p.resolve())]=file_sha(p);index.append({'answer_id':name,'task_id':'assembly' if i<9 else 'discovery','evidence':'tools/'+name+'.json','tool_calls':1})
        ip=root/'blind/TOOL_EVIDENCE_INDEX.json';save(ip,{'answers':index});packets[str(ip.resolve())]=file_sha(ip)
        prov=root/'private/TOOL_EVIDENCE_PROVENANCE.json';save(prov,{'published_files_sha256':packets})
        bound,ids=package_binding(root,{str(prov.resolve()):file_sha(prov)},'a'*64)
        assert bound['verified'] and len(ids)==18
        try:package_binding(root,{str(ip.resolve()):file_sha(ip)},'a'*64)
        except ValueError:pass
        else:raise AssertionError('index-only weak binding accepted')
        first=Path(next(p for p in packets if p.endswith('answer0.json')));first.write_text('{}')
        try:package_binding(root,{str(prov.resolve()):file_sha(prov)},'a'*64)
        except ValueError:pass
        else:raise AssertionError('changed anonymous packet accepted')
    # Explicit fixed-denominator quality split; a fast wrong row stays in all.
    fake=[{'full_pass':False,'cost':1},{'full_pass':True,'cost':10},{'full_pass':None,'cost':2}]
    assert stats([r['cost'] for r in fake],3)['median']==2
    assert stats([r['cost'] for r in fake if r['full_pass'] is True],1)['median']==10
    return {'passed':True,'fake_only':True,'checks':['unknown_not_truthy','tri_state_conjunction','duplicates_and_tail_rejected',
        'null_not_zero','entire_18_packet_binding','index_only_binding_rejected','changed_packet_rejected','fast_wrong_not_success_subset'],
        'real_cost_records_read':False,'actual_unblinded_output_created':False,'new_model_calls':0,'new_product_calls':0,'new_Blender_runs':0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE);parser.add_argument('--run',action='store_true');parser.add_argument('--self-test',action='store_true')
    for name in ('semantic-review','evidence-review','analysis','evidence-binding'):
        repeat={'action':'append'} if name=='evidence-review' else {}
        parser.add_argument('--'+name,type=Path,**repeat);parser.add_argument('--'+name+'-sha256',**repeat)
    parser.add_argument('--output-json',type=Path);parser.add_argument('--output-md',type=Path);args=parser.parse_args()
    if args.self_test:print(json.dumps(self_test()));return
    if not args.run:
        print(json.dumps({'mode':'interface_only_no_cost_read','requires':['--run','--semantic-review PATH --semantic-review-sha256 SHA',
            '--evidence-review PATH --evidence-review-sha256 SHA','--analysis PATH --analysis-sha256 SHA'],
            'optional':'--evidence-binding PATH --evidence-binding-sha256 SHA when root review uses no complete packet manifest',
            'evidence_adapter':'answers: answer_id, task_id, evidence_supported bool/null/status, readonly_current_state bool/null/status; input_files path/SHA manifest',
            'outputs':'private/FINAL_QUALITY_COST.json and .md; no overwrite'}));return
    for name in ('semantic_review','evidence_review','analysis'):
        if getattr(args,name) is None or getattr(args,name+'_sha256') is None:parser.error('--run requires explicit path and SHA256 for '+name)
    if (args.evidence_binding is None)!=(args.evidence_binding_sha256 is None):parser.error('evidence binding path/SHA must be paired')
    value=merge(args.root,args.semantic_review,args.semantic_review_sha256,args.evidence_review,args.evidence_review_sha256,
        args.analysis,args.analysis_sha256,args.evidence_binding,args.evidence_binding_sha256)
    output=args.output_json or args.root/'private/FINAL_QUALITY_COST.json';md=args.output_md or args.root/'private/FINAL_QUALITY_COST.md'
    if output.exists() or md.exists():raise FileExistsError('final_join_outputs_are_exclusive')
    with output.open('xb') as stream:stream.write(dump_bytes(value))
    with md.open('x',encoding='utf8',newline='\n') as stream:stream.write(markdown(value))
    print(json.dumps({'output_json':str(output),'output_md':str(md),'denominator':18,'quality_full_pass':sum(row['quality_full_pass'] is True for row in value['rows'])}))


if __name__=='__main__':main()
