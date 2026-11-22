"""Run fixed archived acquisitions through real installed production stdio.

Each positive has an independent held process. Only root executes candidate
formal arms. No Blender, renderer, model, source rebuilding or old-file writes.
"""

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fixtures import POSITIVE_NAMES, compact, compatibility, dataset, pin, read, require

EXTERNAL = Path('D:/he_m1_source_region_no_image_measurement_packet_001')
TRANSPORT = HERE.parent.parent / 'm4_source_region_display_001/harness/reused/stdio_checks.py'


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(compact(value) + b'\n')


def rpc(identifier, method, **params):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}


def references(arguments, ref):
    result = deepcopy(arguments)
    result['query'].pop('region', None)
    result['query']['region_ref'] = deepcopy(ref)
    return result


def steps(data):
    calls = [(('full' if index == 0 else 'brief'), deepcopy(record['request']), False)
             for index, record in enumerate(data['records'])]
    if data['name'] not in POSITIVE_NAMES:
        return calls
    base = data['records'][0]['request']
    ref = data['records'][0]['producer']['region_ref']
    good = references(base, ref)
    bad = deepcopy(good)
    bad['query']['region_ref']['region_id'] = 'source-region:' + '0' * 64
    stale = deepcopy(good)
    unsigned = stale['query']['region_ref']
    epoch = unsigned['document_epoch']
    require(type(epoch) is str and len(epoch) == 64, 'actual_canonical_epoch_required')
    unsigned['document_epoch'] = ('1' if epoch[0] == '0' else '0') + epoch[1:]
    unsigned['region_id'] = 'source-region:' + hashlib.sha256(json.dumps(
        {key: value for key, value in unsigned.items() if key != 'region_id'},
        default=str, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()
    extra = deepcopy(base)
    extra['query']['requested_facts'].append('aabb')
    return calls + [('valid_ref', good, False), ('invalid_ref', bad, True),
                    ('stale_ref', stale, True), ('extra_facts', extra, True),
                    ('recovery', deepcopy(base), False)]


def case(root, binding_path, mode, name):
    started = time.perf_counter_ns()
    root.mkdir(parents=True, exist_ok=False)
    data = dataset(name)
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'replay.py'),
               '--worker', str(root / 'worker'), '--binding', str(binding_path), '--case', name]
    if mode == 'evidence':
        command.append('--region-task-evidence')
    transport = run_path(str(TRANSPORT))
    client = None
    calls, error = [], None
    try:
        client = transport['StdioClient'](command, root, root / 'wire', started + 120_000_000_000)
        initialized = client.call(rpc('initialize', 'initialize', protocolVersion='2025-03-26',
            capabilities={}, clientInfo={'name': 'measurement-packet-replay', 'version': '1'}))
        require(initialized['result']['_meta']['human_eye']['source_kind'] == 'installed_distribution',
                'actual_installed_initialization_required')
        save(root / 'INITIALIZE.json', initialized)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        catalogue = client.call(rpc('catalogue', 'tools/list'))
        save(root / 'CATALOGUE.json', catalogue)
        for label, arguments, expected_error in steps(data):
            folder = root / label
            folder.mkdir()
            request = rpc(label, 'tools/call', name='human_eye_scene_observe', arguments=arguments)
            save(folder / 'REQUEST.json', request)
            response = client.call(request)
            save(folder / 'RESPONSE.json', response)
            wire = client.output / ('rpc_' + str(client.records[-1]['index']).zfill(2))
            result = response.get('result', {})
            is_error = response.get('error') is not None or result.get('isError') is True
            text_blocks = [block['text'] for block in result.get('content', []) if block.get('type') == 'text']
            public = None
            if text_blocks:
                raw = text_blocks[0].encode('utf8')
                (folder / 'PUBLIC.txt').write_bytes(raw)
                try:
                    public = json.loads(raw)
                    save(folder / 'PUBLIC.json', public)
                except json.JSONDecodeError:
                    pass
            images = []
            for block in result.get('content', []):
                if block.get('type') == 'image':
                    raw = base64.b64decode(block['data'], validate=True)
                    images.append({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            row = {'label': label, 'arguments': arguments, 'expected_error': expected_error,
                'actual_error': is_error, 'matches_expected_error': is_error == expected_error,
                'request_path': str(folder / 'REQUEST.json'), 'response_path': str(folder / 'RESPONSE.json'),
                'public_path': str(folder / 'PUBLIC.txt') if text_blocks else None,
                'public_UTF8_bytes': len(text_blocks[0].encode('utf8')) if text_blocks else 0,
                'TX_path': str(wire / 'TX.bin'), 'RX_path': str(wire / 'RX.bin'),
                'receipt_path': str(wire / 'RECEIPT.json'), 'images': images,
                'public_schema': public.get('schema') if isinstance(public, dict) else None}
            calls.append(row)
            save(folder / 'RECEIPT.json', row)
            require(row['matches_expected_error'], 'unexpected_public_error/' + label)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        closed = client.finish() if client is not None else None
        events = []
        if client is not None:
            while True:
                try:
                    kind, value, at = client.events.get_nowait()
                except queue.Empty:
                    break
                events.append({'kind': kind, 'observed_ns': at, 'error': value if kind == 'error' else None})
        eof_path = root / 'worker/EOF.json'
        eof = read(eof_path) if eof_path.exists() else None
        held = {'events': events, 'stdout_eof_observed': any(e['kind'] == 'eof' for e in events),
                'input_eof_observed': eof.get('input_eof_observed') if eof else None,
                'held_close': closed, 'worker_eof': eof, 'platform': os.name}
        save(root / 'HELD_EOF.json', held)
        completed = (error is None and closed and closed['confirmed'] and eof and eof['closed']
                     and eof['archived_inputs_unchanged'] and eof['input_eof_observed']
                     and eof['socket_attempts'] == eof['host_attempts'] == eof['actual_new_rasters'] == 0
                     and held['stdout_eof_observed'])
        result = {'case': name, 'completed': bool(completed), 'binding': pin(binding_path), 'mode': mode,
            'started_ns': started, 'closed_ns': time.perf_counter_ns(), 'error': error, 'calls': calls,
            'INPUTS_path': str(root / 'worker/INPUTS.json'), 'producer_glob': str(root / 'worker/PRODUCER_*.json'),
            'service_glob': str(root / 'worker/SERVICE_*.json'), 'worker_EOF_path': str(eof_path),
            'held_EOF_path': str(root / 'HELD_EOF.json'), 'held_close_path': str(root / 'wire/CLOSE.json'),
            'actual_models': 0, 'actual_new_rasters': 0}
        save(root / 'CASE.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--mode', choices=('standard', 'evidence'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('all', 'positive', 'compat'), default='all')
    parser.add_argument('--case', choices=POSITIVE_NAMES)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(EXTERNAL) and output != EXTERNAL, 'isolated_new_arm_root_required')
    output.mkdir(parents=True, exist_ok=False)
    binding = args.binding.resolve(strict=True)
    selected = list(POSITIVE_NAMES) if args.suite != 'compat' else []
    if args.case:
        selected = [args.case]
    elif args.suite != 'positive':
        selected.extend(compatibility())
    source = [pin(path) for path in (HERE / 'run.py', HERE / 'replay.py', HERE / 'fixtures.py', TRANSPORT)]
    snapshots = output / 'source_snapshot'
    snapshots.mkdir()
    for row in source:
        (snapshots / Path(row['path']).name).write_bytes(Path(row['path']).read_bytes())
    save(output / 'SOURCE.json', {'files': source, 'binding': pin(binding), 'suite': args.suite, 'cases': selected})
    rows = []
    for name in selected:
        value = case(output / 'cases' / name, binding, args.mode, name)
        rows.append(value)
        print(json.dumps({'case': name, 'completed': value['completed'], 'path': str(output / 'cases' / name / 'CASE.json')}), flush=True)
        if not value['completed']:
            break
    result = {'schema': 'source-region-measurement-packet-stdio-replay-v1',
        'completed': len(rows) == len(selected) and all(row['completed'] for row in rows),
        'planned': selected, 'actual': rows, 'source': source, 'binding': pin(binding),
        'mode': args.mode, 'actual_models': 0, 'actual_new_rasters': 0,
        'unrun': selected[len(rows):]}
    save(output / 'INDEX.json', result)
    return 0 if result['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
