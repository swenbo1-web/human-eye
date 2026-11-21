"""Measure this run from the original wire, visible CLI events and host receipts."""

import argparse
import base64
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_perf050_readonly_product_pilot_001')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_receipt(path):
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': digest(path)}


def read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


def lines(path):
    if path.is_file():
        with path.open('rb') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    return []


def elapsed(start, stop):
    return (stop - start) / 1e6 if type(start) is int and type(stop) is int and start <= stop else None


def usage(folder, consumer, errors):
    original, timed = [], []
    raw = folder / 'stdout.raw.bin'
    if raw.is_file():
        with raw.open('rb') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    errors.append('CLI_stdout_unparsed_record')
                    continue
                if event.get('type') == 'turn.completed':
                    original.append(event.get('usage'))
    for row in lines(folder / 'events.jsonl'):
        if row['event'].get('type') == 'turn.completed':
            timed.append(row['event'].get('usage'))
    if raw.is_file() and not original == timed == consumer.get('raw_usage_events', []):
        errors.append('raw_timed_and_consumer_usage_not_equal')
    if len(original) != 1:
        return original, None
    only = original[0]
    if (type(only) is not dict or not all(type(only.get(key)) is int and only[key] >= 0 for key in
            ('input_tokens', 'output_tokens'))):
        errors.append('single_usage_missing_nonnegative_token_counts')
        return original, None
    return original, only['input_tokens'] + only['output_tokens']


def content_metrics(response):
    blocks = (response or {}).get('result', {}).get('content', [])
    return {'text_bytes': sum(len(block['text'].encode('utf8')) for block in blocks if block['type'] == 'text'),
            'PNG': [{'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                    for raw in (base64.b64decode(block['data'], validate=True) for block in blocks
                                if block.get('type') == 'image' and block.get('mimeType') == 'image/png')],
            'error': (response or {}).get('result', {}).get('isError', False) or 'error' in (response or {}),
            'response_present': response is not None}


def tool_stages(value):
    return {key: row['elapsed_ns'] / 1e6 for key, row in value.items()
            if type(row) is dict and type(row.get('elapsed_ns')) is int and row['elapsed_ns'] >= 0}


def product_record(owner_tool, products, meters, traces):
    request_path = owner_tool / 'PRODUCT_REQUEST.json'
    if not request_path.is_file():
        return None
    request = read(request_path)
    ident = request['id']
    packet = products.get(ident, {})
    meter = meters.get(ident, {})
    trace = traces.get(ident, {})
    producer = packet.get('producer_archive')
    raw = read(Path(producer['path'])) if producer else {}
    product_response = owner_tool / 'PRODUCT_RESPONSE.json'
    return {'request_file': file_receipt(request_path),
            'response_file': file_receipt(product_response) if product_response.is_file() else None,
            'arguments': request['params']['arguments'], 'producer_archive': producer,
            'service_stage_ms': tool_stages(raw.get('stages', {})), 'new_work': raw.get('work'),
            'request_trace_duration_ms': {span['name']: span['duration_ns'] / 1e6 for span in trace.get('spans', [])},
            'server_RPC_ms': elapsed(meter.get('request_received_ns'), meter.get('reply_completed_ns')),
            'client_RPC_ms': elapsed(packet.get('started_ns'), packet.get('client_returned_ns')),
            'raster_attempts': meter.get('raster_actual'),
            'constructed_frame_ms': [{'scope': row.get('scope_id'), 'view': row.get('view_name'),
                                      'stage_ms': tool_stages(row.get('stages', {}))}
                                     for row in raw.get('constructed_frames', [])]
            if meter.get('raster_actual') else []}


