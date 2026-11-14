"""Independent offline execution-chain and clock audit. No product imports."""
import ast
import base64
import hashlib
import json
import marshal
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = AUTHOR / 'verification/m4_explicit_observation_consumption_001'
RUNTIME = Path('D:/he_explicit_001')
SLOT = RUNTIME / 'formal/P1'
inputs, checks = {}, []

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def raw(path):
    path = Path(path)
    value = path.read_bytes()
    inputs[path.as_posix()] = {'sha256': sha(value), 'bytes': len(value)}
    return value

def read(path):
    return json.loads(raw(path))

def check(name, ok):
    checks.append({'name': name, 'passed': bool(ok)})

def differences(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict):
        return [row for k in a.keys() | b.keys() for row in differences(a.get(k), b.get(k), prefix+'/'+k)]
    return [] if a == b else [{'path': prefix, 'before': a, 'after': b}]

before = read(RUNTIME / 'formal/ENTRY_PROOF_BEFORE.json')
after = read(RUNTIME / 'formal/ENTRY_PROOF_AFTER.json')
delta = sorted(differences(before, after), key=lambda x: x['path'])
check('only_three_marshal_fields_differ', [r['path'] for r in delta] == [
    '/accepted_route/code_sha256', '/old_connect/code_sha256', '/single_route/code_sha256'])
check('all_recorded_checks_true_both_times', all(before['checks'].values()) and all(after['checks'].values()))
check('17_recorded_checks', len(before['checks']) == len(after['checks']) == 17)
for key in ['accepted_launcher', 'matcher']:
    check(key+'_saved_source_hash', sha(raw(before[key+'_path'])) == before[key+'_sha256'])

launcher_path = BATCH / 'launcher.py'
launcher = raw(launcher_path).decode('utf-8-sig')
tree = ast.parse(launcher)
pointer = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'pointer_proof')
check_dict = next(n.value for n in pointer.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'checks' for t in n.targets))
fresh_names = [k.value for k in check_dict.keys if isinstance(k, ast.Constant)]
check('nine_fresh_checks_eight_inherited_snapshots', len(fresh_names) == 9 and len(before['checks'])-len(fresh_names) == 8)
run_once = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_once')
ordered_lines = {'route': launcher.index("record = route('P1', 'P', plan, runtime)"),
    'run_result': launcher.index("save(runtime / 'RUN_RESULT.json'"),
    'verify_sources': launcher.index('    verify_frozen(sources)', launcher.index("save(runtime / 'RUN_RESULT.json'")),
    'after_proof': launcher.index("save(runtime / 'ENTRY_PROOF_AFTER.json'"),
    'marshal_compare': launcher.index('    if after != proof:'),
    'launch_result': launcher.index("save(runtime / 'LAUNCH_RESULT.json'"),
    'launch_timing': launcher.index("save(runtime / 'LAUNCH_TIMING.json'")}
check('route_result_source_check_precede_marshal_failure', list(ordered_lines.values()) == sorted(ordered_lines.values()))
frozen = read(BATCH / 'FROZEN.json')['files_sha256']
check('launcher_matches_frozen', frozen[str(launcher_path)] == sha(raw(launcher_path)))

# A fresh, compile-only witness: no exec and no call of any compiled function.
code = compile("def probe():\n    return {'alpha': ('new-unique-literal', 42)}\n", '<independent-marshal-witness>', 'exec', dont_inherit=True)
code_id = id(code)
opcode_sha = sha(code.co_code)
marshaled_before = marshal.dumps(code)
held_constants = code.co_consts
marshaled_after = marshal.dumps(code)
witness = {'python': sys.version, 'same_code_object': id(code) == code_id,
    'co_code_unchanged': sha(code.co_code) == opcode_sha,
    'marshal_bytes_differ': marshaled_before != marshaled_after,
    'decoded_code_objects_equal': marshal.loads(marshaled_before) == marshal.loads(marshaled_after),
    'before_sha256': sha(marshaled_before), 'after_sha256': sha(marshaled_after),
    'first_byte_difference': next((i for i, (a,b) in enumerate(zip(marshaled_before, marshaled_after)) if a != b), None),
    'compiled_code_executions': 0, 'change': 'retain code.co_consts reference only'}
check('compile_only_marshal_instability_witness', all(witness[k] for k in ['same_code_object','co_code_unchanged','marshal_bytes_differ','decoded_code_objects_equal']))

