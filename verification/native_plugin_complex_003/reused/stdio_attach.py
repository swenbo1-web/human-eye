"""Thin per-turn MCP client for one existing chain owner; EOF never closes it.

Uses the historical broker's single-request TCP framing and no automatic retry.
The owner transport/startup is deliberately not launched by this client.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
import uuid
import os

MAX_FRAME = 24 * 1024 * 1024


def attach(endpoint, kind, message, *, connect=socket.create_connection,
           clock_ns=time.perf_counter_ns):
    left = (endpoint['chain_deadline_ns']-clock_ns())/1e9
    if left <= 0: raise TimeoutError('original_chain_deadline')
    request = dict(request_id=uuid.uuid4().hex, operation='attached_mcp',
                   args=dict(kind=kind, message=message))
    raw = (json.dumps(request, ensure_ascii=False, allow_nan=False)+'\n').encode('utf8')
    if len(raw) > MAX_FRAME: raise ValueError('MCP_frame_limit')
    with connect((endpoint['host'], endpoint['port']), timeout=min(left, 30)) as stream:
        stream.sendall(raw); stream.shutdown(socket.SHUT_WR); data = bytearray()
        while True:
            left = (endpoint['chain_deadline_ns']-clock_ns())/1e9
            if left <= 0: raise TimeoutError('original_chain_deadline')
            stream.settimeout(min(left, 30)); block = stream.recv(65536)
            if not block: break
            data.extend(block)
            if len(data) > MAX_FRAME: raise ValueError('MCP_frame_limit')
    reply = json.loads(data)
    if reply.get('request_id') != request['request_id']:
        raise ValueError('broker_reply_binding_no_replay')
    if not reply.get('ok'): raise RuntimeError('owner_refused_no_replay')
    return reply['result']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', type=Path, required=True)
    parser.add_argument('--kind', choices=('native', 'he'), required=True)
    parser.add_argument('--audit', type=Path, required=True)
    options = parser.parse_args(); endpoint = json.loads(options.endpoint.read_bytes())
    folder=options.audit/('bridge_'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
    started=dict(pid=os.getpid(),kind=options.kind,started_ns=time.perf_counter_ns(),instance_nonce=uuid.uuid4().hex)
    (folder/'STARTED.json').write_text(json.dumps(started),encoding='utf8')
    sequence=0;normal=False;total_rx=total_tx=0
    try:
        while True:
            raw = sys.stdin.buffer.readline(MAX_FRAME+1)
            if not raw: break
            if len(raw) > MAX_FRAME: raise ValueError('MCP_frame_limit')
            message = json.loads(raw)
            sequence+=1;call=folder/str(sequence).zfill(3);call.mkdir();(call/'TX.bin').write_bytes(raw)
            total_tx+=len(raw)
            if 'id' not in message: continue
            reply = attach(endpoint, options.kind, message)
            if reply is not None:
                output=(json.dumps(reply, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n').encode('utf8')
                sys.stdout.buffer.write(output);sys.stdout.buffer.flush()
                (call/'RX.bin').write_bytes(output);total_rx+=len(output)
        normal=True
    finally:
        (folder/'EXIT.json').write_text(json.dumps(dict(started,normal_exit=normal,ended_ns=time.perf_counter_ns(),
            requests=sequence,complete_tx_bytes=total_tx,complete_rx_bytes=total_rx,
            backend_close_requested=False)),encoding='utf8')
    # No close/terminate/restart command, and no destructor owns the product.


if __name__ == '__main__': main()
