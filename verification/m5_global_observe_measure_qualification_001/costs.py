"""Account for actual public requests, Blender reads, and the one outer batch per arm."""

import ast
import base64
import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, verify_freeze
from common import EXTERNAL, ORDER, read, save, sha


def lines(path):
    return [json.loads(raw) for raw in path.read_bytes().splitlines() if raw.strip()] if path.is_file() else []


def ms(start, end):
    return (end - start) / 1e6 if type(start) is int and type(end) is int and end >= start else None


def pinned_path(path, digest, slot):
    path = Path(path).resolve()
    if not path.is_relative_to(slot.resolve()) or sha(path) != digest:
        raise ValueError('packet_path_or_content_not_bound_to_current_slot')
    return path


def payload_bytes(value):
    data = value.get('content', [])
    return {'text_UTF8_bytes': sum(len(block['text'].encode()) for block in data if block['type'] == 'text'),
            'PNG_bytes': [len(base64.b64decode(block['data'], validate=True))
                          for block in data if block['type'] == 'image']}


def native_reads(slot):
    index = slot / 'native/WIRE/INDEX.json'
    if not index.is_file():
        return []
    captured = []
    for row in read(index):
        folder = index.parent / f"{row['sequence']:03d}"
        tx, rx = folder / 'REQUEST.bin', folder / 'RESPONSE.bin'
        if (tx.stat().st_size != row['request_bytes'] or rx.stat().st_size != row['response_attempted_bytes']
                or row['response_sendall_completed'] is not True):
            raise ValueError('Blender_wire_not_confirmed')
        request, response = read(tx), read(rx)
        result = (response.get('result') or {}).get('result', '')
        marker = 'HUMAN_EYE_BLENDER_MCP:'
        if not isinstance(result, str) or marker not in result:
            continue
        matching = [line[len(marker):] for line in result.splitlines() if line.startswith(marker)]
        payload, = matching
        output = json.loads(payload)
        assignment, = [node for node in ast.parse(request['params']['code']).body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == '_request' for target in node.targets)]
        query = json.loads(ast.literal_eval(assignment.value.args[0]))
        if query['id'] != output['id']:
            raise ValueError('Blender_request_and_response_id_differ')
        value = output.get('result') or {}
        resources = value.get('resources', [])
        if not isinstance(resources, list):
            raise ValueError('unexpected_Blender_resource_packet')
        capture = value.get('capture') or {}
        captured.append({'sequence': row['sequence'], 'command': query['command'], 'args': query['params'],
            'received_resources': len(resources),
            'forwarded_vertices': sum(len(mesh['vertices_local']) for mesh in resources),
            'forwarded_triangles': sum(len(mesh['faces']) for mesh in resources),
            'retained_resource_count': len(value.get('live_resources', [])),
            'capture_scope': capture.get('capture_scope'), 'scene_revision': capture.get('revision'),
            'capture_state': capture.get('capture_state'), 'TX_bytes': tx.stat().st_size, 'RX_bytes': rx.stat().st_size,
            'TX_sha256': sha(tx), 'RX_sha256': sha(rx), 'response_schema': value.get('schema')})
    return captured


def timing(stages):
    measured = {}
    for key, row in stages.items():
        if isinstance(row, dict) and type(row.get('elapsed_ns')) is int:
            if type(row.get('started_ns')) is int and type(row.get('closed_ns')) is int:
                if row['closed_ns'] - row['started_ns'] != row['elapsed_ns']:
                    raise ValueError('recorded_interval_does_not_match_its_bounds/' + key)
            measured[key] = row['elapsed_ns'] / 1e6
    return measured


def public_packets(slot):
    audit = lines(slot / 'product_audit.jsonl')
    traces = {event['trace']['annotations'].get('mcp_request_id'): event['trace'] for event in audit
              if event.get('event') == 'request_trace'}
    meters = {event['id']: event for event in lines(slot / 'mcp_io/MCP_IO.jsonl') if event.get('method') == 'tools/call'}
    packets = []
    for event in lines(slot / 'PUBLIC_REQUESTS.jsonl'):
        ident = event.get('id', event['request']['id'])
        request, response = event['request'], event['response']
        path = pinned_path(event['actual_TX_path'], event['actual_TX_sha256'], slot)
        reverse = pinned_path(event['actual_RX_path'], event['actual_RX_sha256'], slot)
        meter = meters[ident]
        if (read(path) != request or read(reverse) != response or response.get('id') != ident
                or path.stat().st_size != meter['TX_bytes'] or meter['TX_sha256'] != sha(path)):
            raise ValueError('actual_public_stdio_disagrees_with_raw_files')
        trace = traces.get(ident) or {}
        spans = [{'name': span['name'], 'ms': span['duration_ns'] / 1e6}
                 for span in trace.get('spans', []) if type(span.get('duration_ns')) is int]
        producer = event.get('producer_archive')
        original = read(pinned_path(producer['path'], producer['sha256'], slot)) if producer else {}
        stages = timing(original.get('stages', {}))
        images = [{'view': frame['view_name'], 'scope': frame['scope_id'],
                   'timing_ms': timing(frame.get('stages', {}))}
                  for frame in original.get('constructed_frames', [])]
        work = original.get('work') or {}
        selected = request['params']['arguments']['query']
        packets.append({'id': ident, 'request': selected, 'is_error': response.get('result', {}).get('isError'),
            'service_archive_index': event.get('producer_archive_index'), 'post_reply_binding_error': event.get('post_reply_binding_error'),
            'client_RPC_ms': ms(event['started_ns'], event['closed_ns']),
            'server_RPC_ms': ms(meter['request_received_ns'], meter['reply_completed_ns']),
            'public_wire_TX_bytes': path.stat().st_size, 'public_wire_RX_bytes': reverse.stat().st_size,
            'timing_ms': stages, 'trace': spans, 'frames': images, 'work': work,
            'raster_actual': meter.get('raster_actual'), **payload_bytes(response.get('result', {}))})
    task_work = [event['task_work'] for event in audit if event.get('event') == 'observe'
                 and event.get('observation_mode') is None and 'surface_pair_count' in event.get('task_work', {})]
    return packets, task_work


