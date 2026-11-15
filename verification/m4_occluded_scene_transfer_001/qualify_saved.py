"""Judge the sole saved pair and publish N-frame pixel truth offline."""

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_occluded_transfer_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def module(name):
    spec = importlib.util.spec_from_file_location('_qualification_' + name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def check_owner(record, manifest):
    group = record['group']
    folder = EXTERNAL / 'preparation' / ('Q' + group)
    owner = folder / 'o'
    require(record == read(folder / 'QUALIFICATION_RUN.json'), 'pair_owner_record_binding')
    require(record['transport_passed'] is True and not record['errors'], 'actual_owner_transport')
    require(record['actual_model_calls'] == 0 and record['outer_retries'] == 0, 'zero_model_or_retry')
    require(record['actual_product_calls'] == int(group == 'P'), 'one_P_product_call')
    require(record['actual_business_tools'] == 2 and record['actual_MCP_requests'] == 4
            and record['successful_MCP_responses'] == 4, 'actual_qualification_request_counts')
    require(type(record['actual_rasters']) is int and 1 <= record['actual_rasters'] <= 6,
            'qualification_per_owner_six_raster_cap')
    require(record['started_ns'] < record['closed_ns'] < record['original_deadline_ns'], 'owner_original_deadline')
    require(Path(record['owner_output']).resolve() == owner.resolve(), 'actual_owner_directory')
    pid = record['actor_pid']
    process, close = record['process_cleanup'], record['owner_close']
    require(process['pid'] == pid and process['confirmed'] is True and process['reaped'] is True
            and process['process_handle_closed'] is True and process['exit_code'] == 0
            and process['kill_requested'] is False and not process['errors']
            and all(process['pipes_closed'].get(k) is True for k in ('stdin', 'stdout', 'stderr')),
            'qualification_held_process_cleanup')
    require(close == read(owner / 'CLOSE.json') and close['actor_pid'] == pid
            and close['confirmed'] is True and close['server_thread_stopped'] is True and not close['errors'],
            'qualification_service_close')
    config = read(folder / 'ACTOR_CONFIG.json')
    require(config['group'] == group and config['phase'] == 'preparation'
            and config['phase_render_cap'] == 12 and config['whole_render_cap'] == 48
            and config['max_render_attempts'] == 6 and config['max_tool_calls'] == 12
            and config['worker_deadline_ns'] == record['original_deadline_ns'], 'actual_owner_configuration')
    metrics = read(owner / 'METRICS.json')
    observations = read(owner / 'OBSERVATIONS.json')
    require(observations['process_id'] == pid and observations['group'] == group
            and metrics['tool_attempts'] == 2 and metrics['common']['render_attempts'] == record['actual_rasters'],
            'actual_owner_metrics')
    before = read(folder / 'METRICS_BEFORE_REPEAT.json')['common']
    require(before['render_attempts'] == metrics['common']['render_attempts'], 'repeat_without_new_raster')
    repeat = read(owner / 'tool_02/RESPONSE.json')
    require(repeat['result']['isError'] is False, 'repeat_public_tool_success')
    repeat_frames = observations['cache_requests'][-1]['frames']
    require(len(repeat_frames) == 1 and repeat_frames[0]['cached'] is True
            and repeat_frames[0]['new_raster_attempts'] == 0, 'actual_repeat_cached_frame')
    for i in range(1, 5):
        request = read(folder / ('request_' + str(i).zfill(2)) / 'TCP_TX.bin')
        response = read(folder / ('request_' + str(i).zfill(2)) / 'TCP_RX.bin')
        require(request['request_id'] == i and response['request_id'] == i and response['ok'] is True,
                'actual_socket_request_identity')
        require(response['result'] == read(folder / ('MCP_RESPONSE_' + str(i).zfill(2) + '.json')),
                'saved_public_response_identity')
        require((folder / ('request_' + str(i).zfill(2)) / 'TCP_RX.bin').read_bytes()
                == (owner / ('rpc_' + str(i).zfill(3)) / 'TCP_RX.bin').read_bytes(), 'actual_socket_reply_bytes')
    for name in ('scene', 'capture', 'cameras', 'product_binding'):
        require(observations['source_inputs'][name + '_sha256'] == manifest[name]['sha256'],
                'actual_owner_source_binding_' + name)
    return owner, observations


def main():
    started = time.perf_counter_ns()
    output = HERE / 'admin/QUALIFICATION.json'
    pixel_output = HERE / 'admin/PIXEL_TRUTH.json'
    require(not output.exists() and not pixel_output.exists(), 'qualification_outputs_exclusive')
    result = dict(schema='occluded-transfer-qualification-v1', passed=False, status='evidence_failed',
                  errors=[], actual_model_calls=0, actual_product_calls=None, actual_rasters=None,
                  source_freeze_sha256=sha(HERE / 'FROZEN.json'), started_ns=started,
                  qualification_run=dict(path=str(EXTERNAL / 'preparation/QUALIFICATION_RUN.json'), sha256=None))
    evidence = None
    try:
        frozen = read(HERE / 'FROZEN.json')
        for path, expected in frozen['files_sha256'].items():
            require(sha(path) == expected, 'frozen_source_changed_' + path)
        truth = read(HERE / 'admin/TRUTH.json')
        manifest = read(HERE / 'inputs/SOURCES.json')
        run = read(result['qualification_run']['path'])
        result['qualification_run']['sha256'] = sha(result['qualification_run']['path'])
        require(run['schema'] == 'occluded-transfer-paired-qualification-run-v1'
                and run['transport_passed'] is True and not run['errors'] and run['outer_retries'] == 0,
                'actual_pair_transport')
        require(run['source_freeze_sha256'] == result['source_freeze_sha256'], 'qualification_source_freeze')
        require(run['actual_owners'] == 2 and [r['group'] for r in run['records']] == ['N', 'P']
                and run['actual_model_calls'] == 0 and run['actual_product_calls'] == 1,
                'single_actual_pair_counts')
        for path, expected in run['source_inputs_sha256'].items():
            require(frozen['files_sha256'].get(path) == expected and sha(path) == expected,
                    'actual_source_closure')
        result.update(actual_product_calls=run['actual_product_calls'], actual_rasters=run['actual_rasters'])
        evidence = module('saved_evidence')
        measured, observations = {}, {}
        for record in run['records']:
            owner, observation = check_owner(record, manifest)
            observations[record['group']] = observation
            measured[record['group']] = evidence.evaluate_owner(owner, truth)
        native = measured['N']
        require(len(native['frames']) == 6 and {f['view_name'] for f in native['frames']} == set(truth['view_names']),
                'actual_native_six_view_pool')
        by_view = {f['view_name']: f for f in native['frames']}
        sets = {v: {r['roi_id'] for r in f['rows'] if r['complete_readable']} for v, f in by_view.items()}
        union = set().union(*sets.values())
        minimum_cover = next((count for count in range(1, 7) if any(
            set().union(*(sets[v] for v in group)) == union
            for group in itertools.combinations(truth['view_names'], count))), None)
        reasons = {}
        for region in truth['regions']:
            rows = [r for f in native['frames'] for r in f['rows'] if r['roi_id'] == region['roi_id']]
            reasons[region['roi_id']] = evidence.unknown_reason(region, rows)
        targets = []
        samples = read(HERE / 'inputs/TASK_INPUTS.json')['pixel_samples']
        expected_targets = {r['id']: r for r in truth['pixel_targets']}
        for sample in samples:
            f = by_view[sample['view_name']]
            require(type(sample['x']) is int and type(sample['y']) is int
                    and 0 <= sample['x'] < 512 and 0 <= sample['y'] < 512, 'registered_pixel_coordinate')
            actual = f['raw_region_by_pixel'][sample['y'] * 512 + sample['x']]
            expected = expected_targets[sample['id']]
            targets.append(dict(**sample, expected_region_id=expected['region_id'], actual_region_index=actual,
                                expected_region_index=expected['region_index'], passed=actual == expected['region_index']))
        scene_partial = sorted(r['roi_id'] for r in by_view['SCENE']['rows']
                               if r['readable'] and not r['complete'] and r['roi_id'] in union)
        conditions = dict(minimum_three_view_cover=minimum_cover is not None and minimum_cover >= 3,
                          scene_partial_readable_with_full_witness=bool(scene_partial),
                          positive_but_occluded_unknown='positive_area_occlusion_all_front_views' in reasons.values(),
                          no_front_candidate_unknown='no_front_facing_candidate' in reasons.values(),
                          both_registered_pixels_on_expected_support=len(targets) == 2 and all(t['passed'] for t in targets))
        pixel = dict(schema='occluded-transfer-independent-pixel-truth-v1',
                     source_freeze_sha256=result['source_freeze_sha256'], geometric_truth_sha256=sha(HERE / 'admin/TRUTH.json'),
                     qualification_run=result['qualification_run'], actual_native_owner_pid=native['actual_owner_pid'],
                     frames=[dict(view_name=f['view_name'], image_ref=f['image_ref'], rows=f['rows']) for f in native['frames']],
                     native_frame_descriptors=observations['N']['frames'],
                     complete_readable_roi_ids=sorted(union), remaining_roi_ids=sorted(set(reasons) - union),
                     remaining_reasons={r: reasons[r] for r in sorted(set(reasons) - union)}, pixel_targets=targets,
                     minimum_view_cover=minimum_cover, complete_readable_sets={v: sorted(s) for v, s in sets.items()},
                     scene_partial_readable_region_ids=scene_partial, conditions=conditions,
                     origin='Derived once from actual qualification N six saved raw/RGB frames using preregistered code.')
        save(pixel_output, pixel)
        result.update(pixel_truth=dict(path=str(pixel_output), sha256=sha(pixel_output)), conditions=conditions,
                      independent_native=evidence.summary(native), independent_product=evidence.summary(measured['P']))
        if measured['P']['product_errors']:
            result['status'] = 'product_incorrect'
        elif not all(conditions.values()):
            result['status'] = 'not_realized'
        else:
            result.update(status='qualified', passed=True)
        intents = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
        require(len(intents) == run['actual_rasters'] <= 12
                and [r['global_attempt'] for r in intents] == list(range(1, len(intents) + 1)), 'actual_global_ledger_prefix')
        for row in intents:
            group = row['group']
            require(row['phase'] == 'preparation' and row['process_id'] == measured[group]['actual_owner_pid']
                    and row['source_scene_sha256'] == manifest['scene']['sha256']
                    and row['source_capture_sha256'] == manifest['capture']['sha256'], 'actual_ledger_owner_binding')
    except Exception as error:
        factual_error = evidence is not None and isinstance(error, getattr(evidence, 'ProductFactError', ()))
        result.update(passed=False, status='product_incorrect' if factual_error else 'evidence_failed')
        result['errors'].append(dict(type=type(error).__name__, message=str(error)))
    result['before_publication_ns'] = time.perf_counter_ns()
    result['offline_analysis_elapsed_ns'] = result['before_publication_ns'] - started
    save(output, result)
    print(json.dumps({k: result[k] for k in ('passed', 'status', 'actual_rasters', 'errors')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
