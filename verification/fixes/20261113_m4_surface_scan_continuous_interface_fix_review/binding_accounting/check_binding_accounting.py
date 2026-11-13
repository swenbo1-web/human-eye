"""Offline independent source/archive preservation and original failure ledger audit."""
import hashlib,io,json,pathlib,subprocess,traceback,zipfile
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuous_interface_fix_001'
OLD=R/'verification/m4_surface_scan_continuous_consumption_001'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_interface_fix_review/binding_accounting')
D='b51dc02eb4f25966f983033b42dad3c9cfec9393';P='1adbf71062f5821dbd6b15c9138c58bc05355a45';BASE='11f944e71bc530822e8741384732529003efc29f'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def ck(n,v):checks.append({'check':n,'passed':bool(v)})
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(c):
 d={}
 for x in git('ls-tree','-rz',c).split(b'\0'):
  if x:m,n=x.split(b'\t',1);d[n.decode()]=m.split()[2].decode()
 return d
def compact(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def main():
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();ck('fixed clean delivery',head==D and status=='');dt,pt,ot=tree(D),tree(P),tree(BASE);rel=B.relative_to(R).as_posix()
 manifest=j(B/'DELIVERY_MANIFEST.json');prep=j(B/'PREPARATION.json');names={x['path'] for x in manifest['files']};gitnames={n[len(rel)+1:] for n in dt if n.startswith(rel+'/')}
 ck('48 tracked delivery files exactly',len(names)==47 and gitnames==names|{'DELIVERY_MANIFEST.json'})
 bad=[]
 for x in manifest['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=dt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('47 delivery member size hash Git',not bad);ck('manifest Git',blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 bad=[]
 for x in prep['files']:
  b=raw(B/x['path'])
  if sha(b)!=x['sha256'] or len(b)!=x['bytes'] or blob(b)!=pt.get(rel+'/'+x['path']):bad.append(x['path'])
 ck('44 preparation members plus PREPARATION',len(prep['files'])==44 and not bad and blob(raw(B/'PREPARATION.json'))==pt[rel+'/PREPARATION.json'])
 ck('fixed preparation commit',manifest['preparation_commit']==P and prep['parent_commit']==BASE)
 ck('520 external dependencies unchanged',len(prep['external_sha256'])==520 and all(sha(raw(path))==h for path,h in prep['external_sha256'].items()))
 protected=['verification/m4_surface_scan_continuous_consumption_001','verification/m4_surface_scan_continuity_001_fix1','verification/m4_surface_scan_continuity_001_fix2','human_eye_plugin','human_eye_module1_operators']
 ck('old batch and reused source directories unchanged',git('diff','--name-only',BASE,D,'--',*protected)==b'')
 oldmanifest=j(OLD/'DELIVERY_MANIFEST.json');oldrel=OLD.relative_to(R).as_posix();bad=[]
 for x in oldmanifest['files']:
  b=raw(OLD/x['path'])
  if len(b)!=x['bytes'] or sha(b)!=x['sha256'] or blob(b)!=ot[oldrel+'/'+x['path']]:bad.append(x['path'])
 ck('old 144 members plus manifest unchanged',len(oldmanifest['files'])==144 and not bad and blob(raw(OLD/'DELIVERY_MANIFEST.json'))==ot[oldrel+'/DELIVERY_MANIFEST.json'])
 archives=[];total=0
 for name in ['replay/RUN_01_MANIFEST.json']+[f'integration/offline/a{i:02}_MANIFEST.json' for i in range(1,5)]:
  m=j(B/name);ab=raw(m['archive']);z=zipfile.ZipFile(io.BytesIO(ab));root=pathlib.Path(m.get('raw_directory',m.get('run_folder')));members=z.namelist();total+=len(members)
  ck(name+' ZIP hash and complete names',sha(ab)==m['archive_sha256'] and len(members)==len(set(members)) and set(members)==set(m['members'])=={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} and not any(n.startswith('/') or '\\' in n or '..' in pathlib.Path(n).parts for n in members))
  ck(name+' each archived byte matches retained local',all({'bytes':len(z.read(n)),'sha256':sha(z.read(n))}==m['members'][n] and z.read(n)==raw(root/n) for n in members))
  archives.append({'manifest':name,'members':len(members),'archive_sha256':sha(ab)})
 ck('five archives 2400 members',len(archives)==5 and total==2400)
 summary=j(B/'integration/RESULTS.json');fake_count=thin_count=0;historical=[]
 for n in range(1,5):
  a=f'a{n:02}';m=j(B/f'integration/offline/{a}_MANIFEST.json');p=pathlib.Path(m['raw_directory']);result=j(B/f'integration/offline/{a}_RESULT.json');metadata=summary['attempts'][n-1]
  ck(a+' original and shallow results identical',raw(p/'RESULT.json')==raw(B/f'integration/offline/{a}_RESULT.json') and sha(raw(B/f'integration/offline/{a}_RESULT.json'))==metadata['shallow_result_sha256'] and sha(raw(B/f'integration/offline/{a}_MANIFEST.json'))==metadata['manifest_sha256'])
  ck(a+' preserved four expected cases',result['tests']==4 and result['failures']==result['errors']==0 and result['passed'] and len(result['cases'])==4 and {k:sum(c['counts'][k] for c in result['cases']) for k in ['completed','failed','not_run']}=={'completed':10,'failed':1,'not_run':1})
  consumers=[j(f) for f in p.rglob('CONSUMER.json')];exits=[j(f) for f in p.rglob('EXIT.json') if '/attachments/bridge_' in f.as_posix()];starts=[j(f) for f in p.rglob('STARTED.json') if '/attachments/bridge_' in f.as_posix()]
  ck(a+' eleven actual fixture consumers and thin closes',len(consumers)==len(exits)==len(starts)==11 and all(c['process_reaped'] and c['readers_stopped'] and c['exit_code']==0 for c in consumers) and all(x['normal_exit'] and x['backend_close_requested'] is False for x in exits) and {x['pid'] for x in starts}=={x['pid'] for x in exits})
  fake_count+=len(consumers);thin_count+=len(starts)
  if n>1:ck(a+' source before after equal',result['source_sha256_before']==result['source_sha256_after'] and result['sources_unchanged_during_replay'])
  else:ck('a01 only postrun source claim retained','source_sha256' in result and 'source_sha256_before' not in result and metadata['sources_unchanged_during_replay'] is None)
  if n>=3:
   sz=zipfile.ZipFile(io.BytesIO(raw(p/'SOURCES.zip')));recorded=result['source_sha256_before'];ck(a+' retained per-attempt source ZIP hashes',len(sz.namelist())==len(recorded)==12 and all(sha(sz.read(pathlib.Path(path).relative_to(R).as_posix()))==h for path,h in recorded.items()))
  if n==4:ck('a04 final source equals recorded snapshot',all(sha(raw(path))==h for path,h in result['source_sha256_before'].items()))
  historical.append({'attempt':a,'fixture_cases':4,'actual_fake_CLI':len(consumers),'actual_thin_clients':len(starts),'original_main_exit_code':metadata['original_main_exit_code']})
 failure=j(B/'integration/offline/a03_ARCHIVE_FAILURE.json')
 ck('a03 test-pass archive-failure distinction retained',failure['main_exit_code']==1 and failure['exception_type']=='FileNotFoundError' and failure['stage']=='archive_run' and summary['attempts'][2]['original_main_exit_code']==1 and summary['attempts'][3]['original_main_exit_code']==0)
 ck('no hidden formal sample in preparation totals',fake_count==thin_count==44 and summary['preparation_totals']=={'attempts':4,'fixture_cases':16,'fake_CLI_processes':44,'thin_client_processes':44,'fixture_processes_combined':88,'formal_samples':0})
 ledger=j(B/'accounting/LEDGER.json');sealraw=raw(B/'inputs/QUALITY_SEAL.json');seal=json.loads(sealraw);run=j(OLD/'RUN_RESULT.json')
 ck('quality sealed before original failure accounting',sha(sealraw)==ledger['quality_seal_sha256']=='7f90243826c1a113d0365282517899902cc9aa2f1b163b67c43d6c644d2a51c6' and seal['delivery_commit']==ledger['delivery_commit']==BASE and seal['decision'].startswith('Content quality sealed; strict failures retained.'))
 ck('ledger six failures twelve notrun no actual resume',len(ledger['rows'])==6 and ledger['planned_turns']==18 and ledger['actual_failed_first_turns']==6 and ledger['not_run_turns']==12 and ledger['actual_resume_turns']==0 and run['execution_counts']=={'planned':18,'completed':0,'failed':6,'not_run':12})
 source_checks=ledger['source_integrity'];ck('ledger all declared input hashes',all({'bytes':len(raw(path)),'sha256':sha(raw(path))}==m for path,m in source_checks['sources'].items()))
 ck('old manifest ledger reference exact',source_checks['root_reviewed_old_delivery_manifest_sha256']==sha(raw(OLD/'DELIVERY_MANIFEST.json')) and source_checks['old_delivery_files_including_manifest_bound']==145 and source_checks['old_delivery_manifest_entries_checked']==144)
 total_attempts=0;rows=[]
 for lr,outer in zip(ledger['rows'],run['records']):
  cell=outer['cell'];rt=pathlib.Path(outer['runtime_folder']);ep=pathlib.Path(outer['folder']);m=j(ep/'RUNTIME_MANIFEST.json');z=zipfile.ZipFile(io.BytesIO(raw(ep/'ORIGINALS.zip')))
  def original(path):
   b=raw(path);name=pathlib.Path(path).relative_to(rt).as_posix();ck(cell+' archive source '+name,z.read(name)==b and m['members'][name]=={'bytes':len(b),'sha256':sha(b)});return json.loads(b)
  con=original(rt/'c/turns/BASE/CONSUMER.json');tt=original(rt/'c/turns/BASE/FINAL_TIMING.json');eventraw=raw(rt/'c/turns/BASE/events.jsonl');ck(cell+' raw event archive exact',z.read('c/turns/BASE/events.jsonl')==eventraw);events=[json.loads(line)['event'] for line in eventraw.splitlines()];tools=original(rt/'owner/TOOLS.json');otime=j(ep/'FINAL_TIMING.json')
  ck(cell+' outer/turn boundaries from original integers',otime==outer['timing'] and lr['outer_wall_ns']==otime['full_episode_wall_ns']==otime['business_receipts_closed_ns']-otime['started_ns'] and lr['turn_wall_ns']==tt['full_turn_wall_ns']==tt['consumer_record_closed_ns']-tt['started_ns'] and otime['started_ns']<=tt['started_ns']<=con['prompt_submitted_ns']<=con['final_received_ns']<=tt['consumer_record_closed_ns']<=otime['business_receipts_closed_ns'])
  ck(cell+' nested prompt interval and scope exact',lr['prompt_to_final_ns']==con['prompt_to_final_ns']==con['final_received_ns']-con['prompt_submitted_ns'] and lr['outer_timing_scope']==otime['scope'] and lr['turn_timing_scope']==tt['scope'])
  ck(cell+' original execution failures unchanged',not otime['outer_valid_completion'] and not tt['accepted_success'] and not con['valid_completion'] and con['status']=='failed' and lr['execution_state']=='failed' and con['expected_thread_id'] is None and 'resume' not in con['frozen_cli_argv'])
  actualusage=[e['usage'] for e in events if e.get('type')=='turn.completed'];ck(cell+' every raw usage key/value retained',len(actualusage)==1 and actualusage==lr['raw_turn_completed_usage']==con['raw_usage_events']==con['usage_rows'] and all(type(v) is int and v>=0 for v in actualusage[0].values()))
  ck(cell+' fees provider and usage unknown not estimated',lr['provider_requests']==con['provider_requests'] and lr['fees']==con['fees'] and lr['usage_scope']=='unknown' and lr['usage_aggregation'] is None)
  attempts=[];response_sum=0
  for n,t in enumerate(tools['tools'],1):
   a=original(rt/f'owner/tool_{n:02}/ATTEMPT.json');response=original(rt/f'owner/tool_{n:02}/RESPONSE.json');ck(cell+f' attempt {n} original and encoded response bytes',a==t and a['attempt']==n and a['response_bytes']==a['produced_response_bytes']==len(compact(response)) and a['elapsed_ns']>0)
   attempts.append({k:a[k] for k in ['attempt','name','elapsed_ns','response_bytes','produced_response_bytes','is_error']});response_sum+=a['response_bytes']
  completed=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
  ck(cell+' all attempts and byte total ledger exact',lr['tool_attempt_records']==attempts and lr['tool_attempts']==tools['attempts']==len(attempts)==len(completed) and lr['wire_tool_bytes']==tools['wire_tool_bytes']==response_sum);total_attempts+=len(attempts)
  judgments=[x for x in seal['judgments'] if x['episode_id']==outer['anonymous_episode_id'] and x['turn_index']==1];ck(cell+' sealed quality provenance only',lr['cell']==cell and lr['anonymous_episode_id']==outer['anonymous_episode_id'] and len(judgments)==1 and lr['sealed_primary_content']==judgments[0]['primary_content_classification']=='complete_correct')
  ck(cell+' unknown thin and owned close separate',lr['thin_EXIT_status']==con['bridge_cleanup']['receipt_status']=='unknown' and con['bridge_cleanup']['confirmed'] is None and lr['owner_close_confirmed']==outer['owner_finish']['confirmed'] is True)
  ck(cell+' notrun slots unestimated',[x['turn'] for x in lr['not_run']]==['REPEAT','EDIT'] and all(x['execution_state']=='not_run' and x['elapsed_ns'] is x['usage'] is None for x in lr['not_run']))
  rows.append({'cell':cell,'outer_wall_ns':lr['outer_wall_ns'],'turn_wall_ns':lr['turn_wall_ns'],'tool_attempts':len(attempts),'wire_tool_bytes':response_sum,'usage_fields_preserved':sorted(actualusage[0]),'source_bound':True})
 ck('all fourteen attempts bound',total_attempts==14)
 for entry in source_checks['archive_member_checks']:
  rt=pathlib.Path(next(x for x in run['records'] if x['cell']==entry['cell'])['runtime_folder']);b=raw(rt/entry['member']);ck('ledger declared member '+entry['cell']+':'+entry['member'],len(b)==entry['bytes'] and sha(b)==entry['sha256'])
 ck('shared cost unknown and no usage aggregation',ledger['usage_scope']=='unknown' and ledger['usage_aggregation'] is None and ledger['shared_costs']['status']=='unknown' and all(v is None for k,v in ledger['shared_costs'].items() if k not in ['status','scope']))
 ck('author tree/head unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(tracked_delivery_files=48,preparation_content_files=44,preparation_including_manifest=45,external_files=520,old_preserved_files=145,archives=archives,archive_members=2400,preparation_attempts=historical,old_failure_ledger_rows=rows,total_bound_tool_attempts=14,actual_model_resumes=0,formal_old_failed=6,formal_old_notrun=12,thin_EXIT_unknown=6,new_formal_samples=0,AL_assignment_current=False,AL_own_write=611,AL_parent_write=628)
 facts['limits']=['No author checker/process replay rerun; preserved evidence inspected offline.','a01 records source hashes after run only; a02 before/after; a03/a04 additionally retain source ZIP.','a03 command exit1 provenance is the retained author failure receipt referencing original conversation stderr, not a new independent historical process trace.','Times are nested original failed-batch intervals. Do not sum outer+turn+tool durations or declare continuous performance winner.','Raw usage retained; actual resume usage semantics, provider fees and shared end-to-end costs remain unknown.']

if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'independent audit script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(c['passed'] for c in checks),'checks':len(checks),'input_paths':len(inputs),'failed':[c for c in checks if not c['passed']],'facts':facts,'new_product_Blender_model_API_runs':0}
 for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]: (O/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
