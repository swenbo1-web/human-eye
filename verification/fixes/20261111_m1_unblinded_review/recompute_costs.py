"""Read-only independent M1 cost recomputation. Writes only this review directory.
No Blender, product, consumer, network or provider calls. Python stdlib only.
"""
import base64, collections, hashlib, json, math, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parent
EVAL=pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval')
MANIFEST={}
def raw(path):
    path=pathlib.Path(path);b=path.read_bytes();MANIFEST[str(path)]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};return b
def load(path):return json.loads(raw(path))
def lines(path):return [json.loads(x) for x in raw(path).decode('utf-8').splitlines() if x.strip()]
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def stats(values):
    known=[v for v in values if v is not None]
    return {'n':len(values),'observed':len(known),'unknown':len(values)-len(known),'sum':sum(known) if known else None,'median':statistics.median(known) if known else None,'min':min(known) if known else None,'max':max(known) if known else None}
def union_ns(intervals):
    if not intervals:return 0
    out=0;a,b=sorted(intervals)[0]
    for c,d in sorted(intervals)[1:]:
        if c>b:out+=b-a;a,b=c,d
        else:b=max(b,d)
    return out+b-a
def text_bytes(result):return sum(len(x.get('text','').encode('utf-8')) for x in (result or {}).get('content',[]) if x.get('type')=='text')
def parse_content(result):
    ans=[]
    for x in (result or {}).get('content',[]):
        if x.get('type')=='text':
            try:ans.append(json.loads(x['text']))
            except (ValueError,TypeError):pass
    return ans
# Selected by inspection of actual evidence after quality seal; not by latency.
# Indices are one-based completed public tool calls. Mandatory task facts only.
FACT_CALL={'01':3,'02':1,'03':1,'04':5,'05':1,'06':3,'07':1,'08':3,'09':4,
           '10':1,'11':3,'12':2,'13':3,'14':5,'15':1,'16':1,'17':1,'18':4,
           '19':2,'20':1,'21':3,'22':1,'23':3,'24':1,'25':3,'26':6,'27':1}
FACT_NOTE={
 '09':'Call 3 gives feature minima without intersection check or delivered bounds; call 4 supplies all candidate bounds plus no-intersection checks. Conservative sufficient-evidence timestamp is call 4.',
 '12':'Complete global nearest at call 2 suffices; later failed requests and local witness verification remain in total cost.',
 '14':'Calls 4+5 cover 3+2 candidates with measured surface distances; unknown closed-solid relation on open meshes does not invalidate requested surface distance.',
 '18':'Call 4 supplies both separated distances and shared-interior witness after earlier relation checks.',
 '19':'Complete global nearest at call 2 suffices; subsequent 5 calls remain in total cost.',
 '25':'Pruned complete surface solve at call 3 suffices; exhaustive call 4 is additional confirmation, retained in total cost.',
 '26':'Enumeration plus successful candidate batches 3+3+2 becomes complete only at call 6.'}
