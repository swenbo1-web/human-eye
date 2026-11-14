"""Recompute the fixed acceptance decision from closed, original samples."""

import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_view_reuse_001/run')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cost_path = RUNTIME / 'benchmark_01/COST_RESULT.json'
    integration_path = RUNTIME / 'integration_01/INTEGRATION_RESULT.json'
    cost = read(cost_path)
    integration = read(integration_path)
    assert cost['passed'] and integration['passed']
    assert len(cost['samples']) == 10 and len(cost['pairs']) == 5
    assert integration['actual_rasters'] == 13 and cost['actual_rasters'] == 45
    expected_order = ['old', 'new', 'new', 'old', 'old', 'new', 'new', 'old', 'old', 'new']
    assert [row['variant'] for row in cost['samples']] == expected_order
    pairs = []
    all_sources_match = cost['runtime_sources'] == integration['runtime_sources']
    assert all_sources_match
    for block in range(1, 6):
        arms = {row['variant']: row for row in cost['samples'] if row['block'] == block}
        values = {}
        for variant, sample in arms.items():
            worker = sample['worker']
            assert sample['passed'] and worker['passed']
            assert sample['process_id'] == worker['process_id']
            assert sample['process_cleanup']['confirmed'] and sample['process_cleanup']['exit_code'] == 0
            assert worker['owner_close']['confirmed']
            assert len(worker['requests']) == 4
            assert all(row['local_socket_confirmed'] and not row['is_error'] for row in worker['requests'])
            expected_rasters = 6 if variant == 'old' else 3
            assert worker['owner_close']['metrics']['common']['render_attempts'] == expected_rasters
            values[variant] = [row['closed_ns'] - worker['started_ns'] for row in worker['requests']]
            for key, index in [('first', 0), ('first_plus_one_repeat', 1), ('first_plus_three_repeats', 3)]:
                assert worker['checkpoints'][key]['elapsed_ns'] == values[variant][index]
        differences = [new - old for old, new in zip(values['old'], values['new'])]
        break_even = next((index for index, delta in enumerate(differences) if delta < 0), None)
        pairs.append(dict(block=block, old_cumulative_ns=values['old'], new_cumulative_ns=values['new'],
                          differences_new_minus_old_ns=differences, observed_first_profitable_repeat_count=break_even))
    checkpoints = {}
    for key, index in [('first', 0), ('first_plus_one_repeat', 1), ('first_plus_three_repeats', 3)]:
        old = [row['old_cumulative_ns'][index] for row in pairs]
        new = [row['new_cumulative_ns'][index] for row in pairs]
        ratios = [b / a for a, b in zip(old, new)]
        differences = [b - a for a, b in zip(old, new)]
        reported = cost['summary'][key]
        assert reported['old_raw_ns'] == old and reported['new_raw_ns'] == new
        assert reported['old_sum_ns'] == sum(old) and reported['new_sum_ns'] == sum(new)
        checkpoints[key] = dict(old_raw_ns=old, new_raw_ns=new,
            old_median_ns=statistics.median(old), new_median_ns=statistics.median(new),
            paired_difference_median_ns=statistics.median(differences),
            paired_ratio_median=statistics.median(ratios),
            paired_reduction_median=1 - statistics.median(ratios),
            old_sum_ns=sum(old), new_sum_ns=sum(new),
            new_faster_pairs=sum(value < 0 for value in differences),
            new_slower_pairs=sum(value > 0 for value in differences))
    sample_details = []
    for row in cost['samples']:
        worker = row['worker']
        metrics = worker['owner_close']['metrics']
        snapshots = [request['snapshot'] for request in worker['requests']]
        sample_details.append(dict(name=row['name'], variant=row['variant'],
            parent_elapsed_ns=row['elapsed_ns'], worker_elapsed_ns=worker['elapsed_ns'],
            first_unique_array_bytes=snapshots[0]['memory']['unique_array_payload_bytes'],
            final_unique_array_bytes=snapshots[-1]['memory']['unique_array_payload_bytes'],
            first_raw_array_bytes=snapshots[0]['memory']['raw_buffer_unique_bytes'],
            final_raw_array_bytes=snapshots[-1]['memory']['raw_buffer_unique_bytes'],
            first_NPZ_bytes=snapshots[0]['owner_metrics']['NPZ_bytes'],
            final_NPZ_bytes=metrics['common']['NPZ_bytes'], final_PNG_bytes=metrics['common']['PNG_bytes'],
            delivered_image_blocks=metrics['server_socket_sent_image_blocks'],
            delivered_PNG_bytes=metrics['server_socket_sent_PNG_bytes'],
            delivered_outer_wire_bytes=metrics['server_socket_sent_outer_TCP_JSON_bytes'],
            repeated_request_elapsed_ns=[request['elapsed_ns'] for request in worker['requests'][1:]]))
    focused = read(HERE / 'product_checks_01/RESULT.json')
    final_no_ref = read(HERE / 'no_ref_after_02/RESULT.json')
    assert focused['passed'] and focused['actual_raster_calls'] == 19
    assert final_no_ref['passed'] and final_no_ref['units']['passed']
    assert final_no_ref['units']['tests_run'] == 31
    assert final_no_ref['actual_product_raster_calls'] == 0
    assert final_no_ref['actual_direct_raster_calls'] == 0
    decision = dict(schema='view-reuse-root-decision-v1',
        registered_mechanical_gate_passed=True,
        registered_repeated_workflow_cost_gate_passed=checkpoints['first_plus_three_repeats']['new_sum_ns'] < checkpoints['first_plus_three_repeats']['old_sum_ns'],
        repeated_workflow_all_five_pairs_faster=checkpoints['first_plus_three_repeats']['new_faster_pairs'] == 5,
        all_five_pairs_profitable_after_one_repeat=checkpoints['first_plus_one_repeat']['new_faster_pairs'] == 5,
        checkpoints=checkpoints, pairs=pairs, samples=sample_details,
        exact_rasters=dict(focused=19, installed_integration=13, paired_measurement=45, total=77),
        registered_case_denominator=12, model_sessions=0,
        inputs_sha256={str(cost_path): sha(cost_path), str(integration_path): sha(integration_path),
                      str(HERE / 'product_checks_01/RESULT.json'): sha(HERE / 'product_checks_01/RESULT.json'),
                      str(HERE / 'no_ref_after_02/RESULT.json'): sha(HERE / 'no_ref_after_02/RESULT.json')},
        source_scope='The focused19 matrix precedes the narrowly audited fallback-reference correction. Final installed integration uses the final source and installation. Saved-array fallback checks and final31 mocked tests add zero raster calls.',
        limits=['Fixed source and six registered512 cameras in the versioned consumer.',
                'Local service, actual local byte delivery and observable array payload only.',
                'RSS, allocator peak, model latency, token usage and cash savings are unmeasured.',
                'Fresh processes and application caches; operating-system file caches were not flushed.'])
    with (HERE / 'DECISION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(decision, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(mechanical=True, repeated_cost=decision['registered_repeated_workflow_cost_gate_passed'],
                         total_rasters=77, paired_reduction=checkpoints['first_plus_three_repeats']['paired_reduction_median'])))


if __name__ == '__main__':
    main()
