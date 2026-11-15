"""Root recomputation of the fixed M5 engineering gates from closed originals."""

import hashlib
import json
from pathlib import Path
import statistics
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_observe_measure_001')
MAIN = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
CONTROLS = ['A_task_only', 'B_task_only']
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    INPUTS[str(path)] = dict(path=str(path), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    return blob


def read(path):
    return json.loads(raw(path))


def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()


def need(value, label):
    if not value:
        raise ValueError(label)


def pins(rows):
    for row in rows:
        blob = raw(row['path'])
        need(hashlib.sha256(blob).hexdigest() == row['sha256']
             and ('bytes' not in row or len(blob) == row['bytes']), 'changed reviewed input ' + row['path'])


def collect(label, record, quality, gate, contracts):
    folder = RUNTIME / 'formal' / label
    need(Path(record['output']).resolve() == folder.resolve(), label + '/registered_slot_path')
    result = read(folder / 'RESULT.json')
    publication = read(folder / 'PUBLICATION.json')
    need(result['label'] == record['label'] == label and result['phase'] == 'formal', label + '/slot_identity')
    need(result['source_sha256'] == gate[label[0] + '_binding']['source_sha256'], label + '/fixed_source')
    need(publication['result_sha256'] == sha(folder / 'RESULT.json'), label + '/original_publication')
    started, closed = result['started_ns'], publication['result_published_ns']
    need(publication['complete_session_ns'] == closed-started
         and result['original_owned_deadline_ns'] == started+600_000_000_000
         and closed < result['original_owned_deadline_ns'], label + '/complete_original_window')
    windows = result['business_windows']
    need(len(windows) == 1 and windows[0]['label'] == 'main', label + '/single_registered_business_window')
    window = windows[0]
    need(window['continuous_business_ns'] == window['completed_ns']-window['started_ns']
         and started <= window['started_ns'] <= window['completed_ns'] <= closed, label + '/continuous_business')
    requests = result['requests']
    control = label in CONTROLS
    key = 'task_only' if control else label[0]+'_main'
    need(record['arm'] == label[0] and record['request_key'] == key, label + '/workflow_arm')
    need([request['request'] for request in requests] == contracts[key], label + '/registered_public_arguments')
    expected = 1 if control or label[0] == 'B' else 2
    need(window['public_business_calls'] == len(requests) == expected, label + '/actual_call_reduction')
    values, producers = [], []
    for request in requests:
        response = request['response']
        need(response['id'] == request['id'] and response['result']['isError'] is False, label + '/actual_response')
        value = read(request['public_path'])
        text = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
        need(len(text) == 1 and json.loads(text[0]) == value, label + '/public_original')
        need(len(text[0].encode('utf-8')) == request['public_text_UTF8_bytes'], label + '/public_byte_count')
        producer = read(request['producer']['path'])
        need(sha(request['producer']['path']) == request['producer']['sha256'], label + '/same_producer')
        values.append(value)
        producers.append(producer)
    if not control:
        need(values[0]['result_kind'] == 'active_observation', label + '/observation')
    task = values[-1] if control or label[0] == 'A' else values[0]['task_result']
    need(task['result_kind'] == 'task_query' and task['facts']['surface_proximity']['status'] == 'measured', label + '/measured_task')
    wire = read(folder / 'SAVED_WIRE.json')
    commands = [step for step in wire['steps'] if step.get('command')]
    audit = [json.loads(line) for line in raw(folder / 'audit.jsonl').splitlines() if line.strip()]
    task_work = [event['task_work'] for event in audit if event.get('event') == 'observe'
                 and event.get('observation_mode') is None and 'surface_pair_count' in event.get('task_work', {})]
    work = producers[0].get('work', {})
    if not control and label[0] == 'B':
        task_work = [work['task_query']]
    need(len(task_work) == 1 and task_work[0]['surface_pair_count'] == 1, label + '/one_actual_M3_pair')
    raster = sum(producer.get('work', {}).get('raster_attempts', 0) for producer in producers)
    images = sum(request['image_blocks'] for request in requests)
    need(raster == (0 if control else 1) and images == (0 if control else 1), label + '/image_path')
    return dict(label=label, arm=label[0], kind='task_only_control' if control else 'main',
        quality_passed=quality['passed_checked_scope'], transport_passed=publication['passed_transport_scope'],
        business_ns=window['continuous_business_ns'], complete_session_ns=closed-started,
        owned_lifecycle_ns=result['owned_lifecycle_ns'], public_business_calls=expected,
        complete_client_calls_ns=sum(request['complete_client_call_ns'] for request in requests),
        server_request_windows_ns=sum(request['server']['request_to_reply_ns'] for request in requests),
        client_flush_to_received_ns=sum(request['client_flush_to_received_ns'] for request in requests),
        public_text_UTF8_bytes=sum(request['public_text_UTF8_bytes'] for request in requests),
        actual_stdio_TX_bytes=sum(request['receipt']['TX_bytes'] for request in requests),
        actual_stdio_RX_bytes=sum(request['receipt']['RX_bytes'] for request in requests),
        image_blocks=images, raster_attempts=raster, M3_surface_pair_calls=task_work[0]['surface_pair_count'],
        actual_host_commands=[step['command']['command'] for step in commands],
        native_TCP_TX_bytes=sum(step['actual_TCP_TX_bytes'] for step in commands),
        native_TCP_RX_bytes=sum(step['actual_TCP_RX_bytes'] for step in commands),
        forwarded_resources=sum(step['resources_forwarded'] for step in commands),
        forwarded_vertices=sum(step['resource_vertices_forwarded'] for step in commands),
        forwarded_faces=sum(step['resource_faces_forwarded'] for step in commands),
        task_work=task_work[0], frames=len(producers[0].get('frames', [])),
        output_path=str(folder), original_result_sha256=publication['result_sha256'])


def main():
    started = time.perf_counter_ns()
    seal = read(HERE / 'QUALITY_SEAL.json')
    quality = read(HERE / 'QUALITY.json')
    need(seal['cost_unlocked'] is True and seal['sealed_ns'] < started
         and seal['quality_sha256'] == sha(HERE / 'QUALITY.json'), 'quality_before_formal_ranking')
    need(raw(HERE / 'QUALITY.json') == raw(HERE / 'FORMAL_QUALITY.json'), 'exact_quality_publication_copy')
    need(quality['registered_order'] == MAIN+CONTROLS
         and [row['label'] for row in quality['slots']] == MAIN+CONTROLS, 'all_eight_unique_quality_rows')
    need([(pair['A'], pair['B']) for pair in quality['paired_quality_comparisons']]
         == [('A1', 'B1'), ('A2', 'B2'), ('A3', 'B3')], 'three_unique_quality_pairs')
    pins(quality['input_pins'])
    plan = read(HERE / 'PLAN.json')
    contracts = read(HERE / 'REQUESTS.json')
    gate = read(HERE / 'FORMAL_GATE.json')
    run = read(RUNTIME / 'formal/RUN_RESULT.json')
    frozen = read(HERE / 'FORMAL_FROZEN.json')
    need(sha(HERE / 'PLAN.json') == gate['plan_sha256']
         and sha(HERE / 'REQUESTS.json') == gate['requests_sha256']
         and sha(HERE / 'FORMAL_FROZEN.json') == gate['formal_freeze_sha256']
         and sha(HERE / 'FORMAL_GATE.json') == run['gate_sha256'], 'original_formal_plan_and_gate')
    pins(frozen['files'])
    need([row['label'] for row in run['records']] == MAIN+CONTROLS
         and run['retries'] == run['replacement_samples'] == 0
         and run['not_run'] == [] and run['blocker'] is None, 'original_eight_closed_slots')
    runtime = read(HERE / 'RUNTIME_REVIEW.json')
    need(runtime['passed_checked_scope'] is True and runtime['qualification_only'] is False, 'runtime_source_budget_closure')
    pins(runtime['input_pins'])
    rows = [collect(label, record, q, gate, contracts) for label, record, q in zip(MAIN+CONTROLS, run['records'], quality['slots'])]
    pairs = []
    for number in (1, 2, 3):
        a = next(row for row in rows if row['label'] == 'A'+str(number))
        b = next(row for row in rows if row['label'] == 'B'+str(number))
        pairs.append(dict(pair=number, A_business_ns=a['business_ns'], B_business_ns=b['business_ns'],
            business_B_over_A=b['business_ns']/a['business_ns'], B_business_faster=b['business_ns'] < a['business_ns'],
            A_complete_session_ns=a['complete_session_ns'], B_complete_session_ns=b['complete_session_ns'],
            complete_session_B_over_A=b['complete_session_ns']/a['complete_session_ns']))
    business_ratio = statistics.median(pair['business_B_over_A'] for pair in pairs)
    session_ratio = statistics.median(pair['complete_session_B_over_A'] for pair in pairs)
    main = [row for row in rows if row['kind'] == 'main']
    gates = dict(main_quality=quality['main_denominator'] == quality['main_passed'] == 6,
        task_only_quality=quality['task_only_denominator'] == quality['task_only_passed'] == 2,
        paired_quality=all(row['passed_checked_scope'] for row in quality['paired_quality_comparisons']),
        public_calls_2_to_1=all(row['public_business_calls'] == (2 if row['arm'] == 'A' else 1) for row in main),
        no_additional_quantitative_capture=all(row['task_work']['supplemental_capture_calls'] == 0 for row in main if row['arm'] == 'B'),
        no_additional_quantitative_raster=all(row['task_work']['additional_raster_attempts'] == 0 for row in main if row['arm'] == 'B'),
        one_M3_pair=all(row['M3_surface_pair_calls'] == 1 for row in main),
        source_faces_retraceable=quality['passed_checked_scope'],
        minimum_faster_pairs=sum(pair['B_business_faster'] for pair in pairs) >= plan['gates']['minimum_B_faster_business_pairs'],
        business_median=business_ratio <= plan['gates']['median_business_B_over_A_max'],
        complete_session_median=session_ratio <= plan['gates']['median_complete_session_B_over_A_max'])
    passed = all(gates.values())
    totals = {}
    for arm in ('A', 'B'):
        totals[arm] = {field: sum(row[field] for row in main if row['arm'] == arm) for field in (
            'business_ns', 'complete_session_ns', 'public_business_calls', 'public_text_UTF8_bytes',
            'actual_stdio_TX_bytes', 'actual_stdio_RX_bytes', 'image_blocks', 'raster_attempts',
            'M3_surface_pair_calls', 'native_TCP_TX_bytes', 'native_TCP_RX_bytes', 'forwarded_resources',
            'forwarded_vertices', 'forwarded_faces')}
    output = dict(schema='m5-observe-measure-decision-v1', decision_source_sha256=sha(Path(__file__)),
        quality_sha256=sha(HERE / 'QUALITY.json'), quality_seal_sha256=sha(HERE / 'QUALITY_SEAL.json'),
        cost_analysis_started_ns=started, decision_closed_ns=time.perf_counter_ns(),
        passed_frozen_gates=passed, disposition='freeze_local_observe_measure_candidate' if passed else 'close_without_accepting_candidate',
        gates=gates, rows=rows, pairs=pairs, totals=totals,
        median_business_B_over_A=business_ratio, median_complete_session_B_over_A=session_ratio,
        median_business_reduction=1-business_ratio, median_complete_session_reduction=1-session_ratio,
        engineering_business_10percent_benefit=business_ratio <= plan['gates']['engineering_time_benefit_separate_ratio_max'],
        engineering_complete_10percent_benefit=session_ratio <= plan['gates']['engineering_time_benefit_separate_ratio_max'],
        task_only_scope='One diagnostic pair with no statistical performance gate.',
        optimization_attempts=1, formal_batches=1, retries=0, replacement_samples=0,
        model_consumers=0, paid_API_calls=0, monetary_cost=None,
        limitations=['One fixed asset and six fresh engineering main slots, plus two task-only controls.',
            'A second capture already forwards zero new geometry and builds no new resource. B removes a public request and host command, with measured source alias reuse.',
            'The qualification preparation/finalization timings are single-sample hotspot diagnostics. Formal A/B ratios evaluate the complete fixed workflows.',
            'Business, server, client transport and complete-session clocks retain distinct boundaries. Publication marker I/O is separate.',
            'Array payload and retained metadata are not allocation or copy counts. Copy counts and transient memory are unmeasured.',
            'No model task or billed fee was measured in this batch. Natural routing and broader assets require later evidence.'],
        input_pins=sorted(INPUTS.values(), key=lambda row: row['path']))
    with (HERE / 'DECISION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=passed, business_B_over_A=business_ratio, complete_session_B_over_A=session_ratio)))


if __name__ == '__main__':
    main()
