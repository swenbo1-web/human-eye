"""Independent offline cost/denominator audit. No product imports or execution."""
import ast
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = ROOT / 'verification/m4_active_observation_core_integration_001'
OUT = Path(__file__).resolve().parent
checks = []
inputs = {}

def read_bytes(p):
    p = Path(p)
    b = p.read_bytes()
    inputs[str(p)] = hashlib.sha256(b).hexdigest()
    return b

def sha(p):
    return hashlib.sha256(read_bytes(p)).hexdigest()

def read(p):
    return json.loads(read_bytes(p))

def ck(name, condition, detail=None):
    checks.append({'check': name, 'passed': bool(condition), 'detail': detail})

def eq(name, actual, expected):
    ck(name, actual == expected, None if actual == expected else {'actual': actual, 'expected': expected})

protocol = read(H/'BENCHMARK_PROTOCOL.json')
worker = read_bytes(H/'isolated_worker_r2.py').decode()
old_worker = read_bytes(H/'isolated_worker.py').decode()
tree = ast.parse(worker)
functions = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
benchmark_code = ast.get_source_segment(worker, functions['benchmark'])
old_benchmark = next(x for x in ast.parse(old_worker).body if isinstance(x, ast.FunctionDef) and x.name == 'benchmark')
eq('benchmark_unchanged_by_install_repair', ast.dump(functions['benchmark']), ast.dump(old_benchmark))
ck('timer_before_read_hash_json_and_both_calls', benchmark_code.index('began = time.perf_counter_ns()') < benchmark_code.index('scene_raw =') < benchmark_code.index('scene_sha, camera_sha =') < benchmark_code.index('scene, cameras = json.loads') < benchmark_code.index('old.build_index') < benchmark_code.index('core.prepare_scene') < benchmark_code.index('closed = time.perf_counter_ns()'))
ck('result_serialization_outside_timer', benchmark_code.index('closed = time.perf_counter_ns()') < benchmark_code.index("'index': index_row(index)") < benchmark_code.index("save(output / 'PROGRESS.json'"))
ck('old_import_outside_timer', benchmark_code.index('spec.loader.exec_module(old)') < benchmark_code.index('for pair, order in enumerate'))
ck('single_benchmark_exclusive_start', ".open('x', encoding='utf8')" in benchmark_code and "'run/BENCHMARK_STARTED.json'" in benchmark_code)
ck('old_selected_candidate', "discovery_variant='candidate'" in benchmark_code)
ck('new_default_core', 'core.prepare_scene(scene, cameras).index' in benchmark_code)
observe_code = ast.get_source_segment(worker, functions['observe'])
reserve_code = ast.get_source_segment(worker, functions['reserve_render'])
ck('render_reserved_before_call', observe_code.index('reserve_render(') < observe_code.index('images.render_view('))
ck('render_intents_exclusive_no_refund', "path.open('x'" in reserve_code and 'range(1, 9)' in reserve_code and 'os.fsync' in reserve_code and 'unlink' not in worker)
ck('progress_keeps_attempt_before_success', observe_code.index('frames.append(pending)') < observe_code.index('images.render_view(') < observe_code.index("pending.update(status='completed'"))
main_code = ast.get_source_segment(worker, functions['main'])
ck('quality_evidence_hashed_before_benchmark', main_code.index("digest(path.read_bytes()) == wanted") < main_code.index("result['benchmark'] = benchmark"))
ck('no_model_or_host_client_imports', not any(word in worker.lower() for word in ['subprocess.', 'openai.', 'genai.', 'bpy.', 'requests.']))

archive = read(H/'EXTERNAL_ARCHIVE.json')
archive_map = {str(Path(r['source'])): ROOT/r['archive'] for r in archive['files']}
for row in archive['files']:
    p = ROOT/row['archive']
    eq('archive_hash:'+row['archive'], sha(p), row['sha256'])
    eq('original_archive_equal:'+row['archive'], read_bytes(p), read_bytes(row['source']))
eq('archive_files_count', len(archive['files']), 39)

