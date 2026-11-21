"""Read the batch's immutable attempt-numbered TCP envelope without changing its freeze."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import digest, read, require
import live


def actual_outer(slot, turn, side, expected, inner, image):
    path = slot / 'batch' / f'rpc_{turn + 2:02d}'
    original = read(path / 'RECEIPT.json')
    tx, rx = [(path / name).read_bytes() for name in ('TCP_TX.bin', 'TCP_RX.bin')]
    request = {'jsonrpc': '2.0', 'id': 'source-region-' + side, 'method': 'tools/call',
               'params': {'name': 'human_eye_scene_observe', 'arguments': expected}}
    wrapper = {'operation': 'attached_mcp', 'request_id': request['id'],
               'args': {'kind': 'native', 'message': request, 'attempt': turn}}
    received = json.loads(rx)
    parsed = received['result']
    require(json.loads(tx) == wrapper and received['ok'] is True and received['request_id'] == request['id']
            and parsed == original['response'] and parsed['id'] == request['id']
            and parsed['result'] == inner and len(tx) == original['TX_bytes'] and len(rx) == original['RX_bytes']
            and digest(tx) == original['TX_sha256'] and digest(rx) == original['RX_sha256'] and
            image == (path / 'image_1.png').read_bytes(), 'outer_relay_did_not_deliver_exact_public_PNG_or_text')
    return {name: original[name] for name in ('started_ns', 'closed_ns', 'TX_bytes', 'RX_bytes', 'TX_sha256',
                                                'RX_sha256', 'client_socket_ns')}


if __name__ == '__main__':
    live.actual_outer = actual_outer
    raise SystemExit(live.main())
