"""Open the registered QP slot with one unmodified installed brief request."""

import argparse
from pathlib import Path
import sys
import time
import traceback


sys.path.insert(0, str(Path(__file__).resolve().parent))
from admission import CATALOGUE, admit
from common import EXTERNAL, FORMAL, NS, ORDER, PRODUCT_BINDING, SLOTS, asset_identity, load, read, save, sha


def optional(path):
    return read(path) if path.is_file() else None


def match_source(folder, initial, terminal, asset_sha, pid):
    packets = []
    for receipt, directory in ((initial, folder / 'initial_capture'), (terminal, folder)):
        path = directory / 'TERMINAL_SOURCE.json'
        if (receipt['status'] != 'complete' or receipt['terminal'] is not True
                or Path(receipt['path']).resolve() != path.resolve()
                or path.stat().st_size != receipt['bytes'] or sha(path) != receipt['sha256']
                or receipt['worker']['pid'] != pid):
            raise ValueError('independent_current_capture_binding_failed')
        packet = read(path)
        if (packet['source']['pid'] != pid or packet['source']['asset_sha256'] != asset_sha
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


def startup_verification(closure, runtime, folder, result, asset, asset_sha):
    native = folder / 'native'
    settlements = [row['settlement'] for row in (result.get('budget') or {}).get('records', [])
                   if row['claim']['kind'] == 'Blender_start' and row['claim']['label'] == result['label']]
    if len(settlements) > 1:
        raise ValueError('multiple_startup_settlements_for_original_slot')
    copy_path = native / 'input.blend'
    return closure.startup_closure(
        spawn=optional(native / 'SPAWN.json'), failure=optional(native / 'START_FAILURE.json'),
        launch_cleanup=runtime.startup_cleanup, settlement=settlements[0] if settlements else None,
        asset_matches=sha(asset) == asset_sha,
        copy_matches=sha(copy_path) == asset_sha if copy_path.is_file() else None,
        ready=optional(native / 'READY.json'), startup_entered=runtime.native_start_entered)


def run(label):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    checked = time.perf_counter_ns()
    frozen, binding = admit(label)
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    owned_deadline = began + 600_000_000_000
    asset, asset_sha = asset_identity()
    group, phase = SLOTS[label]
    folder = EXTERNAL / 'slots' / label
    folder.mkdir(parents=True, exist_ok=False)
    result = {
        'slot': label, 'label': label, 'group': group, 'phase': phase, 'arm': group,
        'status': 'failed', 'errors': [], 'started_ns': began, 'asset_path': str(asset),
        'asset_sha256': asset_sha, 'task_deadline_ns': task_deadline, 'owned_deadline_ns': owned_deadline,
        'admission_verification_ns': began - checked, 'freeze_sha256': frozen,
        'product_source_sha256': binding['source_sha256'], 'product_binding_sha256': sha(PRODUCT_BINDING),
        'actual_model_admitted': False, 'model_consumers': 0, 'paid_API_calls': 0, 'business_calls': [],
    }
    save(folder / 'SLOT_STARTED.json', result)
    runtime = None
    try:
        shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
        sys.path[:0] = [str(FORMAL), binding['dependency_root'], shared['dependency_root']]
        closure = load('_dense_panel_slot_closure', FORMAL / 'harness/closure.py')
        runtime_module = load('_dense_panel_owned_runtime', FORMAL / 'harness/runtime.py')
        runtime = runtime_module.Runtime(folder, label, task_deadline, owned_deadline)
        runtime.start()
        if len(runtime.product_tools) != 5 or runtime.product_tools != read(CATALOGUE):
            raise ValueError('actual_installed_tool_catalogue_changed')
        result['initial_source'] = runtime.capture_initial()
        result['ready_ns'] = time.perf_counter_ns()

        path = NS / 'inputs/REQUEST.json'
        arguments = read(path)
        claim = runtime.budget.admit_business(label, phase)
        call = {'kind': 'cold', 'claim': claim, 'started_ns': time.perf_counter_ns(),
                'arguments_sha256': sha(path), 'status': 'failed'}
        result['business_calls'].append(call)
        try:
            response = runtime.public_request(arguments)
            if 'error' in response or response.get('result', {}).get('isError') is not False:
                raise ValueError('installed_region_task_did_not_return_success')
            call['status'] = 'completed'
        finally:
            call['closed_ns'] = time.perf_counter_ns()
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'installed_region_request', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['cleanup_started_ns'] = time.perf_counter_ns()

        def capture(stage, operation):
            try:
                return operation()
            except BaseException as error:
                result['status'] = 'failed'
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if runtime is not None:
            if runtime.device is not None:
                result['terminal_source'] = capture('terminal_export', runtime.device.export_terminal)
            closed = capture('runtime_close', lambda: runtime.close(result['status']))
            result['budget'] = capture('budget_snapshot', runtime.budget.snapshot)
            if runtime.native is None:
                result['closure_verification'] = capture('startup_closure_verification',
                    lambda: startup_verification(closure, runtime, folder, result, asset, asset_sha))
            elif closed is not None:
                verified = capture('closure_verification', lambda: closure.ready_closure(
                    closed, group, optional(folder / 'NATIVE_RUNTIME_PROOF.json'),
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
    parser.add_argument('slot', choices=(ORDER[0],))
    raise SystemExit(run(parser.parse_args().slot))
