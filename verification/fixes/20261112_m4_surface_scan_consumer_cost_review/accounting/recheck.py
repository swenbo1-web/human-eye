"""Independent raw-file cost recomputation; never imports author checkers."""
from pathlib import Path
from fractions import Fraction
from statistics import median
import hashlib
import json
import subprocess

REPO=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=REPO/'verification/m4_surface_scan_consumption_001'
OUT=Path(__file__).resolve().parent
checks=[]
sources={}

def sha(data): return hashlib.sha256(data).hexdigest()

def check(name, value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:
        (OUT/'FAILED.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        raise AssertionError(name)

manifest_data=(BASE/'DELIVERY_MANIFEST.json').read_bytes()
check('original_manifest_Git',manifest_data==subprocess.check_output(['git','show','e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3:verification/m4_surface_scan_consumption_001/DELIVERY_MANIFEST.json'],cwd=REPO))
original={x['path']:x for x in json.loads(manifest_data)['files']}

def raw(path):
    if not path.is_absolute(): path=BASE/path
    data=path.read_bytes()
    rel=path.relative_to(REPO).as_posix()
    if rel in original:
        expected=original[rel]
        check('source_'+rel, len(data)==expected['bytes'] and sha(data)==expected['sha256'])
    sources[rel]={'bytes':len(data),'sha256':sha(data)}
    return data

def js(path): return json.loads(raw(Path(path)))

def frac(value): return {'numerator':value.numerator,'denominator':value.denominator,'value':float(value)}

def main():
    run=js('RUN_RESULT.json')
    order=['N1','P1','P2','N2','N3','P3']
    check('fixed_six',[r['cell'] for r in run['records']]==order and run['started_cells']==6 and run['maximum_consumers']==6 and run['all_planned_dispatched'] and run['no_replacements'])
    check('no_batch_stop',run['stop'] is None)
    formal=js('FORMAL_PROCESS.json');publication=js('FORMAL_PUBLICATION.json');prep=js('PREPARATION_COST.json');packaging=js('private/PACKAGING_COST.json')
    driver=raw(Path('runtime/driver.py')).decode('utf-8')
    lo=driver.index('def close_cell_accounting(')
    hi=driver.index('\ndef ',lo+5)
    accounting_source=driver[lo:hi]
    (OUT/'CLOSE_CELL_ACCOUNTING_SOURCE.txt').write_text(accounting_source,encoding='utf-8')
    # Source is inspected manually to verify that end is observed after writes.
    check('business_close_sample_present','business_receipts_closed_ns' in accounting_source)
    expected_ledger=js('cost/accounting/LEDGER.json')
    expect={x['cell']:x for x in expected_ledger['cells']}
    cells=[]
    tids=[]
    for label, row in zip(order,run['records']):
        folder=Path('cells')/label
        c=js(folder/'CONSUMER.json');tim=js(folder/'CELL_FINAL_TIMING.json');pub=js(folder/'CELL_TIMING_PUBLICATION.json');finish=js(folder/'OWNER_FINISH.json')
        events=[json.loads(line) for line in raw(folder/'events.jsonl').decode('utf-8').splitlines() if line]
        usages=[e['event']['usage'] for e in events if e['event']['type']=='turn.completed']
        check(label+'_single_cumulative',len(usages)==1 and usages[0]==c['usage'] and usages==c['usage_rows'])
        usage=usages[0]
        check(label+'_usage_subsets',0<=usage['cached_input_tokens']<=usage['input_tokens'] and 0<=usage['reasoning_output_tokens']<=usage['output_tokens'])
        check(label+'_usage_no_cachewrite',usage['cache_write_input_tokens']==0)
        thread=[e['event']['thread_id'] for e in events if e['event']['type']=='thread.started']
        check(label+'_thread',thread==[c['thread_id']]);tids+=thread
        final_events=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
        check(label+'_final_received',final_events[-1]['perf_ns']==c['final_received_ns'])
        final_bytes=raw(folder/'PUBLIC_FINAL.txt')
        check(label+'_final_exact',final_events[-1]['event']['item']['text'].encode()==final_bytes and raw(folder/'final.txt')==final_bytes)
        start=tim['cell_started_ns'];end=tim['business_receipts_closed_ns'];full=end-start
        check(label+'_full_integer',all(type(v) is int for v in (start,end,full)) and full==tim['full_cell_wall_ns'])
        check(label+'_start_and_budget',start==row['cell_started_ns'] and row['worker_deadline_ns']==start+570_000_000_000 and full<570_000_000_000)
        check(label+'_ordered_span',start<c['started_ns']<=c['prompt_submitted_ns']<=c['final_received_ns']<=c['turn_completed_ns']<=c['process_exit_ns']<=c['cleanup_end_ns']<=finish['close']['ended_ns']<=end)
        check(label+'_cleanup',c['process_reaped'] and finish['confirmed'] and finish['close']['confirmed'] and tim['owner_cleanup_confirmed'])
        check(label+'_prefix',row['cell_ended_ns']-start==c['total_task_wall_ns'] and c['total_task_wall_ns']<full)
        check(label+'_publication',pub['business_receipts_closed_ns']==end and end<=pub['timing_receipt_publication_started_ns']<=pub['timing_receipt_publication_closed_ns'] and pub['timing_receipt_publication_ns']==pub['timing_receipt_publication_closed_ns']-pub['timing_receipt_publication_started_ns'])
        check(label+'_thin_unknown',c['bridge_cleanup']['receipt_status']=='unknown' and c['bridge_cleanup']['missing_exit_count']==1 and c['bridge_cleanup']['confirmed'] is None)
        check(label+'_provider_unknown',c['provider_requests'] is None and c['fees'] is None and c['resolved_effort'] is None)
        check(label+'_requests_same',c['model']=='gpt-6.1-sol' and c['requested_effort']=='medium')
        starts={e['event']['item']['id']:e for e in events if e['event']['type']=='item.started' and e['event']['item'].get('type')=='mcp_tool_call'}
        completed=[e for e in events if e['event']['type']=='item.completed' and e['event']['item'].get('type')=='mcp_tool_call']
        check(label+'_paired_events',len(starts)==len(completed)==finish['close']['tool_attempts'])
        attempts=[]
        for i,event in enumerate(completed,1):
            item=event['event']['item'];item_start=starts[item['id']];meta=js(folder/f'owner/tool_{i:02d}/ATTEMPT.json');req=js(folder/f'owner/tool_{i:02d}/REQUEST.json');resp=js(folder/f'owner/tool_{i:02d}/RESPONSE.json')
            check(label+f'_{i}_name_args',req['params']['name']==item['tool']==meta['name'] and req['params']['arguments']==item['arguments'])
            check(label+f'_{i}_content',resp['result']['content']==item['result']['content'])
            check(label+f'_{i}_error',bool(resp['result'].get('isError'))==bool(meta['is_error']))
            interval=event['perf_ns']-item_start['perf_ns']
            check(label+f'_{i}_time',item_start['perf_ns']<=meta['started_ns']<=meta['started_ns']+meta['elapsed_ns']<=event['perf_ns'])
            if i>1:check(label+f'_{i}_no_overlap',completed[i-2]['perf_ns']<=item_start['perf_ns'])
            content_bytes=sum(len(part['text'].encode('utf-8')) for part in item['result']['content'] if part['type']=='text')
            check(label+f'_{i}_no_images',all(part['type']!='image' for part in item['result']['content']))
            attempts.append({'order':i,'tool':item['tool'],'cli_interval_ns':interval,'owner_elapsed_ns':meta['elapsed_ns'],'error':bool(meta['is_error']),'text_utf8_bytes':content_bytes,'response_envelope_bytes':meta['response_bytes']})
        tool_sum=sum(x['cli_interval_ns'] for x in attempts)
        prompt_final=c['final_received_ns']-c['prompt_submitted_ns']
        check(label+'_promptfinal',prompt_final==c['prompt_to_final_ns'])
        bridge_dirs=list((BASE/folder/'attachments').glob('bridge_*'))
        check(label+'_one_bridge',len(bridge_dirs)==1)
        bridge=[]
        for entry in sorted(bridge_dirs[0].iterdir()):
            if not entry.is_dir() or not (entry/'TX.bin').is_file():continue
            tx=raw(entry/'TX.bin');request=json.loads(tx)
            rx=raw(entry/'RX.bin') if (entry/'RX.bin').exists() else b''
            bridge.append({'method':request['method'],'tx':len(tx),'rx':len(rx)})
        check(label+'_bridge_attempts',sum(x['method']=='tools/call' for x in bridge)==len(attempts))
        check(label+'_bridge_admin',sum(x['method']!='tools/call' for x in bridge)==3)
        business_rx=sum(x['rx'] for x in bridge if x['method']=='tools/call')
        check(label+'_bridge_response_lengths',business_rx==sum(x['response_envelope_bytes'] for x in attempts))
        stderr=raw(folder/'stderr.raw.bin').decode('utf-8')
        timeouts=stderr.count('failed to refresh available models: timeout waiting for child process to exit')
        analytics=stderr.count('codex_analytics::client: failed to send events request')
        result={'cell':label,'full_cell_wall_ns':full,'prefix_wall_ns':c['total_task_wall_ns'],'after_prefix_ns':full-c['total_task_wall_ns'],
            'prompt_to_final_ns':prompt_final,'cli_tools_ns':tool_sum,'non_tool_remainder_ns':prompt_final-tool_sum,
            'timing_receipt_publication_ns':pub['timing_receipt_publication_ns'],'usage':usage,
            'tokens':usage['input_tokens']+usage['output_tokens'],'uncached_input':usage['input_tokens']-usage['cached_input_tokens'],
            'tool_attempts':len(attempts),'tool_errors':sum(x['error'] for x in attempts),'tool_text_utf8_bytes':sum(x['text_utf8_bytes'] for x in attempts),
            'tool_response_envelope_bytes':business_rx,'bridge_rx_bytes':sum(x['rx'] for x in bridge),'bridge_tx_bytes':sum(x['tx'] for x in bridge),
            'owner_tools_ns':sum(x['owner_elapsed_ns'] for x in attempts),'stderr_refresh_timeouts':timeouts,'stderr_analytics_warnings':analytics,'attempts':attempts}
        for key,ledger_key in [('full_cell_wall_ns','full_cell_wall_ns'),('prefix_wall_ns','prefix_wall_ns'),('cli_tools_ns','CLI_tool_intervals_sum_ns'),('non_tool_remainder_ns','prompt_to_final_non_tool_remainder_ns'),('tokens','total_input_plus_output_tokens'),('uncached_input','uncached_input_tokens'),('tool_attempts','tool_attempts'),('tool_errors','failed_tool_attempts'),('tool_text_utf8_bytes','recorded_model_facing_tool_text_utf8_bytes'),('tool_response_envelope_bytes','tool_response_envelope_bytes'),('bridge_rx_bytes','bridge_rx_bytes'),('bridge_tx_bytes','bridge_tx_bytes')]:
            check(label+'_author_cross_'+key,result[key]==expect[label][ledger_key])
        check(label+'_author_usage',usage==expect[label]['consumer_usage_final_cumulative'])
        cells.append(result)
    check('fresh_threads',len(tids)==len(set(tids))==6)
    by={x['cell']:x for x in cells}
    pairs=[Fraction(by[f'P{i}']['full_cell_wall_ns'],by[f'N{i}']['full_cell_wall_ns']) for i in range(1,4)]
    groups={}
    for g in ('N','P'):
        rows=[x for x in cells if x['cell'].startswith(g)]
        groups[g]={'full_sum_ns':sum(x['full_cell_wall_ns'] for x in rows),'full_median_ns':median(x['full_cell_wall_ns'] for x in rows),'token_sum':sum(x['tokens'] for x in rows),'input_sum':sum(x['usage']['input_tokens'] for x in rows),'output_sum':sum(x['usage']['output_tokens'] for x in rows),'cached_sum':sum(x['usage']['cached_input_tokens'] for x in rows),'uncached_input_sum':sum(x['uncached_input'] for x in rows),'reasoning_sum':sum(x['usage']['reasoning_output_tokens'] for x in rows),'cli_tools_ns':sum(x['cli_tools_ns'] for x in rows),'tool_attempts':sum(x['tool_attempts'] for x in rows),'tool_errors':sum(x['tool_errors'] for x in rows),'tool_text_bytes':sum(x['tool_text_utf8_bytes'] for x in rows)}
    full_sum=sum(x['full_cell_wall_ns'] for x in cells)
    formal_wall=formal['ended_ns']-formal['started_ns']
    check('outer_span',formal['started_ns']<=run['batch_started_ns'] and run['batch_ended_ns']<=formal['ended_ns'])
    check('outer_covers_cells',formal_wall>=full_sum)
    check('batch_wall',run['batch_wall_ns']==run['batch_ended_ns']-run['batch_started_ns'])
    check('formal_publish',publication['terminal_observed_ns']==formal['ended_ns'] and publication['publication_ns']==publication['publication_closed_ns']-publication['publication_started_ns'])
    check('packaging_span',packaging['archive_creation_ns']==packaging['archive_closed_ns']-packaging['started_ns'])
    shared={'full_sum_ns':full_sum,'formal_wall_ns':formal_wall,'formal_minus_fullsum_ns':formal_wall-full_sum,'run_models_wall_ns':run['batch_wall_ns'],'cell_timing_publication_ns':sum(x['timing_receipt_publication_ns'] for x in cells),'formal_publication_ns':publication['publication_ns'],'bootstrap_elapsed_ns':prep['bootstrap_elapsed_ns'],'historical_install_ns':prep['reused_install_elapsed_ns'],'historical_install_not_current_rebuild':prep['installation_rebuilds']==0,'public_zip_creation_ns':packaging['archive_creation_ns']}
    quality=True # sealed root decision; separately bound by provenance reviewer
    gate={'quality':quality,'paired_full_ratio_median':frac(median(pairs)),'full_gate':median(pairs)<=Fraction(7,10),'token_gate':groups['P']['token_sum']<=groups['N']['token_sum'],'overall':quality and median(pairs)<=Fraction(7,10) and groups['P']['token_sum']<=groups['N']['token_sum']}
    check('reported_wall_gate',gate['full_gate']==expected_ledger['gate']['paired_full_wall_pass'])
    check('reported_token_gate',gate['token_gate']==expected_ledger['gate']['token_pass'])
    result={'passed':True,'independent_checks':len(checks),'selected_original_sources':len(sources),'raw_cells':cells,'paired_ratios':[frac(p) for p in pairs],'groups':groups,'shared':shared,'gate':gate,'new_Blender_model_API_runs':0,'no_author_checker_imported':True,'unknown':['actual provider-rendered input/truncation','provider resolved model/effort','provider per-request usage and retries','fees/subscription debits','non-tool time attribution','thin-client EXIT','all preparation/review costs','fsync durability'],'scope_excluded':['full1974-source binding and private projections handled by sibling reviewer','native host/kernel instrumentation not independently recomputed here']}
    for name,data in [('RESULTS.json',result),('CHECKS.json',checks),('SOURCES.json',sources)]:
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'sources':len(sources),'gate':gate,'groups':groups,'shared':shared},ensure_ascii=False))

if __name__=='__main__':main()
