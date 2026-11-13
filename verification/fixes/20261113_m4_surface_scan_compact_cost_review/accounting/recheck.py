"""Independent nine-cell raw-accounting recheck; stdlib, offline, no author imports."""
from pathlib import Path
from fractions import Fraction
import collections
import hashlib
import json
import statistics
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=ROOT/'verification/m4_surface_scan_compact_consumption_001'
OUT=Path(__file__).resolve().parent
HEAD='e089a7ba42c276b6f537b62c1a0a4f037fdaec6d'
SEAL_SHA='c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb'
ORDER=['N1','O1','C1','O2','C2','N2','C3','N3','O3']
CHECKS=[];INPUTS={}
tree_raw=subprocess.check_output(['git','ls-tree','-r','-z',HEAD,'--',B.relative_to(ROOT).as_posix()],cwd=ROOT)
TREE={r.split(b'\t',1)[1].decode():r.split(b'\t',1)[0].split()[2].decode()for r in tree_raw.split(b'\0')if r}

def ck(label,value,detail=None):CHECKS.append({'check':label,'passed':bool(value),'detail':detail})
def raw(path):
    p=Path(path);b=p.read_bytes();k=str(p)
    if k not in INPUTS:
        rel=p.relative_to(ROOT).as_posix();sha=hashlib.sha256(b).hexdigest()
        blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        INPUTS[k]={'bytes':len(b),'sha256':sha,'fixed_git_commit':HEAD,'expected_git_blob':TREE.get(rel),'actual_git_blob':blob}
        ck('git:'+rel,blob==TREE.get(rel))
    return b
def load(p):return json.loads(raw(p).decode('utf-8-sig'))
def lines(p):return[json.loads(x)for x in raw(p).decode('utf-8-sig').splitlines()if x]
def h(b):return hashlib.sha256(b).hexdigest()
def fraction_record(x):return{'numerator':x.numerator,'denominator':x.denominator,'decimal':float(x)}
def union(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]:merged[-1][1]=max(end,merged[-1][1])
        else:merged.append([start,end])
    return sum(b-a for a,b in merged)
def content_bytes(result):return sum(len(x['text'].encode('utf-8'))for x in result.get('content',[])if x.get('type')=='text')

