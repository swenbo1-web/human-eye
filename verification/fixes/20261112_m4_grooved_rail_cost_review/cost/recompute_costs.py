"""Independent, offline audit. No author analysis import/execution, no model or product calls.
Only stdlib; original sources are read and checked against Git blob ids at ORIGINAL.
"""
import collections
import datetime
import hashlib
import json
import pathlib
import statistics
import subprocess

TREE = pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
REL = pathlib.Path('verification/m4_grooved_rail_consumption_001')
BASE = TREE / REL
OUT = pathlib.Path('D:/hefe/verification/fixes/20261112_m4_grooved_rail_cost_review/cost')
SEAL = pathlib.Path('D:/hefe/verification/fixes/20261112_m4_grooved_rail_quality_review/QUALITY_SEAL.json')
ORIGINAL = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
EXPECTED_HEAD = 'ea70339772159e5f0279784ebe18b1bf16e70439'
index = {}
for line in subprocess.check_output(['git','ls-tree','-r',ORIGINAL],cwd=TREE).decode().splitlines():
    meta, name = line.split('\t',1)
    index[name] = meta.split()[2]
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=TREE).decode().strip()==EXPECTED_HEAD
inputs = {}
checks = []

def check(name, value, details=None):
    checks.append({'name':name,'passed':bool(value),'details':details})
    if not value:
        raise AssertionError((name, details))

def raw(path):
    path = pathlib.Path(path)
    data = path.read_bytes()
    rel = path.relative_to(TREE).as_posix()
    blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    check('original_blob:'+rel, index.get(rel)==blob)
    inputs[rel] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_blob':blob}
    return data

def read(path):
    return json.loads(raw(path))

def load(name):
    return read(BASE/name)

def lines(path):
    return [json.loads(s) for s in raw(path).decode('utf-8').splitlines() if s]

def text(path):
    # Worker SCRIPT.py persisted with Windows newline translation; the code checksum
    # is over the executable UTF-8 string, so normalize CRLF and verify worker hash.
    return raw(path).decode('utf-8').replace('\r\n','\n')

def union_ns(intervals):
    result=0; stop=None
    for a,b in sorted(intervals):
        if stop is None or a>=stop: result+=b-a
        elif b>stop: result+=b-stop
        stop=max(stop or b,b)
    return result

def stats(v):
    return {'sum':sum(v),'min':min(v),'median':statistics.median(v),'max':max(v)}

def reduction(n,p):
    return 100*(n-p)/n

def frames(folder):
    rows=[]
    if not folder.exists(): return rows
    for p in sorted(folder.iterdir()):
        if not p.is_dir() or not (p/'TX.bin').exists(): continue
        tx=raw(p/'TX.bin'); request=json.loads(tx)
        rx=raw(p/'RX.bin') if (p/'RX.bin').exists() else None
        response=json.loads(rx) if rx else None
        if response: check('frame_ids:'+str(p), request['id']==response['id'])
        rows.append({'path':p.relative_to(BASE).as_posix(),'request':request,'response':response,
                     'tx_bytes':len(tx),'rx_bytes':len(rx) if rx else 0})
    return rows

plan=load('PLAN.json'); contract=load('BENEFIT_CONTRACT.json'); run=load('RUN_RESULT.json')
limits={'max_session_seconds':450,'total_cell_seconds':570,'actor_startup_seconds':40,'tool_attempts':32,
        'physical_RPC_limit':128,'tool_timeout_s':30,'tool_response_bytes':1048576,'code_bytes':262144}
check('frozen_limits',all(plan[k]==v for k,v in limits.items()))
for name in ['runtime/actor.py','runtime/driver.py','runtime/consumer_transport.py','runtime/run_formal.py','ROOT_PLAN.md','WORK_ORDER.json']:
    raw(BASE/name)
for name in ['verification/native_plugin_complex_003/reused/accepted_native.py','verification/native_plugin_complex_003/reused/stdio_attach.py']:
    raw(TREE/name)
