"""Read saved originals only. No product import, model call or Blender execution."""
from pathlib import Path
import datetime, hashlib, json, statistics

B=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001')
O=Path(__file__).parent
HASHES={}
def blob(p):
    raw=p.read_bytes();HASHES[str(p)]=hashlib.sha256(raw).hexdigest();return raw
def read(p):return json.loads(blob(p))
def lines(p):return [json.loads(l) for l in blob(p).splitlines() if l.strip()]
def enc(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
def stats(v):return dict(n=len(v),sum=sum(v),median=statistics.median(v),min=min(v),max=max(v))
def frames(folder,private=False):
    rows=[]
    for p in sorted(folder.glob('*/TX.bin')):
        tx=blob(p);q=json.loads(tx);rx=blob(p.with_name('RX.bin')) if p.with_name('RX.bin').exists() else b''
        if 'id' in q:assert rx and json.loads(rx)['id']==q['id']
        if private:
            receipt=read(p.with_name('RECEIPT.json'))
            assert receipt['sent_bytes']==len(tx) and receipt['received_bytes']==len(rx) and receipt['error'] is None
        rows.append(dict(method=q['method'],has_id='id' in q,tx_bytes=len(tx),rx_bytes=len(rx)))
    return rows

seal=read(Path('D:/hefe/verification/fixes/20261111_m4_local_consumption_quality_review/QUALITY_SEAL.json'))
assert seal['root_complete_correct']==seal['independent_complete_correct']==9
plan=read(B/'PLAN.json');contract=read(B/'BENEFIT_CONTRACT.json');run=read(B/'RUN_RESULT.json')
assert HASHES[str(B/'PLAN.json')]=='036a091cfc69a5cb085d5d71e649f7d2673967fb3be5552a6669e2e724117efb'
mapping=read(B/'private/ANON_MAP.json')['rows'];seq=read(B/'SEQUENCE.json')
assert len(run['records'])==run['started_cells']==run['maximum_consumers']==9
assert run['all_planned_dispatched'] and run['no_replacements'] and run['stop'] is None
assert [r['group'] for r in run['records']]==['N','P0','P1','P0','P1','N','P1','N','P0']
rows=[]
for r in run['records']:
    p=B/'cells'/r['cell'];c=read(p/'CONSUMER.json');close=read(p/'owner/CLOSE.json');finish=read(p/'OWNER_FINISH.json')
    assert c==r['consumer'] and finish==r['finish'] and finish['close']==close
    assert r['cell_ended_ns']-r['cell_started_ns']==r['full_cell_wall_ns']==c['total_task_wall_ns']
    assert c['cleanup_end_ns']-c['started_ns']==c['wall_ns']
    assert c['started_ns']-r['cell_started_ns']==c['pre_consumer_setup_ns']
    assert c['final_received_ns']-c['prompt_submitted_ns']==c['prompt_to_final_ns']
    assert c['deadline_ns']-c['started_ns']==450*10**9 and r['worker_deadline_ns']-r['cell_started_ns']==570*10**9
    assert c['status']=='completed' and c['valid_completion'] and c['safe_to_continue'] and r['within_570s']
    assert c['process_reaped'] and c['exit_code']==0 and not c['deadline_timer_fired'] and not c['mutation_unknown']
    assert not (r['errors'] or c['errors'] or c['unexpected_tool_deviations'] or c['bridge_protocol_errors'] or close['errors'])
    assert finish['confirmed'] and close['confirmed'] and close['native_close']['response']['status']=='closed'
    assert close['native_close']['process_reaped'] and close['native_close']['exit_code']==0
    assert close['asset_unchanged'] and close['geometry_unchanged'] and close['zero_new_images_budget_met']
    ev=lines(p/'events.jsonl');turns=[e for e in ev if e['event']['type']=='turn.completed'];assert len(turns)==1
    assert turns[0]['event']['usage']==c['usage'] and c['usage_rows']==[c['usage']]
    finals=[e for e in ev if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
    assert finals[-1]['perf_ns']==c['final_received_ns'] and finals[-1]['event']['item']['text']==c['final']
    tool_events=[e for e in ev if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    owner=[]
    for td in sorted((p/'owner').glob('tool_*')):
        a=read(td/'ATTEMPT.json');q=read(td/'REQUEST.json');response=read(td/'RESPONSE.json')
        assert a['response_bytes']==len(enc(response)) and not a['is_error'] and a['exception'] is None
        owner.append(dict(**a,code_bytes=len(q['params']['arguments'].get('code','').encode()),content_text_bytes=sum(len(t.get('text','').encode()) for t in response['result'].get('content',[]))))
    assert len(owner)==len(tool_events)==len(c['tool_calls'])==close['tool_attempts']
    toolsummary=read(p/'owner/TOOLS.json');assert sum(a['response_bytes'] for a in owner)==toolsummary['wire_tool_bytes']
    public=[];missing_exit=0
    for bridge in (p/'attachments').glob('bridge_*'):
        read(bridge/'STARTED.json');missing_exit+=not (bridge/'EXIT.json').exists();public+=frames(bridge)
    assert missing_exit==c['bridge_cleanup']['missing_exit_count']
    private=[]
    if (p/'owner/plugin/RPC.json').exists():
        rpc=read(p/'owner/plugin/RPC.json');private=frames(p/'owner/plugin',True)
        assert len(private)==len(rpc['requests']) and not rpc['poisoned']
        assert sum(f['tx_bytes'] for f in private)==rpc['tx_bytes'] and sum(f['rx_bytes'] for f in private)==rpc['rx_bytes']
    worker=lines(p/'owner/native/WORKER_EVENTS.jsonl');execs=[w for w in worker if 'script_sha256' in w];ends=[w for w in worker if 'script_sha256' not in w]
    assert len(ends)==1 and ends[0]['sequence']==max(w['sequence'] for w in worker)
    assert all(w['status']=='completed' and w['script_error'] is None for w in execs)
    assert all(not w['changed_or_new_PNG_files'] and w['render_events_before']==w['render_events_after']==0 for w in execs)
    scripts=list((p/'owner/native').glob('call_*/SCRIPT.py'));assert len(scripts)==len(execs)
    session=read(p/'owner/native/SESSION.json');assert session['deadline_ns']==r['worker_deadline_ns']
    identity=read(p/'owner/IDENTITY.json');config=read(p/'ACTOR_CONFIG.json')
    assert config['external_group']==r['group']==c['external_group']
    assert identity['asset_sha256']==plan['inputs']['scene_sha256'] and identity['private_geometry_warmup'] is False
    if r['group']!='N':
        assert identity['runtime_identity']['source_sha256']==config['source_sha256']==plan['arms'][r['group']]['source_sha256']
        assert identity['runtime_identity']['source_file_count']==137 and identity['runtime_identity']['identity_check']['compatible']
    assert c['input_sha256']==plan['inputs']['prompt_sha256'] and c['initial_image_unchanged'] and c['input_image_count']==1
    assert c['input_image_bytes']==1185069 and c['public_image_count']==0
    assert c['image_delivery']['initial_attachment_in_argv'] and c['image_delivery']['CLI_thread_started']
    assert c['model']==plan['model']=='gpt-6.1-sol' and c['requested_effort']==plan['requested_effort']=='medium'
    usage=c['usage'];assert 0<=usage['cached_input_tokens']<=usage['input_tokens'] and 0<=usage['reasoning_output_tokens']<=usage['output_tokens']
    timing={'full_cell_s':r['full_cell_wall_ns']/1e9,'consumer_wall_s':c['wall_ns']/1e9,'prompt_to_final_s':c['prompt_to_final_ns']/1e9,'setup_s':c['pre_consumer_setup_ns']/1e9,'post_consumer_close_tail_s':(r['cell_ended_ns']-c['cleanup_end_ns'])/1e9,'owner_tool_s':sum(a['elapsed_ns'] for a in owner)/1e9,'last_tool_to_final_s':(c['final_received_ns']-tool_events[-1]['perf_ns'])/1e9,'native_worker_exec_s':sum(w['elapsed_ns'] for w in execs)/1e9}
    counts={'model_visible_tools':len(owner),'native_tools':sum(a['name']=='execute_blender_code' for a in owner),'plugin_tools':sum(a['name']!='execute_blender_code' for a in owner),'public_id_requests':sum(f['has_id'] for f in public),'public_notifications':sum(not f['has_id'] for f in public),'private_plugin_id_requests':sum(f['has_id'] for f in private),'private_plugin_notifications':sum(not f['has_id'] for f in private),'worker_execute_rpcs':len(execs),'worker_close_rpcs':len(ends),'thin_exit_missing':missing_exit}
    bytecounts={'owner_tool_wire':sum(a['response_bytes'] for a in owner),'owner_tool_content_text':sum(a['content_text_bytes'] for a in owner),'public_tx':sum(f['tx_bytes'] for f in public),'public_rx':sum(f['rx_bytes'] for f in public),'public_catalogue_rx':sum(f['rx_bytes'] for f in public if f['method']=='tools/list'),'private_plugin_tx':sum(f['tx_bytes'] for f in private),'private_plugin_rx':sum(f['rx_bytes'] for f in private),'native_worker_stdout_internal':sum(w['stdout_bytes'] for w in execs),'consumer_native_code':sum(a['code_bytes'] for a in owner),'initial_image':c['input_image_bytes'],'prompt':c['input_text_bytes'],'final_text':len(c['final'].encode())}
    row={'cell':r['cell'],'round':r['round'],'group':r['group'],'anonymous_id':next(v['anonymous_id'] for v in mapping if v['cell']==r['cell']),'timing':timing,'counts':counts,'bytes':bytecounts,'usage':usage,'input_plus_output':usage['input_tokens']+usage['output_tokens'],'uncached_input':usage['input_tokens']-usage['cached_input_tokens'],'tools':owner,'runtime_source':(identity.get('runtime_identity') or {}).get('source_sha256'),'public_frames':public,'private_plugin_frames':private,'worker_close_marker':ends[0],'warnings':blob(p/'stderr.raw.bin').decode('utf8',errors='replace').splitlines(),'image_delivery':c['image_delivery'],'unknowns':{'fees':c['fees'],'provider_requests':c['provider_requests'],'resolved_effort':c['resolved_effort'],'resolved_model':None,'image_tokens':c['image_tokens'],'thin_close':c['bridge_cleanup']['confirmed'],'cache_memory_peak':None,'coordinator_usage':None},'provider_retry_observations':c['provider_retry_observations'],'source_status':'same-source receipt and independent hash checks; no new live capture','valid_completed':True}
    rows.append(row)
groups={}
for g in ['N','P0','P1']:
    subset=[r for r in rows if r['group']==g]
    groups[g]={section:{k:stats([r[section][k] for r in subset]) for k in subset[0][section]} for section in ['timing','counts','bytes','usage']}
    groups[g]['input_plus_output']=stats([r['input_plus_output'] for r in subset]);groups[g]['uncached_input']=stats([r['uncached_input'] for r in subset])
comparisons={};pairs=[]
for g in ['P0','N']:
    a=groups['P1'];b=groups[g];tm=a['timing']['full_cell_s']['median'];tr=b['timing']['full_cell_s']['median'];tk=a['input_plus_output']['sum'];kr=b['input_plus_output']['sum']
    comparisons['P1_vs_'+g]={'median_s_delta':tm-tr,'median_change_percent':100*(tm/tr-1),'total_tokens_delta':tk-kr,'total_tokens_change_percent':100*(tk/kr-1),'frozen_net_benefit_pass':tm<tr and tk<=kr,'quality_gate':'all three complete correct in both compared groups, pre-cost seal'}
    for rnd in [1,2,3]:
        a=next(r for r in rows if r['round']==rnd and r['group']=='P1');b=next(r for r in rows if r['round']==rnd and r['group']==g)
        pairs.append({'comparison':'P1_vs_'+g,'round':rnd,'P1_cell':a['cell'],'reference_cell':b['cell'],'full_cell_s_delta':a['timing']['full_cell_s']-b['timing']['full_cell_s'],'input_plus_output_delta':a['input_plus_output']-b['input_plus_output']})
prep=read(B/'PREP_READY.json');fix=read(B/'FIX_READY.json');start=read(B/'CONTROLLER_STARTED.json');end=read(B/'CONTROLLER_EXIT.json')
dt=lambda s:datetime.datetime.fromisoformat(s)
result={'cycle_id':'M4-LOCAL-RELATION-CONSUMPTION-001','execution_commit':'06d1b4b4cadd880884a0a3c0927a3095ea761f30','quality_seal_sha256':'efdee7dbf1bb4230c465afdaeb77f82b2266a8e7ef209c52c4323d3f83d5d2b0','method':'Independent original-file calculations after sealed quality. No product or prior cost postprocessor executed. Layer definitions checked against existing actor/helper and prior accounting schema. All nine retained.','rows':rows,'groups':groups,'comparisons':comparisons,'paired_rounds':pairs,'batch':{'driver_wall_s':run['batch_wall_ns']/1e9,'sum_full_cell_s':sum(r['full_cell_wall_ns'] for r in run['records'])/1e9,'driver_outside_cell_s':(run['batch_wall_ns']-sum(r['full_cell_wall_ns'] for r in run['records']))/1e9,'controller_UTC_start_to_exit_s':(dt(end['ended_utc'])-dt(start['started_utc'])).total_seconds(),'stop':run['stop'],'complete':True,'new_consumer_retries':0},'separate_preparation_costs':{'original_preparation_window_s':prep['measured_preparation_wall_seconds'],'window_scope':prep['preparation_timing_scope'],'fix_window_s':None,'fix_note':'Fix and review were real additional work, not included in original875.063302s. This subreview did not independently read implementation chat duration.','reused_build_install_and_engineering_costs':'Existing artifacts reused; historical build/install, local-evidence implementation, first failed synthetic checks and reviews remain costs; not zero, not recharged into per-cell time. No complete disjoint monetary/coordination ledger.','failed_preparation_records':prep['failures_preserved'],'review_and_packaging_time_s':None},'accounting_rules':['cached input is a subset of input; reasoning output is a subset of output, neither added twice','public MCP, private product MCP, and native worker RPC are distinct layers, not independent model calls','setup plus consumer wall plus close tail partitions fullcell; owner/tool/worker spans are nested and not summed into fullcell','one1185069-byte initial attachment per cell; actual image token allocation, provider receipt and cognitive use unknown','thin EXIT missing in all9; backend close and CLI parent reaping separately confirmed; unknown worker close marker is retained with explicit closed response, not silently converted','same model metadata and PowerShell snapshot warnings retained, no latency subtracted; last-tool-to-final is observed wall latency, not isolated private model reasoning','one scene/3repeats per arm, not independent scene diversity or statistical significance; token difference84 is small and cache/context dependent','fees/provider requests/cache peak/coordinator cost unknown; no monetary savings or overall development ROI claimed'],'source_sha256':HASHES}
(O/'COST_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'comparisons':comparisons,'batch':result['batch'],'groups':{g:{'full_cell_s':groups[g]['timing']['full_cell_s'],'tokens':groups[g]['input_plus_output'],'bytes':groups[g]['bytes']['owner_tool_wire'],'counts':{k:v['sum'] for k,v in groups[g]['counts'].items()}} for g in groups}},ensure_ascii=False,indent=2))
