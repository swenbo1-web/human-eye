"""Run one immutable diagnostic or formal slot and retain its original outcome."""

import argparse
from pathlib import Path
import sys
import time
import traceback


sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EXTERNAL, NS, PRODUCT_BINDING, SLOTS, asset_identity, read, save, sha
from closure import ready_closure, startup_closure


def validate_publication(label, frozen):
    folder = EXTERNAL / 'slots' / label
    published = read(folder / 'SLOT_PUBLICATION.json')
    result = read(folder / 'SLOT_RESULT.json')
    if (published['label'] != label or published['result_sha256'] != sha(folder / 'SLOT_RESULT.json')
            or result['freeze_sha256'] != frozen):
        raise ValueError('prior_slot_publication_not_bound/' + label)
    return published


def validate_admission(label, freeze_path):
    frozen = sha(freeze_path)
    for row in read(freeze_path)['direct_inputs']:
        p = Path(row['path'])
        if p.stat().st_size != row['bytes'] or sha(p) != row['sha256']:
            raise ValueError('frozen_cross_scale_task_input_changed/' + str(p))
    if label in ('N1', 'P1'):
        qualification = NS / 'QUALIFICATION.json'
        receipt = read(qualification)
        if receipt['passed'] is not True or receipt['freeze_sha256'] != frozen:
            raise ValueError('independent_paired_qualification_required')
        rows = receipt['slots']
        if [r['label'] for r in rows] != ['QN', 'QP']:
            raise ValueError('two_original_qualification_slots_required')
        for row in rows:
            source = validate_publication(row['label'], frozen)
            if source['status'] != 'completed' or row['result_sha256'] != source['result_sha256']:
                raise ValueError('qualified_slot_result_digest_mismatch/' + row['label'])
        if label == 'P1':
            validate_publication('N1', frozen)
        return {'freeze_sha256': frozen, 'qualification_sha256': sha(qualification)}
    if label == 'QP':
        validate_publication('QN', frozen)
    return {'freeze_sha256': frozen}


def optional_receipt(path):
    return read(path) if path.is_file() else None


def startup_evidence(runtime, folder, result, asset, digest):
    native_dir = folder / 'native'
    copy_path = native_dir / 'input.blend'
    matched = [row['settlement'] for row in (result.get('budget') or {}).get('records', [])
               if row['claim']['kind'] == 'Blender_start' and row['claim']['label'] == result['label']]
    if len(matched) > 1:
        raise ValueError('multiple_startup_settlements_for_original_slot')
    return startup_closure(spawn=optional_receipt(native_dir / 'SPAWN.json'),
        failure=optional_receipt(native_dir / 'START_FAILURE.json'), launch_cleanup=runtime.startup_cleanup,
        settlement=matched[0] if matched else None, asset_matches=asset.is_file() and sha(asset) == digest,
        copy_matches=sha(copy_path) == digest if copy_path.is_file() else None,
        ready=optional_receipt(native_dir / 'READY.json'), startup_entered=runtime.native_start_entered)


def independent_pair(folder, initial, terminal, digest, pid):
    packets = []
    for receipt, directory in ((initial, folder / 'initial_capture'), (terminal, folder)):
        path = directory / 'TERMINAL_SOURCE.json'
        if (receipt['status'] != 'complete' or receipt['terminal'] is not True
                or Path(receipt['path']).resolve() != path.resolve()
                or path.stat().st_size != receipt['bytes'] or sha(path) != receipt['sha256']
                or receipt['worker']['pid'] != pid):
            raise ValueError('independent_current_capture_binding_failed')
        packet = read(path)
        if (packet['source']['pid'] != pid or packet['source']['asset_sha256'] != digest
                or Path(packet['source']['asset_copy']).resolve() != (folder / 'native/input.blend').resolve()):
            raise ValueError('independent_current_source_identity_failed')
        packets.append(packet)
    first, last = packets
    stable = ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'layer_collections', 'scene_cameras')
    if (initial['worker']['file_closed_ns'] >= terminal['worker']['started_ns']
            or any(first[field] != last[field] for field in stable)):
        raise ValueError('independent_before_after_geometry_or_display_changed')
    return {'passed': True, 'initial_sha256': initial['sha256'], 'terminal_sha256': terminal['sha256'],
            'checked': list(stable), 'same_owned_scene': True}


