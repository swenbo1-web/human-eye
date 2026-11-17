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
RUNTIME = Path('D:/he_m4_source_region_display_001')


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


def host_residency_work(runtime, folder):
    install_root = Path(runtime.binding['install_root']).resolve()
    slot = '_human_eye_mcp_resident_' + hashlib.sha256(str(install_root).encode('utf8')).hexdigest()[:20]
    expected_host_sha = next(row['sha256'] for row in runtime.binding['source_manifest']
                             if row['path'] == 'human_eye_plugin/blender_host.py')
    code = '''
import json as residency_json
import os as residency_os
import sys as residency_sys
import time as residency_time
residency_started = residency_time.perf_counter_ns()
residency_slot = ''' + repr(slot) + '''
residency_module = residency_sys.modules.get(residency_slot)
if residency_module is None:
    raise ValueError('fixed_resident_module_unavailable')
if getattr(residency_module, '_READONLY_LOADED_HOST_SHA256', None) != ''' + repr(expected_host_sha) + ''':
    raise ValueError('fixed_resident_module_source_mismatch')
residency_host = getattr(residency_module, '_mcp_resident_host', None)
if residency_host is None:
    raise ValueError('fixed_resident_host_unavailable')
residency_counters = residency_host.residency_work()
if any(type(residency_counters.get(key)) is not int or residency_counters[key] < 0
       for key in ('display_snapshots', 'display_objects', 'display_read_ns')):
    raise ValueError('fixed_resident_display_counters_unavailable')
print('HOST_RESIDENCY_WORK:' + residency_json.dumps({
    'process_id': residency_os.getpid(), 'module_slot': residency_slot,
    'module_file': residency_module.__file__,
    'loaded_host_source_sha256': residency_module._READONLY_LOADED_HOST_SHA256,
    'read_started_ns': residency_started, 'read_complete_ns': residency_time.perf_counter_ns(),
    'counters': residency_counters}, sort_keys=True, allow_nan=False))
'''
    started = time.perf_counter_ns()
    response = runtime._native_call(code, trusted=True)
    if response['error'] is not None:
        raise ValueError('host_residency_work_read_failed/' + str(response['error']))
    lines = [line for line in response['stdout'].splitlines() if line.startswith('HOST_RESIDENCY_WORK:')]
    if len(lines) != 1:
        raise ValueError('host_residency_work_receipt_count')
    value = json.loads(lines[0].split(':', 1)[1])
    if value['process_id'] != runtime.native.config['pid'] or value['module_slot'] != slot:
        raise ValueError('host_residency_work_process_binding')
    if (Path(value['module_file']).resolve() != install_root / 'human_eye_plugin/blender_host.py'
            or value['loaded_host_source_sha256'] != expected_host_sha):
        raise ValueError('host_residency_work_source_binding')
    record = dict(started_ns=started, returned_ns=time.perf_counter_ns(),
                  native_call_index=len(runtime.native_calls), value=value,
                  source='existing_owned_resident_BlenderSceneHost.residency_work',
                  new_capture_calls=0, new_rasters=0, new_processes=0)
    save(folder / 'HOST_RESIDENCY_WORK.json', record)
    return record


def arguments(selection, region_ref=None, full=False):
    query = {'mode': 'source_region', 'reference': {'name': 'Cube'},
             'requested_facts': ['surface_proximity']}
    if region_ref is None:
        query['region'] = {'object': {'name': selection['object']},
                           'source_triangle_indices': sorted(selection['source_triangle_ids'])}
    else:
        query['region_ref'] = copy.deepcopy(region_ref)
    value = {'session_id': 'source-region-display-001', 'include_image': True, 'query': query}
    if full:
        value['response_detail'] = 'full'
    return value