names = ['source_check', 'source_check_r2', 'qualify_r2', 'observe_r2', 'benchmark_r2']
eq('exact_parent_receipt_names', sorted(p.stem.removesuffix('_PROCESS') for p in (H/'runs').glob('*PROCESS.json')), sorted(names))
processes = []
results = {}
freeze_sha = sha(H/'FROZEN_R2.json')
binding_sha = sha(H/'build/RUN_BINDING_R2.json')
for name in names:
    p = read(H/'runs'/f'{name}_PROCESS.json')
    r = read(H/'external/run'/name/'RESULTS.json')
    results[name] = r
    eq(name+':parent_elapsed', p['elapsed_ns'], p['closed_after_process_exit_ns']-p['started_ns'])
    ck(name+':worker_inside_parent', p['started_ns'] < r['started_ns'] < r['closed_before_publication_ns'] < p['closed_after_process_exit_ns'])
    eq(name+':result_original_equal', read_bytes(p['result_path']), read_bytes(H/'external/run'/name/'RESULTS.json'))
    for suffix, key in [('STDOUT.txt','stdout_sha256'),('STDERR.txt','stderr_sha256')]:
        eq(name+':'+suffix, sha(H/'runs'/f'{name}_{suffix}'), p[key])
    eq(name+':correct_exit', p['exit_code'], 1 if name == 'source_check' else 0)
    eq(name+':correct_status', r['passed'], name != 'source_check')
    eq(name+':binding_parent_child', p['binding_sha256'], r['binding_sha256'])
    eq(name+':no_model_calls', r['new_model_CLI_Blender_provider_calls'], 0)
    if name != 'source_check':
        eq(name+':binding_same', r['binding_sha256'], binding_sha)
        eq(name+':worker_same', r['worker_source_sha256'], sha(H/'isolated_worker_r2.py'))
        eq(name+':interpreter', Path(r['environment']['python']), Path('D:/he_core_001/venv/Scripts/python.exe'))
        eq(name+':cwd', Path(r['environment']['cwd']), Path('D:/he_core_001/run'))
        if name != 'benchmark_r2': eq(name+':freeze_direct', p['freeze_r2_sha256'], freeze_sha)
    access_rows = [json.loads(line) for line in read_bytes(H/'external/run'/name/'ACCESS.jsonl').splitlines()]
    eq(name+':all_reads_allowed', sum(not x['allowed'] for x in access_rows), 0)
    eq(name+':access_denied', r['access']['denied'], [])
    eq(name+':access_count', len(access_rows), r['access']['reads']+r['access']['writes'])
    for row in access_rows:
        if '/baseline/' in row['path'].replace('\\','/'):
            ck(name+':baseline_only_at_old_import', name == 'benchmark_r2' and row['stage'] == 'old_baseline_import')
    processes.append({'name':name,'start':p['started_ns'],'end':p['closed_after_process_exit_ns'],'elapsed_ns':p['elapsed_ns'],'exit_code':p['exit_code']})
eq('known_setup_failure_message', results['source_check']['error']['message'], 'verified_source_preloaded_module:numpy.version')
ck('failure_before_setup_complete_or_algorithm', 'setup_closed_ns' not in results['source_check'] and not any(k in results['source_check'] for k in ['qualification','observations','benchmark']))
eq('failure_preserved', read_bytes(H/'failures/source_check_01/RESULTS.json'), read_bytes(H/'external/run/source_check/RESULTS.json'))
for left,right in zip(processes,processes[1:]): ck('workers_nonoverlap:'+right['name'], left['end'] < right['start'])
eq('unique_worker_pids', len({x['pid'] for x in results.values()}), 5)

