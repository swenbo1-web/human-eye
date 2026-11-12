"""Recompute fixed planned denominators and preregistered paired gates offline."""
import json
from pathlib import Path
import statistics
import time

from common import QUAL
from verify_state import object_ids

STATES = ('cold', 'repeat', 'edit')


def rows_from_sequences(sequences):
    rows = []
    for index in range(1, 6):
        for version in ('A', 'B'):
            sequence = sequences.get((index, version))
            for state in STATES:
                matching = [] if sequence is None else [row for row in sequence.get('business', []) if row.get('state') == state]
                status = ('not_attempted' if not matching else 'duplicate' if len(matching) != 1 else
                    'failed' if matching[0].get('errors') or not matching[0].get('verification', {}).get('passed') else 'passed')
                rows.append({'pair': index, 'version': version, 'state': state, 'status': status})
    return rows


def reuse_mapping(sequence):
    cold = next(row for row in sequence['business'] if row['state'] == 'cold')
    edit = next(row for row in sequence['business'] if row['state'] == 'edit')
    ids = object_ids(json.loads((QUAL/'EDIT_SNAPSHOT.json').read_bytes()))
    old_pairs = cold['diagnostics']['pairs']
    result = []
    for key, work in edit['diagnostics']['pairs'].items():
        pair = json.loads(key)
        assert all(oid in ids for oid in pair)
        changed = any(ids[oid] == 'Obj_008' for oid in pair)
        previous = old_pairs.get(key)
        hit = work.get('surface_dependency_cache_hit') is True
        current_key = work.get('surface_dependency_key')
        previous_key = None if previous is None else previous.get('surface_dependency_key')
        result.append({'object_ids': pair, 'object_names': [ids[oid] for oid in pair],
                       'changed_endpoint': changed, 'cache_hit': hit,
                       'cold_key': previous_key, 'edit_key': current_key,
                       'cold_object_dependencies': None if previous is None else previous.get('surface_dependency_objects'),
                       'edit_object_dependencies': work.get('surface_dependency_objects')})
        assert work.get('surface_dependency_used') is True
        assert current_key
        if changed:
            assert not hit and (previous_key is None or current_key != previous_key)
        else:
            assert hit and current_key == previous_key
    assert len(result) == 114
    assert sum(row['changed_endpoint'] for row in result) == 10
    assert sum(row['cache_hit'] for row in result) == 104
    return result


def summarize(folder):
    folder = Path(folder)
    sequences = {}
    for index in range(1, 6):
        for version in ('A', 'B'):
            path = folder/('pair_'+str(index).zfill(2))/version/'RESULTS.json'
            if path.exists():
                sequences[index, version] = json.loads(path.read_bytes())
    planned = rows_from_sequences(sequences)
    result = {'planned_business_rows': planned, 'planned_business_count': 30,
        'actual_business_rows': sum(len(seq.get('business', [])) for seq in sequences.values()),
        'missing': sum(row['status'] == 'not_attempted' for row in planned),
        'duplicates': sum(row['status'] == 'duplicate' for row in planned),
        'failed': sum(row['status'] == 'failed' for row in planned),
        'quality_passed': all(row['status'] == 'passed' for row in planned)
            and len(sequences) == 10 and all(seq.get('passed') and
                [row['state'] for row in seq['business']] == list(STATES) for seq in sequences.values()),
        'gates': {}, 'all_gates_passed': False, 'reuse_mapping': {},
        'timing_scope': 'client wall includes Peer evidence I/O; server trace includes wire and stdio; lifecycle includes prepare, QA, quality and close, ending before final RESULTS serialization/write',
        'reuse_mapping_validation_ns': {}}
    if not result['quality_passed']:
        return result
    expected_orders = ['AB','BA','AB','BA','AB']
    result['actual_pair_orders'] = [''.join(sorted(('A','B'),
        key=lambda version: sequences[i,version]['started_ns'])) for i in range(1,6)]
    result['order_passed'] = result['actual_pair_orders'] == expected_orders
    business = {(i, version, row['state']): row for (i, version), seq in sequences.items() for row in seq['business']}
    try:
        for i in range(1, 6):
            mark = time.perf_counter_ns()
            result['reuse_mapping'][str(i)] = reuse_mapping(sequences[i, 'B'])
            result['reuse_mapping_validation_ns'][str(i)] = time.perf_counter_ns()-mark
            for version in ('A', 'B'):
                expected = (112, 0, 114) if version == 'A' else (112, 0, 10)
                for state, calls in zip(STATES, expected):
                    row = business[i, version, state]
                    assert row['diagnostics']['kernel_calls'] == calls
                    assert row['actual_host_RPC'] == 1
                    delta = row['diagnostics']['acquisition_work']['residency_delta']
                    if state == 'edit':
                        assert delta['resource_vertices_read'] == 0 and delta['world_vertices_transformed'] == 8
                    if version == 'B':
                        stats = row['diagnostics']['measurement_cache_after']
                        assert stats['max_bytes'] == 2*1024*1024
                        assert stats['accounted_bytes'] <= stats['max_bytes']
                        assert row['diagnostics']['measurement_cache_max_measurements'] == 256
                        assert stats['measurement_entries'] <= 256
        result['mechanism_passed'] = True
    except (AssertionError, KeyError, StopIteration, TypeError) as error:
        result['mechanism_passed'] = False
        result['mechanism_error'] = repr(error)
    times = {}
    for state in STATES:
        old = [business[i, 'A', state]['complete_client_request_ns']/1e6 for i in range(1, 6)]
        new = [business[i, 'B', state]['complete_client_request_ns']/1e6 for i in range(1, 6)]
        ratios = [b/a for a,b in zip(old,new)]
        deltas = [b-a for a,b in zip(old,new)]
        times[state] = {'old_ms': old, 'new_ms': new, 'paired_ratios': ratios,
            'median_ratio': statistics.median(ratios), 'paired_delta_ms': deltas,
            'median_delta_ms': statistics.median(deltas)}
        if state == 'edit':
            gate = statistics.median(ratios) <= .70
            limit = .70
        else:
            limit = max(.05*statistics.median(old), 2.)
            gate = statistics.median(deltas) <= limit
        result['gates'][state] = {'passed': gate, 'limit': limit}
    sums = [[sum(business[i, version, state]['complete_client_request_ns'] for state in STATES)
             for i in range(1,6)] for version in ('A','B')]
    sums_ratios = [b/a for a,b in zip(*sums)]
    life = [[sequences[i, version]['session_wall_ns'] for i in range(1,6)] for version in ('A','B')]
    life_ratios = [b/a for a,b in zip(*life)]
    result['paired_request_costs'] = times
    result['business_sum_ratios'] = sums_ratios
    result['lifecycle_ratios'] = life_ratios
    result['lifecycle_old_ns'], result['lifecycle_new_ns'] = life
    result['gates']['business_sum'] = {'passed': statistics.median(sums_ratios) < 1, 'median_ratio': statistics.median(sums_ratios), 'exclusive_limit': 1}
    result['gates']['lifecycle'] = {'passed': statistics.median(life_ratios) <= 1.05, 'median_ratio': statistics.median(life_ratios), 'limit': 1.05}
    result['all_gates_passed'] = result['order_passed'] and result['mechanism_passed'] and all(gate['passed'] for gate in result['gates'].values())
    result['lifecycle_net_improvement'] = statistics.median(life_ratios) < 1
    return result