parent = read(BATCH / 'FORMAL_PROCESS.json')
parent_start = read(BATCH / 'FORMAL_PARENT_STARTED.json')
route = read(SLOT / 'RESULT.json')
route_time = read(SLOT / 'FINAL_TIMING.json')
consumer = read(SLOT / 'c/CONSUMER.json')
consumer_time = read(SLOT / 'c/FINAL_TIMING.json')
run_result = read(RUNTIME / 'formal/RUN_RESULT.json')
config = read(SLOT / 'ACTOR_CONFIG.json')
check('original_450s_deadline', route['deadline_ns']-route['started_ns'] == 450_000_000_000)
check('shared_absolute_deadline', route['deadline_ns'] == config['worker_deadline_ns'] == consumer['deadline_ns'] == consumer['episode_deadline_ns'] == route_time['original_deadline_ns'] == consumer_time['original_turn_deadline_ns'] == consumer_time['episode_deadline_ns'])
check('budget_config_12_tools_6_rasters', config['max_tool_calls'] == 12 and config['max_render_attempts'] == config['phase_render_cap'] == 6)
check('one_route_one_thread_no_outer_retry', run_result['actual_routes'] == run_result['actual_CLI_processes'] == len(run_result['observed_fresh_threads']) == 1 and run_result['outer_retries'] == 0)
check('failed_route_saved_before_tail_exception', run_result['records'][0]['execution_state'] == 'failed' and not route['outer_valid_completion'])
check('parent_clock', parent_start['started_ns'] == parent['started_ns'] and parent['closed_ns']-parent['started_ns'] == parent['elapsed_ns'])
check('route_clock', route_time['result_closed_ns']-route_time['started_ns'] == route_time['elapsed_ns'])
check('consumer_clock', consumer_time['consumer_record_closed_ns']-consumer_time['started_ns'] == consumer_time['full_turn_wall_ns'])
check('nested_and_before_deadline', parent['started_ns'] < route_time['started_ns'] < consumer_time['started_ns'] < consumer_time['consumer_record_closed_ns'] < route_time['result_closed_ns'] < parent['closed_ns'] < route['deadline_ns'])

events = [json.loads(line) for line in raw(SLOT / 'c/events.jsonl').splitlines()]
stdout = [json.loads(line) for line in raw(SLOT / 'c/stdout.raw.bin').splitlines()]
tools = [e for e in events if e['event'].get('type') == 'item.completed' and e['event'].get('item', {}).get('type') == 'mcp_tool_call']
raw_tools = [e['item'] for e in stdout if e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'mcp_tool_call']
check('13_completed_tools_bound_raw_events', len(tools) == len(raw_tools) == 13 and [e['event']['item'] for e in tools] == raw_tools)
check('one_active_then_twelve_python', [e['tool'] for e in raw_tools] == ['active_observation']+['execute_python']*12)
check('no_terminal_usage_event', not any(e.get('type') in ('turn.completed','turn.failed') for e in stdout) and consumer['usage'] is None and not consumer['raw_usage_events'])
check('one_thread_one_turn', sum(e.get('type') == 'thread.started' for e in stdout) == sum(e.get('type') == 'turn.started' for e in stdout) == 1)
check('PUBLIC_FINAL_absent_despite_progress_capture', not (SLOT / 'c/PUBLIC_FINAL.txt').exists() and consumer['final'] is not None and not consumer['valid_completion'])

receipts, requests, responses = [], [], []
for n, item in enumerate(raw_tools, 1):
    folder = SLOT / f'o/tool_{n:02}'
    receipt, request, response = [read(folder / name) for name in ('RECEIPT.json','REQUEST.json','RESPONSE.json')]
    receipts.append(receipt); requests.append(request); responses.append(response)
    check(f'tool_{n}_clock', receipt['closed_ns']-receipt['started_ns'] == receipt['elapsed_ns'])
    check(f'tool_{n}_request_binding', request['params']['name'] == item['tool'] and request['params']['arguments'] == item['arguments'])
    check(f'tool_{n}_copy', raw(folder/'RECEIPT.json') == raw(SLOT / f'c/owner_turn/tool_{n:02}/RECEIPT.json'))
check('guard_rejected_thirteenth', receipts[12]['error']['message'] == 'route_twelve_tool_call_limit' and all(not (r['error'] and r['error'].get('message') == 'route_twelve_tool_call_limit') for r in receipts[:12]))
bridge = raw(AUTHOR / 'verification/m4_region_localization_consumption_001/bridge.py').decode('utf-8-sig')
check('owner_guard_precedes_business_dispatch', bridge.index('if self.calls > 12:') < bridge.index('result = self.execute_python(arguments)'))
native = raw(AUTHOR / 'verification/m4_region_localization_consumption_001/native_tools.py').decode('utf-8-sig')
check('raster_reservation_precedes_actual_raster', "if len(self.attempts) >= 6:" in native and native.index('row = self.reserve(self._render_view)') < native.index('value = self.original_raster(*args, **kwargs)'))
check('raster_and_missing_key_errors_preserved', 'six_actual_raster_attempt_limit' in str(responses[3]) and "KeyError" in str(responses[10]))
legacy_consumer = raw(AUTHOR / 'verification/m4_active_coverage_consumption_001/consumer.py').decode('utf-8-sig')
check('consumer_itself_aborts_after_tool13', "if len(record['tool_calls']) > 12:" in legacy_consumer and "raise ValueError('route_twelve_tool_call_limit')" in legacy_consumer)
check('PUBLIC_FINAL_write_bypassed_on_abort', legacy_consumer.index("if len(record['tool_calls']) > 12:") < legacy_consumer.index("(folder/'PUBLIC_FINAL.txt').write_bytes") < legacy_consumer.index("except BaseException as error:record['errors'].append"))

