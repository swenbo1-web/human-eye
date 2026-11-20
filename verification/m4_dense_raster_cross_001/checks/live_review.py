"""Qualify the unchanged dense output and measure only actual paired raster time."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import runpy
from statistics import median
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
PRIOR = V / 'm4_global_pixel_bound_short_circuit_001'
PRIOR_SCRIPT = PRIOR / 'checks/live_review.py'
PRIOR_RUN = Path('D:/he_m4_global_pixel_bound_short_circuit_001')
RUN = Path('D:/he_m4_dense_raster_cross_001')
BASE_COMMIT = 'f72e648f763fb6399f82c8e5d7f2b35840597bed'
BASE_SOURCE = '0e71932b2bccbf8a6583460875cea8bdc55b092b7d8f3391c9b0124aef986d4f'
PRIOR_BINDING_SHA256 = '395f3b4283e4a46477da960c213b031a8d7036cc1e03142ae039eaccd968a452'
PRIOR_FREEZE_SHA256 = '8c9424b343f2794158f0b7d7a584f9d697fa9ea0a2c999207bbdeb9ad84b381e'
PRIOR_REVIEW_SHA256 = 'cac0191c908d43de693c1af201a8574cd8392812905f2e22b3c8a3482e27f8f1'
PRIOR_INDEX_SHA256 = 'c412558ed01216ffed1dff1634112cb95a2fd70469ca049d86874e5c8ba15a9e'
PRIOR_ARCHIVE_SHA256 = '853d1bbde7295110e2a5a7214c40eb59a7cfed5169302e5f94e0c5b96fd6c9ef'
CHANGED = 'human_eye_plugin/attention_raster.py'
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
VIEWS = ('SCENE', 'LEFT')
RASTER_THRESHOLD = 10
MIN_RPC_IMPROVEMENTS = 2
BINDINGS = {'A': PRIOR / 'install/PRODUCT_RUN_BINDING.json', 'B': NS / 'install/PRODUCT_RUN_BINDING.json'}

prior = runpy.run_path(str(PRIOR_SCRIPT))
original = prior['original']
read, require, verified, write, digest, rows, ms, pin = (prior[k] for k in (
    'read', 'require', 'verified', 'write', 'digest', 'rows', 'ms', 'pin'))


def baseline_binding():
    binding = json.loads(verified(BINDINGS['A'], PRIOR_BINDING_SHA256, PRIOR))
    require(binding['preparation_git'] == BASE_COMMIT and binding['source_sha256'] == BASE_SOURCE
            and len(binding['source_manifest']) == 143, 'fixed_accepted_baseline_binding_changed')
    return binding


def installations():
    baseline, candidate = baseline_binding(), read(BINDINGS['B'])
    require(candidate['historical_preparation_git'] == BASE_COMMIT
            and candidate['historical_source_sha256'] == BASE_SOURCE
            and candidate['preparation_git'] != BASE_COMMIT and candidate['source_sha256'] != BASE_SOURCE
            and candidate['dependency_root'] == baseline['dependency_root']
            and candidate['changed_product_sources'] == [CHANGED],
            'candidate_is_not_one_raster_change_from_accepted_isolation')
    base_files, new_files = ({row['path']: row['sha256'] for row in item['source_manifest']}
                             for item in (baseline, candidate))
    require(len(base_files) == len(new_files) == len(candidate['source_manifest']) == 143
            and base_files.keys() == new_files.keys()
            and {path for path in base_files if base_files[path] != new_files[path]} == {CHANGED},
            'candidate_raster_install_changed_additional_sources')
    catalog = read(BINDINGS['A'].with_name('TOOLS_SCHEMA.json'))
    require(len(catalog) == 5 and catalog == read(BINDINGS['B'].with_name('TOOLS_SCHEMA.json')),
            'candidate_tool_catalog_changed')
    return {'A': baseline, 'B': candidate}, catalog


def historical_reference():
    review_path, index_path = PRIOR / 'checks/LIVE_REVIEW.json', PRIOR / 'RUNTIME_INDEX.json'
    previous = json.loads(verified(review_path, PRIOR_REVIEW_SHA256, PRIOR))
    index = json.loads(verified(index_path, PRIOR_INDEX_SHA256, PRIOR))
    historical, = [row for row in previous['slots'] if row['label'] == 'B1']
    require(previous['passed'] is True and previous['freeze_sha256'] == PRIOR_FREEZE_SHA256 and
            historical['passed'] is True and historical['installed_product']['commit'] == BASE_COMMIT and
            historical['installed_product']['source_sha256'] == BASE_SOURCE and
            historical['work']['pixel_bound_region_calls'] == 1 and
            len(historical['actual_bound_blocker_evidence']) == 2, 'accepted_dense_baseline_receipt_changed')
    slot = PRIOR_RUN / 'slots/B1'
    bundle = PRIOR_RUN / 'ORIGINAL_RUNTIME.zip'
    raw_zip = verified(bundle, PRIOR_ARCHIVE_SHA256, PRIOR_RUN)
    require(index['archive']['sha256'] == PRIOR_ARCHIVE_SHA256 and
            index['archive']['bytes'] == len(raw_zip) and
            Path(index['archive']['path']).resolve() == bundle.resolve() and
            index['count'] == len(index['files']) == 549, 'fixed_baseline_archive_binding_changed')
    entries = {row['path']: row for row in index['files']}
    selected = [name for name in entries if name.startswith('slots/B1/')]
    result = read(slot / 'SLOT_RESULT.json')
    for row in result['budget']['records']:
        claim = row['claim']
        if claim['label'] == 'B1':
            selected.append('budget/claims/' + claim['token'] + '.json')
            if row['settlement'] is not None:
                selected.append('budget/settlements/' + claim['token'] + '.json')
    paths = [review_path, index_path, bundle]
    with ZipFile(BytesIO(raw_zip)) as archive:
        require(set(archive.namelist()) == entries.keys() and len(archive.namelist()) == len(entries),
                'fixed_baseline_archive_membership_changed')
        for name in selected:
            target = PRIOR_RUN / name
            raw = verified(target, entries[name]['sha256'], PRIOR_RUN)
            require(len(raw) == entries[name]['bytes'] and raw == archive.read(name),
                    'accepted_original_slot_and_archive_bytes_differ/' + name)
            paths.append(target)
    event, = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    producer_file = Path(event['producer_archive']['path'])
    require(producer_file in paths, 'baseline_producer_snapshot_not_selected_from_archive')
    producer = read(producer_file)
    reply = read(slot / 'product_calls/call_001/RESPONSE.json')
    body_text = reply['result']['content'][0]['text']
    require(historical['slot_result_sha256'] == digest((slot / 'SLOT_RESULT.json').read_bytes())
            and historical['publication_sha256'] == digest((slot / 'SLOT_PUBLICATION.json').read_bytes())
            and historical['wire']['body_sha256'] == digest(body_text.encode())
            and historical['wire']['producer_archive_sha256'] == digest(producer_file.read_bytes()),
            'sealed_baseline_actual_result_wire_or_producer_changed')
    return historical, json.loads(body_text), producer, paths


def timed_frames(slot, producer, outcome, reference):
    """Bind pure raster spans to their own frame, distinct from its publishing interval."""
    import numpy as np

    shapes = {'color': ('uint8', (512, 512, 3)), 'depth': ('float64', (512, 512)),
              'owners': ('int32', (512, 512)), 'triangle_ids': ('int32', (512, 512)),
              'patch_owners': ('int32', (512, 512))}
    frames, old_frames = producer['constructed_frames'], reference[2]['constructed_frames']
    retained = outcome['frames']
    require(tuple(frame['view_name'] for frame in frames) == VIEWS, 'wrong_original_raster_frame_order')
    previous_end, server_end = outcome['cold_rpc_ns']
    measured = []
    for frame, previous, row in zip(frames, old_frames, retained, strict=True):
        view = frame['view_name']
        declared = producer['stages']['render_and_publish_global_' + view]
        stages = frame['stages']
        intervals = [stages[key] for key in ('actual_raster', 'PNG_NPZ_publication', 'frame_metadata')]
        require(all(type(value[key]) is int for value in [declared, *intervals]
                    for key in ('started_ns', 'closed_ns', 'elapsed_ns')) and
                all(value['closed_ns'] - value['started_ns'] == value['elapsed_ns'] > 0
                    for value in [declared, *intervals]), 'frame_stage_nanoseconds_not_exact/' + view)
        raster, png_npz, metadata = intervals
        require(previous_end <= declared['started_ns'] <= raster['started_ns'] < raster['closed_ns']
                <= png_npz['started_ns'] < png_npz['closed_ns'] <= metadata['started_ns']
                < metadata['closed_ns'] <= declared['closed_ns'] <= server_end and
                row['raster_ms'] == ms(raster['started_ns'], raster['closed_ns']),
                'frame_stage_spans_not_ordered_inside_cold_RPC/' + view)
        previous_end = declared['closed_ns']
        arrays = {}
        for path_key, hash_key in (('image_path', 'image_sha256'), ('arrays_path', 'arrays_sha256')):
            current = verified(frame[path_key], frame[hash_key], slot)
            sealed = verified(previous[path_key], previous[hash_key], PRIOR_RUN / 'slots/B1')
            require(current == sealed, 'raw_frame_bytes_differ_from_sealed_baseline/' + view + '/' + path_key)
            if path_key == 'arrays_path':
                with np.load(BytesIO(current), allow_pickle=False) as payload:
                    for name, (dtype, shape) in shapes.items():
                        array = payload[name]
                        require(array.dtype == np.dtype(dtype) and array.shape == shape,
                                'expected_raw_dtype_or_shape_changed/' + view + '/' + name)
                        arrays[name] = {'dtype': array.dtype.str, 'shape': list(shape),
                                        'raw_bytes_sha256': digest(array.tobytes(order='C'))}
        measured.append({'view': view, 'frame_identity': frame['frame_identity'],
                         'PNG_sha256': frame['image_sha256'], 'NPZ_sha256': frame['arrays_sha256'],
                         'arrays': arrays, 'raster_ns': raster['elapsed_ns'],
                         'raster_interval_ns': [raster['started_ns'], raster['closed_ns']],
                         'PNG_NPZ_publication_ns': png_npz['elapsed_ns'],
                         'frame_metadata_ns': metadata['elapsed_ns'],
                         'render_publish_ns': declared['elapsed_ns']})
    total_ns = sum(row['raster_ns'] for row in measured)
    require(total_ns <= server_end - outcome['cold_rpc_ns'][0], 'raster_sum_exceeds_cold_RPC')
    outcome.update(raster_frames=measured, raster_total_ns=total_ns, raster_total_ms=total_ns / 1e6)


def verify_slot(slot, label, freeze, installed, catalog, reference, archive_truth, outcome, binding_path):
    result_path, publication_path = (slot / name for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
    require(result_path.is_file(), 'slot_started_without_a_closed_result')
    result = read(result_path)
    outcome.update(slot_result_sha256=digest(result_path.read_bytes()),
                   original_runtime_status=result['status'], original_slot_errors=result['errors'])
    published, started = read(publication_path), read(slot / 'SLOT_STARTED.json')
    outcome.update(publication_sha256=digest(publication_path.read_bytes()),
                   original_publication_status=published['status'])
    expected_arm = 'B' if slot.parent.parent == PRIOR_RUN and label == 'B1' else label[0]
    require(all(x['phase'] == 'formal' and x['group'] == 'P' and x['arm'] == expected_arm
                and x['product_git'] == installed['preparation_git'] for x in (started, result)),
            'mismatched_executed_actual_arm')
    prior['verify_close'](slot, started, result, published, freeze, label)
    prior['verified_budget'](slot.parent.parent, label, result)
    outcome['installed_product'] = prior['inspect_current_install'](slot, result, installed, binding_path, catalog)
    producer, event = prior['measure'](slot, installed, result, published, started, outcome, reference, archive_truth, 1)
    context = Path(event['producer_archive']['read_context']).resolve()
    require(context == (slot / 'product_full/call_001/READ_CONTEXT.json').resolve(),
            'raster_read_context_not_bound_to_current_observation')
    record = read(context)
    outcome['read_context_sha256'] = digest(context.read_bytes())
    profiled = any(record[key].get(name) is not None for key in ('before', 'after')
                   for name in ('pixel_bound_probe', 'producer_window_cpu_ns'))
    require(slot.parent.parent == PRIOR_RUN or not profiled, 'actual_paired_raster_process_is_instrumented')
    outcome['accepted_baseline_used_previous_auxiliary_probes'] = profiled
    timed_frames(slot, producer, outcome, reference)
    outcome.update(status='completed', passed=True)


def review_slot(runtime, label, freeze, installed, catalog, reference, archive_truth):
    slot = runtime / 'slots' / label
    outcome = {'label': label, 'arm': label[0], 'passed': False, 'issues': [],
               'status': 'failed' if slot.exists() else 'unrun',
               'cli_path': runtime / 'preflight/CLI_REPLAY' / label}
    try:
        if slot.exists():
            verify_slot(slot, label, freeze, installed, catalog, reference, archive_truth, outcome, BINDINGS[label[0]])
    except Exception as error:
        outcome['issues'].append({'type': type(error).__name__, 'message': str(error)})
    finally:
        outcome['cli_path'] = str(outcome['cli_path'])
    return outcome


def compare_pair(a, b):
    require(a['passed'] is True and b['passed'] is True, 'one_or_both_slots_not_quality_verified')
    require(a['normalized_original_brief_sha256'] == b['normalized_original_brief_sha256'] and
            [a['pixel_bound_region_calls'], b['pixel_bound_region_calls']] == [1, 1],
            'brief_or_accepted_global_view_work_changed')
    static_frame_keys = ('view', 'frame_identity', 'PNG_sha256', 'NPZ_sha256', 'arrays')
    require(all(old[key] == new[key] for old, new in zip(a['raster_frames'], b['raster_frames'], strict=True)
                for key in static_frame_keys), 'paired_frames_or_named_array_bytes_differ')
    timing_keys = {'cold_server_RPC_ms': 'request_server_RPC_ms', 'cold_client_RPC_ms': 'request_client_RPC_ms',
                   'startup_to_ready_ms': 'startup_to_ready_ms', 'owned_window_ms': 'owned_window_ms',
                   'request_end_to_publication_ms': 'request_end_to_publication_ms',
                   'formatting_ms': 'formatting_ms', 'archive_producer_snapshot_ms': 'archive_producer_snapshot_ms'}
    clocks = {key: [slot['timing'][name] for slot in (a, b)] for key, name in timing_keys.items()}
    for key, name in (('capture_ms', 'host_capture'), ('index_ms', 'index_global')):
        clocks[key] = [slot['timing']['producer_stages_ms'][name] for slot in (a, b)]
    for i, view in enumerate(VIEWS):
        for key in ('raster', 'render_publish', 'PNG_NPZ_publication', 'frame_metadata'):
            clocks[view + '_' + key + '_ms'] = [slot['raster_frames'][i][key + '_ns'] / 1e6 for slot in (a, b)]
    clocks['raster_total_ms'] = [slot['raster_total_ms'] for slot in (a, b)]
    raster_a, raster_b = clocks['raster_total_ms']
    cold_a, cold_b = clocks['cold_server_RPC_ms']
    return {'A': a['label'], 'B': b['label'], 'passed': True, 'raw_frame_bytes_equal': True,
            'timing_A_B_ms': clocks, 'raster_reduction_percent': 100 * (raster_a - raster_b) / raster_a,
            'raster_delta_ms': raster_b - raster_a, 'cold_RPC_delta_ms': cold_b - cold_a,
            'cold_RPC_improved': cold_b < cold_a,
            'owned_window_delta_ms': b['timing']['owned_window_ms'] - a['timing']['owned_window_ms']}


def review(runtime, freeze_path):
    freeze = digest(freeze_path.read_bytes())
    frozen = read(freeze_path)
    installed, catalog = installations()
    require(frozen['slots'] == list(ORDER) and frozen['asset_sha256'] == original['ASSET_SHA'],
            'frozen_actual_six_slots_or_dense_asset_changed')
    for arm, item in installed.items():
        prior['verify_install'](item)
        require(all(frozen['products'][arm][k] == item[f] for k, f in
                    (('commit', 'preparation_git'), ('source_sha256', 'source_sha256'))),
                'installed_product_differs_from_frozen_arm/' + arm)
    sys.path.insert(0, installed['A']['dependency_root'])
    reference, source = historical_reference(), prior['truth']()
    slot_root = runtime / 'slots'
    attempted = {path.name for path in slot_root.iterdir()} if slot_root.is_dir() else set()
    require(attempted == set(ORDER[:len(attempted)]), 'non_prefix_or_unknown_original_slot')
    denominator = prior['raw_denominator'](runtime)
    expected = {'Blender_start': 1, 'business_tool': 1, 'raster_attempt': 2,
                'actual_rasters_or_lower_bound': 2, 'potential_upper_rasters': 2, 'pending_rasters': 0}
    slots = {label: review_slot(runtime, label, freeze, installed[label[0]], catalog, reference, source) for label in ORDER}
    pairs = []
    for i in (1, 2, 3):
        a, b = f'A{i}', f'B{i}'
        try:
            pairs.append(compare_pair(slots[a], slots[b]))
        except (KeyError, TypeError, ValueError) as error:
            pairs.append({'A': a, 'B': b, 'passed': False, 'reason': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    require(all(denominator[row['label']] == expected for row in complete), 'completed_slot_ledger_mismatch')
    nonoverlap = all(a['owned_window_ns'][1] <= b['owned_window_ns'][0] for a, b in zip(complete, complete[1:]))
    good = [pair for pair in pairs if pair['passed']]
    quality = len(complete) == len(ORDER) and nonoverlap and len(good) == 3
    reduction = median(row['raster_reduction_percent'] for row in good) if good else None
    raster_delta = median(row['raster_delta_ms'] for row in good) if good else None
    rpc_delta = median(row['cold_RPC_delta_ms'] for row in good) if good else None
    rpc_wins = sum(row['cold_RPC_improved'] for row in good)
    window_delta = median(row['owned_window_delta_ms'] for row in good) if good else None
    raster_gate = len(good) == 3 and reduction >= RASTER_THRESHOLD
    rpc_gate = len(good) == 3 and rpc_wins >= MIN_RPC_IMPROVEMENTS and rpc_delta < 0
    return {'schema': 'm4-dense-raster-cross-live-review-v1', 'passed': quality and raster_gate and rpc_gate,
            'quality_passed': quality, 'performance_passed': raster_gate and rpc_gate,
            'raster_stage_gate_passed': raster_gate, 'cold_rpc_gate_passed': rpc_gate,
            'verified_nonoverlap': nonoverlap, 'freeze_sha256': freeze, 'registered_order': list(ORDER),
            'passed_slot_count': len(complete), 'attempted_owned_slots': len(attempted),
            'nonpassing_slot_count': len(attempted) - len(complete), 'unrun_slot_count': len(ORDER) - len(attempted),
            'original_admissions_even_when_slot_failed': denominator, 'fixed_asset_sha256': source['asset_sha256'],
            'historical_archive_sha256': PRIOR_ARCHIVE_SHA256, 'fixed_baseline_source_sha256': BASE_SOURCE,
            'candidate_source_sha256': installed['B']['source_sha256'],
            'median_paired_raster_reduction_percent': reduction, 'raster_stage_threshold_percent': RASTER_THRESHOLD,
            'median_paired_raster_delta_ms': raster_delta, 'median_cold_RPC_delta_ms': rpc_delta,
            'cold_RPC_improved_pairs': rpc_wins, 'cold_RPC_improved_pairs_required': MIN_RPC_IMPROVEMENTS,
            'median_owned_window_delta_ms': window_delta, 'model_consumers': 0,
            'slots': list(slots.values()), 'pairs': pairs}


def preflight():
    reference, installed = historical_reference(), baseline_binding()
    prior['verify_install'](installed)
    sys.path.insert(0, installed['dependency_root'])
    frozen = PRIOR / 'FROZEN.json'
    verified(frozen, PRIOR_FREEZE_SHA256, PRIOR)
    slot = PRIOR_RUN / 'slots/B1'
    catalog_path = BINDINGS['A'].with_name('TOOLS_SCHEMA.json')
    outcome = {'label': 'B1', 'arm': 'B', 'issues': [], 'cli_path': HERE / 'historical_CLI_REPLAY'}
    verify_slot(slot, 'B1', PRIOR_FREEZE_SHA256, installed, read(catalog_path), reference,
                prior['truth'](), outcome, BINDINGS['A'])
    check_previous_clock_sum = sum(row['raster_ms'] for row in reference[0]['frames'])
    require(abs(outcome['raster_total_ms'] - check_previous_clock_sum) < 1e-8,
            'pure_raster_stage_definition_disagrees_with_accepted_original')
    retained_pref = read(PRIOR / 'checks/LIVE_PREFLIGHT.json')
    pins = {p['path']: p for p in retained_pref['source_pins']}
    for path in (Path(__file__), PRIOR_SCRIPT, *reference[3], frozen, BINDINGS['A'], catalog_path,
                 PRIOR / 'checks/LIVE_PREFLIGHT.json'):
        row = pin(path)
        pins[row['path']] = row
    outcome['cli_path'] = str(outcome['cli_path'])
    return {'passed': True, 'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
            'historical_archive_sha256': PRIOR_ARCHIVE_SHA256, 'verified_B1': outcome,
            'source_pins': [pins[key] for key in sorted(pins)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    result = preflight() if args.preflight else review(args.runtime, args.freeze)
    output = args.output or HERE / ('LIVE_PREFLIGHT.json' if args.preflight else 'LIVE_REVIEW.json')
    write(output, result)
    fields = ('passed', 'quality_passed', 'performance_passed', 'passed_slot_count',
              'median_paired_raster_reduction_percent', 'median_cold_RPC_delta_ms', 'cold_RPC_improved_pairs')
    print(json.dumps({key: result[key] for key in fields if key in result}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
