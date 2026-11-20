"""Reconcile the sole failed slot from original startup and closure evidence."""

from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUN = Path('D:/he_m5_joint_brief_source_projection_001')
SLOT = RUN / 'slots/B'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def review():
    evidence = {}

    def raw(path):
        data = path.read_bytes()
        evidence[path.resolve()] = {'path': str(path.resolve()), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}
        return data

    def read(path):
        return json.loads(raw(path))

    freeze_path = NS / 'FROZEN.json'
    frozen = read(freeze_path)
    freeze = evidence[freeze_path]['sha256']
    frozen_input = {Path(row['path']).resolve(): row for row in frozen['direct_inputs']}

    def bound(path):
        return evidence[path.resolve()] == frozen_input.get(path.resolve())

    require(frozen['slots'] == ['B'] and sorted(path.name for path in (RUN / 'slots').iterdir()) == ['B'],
            'original_one_slot_denominator_changed')
    started, result, publication, closed = (read(SLOT / name) for name in (
        'SLOT_STARTED.json', 'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'RUNTIME_CLOSE.json'))
    result_sha = evidence[(SLOT / 'SLOT_RESULT.json').resolve()]['sha256']
    require(started['freeze_sha256'] == result['freeze_sha256'] == freeze
            and started['label'] == result['label'] == publication['label'] == 'B'
            and started['started_ns'] == result['started_ns'] == publication['started_ns']
            and publication['result_sha256'] == result_sha and publication['owned_budget_passed'] is True
            and publication['status'] == result['status'] == 'failed', 'original_failed_publication_binding_changed')

    install, declared_schema, declared_tools = (NS / 'install' / name for name in (
        'PRODUCT_RUN_BINDING.json', 'PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'))
    binding, schema, tools = (read(path) for path in (install, declared_schema, declared_tools))
    require(all(bound(path) for path in (install, declared_schema, declared_tools))
            and result['product_binding_sha256'] == evidence[install]['sha256']
            and (result['product_git'], result['product_source_sha256']) ==
                (binding['preparation_git'], binding['source_sha256']) ==
                (frozen['product']['commit'], frozen['product']['source_sha256']), 'actual_candidate_outside_freeze')
    (error,) = result['errors']
    missing = NS / 'inputs/PRODUCT_SCHEMA.json'
    retained = NS.parent / 'm4_live_source_region_task_003/harness/owned_runtime.py'
    require(not missing.exists() and missing not in frozen_input and error['type'] == 'FileNotFoundError'
            and error['stage'] == 'shared_qualification_requests' and repr(str(missing)) in error['message']
            and str(retained) in error['traceback'] and '_start_public_mcp' in error['traceback']
            and b"read(NS / 'inputs/PRODUCT_SCHEMA.json')" in raw(retained) and bound(retained),
            'startup_missing_schema_cause_not_bound_to_retained_code')

    wire_rows = [json.loads(line) for line in raw(SLOT / 'mcp_io/MCP_IO.jsonl').splitlines()]
    calls = {row['sequence']: row for row in wire_rows}
    methods = ('initialize', 'notifications/initialized', 'tools/list')
    require(sorted(calls) == [1, 3] and len(wire_rows) == 2 and
            sorted(path.name for path in (SLOT / 'mcp').glob('rpc_*')) == ['rpc_01', 'rpc_02', 'rpc_03'],
            'business_traffic_or_missing_handshake_record')
    handshakes = {}
    for index, method in enumerate(methods, start=1):
        folder = SLOT / f'mcp/rpc_{index:02}'
        tx_path, rx_path = folder / 'TX.bin', folder / 'RX.bin'
        tx, receipt = read(tx_path), read(folder / 'RECEIPT.json')
        require(tx['method'] == receipt['method'] == method and tx.get('id') == receipt['id']
                and receipt['index'] == index and receipt['error'] is None
                and evidence[tx_path.resolve()]['bytes'] == receipt['TX_bytes'], 'original_handshake_TX_changed')
        if index == 2:
            require(not rx_path.exists(), 'notification_unexpected_response')
            continue
        parsed = read(rx_path)
        rx = evidence[rx_path.resolve()]
        meter = calls[index]
        normalized = rx_path.read_bytes().replace(b'\r\n', b'\n')
        require(parsed['id'] == tx['id'] == meter['response_id'] and 'error' not in parsed
                and read(folder / 'RESPONSE.json') == parsed and meter['method'] == method
                and rx['bytes'] == receipt['RX_bytes'] and rx['sha256'] == receipt['RX_sha256']
                and meter['TX_sha256'] == evidence[tx_path.resolve()]['sha256']
                and (meter['RX_text_UTF8_LF_sha256'], meter['RX_text_UTF8_LF_bytes']) ==
                    (sha256(normalized).hexdigest(), len(normalized))
                and result['started_ns'] <= receipt['started_ns'] <= receipt['closed_ns'] <= result['cleanup_started_ns'],
                'original_handshake_RX_or_timing_changed')
        handshakes[method] = (parsed, receipt)

    identity = handshakes['initialize'][0]['result']['_meta']['human_eye']
    actual_tools = handshakes['tools/list'][0]['result']['tools']
    actual_schema, = (row for row in actual_tools if row['name'] == 'human_eye_scene_observe')
    require(identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143
            and all(identity[key] == binding[key] for key in ('source_sha256', 'build_id', 'distribution_version',
                                                            'implementation_revision', 'protocol_version'))
            and actual_schema == schema and actual_tools == tools, 'actual_initialize_or_list_differs_from_frozen_install')

    counts = result['budget']['counts']
    (owned,) = result['budget']['records']
    claim, settlement = owned['claim'], owned['settlement']
    token = claim['token']
    require(read(RUN / f'budget/claims/{token}.json') == claim and
            read(RUN / f'budget/settlements/{token}.json') == settlement and
            claim['kind'] == 'Blender_start' and claim['label'] == 'B' and
            settlement['spawn_status'] == 'spawned' and settlement['outcome'] == 'failed' and
            counts['Blender_spawned_confirmed'] == counts['Blender_start_attempts'] == 1 and
            all(counts[key] == 0 for key in ('Blender_spawned_unknown', 'business_admissions', 'all_raster_actual',
                'all_raster_upper', 'pending_raster_reservations', 'consumer_admissions')) and
            result['model_consumers'] == result['paid_API_calls'] == 0 and not result['business_calls'] and
            not any((SLOT / name).exists() for name in ('PUBLIC_REQUESTS.jsonl', 'batch', 'NATIVE_CALLS.jsonl',
                    'initial_capture', 'TERMINAL_SOURCE.json', 'RUNTIME_READY.json')) and
            not any((SLOT / 'product_full').iterdir()), 'unexpected_business_or_geometry_evidence')

    native_ready = read(SLOT / 'native/READY.json')
    native_closed = read(SLOT / 'native/WORKER_CLOSED.json')
    require(len(list((SLOT / 'native/WIRE').glob('*/REQUEST.bin'))) == 1
            and read(SLOT / 'native/WIRE/001/REQUEST.bin') == {'type': 'close'}
            and native_closed['pid'] == native_ready['pid'] == settlement['pid']
            and native_closed['initial_geometry_fingerprint'] == native_closed['final_geometry_fingerprint'] ==
                native_ready['initial_fingerprint'] == result['closure_verification']['initial_final_fingerprint']
            and not native_closed['poisoned'] and result['closure_verification']['passed'] and not closed['errors']
            and closed['Blender_close']['source_file_unchanged'] and closed['Blender_close']['protected_files_unchanged']
            and all(closed[key]['confirmed'] and closed[key]['exited'] and closed[key]['exit_code'] == 0
                    and closed[key]['handle_closed'] for key in ('Blender_exit', 'public_MCP_exit')),
            'native_read_only_or_process_closure_did_not_match_original')
    asset = Path(result['asset_path']).resolve()
    copy = SLOT / 'native/input.blend'
    raw(asset)
    raw(copy)
    require(bound(asset) and evidence[asset]['sha256'] == evidence[copy.resolve()]['sha256'] ==
            result['asset_sha256'] == frozen['asset_sha256'], 'original_asset_or_copy_changed')

    began, cleanup, end = result['started_ns'], result['cleanup_started_ns'], publication['published_ns']
    listed = handshakes['tools/list'][1]
    require(began <= listed['closed_ns'] <= cleanup <= result['closed_ns'] <= end < result['owned_deadline_ns']
            and end - began == publication['complete_slot_ns'], 'failed_slot_time_boundary_changed')
    return {'schema': 'm5-joint-brief-source-projection-live-review-v1', 'freeze_sha256': freeze,
            'passed': False, 'failure_review_verified': True, 'slots': [{'label': 'B', 'status': 'failed',
                'passed': False, 'result_sha256': result_sha, 'error': error,
                'missing_runtime_schema_path': str(missing), 'declared_schema_path': str(declared_schema),
                'actual_product_identity': identity, 'actual_tools_list_matches_declared_catalogue': True,
                'actual_observe_schema_matches_declared_schema': True, 'MCP_handshake_methods': list(methods),
                'only_native_wire_operation': 'close', 'closed_fingerprint': native_ready['initial_fingerprint'],
                'native_and_product_confirmed_clean_exit': True, 'source_asset_and_copy_sha256': result['asset_sha256'],
                'startup_and_failed_schema_open_ms': (cleanup - began) / 1e6,
                'Blender_spawn_to_ready_ms': closed['Blender_status']['config']['startup_ns'] / 1e6,
                'public_MCP_init_RPC_ms': handshakes['initialize'][1]['elapsed_ns'] / 1e6,
                'public_tools_list_RPC_ms': listed['elapsed_ns'] / 1e6,
                'cleanup_to_publication_ms': (end - cleanup) / 1e6, 'owned_window_ms': (end - began) / 1e6}],
            'denominators': {'registered_owned': 1, 'Blender_start_attempts': 1, 'actual_owned_slot_directories': 1,
                'completed_slots': 0, 'failed_slots': 1, 'replacement_slots': 0, 'observed_public_requests': 0,
                'observed_outer_batches': 0, 'product_geometry_captures': 0, 'raster_attempts': 0,
                'proven_actual_frames': 0, 'model_consumers': 0, 'paid_API_calls': 0},
            'source_pins': list(evidence.values())}


if __name__ == '__main__':
    reviewed = review()
    with (HERE / 'LIVE_REVIEW.json').open('xb') as output:
        output.write(json.dumps(reviewed, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')
    print('Failure review verified: 1 failed owned start, zero business requests, captures, or rasters')