run=load(EVAL/'RUN_RESULT.json');plan=load(EVAL/'PLAN.json');amap=load(EVAL/'private/ANON_MAP.json')
seal=load(pathlib.Path('D:/hefe/verification/fixes/20261111_m1_quality_review/QUALITY_SEAL.json'))
assert MANIFEST[str(pathlib.Path('D:/hefe/verification/fixes/20261111_m1_quality_review/QUALITY_SEAL.json'))]['sha256']=='ba70bf01571e86f19953b55391e447723f6e20a9bd52ffed0e7c4e9e99d44554'
assert len(run['records'])==27 and run['stop'] is None
assert plan['max_session_seconds']==450 and plan['total_cell_seconds']==570
mapped={x['cell']:x for x in amap['rows']};cells=[];checks=[];extra=[]
for record in run['records']:
    cid=record['cell'];d=EVAL/'cells'/cid;c=load(d/'CONSUMER.json');ev=lines(d/'events.jsonl')
    owner=load(d/'owner/TOOLS.json');close=load(d/'owner/CLOSE.json');launch=load(d/'ACTOR_LAUNCH.json');cfg=load(d/'ACTOR_CONFIG.json')
    sess=load(d/'owner/native/SESSION.json');worker=lines(d/'owner/native/WORKER_EVENTS.jsonl');wclose=load(d/'owner/native/WORKER_CLOSED.json')
    for k in ['task','group','round']:assert record[k]==c[k]==mapped[cid][k]
    assert record['consumer']==c
    starts={x['event']['item']['id']:x for x in ev if x['event'].get('type')=='item.started' and x['event'].get('item',{}).get('type')=='mcp_tool_call'}
    calls=[x for x in ev if x['event'].get('type')=='item.completed' and x['event'].get('item',{}).get('type')=='mcp_tool_call']
    finals=[x for x in ev if x['event'].get('type')=='item.completed' and x['event'].get('item',{}).get('type')=='agent_message']
    usage_events=[x for x in ev if x['event'].get('type')=='turn.completed'];assert len(usage_events)==1
    usage=usage_events[0]['event']['usage'];assert usage==c['usage'] and c['usage_rows']==[usage]
    assert len(calls)==len(c['tool_calls'])==owner['attempts']==len(owner['tools'])
    assert finals[-1]['perf_ns']==c['final_received_ns'] and finals[-1]['event']['item']['text']==c['final']
    assert raw(d/'PUBLIC_FINAL.txt')==c['final'].encode('utf-8')
    for k in ['input_tokens','output_tokens','cached_input_tokens','cache_write_input_tokens','reasoning_output_tokens']:assert type(usage[k]) is int and usage[k]>=0
    assert usage['cached_input_tokens']<=usage['input_tokens'] and usage['reasoning_output_tokens']<=usage['output_tokens']
    ns={'cell_start':record['cell_started_ns'],'cell_end':record['cell_ended_ns'],'prepare_start':launch['prepare_started_ns'],
        'consumer_start':c['started_ns'],'consumer_deadline':c['deadline_ns'],'worker_deadline':record['worker_deadline_ns'],
        'prompt_submitted':c['prompt_submitted_ns'],'first_tool_started':min(x['perf_ns'] for x in starts.values()),
        'first_sufficient_fact_received':calls[FACT_CALL[cid]-1]['perf_ns'],'last_tool_completed':calls[-1]['perf_ns'],
        'final_received':finals[-1]['perf_ns'],'turn_completed':usage_events[0]['perf_ns'],'process_exit':c['process_exit_ns'],'consumer_cleanup_end':c['cleanup_end_ns']}
    assert launch['cell_started_ns']==launch['started_ns']==ns['cell_start']
    assert cfg['worker_deadline_ns']==sess['deadline_ns']==ns['worker_deadline']==ns['cell_start']+570*10**9
    assert sess['max_calls']==128
    assert c['deadline_ns']==ns['consumer_start']+450*10**9
    assert launch['actor_startup_deadline_ns']==min(ns['worker_deadline'],ns['prepare_start']+40*10**9)
    assert record['full_cell_wall_ns']==ns['cell_end']-ns['cell_start']==c['total_task_wall_ns']
    assert c['wall_ns']==ns['consumer_cleanup_end']-ns['consumer_start']
    assert c['pre_consumer_setup_ns']==ns['consumer_start']-ns['cell_start']
    assert c['prompt_to_final_ns']==ns['final_received']-ns['prompt_submitted']
    metrics={
      'full_cell_s':(ns['cell_end']-ns['cell_start'])/1e9,
      'setup_before_consumer_s':(ns['consumer_start']-ns['cell_start'])/1e9,
      'consumer_lifecycle_s':(ns['consumer_cleanup_end']-ns['consumer_start'])/1e9,
      'owner_close_after_consumer_s':(ns['cell_end']-ns['consumer_cleanup_end'])/1e9,
      'prompt_to_final_s':(ns['final_received']-ns['prompt_submitted'])/1e9,
      'prompt_to_first_tool_s':(ns['first_tool_started']-ns['prompt_submitted'])/1e9,
      'first_sufficient_fact_to_final_s':(ns['final_received']-ns['first_sufficient_fact_received'])/1e9,
      'last_tool_to_final_s':(ns['final_received']-ns['last_tool_completed'])/1e9,
      'final_to_consumer_cleanup_s':(ns['consumer_cleanup_end']-ns['final_received'])/1e9,
      'input_tokens':usage['input_tokens'],'cached_input_tokens_subset':usage['cached_input_tokens'],
      'uncached_input_tokens':usage['input_tokens']-usage['cached_input_tokens'],'cache_write_input_tokens_reported':usage['cache_write_input_tokens'],
      'output_tokens':usage['output_tokens'],'reasoning_output_tokens_subset':usage['reasoning_output_tokens'],
      'input_plus_output_tokens':usage['input_tokens']+usage['output_tokens'],
      'tool_calls':len(calls),'native_tool_calls':sum(x['event']['item']['tool']=='execute_blender_code' for x in calls),
      'plugin_tool_calls':sum(x['event']['item']['tool']!='execute_blender_code' for x in calls),
      'tool_error_calls':sum(bool(x['is_error']) for x in owner['tools']),
      'prompt_text_bytes':c['input_text_bytes'],'final_text_bytes':len(c['final'].encode('utf-8')),
      'all_public_message_text_bytes':sum(len(x['event']['item']['text'].encode('utf-8')) for x in finals),
      'public_tool_result_text_bytes':sum(text_bytes(x['event']['item'].get('result')) for x in calls),
      'public_image_count':0,'public_image_encoded_bytes':0,
      'provider_requests':None,'dollar_fees':None,'model_reasoning_time_s':None}
    attempts=[];public_intervals=[];owner_intervals=[]
    for i,(x,ot) in enumerate(zip(calls,owner['tools']),1):
        item=x['event']['item'];st=starts[item['id']]['perf_ns'];end=x['perf_ns'];a=load(d/'owner'/('tool_'+str(i).zfill(2))/'ATTEMPT.json');req=load(d/'owner'/('tool_'+str(i).zfill(2))/'REQUEST.json')
        assert a==ot and req['params']['name']==item['tool'] and req['params']['arguments']==item['arguments']
        assert c['tool_calls'][i-1]['perf_ns']==end and c['tool_calls'][i-1]['item']==item
        errs=[o.get('error') for o in parse_content(item.get('result')) if o.get('status')=='error']
        for part in (item.get('result') or {}).get('content',[]):
            if part.get('type')=='image':metrics['public_image_count']+=1;metrics['public_image_encoded_bytes']+=len(part.get('data','').encode())
        row={'call_index':i,'tool':item['tool'],'status':item.get('status'),'is_error':bool(a['is_error']),
             'error_messages':errs,'owner_exception':a.get('exception'),'arguments_sha256':digest(item['arguments']),
             'public_start_ns':st,'public_end_ns':end,'public_tool_wall_s':(end-st)/1e9,
             'owner_start_ns':a['started_ns'],'owner_tool_wall_s':a['elapsed_ns']/1e9,
             'actual_owner_response_bytes':a['response_bytes'],'produced_response_bytes':a['produced_response_bytes'],
             'public_text_bytes':text_bytes(item.get('result')),'evidence':str(d/'owner'/('tool_'+str(i).zfill(2))),
             'per_call_usage':None,
             'returned_fact_statuses':[o.get('status') for o in parse_content(item.get('result'))],
             'returned_result_kinds':[o.get('result_kind') for o in parse_content(item.get('result')) if o.get('result_kind')],
             'partial_fact_response':any(o.get('status')=='partial' for o in parse_content(item.get('result')))}
        attempts.append(row);public_intervals.append((st,end));owner_intervals.append((a['started_ns'],a['started_ns']+a['elapsed_ns']))
    metrics['partial_fact_responses']=sum(a['partial_fact_response'] for a in attempts)
    metrics.update(public_tool_wall_sum_s=sum(b-a for a,b in public_intervals)/1e9,
                   public_tool_wall_union_s=union_ns(public_intervals)/1e9,
                   owner_tool_wall_sum_s=sum(b-a for a,b in owner_intervals)/1e9,
                   owner_tool_wall_union_s=union_ns(owner_intervals)/1e9,
                   owner_produced_tool_response_bytes=sum(x['produced_response_bytes'] or 0 for x in attempts))
    # Public actual transport frames, including handshake/catalogue and failures.
    frames=[]
    for txp in sorted((d/'attachments').glob('bridge_*/*/TX.bin')):
        tx=raw(txp);req=json.loads(tx);rxp=txp.with_name('RX.bin');rx=raw(rxp) if rxp.exists() else b'';resp=json.loads(rx) if rx else None
        method=req.get('method');kind='tool' if method=='tools/call' else ('catalogue' if method=='tools/list' else 'handshake_or_control')
        frames.append({'directory':str(txp.parent),'method':method,'has_id':'id' in req,'kind':kind,'tx_bytes':len(tx),'rx_bytes':len(rx),
                       'tool':req.get('params',{}).get('name'),'response_missing':'id' in req and not rx,'response_error':None if resp is None else bool(resp.get('error') or resp.get('result',{}).get('isError'))})
    metrics.update(public_request_frames=sum(x['has_id'] for x in frames),public_notification_frames=sum(not x['has_id'] for x in frames),
                   public_tx_bytes=sum(x['tx_bytes'] for x in frames),public_rx_bytes=sum(x['rx_bytes'] for x in frames),
                   public_tool_tx_bytes=sum(x['tx_bytes'] for x in frames if x['kind']=='tool'),
                   public_tool_rx_bytes=sum(x['rx_bytes'] for x in frames if x['kind']=='tool'),
                   public_catalogue_rx_bytes=sum(x['rx_bytes'] for x in frames if x['kind']=='catalogue'),
                   public_handshake_control_tx_rx_bytes=sum(x['tx_bytes']+x['rx_bytes'] for x in frames if x['kind']=='handshake_or_control'))
    assert sum(x['kind']=='tool' for x in frames)==len(calls)
    assert metrics['public_tool_rx_bytes']==owner['wire_tool_bytes']==sum(x['actual_owner_response_bytes'] for x in attempts)
    assert metrics['public_image_count']==c['public_image_count']==0
    # Separate internal product MCP; not additional public model calls/bytes.
    peer_path=d/'owner/plugin/RPC.json';peer=load(peer_path) if peer_path.exists() else None
    pframes=[]
    if peer:
        for f in sorted((d/'owner/plugin').glob('*/TX.bin')):
            q=json.loads(raw(f));rx=f.with_name('RX.bin');pframes.append({'method':q.get('method'),'has_id':'id' in q,'tx_bytes':f.stat().st_size,'rx_bytes':len(raw(rx)) if rx.exists() else 0})
        assert sum(x['tx_bytes'] for x in pframes)==peer['tx_bytes'] and sum(x['rx_bytes'] for x in pframes)==peer['rx_bytes']
        assert len(pframes)==len(peer['requests'])
    metrics.update(internal_product_request_frames=sum(x['has_id'] for x in pframes),internal_product_notification_frames=sum(not x['has_id'] for x in pframes),
                   internal_product_tx_bytes=sum(x['tx_bytes'] for x in pframes),internal_product_rx_bytes=sum(x['rx_bytes'] for x in pframes),
                   internal_product_catalogue_rx_bytes=sum(x['rx_bytes'] for x in pframes if x['method']=='tools/list'))
    scripts=list((d/'owner/native').glob('call_*/SCRIPT.py'));commands=[x for x in worker if 'script_sha256' in x]
    assert len(scripts)==len(commands)
    metrics.update(worker_execute_code_requests=len(commands),worker_all_request_events=sum('sequence' in x for x in worker),
                   worker_script_bytes=sum(len(raw(f)) for f in scripts),
                   worker_stdout_archived_bytes=sum(len(raw(f)) for f in (d/'owner/native').glob('call_*/stdout.txt')),
                   worker_request_wire_bytes=None,worker_response_wire_bytes=None)
    # Terminal close logs its request as status unknown before exiting; retain separately.
    terminal=[x for x in worker if 'sequence' in x and 'script_sha256' not in x]
    stderr=lines(d/'stderr_lines.jsonl')
    stderr_summary=collections.Counter()
    for x in stderr:
        txt=x['text']
        if 'failed to refresh available models' in txt:stderr_summary['model_catalogue_refresh_timeout']+=1
        elif 'Unknown model gpt-6.1-sol' in txt:stderr_summary['fallback_model_metadata_warning']+=1
        elif 'Shell snapshot not supported yet for PowerShell' in txt:stderr_summary['unsupported_shell_snapshot']+=1
        else:stderr_summary['other']+=1
    duplicate_args=[];seen={}
    for a in attempts:
        key=(a['tool'],a['arguments_sha256'])
        if key in seen:duplicate_args.append({'earlier_call':seen[key],'later_call':a['call_index'],'same_arguments':True})
        else:seen[key]=a['call_index']
    row={'cell':cid,'anonymous_id':mapped[cid]['anonymous_id'],'task':record['task'],'group':record['group'],'round':record['round'],
         'original_timestamps_ns':ns,'metrics':metrics,'first_sufficient_fact':{'completed_public_call_index':FACT_CALL[cid],
          'evidence_note':FACT_NOTE.get(cid,'First successful complete task fact response, or the completed global surface solve following complete scene enumeration.'),
          'scope':'Sufficiency of mandatory requested facts based on received public tool completion; not proof of exact model ingestion time, model belief or pure reasoning duration.'},
         'attempts':attempts,'public_frames':frames,'internal_product_frames':pframes,
         'budget_checks':{'cell_within_570s':record['full_cell_wall_ns']<570*10**9,'consumer_deadline_not_fired':not c['deadline_timer_fired'],
                          'consumer_turn_within_450s':c['turn_completed_ns']<c['deadline_ns'],
                          'tool_attempts_at_most_32':len(attempts)<=32,'tool_response_bytes_at_most_1MiB':owner['wire_tool_bytes']<=1048576,
                          'maximum_owner_tool_wall_s':max(a['owner_tool_wall_s'] for a in attempts),
                          'owner_tool_wall_at_most_30s':all(a['owner_tool_wall_s']<=30 for a in attempts),
                          'worker_code_requests_at_most_128':len(commands)<=128},
         'anomalies':{'run_errors':record['errors'],'consumer_errors':c['errors'],'unexpected_tool_deviations':c['unexpected_tool_deviations'],
                      'provider_retry_observations':c['provider_retry_observations'],'same_argument_repeated_calls':duplicate_args,
                      'stderr_counts':dict(stderr_summary),'stderr_source':str(d/'stderr_lines.jsonl'),
                      'thin_exit_receipt_status':c['bridge_cleanup'].get('receipt_status'),'thin_exit_confirmed':c['bridge_cleanup'].get('confirmed'),
                      'worker_terminal_events':terminal,'worker_close_confirmed_separately':close['confirmed'],
                      'mutation_unknown':c['mutation_unknown'],'bridge_protocol_errors':c['bridge_protocol_errors']},
         'model':{'requested':c['model'],'requested_effort':c['requested_effort'],'resolved_effort':c['resolved_effort'],
                  'actual_provider_request_count':c['provider_requests'],'dollars':c['fees']}}
    cells.append(row)
    if record['group']=='S' and record['task'] in ['T2','T3']:
        a,b=attempts;assert a['tool']=='human_eye_surface_nearest' and b['tool']=='human_eye_spatial_relations'
        extra.append({'cell':cid,'task':record['task'],'nearest_completed_ns':a['public_end_ns'],'second_start_ns':b['public_start_ns'],'second_end_ns':b['public_end_ns'],'final_ns':ns['final_received'],
                      'nearest_to_second_start_s':(b['public_start_ns']-a['public_end_ns'])/1e9,'second_public_tool_wall_s':b['public_tool_wall_s'],
                      'second_owner_tool_wall_s':b['owner_tool_wall_s'],'second_to_final_s':(ns['final_received']-b['public_end_ns'])/1e9,
                      'nearest_to_final_s':(ns['final_received']-a['public_end_ns'])/1e9,'second_response_wire_bytes':b['actual_owner_response_bytes'],
                      'second_response_text_bytes':b['public_text_bytes'],'per_call_usage':None})
