"""Recompute nine-cell costs from sealed raw records only. No runtime/model/project imports."""
import argparse, collections, hashlib, json, statistics, subprocess, time
from pathlib import Path

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HEAD='de35ceda1f5e3f5af2c9ec02f0e4646808f417c2'
BATCH=WT/'verification/m4_selected_geometry_consumption_001'
HERE=Path(__file__).resolve().parent
SEAL=HERE.parent/'QUALITY_SEAL.json'
SEAL_SHA='dfffad47ef02eea55389f617882a55833f1a6a46ae29978abf4b61383acadc64'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(o):return json.dumps(o,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def summary(v):return {'count':len(v),'minimum':min(v),'median':statistics.median(v),'maximum':max(v),'total':sum(v),'raw':v}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=HERE/'RESULTS.json');args=parser.parse_args()
    begun=time.perf_counter_ns();checks=[];inputs={}
    def ck(name,passed,detail=None):checks.append({'check':name,'passed':bool(passed),'detail':detail})
    def raw(path):
        path=Path(path);data=path.read_bytes();inputs[str(path)]=sha(data);return data
    def rd(path):return json.loads(raw(path))
    def git(*argv):return subprocess.run(['git','-C',str(WT),*argv],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    ck('fixed_HEAD',git('rev-parse','HEAD').decode().strip()==HEAD);status=git('status','--short').decode();ck('clean_worktree',status=='')
    seal=rd(SEAL);ck('quality_seal_before_unblind',inputs[str(SEAL)]==SEAL_SHA and seal['source_commit']==HEAD and seal['root_complete_correct']==seal['fresh_independent_complete_correct']==seal['denominator']==9)
    for pin in seal['files']:
        data=raw(SEAL.parent/pin['path']);ck('quality_fixed:'+pin['path'],len(data)==pin['bytes'] and sha(data)==pin['sha256'])
    plan=rd(BATCH/'PLAN.json');contract=rd(BATCH/'BENEFIT_CONTRACT.json');go=rd(BATCH/'GO.json');batch=rd(BATCH/'RUN_RESULT.json');mapping=rd(BATCH/'private/ANON_MAP.json')['rows']
    ck('map_and_PLAN_binding',sha(raw(BATCH/'private/ANON_MAP.json'))==plan['private_anonymous_map_sha256'] and sha(raw(BATCH/'PLAN.json'))==go['plan_sha256'])
    ck('nine_ordered_cells_no_replacements',[r['cell'] for r in batch['records']]==[r['cell'] for r in mapping]==[r['cell'] for r in plan['sequence']] and len(mapping)==9 and batch['started_cells']==9 and batch['all_planned_dispatched'] and batch['no_replacements'] and batch['stop'] is None)
    rows=[]
    for rec,m in zip(batch['records'],mapping):
        cell=rec['cell'];folder=BATCH/'cells'/cell;consumer=rd(folder/'CONSUMER.json');finish=rd(folder/'OWNER_FINISH.json');close=rd(folder/'owner/CLOSE.json');launch=rd(folder/'ACTOR_LAUNCH.json')
        ck(cell+'_map_and_summary',rec['group']==consumer['external_group']==m['group'] and rec['round']==m['round']==consumer['round'] and rec['consumer']==consumer and rec['finish']==finish==consumer['owner_finish'] and finish['close']==close)
        events=[json.loads(line) for line in raw(folder/'events.jsonl').splitlines() if line]
        complete=[e for e in events if e['event']['type']=='turn.completed'];usage=[e['event']['usage'] for e in complete]
        ck(cell+'_actual_single_turn_usage',len(complete)==1 and usage==consumer['usage_rows'] and usage[0]==consumer['usage'])
        u=usage[0]
        ck(cell+'_token_fields',all(type(u[k]) is int and u[k]>=0 for k in ['input_tokens','output_tokens','cached_input_tokens','cache_write_input_tokens','reasoning_output_tokens']) and u['cached_input_tokens']<=u['input_tokens'] and u['reasoning_output_tokens']<=u['output_tokens'])
        final_events=[e for e in events if e['event']['type']=='item.completed' and e['event']['item'].get('type')=='agent_message' and e['event']['item'].get('text')==consumer['final']]
        ck(cell+'_final_event_timestamp',len(final_events)==1 and final_events[0]['perf_ns']==consumer['final_received_ns'] and complete[0]['perf_ns']==consumer['turn_completed_ns'])
        tool_events=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
        started_tool=[e for e in events if e['event']['type']=='item.started' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
        normalized=[{'perf_ns':e['perf_ns'],**e['event']} for e in tool_events]
        ck(cell+'_raw_tools_not_double_counted',normalized==consumer['tool_calls'] and len(started_tool)==len(tool_events) and [e['event']['item']['id'] for e in started_tool]==[e['event']['item']['id'] for e in tool_events])
        tools=close['tools'];ck(cell+'_owner_tool_denominator',len(tools)==close['tool_attempts']==len(tool_events))
        toolrows=[]
        for number,(attempt,event) in enumerate(zip(tools,tool_events),1):
            f=folder/'owner'/f'tool_{number:02}';saved=rd(f/'ATTEMPT.json');request=rd(f/'REQUEST.json');response=rd(f/'RESPONSE.json');item=event['event']['item']
            ck(cell+f'_tool_{number}_source',saved==attempt and item['tool']==attempt['name']==request['params']['name'] and item['arguments']==request['params']['arguments'])
            ck(cell+f'_tool_{number}_cost',len(encoded(response))==attempt['response_bytes']==attempt['produced_response_bytes'] and attempt['elapsed_ns']>=0)
            ck(cell+f'_tool_{number}_result',attempt['exception'] is None and not attempt['is_error'] and item['status']=='completed' and item['result']['content']==response['result']['content'])
            code=request['params']['arguments'].get('code')
            toolrows.append({'attempt':number,'name':attempt['name'],'elapsed_ns':attempt['elapsed_ns'],'response_bytes':attempt['response_bytes'],
                'native_code_bytes':len(code.encode()) if isinstance(code,str) else 0,'public_started_ns':started_tool[number-1]['perf_ns'],'public_completed_ns':event['perf_ns']})
        totals=rd(folder/'owner/TOOLS.json');ck(cell+'_owner_cost_totals',totals['attempts']==totals['calls']==len(tools) and totals['tools']==tools and totals['wire_tool_bytes']==sum(t['response_bytes'] for t in tools))
        worker=[json.loads(line) for line in raw(folder/'owner/native/WORKER_EVENTS.jsonl').splitlines() if line]
        ck(cell+'_worker_rpc_complete',len(worker)==len(tools)+3 and [e['sequence'] for e in worker]==list(range(1,len(worker)+1)) and all(e['status']=='completed' for e in worker[:-1]) and worker[-1]['status']=='unknown')
        # The two extra business reads are initial and final validation; close is the final RPC.
        native=close['native_close'];closed=rd(folder/'owner/native/WORKER_CLOSED.json')
        ck(cell+'_native_actual_owned_exit',close['worker_closed']==closed and native['response']['status']=='closed' and native['exit_code']==0 and native['process_reaped'] and native['source_file_unchanged'] and native['protected_files_unchanged'] and closed['poisoned'] is False and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'])
        ck(cell+'_owner_exit_and_deadline',finish['confirmed'] and finish['exit_code']==0 and close['confirmed'] and not close['errors'] and finish['actor_pid']==launch['pid'] and close['actor_parent_pid']==launch['pid'] and closed['original_deadline_ns']==rec['worker_deadline_ns'])
        plugin_stdio=0;plugin_tx=plugin_rx=0;plugin_launcher_confirmed=None
        if rec['group']!='N':
            plugin=folder/'owner/plugin';pc=rd(plugin/'CLOSE.json');ps=rd(plugin/'START.json');pr=rd(plugin/'RPC.json')
            ck(cell+'_product_launcher_close',pc==close['plugin_close'] and pc['launcher_pid']==ps['launcher_pid'] and pc['confirmed'] and pc['process_reaped'] and pc['exit_code']==0 and pc['reader_stopped'] and pc['error'] is None and pc['ended_ns']<=close['ended_ns'])
            plugin_launcher_confirmed=True;plugin_stdio=len(pr['requests'])
            ck(cell+'_product_rpc_count',plugin_stdio==4+sum(t['name']!='execute_blender_code' for t in tools) and not pr['poisoned'])
            for number,rpc in enumerate(pr['requests'],1):
                f=plugin/f'{number:03}';tx=raw(f/'TX.bin');rx=raw(f/'RX.bin') if (f/'RX.bin').exists() else b''
                ck(cell+f'_product_wire_{number}',len(tx)==rpc['sent_bytes'] and len(rx)==rpc['received_bytes'] and rpc['send_confirmed'] and rpc['error'] is None)
                plugin_tx+=len(tx);plugin_rx+=len(rx)
            ck(cell+'_product_stdio_bytes',plugin_tx==pr['tx_bytes'] and plugin_rx==pr['rx_bytes'])
        else:ck(cell+'_native_has_no_product',close['plugin_close'] is None and not (folder/'owner/plugin').exists())
        bridges=list((folder/'attachments').glob('bridge_*'));bridge_tx=bridge_rx=bridge_stdio=0;schema_bytes=[];raw_bridge_calls=0
        for bridge in bridges:
            rd(bridge/'STARTED.json')
            for f in sorted(bridge.iterdir()):
                if not f.is_dir():continue
                tx=raw(f/'TX.bin');message=json.loads(tx);rx=raw(f/'RX.bin') if (f/'RX.bin').exists() else b''
                bridge_tx+=len(tx);bridge_rx+=len(rx);bridge_stdio+=1
                if message['method']=='tools/list':schema_bytes.append(len(rx))
                if message['method']=='tools/call':raw_bridge_calls+=1
        ck(cell+'_raw_bridge_tools_match',raw_bridge_calls==len(tools))
        bc=consumer['bridge_cleanup']
        ck(cell+'_thin_exit_unknown_retained',len(bridges)==1 and bc['confirmed'] is None and bc['receipt_status']=='unknown' and bc['missing_exit_count']==1 and not any((p/'EXIT.json').exists() for p in bridges))
        full=rec['cell_ended_ns']-rec['cell_started_ns'];cw=consumer['cleanup_end_ns']-consumer['started_ns'];pf=consumer['final_received_ns']-consumer['prompt_submitted_ns']
        ck(cell+'_time_recomputed',full==rec['full_cell_wall_ns']==consumer['total_task_wall_ns'] and cw==consumer['wall_ns'] and pf==consumer['prompt_to_final_ns'])
        ck(cell+'_full_cell_includes_closed_owner',rec['cell_started_ns']==launch['cell_started_ns']<=consumer['started_ns']<=consumer['cleanup_end_ns']<=close['ended_ns']<=rec['cell_ended_ns'] and closed['closed_ns']<=close['ended_ns'] and consumer['process_reaped'] and consumer['exit_code']==0 and consumer['readers_stopped'])
        ck(cell+'_no_omitted_errors_or_fee_zero',not rec['errors'] and not consumer['errors'] and not consumer['unexpected_tool_deviations'] and consumer['valid_completion'] and consumer['fees'] is None and consumer['provider_requests'] is None)
        ck(cell+'_image_count',consumer['input_image_count']==1 and consumer['input_image_bytes']==1185069 and consumer['public_image_count']==0 and close['zero_new_images_budget_met'])
        row={'cell':cell,'group':m['group'],'round':m['round'],'anonymous_id':m['anonymous_id'],'quality_complete_correct':True,
            'full_cell_ns':full,'consumer_ns':cw,'prompt_to_final_ns':pf,'pre_consumer_setup_ns':consumer['started_ns']-rec['cell_started_ns'],
            'post_consumer_close_ns':rec['cell_ended_ns']-consumer['cleanup_end_ns'],'final_to_cleanup_ns':consumer['cleanup_end_ns']-consumer['final_received_ns'],
            'last_tool_to_final_ns':consumer['final_received_ns']-tool_events[-1]['perf_ns'],'usage':u,'input_plus_output_tokens':u['input_tokens']+u['output_tokens'],
            'uncached_input_tokens_arithmetic':u['input_tokens']-u['cached_input_tokens'],'tool_attempts':len(tools),'tool_counts':dict(collections.Counter(t['name'] for t in tools)),
            'tool_owner_elapsed_ns':sum(t['elapsed_ns'] for t in tools),'tool_response_bytes':sum(t['response_bytes'] for t in tools),'native_code_bytes':sum(t['native_code_bytes'] for t in toolrows),
            'tools':toolrows,'worker_RPC':len(worker),'worker_RPC_scope':{'initial_validation':1,'consumer_tool_requests':len(tools),'final_validation':1,'close':1},
            'product_stdio_messages':plugin_stdio,'product_stdio_tx_bytes':plugin_tx,'product_stdio_rx_bytes':plugin_rx,
            'thin_stdio_messages':bridge_stdio,'thin_stdio_tx_bytes':bridge_tx,'thin_stdio_rx_bytes':bridge_rx,'tools_list_response_wire_bytes':schema_bytes,
            'observed_provider_retry_messages':len(consumer['provider_retry_observations']),'actual_provider_request_count':None,'fees':None,'image_tokens':consumer['image_tokens'],
            'closure':{'consumer_launcher_exit0':True,'actor_launcher_exit0':True,'native_owned_exit0':True,'product_launcher_exit0':plugin_launcher_confirmed,
                'thin_client_EXIT_confirmed':None,'unmeasured_inner_runtime_exit':'Not separately recorded by this historical formal runner; launcher/owner receipts retained.'}}
        rows.append(row)
    groups={}
    for group in ('N','P','G'):
        chosen=[r for r in rows if r['group']==group];ck(group+'_three_quality_fixed_cells',len(chosen)==3)
        scalars=['full_cell_ns','consumer_ns','prompt_to_final_ns','pre_consumer_setup_ns','post_consumer_close_ns','final_to_cleanup_ns','last_tool_to_final_ns',
            'input_plus_output_tokens','tool_attempts','tool_owner_elapsed_ns','tool_response_bytes','native_code_bytes','worker_RPC','product_stdio_messages',
            'product_stdio_tx_bytes','product_stdio_rx_bytes','thin_stdio_messages','thin_stdio_tx_bytes','thin_stdio_rx_bytes']
        groups[group]={'cells':[r['cell'] for r in chosen],'quality_complete_correct':3,'metrics':{k:summary([r[k] for r in chosen]) for k in scalars},
            'usage':{k:summary([r['usage'][k] for r in chosen]) for k in rows[0]['usage']},'tool_counts':dict(sum((collections.Counter(r['tool_counts']) for r in chosen),collections.Counter())),'fees':None}
    comparisons=[];rounds=[]
    for reference in ('P','N'):
        gt=groups['G']['metrics']['full_cell_ns']['median'];rt=groups[reference]['metrics']['full_cell_ns']['median']
        gu=groups['G']['metrics']['input_plus_output_tokens']['total'];ru=groups[reference]['metrics']['input_plus_output_tokens']['total']
        time_ok=gt<=rt;token_ok=gu<=ru;meaningful=gt*10<=rt*9 or gu*10<=ru*9
        comparisons.append({'reference':reference,'G_full_cell_median_ns':gt,'reference_full_cell_median_ns':rt,'time_ratio':gt/rt,'time_change_fraction':gt/rt-1,
            'G_total_input_plus_output':gu,'reference_total_input_plus_output':ru,'token_ratio':gu/ru,'token_change_fraction':gu/ru-1,
            'time_nonincrease':time_ok,'tokens_nonincrease':token_ok,'one_improvement_at_least_10_percent':meaningful,'quality_gate':True,
            'passes_frozen_cost_gate':time_ok and token_ok and meaningful,'interpretation':'tradeoff' if time_ok!=token_ok else 'both improve but material threshold not reached' if not meaningful else 'passes'})
        for round_id in (1,2,3):
            g=next(r for r in rows if r['group']=='G' and r['round']==round_id);r=next(r for r in rows if r['group']==reference and r['round']==round_id)
            rounds.append({'round':round_id,'reference':reference,'G_cell':g['cell'],'reference_cell':r['cell'],'G_minus_reference_ns':g['full_cell_ns']-r['full_cell_ns'],
                'time_ratio':g['full_cell_ns']/r['full_cell_ns'],'G_minus_reference_tokens':g['input_plus_output_tokens']-r['input_plus_output_tokens'],
                'token_ratio':g['input_plus_output_tokens']/r['input_plus_output_tokens'],'G_minus_reference_calls':g['tool_attempts']-r['tool_attempts']})
    formal=rd(BATCH/'formal/PROCESS.json');preparation=rd(BATCH/'PREPARATION_COST.json');sum_cells=sum(r['full_cell_ns'] for r in rows)
    ck('batch_time_and_serial_order',batch['batch_ended_ns']-batch['batch_started_ns']==batch['batch_wall_ns'] and all(a['cell_ended_ns']<=b['cell_started_ns'] for a,b in zip(batch['records'],batch['records'][1:])))
    scopes={'formal_batch_ns':batch['batch_wall_ns'],'sum_full_cells_ns':sum_cells,'formal_outside_cells_ns':batch['batch_wall_ns']-sum_cells,
        'formal_wrapper_ns':formal['ended_ns']-formal['started_ns'],'formal_wrapper_scope':'execute_once entry through driver return; final publication tail excluded',
        'preparation':preparation,'preparation_review_total_time_ns':None,'quality_review_total_time_ns':None,'post_unblind_review_total_time_ns':None,
        'review_token_usage':None,'review_fees':None,'known_scope_warning':'Preparation program windows overlap preparation chat; review orchestration/quality/unblind costs lack one complete ledger. Never add overlapping windows or call formal batch full R&D cost.'}
    # Bind only inputs actually inspected, using the fixed commit in one batch read.
    rels=sorted({Path(p).relative_to(WT).as_posix() for p in inputs if Path(p).is_relative_to(WT)})
    data=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(HEAD+':'+p+'\n' for p in rels).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    pos=0;bad=[]
    for p in rels:
        end=data.index(b'\n',pos);oid,kind,size=data[pos:end].decode().split();size=int(size);blob=data[end+1:end+1+size];pos=end+size+2
        if kind!='blob' or sha(blob)!=sha((WT/p).read_bytes()):bad.append(p)
    ck('all_used_source_records_match_fixed_Git',not bad,{'files':len(rels),'mismatches':bad})
    ck('source_and_quality_seal_unchanged',status==git('status','--short').decode() and sha(SEAL.read_bytes())==SEAL_SHA)
    failed=[c for c in checks if not c['passed']]
    result={'HEAD':HEAD,'quality_seal_sha256':SEAL_SHA,'quality_changed':False,'audit_passed':not failed,'check_count':len(checks),'failed_checks':failed,'checks':checks,
        'inputs':inputs,'cells':rows,'groups':groups,'comparisons':comparisons,'per_round_contrasts':rounds,'cost_scopes':scopes,
        'cost_advancement_gate_passed':all(c['passes_frozen_cost_gate'] for c in comparisons),'mechanism_verdict':'Separate reviewer; not inferred from lower call counts.',
        'token_semantics':'Use actual turn.completed input_tokens+output_tokens. cached_input and reasoning_output are subsets and are never added twice; dollars unknown.',
        'new_model_Blender_product_calls':0,'pure_audit_program_elapsed_ns':time.perf_counter_ns()-begun,
        'limitations':['Three repeated consumers per group on one fixed scene, not three independent tasks.','No price, exact provider request count or complete review/coordinator-cost ledger is exposed.','All nine thin-client EXIT receipts remain unknown; do not substitute zero cost or successful EXIT.','Measured owner/native lifecycle and launcher exits are included in each full-cell boundary; internal runtime exit is not separately witnessed by this reused runner.']}
    with args.output.open('x',encoding='utf8',newline='\n') as out:json.dump(result,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n')
    print(json.dumps({'audit_passed':not failed,'checks':len(checks),'failed':failed,'comparisons':comparisons,'output':str(args.output)},ensure_ascii=False))
    return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
