"""Independent read-only replay of recorded cost; never imports author code."""
import ast
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import statistics
import struct
import zipfile

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_001')
OUT = Path(__file__).resolve().parent
CHECKS = []
INPUTS = {}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def raw(path):
    path = Path(path)
    value = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(value), 'sha256': sha(value)}
    return value

def read(name):
    return json.loads(raw(AUTHOR / name))

def check(name, value, detail=None):
    CHECKS.append({'name': name, 'passed': bool(value), 'detail': detail})

def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf8')

def frac(value):
    value = Fraction(value)
    return {'numerator': value.numerator, 'denominator': value.denominator, 'decimal': float(value)}

def declared(record):
    return Fraction(record['numerator'], record['denominator'])

def median(values):
    ordered = sorted(values)
    n = len(ordered)
    return Fraction(ordered[n//2]) if n % 2 else (Fraction(ordered[n//2-1]) + Fraction(ordered[n//2])) / 2

def npy_header(blob):
    check('npy_magic', blob[:6] == b'\x93NUMPY')
    version = tuple(blob[6:8])
    size, offset = (struct.unpack('<H', blob[8:10])[0], 10) if version == (1, 0) else (struct.unpack('<I', blob[8:12])[0], 12)
    data = ast.literal_eval(blob[offset:offset+size].decode('latin1').strip())
    count = 1
    for dimension in data['shape']:
        count *= dimension
    payload = count * int(data['descr'][2:])
    check('npy_payload_size', len(blob) - offset - size == payload)
    return {'dtype': data['descr'], 'shape': data['shape'], 'payload_bytes': payload}

plan = read('benchmark/BENCHMARK_PLAN.json')
frozen = read('benchmark/FROZEN_RUNTIME.json')
runfile = read('benchmark/RUNS.json')
result = read('benchmark/RESULTS.json')
start = read('benchmark/BENCHMARK_STARTED.json')
prep = read('PREPARATION.json')
root = read('RESULTS.json')
deps = read('render/DEPENDENCIES.json')
raster = read('render/RASTER_RESULTS.json')
cameras = read('inputs/CAMERAS.json')
scene = read('inputs/SCENE_GEOMETRY_RATIONAL.json')
summary = result['summary']
rows = runfile['rows']
check('RUNS_RESULTS_exact_rows', rows == result['rows'])
check('no_stop_records', runfile['stop'] is None and result['stop'] is None)
check('40_rows', len(rows) == 40)
sequence = [(i, kind) for i in range(1, 21) for kind in (('reference', 'optimized') if i % 2 else ('optimized', 'reference'))]
check('raw_registered_order', [(r['pair'], r['variant']) for r in rows] == sequence)
check('plan_order', [(p['pair'], v) for p in plan['sequence'] for v in p['order']] == sequence)
check('plan_denominator', plan['formal_pair_count'] == 20 and plan['formal_run_count'] == 40)
check('plan_root_binding', plan['root_plan_sha256'] == sha(raw(Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_001_PLAN.md'))))
check('source_entry_count_166', len(frozen['inputs_sha256']) == 166)
check('138_product_sources', len(deps['installed_sources_sha256']) == deps['source_count'] == 138)
check('runtime_list_results_exact', frozen['inputs_sha256'] == result['inputs_sha256'])
freeze_sha = sha(raw(AUTHOR / 'benchmark/FROZEN_RUNTIME.json'))
for label, digest in [('start', start['freeze_sha256']), ('result', result['freeze_sha256']), ('prep', prep['runtime_freeze_sha256'])]:
    check('freeze_sha_' + label, digest == freeze_sha)
for path, digest in frozen['inputs_sha256'].items():
    check('runtime_sha:' + path, sha(raw(Path(path))) == digest)
for path, digest in deps['installed_sources_sha256'].items():
    check('installed_dependency_is_frozen:' + path, frozen['inputs_sha256'].get(path) == digest)
check('python_executable_recorded_sha', sha(raw(Path(root['runtime']['python_executable']))) == root['runtime']['python_executable_sha256'])
check('no_oracle_runtime_entry', not any('/oracle/' in p.replace('\\', '/') or 'READABILITY.json' in p for p in frozen['inputs_sha256']))
check('prepared_before_formal_record', prep['formal_runs_started'] is False)
check('batch_ordering', start['started_ns'] < result['batch_started_ns'] <= result['shared_setup']['started_ns'] < result['shared_setup']['closed_ns'] <= rows[0]['started_ns'])

outputs = {}
for variant in ('reference', 'optimized'):
    payload = raw(AUTHOR / 'benchmark' / ('OUTPUT_' + variant.upper() + '.json'))
    output = json.loads(payload)
    check(variant + '_canonical_encoding', payload == encode(output))
    outputs[variant] = {'raw': payload, 'json': output}
    check(variant + '_regions_6', len(output['semantic']['regions']) == 6)
    check(variant + '_pixel_rows_36', len(output['semantic']['pixel_evidence']) == 36)
    check(variant + '_two_deliveries', len(output['semantic']['steps']) == 2)
    check(variant + '_two_distinct_views', output['semantic']['state']['observed_views'] == ['SCENE', 'BACK'])
    check(variant + '_covered5_unresolved1', len(output['semantic']['state']['covered_roi_ids']) == 5 and len(output['semantic']['state']['unresolved_roi_ids']) == 1)
check('outputs_semantic_equal', outputs['reference']['json']['semantic'] == outputs['optimized']['json']['semantic'])
for i, row in enumerate(rows):
    label = str(i) + ':' + row['variant']
    output = outputs[row['variant']]
    check(label + ':completed', row['state'] == 'completed')
    check(label + ':integer_times', all(type(row[k]) is int for k in ('started_ns', 'closed_ns', 'elapsed_ns')))
    check(label + ':exact_delta', row['closed_ns'] - row['started_ns'] == row['elapsed_ns'] > 0)
    check(label + ':no_overlap', i == 0 or rows[i-1]['closed_ns'] <= row['started_ns'])
    check(label + ':output_bytes_sha', row['output_bytes'] == len(output['raw']) and row['output_sha256'] == sha(output['raw']))
    check(label + ':semantic_sha', row['semantic_sha256'] == sha(encode(output['json']['semantic'])))
    check(label + ':metrics_equal_stored_output', row['metrics'] == output['json']['metrics'])
    check(label + ':same_covered_work', row['metrics']['discovered_regions'] == 6 and row['metrics']['geometry_vertices'] == 200 and row['metrics']['triangles'] == 276 and row['metrics']['pixel_region_tests'] == 36 and row['metrics']['bitset_state_updates'] == 2)
    check(label + ':no_planning_render', row['metrics']['planning_render_calls'] == 0)
check('whole_integer_delta', result['batch_closed_before_result_publication_ns'] - result['batch_started_ns'] == result['whole_benchmark_through_analysis_ns'])
setup = result['shared_setup']
check('setup_integer_delta', setup['closed_ns'] - setup['started_ns'] == setup['elapsed_ns'] > 0)
check('batch_ends_after_samples', result['batch_closed_before_result_publication_ns'] > rows[-1]['closed_ns'])
check('no_planning_render_attempt', result['actual_planning_render_attempts'] == 0 and result['new_planning_raster_calls'] == 0)
check('all_same_semantic_sha', len(set(r['semantic_sha256'] for r in rows)) == 1)

arms = {v: [r for r in rows if r['variant'] == v] for v in ('reference', 'optimized')}
med = {v: median(r['elapsed_ns'] for r in arm) for v, arm in arms.items()}
pairs = []
for pair in range(1, 21):
    rr = next(r for r in arms['reference'] if r['pair'] == pair)
    oo = next(r for r in arms['optimized'] if r['pair'] == pair)
    ratio = Fraction(oo['elapsed_ns'], rr['elapsed_ns'])
    item = {'pair': pair, 'reference_ns': rr['elapsed_ns'], 'optimized_ns': oo['elapsed_ns'], 'difference_ns': oo['elapsed_ns']-rr['elapsed_ns'], 'ratio': frac(ratio)}
    pairs.append(item)
    recorded = summary['pairs'][pair-1]
    check('pair_record_' + str(pair), recorded['pair'] == pair and recorded['reference_ns'] == rr['elapsed_ns'] and recorded['optimized_ns'] == oo['elapsed_ns'] and declared(recorded['optimized_over_reference']) == ratio and recorded['optimized_minus_reference_ns'] == item['difference_ns'])
ratio_medians = med['optimized'] / med['reference']
median_ratios = median(Fraction(p['optimized_ns'], p['reference_ns']) for p in pairs)
clips = {v: sum(r['metrics']['exact_clips'] for r in arm) for v, arm in arms.items()}
clip_reduction = 1 - Fraction(clips['optimized'], clips['reference'])
for key, value in [('reference_median_ns', med['reference']), ('optimized_median_ns', med['optimized']), ('ratio_of_medians', ratio_medians), ('median_pair_ratio', median_ratios), ('exact_clip_reduction', clip_reduction)]:
    check('summary_' + key, declared(summary[key]) == value and summary[key]['value'] == float(value))
check('summary_exact_clips', summary['reference_exact_clip_sum'] == clips['reference'] and summary['optimized_exact_clip_sum'] == clips['optimized'])
for variant in arms:
    check(variant + '_range', summary[variant+'_range_ns'] == [min(r['elapsed_ns'] for r in arms[variant]), max(r['elapsed_ns'] for r in arms[variant])])
check('engineering_gate_recomputed', summary['engineering_gate'] is True and med['optimized'] <= med['reference'] and clip_reduction >= Fraction(3, 10))
check('all_pairs_faster', all(p['difference_ns'] < 0 for p in pairs))
check('root_summary_exact', root['benchmark_summary'] == summary)
check('complete_denominator_summary', summary['completed_runs'] == 40 and summary['failed_runs'] == 0 and summary['not_run'] == 0 and summary['planned_runs'] == 40 and summary['planned_pairs'] == 20)
check('raster_copy_exact', result['preexisting_six_image_generation_cost'] == raster)

order = ['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']
check('six_images_order', [v['view'] for v in raster['views']] == order and raster['render_calls'] == 6)
views = []
for record, pose in zip(raster['views'], cameras['views']):
    name = record['view']
    metadata = read('render/' + name + '.json')
    check(name + '_metadata_equals_full', metadata == record)
    check(name + '_pose_equal', metadata['pose'] == pose)
    png = raw(AUTHOR / 'render' / record['PNG'])
    npz = raw(AUTHOR / 'render' / record['owner_depth_RGB_arrays'])
    check(name + '_png_bytes_sha', len(png) == record['PNG_bytes'] and sha(png) == record['PNG_sha256'])
    check(name + '_PNG_512_rgb', png[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',png[16:24]) == (512,512) and png[24:26] == bytes((8,2)))
    check(name + '_npz_bytes_sha', len(npz) == record['compressed_array_file_bytes'] and sha(npz) == record['arrays_sha256'])
    with zipfile.ZipFile(io.BytesIO(npz)) as zf:
        check(name + '_3arrays', sorted(zf.namelist()) == ['color.npy','depth.npy','owners.npy'])
        arrays = {f[:-4]:npy_header(zf.read(f)) for f in zf.namelist()}
    check(name + '_nbytes_recomputed', sum(a['payload_bytes'] for a in arrays.values()) == record['array_payload_bytes'] == 3932160)
    check(name + '_array_types', arrays['color']['dtype'] == '|u1' and arrays['color']['shape'] == (512,512,3) and arrays['depth']['dtype'] == '<f8' and arrays['owners']['dtype'] == '<i4' and arrays['depth']['shape'] == arrays['owners']['shape'] == (512,512))
    check(name + '_render_duration_order', 0 < record['raster_elapsed_ns'] < record['render_and_publish_elapsed_ns'])
    check(name + '_all_meshes', record['all_object_count'] == len(scene['objects']) == 28 and record['triangle_count'] == sum(len(o['triangles']) for o in scene['objects']) == 276)
    views.append({'view':name, 'png_bytes':len(png), 'npz_bytes':len(npz), 'array_bytes':record['array_payload_bytes'], 'raster_ns':record['raster_elapsed_ns'], 'render_and_encode_window_ns':record['render_and_publish_elapsed_ns']})
check('six_image_byte_totals', sum(v['png_bytes'] for v in views) == raster['PNG_output_bytes'] and sum(v['npz_bytes'] for v in views) == raster['compressed_array_output_bytes'] and sum(v['array_bytes'] for v in views) == raster['array_payload_bytes'])
check('array_shared_matches', raster['array_payload_bytes'] == setup['common_raster_array_payload_bytes'])
check('raster_includes_recorded_subwindows', raster['total_elapsed_ns'] >= sum(v['render_and_encode_window_ns'] for v in views))
check('no_new_consumers', raster['Blender_runs'] == raster['model_calls'] == raster['API_calls'] == result['new_model_provider_Blender_API_runs'] == 0)

runs_total = sum(r['elapsed_ns'] for r in rows)
residual = result['whole_benchmark_through_analysis_ns'] - runs_total - setup['elapsed_ns']
intervals = [{'where':'setup_close_to_first_start','elapsed_ns':rows[0]['started_ns']-setup['closed_ns']}]
intervals += [{'where':'between_runs','after_index':i,'elapsed_ns':rows[i+1]['started_ns']-rows[i]['closed_ns']} for i in range(39)]
intervals += [{'where':'last_close_to_batch_close','elapsed_ns':result['batch_closed_before_result_publication_ns']-rows[-1]['closed_ns']}, {'where':'batch_start_to_setup','elapsed_ns':setup['started_ns']-result['batch_started_ns']}]
check('residual_partition_exact', sum(x['elapsed_ns'] for x in intervals) == residual and all(x['elapsed_ns'] >= 0 for x in intervals))
common = raster['total_elapsed_ns'] + setup['elapsed_ns']
composition = {v: med[v] + common for v in med}
findings = {
    'status':'cost_replay_complete', 'checks':len(CHECKS), 'failed':sum(not c['passed'] for c in CHECKS),
    'source_files':len(frozen['inputs_sha256']), 'rows':40, 'pairs':20, 'source_scope':'166 listed files, including 138 product source bytes, read and hashed; NumPy/Pillow versions only, Python executable SHA separately verified; no execution replay.',
    'metrics':{'medians_ns':{v:frac(t) for v,t in med.items()},'ratio_of_medians':frac(ratio_medians),'median_pair_ratio':frac(median_ratios),'clip_sum':clips,'clip_reduction':frac(clip_reduction), 'pairs':pairs,
               'all_pairs_optimized_faster':all(p['difference_ns'] < 0 for p in pairs), 'semantic_sha256':rows[0]['semantic_sha256'], 'output_bytes':{v:len(o['raw']) for v,o in outputs.items()}},
    'cost_partition':{'setup_ns':setup['elapsed_ns'],'runs_ns':runs_total,'runs_by_arm_ns':{v:sum(r['elapsed_ns']for r in arm)for v,arm in arms.items()},'integrity_io_analysis_remainder_ns':residual,'whole_benchmark_through_analysis_ns':result['whole_benchmark_through_analysis_ns'],'recorded_image_preparation_ns':raster['total_elapsed_ns'],'sum_disjoint_recorded_preparation_and_batch_windows_ns':result['whole_benchmark_through_analysis_ns']+raster['total_elapsed_ns'],'gaps':intervals,'views':views,'PNG_bytes':raster['PNG_output_bytes'],'compressed_arrays_bytes':raster['compressed_array_output_bytes'],'array_payload_bytes':raster['array_payload_bytes']},
    'illustrative_additive_budget_not_measured_episode':{'assumption':'Charge the separately recorded six-image preparation and shared setup once to each arm median. No predicted two-image generation saving; no full cold execution measured. Missing startup/integrity/IO remains.', 'common_ns':common,'combined_ns':{v:frac(t)for v,t in composition.items()},'ratio':frac(composition['optimized']/composition['reference']),'reduction':frac(1-composition['optimized']/composition['reference'])},
    'limits':['No new algorithm execution, benchmark, renderer, Blender, model or provider runs in this review.', 'Source file hashes do not independently prove historical executed bytecode/binary package identity; paired runs used same documented process.', '166 list does not include NumPy/Pillow binary hashes; only their recorded versions. Not a full runtime binary seal.', 'Six image generation charged. Two selected local PNG receipts are not only two generated images and not evidence of model delivery/consumption.', 'Only one retained payload per variant; 40 records contain matching payload and semantic hashes, not 40 separately retained payload bodies.', 'Per-view render_and_publish_elapsed stops before receipt hashing and metadata save; total six-view preparation includes these steps, excluding final RASTER_RESULTS self-publication.', 'Total benchmark stops before final RESULTS publication; interpreter startup before scopes, all imports before render.prepare, Python/Fraction/index heap, RSS and final self-receipt publication unmeasured.', 'No measured complete user task/native baseline/token/cash fee, so 91.52 percent planning reduction cannot be called product end-to-end benefit.', 'No full performance re-run or statistical extrapolation; same-process 20-pair descriptive evidence only.']}
OUT.mkdir(parents=True,exist_ok=True)
for name,obj in [('CHECKS.json',CHECKS),('INPUTS.json',INPUTS),('RESULTS.json',findings)]:
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(CHECKS),'failed':findings['failed'],'failed_items':[c for c in CHECKS if not c['passed']],'cost_partition':{k:v for k,v in findings['cost_partition'].items()if k not in ['gaps','views']},'illustrative':findings['illustrative_additive_budget_not_measured_episode']},ensure_ascii=False))
if findings['failed']:
    raise SystemExit(1)
