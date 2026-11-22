"""Three independent actual stdio replays, each original cold and hot query."""

import argparse
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
from fixtures import EXTERNAL, LABELS, V, fixture, pin, read, require, save

TRANSPORT = V / 'm4_source_region_display_001/harness/reused/stdio_checks.py'


def case(root, binding_path, label, evidence):
    root.mkdir(parents=True, exist_ok=False)
    original = fixture(label)
    started = time.perf_counter_ns()
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'worker.py'),
               '--worker', str(root / 'worker'), '--binding', str(binding_path), '--case', label]
    if evidence:
        command.append('--region-task-evidence')
    client = None
    observations, failure = {}, None
    try:
        client = run_path(str(TRANSPORT))['StdioClient'](command, root, root / 'wire',
                                                       started + 120_000_000_000)
        initial = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'whole-object-witness-triangle-replay', 'version': '1'}}})
        identity = initial['result']['_meta']['human_eye']
        require(identity['source_sha256'] == read(binding_path)['source_sha256']
                and identity['source_kind'] == 'installed_distribution', 'actual_installed_identity_required')
        save(root / 'INITIALIZE.json', initial)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listed = client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list', 'params': {}})
        save(root / 'CATALOGUE.json', listed)
        for ordinal, phase in enumerate(('cold', 'hot'), 1):
            folder = root / phase
            folder.mkdir()
            request = deepcopy(original['request'])
            # Replay preserves the original id and original argument values.
            save(folder / 'REQUEST.json', request)
            response = client.call(request)
            save(folder / 'RESPONSE.json', response)
            public = response['result']
            require(public.get('isError') is False and len(public['content']) == 1
                    and public['content'][0]['type'] == 'text', 'successful_original_no_image_task_required/' + phase)
            text = public['content'][0]['text']
            value = json.loads(text)
            require(value['status'] == 'observed' and value['result_kind'] == 'task_query',
                    'actual_whole_task_solver_result_required/' + phase)
            (folder / 'PUBLIC.txt').write_bytes(text.encode('utf8'))
            save(folder / 'PUBLIC.json', value)
            wire = client.output / ('rpc_' + str(client.records[-1]['index']).zfill(2))
            observations[phase] = {'request': pin(folder / 'REQUEST.json'), 'response': pin(folder / 'RESPONSE.json'),
                'public': pin(folder / 'PUBLIC.txt'), 'TX': pin(wire / 'TX.bin'), 'RX': pin(wire / 'RX.bin'),
                'receipt': pin(wire / 'RECEIPT.json'), 'public_UTF8_bytes': len(text.encode('utf8')),
                'producer_path': str(root / 'worker' / ('call_' + str(ordinal).zfill(2)) / 'SERVICE_RESULT.json'),
                'capture_path': str(root / 'worker' / ('CAPTURE_' + str(ordinal).zfill(2) + '.json')),
                'original_arguments_equal': request['params'] == original['request']['params'], 'image_blocks': 0}
            save(folder / 'RECEIPT.json', observations[phase])
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    finally:
        closed = client.finish() if client is not None else None
        events = []
        if client is not None:
            while True:
                try:
                    kind, raw, at = client.events.get_nowait()
                except queue.Empty:
                    break
                events.append({'kind': kind, 'observed_ns': at, 'error': raw if kind == 'error' else None})
        eof_path, exit_path = root / 'worker/EOF.json', root / 'worker/WORKER_EXIT.json'
        eof = read(eof_path) if eof_path.exists() else None
        exited = read(exit_path) if exit_path.exists() else None
        stdout_eof = any(row['kind'] == 'eof' for row in events)
        held = {'events': events, 'stdout_eof_observed': stdout_eof, 'process_close': closed,
                'worker_EOF': eof, 'worker_exit': exited, 'platform': os.name}
        save(root / 'HELD_EOF.json', held)
        good = (failure is None and len(observations) == 2 and closed and closed['confirmed'] and stdout_eof
            and eof and eof['closed'] and eof['input_eof_observed'] and eof['old_inputs_unchanged']
            and eof['host_requests'] == eof['observe_calls'] == 2
            and eof['network_attempts'] == eof['old_write_attempts'] == eof['PNG_open_attempts'] == eof['raster_attempt_events'] == 0
            and exited and exited['production_returned'] and exited['production_return_code'] == 0
            and exited['installed_source_verified'] and exited['input_eof_observed']
            and eof['pid'] == exited['pid'] == closed['pid'])
        result = {'label': label, 'passed': bool(good), 'production_evidence_option': evidence,
            'binding': pin(binding_path), 'observations': observations, 'failure': failure,
            'started_ns': started, 'closed_ns': time.perf_counter_ns(),
            'closure': pin(root / 'wire/CLOSE.json') if (root / 'wire/CLOSE.json').exists() else None,
            'held_EOF': pin(root / 'HELD_EOF.json'), 'actual_Blender_starts': 0,
            'actual_models': 0, 'actual_rasters': 0,
            'scope': 'original ordered task capture and args; normal installed service/solver/cache/formatter, original #2 id retained'}
        save(root / 'CASE.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--mode', choices=('standard', 'evidence'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=LABELS)
    args = parser.parse_args()
    root, binding = args.output.resolve(), args.binding.resolve(strict=True)
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'new_exclusive_arm_directory_required')
    root.mkdir(parents=True, exist_ok=False)
    sources = [pin(path) for path in (HERE / 'run.py', HERE / 'worker.py', HERE / 'fixtures.py', TRANSPORT)]
    snapshot = root / 'source_snapshot'
    snapshot.mkdir()
    for row in sources:
        (snapshot / Path(row['path']).name).write_bytes(Path(row['path']).read_bytes())
    labels = [args.case] if args.case else list(LABELS)
    save(root / 'SOURCE.json', {'files': sources, 'binding': pin(binding), 'labels': labels, 'mode': args.mode})
    rows = []
    for label in labels:
        value = case(root / 'cases' / label, binding, label, args.mode == 'evidence')
        rows.append(value)
        print(json.dumps({'label': label, 'passed': value['passed'],
                          'path': str(root / 'cases' / label / 'CASE.json')}), flush=True)
        if not value['passed']:
            break
    result = {'schema': 'whole-object-witness-triangle-stdio-replay-v1',
        'passed': len(rows) == len(labels) and all(row['passed'] for row in rows),
        'planned': labels, 'actual': rows, 'unrun': labels[len(rows):], 'sources': sources,
        'binding': pin(binding), 'mode': args.mode, 'actual_Blender_starts': 0,
        'actual_models': 0, 'actual_rasters': 0}
    save(root / 'INDEX.json', result)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    raise SystemExit(main())
