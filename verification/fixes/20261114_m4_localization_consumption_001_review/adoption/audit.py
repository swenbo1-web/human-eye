"""Independent read-only protocol/adoption/lifecycle audit; no product imports."""
from pathlib import Path
import collections,hashlib,json,tomllib
R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_region_localization_consumption_001'
E=Path('D:/he_loc_001'); O=Path(__file__).parent
checks=[]; inputs={}; used_archive=set()
def ck(n,v):checks.append({'name':n,'passed':bool(v)})
archive=json.loads((H/'EXTERNAL_ARCHIVE.json').read_bytes())
mapping={str(Path(r['original_path'])):r for r in archive['files']}
def raw(p):
 p=Path(p); b=p.read_bytes(); s=hashlib.sha256(b).hexdigest(); inputs[str(p)]=s
 if str(p) in mapping and str(p) not in used_archive:
  row=mapping[str(p)]; a=R/row['archive_path']; ab=a.read_bytes();inputs[str(a)]=hashlib.sha256(ab).hexdigest()
  ck('archive:'+str(p),b==ab and s==row['sha256'] and len(b)==row['bytes']);used_archive.add(str(p))
 return b
def js(p):return json.loads(raw(p))
def events(p):return [json.loads(x) for x in raw(p).splitlines() if x.strip()]
prompt=raw(H/'inputs/PROMPT.txt');promptsha=hashlib.sha256(prompt).hexdigest()
ck('prompt_frozen',promptsha=='3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a')
plan=js(H/'PLAN.json'); sequence=[x['slot'] for x in plan['sequence']]
ck('sequence',sequence==['N1','P1','P2','N2','N3','P3'])
common={'execute_python','scene_data','render_views','read_images'}
slots=[];threadids=[];tooltotal=0;errors=[];schemas={};p_list_hash=[]
for slot in sequence:
 p=E/'formal'/slot; c=p/'c'; owner=p/'o'; group=slot[0]
 result=js(p/'RESULT.json'); consumer=js(c/'CONSUMER.json'); observations=js(owner/'OBSERVATIONS.json')
 metrics=js(owner/'METRICS.json'); schema=js(owner/'TOOLS_SCHEMA.json');schemas[slot]=schema
 wanted=common|({'active_observation'} if group=='P' else set())
 ck(slot+':schema_set',{x['name'] for x in schema}==wanted)
 argv=consumer['argv']; config=tomllib.loads('\n'.join(argv[i+1] for i,x in enumerate(argv) if x=='-c'))
 mc=config['mcp_servers']['arm_engine'];ck(slot+':approval_names',set(mc['tools'])==wanted)
 ck(slot+':approval_values',all(x=={'approval_mode':'approve'} for x in mc['tools'].values()))
 ck(slot+':one_turn_fresh',consumer['turn_index']==1 and consumer['expected_thread_id'] is None and 'resume' not in argv)
 ck(slot+':hooks_intentionally_off',config['features']['hooks'] is False)
 ck(slot+':isolation','--ignore-user-config' in argv and '--ignore-rules' in argv and config['features']['shell_tool'] is False)
 ck(slot+':prompt_same',consumer['input_sha256']==promptsha)
 ck(slot+':deadline_preserved',result['deadline_ns']-result['started_ns']==450_000_000_000 and consumer['deadline_ns']==result['deadline_ns'])
 transcript=events(c/'stdout.raw.bin')
 threads=[x['thread_id'] for x in transcript if x['type']=='thread.started'];threadids.extend(threads)
 ck(slot+':one_real_thread',threads==[consumer['thread_id']]==[result['observed_thread_id']])
 ck(slot+':normal_terminal',sum(x['type']=='turn.completed' for x in transcript)==1 and not any(x['type']=='turn.failed' for x in transcript))
 calls=[x['item'] for x in transcript if x['type']=='item.completed' and x.get('item',{}).get('type')=='mcp_tool_call']
 starts=[x['item'] for x in transcript if x['type']=='item.started' and x.get('item',{}).get('type')=='mcp_tool_call']
 ck(slot+':start_complete_bound',[x['id'] for x in starts]==[x['id'] for x in calls])
 ck(slot+':consumer_calls',calls==[x['item'] for x in consumer['tool_calls']])
 attachments=list((c/'attachments').glob('bridge_*'));ck(slot+':one_stdio',len(attachments)==1)
 io_records=[]; listrows=[]
 for file in sorted(attachments[0].glob('*/TX.bin')):
  tx=js(file); rxpath=file.with_name('RX.bin'); rx=js(rxpath) if rxpath.exists() else None
  io_records.append((file,tx,rx))
  if tx.get('method')=='tools/list':listrows.append((file,rx))
 ck(slot+':actual_tools_list_one',len(listrows)==1)
 listfile,listresult=listrows[0]
 ck(slot+':actual_tools_list_exact',listresult['result']['tools']==schema)
 if group=='P':p_list_hash.append(hashlib.sha256(raw(listfile.with_name('RX.bin'))).hexdigest())
 wirecalls=[r for r in io_records if r[1].get('method')=='tools/call']
 ck(slot+':wire_call_count',len(wirecalls)==len(calls)==result['actual_tool_calls']==metrics['tool_attempts'])
 for i,(cli,(file,tx,rx)) in enumerate(zip(calls,wirecalls),1):
  req=js(owner/f'tool_{i:02d}'/'REQUEST.json');res=js(owner/f'tool_{i:02d}'/'RESPONSE.json');receipt=js(owner/f'tool_{i:02d}'/'RECEIPT.json')
  ck(f'{slot}:wire_request:{i}',tx==req)
  ck(f'{slot}:wire_response:{i}',rx==res)
  ck(f'{slot}:call_request:{i}',cli['server']=='arm_engine' and cli['tool']==req['params']['name'] and cli['arguments']==req['params']['arguments'])
  ck(f'{slot}:call_content:{i}',cli['result']['content']==res['result']['content'] and cli['error'] is None)
  expected='failed' if res['result']['isError'] else 'completed'
  ck(f'{slot}:call_state:{i}',cli['status']==expected and receipt['is_error']==res['result']['isError'])
  ck(f'{slot}:current_thread:{i}',req['params']['_meta']['threadId']==threads[0])
  if expected=='failed': errors.append({'slot':slot,'index':i,'tool':cli['tool'],'later_success':any(x['status']=='completed' for x in calls[i:])})
  ck(f'{slot}:registered_tool:{i}',cli['tool'] in wanted)
 tooltotal+=len(calls)
 ck(slot+':no_active_tool',not any(x['tool']=='active_observation' for x in calls))
 ck(slot+':no_product_observation',observations['active']==[] and observations['replays']==[] and metrics['common']['product_observation_calls']==0 and metrics['common']['capture_replay_calls']==0)
 ck(slot+':no_product_call_audit',not observations['audit']['forbidden_product_calls'])
 ck(slot+':six_actual_rasters',len(observations['render_attempts'])==6 and result['new_renders']==6)
 binding=js(c/'RUNTIME_BINDING.json');ck(slot+':runtime_bound',binding['confirmed'] and binding['runtime_pid']==binding['stdio_STARTED']['pid'] and binding['launcher_pid']==result['consumer_pid'])
 for key in ['consumer_process_cleanup','owner_process_cleanup']:
  cleanup=result[key];ck(slot+':'+key,cleanup['confirmed'] and cleanup['exit_code']==0 and cleanup['process_handle_closed'] and not cleanup['errors'] and all(cleanup['pipes_closed'].values()))
 close=js(owner/'CLOSE.json');ck(slot+':actor_close',close['confirmed'] and close['server_thread_stopped'] and not close['errors'])
 ex=result['runtime_exit'];ck(slot+':thin_exit',ex['confirmed'] and ex['exited'] and ex['exit_code']==1 and ex['handle_closed'] and ex['error'] is None)
 ck(slot+':EOF_explicit_unknown',result['bridge_cleanup']['receipt_status']=='unknown' and result['bridge_cleanup']['missing_exit_count']==1)
 ck(slot+':completed_outer',result['outer_valid_completion'] and not result['stop_remaining_reasons'])
 ck(slot+':no_protocol_deviation',consumer['bridge_protocol_errors']==[] and consumer['unexpected_tool_deviations']==[] and consumer['provider_retry_observations']==[])
 messages=[x['item']['text'] for x in transcript if x['type']=='item.completed' and x.get('item',{}).get('type')=='agent_message']
 ck(slot+':final_binding',messages[-1]==consumer['final']==raw(c/'final.txt').decode())
 warnings=[x['item'].get('message') for x in transcript if x.get('item',{}).get('type')=='error']
 slots.append({'slot':slot,'thread':threads[0],'tools':collections.Counter(x['tool'] for x in calls),'approval_keys':sorted(mc['tools']),'schema_names':[x['name'] for x in schema],'first_public_message':messages[0],'warnings':warnings,'active_calls':0,'normal_EOF':'unknown','CLI_actor_exit':0,'thin_exit':1})
