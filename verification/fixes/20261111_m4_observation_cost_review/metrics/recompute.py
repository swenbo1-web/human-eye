"""Independent raw-file recomputation; never imports product or author analysis."""
from pathlib import Path
import json, hashlib, statistics, collections, datetime
BASE=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001')
OUT=Path(__file__).resolve().parent
SOURCES={}
def blob(path):
 p=Path(path);raw=p.read_bytes();SOURCES[str(p)]=hashlib.sha256(raw).hexdigest();return raw
def read(path):return json.loads(blob(path))
def lines(path):return [json.loads(x) for x in blob(path).splitlines() if x.strip()]
def enc(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def stat(values):return {'sum':sum(values),'median':statistics.median(values),'min':min(values),'max':max(values),'n':len(values)}
run=read(BASE/'RUN_RESULT.json');plan=read(BASE/'PLAN.json');mapping=read(BASE/'private/ANON_MAP.json')['rows']
rows=[]
for rr in run['records']:
 cell=rr['cell'];folder=BASE/'cells'/cell;c=read(folder/'CONSUMER.json');t=read(folder/'owner/TOOLS.json');close=read(folder/'owner/CLOSE.json');finish=read(folder/'OWNER_FINISH.json');launch=read(folder/'ACTOR_LAUNCH.json');native=read(folder/'owner/native/SESSION.json')
 assert c==rr['consumer']
 assert rr['cell_ended_ns']-rr['cell_started_ns']==rr['full_cell_wall_ns']==c['total_task_wall_ns']
 assert c['cleanup_end_ns']-c['started_ns']==c['wall_ns']
 assert c['started_ns']-rr['cell_started_ns']==c['pre_consumer_setup_ns']
 assert c['deadline_ns']-c['started_ns']==450*10**9
 assert rr['worker_deadline_ns']-rr['cell_started_ns']==570*10**9
 assert launch['worker_deadline_ns']==native['deadline_ns']==rr['worker_deadline_ns']
 ev=lines(folder/'events.jsonl');completed=[e for e in ev if e['event']['type']=='turn.completed'];assert len(completed)==1
 usage=completed[0]['event']['usage'];assert all(usage[k]==v for k,v in c['usage'].items());assert c['usage_rows']==[c['usage']]
 usage=dict(c['usage']);assert 0<=usage['cached_input_tokens']<=usage['input_tokens'];assert 0<=usage['reasoning_output_tokens']<=usage['output_tokens']
 finals=[e for e in ev if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message'];assert finals[-1]['perf_ns']==c['final_received_ns'];assert finals[-1]['event']['item']['text']==c['final']
 tools=[e for e in ev if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call'];assert len(tools)==t['attempts']==len(t['tools'])
 owner=[]
 for td in sorted((folder/'owner').glob('tool_*')):
  req=read(td/'REQUEST.json');receipt=read(td/'ATTEMPT.json');response_path=td/('ERROR_RESPONSE.json' if (td/'ERROR_RESPONSE.json').exists() else 'RESPONSE.json');response=read(response_path)
  assert len(enc(response))==receipt['response_bytes']
  owner.append({'order':receipt['attempt'],'name':req['params']['name'],'request':req,'response':response,'receipt':receipt,'text_bytes':sum(len(x.get('text','').encode()) for x in response['result'].get('content',[]) if x['type']=='text')})
 assert sum(x['receipt']['response_bytes'] for x in owner)==t['wire_tool_bytes']
 public=[];bridge_missing=0
 for bridge in sorted((folder/'attachments').glob('bridge_*')):
  read(bridge/'STARTED.json');bridge_missing+=not (bridge/'EXIT.json').exists()
  if (bridge/'EXIT.json').exists():read(bridge/'EXIT.json')
  for fd in sorted(p for p in bridge.iterdir() if p.is_dir()):
   tx=blob(fd/'TX.bin');q=json.loads(tx);rx=blob(fd/'RX.bin') if (fd/'RX.bin').exists() else None
   row={'method':q.get('method'),'has_id':'id' in q,'tx_bytes':len(tx),'rx_bytes':len(rx) if rx is not None else 0,'error':None}
   if rx is not None:
    response=json.loads(rx);assert response.get('id')==q.get('id');row['error']=response.get('error')
    if q['method']=='tools/call':
     o=next(x for x in owner if x['request']['id']==q['id']);assert q==o['request'];assert rx==enc(o['response'])
   elif 'id' in q:raise AssertionError('missing id response')
   public.append(row)
 assert bridge_missing==c['bridge_cleanup']['missing_exit_count']
 workers=lines(folder/'owner/native/WORKER_EVENTS.jsonl');execs=[v for v in workers if 'script_sha256' in v];ends=[v for v in workers if 'sequence' in v and 'script_sha256' not in v]
 assert len(ends)==1 and ends[0]['sequence']==max(v['sequence'] for v in workers if 'sequence' in v)
 assert close['native_close']['response']['status']=='closed' and close['confirmed'] and finish['confirmed']
 scripts=sorted((folder/'owner/native').glob('call_*/SCRIPT.py'));assert len(scripts)==len(execs)
 private=[];product_rpc=None
 if (folder/'owner/plugin/RPC.json').exists():
  product_rpc=read(folder/'owner/plugin/RPC.json')
  for fd in sorted(p for p in (folder/'owner/plugin').iterdir() if p.is_dir()):
   tx=blob(fd/'TX.bin');q=json.loads(tx);rx=blob(fd/'RX.bin') if (fd/'RX.bin').exists() else None;rec=read(fd/'RECEIPT.json')
   assert len(tx)==rec['sent_bytes'];assert (0 if rx is None else len(rx))==rec['received_bytes']
   private.append({'method':q['method'],'has_id':'id' in q,'tx_bytes':len(tx),'rx_bytes':0 if rx is None else len(rx),'elapsed_ns':rec['elapsed_ns'],'error':rec['error']})
  assert sum(x['tx_bytes'] for x in private)==product_rpc['tx_bytes'];assert sum(x['rx_bytes'] for x in private)==product_rpc['rx_bytes']
 warnings=blob(folder/'stderr.raw.bin').decode('utf8',errors='replace').splitlines()
 timing={'full_cell_s':rr['full_cell_wall_ns']/1e9,'consumer_wall_s':c['wall_ns']/1e9,'setup_s':c['pre_consumer_setup_ns']/1e9,'post_consumer_owner_close_tail_s':(rr['cell_ended_ns']-c['cleanup_end_ns'])/1e9,'owner_finish_s':finish['elapsed_ns']/1e9,'native_startup_s':native['startup_ns']/1e9,'prompt_to_final_s':(c['final_received_ns']-c['prompt_submitted_ns'])/1e9,'final_to_consumer_cleanup_s':(c['cleanup_end_ns']-c['final_received_ns'])/1e9,'owner_tool_work_s':sum(x['receipt']['elapsed_ns'] for x in owner)/1e9,'worker_execution_s':sum(x['elapsed_ns'] for x in execs)/1e9,'plugin_metadata_s':sum(x['elapsed_ns'] for x in private if x['method']!='tools/call')/1e9}
 assert abs(timing['full_cell_s']-timing['setup_s']-timing['consumer_wall_s']-timing['post_consumer_owner_close_tail_s'])<1e-8
 counts={'tool_attempts':len(owner),'native_tool_attempts':sum(x['name']=='execute_blender_code' for x in owner),'plugin_tool_attempts':sum(x['name']!='execute_blender_code' for x in owner),'tool_errors':sum(bool(x['receipt']['is_error']) for x in owner),'public_id_requests':sum(x['has_id'] for x in public),'public_notifications':sum(not x['has_id'] for x in public),'worker_execute_rpcs':len(execs),'worker_close_rpcs':len(ends),'worker_physical_connections':len(execs)+len(ends),'private_plugin_id_requests':sum(x['has_id'] for x in private),'private_plugin_notifications':sum(not x['has_id'] for x in private),'thin_exit_missing':bridge_missing,'warnings':len(warnings)}
 bytes_={'owner_tool_response_bytes':t['wire_tool_bytes'],'owner_tool_content_text_bytes':sum(x['text_bytes'] for x in owner),'public_TX_bytes':sum(x['tx_bytes'] for x in public),'public_RX_bytes':sum(x['rx_bytes'] for x in public),'public_catalogue_RX_bytes':sum(x['rx_bytes'] for x in public if x['method']=='tools/list'),'public_non_tool_RX_bytes':sum(x['rx_bytes'] for x in public if x['method']!='tools/call'),'private_plugin_TX_bytes':sum(x['tx_bytes'] for x in private),'private_plugin_RX_bytes':sum(x['rx_bytes'] for x in private),'worker_stdout_bytes':sum(x['stdout_bytes'] for x in execs),'executed_code_bytes':sum(len(blob(x)) for x in scripts),'initial_image_bytes':c['input_image_bytes'],'prompt_bytes':c['input_text_bytes'],'tool_image_bytes':c['public_image_bytes'],'public_final_text_bytes':len(c['final'].encode())}
 routes=[x['name'] for x in owner]
 row={'cell':cell,'round':rr['round'],'group':rr['group'],'anonymous_id':next(m['anonymous_id'] for m in mapping if m['cell']==cell),'quality':'complete_correct per sealed quality','timing':timing,'counts':counts,'bytes':bytes_,'usage':usage,'derived_input_plus_output_tokens':usage['input_tokens']+usage['output_tokens'],'derived_uncached_input_tokens':usage['input_tokens']-usage['cached_input_tokens'],'raw_timestamps':{k:rr[k] for k in ('cell_started_ns','cell_ended_ns','worker_deadline_ns')}|{k:c[k] for k in ('started_ns','deadline_ns','prompt_submitted_ns','final_received_ns','turn_completed_ns','process_exit_ns','cleanup_end_ns')},'errors':{'cell':rr['errors'],'consumer':c['errors'],'deviations':c['unexpected_tool_deviations'],'provider_retry_observations':c['provider_retry_observations'],'backend':close['errors']},'warnings':warnings,'route':routes,'owner_tool_attempts':[{k:v for k,v in x['receipt'].items()} for x in owner],'public_rpc_frames':public,'private_plugin_rpc_frames':private,'worker_event_scope':{'execute_records':len(execs),'last_close_record':ends[0],'note':'Close record status remains unknown because helper close path leaves event status unset; separate native close response/exit confirms close. Not a failed geometry execution.'},'retained_unknowns':{'thin_EXIT':c['bridge_cleanup']['confirmed'],'provider_requests':c['provider_requests'],'fees':c['fees'],'resolved_effort':c['resolved_effort'],'image_tokens':c['image_tokens'],'provider_image_delivery':c['image_delivery']['provider_delivery_confirmed'],'image_cognitive_use':c['image_delivery']['model_view_confirmed'],'warning_exclusive_time':None,'arbitrary_transient_mutation':None},'completion':{'valid':c['valid_completion'],'within_570s':rr['within_570s'],'backend_close_confirmed':finish['confirmed'],'new_image_construction':close['image_construction']['status']}}
 rows.append(row)
groups={}
for group in ('N','P'):
 chosen=[r for r in rows if r['group']==group]
 groups[group]={section:{key:stat([r[section][key] for r in chosen]) for key in chosen[0][section]} for section in ('timing','counts','bytes','usage')}
 groups[group]['derived_input_plus_output_tokens']=stat([r['derived_input_plus_output_tokens'] for r in chosen]);groups[group]['derived_uncached_input_tokens']=stat([r['derived_uncached_input_tokens'] for r in chosen])
pairs=[]
for round_ in (1,2,3):
 n=next(r for r in rows if r['round']==round_ and r['group']=='N');p=next(r for r in rows if r['round']==round_ and r['group']=='P');a=n['timing']['full_cell_s'];z=p['timing']['full_cell_s'];pairs.append({'round':round_,'N_cell':n['cell'],'P_cell':p['cell'],'N_full_s':a,'P_full_s':z,'P_minus_N_s':z-a,'P_over_N':z/a,'P_reduction_fraction':1-z/a,'P_minus_N_input_tokens':p['usage']['input_tokens']-n['usage']['input_tokens'],'P_minus_N_input_plus_output':p['derived_input_plus_output_tokens']-n['derived_input_plus_output_tokens']})
prep=[]
for rname in ('run_01','run_02'):
 processes=[{'path':str(p.relative_to(BASE)),**read(p)} for p in sorted((BASE/'installation'/rname).glob('*.PROCESS.json'))]
 prep.append({'stage':'installation_'+rname,'known_subprocess_wall_s':sum((r['ended_ns']-r['started_ns'])/1e9 for r in processes),'first_start_to_last_end_window_s':(max(r['ended_ns'] for r in processes)-min(r['started_ns'] for r in processes))/1e9,'processes':[{'path':r['path'],'started_ns':r['started_ns'],'ended_ns':r['ended_ns'],'exit_code':r['returncode'],'elapsed_s':(r['ended_ns']-r['started_ns'])/1e9} for r in processes],'note':'Retain build/archive/failed install cost; subprocess sum/window are nested alternative scopes, not additive.'})
pr=read(BASE/'preflight/run_02/RESULTS.json');prep.append({'stage':'background_preflight_run_02','elapsed_s':pr['elapsed_ns']/1e9,'original_passed':pr.get('passed'),'note':'Original aggregation failure retained; valid N/P background actions and close remain costs. No replay to erase failure.'})
ready=read(BASE/'installation/READY.json');prep.append({'stage':'installation_success_wrapper','elapsed_s':ready['elapsed_ns']/1e9,'note':'Nested run_02 wrapper; do not add again to its subprocess/window total.'})
ref=read(BASE/'scoring/REFERENCE_REPLAY.PROCESS.json');dt=lambda x:datetime.datetime.fromisoformat(x.replace('Z','+00:00'));prep.append({'stage':'independent_reference_replay','elapsed_s':(dt(ref['ended_utc'])-dt(ref['started_utc'])).total_seconds(),'note':'UTC timestamp difference; precision as exposed; not model/product time.'})
prep.extend([{'stage':'preflight_bootstrap_run_01','elapsed_s':None,'failure':'KeyError before backend launch; preserved BOOTSTRAP_FAILURE.txt','path':str(BASE/'preflight/run_01/BOOTSTRAP_FAILURE.txt')},{'stage':'metadata_entry_and_postprocess','elapsed_s':None,'note':'Actual metadata entry and same-raw postprocess occurred; complete elapsed not recorded in their aggregate JSON.'},{'stage':'M4_PREP_001_projection_correction','elapsed_s':None,'note':'Synthetic baseline2 expected failures and revised4 passes; correction and review effort real but total elapsed/model tokens not metered.'},{'stage':'input_preparation_freezing_quality_pack_reviews','elapsed_s':None,'note':'Separate real work, not zero; no complete disjoint ledger, no net ROI or assumed amortization claimed.'}])
prep.append({'stage':'parent_verified_implementation_turn_windows','provenance':'Parent reports actual read_thread/wait_threads records; this subreview did not independently reread those conversations.','windows':[{'turn':'01a1c6c5','phase':'preparation','startedAt':1794336218,'completedAt':1794339007,'durationMs':2789369},{'turn':'01a1c6fc','phase':'projection_correction','startedAt':1794339775,'completedAt':1794340788,'durationMs':1013041},{'turn':'01a1c712','phase':'formal_execution_and_packaging','startedAt':1794341251,'completedAt':1794342573,'durationMs':1321589}],'sum_turn_windows_s':5123.999,'first_preparation_to_formal_end_span_s':6355,'note':'Enclosing elapsed windows include author/subreview/wait/packaging and formal336.8735813s. Do not add them to nested install/preflight/cell time. Span includes between-turn root-review gaps, excludes current final review and earlier original-asset construction. Not pure CPU/model time or fixed per-task overhead; coordinator usage/fees unknown.'})
launch=read(BASE/'formal_run/LAUNCH.json');ret=read(BASE/'formal_run/CONTROLLER_RETURN.json');nmed=groups['N']['timing']['full_cell_s']['median'];pmed=groups['P']['timing']['full_cell_s']['median']
result={'scope':'Independent all-six raw event/frame/receipt cost recomputation after quality seal; no author postprocessor or product/model/Blender execution','quality_seal_sha256_supplied':'16032384e9f0914ba3e377a1fad1ecd05bcdc9c92ffce6e9a8dc5087eeb8c2c1','execution_commit_supplied':'a5f9da9c','all_records':rows,'group_statistics':groups,'round_pairs':pairs,'comparison':{'primary_P_full_median_lower_than_N':pmed<nmed,'primary_median_P_over_N':pmed/nmed,'primary_median_delta_s':pmed-nmed,'primary_median_P_reduction_fraction':1-pmed/nmed,'total_P_over_N':groups['P']['timing']['full_cell_s']['sum']/groups['N']['timing']['full_cell_s']['sum'],'quality_gate':'both3/3 complete_correct; unchanged sealed judgments','interpretation':'P total time lower but median higher: preregistered efficiency criterion fails. One scene/3rep each; totals cannot replace primary median.'},'batch':{'driver_wall_s':(run['batch_ended_ns']-run['batch_started_ns'])/1e9,'sum_full_cells_s':sum(r['full_cell_wall_ns'] for r in run['records'])/1e9,'driver_non_cell_overhead_s':(run['batch_wall_ns']-sum(r['full_cell_wall_ns'] for r in run['records']))/1e9,'controller_launcher_to_return_s':(ret['controller_ended_ns']-launch['launcher_started_ns'])/1e9,'stop':run['stop'],'all_six_dispatched':run['all_planned_dispatched'],'replacement_consumers':0,'scope':'driver begins before batch checks through per-cell accounting; excludes final timing summary/caller; controller receipt includes wrapper but not later seal/analysis work'},'preparation_costs_separate':prep,'accounting_rules':['Counts for public MCP, private plugin MCP and worker RPC are distinct layers; do not sum them as independent model requests.','input+output derived once; cached_input is subset of input and reasoning_output is subset of output, never add again.','Owner bytes complete serialized tool JSON; content text excludes framing; catalogue/non-tool frames and raw private RPC distinct.','Initial image bytes are one1,185,069-byte attachment per cell; actual image tokens/provider payload unknown.','Warnings and missing thin EXIT retained; no causal exclusive latency available, no subtraction. Native helper close status-unknown event has separate successful close/exit proof.','No coordinate-cost estimates from tokens, no API fees, no provider request count, no total ROI or automatic amortization.'],'source_hashes':SOURCES}
(OUT/'COST_REVIEW.json').write_bytes(json.dumps(result,ensure_ascii=False,indent=2).encode()+b'\n')
print(json.dumps({'comparison':result['comparison'],'batch':result['batch'],'group_usage':{g:groups[g]['usage'] for g in groups},'group_counts':{g:groups[g]['counts'] for g in groups},'preparation':prep[:4]},ensure_ascii=False))
