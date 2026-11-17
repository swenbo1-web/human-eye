"""Publish the fixed facts-first candidate and all original bounded outcomes."""

import hashlib
import json
import os
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')


def read(name):
    return json.loads((HERE / name).read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    began = time.perf_counter_ns()
    audit = read('checks/FINAL_RUNTIME_REVIEW.json')
    assert audit['status'] == 'passed' and audit['failed_check_count'] == 0
    author = read('scoring/AUTHOR_SCORES.json')
    independent = read('scoring/INDEPENDENT_SCORES.json')
    assert author['summary']['accepted_cases'] == independent['summary']['accepted_cases'] == 0
    assert len(independent['cases']) == 3
    for case in independent['cases']:
        assert not case['accepted']
        assert [gate.get('gate_id', gate.get('id')) for gate in case['gates'] if gate['verdict'] != 'pass'] == ['G1']
    binding = read('B_RUN_BINDING.json')
    benchmark = read('BENCHMARK_RESULT.json')
    inputs = read('INPUTS.json')
    archive = read('RUNTIME_ARCHIVE.json')
    sealed = read('ANSWERS_SEALED.json')
    previous = json.loads((ROOT / 'verification/m4_source_region_consumption_001/DECISION.json').read_bytes())
    old_brief_bytes = []
    for case in ('S1', 'S2', 'S3'):
        old_brief_bytes.append((HERE / 'historical' / case / 'ORIGINAL_BRIEF.json').stat().st_size)
    new_bytes = [row['brief_UTF8_bytes'] for row in inputs['cases']]
    publication_sum = sum(row['slot_through_publication_seconds'] for row in audit['slots'])
    value = {
        'schema': 'm1-source-region-facts-first-decision-v1',
        'task': 'M1-SOURCE-REGION-FACTS-FIRST-001',
        'decision': 'retain_B_as_isolated_candidate_original_nine_gate_acceptance_unmet',
        'accepted_cases': 0, 'case_denominator': 3,
        'delivery_completed_cases': 3, 'author_and_independent_scores_agree': True,
        'case_scores': [{'case_id': case['case_id'], 'passed_gates': 8,
                         'failed_gates': ['G1'], 'accepted': False} for case in author['cases']],
        'fixed_product': {'source_git': binding['preparation_git'], 'source_files': len(binding['source_manifest']),
            'source_sha256': binding['source_sha256'], 'wheel_sha256': binding['wheel_sha256'],
            'install_root': binding['install_root'], 'distribution_version': binding['distribution_version'],
            'product_file_changes': ['human_eye_plugin/live_spatial_mcp.py'],
            'freeze_pre_model_git': '23553c5794b66c31f46346fd9d4f033160473488',
            'freeze_sha256': sha(HERE / 'FROZEN.json'), 'default_deployment_changes': 0},
        'projection_contract': {'schema': 'source-region-brief-v2',
            'facts': 'Original task_result.facts retained with original unit, coordinate frame, reference and nearest source witness.',
            'region_ref': 'One original complete self-contained v1 reference, unchanged and round-trippable.',
            'details': 'Original full response semantics retained with actual OLD/A/B full MCP result equality.',
            'image': 'Original native PNG bytes retained.',
            'first_4096_UTF8_bytes': 'Task facts, units, nearest source witness, pixel statistics and image references retained.',
            'fixed_case_brief_limit_bytes': 10000,
            'other_legal_selection_scope': 'Pure controls cover one and 4096 selected indices. Complete v1 refs can exceed the fixed three-case byte limit.'},
        'text_delivery': {'old_prepared_brief_bytes': old_brief_bytes,
            'new_delivered_brief_bytes': new_bytes, 'old_total': sum(old_brief_bytes),
            'new_total': sum(new_bytes), 'byte_reduction_fraction': 1 - sum(new_bytes) / sum(old_brief_bytes),
            'original_PNG_delivered_bytes': audit['totals']['native_image_bytes']},
        'construction_optimization': {'selected_candidate': benchmark['selected_candidate'],
            'paired_windows_per_case': 5, 'formatter_iterations_per_window': 20,
            'case_medians': benchmark['summary'], 'deepcopy_calls_A_B': [37, 1],
            'formatter_json_dumps_A_B': [1, 1],
            'timing_scope': benchmark['timing_scope'], 'work_scope': benchmark['instrumentation_scope'],
            'task_speedup_claimed': False},
        'client_budget_evidence': {'public_source_tag': 'rust-v0.152.1',
            'public_source_commit': '5adb68a49933ae446bf11935662c83dba55a0804',
            'qualification_checks': 375,
            'scope': 'Public-source fallback reconstruction, matched to original retained texts. Actual provider request and binary-to-tag reproducible-build proof remain unobserved.'},
        'model_profile': {'requested_model': 'gpt-6.1-sol', 'requested_effort': 'medium',
            'requested_service_tier': 'default', 'CLI_version': '0.152.1',
            'resolved_effort': None, 'provider_internal_profile': 'unobserved'},
        'cases': audit['slots'],
        'original_turn_completed_usage_sums': audit['totals']['original_turn_completed_usage_sums'],
        'usage_scope': audit['cost_scope']['usage_scope'],
        'budget': {'consumers': 3, 'replacement_consumers': 0, 'completed_CLI_tools_each': [1, 1, 1],
            'empty_discoveries_each': [0, 0, 0], 'task_seconds_limit': 450, 'lifecycle_seconds_limit': 600,
            'new_Blender': 0, 'new_source_capture': 0, 'new_product_solving': 0, 'raster': 0,
            'PNG_NPZ_encoding': 0, 'training': 0, 'paid_API': 0, 'default_deployment_changes': 0,
            'Google_and_key': 'paused'},
        'cost': {'preparation_and_nested_phases': audit['cost_phases'],
            'nested_preparation_phases_are_additive': False,
            'formatter_protocol_and_regression_work': audit['cost_operations'],
            'full_slot_seconds_sum': audit['totals']['full_slot_seconds_sum'],
            'full_slot_through_publication_seconds_sum': publication_sum,
            'runtime_audit_seconds': audit['cost_scope']['audit_wall_seconds'],
            'author_scoring_seconds': (author['closed_ns'] - author['started_ns']) / 1e9,
            'archive_files': archive['file_count'], 'archive_original_bytes': archive['original_bytes'],
            'closeout_started_ns': read('CLOSEOUT_STARTED.json')['started_ns'],
            'cost_boundary': 'Per-consumer windows include cleanup and raw archive. Final aggregate archive, scoring, Git publication and administrator review have separate boundaries.',
            'unknowns': audit['unknowns']},
        'comparison': {'previous_accepted_cases': previous['accepted_cases'],
            'previous_case_denominator': previous['case_denominator'],
            'previous_content_scores': {'S1': 'unrun_no_observation', 'S2': '5/9', 'S3': '6/9'},
            'current_content_scores': {'S1': '8/9', 'S2': '8/9', 'S3': '8/9'},
            'current_fact_adoption': 'All three adopt original distance in metres, accurate centimetres, witnesses, complete measurement scope, actual image participation, sample counts, unknowns and bounded surface separation.',
            'preserved_failure': 'All three omit required millimetres under unchanged G1.',
            'comparison_scope': 'S1 is first effective normal-image consumption. S2/S3 compare adoption against earlier delivered observations. Prompt, tool schema, scoring and PNG are byte-identical. Protocol accounting is repaired in this batch, so delivery and content changes have separate causes.',
            'task_performance_comparison': 'Unqualified. Previous cases failed and S1 lacked input. Three one-shot cases establish no distributional or whole-task speedup.'},
        'acceptance_alignment': {
            'prompt': 'Common prompt asks for distance and units generally.',
            'frozen_G1': 'Requires both metres and millimetres.',
            'observed': 'All three accurately choose metres and centimetres.',
            'rule_changed_after_answers': False,
            'interpretation': 'Original strict result stays 0/3. The sole gate failure does not establish a geometric error or failed fact delivery.'},
        'regressions': {'workspace': read('tests/REGRESSIONS_source.json'),
                        'isolated_B': read('tests/REGRESSIONS_installed.json')},
        'independent_reviews': {'prelaunch_passed': 25, 'runtime_passed': audit['check_count'],
            'author_scores_sha256': sha(HERE / 'scoring/AUTHOR_SCORES.json'),
            'independent_scores_sha256': sha(HERE / 'scoring/INDEPENDENT_SCORES.json')},
        'archive': {'original_files_deleted': 0, 'files': archive['file_count'],
            'byte_exact_files': sum(row['byte_exact'] for row in archive['files']),
            'projected_members': archive['projected_members'],
            'reasoning_event_bodies': 'Zero reasoning/analysis events observed in this batch. Shared copies are byte-exact.'},
        'limitations': ['Historical sealed observation formatting and consumption only.',
            'Image-independent contribution, natural tool-selection benefit and current-host whole-task value remain untested.',
            'A/B timing covers formatter calls and original PNG handling only.',
            'Three ordinary MCP children exited with code1 and retained-handle proof. Normal EXIT receipts and the code1 cause remain unknown.',
            'Fees, provider-internal requests, image tokens, actual provider payload and resolved effort are unobserved.',
            'Three original consumers provide no broad model or scenario generalization.'],
        'next_single_recommendation': 'Independent administrator review should first settle the prompt/G1 unit alignment using these sealed originals. Then freeze one current-host complete read-only source-region task for value validation with candidate B. Keep any revised acceptance prospective and retain this original 0/3 result.',
        'answers_sealed_sha256': sha(HERE / 'ANSWERS_SEALED.json'),
        'summarize_started_ns': began, 'summarize_ready_ns': time.perf_counter_ns(),
    }
    save('DECISION.json', value)
    rows = '\n'.join(
        f"| {case['case_id']} | {new_bytes[index]:,} | 8/9 | G1 毫米换算缺失 | {case['slot_through_publication_seconds']:.6f} |"
        for index, case in enumerate(audit['slots']))
    medians = '\n'.join(
        f"| {row['case']} | {row['A_median_ns'] / 1e6:.4f} | {row['B_median_ns'] / 1e6:.4f} | {row['B_time_improvement_fraction'] * 100:.3f}% |"
        for row in benchmark['summary'])
    report = f'''# 事实优先交付与三组实际消费结果

本轮形成 source-region-brief-v2 和一次构造优化 B。三组真实消费者均完成一次读取、原图交付与进程关闭。原九门验收结果为 **0/3**，三组各 **8/9**，作者与独立评分一致。

三份原答都准确采用 0.37011719389236364 m，并换算为约 37.0117 cm。冻结 G1 要求同时给出毫米等价量，三份回答都缺少这一项。原共同题面仅要求报告距离和单位。报告保留原门限及失败，同时记录题面与私有单位要求的对齐限制。

## 固定版本与实现

产品源码提交为 `{binding['preparation_git']}`。143 个源码文件的聚合 SHA 为 `{binding['source_sha256']}`，隔离安装位于 `{binding['install_root']}`。模型启动前输入及执行源封存提交为 `23553c57`，FROZEN.json 绑定 363 项直接输入和 14 项执行源。

产品变更集中在 `human_eye_plugin/live_spatial_mcp.py`。默认交付先给出量测、单位、参考对象、最近点及源见证，再给出像素、显示参与和图像引用。区域坐标、逐面拓扑和完整可见成员清单通过已有 full 入口读取。默认包保留一份完整自包含 v1 region_ref，原查询可直接往返。

三组默认文本从 {sum(old_brief_bytes):,} 字节减为 {sum(new_bytes):,} 字节，合计减少 {(1 - sum(new_bytes) / sum(old_brief_bytes)) * 100:.3f}%。距离、单位、见证、像素与图像引用均在前 4,096 UTF-8 字节。三组实际投影的完整结果和原 PNG 均已核对。4096 面等其他合法选区保留完整引用，固定三例的 10,000 字节门限只适用于这三个登记输入。

## 一次构造优化

A 先实现正确 v2，B 在构造前选择交付字段并共享一次来源校验。默认路径的顶层 deepcopy 调用由 37 次降至 1 次，格式化器 JSON 编码次数保持每次 1 次。复制参数 JSON 字节统计反映复制工作量，内存另由 tracemalloc 记录。

每个输入固定五对窗口，每个窗口 20 次实际安装格式化调用，顺序为 AB、BA、AB、BA、AB。下表为每 20 次调用的窗口中位数。

| 场景 | A 毫秒 | B 毫秒 | 格式化区间减少 |
| --- | --- | --- | --- |
{medians}

A/B 默认完整 MCP 内容一致，旧版/A/B full 内容一致，调用方原对象与缓存隔离控制通过。639 次纯格式化调用包含 600 次定时调用和预热、导出、工作量、内存探查，全部普通 Python worker 已关闭。表中约 90% 的变化仅覆盖格式化与原 PNG 处理区间，整项任务的速度收益仍待完整任务测量。

## 实际消费

本批消费历史 DISPLAY001 封存观测的新投影。沿原题面、原工具说明、原九门及相同 PNG，使用固定 CLI 0.152.1，按 S1、S2、S3 串行启动三个 fresh 消费者。请求配置为 gpt-6.1-sol、medium、default。供应商实际解析后的 effort 尚未暴露。三份原答全部封存后才开始内容评分，新增补样为零。

| 场景 | 默认文本字节 | 原九门 | 未通过项 | 含发布的完整窗口秒 |
| --- | --- | --- | --- | --- |
{rows}

S1 采用 35,452 个选区像素、385 个有样本面和 363 个无样本面，并保留 Cube 未参加图像但作为量测参考的事实。S2 采用双方参与显示、选区零像素和全部 748 面无样本。S3 采用选区未参加显示、零像素和全部 748 面未见。三例均采用完整选区到参考表面的距离、原见证和表面分离结论，实体内外保持证据不足。

旧批 S1 未得到观测，旧 S2/S3 分别为 5/9 与 6/9。本批三例各 8/9。S1 是正常图的首次有效消费。协议交付/计数修复和文本改进均发生在本轮，归因记录各自对应证据。失败旧会话与新会话缺少等质量条件，整任务耗时对照仍需独立安排。

## 验收、预算与成本

源码与隔离安装各通过 9 项回归，25 项独立前置审核、375 项客户端预算重建和 631 项独立运行检查通过。客户端重建依据同版本公开源码及原实际参数，供应商真实请求和二进制到源码标签的可重现构建关系仍缺直接证据。

每例只完成 1 次 CLI 工具调用和 1 幅原生 PNG 交付，均在原 450 秒任务和 600 秒生命周期内结束。三例含发布窗口合计 {publication_sum:.6f} 秒。实交文本共 29,942 字节、PNG 共 28,510 字节。新增 Blender、源采集、产品求解、栅格、PNG/NPZ 编码、训练、付费 API 和默认部署改动均为零，Google/key 保持暂停。

原始 CLI turn.completed 合计 input 42,661、cached input 9,728、output 4,213、reasoning output 0 tokens。准备窗口为 840.674589 秒，已包含构建、实现期间墙钟、协议/客户端检查、回归与基准的子阶段。子阶段各有原时钟记录，总窗与子阶段相加会重复。准备记录前的计划阅读、单独的人工编写工作量、供应商请求数、费用与图像 token 仍缺测量，供应商内实际输入与视觉消费仍未观测。评分、独立审核、汇总归档及 Git 发布具有各自边界。

三个 CLI 均退出 0，MCP 子进程由保留句柄确认退出 1 并关闭。当前对应进程已退出，正常 EXIT 收据缺失及退出 1 的原因仍为 unknown。全过程原件保留在本地，归档 {archive['file_count']} 件、{archive['original_bytes']:,} 字节，本批副本全部同字节，观察到的 reasoning/analysis 事件为零。

## 后续判断

保留 B 作为隔离候选。原九门结果仍为 0/3，独立审核应先根据封存原答核对题面与 G1 的单位要求。验收口径的调整应在后续任务启动前完成冻结。

下一项建议集中完成一个当前宿主中的完整只读选区任务，验证事实交付在真实流程中的质量、模型往返、完整耗时与成本。图像的独立贡献、自然工具选择、多场景泛化及复杂场景的整体收益仍待对应对照。

原答位于 answers/S1.txt、S2.txt、S3.txt，原作者与独立评分位于 scoring/AUTHOR_SCORES.json 和 scoring/INDEPENDENT_SCORES.json，运行与成本核验位于 checks/FINAL_RUNTIME_REVIEW.json。DECISION.json 记录固定版本、全部结果、成本与限制，RUNTIME_ARCHIVE.json 逐件绑定原件和副本。
'''
    with (HERE / 'REPORT.md').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(report)
        stream.flush()
        os.fsync(stream.fileno())
    save('SUMMARY_TIMING.json', {'started_ns': began, 'closed_ns': time.perf_counter_ns(),
        'decision_sha256': sha(HERE / 'DECISION.json'), 'report_sha256': sha(HERE / 'REPORT.md')})
    print(json.dumps({'decision': value['decision'], 'accepted_cases': 0, 'delivered_cases': 3,
                      'original_gate_failures': 3, 'runtime_checks': audit['check_count']}))


if __name__ == '__main__':
    main()
