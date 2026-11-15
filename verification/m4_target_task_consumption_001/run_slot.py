"""Root-held single live slot, including original deadlines and child closure."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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


def qualify(group, folder, endpoint, deadline):
    driver = load('_root_target_task_qualification', HERE / 'qual_driver.py')
    record = driver.qualify(read(endpoint), folder / 'qualification_calls', group, deadline)
    smoke = {'jsonrpc': '2.0', 'id': 'qual-ordinary-libraries', 'method': 'tools/call', 'params': {
        'name': 'execute_python', 'arguments': {'code':
            "import numpy as np\nfrom shapely.geometry import box\nfrom fractions import Fraction\n"
            "print({'sum': int(np.arange(4).sum()), 'area': box(0, 0, 1, 1).area, 'fraction': str(Fraction(1, 2))})\n"
            "native = blender('import bpy\\nprint(len(bpy.context.scene.objects))')\n"
            "assert native['error'] is None\nprint(native)"}}}
    smoke_record = driver.rpc(read(endpoint), smoke, folder / 'qualification_calls/library_smoke', deadline)
    if (record['passed_transport_scope'] is not True
            or smoke_record['response'].get('result', {}).get('isError') is not False):
        raise RuntimeError('qualification_business_error_saved')
    return dict(status='completed', qualification_record=str(folder / 'qualification_calls/QUALIFICATION_CALLS.json'), model_consumers=0)


def validate_closure(result):
    cleanup = result['cleanup']
    actor = cleanup.get('actor_close')
    if not actor or actor.get('errors') or actor.get('actor_pid') != result.get('owned', {}).get('actor_pid'):
        raise RuntimeError('actor_closure_missing_or_failed')
    bridge = actor.get('bridge')
    if not bridge or bridge.get('confirmed') is not True or bridge.get('errors'):
        raise RuntimeError('MCP_listener_closure_failed')
    runtime = actor.get('runtime')
    if not runtime or runtime.get('errors') or runtime.get('runtime', {}).get('errors'):
        raise RuntimeError('runtime_closure_failed')
    native_close = runtime.get('Blender_close', {})
    native_status = runtime.get('Blender_status', {})
    native = native_status.get('closed')
    if (native_close.get('exit_code') != 0 or native_close.get('process_reaped') is not True
            or not native or native.get('poisoned')
            or native['initial_geometry_fingerprint'] != native['final_geometry_fingerprint']
            or native_status.get('source_file_unchanged') is not True
            or native_status.get('protected_files_unchanged') is not True):
        raise RuntimeError('native_source_or_closure_failed')
    if result['group'] == 'P':
        stdio = runtime.get('MCP_stdio_close', {})
        child = runtime.get('MCP_retained_exit', {})
        if (stdio.get('confirmed') is not True or stdio.get('exit_code') != 0
                or child.get('confirmed') is not True or child.get('exit_code') != 0
                or child.get('handle_closed') is not True):
            raise RuntimeError('product_stdio_or_closure_failed')


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
            except BaseException as error:
                result['errors'].append(error_record(error, 'late_child_ownership'))
            try:
                if actor.stdin is not None and not actor.stdin.closed:
                    actor.stdin.close()
            except BaseException as error:
                result['errors'].append(error_record(error, 'actor_stdin_close'))
            try:
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
            try:
                if actor.returncode is not None:
                    actor._handle.Close()
                    result['cleanup']['actor_process_handle_closed'] = True
                else:
                    result['cleanup']['actor_process_handle_closed'] = False
            except BaseException as error:
                result['errors'].append(error_record(error, 'actor_process_handle_close'))
        stdout.close()
        stderr.close()
        try:
            validate_closure(result)
        except BaseException as error:
            result['errors'].append(error_record(error, 'closure_validation'))
        if time.perf_counter_ns() >= owned_deadline:
            result['errors'].append(dict(phase='complete_slot', type='original_owned_deadline_exceeded'))
        if (result['errors'] or result['cleanup'].get('actor_exit_code') != 0
                or result['cleanup'].get('actor_process_handle_closed') is not True
                or any(row.get('confirmed') is not True or row.get('exit_code') != 0
                       or row.get('handle_closed') is not True or row.get('forced_by_root')
                       for key, row in result['cleanup'].items() if key in ('native', 'mcp'))):
            result['status'] = 'failed'
        result['clocks']['cleanup_closed_ns'] = time.perf_counter_ns()
        save(folder / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        publication = dict(schema='target-task-slot-publication-v1',
             slot_id=slot_id, group=group, slot_started_ns=started, slot_result_published_ns=published,
             complete_slot_ns=published - started, result_sha256=sha(folder / 'SLOT_RESULT.json'),
             owned_budget_passed=published < owned_deadline,
             status=result['status'] if published < owned_deadline else 'failed',
             marker_scope='Final slot status includes result fsync and original 600-second boundary. This marker publication is separate.')
        save(folder / 'SLOT_PUBLICATION.json', publication)
    return {**result, 'status': publication['status'], 'publication': publication}


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
