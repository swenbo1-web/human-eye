"""Read-only independent audit of both formal dual-region transport histories."""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from runpy import run_path
import sys


RUN = Path('D:/he_perf050_dual_region_occlusion_transfer_001')
VERIFICATION = Path.cwd()/'verification'
NS = VERIFICATION/'perf050_dual_region_occlusion_transfer_001'
COSTS = VERIFICATION/'perf050_readonly_product_pilot_001/consumer/costs.py'


def verify(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def pin(path):
    raw = path.read_bytes()
    return {'path':str(path.resolve(strict=True)), 'bytes':len(raw), 'sha256':digest(raw)}


def tool_document(blocks):
    for block in blocks:
        if block.get('type') != 'text':
            continue
        try:
            doc = json.loads(block['text'])
        except json.JSONDecodeError:
            continue
        if isinstance(doc,dict):
            return doc
    return {}


def response_image_paths(blocks):
    paths = []
    wanted = {'local_image_path','image_path'}

    def collect(value):
        if isinstance(value,dict):
            paths.extend(v for k,v in value.items() if k in wanted and isinstance(v,str))
            for item in value.values():
                collect(item)
        elif isinstance(value,list):
            for item in value:
                collect(item)

    for block in blocks:
        if block.get('type') != 'text':
            continue
        for candidate in (block['text'],block['text'].partition('\n')[2]):
            if not candidate:
                continue
            try:
                collect(json.loads(candidate))
                break
            except json.JSONDecodeError:
                pass
    return sorted(set(paths))


def product_summary(arguments, document):
    query = arguments.get('query')
    if not isinstance(query,dict):
        return None
    target = query.get('region',{}).get('object')
    visibility = document.get('visibility') or document.get('facts',{}).get('visibility') or {}
    witness = visibility.get('complete_witness')
    task = document.get('task_result',{}).get('facts',{}).get('surface_proximity')
    return {'mode':query.get('mode'),'selected_object':target,'reference':query.get('reference'),
        'requested_facts':query.get('requested_facts'),'include_image_present':'include_image' in arguments,
        'include_image':arguments.get('include_image'),'detail':arguments.get('response_detail','omitted'),
        'response_status':document.get('status'),'observation_status':document.get('observation_status'),
        'visibility_status':visibility.get('status'),'visibility_reason':visibility.get('reason'),
        'visibility_unknown':visibility.get('unknown'),'complete_witness':witness,
        'distance_present':bool(task and task.get('status')=='measured'),'distance':task,
        'top_region_ref_present':bool(document.get('region_ref')),
        'per_view':[{k:view[k] for k in ('view_name','status','geometry_status','first_blocker','reason')
                    if k in view} for view in document.get('view_attempts',[]) if isinstance(view,dict)]}


def arm(label, fixed, summarize, truth):
    slot = RUN/'slots'/label
    consumer_root = slot/'consumer'
    result_path, publication_path = (slot/name for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
    result, publication = read(result_path), read(publication_path)
    consumer = read(consumer_root/'CONSUMER.json')
    verify(publication['result_sha256']==pin(result_path)['sha256'] and result.get('freeze_sha256')==fixed,
           'formal_slot_publication_or_freeze_not_bound/'+label)
    verify(publication['status']==result['status']=='completed' and result['model_consumers']==1
           and result['closure_verification']['passed'] and result['independent_before_after']['passed'],
           'formal_slot_did_not_close_completed/'+label)
    costs = summarize(slot,fixed)
    verify(costs['cost_evidence_verified'] and costs['consumer_status']=='completed','retained_clock_reader_not_bound/'+label)
    events = lines(consumer_root/'stdout.raw.bin')
    event_calls = [row['item'] for row in events if row.get('type')=='item.completed'
        and row.get('item',{}).get('type')=='mcp_tool_call']
    event_answers = [row['item']['text'] for row in events if row.get('type')=='item.completed'
        and row.get('item',{}).get('type')=='agent_message']
    final = (consumer_root/'PUBLIC_FINAL.txt').read_bytes()
    verify(event_answers and event_answers[-1].encode()==final,'raw_agent_message_final_differs/'+label)
    usage = [event['usage'] for event in events if event.get('type')=='turn.completed']
    verify(len(usage)==1 and usage==costs['raw_CLI_usage']==consumer['raw_usage_events'], 'raw_usage_inconsistent/'+label)
    rows=[]
    models = [row['model'] for row in events if row.get('type')=='thread.started' and 'model' in row]
    for timing,event in zip(costs['actual_requests'],event_calls,strict=True):
        ordinal=timing['attempt']
        request_path=Path(timing['stdio_TX']['path'])
        response_path=Path(timing['stdio_RX']['path'])
        request,response=read(request_path),read(response_path)
        carrier=read(request_path.with_name('RECEIPT.json'))
        params=request['params']
        outer_block=response.get('result',{}).get('content',[])
        cli_result=event.get('result') or {}
        verify(pin(request_path)==timing['stdio_TX'] and pin(response_path)==timing['stdio_RX']
          and carrier['attempt']==ordinal and carrier['origin']=='owner' and request['id']==response['id']
          and params['name']==event['tool']==timing['tool'] and params['arguments']==event['arguments']
          and request==read(Path(timing['owner_request']['path']))
          and response==read(Path(timing['owner_response']['path']))
          and (outer_block==cli_result.get('content') or bool(event.get('error'))),
          'raw_stdio_owner_cli_binding_failed/'+label+'/'+str(ordinal))
        product_file=slot/'owner'/f'tool_{ordinal:02d}'/'PRODUCT_RESPONSE.json'
        product=timing['product']
        if product:
            inner=read(product_file)
            verify(inner['result'].get('content')==outer_block and inner['result'].get('isError',False)==response['result'].get('isError',False),
                   'inner_product_content_differs_from_outer/'+label+'/'+str(ordinal))
        verify(not timing['CLI_binding'] or timing['CLI_binding']=='content_and_envelope_match' or bool(event.get('error')),
               'consumer_archive_found_unsupported_binding/'+label+'/'+str(ordinal))
        document=tool_document(outer_block)
        png=[{'bytes':len(raw),'sha256':digest(raw)} for raw in (
            base64.b64decode(block['data'],validate=True) for block in outer_block if block.get('type')=='image' and block.get('mimeType')=='image/png')]
        verify(png==timing['wire_content']['PNG'],'carrier_image_digest_disagrees/'+label+'/'+str(ordinal))
        rows.append({'attempt':ordinal,'tool':params['name'],'cli_item':event['id'],'mcp_TX':pin(request_path),'mcp_RX':pin(response_path),
          'args':params['arguments'],'reply_text_bytes':timing['wire_content']['text_bytes'],'CLI_text_bytes':timing['CLI_delivered_text_bytes'],
          'image_PNGs':png,'public_PNG_paths':response_image_paths(outer_block),'error':bool(event.get('error') or timing['wire_content']['error']),
          'cli_item_exact_content':outer_block==cli_result.get('content'),
          'after_previous_ms':timing['after_previous_result_ms'],'wire_RTT_ms':timing['tool_wire_RTT_ms'],
          'dispatch_to_CLI_ms':timing['dispatch_to_CLI_result_ms'],'owner_ms':timing['owner_window_ms'],
          'inner_product_RPC_ms':(product or {}).get('client_RPC_ms'),'product_rasters':(product or {}).get('raster_attempts'),
          'product_semantics':product_summary(params['arguments'],document) if product else None})
    raw_selected = [r for r in rows if (r['product_semantics'] or {}).get('mode')=='source_region']
    first = raw_selected[0] if raw_selected else None
    repeats = {sha:count for sha,count in Counter(i['sha256'] for r in rows for i in r['image_PNGs']).items() if count>1}
    frames=read(slot/'DEVICE_EVIDENCE.json')['frames']
    by_path={Path(row['PNG']):row for row in frames}
    linked=[]
    terminal=read(slot/'TERMINAL_SOURCE.json')
    truth['verify_geometry'](terminal)
    for target in set(re.findall(r'\]\(<?([A-Za-z]:[/\\][^\s>)]+\.png)>?\)',final.decode())):
        path=Path(target)
        if not path.is_relative_to(slot) or path not in by_path or not path.is_file():
            linked.append({'reference':target,'same_slot_original':False})
            continue
        image=pin(path)
        verify(image['sha256']==by_path[path]['PNG_sha256'],'final_png_digest_mismatch/'+label)
        references=[r['attempt'] for r in rows if any(i['sha256']==image['sha256'] for i in r['image_PNGs'])]
        public_links=[r['attempt'] for r in rows if path in [Path(value) for value in r['public_PNG_paths']]]
        image_proof=truth['verify_image'](slot,by_path[path],packet=terminal)
        linked.append({'reference':target,'same_slot_original':bool(references),'file':image,
          'protected_path_deliveries':public_links,'same_bytes_image_deliveries':references,'independent_image':image_proof})
    counts=result['budget']['slots'][label]
    return {'label':label,'slot_result':pin(result_path),'slot_publication':pin(publication_path),'actual_stdout':pin(consumer_root/'stdout.raw.bin'),
      'final_agent_message':pin(consumer_root/'PUBLIC_FINAL.txt'),'terminal_source':pin(slot/'TERMINAL_SOURCE.json'),
      'first_source_region':first,'source_region_adoption_denominator':int(first is not None),'source_region_calls':len(raw_selected),
      'attempts':rows,'repeated_PNG_hashes':repeats,'actual_final_linked_images':linked,'observed_model_at_start':models,
      'actual_configuration':costs['requested_consumer_configuration'],'clock_ms':costs['clock_ms'],'raw_CLI_usage':usage,
      'input_plus_output_tokens':costs['input_plus_output_tokens'],'CLI_text_bytes':sum(r['CLI_text_bytes'] or 0 for r in rows),
      'CLI_public_PNG_bytes':costs['CLI_public_PNG_bytes'],'CLI_public_PNG_count':costs['CLI_public_PNG_count'],
      'slot_budget_counts':counts,'observed_raster_views':[(row['origin'],row.get('view'),row['ref']) for row in frames]}


def main(output):
    sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
    frozen=NS/'FROZEN.json'
    fixed=pin(frozen)['sha256']
    summarize=run_path(str(COSTS))['summarize']
    truth=run_path(str(NS/'checks/truth.py'))
    arms=[arm(label,fixed,summarize,truth) for label in ('N1','P1')]
    result={'passed_transport':True,'formal_arms':arms,'provider_timing':None,'provider_internal_context':None,
      'provider_billing':None,'raw_source_pins':[pin(path) for path in (frozen,COSTS,NS/'checks/truth.py',Path(__file__))]}
    with output.open('xb') as stream:
        stream.write((json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())
    print(json.dumps(pin(output)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output)
