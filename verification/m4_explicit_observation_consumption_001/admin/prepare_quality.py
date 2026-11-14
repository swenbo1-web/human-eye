"""Preserve actual explicit-slot quality evidence without cost ranking."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parents[1]
RUNTIME = Path('D:/he_explicit_001/formal')
OWNER = RUNTIME/'P1/o'
CONSUMER = RUNTIME/'P1/c'
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def save(name, value):
    with (HERE/name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def strip(value):
    if type(value) is dict:
        return {key: strip(item) for key, item in value.items()
                if not re.search(r'(^|_)(ns|ms|seconds|elapsed|duration|usage|tokens|cost|timing|metrics|stages|perf)(_|$)', key)}
    if type(value) is list:
        return [strip(item) for item in value]
    return value


def text_only(content):
    result = []
    for block in content:
        if block.get('type') != 'text':
            continue
        text = block['text']
        try:
            text = json.dumps(strip(json.loads(text)), ensure_ascii=False, allow_nan=False, indent=2)
        except ValueError:
            pass
        result.append(text)
    return result


def main():
    record = read(CONSUMER/'CONSUMER.json')
    tools = read(OWNER/'TOOLS.json')['tools']
    observations = read(OWNER/'OBSERVATIONS.json')
    producer = read(OWNER/'product_call_01/SERVICE_RESULT.json')
    contract = ROOT/'verification/m4_consumer_error_contract_001/result_contract.py'
    if hashlib.sha256(raw(contract)).hexdigest() != '5da53bbbfee51f1c07fde32ecf0e1ab1e79a73ef68feff388f709931840cd638':
        raise ValueError('original_result_contract_changed')
    spec = importlib.util.spec_from_file_location('_explicit_admin_result_binding', contract)
    binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding)
    calls, bindings = [], []
    for index, tool in enumerate(tools):
        folder = OWNER/('tool_'+str(tool['attempt']).zfill(2))
        request = read(folder/'REQUEST.json')
        response_path = folder/'RESPONSE.json'
        if not response_path.exists():
            response_path = folder/'ERROR_RESPONSE.json'
        response = read(response_path)
        observed = record['tool_calls'][index]['item'] if index < len(record['tool_calls']) else None
        bound = binding.bind_tool_result(response, observed)
        call = dict(attempt=tool['attempt'], tool=request['params']['name'],
            arguments=request['params']['arguments'], is_error=response.get('result', {}).get('isError'),
            result_text=text_only(response.get('result', {}).get('content', [])),
            request_sha256=INPUTS[str((folder/'REQUEST.json').resolve())],
            response_sha256=INPUTS[str(response_path.resolve())], result_binding=bound,
            image_sha256=[hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest()
                          for block in response.get('result', {}).get('content', []) if block.get('type') == 'image'])
        calls.append(call)
        bindings.append(bound)
    events = [json.loads(line)['event'] for line in raw(CONSUMER/'events.jsonl').decode('utf8').splitlines()]
    messages = [dict(event_type=event['type'], **event['item']) for event in events
                if event.get('item', {}).get('type') == 'agent_message']
    terminal = [event['type'] for event in events if event['type'] in ('turn.completed', 'turn.failed', 'error')]
    final_path = CONSUMER/'PUBLIC_FINAL.txt'
    if final_path.exists():
        raise ValueError('this_normalization_describes_the_observed_missing_final_only')
    normalized = dict(schema='region-localization-normalized-v1',
        scoring_role='Actual missing-final normalization. No product facts substituted for a final answer.',
        slots=[dict(slot_id='P1', raw_answer_path=str(final_path.resolve()), raw_answer_sha256=None,
            coverage_use_excerpt='', finite_pool_scope_correct=False, global_invisibility_overclaim=None,
            sources=[], panels=[], unsupported=[], questions={},
            missing_final_artifact=True)])
    save('NORMALIZED.json', normalized)
    save('TOOL_TEXT.json', dict(schema='explicit-observation-quality-tool-evidence-v1', slot_id='P1',
        tools=calls, actual_owner_tool_attempts=len(tools), actual_CLI_tool_items=len(record['tool_calls']),
        all_result_envelopes_bound=all(item['matched'] for item in bindings),
        actual_product_frames=[dict(view=frame['view_name'], ref=frame['image_ref'], PNG_sha256=frame['image_sha256'])
                               for frame in producer['frames']],
        observed_raster_origins=[dict(attempt=row['attempt_id'], view=row['view_name'], origin=row['origin'], status=row['status'])
                                for row in observations['render_attempts']],
        costs_removed=True))
    save('MODEL_MESSAGES.json', dict(schema='explicit-observation-model-messages-v1',
        public_final_artifact_exists=False, consumer_valid_completion=record['valid_completion'],
        last_saved_agent_message=record.get('final'), terminal_event_types=terminal,
        agent_messages=messages, errors=record.get('errors'),
        scope='Public agent messages retained as progress evidence. They do not substitute for the absent final artifact.'))
    save('QUALITY_INPUTS.json', dict(schema='explicit-observation-quality-inputs-v1', inputs_sha256=INPUTS,
        cost_analysis_performed=False,
        limitation='Initial status inspection exposed nested single-slot cleanup timestamps. FINAL_TIMING and usage were not inspected or ranked. Subsequent review outputs remove timing fields.'))
    print(json.dumps(dict(normalized_slots=1, public_final_exists=False, owner_tools=len(tools),
                         actual_product_calls=len(observations['active']), terminal_event_types=terminal,
                         all_result_envelopes_bound=all(item['matched'] for item in bindings), cost_analysis_performed=False)))


if __name__ == '__main__':
    main()
