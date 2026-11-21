"""Account actual tool selection, raw argument forwarding and full-slot costs."""

from collections import Counter
import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUN = Path('D:/he_m1_source_region_task_entry_holdout_001')
NARROW = 'human_eye_source_region_measure'
OBSERVE = 'human_eye_scene_observe'
legacy = run_path(str(V/'perf050_readonly_product_pilot_001/consumer/costs.py'))


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def paired_scope(row,ids):
    tool = row['tool']
    args = row['arguments'] or {}
    survey = args if tool==NARROW else args.get('query') or {}
    target = [{'name':'Obj_08'},{'id':ids['Obj_08']}]
    reference = [{'name':'Obj_04'},{'id':ids['Obj_04']}]
    if tool==NARROW or survey.get('mode')=='source_region':
        selection = survey.get('region') or {}
        region_ref = survey.get('region_ref') or {}
        selected = ((selection.get('object') in target and sorted(selection.get('source_triangle_indices') or [])==[0,1,8,9])
                    or (region_ref.get('host_id')==ids['Obj_08'] and region_ref.get('source_triangle_indices')==[0,1,8,9]))
        return 'selected' if selected and survey.get('reference') in reference else 'other'
    objects = survey.get('objects')
    if (survey.get('mode')=='task' and isinstance(objects,list) and len(objects)==2
            and objects[0] in target and objects[1] in reference):
        return 'whole'
    return 'other'


def collect(output):
    read,digest,lines,file_receipt = (legacy[key] for key in ('read','digest','lines','file_receipt'))
    frozen_path = NS/'FROZEN.json'
    frozen = read(frozen_path)
    freeze = digest(frozen_path)
    slots = []
    directories = {}
    for label in ('A1','B1'):
        path = RUN/'slots'/label
        summary = legacy['summarize'](path,freeze)
        if summary['status']=='unrun':
            slots.append(summary)
            continue
        result = read(path/'SLOT_RESULT.json')
        initial = read(path/'initial_capture/TERMINAL_SOURCE.json')
        ids = {obj['name']:obj['object_id'] for obj in initial.get('objects',[])}
        tools_path = path/'owner/TOOLS_SCHEMA.json'
        if tools_path.is_file():
            directories[label] = read(tools_path)
        calls = {p['request']['id']:p for p in lines(path/'PUBLIC_REQUESTS.jsonl')}
        meters = {p['id']:p for p in lines(path/'mcp_io/MCP_IO.jsonl') if p.get('method')=='tools/call'}
        seen = set()
        events = []
        for row in summary['actual_requests']:
            tool, inner = row['tool'], row['product']
            hashes = []
            for image in row['wire_content']['PNG']:
                key = image['sha256']
                hashes.append({**image,'repeated_raw_png':key in seen})
                seen.add(key)
            event = {'attempt':row['attempt'],'tool':tool,'estimated_scope_from_request':paired_scope(row,ids) if ids else None,
                     'actual_requested_detail':(row['arguments'] or {}).get('response_detail'),
                     'text_bytes':row['wire_content']['text_bytes'],'png':hashes,'error':row['wire_content']['error'],
                     'dispatch_to_CLI_ms':row['dispatch_to_CLI_result_ms']}
            if inner:
                request = read(Path(inner['request_file']['path']))
                ident = request['id']
                product = calls[ident]
                receipt = product['receipt']
                leaf = path/'mcp'/f"rpc_{receipt['index']:02d}"
                tx,rx = leaf/'TX.bin',leaf/'RX.bin'
                require(request['params']=={'name':tool,'arguments':row['arguments']}
                        and read(tx)==request and read(rx)==product['response']
                        and digest(tx)==meters[ident]['TX_sha256']
                        and digest(rx)==receipt['RX_sha256'],
                        'actual_natural_arguments_or_response_changed/' + label)
                event.update(product_TX=file_receipt(tx),product_RX=file_receipt(rx),product_rasters=inner['raster_attempts'])
                if not event['error']:
                    payload = json.loads(product['response']['result']['content'][0]['text'])
                    event['returned_schema'] = payload.get('schema',payload.get('schema_version'))
                    event['observation_status'] = payload.get('observation_status')
                    if NARROW==tool or payload.get('result_kind')=='source_region':
                        event['precise_selection'] = payload.get('region_ref',{}).get('source_triangle_indices')
            events.append(event)
        picked = [e for e in events if e['tool']==NARROW]
        chosen = [e for e in events if e['estimated_scope_from_request']=='selected' and not e['error']]
        counts = (summary.get('budget') or {}).get('slots',{}).get(label,{})
        summary.update(tool_ledger=events,tool_counts=dict(Counter(e['tool'] for e in events)),
                       narrow_attempts=len(picked),narrow_successes=sum(not e['error'] for e in picked),
                       first_selected_observation=chosen[0] if chosen else None,
                       actual_raster_attempts=counts.get('raster_actual'),paid_API_calls=result.get('paid_API_calls'))
        if summary['status']=='completed':
            require(summary['initial_prompt_sha256']==frozen['prompt_sha256'] and summary['cost_evidence_verified'],
                    'actual_formal_consumer_costs_not_bound/' + label)
        slots.append(summary)
    delta = None
    if set(directories)=={'A1','B1'}:
        a,b = (directories[k] for k in ('A1','B1'))
        compact = lambda value: len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
        require(b[:-1]==a and len(b)==len(a)+1 and b[-1]['name']==NARROW,
                'formal_catalogues_differ_beyond_one_new_tool')
        delta = {'model_facing_counts':[len(a),len(b)],'compact_JSON_array_bytes':[compact(a),compact(b)],
                 'array_byte_delta':compact(b)-compact(a),'new_tool_schema_B':compact(b[-1]),'new_tool_token_cost':None}
    threads = [s['thread_id'] for s in slots if s.get('thread_id')]
    require(len(threads)==len(set(threads)),'formal_threads_not_fresh_and_distinct')
    report = {'schema':'m1-source-region-task-entry-holdout-cost-v1','freeze_sha256':freeze,
              'actual_model_consumers':sum(s['model_consumers_launched'] for s in slots),'planned_model_consumers':2,
              'slots':slots,'actual_model_facing_catalogue_delta':delta,'provider_input':None,'provider_timing':None,
              'provider_cash_fees':None,'scope':'One natural pair on the frozen task. Complete timing includes runtime and CLI.'}
    with output.open('x',encoding='utf8',newline='\n') as sink:
        json.dump(report,sink,ensure_ascii=False,allow_nan=False,indent=2)
        sink.write('\n')
    print(digest(output))


if __name__=='__main__':
    collect(Path(sys.argv[1]))
