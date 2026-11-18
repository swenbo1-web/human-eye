"""Attach the fresh CLI to a retained owner and preserve every stdio attempt."""

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid


def import_bridge():
    # The isolated interpreter excludes the script directory from sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bridge
    return bridge


def exchange(endpoint, request, attempt, bridge):
    key = uuid.uuid4().hex
    envelope = {'request_id': key, 'operation': 'attached_mcp',
                'args': {'kind': 'native', 'message': request, 'attempt': attempt}}
    raw = bridge.encoded(envelope) + b'\n'
    if len(raw) > bridge.MAX_FRAME:
        raise ValueError('owner_request_frame_limit')
    deadline_ns = endpoint['chain_deadline_ns']
    with socket.create_connection((endpoint['host'], endpoint['port']),
                                  timeout=min(5, bridge.remaining(deadline_ns))) as stream:
        stream.sendall(raw)
        stream.shutdown(socket.SHUT_WR)
        received = bytearray()
        while True:
            stream.settimeout(bridge.remaining(deadline_ns))
            chunk = stream.recv(65536)
            if not chunk:
                break
            received.extend(chunk)
            if len(received) > bridge.MAX_FRAME:
                raise ValueError('owner_response_frame_limit')
    reply = json.loads(received)
    if reply.get('request_id') != key or reply.get('ok') is not True:
        raise ValueError('owner_reply_identity')
    response = reply['result']
    if 'id' in request and (type(response) is not dict or response.get('jsonrpc') != '2.0'
            or type(response.get('id')) is not type(request['id']) or response['id'] != request['id']):
        raise ValueError('owner_RPC_response_identity')
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    options = parser.parse_args()
    bridge = import_bridge()
    endpoint = json.loads(options.endpoint.read_bytes())
    if endpoint['host'] != '127.0.0.1' or type(endpoint['chain_deadline_ns']) is not int:
        raise ValueError('owned_loopback_endpoint_required')
    folder = options.audit / f'bridge_{uuid.uuid4().hex}'
    folder.mkdir(parents=True)
    started = {'pid': os.getpid(), 'kind': 'native', 'started_ns': time.perf_counter_ns(),
               'instance_nonce': uuid.uuid4().hex}
    bridge.save(folder / 'STARTED.json', started)
    attempts = total_rx = total_tx = sequence = 0
    normal = False
    try:
        while raw := sys.stdin.buffer.readline(bridge.MAX_FRAME + 1):
            sequence += 1
            total_tx += len(raw)
            wire = folder / f'{sequence:03d}'
            wire.mkdir()
            (wire / 'TX.bin').write_bytes(raw)
            received = time.perf_counter_ns()
            if len(raw) > bridge.MAX_FRAME:
                raise ValueError('MCP_stdio_frame_limit')
            request = json.loads(raw)
            method = request.get('method')
            attempt = None
            if method == 'tools/call':
                attempts += 1
                attempt = attempts
            row = {'sequence': sequence, 'method': method, 'RPC_id': request.get('id'), 'attempt': attempt,
                   'received_ns': received, 'request_bytes': len(raw), 'response_bytes': None,
                   'origin': None, 'flush_completed_ns': None, 'owner_TCP_attempted': False}
            bridge.save(wire / 'RECEIPT.json', row)
            try:
                response = None
                # MCP notifications need no reply. All are retained verbatim in TX.bin.
                if 'id' in request or attempt is not None:
                    try:
                        if attempt is not None and attempt > bridge.TOOL_LIMIT:
                            row['origin'] = 'budget_refusal'
                            raise ValueError('business_tool_attempt_budget_exhausted')
                        row['owner_TCP_attempted'] = True
                        response = exchange(endpoint, request, attempt, bridge)
                        row['origin'] = 'owner'
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        if attempt is None or 'id' not in request:
                            raise
                        row['origin'] = row['origin'] or 'transport_failure'
                        row['error'] = {'type': type(error).__name__, 'message': str(error)}
                        response = {'jsonrpc': '2.0', 'id': request['id'], 'result': bridge.error_result(error)}
                if 'id' in request and response is not None:
                    output = bridge.encoded(response) + b'\n'
                    (wire / 'RX.bin').write_bytes(output)
                    row['response_bytes'] = len(output)
                    sys.stdout.buffer.write(output)
                    sys.stdout.buffer.flush()
                    row['flush_completed_ns'] = time.perf_counter_ns()
                    total_rx += len(output)
            finally:
                row['closed_ns'] = time.perf_counter_ns()
                bridge.save(wire / 'RECEIPT.json', row)
        normal = True
    finally:
        bridge.save(folder / 'EXIT.json', {**started, 'normal_exit': normal, 'ended_ns': time.perf_counter_ns(),
            'requests': sequence, 'attempts': attempts, 'complete_tx_bytes': total_tx,
            'complete_rx_bytes': total_rx, 'backend_close_requested': False})


if __name__ == '__main__':
    main()