def main():
    seal_path=B/'cost/inputs/QUALITY_SEAL.json';seal=load(seal_path)
    ck('fixed_quality_seal',h(raw(seal_path))==SEAL_SHA)
    sealmap={x['anonymous_id']:x for x in seal['answers']}
    mapping=load(B/'private/ANON_MAP.json')['rows'];mp={x['cell']:x for x in mapping}
    ck('private_mapping_fixed_sequence',[x['cell']for x in mapping]==ORDER)
    seq=load(B/'SEQUENCE.json');ck('no_replacements_serial',seq['serial']and seq['replacements']==0 and[x['cell']for x in seq['sequence']]==ORDER)
    run=load(B/'RUN_RESULT.json');records={x['cell']:x for x in run['records']}
    author=load(B/'cost/accounting/LEDGER.json');authors={x['cell']:x for x in author['cells']}
    results=[];previous_end=None
    for cell in ORDER:
        p=B/'cells'/cell;g=cell[0];a=authors[cell]
        c=load(p/'CONSUMER.json');ft=load(p/'CELL_FINAL_TIMING.json');pub=load(p/'CELL_TIMING_PUBLICATION.json')
        final=raw(p/'PUBLIC_FINAL.txt');q=sealmap[mp[cell]['anonymous_id']]
        ck(cell+':final_seal_binding',h(final)==q['final_sha256'] and q['execution_state']==c['status']and q['consumer_valid_completion']==c['valid_completion'])
        ck(cell+':full_integer_subtraction',all(type(ft[k])is int for k in['cell_started_ns','business_receipts_closed_ns','full_cell_wall_ns'])and ft['business_receipts_closed_ns']-ft['cell_started_ns']==ft['full_cell_wall_ns'])
        ck(cell+':full_original_budget',ft['full_cell_wall_ns']<=570_000_000_000 and ft['within_570s'])
        ck(cell+':cell_started_consistent',records[cell]['cell_started_ns']==ft['cell_started_ns'])
        ck(cell+':prefix_earlier_than_full',c['total_task_wall_ns']<=ft['full_cell_wall_ns'])
        ck(cell+':publication_separate',pub['business_receipts_closed_ns']==ft['business_receipts_closed_ns']and pub['timing_receipt_publication_started_ns']>=ft['business_receipts_closed_ns']and pub['timing_receipt_publication_closed_ns']-pub['timing_receipt_publication_started_ns']==pub['timing_receipt_publication_ns'])
        if previous_end is not None:ck(cell+':serial_after_prior_publication',ft['cell_started_ns']>=previous_end)
        previous_end=pub['timing_receipt_publication_closed_ns']
        lifecycle=[c['started_ns']-ft['cell_started_ns'],c['prompt_submitted_ns']-c['started_ns'],c['final_received_ns']-c['prompt_submitted_ns'],c['cleanup_end_ns']-c['final_received_ns'],ft['business_receipts_closed_ns']-c['cleanup_end_ns']]
        ck(cell+':lifecycle_partition',min(lifecycle)>=0 and sum(lifecycle)==ft['full_cell_wall_ns'])
        ck(cell+':consumer_wall',c['cleanup_end_ns']-c['started_ns']==c['wall_ns'])
        events=lines(p/'events.jsonl')
        completed_turns=[x for x in events if x['event']['type']=='turn.completed']
        ck(cell+':one_final_usage_event',len(completed_turns)==1)
        usage=completed_turns[-1]['event']['usage']
        ck(cell+':usage_three_copies_equal',usage==c['usage'] and c['usage_rows']==[usage])
        ck(cell+':usage_subset_semantics',all(type(v)is int and v>=0 for v in usage.values())and usage['cached_input_tokens']<=usage['input_tokens']and usage['reasoning_output_tokens']<=usage['output_tokens']and usage['cache_write_input_tokens']==0)
        total=usage['input_tokens']+usage['output_tokens']
        errors=[x for x in events if x['event']['type']=='error']
        reconnect=[x for x in errors if'Reconnecting'in x['event'].get('message','')]
        ck(cell+':reconnect_error_retained',errors==c['errors'] and len(reconnect)==(1 if cell in['N2','O2']else 0))
        ck(cell+':failed_not_erased_after_final',c['status']==('failed'if reconnect else'completed')and c['valid_completion']==(not reconnect)and c['exit_code']==0)
        ck(cell+':turn_completed_time',completed_turns[0]['perf_ns']==c['turn_completed_ns'])
        final_events=[x for x in events if x['event']['type']=='item.completed'and x['event'].get('item',{}).get('type')=='agent_message']
        ck(cell+':last_public_final',final_events[-1]['event']['item']['text'].encode()==final and final_events[-1]['perf_ns']==c['final_received_ns'])
        starts={x['event']['item']['id']:x for x in events if x['event']['type']=='item.started'and x['event'].get('item',{}).get('type')=='mcp_tool_call'}
        ends=[x for x in events if x['event']['type']=='item.completed'and x['event'].get('item',{}).get('type')=='mcp_tool_call']
        intervals=[];cli_text=0;cli_images=0
        for item in ends:
            ei=item['event']['item'];sid=ei['id'];start=starts[sid]['perf_ns'];end=item['perf_ns'];intervals.append((start,end))
            ck(cell+':tool_interval:'+sid,c['prompt_submitted_ns']<=start<=end<=c['final_received_ns'])
            cli_text+=content_bytes(ei['result']);cli_images+=sum(x.get('type')=='image'for x in ei['result'].get('content',[]))
        cli_union=union(intervals)
        ck(cell+':nonoverlap_and_complete_tool_intervals',len(starts)==len(ends)and cli_union==sum(b-a for a,b in intervals))
        turn_start=[x['perf_ns']for x in events if x['event']['type']=='turn.started']
        ck(cell+':single_turn_start',len(turn_start)==1)
        # Raw thin client records, including metadata and all failed attempts.
        bridges=list((p/'attachments').glob('bridge_*'));ck(cell+':one_thin_bridge',len(bridges)==1)
        br=bridges[0];tx_total=rx_total=0;bridge_business=[];methods=[]
        for requestfile in sorted(br.glob('*/TX.bin')):
            tx=raw(requestfile);req=json.loads(tx);methods.append(req['method']);tx_total+=len(tx)
            responsefile=requestfile.with_name('RX.bin')
            responsebytes=raw(responsefile)if responsefile.exists()else b'';rx_total+=len(responsebytes)
            if req['method']=='tools/call':bridge_business.append((req,json.loads(responsebytes),len(responsebytes)))
        ck(cell+':bridge_methods',methods[:3]==['initialize','notifications/initialized','tools/list']and len(bridge_business)==len(ends))
        tool_dirs=sorted((p/'owner').glob('tool_*'));ck(cell+':no_attempt_dropped',len(tool_dirs)==len(ends))
        attempts=[];toolnames=collections.Counter();owner_ns=0;response_bytes=0;argsseen=collections.Counter()
        for i,td in enumerate(tool_dirs):
            attempt=load(td/'ATTEMPT.json');req=load(td/'REQUEST.json');resp=load(td/'RESPONSE.json');end=ends[i]['event']['item']
            br_req,br_resp,rx_n=bridge_business[i]
            ck(cell+':attempt_request_response_copies:'+str(i),req==br_req and resp==br_resp and end['arguments']==req['params']['arguments'] and end['tool']==req['params']['name'])
            # CLI adapts MCP CallToolResult to content/structured_content and
            # moves success/error state to its item envelope. Compare facts
            # byte-for-byte, then explicitly verify the two envelope contracts.
            ck(cell+':CLI_content_owner_equal:'+str(i),end['result']['content']==resp['result']['content'])
            ck(cell+':CLI_envelope_projection:'+str(i),set(end['result'])=={'content','structured_content'}and end['result']['structured_content']is None and not end.get('error')and end['status']=='completed'and resp['result'].get('isError')is False)
            ck(cell+':attempt_response_bytes:'+str(i),attempt['response_bytes']==rx_n==attempt['produced_response_bytes'])
            ck(cell+':attempt_interval_nested:'+str(i),intervals[i][0]<=attempt['started_ns']<=attempt['started_ns']+attempt['elapsed_ns']<=intervals[i][1])
            argsseen[(attempt['name'],json.dumps(req['params']['arguments'],sort_keys=True,ensure_ascii=False))]+=1
            toolnames[attempt['name']]+=1;owner_ns+=attempt['elapsed_ns'];response_bytes+=rx_n;attempts.append(attempt)
        tool_failure=sum(bool(x['is_error']or x['exception'])for x in attempts)
        ck(cell+':CLI_text_owner_equal',cli_text==sum(content_bytes(x[1]['result'])for x in bridge_business))
        worker=lines(p/'owner/native/WORKER_EVENTS.jsonl');we_byseq={x['sequence']:x for x in worker}
        close=load(p/'owner/CLOSE.json');finish=load(p/'OWNER_FINISH.json')
        ck(cell+':owned_close_in_full',close['confirmed']and finish['confirmed']and close['native_close']['process_reaped']and close['ended_ns']<=ft['business_receipts_closed_ns']and ft['owner_cleanup_confirmed'])
        ck(cell+':generic_close_unknown_preserved',worker[-1]['status']=='unknown' and close['native_close']['response']['status']=='closed')
        stdout_all=stderr_all=stdout_business=stderr_business=host_business_ns=0
        business_host=[]
        for call_dir in sorted((p/'owner/native').glob('call_*'),key=lambda x:int(x.name.split('_')[1])):
            k=int(call_dir.name.split('_')[1]);event=we_byseq[k]
            code=raw(call_dir/'SCRIPT.py').replace(b'\r\n',b'\n')
            sout=raw(call_dir/'stdout.txt').replace(b'\r\n',b'\n');serr=raw(call_dir/'stderr.txt').replace(b'\r\n',b'\n')
            ck(cell+':host_code_stdout_stderr:'+str(k),h(code)==event['script_sha256']and len(sout)==event['stdout_bytes']and len(serr)==event['stderr_bytes'])
            stdout_all+=len(sout);stderr_all+=len(serr)
            owning=[j for j,t in enumerate(attempts)if t['started_ns']<=event['started_ns']and event['started_ns']+event['elapsed_ns']<=t['started_ns']+t['elapsed_ns']]
            if owning:
                ck(cell+':host_unique_owner:'+str(k),len(owning)==1)
                business_host.append(k);stdout_business+=len(sout);stderr_business+=len(serr);host_business_ns+=event['elapsed_ns']
        ck(cell+':host_business_and_administration',len(business_host)==len(attempts)and len(worker)-len(business_host)==3)
        product={'tx_bytes':0,'rx_bytes':0,'business_rpcs':0,'administrative_rpcs':0,'observations':[]}
        if g!='N':
            pp=p/'owner/plugin';rpc=load(pp/'RPC.json')
            for i,rr in enumerate(rpc['requests'],1):
                tx=raw(pp/f'{i:03d}'/'TX.bin');req=json.loads(tx)
                rxp=pp/f'{i:03d}'/'RX.bin';rx=raw(rxp)if rxp.exists()else b''
                ck(cell+':product_wire:'+str(i),len(tx)==rr['sent_bytes']and len(rx)==rr['received_bytes']and rr['error']is None)
                product['tx_bytes']+=len(tx);product['rx_bytes']+=len(rx)
                product['business_rpcs'if req['method']=='tools/call'else'administrative_rpcs']+=1
            ck(cell+':product_wire_summary',product['tx_bytes']==rpc['tx_bytes']and product['rx_bytes']==rpc['rx_bytes'])
            audit=lines(p/'owner/audit.jsonl')
            for obs in [x for x in audit if x['event']=='observe']:
                w=obs['task_work'];aw=w['acquisition_work'];before=w['measurement_cache_before'];after=w['measurement_cache_after']
                product['observations'].append({'kernels':w['kernel_calls'],'pair_calls':w['pair_calls'],'result_cache_hit':w['result_cache_hit'],'cache_entries_before':before['measurement_entries'],'cache_entries_after':after['measurement_entries'],'cache_accounted_bytes':after['accounted_bytes'],'source_vertices':aw['source_vertices'],'source_faces':aw['source_faces'],'resource_vertices_read':aw['residency_delta']['resource_vertices_read'],'resource_faces_read':aw['residency_delta']['resource_faces_read'],'scan_cache_hits':aw['residency_delta']['scan_cache_hits']})
            ck(cell+':cold_then_repeat_kernel', [x['kernels']for x in product['observations']]==([112,0]if g=='O'else[112]))
            ck(cell+':cold_cache_empty',product['observations'][0]['cache_entries_before']==0)
            ck(cell+':plugin_close_in_full',close['plugin_close']['process_reaped']and close['product_runtime_exit']['confirmed']and close['product_runtime_exit']['observed_ns']<=ft['business_receipts_closed_ns'])
        stderr=raw(p/'stderr.raw.bin');stderr_rows=lines(p/'stderr_lines.jsonl')
        ck(cell+':stderr_all_original_lines',b''.join(x['text'].encode('utf-8')for x in stderr_rows)==stderr)
        ck(cell+':unknown_metering_stays_unknown',c['fees']is None and c['provider_requests']is None and c['resolved_effort']is None)
        ck(cell+':thin_EXIT_unknown',c['bridge_cleanup']['confirmed']is None and c['bridge_cleanup']['receipt_status']=='unknown')
        # Build independently, then compare a limited list to author ledger.
        out={'cell':cell,'anonymous_id':mp[cell]['anonymous_id'],'primary_quality':q['primary_classification'],'content_quality':q['final_content_classification'],'execution':c['status'],
             'full_ns':ft['full_cell_wall_ns'],'prefix_ns':c['total_task_wall_ns'],'full_minus_prefix_ns':ft['full_cell_wall_ns']-c['total_task_wall_ns'],
             'lifecycle_partitions_ns':lifecycle,'publication_ns':pub['timing_receipt_publication_ns'],'consumer_wall_ns':c['wall_ns'],
             'prompt_to_final_ns':lifecycle[2],'CLI_turn_ns':completed_turns[0]['perf_ns']-turn_start[0],
             'CLI_tool_interval_union_ns':cli_union,'prompt_final_outside_tool_intervals_ns':lifecycle[2]-cli_union,'owner_tool_sum_ns':owner_ns,'host_business_script_sum_ns':host_business_ns,
             'reported_usage':usage,'reported_input_plus_output':total,'uncached_input':usage['input_tokens']-usage['cached_input_tokens'],'reported_usage_event_count':len(completed_turns),
             'retained_reconnect_events':reconnect,'abandoned_stream_usage_inclusion':None,'tool_attempts':len(attempts),'tool_failures':tool_failure,'tools_by_name':dict(toolnames),'same_name_arguments_duplicate_attempts':sum(v-1 for v in argsseen.values()),
             'CLI_tool_text_utf8_bytes':cli_text,'business_MCP_response_bytes':response_bytes,'all_MCP_tx_bytes':tx_total,'all_MCP_rx_bytes':rx_total,'all_host_rpc':len(worker),'host_business_scripts':len(business_host),'host_stdout_all':stdout_all,'host_stdout_business':stdout_business,'host_stderr_all':stderr_all,'host_stderr_business':stderr_business,
             'product':product,'CLI_stdout_bytes_reported_no_raw_copy':c['stdout_bytes'],'CLI_stderr_raw_bytes':len(stderr),'CLI_stderr_lines':stderr_rows,'image_count':cli_images,'initial_image_count':c['input_image_count'],'requested_model':c['model'],'requested_effort':c['requested_effort'],'resolved_model':None,'resolved_effort':None,'fees':None,'thin_client_exit':'unknown','host_close_generic_event_status':worker[-1]['status']}
        comparisons={'full_ns':'full_cell_wall_ns','prefix_ns':'prefix_wall_ns','full_minus_prefix_ns':'business_close_minus_prefix_ns','CLI_tool_interval_union_ns':'CLI_tool_intervals_sum_ns','owner_tool_sum_ns':'owner_tool_elapsed_sum_ns','host_business_script_sum_ns':'native_host_business_script_elapsed_sum_ns','reported_input_plus_output':'total_input_plus_output_tokens','CLI_tool_text_utf8_bytes':'recorded_model_facing_tool_text_utf8_bytes','business_MCP_response_bytes':'tool_response_envelope_bytes','all_MCP_tx_bytes':'bridge_tx_bytes','all_MCP_rx_bytes':'bridge_rx_bytes','all_host_rpc':'native_host_requests_including_close','host_stdout_all':'native_host_stdout_utf8_bytes_all_scripts','host_stdout_business':'native_host_stdout_utf8_bytes_business','tool_attempts':'tool_attempts','tool_failures':'failed_tool_attempts'}
        for our,their in comparisons.items():ck(cell+':author_comparison:'+our,out[our]==a[their],{'ours':out[our],'author':a[their]})
        ck(cell+':zero_images',cli_images==c['input_image_count']==0)
        results.append(out)
    groups={}
    for g in' NOC'.strip():
        rows=[x for x in results if x['cell'][0]==g]
        groups[g]={'cells':[x['cell']for x in rows],'effective_complete':sum(x['primary_quality']=='complete_correct'for x in rows),'content_correct':sum(x['content_quality']=='complete_correct'for x in rows),'full_ns_sum':sum(x['full_ns']for x in rows),'full_ns_median':statistics.median(x['full_ns']for x in rows),'reported_usage_sum':{key:sum(x['reported_usage'][key]for x in rows)for key in rows[0]['reported_usage']},'reported_total_tokens':sum(x['reported_input_plus_output']for x in rows),'uncached_input_sum':sum(x['uncached_input']for x in rows),'tool_attempts':sum(x['tool_attempts']for x in rows),'CLI_tool_text_bytes':sum(x['CLI_tool_text_utf8_bytes']for x in rows),'host_stdout_business_bytes':sum(x['host_stdout_business']for x in rows)}
    cells={x['cell']:x for x in results};comparisons={}
    for ref in'NO':
        ratios=[Fraction(cells['C'+str(i)]['full_ns'],cells[ref+str(i)]['full_ns'])for i in[1,2,3]];med=statistics.median(ratios)
        quality=groups['C']['effective_complete']==groups[ref]['effective_complete']==3
        time_ok=med<=Fraction(7,10)if ref=='N'else med<1
        token_ok=groups['C']['reported_total_tokens']<=groups[ref]['reported_total_tokens']
        comparisons['C/'+ref]={'pair_ratios':[{ 'pair':'C'+str(i+1)+'/'+ref+str(i+1),**fraction_record(r)}for i,r in enumerate(ratios)],'median_pair_ratio':fraction_record(med),'reported_token_ratio':fraction_record(Fraction(groups['C']['reported_total_tokens'],groups[ref]['reported_total_tokens'])),'both_3_of_3_effective_complete':quality,'time_numeric_condition':time_ok,'reported_token_numeric_condition':token_ok,'formal_gate_passed':quality and time_ok and token_ok,'interpretation':'descriptive, includes every failed cell and reconnect; no cost subtraction'}
    formal=load(B/'FORMAL_PROCESS.json');formalpub=load(B/'FORMAL_PUBLICATION.json');prep=load(B/'PREPARATION_COST.json')
    ck('formal_full_contains_all_cells',formal['started_ns']<=load(B/'cells/N1/CELL_FINAL_TIMING.json')['cell_started_ns'] and formal['ended_ns']>=previous_end)
    ck('run_wall_subtraction',run['batch_ended_ns']-run['batch_started_ns']==run['batch_wall_ns'])
    ck('formal_publication_subtraction',formalpub['publication_closed_ns']-formalpub['publication_started_ns']==formalpub['publication_ns']and formalpub['publication_started_ns']>=formal['ended_ns'])
    packaging={}
    for key,f in[('initial','PACKAGING_COST.json'),('r2','PACKAGING_COST_R2.json')]:
        pk=load(B/'private'/f);ck('package_time:'+key,pk['archive_closed_ns']-pk['started_ns']==pk['archive_creation_ns']);packaging[key]=pk
    sumcells=sum(x['full_ns']for x in results);fw=formal['ended_ns']-formal['started_ns']
    shared={'sum_cells_ns':sumcells,'run_models_ns':run['batch_wall_ns'],'formal_process_ns':fw,'formal_minus_cells_ns':fw-sumcells,'cell_publication_sum_ns':sum(x['publication_ns']for x in results),'formal_publication_ns':formalpub['publication_ns'],'preparation':prep,'packaging':packaging,'not_measured':['publication receipt self-write','full coordination and preparation','admin redaction and post-archive verification','review and Git delivery','physical fsync','provider rendering/full request count/abandoned stream usage','cash and subscription debit','actual model version and effort','thin process exits','full native TCP bytes','uniform native vertex/primitive work']}
    ck('shared_matches_author',shared['sum_cells_ns']==author['shared_costs']['sum_full_cells_ns']and shared['formal_minus_cells_ns']==author['shared_costs']['formal_minus_sum_full_cells_ns']and shared['cell_publication_sum_ns']==author['shared_costs']['sum_cell_timing_receipt_publication_ns'])
    report={'fixed_commit':HEAD,'quality_seal_sha256':SEAL_SHA,'method':'Independent new stdlib parser; author ledger read only for cross-comparison, no author verifier imported or run; new Blender/model/API zero.','AL_note':'Own old child assignment retained; parent75ca5929/rev1 observed; no borrowed identity or parent writes.','cells':results,'groups':groups,'comparisons':comparisons,'shared_costs':shared,'non_additivity':'CLI, owner, host and product intervals nest. Count usage final once; cached/reasoning are subsets. Public text, MCP frames and internal stdout are distinct layers. Shared cost not arbitrarily split.','reviewer_history':'ATTEMPT_01 retained: 27 envelope equality checks failed because CLI adapts MCP result.isError=false to item.status=completed/error=null and adds structured_content=null. Original requests/responses and content were equal. Corrected checks explicitly compare both envelope contracts; no original evidence changed.','checks':len(CHECKS),'failed_checks':[x for x in CHECKS if not x['passed']]}
    for name,v in[('RESULTS.json',report),('CHECKS.json',CHECKS),('INPUT_HASHES.json',INPUTS)]:
        (OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(CHECKS),'inputs':len(INPUTS),'failed_checks':report['failed_checks'],'groups':groups,'comparisons':comparisons,'shared_costs':{k:v for k,v in shared.items()if not isinstance(v,(dict,list))}},ensure_ascii=False,indent=2))
    return bool(report['failed_checks'])
if __name__=='__main__':raise SystemExit(main())
