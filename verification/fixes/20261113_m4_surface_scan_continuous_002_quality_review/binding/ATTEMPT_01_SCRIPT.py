"""Independent 002 anonymous/source/continuity review, offline, no scoring.
Reuse only our earlier pure projection readers, never an author checker.
"""
import copy,hashlib,importlib.util,io,json,pathlib,re,subprocess,traceback,zipfile
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe');B=R/'verification/m4_surface_scan_continuous_consumption_002'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review/binding')
D='a798caf982e2d7eefe0bf52b739b9bef88526be4';P='11ae08e791c300c58ae935f4f632a22b3d7f3342';P0='012daa93cd2b67164ac2dc4ed04089d395ef2ed1';OLD='b51dc02eb4f25966f983033b42dad3c9cfec9393'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def enc(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ck(n,v):checks.append({'check':n,'passed':bool(v)})
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(c):
 d={}
 for x in git('ls-tree','-rz',c).split(b'\0'):
  if x:m,n=x.split(b'\t',1);d[n.decode()]=m.split()[2].decode()
 return d
def norm(d):return {'unit_scale_m':d['unit_scale_m'],'objects':sorted([{k:o[k] for k in ['name','vertices_local','matrix_world','faces']} for o in d['objects']],key=lambda o:o['name'])}
def main():
 helper=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_quality_review/binding/check_binding.py');raw(helper)
 spec=importlib.util.spec_from_file_location('_own_previous_projection_only',helper);own=importlib.util.module_from_spec(spec);spec.loader.exec_module(own)
 projection,project_error=own.projection,own.project_error
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();ck('fixed clean delivery',head==D and status=='');dt,pt=tree(D),tree(P);rel=B.relative_to(R).as_posix()
 manifest=j(B/'DELIVERY_MANIFEST.json');prep=j(B/'PREPARATION.json');run=j(B/'RUN_RESULT.json');plan=j(B/'PLAN.json');mapping=j(B/'private/ANON_MAP.json');start=j(B/'FORMAL_STARTED.json');receipt=j(B/'quality/PACKAGE_RECEIPT.json');binding=j(B/'quality/private/BINDING.json');public=B/'quality/public';index=j(public/'INDEX.json')
 ck('310 content plus manifest exact tracked set',len(manifest['files'])==310 and {x['path'] for x in manifest['files']}|{'DELIVERY_MANIFEST.json'}=={p[len(rel)+1:] for p in dt if p.startswith(rel+'/')})
 bad=[]
 for x in manifest['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=dt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('all delivery byte hash Git',not bad);ck('manifest Git',blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 bad=[]
 for x in prep['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=pt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('172 preparation members fixed',len(prep['files'])==172 and not bad and blob(raw(B/'PREPARATION.json'))==pt[rel+'/PREPARATION.json'])
 ck('425 reused dependencies unchanged',len(prep['external_sha256'])==425 and all(sha(raw(path))==h for path,h in prep['external_sha256'].items()))
 ck('final preparation/root contract identity',manifest['preparation_commit']==P and manifest['preparation_sha256']==sha(raw(B/'PREPARATION.json')) and prep['admin_commit']=='79ed3bff7c87d4ac68e2b2bf382de05d41b731c6' and sha(raw(B/'inputs/ROOT_PLAN.md'))==prep['root_plan_sha256'])
 driver=raw(B/'runtime/driver.py');old_driver=git('cat-file','blob',P0+':'+rel+'/runtime/driver.py');p0prep=json.loads(git('cat-file','blob',P0+':'+rel+'/PREPARATION.json'));failure=j(B/'PREPARATION_ATTEMPT_01.json');pathcheck=j(B/'PREPARATION_CAT_FILE_CHECK.json')
 corrected=old_driver.replace(b"['git', 'show', head + ':' + relative]",b"['git', 'cat-file', 'blob', head + ':' + relative]").replace(b"['git', 'show', head + ':' + source.relative_to(ROOT).as_posix()]",b"['git', 'cat-file', 'blob', head + ':' + source.relative_to(ROOT).as_posix()]")
 ck('prelaunch correction exactly two read calls',driver==corrected and old_driver.count(b"['git', 'show', head + ':'")==2 and failure['preparation_commit']==P0 and failure['formal_started'] is False and failure['new_model_Blender_product_provider_calls']==0)
 ck('prior 168-object check scoped correctly',len(p0prep['files'])+1==pathcheck['committed_object_count']==168 and pathcheck['source_preparation_commit']==P0 and pathcheck['passed'])
 text=driver.decode();ck('final preparation validated before formal reservation',text.index('    validate_preparation(frozen)')<text.index("(BATCH / 'FORMAL_STARTED.json').open('x'"))
 ck('actual wrapper and archive source paths','COORDINATOR = INTERFACE_FIX / \'runtime/episode.py\'' in text and 'sources = coordinator.legacy.pack.capture_cell(runtime, archive)' in text and "transport.consume_turn.__globals__['archive_turn'] is transport.archive_turn" in text)
 protected=['verification/m4_surface_scan_continuous_consumption_001','verification/m4_surface_scan_continuous_interface_fix_001','verification/m4_surface_scan_continuity_001_fix1','verification/m4_surface_scan_continuity_001_fix2','human_eye_plugin','human_eye_module1_operators']
 ck('old failures and fixed implementation unchanged',git('diff','--name-only',OLD,D,'--',*protected)==b'')
 ck('public projection algorithm reused except cycle',raw(B/'quality_tools/pack_quality.py')==raw(R/'verification/m4_surface_scan_continuous_consumption_001/quality_tools/pack_quality.py').replace(b'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001',b'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002'))
 ck('frozen mapping plan and actual order',sha(raw(B/'PLAN.json'))==prep['plan_sha256']==binding['plan_sha256'] and sha(raw(B/'private/ANON_MAP.json'))==prep['anonymous_map_sha256']==plan['anonymous_map_sha256']==binding['mapping_sha256'] and mapping==binding['mapping'] and [(x['cell'],x['anonymous_episode_id']) for x in run['records']]==[(x['cell'],x['anonymous_episode_id']) for x in mapping['rows']]==[(x['cell'],x['anonymous_episode_id']) for x in plan['sequence']])
 files={p.relative_to(public).as_posix():{'bytes':len(raw(p)),'sha256':sha(raw(p))} for p in public.rglob('*') if p.is_file()};zraw=raw(B/'quality/ANONYMOUS_QUALITY.zip');z=zipfile.ZipFile(io.BytesIO(zraw))
 ck('89 public files exact ZIP and inventory',len(files)==receipt['public_files']==89 and files==binding['public_files'] and set(z.namelist())==set(files) and len(z.namelist())==89 and all(z.read(n)==raw(public/n) for n in z.namelist()))
 ck('public/private package hash and unscored boundary',sha(zraw)==receipt['archive_sha256']=='21198b498acbbe0eb3ef68e399b468629094b325eb8cdd75eef532755b068610' and sha(raw(B/'quality/private/BINDING.json'))==receipt['private_binding_sha256'] and receipt['source_consistency_issues']=={} and receipt['cost_unsealed'] is False and receipt['quality']=='unscored')
 ck('frozen public task/truth materials',all(sha(raw(public/n))==h for n,h in index['fixed_quality_materials'].items()))
 ck('18 complete slots execution denominator',len(run['records'])==6 and run['execution_counts']=={'planned':18,'completed':18,'failed':0,'not_run':0} and index['counts']==receipt['counts']=={'completed':18,'failed':0,'not_run':0} and run['stop_reasons']==run['publication_errors']==run['not_run_episodes']==[])
 bybind={x['anonymous_episode_id']:x for x in binding['episodes']};bymap={x['cell']:x for x in mapping['rows']};whitelist=j(B/'private/THREAD_WHITELIST.json');base=j(R/'verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json');edited=j(R/'verification/m4_surface_scan_001/qualification/EDIT_SNAPSHOT.json')
 baseids=[];resumes=closed=missing=archive_count=0;tooltypes={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view','file_change','todo_list','collab_tool_call'}
 for rec in run['records']:
  anon=rec['anonymous_episode_id'];mp=bymap[rec['cell']];pb=bybind[anon];rt=pathlib.Path(rec['runtime_folder']);folder=pathlib.Path(rec['folder']);pe=public/anon;pubep=j(pe/'EPISODE.json')
  ck(anon+' mapping/outer immutable binding',all(rec[k]==mp[k] for k in ['cell','group','pair','anonymous_episode_id','anonymous_turn_ids']) and pb['outer_record_sha256']==sha(enc(rec)))
  rm=j(folder/'RUNTIME_MANIFEST.json');ab=raw(folder/'ORIGINALS.zip');az=zipfile.ZipFile(io.BytesIO(ab));names=az.namelist();archive_count+=len(names);inv={n:{'bytes':len(az.read(n)),'sha256':sha(az.read(n))} for n in names}
  ck(anon+' full original archive local binding',len(names)==len(set(names)) and set(names)=={p.relative_to(rt).as_posix() for p in rt.rglob('*') if p.is_file()} and inv==rm['members']==pb['original_sources']['members'] and sha(ab)==rm['archive_sha256']==rec['runtime_archive_sha256']==pb['original_sources']['archive_sha256'] and all(az.read(n)==raw(rt/n) for n in names))
  ck(anon+' original manifest and declared source hashes',sha(raw(folder/'RUNTIME_MANIFEST.json'))==pb['original_sources']['manifest_sha256'] and all(inv.get(n)==v for n,v in pb['used_sources'].items()) and pb['source_issues']==[])
  out=j(folder/'OUTER_RESULT.json');ck(anon+' outer record matches',all(rec[k]==v for k,v in out.items()) and rec['outer_valid_completion'] and rec['errors']==[])
  guard=j(rt/'SOURCE_GUARD_BEFORE.json');ck(anon+' before after exact pinned loaded source bytes',guard==j(rt/'SOURCE_GUARD_AFTER.json') and all(sha(raw(p))==h for p,h in guard.items()))
  wiring=j(rt/'ACTUAL_WIRING.json');expectedpaths={'coordinator':'verification/m4_surface_scan_continuous_interface_fix_001/runtime/episode.py','transport':'verification/m4_surface_scan_continuous_interface_fix_001/runtime/consumer_transport.py','compatibility':'verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py','packer':'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py'}
  ck(anon+' actual wrapper and legacy pack recorded',all(pathlib.Path(wiring[k])==R/p for k,p in expectedpaths.items()) and wiring['original_consumer_global_bound'] and wiring['original_coordinator_global_bound'] and all(str(pathlib.Path(wiring[k])) in guard for k in ['coordinator','transport','compatibility']))
  er=j(rt/'c/EPISODE_RESULT.json');ck(anon+' three completed coordinator turns',len(er['turns'])==3 and er['counts']==pubep['counts']=={'completed':3,'failed':0,'not_run':0} and er['qualified_execution'] and pubep['valid_completion'] and pubep['source_consistency_issues']==[] and all(rec['coordinator'][k]==er[k] for k in ['turns','errors','qualified_execution','owner_finish']))
  episode_ids=[];works=[];contexts=[];before=0;statuses=[]
  for idx,turn in enumerate(er['turns'],1):
   label=['BASE','REPEAT','EDIT'][idx-1];fp=pathlib.Path(turn['folder']);con=j(fp/'CONSUMER.json');ptu=j(pe/f'turn_{idx}/TURN.json');te=j(pe/f'turn_{idx}/tool_evidence.json');evraw=raw(fp/'events.jsonl');events=[json.loads(x)['event'] for x in evraw.splitlines()];final=raw(fp/'PUBLIC_FINAL.txt')
   ck(anon+f' turn{idx} exact consumer/record',turn['turn_index']==idx and turn['turn_label']==label and turn['consumer']=={**con,'final_timing':j(fp/'FINAL_TIMING.json')} and ptu==pubep['turns'][idx-1] and ptu['anonymous_turn_id']==mp['anonymous_turn_ids'][idx-1] and ptu['execution_state']=='completed' and ptu['valid_completion'] and con['valid_completion'] and ptu['source_consistency_issues']==[])
   messages=[e['item'].get('text') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
   ck(anon+f' turn{idx} all finals original',raw(pe/f'turn_{idx}/answer.txt')==final==con['final'].encode() and messages[-1].encode()==final and pb['turns'][idx-1]['answer_sha256']==sha(final) and raw(pe/f'turn_{idx}/cli_output_unconfirmed.txt')==raw(fp/'final.txt'))
   for field,original in [('errors',con.get('errors',[])),('summary_errors',con.get('summary',{}).get('errors',[])),('bridge_protocol_errors',con.get('bridge_protocol_errors',[])),('public_error_events',[e for e in events if e.get('type') in ['error','turn.failed']])]:ck(anon+f' turn{idx} error projection '+field,ptu[field]==[project_error(x,contexts) for x in original])
   selected=[]
   for line,event in zip(evraw.splitlines(),events):
    item=event.get('item',{})
    if event.get('type') in ['item.started','item.completed'] and item.get('type') in tooltypes:selected.append({'order':len(selected)+1,'phase':event['type'],'event':{k:copy.deepcopy(item[k]) for k in ['type','tool','server','arguments','result','error','status','command'] if k in item},'source_sha256':sha(evraw),'source_line_sha256':sha(line)})
   ck(anon+f' turn{idx} all tool events intact',selected==te['public_tool_events'])
   lower=turn['status_before']['business_attempts'];upper=turn['status_after']['business_attempts'];attempts=[];removals=[];ck(anon+f' turn{idx} contiguous business range',lower==before and upper>=lower);before=upper
   for n in range(lower+1,upper+1):
    call={'order':n-lower,'request':None,'responses':[],'is_error':None,'owner_exception':None,'source_files':[]}
    for name in ['REQUEST.json','RESPONSE.json','ERROR_RESPONSE.json','ATTEMPT.json']:
     f=rt/f'owner/tool_{n:02}'/name
     if not f.exists():continue
     b=raw(f);v=json.loads(b);call['source_files'].append({'kind':name,'original_sha256':sha(b)})
     if name=='REQUEST.json':call['request']=projection(v,'request',b,removals)
     elif name=='ATTEMPT.json':call['is_error']=v.get('is_error');call['owner_exception']=projection(v.get('exception'),'exception',b,removals)
     else:call['responses'].append({'kind':name,'value':projection(v,'response',b,removals)})
    call['request_missing']=call['request'] is None;call['response_missing']=not call['responses'];attempts.append(call)
   ck(anon+f' turn{idx} all owner projections and omissions recorded',te['owner_attempts']==attempts and removals==pb['turns'][idx-1]['business_projection']['administrative_projections'])
   bound=j(fp/'BUSINESS_SOURCE_BINDING.json');ck(anon+f' turn{idx} actual archive wrapper copies',bound['binding_errors']==[] and bound['recorded_owner_attempts']==list(range(lower+1,upper+1)) and all(raw(p['original'])==raw(fp/p['copy']) and len(raw(fp/p['copy']))==p['bytes'] and sha(raw(fp/p['copy']))==p['sha256'] for p in bound['sources']))
   tid=con['thread_id'];episode_ids.append(tid);works.append(con['shared_work']);tids=[e['thread_id'] for e in events if e.get('type')=='thread.started'];expected=None if idx==1 else episode_ids[0]
   ck(anon+f' turn{idx} actual UUID and explicit resume',re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',tid) and tids==[tid] and con['expected_thread_id']==turn['expected_thread_id']==expected and ('resume' in con['frozen_cli_argv'])==(idx>1) and (idx==1 or expected in con['frozen_cli_argv']) and ptu['continuity']['observed_context_matches_events'] and ptu['continuity']['resume_requested']==(idx>1))
   ck(anon+f' turn{idx} whitelist exact',sum(x['thread_id']==tid and x['turn_index']==idx and x['expected_thread_id']==expected for x in whitelist['records'])==1)
   resumes+=idx>1;bridge=con['bridge_cleanup'];missing+=bridge['missing_exit_count']
   ck(anon+f' turn{idx} CLI/readers ended independently of missing thin EXIT',con['process_reaped'] and con['readers_stopped'] and con['exit_code']==0 and con['mutation_unknown'] is False and bridge['receipt_status']=='unknown' and bridge['confirmed'] is None and bridge['missing_exit_count']==1 and bridge['backend_close_confirmed'] is None and len(bridge['instances'])==1 and bridge['instances'][0]['exit'] is None and not list((fp/'attachments').glob('bridge_*/EXIT.json')) and len(list((fp/'attachments').glob('bridge_*/STARTED.json')))==1)
   ck(anon+f' turn{idx} public execution flags exact',ptu['execution_checks']=={k:con.get(k) for k in ['process_reaped','readers_stopped','safe_to_continue','mutation_unknown']})
   statuses.extend([turn['status_before'],turn['status_after']])
  baseids.append(episode_ids[0]);ck(anon+' same UUID and shared work all three turns',len(set(episode_ids))==len(set(works))==1 and pb['contexts']==[{'anonymous_context':'context_1','original_value_sha256':sha(enc(episode_ids[0]))}])
  keys=['episode_id','owner_pid','native_pid','native_host','native_port','native_workspace','product_launcher_pid','product_runtime_proof','session_id','worker_deadline_ns'];ck(anon+' same owned backend all business turns',all(all(x[k]==statuses[0][k] for k in keys) and not x['owner_close_called'] for x in statuses))
  for field,original in [('coordinator_errors',er['errors']),('outer_errors',rec['errors'])]:ck(anon+' exact episode error projection '+field,pubep[field]==[project_error(x,contexts) for x in original])
  close=j(rt/'owner/CLOSE.json');finish=j(rt/'OWNER_FINISH.json');worker=j(rt/'owner/native/WORKER_CLOSED.json');session=j(rt/'owner/native/SESSION.json');cont=j(rt/'owner/CONTINUITY.json');launch=j(rt/'ACTOR_LAUNCH.json');pose=j(rt/'owner/POSE_ADVANCE.json')
  ck(anon+' six-state edit geometry independent readback',norm(j(rt/'owner/INITIAL.json'))==norm(j(rt/'owner/PRE_EDIT.json'))==norm(base) and norm(j(rt/'owner/EDIT.json'))==norm(j(rt/'owner/FINAL.json'))==norm(er['registered_pose']['snapshot'])==norm(edited))
  edits=[e for e in cont['events'] if e['operation']=='qa_advance'];host=[json.loads(x) for x in raw(rt/'owner/native/WORKER_EVENTS.jsonl').splitlines()];adv=[e for e in host if e.get('operation')=='qa_advance'];ck(anon+' exactly one actual registered EDIT',len(edits)==len(adv)==1 and er['registered_pose']['advance']==pose and pose['response']['status']=='success' and pose['response']['result']['target_name']=='Obj_008' and adv[0]['patch_sha256']==session['qa_pose_patch']['sha256'])
  ck(anon+' EDIT online between turns and accepted',cont['completed_turns'][1]['ended_ns']<=edits[0]['started_ns']<=adv[0]['started_ns']<=edits[0]['ended_ns']<=cont['completed_turns'][2]['started_ns'] and cont['edit_attempted'] and cont['edit_verified'] and close['registered_pose_applied'] and worker['qa_patch_applied'] and worker['initial_geometry_fingerprint']!=worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not worker['poisoned'])
  ck(anon+' owned actor and Blender confirmed close',rec['owner_finish_calls']==1 and finish['confirmed'] and finish['exit_code']==0 and finish['actor_pid']==launch['pid'] and finish['close']==close and close['confirmed'] and close['errors']==[] and close['native_close']['process_reaped'] and close['native_close']['exit_code']==0 and close['native_close']['pid']==session['pid']==worker['pid'] and close['active_turn'] is cont['active_turn'] is None)
  if close.get('product_runtime_exit') is not None:ck(anon+' product runtime separate closure',close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0 and close['plugin_close']['process_reaped'] and close['plugin_close']['exit_code']==0)
  ck(anon+' original asset immutable',raw(session['asset_copy'])==raw(session['asset']) and close['asset_unchanged'] and close['native_close']['protected_files_unchanged'] and close['native_close']['source_file_unchanged']);closed+=1
 ck('six independent UUID twelve resumes 18 unknown thin EXIT',len(set(baseids))==6 and resumes==12 and missing==18 and len(whitelist['records'])==18)
 ck('public summaries cover all six',index['anonymous_episode_order']==sorted(bybind) and all(x['counts']==j(public/x['anonymous_episode_id']/'EPISODE.json')['counts'] for x in index['episodes']))
 ck('author tree/head unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(delivery_files=311,preparation_content_files=172,preparation_with_manifest=173,external_files=425,public_files=89,original_archive_members=archive_count,actual_independent_UUIDs=6,actual_turns=18,actual_resumes=12,registered_EDITS=6,owned_closures=closed,CLI_reader_closures=18,thin_EXIT_unknown=missing,all_final_tool_error_projections_bound=True,quality_scoring_performed=False,group_cost_usage_disclosed=False,AL_assignment_current=False,AL_own_write=611,AL_parent_write=630)
 facts['limits']=['18 thin EXIT missing remains unknown despite independent CLI/owned closure.','Actual same UUID resume and shared work/backend are proven; task answer quality and model memory utility require separate scoring.','The retained prelaunch failure receipt is historical authored evidence, not a new process probe.','Inherited QA overwrites _j in persistent namespace; shared GUI before/after was not measured.','No costs/numeric usage or unrelated conversations inspected for this audit; cost proof files only blindly hashed for delivery integrity.','INPUT_HASHES_PRIVATE paths expose source mapping; withhold until root quality seal.']

if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'independent script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'input_paths':len(inputs),'failed':[x for x in checks if not x['passed']],'facts':facts,'new_product_Blender_model_API_runs':0}
 for n,v in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES_PRIVATE.json',inputs)]: (O/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
