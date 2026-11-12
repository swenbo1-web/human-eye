"""Owned functional Blender/MCP sequence; never a performance sample."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from verification.m2_tight_directory_001.correctness.oracle import assert_packet, wrong_eight_corner_bounds, tight_bounds


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def control(port, **parameters):
    with socket.create_connection(('127.0.0.1', port), timeout=20) as connection:
        connection.sendall(json.dumps({'type': 'test_control', 'params': parameters}, allow_nan=False).encode())
        response = bytearray()
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
    value = json.loads(response)
    if 'control' not in value:
        raise RuntimeError('functional fixture control rejected: ' + repr(value))
    return value['control']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--engine-root', required=True, type=Path)
    parser.add_argument('--entry', required=True, type=Path)
    parser.add_argument('--python', required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--blender', default='D:/Tools/blender5.2/blender.exe')
    args = parser.parse_args()
    output = HERE / args.output
    assert output.parent.resolve() == HERE.resolve() and output.name not in ('.', '..')
    output.mkdir(exist_ok=False)
    fixture, ready = output / 'fixture.blend', output / 'ready.json'
    sources = {str(path): sha(path.read_bytes()) for path in (
        HERE / 'blender_fixture.py', HERE / 'oracle.py', Path(__file__),
        ROOT / 'verification/arch_resident_001/blender_fixture.py')}
    actor = load(ROOT / 'verification/m4_local_relation_consumption_001/runtime/actor.py', '_directory_existing_peer')
    lifecycle = load(ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py', '_directory_existing_PID_proof')
    verifier = unittest.TestCase()
    records, errors, peer_receipts = [], [], []
    process = peer = handle = None
    port = None
    began = time.perf_counter_ns()
    log = (output / 'blender.log').open('wb')
    serial = 0
    state_path = audit_path = None
    try:
        command = [args.blender, '--factory-startup', '--disable-autoexec', '--background', '--python',
            str(HERE / 'blender_fixture.py'), '--', str(fixture), str(ready)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        save(output / 'BLENDER_START.json', {'argv': command, 'pid': process.pid, 'started_ns': began})
        until = time.monotonic() + 45
        while not ready.exists():
            if process.poll() is not None or time.monotonic() > until:
                raise RuntimeError('owned fixture startup failed')
            time.sleep(.02)
        port = json.loads(ready.read_bytes())['port']
        original_file_sha = sha(fixture.read_bytes())

        def start_peer():
            nonlocal peer, handle, serial, state_path, audit_path
            serial += 1
            folder = output / ('peer_' + str(serial))
            folder.mkdir()
            state_path, audit_path = folder / 'actions.json', folder / 'audit.jsonl'
            config = folder / 'config.json'
            save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                'project_root': str(args.engine_root.resolve()), 'state_file': str(state_path), 'audit_file': str(audit_path),
                'expected_identity': {'source_sha256': args.expected_source_sha256}, 'request_budget_s': 30,
                'blender': {'host': '127.0.0.1', 'port': port, 'timeout_s': 30}})
            peer = actor.Peer({'dependency_python': args.python, 'entry': str(args.entry.resolve()),
                               'group': 'ordinary', 'product_config': config}, folder / 'product')
            initialized = peer.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {}})
            identity = initialized['result']['_meta']['human_eye']
            verifier.assertEqual(identity['source_sha256'], args.expected_source_sha256)
            verifier.assertEqual(identity['source_file_count'], 137)
            save(folder / 'INITIALIZE.json', initialized)
            peer.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            save(folder / 'TOOLS.json', peer.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'}))
            traces = [json.loads(line)['trace'] for line in audit_path.read_bytes().splitlines()
                      if json.loads(line).get('event') == 'request_trace']
            pids = {trace['pid'] for trace in traces}
            verifier.assertEqual(len(pids), 1)
            proof, handle = lifecycle._windows_runtime_proof(peer.process, pids.pop(), time.perf_counter_ns()+30_000_000_000)
            verifier.assertIs(proof['confirmed'], True)
            save(folder / 'RUNTIME_PID_PROOF.json', proof)

        def close_peer():
            nonlocal peer, handle
            if peer is None:
                return
            record = {'close': peer.close(), 'runtime_exit': lifecycle._runtime_exit(handle)}
            handle = None
            verifier.assertIs(record['close']['confirmed'], True)
            verifier.assertTrue(all(record['runtime_exit'][key] is True for key in ('confirmed', 'exited', 'handle_closed')))
            verifier.assertEqual(record['runtime_exit']['exit_code'], 0)
            peer_receipts.append(record)
            peer = None

        def observe(label, query, **extra):
            request = {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call', 'params': {
                'name': 'human_eye_scene_observe', 'arguments': {'session_id': 'directory-functional',
                    'query': query, 'include_image': False, **extra}}}
            started = time.perf_counter_ns()
            response = peer.call(request)
            ended = time.perf_counter_ns()
            save(output / (label + '.REQUEST.json'), request)
            save(output / (label + '.RESPONSE.json'), response)
            verifier.assertFalse(response['result']['isError'])
            verifier.assertTrue(all(block['type'] == 'text' for block in response['result']['content']))
            body = json.loads(response['result']['content'][0]['text'])
            records.append({'label': label, 'started_ns': started, 'ended_ns': ended, 'body': body,
                'scope': 'functional with independent oracle/control work outside this interval; excluded from performance samples'})
            return body

        def directory(label):
            before_state = state_path.read_bytes() if state_path.exists() else None
            value = observe(label, {'mode': 'directory'})
            reference = control(port, op='oracle')
            verifier.assertEqual(reference['pid'], process.pid)
            assert_packet(verifier, value, reference['objects'])
            verifier.assertEqual(value['binding']['frame'], reference['frame'])
            verifier.assertEqual(value['binding']['subframe'], reference['subframe'])
            verifier.assertEqual(state_path.read_bytes() if state_path.exists() else None, before_state)
            save(output / (label + '.ORACLE.json'), reference)
            return value

        start_peer()
        cold = directory('directory_cold')
        warm = directory('directory_warm')
        verifier.assertEqual(cold['capture_state'], warm['capture_state'])
        verifier.assertEqual(cold['objects'], warm['objects'])
        oracle = control(port, op='oracle')
        rotated = next(row for row in oracle['objects'] if row['name'] == 'BluePart')
        actual = tight_bounds(rotated['vertices_local'], rotated['matrix_world'], rotated['unit_scale_m'])
        shortcut = wrong_eight_corner_bounds(rotated['vertices_local'], rotated['matrix_world'], rotated['unit_scale_m'])
        verifier.assertGreater(max(abs(a-b) for a, b in zip(actual['center'], shortcut['center'])), 1e-5)
        target = next(row for row in cold['objects'] if row['name'] == 'BluePart')['object_id']
        task = observe('selected_after_directory', {'mode': 'task', 'objects': [{'id': target}], 'requested_facts': ['aabb']})
        verifier.assertEqual(task['status'], 'observed')
        full = observe('delta_after_directory', {'mode': 'overview'}, scene_delta={
            'base_revision': 'directory:' + cold['directory_sha256'], 'base_fingerprint': cold['directory_sha256']})
        verifier.assertEqual(full['scene_transport']['status'], 'full')
        verifier.assertIn('base_unavailable_full_resync', full['scene_transport']['reason_codes'])
        directory('directory_after_full')
        observe('overview_after_directory', {'mode': 'overview'})
        nearest = observe('nearest_after_directory', {'mode': 'surface_nearest', 'objects': [{'id': target}]})
        verifier.assertIn(nearest['status'], ('complete', 'partial'))
        previous = warm
        for label, parameters in (
            ('pose', dict(op='translate', name='BluePart', dz=.002)),
            ('rotation', dict(op='rotate', name='BluePart', radians=.17)),
            ('geometry', dict(op='mesh', name='BluePart', dz=.001)),
            ('units', dict(op='units', scale=.125)), ('frame', dict(op='frame', frame=2)),
            ('subframe', dict(op='subframe', frame=2, subframe=.5)),
            ('rename', dict(op='rename', name='BluePart', new_name='BlueRenamed')),
            ('replace', dict(op='replace', name='BlueRenamed')),
            ('undo', dict(op='undo')), ('redo', dict(op='redo')),
            ('scene', dict(op='scene')), ('delete', dict(op='delete', name='BluePart')),
            ('reload', dict(op='load', path=str(fixture))),
        ):
            # The inherited undo control targets BluePart, restored before that step.
            if label == 'undo':
                control(port, op='rename', name='BlueRenamed', new_name='BluePart')
            control(port, **parameters)
            current = directory('changed_' + label)
            verifier.assertNotEqual(current['capture_state'], previous['capture_state'])
            previous = current
        close_peer()
        start_peer()
        directory('connector_reconnect')
        close_peer()
        verifier.assertEqual(sha(fixture.read_bytes()), original_file_sha)
    except BaseException as exception:
        errors.append({'type': type(exception).__name__, 'message': str(exception), 'traceback': traceback.format_exc()})
    finally:
        if peer is not None:
            try:
                close_peer()
            except BaseException as exception:
                errors.append({'stage': 'peer_cleanup', 'error': repr(exception)})
        fixture_close = {'requested': False, 'response': None, 'forced': False, 'exit_code': None}
        if process is not None:
            if process.poll() is None and port is not None:
                fixture_close['requested'] = True
                try:
                    fixture_close['response'] = control(port, op='quit')
                except (OSError, ValueError) as exception:
                    fixture_close['response_error_type'] = type(exception).__name__
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                fixture_close['forced'] = True
                process.kill()
                process.wait(timeout=5)
            fixture_close['exit_code'] = process.returncode
        log.close()
        sources_unchanged = all(sha(Path(path).read_bytes()) == digest for path, digest in sources.items())
        result = {'passed': not errors and sources_unchanged and fixture_close['exit_code'] == 0 and not fixture_close['forced'],
            'records': records, 'errors': errors, 'product_closes': peer_receipts, 'Blender_close': fixture_close,
            'source_sha256': args.expected_source_sha256, 'QA_sources': sources, 'QA_sources_unchanged': sources_unchanged,
            'functional_fixture_sessions': 1, 'model_consumers': 0, 'performance_samples': 0,
            'elapsed_ns': time.perf_counter_ns()-began}
        save(output / 'RESULTS.json', result)
        print(json.dumps({'passed': result['passed'], 'functional_records': len(records), 'errors': len(errors)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