gate_path = H/'external/run/QUALITY_GATE_R2.json'
gate = read(gate_path)
parent = read(H/'runs/benchmark_r2_PROCESS.json')
eq('benchmark_indirect_gate_hash', parent['quality_gate_sha256'], sha(gate_path))
eq('gate_binding', gate['binding_sha256'], binding_sha)
root_gate = read(H/'runs/PRE_BENCHMARK_QUALITY_GATE.json')
eq('gate_root_pixel_hash', gate['root_pixel_quality_gate_sha256'], sha(H/'runs/PRE_BENCHMARK_QUALITY_GATE.json'))
eq('root_pixel_gate_freeze', root_gate['source_freeze_r2_sha256'], freeze_sha)
ck('pixel_gate_precedes_benchmark', root_gate['closed_ns'] < parent['started_ns'])
eq('gate_exact_three_previous_phases', {Path(k).parent.name for k in gate['evidence_sha256']}, {'source_check_r2','qualify_r2','observe_r2'})
for p,want in gate['evidence_sha256'].items(): eq('gate_evidence:'+Path(p).parent.name, sha(archive_map[str(Path(p))]), want)

bench = read(H/'external/run/benchmark_r2/BENCHMARK.json')
eq('benchmark_result_equal', bench, results['benchmark_r2']['benchmark'])
eq('benchmark_last_progress_equal', read(H/'external/run/benchmark_r2/PROGRESS.json'), bench['rows'])
eq('sole_start_marker', read(H/'external/run/BENCHMARK_STARTED.json')['pairs'], protocol['benchmark']['pairs'])
eq('trial_count',len(bench['rows']),10)
eq('pair_count',len(bench['pairs']),5)
expected_order = [(i+1,arm) for i,pair in enumerate(protocol['benchmark']['pairs']) for arm in pair]
eq('actual_alternating_order',[(r['pair'],r['arm']) for r in bench['rows']],expected_order)
manifest = read(H/'INPUTS.json')
scene_sha = sha(H/manifest['scenes']['grid16_permuted_alternating']['file'])
camera_sha = sha(H/manifest['cameras']['normal']['file'])
for n,r in enumerate(bench['rows']):
    eq(f'trial{n}:clock',r['elapsed_ns'],r['closed_ns']-r['started_ns'])
    eq(f'trial{n}:scene',r['scene_sha256'],scene_sha)
    eq(f'trial{n}:cameras',r['camera_sha256'],camera_sha)
    ck(f'trial{n}:within_worker',results['benchmark_r2']['setup_closed_ns']<r['started_ns']<r['closed_ns']<results['benchmark_r2']['closed_before_publication_ns'])
    if n: ck(f'trial{n}:sequential',bench['rows'][n-1]['closed_ns']<r['started_ns'])
pairs=[]
for number in range(1,6):
    rows={r['arm']:r for r in bench['rows'] if r['pair']==number}
    eq(f'pair{number}:equal_complete_index',rows['old']['index'],rows['new']['index'])
    value={'pair':number,'old_ns':rows['old']['elapsed_ns'],'new_ns':rows['new']['elapsed_ns'],'new_over_old':rows['new']['elapsed_ns']/rows['old']['elapsed_ns']}
    eq(f'pair{number}:aggregate_row',bench['pairs'][number-1],value)
    pairs.append(value)
median=statistics.median(x['new_over_old'] for x in pairs)
old_total=sum(x['old_ns'] for x in pairs);new_total=sum(x['new_ns'] for x in pairs)
eq('median_from_all_five',median,bench['paired_ratio_median'])
eq('old_total_from_all_five',old_total,bench['old_total_ns'])
eq('new_total_from_all_five',new_total,bench['new_total_ns'])
selection=read(H/'SELECTION.json')
eq('selection_median',selection['paired_new_over_old_median'],median)
eq('selection_total',selection['new_total_ns'],new_total)
eq('regression_retained',[p['pair'] for p in pairs if p['new_over_old']>1],selection['regression_pairs'])
eq('engineering_rule',selection['engineering_rule_passed'],median<=1 and new_total<=old_total)
eq('no_benchmark_rasters',bench['new_renders'],0)

