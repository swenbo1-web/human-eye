"""Offline facts/counts/UTF-8 comparison for M1-NEAREST-EVIDENCE-001.

Reads completed guarded-run artifacts only. Never imports product/test modules
or launches a model, solver, Blender, installation or subprocess.
"""
import argparse
import ast
import copy
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE_SHA='0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
NEW_MODULE='verification/m1_nearest_evidence_001/tests/test_nearest_evidence.py'
DIRECT_MODULE='verification/nearest_integration_001/tests/test_integration.py'
ADDED=('best_known_evidence','measurement_semantics')
REMOVED_ROOT=frozenset((*ADDED,'trace_id'))
COUNTS=frozenset(('capture','pair','kernel','rank','nearest','closed_solid'))
SENTINEL='VERIFIED_RUNTIME_SOURCE_SHA256'


def require(condition,reason):
    if not condition:raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')


def canonical_json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def same(left,right):
    return canonical_json(left)==canonical_json(right)


def save(path,value):
    Path(path).write_bytes(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode('utf8')+b'\n')


def source_values(value,expected):
    """Replace only the exact-validated runtime hash, at any actual hash field."""
    if type(value) is dict:
        answer={}
        for key,item in value.items():
            if key=='runtime_source_sha256':
                require(item==expected,'runtime_source_sha256_mismatch')
                answer[key]=SENTINEL
            else:answer[key]=source_values(item,expected)
        return answer
    if type(value) is list:return [source_values(item,expected) for item in value]
    return value


def core(body,expected):
    require(type(body) is dict and type(body.get('binding')) is dict,'body_binding_missing')
    require(body['binding'].get('runtime_source_sha256')==expected,'body_runtime_source_mismatch')
    # Only these three ROOT fields can be removed. No nested facts/binding
    # fields, epoch, fingerprint, instance token or proof fields are dropped.
    return source_values({key:value for key,value in body.items() if key not in REMOVED_ROOT},expected)


