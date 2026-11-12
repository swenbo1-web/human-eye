"""Check installed request work, cache separation and owned lifecycle records."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    run = HERE / 'run_01'
    result = json.loads((run / 'RESULTS.json').read_bytes())
    rows = result['business']
    assert [row['request']['id'] for row in rows] == [
        'directory', 'spatial_assembly_task', 'legacy_assembly_task', 'spatial_control_task']
    task_events = {event['trace_id']: event['task_work'] for event in result['audit']
                   if event.get('event') == 'observe' and 'task_work' in event}
    checked = []
    for row in rows[1:]:
        work = task_events[row['body']['trace_id']]
        assert work['result_cache_hit'] is False
        if row['request']['id'] == 'legacy_assembly_task':
            assert work['closed_solid_pair_count'] == 3
            assert all(pair['closed_solid_work']['work_units'] == 262144 for pair in work['pairs'])
            assert all(pair['surface_pair_cache_hit'] is False for pair in work['pairs'])
        else:
            expected = [512, 288, 288] if row['request']['id'] == 'spatial_assembly_task' else [16]
            assert work['closed_solid_pair_count'] == 0 and work['spatial_pair_cache_hits'] == 0
            assert len(work['pairs']) == len(expected)
            for pair, count in zip(work['pairs'], expected):
                support = pair['support_work']
                assert pair['closed_solid_pair_count'] == 0 and pair['closed_solid_work'] == {}
                assert support['support_source_vertices'] == support['support_vertex_dots'] == count
                assert support['support_direction_components'] == 3
                assert support['work_units_after'] - support['work_units_before'] == 2 * count + 3
        checked.append({'request_id': row['request']['id'], 'work': work})
    snapshot = run / 'ACTUAL_SNAPSHOT.json'
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == '29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c'
    bindings = json.loads((run / 'INPUT_BINDINGS.json').read_bytes())
    asset = bindings['asset_manifest']
    assert hashlib.sha256(Path(asset['asset']).read_bytes()).hexdigest() == asset['asset_sha256']
    business_ns = sum(row['tool_ns'] for row in rows)
    stage_ns = sum(result['timing_stages_ns'].values())
    verification = {
        'passed': True, 'source_sha256': bindings['ready']['source_sha256'],
        'requests': checked, 'new_spatial_work_and_zero_closed_verified': True,
        'new_request_preceded_legacy': True, 'cross_semantic_memo_prewarming_absent': True,
        'actual_snapshot_and_asset_hashes_verified': True,
        'business_complete_calls_ns': [row['tool_ns'] for row in rows],
        'business_sum_ns': business_ns, 'owned_session_ns': result['session_wall_ns'],
        'session_unallocated_ns': result['session_wall_ns'] - business_ns - stage_ns,
        'scope_counts': result['scope_counts'], 'product_calls_in_this_check': 0,
        'scope': 'saved audit counts with source-bound installed results; separate six-call spies cover internal function entries',
    }
    with (run / 'COUNTER_VERIFICATION.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(verification, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'new_closed_calls': 0, 'legacy_closed_calls': 3,
                      'session_unallocated_ns': verification['session_unallocated_ns']}))


if __name__ == '__main__':
    main()