source_q=read(H/'runs/source_qualification/QUALIFICATION.json')
installed_q=read(H/'external/run/qualify_r2/QUALIFICATION.json')
for name,q in [('source',source_q),('installed',installed_q)]:
    eq(name+':representation_count',len(q['representations']),10)
    eq(name+':representation_keys',{(r['scene'],r['diagnostics_enabled']) for r in q['representations']},{(s,d) for s in manifest['scenes'] for d in [False,True]})
    eq(name+':control_count',len(q['controls']),4)
    eq(name+':control_keys',{(r['control'],r['diagnostics_enabled']) for r in q['controls']},{(s,d) for s in manifest['controls'] for d in [False,True]})
    eq(name+':replay_count',len(q['offline_replays']),4)
    eq(name+':replay_steps',sum(len(r['steps']) for r in q['offline_replays']),8)
    eq(name+':declared_historical_count',q['historical_frame_count'],8)
    eq(name+':new_render_count',q['new_renders'],0)
    for r in q['offline_replays']:
        eq(name+':replay_step_count:'+r['id'],len(r['steps']),r['historical_frames_read'])
        eq(name+':replay_not_new:'+r['id'],r['new_renders'],0)
old_pngs=[H/f['image_file'] for r in manifest['offline_replays'] for f in r['frames']]
eq('unique_historical_file_paths',len(set(old_pngs)),8)
eq('historical_logical_total',sum(len(r['steps']) for q in [source_q,installed_q] for r in q['offline_replays']),16)
qualification_access=[json.loads(line) for line in read_bytes(H/'external/run/qualify_r2/ACCESS.jsonl').splitlines()]
qualification_image_opens={suffix:sum(r['stage']=='qualify' and not r['writing'] and r['path'].endswith(suffix) for r in qualification_access) for suffix in ['.png','.npz']}
eq('installed_qualification_png_open_events',qualification_image_opens['.png'],18)
eq('installed_qualification_npz_open_events',qualification_image_opens['.npz'],9)
# Eight primary replay steps plus one duplicate re-observation; both stale-source
# attempts are rejected before opening the historical image. PNG is read again
# by the downstream state receipt validation, so file opens are a different count.
qualification_code=ast.get_source_segment(worker,functions['qualification'])
ck('duplicate_control_separate_from_main_replays','duplicate = images.observe_frame(frames[0])' in qualification_code)
for r in manifest['offline_replays']:
    for f in r['frames']:
        eq('old_png:'+f['image_file'],sha(H/f['image_file']),f['image_sha256'])
        eq('old_npz:'+f['arrays_file'],sha(H/f['arrays_file']),f['arrays_sha256'])

obs=read(H/'external/run/observe_r2/OBSERVATIONS.json')
eq('observation_embedded_result',obs,results['observe_r2']['observations'])
trace=[json.loads(line) for line in read_bytes(H/'external/run/observe_r2/TRACE.jsonl').splitlines()]
intents=[read(p) for p in sorted((H/'external/run/render_budget').glob('*.json'))]
eq('trace_physical_lines',len(trace),12)
eq('intent_count',len(intents),6)
eq('sequential_intents',[x['attempt'] for x in intents],list(range(1,7)))
eq('trace_intents',[{k:v for k,v in t.items() if k!='event'} for t in trace if t['event']=='render_attempt'],intents)
eq('trace_completion_count',sum(t['event']=='frame_complete' for t in trace),6)
png_bytes=npz_bytes=array_bytes=0
frames=[]
for chain in obs['chains']:
    name=chain['camera'];views=[x['attempt']['view'] for x in chain['frames']]
    gains=[len(x['update']['new_roi_ids']) for x in chain['steps']]
    eq(name+':views',views,protocol['new_observation']['expected_view_order'][name])
    eq(name+':gains',gains,protocol['new_observation']['expected_incremental_counts'][name])
    eq(name+':covered_count',len(chain['summary']['covered_roi_ids']),5)
    eq(name+':unknown_count',len(chain['summary']['unresolved_roi_ids']),1)
    for f in chain['frames']:
        eq('frame_complete:'+str(f['attempt']['attempt']),f['status'],'completed')
        eq('intent_matches_frame',intents[f['attempt']['attempt']-1],f['attempt'])
        frame=f['frame'];p=archive_map[str(Path(frame['image_path']))];a=archive_map[str(Path(frame['arrays_path']))]
        eq('frame_png_hash:'+p.name,sha(p),frame['image_sha256'])
        eq('frame_npz_hash:'+a.name,sha(a),frame['arrays_sha256'])
        eq('frame_png_bytes:'+p.name,p.stat().st_size,frame['PNG_bytes'])
        eq('frame_npz_bytes:'+a.name,a.stat().st_size,frame['compressed_array_file_bytes'])
        # Read standard NPY headers and raw payload bytes with stdlib, no NumPy/product imports.
        payload=0
        with zipfile.ZipFile(a) as z:
            for entry in z.namelist():
                b=z.read(entry);eq('npy_magic:'+a.name+':'+entry,b[:6],b'\x93NUMPY')
                hs=2 if b[6]==1 else 4;hn=int.from_bytes(b[8:8+hs],'little');header=ast.literal_eval(b[8+hs:8+hs+hn].decode('latin1'))
                nbytes=math.prod(header['shape'])*int(header['descr'][2:]);data=b[8+hs+hn:]
                eq('npy_payload:'+a.name+':'+entry,len(data),nbytes)
                row=frame['arrays'][Path(entry).stem]
                eq('npy_record_size:'+a.name+':'+entry,nbytes,row['nbytes'])
                eq('npy_record_hash:'+a.name+':'+entry,hashlib.sha256(data).hexdigest(),row['sha256'])
                payload+=nbytes
        eq('frame_payload_total:'+a.name,payload,frame['array_payload_bytes'])
        png_bytes+=p.stat().st_size;npz_bytes+=a.stat().st_size;array_bytes+=payload
        frames.append({'attempt':f['attempt']['attempt'],'view':frame['view_name'],'png_bytes':p.stat().st_size,'npz_bytes':a.stat().st_size,'array_bytes':payload})
