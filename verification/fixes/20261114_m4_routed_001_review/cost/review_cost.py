"""Independent stdlib-only audit of saved records. No product imports/execution."""
import base64
import collections
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = AUTHOR / 'verification/m4_routed_task_benefit_001'
RAW = Path('D:/he_routed_001/formal')
COMMIT = '6e1e65c6eba0545ef7d3a4280e914b76c99a3f38'
ORDER = ['N1', 'P1', 'P2', 'N2', 'N3', 'P3']
inputs = {}
checks = []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def read(path):
    return json.loads(raw(path).decode('utf-8-sig'))

def lines(path):
    return [json.loads(line) for line in raw(path).decode('utf-8-sig').splitlines() if line]

def check(name, value):
    checks.append({'name': name, 'pass': bool(value)})

def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def source(path):
    p = BATCH / path
    data = raw(p)
    original = subprocess.run(['git', 'show', COMMIT + ':' + p.relative_to(AUTHOR).as_posix()],
                              cwd=AUTHOR, capture_output=True, check=True).stdout
    check('fixed_commit:' + path, original == data)
    return data.decode('utf-8')

launcher = source('launcher.py')
source('bridge.py')
source('native_tools.py')
redaction_source = raw(AUTHOR / 'verification/native_plugin_complex_003/consumer_transport.py').decode('utf-8')
check('existing_redaction_rule', "if item.get('type') in ('reasoning','analysis')" in redaction_source and "'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)" in redaction_source)
plan = read(BATCH / 'PLAN.json')
preregistered = raw('D:/hefe/docs/M4_ROUTED_TASK_BENEFIT_001_PLAN.md')
check('plan_hash', hashlib.sha256(preregistered).hexdigest() == '44f73d0ed19d8c41ffa692bced8505d716353f430c1bb06916f96253465eba67')
suffix = raw(BATCH / 'inputs/PROMPT_SUFFIX.txt')
for g in 'NP':
    prefix = raw(BATCH / ('inputs/PREFIX_' + g + '.txt'))
    prompt = raw(BATCH / ('inputs/PROMPT_' + g + '.txt'))
    check('prompt_exact_composition_' + g, prompt == prefix + b'\n\n' + suffix)

