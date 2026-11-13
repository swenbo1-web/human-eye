"""Independent FIX2 source/three-turn ordering/EDIT/closure audit; offline only."""
import ast,datetime,hashlib,json,pathlib,subprocess,traceback
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuity_001_fix2'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuity_fix2_review/binding')
D='56caf228f6d0224f36796606c7f27b3c24223768';P='1511af696b564a0b261b70d5f0562325daa1f2a7';OLD='1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5'
SOURCE='4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
checks=[];inputs={};facts={}
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines()]
def ck(n,v,detail=None):checks.append({'check':n,'passed':bool(v),**({'detail':detail} if detail is not None else {})})
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(c):
 d={}
 for row in git('ls-tree','-rz',c).split(b'\0'):
  if row:m,p=row.split(b'\t',1);d[p.decode()]=m.split()[2].decode()
 return d
def norm(d):return {'unit_scale_m':d['unit_scale_m'],'objects':sorted([{k:o[k] for k in ('name','vertices_local','faces','matrix_world')} for o in d['objects']],key=lambda o:o['name'])}
def main():
 head=git('rev-parse','HEAD').decode().strip();status=git('status','--porcelain=v1').decode();ck('fixed clean delivery',head==D and status=='')
 dt,pt=tree(D),tree(P);rel=B.relative_to(R).as_posix();manifest=j(B/'DELIVERY_MANIFEST.json');prep=j(B/'PREPARATION.json');ready=j(B/'DELIVERY_READY.json');reservation=j(B/'ENGINEERING_STARTED.json')
 ck('282 content plus manifest exact file set',manifest['file_count']==len(manifest['files'])==282 and {x['path'] for x in manifest['files']}=={p.relative_to(B).as_posix() for p in B.rglob('*') if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in p.parts})
 bad=[];size=0
 for row in manifest['files']:
  b=raw(B/row['path']);size+=len(b)
  if sha(b)!=row['sha256'] or len(b)!=row['bytes'] or blob(b)!=dt.get(rel+'/'+row['path']):bad.append(row['path'])
 ck('all delivery bytes/hash/Git',not bad,bad);ck('delivery total and manifest',size==manifest['total_bytes'] and blob(raw(B/'DELIVERY_MANIFEST.json'))==dt[rel+'/DELIVERY_MANIFEST.json'])
 bad=[]
 for row in prep['files']:
  b=raw(B/row['path'])
  if sha(b)!=row['sha256'] or len(b)!=row['bytes'] or blob(b)!=pt.get(rel+'/'+row['path']):bad.append(row['path'])
 ck('58 preparation content plus manifest',len(prep['files'])==58 and not bad,bad);ck('preparation manifest identity',blob(raw(B/'PREPARATION.json'))==pt[rel+'/PREPARATION.json'] and sha(raw(B/'PREPARATION.json'))==ready['preparation_sha256'])
 bad=[]
 for p,h in prep['external_sha256'].items():
  if sha(raw(p))!=h:bad.append(p)
 ck('369 external fixed bytes',len(prep['external_sha256'])==369 and not bad,bad)
 ck('prep/reuse/reservation fixed',ready['preparation_commit']==reservation['preparation_commit']==manifest['preparation_commit']==P and prep['preparation_parent_commit']==OLD and j(B/'REUSE.json')['external_sha256']==prep['external_sha256'])
 preserved=['verification/m4_surface_scan_continuity_001','verification/m4_surface_scan_continuity_001_fix1','human_eye_plugin','human_eye_module1_operators']
 ck('prior evidence/source unchanged',git('diff','--name-only',OLD,D,'--',*preserved)==b'')
 runner=raw(B/'engineering/run_candidate.py').decode();module=ast.parse(runner);run=next(x for x in module.body if isinstance(x,ast.FunctionDef) and x.name=='run_episode')
 calls=[x for x in ast.walk(run) if isinstance(x,ast.Call)];finishcalls=[x for x in calls if ast.unparse(x.func)=='driver.finish'];qcalls=[x for x in calls if ast.unparse(x.func)=='qualify_after_finish']
 # The nested admin() has a separate local row and its own ended_ns write.
 # Count only business-loop writes, not that independent admin receipt.
 turnloop=next(x for x in ast.walk(run) if isinstance(x,ast.For) and ast.unparse(x.target)=='turn')
 endwrites=[x for x in ast.walk(turnloop) if isinstance(x,ast.Assign) and any(ast.unparse(t)=="row['ended_ns']" for t in x.targets)]
 ck('sole finish then qualification call',len(finishcalls)==len(qcalls)==1 and finishcalls[0].lineno<qcalls[0].lineno and len(endwrites)==1)
 ck('fixed reader/actor/transport path references',"qualification = load('_fix2_fixed_qualification', FIX1 / 'qualification/verify_continuity.py')" in runner and "str(FIX1 / 'runtime/actor.py')" in runner and "transport = load('_fix2_fixed_transport', FIX1 / 'runtime/consumer_transport.py')" in runner)
 ck('prep checked before exclusive reservation',runner.index('    validate_preparation(frozen)')<runner.index("with (BATCH / 'ENGINEERING_STARTED.json').open('x'"))
 ep=B/'episodes/C';res=j(ep/'RESULTS.json');tim=j(ep/'FINAL_TIMING.json');pub=j(ep/'TIMING_PUBLICATION.json');overall=j(B/'ENGINEERING_RESULT.json');close=j(ep/'owner/CLOSE.json');finish=j(ep/'OWNER_FINISH.json');cont=j(ep/'owner/CONTINUITY.json');session=j(ep/'owner/native/SESSION.json');worker=j(ep/'owner/native/WORKER_CLOSED.json');launch=j(ep/'ACTOR_LAUNCH.json');cfg=j(ep/'ACTOR_CONFIG.json');pcfg=j(ep/'owner/product_config.json');source=j(B/'inputs/C_READY.json')
 ck('one actual C no N/model/retries',reservation['groups']==['C'] and {p.name for p in (B/'episodes').iterdir() if p.is_dir()}=={'C'} and overall['planned_episodes']==overall['started_episodes']==1 and overall['N_episodes']==res['model_calls']==res['API_calls']==res['automatic_retries']==0 and res['usage'] is None)
 ck('three actual execution records',res['execution_counts']==ready['execution_counts']=={'planned':3,'attempted':3,'successful_returns':3,'succeeded':3,'failed':0,'not_run':0} and [x['turn'] for x in res['business']]==['BASE','REPEAT','EDIT'])
 ck('qualification denominator separate',res['qualification_counts']==ready['qualification_counts']=={'planned':3,'passed':3,'failed':0,'unverified':0} and res['sequence_qualification_state']=='passed' and res['qualification_errors']==res['errors']==res['publication_errors']==[])
 deadline=res['deadline_ns'];ck('590s original deadline retained',deadline-res['started_ns']==590*10**9 and deadline==cfg['worker_deadline_ns']==session['deadline_ns']==worker['original_deadline_ns']==launch['deadline_ns']==tim['original_deadline_ns'])
 ck('30s tool bound and exact argv',prep['tool_seconds']==pcfg['request_budget_s']==pcfg['blender']['timeout_s']==30 and pathlib.Path(launch['argv'][5])==R/'verification/m4_surface_scan_continuity_001_fix1/runtime/actor.py')
 events=lines(ep/'owner/native/WORKER_EVENTS.jsonl');wire=j(ep/'owner/native/WIRE/INDEX.json');ck('nine actual host operations',len(events)==len(wire)==9 and [x['sequence'] for x in events]==[x['sequence'] for x in wire]==list(range(1,10)))
 rawresponses={};requesttypes=[]
 for n,item in enumerate(wire,1):
  qb=raw(ep/f'owner/native/WIRE/{n:03}/REQUEST.bin');ab=raw(ep/f'owner/native/WIRE/{n:03}/RESPONSE.bin');q,a=json.loads(qb),json.loads(ab);rawresponses[n]=a;requesttypes.append(q['type'])
  ck(f'host {n} raw wire complete',len(qb)==item['request_bytes'] and len(ab)==item['response_attempted_bytes'] and len(qb)+len(ab)==item['request_response_attempted_bytes'] and item['response_sendall_completed'])
  if q['type']=='execute_code':
   code=q['params']['code'];stdout=a['result']['result'];ck(f'host {n} exact written call',raw(ep/f'owner/native/call_{n}/SCRIPT.py')==code.replace('\n','\r\n').encode() and raw(ep/f'owner/native/call_{n}/stdout.txt')==stdout.replace('\n','\r\n').encode() and raw(ep/f'owner/native/call_{n}/stderr.txt')==b'' and sha(code.encode())==events[n-1]['script_sha256'] and events[n-1]['status']=='completed' and events[n-1]['terminal_geometry_and_file_checks_passed'])
 ck('one EDIT and sole close in real wire',requesttypes==['execute_code','execute_code','execute_code','execute_code','qa_advance','execute_code','execute_code','execute_code','close'])
 ck('close unknown event classified from original response',events[-1]['status']=='unknown' and rawresponses[9]['status']=='closed' and rawresponses[9]['pid']==session['pid'])
 pids=[];turnfacts=[];previous_end=res['started_ns'];lastqual=res['qualification_started_ns']
 for n,turn in enumerate(['BASE','REPEAT','EDIT'],1):
  row=j(ep/f'TURN_{turn}.json');thin=j(ep/turn/'THIN_TURN.json');tx=lines(ep/turn/'TX.bin');rx=lines(ep/turn/'RX.bin');pids.append(thin['pid'])
  ck(turn+' original turn exact',row==res['business'][n-1] and row['thin']==thin and row['execution_state']=='succeeded' and row['qualification_state']=='passed' and row['errors']==row['qualification_errors']==[])
  ck(turn+' original four requests/three responses',tx==thin['requests'] and [x['method'] for x in tx]==['initialize','notifications/initialized','tools/list','tools/call'] and tx[-1]==row['request'] and rx==thin['responses'] and rx[-1]==row['response'] and not rx[-1]['result']['isError'])
  ck(turn+' exact owner business',j(ep/f'owner/tool_{n:02}/REQUEST.json')==row['request'] and j(ep/f'owner/tool_{n:02}/RESPONSE.json')==row['response'])
  ck(turn+' independent thin closure',thin['confirmed'] and thin['process_reaped'] and thin['exit_code']==0 and thin['error'] is None and pathlib.Path(thin['argv'][5])==R/'verification/native_plugin_complex_003/reused/stdio_attach.py')
  bridges=list((ep/turn/'attachments').glob('bridge_*'));ck(turn+' one bridge',len(bridges)==1);bridge=bridges[0];ex=j(bridge/'EXIT.json');bs=j(bridge/'STARTED.json')
  ck(turn+' original bridge EXIT',ex==thin['bridge_cleanup']['instances'][0]['exit'] and bs==thin['bridge_cleanup']['instances'][0]['started'] and ex['pid']==bs['pid'] and ex['normal_exit'] and not ex['backend_close_requested'] and ex['requests']==4 and thin['bridge_cleanup']['confirmed'])
  txsize=rxsize=0
  for k,q in enumerate(tx,1):
   qb=raw(bridge/f'{k:03}/TX.bin');txsize+=len(qb);ck(f'{turn} bridge request{k}',json.loads(qb)==q)
   f=bridge/f'{k:03}/RX.bin'
   if f.exists():ab=raw(f);rxsize+=len(ab);ck(f'{turn} bridge response{k}',json.loads(ab)==next(x for x in rx if x['id']==q['id']))
  ck(turn+' bridge byte totals',txsize==ex['complete_tx_bytes'] and rxsize==ex['complete_rx_bytes'])
  ck(turn+' original business before qualification',previous_end<row['started_ns']<=thin['started_ns']<thin['process_exit_ns']<=thin['ended_ns']<=row['ended_ns']<res['qualification_started_ns']<=lastqual<=row['qualification_started_ns']<=row['qualification_ended_ns']<deadline)
  previous_end=row['ended_ns'];lastqual=row['qualification_ended_ns']
  inwindow=[x for x in events if row['started_ns']<=x['started_ns']<=row['ended_ns']];expected_seq=[2,3,7][n-1]
  ck(turn+' entire sole capture in original window',len(inwindow)==1 and inwindow[0]['sequence']==expected_seq and inwindow[0]['started_ns']+inwindow[0]['elapsed_ns']<=row['ended_ns'])
  identity=res['initial_status'];ik=['episode_id','owner_pid','native_pid','native_host','native_port','native_workspace','product_launcher_pid','product_runtime_proof','session_id','worker_deadline_ns']
  ck(turn+' continuous backend/session and ended turn',all(all(s[k]==identity[k] for k in ik) and not s['owner_close_called'] for s in [row['status_before'],row['status_after']]) and row['status_after']['active_turn'] is None and row['status_after']['completed_turns'][-1]['turn_id']==turn)
  body=json.loads(row['response']['result']['content'][0]['text']);ck(turn+' response source and complete status',body==row['body'] and body['status']=='complete' and len(body['matches'])==[71,71,72][n-1] and body['coverage']['unknown']==body['coverage']['deferred']==0 and body['binding']['runtime_source_sha256']==SOURCE)
  turnfacts.append({'turn':turn,'host_sequence':expected_seq,'started_ns':row['started_ns'],'ended_ns':row['ended_ns'],'thin_wall_ns':thin['wall_ns'],'qualification_started_ns':row['qualification_started_ns'],'qualification_ended_ns':row['qualification_ended_ns']})
 ck('three distinct thin processes one owner',len(set(pids))==3 and close['tool_attempts']==3 and len(close['tools'])==3 and all(x['elapsed_ns']<30*10**9 for x in close['tools']))
 ck('all twelve admin records',len(res['administrative'])==len(cont['events'])==12)
 for n,a in enumerate(res['administrative'],1):
  e=cont['events'][n-1];ck(f'admin {n} original window',a==j(ep/f'ADMIN_{n:02}.json') and e['operation']==a['request']['method'].split('/')[-1] and a['started_ns']<=e['started_ns']<=e['ended_ns']<=a['ended_ns'] and e['error'] is None)
 edits=[x for x in cont['events'] if x['operation']=='qa_advance'];editadmin=[x for x in res['administrative'] if x['request']['method']=='continuity/qa_advance']
 ck('one online EDIT between REPEAT and EDIT windows',len(edits)==len(editadmin)==1 and res['business'][1]['ended_ns']<edits[0]['started_ns']<events[4]['started_ns']<events[5]['started_ns']<edits[0]['ended_ns']<res['business'][2]['started_ns'])
 ck('admin EDIT response exact',editadmin[0]['response']['result']==res['registered_pose'] and res['registered_pose']['advance']['response']==rawresponses[5])
 base=j(R/'verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json');edited=j(R/'verification/m4_surface_scan_001/qualification/EDIT_SNAPSHOT.json')
 initial=j(ep/'owner/INITIAL.json');preedit=j(ep/'owner/PRE_EDIT.json');editsnap=j(ep/'owner/EDIT.json');final=j(ep/'owner/FINAL.json')
 ck('BASE and pre-EDIT complete geometry',norm(initial)==norm(preedit)==norm(base))
 ck('EDIT and final complete geometry',norm(editsnap)==norm(final)==norm(res['registered_pose']['snapshot'])==norm(edited))
 for seq,snapshot in [(1,initial),(4,preedit),(6,editsnap),(8,final)]:ck(f'readback {seq} raw response matches snapshot',json.loads(rawresponses[seq]['result']['result'])==snapshot)
 before={o['name']:o for o in norm(initial)['objects']};after={o['name']:o for o in norm(editsnap)['objects']};changes=[n for n in before if before[n]!=after[n]]
 ck('only registered Obj_008 changed',changes==['Obj_008'] and before['Obj_008']['vertices_local']==after['Obj_008']['vertices_local'] and before['Obj_008']['faces']==after['Obj_008']['faces'] and events[4]['target_name']=='Obj_008' and events[4]['patch_sha256']==session['qa_pose_patch']['sha256'])
 ck('EDIT accepted state preserved',cont['edit_attempted'] and cont['edit_verified'] and worker['qa_patch_applied'] and close['registered_pose_applied'] and worker['initial_geometry_fingerprint']!=worker['accepted_geometry_fingerprint']==worker['final_geometry_fingerprint'] and not worker['poisoned'] and close['accepted_worker_geometry_matches'] and close['expected_terminal_geometry_matches'])
 ck('all finished turns no unknown active action',[x['turn_id'] for x in cont['completed_turns']]==['BASE','REPEAT','EDIT'] and cont['completed_turns']==close['completed_turns'] and close['active_turn'] is cont['active_turn'] is None and close['errors']==[])
 nc=close['native_close'];pc=j(ep/'owner/plugin/CLOSE.json');ps=j(ep/'owner/plugin/START.json');proof=j(ep/'owner/PRODUCT_RUNTIME_PROOF.json');ident=j(ep/'owner/IDENTITY.json')
 ck('actor sole finish confirmed',finish['close']==close and finish['confirmed'] and finish['exit_code']==0 and finish['actor_pid']==launch['pid']==close['actor_parent_pid'] and close['confirmed'])
 ck('Blender and product actual processes closed',nc['pid']==session['pid']==worker['pid'] and nc['process_reaped'] and nc['exit_code']==0 and nc['error'] is None and pc==close['plugin_close'] and pc['process_reaped'] and pc['exit_code']==0 and close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0)
 ck('runtime identity and proof',ident['runtime_identity']['source_sha256']==prep['product_source_sha256']==source['source_sha256']==SOURCE and ident['runtime_identity']['source_file_count']==138 and proof['confirmed'] and proof['runtime_pid']==proof['parent_chain'][0]['pid'] and proof['launcher_pid']==ps['launcher_pid']==proof['parent_chain'][0]['parent_pid'] and pathlib.Path(ps['command'][3])==pathlib.Path(source['entry']))
 ck('proof proper phase',proof['before_stdin'] is False and proof['initial_QA_completed_ns']<=proof['metadata_completed_ns']<=proof['observed_ns']<=proof['proved_ns']<res['business'][0]['started_ns'])
 ck('soleclose before all qualification',res['business'][-1]['ended_ns']<events[7]['started_ns']<pc['ended_ns']<=close['product_runtime_exit']['observed_ns']<events[8]['started_ns']<worker['closed_ns']<=close['ended_ns']<res['qualification_started_ns']<=res['business'][0]['qualification_started_ns'])
 ck('qualification and publish included in full timing',lastqual<=res['sequence_qualification_started_ns']<=res['sequence_qualification_ended_ns']<=res['qualification_ended_ns']<=tim['business_receipts_closed_ns']<=pub['started_ns']<=pub['closed_ns']<deadline and res['stages_ns']['qualification']==res['qualification_ended_ns']-res['qualification_started_ns'])
 ck('complete 5.0941225 second boundary',tim['full_episode_wall_ns']==tim['business_receipts_closed_ns']-res['started_ns']==5094122500 and tim['accepted_success'] and overall['passed'] and tim['publication_errors']==[])
 ck('source asset unchanged',raw(session['asset'])==raw(session['asset_copy']) and sha(raw(session['asset']))==prep['scene_sha256'] and nc['source_file_unchanged'] and nc['protected_files_unchanged'])
 first=[x for x in lines(ep/'owner/audit.jsonl') if x['event']=='observe'][0];ck('first capture cold',first['task_work']['measurement_cache_before']['measurement_entries']==0 and events[1]['m2_work']['before']==[] and ident['private_geometry_warmup'] is False)
 epoch=datetime.datetime.fromisoformat(git('show','-s','--format=%cI',P).decode().strip()).timestamp();runtime_epoch=(proof['runtime_created_filetime']-116444736000000000)/10**7;earliest=runtime_epoch-(proof['proved_ns']-reservation['started_ns'])/10**9
 ck('preparation before actual launch',epoch<earliest);ck('author HEAD/tree unchanged',git('rev-parse','HEAD').decode().strip()==head and git('status','--porcelain=v1').decode()==status)
 facts.update(delivery_files=283,preparation_files=59,external_files=369,real_C_episodes=1,new_N_episodes=0,real_business=3,edit_count=1,finish_count=1,execution_counts=res['execution_counts'],qualification_counts=res['qualification_counts'],full_episode_wall_ns=5094122500,qualification_ns=res['stages_ns']['qualification'],turns=turnfacts,AL_own_assignment_current=False,AL_own_write=611,AL_parent_write=624,source_or_unknown_action_blocker=False,freeze_time_margin_seconds=earliest-epoch)
 facts['not_claimed']=['No independent replay of exact geometric truth here; another root task covers facts.','Engineering wall time is not model task benefit. No model resume/usage/cost observed.','Buffered write/close is measured; report fsync and all preparation/review/coordination time are unmeasured.','Missing rich source metadata retained; generic close event unknown is resolved by original closed response/reap.']
 facts['next']='Proceed to fixed fair N/C continuous model consumption contract; no new unmotivated engineering/preparation round.'

if __name__=='__main__':
 O.mkdir(parents=True,exist_ok=True)
 try:main()
 except Exception:checks.append({'check':'independent script exception','passed':False,'traceback':traceback.format_exc()})
 value={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'input_paths':len(inputs),'failed':[x for x in checks if not x['passed']],'facts':facts,'new_product_Blender_model_API_runs':0}
 for name,obj in [('RESULTS.json',value),('CHECKS.json',checks),('INPUT_HASHES.json',inputs)]: (O/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in value.items() if k!='facts'},ensure_ascii=False,indent=2))
