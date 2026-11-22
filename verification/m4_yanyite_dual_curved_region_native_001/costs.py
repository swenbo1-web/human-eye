"""Measure only observed stages in closed Yanyite slots and keep nesting explicit."""

import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def window(start, end):
    if type(start) is not int or type(end) is not int:
        return None
    if end < start:
        raise ValueError('observed_cost_window_inverted')
    return end-start


def transport(slot):
    calls = []
    for folder in sorted((slot/'native/WIRE').glob('*')):
        raw = folder/'RESPONSE.bin'
        if not raw.is_file():
            continue
        response = read(raw)
        embedded = response.get('result',{}).get('result')
        prefix = 'HUMAN_EYE_BLENDER_MCP:'
        if not isinstance(embedded,str) or not embedded.startswith(prefix):
            continue
        capture = json.loads(embedded[len(prefix):]).get('result',{})
        if capture.get('schema') != 'human-eye-scene-delta-v1':
            continue
        resources = capture['resources']
        calls.append({'wire_folder':folder.name,'outer_RX_bytes':raw.stat().st_size,
                      'embedded_capture_bytes':len(embedded[len(prefix):].encode('utf8')),
                      'transferred_mesh_resources':len(resources),
                      'resource_encodings':type(resources).__name__,
                      'display_present':any('display' in key for key in capture['capture'])})
    return calls


def product_calls(slot):
    result = []
    for path in sorted((slot/'product_full').glob('call_*/SERVICE_RESULT.json')):
        value = read(path)
        work = value.get('work',{})
        stages = value.get('stages',{})
        actual = {}
        for name,stage in stages.items():
            if not isinstance(stage,dict) or 'elapsed_ns' not in stage:
                continue
            if window(stage.get('started_ns'),stage.get('closed_ns')) != stage['elapsed_ns']:
                raise ValueError('unbound_product_stage/'+path.name+'/'+name)
            actual[name] = stage['elapsed_ns']
        result.append({'call':path.parent.name,'producer_bytes':path.stat().st_size,'stage_ns':actual,
                       'work':work,'request_trace':value.get('request_trace')})
    return result


def slot_metrics(slot):
    result,publication = slot/'SLOT_RESULT.json',slot/'SLOT_PUBLICATION.json'
    if not result.is_file() or not publication.is_file():
        return {'status':'unrun' if not slot.exists() else 'unconfirmed'}
    result,publication = read(result),read(publication)
    if window(result['started_ns'],publication['published_ns']) != publication['complete_slot_ns']:
        raise ValueError('publication_cost_not_original_clock/'+slot.name)
    summary = {
        'status':publication['status'],'complete_slot_ns':publication['complete_slot_ns'],
        'startup_to_ready_ns':window(result['started_ns'],result.get('ready_ns')),
        'models':result['model_consumers'],'paid_API_calls':result['paid_API_calls'],
        'closes_verified':bool((result.get('closure_verification') or {}).get('passed')),
        'capture_transport':transport(slot),'product_calls':product_calls(slot),
        'native_calls':rows(slot/'NATIVE_CALLS.jsonl'),
    }
    budget = result.get('budget') or {}
    summary['budget_slot'] = budget.get('slots',{}).get(slot.name)
    device = slot/'DEVICE_EVIDENCE.json'
    if device.is_file():
        value = read(device)
        summary['device_sources'] = value['sources']
        summary['device_events'] = value['events']
        summary['internal_image_files'] = [
            {'view':f.get('view_name'),'PNG_bytes':f.get('PNG_bytes'),'NPZ_bytes':f.get('NPZ_bytes')}
            for f in value['frames']]
        summary['independent_source_capture'] = {'initial':result.get('initial_source'),'terminal':result.get('terminal_source')}
    bridge = slot/'owner/BRIDGE_RESULT.json'
    if bridge.is_file():
        calls = read(bridge)['calls']
        summary['public_requests'] = [{key:call.get(key) for key in
            ('attempt','name','status','started_ns','closed_ns','response_ready_ns','response_bytes','content_metrics','is_error')}
            for call in calls]
        summary['public_request_sum_ns'] = sum(elapsed for call in calls if (elapsed :=
            window(call.get('started_ns'),call.get('closed_ns'))) is not None)
    consumer = slot/'consumer/CONSUMER.json'
    if not consumer.is_file():
        return summary
    data = read(consumer)
    actual_usage = data['raw_usage_events']
    usage = data['usage']
    output, input_, cached = (usage.get(key) for key in ('output_tokens','input_tokens','cached_input_tokens'))
    if all(type(value) is int and value>=0 for value in (output,input_,cached)):
        if cached > input_:
            raise ValueError('original_CLI_cached_tokens_exceed_reported_input')
        usage_total = {'reported_input_plus_output':input_+output,'reported_input_minus_cache_plus_output':input_-cached+output}
    else:
        usage_total = None
    completed = [r['perf_ns'] for r in data['tool_calls'] if r.get('type')=='item.completed']
    first = min(completed,default=None)
    last = max(completed,default=None)
    submitted = data.get('prompt_submitted_ns')
    final = data.get('final_received_ns')
    summary['consumer_observed'] = {
        'valid_completion':data.get('valid_completion'),
        'prompt_sha256':data.get('input_sha256'),'raw_usage_events':actual_usage,'reported_usage':usage,'usage_totals':usage_total,
        'reported_text_bytes':data.get('public_text_bytes'),'bridge_public_text_bytes':data.get('bridge_public_text_bytes'),
        'reported_PNG_bytes':data.get('public_image_bytes'),'reported_PNG_count':data.get('public_image_count'),
        'actual_tool_accounting':data.get('tool_accounting'),'safe_to_continue':data.get('safe_to_continue'),
        'start_to_prompt_ns':window(result['started_ns'],submitted),'prompt_to_final_ns':window(submitted,final),
        'prompt_to_first_completed_CLI_tool_event_ns':window(submitted,first),
        'first_to_last_completed_CLI_tool_event_ns':window(first,last),
        'last_completed_CLI_tool_event_to_final_ns':window(last,final),
        'final_to_publication_ns':window(final,publication['published_ns']),
    }
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runtime',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    report = {label:slot_metrics(args.runtime.resolve(strict=True)/'slots'/label) for label in ('QN','QP','N1','P1')}
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump({'slots':report,'window_note':'Native, product, bridge and CLI measurements may be nested.',
                   'provider_internal_time_and_model_received_context':'unobserved'},stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