slots = {}
for slot in ORDER:
    folder = RAW / slot
    timing = read(RAW / 'slot_records' / slot / 'SLOT_TIMING.json')
    wrapper = read(RAW / 'slot_records' / slot / 'SLOT_RESULT.json')
    route = read(folder / 'RESULT.json')
    route_clock = read(folder / 'FINAL_TIMING.json')
    consumer_clock = read(folder / 'c/FINAL_TIMING.json')
    consumer = read(folder / 'c/CONSUMER_STARTED.json')
    metrics = read(folder / 'o/METRICS.json')
    dependencies = read(folder / 'o/DEPENDENCIES.json')
    schema = read(folder / 'o/TOOLS_SCHEMA.json')
    events = lines(folder / 'c/events.jsonl')
    stdout_lines = raw(folder / 'c/stdout.raw.bin').splitlines(keepends=True)
    stdout = [json.loads(line) for line in stdout_lines]
    # Public events intentionally redact reasoning text. Compare ordinary rows
    # literally and redacted rows by their original byte count and digest.
    match = len(events) == len(stdout_lines)
    redacted = 0
    for saved, direct, binary in zip(events, stdout, stdout_lines):
        item = saved['event']
        if item.get('item', {}).get('redacted'):
            redacted += 1
            match = match and item.get('raw_bytes') == len(binary) and item.get('raw_sha256') == hashlib.sha256(binary).hexdigest()
        else:
            match = match and item == direct
    check(slot + '_events_match_raw_stdout_or_redaction_hash', match)
    usage_events = [(i, r) for i, r in enumerate(events) if 'usage' in r['event']]
    check(slot + '_one_usage_terminal', len(usage_events) == 1 and usage_events[0][1]['event']['type'] == 'turn.completed')
    usage = usage_events[0][1]['event']['usage']
    check(slot + '_usage_subsets', usage['cached_input_tokens'] <= usage['input_tokens'] and usage['reasoning_output_tokens'] <= usage['output_tokens'])
    tools = [r for r in events if r['event'].get('type') == 'item.completed' and r['event'].get('item', {}).get('type') == 'mcp_tool_call']
    images = []
    texts = 0
    for row in tools:
        item = row['event']['item']
        for block in (item.get('result') or {}).get('content', []):
            if block['type'] == 'image':
                binary = base64.b64decode(block['data'], validate=True)
                images.append({'sha256': hashlib.sha256(binary).hexdigest(), 'bytes': len(binary), 'tool': item['tool']})
            elif block['type'] == 'text':
                texts += len(block['text'].encode('utf-8'))
    errors = []
    receipts = []
    for p in sorted((folder / 'o').glob('tool_*/RESPONSE.json')):
        response = read(p)
        request = read(p.with_name('REQUEST.json'))
        receipt = read(p.with_name('RECEIPT.json'))
        receipts.append(receipt)
        if response.get('result', {}).get('isError'):
            content = response['result']['content']
            error_payload = json.loads(content[0]['text']) if content and content[0].get('type') == 'text' else None
            errors.append({'tool': p.parent.name, 'error': error_payload.get('error') if isinstance(error_payload, dict) else error_payload,
                           'service_elapsed_ns': receipt['elapsed_ns'], 'code': request.get('params', {}).get('arguments', {}).get('code')})
    check(slot + '_count_tools', len(tools) == metrics['tool_attempts'] == route['actual_tool_calls'] == len(receipts))
    check(slot + '_delivered_images', len(images) == metrics['server_socket_sent_image_blocks'] == route['public_image_count'])
    check(slot + '_outer_clock_subtraction', timing['elapsed_ns'] == timing['SLOT_RESULT_closed_ns'] - timing['started_ns'])
    check(slot + '_nested_clock_bounds', timing['started_ns'] <= route_clock['started_ns'] <= consumer_clock['started_ns'] <= consumer_clock['consumer_record_closed_ns'] <= route_clock['result_closed_ns'] <= timing['SLOT_RESULT_closed_ns'])
    check(slot + '_wrapper_closed_successfully', wrapper['source_unchanged'] and not wrapper['terminal_errors'] and not timing['publication_errors'] and route['outer_valid_completion'])
    check(slot + '_remaining_deadline', consumer_clock['original_turn_deadline_ns'] == route_clock['original_deadline_ns'] == route['deadline_ns'])
    check(slot + '_all_recorded_tools_inside_clock', all(timing['started_ns'] <= r['started_ns'] <= r['closed_ns'] <= timing['SLOT_RESULT_closed_ns'] for r in receipts))
    check(slot + '_tool_receipts_nonoverlap', all(a['closed_ns'] <= b['started_ns'] for a,b in zip(receipts, receipts[1:])))
    check(slot + '_tool_duration_subtraction', all(r['elapsed_ns'] == r['closed_ns'] - r['started_ns'] for r in receipts))
    check(slot + '_CLI_text_equals_server_receipts', texts == sum(r['content_metrics']['text_UTF8_bytes'] for r in receipts))
    check(slot + '_CLI_actor_cleanup', all(route[k]['confirmed'] and route[k]['reaped'] and route[k]['process_handle_closed'] and route[k]['exit_code'] == 0 and not route[k]['kill_requested'] for k in ['consumer_process_cleanup', 'owner_process_cleanup']))
    check(slot + '_thin_closed_actual_status', route['runtime_exit']['confirmed'] and route['runtime_exit']['handle_closed'] and route['runtime_exit']['exit_code'] == 1)
    argv = [a.replace(slot, 'SLOT') for a in consumer['frozen_cli_argv']]
    argv = [a.replace('"active_observation"={"approval_mode"="approve"},', '') for a in argv]
    slots[slot] = {'seconds': timing['elapsed_ns'] / 1e9, 'started_ns': timing['started_ns'], 'closed_ns': timing['SLOT_RESULT_closed_ns'],
        'route_seconds': route_clock['elapsed_ns'] / 1e9, 'consumer_seconds': consumer_clock['full_turn_wall_ns'] / 1e9,
        'usage': usage, 'usage_line_index_zero_based': usage_events[0][0], 'verified_redacted_rows': redacted, 'input_plus_output': usage['input_tokens'] + usage['output_tokens'],
        'tools': len(tools), 'tool_service_seconds': sum(r['elapsed_ns'] for r in receipts)/1e9,
        'errors': errors, 'CLI_image_blocks': len(images), 'CLI_PNG_bytes': sum(r['bytes'] for r in images), 'CLI_text_UTF8_bytes': texts,
        'rasters': metrics['new_renders'], 'constructed_image_blocks': metrics['constructed_image_blocks'],
        'PNG_generated_bytes': metrics['common']['PNG_bytes'], 'NPZ_generated_bytes': metrics['common']['NPZ_bytes'],
        'array_payload_bytes': metrics['common']['array_payload_bytes'], 'product_calls': metrics['common']['product_observation_calls'],
        'dependencies': dependencies, 'thread_id': route['observed_thread_id'], 'argv_normalized': argv,
        'thin_EXIT_receipt': route['bridge_cleanup']['receipt_status'], 'thin_process_exit': route['runtime_exit']['exit_code']}

