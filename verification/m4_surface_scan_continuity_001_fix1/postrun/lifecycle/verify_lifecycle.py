"""Read-only FIX1 C attempt audit, including online/closed-archive ordering.

Reuses the prior lifecycle audit's evidence model. Starts no process or RPC.
Only new derived material in this directory is written.
"""

import ast
import hashlib
import json
from pathlib import Path
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_continuity_001'
checks = []
inputs = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    try:
        name = path.relative_to(ROOT).as_posix()
    except ValueError:
        name = path.as_posix()
    record = {'path': name, 'bytes': len(data), 'sha256': digest(data)}
    if name in inputs:
        assert inputs[name] == record, name
    inputs[name] = record
    return data


def read(path):
    return json.loads(raw(path))


def need(condition, label):
    checks.append(label)
    if not condition:
        raise AssertionError(label)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')


def identity(status):
    keys = ('episode_id', 'owner_pid', 'native_pid', 'native_host', 'native_port', 'native_workspace',
            'product_launcher_pid', 'product_runtime_proof', 'session_id', 'worker_deadline_ns')
    return {key: status[key] for key in keys}


def main():
    preparation = read(BATCH / 'PREPARATION.json')
    need(len(preparation['files']) == 1189, '1189 frozen content files plus preparation itself')
    for item in preparation['files']:
        data = raw(BATCH / item['path'])
        need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'fixed preparation ' + item['path'])
    for name, expected in preparation['external_sha256'].items():
        need(digest(raw(name)) == expected, 'fixed external source ' + name)
    previous = read(OLD / 'DELIVERY_MANIFEST.json')
    need(previous['file_count'] == len(previous['files']) == 367, 'previous 001 delivery scope')
    for item in previous['files']:
        data = raw(OLD / item['path'])
        need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'old 001 preserved ' + item['path'])

    repair = read(BATCH / 'preparation_repair/attempt_01/FAILURE.json')
    regression = read(BATCH / 'preparation_repair/attempt_01/PATH_REGRESSION.json')
    original_plan = read(BATCH / 'preparation_repair/attempt_01/PREPARATION_BEFORE.json')
    need(repair['preparation_commit'] == '8000b52fa333339a8e249051329982768c136d5d'
         and repair['ENGINEERING_STARTED_exists'] is False and repair['episodes_directory_exists'] is False
         and repair['new_Blender_model_API_calls'] == 0, '8000 guard failure occurred before reservation and live')
    need(regression['current_committed_bytes_match'] and regression['prior_batch_path_rejected']
         and regression['new_live_episodes'] == 0, 'prelaunch path guard correction has no live sample')
    need(original_plan['preparation_parent_commit'] == 'a206a96e51ca6293ea555f17960b964ba02f0606', 'original preparation retained separately')

    outer = read(BATCH / 'ENGINEERING_RESULT.json')
    reservation = read(BATCH / 'ENGINEERING_STARTED.json')
    need(reservation['groups'] == ['C'] and reservation['maximum_episodes'] == 1, 'one exclusive FIX1 C reservation')
    need(reservation['preparation_commit'] == 'e06597f92d1193b40e9a62b78919a3125e4e346d', 'corrected preparation used for actual live')
    need(outer['planned_episodes'] == outer['started_episodes'] == 1 and outer['N_episodes'] == 0 and outer['passed'] is False,
         'one actual C episode no new N and overall failed')
    need(outer['model_calls'] == outer['API_calls'] == reservation['model_calls'] == 0, 'zero actual model/API calls')

    folder = BATCH / 'episodes/C'
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            raw(path)
    result = read(folder / 'RESULTS.json')
    timing = read(folder / 'FINAL_TIMING.json')
    publication = read(folder / 'TIMING_PUBLICATION.json')
    config = read(folder / 'ACTOR_CONFIG.json')
    launch = read(folder / 'ACTOR_LAUNCH.json')
    endpoint = read(folder / 'ENDPOINT.json')
    owner = read(folder / 'owner/IDENTITY.json')
    session = read(folder / 'owner/native/SESSION.json')
    ready = read(folder / 'owner/native/READY.json')
    continuity = read(folder / 'owner/CONTINUITY.json')
    close = read(folder / 'owner/CLOSE.json')
    worker = read(folder / 'owner/native/WORKER_CLOSED.json')
    finish = read(folder / 'OWNER_FINISH.json')
    tools = read(folder / 'owner/TOOLS.json')
    initial = read(folder / 'owner/INITIAL.json')
    final = read(folder / 'owner/FINAL.json')
    proof = read(folder / 'owner/PRODUCT_RUNTIME_PROOF.json')
    status = result['initial_status']
    episode = 'continuity-fix1-engineering-C-001'
    deadline = timing['original_deadline_ns']
    need(result['episode_id'] == config['episode_id'] == continuity['episode_id'] == status['episode_id'] == episode, 'actual episode ID')
    need(deadline - timing['started_ns'] == 590_000_000_000, 'original absolute 590 second window')
    need(deadline == config['worker_deadline_ns'] == launch['deadline_ns'] == session['deadline_ns'] == ready['deadline_ns']
         == endpoint['chain_deadline_ns'] == worker['original_deadline_ns'], 'one deadline across all owned components')
    need(timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns'], 'integer full wall interval')
    need(timing['within_590s'] is True and timing['accepted_success'] is False
         and publication['closed_ns'] < deadline, 'failure and actual publication within original deadline')
    need(owner['actor_parent_pid'] == launch['pid'] and owner['actor_pid'] == endpoint['actor_pid'] == status['owner_pid'] == close['actor_pid'],
         'launcher and actual actor identities')
    need(session['pid'] == ready['pid'] == status['native_pid'] == worker['pid'], 'one actual owned Blender PID')
    need(session['host'] == status['native_host'] and session['port'] == status['native_port']
         and Path(session['workspace']) == Path(status['native_workspace']), 'actual backend endpoint/workspace')
    need(proof == status['product_runtime_proof'] and proof['confirmed'] and proof['before_consumer_business'], 'actual runtime proof before business')
    need(proof['launcher_pid'] == status['product_launcher_pid'] == close['plugin_close']['launcher_pid'], 'product launcher identity')
    need(owner['runtime_identity']['source_sha256'] == preparation['product_source_sha256']
         == '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6', 'fixed loaded compact product source')
    need(len(result['business']) == tools['calls'] == tools['attempts'] == close['tool_attempts'] == 1, 'one actual product business attempt')
    need(result['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}, 'original failed and unrun counts preserved')
    need([row['turn_id'] for row in continuity['completed_turns']] == ['BASE'] and continuity['active_turn'] is None,
         'BASE ended before qualification rejected')
    need(not (folder / 'REPEAT').exists() and not (folder / 'EDIT').exists(), 'REPEAT and EDIT clients never launched')

    turn = read(folder / 'TURN_BASE.json')
    thin = read(folder / 'BASE/THIN_TURN.json')
    boundary = continuity['completed_turns'][0]
    need(turn['thin'] == thin and thin['confirmed'] and thin['exit_code'] == 0 and thin['process_reaped'], 'actual BASE thin success')
    need(identity(turn['status_before']) == identity(status) == identity(turn['status_after']), 'owner/backend/product/session constant during BASE')
    need(not turn['status_before']['owner_close_called'] and not turn['status_after']['owner_close_called'], 'thin EOF did not finish owner')
    need(read(folder / 'BASE/ENDPOINT.json') == endpoint, 'thin attaches existing episode endpoint')
    need(boundary['deadline_ns'] == thin['deadline_ns'] == deadline and boundary['business_attempts'] == 1,
         'BASE deadline and one actual call')
    need(boundary['started_ns'] < thin['started_ns'] < thin['process_exit_ns'] <= thin['ended_ns'] <= boundary['ended_ns'] < turn['ended_ns'] < deadline,
         'thin success then end_turn then qualification failure')
    tx = raw(folder / 'BASE/TX.bin')
    rx = raw(folder / 'BASE/RX.bin')
    requests = [json.loads(line) for line in tx.splitlines()]
    responses = [json.loads(line) for line in rx.splitlines()]
    need(requests == thin['requests'] and responses == thin['responses'], 'full actual stdio byte projection')
    need([row['method'] for row in requests] == ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'], 'two metadata RPC one notice one business')
    need([row['id'] for row in responses] == thin['request_ids'] == [row['id'] for row in requests if 'id' in row], 'request response IDs')
    instance = thin['bridge_cleanup']['instances']
    need(len(instance) == 1 and thin['bridge_cleanup']['confirmed'] is True, 'one real confirmed thin instance')
    bridge = Path(instance[0]['directory'])
    start = read(bridge / 'STARTED.json')
    exit_record = read(bridge / 'EXIT.json')
    need(start == instance[0]['started'] and exit_record == instance[0]['exit'], 'actual thin START EXIT binding')
    need(all(start[key] == exit_record[key] for key in ('pid', 'kind', 'started_ns', 'instance_nonce')), 'thin process instance identity')
    need(exit_record['normal_exit'] is True and exit_record['backend_close_requested'] is False and exit_record['requests'] == 4,
         'actual EOF normal without backend close')
    need(exit_record['complete_tx_bytes'] == len(tx) and exit_record['complete_rx_bytes'] == len(rx), 'raw thin byte counters')
    for number, request in enumerate(requests, 1):
        call = bridge / str(number).zfill(3)
        need(json.loads(raw(call / 'TX.bin')) == request, 'thin original request ' + str(number))
        if 'id' in request:
            need(json.loads(raw(call / 'RX.bin')) == next(row for row in responses if row['id'] == request['id']), 'thin original response ' + str(number))
    attempt = read(folder / 'owner/tool_01/ATTEMPT.json')
    need(read(folder / 'owner/tool_01/REQUEST.json') == turn['request'] == requests[-1], 'actual business request owner/thin equality')
    need(read(folder / 'owner/tool_01/RESPONSE.json') == turn['response'] == responses[-1], 'actual business response owner/thin equality')
    need(not attempt['is_error'] and attempt['exception'] is None and 0 < attempt['elapsed_ns'] < 30_000_000_000, 'successful actual business within 30 seconds')
    need(requests[-1]['params']['arguments'] == {'session_id': episode, 'include_image': False, 'query': {'mode': 'surface_scan', 'threshold_m': .002}},
         'ordinary default scan same configured session')

    controls = sorted((folder / 'owner').glob('control_*'))
    operations = []
    for number, control in enumerate(controls, 1):
        request = read(control / 'REQUEST.json')
        receipt = read(control / 'RECEIPT.json')
        response = read(control / 'RESPONSE.json')
        administrative = read(folder / ('ADMIN_' + str(number).zfill(2) + '.json'))
        need(administrative['request'] == request and administrative['response']['result'] == response, 'management original binding ' + str(number))
        need(receipt == continuity['events'][number - 1] and receipt['error'] is None, 'management receipt ' + str(number))
        operations.append(receipt['operation'])
    need(operations == ['status', 'status', 'begin_turn', 'end_turn'], 'actual management prefix no edit or extra turn')
    need(not continuity['edit_attempted'] and not continuity['edit_verified'] and worker['qa_patch_applied'] is False, 'no actual EDIT attempted')
    need(initial == final and close['geometry_unchanged'] and worker['initial_geometry_fingerprint'] == worker['accepted_geometry_fingerprint']
         == worker['final_geometry_fingerprint'], 'unchanged BASE terminal geometry')
    need(finish['close'] == close and finish['confirmed'] and finish['exit_code'] == 0 and close['confirmed'], 'actual outer/owner finish confirmed')
    need(close['native_close']['process_reaped'] and close['native_close']['exit_code'] == 0 and close['native_close']['response']['status'] == 'closed',
         'actual native closure and reap')
    need(close['plugin_close']['confirmed'] and close['plugin_close']['exit_code'] == 0 and close['plugin_close']['reader_stopped'], 'product launcher reader close')
    need(close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exited'] and close['product_runtime_exit']['exit_code'] == 0
         and close['product_runtime_exit']['handle_closed'], 'actual runtime retained handle exit')
    need(close['worker_closed'] == worker and not worker['poisoned'] and close['asset_unchanged'] and close['expected_terminal_geometry_matches'], 'protected terminal state and original asset')
    need(close['ended_ns'] <= timing['business_receipts_closed_ns'] < publication['started_ns'], 'owned closure included before final timing publication')

    host_events = [json.loads(line) for line in raw(folder / 'owner/native/WORKER_EVENTS.jsonl').splitlines()]
    actual_capture = [row for row in host_events if turn['started_ns'] <= row.get('started_ns', -1) <= thin['ended_ns']]
    need(len(actual_capture) == 1 and actual_capture[0]['sequence'] == 2 and actual_capture[0]['status'] == 'completed', 'exactly one actual request-local capture')
    need(actual_capture[0]['terminal_geometry_and_file_checks_passed'] and actual_capture[0]['changed_or_new_PNG_files'] == []
         and actual_capture[0]['render_events_before'] == actual_capture[0]['render_events_after'], 'actual capture protected zero images')
    final_snapshot = next(row for row in host_events if row['sequence'] == 3)
    need(turn['ended_ns'] < final_snapshot['started_ns'], 'qualification failure before cleanup snapshot')
    audit = [json.loads(line) for line in raw(folder / 'owner/audit.jsonl').splitlines()]
    body = turn['body']
    observed = [row for row in audit if row.get('event') == 'observe' and row.get('trace_id') == body['trace_id']]
    traces = [row for row in audit if row.get('event') == 'request_trace' and row.get('trace_id') == body['trace_id']]
    need(len(observed) == len(traces) == 1 and observed[0]['pid'] == traces[0]['pid'] == proof['runtime_pid'], 'actual scan trace and product PID')
    work, trace = observed[0]['task_work'], traces[0]['trace']
    need(body['status'] == 'complete' and body['result_kind'] == 'surface_scan' and len(body['matches']) == 71, 'actual complete 71 matching rows')
    need(body['coverage'] == {'objects': 24, 'total_pairs': 276, 'bound_excluded': 164, 'measured_match': 71,
                            'measured_nonmatch': 41, 'unknown': 0, 'deferred': 0, 'catalog_scope_confirmed': True}, 'actual full coverage and no unresolved')
    need(work['kernel_calls'] == 112 and work['measurement_cache_before']['measurement_entries'] == 0
         and work['measurement_cache_after']['measurement_entries'] == 112, 'actual first scan 112 new kernel and measurement entries')
    need(sum(span['name'] == 'host.capture' for span in trace['spans']) == 1 and trace['annotations']['mcp_native_image_block_count'] == 0,
         'one capture span zero image delivery')
    need(body['binding']['runtime_source_sha256'] == preparation['product_source_sha256'], 'actual result fixed product generation')

    errors = result['errors']
    need(len(errors) == len(turn['errors']) == 1 and errors[0] == turn['errors'][0], 'one original qualification exception')
    error = errors[0]
    need(error['type'] == 'FileNotFoundError' and 'WIRE' in error['message'] and 'INDEX.json' in error['message'], 'actual missing closed archive error')
    need('verify_business' in error['traceback'] and 'read_capture' in error['traceback'] and 'read_bytes' in error['traceback'],
         'failure in capture reader before fact verifier')
    runner_source = raw(BATCH / 'engineering/run_candidate.py').decode('utf8')
    qualification_source = raw(BATCH / 'qualification/verify_continuity.py').decode('utf8')
    worker_source = raw(ROOT / 'verification/m4_surface_scan_001_opt1/engineering/pose_native_metered.py').decode('utf8')
    meter_source = raw(ROOT / 'verification/m4_surface_scan_001_opt1/engineering/wire_meter.py').decode('utf8')
    runner_ast = ast.parse(runner_source)
    verify_function = next(node for node in runner_ast.body if isinstance(node, ast.FunctionDef) and node.name == 'verify_business')
    calls = [(node.lineno, node.func.attr) for node in ast.walk(verify_function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    need(next(line for line, name in calls if name == 'read_capture') < next(line for line, name in calls if name == 'verify_c_turn'),
         'actual runner requires closed wire before source/fact validation')
    meter_ast = ast.parse(meter_source)
    flush = next(node for node in meter_ast.body if isinstance(node, ast.FunctionDef) and node.name == 'flush')
    need("folder.mkdir(exist_ok=False)" in ast.get_source_segment(meter_source, flush)
         and "(folder / 'INDEX.json').write_text" in ast.get_source_segment(meter_source, flush), 'wire flush creates folder and index only on flush')
    worker_ast = ast.parse(worker_source)
    flush_calls = [node for node in ast.walk(worker_ast) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name) and node.func.value.id == 'meter' and node.func.attr == 'flush']
    need(len(flush_calls) == 1 and worker_source.index('meter.flush(workspace)') > worker_source.index("closed=dict(pid=os.getpid()")
         and worker_source.index('meter.flush(workspace)') < worker_source.index("save(workspace/'WORKER_CLOSED.json',closed)"),
         'only meter flush after worker serving ended and before WORKER_CLOSED')
    need('index = json.loads((wire / "INDEX.json").read_bytes())' in qualification_source, 'capture reader requires terminal aggregate index')
    index = read(folder / 'owner/native/WIRE/INDEX.json')
    need([row['sequence'] for row in index] == [1, 2, 3, 4], 'postclose archive now contains initial capture final and close')
    for row in index:
        wire = folder / 'owner/native/WIRE' / str(row['sequence']).zfill(3)
        request_raw, response_raw = raw(wire / 'REQUEST.bin'), raw(wire / 'RESPONSE.bin')
        need(len(request_raw) == row['request_bytes'] and len(response_raw) == row['response_attempted_bytes'] and row['response_sendall_completed'],
             'postclose original wire row ' + str(row['sequence']))
    capture_response = read(folder / 'owner/native/WIRE/002/RESPONSE.bin')
    capture_request = read(folder / 'owner/native/WIRE/002/REQUEST.bin')
    need(capture_request['type'] == 'execute_code' and capture_response['status'] == 'success', 'actual capture executed successfully')
    saved_script = raw(folder / 'owner/native/call_2/SCRIPT.py').decode('utf8').replace('\r\n', '\n')
    saved_stdout = raw(folder / 'owner/native/call_2/stdout.txt').decode('utf8').replace('\r\n', '\n')
    saved_stderr = raw(folder / 'owner/native/call_2/stderr.txt')
    need(saved_script == capture_request['params']['code']
         and digest(saved_script.encode('utf8')) == actual_capture[0]['script_sha256'], 'per-call saved executed code binds host event and wire')
    need(saved_stdout == capture_response['result']['result'] and len(saved_stdout.encode('utf8')) == actual_capture[0]['stdout_bytes']
         and len(saved_stderr) == actual_capture[0]['stderr_bytes'] == 0, 'per-call saved text binds logical captured stdout with Windows text newlines accounted')
    stdout_write = worker_source.index("(call/'stdout.txt').write_text")
    event_update = worker_source.index('event.update(script_sha256', stdout_write)
    event_publish = worker_source.index('append(audit,event)', event_update)
    response_send = worker_source.index('connection.sendall(wire)', event_publish)
    need(stdout_write < event_update < event_publish < response_send < worker_source.index('meter.flush(workspace)'),
         'per-call output files published before completed event and response, aggregate wire only at worker end')
    lines = [line.removeprefix('HUMAN_EYE_BLENDER_MCP:') for line in capture_response['result']['result'].splitlines()
             if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
    need(len(lines) == 1, 'one postclose retained capture envelope')
    delta = json.loads(lines[0])['result']
    need(delta['schema'] == 'human-eye-scene-delta-v1' and len(delta['resources']) == 24 and len(delta['capture']['capture']['meshes']) == 24,
         'actual capture retained complete initial resource delta')

    for item in inputs.values():
        data = Path(item['path']) if Path(item['path']).is_absolute() else ROOT / item['path']
        current = data.read_bytes()
        need(len(current) == item['bytes'] and digest(current) == item['sha256'], 'final input stability ' + item['path'])
    output = {'schema': 'continuity_FIX1_original_lifecycle_audit_v1', 'status': 'pass_as_recorded_failure_audit',
              'prelaunch_guard_commit': repair['preparation_commit'], 'prelaunch_guard_live_episodes': 0,
              'actual_preparation_commit': reservation['preparation_commit'], 'actual_episodes': 1, 'actual_N_episodes': 0,
              'original_engineering_qualification_passed': False,
              'counts': {'planned_C_business': 3, 'actual_C_business': 1, 'tool_and_thin_success': 1,
                         'qualification_completed': 0, 'qualification_failed': 1, 'not_run': 2},
              'fixed_preparation_files_preserved': 1190, 'external_files_preserved': len(preparation['external_sha256']),
              'old_001_content_files_preserved': 367,
              'identity': {'owner_launcher_pid': launch['pid'], 'actual_owner_pid': owner['actor_pid'],
                           'Blender_pid': session['pid'], 'product_launcher_pid': proof['launcher_pid'], 'product_runtime_pid': proof['runtime_pid'],
                           'thin_launcher_pid': thin['pid'], 'actual_thin_pid': start['pid'], 'session_id': episode},
              'complete_wall_ns': timing['full_episode_wall_ns'], 'owned_closure_confirmed': True, 'registered_EDIT_applied': False,
              'actual_BASE': {'matched_pairs': 71, 'new_kernel_calls': 112, 'actual_capture_count': 1, 'catalog_objects': 24, 'all_pair_denominator': 276},
              'failure_stage': {'kind': 'online_reader_requires_terminal_archive', 'original_type': error['type'],
                                'original_message': error['message'], 'business_and_thin_completed_before_error': True,
                                'read_capture_before_verify_c_turn': True, 'wire_index_published_only_after_worker_serving_ended': True,
                                'per_call_outputs_published_before_response': True,
                                'postclose_wire_index_present': True, 'qualification_not_retroactively_upgraded': True},
              'unknown_worker_close_events_retained': [row for row in host_events if row.get('status') == 'unknown'],
              'checks': len(checks), 'check_labels': checks, 'input_files': len(inputs), 'inputs': sorted(inputs.values(), key=lambda item: item['path']),
              'new_Blender_product_model_API_runs': 0, 'original_mutations': 0,
              'limits': ['Only one actual C transport boundary executed, later cache and EDIT continuity remain unmeasured.',
                         'The 8000 prelaunch guard failure is separate from the e065 actual episode denominator.',
                         'Closed archives can verify completed requests offline but were unavailable to this reader during the live worker.',
                         'Source order and original exception establish the failure boundary; historical memory and arbitrary reverted transients are not replayed.',
                         'Generic close event status unknown remains alongside independently confirmed response/wait/reap/runtime-handle closure.',
                         'No actual model consumer, model memory, cross-turn provider usage or same-task benefit was measured.']}
    write(HERE / 'RESULTS.json', output)
    report = f'''# FIX1 实际工程失败的生命周期复核

2026-11-13。只读原件复核通过，共 {len(checks)} 项检查，绑定 {len(inputs)} 份输入。FIX1 原工程资格仍未通过。新增 Blender、产品、模型、API 和 Git 操作为零。

## 实际分母和关闭

纠正准备 e06597f92d1193b40e9a62b78919a3125e4e346d 后，只实际启动一次 C episode。BASE 的业务请求成功返回，真实薄客户端正常 EOF 退出，随后资格失败。原分母为计划 3、实际 1、资格完成 0、资格失败 1、未运行 2。REPEAT、EDIT 没有启动。新增 N episode 为零。

8000b52f 的第一次准备守卫在预留及实例启动之前失败，记录 ENGINEERING_STARTED=false、episodes_directory=false、新 live=0。它与 e065 的一次实际工程分母分别保留。

实际 owner、Blender、产品 launcher/runtime、session 与薄客户端逐项绑定，原始 stdio 和 owner 请求/返回一致。单业务在 30 秒内完成。完整 episode 为 {timing['full_episode_wall_ns'] / 1e9:.7f} 秒，结果关闭及最终计时发布均在原绝对 590 秒内。两个 metadata RPC、一个通知及一个业务分别保留。

BASE 已 end_turn，active_turn 为空。C 没有尝试登记 EDIT，初末几何及 worker initial/accepted/final fingerprint 相同。owner、产品和 Blender 的实际关闭及回收均确认。通用 worker close 事件的 status=unknown 与这些实际关闭证明分别记录。

## 实际结果和失效阶段

产品实际返回 complete、71 匹配、24 对象及 276 对完整覆盖，unknown/deferred 为零。私有工作量记录首次 kernel 112，测量条目从 0 到 112。此次业务恰好一次真实宿主捕获，捕获及图片保护检查完成，零新图像。上述是原件中的业务事实，原工程验收失败保留。

失败栈发生在 runner.verify_business 调用 qualification.read_capture 的 WIRE/INDEX.json 读取处，尚未进入 verify_c_turn。业务成功、thin 退出和 end_turn 都早于这次 FileNotFoundError。清理的最终快照发生在错误之后。

冻结 worker 把 WireSocket 请求/返回先留在进程内 RECORDS。wire_meter.flush 才创建 WIRE 目录和汇总 INDEX。源码中该 flush 只有一处调用，位于 worker 服务循环结束之后、WORKER_CLOSED 发布之前。因此关闭后离线归档可读，不代表同一材料在在线资格时已经发布。

关闭后的实际 INDEX 现有四条原帧，依次为初始 QA、业务捕获、最终 QA 和 close，长度及 sendall 回执逐项一致。业务捕获的资源 delta 保留 24 resources/24 meshes。原 FileNotFoundError 及原 failed 不因关闭后文件存在而升级。

单次运行材料的时机不同。worker 每次先写 call_N/SCRIPT.py、stdout.txt、stderr.txt，再发布完成事件，随后发送成功响应。实际 call_2 的代码与 script_sha256、stdout 与实际响应及字节计数一致，保存文本的 Windows 换行转换单独处理。因此既有单次输出可以供在线资格绑定；后续修复应在此材料与原宿主事件、资源历史之间接线，并继续把关闭后 WIRE 汇总作为完整归档。本复核没有替换读入口或重新执行业务。

## 字节保护与边界

1,190 份准备文件、{len(preparation['external_sha256'])} 份外部输入以及旧 001 的 367 份内容文件保持原字节。原 actor、stdio、worker 和产品组件的固定摘要继续成立。

本复核建立记录、来源和清理的一致性，未补跑 C2/C3，也未运行任何模型/provider。C 的三轮缓存复用、EDIT 失效以及真实模型续接仍未测。完整原异常、证据时间顺序和逐文件摘要见 RESULTS.json。
'''
    (HERE / 'REPORT.md').write_text(report, encoding='utf8', newline='\n')
    print(json.dumps({'status': output['status'], 'checks': len(checks), 'inputs': len(inputs), 'actual_C': 1,
                      'not_run': 2, 'original_pass': False, 'closed': True, 'new_live': 0}))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        number = len(list(HERE.glob('ANALYZER_FAILURE_*.json'))) + 1
        write(HERE / ('ANALYZER_FAILURE_' + str(number).zfill(2) + '.json'),
              {'scope': 'offline lifecycle checker failure', 'traceback': traceback.format_exc(), 'originals_changed': False})
        raise
