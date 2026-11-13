"""Independent bounded offline FIX1 source, original denominator and closure audit.
Never imports the product or author checkers; subprocess use is read-only Git.
"""
import datetime, hashlib, json, pathlib, subprocess, traceback
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuity_001_fix1'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuity_fix1_review/binding')
D='1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5'
P='e06597f92d1193b40e9a62b78919a3125e4e346d'
P0='8000b52fa333339a8e249051329982768c136d5d'
OLD='a206a96e51ca6293ea555f17960b964ba02f0606'
PRODUCT='452b44d2dcf231d6675bef54e568db0431a29261'
SOURCE='4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'sha256':sha(b),'bytes':len(b)};return b
def j(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines()]
def ck(n,v,detail=None):checks.append({'check':n,'passed':bool(v),**({'detail':detail} if detail is not None else {})})
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(c):
 out={}
 for row in git('ls-tree','-rz',c).split(b'\0'):
  if row:m,p=row.split(b'\t',1);out[p.decode()]=m.split()[2].decode()
 return out
def norm(d):return {'unit_scale_m':d['unit_scale_m'],'objects':sorted([{k:o[k] for k in ('name','vertices_local','faces','matrix_world')} for o in d['objects']],key=lambda o:o['name'])}
def main():
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode()
 ck('fixed clean delivery',head==D and status=='');dt,pt,zt,prod=map(tree,[D,P,P0,PRODUCT])
 manifest=j(B/'DELIVERY_MANIFEST.json');prep=j(B/'PREPARATION.json');ready=j(B/'DELIVERY_READY.json');start=j(B/'ENGINEERING_STARTED.json')
 rel=B.relative_to(R).as_posix();names={x['path'] for x in manifest['files']}
 actual={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in p.parts}
 ck('1313 members plus manifest',len(manifest['files'])==manifest['file_count']==1313 and names==actual)
 bad=[];size=0
 for row in manifest['files']:
  p=B/row['path'];b=raw(p);size+=len(b)
  if sha(b)!=row['sha256'] or len(b)!=row['bytes'] or blob(b)!=dt.get(p.relative_to(R).as_posix()):bad.append(row['path'])
 ck('all 1313 delivery member bytes/hash/Git',not bad,bad);ck('delivery size and manifest Git',size==manifest['total_bytes'] and blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 bad=[]
 for row in prep['files']:
  b=raw(B/row['path'])
  if sha(b)!=row['sha256'] or len(b)!=row['bytes'] or blob(b)!=pt.get(rel+'/'+row['path']):bad.append(row['path'])
 ck('1189 preparation content plus manifest',len(prep['files'])==1189 and not bad,bad)
 ck('preparation manifest fixed Git/hash',blob(raw(B/'PREPARATION.json'))==pt[rel+'/PREPARATION.json'] and sha(raw(B/'PREPARATION.json'))==ready['preparation_sha256'])
 bad=[]
 for path,h in prep['external_sha256'].items():
  if sha(raw(path))!=h:bad.append(path)
 ck('362 external input hashes unchanged',len(prep['external_sha256'])==362 and not bad,bad)
 ck('final freeze identity',start['preparation_commit']==ready['fixed_preparation_commit']==manifest['preparation_commit']==P and prep['preparation_parent_commit']==P0)
 oldprep=raw(B/'preparation_repair/attempt_01/PREPARATION_BEFORE.json');failure=j(B/'preparation_repair/attempt_01/FAILURE.json')
 ck('first preparation original retained',blob(oldprep)==zt[rel+'/PREPARATION.json'])
 oldrunner=git('show',P0+':'+rel+'/engineering/run_candidate.py').decode();runner=raw(B/'engineering/run_candidate.py').decode()
 ck('initial wrong path before reservation',"HEAD:verification/m4_surface_scan_continuity_001/PREPARATION.json" in oldrunner and oldrunner.index('HEAD:verification/m4_surface_scan_continuity_001/PREPARATION.json')<oldrunner.index("reservation = BATCH / 'ENGINEERING_STARTED.json'"))
 wrong=git('show',P0+':verification/m4_surface_scan_continuity_001/PREPARATION.json')
 ck('initial wrong path actually mismatches',wrong!=oldprep)
 ck('prelaunch failure not a live run',failure['preparation_commit']==P0 and not failure['ENGINEERING_STARTED_exists'] and not failure['episodes_directory_exists'] and failure['new_Blender_model_API_calls']==0)
 ck('final runner checks prior to exclusive reservation',runner.index("for record in frozen['files']")<runner.index("reservation = BATCH / 'ENGINEERING_STARTED.json'")<runner.index("row = run_episode('C'"))
 ck('only one fresh C selected',start['groups']==['C'] and start['maximum_episodes']==1 and {p.name for p in (B/'episodes').iterdir() if p.is_dir()}=={'C'})
 ck('old001 committed evidence unchanged',git('diff','--name-only',OLD,D,'--','verification/m4_surface_scan_continuity_001')==b'')
 old_manifest=R/'verification/m4_surface_scan_continuity_001/DELIVERY_MANIFEST.json'
 ck('old manifest reuses prior seal',blob(raw(old_manifest))==tree(OLD)[old_manifest.relative_to(R).as_posix()])
 actor=raw(B/'runtime/actor.py');old_actor=raw(R/'verification/m4_surface_scan_continuity_001/runtime/actor.py')
 ck('actor unchanged from accepted continuity prep',actor==old_actor and sha(actor)==prep['actor_sha256']==ready['actor_sha256'])
 source=j(B/'inputs/C_READY.json');binding=j(pathlib.Path(source['release'])/'admin/RUNTIME_BINDING.json')
 ck('fixed product/source',source['commit']==prep['product_commit']==PRODUCT and source['source_sha256']==prep['product_source_sha256']==SOURCE)
 bad=[]
 for row in binding['source_files']:
  b=raw(pathlib.Path(source['install_root'])/row['path'])
  if sha(b)!=row['sha256'] or blob(b)!=prod.get(row['path']):bad.append(row['path'])
 ck('138 installed source byte/Git identity reused',len(binding['source_files'])==138 and not bad,bad)
 ck('fixed entry and binding',sha(raw(source['entry']))==source['launcher_sha256'] and sha(raw(pathlib.Path(source['release'])/'admin/RUNTIME_BINDING.json'))==source['binding_sha256'])
 ep=B/'episodes/C';res=j(ep/'RESULTS.json');timing=j(ep/'FINAL_TIMING.json');pub=j(ep/'TIMING_PUBLICATION.json');overall=j(B/'ENGINEERING_RESULT.json')
 close=j(ep/'owner/CLOSE.json');finish=j(ep/'OWNER_FINISH.json');session=j(ep/'owner/native/SESSION.json');worker=j(ep/'owner/native/WORKER_CLOSED.json');cont=j(ep/'owner/CONTINUITY.json');launch=j(ep/'ACTOR_LAUNCH.json');cfg=j(ep/'ACTOR_CONFIG.json');pcfg=j(ep/'owner/product_config.json')
 ck('original failure denominator',res['execution_counts']==ready['frozen_counts']=={'planned':3,'attempted':1,'completed':0,'failed':1,'not_run':2} and len(res['business'])==1)
 ck('no repeat/edit artifacts',not any((ep/p).exists() for p in ['REPEAT','EDIT','TURN_REPEAT.json','TURN_EDIT.json']))
 ck('no retries/model/API',res['automatic_retries']==res['model_calls']==res['API_calls']==overall['model_calls']==overall['API_calls']==0 and res['usage'] is None)
 ck('overall failure retained',overall['started_episodes']==overall['planned_episodes']==1 and overall['N_episodes']==0 and not overall['passed'] and not res['passed_before_publication'] and not timing['accepted_success'])
 ck('original exception retained',res['errors'][0]['type']=='FileNotFoundError' and 'WIRE' in res['errors'][0]['message'] and 'INDEX.json' in res['errors'][0]['message'])
 row=j(ep/'TURN_BASE.json');thin=j(ep/'BASE/THIN_TURN.json');tx=lines(ep/'BASE/TX.bin');rx=lines(ep/'BASE/RX.bin')
 ck('actual record agrees',row==res['business'][0] and row['thin']==thin and row['turn']==row['state']=='BASE' and row['errors'][0]==res['errors'][0])
 ck('all four thin requests exact',tx==thin['requests'] and [x['method'] for x in tx]==['initialize','notifications/initialized','tools/list','tools/call'] and tx[-1]==row['request'])
 ck('all three thin responses exact',rx==thin['responses'] and rx[-1]==row['response'] and not row['response']['result']['isError'])
 body=json.loads(row['response']['result']['content'][0]['text'])
 ck('real BASE output with complete coverage',body==row['body'] and body['status']=='complete' and len(body['matches'])==71 and body['coverage']['objects']==24 and body['coverage']['total_pairs']==276 and body['coverage']['unknown']==body['coverage']['deferred']==0 and body['binding']['runtime_source_sha256']==SOURCE)
 ck('single owner business exact',j(ep/'owner/tool_01/REQUEST.json')==row['request'] and j(ep/'owner/tool_01/RESPONSE.json')==row['response'] and close['tool_attempts']==1 and len(close['tools'])==1)
 ck('thin exit actual',thin['process_reaped'] and thin['exit_code']==0 and thin['confirmed'] and thin['error'] is None)
 bridges=list((ep/'BASE/attachments').glob('bridge_*'));ck('one thin attachment',len(bridges)==1);bridge=bridges[0];exit=j(bridge/'EXIT.json');bs=j(bridge/'STARTED.json');bc=thin['bridge_cleanup']
 ck('real EXIT evidence',len(bc['instances'])==1 and bc['instances'][0]['exit']==exit and bc['instances'][0]['started']==bs and exit['pid']==bs['pid'] and exit['normal_exit'] and exit['backend_close_requested'] is False and exit['requests']==4 and bc['confirmed'])
 txsize=rxsize=0
 for n,request in enumerate(tx,1):
  data=raw(bridge/f'{n:03}/TX.bin');txsize+=len(data);ck(f'bridge original TX {n}',json.loads(data)==request)
  f=bridge/f'{n:03}/RX.bin'
  if f.exists():data=raw(f);rxsize+=len(data);ck(f'bridge original RX {n}',json.loads(data)==next(x for x in rx if x['id']==request['id']))
 ck('bridge wire bytes',txsize==exit['complete_tx_bytes'] and rxsize==exit['complete_rx_bytes'])
 deadline=res['deadline_ns'];ck('590s unchanged deadline',deadline-res['started_ns']==590*10**9 and deadline==thin['deadline_ns']==session['deadline_ns']==worker['original_deadline_ns']==launch['deadline_ns']==cfg['worker_deadline_ns']==timing['original_deadline_ns'])
 ck('30s tool bound configured',prep['tool_seconds']==pcfg['request_budget_s']==pcfg['blender']['timeout_s']==30 and close['tools'][0]['elapsed_ns']<30*10**9)
 ck('actual actor and thin loaded pinned files',pathlib.Path(launch['argv'][5])==B/'runtime/actor.py' and pathlib.Path(thin['argv'][5])==R/'verification/native_plugin_complex_003/reused/stdio_attach.py')
 ck('owner stayed live through end_turn',all(x['owner_pid']==close['actor_pid'] and x['native_pid']==session['pid'] and x['worker_deadline_ns']==deadline and not x['owner_close_called'] for x in [row['status_before'],row['status_after']]) and row['status_after']['active_turn'] is None)
 ck('four admin actions only',len(res['administrative'])==len(cont['events'])==4 and [x['operation'] for x in cont['events']]==['status','status','begin_turn','end_turn'])
 for n,a in enumerate(res['administrative'],1):
  e=cont['events'][n-1];ck(f'admin original/order {n}',a==j(ep/f'ADMIN_{n:02}.json') and a['started_ns']<=e['started_ns']<=e['ended_ns']<=a['ended_ns'] and e['error'] is None)
 ck('no edit or active turn',not cont['edit_attempted'] and not cont['edit_verified'] and not close['registered_pose_applied'] and not worker['qa_patch_applied'] and cont['active_turn'] is close['active_turn'] is None)
 base=j(R/'verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json')
 ck('initial/final complete geometry equal BASE',norm(j(ep/'owner/INITIAL.json'))==norm(j(ep/'owner/FINAL.json'))==norm(base))
 ck('unchanged accepted terminal state',close['geometry_unchanged'] and close['expected_terminal_geometry_matches'] and close['accepted_worker_geometry_matches'] and worker['initial_geometry_fingerprint']==worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not worker['poisoned'])
 ck('source asset unchanged',sha(raw(session['asset']))==prep['scene_sha256'] and raw(session['asset_copy'])==raw(session['asset']) and close['asset_unchanged'])
 nc=close['native_close'];ck('Blender closed/reaped',nc['pid']==session['pid']==worker['pid'] and nc['process_reaped'] and nc['exit_code']==0 and nc['error'] is None and nc['response']['status']=='closed' and nc['source_file_unchanged'] and nc['protected_files_unchanged'])
 ck('actor closed/reaped',finish['close']==close and finish['confirmed'] and finish['exit_code']==0 and finish['actor_pid']==launch['pid']==close['actor_parent_pid'] and close['errors']==[] and close['confirmed'])
 proof=j(ep/'owner/PRODUCT_RUNTIME_PROOF.json');ps=j(ep/'owner/plugin/START.json');pc=j(ep/'owner/plugin/CLOSE.json');ident=j(ep/'owner/IDENTITY.json')
 ck('actual runtime identity',ident['runtime_identity']['source_sha256']==SOURCE and ident['runtime_identity']['source_file_count']==138 and pathlib.Path(ps['command'][3])==pathlib.Path(source['entry']))
 ck('runtime ancestry proof',proof['confirmed'] and proof['parent_chain'][0]['pid']==proof['runtime_pid'] and proof['parent_chain'][0]['parent_pid']==proof['launcher_pid']==ps['launcher_pid'])
 ck('runtime proof accurate phase',proof['before_stdin'] is False and proof['before_consumer_business'] and proof['initial_QA_completed_ns']<=proof['metadata_completed_ns']<=proof['observed_ns']<=proof['proved_ns']<row['started_ns'])
 ck('product launcher/runtime separately closed',pc==close['plugin_close'] and pc['process_reaped'] and pc['exit_code']==0 and close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0 and pc['ended_ns']<=close['product_runtime_exit']['observed_ns']<worker['closed_ns'])
 ck('all closure within original deadline',thin['process_exit_ns']<=thin['ended_ns']<worker['closed_ns']<=close['ended_ns']<=timing['business_receipts_closed_ns']<=pub['started_ns']<=pub['closed_ns']<deadline and timing['full_episode_wall_ns']==timing['business_receipts_closed_ns']-res['started_ns'])
 audit=lines(ep/'owner/audit.jsonl');obs=[x for x in audit if x['event']=='observe'];events=lines(ep/'owner/native/WORKER_EVENTS.jsonl')
 ck('one cold scan no hidden geometry prewarm',len(obs)==1 and obs[0]['task_work']['kernel_calls']==112 and obs[0]['task_work']['measurement_cache_before']['measurement_entries']==0 and obs[0]['task_work']['measurement_cache_after']['measurement_entries']==112 and events[1]['m2_work']['before']==[] and not ident['private_geometry_warmup'])
 helper=R/'verification/m4_surface_scan_001_opt1/engineering/pose_native_metered.py';helperraw=raw(helper);ck('actual helper unchanged',sha(helperraw)==session['helper_sha256'])
 wire=j(ep/'owner/native/WIRE/INDEX.json');ck('four host operations and originals',len(wire)==len(events)==4 and [x['sequence'] for x in wire]==[1,2,3,4])
 for n,record in enumerate(wire,1):
  req=raw(ep/f'owner/native/WIRE/{n:03}/REQUEST.bin');resp=raw(ep/f'owner/native/WIRE/{n:03}/RESPONSE.bin')
  ck(f'host wire original {n}',len(req)==record['request_bytes'] and len(resp)==record['response_attempted_bytes'] and record['response_sendall_completed'])
  request,response=json.loads(req),json.loads(resp)
  if n<4:
   script=raw(ep/f'owner/native/call_{n}/SCRIPT.py');stdout=raw(ep/f'owner/native/call_{n}/stdout.txt');stderr=raw(ep/f'owner/native/call_{n}/stderr.txt')
   ck(f'host completed call {n}',request['type']=='execute_code' and script.decode()==request['params']['code'] and sha(script)==events[n-1]['script_sha256'] and stdout.decode()==response['result']['result'] and events[n-1]['status']=='completed' and events[n-1]['terminal_geometry_and_file_checks_passed'] and not stderr)
  else:ck('generic unknown is close event not unknown action',request=={'type':'close'} and response['status']=='closed' and response['pid']==worker['pid'] and events[n-1]['status']=='unknown')
 helpertext=helperraw.decode();ck('WIRE published at terminal flush',helpertext.index('meter.flush(workspace)')<helpertext.index("save(workspace/'WORKER_CLOSED.json',closed)") and helpertext.count('meter.flush(workspace)')==1)
 ck('original qualification still terminal-WIRE dependent', 'index = json.loads((wire / "INDEX.json").read_bytes())' in raw(B/'qualification/verify_continuity.py').decode() and ready['phase_candidate_applied'] is False)
 prep_epoch=datetime.datetime.fromisoformat(git('show','-s','--format=%cI',P).decode().strip()).timestamp();runtime_epoch=(proof['runtime_created_filetime']-116444736000000000)/10**7
 earliest=runtime_epoch-(proof['proved_ns']-start['started_ns'])/10**9
 ck('freeze commit precedes actual reserved run',prep_epoch<earliest)
 ck('review leaves author head/tree unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(delivery_files=1314,preparation_files=1190,external_files=362,original_counts=res['execution_counts'],full_episode_wall_ns=timing['full_episode_wall_ns'],prep_to_earliest_reservation_seconds=earliest-prep_epoch,closure_confirmed=close['confirmed'],edit_applied=False,unknown_action=False,generic_close_event_unknown_retained=True,new_C_state_blocker=False,AL_own_assignment_current=False,AL_own_write=611,AL_parent_write=622)
 facts['limitations']=['Prelaunch failure 0-live claim additionally relies on authored failure receipt plus deterministic pre-reservation path mismatch; not an independent historical process trace.','No C REPEAT/EDIT or consumer model semantics verified by this failed batch.','Missing rich source metadata stays unrecorded; terminal geometry equality does not prove absence of transient reverted mutations.','Postclose WIRE and postrun candidate must not upgrade original failed episode.','Author 4008 checks are not this audit denominator.']
 facts['next']=['Apply/refreeze one phase-correct reader in new batch.','Exactly one fresh owned C engineering episode; no new N or model run.','Retain old C failed1/notrun2; require BASE/REPEAT/EDIT plus close on new episode.']

if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'review script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(c['passed'] for c in checks),'checks':len(checks),'input_paths':len(inputs),'failed':[c for c in checks if not c['passed']],'facts':facts,'new_product_Blender_model_API_runs':0}
 for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]: (O/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
