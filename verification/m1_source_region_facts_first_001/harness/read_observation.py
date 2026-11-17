"""Return one frozen original public tool result through standard MCP stdio."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

MAX_FRAME = 24 * 1024 * 1024
DESCRIPTION = '读取本会话绑定的一份封存观测，返回原产品JSON和PNG。采集时刻以返回的来源绑定为准。'
TOOL = {'name': 'read_observation', 'description': DESCRIPTION,
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf8')


def save(path, value, replace=False):
    path = Path(path)
    temporary = path.with_name(path.name + '.next') if replace else path
    with temporary.open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--input-sha256', required=True)
    parser.add_argument('--owner', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--deadline-ns', type=int, required=True)
    options = parser.parse_args()
    raw_input = options.input.read_bytes()
    if hashlib.sha256(raw_input).hexdigest() != options.input_sha256:
        raise ValueError('frozen_observation_input_changed')
    payload = json.loads(raw_input)
    if type(payload) is not dict or type(payload.get('content')) is not list:
        raise ValueError('original_public_content_required')
    folder = options.audit / ('bridge_' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    options.owner.mkdir(parents=True, exist_ok=True)
    started = {'pid': os.getpid(), 'kind': 'native', 'started_ns': time.perf_counter_ns(),
               'instance_nonce': uuid.uuid4().hex}
    save(folder / 'STARTED.json', started)
    ledger_path = options.owner / 'TOOLS.json'
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_bytes())
    else:
        ledger = {'attempts': 0, 'admitted': 0, 'tools': []}
    normal, sequence, total_tx, total_rx = False, 0, 0, 0
    calls, errors = [], []
    def publish_bridge():
        path = options.owner / 'BRIDGE_RESULT.json'
        save(path, {'calls': calls, 'protocol_errors': errors,
            'input_sha256': options.input_sha256, 'business_limit': 4,
            'attempts': ledger['attempts'], 'admitted': ledger['admitted'],
            'new_Blender': 0, 'new_product_calls': 0, 'raster': 0, 'image_encoding': 0}, replace=path.exists())
    publish_bridge()
    try:
        while True:
            raw = sys.stdin.buffer.readline(MAX_FRAME + 1)
            if not raw:
                break
            received = time.perf_counter_ns()
            if len(raw) > MAX_FRAME:
                raise ValueError('MCP_frame_limit')
            if received >= options.deadline_ns:
                raise TimeoutError('original_consumer_task_deadline')
            message = json.loads(raw)
            sequence += 1
            wire = folder / str(sequence).zfill(3)
            wire.mkdir()
            (wire / 'TX.bin').write_bytes(raw)
            total_tx += len(raw)
            if 'id' not in message:
                continue
            result = None
            method = message.get('method')
            if method == 'initialize':
                result = {'protocolVersion': message.get('params', {}).get('protocolVersion', '2025-03-26'),
                          'capabilities': {'tools': {}}, 'serverInfo': {'name': 'sealed-observation-reader', 'version': '1.0'}}
            elif method == 'tools/list':
                result = {'tools': [TOOL]}
            elif method == 'ping':
                result = {}
            elif method == 'resources/list':
                result = {'resources': []}
            elif method == 'resources/templates/list':
                result = {'resourceTemplates': []}
            elif method == 'tools/call':
                ledger['attempts'] += 1
                attempt = ledger['attempts']
                business = options.owner / ('tool_' + str(attempt).zfill(2))
                business.mkdir(exist_ok=False)
                save(business / 'REQUEST.json', message)
                row = {'attempt': attempt, 'received_ns': received, 'input_sha256': options.input_sha256,
                       'RPC_id': message.get('id'), 'RPC_method': method,
                       'transport_meta': message.get('params', {}).get('_meta') if type(message.get('params')) is dict else None}
                ledger['tools'].append(row)
                save(ledger_path, ledger, replace=ledger_path.exists())
                if attempt > 4:
                    row['status'] = 'business_tool_budget_exhausted'
                    result = {'isError': True, 'content': [{'type': 'text', 'text': 'business_tool_budget_exhausted'}]}
                elif (type(message.get('params')) is not dict
                        or set(message['params']) - {'name', 'arguments', '_meta'}
                        or message['params'].get('name') != 'read_observation'
                        or message['params'].get('arguments') != {}
                        or ('_meta' in message['params'] and type(message['params']['_meta']) is not dict)):
                    row['status'] = 'empty_parameter_read_observation_required'
                    result = {'isError': True, 'content': [{'type': 'text', 'text': 'empty_parameter_read_observation_required'}]}
                else:
                    ledger['admitted'] += 1
                    row['status'] = 'returned_original_public_content'
                    result = payload
                reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
                save(business / 'RESPONSE.json', reply)
                row['closed_ns'] = time.perf_counter_ns()
                save(ledger_path, ledger, replace=True)
                calls.append(row.copy())
                publish_bridge()
            else:
                errors.append({'method': method, 'reason': 'unsupported_MCP_method'})
            if result is None:
                reply = {'jsonrpc': '2.0', 'id': message['id'],
                         'error': {'code': -32601, 'message': 'Method not found'}}
            else:
                reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
            output = encoded(reply)
            (wire / 'RX.bin').write_bytes(output)
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()
            total_rx += len(output)
        normal = True
    finally:
        publish_bridge()
        save(folder / 'EXIT.json', {**started, 'normal_exit': normal, 'ended_ns': time.perf_counter_ns(),
            'requests': sequence, 'complete_tx_bytes': total_tx, 'complete_rx_bytes': total_rx,
            'backend_close_requested': False})


if __name__ == '__main__':
    main()
