"""Compare the actual stdio packets and retain independent per-case CLI scores."""
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parent
ROOT = Path('D:/he_m1_source_region_no_image_measurement_packet_001')
ARMS = ('baseline_standard', 'candidate_standard', 'candidate_evidence')
CASES = ('holdout_A1', 'holdout_B1', 'independent_P1')
DETAILS = 'response_detail=full on the standard endpoint'


def require(check, reason, *detail):
    if not check:
        raise ValueError(reason, *detail)


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def tool_packet(case_root, detail):
    for pipe in sorted((case_root/'wire').glob('rpc_*'), key=lambda path: int(path.name.split('_')[1])):
        tx = read(pipe/'TX.bin')
        args = tx.get('params', {}).get('arguments', {})
        if (tx.get('method') == 'tools/call' and args.get('response_detail') == detail
                and 'region' in args.get('query', {})):
            raw = (pipe/'RX.bin').read_bytes()
            rx = json.loads(raw)
            require(rx['id'] == tx['id'], 'different held JSON-RPC request and response ids')
            receipt = read(pipe/'RECEIPT.json')
            require(receipt['TX_bytes'] == (pipe/'TX.bin').stat().st_size and receipt['RX_bytes'] == len(raw),
                    'outer stdio sizes differ from actual wire')
            return {'tx': tx, 'rx': rx, 'tx_path': pipe/'TX.bin', 'rx_path': pipe/'RX.bin', 'receipt': receipt}
    raise ValueError('missing actual full or brief request', str(case_root), detail)


def stable_standard_body(text):
    body = json.loads(text)
    dumps = lambda obj: json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    require(dumps(body) == text, 'body encoding differs before normalizing trace identifiers')
    trace = body.get('request_trace', {})
    dynamic = {}
    for key in ('trace_id','request_id'):
        if key in trace:
            require(isinstance(trace[key], str), 'unexpected trace identifier type', key)
            dynamic[key] = trace[key]
            trace[key] = '<replay-identifier>'
    return dumps(body).encode(), dynamic


def timings(case_root, item):
    events = [json.loads(line) for line in (case_root/'worker/PRODUCT_EVENTS.jsonl').read_bytes().splitlines()]
    traces = [event['trace'] for event in events if event['event'] == 'request_trace'
              and event['trace']['annotations'].get('mcp_request_id') == item['tx']['id']]
    require(len(traces) == 1, 'actual product request trace not unique', item['tx']['id'])
    trace = traces[0]
    spans = {row['name']:row['duration_ns'] for row in trace['spans']}
    wanted = ('service.observe','mcp.content_encode','mcp.wire_encode','mcp.stdio_write')
    require(all(key in spans for key in wanted) and trace['annotations']['mcp_native_image_block_count'] == 0,
            'published stage or no-image proof missing')
    return {'product_trace_id':trace['trace_id'], 'product_trace_ns':trace['duration_ns'],
            'stages_ns':{key:spans[key] for key in wanted}}


def verify_compatibility():
    runs = {arm:read(ROOT/arm/'INDEX.json') for arm in ARMS}
    require(all(run['completed'] and not run['unrun'] for run in runs.values()), 'formal stdio arm incomplete')
    require(all(run['planned'] == runs[ARMS[0]]['planned'] for run in runs.values()), 'arm fixture roster differs')
    paired = {}
    total = success = rejects = 0
    for case in runs[ARMS[0]]['planned']:
        arm_results = {arm:read(ROOT/arm/'cases'/case/'CASE.json') for arm in ARMS}
        lists = [arm_results[arm]['calls'] for arm in ARMS]
        closure = {arm:read(ROOT/arm/'cases'/case/'HELD_EOF.json') for arm in ARMS}
        for arm, record in closure.items():
            terminal = record['worker_eof']
            close = record['held_close']
            require(record['stdout_eof_observed'] and record['input_eof_observed']
                    and close['exit_code'] == 0 and close['process_handle_closed'] and close['reader_stopped']
                    and terminal['host_attempts'] == terminal['socket_attempts'] == terminal['blocked_old_writes']
                    == terminal['actual_new_rasters'] == 0, 'replay closure or work guard failed', arm, case)
        required_compact = case in CASES
        for base, stock, evidence in zip(*lists, strict=True):
            require(base['label'] == stock['label'] == evidence['label']
                    and base['arguments'] == stock['arguments'] == evidence['arguments']
                    and base['expected_error'] == stock['expected_error'] == evidence['expected_error']
                    and all(row['matches_expected_error'] for row in (base,stock,evidence)),
                    'unexpected request semantics or result classification', case)
            total += 1
            rejects += int(base['expected_error'])
            success += int(not base['expected_error'])
            bodies = [Path(row['public_path']).read_text(encoding='utf8') for row in (base, stock, evidence)]
            if base['expected_error']:
                errors = [json.loads(text)['error'] for text in bodies]
                require(errors[0] == errors[1] == errors[2], 'public error reason changed', case, base['label'])
                continue
            require(base['images'] == stock['images'] == evidence['images'], 'image blocks changed', case)
            left, right = (json.loads(text) for text in bodies[:2])
            for packet in (left,right):
                packet.pop('request_trace', None)
            require(left == right, 'standard compatible fields changed', case, base['label'])
            if not required_compact and case != 'region_task':
                isolated = json.loads(bodies[2])
                isolated.pop('request_trace', None)
                require(isolated == left, 'isolated endpoint changed an unrelated reply', case)
        paired[case] = {'calls_per_arm':len(lists[0]), 'actual_closed_processes':len(closure),
                        'source_dispatches':{arm:closure[arm]['worker_eof']['dispatches'] for arm in ARMS}}
    return {'paired_calls':total,'paired_successes':success,'paired_expected_rejections':rejects,'cases':paired}