def load_run(folder,role,expected):
    identity=read(folder/'EXECUTION_IDENTITY.json');result=read(folder/'RESULTS.json')
    require(identity['role']==role and result['role']==role,'runner_role_mismatch')
    require(identity['runtime_source_sha256']==expected and result['runtime_source_sha256']==expected,'runner_runtime_mismatch')
    require(identity['source_count']==137 and result['source_count']==137,'source_count_mismatch')
    require(result['successful'] is True,'runner_not_successful')
    require(not result['external_operation_attempts'] and result['model_consumers']==0
        and result['Blender_sessions']==0 and result['network_sessions']==0,'runner_external_operation')
    require(identity['guard_verify_loaded'] is True and identity['checkout_files_unchanged'] is True
        and identity['loaded_tests_unchanged'] is True and identity['original_read_evidence_unchanged'] is True,'runner_guard_not_confirmed')
    manifest=identity['manifest']
    require(type(manifest) is list and len(manifest)==137,'manifest_count')
    require(len({row['path'] for row in manifest})==137,'duplicate_source_path')
    require(manifest==sorted(manifest,key=lambda row:row['path']),'manifest_order')
    engine=(folder/'engine').resolve()
    for row in manifest:
        path=(engine/row['path']).resolve()
        require(path.is_relative_to(engine),'source_manifest_path_escape')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'source_snapshot_bytes_mismatch:'+row['path'])
    tree=ast.parse((engine/'human_eye_plugin/runtime_identity.py').read_bytes())
    constants={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
    material={'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':manifest}
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    require(digest==expected,'source_canonical_mismatch')
    host_sha=next(row['sha256'] for row in manifest if row['path']=='human_eye_plugin/blender_host.py')
    evidence=read(folder/'EVIDENCE.json')
    return {'folder':folder,'identity':identity,'result':result,'evidence':evidence,'source':expected,'host_sha':host_sha}


def artifact(folder,name,raw,scope):
    path=folder/name;path.write_bytes(raw)
    return {'path':str(path),'utf8_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'scope':scope}


def persist_body(folder,role,body,row=None):
    result={}
    result['body']=artifact(folder,role+'.body.json.utf8',encoded(body),
        'complete result body, compact UTF-8 JSON re-encoding; not a network frame')
    added={key:body[key] for key in ADDED if key in body}
    result['added_fields']=artifact(folder,role+'.added-fields.json.utf8',encoded(added),
        'compact JSON object containing only the two root evidence additions; includes its braces')
    result['added_fields_present']=bool(added)
    result['added_fields_payload_utf8_bytes']=len(encoded(added)) if added else 0
    if row is not None and row.get('raw_text') is not None:
        text=row['raw_text'];require(type(text) is str,'raw_content_text_not_string')
        require(same(json.loads(text),body),'raw_content_text_body_mismatch')
        result['content_text']=artifact(folder,role+'.content-text.utf8',text.encode('utf8'),
            'exact UTF-8 of captured MCP content[0].text string; not a network frame')
    if row is not None and row.get('raw_tool_result') is not None:
        tool=row['raw_tool_result'];raw=row.get('raw_tool_result_json')
        require(type(raw) is str and same(json.loads(raw),tool),'captured_tool_object_encoding_mismatch')
        require(type(tool.get('content')) is list and len(tool['content'])==1
            and tool['content'][0].get('type')=='text','unexpected_tool_content_shape')
        require(same(json.loads(tool['content'][0]['text']),body),'tool_body_mismatch')
        if row.get('raw_text') is not None:require(tool['content'][0]['text']==row['raw_text'],'tool_raw_text_mismatch')
        result['tool_result_object']=artifact(folder,role+'.tool-result-object.json.utf8',raw.encode('utf8'),
            'exact UTF-8 of test-captured JSON serialization of full MCP tool-result object; re-encoded object, not stdio/network bytes')
    return result


def original_measurements(case,row,cases):
    """A warm result reuses the earlier recorded same-bound cold measurement."""
    ids=[item['id'] for item in row['body']['best_known_objects']]
    if all(oid in row['measurements'] for oid in ids):
        return row['measurements'],case
    require(not row['measurements'] and row['diagnostics'].get('result_cache_hit') is True
        and all(row['counts'][key]==0 for key in ('pair','kernel','rank','nearest')),
        'measurement_missing_without_recorded_result_cache_hit:'+case)
    matches=[]
    for name,other in cases.items():
        if (name!=case and same(other['capture_binding'],row['capture_binding'])
                and same(other['body']['focal'],row['body']['focal'])
                and same(other['body']['best_known_objects'],row['body']['best_known_objects'])
                and same(other['body']['binding'],row['body']['binding'])
                and all(oid in other['measurements'] for oid in ids)):
            matches.append((name,other['measurements']))
    require(bool(matches),'same_bound_cold_measurement_missing:'+case)
    require(all(same(matches[0][1],value) for _,value in matches),'same_bound_cold_measurements_conflict:'+case)
    name,value=sorted(matches,key=lambda pair:pair[0])[0]
    return value,name


def validate_entry(row,run,role,measurements):
    body=row['body'];calculated=core(body,run['source'])
    require(same({key:value for key,value in body.items() if key not in REMOVED_ROOT},row['core']),'recorded_core_not_body_minus_root_fields')
    require(body['result_kind']=='surface_nearest' and body['unit']=='m','nearest_body_contract')
    binding=body['binding'];capture=row['capture_binding']
    require(binding['host_source_sha256']==run['host_sha']==capture['host_source_sha256'],'entry_host_source_mismatch')
    require(binding['document_epoch']==capture['host_identity']['document_epoch'],'entry_document_epoch_mismatch')
    require(binding['directory_sha256']==capture['directory_sha256'],'entry_directory_mismatch')
    require(capture['unit']=='m' and capture['coordinate_frame']=='world' and capture['same_main_thread_read'] is True,'entry_capture_contract')
    known=body['best_known_objects'];ids=[item['id'] for item in known]
    require(len(ids)==len(set(ids)),'duplicate_best_known_ID')
    require(body['focal']['id'] in capture['host_identity']['object_instances'],'focal_not_bound_to_capture')
    require(all(oid in capture['host_identity']['object_instances'] for oid in ids),'best_known_not_bound_to_capture')
    if body['status']=='complete':require(same(body['nearest_objects'],known),'complete_nearest_best_known_mismatch')
    else:require(body['nearest_objects'] is None and body['distance_m'] is None,'incomplete_promoted_to_global')
    require(set(row['counts'])==COUNTS and all(type(v) is int and v>=0 for v in row['counts'].values()),'count_shape')
    require(all(oid in measurements for oid in ids),'best_known_measurement_missing')
    if role=='baseline':
        require(not set(ADDED).intersection(body),'baseline_has_new_evidence_fields')
    else:
        evidence=body['best_known_evidence'];semantics=body['measurement_semantics']
        expected_semantics={'distance':'unsigned_surface_distance_not_penetration_depth',
            'coordinate_frame':'world','pair_order':'focal_to_candidate',
            'method':measurements[ids[0]].get('method') if ids else None}
        require(same(semantics,expected_semantics),'measurement_semantics_not_original_method')
        require(type(evidence) is list and len(evidence)==len(ids),'evidence_winner_count')
        for named,item,oid in zip(known,evidence,ids):
            measured=measurements[oid]
            expected={'candidate':named,
                **{key:measured.get(key) for key in ('point_a_world','point_b_world','direction_a_to_b','witness_status','direction_status')},
                **{key:measured[key] for key in ('witness_reason','direction_reason') if key in measured}}
            require(same(item,expected),'evidence_not_original_winner_measurement:'+oid)
            if measured['witness_status']=='measured':
                require(abs(math.dist(item['point_a_world'],item['point_b_world'])-measured['distance_m'])<=1e-9,'original_witness_publication_tolerance')
    return calculated


def compare(baseline,candidate,output,candidate_sha):
    output.mkdir(exist_ok=False)
    summary={'scope':'offline fixed-input facts/call-count/payload comparison; no new product or model execution',
        'baseline_source_sha256':BASE_SHA,'candidate_source_sha256':candidate_sha,
        'normalization':['remove only root best_known_evidence/measurement_semantics/trace_id',
            'exact-validate each runtime_source_sha256 then replace with one shared sentinel'],
        'binding_policy':'never remove epoch, fingerprint, directory, source, instance or other original fields',
        'errors':[],'direct_groups':[],'entry_cases':[],'model_benefit_measured':False,'passed':False}
    try:
        runs=[load_run(baseline,'baseline',BASE_SHA),load_run(candidate,'candidate',candidate_sha)]
        old,new=runs
        require(same(old['identity']['loaded_tests'],new['identity']['loaded_tests']),'loaded_test_source_differs')
        require(same(old['identity']['fixture_sha256'],new['identity']['fixture_sha256']),'loaded_fixture_source_differs')
        require(old['identity']['runner_sha256']==new['identity']['runner_sha256'],'runner_source_differs')
        require(same(old['identity']['original_read_evidence_sha256'],
            new['identity']['original_read_evidence_sha256']),'original_evidence_source_differs')
        require(old['host_sha']==new['host_sha'],'host_changed_outside_batch')
        summary['runner_tests']={role:{'tests':run['result']['tests'],'skipped':run['result']['skipped']}
            for role,run in zip(('baseline','candidate'),runs)}
        old_direct,new_direct=[run['evidence'][DIRECT_MODULE] for run in runs]
        require(set(old_direct)==set(new_direct) and len(old_direct)>=9,'direct_group_set_or_minimum9_mismatch')
        for group in sorted(old_direct):
            before,after=old_direct[group],new_direct[group]
            group_folder=output/('direct_'+group);group_folder.mkdir()
            normalized=[]
            for role,row,run in zip(('baseline','candidate'),(before,after),runs):
                value=copy.deepcopy(row)
                for index,observation in enumerate(value['observations']):
                    body=observation['result']
                    persist_body(group_folder,role+'.'+str(index+1).zfill(2),body)
                    # Validate the exact pin here, then leave the original
                    # value for the single whole-row normalization below.
                    # Normalizing twice would reject our own sentinel.
                    core(body,run['source'])
                    observation['result']={key:item for key,item in body.items()
                        if key not in REMOVED_ROOT}
                normalized.append(source_values(value,run['source']))
            equal=same(*normalized)
            record={'group':group,'observations':len(before['observations']),
                'strict_full_original_row_equal':equal,
                'scope':'fixed direct packet fixtures; full observations/measurements/diagnostics/counters and all bindings preserved'}
            summary['direct_groups'].append(record)
            require(equal,'direct_original_facts_or_counts_changed:'+group)
        old_cases,new_cases=[run['evidence'][NEW_MODULE] for run in runs]
        require(set(old_cases)==set(new_cases) and len(old_cases)>=18,'new_entry_case_set_mismatch')
        for case in sorted(old_cases):
            before,after=old_cases[case],new_cases[case]
            safe=case.replace('.','_')
            require(safe and all(c.isalnum() or c in '_-' for c in safe),'invalid_case_artifact_name')
            folder=output/('entry_'+safe);folder.mkdir()
            sizes={role:persist_body(folder,role,row['body'],row)
                for role,row in (('baseline',before),('candidate',after))}
            old_measurements,old_measurement_case=original_measurements(case,before,old_cases)
            new_measurements,new_measurement_case=original_measurements(case,after,new_cases)
            old_core=validate_entry(before,old,'baseline',old_measurements)
            new_core=validate_entry(after,new,'candidate',new_measurements)
            same_input=same(source_values(before['capture_binding'],BASE_SHA),source_values(after['capture_binding'],candidate_sha))
            counts_equal=same(before['counts'],after['counts'])
            record={'case':case,'source_and_evidence_self_checks':True,'input_capture_binding_equal':same_input,
                'measurement_evidence_case':{'baseline':old_measurement_case,'candidate':new_measurement_case},
                'call_counts_equal':counts_equal,'counts':{'baseline':before['counts'],'candidate':after['counts']},
                'original_core_equal':same(old_core,new_core) if same_input else None,
                'measurements_equal':same(before['measurements'],after['measurements']) if same_input else None,
                'diagnostics_equal':same(before['diagnostics'],after['diagnostics']) if same_input else None,
                'packet_work_equal':same(before['packet_work'],after['packet_work']) if same_input else None,
                'cross_version_scope':'strict complete core+binding comparison' if same_input else
                    'not full-pair comparable: capture binding differs; each entry source verified without stripping fields',
                'payloads':sizes,'payload_deltas':{}}
            for representation in ('body','content_text','tool_result_object'):
                if representation in sizes['baseline'] and representation in sizes['candidate']:
                    record['payload_deltas'][representation]=sizes['candidate'][representation]['utf8_bytes']-sizes['baseline'][representation]['utf8_bytes']
            record['added_fields_payload_utf8_bytes']=sizes['candidate']['added_fields_payload_utf8_bytes']
            summary['entry_cases'].append(record)
            require(counts_equal,'entry_capture_pair_kernel_rank_count_changed:'+case)
            if same_input:
                for field in ('original_core_equal','measurements_equal','diagnostics_equal','packet_work_equal'):
                    require(record[field] is True,field+':'+case)
        summary['payload_totals']={representation:{
            'baseline_utf8_bytes':sum(row['payloads']['baseline'].get(representation,{}).get('utf8_bytes',0) for row in summary['entry_cases']),
            'candidate_utf8_bytes':sum(row['payloads']['candidate'].get(representation,{}).get('utf8_bytes',0) for row in summary['entry_cases']),
            'paired_cases':sum(representation in row['payloads']['baseline'] and representation in row['payloads']['candidate'] for row in summary['entry_cases'])}
            for representation in ('body','content_text','tool_result_object')}
        summary['candidate_added_fields_payload_utf8_bytes']=sum(row['added_fields_payload_utf8_bytes'] for row in summary['entry_cases'])
        summary['strict_entry_core_pairs']=sum(row['original_core_equal'] is True for row in summary['entry_cases'])
        summary['entry_pairs_with_different_capture_binding']=sum(not row['input_capture_binding_equal'] for row in summary['entry_cases'])
        summary['payload_scope']='Body/object JSON byte counts are explicitly labelled re-encodings; captured content-text bytes are exact strings, not network frames. Added-field object bytes include braces and are not asserted equal to complete response delta.'
        summary['second_query_cost']='Not measured by this comparator; no second tool request is executed or inferred.'
        summary['passed']=True
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:
        summary['errors'].append({'type':type(exc).__name__,'message':str(exc)})
    save(output/'RESULTS.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',default='baseline_02')
    parser.add_argument('--candidate',default='candidate_02')
    parser.add_argument('--candidate-source-sha256',required=True)
    parser.add_argument('--output',required=True,help='New immediate child comparison directory; never overwrite evidence')
    args=parser.parse_args()
    require(len(args.candidate_source_sha256)==64 and all(c in '0123456789abcdef' for c in args.candidate_source_sha256),'invalid_candidate_canonical')
    require(Path(args.output).name==args.output and args.output not in ('.','..'),'invalid_output_name')
    before=Path(args.baseline);after=Path(args.candidate)
    before=before if before.is_absolute() else HERE/before
    after=after if after.is_absolute() else HERE/after
    result=compare(before,after,HERE/args.output,args.candidate_source_sha256)
    print(json.dumps({'passed':result['passed'],'output':str(HERE/args.output),'errors':result['errors']},ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
