"""Recalculate the fixed, quality-sealed 002 cost ledger without live calls."""

import hashlib
import importlib.util
import json
from pathlib import Path
from fractions import Fraction
import statistics
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'verification/m4_surface_scan_continuous_consumption_002'
SOURCE_COMMIT = 'a798caf982e2d7eefe0bf52b739b9bef88526be4'
SEAL_SHA = 'ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c'
ORDER = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
inputs = {}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    inputs[str(path)] = digest(raw)
    return json.loads(raw)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                    encoding='utf8', newline='\n')


def ratio(numerator, denominator):
    value = Fraction(numerator, denominator)
    return {'numerator': value.numerator, 'denominator': value.denominator, 'value': float(value)}


def run_builders():
    for name in ('timing/build_timing.py', 'usage/recompute_usage.py'):
        subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / name)],
                       capture_output=True, check=True)
    path = HERE / 'mechanism/build_mechanism.py'
    spec = importlib.util.spec_from_file_location('_cost_recorded_mechanism', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rebuilt = module.Builder().run()
    assert module.encoded(rebuilt) == (HERE / 'mechanism/MECHANISM.json').read_bytes()


def immutable_sources(seal):
    """Bind recorded files and runtime members to the sealed delivery."""
    manifest_path = SOURCE / 'DELIVERY_MANIFEST.json'
    manifest = read(manifest_path)
    assert inputs[str(manifest_path)] == seal['delivery_manifest_sha256']
    relative = manifest_path.relative_to(ROOT).as_posix()
    assert subprocess.check_output(['git', 'cat-file', 'blob', SOURCE_COMMIT + ':' + relative], cwd=ROOT) == manifest_path.read_bytes()
    pinned = {str(manifest_path): seal['delivery_manifest_sha256']}
    for row in manifest['files']:
        path = (SOURCE / row['path']).resolve()
        assert digest(path.read_bytes()) == row['sha256'], path
        pinned[str(path)] = row['sha256']
        inputs[str(path)] = row['sha256']
    preparation = read(SOURCE / 'PREPARATION.json')
    pinned.update({str(Path(path).resolve()): sha for path, sha in preparation['external_sha256'].items()})
    runtime_roots = []
    for batch in (SOURCE, ROOT / 'verification/m4_surface_scan_continuous_consumption_001'):
        run = read(batch / 'RUN_RESULT.json')
        for episode in run['records']:
            manifest_path = Path(episode['folder']) / 'RUNTIME_MANIFEST.json'
            member_manifest = read(manifest_path)
            relative = manifest_path.relative_to(ROOT).as_posix()
            committed = subprocess.check_output(['git', 'cat-file', 'blob', SOURCE_COMMIT + ':' + relative], cwd=ROOT)
            assert committed == manifest_path.read_bytes()
            archive = Path(member_manifest['archive'])
            assert digest(archive.read_bytes()) == member_manifest['archive_sha256']
            inputs[str(archive.resolve())] = member_manifest['archive_sha256']
            runtime_roots.append((Path(episode['runtime_folder']).resolve(), member_manifest))
    review = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
    for name, sha in seal['independent_evidence_sha256'].items():
        path = (review / name).resolve()
        assert digest(path.read_bytes()) == sha, path
        inputs[str(path)] = sha
        pinned[str(path)] = sha
    work = read(HERE / 'WORK_ORDER.json')
    for row in work['inputs']:
        path = Path(row['source']).resolve()
        assert digest(path.read_bytes()) == row['sha256']
        assert (HERE / row['path']).read_bytes() == path.read_bytes()
        pinned[str(path)] = row['sha256']
        inputs[str(path)] = row['sha256']
        inputs[str((HERE / row['path']).resolve())] = row['sha256']
    return pinned, runtime_roots


def bind_inputs(pinned, runtime_roots):
    bindings = []
    for name, sha in sorted(inputs.items()):
        path = Path(name)
        assert digest(path.read_bytes()) == sha, name
        provenance = 'current_cost_material'
        if not path.is_relative_to(HERE):
            provenance = 'sealed_source'
            expected = pinned.get(name)
            for runtime, manifest in runtime_roots:
                if path.is_relative_to(runtime):
                    member = path.relative_to(runtime).as_posix()
                    expected = manifest['members'][member]['sha256']
                    provenance = 'sealed_runtime_archive_member'
            if expected is None:
                repository = ROOT if path.is_relative_to(ROOT) else Path('D:/hefe')
                commit = SOURCE_COMMIT if repository == ROOT else 'd05cecf6fe3ddfeb19e04518d3d80a8dbdc40488'
                relative = path.relative_to(repository).as_posix()
                committed = subprocess.check_output(['git', 'cat-file', 'blob', commit + ':' + relative], cwd=repository)
                expected = digest(committed)
            assert expected == sha, name
        bindings.append({'path': name, 'sha256': sha, 'provenance': provenance})
    return bindings


def raw_metrics(run):
    result = {}
    for episode in run['records']:
        outer = read(Path(episode['folder']) / 'FINAL_TIMING.json')
        assert outer['outer_valid_completion'] is True
        assert outer['full_episode_wall_ns'] == outer['business_receipts_closed_ns'] - outer['started_ns']
        times, tokens = [], []
        for turn in episode['coordinator']['turns']:
            folder = Path(turn['folder'])
            timing = read(folder / 'FINAL_TIMING.json')
            assert timing['full_turn_wall_ns'] == timing['consumer_record_closed_ns'] - timing['started_ns']
            times.append(timing['full_turn_wall_ns'])
            event_path = folder / 'events.jsonl'
            raw = event_path.read_bytes()
            inputs[str(event_path.resolve())] = digest(raw)
            events = [json.loads(line)['event'] for line in raw.splitlines()]
            terminal = [event['usage'] for event in events if event.get('type') == 'turn.completed']
            assert len(terminal) == 1 and terminal[0] == turn['consumer']['usage']
            assert type(terminal[0]['input_tokens']) is int and type(terminal[0]['output_tokens']) is int
            tokens.append(terminal[0]['input_tokens'] + terminal[0]['output_tokens'])
        assert len(times) == len(tokens) == 3
        result[episode['cell']] = {'whole_ns': outer['full_episode_wall_ns'], 'turn_ns': times, 'turn_tokens': tokens}
    return result


def build_views(raw):
    views = {}
    for name, selected in (('FULL', (0, 1, 2)), ('BASE', (0,)), ('REPEAT_EDIT', (1, 2))):
        pairs = []
        for pair in (1, 2, 3):
            n, c = raw['N' + str(pair)], raw['C' + str(pair)]
            n_time = n['whole_ns'] if name == 'FULL' else sum(n['turn_ns'][i] for i in selected)
            c_time = c['whole_ns'] if name == 'FULL' else sum(c['turn_ns'][i] for i in selected)
            n_tokens = sum(n['turn_tokens'][i] for i in selected)
            c_tokens = sum(c['turn_tokens'][i] for i in selected)
            pairs.append({'pair': pair, 'N_time_ns': n_time, 'C_time_ns': c_time,
                          'time_C_over_N': ratio(c_time, n_time), 'N_input_plus_output': n_tokens,
                          'C_input_plus_output': c_tokens, 'token_C_over_N': ratio(c_tokens, n_tokens)})
        time_median = statistics.median(Fraction(p['C_time_ns'], p['N_time_ns']) for p in pairs)
        token_median = statistics.median(Fraction(p['C_input_plus_output'], p['N_input_plus_output']) for p in pairs)
        n_time, c_time = sum(p['N_time_ns'] for p in pairs), sum(p['C_time_ns'] for p in pairs)
        n_tokens, c_tokens = sum(p['N_input_plus_output'] for p in pairs), sum(p['C_input_plus_output'] for p in pairs)
        views[name] = {'pairs': pairs, 'N_total_time_ns': n_time, 'C_total_time_ns': c_time,
                       'N_total_input_plus_output': n_tokens, 'C_total_input_plus_output': c_tokens,
                       'median_pair_time_C_over_N': ratio(time_median.numerator, time_median.denominator),
                       'median_pair_token_C_over_N': ratio(token_median.numerator, token_median.denominator),
                       'group_time_total_C_over_N': ratio(c_time, n_time),
                       'group_token_total_C_over_N': ratio(c_tokens, n_tokens)}
    return views


def write_report(ledger):
    views = ledger['views']
    full = views['FULL']
    time_saved = 100 * (1 - full['median_pair_time_C_over_N']['value'])
    tokens_saved = 100 * (1 - full['group_token_total_C_over_N']['value'])
    lines = ['# 连续消费002成本解封', '',
             '固定交付a798caf982e2d7eefe0bf52b739b9bef88526be4，根质量seal为' + SEAL_SHA + '。', '',
             'N使用原生execute_blender_code，C增加普通human_eye_scene_observe。两组均请求gpt-6.1-sol、medium、default及同一Pro接点。'
             '固定任务为全场2毫米三角表面距离查询，三轮依次为首次观察、未变重查和登记局部修改后重查。各集保留同一模型线程、脚本与宿主状态。', '',
             '双方各3/3完整episode、9/9完整正确且当前依据充分，质量门通过。完整episode配对C/N比值中位数为'
             f"{full['median_pair_time_C_over_N']['value']:.6f}，满足≤0.70。input＋output总量为N "
             f"{full['N_total_input_plus_output']:,}、C {full['C_total_input_plus_output']:,}，token门通过。", '',
             f'本固定任务三门均通过。按预登记的配对中位比，完整任务耗时减少约{time_saved:.1f}%。'
             f'按实际终值总量，input＋output减少约{tokens_saved:.1f}%。', '',
             '## 固定配对', '',
             '| 配对 | N完整秒 | C完整秒 | 时间C/N | N input＋output | C input＋output |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for pair in full['pairs']:
        lines.append(f"| {pair['pair']} | {pair['N_time_ns']/1e9:.6f} | {pair['C_time_ns']/1e9:.6f} | "
                     f"{pair['time_C_over_N']['value']:.6f} | {pair['N_input_plus_output']:,} | {pair['C_input_plus_output']:,} |")
    lines += ['', '## 三个独立视角', '',
              '| 区段 | N合计秒 | C合计秒 | 配对耗时比中位数 | N tokens | C tokens | token总量比 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name, view in views.items():
        lines.append(f"| {name} | {view['N_total_time_ns']/1e9:.6f} | {view['C_total_time_ns']/1e9:.6f} | "
                     f"{view['median_pair_time_C_over_N']['value']:.6f} | {view['N_total_input_plus_output']:,} | "
                     f"{view['C_total_input_plus_output']:,} | {view['group_token_total_C_over_N']['value']:.6f} |")
    repeated = views['REPEAT_EDIT']
    lines += ['', 'FULL包含启动、登记EDIT、关闭、归档和结果写闭。BASE与REPEAT_EDIT使用相应consumer完整时段，'
              '轮间管理间隙保留在FULL及独立账目。三对先各算C/N再取中位数，组总量比另存JSON。', '',
              'BASE的观察到的时间差最大。REPEAT＋EDIT三个配对均有时间收益，中位耗时减少约'
              f"{100*(1-repeated['median_pair_time_C_over_N']['value']):.1f}%，其input＋output总量减少约"
              f"{100*(1-repeated['group_token_total_C_over_N']['value']):.1f}%。暂留机制的独立因果贡献未单独识别。", '',
              '## 实际调用、数据和复用', '',
              '| 计量 | N | C |', '| --- | ---: | ---: |']
    for label, key in [('工具尝试', 'tool_attempts'), ('CLI可见工具正文UTF8字节', 'consumer_visible_tool_text_utf8_bytes'),
                       ('最终答案UTF8字节', 'final_answer_utf8_bytes'), ('业务host响应字节', 'host_business_response_bytes')]:
        lines.append(f"| {label} | {ledger['group_mechanism']['N'][key]:,} | {ledger['group_mechanism']['C'][key]:,} |")
    lines += ['', '工具错误和图像均为0，C原生工具回退为0。C三集各实测新kernel为112→0→10。REPEAT整份结果复用，'
              'EDIT复用104对并计算8个既有依赖变化及2个新增候选。局部数组首次驻留后继续复用，EDIT只更新1个world transform和8个顶点。'
              'N后续六轮复用原距离函数，同时读取当前求值网格、三角化并求解。', '',
              '工具正文、host采集包、最终答案与token各自列账。完整provider序列化输入字节及实际缓存RAM未测。'
              '已有accounted_bytes是预算载荷统计，进程RSS峰值保留其进程生命周期范围。', '',
              '## 时界、历史和未测项', '',
              'prompt至final内工具区间并集为N 15.494秒、C 5.985秒。模型/服务/传输未分解区间为N 564.692秒、C 306.582秒。'
              '推理、排队、网络及交付各自的份额未测。首次充分事实时刻保持unknown，最后工具完成至final等标记另列。', '',
              '旧001六首轮失败完整outer合计450.893秒，接口修复四次本地检查部分时界合计19.941秒，均独立保留。'
              '本次002必要离线检查原文本为1.632秒，仅计其runner部分范围。完整准备、修复、审核、打包、发布、协调及本次解封整理投入未完整计量。', '',
              '每轮仅取一个已独审范围的CLI终值，cached和reasoning分别保留在input和output中，真实重发历史input完整计入。'
              '费用、Pro扣账、provider请求/隐藏重试、十八份thin EXIT以及共享GUI前后状态仍未测。QA namespace副作用和准备期长路径修正记录保留。', '',
              '整理期修正了时间门字段读取和N1求值网格采集路径识别，初稿与修正记录保存在review和mechanism/attempts目录。', '',
              '## 收口', '',
              '结果限定于当前24对象、978三角面的三配对任务。按已定出口冻结当前指定阈值数值扫描能力，结束同题准备和格式调优。'
              '目标发现、选择补看和覆盖收口的主动扫视留待根设计下一阶段。', '',
              'LEDGER.json为逐集逐轮合账，INPUTS.json为输入摘要与历史来源约束，timing、usage和mechanism目录保存各自复算细节。'
              '全部新增模型、Blender、产品及API实验次数为0。', '',
              '```text', 'python -I -B -X utf8 verification/m4_surface_scan_continuous_consumption_002_cost/recalculate.py', '```', '']
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf8', newline='\n')


def main():
    run_builders()
    seal = read(HERE / 'inputs/QUALITY_SEAL.json')
    assert inputs[str((HERE / 'inputs/QUALITY_SEAL.json').resolve())] == SEAL_SHA
    pinned, runtime_roots = immutable_sources(seal)
    timing = read(HERE / 'timing/TIMING.json')
    usage = read(HERE / 'usage/USAGE.json')
    mechanism = read(HERE / 'mechanism/MECHANISM.json')
    for component in (timing, usage, mechanism):
        for name, sha in component['inputs_sha256'].items():
            path = str(Path(name).resolve())
            assert path not in inputs or inputs[path] == sha, path
            inputs[path] = sha
    run = read(SOURCE / 'RUN_RESULT.json')
    assert tuple(row['cell'] for row in run['records']) == ORDER
    views = build_views(raw_metrics(run))
    for name, view in views.items():
        assert view['median_pair_time_C_over_N']['value'] == timing['aggregates'][name]['median_pair_C_over_N']['value']
        assert view['N_total_input_plus_output'] == usage['segment_summaries'][name]['N_total_input_plus_output']
        assert view['C_total_input_plus_output'] == usage['segment_summaries'][name]['C_total_input_plus_output']
    quality_passed = (seal['quality']['primary_complete_correct'] == seal['quality']['current_state_basis_sufficient'] == 18
                      and seal['execution']['completed_episodes'] == 6 and usage['gates']['quality']['passed'])
    median = views['FULL']['median_pair_time_C_over_N']
    time_passed = Fraction(median['numerator'], median['denominator']) <= Fraction(7, 10)
    token_passed = views['FULL']['C_total_input_plus_output'] <= views['FULL']['N_total_input_plus_output']
    assert time_passed == timing['full_episode_time_gate_C_over_N_median_le_0_70']
    assert token_passed == usage['gates']['token']['passed']
    turns = []
    for row in timing['turns']:
        key = row['cell'], row['turn_index']
        usage_row = next(x for x in usage['rows'] if (x['cell'], x['turn_index']) == key)
        mechanism_row = next(x for x in mechanism['turns'] if (x['cell'], x['turn_index']) == key)
        turns.append({'cell': key[0], 'turn_index': key[1], 'timing': row, 'usage': usage_row, 'mechanism': mechanism_row})
    assert len(turns) == 18 and mechanism['passed']
    inputs[str(Path(__file__).resolve())] = digest(Path(__file__).read_bytes())
    bindings = bind_inputs(pinned, runtime_roots)
    ledger = {'schema': 'continuous_002_full_cost_ledger_v1', 'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002-COST',
              'source_delivery_commit': SOURCE_COMMIT, 'quality_seal_sha256': SEAL_SHA,
              'gates': {'quality': quality_passed, 'time': time_passed, 'token': token_passed,
                        'overall_fixed_task': quality_passed and time_passed and token_passed},
              'views': views, 'episodes': timing['episodes'], 'turns': turns,
              'group_usage': usage['group_aggregates'], 'group_mechanism': mechanism['group_summary'],
              'mechanism_episodes': [{key: value for key, value in row.items() if key != 'turns'} for row in mechanism['episodes']],
              'consumer_phase_totals_ns': timing['consumer_phase_totals_ns'],
              'shared_and_historical_costs': timing['shared_and_historical_costs'],
              'unknown_mechanism_fields': mechanism['unknown'],
              'time_scope': 'FULL uses complete outer FINAL_TIMING. BASE and REPEAT_EDIT use consumer interval sums; intervening administration remains separately in FULL.',
              'token_scope': 'One independently scoped CLI terminal per invocation. Input includes reported cached and repeated history. Output includes reported reasoning.',
              'limits': seal['limits'], 'first_sufficient_facts_time': None,
              'independent_retention_causal_effect': None, 'fees_subscription_debit_provider_requests': None,
              'decision': 'freeze_current_numeric_surface_scan_after_root_review' if quality_passed and time_passed and token_passed else 'one_evidence_supported_candidate_only',
              'new_model_Blender_product_provider_API_runs': 0}
    save(HERE / 'INPUTS.json', {'files': bindings, 'originals_verified_unchanged': True})
    save(HERE / 'LEDGER.json', ledger)
    write_report(ledger)
    save(HERE / 'RECALC_CHECK.json', {'passed': True, 'gates': ledger['gates'], 'episodes': 6, 'turns': 18,
                                      'input_files': len(bindings), 'new_model_Blender_product_provider_API_runs': 0,
                                      'ledger_sha256': digest((HERE / 'LEDGER.json').read_bytes())})
    print(json.dumps({'passed': True, 'gates': ledger['gates'], 'FULL_time_median_ratio': median['value'],
                      'N_tokens': views['FULL']['N_total_input_plus_output'], 'C_tokens': views['FULL']['C_total_input_plus_output']}))


if __name__ == '__main__':
    main()
