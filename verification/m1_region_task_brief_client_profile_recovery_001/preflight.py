"""Preflight the retained assembly and both real budget boundaries without a model."""

from contextlib import ExitStack
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'm1_region_task_brief_client_profile_001'
FRAME_DEVICE = HERE.parent / 'm4_dense_panel_sweep_formal_001/frame_device.py'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def reproduce_old(probe):
    """Invoke the historical ReplayRuntime in a clean interpreter and a new path."""
    old = run_path(str(PREVIOUS / 'trial.py'))
    sys.path[:0] = [old['BINDING']['dependency_root'], old['SHARED']['dependency_root']]
    require(not probe.exists(), 'reproduction_path_must_be_unused')
    try:
        old['ReplayRuntime'](probe, 'QA', None, 'P3', time.perf_counter_ns() + 30_000_000_000)
    except ImportError as error:
        detail = traceback.format_exc()
        require("cannot import name 'SOURCE_REGION' from 'bridge'" in str(error)
                and str(PREVIOUS / 'harness/bridge.py') in str(error)
                and str(FRAME_DEVICE) in detail and not probe.exists(),
                'different_historical_import_failure')
        print(json.dumps({'reproduced': True, 'error_type': type(error).__name__,
                          'error': str(error), 'traceback': detail, 'probe_path_created': False},
                         ensure_ascii=True))
    else:
        raise ValueError('historical_import_unexpectedly_succeeded')


def worker_evidence(root, side, expected):
    stock_root = root / ('stock_' + side)
    eof = json.loads((stock_root / 'worker/EOF.json').read_bytes())
    closed = json.loads((stock_root / 'STOCK_CLOSE.json').read_bytes())
    require(eof['closed'] and eof['observe_dispatches'] == expected
            and eof['host_attempts'] == eof['new_rasters'] == 0
            and closed['confirmed'] and closed['exit_code'] == 0,
            'actual_preflight_worker_eof_or_dispatch_changed/' + side)
    outer = json.loads((root / side / 'direct/OUTER_CLOSE.json').read_bytes())
    owner = json.loads((root / side / 'OWNER_CLOSE.json').read_bytes())
    audit, = (root / side / 'direct/attachments').glob('bridge_*')
    thin = json.loads((audit / 'EXIT.json').read_bytes())
    require(outer['confirmed'] and outer['exit_code'] == 0 and thin['normal_exit'] is True
            and owner['confirmed'] and not owner['errors'] and not owner['transport_errors'],
            'actual_preflight_outer_or_owner_close_unconfirmed/' + side)
    return {'stock': closed, 'worker_eof': {'closed': eof['closed'],
            'observe_dispatches': eof['observe_dispatches'], 'host_attempts': eof['host_attempts'],
            'new_rasters': eof['new_rasters']}, 'owner': owner, 'outer_stdio': outer, 'thin': thin}


def record_frames(runtime):
    frames = runtime.originals
    refs = {frame['ref'] for frame in frames}
    original_scene = [frame for frame in frames if frame['view_name'] == 'SCENE']
    require(len(refs) == len(frames) == 3 and refs == set(runtime.device.by_ref)
            and len(original_scene) == 2 and len({frame['scope_id'] for frame in original_scene}) == 2
            and len({frame['frame_identity'] for frame in original_scene}) == 2,
            'actual_preflight_frame_cache_scope_or_identity_changed')
    require(all(callable(method) for method in (runtime.image_specification, runtime.device.image_specification,
                                                runtime.public_request)),
            'actual_preflight_runtime_ordinary_readout_missing')
    return [{'view': row['view_name'], **{key: row[key] for key in ('ref', 'scope_id', 'frame_identity', 'PNG_sha256')}}
            for row in frames]


