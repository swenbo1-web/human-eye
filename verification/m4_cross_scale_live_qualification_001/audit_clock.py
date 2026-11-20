"""Account observed generation, repeated delivery and owned-slot timing separately."""

import base64
import hashlib
import json
from pathlib import Path
import time


NS = Path(__file__).resolve().parent
SLOT = Path('D:/he_m4_cross_scale_live_qualification_001/slots/Q1')


def load(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def elapsed_ms(start, end):
    return (end - start) / 1e6 if type(start) is int and type(end) is int and end >= start else None


def selected_elapsed(stages):
    return {name: span['elapsed_ns'] / 1e6 for name, span in sorted(stages.items()) if isinstance(span, dict)
            and type(span.get('elapsed_ns')) is int}


def packet_summary(row, wire, events, trace):
    original_path = Path(row['request_path'])
    rx = original_path.with_name('RESPONSE.json')
    result = load(rx).get('result', {}) if rx.is_file() else {}
    contents = result.get('content', [])
    text = [block['text'] for block in contents if block['type'] == 'text']
    images = [base64.b64decode(block['data'], validate=True) for block in contents if block['type'] == 'image']
    receipt = row.get('receipt') or {}
    producer = row.get('producer_archive')
    summary = {'RPC_id': row['request']['id'], 'status': 'error' if result.get('isError') or row.get('error') else 'returned',
               'error': row.get('error'), 'text_bytes': sum(len(t.encode('utf8')) for t in text),
               'text_sha256': [sha(t.encode('utf8')) for t in text], 'images': len(images),
               'image_bytes': [len(raw) for raw in images], 'image_sha256': [sha(raw) for raw in images],
               'wire_bytes': {k: receipt.get(k) for k in ('TX_bytes', 'RX_bytes')},
               'client_RPC_ms': elapsed_ms(receipt.get('started_ns'), receipt.get('closed_ns')),
               'owner_runtime_window_ms': elapsed_ms(row.get('started_ns'), row.get('closed_ns')),
               'request_to_flush_with_producer_archive_ms': elapsed_ms(wire.get('request_received_ns'),
                                                                       wire.get('reply_completed_ns')),
               'raster_events': len(events), 'raster_io_meter': wire.get('raster_actual')}
    if wire.get('raster_actual') is not None and wire['raster_actual'] != len(events):
        raise ValueError('raster event and stdio meter differ')
    if trace is not None:
        summary['request_trace_ms'] = trace['duration_ns'] / 1e6
        summary['transport_spans_ms'] = {span['name']: span['duration_ns'] / 1e6 for span in trace.get('spans', [])
                                        if span['name'].startswith('mcp.')}
    if producer is None:
        return summary
    raw = Path(producer['path']).read_bytes()
    if sha(raw) != producer['sha256']:
        raise ValueError('producer evidence changed')
    body = json.loads(raw)
    work = body.get('work', {})
    source_status = body.get('status')
    if len(events) != work.get('raster_attempts'):
        raise ValueError('producer current request raster count differs from audit')
    summary.update(producer_result_sha256=producer['sha256'], producer_status=source_status,
                   producer_ms=elapsed_ms(producer.get('started_ns'), producer.get('producer_returned_ns')),
                   producer_archive_ms=elapsed_ms(producer.get('producer_returned_ns'), producer.get('saved_ns')),
                   current_request_work=work, current_request_stages_ms=selected_elapsed(body.get('stages', {})))
    # Cached generation frames carry original phase times. Count them only as
    # current construction work when the current request admitted those rasters.
    summary['current_new_frame_stages_ms'] = []
    if events:
        for frame in body.get('constructed_frames', []):
            summary['current_new_frame_stages_ms'].append({'view': frame['view_name'], 'scope': frame['scope_id'],
                'frame_identity': frame['frame_identity'], 'render_and_encode': selected_elapsed(frame['stages']),
                'feedback': selected_elapsed(frame['feedback_stages'])})
        if len(summary['current_new_frame_stages_ms']) != len(events):
            raise ValueError('construction events and current new frame count differ')
    return summary


def main():
    started = time.perf_counter_ns()
    result_file = SLOT / 'SLOT_RESULT.json'
    publication = load(SLOT / 'SLOT_PUBLICATION.json')
    slot = load(result_file)
    public = jsonl(SLOT / 'PUBLIC_REQUESTS.jsonl')
    audits = jsonl(SLOT / 'product_audit.jsonl')
    calls = [x for x in audits if x['event'] == 'active_observation_render_attempt']
    meter = {x['id']: x for x in jsonl(SLOT / 'mcp_io/MCP_IO.jsonl') if x.get('method') == 'tools/call'}
    traces = {x['trace']['annotations'].get('mcp_request_id'): x['trace'] for x in audits
              if x['event'] == 'request_trace'}
    summaries = []
    for row in public:
        ident = row['request']['id']
        trace = traces.get(ident)
        events = [x for x in calls if trace is not None and x['request_id'] == trace['request_id']]
        summaries.append(packet_summary(row, meter.get(ident, {}), events, trace))
    if len(public) > 2 or len(calls) > 6 or sum(x['raster_events'] for x in summaries) != len(calls):
        raise ValueError('observed product work exceeded or did not reconcile to the qualification budget')
    result = {'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'slot_status': slot['status'],
              'slot_result_sha256': sha(result_file.read_bytes()), 'slot_publication': publication,
              'slot_durations': slot.get('clocks', {}), 'product_requests': summaries,
              'actual_business_calls_to_product': len(public), 'actual_raster_attempts': len(calls),
              'model_consumers': 0, 'provider_usage': None,
              'scope': 'Actual product RPC, trace, rendering and encoding. Nested times are inclusive. '
                       'Second delivery of existing frames is not counted as construction.'}
    with (NS / 'checks/COSTS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print('Product calls', len(public), 'actual raster attempts', len(calls))


if __name__ == '__main__':
    main()
