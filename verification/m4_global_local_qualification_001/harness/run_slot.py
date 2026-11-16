"""One fresh read-only Blender plus the fixed public MCP, held to full closure."""

import argparse
import base64
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
RUNTIME = Path('D:/he_m4_global_local_001')


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
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def validate_source(source, expected):
    actual = {row['name']: row for row in source['objects']}
    wanted = {row['name']: row for row in expected['objects']}
    if set(actual) != set(wanted) or source['source']['scale_length'] != 1:
        raise ValueError('frozen_fixture_object_set_or_unit')
    for name, row in wanted.items():
        points = row.get('vertices', row.get('vertices_world_m'))
        triangles = row.get('triangles', row.get('faces'))
        vertices = [[float(Fraction(value)) for value in point] for point in points]
        if actual[name]['vertices'] != vertices or actual[name]['triangles'] != triangles:
            raise ValueError('frozen_fixture_geometry_or_order_changed/' + name)


def closure_valid(close, native_exit):
    native = close.get('Blender_status', {})
    state = native.get('closed') or {}
    stdio = close.get('MCP_stdio_close', {})
    mcp_exit = close.get('MCP_retained_exit', {})
    return (not close.get('errors') and not close['runtime'].get('errors')
            and close.get('Blender_close', {}).get('exit_code') == 0
            and close.get('Blender_close', {}).get('process_reaped') is True
            and state.get('poisoned') is False
            and state.get('initial_geometry_fingerprint') == state.get('final_geometry_fingerprint')
            and native.get('source_file_unchanged') is True
            and native.get('protected_files_unchanged') is True
            and stdio.get('confirmed') is True and stdio.get('reader_stopped') is True
            and mcp_exit.get('confirmed') is True and mcp_exit.get('exit_code') == 0
            and native_exit.get('confirmed') is True and native_exit.get('exit_code') == 0)


def run(label):
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    folder = RUNTIME / 'sessions' / label
    folder.mkdir(parents=True, exist_ok=False)
    result = dict(schema='m4-global-local-slot-v1', label=label, group='B', status='running',
                  clocks=dict(slot_started_ns=started, owned_deadline_ns=deadline), errors=[],
                  model_consumers=0, paid_API_calls=0, public_requests_attempted=0, cleanup={})
    runtime = None
    native_handle = None
    proof = None
    try:
        frozen = read(NAMESPACE / 'FROZEN.json')
        for row in frozen['files']:
            if sha(NAMESPACE / row['relative']) != row['sha256']:
                raise ValueError('frozen_qualification_input_changed/' + row['relative'])
        binding = read(NAMESPACE / 'B_RUN_BINDING.json')
        sys.path.insert(0, binding['dependency_root'])
        controller = load('_global_local_owned_runtime', HERE / 'owned_runtime.py')
        proof = load('_global_local_process_proof', HERE / 'reused/process_proof.py')
        runtime = controller.RootRuntime.start(folder, 'qualification', label, 'B', deadline_ns=deadline)
        original, native_handle = proof._windows_runtime_proof(runtime.native.process, runtime.native.config['pid'], deadline)
        save(folder / 'NATIVE_RUNTIME_PROOF.json', original)
        if original.get('confirmed') is not True:
            raise RuntimeError('native_runtime_identity_unconfirmed')
        result['clocks']['ready_ns'] = time.perf_counter_ns()
        source = runtime.scene_data()
        validate_source(source, read(NAMESPACE / 'fixture/GEOMETRY.json'))
        result['source'] = dict(asset_sha256=controller.ASSET_SHA256,
                              product_sha256=binding['source_sha256'], raw_source_ref=source['source_ref'])
        arguments = read(NAMESPACE / 'REQUESTS.json')[label]
        result['request_arguments'] = arguments
        result['paths'] = dict(session=str(folder), producer_result=str(folder / 'product_full/call_001/SERVICE_RESULT.json'),
                               public_request=str(folder / 'product_calls/call_001/REQUEST.json'),
                               public_response=str(folder / 'product_calls/call_001/RESPONSE.json'),
                               saved_evidence=str(folder / 'SAVED_EVIDENCE.json'))
        request_started = time.perf_counter_ns()
        request_deadline = min(deadline, request_started + 30_000_000_000)
        result['clocks'].update(public_started_ns=request_started, public_deadline_ns=request_deadline)
        result['public_requests_attempted'] = 1
        runtime.client.deadline = request_deadline
        try:
            response = runtime.public_request(arguments)
        finally:
            runtime.client.deadline = deadline
        result['clocks']['public_returned_ns'] = time.perf_counter_ns()
        result['product_is_error'] = response.get('result', {}).get('isError')
        if 'error' in response or response.get('result', {}).get('isError') is True:
            raise RuntimeError('actual_public_error_preserved')
        image_rows = []
        delivery = folder / 'delivered'
        delivery.mkdir()
        for block in response['result'].get('content', []):
            if block.get('type') != 'image':
                continue
            raw = base64.b64decode(block['data'], validate=True)
            path = delivery / ('image_' + str(len(image_rows) + 1).zfill(2) + '.png')
            path.write_bytes(raw)
            image_rows.append(dict(path=str(path), sha256=sha(path), bytes=len(raw)))
        save(delivery / 'DELIVERY.json', dict(images=image_rows, model_consumers=0,
            scope='Actual public MCP image bytes decoded by the zero-model qualification caller.'))
        result['clocks']['business_closed_ns'] = time.perf_counter_ns()
        if result['clocks']['public_returned_ns'] >= request_deadline:
            raise TimeoutError('original_public_30_second_deadline')
        result['status'] = 'completed'
    except BaseException as error:
        result['status'] = 'failed'
        result['errors'].append(dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    finally:
        result['clocks']['cleanup_started_ns'] = time.perf_counter_ns()
        if runtime is not None:
            try:
                result['cleanup']['runtime_close'] = runtime.close()
            except BaseException as error:
                result['errors'].append(dict(phase='runtime_close', type=type(error).__name__, message=str(error)))
            try:
                native_exit = proof._runtime_exit(native_handle)
                native_handle = None
                process = runtime.native.process
                if process.poll() is not None:
                    process._handle.Close()
                native_exit['Popen_handle_closed'] = bool(process._handle.closed)
                result['cleanup']['native_retained_exit'] = native_exit
                if not closure_valid(result['cleanup'].get('runtime_close', {}), native_exit):
                    raise RuntimeError('closure_or_source_integrity_failed')
            except BaseException as error:
                result['errors'].append(dict(phase='closure_validation', type=type(error).__name__, message=str(error)))
        if native_handle is not None and proof is not None:
            result['cleanup']['native_late_exit'] = proof._runtime_exit(native_handle)
        if result['errors'] or time.perf_counter_ns() >= deadline:
            result['status'] = 'failed'
        result['clocks']['cleanup_closed_ns'] = time.perf_counter_ns()
        save(folder / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        publication = dict(schema='m4-global-local-publication-v1', label=label,
            slot_started_ns=started, slot_result_published_ns=published, complete_slot_ns=published-started,
            result_sha256=sha(folder / 'SLOT_RESULT.json'), owned_budget_passed=published < deadline,
            status=result['status'] if published < deadline else 'failed')
        save(folder / 'SLOT_PUBLICATION.json', publication)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', choices=('global', 'local_open', 'local_covered'), required=True)
    outcome = run(parser.parse_args().label)
    print(json.dumps(dict(label=outcome['label'], status=outcome['status'], errors=outcome['errors'])))
    if outcome['status'] != 'completed':
        raise SystemExit(1)