def attempt_rows(slot, errors):
    folder = slot / 'consumer'
    archive = read(folder / 'BUSINESS_SOURCE_BINDING.json')
    bound = {row['attempt']: row for row in archive.get('result_contracts', [])}
    products = {row['request']['id']: row for row in lines(slot / 'PUBLIC_REQUESTS.jsonl')}
    meters = {row['id']: row for row in lines(slot / 'mcp_io/MCP_IO.jsonl') if row.get('method') == 'tools/call'}
    traces = {trace['annotations'].get('mcp_request_id'): trace for event in lines(slot / 'product_audit.jsonl')
              if event.get('event') == 'request_trace' for trace in [event['trace']]}
    attempts = []
    previous_arrived = None
    for path in sorted(folder.glob('attachments/bridge_*/*/TX.bin')):
        request = read(path)
        if request.get('method') != 'tools/call':
            continue
        response_path = path.with_name('RX.bin')
        response = read(response_path) if response_path.is_file() else None
        stdio = read(path.with_name('RECEIPT.json'))
        index = stdio.get('attempt') or len(attempts) + 1
        owner_tool = slot / 'owner' / f'tool_{index:02d}'
        owner_receipt = read(owner_tool / 'RECEIPT.json')
        owner_request, owner_response = owner_tool / 'REQUEST.json', owner_tool / 'RESPONSE.json'
        binding = bound.get(index, {})
        arrival = binding.get('CLI_received_ns')
        if (index != len(attempts) + 1 or binding and binding.get('TX_sha256') != digest(path)
                or binding and response is not None and binding.get('RX_sha256') != digest(response_path)):
            errors.append('stdio_attempt_index_or_archive_binding_mismatch')
        params = request.get('params', {})
        attempts.append({'attempt': index, 'tool': params.get('name'), 'arguments': params.get('arguments'),
                         'request_started_ns': stdio.get('received_ns'), 'flush_completed_ns': stdio.get('flush_completed_ns'),
                         'CLI_received_ns': arrival, 'origin': stdio.get('origin'),
                         'stdio_TX': file_receipt(path),
                         'stdio_RX': file_receipt(response_path) if response is not None else None,
                         'owner_request': file_receipt(owner_request) if owner_request.is_file() else None,
                         'owner_response': file_receipt(owner_response) if owner_response.is_file() else None,
                         'wire_content': content_metrics(response),
                         'CLI_delivered_text_bytes': binding.get('CLI_text_UTF8_bytes'),
                         'CLI_delivered_images': binding.get('CLI_images'),
                         'CLI_binding': binding.get('reason'), 'error': stdio.get('error') or owner_receipt.get('error'),
                         'tool_wire_RTT_ms': elapsed(stdio.get('received_ns'), stdio.get('flush_completed_ns')),
                         'dispatch_to_CLI_result_ms': elapsed(stdio.get('received_ns'), arrival),
                         'owner_window_ms': elapsed(owner_receipt.get('started_ns'), owner_receipt.get('closed_ns')),
                         'after_previous_result_ms': elapsed(previous_arrived, stdio.get('received_ns')),
                         'product': product_record(owner_tool, products, meters, traces)})
        previous_arrived = arrival
    return attempts, archive.get('binding_errors'), archive.get('first_CLI_nonempty_successful_evidence_ns')


