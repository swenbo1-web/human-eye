"""Independent offline lifecycle audit. Does not import author code or run processes."""
import hashlib
import json
from pathlib import Path

BASE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
OUT = Path(__file__).resolve().parent
checks, inputs, routes = [], {}, {}

def raw(path):
    data = Path(path).read_bytes()
    inputs[str(path)] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return data

def doc(path): return json.loads(raw(path))
def check(name, condition): checks.append({'name':name,'passed':bool(condition)})

snapshot = doc(BASE/'EXIT_OBSERVATION.json')
actual_threads = []
for group in ('N','P'):
    folder = BASE/'r'/group
    outer = doc(folder/'RESULT.json')
    timing = doc(folder/'FINAL_TIMING.json')
    consumer = doc(folder/'c/CONSUMER.json')
    close = doc(folder/'o/CLOSE.json')
    endpoint = doc(folder/'ENDPOINT.json')
    events = [json.loads(line) for line in raw(folder/'c/events.jsonl').splitlines()]
    threaded = [row for row in events if row['event']['type']=='thread.started']
    completed = [row for row in events if row['event']['type']=='turn.completed']
    failures = [row for row in events if row['event']['type'] in ('error','turn.failed')]
    warnings = [row for row in events if row['event'].get('item',{}).get('type')=='error']
    calls = [row for row in events if row['event']['type']=='item.completed' and row['event'].get('item',{}).get('type')=='mcp_tool_call']
    messages = [row for row in events if row['event']['type']=='item.completed' and row['event'].get('item',{}).get('type')=='agent_message']
    actual_threads.append(consumer['thread_id'])
    check(group+'/one_fresh_thread', len(threaded)==1 and threaded[0]['event']['thread_id']==consumer['thread_id'] and consumer['expected_thread_id'] is None)
    check(group+'/one_completed_no_turn_failed', len(completed)==1 and not failures)
    check(group+'/two_item_error_warnings_retained', len(warnings)==2 and any('fallback metadata' in w['event']['item']['message'] for w in warnings) and any('skip_host_skill_discovery' in w['event']['item']['message'] for w in warnings))
    check(group+'/final_matches_raw_events', messages[-1]['event']['item']['text']==consumer['final'] and raw(folder/'c/PUBLIC_FINAL.txt').decode('utf8')==consumer['final'])
    check(group+'/all_tool_receipts_precede_final', all(row['perf_ns'] < messages[-1]['perf_ns'] for row in calls))
    check(group+'/final_then_completed_then_exit', messages[-1]['perf_ns']==consumer['final_received_ns'] < completed[0]['perf_ns']==consumer['turn_completed_ns'] < consumer['process_exit_ns'])
    check(group+'/no_replayed_tool', len(calls)==(2 if group=='N' else 1) and len({r['event']['item']['id'] for r in calls})==len(calls))
    check(group+'/no_python_tool', all(r['event']['item']['tool']!='execute_python' for r in calls))
    check(group+'/CLI_exit0_reaped_and_closed', consumer['process_cleanup']==outer['consumer_process_cleanup'] and consumer['process_cleanup']['confirmed'] is True and consumer['process_cleanup']['exit_code']==0 and consumer['process_cleanup']['reaped'] is True and consumer['process_cleanup']['process_handle_closed'] is True and all(consumer['process_cleanup']['pipes_closed'].values()) and not consumer['process_cleanup']['kill_requested'] and not consumer['process_cleanup']['errors'])
    check(group+'/CLI_PID_bound', consumer['consumer_pid']==consumer['process_cleanup']['pid'])
    check(group+'/reader_threads_stopped', consumer['readers_stopped'] is True)
    check(group+'/original_deadline_retained', outer['deadline_ns']==consumer['deadline_ns']==endpoint['chain_deadline_ns']==timing['original_deadline_ns']==outer['started_ns']+450_000_000_000)
    check(group+'/no_deadline_fire', consumer['deadline_timer_fired'] is False)
    check(group+'/owner_PID_bound', outer['owner_pid']==endpoint['actor_pid']==close['actor_pid']==outer['owner_process_cleanup']['pid'])
    check(group+'/owner_exit0_reaped_and_closed', outer['owner_process_cleanup']['confirmed'] is True and outer['owner_process_cleanup']['exit_code']==0 and outer['owner_process_cleanup']['reaped'] is True and outer['owner_process_cleanup']['process_handle_closed'] is True and not outer['owner_process_cleanup']['kill_requested'] and not outer['owner_process_cleanup']['errors'])
    check(group+'/owner_listener_and_thread_closed', close['confirmed'] is True and close['server_thread_stopped'] is True and not close['errors'])
    check(group+'/owner_close_after_consumer_cleanup', consumer['cleanup_end_ns'] <= close['ended_ns'] <= outer['owner_process_cleanup']['closed_ns'])
    check(group+'/closure_before_publication_deadline', outer['owner_process_cleanup']['closed_ns'] < timing['result_closed_ns'] < timing['original_deadline_ns'])
    check(group+'/timer_raw_interval', timing['elapsed_ns']==timing['result_closed_ns']-outer['started_ns'])
    check(group+'/actual_success_scoped_to_known_owners', outer['outer_valid_completion'] is True and consumer['valid_completion'] is True and not outer['errors'] and not consumer['errors'])
    folders = list((folder/'c/attachments').glob('bridge_*'))
    check(group+'/one_actual_thin_instance', len(folders)==1)
    bridge = folders[0]
    start = doc(bridge/'STARTED.json')
    check(group+'/real_EXIT_absent', not (bridge/'EXIT.json').exists())
    receipt = consumer['bridge_cleanup']
    check(group+'/unknown_preserved', receipt['confirmed'] is None and receipt['receipt_status']=='unknown' and receipt['missing_exit_count']==1 and receipt['instances'][0]['exit'] is None and receipt['instances'][0]['confirmed'] is None)
    check(group+'/STARTED_matches_receipt', receipt['instances'][0]['started']==start and outer['bridge_cleanup']==receipt)
    check(group+'/distinct_actual_process_roles', len({start['pid'],outer['owner_pid'],consumer['consumer_pid']})==3)
    check(group+'/thin_STARTED_precedes_tools', start['started_ns'] < min(row['perf_ns'] for row in calls))
    check(group+'/null_allowed_is_limited_scope', consumer['safe_to_continue'] is True and 'unknown thin EXIT is retained' in consumer['safe_to_continue_scope'])
    observed = next(row for row in snapshot['observations'] if row['group']==group)
    check(group+'/late_absence_only', observed['recorded_stdio_pid']==start['pid'] and observed['process_present_at_query'] is False and snapshot['observed_after_ns'] > timing['result_closed_ns'] and snapshot['normal_EXIT_receipt'].startswith('unknown'))
    local_folder=BASE/'local/a01'/group
    local_consumer=doc(local_folder/'c/CONSUMER.json')
    local_bridge=list((local_folder/'c/attachments').glob('bridge_*'))
    local_start=doc(local_bridge[0]/'STARTED.json'); local_end=doc(local_bridge[0]/'EXIT.json')
    check(group+'/synthetic_EOF_identity', all(local_start[k]==local_end[k] for k in ('pid','instance_nonce','started_ns')) and local_end['normal_exit'] is True and local_end['backend_close_requested'] is False)
    check(group+'/synthetic_not_real_substitution', local_consumer['execution_kind']=='synthetic_local_process' and local_consumer['bridge_cleanup']['confirmed'] is True and local_start['pid']!=start['pid'])
    routes[group] = dict(actor_pid=outer['owner_pid'],CLI_pid=consumer['consumer_pid'],stdio_pid=start['pid'],thread_id=consumer['thread_id'],CLI_exit_code=consumer['exit_code'],actor_exit_code=outer['owner_process_cleanup']['exit_code'],
        CLI_actor_handle_cleanup_confirmed=True,stdio_normal_EOF='unknown',stdio_actual_exit_time='unknown',stdio_historical_exit_code='unknown',thin_receipt_absent=True,
        outer_valid_completion=outer['outer_valid_completion'],consumer_safe_to_continue=consumer['safe_to_continue'],
        tool_completed_count=len(calls),CLI_item_error_warning_count=len(warnings),
        last_tool_to_final_ns=consumer['final_received_ns']-max(row['perf_ns'] for row in calls),
        turn_completed_to_CLI_exit_ns=consumer['process_exit_ns']-consumer['turn_completed_ns'],
        final_to_CLI_exit_ns=consumer['process_exit_ns']-consumer['final_received_ns'],
        late_PID_absence_observed_after_route_ns=snapshot['observed_after_ns']-timing['result_closed_ns'],
        recorded_outer_interval_ns=timing['elapsed_ns'])

