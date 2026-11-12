"""Independently reconstruct frozen cost and request-use facts from saved data."""

import argparse
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess


HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
BATCH = REVIEW.parent
ROOT = BATCH.parents[1]
AUTHOR = '5cdf62f311f94890ca569d06c1a858f1578225e4'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='CONTRACT_CHECK.json')
    args = parser.parse_args()
    assert Path(args.output).name == args.output and not (HERE / args.output).exists()
    run = read(BATCH / 'RUN_RESULT.json')
    seal = read(REVIEW / 'quality_source/QUALITY_SEAL.json')
    checks = {}
    by_group = {'N': [], 'P': []}
    request_facts = []
    for row in run['records']:
        folder = BATCH / 'cells' / row['cell']
        consumer = read(folder / 'CONSUMER.json')
        event_usage = []
        for raw in (folder / 'events.jsonl').read_bytes().splitlines():
            if not raw:
                continue
            event = json.loads(raw)['event']
            if event.get('type') == 'turn.completed' and isinstance(event.get('usage'), dict):
                event_usage.append(event['usage'])
        usage = event_usage[-1]
        checks[row['cell'] + '_final_cumulative_usage_binding'] = usage == consumer['usage'] and event_usage == consumer['usage_rows']
        checks[row['cell'] + '_full_cell_timing_binding'] = row['full_cell_wall_ns'] == consumer['total_task_wall_ns'] == row['cell_ended_ns'] - row['cell_started_ns']
        checks[row['cell'] + '_finite_nonnegative_usage'] = all(type(usage.get(key)) is int and usage[key] >= 0 for key in ('input_tokens', 'output_tokens'))
        checks[row['cell'] + '_provider_cached_subset'] = 'cached_input_tokens' not in usage or 0 <= usage['cached_input_tokens'] <= usage['input_tokens']
        by_group[row['group']].append({'cell': row['cell'], 'full_cell_ns': row['full_cell_wall_ns'],
            'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
            'cached_input_tokens': usage.get('cached_input_tokens'),
            'input_plus_output_tokens': usage['input_tokens'] + usage['output_tokens']})
        if row['group'] == 'P':
            names, engine_calls = [], []
            for directory in sorted(folder.glob('owner/tool_*'), key=lambda path: int(path.name.split('_')[1])):
                request = read(directory / 'REQUEST.json')['params']
                names.append(request['name'])
                if request['name'] == 'human_eye_scene_observe':
                    response_path = directory / 'RESPONSE.json'
                    if not response_path.exists():
                        response_path = directory / 'ERROR_RESPONSE.json'
                    response = read(response_path)['result']
                    query = request['arguments'].get('query', {})
                    facts = query.get('requested_facts', [])
                    engine_calls.append({'attempt': int(directory.name.split('_')[1]),
                        'requested_spatial_and_surface': {'spatial_relation', 'surface_proximity'} <= set(facts),
                        'requested_facts': facts, 'protocol_is_error': bool(response.get('isError'))})
            request_facts.append({'cell': row['cell'], 'engine_calls': engine_calls,
                'successful_engine_responses': sum(not call['protocol_is_error'] for call in engine_calls),
                'failed_engine_attempts': sum(call['protocol_is_error'] for call in engine_calls),
                'native_tool_called': 'execute_blender_code' in names,
                'successful_requested_pair': any(call['requested_spatial_and_surface'] and not call['protocol_is_error'] for call in engine_calls)})
    summaries = {}
    for group, cells in by_group.items():
        summaries[group] = {'cells': len(cells), 'median_full_cell_ns': median(cell['full_cell_ns'] for cell in cells),
            'sum_input_plus_output_tokens': sum(cell['input_plus_output_tokens'] for cell in cells),
            'provider_cached_input_tokens_sum': None if any(cell['cached_input_tokens'] is None for cell in cells)
                else sum(cell['cached_input_tokens'] for cell in cells), 'raw_cell_values': cells}
    n, p = summaries['N'], summaries['P']
    time_gain = Fraction(n['median_full_cell_ns'] - p['median_full_cell_ns'], n['median_full_cell_ns'])
    token_gain = Fraction(n['sum_input_plus_output_tokens'] - p['sum_input_plus_output_tokens'], n['sum_input_plus_output_tokens'])
    quality_pass = seal['quality']['complete_correct'] == 6 and seal['quality']['facts_correct'] == seal['quality']['facts_required'] == 78
    cost_gate = quality_pass and all(summary['cells'] == 3 for summary in summaries.values())
    cost_gate = cost_gate and p['median_full_cell_ns'] <= n['median_full_cell_ns']
    cost_gate = cost_gate and p['sum_input_plus_output_tokens'] <= n['sum_input_plus_output_tokens']
    cost_gate = cost_gate and (time_gain >= Fraction(1, 10) or token_gain >= Fraction(1, 10))

    ledger = read(REVIEW / 'STAGE_LEDGER.json')
    full_sum = sum(row['full_cell_wall_ns'] for row in run['records'])
    formal = ledger['formal_six_consumers']
    checks['stage_formal_batch'] = formal['batch_wall_s'] == run['batch_wall_ns'] / 1e9
    checks['stage_formal_cell_sum'] = formal['sum_full_cell_wall_s'] == full_sum / 1e9
    checks['stage_formal_outside_cell_accounting'] = formal['batch_outside_cells_s'] == (run['batch_wall_ns'] - full_sum) / 1e9
    prep = read(BATCH / 'PREPARATION_COST.json')
    prep_delta = datetime.fromisoformat(prep['freeze_utc']) - datetime.fromisoformat(prep['recorded_start_utc'])
    prep_seconds = prep_delta.days * 86400 + prep_delta.seconds + prep_delta.microseconds / 1e6
    checks['stage_preparation_window_separate'] = ledger['preparation']['recorded_wall_window_s'] == prep_seconds and ledger['preparation']['amortized_into_query_cost'] is False
    ready = read(BATCH / 'installations/P_READY.json')
    checks['stage_historical_install_not_recharged'] = ledger['historical_installation']['recorded_historical_installation_s'] == ready['elapsed_ns'] / 1e9 and ledger['historical_installation']['charged_again_as_current_build'] is False
    checks['stage_unexposed_costs_remain_null'] = formal['monetary_fees'] is None and ledger['preparation']['coordinator_model_cost'] is None and ledger['saved_data_cost_review']['coordinator_and_review_model_cost'] is None
    source_index = read(REVIEW / 'ORIGINAL_DATA_INDEX.json')
    prefix = BATCH.relative_to(ROOT).as_posix() + '/'
    tree_raw = subprocess.run(['git', '-C', str(ROOT), 'ls-tree', '-r', '-z', AUTHOR, '--', prefix], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    tree = {}
    for raw in tree_raw.split(b'\0'):
        if raw:
            metadata, name = raw.split(b'\t', 1)
            tree[name.decode('utf8')] = metadata.decode('ascii').split()[2]
    checks['all_original_index_entries_match_author_tree'] = tree == {row['path']: row['git_blob'] for row in source_index['original_batch_files']}
    checks['all_original_index_bytes_still_match'] = all(sha(ROOT / row['path']) == row['sha256'] and (ROOT / row['path']).stat().st_size == row['bytes'] for row in source_index['original_batch_files'])
    output = {'passed': all(checks.values()), 'checks': checks, 'groups': summaries,
        'median_full_cell_reduction_ratio': str(time_gain), 'median_full_cell_reduction_percent': float(time_gain * 100),
        'input_plus_output_reduction_ratio': str(token_gain), 'input_plus_output_reduction_percent': float(token_gain * 100),
        'frozen_useful_benefit_gate': cost_gate, 'quality_source': 'sealed six complete-correct answers, no rescore',
        'P_request_facts': request_facts, 'P_successful_spatial_surface_requests': sum(row['successful_requested_pair'] for row in request_facts),
        'P_native_tool_calling_cells': sum(row['native_tool_called'] for row in request_facts),
        'mechanism_scope': 'request/response and absence-of-native facts only; semantic task-use judgment is reviewed separately',
        'provider_cached_input_tokens_scope': 'subset already included in input_tokens; no monetary conversion or product-cache inference',
        'result_source_sha256': {'RUN_RESULT.json': sha(BATCH / 'RUN_RESULT.json'), 'STAGE_LEDGER.json': sha(REVIEW / 'STAGE_LEDGER.json'),
            'QUALITY_SEAL.json': sha(REVIEW / 'quality_source/QUALITY_SEAL.json'), 'ORIGINAL_DATA_INDEX.json': sha(REVIEW / 'ORIGINAL_DATA_INDEX.json')},
        'checker_sha256': sha(Path(__file__)), 'new_consumer_Blender_product_runs': 0}
    with (HERE / args.output).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': output['passed'], 'frozen_useful_benefit_gate': cost_gate,
        'P_successful_spatial_surface_requests': output['P_successful_spatial_surface_requests'],
        'P_native_tool_calling_cells': output['P_native_tool_calling_cells'], 'original_files_modified': 0}))


if __name__ == '__main__':
    main()
