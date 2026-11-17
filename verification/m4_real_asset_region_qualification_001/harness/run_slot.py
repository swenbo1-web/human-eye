"""Two bounded real-asset sessions using the fixed installed public entry."""

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUNTIME = Path('D:/he_m4_real_asset_region_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def export(runtime, state, folder, oracle):
    path = folder / ('SOURCE_' + state + '.json')
    code = ('OUTPUT_PATH=' + repr(str(path)) + '\nSTATE=' + repr(state)
            + '\nOWNED_ROOT=' + repr(str(folder)) + '\n' + (HERE / 'export_source.py').read_text(encoding='utf8'))
    began = time.perf_counter_ns()
    response = runtime._native_call(code, trusted=True)
    if response['error'] is not None:
        raise ValueError('fresh_source_export_failed/' + str(response['error']))
    lines = [line for line in response['stdout'].splitlines() if line.startswith('REAL_ASSET_EXPORT:')]
    if len(lines) != 1:
        raise ValueError('fresh_source_export_receipt_missing')
    receipt = json.loads(lines[0].split(':', 1)[1])
    if sha(path) != receipt['sha256'] or receipt['process_id'] != runtime.native.config['pid']:
        raise ValueError('fresh_source_export_binding')
    answer_path = folder / ('ORACLE_' + state + '.json')
    answer = oracle.analyze(path, NS / 'inputs/ARM_REGION.json', answer_path)
    if answer is None:
        answer = read(answer_path)
    if answer.get('status') != 'passed':
        raise ValueError('fresh_source_or_independent_answer_not_qualified/' + str(answer.get('failure')))
    finished = time.perf_counter_ns()
    save(folder / ('SOURCE_' + state + '_RECEIPT.json'), {
        'started_ns': began, 'finished_ns': finished, 'receipt': receipt,
        'oracle_path': str(answer_path), 'oracle_sha256': sha(answer_path),
        'fixed_before_subsequent_product_query': True,
    })
    runtime.check()
    return answer


def request(runtime, arguments, label, folder, deadline):
    began = time.perf_counter_ns()
    request_deadline = min(deadline, began + 30_000_000_000)
    runtime.client.deadline = request_deadline
    try:
        response = runtime.public_request(arguments)
    finally:
        runtime.client.deadline = deadline
    returned = time.perf_counter_ns()
    record = dict(label=label, arguments=arguments, started_ns=began, returned_ns=returned,
                  deadline_ns=request_deadline, public_index=runtime._product_calls,
                  is_error='error' in response or response.get('result', {}).get('isError') is True)
    call = folder / 'product_calls' / ('call_' + str(runtime._product_calls).zfill(3))
    delivery = call / 'delivered'
    delivery.mkdir()
    images = []
    for block in response.get('result', {}).get('content', []):
        if block.get('type') == 'image':
            raw = base64.b64decode(block['data'], validate=True)
            path = delivery / ('image_' + str(len(images) + 1).zfill(2) + '.png')
            path.write_bytes(raw)
            images.append(dict(path=str(path), sha256=sha(path), bytes=len(raw)))
    record['images'] = images
    record['public_result'] = None
    if not record['is_error']:
        texts = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
        if len(texts) != 1:
            raise ValueError('public_result_text_count')
        record['public_result'] = json.loads(texts[0])
    save(call / 'DELIVERY.json', record)
    if returned >= request_deadline:
        raise TimeoutError('original_30_second_public_deadline')
    return record


def arguments(selection, region_ref=None, full=False):
    query = {'mode': 'source_region', 'reference': {'name': 'Cube'},
             'requested_facts': ['surface_proximity']}
    if region_ref is None:
        query['region'] = {'object': {'name': selection['object']},
                           'source_triangle_indices': sorted(selection['source_triangle_ids'])}
    else:
        query['region_ref'] = copy.deepcopy(region_ref)
    value = {'session_id': 'real-asset-region-001', 'include_image': True, 'query': query}
    if full:
        value['response_detail'] = 'full'
    return value


def run(label):
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    folder = RUNTIME / 'sessions' / label
    folder.mkdir(parents=True, exist_ok=False)
    result = dict(schema='real-asset-region-slot-v1', label=label, status='running', errors=[], requests=[],
                  clocks=dict(slot_started_ns=started, owned_deadline_ns=deadline),
                  model_consumers=0, paid_API_calls=0, cleanup={}, source_exports=[])
    runtime = None
    native_handle = None
    proof = load('_real_process_proof', HERE / 'reused/process_proof.py')
    moved = restored = False
    try:
        frozen = read(NS / 'SOURCE_FREEZE.json')
        for row in frozen['direct_inputs']:
            if sha(row['path']) != row['sha256']:
                raise ValueError('frozen_direct_input_changed/' + row['path'])
        binding = read(NS / 'R1_RUN_BINDING.json')
        for dependency in (binding['dependency_root'], read(NS / 'SHARED_DEPENDENCY.json')['dependency_root']):
            sys.path.insert(0, dependency)
        oracle = load('_real_asset_oracle', NS / 'oracle/source_oracle.py')
        controller = load('_real_owned', HERE / 'owned_runtime.py')
        runtime = controller.RootRuntime.start(folder, 'qualification', label, 'R1', deadline_ns=deadline)
        identity, native_handle = proof._windows_runtime_proof(runtime.native.process, runtime.native.config['pid'], deadline)
        save(folder / 'NATIVE_RUNTIME_PROOF.json', identity)
        if identity.get('confirmed') is not True:
            raise RuntimeError('native_identity_unconfirmed')
        result['clocks']['ready_ns'] = time.perf_counter_ns()
        answer = export(runtime, 'initial', folder, oracle)
        result['source_exports'].append('initial')
        selection = answer['request_region_selection']
        first = request(runtime, arguments(selection), 'initial', folder, deadline)
        result['requests'].append(first)
        initial_ref = None if first['is_error'] else first['public_result'].get('region_ref')
        if label == 'main':
            if initial_ref is None:
                result['not_run'] = {'repeat': 'initial_public_region_ref_unavailable'}
            else:
                result['requests'].append(request(runtime, arguments(selection, initial_ref, full=True),
                                                  'repeat', folder, deadline))
        else:
            save(folder / 'MOVE_RECEIPT.json', runtime.native.m5_matrix_step('qa_m5_matrix_move'))
            moved = True
            moved_answer = export(runtime, 'moved', folder, oracle)
            result['source_exports'].append('moved')
            if initial_ref is not None:
                result['requests'].append(request(runtime, arguments(selection, initial_ref), 'moved_old', folder, deadline))
            result['requests'].append(request(runtime, arguments(moved_answer['request_region_selection']),
                                              'moved_current', folder, deadline))
            save(folder / 'RESTORE_RECEIPT.json', runtime.native.m5_matrix_step('qa_m5_matrix_restore'))
            restored = True
            restored_answer = export(runtime, 'restored', folder, oracle)
            result['source_exports'].append('restored')
            if initial_ref is not None:
                result['requests'].append(request(runtime, arguments(selection, initial_ref), 'restored_old', folder, deadline))
            result['requests'].append(request(runtime, arguments(restored_answer['request_region_selection']),
                                              'restored_current', folder, deadline))
        result['status'] = 'completed'
    except BaseException as error:
        result['status'] = 'failed'
        result['errors'].append(dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    finally:
        if runtime is not None:
            if moved and not restored and not (runtime.native.workspace / 'POISONED.json').exists():
                try:
                    save(folder / 'CLEANUP_RESTORE_RECEIPT.json', runtime.native.m5_matrix_step('qa_m5_matrix_restore'))
                    restored = True
                except BaseException as error:
                    result['errors'].append(dict(phase='fixture_restore', type=type(error).__name__, message=str(error)))
            try:
                close = runtime.close()
                result['cleanup']['runtime_close'] = close
                state = close['Blender_status']['closed']
                if (close.get('errors') or close['runtime']['errors'] or close['Blender_close']['exit_code'] != 0
                        or state['poisoned'] or state['initial_geometry_fingerprint'] != state['final_geometry_fingerprint']
                        or close['Blender_status']['source_file_unchanged'] is not True
                        or close['Blender_status']['protected_files_unchanged'] is not True
                        or close['MCP_stdio_close']['confirmed'] is not True
                        or close['MCP_retained_exit']['exit_code'] != 0):
                    raise RuntimeError('source_or_process_closure_unconfirmed')
            except BaseException as error:
                result['errors'].append(dict(phase='close', type=type(error).__name__, message=str(error)))
            try:
                result['cleanup']['native_retained_exit'] = proof._runtime_exit(native_handle)
                native_handle = None
                runtime.native.process._handle.Close()
                result['cleanup']['native_Popen_handle_closed'] = bool(runtime.native.process._handle.closed)
                if result['cleanup']['native_retained_exit'].get('exit_code') != 0:
                    raise RuntimeError('native_exit_unconfirmed')
            except BaseException as error:
                result['errors'].append(dict(phase='native_exit', type=type(error).__name__, message=str(error)))
        if native_handle is not None:
            result['cleanup']['late_native_exit'] = proof._runtime_exit(native_handle)
        result['fixture_control'] = dict(moved=moved, restored=restored, source_file_saved=False,
                                         product_setters=0, fixture_matrix_setters=int(moved) + int(restored))
        if result['errors'] or time.perf_counter_ns() >= deadline:
            result['status'] = 'failed'
        result['clocks']['cleanup_closed_ns'] = time.perf_counter_ns()
        save(folder / 'SLOT_RESULT.json', result)
        ended = time.perf_counter_ns()
        save(folder / 'SLOT_PUBLICATION.json', dict(label=label, status=result['status'], slot_started_ns=started,
             slot_result_published_ns=ended, complete_slot_ns=ended - started,
             result_sha256=sha(folder / 'SLOT_RESULT.json'), owned_budget_passed=ended < deadline))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', choices=('main', 'state'), required=True)
    args = parser.parse_args()
    value = run(args.label)
    print(json.dumps({'label': args.label, 'status': value['status'], 'errors': value['errors']}))
    raise SystemExit(0 if value['status'] == 'completed' else 1)
