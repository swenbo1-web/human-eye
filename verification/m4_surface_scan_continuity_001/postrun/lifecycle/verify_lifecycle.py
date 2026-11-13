"""Read-only audit of the two original continuity engineering episodes.

No producer module import, process launch, RPC or historical evidence mutation.
Only deterministic derived files in this postrun/lifecycle directory are written.
"""

import copy
import hashlib
import json
from pathlib import Path
import struct
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
checks = []
inputs = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    name = path.relative_to(ROOT).as_posix()
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')


def identity(status):
    return {key: status[key] for key in ('episode_id', 'owner_pid', 'native_pid', 'native_host', 'native_port',
            'native_workspace', 'product_launcher_pid', 'product_runtime_proof', 'session_id', 'worker_deadline_ns')}


def main():
    preparation = read(BATCH / 'PREPARATION.json')
    for item in preparation['files']:
        data = raw(BATCH / item['path'])
        need(digest(data) == item['sha256'], 'frozen preparation source ' + item['path'])
    for group in ('N', 'C'):
        for path in sorted((BATCH / 'episodes' / group).rglob('*')):
            if path.is_file():
                raw(path)
    outer = read(BATCH / 'ENGINEERING_RESULT.json')
    reservation = read(BATCH / 'ENGINEERING_STARTED.json')
    need(outer['started_episodes'] == outer['planned_episodes'] == 2 and not outer['passed'], 'two actual episodes overall retained failure')
    need(reservation['maximum_episodes'] == 2 and reservation['groups'] == ['N', 'C'], 'single reservation fixed N then C')
    need(outer['model_calls'] == outer['API_calls'] == 0, 'no live model/API')
    results = []
    actual_thin_pids = set()
    previous_final_close = None
    for group, turns in (('N', ('BASE', 'REPEAT', 'EDIT')), ('C', ('BASE',))):
        prefix = group + ' '
        folder = BATCH / 'episodes' / group
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
        original_status = result['initial_status']
        episode_id = 'continuity-engineering-' + group + '-001'
        deadline = timing['original_deadline_ns']
        need(result['episode_id'] == config['episode_id'] == continuity['episode_id'] == episode_id, prefix + 'episode binding')
        need(deadline - timing['started_ns'] == 590_000_000_000, prefix + 'original 590 second window')
        need(deadline == launch['deadline_ns'] == config['worker_deadline_ns'] == session['deadline_ns'] == ready['deadline_ns']
             == endpoint['chain_deadline_ns'] == worker['original_deadline_ns'], prefix + 'deadline identical across owner worker endpoint')
        need(timing['business_receipts_closed_ns'] - timing['started_ns'] == timing['full_episode_wall_ns'], prefix + 'full interval integer identity')
        need(result['started_ns'] == timing['started_ns'] and result['deadline_ns'] == deadline, prefix + 'result and timing binding')
        need(timing['within_590s'] and timing['business_receipts_closed_ns'] < deadline, prefix + 'complete lifecycle within deadline')
        need(publication['started_ns'] >= timing['business_receipts_closed_ns'] and publication['closed_ns'] < deadline,
             prefix + 'final timing publication separate and within deadline')
        need(previous_final_close is None or timing['started_ns'] > previous_final_close, prefix + 'serial episodes')
        previous_final_close = publication['closed_ns']
        need(owner['actor_parent_pid'] == launch['pid'] and owner['actor_pid'] == endpoint['actor_pid'] == original_status['owner_pid']
             == close['actor_pid'], prefix + 'Python launcher and actual owner separately bound')
        need(session['pid'] == ready['pid'] == original_status['native_pid'] == worker['pid'], prefix + 'same actual Blender worker')
        need(session['host'] == original_status['native_host'] and session['port'] == original_status['native_port'], prefix + 'same native endpoint')
        need(Path(session['workspace']) == Path(original_status['native_workspace']), prefix + 'same native workspace')
        need(len(result['business']) == tools['calls'] == tools['attempts'] == close['tool_attempts'] == len(turns), prefix + 'actual business count')
        need([row['turn'] for row in result['business']] == list(turns), prefix + 'actual turn prefix retained')
        need([row['turn_id'] for row in continuity['completed_turns']] == list(turns) and continuity['active_turn'] is None,
             prefix + 'owner ended exactly actual completed transport turns')
        need(close['completed_turns'] == continuity['completed_turns'] and close['active_turn'] is None, prefix + 'close reports same phase')
        thin_rows = []
        for index, turn in enumerate(turns, 1):
            label = prefix + turn + ' '
            turn_folder = folder / turn
            turn_record = read(folder / ('TURN_' + turn + '.json'))
            thin = read(turn_folder / 'THIN_TURN.json')
            turn_endpoint = read(turn_folder / 'ENDPOINT.json')
            boundary = continuity['completed_turns'][index - 1]
            need(thin == turn_record['thin'] and thin['confirmed'] and thin['error'] is None, label + 'actual thin receipt and embedded row')
            need(turn_endpoint == endpoint, label + 'endpoint unchanged across fresh client')
            need(thin['exit_code'] == 0 and thin['process_reaped'] and thin['model_or_API_calls'] == 0, label + 'thin launcher closed')
            need(boundary['started_ns'] <= thin['started_ns'] < thin['process_exit_ns'] <= thin['ended_ns'] <= boundary['ended_ns'] < deadline,
                 label + 'thin lifetime lies inside original active turn')
            need(boundary['deadline_ns'] == thin['deadline_ns'] == deadline, label + 'turn deadline unchanged')
            need(boundary['business_attempts'] == 1 and boundary['first_business_attempt'] == boundary['last_business_attempt'] == index,
                 label + 'one business attempt in this turn')
            need(identity(turn_record['status_before']) == identity(original_status)
                 == identity(turn_record['status_after']), label + 'owner native product and session persistent')
            need(not turn_record['status_before']['owner_close_called'] and not turn_record['status_after']['owner_close_called'],
                 label + 'client EOF did not close owner')
            request_wire = raw(turn_folder / 'TX.bin')
            requests = [json.loads(line) for line in request_wire.splitlines()]
            response_wire = raw(turn_folder / 'RX.bin')
            responses = [json.loads(line) for line in response_wire.splitlines()]
            need(requests == thin['requests'] and responses == thin['responses'], label + 'whole stdio wire binding')
            need([r['method'] for r in requests] == ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'],
                 label + 'two metadata RPC one notify one business')
            need([r['id'] for r in responses] == thin['request_ids'] == [r['id'] for r in requests if 'id' in r], label + 'response id sequence')
            instances = thin['bridge_cleanup']['instances']
            need(len(instances) == 1 and thin['bridge_cleanup']['confirmed'] is True, label + 'one confirmed real thin instance')
            bridge = Path(instances[0]['directory'])
            start = read(bridge / 'STARTED.json')
            end = read(bridge / 'EXIT.json')
            need(start == instances[0]['started'] and end == instances[0]['exit'], label + 'actual START EXIT files')
            need(all(end[key] == start[key] for key in ('pid', 'kind', 'started_ns', 'instance_nonce')),
                 label + 'START EXIT instance identity')
            need(end['normal_exit'] and not end['backend_close_requested'] and end['requests'] == 4, label + 'EOF normal no backend close')
            need(thin['started_ns'] < start['started_ns'] < end['ended_ns'] < thin['process_exit_ns'], label + 'real client between launcher timestamps')
            need(end['complete_tx_bytes'] == len(request_wire) and end['complete_rx_bytes'] == len(response_wire), label + 'stdio byte totals')
            need(start['pid'] not in actual_thin_pids, label + 'fresh thin PID')
            actual_thin_pids.add(start['pid'])
            for number, request in enumerate(requests, 1):
                call = bridge / str(number).zfill(3)
                need(json.loads(raw(call / 'TX.bin')) == request, label + 'per-message TX ' + str(number))
                if 'id' in request:
                    need(json.loads(raw(call / 'RX.bin')) == next(r for r in responses if r['id'] == request['id']),
                         label + 'per-message RX ' + str(number))
            business = folder / 'owner' / ('tool_' + str(index).zfill(2))
            attempt = read(business / 'ATTEMPT.json')
            need(read(business / 'REQUEST.json') == turn_record['request'] == requests[-1], label + 'owner request equals actual thin business')
            need(read(business / 'RESPONSE.json') == turn_record['response'] == responses[-1], label + 'owner response equals actual thin business')
            need(not attempt['is_error'] and attempt['exception'] is None and attempt['elapsed_ns'] < 30_000_000_000, label + 'one executed business within 30s')
            need(start['started_ns'] <= attempt['started_ns'] and attempt['started_ns'] + attempt['elapsed_ns'] <= end['ended_ns'],
                 label + 'business executes before thin EOF')
            thin_rows.append({'turn': turn, 'thin_launcher_pid': thin['pid'], 'actual_thin_pid': start['pid'],
                              'backend_close_requested': False, 'thin_EXIT_confirmed': True,
                              'business_elapsed_ns': attempt['elapsed_ns'], 'thin_wall_ns': thin['wall_ns']})
        controls = sorted((folder / 'owner').glob('control_*'))
        admin_files = sorted(folder.glob('ADMIN_*.json'))
        need(len(controls) == len(admin_files) == len(continuity['events']), prefix + 'administrative and owner controls count')
        operations = []
        for number, control in enumerate(controls):
            request = read(control / 'REQUEST.json')
            receipt = read(control / 'RECEIPT.json')
            response = read(control / 'RESPONSE.json')
            admin = read(admin_files[number])
            need(admin['request'] == request and admin['response']['result'] == response, prefix + 'control wire ' + str(number))
            need(receipt == continuity['events'][number] and receipt['error'] is None, prefix + 'control receipts ' + str(number))
            need(timing['started_ns'] <= admin['started_ns'] <= receipt['started_ns'] < receipt['ended_ns'] <= admin['ended_ns'] < deadline,
                 prefix + 'control deadline ' + str(number))
            operations.append(receipt['operation'])
        need(operations == (['status', 'status', 'begin_turn', 'end_turn', 'status', 'begin_turn', 'end_turn', 'qa_advance',
                            'status', 'begin_turn', 'end_turn', 'status'] if group == 'N' else
                           ['status', 'status', 'begin_turn', 'end_turn']), prefix + 'fixed begin end edit order')
        need(finish['confirmed'] and finish['exit_code'] == 0 and finish['close'] == close and close['confirmed'], prefix + 'outer finish and owner closure')
        need(close['native_close']['process_reaped'] and close['native_close']['exit_code'] == 0
             and close['native_close']['response']['status'] == 'closed', prefix + 'actual native closure independently confirmed')
        need(close['worker_closed'] == worker and worker['final_geometry_fingerprint'] == worker['accepted_geometry_fingerprint']
             and not worker['poisoned'], prefix + 'accepted worker terminal fingerprint')
        need(close['expected_terminal_geometry_matches'] and close['asset_unchanged'] and not close['errors'], prefix + 'final geometry contract and asset intact')
        need(close['ended_ns'] <= timing['business_receipts_closed_ns'] and close['original_deadline_met'], prefix + 'owned close included in full interval')
        events = [json.loads(line) for line in raw(folder / 'owner/native/WORKER_EVENTS.jsonl').splitlines()]
        advances = [r for r in events if r.get('operation') == 'qa_advance']
        unknown_worker_events = [r for r in events if r.get('status') == 'unknown']
        if group == 'N':
            need(continuity['edit_attempted'] and continuity['edit_verified'] and len(advances) == 1, 'N one registered edit')
            expected = copy.deepcopy(initial)
            target = next(r for r in expected['objects'] if r['name'] == 'Obj_008')
            target['matrix_world'][2][3] = struct.unpack('<f', struct.pack('<f', target['matrix_world'][2][3] - .00075))[0]
            need(final == expected and final != initial and not close['geometry_unchanged'] and worker['qa_patch_applied'], 'N exact registered EDIT terminal snapshot')
            native_states = [read(folder / ('TURN_' + turn + '.json'))['native_state'] for turn in turns]
            need(len({r['pid'] for r in native_states}) == len({r['namespace_id'] for r in native_states}) == 1,
                 'N actual persistent native namespace')
            need(all(r['pid'] == session['pid'] and r['marker_token'] == episode_id and r['marker_generation'] == 1 for r in native_states),
                 'N in-memory marker persists')
            identities = [{r['name']: r['session_uid'] for r in state['objects']} for state in native_states]
            need(identities[0] == identities[1] == identities[2] and len(identities[0]) == 24, 'N actual object identities persist')
            for index, state in enumerate(native_states):
                expected_state = initial if index < 2 else expected
                actual_matrices = {r['name']: r['matrix_world'] for r in state['objects']}
                expected_matrices = {r['name']: r['matrix_world'] for r in expected_state['objects']}
                need(actual_matrices == expected_matrices and state['unit_scale'] == expected_state['unit_scale_m'],
                     'N current pose visible in marker call ' + turns[index])
            need(result['execution_counts'] == {'planned': 3, 'attempted': 3, 'completed': 3, 'failed': 0, 'not_run': 0}
                 and timing['accepted_success'], 'N original three passed status')
        else:
            need(not continuity['edit_attempted'] and not continuity['edit_verified'] and not advances, 'C no EDIT attempted')
            need(final == initial and close['geometry_unchanged'] and not worker['qa_patch_applied'], 'C untouched BASE terminal geometry')
            need(not (folder / 'REPEAT').exists() and not (folder / 'EDIT').exists(), 'C two later clients never launched')
            need(result['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}
                 and not timing['accepted_success'] and len(result['errors']) == 1, 'C original validation failure and two not-run retained')
            need(result['errors'][0]['type'] == 'AssertionError' and 'bind_snapshot' in result['errors'][0]['traceback'], 'C qualification failure preserved')
            proof = read(folder / 'owner/PRODUCT_RUNTIME_PROOF.json')
            plugin_start = read(folder / 'owner/plugin/START.json')
            need(proof == original_status['product_runtime_proof'] and proof['confirmed'] and proof['before_consumer_business'], 'C runtime launch proof')
            need(proof['launcher_pid'] == original_status['product_launcher_pid'] == plugin_start['launcher_pid'], 'C product launcher binding')
            need(close['plugin_close']['confirmed'] and close['plugin_close']['exit_code'] == 0
                 and close['plugin_close']['launcher_pid'] == proof['launcher_pid'], 'C product launcher closed')
            need(close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['exited']
                 and close['product_runtime_exit']['exit_code'] == 0 and close['product_runtime_exit']['handle_closed'], 'C actual product runtime exited')
            need(original_status['session_id'] == episode_id and read(folder / 'TURN_BASE.json')['request']['params']['arguments']['session_id'] == episode_id,
                 'C configured session and only actual call bind')
        results.append({'group': group, 'actual_business_calls': len(turns), 'actual_turns': list(turns),
                        'original_episode_accepted_success': timing['accepted_success'],
                        'classification': 'passed' if group == 'N' else 'validation_failed',
                        'later_turns_not_run': 0 if group == 'N' else 2,
                        'full_episode_wall_ns': timing['full_episode_wall_ns'],
                        'owner_launcher_pid': launch['pid'], 'actual_owner_pid': owner['actor_pid'], 'actual_native_pid': session['pid'],
                        'product_launcher_pid': original_status['product_launcher_pid'],
                        'actual_product_runtime_pid': None if group == 'N' else proof['runtime_pid'],
                        'thin_clients': thin_rows, 'owned_closure_confirmed': True,
                        'registered_edit_applied': group == 'N', 'worker_unknown_status_events_retained': unknown_worker_events})
    need(len(actual_thin_pids) == 4, 'exactly four real thin clients')
    need(results[0]['actual_native_pid'] != results[1]['actual_native_pid'], 'two isolated Blender processes')
    for item in inputs.values():
        data = (ROOT / item['path']).read_bytes()
        need(len(data) == item['bytes'] and digest(data) == item['sha256'], 'final stable input ' + item['path'])
    output = {'schema': 'continuity-original-lifecycle-postrun-v1', 'status': 'pass_as_original_lifecycle_audit',
              'original_engineering_qualification_passed': False, 'original_preparation_commit': reservation['preparation_commit'],
              'root_plan_sha256': preparation['root_plan_sha256'], 'episodes': results,
              'planned_business': 6, 'executed_business': 4, 'executed_N': 3, 'executed_C': 1,
              'qualification_passed_business': 3, 'validation_failed_business': 1, 'not_run_business': 2,
              'new_Blender_product_model_API_runs': 0, 'original_mutations': 0,
              'checks': len(checks), 'check_labels': checks, 'inputs': sorted(inputs.values(), key=lambda r: r['path']),
              'limitations': ['C has only one actual transport turn, so three-turn product/session/cache continuity remains unmeasured.',
                              'The two unrun C clients have no execution receipt and remain not_run.',
                              'No actual model CLI or inference API was launched, so model thread/context/usage continuity remains unmeasured.',
                              'Past process records and terminal fingerprints bind observed identity/geometry, without attesting arbitrary reverted transient effects.',
                              'Generic worker close events retain status unknown alongside independent actual close/process-reap receipts.',
                              'Outer timing publications use buffered writes and close, fsync-level durability is unmeasured.']}
    write(HERE / 'RESULTS.json', output)
    lines = ['# 连续工程原件生命周期复核', '',
             '2026-11-13。离线原件复核通过。原工程资格整体仍为未通过。新增 Blender、产品、模型和 API 运行均为零。', '',
             f"本复核共 {len(checks)} 项检查，绑定 {len(inputs)} 份输入。原始 episode 和冻结准备文件保持原件。", '',
             '| 组 | 实际业务 | 实际薄客户端 | 资格主分类 | 后续未运行 | 完整秒 | 关闭 |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for item in results:
        lines.append(f"| {item['group']} | {item['actual_business_calls']} | {len(item['thin_clients'])} | {item['classification']} | {item['later_turns_not_run']} | {item['full_episode_wall_ns']/1e9:.7f} | confirmed |")
    lines += ['', 'N 的三个独立薄客户端均正常 EOF 退出，四个真实客户端 EXIT 都声明 backend_close_requested=false。逐次完整 stdio、逐消息附件和 owner 业务回执一致。N 三轮 owner、Blender PID、工作 namespace、内存标记及对象身份持续，编辑 barrier 后可读到登记姿态。', '',
              'C BASE 的实际业务响应成功，薄客户端正常退出，owner 已结束 BASE。随后的资格检查因快照字段合同不一致抛出 AssertionError，原主分类继续保留 validation_failed。REPEAT、EDIT 没有启动，未将未运行视为通过。', '',
              'C 关闭时未尝试 EDIT，初末快照及 worker initial/accepted/final fingerprint 相同。产品 launcher、真实 runtime 和 Blender 都有独立退出及回收确认。两组均在原绝对 590 秒内完成原结果文件关闭和终态计时发布。', '',
              '每轮包含两个 metadata RPC、一个 initialized 通知和一个业务请求。N 完成三轮，C 仅完成一轮传输边界。本次不存在完整 C 连续缓存资格，也没有模型续接或模型 usage 的实测。', '',
              'worker 通用关闭事件的 status=unknown 保留，同时单列真实关闭响应、worker closed 文件、launcher wait/reap 以及适用的 runtime retained-handle 退出证明。原件证明范围限已记录的身份和终态保护。', '',
              '复核脚本只读输入，仅在本 postrun/lifecycle 目录写派生结果。完整逐项断言、输入字节和 SHA256 见 RESULTS.json。', '']
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf8', newline='\n')
    print(json.dumps({'checks': len(checks), 'input_files': len(inputs), 'executed': 4, 'N': 3, 'C': 1,
                      'original_qualification_passed': False, 'status': output['status']}))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        index = len(list(HERE.glob('ANALYZER_FAILURE_*.json'))) + 1
        write(HERE / ('ANALYZER_FAILURE_' + str(index).zfill(2) + '.json'),
              {'scope': 'offline lifecycle analyzer failure', 'traceback': traceback.format_exc(), 'originals_changed': False})
        raise
