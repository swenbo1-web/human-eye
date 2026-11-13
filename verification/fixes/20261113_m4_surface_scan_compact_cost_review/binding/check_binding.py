"""Independent offline post-seal source review; no product/checker imports."""
import ast,base64,copy,hashlib,io,json,pathlib,subprocess,tomllib,traceback,zipfile,zlib
ROOT=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=ROOT/'verification/m4_surface_scan_compact_consumption_001'
OUT=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_cost_review/binding')
OLD='f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).decode().splitlines()]
def check(n,v):checks.append({'check':n,'passed':bool(v)})
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def normalize(s):return {'unit_scale_m':s['unit_scale_m'],'objects':sorted([{k:o[k] for k in ['name','vertices_local','matrix_world','faces']} for o in s['objects']],key=lambda o:o['name'])}
def subset(actual,projected):
 if isinstance(projected,dict):return isinstance(actual,dict) and all(k in actual and subset(actual[k],v) for k,v in projected.items())
 return actual==projected
def main():
 commit=git('rev-parse','e089a7ba').decode().strip();head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode()
 check('fixed_head',commit==head);check('clean_author_tree',status=='');facts['commit']=commit
 tree={}
 for x in git('ls-tree','-rz',commit).split(b'\0'):
  if x:meta,path=x.split(b'\t',1);tree[path.decode()]=meta.split()[2].decode()
 changed=git('diff','--name-only',OLD,commit).decode().splitlines();prefix=B.relative_to(ROOT).as_posix()+'/cost/'
 check('only_27_cost_files_added',len(changed)==27 and all(x.startswith(prefix) for x in changed))
 prior=j(pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_quality_review/package/INPUT_HASHES.json'))
 check('old_manifest_same_as_independent_review',sha(raw(B/'DELIVERY_MANIFEST.json'))==prior['DELIVERY_MANIFEST.json']['sha256'])
 cost=j(B/'cost/DELIVERY_MANIFEST.json');check('cost_increment_count',len(cost['files'])==26 and cost['file_count']==26)
 check('cost_manifest_exact_set',{p.relative_to(B/'cost').as_posix() for p in (B/'cost').rglob('*') if p.is_file() and p.name!='DELIVERY_MANIFEST.json'}=={x['path'] for x in cost['files']})
 for row in cost['files']:
  p=B/'cost'/row['path'];b=raw(p);check('cost_sha:'+row['path'],sha(b)==row['sha256'] and len(b)==row['bytes']);check('cost_git:'+row['path'],blob(b)==tree[p.relative_to(ROOT).as_posix()])
 check('cost_manifest_git',blob(raw(B/'cost/DELIVERY_MANIFEST.json'))==tree[(B/'cost/DELIVERY_MANIFEST.json').relative_to(ROOT).as_posix()])
 rootseal=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json');seal=j(rootseal)
 check('root_seal_sha',sha(raw(rootseal))=='c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb')
 check('seal_copy',raw(rootseal)==raw(B/'cost/inputs/QUALITY_SEAL.json'))
 rootgit=subprocess.check_output(['git','show','1f1a23dda3413721d6c71bd1db95f3a40a7c4977:verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json'],cwd='D:/hefe');check('root_seal_git',rootgit==raw(rootseal))
 pub=B/'quality/public';check('r2_zip_unchanged',sha(raw(B/'quality/SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip'))==seal['r2_zip_sha256'])
 pm=[{'path':p.relative_to(pub).as_posix(),'bytes':len(raw(p)),'sha256':sha(raw(p))} for p in sorted(pub.rglob('*')) if p.is_file()];pm.sort(key=lambda x:x['path'])
 check('r2_canonical_unchanged',sha(canonical(pm))==seal['public_canonical_sha256']);check('redaction_receipt_unchanged',sha(raw(B/'quality/ADMIN_REDACTION.json'))==prior['quality/ADMIN_REDACTION.json']['sha256'])
 mapping=j(B/'private/ANON_MAP.json');check('original_map_handoff_equal',mapping==j(B/'runtime/handoff_01/private/control/private/ANON_MAP.json'))
 plan=j(B/'PLAN.json');check('map_frozen',sha(raw(B/'private/ANON_MAP.json'))==plan['private_anonymous_map_sha256'])
 prov=j(B/'runtime/handoff_01/private/PROVENANCE.json');prows={x['mapping']['cell']:x for x in prov['answers']};srows={x['anonymous_id']:x for x in seal['answers']};index=j(pub/'INDEX.json');irows={x['anonymous_id']:x for x in index['answers']}
 base=normalize(j(pub/'scoring/ACTUAL_SNAPSHOT.json'));readies={g:j(B/f'installations/{g}_READY.json') for g in ['O','C']}
 for g,ready in readies.items():
  fixed=j(ready['fixed_inputs']);site=pathlib.Path(ready['install_root']);binding=j(pathlib.Path(ready['release'])/'admin/RUNTIME_BINDING.json')
  check(g+':source_count',len(fixed['manifest'])==len(binding['source_files'])==138 and fixed['manifest']==binding['source_files'])
  identity=binding['identity'];aggregate=sha(json.dumps({'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':fixed['manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
  check(g+':aggregate',aggregate==ready['source_sha256']==plan['candidate_source_sha256'][g])
  for item in fixed['manifest']:check(g+':source:'+item['path'],sha(raw(site/item['path']))==item['sha256'])
  for name,key in [('target_runtime_entry.py','launcher_sha256'),('RUNTIME_BINDING.json','binding_sha256')]:check(g+':entry:'+name,sha(raw(pathlib.Path(ready['release'])/'admin'/name))==ready[key])
 for name,digest in plan['external_input_sha256'].items():check('external_binding:'+name,sha(raw(name))==digest)
 threads=[];workers=[];runtime_pids=[];owner_pids=[];consumer_pids=[];zip_members=0;total_tools=0;total_events=0;last_end=None;facts['cells']=[]
 for m in mapping['rows']:
  label=m['cell'];group=m['group'];anon=m['anonymous_id'];cell=B/'cells'/label;p=prows[label];s=srows[anon];i=irows[anon]
  check(label+':map',p['mapping']==m)
  archive=zipfile.ZipFile(io.BytesIO(raw(B/f'runtime/handoff_01/private/raw/{anon}.zip')))
  check(label+':archive_inventory',set(archive.namelist())==set(p['source_files_sha256']) and len(archive.namelist())==len(set(archive.namelist())))
  zip_members+=len(archive.namelist())
  for name in archive.namelist():
   data=raw(cell/name);check(label+':archive_member:'+name,archive.read(name)==data and sha(data)==p['source_files_sha256'][name]);check(label+':raw_git:'+name,blob(data)==tree[(cell/name).relative_to(ROOT).as_posix()])
  con=j(cell/'CONSUMER.json');ev=lines(cell/'events.jsonl');public_final=raw(cell/'PUBLIC_FINAL.txt');final=raw(cell/'final.txt')
  messages=[x['event']['item']['text'] for x in ev if x['event'].get('type')=='item.completed' and x['event'].get('item',{}).get('type')=='agent_message']
  check(label+':final_chain',final==public_final==con['final'].encode()==messages[-1].encode()==raw(pub/anon/'answer.txt')==raw(pub/anon/'cli_output_unconfirmed.txt'))
  check(label+':seal_final_hash',sha(final)==s['final_sha256']==i['answer_original_sha256'])
  starts=[x['event']['thread_id'] for x in ev if x['event']['type']=='thread.started'];check(label+':thread',starts==[con['thread_id']]);threads.extend(starts)
  errors=[x for x in ev if x['event']['type']=='error'];check(label+':error_chain',errors==con['errors'] and [{'event':x['event']} for x in errors]==s['execution_errors']==i['consumer_execution_errors'])
  check(label+':valid_failure_preserved',con['valid_completion']==s['consumer_valid_completion'] and (s['execution_state']=='failed')==(label in ['N2','O2']))
  check(label+':consumer_reaped',con['process_reaped'] and con['exit_code']==0 and con['readers_stopped'] and con['process_cleanup']['parent_reaped'] and con['process_cleanup']['parent_exit']==0)
  check(label+':thin_exit_unknown',con['bridge_cleanup']['receipt_status']=='unknown' and con['bridge_cleanup']['missing_exit_count']==1 and con['bridge_cleanup']['instances'][0]['exit'] is None)
  check(label+':prompt_model',con['input_sha256']==plan['inputs']['prompt_sha256'] and con['model']==plan['model'] and con['requested_effort']==plan['requested_effort'])
  argv=con['argv'];opts=[argv[n+1] for n,x in enumerate(argv[:-1]) if x=='-c'];cfg={}
  for option in opts:
   d=tomllib.loads(option)
   def merge(a,b):
    for k,v in b.items():
     if isinstance(v,dict) and isinstance(a.get(k),dict):merge(a[k],v)
     else:a[k]=v
   merge(cfg,d)
  check(label+':CLI_isolation',all(x in argv for x in ['--ignore-user-config','--ignore-rules','--ephemeral','--strict-config','--json']) and cfg['features']['hooks'] is False and cfg['features']['shell_tool'] is False and cfg['approval_policy']=='never')
  check(label+':CLI_requested_model',cfg['model']=='gpt-6.1-sol' and cfg['model_reasoning_effort']=='medium' and cfg['forced_login_method']=='chatgpt')
  check(label+':CLI_provider_endpoint',cfg['model_provider']=='openai_http' and cfg['model_providers']['openai_http']['base_url']=='https://chatgpt.com/backend-api/codex' and cfg['model_providers']['openai_http']['supports_websockets'] is False)
  server=cfg['mcp_servers']['arm_engine'];server_args=server['args'];check(label+':CLI_owner_endpoint',pathlib.Path(server_args[server_args.index('--endpoint')+1])==cell/'ENDPOINT.json' and pathlib.Path(server_args[server_args.index('--audit')+1])==cell/'attachments')
  endpoint=j(cell/'ENDPOINT.json');actor=j(cell/'ACTOR_CONFIG.json');launch=j(cell/'ACTOR_LAUNCH.json');identity=j(cell/'owner/IDENTITY.json');close=j(cell/'owner/CLOSE.json');finish=j(cell/'OWNER_FINISH.json');native=j(cell/'owner/native/SESSION.json');worker=j(cell/'owner/native/WORKER_CLOSED.json')
  owner_pids.append(identity['actor_pid']);consumer_pids.append(con['consumer_pid']);workers.append(native['pid'])
  check(label+':owner_parent',launch['pid']==identity['actor_parent_pid']==close['actor_parent_pid']==finish['actor_pid'] and identity['actor_pid']==close['actor_pid'])
  check(label+':owned_asset',raw(native['asset_copy'])==raw(B/'input/scene.blend') and sha(raw(native['asset']))==actor['asset_sha256']==identity['asset_sha256']==plan['inputs']['scene_sha256'])
  check(label+':schemas_config',actor.get('read_schemas',[])==(j(B/f'schemas/{group}_PUBLIC_TOOLS.json') if group!='N' else []))
  toolcatalog=j(cell/'owner/TOOLS.json');check(label+':tools_attempt_ledger',toolcatalog['tools']==close['tools'] and toolcatalog['attempts']==close['tool_attempts'])
  attachment=next((cell/'attachments').glob('bridge_*'));lists=[j(p) for p in attachment.glob('*/RX.bin') if 'tools' in j(p).get('result',{})]
  check(label+':consumer_actual_tools_list',len(lists)==1 and lists[0]['result']['tools']==j(B/f'schemas/{group}_CONSUMER_TOOLS.json'))
  common=j(B/'schemas/COMMON_NATIVE.json');check(label+':common_native_schema',common in lists[0]['result']['tools'])
  original_events=lines(cell/'owner/native/WORKER_EVENTS.jsonl')
  for stage in ['INITIAL','FINAL']:
   snap=j(cell/f'owner/{stage}.json');receipt=j(cell/f'owner/{stage}.json.receipt.json');body=json.loads(receipt['response']['result']['result']);check(label+':snapshot:'+stage,normalize(snap)==base and body==snap)
   matching=[]
   for stdout in (cell/'owner/native').glob('call_*/stdout.txt'):
    try:v=json.loads(raw(stdout))
    except (json.JSONDecodeError,UnicodeDecodeError):continue
    if v==snap:matching.append(stdout.parent)
   check(label+':snapshot_worker_stdout:'+stage,len(matching)==2)
   for call in matching:
    seq=int(call.name.split('_')[1]);code=raw(call/'SCRIPT.py').replace(b'\r\n',b'\n');check(label+':snapshot_script:'+stage+call.name,sha(code)==original_events[seq-1]['script_sha256'])
  check(label+':close_binding',finish['close']==close and finish['confirmed'] and finish['exit_code']==0 and close['worker_closed']==worker and close['confirmed'] and close['errors']==[])
  source=j(pub/anon/'source_consistency.json')
  for name,digest in source['source_records_sha256'].items():check(label+':public_source_record:'+name,sha(raw(cell/name))==digest)
  check(label+':public_source_actor_identity',subset(actor,source['ACTOR_CONFIG']) and subset(identity,source['owner_IDENTITY']))
  projected=copy.deepcopy(source['CLOSE']);projected.pop('worker_fingerprint_fields',None);check(label+':public_source_close',subset(close,projected))
  check(label+':public_source_snapshot_hashes',source['INITIAL_original_file_sha256']==sha(raw(cell/'owner/INITIAL.json')) and source['FINAL_original_file_sha256']==sha(raw(cell/'owner/FINAL.json')))
  nc=close['native_close'];check(label+':native_close',nc['pid']==worker['pid']==native['pid'] and nc['process_reaped'] and nc['exit_code']==0 and nc['response']['status']=='closed' and nc['error'] is None)
  check(label+':geometry_final',worker['final_geometry_fingerprint']==worker['initial_geometry_fingerprint'] and not worker['poisoned'] and close['geometry_unchanged'] and close['asset_unchanged'])
  evidence=j(pub/anon/'tool_evidence.json');attempts=sorted((cell/'owner').glob('tool_*'));tools=[x for x in ev if x['event'].get('item',{}).get('type')=='mcp_tool_call'];total_tools+=len(attempts);total_events+=len(tools)
  check(label+':attempt_count',len(attempts)==close['tool_attempts']==len(evidence['owner_attempts']) and len(tools)==2*len(attempts))
  for n,path in enumerate(attempts):
   req=j(path/'REQUEST.json');response=j(path/'RESPONSE.json');att=j(path/'ATTEMPT.json');pubatt=evidence['owner_attempts'][n];projected=copy.deepcopy(req);projected.pop('id',None);projected.pop('jsonrpc',None);projected['params'].pop('_meta',None)
   check(label+f':public_request:{n}',projected==pubatt['request'])
   projected=copy.deepcopy(response);projected.pop('id',None);projected.pop('jsonrpc',None)
   check(label+f':public_response:{n}',pubatt['responses']==[{'kind':'RESPONSE.json','value':projected}])
   pair=tools[2*n:2*n+2];check(label+f':tool_pair:{n}',[x['event']['type'] for x in pair]==['item.started','item.completed'] and pair[0]['event']['item']['id']==pair[1]['event']['item']['id'])
   check(label+f':tool_arguments:{n}',pair[0]['event']['item']['arguments']==req['params']['arguments'] and pair[0]['event']['item']['tool']==att['name']==req['params']['name'])
   delivered=pair[1]['event']['item'];check(label+f':tool_response:{n}',delivered['result']['content']==response['result']['content'] and delivered['result'].get('structured_content')==response['result'].get('structuredContent') and delivered['error'] is None and response['result']['isError'] is False)
   check(label+f':request_thread:{n}',req['params']['_meta']['threadId']==con['thread_id'])
   check(label+f':tool_receipt:{n}',att==close['tools'][n] and not att['is_error'] and att['exception'] is None)
  event_lines=[line for line in raw(cell/'events.jsonl').splitlines() if json.loads(line)['event'].get('item',{}).get('type')=='mcp_tool_call']
  for public_event,original_event,line in zip(evidence['public_tool_events'],tools,event_lines,strict=True):
   item=copy.deepcopy(original_event['event']['item']);item.pop('id',None)
   check(label+':public_event_projection:'+str(public_event['order'])+public_event['phase'],item==public_event['event'] and original_event['event']['type']==public_event['phase'])
   check(label+':public_event_line_hash:'+str(public_event['order'])+public_event['phase'],sha(line)==public_event['source_line_sha256'] and sha(raw(cell/'events.jsonl'))==public_event['source_sha256'])
  timing=j(cell/'CELL_FINAL_TIMING.json');publish=j(cell/'CELL_TIMING_PUBLICATION.json');start=timing['cell_started_ns'];end=timing['business_receipts_closed_ns'];deadline=actor['worker_deadline_ns']
  check(label+':deadline_570',deadline-start==570_000_000_000 and deadline==native['deadline_ns']==worker['original_deadline_ns']==launch['worker_deadline_ns'])
  check(label+':full_close_boundary',end-start==timing['full_cell_wall_ns'] and close['ended_ns']<=end<=deadline and con['cleanup_end_ns']<=end and timing['within_570s'] and timing['owner_cleanup_confirmed'])
  check(label+':publication_boundary',end==publish['business_receipts_closed_ns']<=publish['timing_receipt_publication_started_ns']<=publish['timing_receipt_publication_closed_ns'])
  if last_end is not None:check(label+':sequential_cells',start>last_end)
  last_end=publish['timing_receipt_publication_closed_ns']
  if group!='N':
   ready=readies[group];proof=j(cell/'owner/PRODUCT_RUNTIME_PROOF.json');rpc=j(cell/'owner/plugin/RPC.json');pstart=j(cell/'owner/plugin/START.json');pclose=j(cell/'owner/plugin/CLOSE.json');runtime_pids.append(proof['runtime_pid'])
   check(label+':actual_source',identity['runtime_identity']['source_sha256']==ready['source_sha256']==actor['source_sha256'] and identity['runtime_identity']['distribution_version']==ready['version'])
   check(label+':initialize_source',j(cell/'owner/PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye']['source_sha256']==ready['source_sha256'])
   check(label+':entry_actual',pstart['command'][3]==actor['entry']==ready['entry'] and j(cell/'owner/product_config.json')['expected_identity']['source_sha256']==ready['source_sha256'])
   chain=proof['parent_chain'];check(label+':ancestry',proof['confirmed'] and chain[0]['pid']==proof['runtime_pid'] and chain[0]['parent_pid']==chain[1]['pid']==proof['launcher_pid']==pstart['launcher_pid'] and chain[1]['parent_pid']==identity['actor_pid'] and chain[0]['created_filetime']>=chain[1]['created_filetime'])
   metadata=rpc['requests'][:4];check(label+':metadata_sequence',[x['method'] for x in metadata]==['initialize','notifications/initialized','tools/list','ping'])
   check(label+':proof_timing',original_events[0]['started_ns']+original_events[0]['elapsed_ns']<=proof['initial_QA_completed_ns']<metadata[0]['started_ns'] and max(x['started_ns']+x['elapsed_ns'] for x in metadata)<=proof['observed_ns']<=proof['proved_ns']<close['tools'][0]['started_ns'] and proof['before_stdin'] is False)
   ptools=j(cell/'owner/PLUGIN_TOOLS.json')['result']['tools'];check(label+':schema_transparency',[x for x in ptools if x['name']=='human_eye_scene_observe']==actor['read_schemas'])
   audit=lines(cell/'owner/audit.jsonl');check(label+':actual_audit_identity',all(x['pid']==proof['runtime_pid'] and x['runtime_identity']['build_id']=='sha256:'+ready['source_sha256'] for x in audit))
   obs=[x for x in audit if x['event']=='observe'];check(label+':first_scan_empty',obs[0]['task_work']['measurement_cache_before']['measurement_entries']==0 and obs[0]['task_work']['kernel_calls']==112)
   embedded=[];known={x['sha256']:x['path'] for x in j(ready['fixed_inputs'])['manifest']}
   for path in (cell/'owner/native').glob('call_*/SCRIPT.py'):
    code=raw(path).decode();
    if 'capture_surface_scan' not in code:continue
    for node in ast.walk(ast.parse(code)):
     if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>1000:
      try:data=zlib.decompress(base64.b64decode(node.value,validate=True))
      except Exception:continue
      check(label+':embedded_source:'+sha(data),sha(data) in known);embedded.append(known.get(sha(data)))
   check(label+':embedded_host_source_inventory',len(embedded)==6 and 'human_eye_plugin/blender_host.py' in embedded and 'human_eye_plugin/scene_residency.py' in embedded)
   check(label+':product_exit',pclose==close['plugin_close'] and pclose['process_reaped'] and pclose['exit_code']==0 and close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0 and pclose['ended_ns']<=close['product_runtime_exit']['observed_ns']<worker['closed_ns'])
  facts['cells'].append({'cell':label,'anonymous_id':anon,'thread_id':con['thread_id'],'final_sha256':sha(final),'primary_classification':s['primary_classification'],'content_classification':s['final_content_classification'],'full_wall_ns':timing['full_cell_wall_ns'],'tools':len(attempts),'thin_exit':'unknown'})
 check('zip_member_denominator',zip_members==807);check('tools_events_denominator',total_tools==27 and total_events==54)
 check('fresh_threads',len(set(threads))==len(threads)==9);check('distinct_workers',len(set(workers))==9);check('distinct_runtimes',len(set(runtime_pids))==6);check('distinct_owners',len(set(owner_pids))==9);check('distinct_consumers',len(set(consumer_pids))==9)
 facts.update({'zip_members':zip_members,'business_attempts':total_tools,'public_tool_events':total_events,'actual_snapshots':18,'threads':9,'workers':9,'product_runtimes':6,'reused_old_full_matrix_files':2335})
 check('author_tree_unchanged',git('status','--porcelain=v1').decode()==status and git('rev-parse','HEAD').decode().strip()==head)

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception as e:checks.append({'check':'script_exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'check_count':len(checks),'input_count':len(inputs),'failed':[x for x in checks if not x['passed']],'facts':facts,'new_experiments':0}
 for name,data in [('RESULTS.json',result),('CHECKS.json',checks),('INPUTS.json',inputs)]: (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
