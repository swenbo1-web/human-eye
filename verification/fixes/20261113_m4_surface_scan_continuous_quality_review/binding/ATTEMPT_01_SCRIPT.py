"""Independent anonymous-to-original binding and execution audit, no scoring.
Private paths/hashes are stored separately; public results omit route/cost/usage.
Only read-only Git subprocesses; no author checker or product import.
"""
import copy,hashlib,io,json,pathlib,re,subprocess,traceback,zipfile
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuous_consumption_001'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_quality_review/binding')
D='11f944e71bc530822e8741384732529003efc29f';P='a02c4230651b8134539fb4d96595998d8146c75a';OLD='56caf228f6d0224f36796606c7f27b3c24223768'
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
 out={}
 for row in git('ls-tree','-rz',c).split(b'\0'):
  if row:m,p=row.split(b'\t',1);out[p.decode()]=m.split()[2].decode()
 return out
def drop(value,fields):return {k:copy.deepcopy(v) for k,v in value.items() if k not in fields} if isinstance(value,dict) else copy.deepcopy(value)
def project_error(value,contexts):
 if not isinstance(value,dict):return copy.deepcopy(value)
 if 'event' in value and 'perf_ns' in value:
  out=drop(value,['perf_ns']);out['event']=project_error(out['event'],contexts);return out
 out=drop(value,['traceback'])
 def alias(x):
  if x is None:return None
  if x not in contexts:contexts.append(x)
  return 'context_'+str(contexts.index(x)+1)
 if out.get('type') in ('error','turn.failed'):
  out=drop(out,['usage','timestamp','perf_ns','argv','episode_id'])
  for k in ['thread_id','expected_thread_id','observed_thread_id']:
   if k in out:out[k]=alias(out[k])
 if out.get('type')=='resume_thread_mismatch':
  for k in ['expected','observed']:out[k]=alias(out.get(k))
 return out
def projection(value,kind,rawbytes,removed):
 out=copy.deepcopy(value)
 def remove(d,k,pointer,rule):
  if isinstance(d,dict) and k in d:
   v=d.pop(k);removed.append({'source_sha256':sha(rawbytes),'pointer':pointer+'/'+k,'rule':rule,'original_value_sha256':sha(enc(v))})
 if kind in ['request','response']:
  for k in ['id','jsonrpc','_meta']:remove(out,k,'$','RPC_transport_envelope')
  if kind=='request' and isinstance(out,dict):remove(out.get('params'),'_meta','$/params','RPC_administrative_meta_envelope')
 elif kind=='exception':remove(out,'traceback','$/exception','known_administrative_envelope_field')
 return out
