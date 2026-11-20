"""Prove fresh entry dispatch, original-wire association and quotas without owned launches."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission
import batch
from budget import Budget, LIMITS
from common import (ASSET, CATALOGUE, EXTERNAL, NS, ORDER, PIXEL, PRODUCT_BINDING, PRODUCT_SCHEMA, REQUESTS,
                    ROOT, SEAL, SLOT_REQUESTS, load_retained, read, save, sha)


OLDER = Path('D:/he_m5_harness_recovery_001/sessions/B')
ASSEMBLY = Path('D:/he_m4_cross_scale_pixel_evidence_001/slots/P1')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def rejected(callback, reason):
    try:
        callback()
    except (ValueError, RuntimeError) as error:
        require(str(error).startswith(reason), 'expected_rejection_' + reason + '/' + str(error))
    else:
        raise ValueError('negative_control_not_rejected/' + reason)


def check_archives(pins):
    recover = load_retained('_m5_preflight_recovered_archive', SEAL / 'harness/owned_runtime.py')
    result, bodies, old_rows = {}, {}, []
    for name, slot, wanted in (('recovered', OLDER, (1, 2, 3, 4, 5)), ('assembly', ASSEMBLY, (1,))):
        public_path = slot / 'PUBLIC_REQUESTS.jsonl'
        pins.add(public_path)
        rows = [json.loads(line) for line in public_path.read_bytes().splitlines()]
        indices = []
        for index in wanted:
            row = rows[index - 1]
            call = slot / 'product_calls' / f'call_{index:03d}'
            prefix = slot / 'mcp' / f"rpc_{row['receipt']['index']:02d}"
            paths = [call / f'{key}.json' for key in ('REQUEST', 'RESPONSE')]
            paths.append(call / 'RECEIPT.json' if name == 'recovered' else prefix / 'RECEIPT.json')
            pins.update(paths)
            request, response, receipt = map(read, paths)
            require(request == row['request'] and response == row['response'] and receipt == row['receipt'],
                    'original_public_request_receipt_changed')
            tx_path, rx_path = prefix / 'TX.bin', prefix / 'RX.bin'
            pins.update((tx_path, rx_path))
            tx, rx = tx_path.read_bytes(), rx_path.read_bytes()
            require((json.loads(tx), json.loads(rx)) == (request, response), 'original_stdio_bytes_differ_from_actual_rpc')
            require(request['id'] == response['id'] == receipt['id'] and receipt['TX_bytes'] == len(tx)
                    and receipt['RX_bytes'] == len(rx) and receipt['RX_sha256'] == sha256(rx).hexdigest(),
                    'original_trusted_stdio_id_size_or_rx_sha_changed')
            archive = row.get('producer_archive')
            if name == 'recovered':
                before, after = (call / f'ARCHIVE_{part}.bin' for part in ('BEFORE', 'AFTER'))
                pins.update((before, after))
                selected = recover.correlate_archive(before.read_bytes(), after.read_bytes(), row['started_ns'],
                    row['closed_ns'], response['result']['isError'], slot / 'product_full')
                require(selected == archive, 'recovered_correlation_disagrees_with_original_acceptance')
                old_rows.append((index, row, before, after))
            if archive is not None:
                product = Path(archive['path'])
                pins.add(product)
                for frame in read(product).get('constructed_frames', read(product).get('frames', [])):
                    for field, hash_key in (('image_path', 'image_sha256'), ('arrays_path', 'arrays_sha256')):
                        frame_path = Path(frame[field])
                        require(frame_path.resolve().is_relative_to(slot.resolve()) and sha(frame_path) == frame[hash_key],
                                'archived_original_frame_or_array_changed')
                        pins.add(frame_path)
            bodies[(name, index)] = response['result']
            indices.append({'index': index, 'id': request['id'], 'isError': response['result']['isError'],
                            'producer_index': None if archive is None else archive['index'],
                            'derived_TX_sha256': sha256(tx).hexdigest(), 'RX_sha256': sha256(rx).hexdigest()})
        result[name] = indices
    require([row['producer_index'] for row in result['recovered']] == [1, None, 2, 3, 4],
            'real_rejection_before_valid_recovery_is_required')
    require([row['isError'] for row in result['recovered']] == [False, True, False, False, False],
            'real_historical_error_sequence_changed')
    _, rejected_row, original_before, original_after = old_rows[1]
    rejected(lambda: recover.correlate_archive(original_before.read_bytes(),
        original_after.read_bytes(), rejected_row['started_ns'], rejected_row['closed_ns'],
        False, OLDER / 'product_full'), 'same_producer_archive_missing')
    _, next_row, before, after = old_rows[2]
    rejected(lambda: recover.correlate_archive(before.read_bytes(), after.read_bytes()[:-1], next_row['started_ns'],
        next_row['closed_ns'], False, OLDER / 'product_full'), 'same_producer_archive_incomplete_index')
    result['negative_controls'] = ['refuse_success_without_producer_append', 'refuse_incomplete_index']
    return result, bodies


class ArchivedTransport:
    def __init__(self, label, responses):
        self.label = label
        self.responses = list(responses)
        self.public_requests = []
        self.cameras = {'views': [{'name': 'SCENE'}]}
        self.buffers = {}
        self.product_tools = read(CATALOGUE)

    def public_request(self, arguments):
        expect = SLOT_REQUESTS[self.label][len(self.public_requests)]
        require(arguments == read(REQUESTS[expect]), 'outer_replay_changed_current_public_arguments')
        response = {'jsonrpc': '2.0', 'id': f'archived-replay-{len(self.public_requests) + 1}',
                    'result': self.responses[len(self.public_requests)]}
        self.public_requests.append({'id': response['id'], 'response': response})
        return response


def verify_outer(tmp, bodies):
    records = {}
    for label in ORDER:
        source = ([bodies['assembly', 1], bodies['recovered', 3]] if label == 'A'
                  else [bodies['recovered', 5]])
        folder = tmp / label
        folder.mkdir()
        begin = time.perf_counter_ns()
        deadline = begin + 30_000_000_000
        transport = ArchivedTransport(label, source)
        owner = batch.owner_for(transport, label, folder, deadline)
        try:
            endpoint = Path(owner.start(folder / 'ENDPOINT.json'))
            record = batch.execute(owner, label, folder, read(endpoint), deadline)
        finally:
            closure = owner.close()
        require(closure['confirmed'] and not closure['errors'], 'archived_loopback_bridge_did_not_close')
        client = folder / 'batch/rpc_03'
        server = folder / 'owner/rpc_003'
        require(all((client / name).read_bytes() == (server / name).read_bytes() for name in ('TCP_TX.bin', 'TCP_RX.bin')),
                'actual_loopback_client_and_owner_wire_bytes_differ')
        assert record['outer_business_count'] == 1
        records[label] = {key: record[key] for key in ('outer_business_count', 'inner_public_count', 'TX_bytes', 'RX_bytes')}
    return records


def verify_budget(tmp):
    ledger = Budget(tmp / 'test_budget')
    for label in ORDER:
        mark = ledger.reserve('Blender_start', label, 'qualification', 1)
        ledger.settle_start(mark, pid=None, spawn_status='not_spawned', outcome='offline_budget_control')
        for _ in SLOT_REQUESTS[label]:
            ledger.admit_business(label, 'qualification')
        rejected(lambda: ledger.admit_business(label, 'qualification'), 'business_tool_budget_exhausted')
        for _ in range(3):
            mark = ledger.reserve('raster_attempt', label, 'qualification', 1)
            ledger.settle_rasters(mark, actual=0, lower_bound=0, evidence={'replayed': True}, outcome='offline_quota_control')
        rejected(lambda: ledger.reserve('consumer_task', label, 'qualification', 1), 'qualification_model_consumer_forbidden')
    rejected(lambda: ledger.reserve('Blender_start', 'A', 'qualification', 1), 'registered_slot_already_admitted')
    return {'test_only': True, 'actual_owned_starts': 0, 'actual_rasters': 0, 'actual_models': 0, 'business_cap': 3}


def verify_entrypoints():
    entries = [(NS / 'run_sequence.py', []),
               *((HERE / 'run_slot.py', [label]) for label in ORDER), (HERE / 'mcp_entry.py', [])]
    outputs = []
    for entry, args in entries:
        argv = [sys.executable, '-I', '-B', str(entry), *args, '--dispatch-smoke']
        output = json.loads(subprocess.check_output(argv, cwd=ROOT, timeout=20))
        require(Path(output['entry']).resolve() == entry.resolve()
                and Path(output['admission']).resolve() == (HERE / 'admission.py').resolve()
                and output['schema'] == admission.SCHEMA and output['fresh_process_prepared_only'] is True,
                'fresh_process_dispatch_bound_to_other_experiment')
        if args:
            require(output['wrapper'] == batch.outer_message(args[0]) and Path(output['mcp_entry']).resolve() ==
                    (HERE / 'mcp_entry.py').resolve(), 'fresh_slot_dispatch_changed')
        outputs.append(output)
    return outputs


def verify_product_schema(pins):
    installed = read(PRODUCT_BINDING)
    shared = read(SEAL / 'SHARED_DEPENDENCY.json')
    sys.path[:0] = [installed['dependency_root'], shared['dependency_root']]
    bootstrap = load_retained('_m5_global_preflight_bootstrap', SEAL / 'bootstrap.py')
    helper = load_retained('_m5_global_preflight_installed_check', SEAL / 'harness/reused/verified_bootstrap.py')
    helper.bootstrap(installed)
    from human_eye_plugin.live_spatial_mcp import _validate_arguments
    require(read(NS / 'inputs/PRODUCT_SCHEMA.json') == read(PRODUCT_SCHEMA),
            'frozen_input_catalogue_differs_from_installed_schema')
    for path in REQUESTS.values():
        _validate_arguments('human_eye_scene_observe', read(path))
    observe, measure, joint = (read(REQUESTS[key]) for key in ('OBSERVE', 'MEASURE', 'JOINT'))
    require(joint['query'].pop('task_query') == measure['query'] and joint == observe,
            'joint_and_split_input_conditions_differ')
    pins.add(Path(bootstrap.__file__))


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and not EXTERNAL.exists(), 'fresh_isolated_preflight_required')
    pins = {Path(__file__), PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, ASSET, NS / 'inputs/PRODUCT_SCHEMA.json',
            PIXEL / 'harness/run_slot.py', SEAL / 'bridge.py', SEAL / 'native_tools.py',
            SEAL / 'harness/qual_driver.py', SEAL / 'harness/owned_runtime.py',
            SEAL / 'harness/reused/verified_bootstrap.py', SEAL / 'SHARED_DEPENDENCY.json',
            *REQUESTS.values(), *(HERE.glob('*.py')), NS / 'run_sequence.py'}
    entries = verify_entrypoints()
    verify_product_schema(pins)
    archives, bodies = check_archives(pins)
    with TemporaryDirectory(prefix='m5-global-dispatch-preflight-') as directory:
        tmp = Path(directory)
        outer, ledger = verify_outer(tmp, bodies), verify_budget(tmp)
    require(not EXTERNAL.exists(), 'preflight_changed_frozen_run_root')
    save(HERE / 'DISPATCH_PREFLIGHT.json', {'passed': True, 'limits': LIMITS,
         'actual_Blender_processes': 0, 'actual_raster_attempts': 0, 'actual_model_runs': 0,
         'actual_product_schema_validation': True, 'fresh_entrypoints': entries, 'outer_archived_loopback': outer,
         'ledger_rejection_control': ledger, 'archived_protocol': archives,
         'source_pins': [{'path': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size}
                         for p in sorted(pins, key=str)]})
    print('Dispatch preflight passed', sha(HERE / 'DISPATCH_PREFLIGHT.json'), len(pins))


if __name__ == '__main__':
    main()
