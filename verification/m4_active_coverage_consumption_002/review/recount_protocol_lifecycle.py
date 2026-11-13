"""Read saved local/formal records, byte archives and source identities only."""

from collections import Counter
import hashlib
import json
from pathlib import Path
from uuid import UUID
import zipfile


BASE = Path(__file__).resolve().parents[1]
OLD = BASE.parent / 'm4_active_coverage_consumption_001'
INPUTS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUTS[str(path)] = digest(data)
    return data


def read(path):
    return json.loads(raw(path))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def verify_zip(path, wanted_sha, wanted_bytes, members, source_directory):
    path = Path(path)
    data = raw(path)
    assert digest(data) == wanted_sha and len(data) == wanted_bytes
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and set(names) == set(members)
        for name, wanted in members.items():
            value = archive.read(name)
            assert digest(value) == wanted
            assert value == raw(source_directory / name)
    return {'path': str(path), 'sha256': wanted_sha, 'members_verified': len(members)}


def inspect_route(row, scope):
    folder = Path(row['folder'])
    consumer_directory = Path(row['consumer_output'])
    owner = Path(row['owner_output'])
    consumer = read(consumer_directory / 'CONSUMER.json')
    timing = read(folder / 'FINAL_TIMING.json')
    endpoint = read(folder / 'ENDPOINT.json')
    identity = read(owner / 'IDENTITY.json')
    owner_tools = read(owner / 'TOOLS.json')['tools']
    calls = consumer['tool_calls']
    contracts = consumer['archive']['result_contracts']
    assert len(owner_tools) == len(calls) == len(contracts)
    assert [value['attempt'] for value in owner_tools] == list(range(1, len(owner_tools) + 1))
    stdout = raw(consumer_directory / 'stdout.raw.bin')
    assert len(stdout) == consumer['stdout_raw_bytes'] and digest(stdout) == consumer['stdout_raw_sha256']
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    completed = [event['item'] for event in events if event.get('type') == 'item.completed'
                 and event.get('item', {}).get('type') == 'mcp_tool_call']
    assert canonical(completed) == canonical([value['item'] for value in calls])
    thread_events = [event['thread_id'] for event in events if event.get('type') == 'thread.started']
    assert thread_events == [consumer['thread_id']] and str(UUID(thread_events[0])) == thread_events[0]
    usage_events = [event.get('usage') for event in events if event.get('type') == 'turn.completed']
    assert canonical(usage_events) == canonical(consumer['raw_usage_events'])
    final_events = [event['item']['text'] for event in events if event.get('type') == 'item.completed'
                    and event.get('item', {}).get('type') == 'agent_message']
    assert final_events and final_events[-1] == consumer['final']
    assert raw(consumer_directory / 'PUBLIC_FINAL.txt') == final_events[-1].encode('utf8')
    bindings = []
    for number, (logged, public, contract) in enumerate(zip(owner_tools, calls, contracts), 1):
        original = owner / ('tool_' + str(number).zfill(2))
        request = read(original / 'REQUEST.json')
        response = read(original / 'RESPONSE.json')
        receipt = read(original / 'RECEIPT.json')
        item = public['item']
        result = response['result']
        actual = item['result']
        assert request['params']['name'] == item['tool'] == contract['tool']
        assert canonical(request['params']['arguments']) == canonical(item['arguments'])
        assert type(request['id']) is type(response['id']) and request['id'] == response['id']
        assert response['jsonrpc'] == '2.0' and 'error' not in response
        assert set(result) == {'content', 'isError'} and type(result['isError']) is bool
        assert item['type'] == 'mcp_tool_call' and item['server'] == 'arm_engine'
        assert 'error' in item and item['error'] is None
        expected = 'tool_error' if result['isError'] else 'success'
        assert item['status'] == ('failed' if result['isError'] else 'completed')
        if set(actual) == {'content', 'structured_content'}:
            assert actual['structured_content'] is None
        else:
            assert set(actual) == {'content', 'isError'}
            assert type(actual['isError']) is bool and actual['isError'] is result['isError']
        assert canonical(result['content']) == canonical(actual['content'])
        assert contract['matched'] is True and contract['classification'] == expected
        assert receipt['is_error'] is result['isError'] and receipt['response_serialization_error'] is None
        for name in ('REQUEST.json', 'RESPONSE.json', 'RECEIPT.json'):
            assert raw(original / name) == raw(consumer_directory / 'owner_turn' / original.name / name)
        bindings.append({'attempt': number, 'tool': item['tool'], 'classification': expected,
                         'owner_isError': result['isError'], 'CLI_status': item['status'],
                         'complete_content_equal': True, 'request_and_RPC_ID_bound': True,
                         'content_sha256': digest(canonical(result['content']).encode('utf8'))})
    binding = consumer['runtime_binding']
    exit_record = consumer['runtime_exit']
    cleanup = consumer['process_cleanup']
    assert cleanup['pid'] == consumer['consumer_pid'] and cleanup['confirmed'] is True
    assert cleanup['exit_code'] == consumer['exit_code'] == 0
    assert endpoint['actor_pid'] == identity['actor_pid'] == row['owner_pid'] == row['owner_process_cleanup']['pid']
    assert row['owner_process_cleanup']['confirmed'] is True and row['owner_process_cleanup']['exit_code'] == 0
    assert row['owner_close_confirmed'] is True
    assert binding['confirmed'] is True and binding['after_stdio_STARTED'] is True and 'before_stdin' not in binding
    assert binding['runtime_pid'] == binding['stdio_STARTED']['pid']
    assert binding['launcher_pid'] == consumer['consumer_pid']
    assert binding['actual_executable_sha256'] == binding['expected_executable_sha256'] == '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
    assert binding['parent_chain'][-1]['pid'] == consumer['consumer_pid'] and binding['parent_edges'] <= 4
    assert binding['runtime_created_filetime'] >= binding['launcher_created_filetime']
    assert exit_record['confirmed'] is True and exit_record['exited'] is True and exit_record['handle_closed'] is True
    assert consumer['process_exit_ns'] <= exit_record['started_ns'] <= exit_record['closed_ns'] < consumer['deadline_ns']
    assert consumer['deadline_ns'] == row['deadline_ns'] == endpoint['chain_deadline_ns']
    assert row['deadline_ns'] - row['started_ns'] == 450_000_000_000
    assert consumer['safe_to_continue'] is True and consumer['valid_completion'] is True
    assert row['outer_valid_completion'] is True and timing['accepted_success'] is True
    assert row['input_readback_unchanged'] is True
    assert not row['errors'] and not consumer['errors'] and not row['common_image_faults'] and not row['stop_remaining_reasons']
    assert not row['owner_metrics']['common']['runtime_faults']
    assert not consumer['archive']['business_binding_errors']
    inner = consumer['archive']
    outer = row['originals']
    archives = [
        verify_zip(inner['archive'], inner['archive_sha256'], inner['archive_bytes'],
                   inner['source_files_sha256'], consumer_directory),
        verify_zip(outer['path'], outer['sha256'], outer['bytes'], outer['members_sha256'], folder),
    ]
    return {
        'scope': scope, 'slot': row.get('slot'), 'group': row['group'],
        'CLI_pid': consumer['consumer_pid'], 'actor_pid': row['owner_pid'],
        'actual_thin_pid': binding['runtime_pid'], 'CLI_created_filetime': binding['launcher_created_filetime'],
        'thin_created_filetime': binding['runtime_created_filetime'], 'thread_id': consumer['thread_id'],
        'CLI_exit_code': consumer['exit_code'], 'actor_exit_code': row['owner_process_cleanup']['exit_code'],
        'actual_thin_exit_code': exit_record['exit_code'], 'actual_thin_exit_and_close_confirmed': True,
        'thin_EXIT_receipt_confirmed': consumer['bridge_cleanup']['confirmed'],
        'consumer_and_outer_accepted': True, 'raw_stdout_verified': True,
        'raw_usage_events_preserved': True, 'CLI_error_events': consumer['errors'],
        'CLI_retry_observations': consumer['provider_retry_observations'],
        'tool_bindings': bindings, 'archives': archives,
        'source_readback_unchanged': True, 'requested_model': consumer['model'],
        'requested_effort': consumer['requested_effort'], 'resolved_effort': consumer['resolved_effort'],
        'provider_internal_requests': consumer['provider_requests'], 'fees': consumer['fees'],
    }


