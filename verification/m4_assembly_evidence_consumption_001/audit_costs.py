"""Audit the paired original public receipts, timing and installed entry binding."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import ASSET, ASSET_SHA256, EXTERNAL, LIVE, product_binding, load, read, save, sha


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def ms(ns):
    return ns / 1e6 if type(ns) is int else None


def unique(rows, predicate, reason):
    selected = [r for r in rows if predicate(r)]
    if len(selected) != 1:
        raise ValueError(reason)
    return selected[0]


def byte_count(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def capture_metadata(slot, first_seal):
    run = EXTERNAL / 'slots' / slot
    _, binding = product_binding(slot)
    expected = read(NS / 'inputs' / f'PRODUCT_SCHEMA_{slot[0]}.json')
    producer = read(run / 'MCP_IDENTITY.json') if (run / 'MCP_IDENTITY.json').is_file() else {}
    device = read(run / 'RUNTIME_READY.json') if (run / 'RUNTIME_READY.json').is_file() else {}
    if not producer:
        return {'product_identity': None, 'observed_first': False}
    if producer['source_sha256'] != binding['source_sha256'] or (
        device['product_source_sha256'] != binding['source_sha256'] or device['asset_copy_sha256'] != ASSET_SHA256
    ):
        raise ValueError('product or owned asset binding differs for ' + slot)
    exposed_schema = read(run / 'owner/TOOLS_SCHEMA.json')
    public = unique(exposed_schema, lambda row: row['name'] == expected['name'], 'one public product tool required')
    entry = (NS / 'inputs/ENTRY.txt').read_text(encoding='utf8').strip()
    if public != expected and public != {**expected, 'description': entry + ' ' + expected['description']}:
        raise ValueError('public tool schema differs from the pinned installation and common entry')
    audit = {'observed_first': bool(first_seal['path']), 'installed_schema_bytes': byte_count(expected),
             'model_bridge_tool_schema_bytes': byte_count(public),
             'model_bridge_catalogue_bytes': byte_count(exposed_schema),
             'product_identity': producer['source_sha256']}
    if first_seal['path'] is None:
        return audit
    tool = run / 'owner' / first_seal['owner_tool']
    detail = read(tool / 'PRODUCT_DETAIL.json')
    request = read(tool / 'PRODUCT_REQUEST.json')
    raw = read(Path(first_seal['original_product_response_path']))
    body = Path(first_seal['path'])
    if (sha(body) != first_seal['sha256'] or raw['result']['content'][0]['text'].encode() != body.read_bytes()
            or sha(tool / 'RESPONSE.json') != first_seal['owner_response_sha256']):
        raise ValueError('sealed first-packet bytes differ')
    expected_assembly = read(NS / 'inputs/ASSEMBLY.json')
    expected_arguments = {'query': {'mode': 'task', **expected_assembly}, 'include_image': False, 'response_detail': 'brief'}
    if request['params']['arguments'] != expected_arguments or not detail['forwarded_arguments_unchanged']:
        raise ValueError('first-packet request differs from registered A/B entry')
    receipt = first_seal['original_rpc_receipt']
    transport = next((row for row in jsonl(run / 'mcp_io/MCP_IO.jsonl') if row.get('id') == request['id']), {})
    trace = next((r['trace'] for r in jsonl(run / 'product_audit.jsonl') if r.get('trace', {}).get('annotations', {})
                  .get('mcp_request_id') == request['id']), None)
    packet = read(body)
    selected = packet.get('binding') or {}
    returned = receipt.get('producer_archive')
    if returned and sha(returned['path']) != returned['sha256']:
        raise ValueError('producer archive differs for ' + slot)
    stage_names = {'host.capture', 'observation.task_facts', 'observation.task_capture_evidence',
                   'observation.task_capture_evidence.validate', 'observation.task_capture_evidence.construct',
                   'mcp.content_encode', 'mcp.wire_encode', 'mcp.stdio_write'}
    spans = [] if trace is None else [{k: span[k] for k in ('name', 'source_name', 'start_offset_ns', 'duration_ns')}
                                    for span in trace['spans'] if span['name'] in stage_names]
    audit.update(first_packet_UTF8_bytes=body.stat().st_size, first_packet_sha256=sha(body),
                 found_capture_evidence='capture_evidence' in packet, first_packet_binding=selected,
                 first_arguments=expected_arguments, first_forward_request_sha256=sha(tool / 'PRODUCT_REQUEST.json'),
                 first_product_stdio_ms=ms(receipt.get('receipt', {}).get('elapsed_ns')),
                 first_product_request_to_flush_with_archive_ms=ms(transport.get('request_to_reply_ns')),
                 first_product_trace_duration_ms=ms(None if trace is None else trace['duration_ns']),
                 first_product_spans=spans, first_product_wire_bytes={k: receipt.get('receipt', {}).get(k)
                    for k in ('TX_bytes', 'RX_bytes')})
    return audit


def main():
    started = time.perf_counter_ns()
    frozen = sha(NS / 'FROZEN.json')
    old = load('_preceding_assembly_cost_functions', LIVE / 'checks/runtime_audit.py')
    if old.EXTERNAL != EXTERNAL:
        raise ValueError('prior audit helper must use this batch runtime')
    answers = read(NS / 'ANSWERS_SEALED.json')['answers']
    first = {row['slot']: row for row in read(NS / 'FIRST_PACKETS_SEALED.json')['first_packets']}
    slots = []
    for row in answers:
        label = row['slot']
        report = old.audit_slot(label, frozen, row)
        report['installed_first'] = capture_metadata(label, first[label])
        rows = report.get('attempts', [])
        for previous, current in zip(rows, rows[1:]):
            # Timing scope includes model-side waiting, processing and scheduling.
            current['previous_CLI_result_to_next_owner_request_s'] = old.seconds(
                previous['CLI_received_ns'], current['owner_started_ns'])
        slots.append(report)
    a, b = slots
    if a['published_ns'] > b['started_ns'] or sha(ASSET) != ASSET_SHA256:
        raise ValueError('publication order or original asset changed')
    save(NS / 'checks/RUNTIME_REVIEW.json', {'started_ns': started, 'closed_ns': time.perf_counter_ns(),
         'launch_order': ['A1', 'B1'], 'frozen_sha256': frozen, 'slots': slots,
         'unmeasured': ['provider actual inputs', 'provider request count', 'provider internal timing', 'cash fees'],
         'scope': 'Original public wire, usage and timing evidence, with prior sealed CLI binding audit. Private event bodies are excluded.'})


if __name__ == '__main__':
    main()
