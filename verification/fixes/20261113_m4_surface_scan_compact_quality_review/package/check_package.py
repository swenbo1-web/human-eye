"""Offline anonymous package review. No private content decoding or scoring.

Private batch files may only be streamed through byte/hash comparisons. Their
names are represented by ordinal and path hash in this review's artifacts.
Only r2 ZIP is opened. Initial administrative perf_ns values are used in memory
for exact two-field projection comparison, never printed or persisted here.
"""
import collections, copy, hashlib, io, json, pathlib, subprocess, traceback, zipfile

ROOT=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=ROOT/'verification/m4_surface_scan_compact_consumption_001'
PUB=B/'quality/public'
ORIGINAL=B/'runtime/handoff_01/public'
OUT=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_quality_review/package')
COMMIT='f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907'
ZIP_SHA='5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f'
PUBLIC_SHA='03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101'
ORIGINAL_SHA='1b8136e92e8533d6a7b95dddf952165ed58baff206c4551aa473728cbf20b8b2'
checks=[];inputs={};facts={};seen_files=set()
def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def encoded(obj):return (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
def raw(path):
    p=pathlib.Path(path); data=p.read_bytes();seen_files.add(str(p.resolve()).lower());inputs[p.relative_to(B).as_posix()]={'bytes':len(data),'sha256':sha(data),'mode':'authorized_public_or_administrative_read'};return data
def js(path):return json.loads(raw(path))
def check(name,value):checks.append({'check':name,'passed':bool(value)})
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def git_blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def manifest(files):return [{'path':name,'bytes':len(data),'sha256':sha(data)} for name,data in sorted(files.items())]
def keyscan(obj):
    if isinstance(obj,dict):
        for key,value in obj.items():
            yield key;yield from keyscan(value)
    elif isinstance(obj,list):
        for value in obj:yield from keyscan(value)

def main():
    head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();facts['head']=head
    check('fixed_commit',head==COMMIT);check('author_tree_clean_before',status=='')
    tree={}
    for line in git('ls-tree','-rz',COMMIT).split(b'\0'):
        if line:
            meta,name=line.split(b'\t',1);tree[name.decode()]=meta.split()[2].decode()
    delivery=js(B/'DELIVERY_MANIFEST.json');records=delivery['files'];check('batch_manifest_count',len(records)==delivery['file_count']==2335)
    check('batch_manifest_unique_paths',len({r['path'] for r in records})==len(records))
    actual={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json'}
    check('batch_manifest_exact_file_set',actual=={r['path'] for r in records})
    total=0
    # Byte/hash validation only: do not JSON-decode or ZIP-open any batch member.
    for ordinal,row in enumerate(records,1):
        path=B/row['path'];data=path.read_bytes();seen_files.add(str(path.resolve()).lower());digest=sha(data);total+=len(data)
        identifier=f'blind_batch_file_{ordinal:04}'
        inputs[identifier]={'path_sha256':sha(row['path'].encode()),'bytes':len(data),'sha256':digest,'mode':'byte_hash_only_no_content_decoding'}
        check(identifier+':manifest',len(data)==row['bytes'] and digest==row['sha256'])
        check(identifier+':git',tree.get(path.relative_to(ROOT).as_posix())==git_blob(data))
    check('batch_total_bytes',total==delivery['total_bytes'])
    check('manifest_itself_git',tree.get((B/'DELIVERY_MANIFEST.json').relative_to(ROOT).as_posix())==git_blob(raw(B/'DELIVERY_MANIFEST.json')))
    facts['blind_batch_files']=len(records);facts['blind_batch_bytes']=total
    package=js(B/'quality/PACKAGE_RECEIPT.json');redaction=js(B/'quality/ADMIN_REDACTION.json');ready=js(B/'FORMAL_QUALITY_READY.json')
    raw(B/'QUALITY_HANDOFF_REPORT.md')
    check('redaction_script_hash',sha(raw(B/'scoring/redact_handoff_admin.py'))==redaction['script_sha256'])
    check('package_redaction_receipt_binding',sha(raw(B/'quality/ADMIN_REDACTION.json'))==package['administrative_projection_receipt_sha256'])
    public={p.relative_to(PUB).as_posix():raw(p) for p in PUB.rglob('*') if p.is_file()}
    original={p.relative_to(ORIGINAL).as_posix():raw(p) for p in ORIGINAL.rglob('*') if p.is_file()}
    check('public_original_file_sets',set(public)==set(original) and len(public)==42)
    new_manifest=manifest(public);old_manifest=manifest(original)
    new_canonical=sha(canonical(new_manifest));old_canonical=sha(canonical(old_manifest))
    check('final_public_canonical',new_canonical==PUBLIC_SHA==redaction['final_public_manifest_sha256']==package['public_canonical_sha256']==ready['final_public_canonical_sha256'])
    check('initial_public_canonical',old_canonical==ORIGINAL_SHA==redaction['source_public_manifest_sha256'] and old_canonical!=new_canonical)
    check('final_public_manifest_entries',new_manifest==redaction['final_public_manifest'])
    facts['initial_public_canonical_sha256']=old_canonical;facts['final_public_canonical_sha256']=new_canonical;facts['public_file_count']=len(public)
    data=raw(B/'quality/SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip');check('r2_zip_digest',sha(data)==ZIP_SHA==package['sha256']==ready['final_anonymous_zip_sha256']);check('r2_zip_size',len(data)==package['bytes']==295089)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist();check('zip_unique_names',len(names)==len(set(names))==42);check('zip_exact_members',set(names)==set(public))
        check('zip_relative_paths',all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in names))
        for name in names:check('r2_member:'+name,z.read(name)==public[name])
    check('zip_package_inventory',package['public_file_count']==42 and package['final_texts_present']==9)
    index=json.loads(public['INDEX.json']);old_index=json.loads(original['INDEX.json'])
    check('old_index_hash',sha(original['INDEX.json'])==redaction['source_INDEX_sha256'])
    check('new_index_hash',sha(public['INDEX.json'])==redaction['final_INDEX_sha256'])
    check('original_index_encoding',encoded(old_index)==original['INDEX.json'])
    expected=copy.deepcopy(old_index);removed=[]
    for ai,a in enumerate(expected['answers']):
        for ei,error in enumerate(a['consumer_execution_errors']):
            check(f'error_envelope_shape:{ai}:{ei}',set(error)=={'event','perf_ns'})
            value=error.pop('perf_ns');check(f'error_timestamp_type:{ai}:{ei}',type(value) is int)
            removed.append({'pointer':f'$/answers/{ai}/consumer_execution_errors/{ei}/perf_ns','rule':'known_consumer_error_administrative_perf_counter','removed_value_canonical_sha256':sha(canonical(value)),'event_payload_canonical_sha256':sha(canonical(error['event']))})
    check('exact_two_field_derivation',encoded(expected)==public['INDEX.json'])
    check('exact_registered_redactions',removed==redaction['removals'] and len(removed)==2)
    check('exact_known_positions',{r['pointer'] for r in removed}=={'$/answers/1/consumer_execution_errors/0/perf_ns','$/answers/3/consumer_execution_errors/0/perf_ns'})
    restored=copy.deepcopy(index)
    for ai,a in enumerate(old_index['answers']):
        for ei,error in enumerate(a['consumer_execution_errors']):
            if 'perf_ns' in error:restored['answers'][ai]['consumer_execution_errors'][ei]['perf_ns']=error['perf_ns']
    check('restored_original_bytes',encoded(restored)==original['INDEX.json'])
    for name in public:
        if name!='INDEX.json':check('unchanged_public_file:'+name,public[name]==original[name])
    check('forty_one_unchanged',sum(public[n]==original[n] for n in public)==41)
    # Administrative keys checked only in INDEX. Do not scrub tool fact payloads.
    check('index_has_no_timing_usage_envelope_keys',not set(keyscan(index)) & {'perf_ns','elapsed_ns','duration_ns','usage','input_tokens','output_tokens','group','arm','condition'})
    answers=index['answers'];check('nine_unique_answers',len(answers)==index['fixed_slots']==9 and len({a['anonymous_id'] for a in answers})==9)
    check('no_preexisting_quality_scoring',index['scoring_performed'] is False and package['formal_quality_scoring_performed'] is False and ready['formal_quality_scoring_performed'] is False)
    check('controller_started_nine',index['controller_execution']['started_cells']==9 and index['controller_execution']['status']=='terminal')
    expected_names={'INDEX.json','README.md','tasks/T1.txt','scoring/SCORING_CONTRACT.json','scoring/ACTUAL_SNAPSHOT.json','scoring/TRUTH.json'}
    execution=collections.Counter();error_count=attempt_count=event_count=0
    facts['anonymous_rows']=[]
    for a in answers:
        label=a['anonymous_id'];directory=a['directory'];check(label+':directory_id',label==directory)
        names=[a['answer_file'],a['cli_output_corroboration'],a['source_consistency_file'],a['evidence_file']]
        expected_names.update(directory+'/'+n for n in names)
        final=public[directory+'/'+a['answer_file']];cli=public[directory+'/'+a['cli_output_corroboration']]
        check(label+':answer_cli_equal',final==cli and len(final)>0)
        check(label+':final_sha',sha(final)==a['answer_original_sha256']==a['source_provenance']['public_final_sha256'])
        check(label+':final_present',a['answer_state']=='present' and a['task_id']=='T1' and a['unconfirmed_public_messages']==[])
        source=json.loads(public[directory+'/'+a['source_consistency_file']]);evidence=json.loads(public[directory+'/'+a['evidence_file']])
        check(label+':consumer_provenance',a['source_provenance']['consumer_record_sha256']==source['source_records_sha256']['CONSUMER.json'])
        check(label+':source_initial_final_hash_links',source['INITIAL_original_file_sha256']==source['source_records_sha256']['owner/INITIAL.json'] and source['FINAL_original_file_sha256']==source['source_records_sha256']['owner/FINAL.json'])
        check(label+':source_asset_consistency',source['ACTOR_CONFIG']['asset_sha256']==source['owner_IDENTITY']['asset_sha256']==ready['input_scene_sha256'])
        close=source['CLOSE'];wf=close['worker_fingerprint_fields'];wc=close['worker_closed']
        check(label+':source_fingerprint_fields',wf['initial_geometry_fingerprint']==wc['initial_geometry_fingerprint'] and wf['final_geometry_fingerprint']==wc['final_geometry_fingerprint'])
        inp=source['CONSUMER_INPUT'];check(label+':text_only_input',inp['input_image_count']==inp['input_image_bytes']==0 and inp['initial_image_sha256'] is None)
        check(label+':image_unknown_preserved',all(inp['image_delivery'][key] is None for key in ['model_view_confirmed','prepared_file_verified','provider_delivery_confirmed']))
        check(label+':producer_scope_preserved','Existing producer fields' in source['scope'])
        errors=a['consumer_execution_errors'];error_count+=len(errors);execution[a['cell_execution_state']]+=1
        check(label+':execution_states_consistent',a['cell_execution_state']==a['execution_record_state'])
        check(label+':failure_retained',a['consumer_valid_completion']==(not errors) and a['cell_execution_state']==('failed' if errors else 'completed'))
        for error in errors:check(label+':error_event_preserved',set(error)=={'event'} and error['event']['type']=='error' and 'stream disconnected before completion' in error['event']['message'])
        attempts=evidence['owner_attempts'];events=evidence['public_tool_events'];attempt_count+=len(attempts);event_count+=len(events)
        check(label+':attempt_order',[x['order'] for x in attempts]==list(range(1,len(attempts)+1)))
        check(label+':event_pair_counts',len(events)==len(attempts)*2)
        check(label+':requests_responses_retained',all(not x['request_missing'] and not x['response_missing'] for x in attempts))
        facts['anonymous_rows'].append({'anonymous_id':label,'state':a['cell_execution_state'],'final_sha256':sha(final),'cli_equal':final==cli,'consumer_error_count':len(errors),'business_attempts':len(attempts)})
    check('exact_public_42_expected_layout',set(public)==expected_names)
    check('execution_denominator',dict(execution)=={'completed':7,'failed':2} and error_count==2)
    check('all_public_business_attempts',attempt_count==27 and event_count==54)
    check('receipt_execution_counts',package['execution_counts']==ready['execution_counts']=={'completed':7,'failed':2,'not_run':0})
    for record in index['scoring_materials']:check('scoring_material_hash:'+record['file'],sha(public[record['file']])==record['sha256'])
    check('same_task_bytes',len(index['tasks'])==1 and sha(public[index['tasks'][0]['prompt']])==index['tasks'][0]['input_sha256']==ready['input_prompt_sha256'])
    for name,digest in redaction['historical_zip_sha256_unchanged'].items():
        # Hash bytes only; never open the initial archive or expose its timestamps.
        check('historical_anonymous_zip_retained',sha((B/'quality'/name).read_bytes())==digest)
    facts['business_attempts']=attempt_count;facts['public_tool_events']=event_count;facts['execution_counts']=dict(execution);facts['redaction_count']=len(removed);facts['zip_sha256']=ZIP_SHA
    check('author_tree_clean_after',git('status','--porcelain=v1').decode()==status and git('rev-parse','HEAD').decode().strip()==head)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    try:main()
    except Exception as error:
        # No exception arguments: these could contain protected private values.
        checks.append({'check':'review_script_exception','passed':False,'exception_type':type(error).__name__,'location':[{'file':pathlib.Path(x.filename).name,'line':x.lineno,'function':x.name} for x in traceback.extract_tb(error.__traceback__)]})
    result={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'failed':[x for x in checks if not x['passed']],'input_hash_records':len(inputs),'unique_input_files':len(seen_files),'facts':facts,'scope':{'answer_scoring':False,'private_mapping_decoded':False,'private_cost_decoded':False,'original_perf_ns_values_published':False,'new_product_Blender_model_API_runs':0,'formal_consumer_denominator':9}}
    for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'all_passed':result['all_passed'],'checks':len(checks),'failed':result['failed'],'input_hash_records':len(inputs),'unique_input_files':len(seen_files),'public_files':facts.get('public_file_count'),'blind_batch_files':facts.get('blind_batch_files'),'redactions':facts.get('redaction_count')},ensure_ascii=False))
