"""Run the frozen cold brief and no-image prediction in one exclusive Blender copy."""

import argparse
from pathlib import Path
import sys
import time
import traceback


sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from admission import admit
from common import BINDINGS, EXTERNAL, FORMAL, NS, ORDER, asset_identity, load, read, save, sha


def optional(path):
    return read(path) if path.is_file() else None


def match_source(folder, initial, terminal, digest, pid):
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
    fields = ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'layer_collections', 'scene_cameras')
    if (initial['worker']['file_closed_ns'] >= terminal['worker']['started_ns']
            or any(first[field] != last[field] for field in fields)):
        raise ValueError('independent_before_after_geometry_or_display_changed')
    return {'passed': True, 'initial_sha256': initial['sha256'], 'terminal_sha256': terminal['sha256'],
            'checked': list(fields), 'same_owned_scene': True}


def run(label):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    checked = time.perf_counter_ns()
    freeze, arm, binding = admit(label)
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    owned_deadline = began + 600_000_000_000
    asset, asset_sha = asset_identity()
    folder = EXTERNAL / 'slots' / label
    folder.mkdir(parents=True, exist_ok=False)
    product_source = binding['source_sha256']
    result = {'slot': label, 'label': label, 'group': 'P', 'phase': 'formal', 'arm': arm,
              'status': 'failed', 'errors': [], 'started_ns': began, 'asset_path': str(asset),
              'asset_sha256': asset_sha, 'task_deadline_ns': task_deadline, 'owned_deadline_ns': owned_deadline,
              'admission_verification_ns': began - checked, 'freeze_sha256': freeze,
              'product_source_sha256': product_source, 'product_binding_sha256': sha(BINDINGS[arm]),
              'model_consumers': 0, 'paid_API_calls': 0, 'business_calls': []}
    save(folder / 'SLOT_STARTED.json', result)
    common.PRODUCT_BINDING, common.SOURCE_SHA = BINDINGS[arm], product_source
    shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(FORMAL), binding['dependency_root'], shared['dependency_root']]
    runtime = None
    closure_module = load('_local_first_retained_slot_closure', FORMAL / 'harness/closure.py')
    try:
        runtime_module = load('_local_first_retained_owned_runtime', FORMAL / 'harness/runtime.py')
        runtime = runtime_module.Runtime(folder, label, task_deadline, owned_deadline)
        runtime.start()
        result['initial_source'] = runtime.capture_initial()
        if runtime.product_tools != read(NS / 'install/TOOLS_SCHEMA.json'):
            raise ValueError('actual_tools_catalogue_differs_from_both_bound_arms')
        result['ready_ns'] = time.perf_counter_ns()
        for kind, filename in (('cold', 'REQUEST.json'), ('prediction', 'PREDICTION.json')):
            request_path = NS / 'inputs' / filename
            arguments = read(request_path)
            claim = runtime.budget.admit_business(label)
            started = time.perf_counter_ns()
            row = {'kind': kind, 'claim': claim, 'started_ns': started, 'arguments_sha256': sha(request_path)}
            result['business_calls'].append(row)
            try:
                response = runtime.public_request(arguments)
                if 'error' in response or response['result']['isError'] is not False:
                    raise ValueError('installed_region_task_did_not_return_success')
                row['status'] = 'completed'
            finally:
                row['closed_ns'] = time.perf_counter_ns()
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'installed_region_requests', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['cleanup_started_ns'] = time.perf_counter_ns()

        def capture(stage, action):
            try:
                return action()
            except BaseException as error:
                result['status'] = 'failed'
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if runtime is not None:
            if runtime.device is not None:
                result['terminal_source'] = capture('terminal_export', runtime.device.export_terminal)
            closure = capture('runtime_close', lambda: runtime.close(result['status']))
            result['budget'] = capture('budget_snapshot', runtime.budget.snapshot)
            if runtime.native is None:
                native = folder / 'native'
                owned = [row['settlement'] for row in (result.get('budget') or {}).get('records', [])
                         if row['claim']['kind'] == 'Blender_start' and row['claim']['label'] == label]
                copy_path = native / 'input.blend'
                result['closure_verification'] = capture('startup_closure_verification',
                    lambda: closure_module.startup_closure(spawn=optional(native / 'SPAWN.json'),
                        failure=optional(native / 'START_FAILURE.json'), launch_cleanup=runtime.startup_cleanup,
                        settlement=owned[0] if owned else None, asset_matches=sha(asset) == asset_sha,
                        copy_matches=sha(copy_path) == asset_sha if copy_path.is_file() else None,
                        ready=optional(native / 'READY.json'), startup_entered=runtime.native_start_entered))
            elif closure is not None:
                verified = capture('closure_verification', lambda: closure_module.ready_closure(
                    closure, 'P', optional(folder / 'NATIVE_RUNTIME_PROOF.json'),
                    require_mcp=runtime.client is not None or runtime.mcp_handle is not None))
                result['closure_verification'] = verified
                if verified and result.get('initial_source') and result.get('terminal_source'):
                    result['independent_before_after'] = capture('independent_before_after', lambda: match_source(
                        folder, result['initial_source'], result['terminal_source'], asset_sha, verified['pid']))
                elif result['status'] == 'completed':
                    result['status'] = 'failed'
                    result['errors'].append({'stage': 'independent_before_after', 'type': 'missing_current_pair'})
        result['closed_ns'] = time.perf_counter_ns()
        if result['closed_ns'] >= owned_deadline or sha(asset) != asset_sha:
            result['status'] = 'failed'
            result['errors'].append({'stage': 'publication', 'type': 'original_asset_or_owned_deadline_failed'})
        save(folder / 'SLOT_RESULT.json', result)
        published = time.perf_counter_ns()
        status = result['status'] if published < owned_deadline else 'failed'
        save(folder / 'SLOT_PUBLICATION.json', {'label': label, 'slot': label, 'status': status,
             'started_ns': began, 'published_ns': published, 'complete_slot_ns': published - began,
             'owned_budget_passed': published < owned_deadline, 'result_sha256': sha(folder / 'SLOT_RESULT.json')})
    print(label, status, round((published - began) / 1e9, 3), 'seconds',
          [error['stage'] for error in result['errors']])
    return 0 if status == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    raise SystemExit(run(parser.parse_args().slot))
