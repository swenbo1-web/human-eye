"""Reproduce the frozen cost reader for a turn with unreported usage and no final."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


NS = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_yanyite_dual_curved_region_native_001').resolve()


def metrics():
    frozen = json.loads((NS/'FROZEN.json').read_bytes())
    path = NS/'costs.py'
    expected, = [row for row in frozen['direct_inputs'] if Path(row['path'])==path]
    raw = path.read_bytes()
    if len(raw)!=expected['bytes'] or sha256(raw).hexdigest()!=expected['sha256']:
        raise ValueError('frozen_cost_reader_changed')
    source = raw.decode('utf8')
    original = "    output, input_, cached = (usage.get(key) for key in ('output_tokens','input_tokens','cached_input_tokens'))"
    adapted = "    output, input_, cached = ((usage or {}).get(key) for key in ('output_tokens','input_tokens','cached_input_tokens'))"
    clock_original = "    final = data.get('final_received_ns')"
    clock_adapted = "    final = data.get('final_received_ns') if data.get('valid_completion') else None"
    if source.count(original)!=1 or source.count(clock_original)!=1:
        raise ValueError('missing_usage_probe_anchor_changed')
    text = source.replace(original,adapted).replace(clock_original,clock_adapted)
    scope = {'__name__':'_frozen_cost_reader','__file__':str(path)}
    exec(compile(text,str(path),'exec'),scope)
    slots = {}
    for label in frozen['slots']:
        slot = RUNTIME/'slots'/label
        data = scope['slot_metrics'](slot)
        record = data.get('consumer_observed')
        if record is not None:
            events = scope['rows'](slot/'consumer/events.jsonl')
            text_bytes = 0
            for row in events:
                event = row['event']
                item = event.get('item',{})
                if event['type']=='item.completed' and item.get('type')=='mcp_tool_call':
                    text_bytes += sum(len(piece['text'].encode('utf8')) for piece in
                                      ((item.get('result') or {}).get('content') or [])
                                      if piece.get('type')=='text')
                if event['type']=='turn.failed':
                    record['actual_turn_failure'] = {'received_ns':row['perf_ns'],'error':event['error']}
            record['public_CLI_tool_text_bytes'] = text_bytes
        slots[label] = data
    return {'slots':slots,'original_cost_reader':expected,
            'adapter_reason':'Frozen reader expected a usage object. P1 CLI reported null and no usage events.',
            'model_reported_null_usage_preserved':True,
            'window_note':'Native, product, bridge and CLI times can be nested. Failed turns have no accepted final time.',
            'provider_internal_time_and_model_received_context':'unobserved'}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('output',type=Path)
    a = cli.parse_args()
    result = metrics()
    with a.output.open('x',encoding='utf8',newline='\n') as out:
        json.dump(result,out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write('\n')