def check():
    save_score = run_path(str(NS/'checks/score.py'))
    score = save_score['score']
    public = save_score['public']
    output = ROOT/'qualification'
    output.mkdir(exist_ok=False)
    rows = []
    for case in CASES:
        replies = {}
        for arm in ARMS:
            case_root = ROOT/arm/'cases'/case
            exit_receipt = read(case_root/'worker/EOF.json')
            require(not (case_root/'worker/PNG_READS.jsonl').exists()
                    and exit_receipt['closed'] and exit_receipt['input_eof_observed']
                    and not exit_receipt['host_attempts'] and not exit_receipt['socket_attempts']
                    and exit_receipt['archived_inputs_unchanged'], 'unsafe production replay closing', arm, case)
            for index, detail in enumerate(('full', 'brief'), 1):
                item = tool_packet(case_root, detail)
                producer_path = case_root/'worker'/f'PRODUCER_{index:02d}.json'
                producer = read(producer_path)
                mode = 'compact' if detail == 'brief' or arm == 'candidate_evidence' else 'full'
                proof = score(case, item['rx'], mode=mode, producer=producer)
                proof['actual_tx'] = save_score['pin'](item['tx_path'])
                proof['actual_rx'] = save_score['pin'](item['rx_path'])
                proof['actual_producer'] = save_score['pin'](producer_path)
                proof['stdio_receipt'] = item['receipt']
                proof['execution_timing'] = timings(case_root, item)
                save(output/f'{case}_{arm}_{detail}.json', proof)
                _, text, packet = public(item['rx'])
                item.update(packet=packet, text=text, proof=proof)
                replies[arm, detail] = item
        row = {'case':case}
        for detail in ('full','brief'):
            base, stock, evidence = (replies[arm,detail] for arm in ARMS)
            require(base['tx']['params'] == stock['tx']['params'] == evidence['tx']['params'],
                    'service-facing request changed between installs', case, detail)
            base_stable, base_trace = stable_standard_body(base['text'])
            stock_stable, stock_trace = stable_standard_body(stock['text'])
            require(base_stable == stock_stable,
                    'standard encoded reply differs outside its actual trace identifiers', case, detail)
            task = evidence['packet'].copy()
            require(task.pop('details') == DETAILS, 'isolated diagnostic directions changed', case, detail)
            baseline_brief = replies['baseline_standard','brief']['packet'].copy()
            baseline_brief.pop('details')
            require(task == baseline_brief, 'compact output changed fixed facts', case, detail)
            row[detail] = {arm:{'body_bytes':replies[arm,detail]['proof']['actual_body_utf8_bytes'],
                                 'body_sha256':replies[arm,detail]['proof']['actual_body_sha256'],
                                 'stdio_RX_bytes':replies[arm,detail]['receipt']['RX_bytes'],
                                 'stdio_RTT_ns':replies[arm,detail]['receipt']['elapsed_ns'],
                                 **replies[arm,detail]['proof']['execution_timing'],
                                 'fixed_CLI_exact_stages':replies[arm,detail]['proof']['fixed_CLI']['exact_stages']}
                           for arm in ARMS}
            row[detail]['standard_comparison'] = {
                'raw_bytes_equal': base['text'].encode() == stock['text'].encode(),
                'trace_identifiers': {'baseline':base_trace,'candidate':stock_trace},
                'bytes_equal_after_excluding_actual_trace_identifiers': True,
            }
        rows.append(row)
    result = {'passed':True, 'scored_actual_packets':18, 'candidate_evidence_CLI_exact_checks':36,
              'standard_stable_byte_equal_pairs':6, 'install_arms':list(ARMS), 'cases':rows,
              'compatibility':verify_compatibility(),
              'freeze_sha256':sha256((NS/'FROZEN.json').read_bytes()).hexdigest()}
    save(output/'QUALIFICATION.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    check()