def diagnostic_plan(group):
    expected = {'query': {'mode': 'active_observation', 'region_task': {'area_min_m2': 0.0078125,
                'area_max_m2': 0.03125, 'normal_z_min': 0.75}}, 'include_image': True}
    if group == 'P':
        fixed = read(NS / 'inputs/REQUEST.json')
        if fixed != expected:
            raise ValueError('qualification_product_request_differs_from_plan')
        return [{'name': 'human_eye_scene_observe', 'arguments': fixed}]
    calls = read(NS / 'inputs/DIAGNOSTIC_N.json')['calls']
    if type(calls) is not list or not 1 <= len(calls) <= 12 or any(
            type(row) is not dict or set(row) != {'name', 'arguments'} or type(row['arguments']) is not dict
            or row['name'] == 'human_eye_scene_observe' for row in calls):
        raise ValueError('native_diagnostic_plan_outside_ordinary_tools')
    return calls


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from runtime import transport

    local = folder / 'client'
    calls = diagnostic_plan(group)
    client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'thin_stdio.py'),
          '--endpoint', endpoint, '--audit', str(local / 'attachments')], folder, local / 'transport', deadline)
    try:
        initialize = client.call({'jsonrpc': '2.0', 'id': 'init-diagnostic', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'cross-scale-task-qualification', 'version': '1.0'}}})
        save(local / 'INITIALIZE.json', initialize)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = client.call({'jsonrpc': '2.0', 'id': 'list-diagnostic', 'method': 'tools/list'})
        save(local / 'TOOLS.json', listing)
        if listing['result']['tools'] != owner.tools:
            raise ValueError('diagnostic_tool_schema_differs_from_owner')
        result['diagnostic_ready_ns'] = time.perf_counter_ns()
        for ordinal, item in enumerate(calls, 1):
            tool = local / f'call_{ordinal:02d}'
            tool.mkdir()
            payload = {'jsonrpc': '2.0', 'id': f'diagnostic-{ordinal}', 'method': 'tools/call', 'params': item}
            save(tool / 'REQUEST.json', payload)
            row = {'ordinal': ordinal, 'name': item['name'], 'request_sha256': sha(tool / 'REQUEST.json'),
                   'started_ns': time.perf_counter_ns()}
            result['diagnostic_calls'].append(row)
            response = client.call(payload)
            row['returned_ns'] = time.perf_counter_ns()
            save(tool / 'RESPONSE.json', response)
            save(tool / 'RECEIPT.json', client.records[-1])
            content = response.get('result', {}).get('content', [])
            row.update(response_sha256=sha(tool / 'RESPONSE.json'),
                       text_UTF8_bytes=sum(len(x['text'].encode()) for x in content if x['type'] == 'text'),
                       images=sum(x['type'] == 'image' for x in content),
                       tool_error='error' in response or response.get('result', {}).get('isError') is True)
            if row['tool_error']:
                raise ValueError(f'diagnostic_tool_error_preserved/{ordinal}')
            if row['images']:
                inspection = transport.inspect_images(response, tool / 'delivered')
                row['delivered_PNG_bytes'] = inspection['PNG_bytes']
                row['readback_sha256'] = sha(tool / 'delivered/READBACK.json')
    finally:
        result['diagnostic_close'] = closed = client.finish()
        if not closed['confirmed'] or closed['exit_code'] != 0:
            raise RuntimeError('diagnostic_stdio_close_unconfirmed')