eq('new_frames_count',len(frames),obs['new_render_attempts'])
eq('exact_new_png_count',len(list((H/'external/run/observe_r2').rglob('*.png'))),6)
eq('exact_new_npz_count',len(list((H/'external/run/observe_r2').rglob('*.npz'))),6)

prep=read(H/'PREPARATION.json');env=read(H/'preparation/ENVIRONMENT.json');venv=read(H/'preparation/VENV_SETUP.json')
source=read(H/'runs/SOURCE_QUALIFICATION_RESULT.json');build=read(H/'build/BUILD_INSTALL.json');repair=read(H/'preparation/INSTALL_LAYOUT_REPAIR.json')
windows={'marked_preparation':(prep['marked_preparation_started_ns'],prep['closed_before_publication_ns']),
 'environment_total':(env['started_ns'],env['closed_ns']), 'venv_setup':(venv['started_ns'],venv['closed_ns']),
 'dependency_copy':(env['copy_started_ns'],env['closed_ns']),
 'source_qualification_and_units':(source['started_ns'],source['closed_before_publication_ns']),
 'wheel_build_install':(build['started_ns'],build['closed_before_publication_ns']),
 'wheel_generation':(build['wheel_started_ns'],build['wheel_closed_ns']),
 'initial_install':(build['install_started_ns'],build['install_closed_ns']),
 'layout_repair':(repair['repair_started_ns'],repair['repair_closed_before_publication_ns'])}
reported=read(H/'review/FINAL_COST_AUDIT.json')
for name,(start,end) in windows.items():
    ck(name+':positive_clock',end>start)
    eq(name+':reported_duration',end-start,reported['windows'][name]['elapsed_ns'])
for inner,outer in [('environment_total','marked_preparation'),('venv_setup','environment_total'),('dependency_copy','environment_total'),('wheel_generation','wheel_build_install'),('initial_install','wheel_build_install')]:
    ck(inner+':nested_in:'+outer,windows[outer][0]<=windows[inner][0]<windows[inner][1]<=windows[outer][1])