def run(label):
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    folder = RUNTIME / 'sessions' / label
    folder.mkdir(parents=True, exist_ok=False)
    result = dict(schema='source-region-display-slot-v1', label=label, status='running', errors=[], requests=[],
                  clocks=dict(slot_started_ns=started, owned_deadline_ns=deadline),
                  model_consumers=0, paid_API_calls=0, cleanup={}, source_exports=[])
    runtime = None
    native_handle = None
    proof = load('_real_process_proof', HERE / 'reused/process_proof.py')
    fixture_stage = 0
    try:
        frozen = read(NS / 'SOURCE_FREEZE.json')
        for row in frozen['direct_inputs']:
            if sha(row['path']) != row['sha256']:
                raise ValueError('frozen_direct_input_changed/' + row['path'])
        binding = read(NS / 'R0_RUN_BINDING.json')
        for dependency in (binding['dependency_root'], read(NS / 'SHARED_DEPENDENCY.json')['dependency_root']):
            sys.path.insert(0, dependency)
        oracle = load('_real_asset_oracle', NS / 'oracle/source_oracle.py')
        controller = load('_real_owned', HERE / 'owned_runtime.py')
        runtime = controller.RootRuntime.start(folder, 'qualification', label, 'R0', deadline_ns=deadline)
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
            states = (
                ('cube_visible', 'qa_display_cube_visible'),
                ('cube_restored', 'qa_display_cube_restored'),
                ('target_hidden', 'qa_display_target_hidden'),
                ('target_restored', 'qa_display_target_restored'),
            )
            last_ref = initial_ref
            for state, operation in states:
                receipt = runtime.native.display_step(operation)
                fixture_stage = receipt['response']['result']['stage']
                save(folder / (state.upper() + '_RECEIPT.json'), receipt)
                answer = export(runtime, state, folder, oracle)
                result['source_exports'].append(state)
                current = request(runtime, arguments(answer['request_region_selection']), state, folder, deadline)
                result['requests'].append(current)
                last_ref = None if current['is_error'] else current['public_result'].get('region_ref')
            if last_ref is None:
                result.setdefault('not_run', {})['repeat'] = 'restored_public_region_ref_unavailable'
            else:
                result['requests'].append(request(runtime, arguments(selection, last_ref, full=True),
                                                  'repeat', folder, deadline))
        result['host_residency_work'] = host_residency_work(runtime, folder)
        result['public_ref_observations'] = [
            dict(label=row['label'], is_error=row['is_error'],
                 region_ref=None if row['public_result'] is None else row['public_result'].get('region_ref'),
                 image_refs=[] if row['public_result'] is None else [frame.get('image_ref')
                     for frame in row['public_result'].get('frames', row['public_result'].get('images', []))])
            for row in result['requests']]
        for row in result['requests']:
            if row['is_error']:
                result['errors'].append(dict(phase='public_request', label=row['label'], message='public_request_error'))
        result['status'] = 'completed'
    except BaseException as error:
        result['status'] = 'failed'
        result['errors'].append(dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    finally:
        if runtime is not None:
            if fixture_stage in (1, 3) and not (runtime.native.workspace / 'POISONED.json').exists():
                try:
                    operation = 'qa_display_cube_restored' if fixture_stage == 1 else 'qa_display_target_restored'
                    receipt = runtime.native.display_step(operation)
                    fixture_stage = receipt['response']['result']['stage']
                    save(folder / 'CLEANUP_RESTORE_RECEIPT.json', receipt)
                except BaseException as error:
                    result['errors'].append(dict(phase='fixture_restore', type=type(error).__name__, message=str(error)))
            try:
                close = runtime.close()
                result['cleanup']['runtime_close'] = close
                state = close['Blender_status']['closed']
                if (close.get('errors') or close['runtime']['errors'] or close['Blender_close']['exit_code'] != 0
                        or state['poisoned'] or state['display_restored'] is not True
                        or state['initial_geometry_fingerprint'] != state['final_geometry_fingerprint']
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
        fixture_attempts = 0 if runtime is None else len(list(runtime.native.workspace.glob('DISPLAY_*_ATTEMPT.json')))
        result['fixture_control'] = dict(stage=fixture_stage,
            restored=fixture_attempts == fixture_stage and fixture_stage in (0, 2, 4),
            source_file_saved=False, product_setters=0,
            fixture_hide_set_setters=fixture_stage if fixture_attempts == fixture_stage else None,
            fixture_hide_set_setters_confirmed_lower_bound=fixture_stage,
            fixture_hide_set_setters_upper_bound=fixture_attempts,
            fixture_operation_attempts=fixture_attempts)
        if result['status'] == 'completed' and (result.get('not_run') or fixture_stage != (4 if label == 'state' else 0)):
            result['errors'].append(dict(phase='completion', message='required_public_repeat_or_fixture_sequence_incomplete'))
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
