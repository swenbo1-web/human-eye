"""Independent offline evidence review. No product imports or execution."""
import ast, base64, csv, datetime, hashlib, io, json, pathlib, re, subprocess, traceback, zipfile, zlib

ROOT = pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = ROOT / 'verification/m4_surface_scan_compact_facts_001'
E = B / 'engineering/run_01'
OUT = pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_review/binding')
PRODUCT = '452b44d2dcf231d6675bef54e568db0431a29261'
DELIVERY = '6ab4e53409e539c71a377f48708f2f8725db6dde'
BASE = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
checks, inputs, facts = [], {}, {}
def sha(data): return hashlib.sha256(data).hexdigest()
def raw(path):
    p=pathlib.Path(path); data=p.read_bytes(); inputs[str(p)]={'bytes':len(data),'sha256':sha(data)}; return data
def js(path): return json.loads(raw(path).decode('utf-8-sig'))
def check(label, condition, detail=None):
    checks.append({'check':label,'passed':bool(condition),**({'detail':detail} if detail is not None else {})})
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def tree(commit):
    result={}
    for row in git('ls-tree','-rz',commit).split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1); result[path.decode()]=meta.split()[2].decode()
    return result
def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()

def main():
    facts['head']=git('rev-parse','HEAD').decode().strip()
    facts['git_status_before']=git('status','--porcelain=v1').decode()
    check('head_is_fixed_delivery',facts['head']==DELIVERY)
    check('author_tree_clean_before',facts['git_status_before']=='')
    pt,dt=tree(PRODUCT),tree(DELIVERY)
    manifest=js(B/'DELIVERY_MANIFEST.json')
    manifest_paths={x['path'] for x in manifest['files']}
    actual_paths={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json'}
    check('delivery_manifest_exact_files',manifest_paths==actual_paths,{'listed':len(manifest_paths),'actual':len(actual_paths)})
    check('delivery_manifest_file_count',manifest['file_count']==len(manifest_paths)==329)
    total=0
    for row in manifest['files']:
        data=raw(B/row['path']); total+=len(data)
        check('manifest:'+row['path'],len(data)==row['bytes'] and sha(data)==row['sha256'])
        path=(B/row['path']).relative_to(ROOT).as_posix()
        check('delivery_git:'+row['path'],dt.get(path)==blob(data))
    check('manifest_total_bytes',total==manifest['total_bytes'])
    check('manifest_itself_in_git',dt[B.relative_to(ROOT).as_posix()+'/DELIVERY_MANIFEST.json']==blob(raw(B/'DELIVERY_MANIFEST.json')))
    old=ROOT/'verification/m4_surface_scan_consumption_001/DELIVERY_MANIFEST.json'
    check('reuse_old_1974_manifest_unchanged',sha(raw(old))=='1ead579f888711876cb6295d86c3134285bcf578e278247c8ea5a8affc66ce2d')
    seal=pathlib.Path('D:/hefe/verification/fixes/20261112_m4_surface_scan_consumer_quality_review/QUALITY_SEAL.json')
    check('reuse_root_quality_seal_unchanged',sha(raw(seal))=='1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f')
    facts['reused_old_review']={'root_commit':'91cce49cd83c5dd00bac270b2ae128a2ede5b3ba','scope':'1974 original consumer files; not repeated in this review'}
    source=js(B/'CANDIDATE_SOURCE.json'); ready=js(B/'installation/run_01/READY.json'); installed=pathlib.Path(ready['install_root']); release=pathlib.Path(ready['release'])
    aggregate=sha(canonical({'base_version':source['base_version'],'implementation_revision':source['implementation_revision'],'files':source['source_files']}))
    check('source_aggregate',aggregate==source['source_sha256']=='4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6')
    check('source_count',len(source['source_files'])==source['source_count']==138)
    check('fixed_candidate',source['commit']==ready['commit']==PRODUCT)
    wheel=next((B/'installation/run_01/bundle').glob('*.whl')); wheel_data=raw(wheel)
    check('wheel_digest',sha(wheel_data)==ready['wheel_sha256']=='f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792')
    w=zipfile.ZipFile(io.BytesIO(wheel_data)); names=w.namelist(); check('wheel_members_unique',len(names)==len(set(names)))
    changed=set(git('diff','--name-only',BASE,PRODUCT).decode().splitlines())
    source_paths={s['path'] for s in source['source_files']}
    check('only_one_product_source_changed',changed & source_paths=={'human_eye_plugin/live_spatial_mcp.py'})
    check('no_product_change_delivery_after_candidate',not set(git('diff','--name-only',PRODUCT,DELIVERY).decode().splitlines()) & source_paths)
    for row in source['source_files']:
        name=row['path']; data=raw(ROOT/name)
        check('source_git:'+name,sha(data)==row['sha256'] and pt.get(name)==blob(data))
        check('archive_source:'+name,raw(B/'installation/run_01/source_452b44d2'/name)==data)
        check('wheel_source:'+name,w.read(name)==data)
        check('installed_source:'+name,raw(installed/name)==data)
    record=next(n for n in names if n.endswith('.dist-info/RECORD')); record_rows=list(csv.reader(io.StringIO(w.read(record).decode())))
    for name,digest,size in record_rows:
        data=w.read(name)
        if digest:
            check('wheel_record:'+name,digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=') and int(size)==len(data))
        check('wheel_install:'+name,raw(installed/name)==data)
    facts['wheel_members']=len(names); facts['source_count']=len(source_paths); facts['source_sha256']=aggregate
    install=js(B/'installation/run_01/receipt/ISOLATED_INSTALL.json')
    for name,key in [('target_runtime_entry.py','launcher_sha256'),('installed_release.py','admin_sha256'),('RUNTIME_BINDING.json','binding_sha256')]:
        check('admin:'+name,sha(raw(release/'admin'/name))==install[key])
    template=raw(B/'installation/run_01/source_452b44d2/examples/agents/target_runtime_entry.py').decode()
    ident={k:source[k] for k in ['base_version','implementation_revision','source_sha256']};ident['build_id']='sha256:'+aggregate;ident['distribution_version']=ready['version']
    for key,expr in [('RELEASE_NAME',repr(ready['version'])),('DEPENDENCY_PYTHON','Path('+repr(ready['dependency_python'])+')'),('SOURCE_SHA256',repr(aggregate))]:
        template=re.sub('^'+key+' = .*$',lambda m:key+' = '+expr,template,flags=re.M)
    template=re.sub('^IDENTITY = .*?^ROOT_MODULES',lambda m:'IDENTITY = '+repr(ident)+'\nROOT_MODULES',template,flags=re.M|re.S)
    template=re.sub(r'len\(manifest\) != \d+','len(manifest) != 138',template);template=re.sub(r'fixed \d+-file core','fixed 138-file core',template)
    check('entry_only_registered_template_substitutions',raw(release/'admin/target_runtime_entry.py')==template.encode())
    admin=raw(B/'installation/run_01/source_452b44d2/examples/agents/installed_release.py').decode();admin=re.sub('^_TARGET_ENTRY_SHA256 = .*$',lambda m:'_TARGET_ENTRY_SHA256 = '+repr(sha(template.encode())),admin,flags=re.M)
    check('admin_only_entry_digest_substitution',raw(release/'admin/installed_release.py')==admin.encode())
    runtime_binding=js(release/'admin/RUNTIME_BINDING.json')
    check('runtime_binding_source_files',runtime_binding['source_files']==source['source_files'] and runtime_binding['identity']==ident)
    check('runtime_binding_paths',pathlib.Path(runtime_binding['site_packages'])==installed and pathlib.Path(runtime_binding['target_release'])==release and runtime_binding['dependency_python']==ready['dependency_python'])
    identity=js(B/'installation/run_01/receipt/INSTALLED_IDENTITY_STDOUT.json')
    check('installed_identity_manifest',identity['runtime_identity']['source_files']==source['source_files'] and identity['runtime_identity']['source_sha256']==aggregate)
    for name,path in identity['module_origins'].items():
        check('installed_module_origin:'+name,pathlib.Path(path).is_relative_to(installed))
    fixed=js(B/'installation/run_01/FIXED_BUILD_INPUTS.json'); check('fixed_build_manifest',fixed['manifest']==source['source_files'])
    for prefix in ['01_GIT_TREE','02_IDENTITY_SOURCE','03_GIT_ARCHIVE','04_BUILD','05_INSTALL']:
        pr=js(B/f'installation/run_01/{prefix}.PROCESS.json')
        check('build_process:'+prefix,pr['returncode']==0 and pr['timed_out']==False and pr['started_ns']<pr['ended_ns'])
        check('build_stdout:'+prefix,sha(raw(B/f'installation/run_01/{prefix}.stdout.bin'))==pr['stdout_sha256'])
        check('build_stderr:'+prefix,sha(raw(B/f'installation/run_01/{prefix}.stderr.txt'))==pr['stderr_sha256'])
    protected=js(B/'installation/run_01/PROTECTED_BEFORE.json'); after=js(B/'installation/run_01/PROTECTED_AFTER.json'); check('protected_install_after_inventory',after['all_unchanged'] and after['unchanged']==dict.fromkeys(protected,True))
    for name,digest in protected.items(): check('protected_current:'+name,sha(raw(name))==digest)
    bindings=js(E/'INPUT_BINDINGS.json')
    candidate_time=git('show','-s','--format=%cI',PRODUCT).decode().strip(); prepared_time=bindings['prepared_utc']
    check('candidate_frozen_before_engineering_input',datetime.datetime.fromisoformat(candidate_time)<datetime.datetime.fromisoformat(prepared_time))
    facts['candidate_committed_at']=candidate_time; facts['input_prepared_at']=prepared_time
    for name,digest in bindings['files'].items(): check('actual_input_binding:'+name,sha(raw(name))==digest)
    check('actual_input_identity',bindings['ready']==ready and bindings['planned_business_rows']==5)
    result=js(E/'RESULTS.json'); proof=js(E/'RUNTIME_PROOF.json'); start=js(E/'product/START.json'); rpc=js(E/'product/RPC.json'); native=js(E/'native/SESSION.json'); native_ready=js(E/'native/READY.json')
    init=js(E/'INITIALIZE.json')['result']['_meta']['human_eye']; check('actual_initialize_source',init['source_sha256']==aggregate and init['source_file_count']==138 and init['distribution_version']==ready['version'])
    check('actual_command_entry',start['command'][3]==ready['entry'])
    check('actual_config_binding',js(E/'config.json')['expected_identity']=={'source_sha256':aggregate})
    check('actual_config_owned_port',js(E/'config.json')['blender']['port']==native['port']==native_ready['port'])
    chain=proof['parent_chain']; check('runtime_parent_chain',chain[0]['pid']==proof['runtime_pid'] and chain[0]['parent_pid']==proof['launcher_pid']==start['launcher_pid'] and chain[1]['pid']==proof['launcher_pid'])
    check('runtime_creation_time',chain[0]['created_filetime']==proof['runtime_created_filetime']>=proof['launcher_created_filetime']==chain[1]['created_filetime'])
    check('runtime_proof_recorded',proof['confirmed'] and proof['error'] is None and proof['parent_edges']==1)
    erratum=js(B/'audits/binding/RUNTIME_PROOF_ERRATUM.json')
    check('erratum_original_bound',erratum['original_sha256']==sha(raw(E/'RUNTIME_PROOF.json')) and proof['before_stdin'] is True and erratum['before_stdin_field_is_valid_evidence'] is False)
    rows=['base_default','base_brief','base_full','edit_default','edit_full']; expected_counts=[71,71,71,72,72]; kernels=[112,0,0,10,0]; seqs=[2,3,4,7,8]
    check('planned_rows_order',[x['label'] for x in js(E/'PLANNED_ROWS.json')]==rows)
    check('business_rows_complete',[x['state'] for x in result['business']]==rows and len(result['business'])==5)
    check('stdio_rpc_all_nine',len(rpc['requests'])==9 and [x['method'] for x in rpc['requests']]==['initialize','notifications/initialized','tools/list','ping']+['tools/call']*5)
    check('stdio_raw_directory_inventory',{p.name for p in (E/'product').iterdir() if p.is_dir()}=={f'{i:03}' for i in range(1,10)})
    check('business_no_retries',result['automatic_retries']==bindings['automatic_retries']==0)
    txsum=rxsum=0
    for i,item in enumerate(rpc['requests'],1):
        p=E/f'product/{i:03}'; tx=raw(p/'TX.bin'); rx=raw(p/'RX.bin') if (p/'RX.bin').exists() else b''
        check(f'stdio_receipt_{i}',js(p/'RECEIPT.json')==item)
        check(f'stdio_bytes_{i}',len(tx)==item['sent_bytes']==item['attempted_send_bytes'] and len(rx)==item['received_bytes'] and item['send_confirmed'] and item['error'] is None)
        check(f'stdio_request_{i}',json.loads(tx)['method']==item['method'] and json.loads(tx).get('id')==item['request_id'])
        if rx: check(f'stdio_response_id_{i}',json.loads(rx).get('id')==item['request_id'])
        txsum+=len(tx);rxsum+=len(rx)
    check('stdio_total',txsum==rpc['tx_bytes'] and rxsum==rpc['rx_bytes'] and not rpc['poisoned'])
    audit=[json.loads(x) for x in raw(E/'audit.jsonl').decode().splitlines()]
    check('audit_exact_events',[x['event'] for x in audit]==['request_trace']+['observe','request_trace']*5)
    for i,event in enumerate(audit):
        check(f'audit_source_{i}',event['pid']==proof['runtime_pid'] and event['runtime_identity']['build_id']=='sha256:'+aggregate and event['identity_check']['actual']['source_sha256']==aggregate)
    events=[json.loads(x) for x in raw(E/'native/WORKER_EVENTS.jsonl').decode().splitlines()]; wire=js(E/'native/WIRE/INDEX.json')
    check('host_raw_directory_inventory',{p.name for p in (E/'native/WIRE').iterdir() if p.is_dir()}=={f'{i:03}' for i in range(1,10)})
    check('worker_events_complete',events==result['all_worker_events'] and len(events)==len(wire)==9 and [x['sequence'] for x in events]==list(range(1,10)))
    all_requests={};all_responses={}
    for i,item in enumerate(wire,1):
        req=raw(E/f'native/WIRE/{i:03}/REQUEST.bin');resp=raw(E/f'native/WIRE/{i:03}/RESPONSE.bin');all_requests[i]=json.loads(req);all_responses[i]=json.loads(resp)
        check(f'host_wire_bytes_{i}',len(req)==item['request_bytes'] and len(resp)==item['response_attempted_bytes'] and item['request_response_attempted_bytes']==len(req)+len(resp) and item['response_sendall_completed'])
        if all_requests[i]['type']=='execute_code':
            code=all_requests[i]['params']['code']; check(f'host_script_{i}',raw(E/f'native/call_{i}/SCRIPT.py').replace(b'\r\n',b'\n').decode()==code and sha(code.encode())==events[i-1]['script_sha256'])
            stdout=raw(E/f'native/call_{i}/stdout.txt').replace(b'\r\n',b'\n');check(f'host_stdout_{i}',len(stdout)==events[i-1]['stdout_bytes'] and stdout.decode()==all_responses[i]['result']['result'])
        check(f'host_render_free_{i}',events[i-1].get('render_events_before',0)==events[i-1].get('render_events_after',0)==0 and events[i-1].get('changed_or_new_PNG_files',[])==[])
    check('host_method_inventory',[all_requests[i]['type'] for i in range(1,10)]==['execute_code']*4+['qa_advance','execute_code','execute_code','execute_code','close'])
    check('metadata_zero_host_proven',max(x['started_ns']+x['elapsed_ns'] for x in rpc['requests'][:4])<events[0]['started_ns'])
    last_meta=max(x['started_ns']+x['elapsed_ns'] for x in rpc['requests'][:4]); check('proof_actual_time_order',last_meta<proof['observed_ns']<=proof['proved_ns']<events[0]['started_ns']<rpc['requests'][4]['started_ns']<events[1]['started_ns'])
    facts['runtime_proof_scope']={'invalid_label':'before_stdin=true','last_metadata_end_ns':last_meta,'proof_observed_ns':proof['observed_ns'],'proof_completed_ns':proof['proved_ns'],'first_QA_geometry_ns':events[0]['started_ns'],'first_business_host_ns':events[1]['started_ns']}
    check('erratum_times_independently_reconstructed',erratum['actual_time_chain_ns']=={'first_metadata_rpc_started':rpc['requests'][0]['started_ns'],'last_metadata_rpc_ended':last_meta,'runtime_proof_observed':proof['observed_ns'],'runtime_proof_completed':proof['proved_ns'],'first_QA_geometry_request_started':events[0]['started_ns'],'first_business_rpc_started':rpc['requests'][4]['started_ns'],'first_business_host_capture_started':events[1]['started_ns']})
    bodies=[]; factrows=[]
    for n,label in enumerate(rows):
        row=result['business'][n]; p=E/f'product/{n+5:03}'; response=json.loads(raw(p/'RX.bin')); request=json.loads(raw(p/'TX.bin')); receipt=js(E/f'{label}_RESPONSE_RECEIPT.json'); body=json.loads(response['result']['content'][0]['text'])
        check(label+':request_binding',request==js(E/f'{label}_REQUEST.json')==row['request']==receipt['request'])
        check(label+':response_binding',response==row['response']==receipt['response'] and body==row['body']==receipt['body'])
        check(label+':text_length',len(response['result']['content'][0]['text'].encode())==row['business_text_utf8_bytes']==receipt['business_text_utf8_bytes'])
        check(label+':audit_binding',row['audit']==audit[1+2*n:3+2*n] and row['diagnostics']==row['audit'][0]['task_work'])
        check(label+':trace_binding',row['trace']==row['audit'][1]['trace'] and body['trace_id']==row['audit'][0]['trace_id']==row['audit'][1]['trace_id'])
        check(label+':source_binding',body['binding']['runtime_source_sha256']==aggregate and body['binding']['host_source_sha256']==next(x['sha256'] for x in source['source_files'] if x['path']=='human_eye_plugin/blender_host.py'))
        seq=seqs[n]; event=events[seq-1]; check(label+':one_host_rpc',row['actual_host_RPC']==1 and row['wire']==[wire[seq-1]] and row['work_events']==[event])
        check(label+':host_time_contained',row['started_ns']<=event['started_ns']<=event['started_ns']+event['elapsed_ns']<=row['ended_ns'])
        hostbody=json.loads(all_responses[seq]['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1]); check(label+':acquisition_work',row['diagnostics']['acquisition_work']==hostbody['result']['capture']['work'])
        check(label+':kernel_count',row['diagnostics']['kernel_calls']==kernels[n])
        check(label+':complete_matching_count',body['coverage']['measured_match']==len(body['matches'])==expected_counts[n] and body['coverage']['total_pairs']==276)
        check(label+':host_bytes',row['bridge_request_bytes']==wire[seq-1]['request_bytes'] and row['bridge_response_bytes']==wire[seq-1]['response_attempted_bytes'])
        check(label+':no_errors',response['result']['isError']==False and row['errors']==[] and event['status']=='completed' and event['script_error'] is None)
        bodies.append(body); factrows.append({'id':label,'body_bytes':row['business_text_utf8_bytes'],'host_sequence':seq,'kernel_calls':kernels[n]})
    check('same_state_binding_base',bodies[0]['binding']==bodies[1]['binding']==bodies[2]['binding'])
    check('same_state_binding_edit',bodies[3]['binding']==bodies[4]['binding'] and bodies[0]['binding']!=bodies[3]['binding'])
    check('first_measurement_cache_empty',all(result['business'][0]['diagnostics']['measurement_cache_before'][k]==0 for k in ['accounted_bytes','content_blobs','frames','measurement_entries','measurement_computations']))
    check('first_resident_cache_empty',events[1]['m2_work']['before']==[] and events[0]['m2_work']['before']==events[0]['m2_work']['after']==[])
    facts['business_rows']=factrows;facts['business_host_bytes']={'request':sum(wire[s-1]['request_bytes'] for s in seqs),'response':sum(wire[s-1]['response_attempted_bytes'] for s in seqs)}
    check('outside_rpc_exact',result['outside_business_RPC']==[wire[i-1] for i in [1,5,6,9]])
    # Inspect compressed payload as data; never eval or import the host script.
    embedded=[]
    for node in ast.walk(ast.parse(all_requests[2]['params']['code'])):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>1000:
            try: decoded=zlib.decompress(base64.b64decode(node.value,validate=True))
            except Exception: continue
            matches=[s['path'] for s in source['source_files'] if s['sha256']==sha(decoded)]
            check('embedded_host_source:'+sha(decoded),len(matches)==1);embedded.extend(matches)
    check('embedded_host_sources_nonempty',len(embedded)==6 and 'human_eye_plugin/blender_host.py' in embedded)
    facts['actual_embedded_sources']=embedded
    check('original_asset_copy_equal',raw(native['asset'])==raw(native['asset_copy']) and sha(raw(native['asset']))==native['asset_sha256'])
    check('native_blender_binary',sha(raw(native['blender']))==native['blender_sha256'])
    check('pose_patch_bytes',sha(raw(native['qa_pose_patch']['path']))==native['qa_pose_patch']['sha256'])
    check('pose_rpc_patch_binding',all_requests[5]['params']['patch_sha256']==native['qa_pose_patch']['sha256'] and js(E/'POSE_ADVANCE.json')['response']==all_responses[5])
    for state in ['base','edit']:
        actual=js(E/f'{state}_ACTUAL_SNAPSHOT.json'); expected_path=next(pathlib.Path(p) for p,h in bindings['files'].items() if h==bindings['qualification'][state+'_snapshot_sha256']); expected=js(expected_path)
        normalize=lambda x:{k:v for k,v in x.items() if k not in ['blend_filepath','pid']}
        check(state+':complete_snapshot_matches_frozen',normalize(actual)==normalize(expected))
        check(state+':snapshot_owned',actual['pid']==native['pid'] and pathlib.Path(actual['blend_filepath'])==pathlib.Path(native['asset_copy']))
    close=js(E/'product/CLOSE.json'); worker=js(E/'native/WORKER_CLOSED.json'); timing=js(E/'FINAL_TIMING.json');runtime_exit=result['runtime_exit'];nclose=result['native_close']
    check('launcher_close_bound',close==result['product_close'] and close['launcher_pid']==start['launcher_pid'] and close['process_reaped'] and close['exit_code']==0 and close['reader_stopped'] and close['error'] is None)
    check('runtime_exit_separate',runtime_exit['confirmed'] and runtime_exit['exited'] and runtime_exit['exit_code']==0 and runtime_exit['handle_closed'])
    check('native_close_bound',nclose['response']==all_responses[9] and nclose['pid']==worker['pid']==native['pid'] and nclose['process_reaped'] and nclose['exit_code']==0 and nclose['error'] is None)
    check('native_final_geometry',worker==result['worker_closed'] and worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and worker['qa_patch_applied'] and not worker['poisoned'])
    check('closure_timeline',result['business'][-1]['ended_ns']<close['ended_ns']<=runtime_exit['observed_ns']<worker['closed_ns']<=result['business_and_owned_cleanup_end_ns']<=timing['business_receipts_closed_ns']<timing['original_deadline_ns'])
    check('original_deadline_unchanged',timing['original_deadline_ns']==result['deadline_ns']==worker['original_deadline_ns']==native['deadline_ns']==nclose['original_deadline_ns'])
    check('full_wall_recalculated',timing['full_session_wall_ns']==timing['business_receipts_closed_ns']-timing['started_ns'] and timing['accepted_success'] and timing['complete_business_write_close_within_original_deadline'])
    facts['close_worker_event_status']=events[-1]['status'];facts['runtime_pids']={'launcher':proof['launcher_pid'],'runtime':proof['runtime_pid'],'Blender':native['pid']};facts['full_engineering_wall_ns']=timing['full_session_wall_ns']
    check('no_author_tree_mutation_during_review',git('status','--porcelain=v1').decode()==facts['git_status_before'] and git('rev-parse','HEAD').decode().strip()==facts['head'])

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    try:main()
    except Exception as error:
        checks.append({'check':'review_script_exception','passed':False,'detail':traceback.format_exc()})
    payload={'all_passed':all(x['passed'] for x in checks),'check_count':len(checks),'failed':[x for x in checks if not x['passed']],'input_count':len(inputs),'facts':facts,'experiment_denominator':{'new_runs':0,'existing_engineering_business_observations':5,'existing_host_RPC':9},'checks_are_not_experiments':True}
    for name,data in [('RESULTS.json',payload),('CHECKS.json',checks),('INPUTS.json',inputs)]: (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))