keys=list(cells[0]['metrics'])
def aggregate(rows):return {'n':len(rows),'cells':[x['cell'] for x in rows],'metrics':{k:stats([x['metrics'][k] for x in rows]) for k in keys}}
by_task={t:{g:aggregate([r for r in cells if r['task']==t and r['group']==g]) for g in 'NCS'} for t in ['T1','T2','T3']}
by_arm={g:aggregate([r for r in cells if r['group']==g]) for g in 'NCS'}
cell_sum=sum(r['original_timestamps_ns']['cell_end']-r['original_timestamps_ns']['cell_start'] for r in cells)
batch=run['batch_ended_ns']-run['batch_started_ns'];assert batch==run['batch_wall_ns']
gaps=[{'after_cell':a['cell'],'before_cell':b['cell'],'ns':b['original_timestamps_ns']['cell_start']-a['original_timestamps_ns']['cell_end']} for a,b in zip(cells,cells[1:])]
pre=cells[0]['original_timestamps_ns']['cell_start']-run['batch_started_ns'];post=run['batch_ended_ns']-cells[-1]['original_timestamps_ns']['cell_end']
assert pre+post+sum(x['ns'] for x in gaps)+cell_sum==batch
prep=load(EVAL/'PREPARATION_COST.json')
report={'schema':'independent-m1-27cell-cost-review-v1','reviewer':'/root/scale_opt_design_review','quality_preserved':{'seal_sha256':'ba70bf01571e86f19953b55391e447723f6e20a9bd52ffed0e7c4e9e99d44554','quality':'27/27 root-sealed, not rescored here'},
 'scope':'All 27 fixed slots; no successful subset selection, rerun, replacement or extra model calls. Original events/frames and recorded monotonic clocks independently recalculated; product/model/Blender not executed.',
 'group_meaning':{'N':'ordinary native execute_blender_code','C':'same fixed7411 product ordinary scene_observe/status catalogue','S':'same fixed7411 product compact spatial_relations/surface_nearest catalogue'},
 'measurement_rules':{
  'full_cell':'Before per-cell input/prompt checks through owner close. Includes startup, CLI, all tools/errors/fallback, final and cleanup. Subsequent cell-accounting publication is in batch wall, not each cell.',
  'consumer':'Recorded consumer monotonic origin through reader/bridge cleanup; includes CLI startup, model/API waiting, tool work and cleanup. Not pure model reasoning.',
  'batch':'run_models entry through last per-cell publication; excludes final timing-summary publication and caller overhead. Initial batch-setup failure may lack end record.',
  'tokens':'Public turn.completed actual usage; cached input is a subset of input, reasoning output is a subset of output. Total=input+output only. No sum of duplicate usage rows.',
  'public_bytes':'Actual TX.bin/RX.bin lengths include JSON framing/newline; catalogue and handshake separated. Decoded content text UTF-8 bytes are different, not added again.',
  'internal_bytes':'Product stdio RPC frames separate from public MCP frames. Worker script/stdout archival bytes are not measured TCP wire bytes or model input tokens.',
  'tool_time':'Owner and consumer-public tool intervals overlap the full wall and one another across levels. Sum and interval union both reported; never added to full-cell time.',
  'first_sufficient_fact':'Manual evidence-based timestamp of earliest completed public call furnishing all mandatory task facts, accounting for accumulated previous calls. Subsequent optional evidence, model/provider waiting and final generation are retained. It is not pure reasoning or all removable latency.',
  'retries':'All attempted tool calls retained, including corrections/fallback. No replacement sessions. Observed stderr retry markers and same-argument repeats are listed; internal provider attempts are unexposed.',
  'unknowns':'Dollar fees, provider request counts, per-call tokens, pure reasoning time, and native TCP bytes remain unknown. Pro subscription usage is not converted into API dollars.',
  'thin_exit':'All missing thin-client EXIT receipts remain unknown; independent owner/worker close confirmation is reported separately.'},
 'batch':{'started_ns':run['batch_started_ns'],'ended_ns':run['batch_ended_ns'],'wall_s':batch/1e9,'sum_cell_wall_s':cell_sum/1e9,'outside_cell_wall_s':(batch-cell_sum)/1e9,'batch_pre_cell_s':pre/1e9,'batch_post_last_cell_s':post/1e9,'between_cell_gaps':gaps},
 'by_task_arm':by_task,'by_arm':by_arm,'all_cells':aggregate(cells),'cells':cells,
 'comparisons':{t:{baseline:{'S_full_cell_median_reduction_fraction':1-z['S']['metrics']['full_cell_s']['median']/z[baseline]['metrics']['full_cell_s']['median'],
 'S_full_cell_sum_reduction_fraction':1-z['S']['metrics']['full_cell_s']['sum']/z[baseline]['metrics']['full_cell_s']['sum'],
 'S_input_plus_output_token_sum_reduction_fraction':1-z['S']['metrics']['input_plus_output_tokens']['sum']/z[baseline]['metrics']['input_plus_output_tokens']['sum']} for baseline in ['N','C']} for t,z in {**by_task,'ALL':by_arm}.items()},
 'diagnostics_by_arm':{g:dict(sum((collections.Counter(x['anomalies']['stderr_counts']) for x in cells if x['group']==g),collections.Counter())) for g in 'NCS'},
 'nearest_followup':{'cells':extra,'summary':{k:stats([r[k] for r in extra]) for k in extra[0] if k.endswith('_s') or k.endswith('_bytes')},
  'interpretation':'Six follow-up spatial_relations calls request witnesses (and sometimes relation/AABB). Their directly measured tool time and bytes are real; nearest-to-final spans include model/provider waits, additional facts and final-answer construction, and are not a predicted time saving. Per-call usage cannot be split from session totals.'},
 'one_time_preparation':{'historical_record':prep,'separate_from_formal_model_batch':True,'historical_measured_s':prep['elapsed_s'],'comparison_caution':'3018.7268128 seconds is the earlier preparation window including coding/review/waits and failed probes, not this model batch. Intended /27 amortization is a disclosed arithmetic illustration, not a net-benefit calculation; earlier analysis, later V2 review/sealing and coordinator tokens/fees are unmeasured.'},
 'limits':{'sample_size':3,'per_arm_total':9,'not_a_population_performance_guarantee':True,'price_or_total_project_cost_claim':False},
 'source_manifest':MANIFEST}
