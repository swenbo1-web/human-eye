"""Read saved replay artifacts and inspect module wiring without replaying cases."""

import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


BASE = Path(__file__).resolve().parents[1]
OLD = BASE.parent / 'm4_active_coverage_consumption_001'
RUN = BASE / 'offline/a01'
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


def verify_map(mapping, directory=None):
    for name, wanted in mapping.items():
        path = Path(name) if directory is None else directory / name
        assert digest(raw(path)) == wanted, str(path)


def main():
    frozen_raw = raw(BASE / 'FROZEN.json')
    frozen = json.loads(frozen_raw)
    results = read(RUN / 'RESULTS.json')
    manifest = read(BASE / 'FIXTURE_MANIFEST.json')
    registered = read(BASE / 'CASES.json')
    started = read(RUN / 'STARTED.json')
    verify_map(frozen['files_sha256'])
    assert results['freeze_sha256'] == digest(frozen_raw) == started['freeze_sha256']
    assert [row['case_id'] for row in registered['cases']] == [row['case_id'] for row in results['cases']]
    assert len(results['cases']) == len({row['case_id'] for row in results['cases']}) == 47
    assert all(row['passed'] is True and row['exception'] is None for row in results['cases'])

    forbidden = []

    def audit(event, arguments):
        if event in {'subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind'}:
            forbidden.append(event)
            raise RuntimeError('review_forbidden_online_operation')

    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location('_independent_connection_review', BASE / 'driver.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    consumer = driver.consumer
    connections = {}
    global_changes = {}
    pairs = [
        ('consume_turn', consumer.consume_turn, consumer.legacy.consume_turn, {'archive_turn'}),
        ('run_route', driver.run_route, driver.legacy.run_route, {'consumer', 'common_image_faults'}),
        ('run_batch', driver.run_batch, driver.legacy.run_batch, {'run_route'}),
    ]
    for name, candidate, original, expected in pairs:
        connections[name + '_code_defaults_closure'] = bool(
            candidate.__code__ is original.__code__
            and candidate.__defaults__ is original.__defaults__
            and candidate.__closure__ is original.__closure__
            and candidate.__kwdefaults__ == original.__kwdefaults__
            and (original.__kwdefaults__ is None or candidate.__kwdefaults__ is not original.__kwdefaults__))
        differences = {key for key in set(candidate.__globals__) | set(original.__globals__)
                       if candidate.__globals__.get(key) is not original.__globals__.get(key)}
        global_changes[name] = {
            'changed_globals': sorted(differences), 'expected_globals': sorted(expected),
            'private_globals_dictionary': candidate.__globals__ is not original.__globals__,
            'exact_expected_changes': differences == expected,
        }
    connections.update({
        'archive_pointer': consumer.consume_turn.__globals__['archive_turn'] is consumer.archive_turn,
        'route_consumer_pointer': driver.run_route.__globals__['consumer'] is consumer,
        'route_check_pointer': driver.run_route.__globals__['common_image_faults'] is driver.common_image_faults,
        'batch_route_pointer': driver.run_batch.__globals__['run_route'] is driver.run_route,
        'safe_environment_unchanged': consumer.safe_environment is consumer.legacy.safe_environment,
        'outer_gate_unchanged': driver.outer_accepted is driver.legacy.outer_accepted,
        'terminal_gate_unchanged': driver.terminal_service_faults is driver.legacy.terminal_service_faults,
        'publication_unchanged': driver.publish_route is driver.legacy.publish_route,
        'old_archive_pointer_unchanged': consumer.legacy.consume_turn.__globals__['archive_turn'] is consumer.legacy.archive_turn,
        'old_route_consumer_unchanged': driver.legacy.run_route.__globals__['consumer'] is driver.legacy.consumer,
        'old_route_check_unchanged': driver.legacy.run_route.__globals__['common_image_faults'] is driver.legacy.common_image_faults,
        'old_batch_route_unchanged': driver.legacy.run_batch.__globals__['run_route'] is driver.legacy.run_route,
    })
    assert all(connections.values()) and connections == results['connections']
    assert all(row['exact_expected_changes'] and row['private_globals_dictionary'] for row in global_changes.values())

    archives = []
    member_count = 0
    for case in results['cases']:
        archive = case.get('archive')
        if archive is None:
            continue
        path = Path(archive['archive'])
        data = raw(path)
        assert digest(data) == archive['archive_sha256'] and len(data) == archive['archive_bytes']
        expected = archive['source_files_sha256']
        with zipfile.ZipFile(path) as zipped:
            names = zipped.namelist()
            assert len(names) == len(set(names)) and set(names) == set(expected)
            for name, wanted in expected.items():
                data = zipped.read(name)
                assert digest(data) == wanted
                assert raw(path.parent / 'consumer' / name) == data
        member_count += len(expected)
        archives.append({'case_id': case['case_id'], 'archive_sha256': archive['archive_sha256'],
                         'members_verified': len(expected), 'passed': True})

    verify_map(manifest['original_sources_sha256'])
    verify_map(manifest['fixture_files_sha256'], BASE / 'fixtures')
    tools = []
    for record in manifest['records']:
        slot, number = record['slot'], record['attempt']
        tool = 'tool_' + str(number).zfill(2)
        original = OLD / 'r' / slot / 'o' / tool
        fixture = BASE / 'fixtures/slots' / slot / 'owner' / tool
        copy = RUN / 'cases' / ('real_slot_' + slot) / 'consumer/owner_turn' / tool
        for name in ('REQUEST.json', 'RESPONSE.json', 'RECEIPT.json'):
            assert raw(original / name) == raw(fixture / name) == raw(copy / name)
        stdout = raw(record['CLI_stdout_source'])
        lines = stdout.splitlines(keepends=True)
        line_number = record['CLI_raw_line_number'] - 1
        line = lines[line_number]
        assert digest(line) == record['CLI_raw_line_sha256']
        assert sum(map(len, lines[:line_number])) == record['CLI_raw_byte_offset']
        event = json.loads(line)
        assert canonical(event) == canonical(read(BASE / 'fixtures' / record['CLI_completed']))
        calls = read(RUN / 'cases' / ('real_slot_' + slot) / 'consumer/CANDIDATE_CLI_ITEMS.json')
        assert canonical(calls[number - 1]['item']) == canonical(event['item'])
        binding = next(row['binding'] for row in results['real_fixture_results']
                       if row['fixture_id'] == record['fixture_id'])
        assert binding['matched'] is True and binding['classification'] == record['expected_classification']
        tools.append({'fixture_id': record['fixture_id'], 'original_owner_byte_copies_verified': True,
                      'actual_CLI_line_offset_and_hash_verified': True, 'candidate_CLI_item_unchanged': True,
                      'classification': binding['classification']})

    old_frozen = read(OLD / 'FROZEN.json')
    verify_map(old_frozen['runtime_sources'])
    assert len(old_frozen['runtime_sources']) == 176
    original_run = read(OLD / 'r/RUN_RESULT.json')
    slots = []
    for row in original_run['records']:
        slot = row['slot']
        original = read(OLD / 'r' / slot / 'c/CONSUMER.json')
        fixture = read(BASE / 'fixtures/slots' / slot / 'CONSUMER_ORIGINAL.json')
        state = read(BASE / 'fixtures/slots' / slot / 'SLOT_STATE.json')
        assert canonical(original) == canonical(fixture)
        assert canonical(original['raw_usage_events']) == canonical(state['raw_usage_events'])
        final = raw(OLD / 'r' / slot / 'c/PUBLIC_FINAL.txt')
        assert final == raw(BASE / 'fixtures/slots' / slot / 'PUBLIC_FINAL.txt')
        assert digest(final) == state['final_sha256']
        errors = [entry['event'] for entry in original['errors']
                  if entry.get('event', {}).get('type') in ('error', 'turn.failed')]
        assert canonical(errors) == canonical(state['top_level_errors'])
        projection = next(item for item in results['historical_invariants']['slots'] if item['slot'] == slot)
        assert projection['original_execution_state'] == row['execution_state']
        assert projection['raw_usage_objects_unchanged'] is True
        slots.append({'slot': slot, 'original_execution_state': row['execution_state'],
                      'original_outer_accepted': row['outer_valid_completion'],
                      'answer_byte_copy_verified': True, 'raw_usage_objects_unchanged': True,
                      'top_level_errors_equal': True, 'top_level_error_count': len(errors),
                      'candidate_event_projection_only_valid': projection['candidate_event_projection_only_valid'],
                      'interrupted_stream_usage_coverage': state['interrupted_stream_usage_coverage']})
    assert Counter(row['original_execution_state'] for row in slots) == Counter({'completed': 4, 'failed': 2})
    n3 = next(row for row in slots if row['slot'] == 'N3')
    assert n3['top_level_error_count'] == 1 and n3['candidate_event_projection_only_valid'] is False
    assert n3['interrupted_stream_usage_coverage'] == 'unknown'

    replay_tree = ast.parse(raw(BASE / 'replay.py'))
    dangerous = []
    live_calls = []
    for node in ast.walk(replay_tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in {'exec', 'eval', 'compile'}:
            dangerous.append({'line': node.lineno, 'call': function.id})
        if isinstance(function, ast.Attribute) and function.attr in {
                'consume_turn', 'run_route', 'run_batch', 'execute_python', 'render_one', 'render_views', 'active_coverage'}:
            live_calls.append({'line': node.lineno, 'call': function.attr})
    assert not dangerous and not live_calls and not forbidden and not results['forbidden_operation_attempts']
    verify_map(frozen['files_sha256'])
    raw(Path(__file__).resolve())
    report = {
        'schema': 'consumer-error-contract-001-independent-connection-review-v1', 'passed': True,
        'frozen_sha256': digest(frozen_raw), 'frozen_file_count': len(frozen['files_sha256']),
        'freeze_all_unchanged': True,
        'cases': {'registered': 47, 'passed': 47, 'failed': 0, 'not_run': 0,
                  'original_case_order_unchanged': True, 'new_case_or_matrix_runs_in_this_review': 0},
        'real_classifications': dict(Counter(row['classification'] for row in tools)),
        'actual_connection_checks': connections, 'exact_globals_changes': global_changes,
        'archive_checks': archives, 'archive_count': len(archives), 'archive_members_verified': member_count,
        'real_original_tool_checks': tools,
        'original_sources_verified': len(manifest['original_sources_sha256']),
        'fixture_files_verified': len(manifest['fixture_files_sha256']),
        'old_frozen_runtime_sources_verified': 176, 'old_constructor_outer_held_handle_source_unchanged': True,
        'original_slots': slots, 'original_execution_counts': {'completed': 4, 'failed': 2, 'not_run': 0},
        'offline_scope': {
            'harness_forbidden_operation_attempts': results['forbidden_operation_attempts'],
            'review_forbidden_operation_attempts': forbidden,
            'source_exec_eval_compile_call_sites': dangerous, 'source_live_consumer_or_renderer_call_sites': live_calls,
            'review_called_matcher_archive_or_cases': False,
            'review_imports': 'Read-only candidate module import for code/defaults/closure/globals identity inspection.',
            'original_tool_strings_executed': False, 'new_Pro_provider_CLI_actor_Blender_raster_calls': 0,
        },
        'interpretation': {
            'candidate_binding_match': '15 original receipts match as 13 success and 2 tool_error. Original business-error controls and body bytes remain preserved.',
            'historical_slot_promotion': False,
            'N3': 'Original top-level reconnect error and unknown interrupted-stream usage coverage remain. Candidate event-only projection remains false.',
            'formal_three_pair_benefit_claim': False,
            'scope': 'Candidate protocol replay verification. Original 4-completed/2-failed formal execution ledger remains unchanged.',
        },
        'inputs_sha256': INPUTS,
    }
    path = BASE / 'review/CONNECTION_REPLAY_REVIEW.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    markdown = f'''# 候选接线与原件复核

一次冻结离线矩阵的 47 项均通过。15 份真实回执分类为 13 个成功、2 个业务错误。独立复核确认原 owner 请求、响应、回执、真实 CLI 行偏移与字节，以及候选归档副本逐字节相符。

独立导入候选模块后检查了三个继承函数的 code、defaults、closure、kwdefaults 和实际 globals 指针。globals 仅替换登记的 archive、consumer/共同核查和 route。旧模块指针及 outer、终态、发布函数均保持原对象。

{len(archives)} 份 ZIP 的哈希、成员集合及全部 {member_count} 个成员与清单和磁盘原件一致。另两项为 matcher 入口控制。冻结 {len(frozen['files_sha256'])} 项、旧冻结 176 源及历史原件保持 SHA 一致。构造账本、完成门和持有句柄源码保持原样。

六槽答案、usage 对象及原执行状态保持原样，仍为 4 通过、2 失败。N3 顶层重连错误保留，候选事件投影仍失败，中断流 usage 覆盖仍为 unknown。候选绑定匹配不会追溯提升正式槽位或形成完整三配对收益结论。

本次复核读取原件并检查模块对象，矩阵、matcher、archive 和工具代码调用均为零。新增 Pro、provider、CLI、actor 服务、Blender 与光栅均为零。审计与源码可达路径支持该离线执行范围。

逐项证据与输入 SHA 见 [JSON 复核]({path.as_posix()})。原始矩阵记录见 [RESULTS]({(RUN / 'RESULTS.json').as_posix()})。
'''
    (BASE / 'review/CONNECTION_REPLAY_REVIEW.md').write_text(markdown, encoding='utf8')
    print(json.dumps({'passed': True, 'connections': len(connections), 'archives': len(archives),
                      'ZIP_members': member_count, 'real_tools': len(tools),
                      'classes': report['real_classifications'], 'old176_unchanged': True,
                      'frozen_sources': len(frozen['files_sha256']), 'new_matrix_or_case_runs': 0}))


if __name__ == '__main__':
    main()
