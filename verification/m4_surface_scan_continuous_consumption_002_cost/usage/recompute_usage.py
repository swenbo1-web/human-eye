"""Recompute one terminal per actual 002 CLI call after the quality seal."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
SOURCE = ROOT / 'verification/m4_surface_scan_continuous_consumption_002'
REVIEW = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
COST_PLAN = Path('D:/hefe/docs/M4_SURFACE_SCAN_CONTINUOUS_CONSUMPTION_002_COST_PLAN.md')
PLAN_SHA = '718af692f891fb27150c8aa40fcfe2408ac80854399d1204a13a234c6ae2e6e3'
SEAL_SHA = 'ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c'
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
TURNS = ('BASE', 'REPEAT', 'EDIT')
SEGMENTS = {'FULL': (1, 2, 3), 'BASE': (1,), 'REPEAT_EDIT': (2, 3)}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ratio(value):
    return {'numerator': value.numerator, 'denominator': value.denominator, 'decimal': float(value)}


def main():
    inputs = {}
    source_expected = {}

    def bind(path):
        path = Path(path).resolve()
        inputs[str(path)] = digest(path)
        if path.is_relative_to(SOURCE.resolve()):
            relative = path.relative_to(SOURCE.resolve()).as_posix()
            if relative in source_expected:
                assert inputs[str(path)] == source_expected[relative], 'sealed_delivery_source:' + relative
        return path

    def read(path):
        return json.loads(bind(path).read_bytes())

    assert digest(bind(COST_PLAN)) == PLAN_SHA
    seal_path = REVIEW / 'QUALITY_SEAL.json'
    seal = read(seal_path)
    assert digest(seal_path) == SEAL_SHA
    assert seal['delivery_commit'] == 'a798caf982e2d7eefe0bf52b739b9bef88526be4'
    assert seal['preparation_commit'] == '11ae08e791c300c58ae935f4f632a22b3d7f3342'
    for relative, expected in seal['independent_evidence_sha256'].items():
        assert digest(bind(REVIEW / relative)) == expected, 'seal_evidence:' + relative
    assert digest(bind(SOURCE / 'quality/ANONYMOUS_QUALITY.zip')) == seal['anonymous_package_sha256']
    manifest_path = bind(SOURCE / 'DELIVERY_MANIFEST.json')
    assert digest(manifest_path) == seal['delivery_manifest_sha256']
    manifest = json.loads(manifest_path.read_bytes())
    source_expected.update({row['path']: row['sha256'] for row in manifest['files']})
    assert len(source_expected) == len(manifest['files']), 'unique_sealed_delivery_members'
    quality = read(REVIEW / 'quality/FINAL_RESULTS.json')
    assert quality['turns'] == 18 and quality['episodes'] == 6 and not quality['failed']
    assert quality['manual_review_pending'] is False
    quality_rows = {(row['anonymous_episode_id'], row['turn']): row for row in quality['results']}
    assert len(quality_rows) == len(quality['results']) == 18
    scope = read(REVIEW / 'usage_scope/RESULTS.json')
    assert scope['authorized_test_threads'] == 6 and scope['CLI_invocations'] == 18 and scope['resume_invocations'] == 12
    assert not scope['failed_checks']
    scope_threads = {row['authorized_thread_id_sha256'] for row in scope['scope_proofs']
                     if row['three_disjoint_task_windows'] and row['per_turn_CLI_terminal_scope_observed']}
    assert len(scope_threads) == 6
    proof_path = SOURCE / 'review/actual_usage/ALL_NUMERIC_PROOF.json'
    proof = read(proof_path)
    assert digest(proof_path) == scope['numeric_proof_sha256']
    proof_rows = {(thread['thread_id'], row['turn_index']): row
                  for thread in proof['threads'] for row in thread['per_turn_proof']}
    assert len(proof_rows) == 18 and all(row['confirmed_per_turn_invocation_scope'] for row in proof_rows.values())
    mapping_path = SOURCE / 'private/ANON_MAP.json'
    mapping = read(mapping_path)['rows']
    plan = read(SOURCE / 'PLAN.json')
    assert digest(mapping_path) == plan['anonymous_map_sha256']
    assert tuple(row['cell'] for row in mapping) == CELLS
    whitelist = read(SOURCE / 'private/THREAD_WHITELIST.json')
    consumers = {(row['thread_id'], row['turn_index']): row for row in whitelist['records']}
    assert len(consumers) == len(whitelist['records']) == 18
    for source in whitelist['source_outer_results']:
        assert digest(bind(source['path'])) == source['sha256']

    rows, episode_quality = [], []
    for identity in mapping:
        cell, group, pair = identity['cell'], identity['group'], identity['pair']
        assert group == cell[0] and pair == int(cell[1]) and group in ('N', 'C')
        episode_id = identity['anonymous_episode_id']
        public = read(SOURCE / 'quality/public' / episode_id / 'EPISODE.json')
        assert public['anonymous_episode_id'] == episode_id and public['execution_state'] == 'completed'
        assert public['valid_completion'] is True and public['outer_valid_completion'] is True
        assert public['counts'] == {'completed': 3, 'failed': 0, 'not_run': 0}
        outer = read(SOURCE / 'episodes' / cell / 'OUTER_RESULT.json')
        outer_timing = read(SOURCE / 'episodes' / cell / 'FINAL_TIMING.json')
        assert outer_timing['outer_valid_completion'] is True
        assert outer['owner_finish']['confirmed'] is True and outer['postclose_verification']['passed'] is True
        episode_quality.append({'cell': cell, 'group': group, 'pair': pair,
            'anonymous_episode_id': episode_id, 'complete_valid_execution': True})
        for index, label in enumerate(TURNS, 1):
            judged = quality_rows[(episode_id, index)]
            anonymous_turn_id = identity['anonymous_turn_ids'][index - 1]
            assert judged['anonymous_turn_id'] == anonymous_turn_id and judged['state'] == label
            assert judged['primary_content_classification'] == 'complete_correct'
            assert judged['current_state_basis']['classification'] == 'sufficient'
            assert judged['execution_classification'] == 'completed'
            public_turn = public['turns'][index - 1]
            assert public_turn['anonymous_turn_id'] == anonymous_turn_id and public_turn['valid_completion'] is True
            folder = ROOT / '.m4cc2' / cell / 'c/turns' / label
            consumer_path = folder / 'CONSUMER.json'
            consumer = read(consumer_path)
            key = (consumer['thread_id'], index)
            authorized = consumers[key]
            assert Path(authorized['consumer_record']).resolve() == consumer_path.resolve()
            assert digest(consumer_path) == authorized['consumer_sha256']
            assert hashlib.sha256(consumer['thread_id'].encode()).hexdigest() in scope_threads
            assert consumer['turn_index'] == index and consumer['status'] == 'completed'
            assert consumer['valid_completion'] is True
            expected = None if index == 1 else consumer['thread_id']
            assert consumer['expected_thread_id'] == authorized['expected_thread_id'] == expected
            events_path = bind(folder / 'events.jsonl')
            assert digest(events_path) == consumer['archive']['source_files_sha256']['events.jsonl']
            terminal_rows = []
            with events_path.open('rb') as stream:
                for line_number, raw in enumerate(stream, 1):
                    event = json.loads(raw).get('event', {})
                    if event.get('type') == 'turn.completed':
                        terminal_rows.append({'line': line_number, 'line_sha256': hashlib.sha256(raw).hexdigest(),
                                              'usage': event.get('usage')})
            assert len(terminal_rows) == 1
            observed = terminal_rows[0]['usage']
            assert type(observed) is dict and {'input_tokens', 'output_tokens'} <= set(observed)
            assert all(type(value) is int and value >= 0 for value in observed.values())
            assert [observed] == consumer['raw_usage_events'] == consumer['usage_rows']
            assert observed == consumer['usage'] == proof_rows[key]['raw_CLI_usage']
            assert observed.get('cached_input_tokens', 0) <= observed['input_tokens']
            assert observed.get('cache_write_input_tokens', 0) <= observed['input_tokens']
            assert observed.get('reasoning_output_tokens', 0) <= observed['output_tokens']
            total = observed['input_tokens'] + observed['output_tokens']
            if 'total_tokens' in observed:
                assert observed['total_tokens'] == total
            rows.append({'cell': cell, 'group': group, 'pair': pair, 'turn_index': index, 'turn': label,
                'anonymous_episode_id': episode_id, 'anonymous_turn_id': anonymous_turn_id,
                'quality_complete_correct': True, 'current_state_basis_sufficient': True, 'execution_completed': True,
                'raw_usage': observed, 'input_plus_output_tokens': total,
                'original_consumer_usage_semantics': consumer['usage_semantics'],
                'original_consumer_usage_aggregation': consumer['usage_aggregation'],
                'derived_scope': 'per_turn_CLI_invocation_observed',
                'actual_thread_id_sha256': hashlib.sha256(consumer['thread_id'].encode()).hexdigest(),
                'scope_seal_sha256': SEAL_SHA, 'consumer_source': str(consumer_path.resolve()),
                'CLI_events_source': str(events_path), 'CLI_terminal_line': terminal_rows[0]['line'],
                'CLI_terminal_line_sha256': terminal_rows[0]['line_sha256']})
    assert [(row['cell'], row['turn_index']) for row in rows] == [(cell, index) for cell in CELLS for index in (1, 2, 3)]
    assert {row['actual_thread_id_sha256'] for row in rows} == scope_threads
    fields = set(rows[0]['raw_usage'])
    assert all(set(row['raw_usage']) == fields for row in rows), 'complete_consistent_reported_fields'

    def aggregate(selected):
        values = {key: sum(row['raw_usage'][key] for row in selected) for key in sorted(fields)}
        return {'invocations': len(selected), 'usage_fields': values,
                'input_plus_output_tokens': values['input_tokens'] + values['output_tokens']}

    episodes = []
    for identity in mapping:
        episode_rows = [row for row in rows if row['cell'] == identity['cell']]
        episodes.append({key: identity[key] for key in ('cell', 'group', 'pair')} | {
            'segments': {segment: aggregate([row for row in episode_rows if row['turn_index'] in indexes])
                         for segment, indexes in SEGMENTS.items()}})
    groups = {group: {segment: aggregate([row for row in rows if row['group'] == group and row['turn_index'] in indexes])
                     for segment, indexes in SEGMENTS.items()} for group in ('N', 'C')}
    pairs, segments = {}, {}
    by_cell = {row['cell']: row for row in episodes}
    for segment in SEGMENTS:
        pairs[segment] = []
        for pair in (1, 2, 3):
            n = by_cell['N' + str(pair)]['segments'][segment]
            c = by_cell['C' + str(pair)]['segments'][segment]
            pairs[segment].append({'pair': pair, 'N_cell': 'N' + str(pair), 'C_cell': 'C' + str(pair),
                'N_usage': n, 'C_usage': c,
                'C_over_N_input_plus_output': ratio(Fraction(c['input_plus_output_tokens'], n['input_plus_output_tokens']))})
        quotients = [Fraction(row['C_usage']['input_plus_output_tokens'], row['N_usage']['input_plus_output_tokens'])
                     for row in pairs[segment]]
        n_total = groups['N'][segment]['input_plus_output_tokens']
        c_total = groups['C'][segment]['input_plus_output_tokens']
        segments[segment] = {'N_total_input_plus_output': n_total, 'C_total_input_plus_output': c_total,
            'median_pair_ratio': ratio(statistics.median(quotients)), 'ratio_of_group_totals': ratio(Fraction(c_total, n_total)),
            'C_total_not_higher_than_N': c_total <= n_total}
    for group in ('N', 'C'):
        assert groups[group]['FULL']['invocations'] == 9
        assert groups[group]['FULL']['input_plus_output_tokens'] == groups[group]['BASE']['input_plus_output_tokens'] + groups[group]['REPEAT_EDIT']['input_plus_output_tokens']
    quality_gate = {group: {'complete_valid_episodes': sum(row['group'] == group and row['complete_valid_execution'] for row in episode_quality),
        'complete_correct_current_basis_turns': sum(row['group'] == group and row['quality_complete_correct'] and row['current_state_basis_sufficient'] for row in rows)}
        for group in ('N', 'C')}
    quality_passed = all(row == {'complete_valid_episodes': 3, 'complete_correct_current_basis_turns': 9} for row in quality_gate.values())
    bind(Path(__file__))
    output = {'schema': 'continuous_002_terminal_usage_accounting_v1',
        'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002-COST',
        'admin_commit': 'd05cecf6fe3ddfeb19e04518d3d80a8dbdc40488', 'cost_plan_sha256': PLAN_SHA,
        'source_delivery_commit': seal['delivery_commit'], 'quality_seal_sha256': SEAL_SHA,
        'rows': rows, 'episode_quality': episode_quality, 'episode_aggregates': episodes,
        'group_aggregates': groups, 'pair_comparisons': pairs, 'segment_summaries': segments,
        'gates': {'quality': {'passed': quality_passed, 'groups': quality_gate},
            'token': {'passed': segments['FULL']['C_total_not_higher_than_N'], 'scope_confirmed_invocations': 18,
                      'metric': 'FULL C input_tokens + output_tokens <= FULL N input_tokens + output_tokens'},
            'time': {'passed': None, 'status': 'await_independent_timing_accounting'}},
        'aggregation': 'Within each view, sum exactly one terminal per independently scope-confirmed CLI invocation. BASE and REPEAT_EDIT partition FULL. Do not add these three overlapping views together.',
        'accounting_limits': ['Cached/cache-write values stay within reported input and are not added to it.',
            'Reasoning stays within reported output and is not added to it.',
            'Repeated history is actual reported input and is not subtracted.',
            'No token_count snapshots were summed for any cost aggregate.',
            'Actual fees, subscription debit, provider requests and hidden retry/abandoned-stream coverage remain unknown.',
            '18 missing thin EXIT receipts remain unknown. This cost step does not change the quality seal.'],
        'inputs_sha256': inputs, 'new_model_provider_Blender_product_API_runs': 0}
    (HERE / 'USAGE.json').write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')
    lines = ['# 连续消费002的终态 token 账本', '',
        '质量 seal 与全部证据摘要核对一致，私有映射逐轮对应十八份完整正确、当前依据充分的答案及六个完整有效 episode。每组均为3/3 episode、9/9轮，质量门通过。十八份缺失 thin EXIT 仍为 unknown。', '',
        '| 片段 | N input＋output | C input＋output | 三对 C/N 比值的中位数 | C/N 总量比 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for segment, values in segments.items():
        lines.append('| ' + ' | '.join((segment, str(values['N_total_input_plus_output']), str(values['C_total_input_plus_output']),
            f"{values['median_pair_ratio']['decimal']:.6f}", f"{values['ratio_of_group_totals']['decimal']:.6f}")) + ' |')
    lines += ['', '## 固定三对', '', '| 片段 | 配对 | N | C | C/N |', '| --- | ---: | ---: | ---: | ---: |']
    for segment, comparisons in pairs.items():
        for row in comparisons:
            lines.append('| ' + ' | '.join((segment, str(row['pair']), str(row['N_usage']['input_plus_output_tokens']),
                str(row['C_usage']['input_plus_output_tokens']), f"{row['C_over_N_input_plus_output']['decimal']:.6f}")) + ' |')
    token_pass = output['gates']['token']['passed']
    lines += ['', '## 口径与判定', '',
        'FULL 的 C 实际 input＋output 总量不高于 N，token 门通过。' if token_pass else 'FULL 的 C 实际 input＋output 总量高于 N，token 门未通过。', '',
        '每轮只取一个 CLI turn.completed 终值，逐字段核对原 consumer、usage_rows、raw_usage_events 及已封的逐轮范围证明。原 consumer 的 unknown 标签和空聚合保留，派生 scope 另列。未累加 token_count 快照，未从 input 扣去 cached、旧历史或相同文本，也未把 reasoning 再加到 output。', '',
        '每个视角内部每轮只计一次。BASE 与 REPEAT_EDIT 划分 FULL，三个视角的总量不能相加。中位比由三对各自 C/N 比值求中位数，总量比由两组原总量相除，两者分列。逐轮、逐 episode、分组和配对原字段均在 USAGE.json。', '',
        '时间门由独立 timing 账本复核，本文件没有据 token 通过宣称总体门通过。费用、Pro 扣账、provider 请求次数及隐藏重试/弃流范围保持 unknown。单一固定任务的三对结果不能外推所有三维场景。', '',
        '本项只读现有原件，没有读取其他 session、凭据或启动模型、provider、Blender、产品、API 或 Git。输入绝对路径与 SHA256 完整保存在 USAGE.json。']
    (HERE / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'rows': len(rows), 'quality_gate': quality_passed, 'token_gate': token_pass, 'segments': segments}, ensure_ascii=False))


if __name__ == '__main__':
    main()
