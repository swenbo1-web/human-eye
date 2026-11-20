"""Independently grade the frozen two-request cold-frustum A/B sequence."""

import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PREVIOUS = NS.parent / 'm4_cross_scale_global_index_reuse_001'
RUN = Path('D:/he_m4_cross_scale_cold_frustum_001')
BASELINE = PREVIOUS / 'install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
BASELINE_SHA = '82c525ec4fbc28aa0e282158bdfde94446bce83e6e4e8854ed7c5ae9c1748ff2'
PHASES = ('cold', 'prediction')
MIN_INDEX_REDUCTION_PERCENT = 20
FRUSTUM_COUNTERS = ('frustum_certified_views', 'frustum_fallback_views', 'frustum_shadow_bypassed',
                    'frustum_shadow_legacy', 'frustum_proof_ns')

spec = importlib.util.spec_from_file_location('_retained_index_reuse_assessor',
                                              PREVIOUS / 'checks/assess_pairs_live.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
prior = previous.prior
from formal import read, require, terminal, verified, write


def retained_index(contexts, prediction):
    snapshots = [context[side]['region_task_global_indexes'] for context in contexts for side in ('before', 'after')]
    require(snapshots[0] == [] and all(type(items) is list and len(items) == 1 for items in snapshots[1:]),
            'expected_one_index_retained_only_after_the_cold_request')
    first = snapshots[1][0]
    for snapshot in snapshots[1:]:
        actual = {key: value for key, value in snapshot[0].items() if key != 'python_graph'}
        expected = {key: value for key, value in first.items() if key != 'python_graph'}
        require(actual == expected, 'same_generation_preparation_resource_changed')
    require(type(first['python_id']) is int and first['python_id'] > 0 and
            first['type'].rsplit('.', 1)[-1] == 'CoverageIndex' and
            (first['regions'], first['views'], first['partition_rows']) == (84, 6, 21) and
            first['scene_identity'] == prediction['geometry_identity'] and
            first['camera_identity'] == prediction['camera_identity'] and
            first['selection_repr'] == contexts[1]['after']['active_selection_repr'],
            'retained_index_not_bound_to_current_prediction')
    return first


def assess_frustum_work(cold, prediction, arm):
    if arm == 'A':
        require(all(key not in phase['work'] for key in FRUSTUM_COUNTERS for phase in (cold, prediction)),
                'baseline_unexpectedly_reported_candidate_frustum_work')
        cold['timing']['frustum_proof_ms'] = 0
        prediction['timing']['frustum_proof_ms'] = 0
        return
    actual = {key: cold['work'][key] for key in FRUSTUM_COUNTERS}
    reused = {key: prediction['work'][key] for key in FRUSTUM_COUNTERS}
    require(all(type(value) is int and value >= 0 for row in (actual, reused) for value in row.values()) and
            actual['frustum_certified_views'] == 6 and actual['frustum_fallback_views'] == 0 and
            actual['frustum_shadow_bypassed'] > 0 and actual['frustum_shadow_legacy'] == 0 and
            0 < actual['frustum_proof_ns'] / 1e6 <= cold['timing']['global_index_ms'] and
            set(reused.values()) == {0}, 'frustum_work_not_bound_to_cold_global_index_construction')
    for phase, values in ((cold, actual), (prediction, reused)):
        phase['frustum_work'] = values
        phase['timing']['frustum_proof_ms'] = values['frustum_proof_ns'] / 1e6


def assess_slot(slot, label, requests, truth, installed, freeze_sha):
    outcome_path = slot / 'SLOT_RESULT.json'
    outcome_raw = outcome_path.read_bytes()
    outcome = json.loads(outcome_raw)
    started = read(slot / 'SLOT_STARTED.json')
    publication_path = slot / 'SLOT_PUBLICATION.json'
    publication = read(publication_path)
    arm = label[0]
    require(outcome['status'] == publication['status'] == 'completed' and not outcome['errors'] and
            publication['owned_budget_passed'] is True and publication['result_sha256'] == prior.digest(outcome_raw)
            and all(row['label'] == label for row in (outcome, started, publication)) and
            all(row['freeze_sha256'] == freeze_sha for row in (outcome, started)),
            'original_owned_slot_admission_or_publication_mismatch')
    require(outcome['arm'] == started['arm'] == arm and outcome['model_consumers'] == outcome['paid_API_calls'] == 0 and
            not (slot / 'consumer').exists() and outcome['asset_sha256'] == truth['asset_sha256'] and
            outcome['task_deadline_ns'] - outcome['started_ns'] == 450_000_000_000 and
            outcome['owned_deadline_ns'] - outcome['started_ns'] == 600_000_000_000,
            'wrong_arm_model_asset_or_owned_deadlines')
    asset = Path(truth['asset_path'])
    source_sha = installed[arm]['source_sha256']
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    require(ready['product_source_sha256'] == identity['source_sha256'] == outcome['product_source_sha256'] ==
            source_sha and identity['source_kind'] == 'installed_distribution' and
            identity['source_file_count'] == 143 and len(installed[arm]['source_manifest']) == 143 and
            asset.read_bytes() == (slot / 'native/input.blend').read_bytes(), 'wrong_actual_install_or_asset_copy')
    closure = read(slot / 'RUNTIME_CLOSE.json')
    exit_receipt = closure['public_MCP_exit']
    require(not closure['errors'] and exit_receipt['confirmed'] and exit_receipt['exited'] and
            exit_receipt['handle_closed'] and exit_receipt['exit_code'] == 0, 'installed_mcp_did_not_close_cleanly')
    terminal_source, native = terminal(slot, outcome, truth['asset_sha256'])

    events = prior.rows(slot / 'PUBLIC_REQUESTS.jsonl')
    calls = [row for row in prior.rows(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    require(len(events) == len(calls) == 2 and [row['index'] for row in events] == [1, 2] and
            [row['request']['id'] for row in events] == [row['id'] for row in calls] and
            len({row['id'] for row in calls}) == 2, 'expected_exact_cold_and_prediction_requests')
    clock = [outcome['ready_ns'], *(mark for row in events for mark in (row['started_ns'], row['closed_ns'])),
             min(outcome['task_deadline_ns'], outcome['cleanup_started_ns']),
             publication['published_ns'], outcome['owned_deadline_ns']]
    require(clock == sorted(clock), 'owned_process_or_request_window_not_closed')
    audit = prior.rows(slot / 'product_audit.jsonl')
    # Both products have the previously accepted local-first and index-reuse behavior.
    cold = prior.assess_call(slot, events[0], calls[0], audit, requests[0], truth, terminal_source,
                             source_sha, 'B', hot=False)
    prediction = previous.assess_prediction(slot, events[1], calls[1], audit, requests[1],
                                            truth, terminal_source, 'B', source_sha)
    require(all(cold[key] == prediction[key] for key in ('session_id', 'capture_state', 'source_binding')),
            'cold_and_prediction_are_not_from_the_same_generation')
    producer = read(Path(events[0]['producer_archive']['path']))
    stages = cold['timing']['scoped_stages_ms']
    require(stages['index_global'] > 0 and cold['work']['partition_calls'] == 1 and
            not cold['work'].get('global_index_cache_hit') and
            producer['binding']['geometry_identity'] == prediction['geometry_identity'] and
            producer['binding']['camera_identity'] == prediction['camera_identity'],
            'cold_global_index_or_current_geometry_and_camera_drift')
    cold['global_index_builds'] = 1
    contexts = previous.read_contexts(slot, events, (cold, prediction))
    retained = retained_index(contexts, prediction)
    assess_frustum_work(cold, prediction, arm)

    budget = outcome['budget']
    entry = budget['slots'][label]
    claims = [row['claim']['kind'] for row in budget['records'] if row['claim']['label'] == label]
    require(entry['business_admissions'] == claims.count('business_tool') == 2 and
            entry['raster_actual'] == entry['raster_upper'] == cold['new_constructed'] == 3 and
            claims.count('Blender_start') == 1 and claims.count('consumer_task') == 0,
            'retained_attempt_budget_differs_from_verified_observations')
    return {'label': label, 'arm': arm, 'status': 'completed', 'passed': True, 'source_sha256': source_sha,
            'product_distribution_version': identity['distribution_version'], 'native_PID': ready['native_pid'],
            'product_PID': ready['product_PID'], 'slot_result_sha256': prior.digest(outcome_raw),
            'publication_sha256': prior.digest(publication_path.read_bytes()), 'native': native, 'business_attempts': 2,
            'raster_attempts': entry['raster_actual'],
            'owned_window_ms': prior.milliseconds(outcome['started_ns'], publication['published_ns']),
            'owned_awake_window': [outcome['started_ns'], publication['published_ns']],
            'startup_to_ready_ms': prior.milliseconds(outcome['started_ns'], outcome['ready_ns']),
            'finished_last_request_to_publication_ms':
                prior.milliseconds(events[1]['closed_ns'], publication['published_ns']),
            'sequence_window_ms': prior.milliseconds(events[0]['started_ns'], events[1]['closed_ns']),
            'sequence_rpc_sum_ms': sum(row['timing']['server_rpc_ms'] for row in (cold, prediction)),
            'retained_global_index': retained,
            'global_index_builds_by_request': [cold['global_index_builds'], prediction['global_index_builds']],
            'cold': cold, 'prediction': prediction}


def compare_pair(run, baseline, candidate):
    a, b = baseline['label'], candidate['label']
    first, second = baseline['cold'], candidate['cold']
    selected_keys = ('view', 'object_name', 'image_sha256', 'png_bytes', 'camera_sha256', 'independent_pixels')
    buffer_keys = ('view', 'object_name', 'named_array_bytes', 'declared_array_payload_bytes')
    require(first['geometry'] == second['geometry'] and
            previous.original_images(run / 'slots' / a, 1) == previous.original_images(run / 'slots' / b, 1) and
            all(all(x[k] == y[k] for k in selected_keys)
                for x, y in zip(first['selected'], second['selected'], strict=True)) and
            all(all(x[k] == y[k] for k in buffer_keys)
                for x, y in zip(first['frames'], second['frames'], strict=True)),
            'paired_current_geometry_original_PNG_or_native_buffer_dimensions_changed')
    prediction_a, prediction_b = baseline['prediction'], candidate['prediction']
    require(prediction_a['geometry'] == prediction_b['geometry'] and
            prediction_a['normalized_full_sha256'] == prediction_b['normalized_full_sha256'] and
            all(prediction_a[key] == prediction_b[key] for key in ('geometry_identity', 'camera_identity')),
            'paired_full_prediction_semantics_or_camera_changed')
    builds = [baseline['global_index_builds_by_request'], candidate['global_index_builds_by_request']]
    require(builds == [[1, 0], [1, 0]], 'paired_global_index_reuse_changed')
    global_a, global_b = [row['timing']['global_index_ms'] for row in (first, second)]
    require(global_a > 0 and global_b > 0, 'cold_global_index_clock_missing')
    changes, byte_changes = {}, {}
    ignored_work = {*FRUSTUM_COUNTERS, 'NPZ_bytes'}
    for phase in PHASES:
        left, right = baseline[phase], candidate[phase]
        require({key: value for key, value in left['work'].items() if key not in ignored_work} ==
                {key: value for key, value in right['work'].items() if key not in ignored_work},
                'other_product_work_changed/' + phase)
        changes[phase] = {key: right['timing'][key] - value for key, value in left['timing'].items()
                          if key.endswith('_ms') and key != 'scoped_stages_ms'}
        byte_changes[phase] = {key: right['wire'][key] - left['wire'][key] for key in
                               ('rpc_bytes', 'public_text_bytes', 'public_png_bytes', 'producer_archive_bytes')}
        byte_changes[phase]['constructed_PNG_bytes'] = right['work']['PNG_bytes'] - left['work']['PNG_bytes']
        byte_changes[phase]['constructed_NPZ_bytes'] = right['work']['NPZ_bytes'] - left['work']['NPZ_bytes']
    return {'A': a, 'B': b, 'passed': True, 'global_index_builds_by_request_A_B': builds,
            'cold_global_index_A_B_ms': [global_a, global_b],
            'cold_global_index_percent_reduction': 100 * (global_a - global_b) / global_a,
            'prediction_normalized_full_sha256': prediction_a['normalized_full_sha256'],
            'selected_PNG_hashes': first['wire']['public_png_hashes'],
            'selected_NPZ_hashes_A_B': [[row['NPZ_sha256'] for row in phase['frames']] for phase in (first, second)],
            'sequence_window_A_B_ms': [baseline['sequence_window_ms'], candidate['sequence_window_ms']],
            'owned_window_A_B_ms': [baseline['owned_window_ms'], candidate['owned_window_ms']],
            'timing_candidate_minus_baseline_ms': changes, 'byte_candidate_minus_baseline': byte_changes,
            **{f'{key}_candidate_minus_baseline_ms': candidate[f'{key}_ms'] - baseline[f'{key}_ms']
               for key in ('sequence_window', 'sequence_rpc_sum', 'owned_window')}}


def compare_performance(pairs, quality, pair_count):
    if not quality:
        return {}, None, None
    medians = {}
    for phase in PHASES:
        measurements = [row['timing_candidate_minus_baseline_ms'][phase] for row in pairs]
        medians[phase] = {key: median(row[key] for row in measurements) for key in measurements[0]}
    for key in ('sequence_window', 'sequence_rpc_sum', 'owned_window'):
        medians[key] = median(row[f'{key}_candidate_minus_baseline_ms'] for row in pairs)
    reduction = median(row['cold_global_index_percent_reduction'] for row in pairs)
    passed = None if pair_count < 3 else (reduction >= MIN_INDEX_REDUCTION_PERCENT
                                         and medians['cold']['server_rpc_ms'] < 0)
    return medians, reduction, passed


def assess(run, request_path, prediction_path, pair_count):
    truth_path = prior.FORMAL / 'fixture/CURRENT_TRUTH.json'
    truth = json.loads(verified(truth_path, prior.TRUTH_SHA256, prior.FORMAL))
    request, prediction = read(request_path), read(prediction_path)
    query = {'mode': 'active_observation', 'region_task': {
        'area_min_m2': 0.0078125, 'area_max_m2': 0.03125, 'normal_z_min': 0.75}}
    require(request == {'include_image': True, 'response_detail': 'brief', 'query': query} and
            prediction == {'include_image': False, 'response_detail': 'full', 'query': query},
            'registered_exact_request_forms_required')
    installed = {'A': read(BASELINE), 'B': read(CANDIDATE)}
    require(installed['A']['source_sha256'] == BASELINE_SHA != installed['B']['source_sha256'],
            'registered_isolated_arm_sources_required')
    sys.path.insert(0, installed['A']['dependency_root'])
    freeze_sha = prior.digest((NS / 'FROZEN.json').read_bytes())
    order = prior.ORDER[:pair_count * 2]
    slots, pairs = {}, []
    for label in order:
        path = run / 'slots' / label
        try:
            slots[label] = assess_slot(path, label, (request, prediction), truth, installed, freeze_sha)
        except Exception as error:
            result = path / 'SLOT_RESULT.json'
            slots[label] = {'label': label, 'arm': label[0], 'status': 'failed' if path.exists() else 'unrun',
                            'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                            'slot_result_sha256': prior.digest(result.read_bytes()) if result.exists() else None}
    for number in range(1, pair_count + 1):
        a, b = slots[f'A{number}'], slots[f'B{number}']
        try:
            require(a['passed'] and b['passed'], 'incomplete_or_failed_original_pair')
            pairs.append(compare_pair(run, a, b))
        except Exception as error:
            pairs.append({'A': a['label'], 'B': b['label'], 'passed': False, 'error_type': type(error).__name__,
                          'error': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    nonoverlap = all(a['owned_awake_window'][1] <= b['owned_awake_window'][0]
                     for a, b in zip(complete, complete[1:]))
    quality = nonoverlap and all(row['passed'] for row in pairs)
    medians, reduction, gains = compare_performance(pairs, quality, pair_count)
    return {'schema': 'm4-cross-scale-cold-frustum-paired-review-v1',
            'passed': quality and (pair_count < 3 or gains is True), 'quality_passed': quality,
            'median_cold_index_and_RPC_gates_passed': gains,
            'cold_global_index_percent_reduction_threshold': MIN_INDEX_REDUCTION_PERCENT,
            'median_cold_global_index_percent_reduction': reduction,
            'registered_order': list(prior.ORDER), 'reviewed_slot_count': len(order),
            'attempted_slot_order': list(slots), 'closed_qualifying_slot_count': len(complete),
            'pair_denominator': 3, 'reviewed_pair_count': pair_count,
            'reviewed_passing_pairs': sum(row['passed'] for row in pairs), 'order_nonoverlap': nonoverlap,
            'model_consumers': 0, 'completed_verified_raster_attempts': sum(s['raster_attempts'] for s in complete),
            'completed_verified_business_attempts': sum(s['business_attempts'] for s in complete),
            'current_truth_sha256': prior.TRUTH_SHA256, 'freeze_sha256': freeze_sha,
            'request_sha256': prior.digest(request_path.read_bytes()),
            'prediction_request_sha256': prior.digest(prediction_path.read_bytes()),
            'median_candidate_minus_baseline_ms': medians, 'slots': list(slots.values()), 'pairs': pairs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--pairs', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--request', type=Path, default=NS / 'inputs/REQUEST.json')
    parser.add_argument('--prediction', type=Path, default=NS / 'inputs/PREDICTION.json')
    parser.add_argument('--output', type=Path, default=HERE / 'PAIR_REVIEW.json')
    options = parser.parse_args()
    result = assess(options.runtime, options.request, options.prediction, options.pairs)
    write(options.output, result)
    print(json.dumps({key: result[key] for key in ('passed', 'quality_passed', 'median_cold_index_and_RPC_gates_passed',
                      'median_cold_global_index_percent_reduction', 'median_candidate_minus_baseline_ms')} |
                     {'failed_slots': [row for row in result['slots'] if not row['passed']],
                      'failed_pairs': [row for row in result['pairs'] if not row['passed']]}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
