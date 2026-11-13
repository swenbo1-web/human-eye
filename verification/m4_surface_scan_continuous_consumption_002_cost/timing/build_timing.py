"""Offline timing reconstruction from the sealed 002 integer-clock originals."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import statistics


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BATCH = ROOT / 'verification/m4_surface_scan_continuous_consumption_002'
REVIEW = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
COST_PLAN = Path('D:/hefe/docs/M4_SURFACE_SCAN_CONTINUOUS_CONSUMPTION_002_COST_PLAN.md')
SEAL_SHA = 'ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c'
PLAN_SHA = '718af692f891fb27150c8aa40fcfe2408ac80854399d1204a13a234c6ae2e6e3'
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
LABELS = ('BASE', 'REPEAT', 'EDIT')


class Inputs:
    def __init__(self):
        self.raw = {}

    def bytes(self, path):
        path = Path(path).resolve()
        if path not in self.raw:
            self.raw[path] = path.read_bytes()
        return self.raw[path]

    def json(self, path):
        return json.loads(self.bytes(path))

    def sha(self, path):
        return hashlib.sha256(self.bytes(path)).hexdigest()

    def unchanged(self):
        for path, raw in self.raw.items():
            assert path.read_bytes() == raw, 'input_changed:' + str(path)

    def manifest(self):
        return {str(path): hashlib.sha256(raw).hexdigest() for path, raw in sorted(self.raw.items())}


def interval(name, start, end):
    assert type(start) is int and type(end) is int and start <= end, 'integer_interval:' + name
    return {'name': name, 'started_ns': start, 'closed_ns': end, 'duration_ns': end - start}


def contains(parent, child):
    assert parent['started_ns'] <= child['started_ns'] <= child['closed_ns'] <= parent['closed_ns'], child['name']


def union(intervals):
    result = []
    for start, end in sorted((row['started_ns'], row['closed_ns']) for row in intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def elapsed(intervals):
    return sum(end - start for start, end in union(intervals))


def ratio(numerator, denominator):
    value = Fraction(numerator, denominator)
    return {'numerator': value.numerator, 'denominator': value.denominator, 'value': float(value)}


def build_turn(inputs, episode, turn, tool_rows):
    cell, label, index = episode['cell'], turn['turn_label'], turn['turn_index']
    folder = Path(turn['folder'])
    raw = inputs.json(folder / 'CONSUMER.json')
    timing = inputs.json(folder / 'FINAL_TIMING.json')
    whole = interval('consumer_full_turn', timing['started_ns'], timing['consumer_record_closed_ns'])
    assert whole['duration_ns'] == timing['full_turn_wall_ns']
    assert raw['started_ns'] == whole['started_ns'] and timing['accepted_success'] is True
    markers = [whole['started_ns'], raw['popen_ns'], raw['prompt_submitted_ns'], raw['final_received_ns'],
               raw['turn_completed_ns'], raw['process_exit_ns'], raw['cleanup_end_ns'], whole['closed_ns']]
    names = ('input_checks_to_launch', 'launch_to_prompt_submitted', 'prompt_to_final_received',
             'final_to_turn_completed', 'turn_completed_to_process_wait_return',
             'process_wait_return_to_cleanup_and_raw_archive_end', 'cleanup_end_to_consumer_record_close')
    phases = [interval(name, start, end) for name, start, end in zip(names, markers, markers[1:])]
    assert sum(row['duration_ns'] for row in phases) == whole['duration_ns']
    before = turn['status_before']['business_attempts']
    after = turn['status_after']['business_attempts']
    selected = [row for row in tool_rows if before < row['attempt'] <= after]
    owner_intervals = []
    for row in selected:
        assert type(row['elapsed_ns']) is int
        window = interval('owner_tool_' + str(row['attempt']), row['started_ns'], row['started_ns'] + row['elapsed_ns'])
        contains(whole, window)
        contains(phases[2], window)
        owner_intervals.append({**window, 'attempt': row['attempt'], 'tool': row['name']})
    events = []
    for line in inputs.bytes(folder / 'events.jsonl').splitlines():
        record = json.loads(line)
        event = record.get('event', {})
        if event.get('item', {}).get('type') == 'mcp_tool_call' and event.get('type') in ('item.started', 'item.completed'):
            assert type(record['perf_ns']) is int
            events.append({'phase': event['type'], 'received_ns': record['perf_ns']})
    completed = [row['received_ns'] for row in events if row['phase'] == 'item.completed']
    started = [row['received_ns'] for row in events if row['phase'] == 'item.started']
    assert len(completed) == len(selected)
    tool_union = elapsed(owner_intervals)
    tool_sum = sum(row['duration_ns'] for row in owner_intervals)
    unresolved = phases[2]['duration_ns'] - tool_union
    assert unresolved >= 0
    first_owner = min((row['started_ns'] for row in owner_intervals), default=None)
    last_result = max(completed, default=None)
    if last_result is not None:
        assert phases[2]['started_ns'] <= last_result <= raw['final_received_ns']
    return {'cell': cell, 'group': cell[0], 'pair': int(cell[1]), 'turn_index': index, 'turn_label': label,
            'anonymous_episode_id': episode['anonymous_episode_id'],
            'anonymous_turn_id': episode['anonymous_turn_ids'][index - 1],
            'whole': whole, 'full_turn_wall_ns': whole['duration_ns'], 'phases': phases,
            'tool_attempt_range': [before + 1, after], 'owner_tool_intervals': owner_intervals,
            'owner_tool_raw_sum_ns': tool_sum, 'owner_tool_union_ns': tool_union,
            'owner_tool_overlap_ns': tool_sum - tool_union,
            'prompt_to_final_partition': {'owner_tool_union_ns': tool_union,
                'model_service_transport_unresolved_ns': unresolved,
                'whole_ns': phases[2]['duration_ns'], 'additive_within_this_window': True},
            'first_owner_request_ns': first_owner,
            'prompt_to_first_owner_request_ns': None if first_owner is None else first_owner - raw['prompt_submitted_ns'],
            'first_cli_tool_started_event_received_ns': min(started, default=None),
            'last_cli_tool_completed_event_received_ns': last_result,
            'last_cli_tool_event_to_final_ns': None if last_result is None else raw['final_received_ns'] - last_result,
            'first_sufficient_facts_ns': None, 'first_sufficient_facts_to_final_ns': None,
            'sufficiency_scope': 'Not independently localized to a request. CLI event delivery marker does not establish provider/model receipt or first sufficient facts.',
            'timing_source': str((folder / 'FINAL_TIMING.json').resolve())}


def build_episode(inputs, row):
    outer_path = Path(row['folder']) / 'FINAL_TIMING.json'
    outer = inputs.json(outer_path)
    full = interval('outer_full_episode', outer['started_ns'], outer['business_receipts_closed_ns'])
    assert full['duration_ns'] == outer['full_episode_wall_ns'] and outer['outer_valid_completion'] is True
    coordinator_folder = Path(row['consumer_output'])
    coordinator = inputs.json(coordinator_folder / 'EPISODE_RESULT.json')
    coordinator_timing = inputs.json(coordinator_folder / 'FINAL_TIMING.json')
    tools = inputs.json(Path(row['owner_output']) / 'TOOLS.json')['tools']
    turns = [build_turn(inputs, row, turn, tools) for turn in coordinator['turns']]
    assert [turn['turn_label'] for turn in turns] == list(LABELS)
    for turn in turns:
        contains(full, turn['whole'])
    points = [full['started_ns'], turns[0]['whole']['started_ns'], turns[0]['whole']['closed_ns'],
              turns[1]['whole']['started_ns'], turns[1]['whole']['closed_ns'],
              turns[2]['whole']['started_ns'], turns[2]['whole']['closed_ns'], full['closed_ns']]
    names = ('outer_prefix_to_BASE', 'BASE', 'BASE_to_REPEAT_gap', 'REPEAT',
             'REPEAT_to_EDIT_gap_including_registered_edit', 'EDIT', 'outer_tail_after_EDIT')
    partition = [interval(name, start, end) for name, start, end in zip(names, points, points[1:])]
    assert sum(segment['duration_ns'] for segment in partition) == full['duration_ns']
    prefix_split = [interval('input_checks_startup_to_coordinator', full['started_ns'], coordinator['started_ns']),
                    interval('coordinator_prefix_to_BASE', coordinator['started_ns'], points[1])]
    assert sum(part['duration_ns'] for part in prefix_split) == partition[0]['duration_ns']
    tail_points = [points[-2], coordinator['cleanup_started_ns'], coordinator['cleanup_ended_ns'],
                   coordinator_timing['business_receipts_closed_ns'], full['closed_ns']]
    tail_names = ('EDIT_close_to_owner_cleanup_start', 'sole_owner_cleanup',
                  'coordinator_archives_and_episode_result_close',
                  'coordinator_timing_publication_postclose_outer_archive_and_result_close')
    tail_split = [interval(name, start, end) for name, start, end in zip(tail_names, tail_points, tail_points[1:])]
    assert sum(part['duration_ns'] for part in tail_split) == partition[-1]['duration_ns']
    assert coordinator_timing['full_episode_wall_ns'] == coordinator_timing['business_receipts_closed_ns'] - coordinator_timing['started_ns']
    administrative = []
    for path in sorted(Path(row['runtime_folder']).glob('ADMIN_*.json')):
        record = inputs.json(path)
        window = interval(record['request']['method'], record['started_ns'], record['ended_ns'])
        contains(full, window)
        administrative.append(window)
    edits = [part for part in administrative if part['name'] == 'continuity/qa_advance']
    assert len(edits) == 1
    contains(partition[4], edits[0])
    publication = inputs.json(Path(row['folder']) / 'TIMING_PUBLICATION.json')
    publication_window = interval('outer_FINAL_TIMING_publication', publication['started_ns'], publication['closed_ns'])
    assert publication_window['started_ns'] >= full['closed_ns']
    segments = {'FULL': full['duration_ns'], 'BASE': turns[0]['full_turn_wall_ns'],
                'REPEAT': turns[1]['full_turn_wall_ns'], 'EDIT': turns[2]['full_turn_wall_ns'],
                'REPEAT_EDIT': turns[1]['full_turn_wall_ns'] + turns[2]['full_turn_wall_ns']}
    turn_total = sum(turn['full_turn_wall_ns'] for turn in turns)
    assigned = [tool['attempt'] for turn in turns for tool in turn['owner_tool_intervals']]
    assert len(assigned) == len(set(assigned))
    assert sorted(assigned) == sorted(tool['attempt'] for tool in tools)
    return {'cell': row['cell'], 'turn_index': None, 'group': row['group'], 'pair': row['pair'],
            'anonymous_episode_id': row['anonymous_episode_id'], 'whole': full,
            'full_episode_wall_ns': full['duration_ns'], 'segments_ns': segments,
            'turns_total_ns': turn_total, 'outside_consumer_turns_ns': full['duration_ns'] - turn_total,
            'partition': partition, 'prefix_partition': prefix_split, 'tail_partition': tail_split,
            'registered_EDIT_admin_interval': edits[0], 'administrative_intervals': administrative,
            'administrative_union_ns': elapsed(administrative),
            'outer_timing_publication_outside_main_interval': publication_window,
            'BASE_including_outer_prefix_ns': turns[0]['whole']['closed_ns'] - full['started_ns'],
            'REPEAT_EDIT_contiguous_window_including_between_turn_gap_ns': turns[2]['whole']['closed_ns'] - turns[1]['whole']['started_ns'],
            'coordinator_wall_ns_nested': coordinator_timing['full_episode_wall_ns'],
            'owner_tool_union_ns_nested': sum(turn['owner_tool_union_ns'] for turn in turns),
            'scope': outer['scope'], 'durability': outer['durability']}, turns


def comparisons(episodes):
    indexed = {row['cell']: row for row in episodes}
    pairs = []
    stages = ('FULL', 'BASE', 'REPEAT', 'EDIT', 'REPEAT_EDIT')
    for pair in (1, 2, 3):
        native, compact = indexed['N' + str(pair)], indexed['C' + str(pair)]
        values = {}
        for stage in stages:
            n, c = native['segments_ns'][stage], compact['segments_ns'][stage]
            values[stage] = {'N_ns': n, 'C_ns': c, 'C_over_N': ratio(c, n)}
        pairs.append({'pair': pair, 'segments': values})
    aggregates = {}
    for stage in stages:
        values = [Fraction(pair['segments'][stage]['C_ns'], pair['segments'][stage]['N_ns']) for pair in pairs]
        native = sum(pair['segments'][stage]['N_ns'] for pair in pairs)
        compact = sum(pair['segments'][stage]['C_ns'] for pair in pairs)
        median = statistics.median(values)
        aggregates[stage] = {'N_total_ns': native, 'C_total_ns': compact,
                             'median_pair_C_over_N': ratio(median.numerator, median.denominator),
                             'total_C_over_N': ratio(compact, native),
                             'all_three_C_faster': all(value < 1 for value in values)}
    return pairs, aggregates


def shared_costs(inputs, run, episodes):
    formal = inputs.json(BATCH / 'FORMAL_STARTED.json')
    batch_span = interval('formal_reservation_to_last_recorded_batch_clock', formal['started_ns'], run['ended_ns'])
    gaps = [interval('reservation_prefix', formal['started_ns'], episodes[0]['whole']['started_ns'])]
    for previous, current in zip(episodes, episodes[1:]):
        gaps.append(interval(previous['cell'] + '_to_' + current['cell'], previous['whole']['closed_ns'], current['whole']['started_ns']))
    gaps.append(interval('last_episode_close_to_batch_recorded_end', episodes[-1]['whole']['closed_ns'], run['ended_ns']))
    outer_total = sum(row['full_episode_wall_ns'] for row in episodes)
    assert outer_total + sum(gap['duration_ns'] for gap in gaps) == batch_span['duration_ns']
    for episode in episodes:
        contains(batch_span, episode['outer_timing_publication_outside_main_interval'])
    historical = []
    for cell in CELLS:
        timing = inputs.json(ROOT / 'verification/m4_surface_scan_continuous_consumption_001/episodes' / cell / 'FINAL_TIMING.json')
        duration = timing['business_receipts_closed_ns'] - timing['started_ns']
        assert duration == timing['full_episode_wall_ns']
        historical.append({'cell': cell, 'started_ns': timing['started_ns'],
                           'closed_ns': timing['business_receipts_closed_ns'], 'full_episode_wall_ns': duration})
    fix_checks = []
    for name in ('a01', 'a02', 'a03', 'a04'):
        path = ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001/integration/offline' / (name + '_RESULT.json')
        result = inputs.json(path)
        assert type(result['wall_ns']) is int
        fix_checks.append({'attempt': name, 'reported_partial_wall_ns': result['wall_ns'],
                           'scope': 'Stored local-process test elapsed prefix. Complete preparation and source/RESULT/ZIP publication lack full timing.'})
    # These records establish a scope but carry no complete elapsed endpoints.
    inputs.json(BATCH / 'ROOT_OFFLINE_CHECK.json')
    inputs.json(BATCH / 'PREPARATION_ATTEMPT_01.json')
    entry_checks_path = BATCH / 'runtime/offline/a01/TESTS.txt'
    entry_checks_text = inputs.bytes(entry_checks_path).decode('utf8')
    entry_summary = re.search(r'(?m)^Ran (\d+) tests? in ([0-9]+(?:\.[0-9]+)?)s\r?$', entry_checks_text)
    assert entry_summary is not None and int(entry_summary[1]) == 3
    entry_checks = {'source': str(entry_checks_path.resolve()), 'source_sha256': inputs.sha(entry_checks_path),
                    'tests': int(entry_summary[1]), 'text_reported_seconds': entry_summary[2],
                    'text_reported_summary': entry_summary[0].rstrip('\r'),
                    'precision': 'Rounded unittest text. Original elapsed nanosecond endpoints unavailable.',
                    'reported_elapsed_ns': None, 'included_in_FULL': False,
                    'scope': '002 three necessary offline outer-entry/scheduler checks. Partial runner timing only. Complete preparation, Git/read-fix, packaging and coordination remain unknown.'}
    return {'current_batch_recorded_span': batch_span, 'current_episode_outer_sum_ns': outer_total,
            'current_publication_and_coordination_gaps': gaps,
            'current_outside_episode_recorded_ns': sum(gap['duration_ns'] for gap in gaps),
            'current_outer_FINAL_TIMING_publication_sum_ns_nested_in_gaps': sum(row['outer_timing_publication_outside_main_interval']['duration_ns'] for row in episodes),
            'final_RUN_RESULT_write_close_ns': None, 'quality_package_build_publish_ns': None,
            'current_preparation_offline_freeze_commit_total_ns': None,
            'current_preparation_offline_entry_checks': entry_checks,
            'unmeasured_scope': 'Final batch write/close, self-published timing receipts, complete preparation, quality packaging/publication and human coordination lack complete raw intervals. Unknown costs retain null without group allocation.',
            'historical_001_failed_episodes': historical,
            'historical_001_failed_outer_sum_ns': sum(row['full_episode_wall_ns'] for row in historical),
            'historical_interface_local_process_checks': fix_checks,
            'historical_interface_reported_partial_check_sum_ns': sum(row['reported_partial_wall_ns'] for row in fix_checks),
            'historical_interface_total_ns': None, 'project_total_investment_ns': None}


def write_report(result):
    aggregates = result['aggregates']
    totals = result['consumer_phase_totals_ns']
    shared = result['shared_and_historical_costs']
    lines = ['# 连续消费002时钟复算', '',
             '根质量 seal 为 `' + SEAL_SHA + '`。六集、十八轮全部保留，原始整数差值、区间包含关系和分割求和均通过。', '',
             '完整 episode 的配对 C/N 比值中位数为 ' + format(aggregates['FULL']['median_pair_C_over_N']['value'], '.6f') +
             '，满足 ≤0.70 时间门。token 门由独立 usage 账本核算。', '',
             '| 配对 | N完整 ns | C完整 ns | C/N |', '|---|---:|---:|---:|']
    for pair in result['pairs']:
        row = pair['segments']['FULL']
        lines.append('| ' + str(pair['pair']) + ' | ' + str(row['N_ns']) + ' | ' + str(row['C_ns']) + ' | ' + format(row['C_over_N']['value'], '.6f') + ' |')
    lines.extend(['', '| 区段 | N合计秒 | C合计秒 | 配对比值中位数 |', '|---|---:|---:|---:|'])
    for stage in ('FULL', 'BASE', 'REPEAT', 'EDIT', 'REPEAT_EDIT'):
        row = aggregates[stage]
        lines.append('| ' + stage + ' | ' + format(row['N_total_ns'] / 1e9, '.6f') + ' | ' + format(row['C_total_ns'] / 1e9, '.6f') + ' | ' + format(row['median_pair_C_over_N']['value'], '.6f') + ' |')
    lines.extend(['',
        '分轮区段使用各自 FINAL_TIMING 的 consumer 写闭范围。REPEAT_EDIT 为两轮相加，之间的管理间隙单列。三个配对的 REPEAT、EDIT 均观察到 C 较快，暂留的独立因果贡献仍需机制证据。', '',
        'prompt→final 内 owner 工具并集，N 为 ' + format(totals['N']['owner_tool_union_ns_nested_in_prompt_final'] / 1e9, '.6f') + ' 秒，C 为 ' + format(totals['C']['owner_tool_union_ns_nested_in_prompt_final'] / 1e9, '.6f') + ' 秒。模型/服务/传输未分解区间分别为 ' + format(totals['N']['model_service_transport_unresolved_ns_nested_in_prompt_final'] / 1e9, '.6f') + ' 秒和 ' + format(totals['C']['model_service_transport_unresolved_ns_nested_in_prompt_final'] / 1e9, '.6f') + ' 秒，尚不能归因于单一推理、缓存或交付格式机制。', '',
        'turn.completed 到 process.wait 返回合计，N 为 ' + format(totals['N']['turn_completed_to_process_wait_return'] / 1e9, '.6f') + ' 秒，C 为 ' + format(totals['C']['turn_completed_to_process_wait_return'] / 1e9, '.6f') + ' 秒。该边界属于本机观测。首次充分事实时刻全部 unknown，另列首次 owner 请求及最后 completed 工具事件到 final 的交付标记。', '',
        '当前 episode 外的已录发布与协调间隙合计 ' + format(shared['current_outside_episode_recorded_ns'] / 1e9, '.6f') + ' 秒。旧001六首轮失败 outer 合计 ' + format(shared['historical_001_failed_outer_sum_ns'] / 1e9, '.6f') + ' 秒。接口修复四次本地检查只记录部分 elapsed 合计 ' + format(shared['historical_interface_reported_partial_check_sum_ns'] / 1e9, '.6f') + ' 秒。本次002三项入口检查的 unittest 圆整文本时长为 ' + shared['current_preparation_offline_entry_checks']['text_reported_seconds'] + ' 秒，属于 runner 部分时长，原始 ns 时界未记录，单列于 FULL 之外。完整准备、修复、freeze/commit、Git/read-fix、质量包发布、最终 RUN_RESULT 写闭及人工协调成本均保持 unknown，未按组分摊。', '',
        '嵌套的工具、管理、coordinator、publication 区间未重复加入完整 outer。fsync、十八项 thin EXIT、共享 GUI 前后状态继续未测，QA 命名空间副作用保留。新增模型、Blender、产品、API及实验次数均为0，原件未改。原始 ns 和所有实际读取路径 SHA256 见 TIMING.json。', ''])
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf8', newline='\n')


def main():
    inputs = Inputs()
    assert inputs.sha(COST_PLAN) == PLAN_SHA, 'cost_authorization_sha'
    seal_path = REVIEW / 'QUALITY_SEAL.json'
    assert inputs.sha(seal_path) == SEAL_SHA, 'quality_seal_sha'
    seal = inputs.json(seal_path)
    for path, expected in seal['independent_evidence_sha256'].items():
        assert inputs.sha(REVIEW / path) == expected, 'sealed_evidence:' + path
    assert inputs.sha(BATCH / 'DELIVERY_MANIFEST.json') == seal['delivery_manifest_sha256']
    assert inputs.sha(BATCH / 'quality/ANONYMOUS_QUALITY.zip') == seal['anonymous_package_sha256']
    assert seal['quality']['primary_complete_correct'] == seal['quality']['current_state_basis_sufficient'] == 18
    assert seal['execution']['completed_episodes'] == 6 and seal['execution']['completed_turns'] == 18
    plan = inputs.json(BATCH / 'PLAN.json')
    mapping_path = BATCH / 'private/ANON_MAP.json'
    assert inputs.sha(mapping_path) == plan['anonymous_map_sha256']
    mapping = {row['cell']: row for row in inputs.json(mapping_path)['rows']}
    run = inputs.json(BATCH / 'RUN_RESULT.json')
    assert tuple(row['cell'] for row in run['records']) == CELLS
    episodes, turns = [], []
    for row in run['records']:
        for key in ('group', 'pair', 'anonymous_episode_id', 'anonymous_turn_ids'):
            assert row[key] == mapping[row['cell']][key], 'sealed_mapping:' + row['cell']
        episode, current_turns = build_episode(inputs, row)
        episodes.append(episode)
        turns.extend(current_turns)
    assert len(episodes) == 6 and len(turns) == 18
    pairs, aggregate = comparisons(episodes)
    shared = shared_costs(inputs, run, episodes)
    phase_totals = {}
    for group in ('N', 'C'):
        rows = [row for row in turns if row['group'] == group]
        names = [phase['name'] for phase in rows[0]['phases']]
        phase_totals[group] = {name: sum(phase['duration_ns'] for row in rows for phase in row['phases'] if phase['name'] == name) for name in names}
        phase_totals[group]['owner_tool_union_ns_nested_in_prompt_final'] = sum(row['owner_tool_union_ns'] for row in rows)
        phase_totals[group]['model_service_transport_unresolved_ns_nested_in_prompt_final'] = sum(row['prompt_to_final_partition']['model_service_transport_unresolved_ns'] for row in rows)
    full_median = aggregate['FULL']['median_pair_C_over_N']
    time_gate = Fraction(full_median['numerator'], full_median['denominator']) <= Fraction(7, 10)
    for producer in (BATCH / 'runtime/driver.py',
                     ROOT / 'verification/m4_surface_scan_continuity_001_fix1/runtime/consumer_transport.py',
                     ROOT / 'verification/m4_surface_scan_continuity_001_fix1/consumer/episode.py',
                     ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001/runtime/consumer_transport.py'):
        inputs.bytes(producer)
    inputs.bytes(Path(__file__))
    inputs.unchanged()
    result = {'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002-COST',
              'source_delivery_commit': seal['delivery_commit'], 'quality_seal_sha256': SEAL_SHA,
              'cost_plan_sha256': PLAN_SHA, 'clock': 'Original integer perf_counter_ns timestamps. Cross-record interval nesting verified on the recorded axis.',
              'episodes': episodes, 'turns': turns, 'pairs': pairs, 'aggregates': aggregate,
              'consumer_phase_totals_ns': phase_totals, 'shared_and_historical_costs': shared,
              'quality_prerequisite': 'sealed 18/18 complete correct and current-state sufficient. 6/6 complete execution',
              'full_episode_time_gate_C_over_N_median_le_0_70': time_gate,
              'token_gate': 'handled by separate usage ledger',
              'first_sufficient_facts_timing': 'unknown for all 18 turns. Delivery markers reported separately',
              'checks': {'raw_outer_deltas_match': True, 'raw_turn_deltas_match': True,
                         'all_turn_phase_partitions_exact': True, 'all_episode_partitions_exact': True,
                         'all_owner_tool_intervals_nested': True, 'all_28_attempts_assigned_once': sum(len(row['owner_tool_intervals']) for row in turns) == 28,
                         'batch_span_partition_exact': True, 'all_inputs_unchanged_during_reconstruction': True},
              'overlap_rule': 'Phase partitions are additive only within their parent. Coordinator, admin, tool, prompt-final and publication diagnostics are nested or separately outside main intervals and are never added to full episode totals.',
              'new_model_Blender_product_API_experiments': 0, 'inputs_sha256': inputs.manifest()}
    (HERE / 'TIMING.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')
    write_report(result)
    print(json.dumps({'episodes': 6, 'turns': 18, 'FULL_median_pair_ratio': full_median,
                      'time_gate': time_gate, 'inputs': len(inputs.raw)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
