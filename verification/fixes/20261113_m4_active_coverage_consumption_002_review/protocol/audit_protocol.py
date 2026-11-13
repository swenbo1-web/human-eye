"""Independent, read-only parsing of recorded protocol/lifetime evidence.

No author Python is imported, compiled or invoked. Captured code stays text.
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = ROOT / 'verification/m4_active_coverage_consumption_002'
OLD = ROOT / 'verification/m4_active_coverage_consumption_001'
CAND = ROOT / 'verification/m4_consumer_error_contract_001'
OUT = Path(__file__).resolve().parent
inputs = {}
checks = []
zip_count = zip_members = 0
formal_tools = local_tools = 0


def h(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(p):
    p = Path(p)
    data = p.read_bytes()
    inputs[str(p)] = {'bytes': len(data), 'sha256': h(data)}
    return data


def read(p):
    return json.loads(raw(p))


def eq(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def ck(name, condition, **details):
    checks.append({'check': name, 'passed': bool(condition), **details})
    if not condition:
        raise AssertionError(name + ': ' + repr(details))


def check_zip(path, owner, mapping, digest, size):
    global zip_count, zip_members
    data = raw(path)
    ck('archive_bytes_and_digest', len(data) == size and h(data) == digest, path=str(path))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        ck('archive_exact_members_no_duplicates', len(names) == len(set(names)) and set(names) == set(mapping), path=str(path))
        for name in names:
            content = z.read(name)
            ck('archive_member_original_and_SHA', content == raw(owner/name) and h(content) == mapping[name], archive=str(path), member=name)
            zip_members += 1
    zip_count += 1


plan = read(B/'PLAN.json')
freeze = read(B/'FROZEN.json')['files_sha256']
old_sources = read(OLD/'FROZEN.json')['runtime_sources']
ck('188_sources_and_original_176_subset', len(freeze) == 188 and len(old_sources) == 176 and all(freeze.get(p) == sha for p, sha in old_sources.items()))
candidate_frozen = read(CAND/'FROZEN.json')['files_sha256']
for name in ['consumer.py', 'driver.py', 'result_contract.py']:
    p = CAND/name
    ck('three_candidate_sources_frozen', freeze.get(str(p)) == candidate_frozen[str(p)] == h(raw(p)), path=str(p))
for p in [B/'launcher.py', B/'PLAN.json', B/'fake_cli.py', B/'admin/score_answers.py', B/'admin/TRUTH.json', B/'admin/SCORING_SCHEMA.json', OLD/'admin/score_answers.py']:
    ck('new_entry_scoring_frozen', freeze.get(str(p)) == h(raw(p)), path=str(p))
base = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
ck('base_and_CLI_frozen', str(base) in freeze and sum(p.endswith('codex.exe') for p in freeze) == 1)
launcher_source = raw(B/'launcher.py').decode()
tree = ast.parse(launcher_source)
main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
calls = [ast.unparse(n) for n in ast.walk(main) if isinstance(n, ast.Call)]
ck('explicit_new_candidate_batch_only', calls.count('driver.run_batch(plan, runtime)') == 1 and not any('legacy.run_batch' in x or 'driver.main' in x for x in calls))
ck('fresh_FORMAL_marker_and_directory', "(HERE / 'FORMAL_STARTED.json').open('x'" in launcher_source and 'runtime.mkdir(exist_ok=False)' in launcher_source)
ck('new_runtime_path', Path(plan['runtime_root']) == B/'r')
driver_source = raw(OLD/'driver.py').decode()
consumer_source = raw(OLD/'consumer.py').decode()
ck('legacy_absolute_deadline_not_reset', 'deadline = began + 450_000_000_000' in driver_source and 'episode_deadline_ns=deadline, turn_deadline_ns=deadline' in driver_source)
ck('legacy_gate_requires_actual_exit_allows_receipt_unknown', "(row.get('runtime_exit') or {}).get('confirmed') is True" in driver_source and "row.get('bridge_cleanup', {}).get('confirmed') is not False" in driver_source)
ck('legacy_consumer_waits_held_handle', 'runtime_handle.wait_exit(held_runtime, deadline)' in consumer_source)
ck('legacy_batch_count_exists', "'actual_CLI_processes': sum(row.get('consumer_pid') is not None for row in records)" in driver_source)
correction = read(B/'PREPARATION_NOTE_CORRECTION.json')
ck('correction_source_digest_and_retained_note', correction['legacy_source_sha256'] == h(driver_source.encode()) and correction['original_preparation_note_retained'] and not correction['source_or_results_changed_after_formal'])
preparation = read(B/'PREPARATION.json')
ck('old_wrong_note_retained', 'nonexistent' in json.dumps(preparation))
for folder in [B/'r', B/'local/N1', B/'local/P1']:
    before, after = read(folder/'POINTERS_BEFORE.json'), read(folder/'POINTERS_AFTER.json')
    ck('13_pointer_assertions_before_after_identical', eq(before,after) and len(before['checks']) == 13 and all(v is True for v in before['checks'].values()), folder=str(folder))
    for field, name in [('candidate_driver','driver.py'),('candidate_consumer','consumer.py'),('candidate_matcher','result_contract.py')]:
        ck('runtime_pointer_source_name', Path(before[field]) == CAND/name, folder=str(folder), field=field)
ck('exact_two_local_attempt_directories', sorted(p.name for p in (B/'local').iterdir() if p.is_dir()) == ['N1','P1'])
run = read(B/'r/RUN_RESULT.json')
sequence = ['N1','P1','P2','N2','N3','P3']
ck('all_fixed_six_no_skips', [r['slot'] for r in run['records']] == sequence and all(r['execution_state']=='completed' for r in run['records']))
ck('fresh_threads_and_CLI_count', len(set(run['observed_fresh_threads'])) == run['actual_CLI_processes'] == run['actual_routes'] == 6)
formal_start = read(B/'FORMAL_STARTED.json')
ck('formal_source_freeze_reference', formal_start['freeze_sha256'] == h(raw(B/'FROZEN.json')))
for q in formal_start['local_qualification']:
    ck('local_pass_source_reference', q['attempts'] == 1 and h(raw(q['path'])) == q['sha256'])

summaries = []
dirs = [(B/'local/N1/LOCAL_N1',False),(B/'local/P1/LOCAL_P1',False)] + [(B/'r'/s,True) for s in sequence]
for folder, formal in dirs:
    label = folder.name
    row = read(folder/'RESULT.json')
    c = read(folder/'c/CONSUMER.json')
    t = read(folder/'FINAL_TIMING.json')
    ct = read(folder/'c/FINAL_TIMING.json')
    config = read(folder/'ACTOR_CONFIG.json')
    endpoint = read(folder/'ENDPOINT.json')
    identity = read(folder/'o/IDENTITY.json')
    ck('original_deadline_single_end_to_end', row['deadline_ns'] == row['started_ns']+450_000_000_000 == c['deadline_ns'] == c['episode_deadline_ns'] == t['original_deadline_ns'] == ct['original_turn_deadline_ns'] == ct['episode_deadline_ns'] == config['worker_deadline_ns'] == endpoint['chain_deadline_ns'] == identity['worker_deadline_ns'], slot=label)
    ck('full_close_within_original_deadline', t['accepted_success'] and ct['accepted_success'] and t['result_closed_ns'] < row['deadline_ns'] and ct['consumer_record_closed_ns'] <= t['result_closed_ns'], slot=label)
    ck('completed_original_acceptance_no_errors', row['outer_valid_completion'] and c['valid_completion'] and c['safe_to_continue'] and not row['errors'] and not row['common_image_faults'] and not row['stop_remaining_reasons'] and not c['errors'] and not c['unexpected_tool_deviations'] and not c['provider_retry_observations'], slot=label)
    ck('unchanged_runtime_budgets', config['max_tool_calls'] == identity['max_tool_calls'] == 12 and config['max_render_attempts'] == identity['max_render_attempts'] == 6, slot=label)
    for name,pid in [('consumer_process_cleanup',row['consumer_pid']),('owner_process_cleanup',row['owner_pid'])]:
        clean = row[name]
        ck('CLI_actor_real_handle_exit0', clean['pid']==pid and clean['confirmed'] and clean['reaped'] and clean['exit_code']==0 and clean['process_handle_closed'] and not clean['kill_requested'] and not clean['errors'] and all(clean['pipes_closed'].values()) and clean['closed_ns'] < t['result_closed_ns'], slot=label, process=name)
    ck('actor_identity_endpoint_close', row['owner_pid']==endpoint['actor_pid']==identity['actor_pid']==row['owner_close']['actor_pid'] and row['owner_close']['server_thread_stopped'] and row['owner_close']['confirmed'], slot=label)
    binding = read(folder/'c/RUNTIME_BINDING.json')
    ck('binding_copies_match', eq(binding,c['runtime_binding']) and eq(binding,row['runtime_binding']),slot=label)
    start = read(binding['STARTED_path'])
    ck('live_STARTED_binding', eq(start,binding['stdio_STARTED']) and binding['confirmed'] and binding['after_stdio_STARTED'] and binding['runtime_pid']==start['pid'] and binding['launcher_pid']==row['consumer_pid'] and start['started_ns'] < binding['proved_ns'] < c['process_exit_ns'], slot=label)
    chain = binding['parent_chain']
    ck('process_ancestry_and_creation_times', chain[0]['pid']==binding['runtime_pid'] and chain[-1]['pid']==row['consumer_pid'] and chain[0]['created_filetime']==binding['runtime_created_filetime'] and chain[-1]['created_filetime']==binding['launcher_created_filetime'] and all(a['parent_pid']==b['pid'] for a,b in zip(chain,chain[1:])),slot=label)
    ck('actual_executable_matches_frozen_base', binding['actual_executable']==binding['expected_executable'] and binding['actual_executable_sha256']==binding['expected_executable_sha256']==freeze[str(base)],slot=label)
    ex = c['runtime_exit']
    ck('retained_runtime_handle_exit_confirmed', eq(ex,row['runtime_exit']) and ex['confirmed'] and ex['exited'] and ex['handle_closed'] and not ex['error'] and ex['original_deadline_ns']==row['deadline_ns'] and ex['closed_ns'] < ct['consumer_record_closed_ns'],slot=label)
    close = read(folder/'o/CLOSE.json')
    ck('actor_close_record_original', eq(close,row['owner_close']) and not close['errors'],slot=label)
    stdout = raw(folder/'c/stdout.raw.bin')
    events=[json.loads(line) for line in stdout.splitlines() if line.strip()]
    calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    ck('stdout_matches_consumer_completed_calls', h(stdout)==c['stdout_raw_sha256'] and len(stdout)==c['stdout_raw_bytes'] and eq(calls,[x['item'] for x in c['tool_calls']]),slot=label)
    ck('no_raw_top_level_error_one_terminal', not any(e.get('type') in ['error','turn.failed'] for e in events) and sum(e.get('type')=='turn.completed' for e in events)==1,slot=label)
    arc = read(folder/'c/ARCHIVE.json')
    binding_record = read(folder/'c/BUSINESS_SOURCE_BINDING.json')
    ck('archive_candidate_binding_record', not arc['business_binding_errors'] and not binding_record['binding_errors'] and eq(arc['result_contracts'],binding_record['result_contracts']) and len(calls)==len(arc['result_contracts']),slot=label)
    for source in binding_record['sources']:
        a,b=raw(source['original']),raw(folder/'c'/source['copy'])
        ck('owner_original_copy_exact', a==b and len(a)==source['bytes'] and h(a)==source['sha256'],slot=label,copy=source['copy'])
    bridge=Path(binding['STARTED_path']).parent
    mcp_requests={};mcp_responses={}
    for wire in sorted(bridge.glob('*/TX.bin')):
        msg=json.loads(raw(wire))
        if 'id' in msg:mcp_requests[str(msg['id'])]=msg
    for wire in sorted(bridge.glob('*/RX.bin')):
        msg=json.loads(raw(wire))
        if 'id' in msg:mcp_responses[str(msg['id'])]=msg
    tcp_calls=[]
    for rpc in sorted((folder/'o').glob('rpc_*')):
        tx,rx=read(rpc/'TCP_TX.bin'),read(rpc/'TCP_RX.bin')
        message=tx['args']['message'];response=rx['result']
        ck('TCP_request_response_and_MCP_body', tx['request_id']==rx['request_id'] and rx['ok'] is True and eq(message,mcp_requests[str(message['id'])]) and eq(response,mcp_responses[str(response['id'])]),slot=label,rpc=rpc.name)
        if message.get('method')=='tools/call':tcp_calls.append((message,response))
    ck('all_attempts_bound_across_three_layers', len(tcp_calls)==len(calls)==len(read(folder/'o/TOOLS.json')['tools'])==row['actual_tool_calls'],slot=label)
    for i,(item,(request,response),contract) in enumerate(zip(calls,tcp_calls,arc['result_contracts']),1):
        req=read(folder/f'o/tool_{i:02}/REQUEST.json');res=read(folder/f'o/tool_{i:02}/RESPONSE.json')
        ck('RPC_owner_Tcp_exact_and_ID', eq(req,request) and eq(res,response) and type(req['id']) is type(res['id']) and req['id']==res['id'],slot=label,attempt=i)
        ck('CLI_request_matches_original', item['tool']==req['params']['name'] and eq(item['arguments'],req['params']['arguments']),slot=label,attempt=i)
        error=res['result']['isError'];classification='tool_error' if error else 'success'
        ck('CLI_result_full_content_and_status', item['status']==('failed' if error else 'completed') and item['error'] is None and set(item['result'])=={'content','structured_content'} and item['result']['structured_content'] is None and eq(item['result']['content'],res['result']['content']),slot=label,attempt=i)
        ck('candidate_classification_preserved', contract['attempt']==i and contract['matched'] is True and contract['classification']==classification,slot=label,attempt=i)
        if formal:
            ck('formal_success_only',not error,slot=label,attempt=i);formal_tools+=1
        else:
            body=json.loads(res['result']['content'][0]['text'])
            ck('local_actual_ValueError_then_42', (error and body['error']['type']=='ValueError' and "raise ValueError('newlocal_m4_active_coverage_consumption_002_value_error')"==req['params']['arguments']['code']) if i==1 else (not error and body['stdout']=='42\n' and body['error'] is None and req['params']['arguments']['code']=='print(6 * 7)'),slot=label,attempt=i)
            local_tools+=1
    if formal:
        ck('formal_thin_exit1_EOF_unknown',ex['exit_code']==1 and c['bridge_cleanup']['confirmed'] is None and c['bridge_cleanup']['receipt_status']=='unknown' and c['bridge_cleanup']['missing_exit_count']==1 and not (bridge/'EXIT.json').exists(),slot=label)
        ck('formal_fresh_exec_only',c['expected_thread_id'] is None and c['turn_index']==1 and c['execution_kind']=='provider' and 'resume' not in c['argv'] and c['status']=='completed',slot=label)
    else:
        local=read(folder.parent/'LOCAL_RESULT.json');fixture=read(folder/'c/LOCAL_FIXTURE.json');exit_receipt=read(bridge/'EXIT.json')
        ck('local_EOF_exit0_without_kill',ex['exit_code']==0 and c['bridge_cleanup']['confirmed'] is True and fixture['normal_EOF_requested'] and fixture['normal_exit_observed'] and fixture['thin_wait_exit_code']==0 and not fixture['thin_cleanup']['kill_requested'] and exit_receipt['normal_exit'] and exit_receipt['pid']==start['pid'] and exit_receipt['instance_nonce']==start['instance_nonce'],slot=label)
        ck('local_first_pass_zero_provider_image_raster',local['attempt']==1 and local['passed'] and local['new_Pro_sessions']==local['new_image_constructions']==local['new_renders']==0 and len(calls)==2,slot=label)
    check_zip(Path(arc['archive']),folder/'c',arc['source_files_sha256'],arc['archive_sha256'],arc['archive_bytes'])
    o=row['originals'];check_zip(Path(o['path']),folder,o['members_sha256'],o['sha256'],o['bytes'])
    summaries.append({'slot':label,'formal':formal,'tools':len(calls),'runtime_exit_code':ex['exit_code'],'EOF_receipt':c['bridge_cleanup']['receipt_status'] if formal else 'confirmed','actual_exit_confirmed':ex['confirmed']})

ck('all_16_ZIP_784_members',zip_count==16 and zip_members==784)
ck('14_formal_success_4_local_calls',formal_tools==14 and local_tools==4)
results={'author_commit':'c556d29156e7d65fc02238dca63321ac062d2c1a','checks_count':len(checks),'passed':sum(x['passed'] for x in checks),'failed':[x for x in checks if not x['passed']],'checks':checks,'slots':summaries,'ZIP_count':zip_count,'ZIP_members':zip_members,'formal_tool_successes':formal_tools,'formal_tool_errors':0,'local_tool_errors':2,'local_success_recoveries':2,'new_CLI_model_actor_Blender_raster_calls':0,'author_code_imports_or_execution':0,'AL_binding':'own child handle bound; parent_read_only','scope':'Independent offline source inspection and data parsing; historical OS handles not re-opened; actor/runtime historical observations validated for consistency, not reproduced.'}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'INPUTS.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
(OUT/'RESULTS.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in results.items() if k not in ['checks','slots']},ensure_ascii=False))
