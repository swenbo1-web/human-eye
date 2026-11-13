"""Account for the sealed failed batch from its existing archived originals."""

import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_continuous_consumption_001'
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
SEAL_SHA = '7f90243826c1a113d0365282517899902cc9aa2f1b163b67c43d6c644d2a51c6'
PLAN_SHA = 'ece9040ed2553687d54ba57b3d4d6acaeaf30610ec526a9353adf95d66a51ae5'
OLD_DELIVERY_SHA = '1523d40aac1ea1681c706c919e1ad9547d423c008f4c5a9b929440ee5b943579'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                    encoding='utf8', newline='\n')


def main():
    sources = {}

    def bind(path):
        path = Path(path).resolve()
        sources[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
        return path

    plan_path = bind(BATCH / 'inputs/ROOT_PLAN.md')
    seal_path = bind(BATCH / 'inputs/QUALITY_SEAL.json')
    assert sha(plan_path) == PLAN_SHA and sha(seal_path) == SEAL_SHA
    seal = read(seal_path)
    assert seal['delivery_commit'] == '11f944e71bc530822e8741384732529003efc29f'
    assert seal['summary']['confirmed_model_resumes_tested'] == 0
    assert seal['decision'].startswith('Content quality sealed; strict failures retained.')
    manifest_source = bind(OLD / 'DELIVERY_MANIFEST.json')
    assert sha(manifest_source) == OLD_DELIVERY_SHA, 'root_reviewed_old_manifest_binding'
    delivery = read(manifest_source)
    delivery_checks = []
    for entry in delivery['files']:
        path = OLD / entry['path']
        delivery_checks.append(path.is_file() and path.stat().st_size == entry['bytes']
                               and sha(path) == entry['sha256'])
    assert all(delivery_checks), 'sealed_old_delivery_changed'
    run = read(bind(OLD / 'RUN_RESULT.json'))
    assert tuple(row['cell'] for row in run['records']) == CELLS
    assert run['execution_counts'] == {'planned': 18, 'completed': 0, 'failed': 6, 'not_run': 12}
    result_rows = []
    archive_checks = []
    for outer in run['records']:
        cell = outer['cell']
        episode = OLD / 'episodes' / cell
        runtime = (ROOT / '.m4cc1' / cell).resolve()
        timing = read(bind(episode / 'FINAL_TIMING.json'))
        disk_outer = read(bind(episode / 'OUTER_RESULT.json'))
        assert timing == outer['timing'] and timing['outer_valid_completion'] is False
        assert disk_outer['coordinator']['turns'][0]['consumer']['thread_id'] == outer['coordinator']['turns'][0]['consumer']['thread_id']
        assert len(outer['coordinator']['turns']) == 1, 'unexpected_resume_or_turn'
        turn = outer['coordinator']['turns'][0]
        assert turn['turn_label'] == 'BASE' and turn['turn_index'] == 1
        assert [row['execution_state'] for row in outer['execution_rows']] == ['failed', 'not_run', 'not_run']
        manifest_path = bind(episode / 'RUNTIME_MANIFEST.json')
        manifest = read(manifest_path)
        archive_path = bind(episode / 'ORIGINALS.zip')
        assert sha(archive_path) == manifest['archive_sha256']

        def archived(path, bundle):
            path = bind(path)
            name = path.relative_to(runtime).as_posix()
            raw = path.read_bytes()
            metadata = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            assert manifest['members'][name] == metadata and bundle.read(name) == raw, name
            archive_checks.append({'cell': cell, 'member': name, **metadata})
            return raw

        with zipfile.ZipFile(archive_path) as bundle:
            folder = runtime / 'c/turns/BASE'
            consumer = json.loads(archived(folder / 'CONSUMER.json', bundle))
            turn_timing = json.loads(archived(folder / 'FINAL_TIMING.json', bundle))
            events = [json.loads(line)['event'] for line in archived(folder / 'events.jsonl', bundle).splitlines()]
            tools = json.loads(archived(runtime / 'owner/TOOLS.json', bundle))
            assert consumer['status'] == 'failed' and consumer['valid_completion'] is False
            assert consumer['expected_thread_id'] is None and 'resume' not in consumer['frozen_cli_argv']
            assert turn_timing['accepted_success'] is False
            assert turn_timing['full_turn_wall_ns'] == turn_timing['consumer_record_closed_ns'] - turn_timing['started_ns']
            assert timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns']
            actual_usage = [event.get('usage') for event in events if event.get('type') == 'turn.completed']
            assert len(actual_usage) == 1 and actual_usage == consumer['raw_usage_events'] == consumer['usage_rows']
            assert type(actual_usage[0]) is dict
            assert all(type(value) is int and value >= 0 for value in actual_usage[0].values())
            completed_tools = [event['item'] for event in events if event.get('type') == 'item.completed'
                               and event.get('item', {}).get('type') == 'mcp_tool_call']
            assert len(completed_tools) == tools['attempts'] == len(tools['tools'])
            attempts = []
            for expected_number, tool in enumerate(tools['tools'], 1):
                assert tool['attempt'] == expected_number
                attempt_path = runtime / 'owner' / ('tool_' + str(expected_number).zfill(2)) / 'ATTEMPT.json'
                attempt = json.loads(archived(attempt_path, bundle))
                assert attempt == tool
                attempts.append({key: attempt[key] for key in (
                    'attempt', 'name', 'elapsed_ns', 'response_bytes', 'produced_response_bytes', 'is_error')})
        judgment = next(item for item in seal['judgments']
                        if item['episode_id'] == outer['anonymous_episode_id'] and item['turn_index'] == 1)
        assert judgment['primary_content_classification'] == 'complete_correct'
        result_rows.append({
            'cell': cell, 'anonymous_episode_id': outer['anonymous_episode_id'],
            'execution_state': 'failed', 'sealed_primary_content': 'complete_correct',
            'actual_turns': 1, 'actual_resume_turns': 0,
            'outer_wall_ns': timing['full_episode_wall_ns'], 'outer_timing_scope': timing['scope'],
            'turn_wall_ns': turn_timing['full_turn_wall_ns'], 'turn_timing_scope': turn_timing['scope'],
            'prompt_to_final_ns': consumer['prompt_to_final_ns'],
            'tool_attempts': tools['attempts'], 'wire_tool_bytes': tools['wire_tool_bytes'],
            'tool_attempt_records': attempts, 'raw_turn_completed_usage': actual_usage,
            'usage_scope': 'unknown', 'usage_aggregation': None,
            'provider_requests': consumer['provider_requests'], 'fees': consumer['fees'],
            'thin_EXIT_status': consumer['bridge_cleanup']['receipt_status'],
            'owner_close_confirmed': outer['owner_finish']['confirmed'],
            'not_run': [{'turn': label, 'execution_state': 'not_run', 'elapsed_ns': None, 'usage': None,
                         'scope': 'Unexecuted slot, unestimated.'} for label in ('REPEAT', 'EDIT')],
        })
    assert sum(row['tool_attempts'] for row in result_rows) == 14
    ledger = {
        'schema': 'sealed_failed_continuous_batch_cost_ledger_v1',
        'source_cycle': run['cycle'], 'delivery_commit': seal['delivery_commit'],
        'quality_seal_sha256': SEAL_SHA, 'cost_unsealed_for_original_failure_accounting': True,
        'planned_turns': 18, 'actual_failed_first_turns': 6, 'not_run_turns': 12,
        'actual_resume_turns': 0, 'rows': result_rows,
        'shared_costs': {
            'preparation_total_wall_ns': None, 'offline_checks_total_wall_ns': None,
            'freeze_and_commit_total_wall_ns': None, 'quality_packaging_total_wall_ns': None,
            'independent_quality_review_total_wall_ns': None, 'complete_end_to_end_wall_ns': None,
            'actual_fees': None, 'invisible_provider_overhead': None,
            'status': 'unknown',
            'scope': 'Complete original timing receipts are unavailable for these shared costs. Unknown is not zero. Existing outer intervals include per-episode startup/cleanup/archives and are nested with turn intervals.',
        },
        'usage_scope': 'unknown', 'usage_aggregation': None,
        'accounting_limits': [
            'CLI turn.completed fields are copied unchanged. There is no resumed turn to establish turn-versus-session scope.',
            'Cached/reasoning fields are listed as reported. They are not added again to input/output.',
            'Outer and turn intervals overlap. They must not be summed as independent costs.',
            'No continuous benefit, group winner, adoption or fee conclusion is made.',
            'No new provider, Blender, product, model, API or Git operation occurred.',
        ],
        'source_integrity': {'old_delivery_manifest_entries_checked': len(delivery_checks),
                             'old_delivery_files_including_manifest_bound': len(delivery_checks) + 1,
                             'root_reviewed_old_delivery_manifest_sha256': OLD_DELIVERY_SHA, 'all_unchanged': True,
                             'archive_member_checks': archive_checks, 'sources': sources},
    }
    save(HERE / 'LEDGER.json', ledger)
    lines = [
        '# 已封质量的连续消费001失败成本账本', '',
        '质量 seal 已授权整理这次失败消耗。六份首轮内容均 complete_correct，原执行状态保持六次 failed、十二轮 not_run。以下逐集列原始观测，不据此判定连续收益。', '',
        '| 集 | Outer 秒 | 首轮秒 | Prompt 至 final 秒 | 工具尝试 | CLI input_tokens | cached_input_tokens | output_tokens | reasoning_output_tokens |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for row in result_rows:
        usage = row['raw_turn_completed_usage'][0]
        values = [row['cell'], *(f'{row[key] / 10**9:.6f}' for key in (
            'outer_wall_ns', 'turn_wall_ns', 'prompt_to_final_ns')), str(row['tool_attempts']),
            *(str(usage.get(key, 'unknown')) for key in (
                'input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens'))]
        lines.append('| ' + ' | '.join(values) + ' |')
    lines.extend([
        '', '## 计量范围', '',
        'Outer 使用原 FINAL_TIMING，覆盖输入检查、owner 启动、实际首轮、sole finish、关闭后验证、原件 ZIP 及 OUTER_RESULT 写入关闭。首轮使用 consumer FINAL_TIMING，覆盖输入检查、模型进程、工具、cleanup、归档及 CONSUMER 写入关闭。Prompt 至 final 为原 consumer 记录的子区间。各区间有包含关系，不能相加。timing receipt 发布范围沿原合同单列。', '',
        '十四次工具尝试的名称、耗时、响应字节及原始 usage 完整保存在 LEDGER.json，逐项通过短目录原件、outer ZIP 成员和 manifest 的字节绑定。各集原 usage 同 turn.completed 事件逐值一致，cache_write_input_tokens 等全部原字段也保留。', '',
        '没有实际 resume，usage 的逐轮或 session 累计语义仍 unknown，aggregation 为 null。cached 与 reasoning 子字段未再次加总。provider 请求计数、费用及不可见服务开销未测。六份 thin EXIT 继续 unknown，独立 owner close 均已确认。', '',
        '## 尚未测得的共享成本', '',
        '共享准备、离线检查、freeze/commit、质量打包、独立质量复核和完整端到端总耗时缺少完整计量回执，保留 unknown。原 per-episode 归档耗时已包含在 outer 区间，批次质量打包的完整耗时单列未知。既有安装回执属于复用准备来源，未归入本次新消耗。', '',
        'REPEAT 与 EDIT 十二槽均未运行，耗时和 usage 不估算。旧交付 manifest 的 SHA256 与根独立来源复核一致，144 份清单成员逐字节核对通过，连同 manifest 自身共绑定 145 份文件。绑定清单见 LEDGER.json。本工作没有新增模型、provider、产品、Blender、API 或 Git 操作。',
    ])
    (HERE / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'rows': len(result_rows), 'tool_attempts': 14,
                      'old_delivery_files_unchanged': len(delivery_checks), 'actual_resume_turns': 0}))


if __name__ == '__main__':
    main()