def run_preflight():
    sys.path.insert(0, str(HERE))
    import trial
    from product_replay import requests

    sys.path[:0] = [trial.BINDING['dependency_root'], trial.SHARED['dependency_root']]
    root = trial.EXTERNAL / 'preflight'
    root.mkdir(parents=True, exist_ok=False)
    command = [str(trial.PYTHON), '-IB', str(Path(__file__).resolve()), '--old-import-check', str(root / 'old_probe')]
    process = subprocess.run(command, cwd=HERE, capture_output=True, timeout=45, check=False)
    (root / 'OLD_IMPORT_STDOUT.bin').write_bytes(process.stdout)
    (root / 'OLD_IMPORT_STDERR.bin').write_bytes(process.stderr)
    require(process.returncode == 0 and not process.stderr, 'old_import_reproduction_process_failed')
    previous = json.loads(process.stdout)
    require(previous['reproduced'] is True and not (root / 'old_probe').exists(), 'old_import_reproduction_untrusted')
    trial.save(root / 'OLD_IMPORT.json', {'command': command, 'exit_code': process.returncode, **previous})

    transport = trial.load_retained('_recovery_preflight_actual_stdio', trial.DISPLAY / 'harness/reused/stdio_checks.py')
    deadline = time.perf_counter_ns() + 180_000_000_000
    programme = requests('P3')
    assembled, frames, delivered, counts = {}, {}, {}, {}
    with ExitStack() as stack:
        for side in ('QA', 'QB'):
            channel = stack.enter_context(trial.stock(root / ('stock_' + side), 'P3', transport, deadline))
            owner, runtime, endpoint = stack.enter_context(trial.endpoint(root / side, side, channel, 'P3', deadline))
            assembled[side] = (owner, runtime, endpoint)
            frames[side] = record_frames(runtime)
            require(type(runtime) is trial.ReplayRuntime and type(owner) is trial.Owner,
                    'preflight_must_reuse_the_actual_formal_assembly')
        for side, (owner, runtime, endpoint) in assembled.items():
            delivered[side] = trial.run_outer(transport, root / side, side, owner, runtime, endpoint, programme, deadline)
            counts[side] = len(runtime.public_requests)
        catalog_a, a_cases = delivered['QA']
        catalog_b, b_cases = delivered['QB']
        trial.check_catalogues(catalog_a, catalog_b)
        names = ('source_region_full', 'source_region_no_image', 'source_region_unknown', 'discover_no_image', 'active_other',
                 'discover_brief')
        compatibility = {key: trial.compatible(a_cases[key]['response'], b_cases[key]['response'], key) for key in names}
        require(b_cases['discover_omitted']['response'] == b_cases['discover_brief']['response'],
                'actual_preflight_omitted_brief_differed')
        for key in ('explicit_full_rejected', 'explicit_null_rejected'):
            row = b_cases[key]
            require(row['response']['isError'] and not row['product_dispatched'] and row['owner']['status'] == 'tool_error'
                    and row['owner']['client_profile']['accepted'] is False,
                    'actual_preflight_profile_rejection_not_owned/' + key)
        require(not b_cases['discover_brief']['response']['isError'] and b_cases['discover_brief']['product_dispatched']
                and not b_cases['common_tool_retained']['response']['isError'], 'actual_preflight_did_not_recover')
        require(b_cases['outer_budget_rejected']['owner'] is None and not b_cases['outer_budget_rejected']['product_dispatched'],
                'actual_preflight_thin_budget_crossed_owner')
        owner, runtime, endpoint = assembled['QB']
        owner_budget = trial.owner_budget(root / 'QB', owner, runtime, endpoint, programme['discover_brief'])
        require(len(runtime.public_requests) == counts['QB'], 'direct_owner_boundary_dispatched_product')
    closing = {side: worker_evidence(root, side, counts[side]) for side in ('QA', 'QB')}
    proof = {'passed': True, 'old_import_failed_at_expected_symbol': True,
             'same_formal_stock_assembly': True, 'same_formal_owner_and_real_thin': True,
             'registered_images': frames, 'compatibility': compatibility,
             'business_thin_attempts': {side: len(data[1]) for side, data in delivered.items()},
             'product_dispatches': counts, 'owner_budget': owner_budget,
             'thin_budget_rejected_before_owner': True, 'closing': closing,
             'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_starts': 0, 'extra_API_calls': 0}
    trial.save(root / 'PREFLIGHT.json', proof)
    print(json.dumps({'passed': True, 'preflight': str(root / 'PREFLIGHT.json'),
                      'attempts': proof['business_thin_attempts'], 'dispatches': counts}, ensure_ascii=True))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    if len(sys.argv) == 3 and sys.argv[1] == '--old-import-check':
        reproduce_old(Path(sys.argv[2]).resolve(strict=False))
    elif len(sys.argv) == 1:
        run_preflight()
    else:
        raise ValueError('unexpected_preflight_arguments')