ck('six_distinct_threads',len(threadids)==len(set(threadids))==6)
ck('fifty_calls',tooltotal==50)
ck('two_recovered_business_errors',len(errors)==2 and all(x['later_success'] for x in errors))
ck('P_list_wire_sha_same',p_list_hash==['7f82345427e8c1d16485b786006814f400a70b81d9818c34ea415e0959c95901']*3)
for s in sequence:
 ck(s+':identical_common_schema',[x for x in schemas[s] if x['name']!='active_observation']==schemas['N1'])
prep=[]
for group in ['N','P']:
 p=E/'preparation'/f'{group}1'/f'LOCAL_{group}1';consumer=js(p/'c/CONSUMER.json');result=js(p/'RESULT.json');obs=js(p/'o/OBSERVATIONS.json');metrics=js(p/'o/METRICS.json')
 calls=[x['item'] for x in events(p/'c/stdout.raw.bin') if x['type']=='item.completed' and x.get('item',{}).get('type')=='mcp_tool_call']
 ck(group+':fake_three_calls',len(calls)==3)
 ck(group+':fake_recovery',calls[0]['status']=='failed' and calls[1]['status']=='completed' and '42' in json.dumps(calls[1]['result']))
 ck(group+':fake_last_success',calls[2]['status']=='completed')
 ck(group+':fake_EOF',result['runtime_exit']['exit_code']==0 and result['bridge_cleanup']['confirmed'] is True)
 if group=='P':
  ck('fakeP_actual_product',calls[2]['tool']=='active_observation' and len(obs['active'])==1 and len(obs['replays'])==1 and metrics['common']['product_observation_calls']==1)
  ck('fakeP_three_images',sum(x['type']=='image' for x in calls[2]['result']['content'])==3)
  ck('fakeP_same_schema',js(p/'o/TOOLS_SCHEMA.json')==schemas['P1'])
 prep.append({'group':group,'calls':[x['tool'] for x in calls],'real_model':False,'rasters':result['new_renders']})
for p,h in list(inputs.items()):ck('unchanged:'+p,hashlib.sha256(Path(p).read_bytes()).hexdigest()==h)
out={'passed':all(x['passed'] for x in checks),'checks':len(checks),'failures':[x for x in checks if not x['passed']],'slots':slots,'tool_count':tooltotal,'business_errors':errors,'preparation':prep,'source_bound_inputs':len(inputs),'new_product_model_Blender_raster_benchmark_calls':0,'conclusions':{'local_tools_list_and_approval':'verified','provider_internal_final_tool_definitions':'unobserved','formal_product_calls':0,'formal_product_consumption_examples':0,'automatic_hooks':'disabled by frozen common configuration; not tested','zero_adoption_cause':'not established','minimal_next_test':'one fresh real Pro explicit active_observation call and evidence-use qualification; no product rewrite or six-slot rerun'}}
O.mkdir(parents=True,exist_ok=True)
(O/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(O/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(O/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in out.items() if k not in ['slots']},ensure_ascii=False,indent=2))
