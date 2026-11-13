"""Read-only arithmetic and byte-binding audit of the one completed benchmark."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def encode(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, allow_nan=False) + '\n').encode('utf8')


def record(value):
    return {'numerator': value.numerator, 'denominator': value.denominator, 'value': float(value)}


def median(values):
    ordered = sorted(values)
    assert len(ordered) == 20
    return (Fraction(ordered[9]) + Fraction(ordered[10])) / 2


def main():
    sources = {}
    checks = []

    def raw(path):
        path = Path(path).resolve()
        value = path.read_bytes()
        digest = hashlib.sha256(value).hexdigest()
        if str(path) in sources:
            assert sources[str(path)] == digest, 'read_source_changed'
        sources[str(path)] = digest
        return value

    def read(path):
        return json.loads(raw(path))

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        assert passed, name

    data = read(HERE / 'RESULTS.json')
    progress = read(HERE / 'RUNS.json')
    frozen_raw = raw(HERE / 'FROZEN_RUNTIME.json')
    frozen = json.loads(frozen_raw)
    started = read(HERE / 'BENCHMARK_STARTED.json')
    protocol = read(HERE / 'BENCHMARK_PLAN.json')
    check('freeze_digest', data['freeze_sha256'] == started['freeze_sha256'] == hashlib.sha256(frozen_raw).hexdigest())
    check('recorded_frozen_input_set', data['inputs_sha256'] == frozen['inputs_sha256'])
    for number, (path, wanted) in enumerate(sorted(frozen['inputs_sha256'].items()), 1):
        check('frozen_source_' + str(number), hashlib.sha256(raw(path)).hexdigest() == wanted)
    expected = [(pair, variant) for pair in range(1, 21)
                for variant in (('reference', 'optimized') if pair % 2 else ('optimized', 'reference'))]
    plan_order = [(row['pair'], variant) for row in protocol['sequence'] for variant in row['order']]
    rows = data['rows']
    check('registered_schedule', plan_order == expected)
    check('one_full_twenty_pair_batch', len(rows) == 40 and started['pairs'] == 20 and started['runs'] == 40)
    check('raw_schedule', [(row['pair'], row['variant']) for row in rows] == expected)
    check('progress_records_equal_terminal', progress['rows'] == rows)
    check('no_stop', progress['stop'] is None and data['stop'] is None)
    sample = {variant: read(HERE / ('OUTPUT_' + variant.upper() + '.json')) for variant in ('reference', 'optimized')}
    check('two_output_semantics_equal', sample['reference']['semantic'] == sample['optimized']['semantic'])
    semantic = sample['reference']['semantic']
    semantic_digest = hashlib.sha256(encode(semantic)).hexdigest()
    previous = data['shared_setup']['closed_ns']
    raw_times = []
    for number, row in enumerate(rows, 1):
        check('completed_' + str(number), row['state'] == 'completed' and not row.get('error'))
        start, end, elapsed = row['started_ns'], row['closed_ns'], row['elapsed_ns']
        check('integer_raw_clock_' + str(number), all(type(value) is int for value in (start, end, elapsed)))
        check('raw_delta_' + str(number), elapsed == end - start > 0)
        check('serial_intervals_' + str(number), previous <= start <= end <= data['batch_closed_before_result_publication_ns'])
        previous = end
        check('semantic_digest_' + str(number), row['semantic_sha256'] == semantic_digest)
        reconstructed = encode({'semantic': semantic, 'metrics': row['metrics']})
        check('encoded_output_' + str(number), len(reconstructed) == row['output_bytes']
              and hashlib.sha256(reconstructed).hexdigest() == row['output_sha256'])
        check('same_variant_metrics_' + str(number), row['metrics'] == sample[row['variant']]['metrics'])
        check('no_run_render_' + str(number), row['metrics']['planning_render_calls'] == 0)
        raw_times.append({'pair': row['pair'], 'variant': row['variant'], 'started_ns': start,
                          'closed_ns': end, 'elapsed_ns': elapsed})
    for variant in ('reference', 'optimized'):
        path = HERE / ('OUTPUT_' + variant.upper() + '.json')
        first = next(row for row in rows if row['variant'] == variant)
        check(variant + '_raw_output_bytes', len(raw(path)) == first['output_bytes']
              and hashlib.sha256(raw(path)).hexdigest() == first['output_sha256'])
        development = read(BATCH / 'development' / (variant + '.json'))
        qualified = read(BATCH / 'results' / (variant + '.json'))
        for key in ('scene_identity', 'candidate_identity', 'view_masks', 'classifications'):
            check(variant + '_development_' + key, semantic[key] == development[key] == qualified[key])
        ids = [roi['roi_id'] for roi in semantic['regions']]
        check(variant + '_region_ids', ids == development['roi_ids'] == qualified['roi_ids'])
        check(variant + '_region_normals', {roi['roi_id']: roi['normal'] for roi in semantic['regions']}
              == {roi['roi_id']: roi['normal'] for roi in development['regions']})
        check(variant + '_state_trace', semantic['steps'] == [step['update'] for step in qualified['actual_observation_trace']])
        check(variant + '_state_summary', semantic['state'] == qualified['coverage'])
        for counter, value in development['stats'].items():
            check(variant + '_counter_' + counter, sample[variant]['metrics'][counter] == value == qualified['stats'][counter])
        for step in qualified['actual_observation_trace']:
            image = step['actual_image_receipt']
            image_raw = raw(image['image_path'])
            check(variant + '_bound_image_' + image['view_name'], image['actual_image_delivered'] is True
                  and image_raw.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(image_raw).hexdigest() == image['image_sha256'])
    scene = read(BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json')
    dev_reference = read(BATCH / 'development/reference.json')
    for roi in semantic['regions']:
        identity = next(row for row in dev_reference['regions'] if row['roi_id'] == roi['roi_id'])
        points = scene['objects'][identity['object_index']]['vertices']
        check('full_region_vertices_' + roi['roi_id'],
              {tuple(Fraction(value) for value in point) for point in roi['vertices']}
              == {tuple(Fraction(value) for value in point) for point in points})
    reference = [row for row in rows if row['variant'] == 'reference']
    optimized = [row for row in rows if row['variant'] == 'optimized']
    ref_median = median([row['elapsed_ns'] for row in reference])
    opt_median = median([row['elapsed_ns'] for row in optimized])
    pairs = []
    for pair in range(1, 21):
        ref = next(row for row in reference if row['pair'] == pair)
        opt = next(row for row in optimized if row['pair'] == pair)
        value = Fraction(opt['elapsed_ns'], ref['elapsed_ns'])
        pairs.append({'pair': pair, 'reference_ns': ref['elapsed_ns'], 'optimized_ns': opt['elapsed_ns'],
                      'optimized_minus_reference_ns': opt['elapsed_ns'] - ref['elapsed_ns'],
                      'optimized_over_reference': record(value)})
    ref_clips = sum(row['metrics']['exact_clips'] for row in reference)
    opt_clips = sum(row['metrics']['exact_clips'] for row in optimized)
    reduction = Fraction(ref_clips - opt_clips, ref_clips)
    resolution = math.ceil(data['clock']['resolution_seconds'] * 10**9)
    resolved = abs(ref_median - opt_median) > 2 * resolution
    primary_ratio = opt_median / ref_median
    pair_median = median([Fraction(row['optimized_ns'], row['reference_ns']) for row in pairs])
    observed_nonworse = opt_median <= ref_median
    clip_pass = reduction >= Fraction(3, 10)
    independent = {'reference_median_ns': record(ref_median), 'optimized_median_ns': record(opt_median),
                   'ratio_of_medians': record(primary_ratio), 'median_pair_ratio': record(pair_median),
                   'reference_exact_clip_sum': ref_clips, 'optimized_exact_clip_sum': opt_clips,
                   'exact_clip_reduction': record(reduction), 'all_twenty_pairs_optimized_faster': all(row['optimized_ns'] < row['reference_ns'] for row in pairs),
                   'clock_resolution_ns': resolution, 'resolved_beyond_clock_quantization': resolved,
                   'observed_median_not_worse': observed_nonworse, 'clip_gate_at_least_30_percent': clip_pass,
                   'engineering_gate': observed_nonworse and resolved and clip_pass}
    for key in ('reference_median_ns', 'optimized_median_ns', 'ratio_of_medians', 'median_pair_ratio',
                'reference_exact_clip_sum', 'optimized_exact_clip_sum', 'exact_clip_reduction',
                'observed_median_not_worse', 'clip_gate_at_least_30_percent', 'engineering_gate'):
        check('author_summary_' + key, data['summary'][key] == independent[key])
    clock_span = data['batch_closed_before_result_publication_ns'] - data['batch_started_ns']
    check('whole_batch_delta', clock_span == data['whole_benchmark_through_analysis_ns'])
    setup = data['shared_setup']
    check('setup_delta', setup['elapsed_ns'] == setup['closed_ns'] - setup['started_ns'])
    run_sum = sum(row['elapsed_ns'] for row in rows)
    overhead = clock_span - setup['elapsed_ns'] - run_sum
    check('setup_and_run_intervals_fit_total', data['batch_started_ns'] <= setup['started_ns'] <= setup['closed_ns'] <= rows[0]['started_ns'] and overhead >= 0)
    renders = read(BATCH / 'render/RASTER_RESULTS.json')
    check('six_actual_prepared_renders_retained', renders['render_calls'] == len(renders['views']) == 6)
    check('same_recorded_image_preparation', data['preexisting_six_image_generation_cost'] == renders)
    check('two_selected_full_images_reused', semantic['state']['observed_views'] == ['SCENE', 'BACK'])
    check('no_benchmark_render_attempts', data['actual_planning_render_attempts'] == data['new_planning_raster_calls'] == 0)
    qualified_summary = read(BATCH / 'results/QUALIFICATION.json')
    check('qualified_coverage_counts', len(semantic['state']['covered_roi_ids']) == qualified_summary['delivered_covered'] == 5
          and len(semantic['state']['candidate_pool_uncovered_roi_ids']) == qualified_summary['candidate_pool_uncovered'] == 1)
    check('frozen_core_matches_qualification', qualified_summary['source_sha256'] == hashlib.sha256(raw(BATCH / 'coverage.py')).hexdigest())
    raw(Path(__file__))
    output = {'passed': all(row['passed'] for row in checks), 'check_count': len(checks), 'checks': checks,
              'preparation_commit': '0b6ad519', 'actual_pairs': 20, 'actual_runs': 40, 'raw_times': raw_times,
              'independent': independent, 'pairs': pairs,
              'cost_scope': {'timed_planning_sum_ns': run_sum, 'shared_setup_ns': setup['elapsed_ns'],
                  'batch_through_analysis_ns': clock_span, 'integrity_progress_and_analysis_residual_ns': overhead,
                  'actual_prepared_images': 6, 'selected_reused_images': 2, 'new_benchmark_renders': 0,
                  'reported_six_image_prepare_elapsed_ns': renders['total_elapsed_ns'],
                  'prepared_PNG_bytes': renders['PNG_output_bytes'], 'prepared_npz_bytes': renders['compressed_array_output_bytes'],
                  'common_raster_array_payload_bytes': renders['array_payload_bytes'],
                  'fresh_mesh_array_payload_bytes_per_run': sample['reference']['metrics']['fresh_mesh_array_payload_bytes'],
                  'RSS_and_Fraction_index_object_memory': None},
              'inputs_sha256': sources, 'new_algorithm_planning_raster_model_Blender_API_calls': 0,
              'reviewer_scope': 'Benchmark implementation worker separately recomputed arithmetic and bytes. No benchmark/helper/oracle imports, algorithm evaluation or performance timing occurred in this recheck.',
              'limits': ['Fixed one-layout engineering result with 20 same-process alternating pairs.',
                         'Clock criterion covers quantization. General statistical or model-consumption benefit remains unmeasured.',
                         'All six prepared rasters remain charged. Two selected frame deliveries reuse that pool.',
                         'Initial freeze/source validation and final benchmark result publication lack complete recorded intervals.']}
    (HERE / 'INDEPENDENT_REVIEW.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    text = '# 二十配对只读复算\n\n' + str(len(checks)) + '项检查全部通过。仅读取既有原件、输出和源码摘要，未调用算法、raster或性能计时。\n\n'
    text += '40/40原始时钟差值、交替顺序、输出字节/SHA及166份冻结源均对应。最终ROI、36分类、SCENE→BACK状态链与已核development/results一致。\n\n'
    text += '参考完整规划中位数为' + str(ref_median) + ' ns，优化为' + str(opt_median) + ' ns。中位数之比' + format(float(primary_ratio), '.9f') + '，配对比值中位数' + format(float(pair_median), '.9f') + '。二十对均观察到优化较快。\n\n'
    text += '精确裁剪总调用' + str(ref_clips) + '→' + str(opt_clips) + '，减少' + format(float(reduction * 100), '.6f') + '%，满足至少30%工作量减少与完整规划中位不劣工程门。\n\n'
    text += '六张实际准备图继续全额计入原准备成本。实际交付选择SCENE、BACK两张已备完整PNG，覆盖5目标，候选池未覆盖1。40次规划新增render为0。数组载荷与RSS口径保持分离。\n\n'
    text += '该复算由benchmark实施worker另写算术与字节核对程序，结果范围为固定布局的工程资格。广域统计结论及模型收益仍待后续验证。\n'
    (HERE / 'INDEPENDENT_REVIEW.md').write_text(text, encoding='utf8', newline='\n')
    print(json.dumps({'passed': output['passed'], 'checks': len(checks), 'independent': independent}, ensure_ascii=False))


if __name__ == '__main__':
    main()
