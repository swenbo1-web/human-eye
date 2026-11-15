"""Independently judge one saved A/B qualification against its frozen source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_source_face_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load(name):
    spec = importlib.util.spec_from_file_location('_m1_qualification_' + name, HERE / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def check_owner(record, manifest, attempt_root):
    arm = record['comparison_arm']
    folder = attempt_root / ('Q' + arm)
    owner = folder / 'o'
    require(record == read(folder / 'QUALIFICATION_RUN.json'), 'pair_owner_record_binding')
    require(record['transport_passed'] is True and not record['errors'], 'actual_owner_transport')
    require(record['actual_model_calls'] == 0 and record['outer_retries'] == 0, 'zero_model_or_retry')
    require(record['actual_product_calls'] == 1, 'one_P_product_call')
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
    require(config['group'] == 'P' and config['comparison_arm'] == arm and config['phase'] == 'preparation'
            and config['phase_render_cap'] == 12 and config['whole_render_cap'] == 48
            and config['max_render_attempts'] == 6 and config['max_tool_calls'] == 12
            and config['worker_deadline_ns'] == record['original_deadline_ns'], 'actual_owner_configuration')
    require(Path(config['input_manifest']).resolve() == Path(record['input_manifest']['path']).resolve()
            and config['expected_product_source_sha256'] == record['product_source_sha256'],
            'actual_owner_manifest_and_product_configuration')
    metrics = read(owner / 'METRICS.json')
    observations = read(owner / 'OBSERVATIONS.json')
    require(observations['process_id'] == pid and observations['group'] == 'P'
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    require(len(args.attempt) == 3 and args.attempt[0] == 'Q' and args.attempt[1:].isdigit(), 'qualification_attempt_Qnn')
    attempt_root = EXTERNAL / 'preparation' / args.attempt
    output = HERE / 'admin/qualification' / (args.attempt + '.json')
    require(not output.exists(), 'saved_qualification_judgment_is_exclusive')
    started = time.perf_counter_ns()
    run_path = attempt_root / 'QUALIFICATION_RUN.json'
    result = dict(schema='source-face-binding-qualification-v1', passed=False, status='evidence_failed',
        errors=[], attempt=args.attempt, source_freeze_sha256=sha(HERE / 'FROZEN.json'),
        qualification_run=dict(path=str(run_path), sha256=sha(run_path)), actual_model_calls=0,
        started_ns=started)
    evidence = None
    try:
        frozen = read(HERE / 'FROZEN.json')
        for path, digest in frozen['files_sha256'].items():
            require(sha(path) == digest, 'frozen_source_changed_' + path)
        plan = read(HERE / 'PLAN.json')
        run = read(run_path)
        require(run['schema'] == 'source-face-binding-paired-qualification-run-v1'
                and run['transport_passed'] is True and not run['errors']
                and run['source_freeze_sha256'] == result['source_freeze_sha256'], 'actual_qualified_pair_source_and_transport')
        require(len(run['records']) == 2 and [r['comparison_arm'] for r in run['records']] == ['A', 'B']
                and all(r['group'] == 'P' for r in run['records']) and run['actual_model_calls'] == 0,
                'one_actual_A_B_pair_no_models')
        require(run['planned_owners'] == run['actual_owners'] == 2 and run['outer_retries'] == 0,
                'actual_pair_denominator_and_retry_count')
        for path, digest in run['source_inputs_sha256'].items():
            require(frozen['files_sha256'].get(path) == digest and sha(path) == digest, 'actual_source_closure')
        truth = read(HERE / 'admin/TRUTH.json')
        evidence = load('saved_evidence')
        measured, observations = {}, {}
        for record in run['records']:
            arm = record['comparison_arm']
            manifest = read(plan['inputs']['manifests'][arm])
            require(record['input_manifest']['path'] == plan['inputs']['manifests'][arm]
                    and record['input_manifest']['sha256'] == sha(plan['inputs']['manifests'][arm]), 'owner_manifest_arm_identity')
            binding = read(manifest['product_binding']['path'])
            require(record['product_source_sha256'] == binding['source_sha256'], 'actual_installed_candidate_identity')
            owner, observation = check_owner(record, manifest, attempt_root)
            observations[arm] = observation
            measured[arm] = evidence.evaluate_owner(owner, truth)
            require(measured[arm]['comparison_arm'] == arm, 'independent_owner_arm_binding')
        product_errors = {arm: m['product_errors'] for arm, m in measured.items() if m['product_errors']}
        if product_errors:
            result.update(status='product_incorrect', product_errors=product_errors)
        else:
            require(not measured['A']['source_face_binding_delivered']
                    and measured['B']['source_face_binding_delivered']
                    and measured['B']['source_face_binding_checked_regions'] == len(truth['regions']), 'default_B_source_binding_delivered')
            a, b = measured['A'], measured['B']
            require(a['independent_covered_roi_ids'] == b['independent_covered_roi_ids']
                    and a['independent_remaining_roi_ids'] == b['independent_remaining_roi_ids'], 'same_actual_complete_readable_sets')
            by_view = {arm: {f['view_name']: f for f in frames['frames']} for arm, frames in measured.items()}
            require(set(by_view['A']) == set(by_view['B']), 'same_actual_view_selection')
            for view, frame in by_view['A'].items():
                other = by_view['B'][view]
                require(frame['rows'] == other['rows'] and frame['raw_region_by_pixel'] == other['raw_region_by_pixel'],
                        'same_actual_per_view_region_and_pixel_facts_' + view)
            descriptors = {arm: {f['view_name']: f for f in o['frames']} for arm, o in observations.items()}
            for view, frame in descriptors['A'].items():
                other = descriptors['B'][view]
                require(frame['PNG_sha256'] == other['PNG_sha256'], 'same_actual_image_bytes_' + view)
                for name in ('color', 'depth', 'owners', 'triangle_ids'):
                    require(frame['arrays'][name]['sha256'] == other['arrays'][name]['sha256'], 'same_actual_array_' + view + '_' + name)
            result.update(passed=True, status='qualified', view_names=sorted(by_view['A']))
        intents = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
        require(len(intents) <= 12 and [r['global_attempt'] for r in intents] == list(range(1, len(intents)+1))
                and all(r['phase'] == 'preparation' for r in intents), 'persistent_cumulative_qualification_cap')
        for record in run['records']:
            owned = [r for r in intents if r['process_id'] == record['actor_pid']
                     and r['owner_output'] == record['owner_output']]
            require(len(owned) == record['actual_rasters'],
                    'actual_durable_raster_owner_binding')
        require(run['cumulative_preparation_rasters'] == len(intents), 'actual_cumulative_qualification_count')
        result.update(actual_product_calls=sum(r['actual_product_calls'] for r in run['records']),
            actual_rasters=sum(r['actual_rasters'] for r in run['records']), cumulative_qualification_rasters=len(intents),
            owners={arm: evidence.summary(value) for arm, value in measured.items()},
            prior_pixel_truth_reference_sha256=sha(HERE / 'admin/PIXEL_TRUTH.json'))
    except Exception as error:
        factual = evidence is not None and isinstance(error, evidence.ProductFactError)
        result.update(passed=False, status='product_incorrect' if factual else 'evidence_failed')
        result['errors'].append(dict(type=type(error).__name__, message=str(error)))
    result['before_publication_ns'] = time.perf_counter_ns()
    result['offline_analysis_elapsed_ns'] = result['before_publication_ns'] - started
    save(output, result)
    if result['passed']:
        save(HERE / 'admin/QUALIFICATION.json', result)
    print(json.dumps({k: result.get(k) for k in ('passed', 'status', 'actual_rasters', 'cumulative_qualification_rasters', 'errors')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
