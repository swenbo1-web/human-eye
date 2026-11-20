"""Execute one admitted and exclusive qualification slot."""

import argparse
import json
from pathlib import Path
import sys
import time
import traceback


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from common import (CATALOGUE, EXTERNAL, FORMAL, NS, ORDER, PIXEL, PRODUCT_BINDING, PRODUCT_GIT, SEAL,
                    SLOTS, asset_identity, load_retained, read, save, sha)


def optional(path):
    return read(path) if path.is_file() else None


def prepare_runner():
    original = load_retained('_m5_global_dense_source_readback', PIXEL / 'harness/run_slot.py')
    if original.admit is not admission.admit or original.EXTERNAL != EXTERNAL:
        raise ValueError('retained_source_readback_must_bind_current_admission')
    closure = load_retained('_m5_global_slot_closure', FORMAL / 'harness/closure.py')
    return original.match_source, closure


def run(label):
    match_source, lifecycle = prepare_runner()
    checked = time.perf_counter_ns()
    freeze, binding = admission.admit(label)
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    owned_deadline = began + 600_000_000_000
    asset, asset_sha = asset_identity()
    folder = EXTERNAL / 'slots' / label
    folder.mkdir(parents=True, exist_ok=False)
    group, phase = SLOTS[label]
    result = {'slot': label, 'label': label, 'group': group, 'phase': phase, 'arm': label,
              'status': 'failed', 'errors': [], 'started_ns': began, 'asset_path': str(asset),
              'asset_sha256': asset_sha, 'task_deadline_ns': task_deadline, 'owned_deadline_ns': owned_deadline,
              'admission_verification_ns': began - checked, 'freeze_sha256': freeze,
              'product_git': PRODUCT_GIT, 'product_source_sha256': binding['source_sha256'],
              'product_binding_sha256': sha(PRODUCT_BINDING), 'model_consumers': 0, 'paid_API_calls': 0,
              'business_calls': []}
    save(folder / 'SLOT_STARTED.json', result)
    shared = read(SEAL / 'SHARED_DEPENDENCY.json')
    sys.path[1:1] = [str(FORMAL), binding['dependency_root'], shared['dependency_root']]
    runtime = owner = None
    try:
        import batch
        import runtime as owned

        runtime = owned.Runtime(folder, label, task_deadline, owned_deadline, result['business_calls'])
        runtime.start()
        result['initial_source'] = runtime.capture_initial()
        if runtime.product_tools != read(CATALOGUE):
            raise ValueError('actual_public_catalogue_changed')
        owner = batch.owner_for(runtime, label, folder, task_deadline)
        endpoint = Path(owner.start(folder / 'ENDPOINT.json'))
        result['ready_ns'] = time.perf_counter_ns()
        result['outer_batch'] = batch.execute(owner, label, folder, read(endpoint), task_deadline)
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'shared_qualification_requests', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['cleanup_started_ns'] = time.perf_counter_ns()

        def capture(stage, action):
            try:
                return action()
            except BaseException as error:
                result['status'] = 'failed'
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if owner is not None:
            result['outer_owner_close'] = capture('outer_owner_close', owner.close)
        if runtime is not None:
            if runtime.device is not None:
                result['terminal_source'] = capture('terminal_export', runtime.device.export_terminal)
            closure = capture('runtime_close', lambda: runtime.close(result['status']))
            result['budget'] = capture('budget_snapshot', runtime.budget.snapshot)
            if runtime.native is None:
                native = folder / 'native'
                starts = [row['settlement'] for row in (result.get('budget') or {}).get('records', [])
                          if row['claim']['kind'] == 'Blender_start' and row['claim']['label'] == label]
                copy_path = native / 'input.blend'
                result['closure_verification'] = capture('startup_closure_verification',
                    lambda: lifecycle.startup_closure(spawn=optional(native / 'SPAWN.json'),
                        failure=optional(native / 'START_FAILURE.json'), launch_cleanup=runtime.startup_cleanup,
                        settlement=starts[0] if starts else None, asset_matches=sha(asset) == asset_sha,
                        copy_matches=sha(copy_path) == asset_sha if copy_path.is_file() else None,
                        ready=optional(native / 'READY.json'), startup_entered=runtime.native_start_entered))
            elif closure is not None:
                verified = capture('closure_verification', lambda: lifecycle.ready_closure(
                    closure, group, optional(folder / 'NATIVE_RUNTIME_PROOF.json'),
                    require_mcp=runtime.client is not None or runtime.mcp_handle is not None))
                result['closure_verification'] = verified
                if verified and result.get('initial_source') and result.get('terminal_source'):
                    result['independent_before_after'] = capture('independent_before_after', lambda: match_source(
                        folder, result['initial_source'], result['terminal_source'], asset_sha, verified['pid']))
                elif result['status'] == 'completed':
                    result['status'] = 'failed'
                    result['errors'].append({'stage': 'independent_before_after', 'type': 'missing_current_pair'})
        if result['status'] == 'completed' and not admission.can_continue(
                result, {'status': 'completed', 'owned_budget_passed': True}):
            result['status'] = 'failed'
            result['errors'].append({'stage': 'lifecycle', 'type': 'required_closure_unconfirmed'})
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
    print(label, status, round((published - began) / 1e9, 3), 'seconds', [error['stage'] for error in result['errors']])
    return 0 if status == 'completed' else 1


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    parser.add_argument('--dispatch-smoke', action='store_true')
    args = parser.parse_args()
    if args.dispatch_smoke:
        prepare_runner()
        shared = read(SEAL / 'SHARED_DEPENDENCY.json')
        binding = read(PRODUCT_BINDING)
        sys.path[1:1] = [str(FORMAL), binding['dependency_root'], shared['dependency_root']]
        import batch
        import runtime as owned

        print(json.dumps({'slot': args.slot, 'entry': str(Path(__file__).resolve()),
              'admission': str(Path(admission.__file__).resolve()), 'schema': admission.SCHEMA,
              'current_binding': str(PRODUCT_BINDING.resolve()), 'run_root': str(EXTERNAL.resolve()),
              'mcp_entry': str(owned.Runtime._start_public_mcp.__globals__['HERE'] / 'mcp_entry.py'),
              'wrapper': batch.outer_message(args.slot), 'fresh_process_prepared_only': True}))
        return 0
    return run(args.slot)


if __name__ == '__main__':
    raise SystemExit(main())
