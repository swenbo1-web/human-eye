"""Reconcile the controlled treatment, product transport, and actual CLI usage."""

from collections import Counter
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m1_source_region_first_packet_consumption_001')
TOOLS = {'human_eye_scene_observe'}
RETAINED = run_path(str(V/'perf050_readonly_product_pilot_001/consumer/costs.py'))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def same_except_detail(old, new):
    return ({key:value for key,value in old.items() if key!='response_detail'}
            == {key:value for key,value in new.items() if key!='response_detail'})


def describe_attempt(row, seen_png):
    pngs = []
    for image in row['wire_content']['PNG']:
        digest = image['sha256']
        pngs.append({**image,'same_digest_previously_delivered':digest in seen_png})
        seen_png.add(digest)
    args = row['arguments'] or {}
    query = args.get('query') or {}
    product = row['product']
    return {'attempt':row['attempt'],'tool':row['tool'],'mode':query.get('mode'),
            'request_detail':args.get('response_detail'),'actual_product_detail':None if not product else product['arguments'].get('response_detail'),
            'actual_rasters':None if not product else product['raster_attempts'], 'error':bool(row['wire_content']['error']),
            'text_bytes':row['wire_content']['text_bytes'],'images':pngs,'request_to_cli_ms':row['dispatch_to_CLI_result_ms']}


def collect(output):
    read, digest = RETAINED['read'], RETAINED['digest']
    frozen_path = NS/'FROZEN.json'
    frozen = read(frozen_path)
    sha = digest(frozen_path)
    slots = []
    for label in ('A1','B1'):
        path = RUN/'slots'/label
        summary = RETAINED['summarize'](path,sha)
        if summary['status']=='unrun':
            slots.append(summary)
            continue
        requests = summary['actual_requests']
        product_calls = [row for row in requests if row['tool'] in TOOLS and row['product'] is not None]
        treatment = RETAINED['lines'](path/'FIRST_PACKET_TREATMENT.jsonl')
        meters = {row['id']:row for row in RETAINED['lines'](path/'mcp_io/MCP_IO.jsonl') if row.get('method')=='tools/call'}
        inner = {row['request']['id']:row for row in RETAINED['lines'](path/'PUBLIC_REQUESTS.jsonl')}
        seen, events, attempted = set(), [], None
        require(len(product_calls)==len(treatment),'treatment_and_public_attempt_count_differ/' + label)
        for count,(row, log) in enumerate(zip(product_calls,treatment,strict=True),1):
            parsed = read(Path(row['product']['request_file']['path']))
            identifier, args = parsed['id'], parsed['params']['arguments']
            original = log['original_arguments']
            applied = log['decision']['applied']
            require(log['index']==count and original==row['arguments'] and args==log['product_arguments']
                    and same_except_detail(original,args)
                    and (args.get('response_detail')==frozen['response_detail_by_slot'][label] if applied else args==original),
                    'non_target_field_or_unmatched_transport_changed/' + label)
            meter, inside = meters[identifier], inner[identifier]
            receipt = inside['receipt']
            leaf = path/'mcp'/f"rpc_{receipt['index']:02d}"
            tx,rx = leaf/'TX.bin',leaf/'RX.bin'
            require(digest(tx)==meter['TX_sha256'] and read(tx)==parsed
                    and digest(rx)==receipt['RX_sha256'] and read(rx)==inside['response'],
                    'formal_product_dispatch_not_bound_to_raw_TX_RX/' + label)
            if applied:
                require(attempted is None,'treatment_was_reapplied/' + label)
                attempted = {'outer_attempt':row['attempt'],'original_arguments':original,'actual_product_arguments':args,
                             'product_TX':RETAINED['file_receipt'](tx),'product_RX':RETAINED['file_receipt'](rx),
                             'outer_RX':row['stdio_RX'],'decision':log['decision'],'outcome':log['outcome'],
                             'body_bytes':row['wire_content']['text_bytes'],'raw_images':row['wire_content']['PNG'],
                             'CLI_delivered_text_bytes':row['CLI_delivered_text_bytes']}
        for row in requests:
            events.append(describe_attempt(row,seen))
        made = [e for e in events if e['tool'] in TOOLS and e['actual_product_detail']=='full'
                and attempted and e['attempt']>attempted['outer_attempt']]
        counts = (summary.get('budget') or {}).get('slots',{}).get(label,{})
        missing = None if summary['status']!='completed' else summary['thread_id'] is None
        if missing or summary.get('initial_prompt_sha256')!=frozen['prompt_sha256']:
            summary['cost_evidence_verified'] = False
        summary.update(treatment_attempted=attempted is not None,treatment=attempted,
                       tool_ledger=events, tool_counts=dict(Counter(e['tool'] for e in events)),
                       later_explicit_full_calls=[e['attempt'] for e in made],
                       raster_actual=counts.get('raster_actual'),
                       original_paid_API_calls=read(path/'SLOT_RESULT.json').get('paid_API_calls'))
        slots.append(summary)
    threads = [r['thread_id'] for r in slots if r.get('thread_id')]
    require(len(threads)==len(set(threads)),'observed_threads_not_independent')
    result = {'schema':'m1-source-region-first-packet-cost-v1','freeze_sha256':sha,'slots':slots,
              'planned_formal_slots':2,'actual_model_consumers':sum(s['model_consumers_launched'] for s in slots),
              'distinct_fresh_threads':len(threads),'provider_timing':None,'provider_input':None,'provider_billing':None,
              'scope':'Consumer CLI usage and local clocks. The controlled slot pair is diagnostic only.'}
    with output.open('x',encoding='utf8',newline='\n') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')
    print(digest(output))


if __name__=='__main__':
    collect(Path(sys.argv[1]))
