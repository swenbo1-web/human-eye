"""Read complete public usage and nested phase clocks; no new execution."""
import hashlib
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dist(values):
    return {'n':len(values),'median_ms':median(values)/1e6 if values else None,
            'min_ms':min(values)/1e6 if values else None,'max_ms':max(values)/1e6 if values else None,
            'total_ms':sum(values)/1e6}


def main():
    plan=read(HERE/'PLAN.json');rows=[];all_usage=[];inputs={}
    for slot in plan['sequence']:
        folder=HERE/'formal_cells'/slot['cell'];c=read(folder/'CONSUMER.json')
        b=read(folder/'bridge_native/BRIDGE_RESULT.json');raw=read(folder/'bridge_native/case_01.json')
        public=[r['event'] for r in map(json.loads,(folder/'events.jsonl').read_text().splitlines())]
        usage=[e['usage'] for e in public if e.get('type')=='turn.completed']
        assert len(usage)==1 and c['valid_completion'] and c['safe_to_continue']
        all_usage+=usage;call=b['calls'][0];assert len(b['calls'])==1
        reply=call['result'];tools=c['tool_calls']
        text=sum(len(item['text'].encode('utf8')) for event in tools
                 for item in event['item']['result']['content'] if item.get('type')=='text')
        assert text==b['public_text_bytes']
        rows.append(dict(slot,usage_complete=usage[0],MCP_calls=len(tools),
            scheduler_entry_ns=call['scheduler_entry_ns'],whole_tool_ns=call['elapsed_ns'],
            post_run_close_ns=call['post_run_close_ns'],
            prompt_to_final_ns=c['prompt_to_final_ns'],process_wall_ns=c['wall_ns'],
            startup_ns=b.get('blender_startup_ns'),installed_import_ns=b.get('installed_import_ns'),
            host_timings_ns=reply['timings_ns'],entry_timings_ns=reply['entry_timings_ns'],
            source_costs=raw['qa_source_costs'],
            ledger_validation_ns=sum(x['elapsed_ns'] for x in b['costs'] if x['phase']=='arm_ledger_validation'),
            ledger_validation_count=b['cost_counts']['arm_ledger_validation'],
            source_work=reply['work']['source'],
            public_tool_text_bytes=text,public_image_bytes=b['public_image_bytes'],
            public_final_bytes=c['output_text_bytes'],input_prompt_bytes=c['input_text_bytes'],
            provider_retries=c['provider_retry_observations']))
        for f in (folder/'CONSUMER.json',folder/'events.jsonl',folder/'bridge_native/BRIDGE_RESULT.json',folder/'bridge_native/case_01.json'):
            inputs[str(f)]=sha(f)
    old=read(HERE/'cells/01/CONSUMER.json')
    old_events=[r['event'] for r in map(json.loads,(HERE/'cells/01/events.jsonl').read_text().splitlines())]
    old_usage=[e['usage'] for e in old_events if e.get('type')=='turn.completed'];assert len(old_usage)==1
    totals={}
    for label,values in [('formal12',all_usage),('all13',all_usage+old_usage)]:
        keys=set.intersection(*(set(v) for v in values))
        totals[label]={k:sum(v[k] for v in values) for k in sorted(keys) if all(type(v[k]) is int for v in values)}
    groups={}
    for version in ('A','B'):
        selected=[r for r in rows if r['version']==version]
        groups[version]={name:dist([r[name] for r in selected]) for name in (
            'scheduler_entry_ns','whole_tool_ns','post_run_close_ns','prompt_to_final_ns','process_wall_ns',
            'ledger_validation_ns','startup_ns','installed_import_ns')}
        groups[version]['source_total']=dist([r['host_timings_ns']['source_before']+
            r['host_timings_ns'].get('source_after',0) for r in selected])
        groups[version]['prepare_inclusive']=dist([c['elapsed_ns'] for r in selected for c in r['source_costs'] if c['phase']=='prepare_patch'])
        groups[version]['source_parse']=dist([c['elapsed_ns'] for r in selected for c in r['source_costs'] if c['phase']=='_parse_patch'])
        groups[version]['tool_text_bytes']=sum(r['public_tool_text_bytes'] for r in selected)
    run=read(HERE/'RUN_RESULT.json')
    recovery_interval=run['started_ns']-old['cleanup_end_ns']
    result={'schema':'plugin-version-ab-supplemental-public-metrics-v1','passed':True,'rows':rows,
        'groups':groups,'actual_usage_totals':totals,'old_attempt_usage_complete':old_usage[0],
        'initial_infra_prompt_to_final_ns':old['prompt_to_final_ns'],
        'initial_infra_process_wall_ns':old['wall_ns'],
        'between_failed_cleanup_and_formal_start_ns':recovery_interval,
        'recovery_interval_scope':'elapsed planning/adapter repair/preflight/admin coordination; not pure algorithm cost',
        'provider_request_count':None,'dollar_cost':None,'provider_resolved_effort':None,
        'provider_retry_observations':sum(len(r['provider_retries']) for r in rows)+len(old['provider_retry_observations']),
        'new_model_calls':0,'new_product_calls':0,'new_Blender_runs':0,
        'input_sha256':inputs,'script_sha256':sha(Path(__file__))}
    (HERE/'SUPPLEMENTAL_METRICS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'usage_totals':totals,'groups':groups,'recovery_interval_s':recovery_interval/1e9}))


if __name__=='__main__':main()
