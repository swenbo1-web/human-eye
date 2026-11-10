import base64, csv, hashlib, io, json, subprocess, sys, traceback, zipfile
from collections import Counter
from pathlib import Path

WT=Path(r'C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe')
REL='verification/m1_task_entry_001_eval';R=WT/REL
OUT=Path(r'D:\hefe\verification\fixes\20261111_m1_eval_ready_review')
COMMIT='82e976cd425fae9703399148a8938bd6099d486f';PARENT='7411ac7aa9338f17355ffe5cdf4df113ce862aed'
CANON='0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
ATTEMPT=OUT/('SOURCE_ENTRY_REVIEW_ATTEMPT_%02d.json'%(len(list(OUT.glob('SOURCE_ENTRY_REVIEW_ATTEMPT_*.json')))+1))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def exception_record(t,v,b):
    save(ATTEMPT,{'status':'reviewer_checker_exception','traceback':''.join(traceback.format_exception(t,v,b)),'product_executed':False})
    sys.__excepthook__(t,v,b)
sys.excepthook=exception_record
sha=lambda b:hashlib.sha256(b).hexdigest()
H=lambda p:sha(Path(p).read_bytes())
J=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
L=lambda p:J(R/p)
G=lambda *a:subprocess.check_output(['git','-C',str(WT),*a])
errors=[];checks=Counter();counts=Counter()
def check(ok,name,path=None):
    checks[name]+=1
    if not ok:errors.append({'check':name,'path':str(path) if path else None})
def git_blobs(commit,paths):
    result=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    s=io.BytesIO(result.stdout);values={}
    for p in paths:
        h=s.readline().split()
        if len(h)!=3 or h[1]!=b'blob':raise ValueError('missing Git blob '+p)
        values[p]=s.read(int(h[2]));assert s.read(1)==b'\n'
    return values
def lines(p):return [json.loads(line) for line in Path(p).read_bytes().splitlines() if line.strip()]
def normalized_mesh(x):
    return {'unit_scale_m':x['unit_scale_m'],'objects':sorted([{'name':o['name'],'vertices_local':o['vertices_local'],'matrix_world':o['matrix_world'],'faces':o.get('faces',o.get('triangles'))} for o in x['objects']],key=lambda o:o['name'])}

index,freeze,plan=L('ARTIFACT_INDEX.json'),L('FREEZE.json'),L('PLAN.json')
pins={'PLAN.json':'80670321c062ff2dca5127f8e54fa9713a4a259608418394145aa911c5b2300b','ARTIFACT_INDEX.json':'8144b00d7296766bbc2a887c3970755fecc9b87631269920d856ddeebcf77dc1','FREEZE.json':'8f4abae37eae380568728a9e5c7063107c14dc5b3536cda0fad13514fa77de20'}
for p,h in pins.items():check(H(R/p)==h,'requested_freeze_pin',p)
head=G('rev-parse','HEAD').decode().strip();status=G('status','--porcelain').decode()
check(head==COMMIT and not status,'clean_fixed_commit')
check(G('rev-parse',COMMIT+'^').decode().strip()==PARENT==freeze['parent_commit'],'fixed_parent')
members=[x['path'] for x in index['files']]+[REL+'/ARTIFACT_INDEX.json',REL+'/FREEZE.json'];git_members=git_blobs(COMMIT,members);total=0
for row in index['files']:
    raw=(WT/row['path']).read_bytes();total+=len(raw)
    check(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'artifact_hash_and_length',row['path'])
for p,raw in git_members.items():check((WT/p).read_bytes()==raw,'artifact_Git_blob',p)
tracked=set(G('ls-tree','-r','--name-only',COMMIT,'--',REL).decode().splitlines())
check(tracked==set(members) and len(tracked)==958,'all_956_plus_2_tracked_members')
check(len(index['files'])==index['file_count']==freeze['artifact_count']==956 and total==index['bytes']==5302637,'artifact_count_bytes')
for row in index['local_duplicates_not_added_to_Git']:
    p=R/row['path'];check(p.stat().st_size==row['bytes'] and H(p)==row['sha256'],'local_duplicate_hash',row['path'])
check(freeze['artifact_index_sha256']==H(R/'ARTIFACT_INDEX.json') and freeze['plan_sha256']==H(R/'PLAN.json') and freeze['report_sha256']==H(R/'REPORT.md'),'freeze_internal_pins')

