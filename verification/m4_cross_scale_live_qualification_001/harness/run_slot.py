"""Run the one registered owned Blender probe with a no-model diagnostic client."""

import argparse
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge import ARGUMENTS, Owner, PRODUCT_TOOL
from common import ASSET, ASSET_SHA, GLOBAL, HERE, NS, SCHEMA, SLOT, load, read, save, sha
from runtime import Runtime, initialize, proof, transport


def reply(client, call, ordinal):
    output = SLOT / 'client' / f'call_{ordinal:02d}'
    output.mkdir(parents=True, exist_ok=False)
    rpc = {'jsonrpc': '2.0', 'id': f'diagnostic-{ordinal}', 'method': 'tools/call',
           'params': {'name': PRODUCT_TOOL, 'arguments': call}}
    save(output / 'REQUEST.json', rpc)
    before = time.perf_counter_ns()
    received = client.call(rpc)
    returned = time.perf_counter_ns()
    save(output / 'RESPONSE.json', received)
    save(output / 'RECEIPT.json', client.records[-1])
    return output, received, {'ordinal': ordinal, 'started_ns': before, 'returned_ns': returned,
                             'RPC_id': rpc['id'], 'response_sha256': sha(output / 'RESPONSE.json')}


def restore_handle(runtime, cleanup):
    if runtime.native_handle is None:
        return
    try:
        exited = proof._runtime_exit(runtime.native_handle)
        process = runtime.native.process
        if process.poll() is not None:
            process._handle.Close()
        exited['Popen_handle_closed'] = bool(process._handle.closed)
        cleanup['native_retained_exit'] = exited
    finally:
        runtime.native_handle = None


def run():
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('fixed_isolated_interpreter_required')
    freeze = read(NS / 'FROZEN.json')
    for row in freeze['direct_inputs']:
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('frozen_cross_scale_input_changed/' + str(path))
    arguments = read(NS / 'inputs/REQUEST.json')
    if arguments != ARGUMENTS:
        raise ValueError('exact_frozen_active_observation_request_required')
    SLOT.mkdir(parents=True, exist_ok=False)
    clocks = {'slot_started_ns': started, 'owned_deadline_ns': deadline}
    result = {'label': 'Q1', 'status': 'failed', 'clocks': clocks, 'cleanup': {}, 'errors': [],
              'source': None, 'calls': [], 'public_requests_attempted': 0, 'model_consumers': 0,
              'paid_API_calls': 0, 'freeze_sha256': sha(NS / 'FROZEN.json')}
    save(SLOT / 'SLOT_STARTED.json', result)
    runtime = owner = client = None
    previous_driver = load('_cross_scale_previous_global_driver', GLOBAL / 'harness/run_slot.py')
    try:
        runtime = Runtime(deadline)
        runtime.start()
        clocks['runtime_ready_ns'] = time.perf_counter_ns()
        independent = runtime.scene_data()
        save(SLOT / 'INDEPENDENT_SCENE.json', independent)
        previous_driver.validate_source(independent, read(GLOBAL / 'fixture/GEOMETRY.json'))
        clocks['independent_scene_checked_ns'] = time.perf_counter_ns()
        objects = independent['objects']
        result['source'] = {'path': str(SLOT / 'INDEPENDENT_SCENE.json'), 'source_ref': independent['source_ref'],
                            'asset_sha256': ASSET_SHA, 'objects': len(objects),
                            'vertices': sum(len(mesh['vertices']) for mesh in objects),
                            'triangles': sum(len(mesh['triangles']) for mesh in objects)}
        owner = Owner(runtime, {'label': 'Q1', 'phase': 'qualification', 'worker_deadline_ns': deadline,
                                'output': str(SLOT / 'owner')}, budget=runtime.budget)
        endpoint = owner.start(SLOT / 'ENDPOINT.json')
        client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'thin_stdio.py'),
            '--endpoint', endpoint, '--audit', str(SLOT / 'client/attachments')],
            SLOT, SLOT / 'client/transport', deadline)
        initialized = client.call(initialize('init-diagnostic'))
        save(SLOT / 'client/INITIALIZE.json', initialized)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = client.call({'jsonrpc': '2.0', 'id': 'list-diagnostic', 'method': 'tools/list'})
        save(SLOT / 'client/TOOLS.json', tools)
        if tools['result']['tools'] != [read(SCHEMA)]:
            raise ValueError('diagnostic_schema_differs_from_actual_installed_current_tool')
        clocks['diagnostic_ready_ns'] = time.perf_counter_ns()
        for ordinal in (1, 2):
            result['public_requests_attempted'] += 1
            output, response, row = reply(client, arguments, ordinal)
            result['calls'].append(row)
            if response.get('error') is not None or response['result']['isError']:
                raise ValueError(f'actual_public_error_preserved/call_{ordinal:02d}')
            if [block['type'] for block in response['result']['content']] != ['text', 'image', 'image', 'image']:
                raise ValueError(f'actual_missing_text_or_three_PNGs/call_{ordinal:02d}')
            received = transport.inspect_images(response, output / 'delivered')
            row.update({'image_count': received['image_blocks_read'], 'PNG_bytes': received['PNG_bytes'],
                        'readback_sha256': sha(output / 'delivered/READBACK.json')})
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'qualification', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        clocks['cleanup_started_ns'] = time.perf_counter_ns()

        def close(stage, call):
            try:
                outcome = call()
                if outcome is not None:
                    result['cleanup'][stage] = outcome
            except BaseException as error:
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if client is not None:
            close('diagnostic', client.finish)
        if owner is not None:
            close('bridge', owner.close)
        if runtime is not None:
            close('runtime_close', runtime.close)
            close('retained_Blender', lambda: restore_handle(runtime, result['cleanup']))
            close('budget_snapshot', runtime.budget.snapshot)
        cleanup = result['cleanup']
        if result['status'] == 'completed':
            diagnostic, bridge = cleanup.get('diagnostic', {}), cleanup.get('bridge', {})
            if (not diagnostic.get('confirmed') or diagnostic.get('exit_code') != 0
                    or not bridge.get('confirmed') or bridge.get('errors') or bridge.get('transport_errors')
                    or not previous_driver.closure_valid(cleanup.get('runtime_close', {}),
                                                        cleanup.get('native_retained_exit', {}))):
                result['errors'].append({'stage': 'closure', 'message': 'owned_process_or_original_asset_closure_failed'})
            counts = cleanup.get('budget_snapshot', {}).get('counts', {})
            if (counts.get('Blender_start_attempts') != 1 or counts.get('business_admissions') != 2
                    or counts.get('consumer_admissions') != 0 or counts.get('all_raster_upper', 7) > 6):
                result['errors'].append({'stage': 'ledger', 'message': 'original_budget_not_proved'})
        clocks['cleanup_closed_ns'] = time.perf_counter_ns()
        if result['errors'] or clocks['cleanup_closed_ns'] >= deadline or sha(ASSET) != ASSET_SHA:
            result['status'] = 'failed'
        save(SLOT / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        save(SLOT / 'SLOT_PUBLICATION.json', {'label': 'Q1', 'started_ns': started, 'published_ns': published,
             'slot_started_ns': started, 'slot_result_published_ns': published, 'complete_slot_ns': published-started,
             'result_sha256': sha(SLOT / 'SLOT_RESULT.json'), 'owned_budget_passed': published < deadline,
             'status': result['status'] if published < deadline else 'failed'})
    print('Q1', result['status'], [error['stage'] for error in result['errors']])
    return 0 if result['status'] == 'completed' and published < deadline else 1


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(run())
