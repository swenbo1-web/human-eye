"""Verify the fresh B route and raw archive with no Blender or model work."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission
import batch
from budget import Budget, LIMITS
from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, GLOBAL, NS, ORDER, PRODUCT_BINDING, PRODUCT_SCHEMA,
                    RASTER, REQUESTS, ROOT, SEAL, asset_identity, load_retained, read, save, sha)
from run_slot import previous as slot_runner


ARCHIVED_RUN = Path('D:/he_m5_global_observe_measure_qualification_001')
ARCHIVE_SHA = '8d584ee6444fc46f7d2756057178ff8bee0bf13e2902c37e43d2772e8e91cfdd'
prior = load_retained('_m5_projection_preflight_source', GLOBAL / 'harness/preflight.py')
require, rejected = prior.require, prior.rejected


def load_wire():
    directory = GLOBAL / 'checks'
    saved = sys.path[:]
    try:
        sys.path.insert(0, str(directory))
        return load_retained('_m5_projection_wire_source', directory / 'live_wire.py')
    finally:
        sys.path[:] = saved


def current_asset(result):
    asset, digest = asset_identity()
    require(Path(result['asset_path']).resolve() == asset and result['asset_sha256'] == digest,
            'archived_result_did_not_use_registered_asset')
    return digest


def verify_archive(pins):
    slot = ARCHIVED_RUN / 'slots/B'
    wire = load_wire()
    index = GLOBAL / 'RUNTIME_INDEX.json'
    bound, _ = wire.frozen_archive(index, ARCHIVED_RUN, ARCHIVE_SHA)
    pins.update((index, ARCHIVED_RUN / 'ORIGINAL_RUNTIME.zip', GLOBAL / 'checks/live_wire.py',
                 GLOBAL / 'checks/live_observation.py'))
    def updated(path):
        pins.add(path)
        return bound(path)

    result_path = slot / 'SLOT_RESULT.json'
    result = json.loads(updated(result_path))
    receipt = json.loads(updated(slot / 'SLOT_PUBLICATION.json'))
    require(result['status'] == receipt['status'] == 'completed' and not result['errors']
            and receipt['result_sha256'] == sha(result_path) and result['label'] == receipt['label'] == 'B'
            and result['model_consumers'] == result['paid_API_calls'] == 0,
            'archived_B_did_not_complete_or_mismatches_result')
    require(read(RASTER / 'install/PRODUCT_RUN_BINDING.json')['source_sha256'] == result['product_source_sha256'],
            'archived_B_used_unexpected_baseline')
    digest = current_asset(result)
    rejected(lambda: current_asset({**result, 'asset_path': str(slot / 'native/input.blend')}),
             'archived_result_did_not_use_registered_asset')
    require(sha(slot / 'native/input.blend') == digest and sha(ASSET) == ASSET_SHA256,
            'actual_asset_or_owned_copy_file_changed')
    for relative in ('native/input.blend', 'initial_capture/TERMINAL_SOURCE.json', 'TERMINAL_SOURCE.json',
                     'SLOT_STARTED.json', 'NATIVE_RUNTIME_PROOF.json'):
        updated(slot / relative)
    match_source, closure = slot_runner.prepare_runner()
    close = closure.ready_closure(json.loads(updated(slot / 'RUNTIME_CLOSE.json')), 'P',
        read(slot / 'NATIVE_RUNTIME_PROOF.json'), require_mcp=True)
    require(close == result['closure_verification'] and close['passed'] is True and
            match_source(slot, result['initial_source'], result['terminal_source'], digest, close['pid'])
            == result['independent_before_after'], 'archived_source_pair_or_process_closure_changed')
    (event,) = [json.loads(line) for line in updated(slot / 'PUBLIC_REQUESTS.jsonl').splitlines()]
    (meter,) = [value for line in updated(slot / 'mcp_io/MCP_IO.jsonl').splitlines()
                if (value := json.loads(line)).get('method') == 'tools/call']
    original = wire.raw_wire(slot, event, meter, read(REQUESTS['JOINT']), updated)
    require(event['index'] == 1 and result['business_calls'][0]['producer_archive_index'] == 1
            and len(result['business_calls']) == 1
            and 'actual_TX_path' not in event and 'actual_RX_path' not in event,
            'archive_receipt_shape_not_original_indexed_wire')
    rejected(lambda: wire.raw_wire(slot, event, {**meter, 'TX_sha256': '0' * 64},
                                  read(REQUESTS['JOINT'])), 'raw_client_and_server_wires_or_raster_accounting_mismatch')
    for frame in original['producer']['constructed_frames']:
        for field, key in (('image_path', 'image_sha256'), ('arrays_path', 'arrays_sha256')):
            frame_path = Path(frame[field])
            require(sha256(updated(frame_path)).hexdigest() == frame[key], 'archived_B_original_frame_changed')
    outer = slot / 'batch/rpc_03'
    tx, rx = (updated(outer / name) for name in ('TCP_TX.bin', 'TCP_RX.bin'))
    outer_receipt = json.loads(updated(outer / 'RECEIPT.json'))
    manifest = json.loads(updated(slot / 'batch/QUALIFICATION_BATCH.json'))
    require(json.loads(tx)['args']['message'] == batch.outer_message('B')
            and json.loads(rx)['result'] == outer_receipt['response']
            and manifest == result['outer_batch']
            and tuple(sha256(raw).hexdigest() for raw in (tx, rx))
                == (outer_receipt['TX_sha256'], outer_receipt['RX_sha256']),
            'archived_actual_outer_packet_changed')
    replay = {'prior_public_count': 1, 'prior_outer_count': 1, 'prior_frame_count': len(original['producer']['constructed_frames']),
              'original_asset': str(ASSET.resolve()), 'original_asset_sha256': digest, 'archive_sha256': ARCHIVE_SHA,
              'original_receipt_index': event['receipt']['index'], 'public_wire': original['wire'],
              'archived_result_sha256': receipt['result_sha256'], 'actual_closure': close}
    return original['result'], outer_receipt['response'], replay


def verify_entrypoints():
    entries = [(NS / 'run_sequence.py', []), (HERE / 'run_slot.py', ['B']), (HERE / 'mcp_entry.py', [])]
    outputs = []
    for entry, args in entries:
        argv = [sys.executable, '-I', '-B', str(entry), *args, '--dispatch-smoke']
        output = json.loads(subprocess.check_output(argv, cwd=ROOT, timeout=20))
        require(Path(output['entry']).resolve() == entry.resolve()
                and Path(output['admission']).resolve() == (HERE / 'admission.py').resolve()
                and output['schema'] == admission.SCHEMA and output['fresh_process_prepared_only'] is True,
                'fresh_process_dispatch_bound_to_other_experiment')
        if 'run_root' in output:
            require(Path(output['run_root']).resolve() == EXTERNAL.resolve(), 'fresh_process_changed_run_root')
        if 'current_binding' in output:
            require(Path(output['current_binding']).resolve() == PRODUCT_BINDING.resolve(),
                    'fresh_process_changed_product_binding')
        if args:
            require(output['wrapper'] == batch.outer_message('B') and Path(output['mcp_entry']).resolve() ==
                    (HERE / 'mcp_entry.py').resolve(), 'fresh_slot_dispatch_changed')
        outputs.append(output)
    return outputs


def verify_budget(tmp):
    budget = Budget(tmp / 'test_budget')
    launch = budget.reserve('Blender_start', 'B', 'qualification', 1)
    budget.settle_start(launch, pid=None, spawn_status='not_spawned', outcome='offline_budget_control')
    rejected(lambda: budget.reserve('Blender_start', 'B', 'qualification', 1), 'registered_slot_already_admitted')
    budget.admit_business('B', 'qualification')
    rejected(lambda: budget.admit_business('B', 'qualification'), 'business_tool_budget_exhausted')
    for _ in range(LIMITS['all_rasters']):
        budget.reserve('raster_attempt', 'B', 'qualification', 1)
    rejected(lambda: budget.reserve('raster_attempt', 'B', 'qualification', 1), 'raster_budget_exhausted')
    rejected(lambda: budget.reserve('consumer_task', 'B', 'qualification', 1), 'qualification_model_consumer_forbidden')
    return {'test_only': True, 'actual_owned_starts': 0, 'actual_rasters': 0, 'actual_models': 0,
            'business_cap': 1, 'raster_cap': LIMITS['all_rasters']}


def verify_product_schema(pins):
    installed = read(PRODUCT_BINDING)
    shared = SEAL / 'SHARED_DEPENDENCY.json'
    bootstrap = SEAL / 'harness/reused/verified_bootstrap.py'
    # Match the actual slot's dependency order for both the schema and outer bridge.
    sys.path[:0] = [installed['dependency_root'], read(shared)['dependency_root']]
    load_retained('_m5_projection_install_check', bootstrap).bootstrap(installed)
    from human_eye_plugin.live_spatial_mcp import _validate_arguments
    _validate_arguments('human_eye_scene_observe', read(REQUESTS['JOINT']))
    baseline = RASTER / 'install'
    require(read(PRODUCT_SCHEMA) == read(baseline / PRODUCT_SCHEMA.name)
            and read(CATALOGUE) == read(baseline / CATALOGUE.name), 'candidate_tool_schema_drift')
    pins.update((shared, bootstrap, baseline / PRODUCT_SCHEMA.name, baseline / CATALOGUE.name,
                 baseline / PRODUCT_BINDING.name))


def main():
    trial_paths = [EXTERNAL / name for name in ('slots', 'budget', 'preflight')]
    require(sys.flags.isolated and sys.dont_write_bytecode and not any(path.exists() for path in trial_paths),
            'fresh_isolated_preflight_required')
    retained = GLOBAL / 'harness'
    pins = {PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, ASSET, NS / 'run_sequence.py',
            GLOBAL / 'run_sequence.py', GLOBAL / 'FROZEN.json',
            *REQUESTS.values(), *HERE.glob('*.py'), *retained.glob('*.py')}
    entries = verify_entrypoints()
    verify_product_schema(pins)
    archives, _ = prior.check_archives(pins)
    public, old_outer, replay = verify_archive(pins)
    with TemporaryDirectory(prefix='m5-projection-preflight-') as directory:
        tmp = Path(directory)
        loopback = prior.verify_outer(tmp, {('recovered', 5): public})
        replayed = read(tmp / 'B/batch/rpc_03/RECEIPT.json')['response']
        require(replayed == old_outer, 'loopback_did_not_preserve_original_B_qualification_payload')
        ledger = verify_budget(tmp)
    require(not any(path.exists() for path in trial_paths), 'preflight_changed_frozen_run_root')
    save(HERE / 'DISPATCH_PREFLIGHT.json', {'passed': True, 'limits': LIMITS, 'slot_order': list(ORDER),
         'actual_Blender_processes': 0, 'actual_raster_attempts': 0, 'actual_model_runs': 0,
         'actual_product_schema_validation': True, 'fresh_entrypoints': entries, 'outer_archived_loopback': loopback,
         'ledger_rejection_control': ledger, 'archived_protocol': archives, 'actual_prior_B_replay': replay,
         'source_pins': [{'path': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size}
                         for p in sorted({p.resolve() for p in pins}, key=str)]})
    print('Dispatch preflight passed', sha(HERE / 'DISPATCH_PREFLIGHT.json'), len(pins))


if __name__ == '__main__':
    main()