intents = [read(p) for p in sorted((RUNTIME / 'raster_budget').glob('attempt_*/INTENT.json'))]
trace = [json.loads(line) for line in raw(SLOT/'o/TRACE.jsonl').splitlines()]
check('six_intents_three_product_three_native', len(intents) == 6 and [r['global_attempt'] for r in intents] == list(range(1,7)) and [r['origin'] for r in intents] == ['product']*3+['native']*3)
check('six_trace_render_attempts', len([r for r in trace if r['event'] == 'render_attempt']) == 6)
metrics = read(SLOT/'o/METRICS.json')
check('six_completed_frames', metrics['common']['raster_completed'] == metrics['common']['frames_completed'] == 6)
check('one_replay_zero_Blender', metrics['common']['capture_replay_calls'] == metrics['common']['product_observation_calls'] == 1 and metrics['common']['actual_Blender_capture_calls'] == 0)
images = [base64.b64decode(b['data']) for item in raw_tools for b in (item.get('result') or {}).get('content',[]) if b['type'] == 'image']
check('three_images_8819_bytes', len(images) == 3 and sum(map(len, images)) == 8819 and all(p.startswith(b'\x89PNG\r\n\x1a\n') for p in images))
check('constructed_delivery_not_refunded', metrics['constructed_image_blocks'] == metrics['server_socket_sent_image_blocks'] == len(images) and metrics['constructed_PNG_bytes'] == sum(map(len,images)))

check('CLI_exit1_closed', consumer['exit_code'] == 1 and consumer['process_cleanup']['confirmed'] and consumer['process_cleanup']['process_handle_closed'])
check('actor_exit0_closed', route['owner_process_cleanup']['exit_code'] == 0 and route['owner_process_cleanup']['confirmed'] and route['owner_process_cleanup']['process_handle_closed'])
check('thin_exit0_closed', consumer['runtime_exit']['exit_code'] == 0 and consumer['runtime_exit']['confirmed'] and consumer['runtime_exit']['handle_closed'])
check('normal_EXIT_unknown', consumer['bridge_cleanup']['receipt_status'] == 'unknown' and consumer['bridge_cleanup']['missing_exit_count'] == 1)
check('tail_launcher_failure', parent['exit_code'] == 1 and 'entry_pointer_chain_changed_during_single_slot' in raw(BATCH/'FORMAL_PROCESS_STDERR.bin').decode())
check('tail_receipts_absent', not (RUNTIME/'formal/LAUNCH_RESULT.json').exists() and not (RUNTIME/'formal/LAUNCH_TIMING.json').exists())
timing = {'parent_seconds': parent['elapsed_ns']/1e9, 'route_seconds': route_time['elapsed_ns']/1e9,
    'consumer_seconds': consumer_time['full_turn_wall_ns']/1e9,
    'prompt_to_active_received_seconds': (tools[0]['perf_ns']-consumer['prompt_submitted_ns'])/1e9,
    'active_received_to_CLI_exit_seconds': (consumer['process_exit_ns']-tools[0]['perf_ns'])/1e9,
    'product_tool_service_seconds': receipts[0]['elapsed_ns']/1e9,
    'later_tool_service_seconds': sum(r['elapsed_ns'] for r in receipts[1:])/1e9,
    'all_tool_service_seconds': sum(r['elapsed_ns'] for r in receipts)/1e9,
    'scope': 'Nested clocks, never sum parent/route/consumer or subtract service as pure reasoning.'}
results = {'passed': all(c['passed'] for c in checks), 'checks': len(checks),
    'failures': [c for c in checks if not c['passed']], 'details': checks, 'input_hashes': inputs,
    'actual_pointer_differences': delta, 'fresh_pointer_check_names': fresh_names,
    'inherited_snapshot_check_names': sorted(set(before['checks'])-set(fresh_names)),
    'independent_compile_only_witness': witness, 'timing': timing,
    'new_product_model_Blender_raster_benchmark_calls': 0,
    'limitations': ['Original process did not store original marshal bytes or co_code snapshots; precise cause of original three digest changes remains unknown.',
                    'CLI exit1 follows harness tool-cap abort; the earlier finally kill has no separate receipt, so later kill_requested=false does not prove no kill.',
                    'Input/output/cached/image tokens, provider internal request count and cash fees remain unmeasured.']}
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'passed': results['passed'], 'checks': len(checks), 'failures': results['failures'], 'inputs': len(inputs), 'timing': timing, 'witness': witness}, ensure_ascii=False))
