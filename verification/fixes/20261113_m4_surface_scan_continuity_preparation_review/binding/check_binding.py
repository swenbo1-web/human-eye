"""Bounded independent offline continuity source/lifecycle review."""
import datetime,hashlib,json,pathlib,subprocess,traceback
ROOT=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=ROOT/'verification/m4_surface_scan_continuity_001'
OUT=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuity_preparation_review/binding')
COMMIT='a206a96e51ca6293ea555f17960b964ba02f0606';PREP='1c96846cbbf948b80860a5366f5442407e1cbabd'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def check(n,v):checks.append({'check':n,'passed':bool(v)})
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(commit):
 out={}
 for x in git('ls-tree','-rz',commit).split(b'\0'):
  if x:m,n=x.split(b'\t',1);out[n.decode()]=m.split()[2].decode()
 return out
def norm(s):return {'unit_scale_m':s['unit_scale_m'],'objects':sorted([{k:o[k] for k in ['name','vertices_local','matrix_world','faces']} for o in s['objects']],key=lambda o:o['name'])}
def main():
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();check('fixed_head',head==COMMIT);check('clean_tree',status=='');dt=tree(COMMIT);pt=tree(PREP)
 manifest=j(B/'DELIVERY_MANIFEST.json');check('delivery_367_plus_manifest',manifest['file_count']==len(manifest['files'])==367)
 check('delivery_exact_files',{x['path'] for x in manifest['files']}=={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in p.parts})
 total=0
 for row in manifest['files']:
  p=B/row['path'];b=raw(p);total+=len(b);check('delivery_sha:'+row['path'],sha(b)==row['sha256'] and len(b)==row['bytes']);check('delivery_git:'+row['path'],blob(b)==dt[p.relative_to(ROOT).as_posix()])
 check('delivery_total_bytes',total==manifest['total_bytes']);check('delivery_manifest_git',blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[(B/'DELIVERY_MANIFEST.json').relative_to(ROOT).as_posix()])
 prep=j(B/'PREPARATION.json');ready=j(B/'DELIVERY_READY.json');reservation=j(B/'ENGINEERING_STARTED.json');check('frozen_commit',reservation['preparation_commit']==ready['preparation_commit']==PREP)
 check('prep_64_plus_manifest',len(prep['files'])==64)
 for item in prep['files']:
  p=B/item['path'];b=raw(p);check('prep_sha:'+item['path'],sha(b)==item['sha256'] and len(b)==item['bytes']);check('prep_git:'+item['path'],blob(b)==pt[p.relative_to(ROOT).as_posix()])
 check('prep_manifest_git',blob(raw(B/'PREPARATION.json'))==pt[(B/'PREPARATION.json').relative_to(ROOT).as_posix()]);check('prep_manifest_sha',sha(raw(B/'PREPARATION.json'))==ready['preparation_sha256'])
 check('external_input_count',len(prep['external_sha256'])==332)
 for p,digest in prep['external_sha256'].items():check('external:'+p,sha(raw(p))==digest)
 runner=raw(B/'engineering/run_episodes.py').decode();check('runner_freeze_before_reservation',runner.index("for record in frozen['files']")<runner.index("reservation = BATCH / 'ENGINEERING_STARTED.json'")<runner.index("for group in ('N', 'C')"))
 source=j(B/'inputs/C_READY.json');check('fixed_product_source',source['source_sha256']==prep['product_source_sha256']==ready['product_source_sha256'] and source['commit']==prep['product_commit']=='452b44d2dcf231d6675bef54e568db0431a29261')
 baseline={state:j(ROOT/f'verification/m4_surface_scan_001/qualification/{state}_SNAPSHOT.json') for state in ['BASE','EDIT']}
 allthin=[];facts['episodes']=[];overall=j(B/'ENGINEERING_RESULT.json')
 for group,turns in [('N',['BASE','REPEAT','EDIT']),('C',['BASE'])]:
  ep=B/'episodes'/group;result=j(ep/'RESULTS.json');timing=j(ep/'FINAL_TIMING.json');pub=j(ep/'TIMING_PUBLICATION.json');launch=j(ep/'ACTOR_LAUNCH.json');close=j(ep/'owner/CLOSE.json');finish=j(ep/'OWNER_FINISH.json');session=j(ep/'owner/native/SESSION.json');worker=j(ep/'owner/native/WORKER_CLOSED.json');continuity=j(ep/'owner/CONTINUITY.json');config=j(ep/'ACTOR_CONFIG.json')
  check(group+':actual_turns',[x['turn'] for x in result['business']]==turns and {p.name for p in ep.iterdir() if p.is_dir() and p.name in ['BASE','REPEAT','EDIT']}==set(turns))
  check(group+':qualification_denominator',result['execution_counts']==({'planned':3,'attempted':3,'completed':3,'failed':0,'not_run':0} if group=='N' else {'planned':3,'attempted':1,'completed':0,'failed':1,'not_run':2}))
  check(group+':not_retried',result['automatic_retries']==0 and result['model_calls']==result['API_calls']==0 and result['usage'] is None)
  start=result['started_ns'];deadline=result['deadline_ns'];end=timing['business_receipts_closed_ns']
  check(group+':original_590s',deadline-start==590_000_000_000 and timing['original_deadline_ns']==session['deadline_ns']==worker['original_deadline_ns']==launch['deadline_ns']==deadline)
  check(group+':full_write_close_timing',timing['started_ns']==start and timing['full_episode_wall_ns']==end-start and close['ended_ns']<=end<=deadline and timing['within_590s'] and timing['accepted_success']==(group=='N'))
  check(group+':publication_within_deadline',end<=pub['started_ns']<=pub['closed_ns']<deadline)
  check(group+':owner_parent_and_finish',launch['pid']==close['actor_parent_pid']==finish['actor_pid'] and finish['close']==close and finish['confirmed'] and finish['exit_code']==0)
  nc=close['native_close'];check(group+':worker_reaped',nc['pid']==session['pid']==worker['pid'] and nc['process_reaped'] and nc['exit_code']==0 and nc['error'] is None and nc['response']['status']=='closed')
  check(group+':terminal_state',close['confirmed'] and close['errors']==[] and close['active_turn'] is None and close['accepted_worker_geometry_matches'] and close['expected_terminal_geometry_matches'] and worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not worker['poisoned'])
  check(group+':close_turns',[x['turn_id'] for x in close['completed_turns']]==turns and close['completed_turns']==continuity['completed_turns'] and continuity['active_turn'] is None)
  check(group+':edit_scope',continuity['edit_attempted']==continuity['edit_verified']==close['registered_pose_applied']==worker['qa_patch_applied']==(group=='N'))
  check(group+':asset_unchanged',sha(raw(session['asset']))==prep['scene_sha256'] and raw(session['asset_copy'])==raw(session['asset']) and close['asset_unchanged'])
  check(group+':final_geometry',norm(j(ep/'owner/FINAL.json'))==norm(baseline['EDIT' if group=='N' else 'BASE']))
  check(group+':initial_geometry',norm(j(ep/'owner/INITIAL.json'))==norm(baseline['BASE']))
  for n,admin in enumerate(result['administrative'],1):
   check(group+f':admin_record:{n}',admin==j(ep/f'ADMIN_{n:02}.json'))
   check(group+f':admin_event:{n}',continuity['events'][n-1]['operation']==admin['request']['method'].split('/')[-1] and admin['started_ns']<=continuity['events'][n-1]['started_ns']<=continuity['events'][n-1]['ended_ns']<=admin['ended_ns'] and continuity['events'][n-1]['error'] is None)
  if group=='C':check('C_no_edit_admin',all(x['request']['method']!='continuity/qa_advance' for x in result['administrative']))
  states=[]
  for n,turn in enumerate(turns):
   row=j(ep/f'TURN_{turn}.json');thin=j(ep/turn/'THIN_TURN.json');check(group+':turn_record:'+turn,row==result['business'][n] and thin==row['thin']);allthin.append(thin['pid'])
   tx=[json.loads(x) for x in raw(ep/turn/'TX.bin').splitlines()];rx=[json.loads(x) for x in raw(ep/turn/'RX.bin').splitlines()]
   check(group+':thin_tx:'+turn,tx==thin['requests'] and [x['method'] for x in tx]==['initialize','notifications/initialized','tools/list','tools/call'] and tx[-1]==row['request'])
   check(group+':thin_rx:'+turn,rx==thin['responses'] and rx[-1]==row['response'] and not rx[-1]['result']['isError'])
   check(group+':thin_reaped:'+turn,thin['process_reaped'] and thin['exit_code']==0 and thin['confirmed'] and thin['error'] is None and thin['deadline_ns']==deadline and thin['process_exit_ns']<=thin['ended_ns']<=deadline)
   bridge=next((ep/turn/'attachments').glob('bridge_*'));exit=j(bridge/'EXIT.json');started=j(bridge/'STARTED.json');instances=thin['bridge_cleanup']['instances']
   check(group+':real_exit:'+turn,len(instances)==1 and instances[0]['exit']==exit and instances[0]['started']==started and exit['pid']==started['pid'] and exit['normal_exit'] and exit['backend_close_requested'] is False and exit['requests']==4 and thin['bridge_cleanup']['confirmed'])
   btx=brx=0
   for k,request in enumerate(tx,1):
    data=raw(bridge/f'{k:03}/TX.bin');btx+=len(data);check(group+f':attachment_tx:{turn}:{k}',json.loads(data)==request)
    f=bridge/f'{k:03}/RX.bin'
    if f.exists():data=raw(f);brx+=len(data);check(group+f':attachment_rx:{turn}:{k}',json.loads(data)==next(x for x in rx if x['id']==request['id']))
   check(group+':thin_bytes:'+turn,btx==exit['complete_tx_bytes'] and brx==exit['complete_rx_bytes'])
   check(group+':business_raw:'+turn,j(ep/f'owner/tool_{n+1:02}/REQUEST.json')==row['request'] and j(ep/f'owner/tool_{n+1:02}/RESPONSE.json')==row['response'])
   for statusrow in [row['status_before'],row['status_after']]:
    check(group+':persistent_owner:'+turn+str(statusrow['business_attempts']),statusrow['owner_pid']==close['actor_pid'] and statusrow['native_pid']==session['pid'] and statusrow['native_workspace']==session['workspace'] and statusrow['worker_deadline_ns']==deadline and statusrow['owner_close_called'] is False)
   check(group+':turn_end_before_qualification:'+turn,row['status_after']['active_turn'] is None and row['status_after']['completed_turns'][-1]['turn_id']==turn)
   if group=='N':
    outer=json.loads(row['response']['result']['content'][0]['text']);state=json.loads(outer['result']['result']);check('N_native_state_response:'+turn,state==row['native_state']);states.append(state)
    expected={o['name']:o['matrix_world'] for o in baseline['EDIT' if turn=='EDIT' else 'BASE']['objects']};check('N_matrices:'+turn,{o['name']:o['matrix_world'] for o in state['objects']}==expected)
   else:
    body=json.loads(row['response']['result']['content'][0]['text']);check('C_actual_scan',body==row['body'] and body['status']=='complete' and len(body['matches'])==71 and body['coverage']['objects']==24 and body['coverage']['total_pairs']==276 and body['coverage']['unknown']==body['coverage']['deferred']==0 and body['binding']['runtime_source_sha256']==prep['product_source_sha256'])
  if group=='N':
   check('N_marker_namespace_retained',len({(x['marker_token'],x['marker_generation'],x['pid'],x['namespace_id']) for x in states})==1 and states[0]['pid']==session['pid'])
   check('N_all_object_identities_retained',all([(o['name'],o['session_uid']) for o in x['objects']]==[(o['name'],o['session_uid']) for o in states[0]['objects']] for x in states))
   check('N_registered_edit_preserved',close['geometry_unchanged'] is False and worker['initial_geometry_fingerprint']!=worker['accepted_geometry_fingerprint'])
  else:
   check('C_failure_retained',result['errors'][0]['type']=='AssertionError' and 'actual geometry or source fields differ' in result['errors'][0]['message'] and result['passed_before_publication'] is False and result['business'][0]['errors'])
   check('C_notrun_no_artifacts',not (ep/'REPEAT').exists() and not (ep/'EDIT').exists() and not (ep/'TURN_REPEAT.json').exists() and not (ep/'TURN_EDIT.json').exists())
   check('C_no_mutation_or_active_state',close['geometry_unchanged'] and worker['initial_geometry_fingerprint']==worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not continuity['edit_attempted'])
   proof=j(ep/'owner/PRODUCT_RUNTIME_PROOF.json');pc=j(ep/'owner/plugin/CLOSE.json');ps=j(ep/'owner/plugin/START.json');rid=j(ep/'owner/IDENTITY.json')['runtime_identity']
   check('C_actual_runtime_source',rid['source_sha256']==prep['product_source_sha256'] and rid['source_file_count']==138 and ps['command'][3]==source['entry'])
   check('C_product_ancestry',proof['confirmed'] and proof['parent_chain'][0]['pid']==proof['runtime_pid'] and proof['parent_chain'][0]['parent_pid']==proof['launcher_pid']==ps['launcher_pid'])
   check('C_product_reaped',close['plugin_close']==pc and pc['process_reaped'] and pc['exit_code']==0 and close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0 and pc['ended_ns']<=close['product_runtime_exit']['observed_ns']<worker['closed_ns'])
   audit=[json.loads(x) for x in raw(ep/'owner/audit.jsonl').splitlines()];obs=[x for x in audit if x['event']=='observe'];check('C_one_cold_scan',len(obs)==1 and obs[0]['task_work']['kernel_calls']==112 and obs[0]['task_work']['measurement_cache_before']['measurement_entries']==0 and obs[0]['task_work']['measurement_cache_after']['measurement_entries']==112)
   prep_time=datetime.datetime.fromisoformat(git('show','-s','--format=%cI',PREP).decode().strip()).timestamp();runtime_epoch=(proof['runtime_created_filetime']-116444736000000000)/10000000
   # Broad temporal bound: C runtime was created before proof; its creation plus
   # monotonic deltas puts engineering reservation after the frozen commit.
   conservative_reservation_epoch=runtime_epoch-(proof['proved_ns']-reservation['started_ns'])/1e9
   check('preparation_predates_run_time_bound',prep_time<conservative_reservation_epoch)
   facts['preparation_time_check']={'commit_unix':prep_time,'earliest_reservation_estimate_unix':conservative_reservation_epoch,'method':'Windows runtime creation time minus upper-bound monotonic reservation-to-proof interval'}
  facts['episodes'].append({'group':group,'counts':result['execution_counts'],'accepted_success':timing['accepted_success'],'closed':close['confirmed'],'full_wall_ns':timing['full_episode_wall_ns'],'active_turn':close['active_turn'],'edit_applied':close['registered_pose_applied']})
 check('four_distinct_thin_processes',len(allthin)==len(set(allthin))==4)
 check('overall_failure_kept',overall['passed'] is False and overall['planned_episodes']==overall['started_episodes']==2 and ready['frozen_qualification_counts']=={'completed':3,'failed':1,'not_run':2})
 check('fixed_author_tree_unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts['fresh_C_rerun_state_blocker']=False;facts['new_C_run_preconditions']=['freeze minimal preparation contract fix','new owned episode/output/session; never reuse old C','retain original C failed and two not-run records','C BASE/REPEAT/EDIT and final independent readback must all pass before consumer experiment']

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception as error:checks.append({'check':'review_script_exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'check_count':len(checks),'input_count':len(inputs),'failed':[x for x in checks if not x['passed']],'facts':facts,'new_Blender_product_model_API_runs':0}
 for name,obj in [('RESULTS.json',result),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]: (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='facts'},ensure_ascii=False,indent=2))