sequence=load('SEQUENCE.json')['sequence']; mapping=load('private/ANON_MAP.json')['rows']
seal=json.loads(SEAL.read_bytes())
check('seal_original',seal['formal_commit']==ORIGINAL)
check('sequence_matches_plan',sequence==plan['sequence'])
check('six_retained',len(run['records'])==len(sequence)==len(mapping)==6)
check('no_stop',run['stop'] is None)
check('no_replacements',run['no_replacements'] and run['started_cells']==6)
qmap={r['answer_id']:r for r in seal['anonymous_answers']}
cells=[]
for row, slot, mapped in zip(run['records'],sequence,mapping):
    cell=slot['cell']; root=BASE/'cells'/cell
    def c(name): return read(root/name)
    for key in ('cell','group','round','task'):
        check(cell+':mapping_'+key,row[key]==slot[key]==mapped[key])
    q=qmap[mapped['anonymous_id']]
    check(cell+':quality_final_hash',hashlib.sha256(raw(root/'final.txt')).hexdigest()==q['answer_sha256'])
    check(cell+':complete_correct',q['status']=='complete_correct' and q['facts_correct']==13)
    consumer=c('CONSUMER.json'); launch=c('ACTOR_LAUNCH.json'); config=c('ACTOR_CONFIG.json')
    endpoint=c('ENDPOINT.json'); close=c('owner/CLOSE.json'); finish=c('OWNER_FINISH.json')
    session=c('owner/native/SESSION.json'); native_config=c('owner/native/CONFIG.json')
    ready=c('owner/native/READY.json'); closed=c('owner/native/WORKER_CLOSED.json')
    events=lines(root/'events.jsonl'); workers=lines(root/'owner/native/WORKER_EVENTS.jsonl')
    turns=[e for e in events if e['event']['type']=='turn.completed']
    check(cell+':one_final_cumulative_turn',len(turns)==1)
    usage=turns[-1]['event']['usage'].copy()
    check(cell+':usage_equals_original_consumer',usage==consumer['usage']==consumer['usage_rows'][0] and len(consumer['usage_rows'])==1)
    usage['input_plus_output']=usage['input_tokens']+usage['output_tokens']
    usage['uncached_input']=usage['input_tokens']-usage['cached_input_tokens']
    check(cell+':zero_input_output_images',consumer['input_image_count']==consumer['public_image_count']==0)
    check(cell+':requested_model_effort',consumer['model']=='gpt-6.1-sol' and consumer['requested_effort']=='medium')
    check(cell+':subsets',0<=usage['cached_input_tokens']<=usage['input_tokens'] and 0<=usage['reasoning_output_tokens']<=usage['output_tokens'])
    messages=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
    check(cell+':raw_final_timestamp',messages[-1]['perf_ns']==consumer['final_received_ns'])
    check(cell+':raw_turn_timestamp',turns[-1]['perf_ns']==consumer['turn_completed_ns'])
    start=row['cell_started_ns']; end=row['cell_ended_ns']; deadline=start+570*10**9
    bounds=[start,consumer['started_ns'],consumer['popen_ns'],consumer['prompt_submitted_ns'],messages[-1]['perf_ns'],turns[-1]['perf_ns'],consumer['process_exit_ns'],consumer['cleanup_end_ns'],end]
    names=['pre_consumer','consumer_to_popen','popen_to_prompt','prompt_to_final','final_to_turn','turn_to_exit','exit_to_cleanup','cleanup_to_cell_end']
    segments=dict(zip(names,[b-a for a,b in zip(bounds,bounds[1:])]))
    check(cell+':monotonic_timing',all(v>=0 for v in segments.values()))
    check(cell+':full_wall_recomputed',end-start==row['full_cell_wall_ns']==consumer['total_task_wall_ns']==sum(segments.values()))
    check(cell+':consumer_wall',consumer['cleanup_end_ns']-consumer['started_ns']==consumer['wall_ns'])
    inherited={'row':row['worker_deadline_ns'],'launch':launch['worker_deadline_ns'],'actor_config':config['worker_deadline_ns'],
               'endpoint':endpoint['chain_deadline_ns'],'native_config':native_config['deadline_ns'],'session':session['deadline_ns'],
               'ready':ready['deadline_ns'],'closed':closed['original_deadline_ns'],'close':close['native_close']['original_deadline_ns'],
               'close_response':close['native_close']['response']['deadline_ns']}
    native_receipts={}
    for p in sorted((root/'owner').rglob('*RECEIPT.json')):
        if p.name!='NATIVE_RECEIPT.json': continue
        receipt=read(p);native_receipts[p.relative_to(root).as_posix()]=receipt['original_deadline_ns']
    for name in ('INITIAL','FINAL'):
        p=root/'owner'/f'{name}.json.receipt.json'; receipt=read(p)
        native_receipts[p.relative_to(root).as_posix()]=receipt['original_deadline_ns']
    check(cell+':original_570_inherited',all(x==deadline for x in list(inherited.values())+list(native_receipts.values())))
    check(cell+':original_start_not_reset',launch['cell_started_ns']==launch['started_ns']==start)
    check(cell+':consumer_450_original',consumer['deadline_ns']==consumer['started_ns']+450*10**9)
    actor_deadline=min(deadline,launch['prepare_started_ns']+40*10**9)
    check(cell+':actor_original_40',launch['actor_startup_deadline_ns']==actor_deadline)
    check(cell+':ready_before_40',consumer['started_ns']<actor_deadline)
    check(cell+':observed_finished_before_deadlines',end<deadline and consumer['process_exit_ns']<consumer['deadline_ns'] and closed['closed_ns']<deadline)
    check(cell+':no_timer',consumer['deadline_timer_fired'] is False)
    check(cell+':worker_max_calls',native_config['max_calls']==session['max_calls']==128)
    check(cell+':worker_seq_contiguous',[w['sequence'] for w in workers]==list(range(1,len(workers)+1)))
    check(cell+':worker_events_in_original_window',all(start<=w['started_ns'] and w['started_ns']+w['elapsed_ns']<deadline for w in workers))
    check(cell+':close_tail_is_unknown_only',workers[-1]['status']=='unknown' and all(w['status']=='completed' for w in workers[:-1]))
    bridges=sorted((root/'attachments').iterdir()); check(cell+':one_bridge',len(bridges)==1)
    bridge_start=read(bridges[0]/'STARTED.json'); consumer_frames=frames(bridges[0])
    check(cell+':thin_exit_unknown',not (bridges[0]/'EXIT.json').exists() and consumer['bridge_cleanup']['confirmed'] is None)
    public_tools=[f for f in consumer_frames if f['request']['method']=='tools/call']
    started={e['event']['item']['id']:e['perf_ns'] for e in events if e['event']['type']=='item.started' and e['event'].get('item',{}).get('type')=='mcp_tool_call'}
    completed=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    check(cell+':public_attempt_count',len(public_tools)==len(completed)==len(close['tools']))
    intervals=[(started[e['event']['item']['id']],e['perf_ns']) for e in completed]
    check(cell+':public_tool_within_prompt',all(bounds[3]<=a<=b<=bounds[4] for a,b in intervals))
    attempts=[]; prefix=0
    for ordinal, f in enumerate(public_tools,1):
        folder=root/'owner'/f'tool_{ordinal:02d}'
        request=read(folder/'REQUEST.json'); attempt=read(folder/'ATTEMPT.json')
        response=read(folder/('RESPONSE.json' if (folder/'RESPONSE.json').exists() else 'ERROR_RESPONSE.json'))
        check(cell+f':tool{ordinal}_raw_request',request==f['request'])
        check(cell+f':tool{ordinal}_raw_response',response==f['response'])
        check(cell+f':tool{ordinal}_attempt',attempt['attempt']==ordinal and attempt['response_bytes']==f['rx_bytes'])
        prefix+=f['rx_bytes']
        body=response.get('result',{}).get('content',[])
        body_bytes=sum(len(x.get('text','').encode()) for x in body if x['type']=='text')
        args=request['params']['arguments']; code=args.get('code')
        attempts.append({'attempt':ordinal,'name':request['params']['name'],'failed':attempt['is_error'],
                         'handler_started_ns':attempt['started_ns'],'handler_ns':attempt['elapsed_ns'],
                         'public_started_ns':intervals[ordinal-1][0],'public_ended_ns':intervals[ordinal-1][1],
                         'tx_bytes':f['tx_bytes'],'rx_bytes':f['rx_bytes'],'text_utf8_bytes':body_bytes,
                         'cumulative_rx_bytes':prefix,'code_utf8_bytes':len(code.encode()) if code else 0,
                         'arguments':args,'image_blocks':sum(x['type']=='image' for x in body)})
        check(cell+f':tool{ordinal}_budgets',prefix<=1048576 and attempt['elapsed_ns']<30*10**9 and intervals[ordinal-1][1]-intervals[ordinal-1][0]<30*10**9 and (not code or len(code.encode())<=262144))
    scripts=[]
    public_hashes={hashlib.sha256(a['arguments']['code'].encode()).hexdigest() for a in attempts if 'code' in a['arguments']}
    for w in workers[:-1]:
        p=root/'owner/native'/f"call_{w['sequence']}"/'SCRIPT.py'; script=text(p)
        check(cell+':executed_script_hash'+str(w['sequence']),hashlib.sha256(script.encode()).hexdigest()==w['script_sha256'])
        kind='consumer_native' if w['script_sha256'] in public_hashes else ('qa_snapshot' if w['sequence'] in (1,len(workers)-1) else 'product_capture')
        scripts.append({'sequence':w['sequence'],'kind':kind,'utf8_bytes':len(script.encode()),'disk_bytes':p.stat().st_size,'elapsed_ns':w['elapsed_ns']})
    check(cell+':request_limits',len(attempts)<=32 and len(workers)<=128 and all(s['utf8_bytes']<=262144 and s['elapsed_ns']<30*10**9 for s in scripts))
    listing=next(f for f in consumer_frames if f['request']['method']=='tools/list')
    plugin_frames=frames(root/'owner/plugin'); plugin_receipts=[]; traces=[]; work=[]
    if slot['group']=='P':
        product_config=c('owner/product_config.json')
        check(cell+':product_local_budget',product_config['request_budget_s']==product_config['blender']['timeout_s']==30)
        for f in plugin_frames:
            receipt=load(f[ 'path']+'/RECEIPT.json')
            check(cell+':plugin_bytes'+f['path'],receipt['sent_bytes']==f['tx_bytes'] and receipt['received_bytes']==f['rx_bytes'])
            plugin_receipts.append(receipt)
        for r in lines(root/'owner/audit.jsonl'):
            if 'trace' in r:
                t=r['trace'];traces.append({k:t[k] for k in ['trace_id','operation','outcome','duration_ns','duration_semantics','spans','annotations','peak_rss','concurrency']})
            if r.get('event')=='observe':work.append(r.get('task_work'))
        check(cell+':peer_under30',all(p['elapsed_ns']<30*10**9 for p in plugin_receipts))
    for proc, ok in [('consumer',consumer['process_reaped'] and consumer['exit_code']==0),('owner',finish['confirmed'] and finish['exit_code']==0),('native',close['native_close']['process_reaped'] and close['native_close']['exit_code']==0)]:
        check(cell+':exit_'+proc,ok)
    if slot['group']=='P':check(cell+':runtime_exit',close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exit_code']==0)
    counts=collections.Counter(s['kind'] for s in scripts)
    cells.append({**slot,'anonymous_id':mapped['anonymous_id'],'quality':'complete_correct','usage':usage,
                  'full_ns':end-start,'segments_ns':segments,'consumer_wall_ns':consumer['cleanup_end_ns']-consumer['started_ns'],
                  'nested':{'owner_finish_ns':finish['elapsed_ns'],'native_startup_ns':session['startup_ns'],
                            'public_tool_interval_union_ns':union_ns(intervals),'actor_handlers_ns':sum(a['handler_ns'] for a in attempts),
                            'prompt_outside_public_tool_intervals_ns':segments['prompt_to_final']-union_ns(intervals)},
                  'budgets':{'original_cell_start_ns':start,'original_cell_deadline_ns':deadline,'inherited_deadlines':inherited,
                             'native_receipt_deadlines':native_receipts,'consumer_started_ns':consumer['started_ns'],'consumer_deadline_ns':consumer['deadline_ns'],
                             'consumer_turn_elapsed_ns':turns[-1]['perf_ns']-consumer['started_ns'],
                             'prepare_started_ns':launch['prepare_started_ns'],'actor_deadline_ns':actor_deadline,
                             'actor_ready_elapsed_upper_bound_ns':consumer['started_ns']-launch['prepare_started_ns'],
                             'attempts':len(attempts),'host_physical_including_close':len(workers),'host_nonclose':len(workers)-1,
                             'response_prefixes':[a['cumulative_rx_bytes'] for a in attempts], 'max_code_utf8_bytes':max(s['utf8_bytes'] for s in scripts),
                             'product_absolute_cell_deadline_exposed':False if slot['group']=='P' else None},
                  'attempts':attempts,'scripts':scripts,'host_execution_counts':dict(counts),'consumer_frame_counts':dict(collections.Counter(f['request']['method'] for f in consumer_frames)),
                  'consumer_frames_tx_bytes':sum(f['tx_bytes'] for f in consumer_frames),'consumer_frames_rx_bytes':sum(f['rx_bytes'] for f in consumer_frames),
                  'public_schema_rx_bytes':listing['rx_bytes'],'public_schema_tool_count':len(listing['response']['result']['tools']),
                  'plugin_frames':[{k:f[k] for k in ('path','tx_bytes','rx_bytes')}|{'method':f['request']['method']} for f in plugin_frames],
                  'plugin_receipts':plugin_receipts,'traces':traces,'task_work':work,
                  'exits':{'consumer':True,'owner':True,'native':True,'product':True if slot['group']=='P' else None,'thin_client':None},
                  'unmeasured_from_consumer':{k:consumer.get(k) for k in ['provider_requests','fees','resolved_effort','image_tokens']},
                  'provider_retry_observations':consumer['provider_retry_observations']})

groups={}
for group in ('N','P'):
    cc=[c for c in cells if c['group']==group]
    aa=[a for c in cc for a in c['attempts']]
    groups[group]={'cells':[c['cell'] for c in cc],'usage':{k:sum(c['usage'][k] for c in cc) for k in cells[0]['usage']},
                   'full_ns':stats([c['full_ns'] for c in cc]),'prompt_to_final_ns':stats([c['segments_ns']['prompt_to_final'] for c in cc]),
                   'tool_attempts':len(aa),'failed_attempts':sum(a['failed'] for a in aa),
                   'tool_tx_bytes':sum(a['tx_bytes'] for a in aa),'tool_rx_bytes':sum(a['rx_bytes'] for a in aa),
                   'tool_text_utf8_bytes':sum(a['text_utf8_bytes'] for a in aa)}
pairs=[]
for rnd in range(1,4):
    n=next(c for c in cells if c['round']==rnd and c['group']=='N');p=next(c for c in cells if c['round']==rnd and c['group']=='P')
    pairs.append({'round':rnd,'N':n['cell'],'P':p['cell'],'time_reduction_percent':reduction(n['full_ns'],p['full_ns']),
                  'token_reduction_percent':reduction(n['usage']['input_plus_output'],p['usage']['input_plus_output'])})
n,p=groups['N'],groups['P']
comparison={'full_median_reduction_percent':reduction(n['full_ns']['median'],p['full_ns']['median']),
            'input_output_reduction_percent':reduction(n['usage']['input_plus_output'],p['usage']['input_plus_output']),
            'uncached_input_P_increase_percent':100*(p['usage']['uncached_input']-n['usage']['uncached_input'])/n['usage']['uncached_input']}
gate={'all_six_complete_correct':len(cells)==6 and len(n['cells'])==len(p['cells'])==3,
      'median_no_regression':p['full_ns']['median']<=n['full_ns']['median'],
      'input_output_no_regression':p['usage']['input_plus_output']<=n['usage']['input_plus_output'],
      'at_least_10_percent_improvement':comparison['full_median_reduction_percent']>=10 or comparison['input_output_reduction_percent']>=10}
gate['passed']=all(gate.values())
prep=load('PREPARATION_COST.json'); formal=load('FORMAL_PROCESS.json')
preparation_seconds=(datetime.datetime.fromisoformat(prep['freeze_utc'])-datetime.datetime.fromisoformat(prep['recorded_start_utc'])).total_seconds()
historical_root=TREE/'verification/m4_grooved_rail_transfer_001'
historical_ledger=read(historical_root/'PREPARATION_LEDGER.json')
historical_prep=read(historical_root/'worker/PREPARATION.json')
historical_oracle=lines(historical_root/'oracle/RUNS.jsonl')
check('historical_preparation_elapsed',historical_prep['ended_ns']-historical_prep['started_ns']==historical_prep['elapsed_ns'])
historical_window=(datetime.datetime.fromisoformat(historical_ledger['finalizer_input_checks_ended_utc'])-datetime.datetime.fromisoformat(historical_ledger['frozen_utc'])).total_seconds()
check('historical_freeze_window',historical_window==historical_ledger['recorded_freeze_to_finalizer_input_checks_window_s'])
check('historical_oracle_one',len(historical_oracle)==1)
oracle=historical_oracle[0]
historical={'qualification_window_seconds':historical_window,'asset_controller_ns':historical_prep['ended_ns']-historical_prep['started_ns'],
            'nested_builder_ns':historical_prep['builder']['elapsed_ns'],'nested_QA_close_ns':historical_prep['QA_close']['elapsed_ns'],
            'oracle_analysis_ns':oracle['analysis_ended_ns']-oracle['started_ns'],'oracle_with_publication_ns':oracle['publication_ended_ns']-oracle['started_ns'],
            'owned_Blender_sessions':historical_prep['Blender_sessions_started_or_attempted'],'product_processes':historical_prep['product_processes'],
            'model_consumers':historical_prep['models'],'candidate_count_reported':historical_ledger['geometric_candidates'],
            'prior_isolated_install_reused_ns':plan['installation_ready']['elapsed_ns'],
            'scope':'Historical preparation only; windows contain nested stages and cannot be added. Prior installation elapsed is recorded history, not repeated in this batch.'}
cell_total=sum(c['full_ns'] for c in cells);batch_wall=run['batch_ended_ns']-run['batch_started_ns'];formal_wall=formal['ended_ns']-formal['started_ns']
check('batch_wall_recomputed',batch_wall==run['batch_wall_ns'])
check('nested_batch_full_process',cell_total<=batch_wall<=formal_wall)
# Only now compare against the author's result; it did not enter any calculation above.
author=json.loads((BASE/'cost_review_01/cost/RESULTS.json').read_bytes())
author_comparison={'gate':author['gate']['passed']==gate['passed'],
                   'N_median':author['groups']['N']['full_cell_ns']['median']==n['full_ns']['median'],
                   'P_median':author['groups']['P']['full_cell_ns']['median']==p['full_ns']['median'],
                   'N_tokens':author['groups']['N']['usage_totals']['input_plus_output_tokens']==n['usage']['input_plus_output'],
                   'P_tokens':author['groups']['P']['usage_totals']['input_plus_output_tokens']==p['usage']['input_plus_output']}
result={'schema':'independent-grooved-rail-cost-audit-v1','original_commit':ORIGINAL,'implementation_head':EXPECTED_HEAD,
        'quality_seal_sha256':hashlib.sha256(SEAL.read_bytes()).hexdigest(),'denominator':{'cells':6,'arms':2,'per_arm':3,'pairs':3,'distinct_tasks':1,'distinct_scenes':1,'facts_per_cell':13},
        'contract':contract,'cells':cells,'groups':groups,'pairs':pairs,'comparison':comparison,'gate':gate,
        'preparation':{'original':prep,'recorded_local_window_seconds':preparation_seconds,'earlier_reading_coordinator_review_cost':None,'amortization_to_formal_cells':False},
        'historical_preparation':historical,'frozen_limits':limits,
        'batch':{'full_cell_sum_ns':cell_total,'run_models_ns':batch_wall,'run_models_outside_cells_ns':batch_wall-cell_total,
                 'outer_formal_process_ns':formal_wall,'outer_process_outside_run_models_ns':formal_wall-batch_wall,'durations_nested_not_additive':True},
        'author_comparison':author_comparison,'observed_budget_checks_passed':True,
        'limitations':['No currency fee or subscription debit measurement.','No provider request/retry count or provider wire bytes.','Requested model/effort metadata is not resolved-provider identity.',
                       'Six thin-client EXIT receipts absent; do not infer normal thin-client exit from owner/worker closure.',
                       'Product config supplies 30-second cooperative budget, not the full-cell absolute deadline; local internal absolute endpoints are not exposed.',
                       'All observed windows fit original deadlines; cancellation, exhaustion, near-deadline startup/cleanup, or boundary-failure paths were not exercised.',
                       'No independent closed-only or pure inference duration; inclusive trace spans overlap.',
                       'Native TCP/owner attach wire bytes, native algorithm cache/RSS, cache occupancy, and token price-weighted cost are unmeasured.',
                       'Single scene and task, three repeats per arm; no cross-scene or global-discovery denominator.'],
        'new_product_blender_consumer_api_runs':0}
OUT.mkdir(parents=True,exist_ok=True)
for name,value in [('RESULTS.json',result),('INPUTS.json',inputs),('CHECKS.json',checks)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report=[
'# 凹槽六格独立成本与原预算复核', '',
'结论：封存质量 6/6 完整正确、78/78 必需事实成立的前提下，原冻结 useful-benefit 门通过。未发现作者主要成本数值或门限结论的算术误报。货币费用下降、所有内部期限均传递、所有进程正常退出，以及跨场景收益，均不能由本批推出。', '',
f'本检查独立编写标准库脚本，不导入、不执行作者分析。原件固定在 `{ORIGINAL}`，实施树 HEAD `{EXPECTED_HEAD}`；质量封条 SHA256 `{result["quality_seal_sha256"]}`。实际读取 {len(inputs)} 份原件逐份比对 Git blob，并记录 SHA256；{len(checks)} 条断言通过。这些是审计检查数量，不能充作独立样本数。', '',
'独立分母是 1 个场景、1 个指定任务、6 个新消费者上下文、N/P 各 3 格和 3 组配对；质量沿用已封存裁决，本审计不重跑质量。末尾每个 answer_id 的真实 final.txt 字节均与封条摘要对齐。', '',
'## 主门与全部六格', '',
'冻结门：双方各 3/3 完整正确；P 完整格耗时中位数及累计实际 input+output 均不劣于 N，至少一项改善 10%。未排除错误、自纠、启动或关闭成本。', '',
'| 指标 | N | P | P 降幅 |', '|---|---:|---:|---:|',
f'| 完整格中位秒 | {n["full_ns"]["median"]/1e9:.7f} | {p["full_ns"]["median"]/1e9:.7f} | {comparison["full_median_reduction_percent"]:.6f}% |',
f'| 累计 input+output | {n["usage"]["input_plus_output"]} | {p["usage"]["input_plus_output"]} | {comparison["input_output_reduction_percent"]:.6f}% |', '',
'| 格 | 组 | 轮 | 完整秒 | prompt→final 秒 | input | cached | output | reasoning | 工具尝试/错误 |',
'|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for c in cells:
    u=c['usage']; report.append(f'| {c["cell"]} | {c["group"]} | {c["round"]} | {c["full_ns"]/1e9:.7f} | {c["segments_ns"]["prompt_to_final"]/1e9:.7f} | {u["input_tokens"]} | {u["cached_input_tokens"]} | {u["output_tokens"]} | {u["reasoning_output_tokens"]} | {len(c["attempts"])}/{sum(a["failed"] for a in c["attempts"])} |')
report+=['', 'usage 只取原始 events.jsonl 内唯一 turn.completed 的最终累计值，逐项核 CONSUMER/usage_rows；cached 已在 input 内，reasoning 已在 output 内，cache-write 为 0。未把子项再次累加。', '',
f'未缓存 input（input−cached）：N {n["usage"]["uncached_input"]}，P {p["usage"]["uncached_input"]}，P 增加 {comparison["uncached_input_P_increase_percent"]:.6f}%；output 为 6901→1566。故 token 主门成立与货币费用更低必须分开；实际费用/价格/订阅扣账未测。', '',
'| 轮 | N/P | 完整耗时降幅 | token 降幅 |', '|---|---|---:|---:|']
for pair in pairs: report.append(f'| {pair["round"]} | {pair["N"]}/{pair["P"]} | {pair["time_reduction_percent"]:.6f}% | {pair["token_reduction_percent"]:.6f}% |')
report+=['', '## 完整时间与重叠', '',
'起点为每格输入核查之前的 cell_started_ns，终点为 owner finish 后的 cell_ended_ns。八段相减逐格精确回加完整耗时；actor/native 启动、QA 快照、产品握手、工具执行、owner finish 以及 trace 子区间均已嵌套，不能再相加。', '',
'| 格 | consumer 前 | 启动到 popen | popen→prompt | prompt→final | final→turn | turn→exit | exit→cleanup | cleanup→格末 |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for c in cells: report.append('| '+c['cell']+' | '+' | '.join(f'{v/1e9:.7f}' for v in c['segments_ns'].values())+' |')
report+=['',
f'六格合计 {cell_total/1e9:.7f}s；run_models 总窗 {batch_wall/1e9:.7f}s，其中格外初始化/记账 { (batch_wall-cell_total)/1e9:.7f}s；外层 formal process {formal_wall/1e9:.7f}s，另有 {(formal_wall-batch_wall)/1e9:.7f}s 外层开销。这三个量嵌套，不能相加。完整格不含随后 accounting 发布；run_models 覆盖最后一次逐格发布，但不含最终 timing-summary 发布/调用方工作。', '',
'公共工具区间按原始 item.started/item.completed 配对并求并集；prompt→final 减并集只是区间外等待，包含 provider/client 等待和未计量工作，不能叫纯推理时间。产品 trace 明示 inclusive，RESULTS 原样保存各父子 span；没有独立 closed-only span，不按大 span 推定 closed 耗时。', '',
'## 原期限与数值预算', '',
'固定预算：450 秒 consumer、570 秒完整格、40 秒 actor 就绪、32 个工具尝试、128 个 host RPC、30 秒单工具、1 MiB 累计业务响应、256 KiB 单段代码、零初图与新图。全部实际窗口和累积前缀均在预算内。', '',
'| 格 | 原 cell_started_ns | 原整格 deadline_ns | consumer turn 秒 | actor 就绪上界秒 | 工具/host含close | 响应累计字节 | 最大执行代码字节 |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for c in cells:
    b=c['budgets'];report.append(f'| {c["cell"]} | {b["original_cell_start_ns"]} | {b["original_cell_deadline_ns"]} | {b["consumer_turn_elapsed_ns"]/1e9:.7f} | {b["actor_ready_elapsed_upper_bound_ns"]/1e9:.7f} | {b["attempts"]}/{b["host_physical_including_close"]} | {b["response_prefixes"][-1]} | {b["max_code_utf8_bytes"]} |')
report+=['',
'逐格重新生成起点+570s 的绝对截止，再比对 RUN_RESULT、ACTOR_LAUNCH/CONFIG、ENDPOINT、native CONFIG/SESSION/READY、INITIAL/FINAL 与业务 native 回执、native close response、WORKER_CLOSED。全部相等，没有观察到重置格期限。consumer 的 450s 从自身原始 started_ns 起算；actor 的 40s 从 prepare_started_ns 起算并取整格截止的较早者。全部原始 worker 起止、consumer exit、worker closed、owner finish 均发生在各自原期限内。', '',
'产品的配置只显露 request_budget_s=30 和 host timeout=30，没有直接接收整格绝对截止。产品内部 cooperative deadline 的绝对原点/终点未记录；外层 attach 与 native worker 持有格期限。实际窗口小于各限值，只证明这些保存的运行没有超限，不能升级为所有层严格期限继承或耗尽/超时/关闭边界认证。也没有把 CLI MCP 的外层 40s 等待当成新的单工具预算；实际 actor/public/worker/peer 窗口均单独核在 30s 内。', '',
'1 MiB 仅计 actor tools/call 业务响应，按原始 RX.bin 的全部 JSON-RPC 回包字节（含错误、封装和换行）逐次累计，tools/list 与控制元数据另列。128 是 native helper 的非 close 分支限制；实际包含 close 也仅 N 每格 6、P 每格 4，非 close 分别 5/3。Worker SCRIPT.py 的 CRLF 磁盘字节与执行字符串字节不同，先归一换行并与 WORKER_EVENTS.script_sha256 对上，再使用真实 UTF-8 执行字节核 256 KiB。', '',
'## 请求与包络', '',
'| 组 | 公共工具 | 错误 | 原始工具 TX 字节 | 原始工具 RX 字节 | content.text UTF-8 字节 |', '|---|---:|---:|---:|---:|---:|']
for group,g in groups.items():report.append(f'| {group} | {g["tool_attempts"]} | {g["failed_attempts"]} | {g["tool_tx_bytes"]} | {g["tool_rx_bytes"]} | {g["tool_text_utf8_bytes"]} |')
report+=['',
'每条公共 TX/RX 与 owner REQUEST/RESPONSE 结构逐项一致，并与原始模型工具事件计数对齐。N 9 个原生业务调用；P 4 个 observe 尝试，其中 grc03 首次 unsupported nearest_witness 拒绝，随后同格修正成功。错误响应、自纠 token/等待、后续成功请求全部保留，没有按“成功调用数”缩分母。P 三次成功均未原生 fallback。', '',
'每格消费者工具清单原始 RX：N 575 B、P 12785 B；工具个数分别 1/2。P 的内层产品 stdio initialize/list/ping/observe 与消费者外层帧不是新增模型请求，两层包络独立记录，不能求和后称“模型输入”。N/P 的 host 执行各包含每格两次 QA 快照；P 的成功 observe 每格一次 capture，拒绝请求没有 host 几何采集。实际同一请求跨层出现，不能把层计数相加成独立业务数。', '',
'## 准备历史单列', '',
f'本批消费准备记录从 WORK_ORDER 到 FREEZE 为 {preparation_seconds:.6f}s；其 model consumers、Blender sessions、live product processes、重装和 smoke 均记录为 0。这个口径不是全部历史投入。', '',
f'先前资格制备窗口为 {historical_window:.6f}s（冻结到 finalizer 输入核查，排除随后发布/Git/回报），实际资产控制器 {historical["asset_controller_ns"]/1e9:.7f}s，包含 builder {historical["nested_builder_ns"]/1e9:.7f}s 与 QA close {historical["nested_QA_close_ns"]/1e9:.7f}s，共 2 个 Blender 进程；oracle 一次，含发布 {historical["oracle_with_publication_ns"]/1e9:.7f}s，分析 {historical["oracle_analysis_ns"]/1e9:.7f}s 嵌套其中。资格记录候选 1、构建失败 0、产品预试/消费者/图片 0；本审计只核该历史记录，不重执行。', '',
f'更早隔离安装复用记录 {historical["prior_isolated_install_reused_ns"]/1e9:.7f}s，没有当作本批新安装重复收费。上述准备、执行、协调与审核窗口分开；未取得协调者/审核模型用量或费用，不摊成零、不加入正式 N/P 主门。', '',
'## 阻塞、误报与未测项', '',
'本批 observed-cost 冻结门没有阻塞，也未发现作者核心数值误报。原件 native worker 最后一条 status=unknown 对应 close 接收，不是第七格或新的执行失败；真实 worker close response、WORKER_CLOSED 与 owned process reap 另有证据。反过来，不能把这些退出证明用于补齐薄 stdio 客户端的 EXIT：6/6 薄客户端缺 EXIT，正常退出仍 unknown。', '',
'不接受以下超出证据的结论：费用已下降；所有内部 deadline 已严格继承；unknown 被归零；全部准备只耗费消费准备窗口；非工具时间就是模型推理；额外 closed 的独立成本已量化；在任意场景/全场发现均有相同收益。', '',
'未测项包括货币费用、订阅扣账、provider 请求/重试次数与网络字节、resolved model/effort、native/owner TCP 实际包络、独立 closed 和 pure inference 时间、缓存占用及 native RSS。产品 peak RSS 是进程生命周期高水位，不是本请求增量。stderr 未见重试不能证明 provider 零重试。', '',
'预算耗尽、卡死、接近原截止的初始化/纠错/关闭、取消与断管等极限路径未在这六格执行。质量与数值审计通过不扩展成这些路径的认证。', '',
'复现：使用授权 Python，以 `-I -B -X utf8` 执行本目录 `recompute_costs.py`；只读原件、写本目录结果。RESULTS.json 保存完整计量，INPUTS.json 保存读取输入摘要，CHECKS.json 保存逐项断言。本次新增产品、Blender、消费者、模型 API 调用均为 0。',
]
(OUT/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
print(json.dumps({'gate':gate,'groups':groups,'comparison':comparison,'batch':result['batch'],'preparation_seconds':preparation_seconds,'source_files':len(inputs),'checks':len(checks),'author_comparison':author_comparison},ensure_ascii=False,indent=2))