source=L('SOURCE_REVIEW.json');manifest=source['files'];paths=[x['path'] for x in manifest]
candidate,parent=git_blobs(COMMIT,paths),git_blobs(PARENT,paths)
check(len(paths)==len(set(paths))==source['source_count']==freeze['source_count']==137,'source_137')
for row in manifest:
    p=row['path'];check(candidate[p]==parent[p]==(WT/p).read_bytes() and sha(candidate[p])==row['sha256'],'product_unchanged_from_7411',p)
ready=L('installation/READY.json');install=L('installation/receipt/ISOLATED_INSTALL.json');entry=Path(ready['entry']);binding=J(entry.with_name('RUNTIME_BINDING.json'));site=Path(ready['install_root']);snapshot=R/'installation/source_7411'
canonical=sha(json.dumps({'base_version':binding['identity']['base_version'],'implementation_revision':binding['identity']['implementation_revision'],'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
check(canonical==CANON==ready['source_sha256']==install['source_sha256']==freeze['canonical']==plan['candidate_source_sha256']==source['canonical'],'shared_canonical_identity')
check(binding['source_files']==manifest and len(binding['source_files'])==137,'installed_binding_manifest')
check(H(entry)==ready['launcher_sha256']==install['launcher_sha256']==binding['launcher_sha256'] and H(entry.with_name('RUNTIME_BINDING.json'))==ready['binding_sha256']==install['binding_sha256'] and H(entry.with_name('installed_release.py'))==binding['admin_sha256']==install['admin_sha256'],'installed_controlled_entry_pins')
wheel=next((R/'installation/bundle').glob('*.whl'));check(H(wheel)==ready['wheel_sha256']==install['wheel_sha256'],'wheel_pin')
with zipfile.ZipFile(wheel) as z:
    for p in paths:check(z.read(p)==candidate[p]==(snapshot/p).read_bytes()==(site/p).read_bytes(),'source_Git_wheel_snapshot_install_equal',p)
    record=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'));record_rows=list(csv.reader(z.read(record).decode().splitlines()));hashed=0
    for p,h,s in record_rows:
        if not h:continue
        alg,digest=h.split('=',1);raw=z.read(p);hashed+=1
        check(base64.urlsafe_b64encode(hashlib.new(alg,raw).digest()).rstrip(b'=').decode()==digest and (not s or len(raw)==int(s)),'wheel_RECORD_member_hash',p)
installed_id=L('installation/receipt/INSTALLED_IDENTITY_STDOUT.json')
check(installed_id['runtime_identity']['source_sha256']==CANON and installed_id['runtime_identity']['source_kind']=='installed_distribution' and installed_id['launcher']['source_file_count']==137 and len(installed_id['runtime_identity']['source_files'])==137 and installed_id['runtime_identity']['source_files']==manifest,'recorded_isolated_installed_identity')
deps=L('installation/DEPENDENCIES.stdout.json');python=ready['dependency_python']
check(deps['python']==python==binding['dependency_python']==install['dependency_python'] and Path(python).is_file(),'same_bound_dependency_interpreter')
for name in ['numpy','pillow']:check(H(deps[name+'_file'])==deps[name+'_init_sha256'],'dependency_recorded_init_hash',name)
catalogues={g:L('catalogues/'+g+'/PUBLIC_TOOLS.json') for g in ['C','S']}
for g in ['C','S']:
    rec=L('catalogues/'+g+'/RESULTS.json');check(rec['source_identity']['source_sha256']==CANON and rec['exit_code']==0 and rec['no_host_request'],'catalogue_source_and_no_host_record',g)
    check(H(R/'catalogues'/g/'TX.bin')==rec['TX_sha256'] and H(R/'catalogues'/g/'RX.bin')==rec['RX_sha256'],'catalogue_wire_pins',g)

# Freeze exactly 27 slots and every task's byte input; scheduling/scoring logic is reviewed separately.
contract=L('EVAL_CONTRACT.json');tasks=L('TASKS.json');rules=(R/'SESSION_RULES.txt').read_bytes()
check(plan['sequence']==contract['sequence'] and len(plan['sequence'])==27 and len({x['cell'] for x in plan['sequence']})==27,'same_frozen_27_slot_order')
check(Counter((x['task'],x['group'],x['round']) for x in plan['sequence'])==Counter({(t,g,n):1 for t in ['T1','T2','T3'] for g in ['N','C','S'] for n in [1,2,3]}),'balanced_27_denominator')
check(sha(rules)==plan['shared_session_rules']['sha256'] and rules==Path(plan['shared_session_rules']['identical_to']).read_bytes(),'shared_rules_exact_bytes')
task_input_rows=[]
for key,task in tasks.items():
    meta=plan['tasks'][key];check(all(meta[k]==v for k,v in task.items()),'plan_task_metadata_binding',key)
    for kind in ['asset','snapshot','truth','prompt']:check(H(R/task[kind])==task[kind+'_sha256'],'task_asset_truth_prompt_pin',key+'/'+kind)
    combined=rules+b'\n'+(R/task['prompt']).read_bytes();check(sha(combined)==meta['model_input_sha256'] and len(combined)==meta['model_input_bytes'],'full_model_input_hash',key)
    task_input_rows.append({'task':key,'model_input_sha256':sha(combined),'model_input_bytes':len(combined),'all_9_slots_same_task_input':sum(x['task']==key for x in plan['sequence'])==9})
for p,h in plan['dispatch_input_sha256'].items():check(H(R/p)==h,'dispatch_input_pin',p)
for field,p in [('actor_sha256','actor.py'),('consumer_transport_sha256','consumer_transport.py'),('preflight_driver_sha256','driver.py'),('scoring_contract_sha256','SCORING_CONTRACT.json'),('arithmetic_guard_sha256','ARITHMETIC_GUARD.json'),('preflight_record_sha256','preflight_02/RESULTS.json')]:check(plan[field]==H(R/p),'plan_runner_and_record_pin',p)
check(not(R/'GO.json').exists() and not(R/'STARTED.json').exists() and not(R/'cells').exists() and plan['actual_models_started']==0,'preparation_has_no_formal_consumers')

preflight=L('preflight_02/RESULTS.json');check(preflight['passed'] and len(preflight['cases'])==9 and preflight['model_calls']==0,'stored_nine_case_summary')
native_definitions=[];common_native_pins=set();case_rows=[];sample_pids=set();native_valid_codes=[]
for task_id in ['T1','T2','T3']:
  for group in ['N','C','S']:
    label=task_id+'_'+group;folder=R/'preflight_02'/label;owner=folder/'owner';task=tasks[task_id]
    config=J(folder/'ACTOR_CONFIG.json');launch=J(folder/'ACTOR_LAUNCH.json');identity=J(owner/'IDENTITY.json');result=J(folder/'PREFLIGHT_RESULT.json');finish=J(folder/'OWNER_FINISH.json');close=J(owner/'CLOSE.json')
    check(result in preflight['cases'] and result['passed'] and result['errors']==[] and result['models']==0,'case_summary_binding',label)
    check(config['dependency_python']==identity['python']==python and config['asset_sha256']==identity['asset_sha256']==task['asset_sha256'],'same_dependency_and_task_asset',label)
    check(config['group']==identity['group']==group and identity['private_geometry_warmup'] is False,'group_and_no_private_warm_record',label)
    check(identity['actor_parent_pid']==launch['pid'] and identity['actor_pid']==close['actor_pid'],'actor_launcher_runtime_record',label)
    common_native_pins.add(identity['common_native_sha256']);sample_pids.update([launch['pid'],identity['actor_pid']])
    probe=J(folder/'thin_probe/RESULT.json');requests=J(folder/'thin_probe/REQUESTS.json');tx=lines(folder/'thin_probe/TX.bin');rx=lines(folder/'thin_probe/RX.bin')
    check(tx==requests and rx==probe['responses'] and len((folder/'thin_probe/TX.bin').read_bytes())==probe['sent_bytes'] and len((folder/'thin_probe/RX.bin').read_bytes())==probe['received_bytes'],'original_stdio_request_response_bytes',label)
    wanted_ids=[x['id'] for x in requests if 'id' in x];check([x['id'] for x in rx]==wanted_ids and probe['reply_ids_match'],'stdio_response_id_binding',label)
    listed=next(y['result']['tools'] for x,y in zip([x for x in requests if 'id' in x],rx) if x['method']=='tools/list')
    native=[x for x in listed if x['name']=='execute_blender_code'];check(len(native)==1,'one_native_tool',label);native_definitions+=native
    expected_tools=native+(catalogues[group] if group!='N' else []);check(listed==expected_tools and [x['name'] for x in listed]==identity['exposed_tool_names'],'actual_exposed_directory_profile',label)
    tool_requests=[x for x in requests if x['method']=='tools/call'];tool_dirs=sorted(owner.glob('tool_*'));tools=J(owner/'TOOLS.json')
    check(len(tool_dirs)==len(tool_requests)==tools['attempts']==close['tool_attempts'] and tools['tools']==close['tools'],'all_public_tool_attempts_accounted',label)
    response_by_id={x['id']:x for x in rx}
    for i,(directory,request) in enumerate(zip(tool_dirs,tool_requests)):
        check(J(directory/'REQUEST.json')==request,'public_request_owner_exact',label+'/'+directory.name)
        responsefiles=[p for p in [directory/'RESPONSE.json',directory/'ERROR_RESPONSE.json'] if p.exists()];check(len(responsefiles)==1,'one_owner_response',label+'/'+directory.name)
        if len(responsefiles)==1:check(J(responsefiles[0])==response_by_id[request['id']],'owner_response_public_stdio_exact',label+'/'+directory.name)
        check(J(directory/'ATTEMPT.json')==tools['tools'][i],'attempt_owner_log_binding',label+'/'+directory.name)
        counts['public_tool_attempts']+=1
    check(tool_requests[0]['params']['arguments'] is None and response_by_id[tool_requests[0]['id']]['result']['isError'] is True and response_by_id[tool_requests[1]['id']]['result']['isError'] is False,'null_rejection_then_native_recovery',label)
    native_valid_codes.append(tool_requests[1]['params']['arguments']['code'])
    initialmesh=J(owner/'INITIAL.json');finalmesh=J(owner/'FINAL.json');expectedmesh=J(R/task['snapshot'])
    check(initialmesh==finalmesh and normalized_mesh(initialmesh)==normalized_mesh(expectedmesh),'initial_final_frozen_full_geometry',label)
    for name,mesh in [('INITIAL',initialmesh),('FINAL',finalmesh)]:
        receipt=J(owner/(name+'.json.receipt.json'));resp=receipt['response'];check(resp['status']=='success' and resp['result']['executed'] is True and json.loads(resp['result']['result'])==mesh and receipt['source_file_unchanged'] and receipt['protected_files_unchanged'],'snapshot_receipt_binding',label+'/'+name)
    nc=J(owner/'native/CONFIG.json');worker=J(owner/'native/WORKER_CLOSED.json');nativeclose=close['native_close']
    check(H(nc['asset'])==H(nc['asset_copy'])==task['asset_sha256'] and nc['max_calls']==plan['physical_RPC_limit'] and nc['blender_sha256']==freeze['Blender_binary_sha256'],'native_same_asset_binary_capacity',label)
    check(nativeclose['process_reaped'] and nativeclose['exit_code']==0 and nativeclose['error'] is None and nativeclose['source_file_unchanged'] and nativeclose['protected_files_unchanged'] and close['worker_closed']==worker and worker['initial_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not worker['poisoned'],'native_backend_close_and_geometry',label)
    check(finish['close']==close==result['finish']['close'] and finish==result['finish'] and finish['confirmed'] and close['confirmed'] and finish['exit_code']==0 and close['errors']==[],'owner_finish_binding',label)
    sample_pids.add(nativeclose['pid'])
    if group=='N':
        check(identity['runtime_identity'] is None and identity['product_serve_entry'] is None and close['plugin_close'] is None and not(owner/'plugin').exists(),'N_no_plugin_process_or_identity',label)
    else:
        start=J(owner/'plugin/START.json');pc=J(owner/'plugin/CLOSE.json');init=J(owner/'PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye'];rpc=J(owner/'plugin/RPC.json');pconfig=J(owner/'product_config.json')
        command=[python,'-I','-B',ready['entry'],'serve','--config',str(owner/'product_config.json')]+(['--spatial-task-only'] if group=='S' else [])
        check(start['command']==command and identity['product_serve_entry']==ready['entry'] and identity['product_spatial_task_only']==(group=='S'),'actual_C_S_serve_single_profile_variable',label)
        check(init==identity['runtime_identity'] and init['source_sha256']==CANON and init['source_file_count']==137 and init['source_kind']=='installed_distribution','actual_C_S_loaded_identity',label)
        check([x['method'] for x in rpc['requests']]==['initialize','notifications/initialized','tools/list','ping','tools/call'] and not rpc['poisoned'] and J(owner/'PLUGIN_PING.json')['result']=={},'same_metadata_only_private_startup_no_geometry_warm',label)
        check(config['read_schemas']==catalogues[group] and pconfig['project_root']==ready['install_root'] and pconfig['expected_identity']['source_sha256']==CANON and pconfig['request_budget_s']==plan['tool_timeout_s'] and pconfig['observe_on_prompt'] is False,'same_installed_source_and_request_budget',label)
        check(pc==close['plugin_close'] and pc['confirmed'] and pc['process_reaped'] and pc['reader_stopped'] and pc['exit_code']==0 and pc['error'] is None,'plugin_normal_close_record',label)
        sample_pids.add(start['launcher_pid']);counts['plugin_samples']+=1
    proof=J(folder/'thin_probe/RUNTIME_PROVENANCE.json');chain=proof['parent_chain'];bridges=list((folder/'thin_probe/attachments').glob('bridge_*'));check(len(bridges)==1,'one_actual_thin_instance',label)
    started=J(bridges[0]/'STARTED.json');ended=J(bridges[0]/'EXIT.json');exit_proof=probe['runtime_exit']
    check(probe['runtime_provenance']==proof and proof['confirmed'] and proof['error'] is None and proof['before_stdin'] and proof['proved_ns']<=probe['stdin_send_started_ns'],'ownership_proved_before_first_stdin',label)
    check(chain[0]['pid']==started['pid']==probe['runtime_pid']==proof['runtime_pid'] and chain[-1]['pid']==probe['launcher_pid']==proof['launcher_pid'] and proof['parent_edges']==len(chain)-1<=4 and chain[0]['created_filetime']==proof['runtime_created_filetime'] and chain[-1]['created_filetime']==proof['launcher_created_filetime'],'runtime_launcher_PID_creation_binding',label)
    check(all(child['parent_pid']==parent['pid'] and parent['created_filetime']<=child['created_filetime'] for child,parent in zip(chain,chain[1:])),'actual_parent_chain_birth_order',label)
    check(started==probe['startup_receipt'] and all(ended[k]==started[k] for k in ['pid','kind','started_ns','instance_nonce']) and ended['normal_exit'] and ended['backend_close_requested'] is False and ended['requests']==len(requests) and ended['complete_tx_bytes']==probe['sent_bytes'] and ended['complete_rx_bytes']==probe['received_bytes'],'thin_STARTED_EXIT_and_wire_binding',label)
    check(exit_proof['confirmed'] is True and exit_proof['exited'] is True and exit_proof['exit_code']==0 and exit_proof['handle_closed'] and probe['launcher_reaped'] and probe['launcher_exit_code']==0 and probe['confirmed'] and probe['error'] is None and probe['within_original_deadline'],'retained_runtime_handle_and_launcher_exit',label)
    sample_pids.update([probe['launcher_pid'],probe['runtime_pid']]);counts['thin_exit_receipts']+=1
    case_rows.append({'case':label,'passed_source_and_stdio_binding':True,'private_geometry_warmup':False,'plugin_loaded':group!='N','initial_final_asset_bound':True,'thin_direct_EOF_receipt_bound':True,'formal_consumer_termination_verified':False})
check(all(x==native_definitions[0] for x in native_definitions) and len(native_definitions)==9 and len(common_native_pins)==1,'all_nine_shared_native_capabilities_identical')
check(len(set(native_valid_codes))==1,'same_native_preflight_read_code_all_arms')
check(counts['plugin_samples']==6 and counts['thin_exit_receipts']==9,'preflight_identity_exit_denominators')

# Preserve the failed first probe and distinguish the later local PID proof from future CLI termination.
old=L('preflight_T2_T3_01/T2_N/thin_probe/RESULT.json');old_bridge=old['client_exit_receipts'][0]
check(old['confirmed'] is False and old['client_exit_confirmed'] is False and old['thin_pid']!=old_bridge['started']['pid'] and old_bridge['started']['pid']==old_bridge['exit']['pid'] and old_bridge['exit']['normal_exit'],'initial_PID_mismatch_failure_preserved')
finalbind=L('RUNNER_FINAL_BINDING.json')
check(H(R/'preflight_client.py')==finalbind['preflight_helper_sha256'] and H(R/'actor.py')==finalbind['actor_sha256']==plan['actor_sha256'] and H(R/'consumer_transport.py')==finalbind['transport_sha256']==plan['consumer_transport_sha256'],'PID_fix_and_unchanged_dispatch_code_pins')
pidindex=L('OWNED_PID_INDEX.json');cleanup=L('CLEANUP.json');indexed=set(pidindex['pids']);cleanupids={x['pid'] for x in cleanup['rows']}
check(len(indexed)==len(pidindex['rows'])==69 and indexed=={x['pid'] for x in pidindex['rows']}==cleanupids and sample_pids<=indexed,'explicit_69_PID_index_and_preflight_coverage')
check(cleanup['all_indexed_absent'] and all(x['present'] is False for x in cleanup['rows']),'recorded_69_PID_absence')
special=[x for x in pidindex['rows'] if x['role']=='thin_runtime_from_matching_START_EXIT_only']
check(len(special)==1 and special[0]['pid']==old_bridge['started']['pid'] and special[0]['scope']=='observed; parent ancestry was not measured in first failed helper','unproven_first_runtime_label_not_upgraded')
def pid_values(x):
    values=set()
    if isinstance(x,dict):
        for k,v in x.items():
            if isinstance(v,int) and (k=='pid' or k.endswith('_pid')):values.add(v)
            values.update(pid_values(v))
    elif isinstance(x,list):
        for v in x:values.update(pid_values(v))
    return values
for row in pidindex['rows']:
    p=R/row['evidence'];check(p.is_file() and row['pid'] in pid_values(J(p)),'PID_index_has_actual_source_record',row['evidence'])
report={'schema_version':1,'status':'passed' if not errors else 'requires_review','candidate_commit':COMMIT,'parent_product_commit':PARENT,'worktree_HEAD':head,'worktree_clean':not status,'requested_pins':pins,'scope':'Independent read-only archive/Git/source/wheel/install/actual recorded entry identity, variables, input and local-preflight evidence binding. Driver dispatch, semantic grading and cost logic are reviewed separately by root. No product, model, Blender or process scan executed.','artifacts':{'members':956,'bytes':total,'Git_members_including_index_freeze':len(tracked),'local_duplicate_hashes':len(index['local_duplicates_not_added_to_Git'])},'source_installation':{'sources':137,'canonical':canonical,'all_product_sources_same_as_7411':True,'Git_snapshot_wheel_install_bytes_compared':137,'wheel_sha256':H(wheel),'wheel_RECORD_hashed_members':hashed,'entry_sha256':H(entry),'binding_sha256':H(entry.with_name('RUNTIME_BINDING.json')),'dependency_interpreter':python,'same_C_S_interpreter_and_installation':True,'dependency_scope':'Same bound interpreter and recorded numpy/Pillow init hashes checked; no full historical transitive dependency replay.'},'frozen_inputs':{'slots':27,'tasks':task_input_rows,'common_session_rules_sha256':sha(rules),'balanced_tasks_arms_rounds':True,'formal_consumers_started':0},'preflight':{'cases':case_rows,'counts':dict(counts),'native_tool_definition_same_all_arms':True,'N_has_no_plugin_start':True,'C_S_differ_only_in_serve_profile_and_tool_presentation_in_checked_entry_setup':True,'private_product_startup':['initialize','notifications/initialized','tools/list','ping'],'private_geometry_warmup':False,'geometry_scope':'Full local vertices/world matrices/faces and unit scale match frozen snapshots; source assets and copies unchanged. No independent geometry oracle recalculation here.'},'PID_revision':{'initial_failure_retained':True,'initial_runtime_observed_only_not_relabelled_owned':True,'new_runtime_proof':'Recorded actual parent chain, creation times, before-stdin binding, retained runtime-handle exit, launcher reap and matching STARTED/EXIT/wire receipts all independently cross-checked. Unknown ownership fails the local probe before stdin; it is not silently accepted.','local_direct_EOF_receipts':9,'indexed_cleanup_records':69,'fresh_process_scan':False,'formal_CLI_thin_EXIT':'unmeasured; local direct EOF is not substituted for formal consumer or historical005 termination'},'checks_performed':dict(checks),'errors':errors,'attempt_record':str(ATTEMPT),'limits':['Archived execution-record verification, not independently rerun product/Blender','Formal 27 consumers have not run','Full transitive dependency history not replayed','Driver/consumer implementation, scoring and full-cost methodology delegated to root review','No claim every frozen source module executed merely because its hash matched'],'product_calls':0,'Blender_calls':0,'model_calls':0,'process_scans':0,'worktree_or_product_writes':0}
save(ATTEMPT,report);save(OUT/'SOURCE_ENTRY_REVIEW.json',report)
print(json.dumps({'status':report['status'],'artifacts':956,'bytes':total,'Git_members':len(tracked),'sources':137,'preflight_cases':len(case_rows),'counts':dict(counts),'errors':errors,'attempt':str(ATTEMPT),'report':str(OUT/'SOURCE_ENTRY_REVIEW.json')},ensure_ascii=False))