check('six_distinct_threads', len({s['thread_id'] for s in slots.values()}) == 6)
check('fixed_order_serial_nonoverlap', all(slots[a]['closed_ns'] <= slots[b]['started_ns'] for a,b in zip(ORDER, ORDER[1:])))
check('same_dependencies_six_slots', all(s['dependencies'] == slots['N1']['dependencies'] for s in slots.values()))
check('same_cli_except_slot_and_product_tool', all(s['argv_normalized'] == slots['N1']['argv_normalized'] for s in slots.values()))
for g in 'NP':
    counts = [slots[s]['product_calls'] for s in ORDER if s[0] == g]
    check('product_calls_' + g, counts == ([0,0,0] if g == 'N' else [1,1,1]))

ledger = [read(p) for p in sorted((RAW.parent / 'raster_budget').glob('attempt_*/INTENT.json'))]
check('raster_ledger_total', len(ledger) == sum(s['rasters'] for s in slots.values()) == 29)
check('raster_unique_ids', len({r['global_attempt'] for r in ledger}) == len(ledger))
check('one_scene_origin_each', len({r['source_scene_sha256'] for r in ledger}) == len({r['source_capture_sha256'] for r in ledger}) == 1)
origins = dict(collections.Counter(r['origin'] for r in ledger))
batch = read(RAW / 'BATCH_TIMING.json')
parent = read(BATCH / 'FORMAL_PROCESS.json')
groups = {}
for g in 'NP':
    rows = [s for k,s in slots.items() if k[0] == g]
    groups[g] = {field: sum(s[field] for s in rows) for field in ['seconds', 'input_plus_output', 'tools', 'tool_service_seconds', 'CLI_image_blocks', 'CLI_PNG_bytes', 'CLI_text_UTF8_bytes', 'rasters', 'array_payload_bytes']}
    groups[g]['usage'] = {key: sum(s['usage'][key] for s in rows) for key in rows[0]['usage']}
pairs = [{'pair':str(i), 'N_seconds':slots['N'+str(i)]['seconds'], 'P_seconds':slots['P'+str(i)]['seconds'], 'ratio':slots['P'+str(i)]['seconds']/slots['N'+str(i)]['seconds']} for i in (1,2,3)]
median_ratio = statistics.median(p['ratio'] for p in pairs)
token_ratio = groups['P']['input_plus_output']/groups['N']['input_plus_output']
decision = {'median_paired_ratio':median_ratio, 'paired_median_time_reduction_fraction':1-median_ratio,
            'faster_pairs':sum(p['ratio']<1 for p in pairs), 'raw_token_ratio':token_ratio, 'raw_token_reduction_fraction':1-token_ratio,
            'numeric_cost_rules_pass':median_ratio <= .9 and sum(p['ratio']<1 for p in pairs)>=2 and token_ratio<=1,
            'conditional_on_independent_quality_and_identity_reviews':True}
result = {'method':'Independent saved-data stdlib recomputation; no author cost_audit import/execution.',
          'new_product_model_Blender_raster_calls':0,'fixed_commit':COMMIT,'slots':slots,'groups':groups,'pairs':pairs,'decision':decision,
          'raster_origins':origins,'batch_seconds':batch['elapsed_ns']/1e9,'slot_sum_seconds':sum(s['seconds'] for s in slots.values()),
          'batch_minus_slots_seconds':(batch['elapsed_ns']-sum(round(s['seconds']*1e9) for s in slots.values()))/1e9,
          'parent_receipt':parent,'checks':checks,'failed_checks':[c for c in checks if not c['pass']]}
dump('RESULT.json', result)
dump('INPUT_HASHES.json', [{'path':p,**v} for p,v in sorted(inputs.items())])
print(json.dumps({'checks':len(checks),'failed':result['failed_checks'],'groups':groups,'pairs':pairs,'decision':decision,'input_files':len(inputs)},ensure_ascii=False,indent=2))