def main():
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();ck('fixed clean delivery',head==D and status=='');dt,pt=tree(D),tree(P);rel=B.relative_to(R).as_posix()
 manifest=j(B/'DELIVERY_MANIFEST.json');prep=j(B/'PREPARATION.json');mapping=j(B/'private/ANON_MAP.json');run=j(B/'RUN_RESULT.json');plan=j(B/'PLAN.json');start=j(B/'FORMAL_STARTED.json');receipt=j(B/'quality/PACKAGE_RECEIPT.json');binding=j(B/'quality/private/BINDING.json');public=B/'quality/public';index=j(public/'INDEX.json')
 names={x['path'] for x in manifest['files']};actual={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in p.parts}
 ck('144 content plus manifest exact set',len(manifest['files'])==144 and names==actual)
 bad=[]
 for x in manifest['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=dt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('all delivery members hash size Git',not bad);ck('delivery manifest Git',blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 bad=[]
 for x in prep['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=pt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('32 preparation files plus manifest',len(prep['files'])==32 and not bad and blob(raw(B/'PREPARATION.json'))==pt[rel+'/PREPARATION.json'])
 ck('fixed preparation reference',manifest['preparation_commit']==P and manifest['preparation_sha256']==sha(raw(B/'PREPARATION.json')) and prep['preparation_parent_commit']==OLD and start['preparation']['committed_verified'])
 bad=[path for path,h in prep['external_sha256'].items() if sha(raw(path))!=h];ck('372 external bytes unchanged',len(prep['external_sha256'])==372 and not bad)
 ck('old FIX1 FIX2 and product unchanged',git('diff','--name-only',OLD,D,'--','verification/m4_surface_scan_continuity_001_fix1','verification/m4_surface_scan_continuity_001_fix2','human_eye_plugin','human_eye_module1_operators')==b'')
 ck('mapping frozen before dispatch',sha(raw(B/'private/ANON_MAP.json'))==prep['anonymous_map_sha256']==plan['anonymous_map_sha256']==binding['mapping_sha256'] and mapping==binding['mapping'] and sha(raw(B/'PLAN.json'))==prep['plan_sha256']==binding['plan_sha256'] and binding['run_result_sha256']==sha(raw(B/'RUN_RESULT.json')))
 ck('six entered records distinct anonymous IDs',len(run['records'])==len(mapping['rows'])==len(binding['episodes'])==6 and len({x['anonymous_episode_id'] for x in run['records']})==6)
 bycell={x['cell']:x for x in run['records']};byanon={x['anonymous_episode_id']:x for x in binding['episodes']}
 ck('same frozen sequence',[(x['cell'],x['anonymous_episode_id']) for x in plan['sequence']]==[(x['cell'],x['anonymous_episode_id']) for x in mapping['rows']]==[(x['cell'],x['anonymous_episode_id']) for x in run['records']])
 files={p.relative_to(public).as_posix():{'bytes':len(raw(p)),'sha256':sha(raw(p))} for p in public.rglob('*') if p.is_file()}
 ck('65 canonical public files exact private inventory',len(files)==receipt['public_files']==65 and files==binding['public_files'])
 zipped=raw(B/'quality/ANONYMOUS_QUALITY.zip');z=zipfile.ZipFile(io.BytesIO(zipped));ck('anonymous ZIP identity and full member bytes',sha(zipped)==receipt['archive_sha256']=='c062e993a1c46d7f7b77215120cafb1d973bf003b5c04436f848be814ec4939d' and len(z.namelist())==len(set(z.namelist()))==65 and set(z.namelist())==set(files) and all(z.read(n)==raw(public/n) for n in z.namelist()))
 ck('private binding digest and unscored boundary',sha(raw(B/'quality/private/BINDING.json'))==receipt['private_binding_sha256'] and receipt['source_consistency_issues']=={} and index['content_quality']==receipt['quality']=='unscored' and receipt['cost_unsealed'] is binding['cost_unsealed'] is False)
 ck('all frozen public scoring and prompts intact',all(sha(raw(public/n))==h for n,h in index['fixed_quality_materials'].items()))
 ck('18 slots exact failed/notrun denominator',receipt['planned_episodes']==index['planned_episodes']==6 and receipt['planned_turns']==index['planned_turns']==18 and index['counts']==receipt['counts']=={'completed':0,'failed':6,'not_run':12})
 threads=[];whitelist=j(B/'private/THREAD_WHITELIST.json');total_archive=total_attempts=total_events=0;closed=missing=0;tooltypes={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view','file_change','todo_list','collab_tool_call'}
 for maprow in mapping['rows']:
  anon=maprow['anonymous_episode_id'];rec=bycell[maprow['cell']];pb=byanon[anon];folder=pathlib.Path(rec['folder']);rt=pathlib.Path(rec['runtime_folder']);pe=public/anon
  ck(anon+' mapping entry bound',all(rec[k]==maprow[k] for k in ['cell','group','pair','anonymous_episode_id','anonymous_turn_ids']) and pb['cell']==maprow['cell'] and pb['outer_record_sha256']==sha(enc(rec)))
  rm=j(folder/'RUNTIME_MANIFEST.json');ar=raw(folder/'ORIGINALS.zip');archive=zipfile.ZipFile(io.BytesIO(ar));members=archive.namelist();actualmembers={p.relative_to(rt).as_posix() for p in rt.rglob('*') if p.is_file()};total_archive+=len(members)
  ck(anon+' original archive whole inventory',len(members)==len(set(members)) and set(members)==actualmembers and not any(n.startswith('/') or '\\' in n or '..' in pathlib.Path(n).parts for n in members))
  inventory={n:{'bytes':len(archive.read(n)),'sha256':sha(archive.read(n))} for n in members}
  ck(anon+' original ZIP manifest disk bytes',inventory==rm['members']==pb['original_sources']['members'] and all(archive.read(n)==raw(rt/n) for n in members) and sha(ar)==rm['archive_sha256']==pb['original_sources']['archive_sha256']==rec['runtime_archive_sha256'])
  ck(anon+' original manifest/binding sources',sha(raw(folder/'RUNTIME_MANIFEST.json'))==pb['original_sources']['manifest_sha256'] and pathlib.Path(rm['runtime_folder'])==rt and pb['source_issues']==[] and all(inventory.get(n)==v for n,v in pb['used_sources'].items()))
  out=j(folder/'OUTER_RESULT.json');ck(anon+' outer published record retained',all(rec[k]==v for k,v in out.items()))
  er=j(rt/'c/EPISODE_RESULT.json');turn=er['turns'][0];con=j(rt/'c/turns/BASE/CONSUMER.json');turnraw=raw(rt/'c/turns/BASE/events.jsonl');events=[json.loads(x)['event'] for x in turnraw.splitlines()];pubep=j(pe/'EPISODE.json');pubturn=j(pe/'turn_1/TURN.json');te=j(pe/'turn_1/tool_evidence.json');contexts=[]
  ck(anon+' one entered first turn only',len(er['turns'])==1 and turn['turn_index']==1 and turn['turn_label']=='BASE' and er['counts']==pubep['counts']=={'completed':0,'failed':1,'not_run':2} and not (rt/'c/turns/REPEAT').exists() and not (rt/'c/turns/EDIT').exists())
  ck(anon+' exact consumer record coordinator',turn['consumer']==con and all(rec['coordinator'][k]==er[k] for k in ['turns','errors','qualified_execution','owner_finish']))
  final=raw(rt/'c/turns/BASE/PUBLIC_FINAL.txt');messages=[x['item'].get('text') for x in events if x.get('type')=='item.completed' and x.get('item',{}).get('type')=='agent_message']
  ck(anon+' answer original final consumer event exact',raw(pe/'turn_1/answer.txt')==final==con['final'].encode() and messages and messages[-1].encode()==final and sha(final)==pb['turns'][0]['answer_sha256'])
  ck(anon+' CLI output retained independently',raw(pe/'turn_1/cli_output_unconfirmed.txt')==raw(rt/'c/turns/BASE/final.txt'))
  for field,original in [('errors',con.get('errors',[])),('summary_errors',con.get('summary',{}).get('errors',[])),('bridge_protocol_errors',con.get('bridge_protocol_errors',[])),('public_error_events',[x for x in events if x.get('type') in ['error','turn.failed']])]:ck(anon+' exact error projection '+field,pubturn[field]==[project_error(x,contexts) for x in original])
  for field,original in [('coordinator_errors',er['errors']),('outer_errors',rec['errors'])]:ck(anon+' exact episode errors '+field,pubep[field]==[project_error(x,contexts) for x in original])
  ck(anon+' failed status not replaced by content',pubturn['execution_state']=='failed' and not pubturn['valid_completion'] and pubturn['final_present'] and pubturn['source_consistency_issues']==[] and pubep['execution_state']=='execution_failure' and pubep['source_consistency_issues']==[] and pubep['turns'][0]==pubturn)
  for t in [2,3]:
   u=j(pe/f'turn_{t}/TURN.json');e=j(pe/f'turn_{t}/tool_evidence.json');ck(anon+f' notrun slot {t}',u==pubep['turns'][t-1] and u['anonymous_turn_id']==maprow['anonymous_turn_ids'][t-1] and u['execution_state']=='not_run' and not u['final_present'] and e['owner_attempts']==e['public_tool_events']==[] and not (pe/f'turn_{t}/answer.txt').exists())
  tid=con['thread_id'];thread_events=[x['thread_id'] for x in events if x.get('type')=='thread.started'];threads.append(tid)
  ck(anon+' actual fresh UUID no resume',re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',tid) and thread_events==[tid] and con['expected_thread_id'] is None and 'resume' not in con['frozen_cli_argv'] and pubturn['continuity']['resume_requested'] is False and pubturn['continuity']['observed_context_matches_events'] and pubturn['continuity']['observed_context']=='context_1')
  ck(anon+' private context and whitelist binding',pb['contexts']==[{'anonymous_context':'context_1','original_value_sha256':sha(enc(tid))}] and sum(x['thread_id']==tid and x['turn_index']==1 and x['expected_thread_id'] is None for x in whitelist['records'])==1)
  selected=[]
  for line,event in zip(turnraw.splitlines(),events):
   item=event.get('item',{})
   if event.get('type') in ['item.started','item.completed'] and item.get('type') in tooltypes:selected.append({'order':len(selected)+1,'phase':event['type'],'event':{k:copy.deepcopy(item[k]) for k in ['type','tool','server','arguments','result','error','status','command'] if k in item},'source_sha256':sha(turnraw),'source_line_sha256':sha(line)})
  ck(anon+' every tool event projection intact',te['public_tool_events']==selected);total_events+=len(selected)
  lower=turn['status_before']['business_attempts'];upper=turn['status_after']['business_attempts'];attempts=[];removed=[]
  for n in range(lower+1,upper+1):
   call={'order':n-lower,'request':None,'responses':[],'is_error':None,'owner_exception':None,'source_files':[]}
   for name in ['REQUEST.json','RESPONSE.json','ERROR_RESPONSE.json','ATTEMPT.json']:
    f=rt/f'owner/tool_{n:02}'/name
    if not f.exists():continue
    b=raw(f);v=json.loads(b);call['source_files'].append({'kind':name,'original_sha256':sha(b)})
    if name=='REQUEST.json':call['request']=projection(v,'request',b,removed)
    elif name=='ATTEMPT.json':call['is_error']=v.get('is_error');call['owner_exception']=projection(v.get('exception'),'exception',b,removed)
    else:call['responses'].append({'kind':name,'value':projection(v,'response',b,removed)})
   call['request_missing']=call['request'] is None;call['response_missing']=not call['responses'];attempts.append(call)
  ck(anon+' every owner attempt projection intact',te['owner_attempts']==attempts and removed==pb['turns'][0]['business_projection']['administrative_projections']);total_attempts+=len(attempts)
  ck(anon+' tool evidence exact bound digest',sha(raw(pe/'turn_1/tool_evidence.json'))==pb['turns'][0]['business_projection']['published_tool_evidence_sha256'])
  close=j(rt/'owner/CLOSE.json');finish=j(rt/'OWNER_FINISH.json');worker=j(rt/'owner/native/WORKER_CLOSED.json');session=j(rt/'owner/native/SESSION.json');launch=j(rt/'ACTOR_LAUNCH.json');bridge=con['bridge_cleanup'];cont=j(rt/'owner/CONTINUITY.json')
  ck(anon+' owned actor and Blender normal close',rec['owner_finish_calls']==1 and finish['confirmed'] and finish['exit_code']==0 and finish['actor_pid']==launch['pid'] and finish['close']==close and close['confirmed'] and close['errors']==[] and close['native_close']['process_reaped'] and close['native_close']['exit_code']==0 and close['native_close']['pid']==worker['pid']==session['pid'])
  if close.get('product_runtime_exit') is not None:ck(anon+' own product runtime closed',close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0 and close['plugin_close']['process_reaped'] and close['plugin_close']['exit_code']==0)
  ck(anon+' no EDIT or unresolved state',not close['registered_pose_applied'] and not worker['qa_patch_applied'] and not worker['poisoned'] and close['active_turn'] is cont['active_turn'] is None and worker['initial_geometry_fingerprint']==worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and close['geometry_unchanged'] and con['mutation_unknown'] is False)
  ck(anon+' CLI reaped separate from thin unknown',con['process_reaped'] and con['readers_stopped'] and con['exit_code']==0 and bridge['receipt_status']=='unknown' and bridge['confirmed'] is None and bridge['missing_exit_count']==1 and bridge['backend_close_confirmed'] is None)
  ck(anon+' actual missing thin EXIT retained',len(bridge['instances'])==1 and bridge['instances'][0]['exit'] is None and bridge['instances'][0]['confirmed'] is None and not list((rt/'c/turns/BASE/attachments').glob('bridge_*/EXIT.json')) and len(list((rt/'c/turns/BASE/attachments').glob('bridge_*/STARTED.json')))==1)
  ck(anon+' consumer checks projected without upgrade',pubturn['execution_checks']=={k:con.get(k) for k in ['process_reaped','readers_stopped','safe_to_continue','mutation_unknown']})
  ck(anon+' original asset bytes unchanged',raw(session['asset_copy'])==raw(session['asset']) and close['asset_unchanged'] and close['native_close']['source_file_unchanged'] and close['native_close']['protected_files_unchanged'])
  closed+=1;missing+=bridge['missing_exit_count']
 ck('six unique actual UUID and zero resume',len(set(threads))==len(threads)==len(whitelist['records'])==6)
 ck('public index references all anonymous summaries',index['anonymous_episode_order']==sorted(byanon) and all(x['counts']==j(public/x['anonymous_episode_id']/'EPISODE.json')['counts'] for x in index['episodes']))
 ck('author HEAD/tree unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(delivery_files=145,preparation_files=33,external_files=372,public_files=65,original_archive_members=total_archive,actual_threads=6,resume_count=0,planned_turns=18,failed_turns=6,not_run_turns=12,owned_backends_closed=closed,thin_EXIT_missing=missing,thin_closure_status='unknown',projected_owner_attempts=total_attempts,projected_tool_events=total_events,quality_scoring_performed=False,cost_or_group_unsealed_to_root=False,AL_own_assignment_current=False,AL_own_write=611,AL_parent_write=626)
 facts['limits']=['All original finals/tool/errors are retained by the stated administrative projections; no claim that model consumed every tool byte.','All owned backend closures and CLI reaps are confirmed, but six missing thin EXIT remain unknown.','Real same-thread resume/repeat/EDIT is not tested: all episodes stop after their first turn.','This review neither diagnoses CLI/owner result wrappers nor scores answer content; these are separate root reviews.','INPUT_HASHES_PRIVATE.json and original source paths can reveal mapping; withhold until root quality seal.']

if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'independent script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'input_paths':len(inputs),'failed':[x for x in checks if not x['passed']],'facts':facts,'new_product_Blender_model_API_runs':0}
 for name,obj in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES_PRIVATE.json',inputs)]: (O/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