check('two_distinct_fresh_threads',len(set(actual_threads))==2)
for path in [BASE/'consumer.py',BASE/'driver.py',BASE/'actor.py',BASE/'fake_cli.py',
             BASE.parent/'native_plugin_complex_003/reused/stdio_attach.py',
             BASE.parent/'m4_surface_scan_compact_consumption_001/runtime/consumer_transport.py',
             BASE.parent/'m1_task_entry_001_eval/preflight_client.py',
             BASE.parent/'m4_active_coverage_003/launch.py']:
    raw(path)
result=dict(author_commit='a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff',review_kind='independent offline raw records and source semantics; no author execution',
            checks=checks,passed=sum(row['passed'] for row in checks),failed=[row for row in checks if not row['passed']],input_files=len(inputs),routes=routes,
            decision='Image receipts and observed final answers remain valid; CLI/actor exit confirmed; thin process graceful EOF and exit time remain unknown.',
            unrun=['Historical OS process-handle observation for stdio','Any new CLI/actor/stdio/model/renderer/Blender/provider process','Runtime failure injection'],
            next_scope='Do not repeat Pro image qualification. If next formal task promises complete process cost, acquire and observe the thin process handle during its lifetime, separately from graceful EOF; fix outer status wiring in the next harness preparation.')
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('passed','failed','input_files','routes')},ensure_ascii=False))