workers_total=sum(p['elapsed_ns'] for p in processes)
nonoverlap=[windows[k] for k in ['source_qualification_and_units','wheel_build_install','layout_repair']]+[(p['start'],p['end']) for p in processes]
nonoverlap.sort()
for previous,current in zip(nonoverlap,nonoverlap[1:]):ck('total_intervals_do_not_overlap',previous[1]<=current[0])
known_total=sum(e-s for s,e in nonoverlap)
eq('worker_total',workers_total,reported['totals']['worker_parent_elapsed_sum_ns'])
eq('nonoverlap_total',known_total,reported['totals']['source_build_repair_and_all_worker_nonoverlapping_sum_ns'])
depbytes=sum(x['bytes'] for x in env['dependency_files'])
eq('dependency_count',len(env['dependency_files']),1046)
eq('dependency_bytes',depbytes,reported['storage_and_setup']['dependency_copy_bytes'])
for key,actual in [('PNG_bytes',png_bytes),('NPZ_bytes',npz_bytes),('array_payload_bytes',array_bytes)]:eq('storage:'+key,actual,reported['new_observations'][key])
eq('mocked_unit_count',source['targeted_tests']['run'],4)
eq('mocked_unit_errors',source['targeted_tests']['errors']+source['targeted_tests']['failures'],0)
ck('unit_explicitly_mocked', '0 actual rasters' in source['targeted_tests']['fixture_scope'])
for key in ['RSS_bytes','overall_CPU_time','all_final_publication_and_archival_ns','unit_mock_fixture_file_bytes']:eq('unknown_not_zero:'+key,reported['unknowns'][key],None)
ck('preparation_not_active_runtime',windows['marked_preparation'][1]-windows['marked_preparation'][0]>known_total)
ck('six_posthoc_readback_corrections_preserved',all((H/p).is_file() for p in ['review/FINAL_AUDIT_FIRST_READBACK.json','review/PRODUCT_API_AND_PACKAGE_AUDIT.json','review/FINAL_SEAL_READBACK_CORRECTION.json']))

result={'schema':'independent-core-integration-001-cost-review-v1','candidate_git':'cd863183b18e35d2ca38f75c0756e1c46e1a1ccb',
 'scope':'Independent stdlib offline reading/hash/clock/arithmetic/NPY payload checks; no algorithm, renderer, model or Blender execution.',
 'passed':all(c['passed'] for c in checks),'check_count':len(checks),'failed_checks':[c for c in checks if not c['passed']],
 'checks':checks,'pairs':pairs,'median_new_over_old':median,'total_new_over_old':new_total/old_total,
 'old_total_ns':old_total,'new_total_ns':new_total,'worker_receipts':processes,'worker_elapsed_total_ns':workers_total,
 'known_nonoverlap_total_ns':known_total,'preparation_elapsed_ns':windows['marked_preparation'][1]-windows['marked_preparation'][0],
 'environment_ns':windows['environment_total'][1]-windows['environment_total'][0],
 'storage':{'PNG_bytes':png_bytes,'NPZ_bytes':npz_bytes,'array_payload_bytes':array_bytes,'dependency_files':len(env['dependency_files']),'dependency_bytes':depbytes},
 'new_frames':frames,'denominators':{'worker_invocations':5,'initial_setup_failures':1,'successful_r2_phases':4,'new_raster_intents':6,'new_raster_completions':6,'trace_physical_lines':12,'historical_file_pairs':8,'historical_primary_logical_steps':16,'duplicate_control_calls_source_and_installed':2,'stale_scene_camera_control_calls_source_and_installed':4,'installed_qualification_png_open_events':qualification_image_opens['.png'],'installed_qualification_npz_open_events':qualification_image_opens['.npz'],'benchmark_pairs':5,'model_calls':0},
 'limits':['No statistical significance established from five pairs.','The paired runtime covers input I/O/hash/JSON through full index; import/guard/install excluded and separately costed.','No causal isolation of pure arithmetic versus removed diagnostics and unchanged-stage variation.','No host/MCP/model-consumption benchmark; historical 61.86% model result is separate.','Five parent invocations do not measure every redirector/helper OS process.','RSS, CPU, full final publication endpoint and mocked temporary fixture bytes unmeasured.'],
 'inputs_sha256':inputs,'new_product_algorithm_model_raster_Blender_calls':0}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'failures':result['failed_checks'],'median_ratio':median,'total_ratio':new_total/old_total,'known_total_seconds':known_total/1e9},ensure_ascii=False))
