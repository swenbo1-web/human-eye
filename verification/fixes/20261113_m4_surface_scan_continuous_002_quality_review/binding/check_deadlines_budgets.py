"""Offline direct original-deadline and budget check; no cost disclosure."""
import hashlib,json,pathlib,traceback
R=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_continuous_consumption_002'
O=pathlib.Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review/binding')
inputs={};checks=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def raw(p):
 p=pathlib.Path(p);b=p.read_bytes();inputs[str(p)]={'bytes':len(b),'sha256':sha(b)};return b
def j(p):return json.loads(raw(p))
def ck(name,ok):checks.append({'check':name,'passed':bool(ok)})
def wire(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def main():
 plan=j(B/'PLAN.json');run=j(B/'RUN_RESULT.json');formal=j(B/'FORMAL_STARTED.json')
 ck('frozen numeric limits',all(plan[k]==v for k,v in {'episode_seconds':590,'turn_seconds':450,'episode_tool_attempts':32,'episode_host_nonclose_requests':128,'episode_tool_response_bytes':1048576,'code_bytes':262144}.items()))
 for rec in run['records']:
  a=rec['anonymous_episode_id'];rt=pathlib.Path(rec['runtime_folder']);folder=pathlib.Path(rec['folder']);dead=rec['episode_deadline_ns'];start=rec['started_ns'];final=j(folder/'FINAL_TIMING.json');pub=j(folder/'TIMING_PUBLICATION.json');er=j(rt/'c/EPISODE_RESULT.json');ef=j(rt/'c/FINAL_TIMING.json');owner=j(rt/'owner/CLOSE.json');continuity=j(rt/'owner/CONTINUITY.json');session=j(rt/'owner/native/SESSION.json');worker=j(rt/'owner/native/WORKER_CLOSED.json');cfg=j(rt/'ACTOR_CONFIG.json');endpoint=j(rt/'ENDPOINT.json')
  ck(a+' full episode original deadline arithmetic',formal['started_ns']<=start and dead==start+590*10**9 and final==rec['timing'] and final['started_ns']==start and final['episode_deadline_ns']==dead and start<final['business_receipts_closed_ns']<dead and final['full_episode_wall_ns']==final['business_receipts_closed_ns']-start and final['publication_errors']==[] and final['business_receipts_closed_ns']<=pub['started_ns']<=pub['closed_ns']<dead)
  ck(a+' original deadline bound through all owners',cfg['worker_deadline_ns']==endpoint['chain_deadline_ns']==session['deadline_ns']==worker['original_deadline_ns']==owner['native_close']['original_deadline_ns']==er['episode_deadline_ns']==ef['episode_deadline_ns']==dead and owner['ended_ns']<dead and worker['closed_ns']<dead and er['cleanup_ended_ns']<=ef['business_receipts_closed_ns']<=final['business_receipts_closed_ns']<dead and ef['business_receipts_closed_ns']==rec['coordinator']['business_receipts_closed_ns'] and ef['started_ns']==er['started_ns'] and ef['full_episode_wall_ns']==ef['business_receipts_closed_ns']-ef['started_ns'])
  for i,t in enumerate(er['turns'],1):
   fp=pathlib.Path(t['folder']);con=j(fp/'CONSUMER.json');ft=j(fp/'FINAL_TIMING.json');ct=continuity['completed_turns'][i-1];td=t['deadline_ns']
   ck(a+f' turn{i} original absolute deadline and complete consumer close',td==con['deadline_ns']==ft['original_turn_deadline_ns']==ct['deadline_ns'] and ft['episode_deadline_ns']==dead and ft['started_ns']==con['started_ns'] and ct['started_ns']<=con['started_ns']<con['turn_completed_ns']<=con['cleanup_end_ns']<=ft['consumer_record_closed_ns']<=ct['ended_ns']<td<=dead and td<=ct['started_ns']+450*10**9 and ft['full_turn_wall_ns']==ft['consumer_record_closed_ns']-con['started_ns'] and con['deadline_timer_fired'] is False)
  ledger=j(rt/'owner/TOOLS.json');calls=sorted((rt/'owner').glob('tool_*'));numbers=sorted(int(x.name[5:]) for x in calls);rows=[];total=0;code_ok=True;call_ok=True
  for n in numbers:
   f=rt/f'owner/tool_{n:02}';row=j(f/'ATTEMPT.json');rows.append(row);req=j(f/'REQUEST.json');responses=[j(f/k) for k in ('RESPONSE.json','ERROR_RESPONSE.json') if (f/k).exists()];size=sum(len(wire(v)) for v in responses);total+=size;call_ok=call_ok and len(responses)==1 and row['attempt']==n and row['response_bytes']==size
   args=req.get('params',{}).get('arguments',{})
   if 'code' in args:code_ok=code_ok and isinstance(args['code'],str) and len(args['code'].encode())<=262144
  ck(a+' complete owner tools and cumulative response budget',numbers==list(range(1,len(numbers)+1)) and len(numbers)==ledger['attempts']==ledger['calls']==owner['tool_attempts']<=32 and rows==ledger['tools']==owner['tools'] and call_ok and total==ledger['wire_tool_bytes']<=1048576)
  host=[json.loads(x) for x in raw(rt/'owner/native/WORKER_EVENTS.jsonl').splitlines()];nonclose=host[:-1];terminal=host[-1];nativescripts=list((rt/'owner/native').glob('call_*/SCRIPT.py'));script_events=[x for x in host if 'script_sha256' in x];script_ok=code_ok and len(nativescripts)==len(script_events)
  for e in script_events:
   # Reverse only Windows text-mode LF expansion; SHA binds exact original logical code.
   logical=raw(rt/f"owner/native/call_{e['sequence']}/SCRIPT.py").replace(b'\r\n',b'\n');script_ok=script_ok and sha(logical)==e['script_sha256'] and len(logical)<=262144
  ck(a+' all host nonclose requests within fixed bound',session['max_calls']==128 and [e['sequence'] for e in host]==list(range(1,len(host)+1)) and len(nonclose)<=128 and terminal['status']=='unknown' and 'script_sha256' not in terminal and 'operation' not in terminal and owner['native_close']['response']['status']=='closed' and all('script_sha256' in e or e.get('operation')=='qa_advance' for e in nonclose))
  ck(a+' all tool and host code within 256KiB exact hashes',script_ok)
if __name__=='__main__':
 try:main()
 except Exception:checks.append({'check':'independent budget script exception','passed':False,'traceback':traceback.format_exc()})
 result={'all_passed':all(x['passed'] for x in checks),'checks':len(checks),'failed':[x for x in checks if not x['passed']],'scope':'6 episode and 18 turn original deadlines; 6 cumulative tools/host/response/code budgets. Numeric costs, timings and group mappings not emitted.','new_product_Blender_model_API_runs':0}
 for name,v in [('BUDGET_RESULTS.json',result),('BUDGET_CHECKS.json',checks),('BUDGET_INPUT_HASHES_PRIVATE.json',inputs)]: (O/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