def summarize(slot, freeze=None):
    label = slot.name
    if not slot.is_dir():
        return {'label': label, 'status': 'unrun', 'model_consumers_launched': 0}
    result_path, published_path = slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'
    result, published = read(result_path), read(published_path)
    started = read(slot / 'SLOT_STARTED.json')
    account = result or started
    consumer_dir = slot / 'consumer'
    consumer = read(consumer_dir / 'CONSUMER.json')
    consumer_start = read(consumer_dir / 'CONSUMER_STARTED.json')
    actual = consumer or consumer_start
    errors = []
    if published and (not result or published.get('result_sha256') != digest(result_path)
                      or published.get('label') != label):
        errors.append('host_result_does_not_bind_original_publication')
    if freeze and account.get('freeze_sha256') != freeze:
        errors.append('host_result_does_not_bind_current_freeze')
    attempts, binding_errors, first_evidence = attempt_rows(slot, errors)
    raw_usage, input_output = usage(consumer_dir, consumer, errors)
    success = published.get('status') == 'completed' and consumer.get('valid_completion') is True
    if success and (binding_errors or len(attempts) != consumer['tool_accounting']['completed_business_calls']):
        errors.append('completed_run_has_unreconciled_business_attempts')
    answer_path = consumer_dir / 'PUBLIC_FINAL.txt'
    answer = consumer.get('final')
    if answer_path.is_file() and answer_path.read_bytes() != (answer or '').encode('utf8'):
        errors.append('public_final_does_not_bind_original_consumer')
    first_request = attempts[0]['request_started_ns'] if attempts else None
    last_result = next((row['CLI_received_ns'] for row in reversed(attempts)
                        if row['CLI_received_ns'] is not None), None)
    prompt = actual.get('prompt_submitted_ns')
    final = actual.get('final_received_ns')
    native = read(slot / 'DEVICE_EVIDENCE.json')
    began, done = account.get('started_ns'), published.get('published_ns')
    launch = actual.get('image_delivery', {}).get('CLI_process_launched') is True
    return {'label': label, 'status': published.get('status', 'unconfirmed'), 'cost_evidence_verified': not errors,
            'consumer_status': actual.get('status'), 'host_errors': account.get('errors'),
            'cost_review_errors': errors, 'binding_errors': binding_errors,
            'result_sha256': digest(result_path) if result else None,
            'model_consumers_launched': max(int(launch), int(account.get('model_consumers', 0))),
            'thread_id': actual.get('thread_id'), 'initial_prompt_sha256': actual.get('input_sha256'),
            'budget': account.get('budget'), 'raw_CLI_usage': raw_usage,
            'input_plus_output_tokens': input_output, 'answer_file': file_receipt(answer_path) if answer_path.is_file() else None,
            'CLI_raw_stdout_file': file_receipt(consumer_dir / 'stdout.raw.bin') if (consumer_dir / 'stdout.raw.bin').is_file() else None,
            'public_timed_events_file': file_receipt(consumer_dir / 'events.jsonl') if (consumer_dir / 'events.jsonl').is_file() else None,
            'requested_consumer_configuration': read(consumer_dir / 'ACTUAL_CONFIGURATION.json') or None,
            'actual_requests': attempts, 'tool_wire_text_total_bytes': sum(row['wire_content']['text_bytes'] for row in attempts),
            'tool_wire_PNG_bytes': sum(image['bytes'] for row in attempts for image in row['wire_content']['PNG']),
            'CLI_public_PNG_bytes': consumer.get('public_image_bytes'), 'CLI_public_PNG_count': consumer.get('public_image_count'),
            'ordinary_frames': [{'reference': frame.get('ref'), 'view': frame.get('view'),
                                 'phases_ms': tool_stages(frame.get('stages', {}))} for frame in native.get('frames', [])],
            'clock_ms': {'startup_to_ready': elapsed(began, account.get('ready_ns')), 'full_window': elapsed(began, done),
                         'ready_to_prompt': elapsed(account.get('ready_ns'), prompt), 'prompt_to_first_call': elapsed(prompt, first_request),
                         'prompt_to_first_evidence': elapsed(prompt, first_evidence), 'prompt_to_final': elapsed(prompt, final),
                         'between_tool_wait': sum(row['after_previous_result_ms'] for row in attempts
                                                  if row['after_previous_result_ms'] is not None),
                         'last_tool_to_final': elapsed(last_result, final),
                         'final_to_publish': elapsed(final, done), 'cleanup_to_publish': elapsed(account.get('cleanup_started_ns'), done)}}


def collect(run, output):
    freeze_path = HERE.parent / 'FROZEN.json'
    freeze = digest(freeze_path)
    rows = [summarize(run / 'slots' / label, freeze) for label in ('N1', 'P1')]
    fresh = [row.get('thread_id') for row in rows if row.get('thread_id')]
    observed = len(fresh)
    data = {'schema': 'perf050-readonly-product-pilot-original-costs-v1', 'freeze_sha256': freeze, 'slots': rows,
            'planned_consumers': 2, 'CLI_process_launches_observed': sum(row['model_consumers_launched'] for row in rows),
            'distinct_fresh_threads': len(set(fresh)), 'observed_thread_ids': observed,
            'provider_timing': None, 'provider_billing': None, 'scope': 'One serial pair is diagnostic. Tool waiting includes runtime and model call generation; internal provider cost is unmeasured.'}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(f'{output.name} {digest(output)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'COSTS.json')
    args = parser.parse_args()
    collect(args.runtime, args.output)
