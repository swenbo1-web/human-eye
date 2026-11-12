"""Bind the saved-data review outputs and recompute the frozen primary gate."""

import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    cross = read(HERE / 'integrity/CROSS_REVIEW.json')
    assert cross['passed']
    for name, digest in cross['files_sha256'].items():
        assert sha(HERE / name) == digest, name
    seal = read(HERE / 'quality_source/QUALITY_SEAL.json')
    assert sha(HERE / 'quality_source/QUALITY_SEAL.json') == 'a493bd997b2003c595795ad90ae3bc9420e9a2a884a0adcf6225493f880f0c21'
    assert seal['quality']['complete_correct'] == 6
    assert seal['quality']['facts_correct'] == seal['quality']['facts_required'] == 78
    assert read(HERE / 'integrity/RESULTS.json')['passed']
    contract = read(HERE / 'integrity/CONTRACT_CHECK.json')
    assert contract['passed'] and contract['frozen_useful_benefit_gate']
    costs = read(HERE / 'cost/RESULTS.json')
    assert costs['gate']['passed']
    assert read(HERE / 'cost/BUDGETS.json')['passed']
    mechanism = read(HERE / 'mechanism/RESULTS.json')['mechanism_verdict']
    assert mechanism['passed']
    assert mechanism['eligible_P_consumers'] == mechanism['qualified_P_consumers'] == 3
    assert mechanism['P_engine_independent_complete_fact_responses'] == 3
    assert mechanism['P_native_calls'] == mechanism['P_native_recomputations_of_complete_facts'] == 0
    result = read(BATCH / 'RUN_RESULT.json')
    assert len(result['records']) == 6 and result['stop'] is None
    groups = {}
    for group in ('N', 'P'):
        rows = [row for row in result['records'] if row['group'] == group]
        assert len(rows) == 3
        assert all(row['consumer']['valid_completion'] and not row['errors'] for row in rows)
        groups[group] = {
            'complete_correct': 3,
            'median_full_cell_ns': statistics.median(row['full_cell_wall_ns'] for row in rows),
            'sum_input_plus_output_tokens': sum(row['consumer']['usage']['input_tokens']
                                                + row['consumer']['usage']['output_tokens'] for row in rows),
        }
        for key in ('median_full_cell_ns', 'sum_input_plus_output_tokens'):
            assert groups[group][key] == contract['groups'][group][key]
    n, p = groups['N'], groups['P']
    time_noninferior = p['median_full_cell_ns'] <= n['median_full_cell_ns']
    token_noninferior = p['sum_input_plus_output_tokens'] <= n['sum_input_plus_output_tokens']
    ten_percent = (10 * p['median_full_cell_ns'] <= 9 * n['median_full_cell_ns']
                   or 10 * p['sum_input_plus_output_tokens'] <= 9 * n['sum_input_plus_output_tokens'])
    passed = time_noninferior and token_noninferior and ten_percent
    assert passed
    summary = {
        'stage': 'M4-GROOVED-RAIL-TRANSFER-001_COST_REVIEW_READY',
        'author_evidence_commit': '4a90bbe95ef46c6666050ef1a1096fc6719c3b97',
        'quality_review_commit': 'e94798714d5d23694f0515f00e9eb083982a2b2f',
        'quality_seal_sha256': sha(HERE / 'quality_source/QUALITY_SEAL.json'),
        'original_data_index_sha256': sha(HERE / 'ORIGINAL_DATA_INDEX.json'),
        'groups': groups,
        'frozen_net_benefit_gate': passed,
        'full_cell_median_reduction_pct': 100 * (1 - p['median_full_cell_ns'] / n['median_full_cell_ns']),
        'input_plus_output_token_reduction_pct': 100 * (1 - p['sum_input_plus_output_tokens'] / n['sum_input_plus_output_tokens']),
        'natural_fact_consumption': {
            'successful_P_cells': mechanism['qualified_P_consumers'],
            'fixed_P_cells': mechanism['eligible_P_consumers'],
            'P_native_recomputation_calls': mechanism['P_native_recomputations_of_complete_facts'],
            'engine_independent_complete_responses': mechanism['P_engine_independent_complete_fact_responses'],
            'frozen_gate': mechanism['passed'],
        },
        'preserved_observations': {'invalid_nearest_witness_fact_requests': 1,
                                  'extra_closed_solid_unknown_facts': 0,
                                  'measured_closed_solid_facts': 9,
                                  'necessary_A_closed_work_units': 7854,
                                  'additional_BC_closed_classifications': 6,
                                  'additional_BC_closed_work_units': 15276,
                                  'product_internal_absolute_full_deadline': 'unexposed; local 30 s plus outer chain and native worker constraints',
                                  'thin_client_EXIT_receipt_unknown_cells': 6,
                                  'applicable_independent_process_exit_proofs_confirmed': True},
        'monetary_fees': None, 'monetary_fee_status': 'unmeasured',
        'derived_uncached_input_tokens': {'N': 21923, 'P': 31167},
        'same_value_relation_field_read_by_model': 'unmeasured',
        'new_consumer_Blender_product_runs': 0,
        'next_direction': 'Administrator-directed global candidate discovery, on-demand inspection and coverage stopping.',
        'completion_boundary': 'Cost-review callback and wait for administrator review.',
    }
    save(HERE / 'COST_REVIEW_READY.json', summary)
    paths = sorted((path for path in HERE.rglob('*') if path.is_file()),
                   key=lambda path: path.relative_to(HERE).as_posix())
    assert not any('__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo') for path in paths)
    save(HERE / 'REVIEW_MANIFEST.json', {
        'scope': 'All review files before this manifest, including COST_REVIEW_READY.json.',
        'files': [{'path': path.relative_to(HERE).as_posix(), 'bytes': path.stat().st_size,
                   'sha256': sha(path)} for path in paths],
    })
    print(json.dumps({'net_benefit_gate': passed, 'natural_fact_consumption': '3/3',
                      'review_files_indexed': len(paths)}))


if __name__ == '__main__':
    main()