(ROOT/'COST_REVIEW.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines_out=['# Independent cost review — M1 formal 27 cells','','All 27 fixed records included; root-sealed quality 27/27 unchanged. No additional consumer, product or Blender execution. N is native, C the ordinary large interface, S the compact interface on the same7411 product.','','| Task | Arm | n | Full cell median / range (s) | Full cell sum (s) | Consumer median (s) | Calls / errors | Input tokens | Output tokens |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
for t in ['T1','T2','T3']:
 for g in 'NCS':
  z=by_task[t][g]['metrics'];f=z['full_cell_s'];lines_out.append(f"| {t} | {g} | 3 | {f['median']:.3f} / {f['min']:.3f}–{f['max']:.3f} | {f['sum']:.3f} | {z['consumer_lifecycle_s']['median']:.3f} | {z['tool_calls']['sum']} / {z['tool_error_calls']['sum']} | {z['input_tokens']['sum']} | {z['output_tokens']['sum']} |")
lines_out+=['','| Arm (9 cells each) | Full total / median (s) | Calls / errors | Input | Cached input subset | Output | Reasoning output subset |','|---|---:|---:|---:|---:|---:|---:|']
for g in 'NCS':
 z=by_arm[g]['metrics'];lines_out.append(f"| {g} | {z['full_cell_s']['sum']:.3f} / {z['full_cell_s']['median']:.3f} | {z['tool_calls']['sum']} / {z['tool_error_calls']['sum']} | {z['input_tokens']['sum']} | {z['cached_input_tokens_subset']['sum']} | {z['output_tokens']['sum']} | {z['reasoning_output_tokens_subset']['sum']} |")
lines_out+=['',f"Batch wall = {batch/1e9:.7f} s; sum of 27 full cells = {cell_sum/1e9:.7f} s; batch setup/inter-cell accounting difference = {(batch-cell_sum)/1e9:.7f} s. Startup, failed requests, fallback and owner cleanup remain included. Tool wall times are nested; do not add them to cell wall.",'','Cached tokens are already inside input; reasoning tokens are already inside output. Both subset counts are publicly reported in this run. Provider request counts, per-tool tokens, model-only reasoning time and dollar costs are not exposed. All stderr diagnostics and 10 tool errors are retained; no consumer replacement or observed provider retry marker was found. Missing thin-client EXIT receipts remain unknown independently of confirmed owner/worker cleanup.','','## Six S nearest follow-up calls','', '| Cell | Nearest → second start (s) | Second public tool wall (s) | Second → final (s) | Nearest → final (s) | Second response wire / text bytes |','|---|---:|---:|---:|---:|---:|']
for r in extra:lines_out.append(f"| {r['cell']} | {r['nearest_to_second_start_s']:.3f} | {r['second_public_tool_wall_s']:.6f} | {r['second_to_final_s']:.3f} | {r['nearest_to_final_s']:.3f} | {r['second_response_wire_bytes']} / {r['second_response_text_bytes']} |")
lines_out+=['','The direct second-call owner work totals '+f"{sum(r['second_owner_tool_wall_s'] for r in extra):.7f} s"+'; public tool intervals total '+f"{sum(r['second_public_tool_wall_s'] for r in extra):.7f} s"+'. The larger nearest-to-final span includes additional query construction and final generation/provider waiting; it is not all removable latency or pure reasoning. Session usage cannot identify tokens specific to the second call.','','## Cost boundaries and retained limitations','','Public tools/list RX frames are exactly 575 bytes (N), 11236 bytes (C), and 2447 bytes (S), each per session. These are serialized wire response sizes, not model tokens. Across the run there are 134 public ID-bearing requests (80 tools plus 54 handshake/list), 27 public notifications; internal product and worker requests remain separate. Thirty-three model-catalogue refresh timeout messages, 54 fallback-model-metadata warnings, and 27 unsupported PowerShell snapshot diagnostics were retained. They are not silently deducted from wall time or labelled provider retries. Requested model/effort settings are fixed; exact backend resolution is not demonstrated by these warnings. Non-error partial relation responses on open T3 meshes retain valid surface facts and are separate from the 10 failed calls. The historical preparation window is 3018.7268128 s (coding/review/waits and failed probes), shown separately. It is not this formal model batch and its intended /27 amortization cannot establish total project net benefit. Earlier analysis, later V2 preparation/review/sealing and coordinator model costs remain unknown.','','All final cells retain original 570-second worker deadlines and 450-second consumer budgets; this is not a claim of a universal 570-second process kill timer. Actual owner tool work and worker code-call budgets are checked. Public MCP handshake/catalogue/tool TX/RX bytes and internal product RPC bytes are separately aggregated in JSON. Native script/stdout archival sizes are not TCP wire sizes. No output or cached token is double counted.','','The JSON contains per-cell raw timestamp references, all 80 attempts, frame-level byte counts, per-task and per-arm sums/medians/ranges, source SHA256 bindings, anomalies, first-sufficient-fact timing and the independent recomputation script is `recompute_costs.py`. Results are descriptive for 3 samples per task/arm.']
(ROOT/'COST_REVIEW.md').write_text('\n'.join(lines_out)+'\n',encoding='utf-8')
for g in 'NCS':
 z=by_arm[g]['metrics'];print(g,'full',z['full_cell_s'],'calls',z['tool_calls']['sum'],'errors',z['tool_error_calls']['sum'],'public_txrx',z['public_tx_bytes']['sum'],z['public_rx_bytes']['sum'],'rpcworker',z['worker_execute_code_requests']['sum'])
print('sources',len(MANIFEST),'all 27 processed')
for name in ['COST_REVIEW.json','COST_REVIEW.md','recompute_costs.py']:print(name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest())