def run(label):
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    owned_deadline = began + 600_000_000_000
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    admission = validate_admission(label, NS / 'FROZEN.json')
    group, phase = SLOTS[label]
    asset, asset_sha = asset_identity()
    folder = EXTERNAL / 'slots' / label
    folder.mkdir(parents=True, exist_ok=False)
    result = {'slot': label, 'label': label, 'group': group, 'phase': phase,
              'status': 'failed', 'errors': [], 'started_ns': began, 'asset_path': str(asset),
              'asset_sha256': asset_sha, 'task_deadline_ns': task_deadline, 'owned_deadline_ns': owned_deadline,
              'actual_model_admitted': False, 'model_consumers': 0, 'paid_API_calls': 0,
              'diagnostic_calls': [], **admission}
    save(folder / 'SLOT_STARTED.json', result)
    runtime = owner = None
    try:
        binding = read(PRODUCT_BINDING)
        shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
        sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
        from runtime import Runtime
        from bridge import Owner

        runtime = Runtime(folder, label, task_deadline, owned_deadline)
        runtime.start()
        result['initial_source'] = runtime.capture_initial()
        output = folder / 'owner'
        owner = Owner(runtime, {'label': label, 'group': group, 'phase': phase,
                      'worker_deadline_ns': task_deadline, 'output': str(output)}, budget=runtime.budget)
        endpoint = owner.start(folder / 'ENDPOINT.json')
        result['ready_ns'] = time.perf_counter_ns()
        import numpy
        import PIL
        import shapely
        result['actual_dependency_modules'] = {m.__name__: {'path': str(Path(m.__file__).resolve()),
                                                'version': m.__version__} for m in (numpy, PIL, shapely)}
        if phase == 'qualification':
            run_diagnostic(folder, endpoint, task_deadline, group, owner, result)
        else:
            from consumer import consume_slot

            runtime.budget.reserve('consumer_task', label, phase)
            result['actual_model_admitted'] = True
            envelope = consume_slot(label, folder, endpoint, output, task_deadline, owned_deadline)
            save(folder / 'CONSUMER_ENVELOPE.json', envelope)
            result['consumer_returned_ns'] = time.perf_counter_ns()
            actual = read(folder / 'consumer/CONSUMER.json')
            result['model_consumers'] = int(bool(actual['image_delivery']['CLI_process_launched']))
            result['consumer'] = {key: actual.get(key) for key in ('status', 'valid_completion', 'final_received_ns',
                'prompt_submitted_ns', 'raw_usage_events', 'thread_id', 'tool_accounting', 'public_image_count',
                'public_image_bytes', 'bridge_public_text_bytes', 'errors', 'exit_code', 'runtime_exit',
                'process_reaped', 'readers_stopped')}
            if not actual.get('valid_completion') or result['consumer_returned_ns'] >= task_deadline:
                raise RuntimeError('formal_consumer_completion_or_original_deadline_failed')
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'consumer' if phase == 'formal' else 'qualification',
                                 'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['cleanup_started_ns'] = time.perf_counter_ns()

        def capture(stage, action):
            try:
                return action()
            except BaseException as error:
                result['status'] = 'failed'
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if owner is not None:
            closed = capture('owner_close', owner.close)
            result['owner_close'] = closed
            if closed is not None and (not closed.get('confirmed') or closed.get('errors') or closed.get('transport_errors')):
                result['status'] = 'failed'
                result['errors'].append({'stage': 'owner_close', 'detail': closed})
        if runtime is not None:
            if runtime.device is not None:
                result['terminal_source'] = capture('terminal_export', runtime.device.export_terminal)
            closure = capture('runtime_close', lambda: runtime.close(result['status']))
            result['budget'] = capture('budget_snapshot', runtime.budget.snapshot)
            if runtime.native is None:
                result['closure_verification'] = startup = capture(
                    'startup_closure_verification', lambda: startup_evidence(runtime, folder, result, asset, asset_sha))
                if startup is not None and startup['passed'] is False:
                    result['errors'].append({'stage': 'startup_cleanup', 'detail': startup['status']})
            elif closure is not None:
                result['closure_verification'] = checked = capture('closure_verification', lambda: ready_closure(
                    closure, group, optional_receipt(folder / 'NATIVE_RUNTIME_PROOF.json'),
                    require_mcp=runtime.client is not None or runtime.mcp_handle is not None))
                if checked and result.get('initial_source') and result.get('terminal_source'):
                    result['independent_before_after'] = capture('independent_before_after', lambda: independent_pair(
                        folder, result['initial_source'], result['terminal_source'], asset_sha, checked['pid']))
                elif result['status'] == 'completed':
                    result['status'] = 'failed'
                    result['errors'].append({'stage': 'independent_before_after',
                                             'message': 'required_current_before_after_captures_unavailable'})
        answer = folder / 'consumer/PUBLIC_FINAL.txt'
        if answer.is_file():
            result['answer'] = {'path': str(answer), 'sha256': sha(answer), 'bytes': answer.stat().st_size}
        actual_start = folder / 'consumer/CONSUMER.json'
        if phase == 'formal' and actual_start.is_file():
            result['model_consumers'] = int(read(actual_start).get('image_delivery', {}).get('CLI_process_launched') is True)
        result['closed_ns'] = time.perf_counter_ns()
        if result['closed_ns'] >= owned_deadline or sha(asset) != asset_sha:
            result['status'] = 'failed'
            result['errors'].append({'stage': 'publication', 'message': 'owned_deadline_or_original_asset_identity_failed'})
        save(folder / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        status = result['status'] if published < owned_deadline else 'failed'
        save(folder / 'SLOT_PUBLICATION.json', {'label': label, 'slot': label, 'status': status, 'started_ns': began,
             'published_ns': published, 'complete_slot_ns': published - began, 'owned_budget_passed': published < owned_deadline,
             'result_sha256': sha(folder / 'SLOT_RESULT.json')})
    print(label, status, round((published - began) / 1e9, 3), 'seconds', [error['stage'] for error in result['errors']])
    return 0 if status == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=tuple(SLOTS))
    raise SystemExit(run(parser.parse_args().slot))
