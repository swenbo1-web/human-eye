"""Root recomputation of frozen six-slot gates after the quality seal."""

import hashlib
import json
from pathlib import Path
import statistics
import time
import tomllib


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_target_consume_001')
ORDER = ['N1', 'P1', 'P2', 'N2', 'N3', 'P3']
PINS = {}


def raw(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    PINS[str(path)] = dict(path=str(path), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    return blob


def read(path):
    return json.loads(raw(path))


def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()


def need(value, label):
    if not value:
        raise ValueError(label)


def verify_pins(rows):
    for row in rows:
        blob = raw(row['path'])
        need(hashlib.sha256(blob).hexdigest() == row['sha256']
             and ('bytes' not in row or len(blob) == row['bytes']), 'reviewed_input_changed/' + row['path'])


def collect(slot, quality):
    folder = RUNTIME / 'formal' / slot
    result = read(folder / 'SLOT_RESULT.json')
    publication = read(folder / 'SLOT_PUBLICATION.json')
    consumer = read(folder / 'consumer/CONSUMER.json')
    timing = read(folder / 'consumer/FINAL_TIMING.json')
    metrics = read(folder / 'owner/METRICS.json')
    tools = read(folder / 'owner/TOOLS.json')
    stdout = raw(folder / 'consumer/stdout.raw.bin')
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    completed = [event for event in events if event.get('type') == 'turn.completed']
    threads = [event['thread_id'] for event in events if event.get('type') == 'thread.started']
    need(len(completed) == len(threads) == 1 and threads[0] == consumer['thread_id'], slot + '/fresh_single_turn')
    usage = completed[0]['usage']
    need(consumer['raw_usage_events'] == consumer['usage_rows'] == [usage]
         and consumer['usage'] == usage, slot + '/raw_usage_projection')
    need(all(type(value) is int and value >= 0 for value in usage.values()), slot + '/raw_nonnegative_usage')
    need(usage['cached_input_tokens'] <= usage['input_tokens']
         and usage['reasoning_output_tokens'] <= usage['output_tokens'], slot + '/usage_subsets')
    need(publication['result_sha256'] == sha(folder / 'SLOT_RESULT.json'), slot + '/result_publication')
    started = publication['slot_started_ns']
    closed = publication['slot_result_published_ns']
    need(publication['complete_slot_ns'] == closed-started
         and result['clocks']['slot_started_ns'] == started
         and result['clocks']['consumer_deadline_ns'] == started+450_000_000_000
         and result['clocks']['owned_deadline_ns'] == started+600_000_000_000, slot + '/original_root_window')
    need(started <= timing['started_ns'] <= timing['consumer_record_closed_ns'] <= closed
         and timing['consumer_record_closed_ns'] < started+450_000_000_000
         and closed < started+600_000_000_000, slot + '/complete_cost_window')
    need(consumer['stdout_raw_sha256'] == hashlib.sha256(stdout).hexdigest(), slot + '/actual_stdout')
    need(consumer['model'] == 'gpt-6.1-sol' and consumer['requested_effort'] == 'medium'
         and consumer['expected_thread_id'] is None and consumer['turn_index'] == 1, slot + '/fixed_profile')
    argv = consumer['argv']
    need(sha(argv[0]) == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6', slot + '/fixed_actual_CLI')
    settings = [argv[index+1] for index, value in enumerate(argv) if value == '-c'
                and not argv[index+1].startswith('mcp_servers.arm_engine=')]
    need(len(settings) == len(set(value.split('=', 1)[0] for value in settings)), slot + '/unique_CLI_overrides')
    profile = tomllib.loads('\n'.join(settings))
    need([argv[index+1] for index, value in enumerate(argv) if value == '-m'] == ['gpt-6.1-sol']
         and profile['model'] == 'gpt-6.1-sol' and profile['model_reasoning_effort'] == 'medium'
         and profile['service_tier'] == 'default', slot + '/actual_CLI_model_effort_tier')
    settings_sha = hashlib.sha256(json.dumps(settings, separators=(',', ':')).encode()).hexdigest()
    need(metrics['tool_attempts'] == tools['calls'] == len(tools['tools']) == len(consumer['tool_calls']), slot + '/tool_count')
    content = metrics['public_content']
    return dict(slot_id=slot, group=slot[0], execution_state=publication['status'],
        quality_passed=quality['final_quality_passed'],
        adopted=quality['adoption']['actual_product_facts_adopted'],
        complete_slot_ns=closed-started, consumer_complete_ns=timing['full_turn_wall_ns'],
        prompt_to_final_ns=consumer['prompt_to_final_ns'],
        business_service_ns=sum(row['elapsed_ns'] for row in tools['tools']),
        owner_RPC_all_exchange_ns=sum(row['closed_ns']-row['started_ns'] for row in metrics['transport']),
        raw_usage=usage, raw_input_plus_output=usage['input_tokens']+usage['output_tokens'],
        uncached_input_tokens=usage['input_tokens']-usage['cached_input_tokens'],
        thread_id=threads[0], business_tools=tools['calls'],
        common_CLI_settings_sha256=settings_sha, resolved_effort=consumer['resolved_effort'],
        CLI_exit_code=consumer['exit_code'], thin_adapter_exit_code=consumer['runtime_exit']['exit_code'],
        thin_adapter_exit_confirmed=consumer['runtime_exit']['confirmed'],
        thin_adapter_EXIT_receipt_status=consumer['bridge_cleanup']['receipt_status'],
        business_tool_errors=sum(row['is_error'] for row in tools['tools']),
        delivered_tool_text_UTF8_bytes=sum(row['text_UTF8_bytes'] for row in content),
        delivered_image_blocks=sum(row['image_blocks'] for row in content),
        delivered_PNG_bytes=sum(row['PNG_bytes'] for row in content),
        delivered_base64_chars=sum(row['base64_chars'] for row in content),
        delivered_image_JSON_bytes=sum(row['image_block_JSON_bytes'] for row in content),
        actual_response_envelope_bytes=sum(row['response_bytes'] for row in tools['tools']),
        assistant_public_UTF8_bytes=consumer['public_text_bytes'],
        final_UTF8_bytes=consumer['output_text_bytes'],
        provider_requests=consumer['provider_requests'], fees=consumer['fees'], image_tokens=consumer['image_tokens'],
        consumer_reported_usage_semantics=consumer['usage_semantics'],
        usage_comparison_scope='One raw terminal CLI usage event per distinct fresh thread, same fixed binary/settings, no cross-turn summation or billing inference.')


def main():
    started = time.perf_counter_ns()
    seal = read(HERE / 'QUALITY_SEAL.json')
    quality = read(HERE / 'QUALITY.json')
    need(seal['cost_unlocked'] is True and seal['sealed_ns'] < started
         and seal['quality_sha256'] == sha(HERE / 'QUALITY.json'), 'quality_first_seal')
    need(quality['denominator'] == 6 and quality['cost_analysis_performed'] is False, 'six_original_quality')
    need([row['slot_id'] for row in quality['slots']] == ORDER
         and all(row['group'] == row['slot_id'][0] for row in quality['slots']), 'six_unique_original_quality_rows')
    verify_pins([dict(path=path, sha256=digest) for path, digest in quality['inputs_sha256'].items()])
    need(seal['semantic_review_sha256'] == sha(HERE / 'admin/SEMANTIC_REVIEW.json')
         and seal['normalized_sha256'] == sha(HERE / 'admin/NORMALIZED.json')
         and seal['scoring_source_sha256'] == sha(HERE / 'score_saved_R1.py'), 'sealed_quality_source_chain')
    plan = read(HERE / 'PLAN.json')
    run = read(RUNTIME / 'RUN_RESULT.json')
    formal_start = read(RUNTIME / 'FORMAL_STARTED.json')
    frozen = read(HERE / 'FROZEN.json')
    need(sha(HERE / 'PLAN.json') == run['plan_sha256'] == formal_start['plan_sha256']
         and sha(HERE / 'FROZEN.json') == run['frozen_sha256'] == formal_start['freeze_sha256'], 'original_frozen_formal_inputs')
    verify_pins(frozen['files'])
    audit = read(HERE / 'RUNTIME_REVIEW.json')
    need(audit['passed_checked_scope'] is True and audit['qualification_only'] is False, 'closed_runtime_source_budget_audit')
    verify_pins(audit['input_pins'])
    need([row['slot_id'] for row in run['records']] == ORDER
         and run['actual_consumers'] == run['consumer_attempts'] == 6
         and run['outer_retries'] == run['replacement_samples'] == 0, 'one_original_six_slot_batch')
    rows = [collect(slot, next(row for row in quality['slots'] if row['slot_id'] == slot)) for slot in ORDER]
    need(len({row['thread_id'] for row in rows}) == 6, 'six_distinct_fresh_consumers')
    need(len({row['common_CLI_settings_sha256'] for row in rows}) == 1, 'identical_common_CLI_settings')
    pairs = []
    for index in range(1, 4):
        native = next(row for row in rows if row['slot_id'] == 'N' + str(index))
        product = next(row for row in rows if row['slot_id'] == 'P' + str(index))
        pairs.append(dict(pair=index, N_complete_ns=native['complete_slot_ns'],
            P_complete_ns=product['complete_slot_ns'], P_over_N=product['complete_slot_ns']/native['complete_slot_ns'],
            P_faster=product['complete_slot_ns'] < native['complete_slot_ns'],
            both_quality_passed=native['quality_passed'] and product['quality_passed']))
    totals = {}
    total_fields = ('complete_slot_ns', 'consumer_complete_ns', 'prompt_to_final_ns', 'business_service_ns',
        'business_tools', 'business_tool_errors', 'raw_input_plus_output', 'uncached_input_tokens',
        'delivered_tool_text_UTF8_bytes', 'delivered_image_blocks', 'delivered_PNG_bytes',
        'delivered_base64_chars', 'delivered_image_JSON_bytes', 'actual_response_envelope_bytes',
        'assistant_public_UTF8_bytes', 'final_UTF8_bytes')
    for group in ('N', 'P'):
        selected = [row for row in rows if row['group'] == group]
        totals[group] = {key: sum(row[key] for row in selected) for key in total_fields}
        totals[group]['raw_usage'] = {key: sum(row['raw_usage'][key] for row in selected) for key in selected[0]['raw_usage']}
    ratio = statistics.median(row['P_over_N'] for row in pairs)
    gates = dict(N_complete_correct=quality['N_quality_count'] == 3,
        P_complete_correct=quality['P_quality_count'] == 3,
        P_actual_adoption=quality['P_actual_product_fact_adoption_count'] == 3,
        same_source_comparable_usage=True,
        complete_time_paired_median=ratio <= plan['decision_gate']['complete_time_paired_median_max'],
        P_faster_pairs=sum(row['P_faster'] for row in pairs) >= plan['decision_gate']['P_faster_pairs_min'],
        P_total_raw_input_plus_output=totals['P']['raw_input_plus_output'] <= totals['N']['raw_input_plus_output'])
    passed = all(gates.values())
    preparation = read(HERE / 'fixtures/DEVICE_PREPARATION.json')
    root_time = read(HERE / 'BASELINE.json')['started_ns']
    own_sha = sha(Path(__file__))
    need(all(Path(row['path']).stat().st_size == row['bytes']
             and hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256'] for row in PINS.values()),
         'decision_inputs_unchanged')
    output = dict(schema='target-task-consumption-decision-v1', passed_frozen_gates=passed,
        disposition='finite_routed_task_positive_signal' if passed else 'frozen_finite_task_gate_not_met',
        quality_sha256=seal['quality_sha256'], quality_seal_sha256=sha(HERE / 'QUALITY_SEAL.json'),
        decision_source_sha256=own_sha, cost_analysis_started_ns=started, decision_closed_ns=time.perf_counter_ns(),
        rows=rows, pairs=pairs, totals=totals, gates=gates,
        complete_time_paired_median_P_over_N=ratio,
        complete_time_paired_median_reduction=1-ratio,
        total_raw_input_plus_output_reduction=1-totals['P']['raw_input_plus_output']/totals['N']['raw_input_plus_output'],
        quality_advantage_observed=False, original_formal_order=ORDER, formal_attempts=1, outer_retries=0, replacement_samples=0,
        runtime_budget=audit['budget'], shared_device_preparation_ns=preparation['elapsed_ns'],
        formal_batch_wall_ns=run['closed_ns']-run['started_ns'],
        preparation_through_formal_launch_ns=run['started_ns']-root_time,
        postformal_through_decision_ns=time.perf_counter_ns()-run['closed_ns'],
        limitations=[
            'One explicit-target asset, fixed six-view device and routed first product call, three consumers per workflow.',
            'Native baseline can use ordinary code, persistent variables, NumPy/PIL/Fraction/Shapely and precomputed raw device matrices. Product still builds its own cameras.',
            'N3 private-attribute query was rejected and recovered. All attempts, image constructions and deliveries remain included. No counterfactual subtraction.',
            'All six CLI parents exited 0. Their held thin Python adapters exited 1 with missing EXIT receipts. Actual adapter exit and handle closure are confirmed, and the cause remains unestablished.',
            'P1 repeats delivery of a cached image. P2 additionally reads raw target geometry. Supplement necessity remains unknown.',
            'Raw input includes cached input. Cached and reasoning subsets are reported separately and never added twice. Monetary fees, image tokens and internal provider request count remain unmeasured.',
            'Service, all owner RPC exchanges, consumer and complete-slot clocks have distinct boundaries. Final publication marker I/O is outside the complete-slot endpoint.',
            'Only task-window costs drive the frozen workflow gate. Whole project preparation/qualification/review costs remain separately recorded, with agent/reviewer provider usage unmeasured.',
            'Population tails, natural tool selection, general assets, arbitrary views, independent repetitions and causal contributions of individual optimizations remain unmeasured.'
        ], input_pins=sorted(PINS.values(), key=lambda row: row['path']))
    with (HERE / 'DECISION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=passed, median_P_over_N=ratio,
        raw_input_plus_output= {group: value['raw_input_plus_output'] for group, value in totals.items()})))


if __name__ == '__main__':
    main()
