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
AUTHOR = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def budgets(row, checks):
    folder = BATCH / 'cells' / row['cell']
    launch = read(folder / 'ACTOR_LAUNCH.json')
    config = read(folder / 'ACTOR_CONFIG.json')
    endpoint = read(folder / 'ENDPOINT.json')
    consumer = read(folder / 'CONSUMER.json')
    native = read(folder / 'owner/native/CONFIG.json')
    session = read(folder / 'owner/native/SESSION.json')
    ready = read(folder / 'owner/native/READY.json')
    closed = read(folder / 'owner/native/WORKER_CLOSED.json')
    tools = read(folder / 'owner/TOOLS.json')
    deadline = row['cell_started_ns'] + 570 * 10**9
    prefix = row['cell'] + '_budget_'
    checks[prefix + 'full_origin_and_inheritance'] = (
        deadline == row['worker_deadline_ns'] == launch['worker_deadline_ns']
        == config['worker_deadline_ns'] == endpoint['chain_deadline_ns']
        == native['deadline_ns'] == session['deadline_ns'] == ready['deadline_ns']
        == closed['original_deadline_ns'])
    checks[prefix + 'full_actual_original_window'] = (
        row['full_cell_wall_ns'] == row['cell_ended_ns'] - row['cell_started_ns']
        and row['cell_ended_ns'] < deadline)
    actor_deadline = min(deadline, launch['prepare_started_ns'] + 40 * 10**9)
    checks[prefix + 'actor_startup_origin'] = actor_deadline == launch['actor_startup_deadline_ns']
    checks[prefix + 'actor_startup_observed_upper_bound'] = consumer['started_ns'] < actor_deadline
    checks[prefix + 'consumer_original_window'] = (
        consumer['deadline_ns'] == consumer['started_ns'] + 450 * 10**9
        and consumer['turn_completed_ns'] < consumer['deadline_ns']
        and consumer['process_exit_ns'] < consumer['deadline_ns']
        and not consumer['deadline_timer_fired'])
    events = [json.loads(line) for line in (folder / 'owner/native/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    requests = [event for event in events if 'sequence' in event]
    scripts = [event for event in requests if 'script_sha256' in event]
    checks[prefix + 'native_physical_sequence'] = (
        [event['sequence'] for event in requests] == list(range(1, len(requests) + 1))
        and len(requests) <= 128 and native['max_calls'] == session['max_calls'] == 128)
    checks[prefix + 'all_native_events_within_original_window'] = all(
        row['cell_started_ns'] <= event['started_ns']
        and event['started_ns'] + event['elapsed_ns'] < deadline for event in requests)
    code_sizes, stored_sizes = [], []
    source_matches = []
    for event in scripts:
        path = folder / ('owner/native/call_' + str(event['sequence'])) / 'SCRIPT.py'
        raw = path.read_bytes()
        normalized = path.read_text(encoding='utf8').encode('utf8')
        matching = raw if hashlib.sha256(raw).hexdigest() == event['script_sha256'] else normalized
        source_matches.append(hashlib.sha256(matching).hexdigest() == event['script_sha256'])
        code_sizes.append(len(matching))
        stored_sizes.append(len(raw))
    checks[prefix + 'all_executed_code_bound_to_events'] = all(source_matches)
    checks[prefix + 'all_executed_code_under_256KiB'] = all(size <= 262144 for size in code_sizes)
    directories = sorted(folder.glob('owner/tool_*'), key=lambda p: int(p.name.split('_')[1]))
    checks[prefix + 'all_attempts_charged_under_32'] = len(directories) == len(tools['tools']) == tools['attempts'] <= 32
    charged, peer_rows, native_receipts = [], [], []
    for directory, attempt in zip(directories, tools['tools'], strict=True):
        response_path = directory / 'RESPONSE.json'
        if not response_path.exists():
            response_path = directory / 'ERROR_RESPONSE.json'
        response = read(response_path)
        size = len(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')) + 1
        charged.append(size)
        checks[prefix + directory.name + '_response_charge'] = size == attempt['response_bytes']
        checks[prefix + directory.name + '_original_time'] = (
            row['cell_started_ns'] <= attempt['started_ns']
            and attempt['started_ns'] + attempt['elapsed_ns'] < deadline
            and attempt['started_ns'] + attempt['elapsed_ns'] < consumer['deadline_ns']
            and attempt['elapsed_ns'] < 30 * 10**9)
        request = read(directory / 'REQUEST.json')['params']
        if request['name'] == 'execute_blender_code':
            checks[prefix + directory.name + '_public_code_budget'] = len(request['arguments']['code'].encode('utf8')) <= 262144
        if (directory / 'NATIVE_RECEIPT.json').exists():
            native_receipts.append(read(directory / 'NATIVE_RECEIPT.json'))
    native_receipts.extend(read(folder / name) for name in ('owner/INITIAL.json.receipt.json', 'owner/FINAL.json.receipt.json'))
    checks[prefix + 'native_receipt_inheritance_and_30s'] = all(
        receipt['original_deadline_ns'] == deadline and receipt['elapsed_ns'] < 30 * 10**9 for receipt in native_receipts)
    checks[prefix + 'cumulative_responses_include_failure'] = sum(charged) == tools['wire_tool_bytes'] <= 1048576
    if row['group'] == 'P':
        cfg = read(folder / 'owner/product_config.json')
        peer_rows = read(folder / 'owner/plugin/RPC.json')['requests']
        traces = [json.loads(line)['trace'] for line in (folder / 'owner/audit.jsonl').read_bytes().splitlines()
                  if line and json.loads(line).get('event') == 'request_trace']
        active_traces = [trace for trace in traces if trace['operation'] != 'startup.service_construct']
        checks[prefix + 'product_config_30s'] = cfg['request_budget_s'] == cfg['blender']['timeout_s'] == 30
        checks[prefix + 'peer_observed_windows'] = all(
            row['cell_started_ns'] <= rpc['started_ns']
            and rpc['started_ns'] + rpc['elapsed_ns'] < deadline
            and rpc['elapsed_ns'] < 30 * 10**9 for rpc in peer_rows)
        entered_service = [trace for trace in active_traces
                           if any(span['name'] == 'service.observe' for span in trace['spans'])]
        rejected_before_service = [trace for trace in active_traces if trace not in entered_service]
        checks[prefix + 'product_observed_durations_and_budget_annotation'] = all(
            trace['duration_ns'] < 30 * 10**9
            and trace['annotations'].get('request_budget_s') == 30 for trace in entered_service)
        rejection_checks = []
        for trace in rejected_before_service:
            request_id = trace['annotations']['mcp_request_id']
            for directory in directories:
                if read(directory / 'REQUEST.json')['id'] != request_id:
                    continue
                response = read(directory / 'RESPONSE.json')['result']
                body = json.loads(response['content'][0]['text'])
                rejection_checks.append(body.get('executed') is False
                    and body.get('execution_status') == 'not_executed'
                    and body.get('host_mutation_started') is False
                    and trace['duration_ns'] < 30 * 10**9
                    and not any(span['name'].startswith(('host.', 'service.')) for span in trace['spans']))
        checks[prefix + 'rejections_remain_outside_service_with_actual_bounded_peer'] = (
            len(rejection_checks) == len(rejected_before_service) and all(rejection_checks))
    unknown_events = [event['sequence'] for event in requests if event['status'] == 'unknown']
    return {'cell': row['cell'], 'group': row['group'], 'full_cell_origin_ns': row['cell_started_ns'],
        'full_cell_deadline_ns': deadline, 'full_cell_elapsed_ns': row['full_cell_wall_ns'],
        'actor_prepare_origin_ns': launch['prepare_started_ns'], 'actor_startup_deadline_ns': actor_deadline,
        'readiness_upper_bound_consumer_start_ns': consumer['started_ns'],
        'consumer_origin_ns': consumer['started_ns'], 'consumer_deadline_ns': consumer['deadline_ns'],
        'consumer_process_exit_ns': consumer['process_exit_ns'],
        'attempt_count': tools['attempts'], 'response_budget_bytes': sum(charged),
        'maximum_actor_handler_ns': max(a['elapsed_ns'] for a in tools['tools']),
        'native_sequenced_requests_including_close': len(requests), 'native_execute_requests': len(scripts),
        'native_unknown_event_sequences': unknown_events, 'maximum_executed_code_bytes': max(code_sizes),
        'maximum_stored_script_file_bytes': max(stored_sizes), 'product_peer_requests': len(peer_rows),
        'native_call_limit_scope': 'Worker checks 128 on non-close requests; close branch precedes that guard. Actual sequence including close is checked separately.',
        'product_deadline_observability': 'Original absolute full-cell deadline is recorded throughout the native chain. Product traces expose a cooperative local 30s budget and observed duration, not every internal absolute deadline.'}


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
    budget_rows = []
    for row in run['records']:
        budget_rows.append(budgets(row, checks))
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
        'budget_rows': budget_rows,
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