def outer_batch(slot):
    records = []
    for folder in sorted((slot / 'batch').glob('rpc_*')):
        if not (folder / 'RECEIPT.json').is_file():
            continue
        receipt = read(folder / 'RECEIPT.json')
        tx = pinned_path(folder / 'TCP_TX.bin', receipt['TX_sha256'], slot)
        rx = pinned_path(folder / 'TCP_RX.bin', receipt['RX_sha256'], slot)
        message = read(tx)['args']['message']
        if message.get('method') != 'tools/call':
            continue
        call = read(rx)
        response = receipt['response']
        if (call['result'] != response or response.get('id') != message['id'] or tx.stat().st_size != receipt['TX_bytes']
                or rx.stat().st_size != receipt['RX_bytes'] or message['params']['name'] != 'execute_python'):
            raise ValueError('outer_batch_not_bound_to_actual_wire')
        records.append({'id': message['id'], 'tool': message['params']['name'],
                        'whole_client_ms': ms(receipt['started_ns'], receipt['closed_ns']),
                        'socket_window_ms': receipt['client_socket_ns'] / 1e6,
                        'TX_bytes': receipt['TX_bytes'], 'RX_bytes': receipt['RX_bytes'],
                        **payload_bytes(response.get('result', {}))})
    return records


def summarize(label, token):
    folder = EXTERNAL / 'slots' / label
    publication_path = folder / 'SLOT_PUBLICATION.json'
    if not publication_path.is_file():
        return {'label': label, 'status': 'unconfirmed' if folder.exists() else 'unrun'}
    result, pub = publication(label, token)
    row = {'label': label, 'status': pub['status'], 'result_sha256': pub['result_sha256'],
           'owned_window_ms': ms(result['started_ns'], pub['published_ns']),
           'startup_to_ready_ms': ms(result['started_ns'], result.get('ready_ns')),
           'close_to_publication_ms': ms(result.get('cleanup_started_ns'), pub['published_ns']),
           'actual_ledger': (result.get('budget') or {}).get('counts'), 'cost_issues': []}
    for name, action in (('public_and_task_audit', public_packets), ('outer_batches', outer_batch),
                         ('Blender_commands', native_reads)):
        try:
            row[name] = action(folder)
        except (OSError, ValueError, KeyError, TypeError) as error:
            row['cost_issues'].append({'stage': name, 'type': type(error).__name__, 'message': str(error)})
    if 'public_and_task_audit' in row:
        packets, task_work = row.pop('public_and_task_audit')
        row['public_packets'] = packets
        works = task_work if label == 'A' else [p['work']['task_query'] for p in packets if 'task_query' in p['work']]
        row['measurement_work'] = works
        row['independently_recorded_kernel_solves'] = sum(w['surface_pair_count'] for w in works)
        row['public_wire_TX_bytes'] = sum(p['public_wire_TX_bytes'] for p in packets)
        row['public_wire_RX_bytes'] = sum(p['public_wire_RX_bytes'] for p in packets)
        row['public_text_UTF8_bytes'] = sum(p['text_UTF8_bytes'] for p in packets)
        row['pure_raster_ms'] = sum(f['timing_ms'].get('actual_raster', 0) for p in packets for f in p['frames'])
    return row


def collect():
    frozen_path = NS / 'FROZEN.json'
    token = verify_freeze(frozen_path)
    rows = [summarize(label, token) for label in ORDER]
    freeze = read(frozen_path)
    save(NS / 'RESOURCE_REVIEW.json', {'schema': 'm5-global-observe-measure-qualified-resources-v1',
         'freeze_sha256': token, 'rows': rows, 'single_pair_timing_is_diagnostic': True,
         'freeze_registration_ms': ms(freeze['started_ns'], freeze['completed_ns']),
         'pure_kernel_elapsed_ms_measured_separately': False,
         'provider_usage_or_cost_measured': False})


if __name__ == '__main__':
    collect()
