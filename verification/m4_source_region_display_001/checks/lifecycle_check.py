"""Audit saved owned-process, display-restoration and budget evidence offline."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
STATES = ['initial', 'cube_visible', 'cube_restored', 'target_hidden', 'target_restored']


def review(sessions_root, budget_root):
    root = Path(sessions_root).resolve()
    budget_root = Path(budget_root).resolve()
    pins, checks, slots = {}, [], []

    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)

    def file(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        check(expected is None or digest == expected, 'pinned_bytes/' + path.name)
        pins[str(path)] = dict(path=str(path), bytes=len(raw), sha256=digest)
        return raw

    def read(path, expected=None):
        return json.loads(file(path, expected))

    def jsonlines(path):
        return [json.loads(line) for line in file(path).splitlines() if line.strip()]

    def geometry(snapshot):
        return dict(frame=snapshot['frame'], subframe=snapshot['subframe'],
            unit_settings=snapshot['unit_settings'], unit_scale=snapshot['unit_scale'],
            objects=[{key: value for key, value in row.items() if key != 'display'}
                     for row in snapshot['objects']])

    for label in ('main', 'state'):
        folder = root / label
        result_path = folder / 'SLOT_RESULT.json'
        publication = read(folder / 'SLOT_PUBLICATION.json')
        result = read(result_path, publication['result_sha256'])
        check(result['status'] == publication['status'] == 'completed' and not result['errors'], label + '/slot_completed')
        started, deadline = result['clocks']['slot_started_ns'], result['clocks']['owned_deadline_ns']
        published = publication['slot_result_published_ns']
        check(deadline - started == 600_000_000_000 and started < published < deadline
              and publication['owned_budget_passed'] is True
              and publication['complete_slot_ns'] == published - started, label + '/original_owned_deadline')
        close = read(folder / 'RUNTIME_CLOSE.json')
        check(close == result['cleanup']['runtime_close'], label + '/same_closure_bytes_in_slot')
        native = close['Blender_status']
        config, state = native['config'], native['closed']
        check(not close['errors'] and not close['runtime']['errors']
              and state['poisoned'] is False, label + '/unpoisoned_closure')
        check(state['initial_geometry_fingerprint'] == state['final_geometry_fingerprint']
              and state['display_restored'] is True
              and state['full_initial_state'] == state['full_final_state'], label + '/complete_original_geometry_and_flags_restored')
        check(native['source_file_unchanged'] is True and native['protected_files_unchanged'] is True,
              label + '/protected_source_closure')
        check(hashlib.sha256(file(config['asset'])).hexdigest() == config['asset_sha256'] == ASSET_SHA
              and hashlib.sha256(file(config['asset_copy'])).hexdigest() == ASSET_SHA, label + '/original_and_unsaved_copy_bytes')
        for protected in config.get('protected_public_images', []):
            file(protected['path'], protected['sha256'])
        native_proof = read(folder / 'NATIVE_RUNTIME_PROOF.json')
        mcp_proof = read(folder / 'MCP_RUNTIME_PROOF.json')
        check(native_proof['confirmed'] is True and native_proof['runtime_pid'] == state['pid'] == config['pid']
              and mcp_proof['confirmed'] is True, label + '/retained_runtime_identity')
        for evidence in (close['MCP_retained_exit'], result['cleanup']['native_retained_exit']):
            check(evidence['confirmed'] is True and evidence['exit_code'] == 0
                  and evidence['handle_closed'] is True, label + '/retained_process_handle_closed')
        check(close['MCP_stdio_close']['confirmed'] is True
              and close['MCP_stdio_close']['exit_code'] == 0
              and close['Blender_close']['exit_code'] == 0
              and close['Blender_close']['process_reaped'] is True
              and result['cleanup']['native_Popen_handle_closed'] is True, label + '/owned_processes_reaped')

        stages = STATES if label == 'state' else ['initial']
        expected_labels = stages + ['repeat']
        requests = result['requests']
        check([row['label'] for row in requests] == expected_labels
              and all(row['is_error'] is False for row in requests), label + '/exact_public_request_sequence')
        check(result['source_exports'] == stages, label + '/exact_source_export_sequence')
        check(requests[-1]['arguments']['query']['region_ref'] == requests[-2]['public_result']['region_ref'],
              label + '/repeat_uses_preceding_actual_public_reference')
        check(all(row['deadline_ns'] == min(deadline, row['started_ns'] + 30_000_000_000)
                  and row['started_ns'] < row['returned_ns'] < row['deadline_ns'] for row in requests),
              label + '/each_original_public_deadline')
        for row in requests[:-1]:
            check('region' in row['arguments']['query'] and 'region_ref' not in row['arguments']['query'],
                  label + '/' + row['label'] + '/fresh_source_selection')
        public = jsonlines(folder / 'PUBLIC_REQUESTS.jsonl')
        check(len(public) == len(requests), label + '/all_public_calls_accounted')
        for row in public:
            file(row['actual_TX_path'], row['actual_TX_sha256'])
            file(row['actual_RX_path'], row['actual_RX_sha256'])
            file(row['request_path'], row['request_sha256'])
            file(row['response_path'], row['response_sha256'])
            archive = row['producer_archive']
            file(archive['path'], archive['sha256'])

        snapshots, displays, distances = [], [], []
        for stage in stages:
            source_path = folder / ('SOURCE_' + stage + '.json')
            receipt = read(folder / ('SOURCE_' + stage + '_RECEIPT.json'))
            snapshot = read(source_path, receipt['receipt']['sha256'])
            oracle = read(receipt['oracle_path'], receipt['oracle_sha256'])
            check(snapshot['state'] == stage and snapshot['process_id'] == config['pid']
                  and snapshot['source_sha256'] == ASSET_SHA and snapshot['source_writes'] == 0
                  and snapshot['saved_blend'] is False, label + '/' + stage + '/source_identity')
            check(oracle['status'] == 'passed' and oracle['process_id'] == config['pid']
                  and oracle['inputs']['snapshot']['sha256'] == receipt['receipt']['sha256'],
                  label + '/' + stage + '/independent_source_oracle')
            display = snapshot['display_snapshot']
            raw = json.dumps(display, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            check(hashlib.sha256(raw).hexdigest() == snapshot['display_snapshot_sha256']
                  and display['scope'] == 'active_view_layer_effective_viewport', label + '/' + stage + '/display_digest_and_scope')
            flags = {row['name']: row for row in display['objects']}
            cube_hidden, target_hidden = stage != 'cube_visible', stage == 'target_hidden'
            check(flags['Cube']['hide_get'] is cube_hidden and flags['Cube']['visible_get'] is (not cube_hidden)
                  and flags['Cube']['hide_render'] is True and flags['Cube']['hide_viewport'] is False
                  and flags[TARGET]['hide_get'] is target_hidden and flags[TARGET]['visible_get'] is (not target_hidden)
                  and flags[TARGET]['hide_render'] is False and flags[TARGET]['hide_viewport'] is False,
                  label + '/' + stage + '/actual_flags_match_authorized_state')
            check(all(row['display'] == flags[row['name']] for row in snapshot['objects']),
                  label + '/' + stage + '/geometry_and_display_share_object_identity')
            snapshots.append(snapshot)
            displays.append(display)
            distances.append(oracle['distance_oracle']['distance_m'])
        check(all(geometry(snapshot) == geometry(snapshots[0]) for snapshot in snapshots),
              label + '/all_world_native_evaluated_geometry_and_matrices_unchanged')
        check(all(distance == distances[0] for distance in distances), label + '/metric_source_unchanged_across_display_states')
        if label == 'state':
            for index in (2, 4):
                check(displays[index] == displays[0], label + '/restored_display_snapshot_' + str(index))
            for index in (1, 3):
                expected = copy.deepcopy(displays[0])
                changed_name = 'Cube' if index == 1 else TARGET
                row = next(row for row in expected['objects'] if row['name'] == changed_name)
                row['hide_get'], row['visible_get'] = not row['hide_get'], not row['visible_get']
                check(displays[index] == expected, label + '/only_authorized_flags_changed_' + str(index))
        events = jsonlines(folder / 'native/WORKER_EVENTS.jsonl')
        mutations = [row for row in events if row.get('status') == 'display_fixture_applied']
        expected_setters = 4 if label == 'state' else 0
        check(len(mutations) == expected_setters == state['fixture_hide_set_setters']
              == result['fixture_control']['fixture_hide_set_setters']
              and state['product_setters'] == result['fixture_control']['product_setters'] == 0,
              label + '/exact_fixture_and_product_setter_counts')
        check([row['display_stage'] for row in mutations] == list(range(1, expected_setters + 1)),
              label + '/ordered_fixed_fixture_operations')
        check(len(list((folder / 'native').glob('DISPLAY_*_ATTEMPT.json'))) == expected_setters
              and len(list((folder / 'native').glob('DISPLAY_*_RECEIPT.json'))) == expected_setters,
              label + '/all_fixture_attempts_confirmed')
        check(result['model_consumers'] == result['paid_API_calls'] == 0, label + '/zero_model_or_paid_calls')
        host_work = read(folder / 'HOST_RESIDENCY_WORK.json')
        check(host_work == result['host_residency_work']
              and host_work['value']['process_id'] == config['pid']
              and requests[-1]['returned_ns'] <= host_work['started_ns'] < host_work['returned_ns'] < deadline,
              label + '/host_residency_counters_read_after_public_within_owned_deadline')
        display_work = {key: host_work['value']['counters'][key]
                        for key in ('display_snapshots', 'display_objects', 'display_read_ns')}
        check(all(type(value) is int and value > 0 for value in display_work.values()),
              label + '/actual_host_display_read_work_recorded')
        slots.append(dict(label=label, complete_slot_s=(published - started) / 1e9,
            native_pid=config['pid'], mcp_pid=mcp_proof['runtime_pid'], source_exports=len(stages),
            public_requests=len(requests), fixture_hide_set_setters=expected_setters,
            host_display_work=display_work,
            public_refs=[dict(label=row['label'], region_ref=row['public_result']['region_ref']) for row in requests]))

    limits = read(budget_root / 'LIMITS.json')
    check(limits['Blender_start_attempts'] == 2 and limits['all_rasters'] == 8
          and limits['consumer_tasks'] == 0, 'registered_global_limits')
    claims = [read(path) for path in sorted((budget_root / 'claims').glob('*.json'))]
    starts = [row for row in claims if row['kind'] == 'Blender_start']
    rasters = [row for row in claims if row['kind'] == 'raster_attempt']
    check(len(starts) == 2 and len(rasters) <= 8
          and all(row['kind'] != 'consumer_task' for row in claims), 'global_admissions_within_budget')
    settlements = [read(budget_root / 'settlements' / (row['token'] + '.json')) for row in starts + rasters]
    actual = sum(row['actual_attempts'] for row in settlements if 'actual_attempts' in row)
    check(actual == len(rasters), 'all_raster_admissions_settled_actual_including_failed_attempts')
    return dict(schema='m4-source-region-display-lifecycle-review-v1', status='passed',
        slots=slots, owned_start_attempts=len(starts), actual_rasters=actual,
        fixture_hide_set_setters=4, product_setters=0, source_exports=6,
        public_requests=8, checks=checks, input_pins=list(pins.values()),
        operations=dict(Blender_starts=0, actual_rasters=0, model_calls=0, paid_calls=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root', type=Path, required=True)
    parser.add_argument('--budget-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = review(args.sessions_root, args.budget_root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(result['checks']), actual_rasters=result['actual_rasters'])))


if __name__ == '__main__':
    main()