def main():
    frozen_path = BASE / 'FROZEN.json'
    frozen = read(frozen_path)
    assert len(frozen['files_sha256']) == 188
    for path, wanted in frozen['files_sha256'].items():
        assert digest(raw(path)) == wanted
    plan = read(BASE / 'PLAN.json')
    launch = read(BASE / 'r/LAUNCH_RESULT.json')
    marker = read(BASE / 'FORMAL_STARTED.json')
    before = read(BASE / 'r/POINTERS_BEFORE.json')
    after = read(BASE / 'r/POINTERS_AFTER.json')
    assert before == after and all(before['checks'].values()) and len(before['checks']) == 13
    assert launch['pointer_chain_unchanged'] is True and launch['source_unchanged'] is True
    assert launch['freeze_sha256'] == marker['freeze_sha256'] == digest(raw(frozen_path))
    assert launch['local_qualification'] == marker['local_qualification']
    local_rows = []
    for reference in launch['local_qualification']:
        path = Path(reference['path'])
        local = read(path)
        assert digest(raw(path)) == reference['sha256'] and reference['attempts'] == local['attempt'] == 1
        assert local['passed'] is True and local['new_Pro_sessions'] == local['new_renders'] == local['new_image_constructions'] == 0
        result = inspect_route(local['route'], 'local_fake_CLI')
        assert result['thin_EXIT_receipt_confirmed'] is True and result['actual_thin_exit_code'] == 0
        fixture = read(Path(local['route']['consumer_output']) / 'LOCAL_FIXTURE.json')
        assert fixture['normal_EOF_requested'] is True and fixture['normal_exit_observed'] is True
        assert fixture['thin_cleanup']['confirmed'] is True and fixture['thin_cleanup']['kill_requested'] is False
        assert [value['classification'] for value in result['tool_bindings']] == ['tool_error', 'success']
        result['normal_EOF_and_no_thin_kill_confirmed'] = True
        local_rows.append(result)
    aggregate = read(BASE / 'r/RUN_RESULT.json')
    assert [row['slot'] for row in aggregate['records']] == [row['slot'] for row in plan['sequence']]
    assert aggregate['actual_routes'] == aggregate['actual_CLI_processes'] == 6
    assert all(row['execution_state'] == 'completed' for row in aggregate['records'])
    formal = [inspect_route(row, 'formal_Pro') for row in aggregate['records']]
    assert len({row['thread_id'] for row in formal}) == 6
    assert aggregate['observed_fresh_threads'] == [row['thread_id'] for row in formal]
    assert all(row['thin_EXIT_receipt_confirmed'] is None and row['actual_thin_exit_code'] == 1 for row in formal)
    old_run = read(OLD / 'r/RUN_RESULT.json')
    old_counts = Counter(row['execution_state'] for row in old_run['records'])
    assert old_counts == Counter({'completed': 4, 'failed': 2}) and old_run['actual_CLI_processes'] == 6
    correction = read(BASE / 'PREPARATION_NOTE_CORRECTION.json')
    assert correction['actual_new_batch_CLI_processes'] == 6
    assert correction['source_or_results_changed_after_formal'] is False
    old_frozen = read(OLD / 'FROZEN.json')
    for path, wanted in old_frozen['runtime_sources'].items():
        assert digest(raw(path)) == wanted
    assert len(old_frozen['runtime_sources']) == 176
    candidate = BASE.parent / 'm4_consumer_error_contract_001'
    candidate_freeze = read(candidate / 'FROZEN.json')
    fixture_manifest_path = candidate / 'FIXTURE_MANIFEST.json'
    assert digest(raw(fixture_manifest_path)) == candidate_freeze['files_sha256'][str(fixture_manifest_path)]
    old_manifest = read(fixture_manifest_path)
    for path, wanted in old_manifest['original_sources_sha256'].items():
        assert digest(raw(path)) == wanted
    formal_tool_counts = Counter(value['classification'] for row in formal for value in row['tool_bindings'])
    raw(Path(__file__).resolve())
    report = {
        'schema': 'active-coverage-consumption-002-protocol-lifecycle-review-v1', 'passed': True,
        'frozen_sha256': digest(raw(frozen_path)), 'frozen_sources_checked': 188,
        'old_runtime_sources_checked': 176, 'source_unchanged': True,
        'old_original_records_hashes_checked': len(old_manifest['original_sources_sha256']),
        'pointer_checks': before['checks'], 'formal_pointer_snapshots_identical': True,
        'local_rows': local_rows, 'formal_rows': formal,
        'local_counts': {'fake_CLI_sessions': 2, 'tool_error': 2, 'success': 2, 'Pro_sessions': 0, 'render_attempts': 0},
        'formal_counts': {'Pro_CLI_sessions': 6, 'fresh_threads': 6, 'completed': 6, 'failed': 0, 'not_run': 0,
                          'tool_classifications': {'success': formal_tool_counts['success'],
                                                   'tool_error': formal_tool_counts['tool_error']},
                          'actual_thin_exits_confirmed': 6, 'thin_EXIT_unknown': 6,
                          'CLI_errors_observed': sum(len(row['CLI_error_events']) for row in formal),
                          'CLI_retry_observations': sum(len(row['CLI_retry_observations']) for row in formal)},
        'old_formal_counts_unchanged': {'completed': 4, 'failed': 2, 'not_run': 0},
        'preparation_note_correction': correction,
        'interpretation': {
            'local_exit_semantics': 'Both local fake consumers request ordinary EOF and observe thin exit 0 with EXIT receipts. Each actual local actor ValueError remains tool_error, followed by successful 42 recovery.',
            'formal_exit_semantics': 'Each formal CLI and actor exits 0. Each STARTED-bound thin process has retained-handle exit status 1 and a closed handle. EXIT-file EOF remains unknown. Exit cause is unobserved. The unchanged completion gate permits this proven terminal state.',
            'formal_business_errors': 'Formal source receipts contain no tool_error. Error-to-recovery evidence belongs to the two local pipelines and the separately preserved older protocol replay.',
            'count_correction': 'The original run_batch already provides actual_CLI_processes. Old and new RUN_RESULT each record six. Removing the redundant launcher copy did not remove the actual ledger field.',
            'provider_observability': 'CLI errors/retries are directly counted from preserved events and observations. Provider-internal request count, fees and resolved effort remain unobserved.',
            'cost_comparison': 'Independent cost accounting is outside this protocol/lifecycle review.',
        },
        'review_execution': {'new_model_local_matrix_or_renderer_runs': 0,
                             'matcher_archive_or_tool_code_called': False,
                             'scope': 'Read existing source hashes, JSON, original stdout and ZIP bytes only.'},
        'inputs_sha256': INPUTS,
    }
    path = BASE / 'review/PROTOCOL_LIFECYCLE_REVIEW.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    count = report['formal_counts']['tool_classifications']
    markdown = f'''# 第二批协议与实际进程终态复核

新批六槽均正式 completed，六个 fresh CLI thread 各有真实 actor 与 stdio 来源、创建时间及持有句柄退出证据。188 项新冻结来源与旧 176 项来源 SHA 保持一致，前后 13 项指针检查一致。

正式工具回执分类为 {count.get('success', 0)} 个 success、{count.get('tool_error', 0)} 个 tool_error。请求名、完整参数、RPC ID、正文全部字段与真实 CLI completed 事件逐项一致。stdout 原字节及双层 ZIP 的哈希、成员和复制原件均通过核对。六槽 CLI error 与 retry observation 均为零。

两路本地各有一次真实 actor ValueError，经 fake CLI 保留 failed/null/原正文投影后匹配为 tool_error，再执行 42 恢复。两路均普通 EOF，实际 thin exit 为 0，EXIT 回执明确且持有进程清理没有请求 kill。正式六槽本轮没有工具业务错误，错误恢复证据按上述本地范围报告。

正式 CLI 与 actor 各自 exit 为 0。六个实际 stdio runtime 的持有句柄均证实 exit 为 1 并已关闭，EXIT 文件的 EOF 状态保持 unknown。退出原因未测，原完成门依据已证终态接受这些槽位。

原第一批保持 4 完成、2 失败，新批独立为 6 完成。准备说明已更正，旧 run_batch 本来包含 actual_CLI_processes，两个批次的 RUN_RESULT 均实记 6。launcher 删除的是冗余复制字段。

本次复核只读原件，新增模型、本地会话、矩阵、工具代码和渲染调用均为零。provider 内部请求、费用及 resolved effort 保持未测。时间与用量比较由独立成本账本处理。

逐项生命周期、绑定和原件 SHA 见 [JSON 复核]({path.as_posix()})。计数说明原件见 [准备说明更正]({(BASE / 'PREPARATION_NOTE_CORRECTION.json').as_posix()})。
'''
    (BASE / 'review/PROTOCOL_LIFECYCLE_REVIEW.md').write_text(markdown, encoding='utf8')
    print(json.dumps({'passed': True, 'frozen_sources': 188, 'local_sessions': 2,
                      'formal_sessions': 6, 'formal_tool_classes': count,
                      'formal_thin_actual_exit_confirmed': 6, 'formal_EOF_unknown': 6,
                      'new_execution_calls': 0}))


if __name__ == '__main__':
    main()
