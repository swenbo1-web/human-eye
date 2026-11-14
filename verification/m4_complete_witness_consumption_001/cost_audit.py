"""Report one closed experiment only after its quality and adoption are sealed."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_complete_witness_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owner_details(output):
    output = Path(output)
    observation_path = output / 'OBSERVATIONS.json'
    metrics_path = output / 'METRICS.json'
    if not observation_path.is_file() or not metrics_path.is_file():
        return dict(status='unavailable', output=str(output))
    observations = read(observation_path)
    metrics = read(metrics_path)
    attempts = observations['render_attempts']
    files = [path for path in output.rglob('*') if path.is_file() and path.suffix.lower() in ('.png', '.npz')]
    return dict(status='recorded', output=str(output), actual_raster_attempts=len(attempts),
                rasters_by_view=dict(Counter(row['view_name'] for row in attempts)),
                rasters_by_origin=dict(Counter(row['origin'] for row in attempts)),
                calls_by_tool=dict(Counter(row['name'] for row in metrics['tools'])),
                cache_requests=observations.get('cache_requests', []),
                failed_attempts=[row for row in attempts if row['status'] != 'completed'],
                physical_image_files=[dict(path=str(path), bytes=path.stat().st_size) for path in files],
                actual_owner_metrics=metrics,
                input_hashes={str(observation_path): sha(observation_path), str(metrics_path): sha(metrics_path)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quality-seal', type=Path, required=True)
    args = parser.parse_args()
    seal = read(args.quality_seal)
    for path, expected in seal['files_sha256'].items():
        if sha(path) != expected:
            raise ValueError('sealed_quality_changed:' + path)
    qualification_path = HERE / 'admin/QUALIFICATION.json'
    qualification_run_path = RUNTIME / 'preparation/Q1/QUALIFICATION_RUN.json'
    qualification = read(qualification_path)
    qualification_run = read(qualification_run_path)
    qualification_owner = owner_details(RUNTIME / 'preparation/Q1/o')
    launch_path = RUNTIME / 'formal/RUN_RESULT.json'
    formal = dict(status='not_run', qualification_admitted=qualification['status'] == 'qualified',
                  reason='No formal launch result was produced.')
    if launch_path.is_file():
        launch = read(launch_path)
        records = launch['records']
        if len(records) > 1:
            raise ValueError('single_formal_consumer_contract')
        formal = dict(status=launch['execution_state'], launcher_succeeded=launch['launcher_succeeded'],
                      terminal_errors=launch['terminal_errors'], actual_routes=launch['actual_routes'],
                      actual_CLI_processes=launch['actual_CLI_processes'], launch_sha256=sha(launch_path))
        timing_path = RUNTIME / 'formal/LAUNCH_TIMING.json'
        formal['launch_timing'] = read(timing_path) if timing_path.is_file() else None
        if records:
            row = records[0]
            formal.update(slot_timing=row.get('slot_timing'), route_timing=row.get('final_timing'),
                          actual_tool_calls=row.get('actual_tool_calls'),
                          raw_CLI_usage_events=row.get('raw_usage_events', []),
                          actual_CLI_image_count=row.get('public_image_count'),
                          actual_CLI_image_bytes=row.get('public_image_bytes'),
                          owner=owner_details(row['owner_output']) if row.get('owner_output') else None,
                          actor_cleanup=row.get('owner_process_cleanup'),
                          CLI_cleanup=row.get('consumer_process_cleanup'),
                          bridge_cleanup=row.get('bridge_cleanup'),
                          actual_consumer_pid=row.get('consumer_pid'),
                          observed_thread_id=row.get('observed_thread_id'))
            events = row.get('raw_usage_events', [])
            formal['single_event_raw_input_plus_output'] = None
            if len(events) == 1 and all(type(events[0].get(key)) is int for key in ('input_tokens', 'output_tokens')):
                formal['single_event_raw_input_plus_output'] = events[0]['input_tokens'] + events[0]['output_tokens']
            formal['usage_scope'] = 'Raw CLI counters for this one turn. Scope within the provider is unconfirmed. Cached-input and reasoning-output subsets are retained separately.'
    intents = [read(path) for path in sorted((RUNTIME / 'raster_budget').glob('attempt_*/INTENT.json'))]
    if ([row['global_attempt'] for row in intents] != list(range(1, len(intents) + 1))
            or len(intents) > 12):
        raise ValueError('shared_twelve_attempt_ledger')
    phase_counts = Counter(row['phase'] for row in intents)
    if set(phase_counts) - {'preparation', 'formal'} or any(value > 6 for value in phase_counts.values()):
        raise ValueError('qualification_and_formal_six_attempt_phases')
    result = dict(schema='complete-witness-single-experiment-cost-v1',
                  quality_seal_path=str(args.quality_seal.resolve()), quality_seal_sha256=sha(args.quality_seal),
                  qualification_status=qualification['status'],
                  qualification_run=dict(path=str(qualification_run_path), sha256=sha(qualification_run_path),
                      started_ns=qualification_run['started_ns'], closed_ns=qualification_run['closed_ns'],
                      elapsed_ns=qualification_run['elapsed_ns'],
                      original_deadline_ns=qualification_run['original_deadline_ns'],
                      actual_model_calls=qualification_run['actual_model_calls'],
                      actual_product_calls=qualification_run['actual_product_calls'],
                      actual_rasters=qualification_run['actual_rasters'],
                      transport_passed=qualification_run['transport_passed'],
                      process_cleanup=qualification_run['process_cleanup']),
                  qualification_owner=qualification_owner,
                  formal=formal, total_actual_raster_attempts=len(intents), raster_attempts_by_phase=dict(phase_counts),
                  source_inputs_sha256={str(qualification_path): sha(qualification_path),
                                        str(qualification_run_path): sha(qualification_run_path)},
                  comparison_scope='One formal P consumer at most, after one zero-model qualification.',
                  provider_requests=None, image_tokens=None, cash_cost=None,
                  speed_or_cost_saving_estimate=None,
                  limits=['No N comparison in this experiment.',
                          'Raw CLI usage remains distinct from provider-request, image-token and monetary accounting.',
                          'Preparation, slot wrapper, route and launch clocks retain their original boundaries.'])
    with (HERE / 'COST.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(total_rasters=len(intents), phase_counts=dict(phase_counts), formal_status=formal['status'])))


if __name__ == '__main__':
    main()
