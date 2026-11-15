"""Root-held single live slot, including original deadlines and child closure."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path('D:/he_m4_target_consume_001')
PYTHON = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
SEQUENCE = [('N1', 'N'), ('P1', 'P'), ('P2', 'P'), ('N2', 'N'), ('N3', 'N'), ('P3', 'P')]


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def error_record(error, phase):
    return dict(phase=phase, type=type(error).__name__, message=str(error),
                traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__)))


def retain_children(actor, folder, deadline, proof_module, retained):
    for kind in ('native', 'mcp'):
        path = folder / kind / 'SPAWN.json'
        if kind in retained or not path.exists():
            continue
        try:
            receipt = read(path)
        except (json.JSONDecodeError, PermissionError):
            continue
        proof, handle = proof_module._windows_runtime_proof(actor, receipt['pid'], deadline)
        proof.update(spawn_receipt=str(path), spawn_receipt_sha256=sha(path),
                     scope='Actual actor child observed before consumer launch, retained through root closure')
        retained[kind] = dict(proof=proof, handle=handle)
        save(folder / ('ROOT_' + kind.upper() + '_PROOF.json'), proof)
        if proof.get('confirmed') is not True:
            raise RuntimeError('owned_child_not_proved_' + kind)


def finish_held_child(row, proof_module):
    handle = row['handle']
    if handle is None:
        return proof_module._runtime_exit(handle)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    forced = False
    if kernel.WaitForSingleObject(handle, 0) == 258:
        termination = kernel.OpenProcess(0x00101001, False, row['proof']['runtime_pid'])
        if not termination:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            stamps = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(termination, *[ctypes.byref(value) for value in stamps]):
                raise ctypes.WinError(ctypes.get_last_error())
            birth = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
            if birth != row['proof']['runtime_created_filetime']:
                raise RuntimeError('owned_child_creation_identity_changed')
            if not kernel.TerminateProcess(termination, 124):
                raise ctypes.WinError(ctypes.get_last_error())
            kernel.WaitForSingleObject(termination, 5000)
            forced = True
        finally:
            kernel.CloseHandle(termination)
    result = proof_module._runtime_exit(handle)
    result['forced_by_root'] = forced
    return result


def rpc(endpoint, message, deadline):
    address = read(endpoint)
    payload = dict(request_id='qualification-' + str(message['id']), operation='attached_mcp',
                   args=dict(kind='native', message=message))
    with socket.create_connection((address['host'], address['port']), timeout=30) as connection:
        connection.settimeout(max(.001, (deadline - time.perf_counter_ns()) / 1e9))
        connection.sendall(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        connection.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            block = connection.recv(65536)
            if not block:
                break
            chunks.append(block)
            if sum(map(len, chunks)) > 24 * 1024 * 1024:
                raise ValueError('qualification_frame_size')
    value = json.loads(b''.join(chunks))
    if value.get('ok') is not True:
        raise RuntimeError('qualification_transport_' + str(value.get('error')))
    return value['result']


def qualify(group, folder, endpoint, deadline):
    messages = [{'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
                 'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                            'clientInfo': {'name': 'target-task-root-qualification', 'version': '1'}}},
                {'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'}]
    if group == 'N':
        messages.extend([
            {'jsonrpc': '2.0', 'id': 'native_read', 'method': 'tools/call', 'params': {
                'name': 'execute_python', 'arguments': {'code':
                    "import numpy as np\nimport shapely\nfrom fractions import Fraction\n"
                    "selected = scene_data(['M4_Far_00'])\n"
                    "print({'source_ref': selected['source_ref'], 'objects': len(selected['objects']), "
                    "'vertices': len(selected['objects'][0]['vertices']), "
                    "'triangles': len(selected['objects'][0]['triangles']), 'fraction': str(Fraction(1, 2))})"}}},
            {'jsonrpc': '2.0', 'id': 'native_frame', 'method': 'tools/call', 'params': {
                'name': 'render_views', 'arguments': {'names': ['SCENE'], 'include_images': True}}}])
    else:
        messages.append({'jsonrpc': '2.0', 'id': 'product', 'method': 'tools/call', 'params': {
            'name': 'active_observation', 'arguments': {'include_images': True}}})
    messages.append({'jsonrpc': '2.0', 'id': 'ping', 'method': 'ping'})
    rows = []
    for index, message in enumerate(messages, 1):
        save(folder / ('QUAL_REQUEST_' + str(index).zfill(2) + '.json'), message)
        began = time.perf_counter_ns()
        response = rpc(endpoint, message, deadline)
        ended = time.perf_counter_ns()
        save(folder / ('QUAL_RESPONSE_' + str(index).zfill(2) + '.json'), response)
        rows.append(dict(id=message['id'], started_ns=began, closed_ns=ended,
                         is_error=response.get('result', {}).get('isError'), error=response.get('error')))
    save(folder / 'QUAL_CALLS.json', rows)
    if any(row['is_error'] is True or row['error'] is not None for row in rows):
        raise RuntimeError('qualification_business_error_saved')
    return dict(status='completed', qualification_calls=rows, model_consumers=0)


def run_slot(slot_id, group, phase):
    started = time.perf_counter_ns()
    consumer_deadline = started + 450_000_000_000
    owned_deadline = started + 600_000_000_000
    if phase == 'formal' and (slot_id, group) not in SEQUENCE:
        raise ValueError('fixed_formal_slot')
    if phase not in ('qualification', 'formal') or group not in ('N', 'P'):
        raise ValueError('fixed_phase_and_group')
    folder = EXTERNAL / phase / slot_id
    folder.mkdir(parents=True, exist_ok=False)
    owner_output = folder / 'owner'
    owner_output.mkdir()
    result = dict(schema='target-task-consumption-slot-v1', slot_id=slot_id, group=group, phase=phase,
                  status='running', consumer_path=None, consumer_record=None, consumer_envelope_path=None,
                  source={}, owned={}, cleanup={}, errors=[], clocks=dict(slot_started_ns=started,
                      consumer_deadline_ns=consumer_deadline, owned_deadline_ns=owned_deadline))
    actor = None
    retained = {}
    stdout = (folder / 'ACTOR_STDOUT.bin').open('xb')
    stderr = (folder / 'ACTOR_STDERR.bin').open('xb')
    proof_module = load('_target_slot_process_proof', ROOT / 'verification/m4_target_acquisition_002/harness/reused/process_proof.py')
    try:
        binding = read(HERE / 'PRODUCT_RUN_BINDING.json')
        for row in binding['source_manifest']:
            if sha(Path(binding['install_root']) / row['path']) != row['sha256']:
                raise ValueError('frozen_product_install_changed')
        if sha('D:/he_m4_target_002/assets_01/main.blend') != '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164':
            raise ValueError('frozen_asset_changed')
        config = dict(runroot=str(folder), phase=phase, label=slot_id, group=group,
                      owned_deadline_ns=owned_deadline, worker_deadline_ns=consumer_deadline,
                      budget_root=str(EXTERNAL / 'budget'), output=str(owner_output),
                      endpoint=str(folder / 'ENDPOINT.json'), ready=str(folder / 'READY.json'))
        save(folder / 'CONFIG.json', config)
        command = [str(PYTHON), '-I', '-B', '-X', 'utf8', str(HERE / 'bootstrap.py'),
                   str(HERE / 'bridge.py'), '--config', str(folder / 'CONFIG.json')]
        actor = subprocess.Popen(command, cwd=folder, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        save(folder / 'ACTOR_SPAWN.json', dict(pid=actor.pid, parent_pid=os.getpid(), command=command,
             started_ns=started, recorded_ns=time.perf_counter_ns(), original_deadline_ns=owned_deadline))
        while not (folder / 'READY.json').exists():
            retain_children(actor, folder, consumer_deadline, proof_module, retained)
            if actor.poll() is not None:
                raise RuntimeError('actor_exited_before_ready')
            if time.perf_counter_ns() >= consumer_deadline:
                raise TimeoutError('original_task_deadline_during_setup')
            time.sleep(.05)
        retain_children(actor, folder, consumer_deadline, proof_module, retained)
        ready = read(folder / 'READY.json')
        if ready['actor_pid'] != actor.pid or ready['worker_deadline_ns'] != consumer_deadline:
            raise ValueError('actual_actor_identity_or_deadline')
        required_children = {'native', 'mcp'} if group == 'P' else {'native'}
        if set(retained) != required_children:
            raise RuntimeError('ready_child_receipts_incomplete')
        if ready['runtime']['native_pid'] != retained['native']['proof']['runtime_pid']:
            raise ValueError('ready_native_pid_mismatch')
        if group == 'P' and ready['runtime']['MCP_pid'] != retained['mcp']['proof']['runtime_pid']:
            raise ValueError('ready_product_pid_mismatch')
        result['owned'] = ready
        result['source'] = dict(product_source141_sha256=binding['source_sha256'],
            product_binding_sha256=sha(HERE / 'PRODUCT_RUN_BINDING.json'),
            common_task_sha256=sha(HERE / 'inputs/COMMON_TASK.txt'), answer_schema_sha256=sha(HERE / 'inputs/ANSWER_SCHEMA.json'),
            asset_sha256='2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164')
        result['clocks']['owner_ready_ns'] = time.perf_counter_ns()
        if phase == 'qualification':
            envelope = qualify(group, folder, config['endpoint'], consumer_deadline)
        else:
            save(folder / 'CONSUMER_START.json', dict(slot_id=slot_id, group=group,
                 original_deadline_ns=consumer_deadline, started_ns=time.perf_counter_ns(), replacement_samples=0))
            launcher = load('_target_task_root_launcher', HERE / 'launcher.py')
            envelope = launcher.consume_slot(slot_id=slot_id, group=group, slot_root=folder,
                endpoint=config['endpoint'], owner_output=owner_output,
                deadline_ns=consumer_deadline, model_consumer_enabled=True)
            save(folder / 'CONSUMER_ENVELOPE.json', envelope)
            result.update(consumer_path=envelope['consumer_path'], consumer_record=envelope['consumer_record'],
                          consumer_envelope_path=str(folder / 'CONSUMER_ENVELOPE.json'))
        result['status'] = envelope['status']
        result['clocks']['business_closed_ns'] = time.perf_counter_ns()
    except BaseException as error:
        result['status'] = 'failed'
        result['errors'].append(error_record(error, 'slot'))
    finally:
        result['clocks']['cleanup_started_ns'] = time.perf_counter_ns()
        if actor is not None:
            try:
                if actor.poll() is None:
                    retain_children(actor, folder, owned_deadline, proof_module, retained)
                if actor.stdin is not None and not actor.stdin.closed:
                    actor.stdin.close()
                try:
                    actor.wait(timeout=max(.001, min(45, (owned_deadline - time.perf_counter_ns()) / 1e9)))
                except subprocess.TimeoutExpired:
                    actor.kill()
                    actor.wait(timeout=5)
                    result['errors'].append(dict(phase='cleanup', type='actor_forced_termination'))
                result['cleanup']['actor_exit_code'] = actor.returncode
            except BaseException as error:
                result['errors'].append(error_record(error, 'root_cleanup'))
            for kind, row in retained.items():
                try:
                    result['cleanup'][kind] = finish_held_child(row, proof_module)
                except BaseException as error:
                    result['errors'].append(error_record(error, 'root_child_cleanup_' + kind))
                    result['cleanup'][kind] = proof_module._runtime_exit(row['handle'])
            try:
                result['cleanup']['actor_close'] = read(folder / 'ACTOR_CLOSE.json') if (folder / 'ACTOR_CLOSE.json').exists() else None
            except BaseException as error:
                result['errors'].append(error_record(error, 'actor_close_receipt'))
        stdout.close()
        stderr.close()
        if (result['errors'] or result['cleanup'].get('actor_exit_code') != 0
                or any(not row.get('confirmed') or row.get('forced_by_root')
                       for key, row in result['cleanup'].items() if key in ('native', 'mcp'))):
            result['status'] = 'failed'
        result['clocks']['cleanup_closed_ns'] = time.perf_counter_ns()
        save(folder / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        save(folder / 'SLOT_PUBLICATION.json', dict(schema='target-task-slot-publication-v1',
             slot_id=slot_id, group=group, slot_started_ns=started, slot_result_published_ns=published,
             complete_slot_ns=published - started, result_sha256=sha(folder / 'SLOT_RESULT.json'),
             marker_scope='Written after final slot result fsync. This marker publication is separate.'))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--slot', required=True)
    parser.add_argument('--group', choices=('N', 'P'), required=True)
    parser.add_argument('--phase', choices=('qualification', 'formal'), required=True)
    options = parser.parse_args()
    outcome = run_slot(options.slot, options.group, options.phase)
    print(json.dumps(dict(slot_id=options.slot, status=outcome['status'], errors=outcome['errors'])))
    if outcome['status'] != 'completed':
        raise SystemExit(1)
