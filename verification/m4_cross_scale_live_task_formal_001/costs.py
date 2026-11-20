"""Account original observed runtime and delivery without reading private CLI event bodies."""

import base64
import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import EXTERNAL, read, save, sha


def lines(path):
    return [json.loads(row) for row in path.read_bytes().splitlines()] if path.is_file() else []


def elapsed(start, end):
    return (end - start) / 1e6 if type(start) is int and type(end) is int and end >= start else None


def stages(values):
    return {name: stage['elapsed_ns'] for name, stage in values.items()
            if type(stage) is dict and type(stage.get('elapsed_ns')) is int}


def slot_summary(label):
    folder = EXTERNAL / 'slots' / label
    publication = folder / 'SLOT_PUBLICATION.json'
    if not publication.is_file():
        return {'label': label, 'status': 'unrun', 'model_consumers': 0,
                'reason': 'formal_launch_not_admitted_by_qualification'}
    pub = read(publication)
    result_path = folder / 'SLOT_RESULT.json'
    assert pub['result_sha256'] == sha(result_path)
    row = read(result_path)
    work = row.get('budget', {}) or {}
    public = []
    meter = {item['id']: item for item in lines(folder / 'mcp_io/MCP_IO.jsonl') if item.get('method') == 'tools/call'}
    audit = lines(folder / 'product_audit.jsonl')
    traces = {trace['annotations'].get('mcp_request_id'): trace for event in audit
              if event.get('event') == 'request_trace' for trace in [event['trace']]}
    rpc = {x['request']['id']: x for x in lines(folder / 'PUBLIC_REQUESTS.jsonl')}
    consumer_binding_path = folder / 'consumer/BUSINESS_SOURCE_BINDING.json'
    delivery = read(consumer_binding_path) if consumer_binding_path.is_file() else {}
    deliveries = {row['attempt']: row for row in delivery.get('result_contracts', [])}
    last_received = None
    tool_folder = folder / 'owner'
    native = read(folder / 'DEVICE_EVIDENCE.json') if (folder / 'DEVICE_EVIDENCE.json').exists() else {}
    for path in sorted(tool_folder.glob('tool_*')):
        if not (path / 'RESPONSE.json').is_file():
            continue
        request = read(path / 'REQUEST.json')
        response = read(path / 'RESPONSE.json')
        receipt = read(path / 'RECEIPT.json')
        result = response.get('result', {})
        contents = result.get('content', [])
        records = {'rpc_id': request['id'], 'tool': request['params']['name'], 'request_sha256': sha(path / 'REQUEST.json'),
                   'response_sha256': sha(path / 'RESPONSE.json'), 'error': bool(result.get('isError')),
                   'owner_started_ns': receipt.get('started_ns'), 'owner_closed_ns': receipt.get('closed_ns'),
                   'owner_window_ms': elapsed(receipt.get('started_ns'), receipt.get('closed_ns')),
                   'text_bytes': sum(len(x['text'].encode()) for x in contents if x['type'] == 'text'),
                   'png_bytes': [len(base64.b64decode(x['data'], validate=True)) for x in contents if x['type'] == 'image']}
        attempt = int(path.name.rsplit('_', 1)[-1])
        received = deliveries.get(attempt, {})
        records.update(attempt=attempt, CLI_received_ns=received.get('CLI_received_ns'),
                       CLI_text_bytes=received.get('CLI_text_UTF8_bytes'), CLI_images=received.get('CLI_images'),
                       original_delivery_binding=received.get('reason'),
                       previous_CLI_result_to_tool_request_ms=elapsed(last_received, receipt.get('started_ns')),
                       tool_request_to_CLI_result_ms=elapsed(receipt.get('started_ns'), received.get('CLI_received_ns')))
        last_received = received.get('CLI_received_ns')
        target = path / 'PRODUCT_REQUEST.json'
        if target.is_file():
            product_request = read(target)
            ident = product_request['id']
            trace = traces.get(ident) or {}
            clock = meter.get(ident) or {}
            whole = rpc.get(ident) or {}
            before_format = whole.get('producer_archive')
            raw_result = {} if not before_format else read(Path(before_format['path']))
            records.update(product_request_arguments=product_request['params']['arguments'],
                           product_exact_first_template=product_request['params']['arguments'] == read(NS / 'inputs/REQUEST.json'),
                           product_rpc_ms=elapsed(clock.get('request_received_ns'), clock.get('reply_completed_ns')),
                           product_spans_ns={x['name']: x['duration_ns'] for x in trace.get('spans', [])},
                           product_service_stages_ns=stages(raw_result.get('stages', {})),
                           product_new_work=raw_result.get('work'), product_raster_attempts=clock.get('raster_actual'))
            frames = raw_result.get('constructed_frames', []) if clock.get('raster_actual') else []
            task_rows = ((raw_result.get('facts') or {}).get('region_task') or {}).get('rows', [])
            region_by_source = {x['host_id']: x['object_name'] for x in task_rows}
            scopes = {x['scope_id']: region_by_source.get((x['binding'].get('region_source') or {}).get('host_id'))
                      for x in raw_result.get('scopes', [])}
            selected_ids = {x['frame_identity'] for x in raw_result.get('frames', [])}
            records['product_generation_frames'] = [{'view': x['view_name'], 'scope': x['scope_id'],
                   'region_object': scopes.get(x['scope_id']), 'selected': x['frame_identity'] in selected_ids,
                   'construction_phases_ns': stages(x['stages'])} for x in frames]
        public.append(records)
    consumer_path = folder / 'consumer/CONSUMER.json'
    consumer = read(consumer_path) if consumer_path.is_file() else {}
    original_usage = []
    raw_stdout = folder / 'consumer/stdout.raw.bin'
    if raw_stdout.is_file():
        with raw_stdout.open('rb') as stream:
            for line in stream:
                if line.startswith(b'{"type":"turn.completed",'):
                    original_usage.append(json.loads(line)['usage'])
    before = row.get('started_ns')
    answer = consumer.get('final_received_ns')
    raw_configuration = folder / 'consumer/ACTUAL_CONFIGURATION.json'
    matched = row.get('diagnostic_calls', [])
    return {'label': label, 'status': row['status'], 'errors': row['errors'], 'publication_sha256': sha(publication),
            'full_window_ms': elapsed(before, pub['published_ns']), 'startup_to_ready_ms': elapsed(before, row.get('ready_ns')),
            'startup_to_answer_ms': elapsed(before, answer), 'answer_to_publish_ms': elapsed(answer, pub['published_ns']),
            'prompt_to_first_successful_evidence_ms': elapsed(consumer.get('prompt_submitted_ns'),
                                                               delivery.get('first_CLI_nonempty_successful_evidence_ns')),
            'first_successful_evidence_to_answer_ms': elapsed(delivery.get('first_CLI_nonempty_successful_evidence_ns'), answer),
            'last_tool_to_answer_ms': elapsed(delivery.get('last_CLI_tool_result_ns'), answer),
            'binary_delivery_errors': delivery.get('binding_errors'),
            'initial_source': row.get('initial_source'), 'terminal_source': row.get('terminal_source'),
            'cleanup_started_ns': row.get('cleanup_started_ns'), 'model_consumers': row['model_consumers'],
            'budget_slot': work.get('slots', {}).get(label), 'cumulative_budget': work.get('counts'),
            'native_frame_stages': [{'ref': f.get('ref'), 'view': f.get('view'), 'stages_ns': stages(f.get('stages', {}))}
                                    for f in native.get('frames', [])], 'native_events': native.get('events', []),
            'diagnostic_calls': matched, 'attempts': public, 'original_CLI_usage': original_usage,
            'CLI_fallback': read(raw_configuration).get('fallback_state') if raw_configuration.is_file() else None,
            'tool_text_total_bytes': sum(x['text_bytes'] for x in public),
            'tool_image_total_bytes': sum(sum(x['png_bytes']) for x in public)}


if __name__ == '__main__':
    history = NS.parent / 'm4_cross_scale_live_task_recovery_001/RUNTIME_REVIEW.json'
    previous = [{'label': row['label'], 'full_window_ms': row['full_window_ms'],
                 'diagnostic_calls': row['diagnostic_calls'], 'status': row['status']}
                for row in read(history)['slots'] if row['label'] in ('QN', 'QP')]
    save(NS / 'RUNTIME_REVIEW.json', {'slots': [slot_summary(label) for label in ('N1', 'P1')],
          'previous_qualification_scope_only': previous, 'previous_qualification_review_sha256': sha(history),
          'new_asset_builds': 0, 'additional_qualification_owned': 0, 'cash_fees': None,
          'actual_internal_provider_input': None})
