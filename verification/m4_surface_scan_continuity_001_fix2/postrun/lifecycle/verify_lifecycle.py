"""Read-only audit of the single FIX2 C collection/close/qualification episode."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import struct
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
PREVIOUS = ROOT / 'verification/m4_surface_scan_continuity_001'
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
TURNS = ('BASE', 'REPEAT', 'EDIT')
checks = []
inputs = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
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
    return {key: status[key] for key in ('episode_id', 'owner_pid', 'native_pid', 'native_host', 'native_port',
            'native_workspace', 'product_launcher_pid', 'product_runtime_proof', 'session_id', 'worker_deadline_ns')}


def main():
    preparation = read(BATCH / 'PREPARATION.json')
    need(len(preparation['files']) == 58 and len(preparation['external_sha256']) == 369, '59 frozen preparation files and 369 external inputs')
    for item in preparation['files']:
        data = raw(BATCH / item['path'])
        need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'fixed preparation ' + item['path'])
    for path, expected in preparation['external_sha256'].items():
        need(digest(raw(path)) == expected, 'fixed external ' + path)
    for folder, expected in ((PREVIOUS, '8f62559516f98202fb3f6d74ab9e9aee775dd917471edfda9f08add39d96b470'),
                             (FIX1, 'ab550815c35a530bff121e409caf9a67316f970b76dac6189457fdeff89755c1')):
        manifest_bytes = raw(folder / 'DELIVERY_MANIFEST.json')
        need(digest(manifest_bytes) == expected, 'fixed prior failure manifest ' + folder.name)
        manifest = json.loads(manifest_bytes)
        by_path = {item['path']: item for item in manifest['files']}
        for name in ('episodes/C/RESULTS.json', 'episodes/C/FINAL_TIMING.json', 'episodes/C/TURN_BASE.json'):
            data = raw(folder / name)
            item = by_path[name]
            need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'prior failed evidence ' + folder.name + '/' + name)
        old_result = read(folder / 'episodes/C/RESULTS.json')
        need(old_result['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}
             and read(folder / 'episodes/C/FINAL_TIMING.json')['accepted_success'] is False, 'old C failed and two not_run retained ' + folder.name)
    need(read(PREVIOUS / 'episodes/N/FINAL_TIMING.json')['accepted_success'] is True, 'fixed previous N engineering evidence retained')
    reservation = read(BATCH / 'ENGINEERING_STARTED.json')
    outer = read(BATCH / 'ENGINEERING_RESULT.json')
    need(reservation['groups'] == ['C'] and reservation['maximum_episodes'] == 1
         and reservation['preparation_commit'] == '1511af696b564a0b261b70d5f0562325daa1f2a7', 'one FIX2 C from committed preparation')
    need(outer['planned_episodes'] == outer['started_episodes'] == 1 and outer['N_episodes'] == 0 and outer['passed'] is True, 'one actual successful C no new N')
    need(outer['model_calls'] == outer['API_calls'] == reservation['model_calls'] == 0, 'zero model/API runs')
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
    native_ready = read(folder / 'owner/native/READY.json')
    continuity = read(folder / 'owner/CONTINUITY.json')
    close = read(folder / 'owner/CLOSE.json')
    worker = read(folder / 'owner/native/WORKER_CLOSED.json')
    finish = read(folder / 'OWNER_FINISH.json')
    proof = read(folder / 'owner/PRODUCT_RUNTIME_PROOF.json')
    tools = read(folder / 'owner/TOOLS.json')
    status = result['initial_status']
    initial = read(folder / 'owner/INITIAL.json')
    edited = read(folder / 'owner/EDIT.json')
    pre_edit = read(folder / 'owner/PRE_EDIT.json')
    final = read(folder / 'owner/FINAL.json')
    episode = 'continuity-fix2-engineering-C-001'
    deadline = timing['original_deadline_ns']
    need(result['episode_id'] == config['episode_id'] == continuity['episode_id'] == status['episode_id'] == episode, 'one actual episode identity')
    need(deadline - timing['started_ns'] == 590_000_000_000, 'absolute original 590 second budget')
    need(deadline == config['worker_deadline_ns'] == launch['deadline_ns'] == session['deadline_ns']
         == native_ready['deadline_ns'] == endpoint['chain_deadline_ns'] == worker['original_deadline_ns'], 'same absolute deadline on every owned component')
    need(timing['accepted_success'] is True and timing['within_590s'] is True and not timing['publication_errors'], 'final authoritative qualification accepted')
    need(timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns'] == 5_094_122_500, 'complete original wall interval')
    need(timing['business_receipts_closed_ns'] <= publication['started_ns'] <= publication['closed_ns'] < deadline, 'result close before timing publication within budget')
    need(owner['actor_parent_pid'] == launch['pid'] and owner['actor_pid'] == endpoint['actor_pid'] == status['owner_pid'] == close['actor_pid'], 'actual owner launcher and child identities')
    need(session['pid'] == native_ready['pid'] == status['native_pid'] == worker['pid'], 'one owned Blender PID')
    need(session['host'] == status['native_host'] and session['port'] == status['native_port']
         and Path(session['workspace']) == Path(status['native_workspace']), 'same native endpoint and namespace workspace')
    need(proof == status['product_runtime_proof'] and proof['confirmed'] is True and proof['before_consumer_business'] is True, 'runtime owned proof before all business')
    need(proof['launcher_pid'] == status['product_launcher_pid'] == close['plugin_close']['launcher_pid'], 'same product launcher')
    need(owner['runtime_identity']['source_sha256'] == preparation['product_source_sha256']
         == '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6', 'actual loaded fixed C source generation')
    need(config['source_sha256'] == preparation['product_source_sha256'], 'launch product source pin')
    need(result['execution_counts'] == {'planned': 3, 'attempted': 3, 'successful_returns': 3, 'succeeded': 3, 'failed': 0, 'not_run': 0}, 'three actually executed and successful returns')
    need(result['qualification_counts'] == {'planned': 3, 'passed': 3, 'failed': 0, 'unverified': 0}, 'three qualified after close')
    need(not result['errors'] and not result['qualification_errors'] and not result['publication_errors'] and result['passed_before_publication'], 'all error and publication guards')
    need([row['turn'] for row in result['business']] == list(TURNS) and tools['calls'] == tools['attempts'] == close['tool_attempts'] == 3, 'three business attempts fixed order')
    need([row['turn_id'] for row in continuity['completed_turns']] == list(TURNS) and continuity['active_turn'] is None, 'all owner turn barriers completed')

    controls = sorted((folder / 'owner').glob('control_*'))
    operations, control_rows = [], []
    for number, control in enumerate(controls, 1):
        request = read(control / 'REQUEST.json')
        receipt = read(control / 'RECEIPT.json')
        response = read(control / 'RESPONSE.json')
        admin = read(folder / ('ADMIN_' + str(number).zfill(2) + '.json'))
        need(admin['request'] == request and admin['response']['result'] == response, 'admin source response binding ' + str(number))
        need(receipt == continuity['events'][number - 1] and receipt['error'] is None, 'admin actual receipt ' + str(number))
        need(request['params']['episode_id'] == episode, 'admin fixed episode ' + str(number))
        operations.append(receipt['operation'])
        control_rows.append(receipt)
    need(operations == ['status', 'status', 'begin_turn', 'end_turn', 'status', 'begin_turn', 'end_turn',
                        'qa_advance', 'status', 'begin_turn', 'end_turn', 'status'], 'exact collection and single EDIT control path')
    need(continuity['edit_attempted'] and continuity['edit_verified'] and worker['qa_patch_applied'], 'registered EDIT attempted and verified once')
    need(pre_edit == initial and result['registered_pose']['snapshot'] == edited == final, 'online pre-edit and saved registered readback')
    expected = copy.deepcopy(initial)
    target = next(row for row in expected['objects'] if row['name'] == 'Obj_008')
    target['matrix_world'][2][3] = struct.unpack('f', struct.pack('f', target['matrix_world'][2][3] - .00075))[0]
    need(expected == edited and initial != edited, 'only registered Obj008 float32 Z matrix change')
    need(close['geometry_unchanged'] is False and close['expected_terminal_geometry_matches'] and close['registered_pose_applied'], 'real changed geometry accepted by registered terminal contract')
    need(worker['accepted_geometry_fingerprint'] == worker['final_geometry_fingerprint']
         and worker['initial_geometry_fingerprint'] != worker['final_geometry_fingerprint'] and not worker['poisoned'], 'worker accepted edited fingerprint')
    need(finish['close'] == close and finish['confirmed'] and finish['exit_code'] == 0 and close['confirmed'], 'one outer owned finish confirmed')
    need(close['native_close']['process_reaped'] and close['native_close']['exit_code'] == 0 and close['native_close']['response']['status'] == 'closed', 'native close response and actual reap')
    need(close['plugin_close']['confirmed'] and close['plugin_close']['exit_code'] == 0 and close['plugin_close']['reader_stopped'], 'product launcher and stdout reader stopped')
    need(close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exited']
         and close['product_runtime_exit']['exit_code'] == 0 and close['product_runtime_exit']['handle_closed'], 'actual retained runtime handle exit')
    need(close['worker_closed'] == worker and close['asset_unchanged'] and result['asset_unchanged']
         and close['accepted_worker_geometry_matches'] and close['zero_new_images_budget_met'], 'terminal asset geometry image protections')
    need(close['ended_ns'] <= result['qualification_started_ns'] <= result['qualification_ended_ns']
         <= timing['business_receipts_closed_ns'] < deadline, 'sole confirmed close before all qualification and final result close')
    need(len(list((folder / 'owner/native').glob('CLOSE_*.json'))) == 1, 'one native close request receipt')

    host_events = [json.loads(line) for line in raw(folder / 'owner/native/WORKER_EVENTS.jsonl').splitlines()]
    audit = [json.loads(line) for line in raw(folder / 'owner/audit.jsonl').splitlines()]
    parsed = []
    thin_actual_pids = []
    for number, label in enumerate(TURNS, 1):
        row = result['business'][number - 1]
        turn = read(folder / ('TURN_' + label + '.json'))
        thin = read(folder / label / 'THIN_TURN.json')
        boundary = continuity['completed_turns'][number - 1]
        need(row == turn and row['thin'] == thin, label + ' row and original thin record equality')
        need(row['execution_state'] == 'succeeded' and row['successful_return'] and row['qualification_state'] == 'passed'
             and not row['errors'] and not row['qualification_errors'], label + ' execution and qualification separately passed')
        need(identity(row['status_before']) == identity(row['status_after']) == identity(status), label + ' same owner backend product session')
        need(not row['status_before']['owner_close_called'] and not row['status_after']['owner_close_called'], label + ' thin did not finish owner')
        need(boundary['deadline_ns'] == thin['deadline_ns'] == deadline and boundary['business_attempts'] == 1, label + ' fixed deadline and one tool')
        need(boundary['started_ns'] <= row['started_ns'] <= thin['started_ns'] < thin['process_exit_ns']
             <= thin['ended_ns'] <= row['ended_ns'] <= boundary['ended_ns'], label + ' original window fixed before end_turn')
        need(row['ended_ns'] < close['ended_ns'] <= row['qualification_started_ns'] <= row['qualification_ended_ns'], label + ' qualification separate from original business interval')
        need(thin['confirmed'] and thin['exit_code'] == 0 and thin['process_reaped'], label + ' actual thin normal completion')
        need(read(folder / label / 'ENDPOINT.json') == endpoint, label + ' original endpoint attached')
        tx, rx = raw(folder / label / 'TX.bin'), raw(folder / label / 'RX.bin')
        requests = [json.loads(line) for line in tx.splitlines()]
        responses = [json.loads(line) for line in rx.splitlines()]
        need(requests == thin['requests'] and responses == thin['responses'], label + ' complete actual stdio transcript')
        need([r['method'] for r in requests] == ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'], label + ' metadata and business denominator')
        need([r['id'] for r in responses] == thin['request_ids'] == [r['id'] for r in requests if 'id' in r], label + ' exact request reply IDs')
        instances = thin['bridge_cleanup']['instances']
        need(len(instances) == 1 and thin['bridge_cleanup']['confirmed'] is True, label + ' one actual thin instance')
        bridge = Path(instances[0]['directory'])
        began, exited = read(bridge / 'STARTED.json'), read(bridge / 'EXIT.json')
        thin_actual_pids.append(began['pid'])
        need(began == instances[0]['started'] and exited == instances[0]['exit'], label + ' START EXIT source binding')
        need(all(began[key] == exited[key] for key in ('pid', 'kind', 'started_ns', 'instance_nonce')),
             label + ' actual process instance identity')
        need(exited['normal_exit'] is True and exited['backend_close_requested'] is False and exited['requests'] == 4,
             label + ' EOF closes client only')
        need(exited['complete_tx_bytes'] == len(tx) and exited['complete_rx_bytes'] == len(rx), label + ' raw stdio byte counts')
        for ordinal, request in enumerate(requests, 1):
            call = bridge / str(ordinal).zfill(3)
            need(read(call / 'TX.bin') == request, label + ' attached TX ' + str(ordinal))
            if 'id' in request:
                need(read(call / 'RX.bin') == next(r for r in responses if r['id'] == request['id']), label + ' attached RX ' + str(ordinal))
        original = folder / 'owner' / ('tool_' + str(number).zfill(2))
        attempt = read(original / 'ATTEMPT.json')
        need(read(original / 'REQUEST.json') == row['request'] == requests[-1], label + ' owner and thin request exact')
        need(read(original / 'RESPONSE.json') == row['response'] == responses[-1], label + ' owner and thin response exact')
        need(not attempt['is_error'] and attempt['exception'] is None and 0 < attempt['elapsed_ns'] < 30_000_000_000,
             label + ' actual tool complete within 30 seconds')
        need(row['request']['params']['arguments'] == {'session_id': episode, 'include_image': False,
             'query': {'mode': 'surface_scan', 'threshold_m': .002}}, label + ' ordinary default query')
        body = json.loads(row['response']['result']['content'][0]['text'])
        verification = row['verification']
        expected_matches, expected_kernels = ((71, 112), (71, 0), (72, 10))[number - 1]
        need(body == row['body'] and body['status'] == 'complete' and body['coverage']['objects'] == 24
             and body['coverage']['total_pairs'] == 276 and body['coverage']['unknown'] == body['coverage']['deferred'] == 0,
             label + ' complete current raw coverage')
        need(len(body['matches']) == expected_matches == verification['matches'] and body['delivery']['complete'], label + ' current returned match count')
        observations = [e for e in audit if e.get('event') == 'observe' and e.get('trace_id') == body['trace_id']]
        traces = [e['trace'] for e in audit if e.get('event') == 'request_trace' and e.get('trace_id') == body['trace_id']]
        need(len(observations) == len(traces) == 1, label + ' unique actual audit observation and trace')
        work = observations[0]['task_work']
        need(work['kernel_calls'] == expected_kernels == verification['new_kernel_calls'], label + ' actual new kernel count')
        need(observations[0]['pid'] == proof['runtime_pid'] == verification['runtime_pid'], label + ' same actual product runtime')
        need(verification['passed'] and verification['verified_pair_dispositions'] == 276
             and verification['facts']['all_pair_partitions_verified'] == 276, label + ' full partition qualification report')
        need(verification['source_report']['rich_source_metadata_verified'] is False
             and verification['source_report']['schema'] == 'owner_complete_geometry_projection', label + ' source metadata boundary retained')
        source_state = 'EDIT' if label == 'EDIT' else 'BASE'
        source_geometry = edited if source_state == 'EDIT' else initial
        projection = {'unit_scale_m': source_geometry['unit_scale_m'], 'objects': [
            {key: obj[key] for key in sorted(('name', 'vertices_local', 'faces', 'matrix_world'))}
            for obj in source_geometry['objects']]}
        projection_bytes = json.dumps(projection, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf8')
        need(verification['truth_state'] == source_state and verification['source_report']['observed_geometry_sha256'] == digest(projection_bytes),
             label + ' actual qualification used state-specific saved source')
        truth_path = ROOT / 'verification/m4_surface_scan_001/qualification' / (source_state + '_TRUTH.json')
        need(verification['truth_sha256'] == digest(raw(truth_path)), label + ' qualified fixed state truth identity')
        need(sum(span['name'] == 'host.capture' for span in traces[0]['spans']) == 1
             and traces[0]['annotations']['mcp_native_image_block_count'] == 0, label + ' one capture span and zero delivered images')
        events = [e for e in host_events if type(e.get('started_ns')) is int and row['started_ns'] <= e['started_ns'] <= row['ended_ns']]
        need(len(events) == 1, label + ' exactly one raw host event in original window')
        event = events[0]
        need(type(event['elapsed_ns']) is int and event['elapsed_ns'] > 0
             and event['started_ns'] + event['elapsed_ns'] <= row['ended_ns'], label + ' full raw event fits original window')
        need(event['status'] == 'completed' and event['terminal_geometry_and_file_checks_passed']
             and event['script_error'] is None and event['changed_or_new_PNG_files'] == []
             and event['render_events_before'] == event['render_events_after'], label + ' current host terminal image and geometry protection')
        need(verification['host_sequence'] == verification['capture_report']['sequence'] == event['sequence'], label + ' qualified actual capture sequence')
        need(all(origin['sequence'] <= event['sequence'] for origin in verification['capture_report']['resource_origins'])
             and all(part['sequence'] <= event['sequence'] for part in verification['capture_report']['wire_sources']), label + ' no future capture resource proof')
        parsed.append({'turn': label, 'matches': expected_matches, 'new_kernels': expected_kernels,
                       'host_sequence': event['sequence'], 'business_window_ns': [row['started_ns'], row['ended_ns']],
                       'qualification_window_ns': [row['qualification_started_ns'], row['qualification_ended_ns']],
                       'thin_wall_ns': thin['wall_ns'], 'actual_thin_pid': began['pid'],
                       'body_binding': body['binding'], 'measurement_cache_before': work['measurement_cache_before'],
                       'measurement_cache_after': work['measurement_cache_after']})
    need(len(set(thin_actual_pids)) == 3, 'three distinct actual thin process instances')
    need(parsed[0]['body_binding'] == parsed[1]['body_binding'] != parsed[2]['body_binding'], 'BASE REPEAT equal binding EDIT invalidation')
    need(control_rows[6]['ended_ns'] < control_rows[7]['started_ns'] < control_rows[7]['ended_ns']
         < result['business'][2]['started_ns'], 'single registered EDIT between completed REPEAT and EDIT business')
    need(result['sequence_qualification_state'] == 'passed' and result['sequence_verification']['passed']
         and result['sequence_verification']['matches'] == [71, 71, 72]
         and result['sequence_verification']['new_kernel_calls'] == [112, 0, 10], 'postclose full sequence accepted')
    need(max(row['qualification_ended_ns'] for row in result['business']) <= result['sequence_qualification_started_ns']
         <= result['sequence_qualification_ended_ns'] <= result['qualification_ended_ns'], 'sequence follows all three qualification windows')

    index = read(folder / 'owner/native/WIRE/INDEX.json')
    need([row['sequence'] for row in index] == list(range(1, 10)), 'complete nine original host frames')
    for item in index:
        wire = folder / 'owner/native/WIRE' / str(item['sequence']).zfill(3)
        request_raw, response_raw = raw(wire / 'REQUEST.bin'), raw(wire / 'RESPONSE.bin')
        need(len(request_raw) == item['request_bytes'] and len(response_raw) == item['response_attempted_bytes']
             and item['response_sendall_completed'] is True
             and item['request_response_attempted_bytes'] == len(request_raw) + len(response_raw), 'terminal raw wire complete ' + str(item['sequence']))
    wire_requests = [read(folder / ('owner/native/WIRE/%03d/REQUEST.bin' % item['sequence'])) for item in index]
    need(sum(req.get('type') == 'qa_advance' for req in wire_requests) == 1
         and sum(req.get('type') == 'close' for req in wire_requests) == 1
         and wire_requests[-1]['type'] == 'close'
         and read(folder / 'owner/native/WIRE/009/RESPONSE.bin')['status'] == 'closed', 'one actual pose command and one final close frame')
    need(result['terminal_wire_verification'] == {'passed': True, 'frames': 9, 'complete_sendall': True, 'closed_frame_verified': True}, 'full wire report corresponds original frames')
    runner = ast.parse(raw(BATCH / 'engineering/run_candidate.py').decode('utf8'))
    run = next(node for node in runner.body if isinstance(node, ast.FunctionDef) and node.name == 'run_episode')
    finish_calls = [node for node in ast.walk(run) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'driver.finish']
    need(len(finish_calls) == 1, 'sole finish call site matches actual close evidence')
    for item in list(inputs.values()):
        path = Path(item['path']) if Path(item['path']).is_absolute() else ROOT / item['path']
        data = path.read_bytes()
        need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'final input stability ' + item['path'])
    output = {'schema': 'continuity_FIX2_success_lifecycle_audit_v1', 'status': 'pass_as_recorded_success_audit',
              'preparation_commit': reservation['preparation_commit'], 'actual_C_episodes': 1, 'actual_N_episodes': 0,
              'new_model_provider_API_calls': 0, 'frozen_preparation_files_preserved': 59, 'external_files_preserved': 369,
              'execution_counts': result['execution_counts'], 'qualification_counts': result['qualification_counts'],
              'actual_original_success': True, 'owned_closure_confirmed': True, 'registered_EDIT_applied_once': True,
              'complete_wall_ns': timing['full_episode_wall_ns'], 'stages_ns': result['stages_ns'], 'turns': parsed,
              'all_three_original_windows_preserved': True, 'all_qualification_after_confirmed_close': True,
              'unknown_worker_close_events_retained': [e for e in host_events if e.get('status') == 'unknown'],
              'old_two_C_failures_and_not_run_preserved': True,
              'checks': len(checks), 'check_labels': checks, 'input_files': len(inputs), 'inputs': sorted(inputs.values(), key=lambda item: item['path']),
              'original_mutations': 0,
              'limits': ['Three engineering requests establish this fixed lifecycle and cache qualification, with no actual model consumer.',
                         'The verifier binds original raw output and qualification reports; it does not re-solve all triangle distances.',
                         'Missing rich source metadata and generic close unknown remain within their recorded scope.',
                         'Provider model memory, resume usage semantics, cash and same-task model benefit remain unmeasured.',
                         'Buffered result close and historical runtime/terminal protection are recorded, fsync-level result durability and arbitrary reverted transient effects are not attested.']}
    write(HERE / 'RESULTS.json', output)
    lines = ['# FIX2 实际三轮与关闭后验收复核', '',
             f"2026-11-13。只读原件复核通过，{len(checks)}项检查、{len(inputs)}份输入。新增live、Blender、模型、API和Git操作均为零。", '',
             '固定准备1511af696b564a0b261b70d5f0562325daa1f2a7。实际仅一个全新C、三次业务，N新增零次。执行3成功/0失败/0未运行，资格3通过/0失败/0未核验。', '',
             '| 轮次 | 实际匹配 | 新kernel | 捕获序号 | thin实际PID |', '| --- | --- | --- | --- | --- |']
    for item in parsed:
        lines.append(f"| {item['turn']} | {item['matches']} | {item['new_kernels']} | {item['host_sequence']} | {item['actual_thin_pid']} |")
    lines += ['', '三个独立thin进程都经原stdio_attach和完整initialize/通知/list/业务链，正常EOF退出且backend_close_requested=false。owner、Blender、产品runtime、session和endpoint跨三轮保持，原始TX/RX与owner请求返回逐项一致。', '',
              '原业务started_ns/ended_ns固定，宿主事件按started_ns+elapsed_ns完整落入各自窗口。三轮先完成收集，唯一登记EDIT位于REPEAT之后，原actor前态及精确姿态回读通过。BASE/REPEAT用INITIAL，EDIT用登记回读；初末几何仅含Obj_008登记Z变化，原资产文件保持。', '',
              '唯一finish、产品runtime退出、Blender回收和worker终态确认后，才进行三次事实验收与sequence。九帧WIRE含唯一qa_advance和末尾唯一close，尺寸、sendall及JSON完整。较早轮次资源只引用当时及之前的捕获，BASE/REPEAT绑定相同、EDIT失效。', '',
              f"完整episode为{timing['full_episode_wall_ns']/1e9:.7f}秒，含后台启动、三轮收集、登记编辑/回读、关闭、后验核验及RESULTS写关，均在原590秒内。各实际工具均在30秒内，计时发布单列。后验阶段约{result['stages_ns']['qualification']/1e6:.4f}毫秒。", '',
              '59份冻结准备及369份外部输入保持原字节，覆盖固定actor、consumer、资格、worker和产品证据。原001及FIX1两个C失败和各两轮未运行继续保留。此前原N三轮仅作为固定工程证据复用。', '',
              '这份复核核对真实来源、请求回执、资源/资格报告对应、时序、分母和关闭，没有重新求解全部几何真值，也没有执行模型消费。实际模型续接、记忆保持、usage范围、费用和连续任务收益仍待正式阶段。rich来源缺失字段及通用close事件unknown与独立关闭确认分别保留。', '',
              'RESULTS.json保留逐项标签、输入摘要、三个原窗口、后验窗口及原始成本。verify_lifecycle.py只读原件并仅在此postrun/lifecycle目录写派生输出。', '']
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf8', newline='\n')
    print(json.dumps({'status': output['status'], 'checks': len(checks), 'inputs': len(inputs), 'C_business': 3,
                      'qualification_passed': 3, 'complete_seconds': timing['full_episode_wall_ns'] / 1e9, 'new_live': 0}))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        number = len(list(HERE.glob('ANALYZER_FAILURE_*.json'))) + 1
        write(HERE / ('ANALYZER_FAILURE_' + str(number).zfill(2) + '.json'),
              {'scope': 'offline FIX2 lifecycle checker failure', 'traceback': traceback.format_exc(), 'originals_changed': False})
        raise
