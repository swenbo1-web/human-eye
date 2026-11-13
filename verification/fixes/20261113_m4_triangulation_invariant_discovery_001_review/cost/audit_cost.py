"""Independent saved-evidence cost/harness audit. No author code is executed."""
import ast
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import struct
import zipfile

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_triangulation_invariant_discovery_001')
OUT = Path(__file__).resolve().parent
INPUTS, CHECKS = {}, []


def raw(path):
    path = Path(path)
    if not path.is_absolute(): path = B / path
    data = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def read(path): return json.loads(raw(path))
def sha(data): return hashlib.sha256(data).hexdigest()
def check(name, ok, detail=None): CHECKS.append({'check': name, 'passed': bool(ok), 'detail': detail})
def interval(name, value):
    check(name + ':clock', value['closed_ns'] >= value['started_ns'] and
          value['elapsed_ns'] == value['closed_ns'] - value['started_ns'])


def concatenated(path):
    text = raw(path).decode('utf-8'); pos = 0; result = []; decoder = json.JSONDecoder()
    while pos < len(text):
        if text[pos].isspace(): pos += 1; continue
        obj, pos = decoder.raw_decode(text, pos); result.append(obj)
    return result


def npy(data):
    assert data[:6] == b'\x93NUMPY'
    major = data[6]
    length_size = 2 if major == 1 else 4
    header_size = struct.unpack('<H' if length_size == 2 else '<I', data[8:8+length_size])[0]
    start = 8 + length_size
    header = ast.literal_eval(data[start:start+header_size].decode('latin1' if major < 3 else 'utf-8'))
    return header, data[start+header_size:]


protocol = read('BENCHMARK_PROTOCOL.json')
frozen = read('FROZEN.json')
freeze_sha = sha(raw('FROZEN.json'))
check('frozen_count275', len(frozen['files_sha256']) == 275)
check('protocol_in_freeze', frozen['registered_protocol_sha256'] == sha(raw('BENCHMARK_PROTOCOL.json')))
check('product138_in_freeze', frozen['fixed_product']['source_count'] == 138 and all(
    frozen['files_sha256'].get(p) == h for p, h in frozen['fixed_product']['installed_sources_sha256'].items()))
for n in ['engineering.py', 'execute.py', 'discovery.py', 'BENCHMARK_PROTOCOL.json', 'INPUT_MANIFEST.json', 'proof/EXPECTED.json']:
    check('new_source_frozen:' + n, frozen['files_sha256'].get(str((B/n).resolve())) == sha(raw(n)))

phase_order = ['proof', 'legacy', 'correctness', 'observations', 'benchmark']
phases = []
for name in phase_order:
    intent = read('execution/' + name + '_INTENT.json')
    result = read('execution/' + name + '_RESULT.json')
    check(name + ':intent_bound', intent['phase'] == result['phase'] == name and
          intent['started_ns'] == result['started_ns'] and intent['pid'] == result['pid'])
    check(name + ':same_freeze_passed', result['passed'] is True and result['source_freeze_sha256'] == freeze_sha and 'error' not in result)
    times = [result[k] for k in ['started_ns', 'binding_closed_ns', 'module_loaded_ns', 'closed_before_result_publication_ns']]
    check(name + ':ordered_clocks', times == sorted(times))
    check(name + ':elapsed', times[-1] - times[0] == result['elapsed_before_result_publication_ns'])
    phases.append(result)
check('five_phases_exact', {p.name for p in (B/'execution').glob('*_INTENT.json')} == {n+'_INTENT.json' for n in phase_order})
check('phase_order', all(a['closed_before_result_publication_ns'] < z['started_ns'] for a,z in zip(phases,phases[1:])))
check('freeze_before_phases', frozen['closed_before_publication_ns'] < phases[0]['started_ns'])
prep = read('PREPARATION.json'); gate = read('PRE_BENCHMARK_GATE.json')
check('prep_before_execution', prep['closed_before_publication_ns'] < phases[0]['started_ns'])
check('gate_before_benchmark', phases[3]['closed_before_result_publication_ns'] < gate['qualified_before_benchmark_ns'] < phases[4]['started_ns'])
check('gate_bound', gate['source_freeze_sha256'] == freeze_sha and gate['actual_phases_same_frozen_source_and_order'])

legacy = read('runs/legacy/RESULTS.json')
counts = {r['scene']: r['discovered_count'] for r in legacy['rows']}
check('actual_legacy6_and4zero', len(counts) == 5 and counts == gate['legacy_counts'] and
      counts['original'] == 6 and all(v == 0 for k,v in counts.items() if k != 'original'))
for row in legacy['rows']: interval('legacy:' + row['scene'], row); check('legacy_count:' + row['scene'], len(row['regions']) == row['discovered_count'])
correct = read('runs/correctness/RESULTS.json')
check('14_correctness_rows', correct['passed'] and len(correct['rows']) == gate['correctness_rows'] == 14 and all(r['passed'] and 'error' not in r for r in correct['rows']))
check('correctness_progress10', read('runs/correctness/PROGRESS.json') == correct['rows'][:10])

bench = read('runs/benchmark/RESULTS.json'); rows = bench['rows']
start = read('BENCHMARK_STARTED.json')
expected_order = [(i,v) for i,pair in enumerate(protocol['pairs'],1) for v in pair]
check('exact10_fixed_order', len(rows) == protocol['trial_count'] == 10 and [(r['pair'],r['variant']) for r in rows] == expected_order)
check('benchmark_marker', start['pairs'] == protocol['pairs'] and phases[4]['module_loaded_ns'] <= start['started_ns'] < rows[0]['started_ns'])
check('no_benchmark_renders', bench['new_renders'] == protocol['render_calls_in_benchmark'] == 0)
check('all_benchmark_passed', bench['passed'] and all(r['passed'] and 'error' not in r for r in rows))
check('benchmark_progress_all_rows', read('runs/benchmark/PROGRESS.json') == rows)
check('trial_intervals_nonoverlap', all(a['closed_ns'] < z['started_ns'] for a,z in zip(rows,rows[1:])))
stage_names = ['read_hash_JSON', 'Fraction_geometry_and_scene_identity', 'discovery', 'old_optimized_index']
for i,row in enumerate(rows):
    label = 'trial' + str(i+1); interval(label, row)
    stages = [row['stages'][k] for k in stage_names]
    for k,v in zip(stage_names, stages): interval(label + ':' + k, v)
    check(label + ':stage_chain', stages[0]['started_ns'] == row['started_ns'] and stages[-1]['closed_ns'] == row['closed_ns'] and
          all(a['closed_ns'] == z['started_ns'] for a,z in zip(stages,stages[1:])) and sum(v['elapsed_ns'] for v in stages) == row['elapsed_ns'])
    check(label + ':input_bytes_SHA', row['scene_sha256'] == sha(raw(row['scene_path'])) and row['scene_JSON_bytes'] == len(raw(row['scene_path'])) and
          row['camera_sha256'] == sha(raw('inputs/CAMERAS.json')) and row['camera_JSON_bytes'] == len(raw('inputs/CAMERAS.json')))
    check(label + ':scene_binding', Path(row['scene_path']).resolve() == (B/protocol['scene']).resolve() and row['index']['scene_identity'] == row['discovery_stats']['geometry']['scene_identity'])
    check(label + ':single_geometry_call', row['discovery_stats']['geometry']['calls'] == 1)
    check(label + ':memory_unknown', row['RSS_bytes'] is None and row['Python_geometry_resident_bytes'] is None)
    work = row['discovery_stats']['discovery']['work']
    expected_arithmetic = (27648,27648,18432) if row['variant'] == 'reference' else (6144,15360,3072)
    actual_arithmetic = tuple(work[k] for k in ['area_rational_multiply_calls','area_rational_subtract_calls','area_rational_add_calls'])
    check(label + ':recorded_actual_work', actual_arithmetic == expected_arithmetic)
    check(label + ':common_work', tuple(work[k] for k in ['face_incidence_visits','oriented_edge_insertions','undirected_edges','connectivity_face_visits','boundary_walk_steps']) == (3336,10008,5196,3072,384))
    for key in work:
        check(label + ':sum_per_object:' + key, work[key] == sum(x.get(key,0) for x in row['discovery_stats']['discovery']['objects']))
check('shared_benchmark_setup_outside_trials', bench['shared_setup']['closed_ns'] <= rows[0]['started_ns'])
for row in correct['rows'][:10]: check('correctness_direct_geometry:' + row['scene'] + ':' + row['variant'], row['trial']['discovery_stats']['geometry']['calls'] == 1)

pairs = []
for i in range(1,6):
    ref = next(r for r in rows if r['pair']==i and r['variant']=='reference'); can = next(r for r in rows if r['pair']==i and r['variant']=='candidate')
    ratio = Fraction(can['elapsed_ns'], ref['elapsed_ns'])
    pairs.append({'pair':i,'reference_ns':ref['elapsed_ns'],'candidate_ns':can['elapsed_ns'],'numerator':ratio.numerator,'denominator':ratio.denominator,'ratio':float(ratio)})
    old = bench['pairs'][i-1]
    check('author_pair' + str(i), old['reference_ns']==ref['elapsed_ns'] and old['candidate_ns']==can['elapsed_ns'] and old['candidate_over_reference']==float(ratio))
med = statistics.median(Fraction(p['numerator'],p['denominator']) for p in pairs)
sums = {v:sum(r['elapsed_ns'] for r in rows if r['variant']==v) for v in ['reference','candidate']}
discovery_medians = {v:statistics.median(r['stages']['discovery']['elapsed_ns'] for r in rows if r['variant']==v) for v in sums}
selection = read('SELECTION.json')
check('selection_time_math', selection['paired_complete_index_ratio_median']==float(med) and selection['reference_total_ns']==sums['reference'] and selection['candidate_total_ns']==sums['candidate'])
check('selection_all_5_pairs', selection['all_pairs_retained']==bench['pairs'] and selection['trial_count']==10 and selection['full_index_regression_pairs']==[1,2])
check('registered_selection_timing_pass', med <= 1 and sums['candidate'] <= sums['reference'])
check('selection_before_final_after_benchmark', phases[4]['closed_before_result_publication_ns'] < selection['selected_ns'])
check('selection_bound', selection['source_freeze_sha256']==freeze_sha and selection['benchmark_protocol_sha256']==sha(raw('BENCHMARK_PROTOCOL.json')))

intents = [read(p) for p in sorted((B/'render_budget').glob('*.json'))]
check('exact8_intents', [x['attempt'] for x in intents] == list(range(1,9)))
observations=[]; totals={'PNG_bytes':0,'NPZ_bytes':0,'array_payload_bytes':0}; event_count=0
for scene,variant in protocol['observations']['chains']:
    directory = B/'runs'/('observe_' + scene + '_' + variant)
    result = read(directory/'RESULTS.json'); timing = read(directory/'FINAL_TIMING.json'); interval(scene+variant,timing)
    check(scene+variant+':same_budget', Path(result['global_budget_directory']).resolve() == (B/'render_budget').resolve())
    check(scene+variant+':2_complete_no_errors', result['passed'] and not result['errors'] and result['actual_chain_render_attempts']==2 and result['new_models_or_Blender']==0)
    check(scene+variant+':new_chain_clock', timing['started_ns']==result['started_ns'] and timing['started_ns'] < result['before_result_publication_ns'] < timing['closed_ns'])
    check(scene+variant+':progress', read(directory/'PROGRESS.json') == {k:result[k] for k in ['frames','steps']})
    trace=concatenated(directory/'TRACE.jsonl');event_count+=len(trace)
    check(scene+variant+':4events', [r['event'] for r in trace]==['render_attempt','frame_complete']*2)
    chain_bytes=0; stages_ns={}
    for j,(view,frame) in enumerate(sorted(result['frames'].items(), key=lambda item: item[1]['attempt']['attempt'])):
        label=scene+variant+view
        check(label+':sequence', view==['SCENE','BACK'][j])
        intent = intents[frame['attempt']['attempt']-1]
        check(label+':intent_bound', frame['attempt']==intent and intent['output']==str(directory) and intent['view']==view and intent['variant']==variant)
        check(label+':trace_attempt', trace[2*j]=={'event':'render_attempt',**intent} and trace[2*j+1]=={'event':'frame_complete','attempt':intent['attempt'],'view':view,'PNG_sha256':frame['PNG_sha256']})
        check(label+':frame_copy', read(Path(frame['PNG']).parent/'FRAME.json') == frame)
        check(label+':actual_raster_after_intent', result['started_ns'] < intent['started_ns'] < frame['stages']['actual_raster']['started_ns'] < result['before_result_publication_ns'])
        for key,val in frame['stages'].items(): interval(label+':'+key,val);stages_ns[key]=stages_ns.get(key,0)+val['elapsed_ns']
        for extension in ['PNG','NPZ']:
            payload=raw(frame[extension]);totals[extension+'_bytes']+=len(payload)
            check(label+':'+extension, len(payload)==frame[extension+'_bytes'] and sha(payload)==frame[extension+'_sha256'])
        with zipfile.ZipFile(io.BytesIO(raw(frame['NPZ']))) as z:
            check(label+':array_set', set(z.namelist())=={k+'.npy' for k in frame['arrays']})
            for key,meta in frame['arrays'].items():
                hdr,data=npy(z.read(key+'.npy'))
                check(label+':array:'+key, list(hdr['shape'])==meta['shape'] and hdr['fortran_order'] is False and len(data)==meta['nbytes'] and sha(data)==meta['sha256'])
                chain_bytes+=len(data);totals['array_payload_bytes']+=len(data)
        check(label+':step_receipt', result['steps'][j]['receipt']['image_path']==frame['PNG'] and result['steps'][j]['receipt']['image_sha256']==frame['PNG_sha256'])
    check(scene+variant+':array_total', chain_bytes==result['array_payload_bytes'])
    setup=result['shared_setup'];setup_ns=setup['closed_ns']-setup['started_ns'];inside=result['started_ns'] <= setup['started_ns'] and setup['closed_ns'] <= timing['closed_ns']
    accounted=sum(stages_ns.values())+(setup_ns if inside else 0)
    observations.append({'scene':scene,'variant':variant,'full_ns':timing['elapsed_ns'],'shared_setup_ns':setup_ns,'setup_inside_chain':inside,'frame_stage_ns':stages_ns,'unallocated_ns':timing['elapsed_ns']-accounted,'unallocated_includes':'Initial build trial not persisted; mesh preparation, inter-stage writes, coverage, serialization and unclocked overhead.'})
check('16_trace_objects', event_count==16)
check('8actual_PNGs', len(list((B/'runs').rglob('*.png')))==8 and len(list((B/'runs').rglob('*.npz')))==8)
check('only_first_chain_setup', [r['setup_inside_chain'] for r in observations]==[True,False,False,False])
check('payload_totals', totals=={'PNG_bytes':27800,'NPZ_bytes':193004,'array_payload_bytes':31457280})

engineering=raw('engineering.py').decode();execute=raw('execute.py').decode()
eng_ast=ast.parse(engineering);funcs={n.name:n for n in eng_ast.body if isinstance(n,ast.FunctionDef)}
calls=lambda f,name: [n for n in ast.walk(funcs[f]) if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Attribute) and n.func.attr==name) or (isinstance(n.func,ast.Name) and n.func.id==name))]
check('single_parse_per_trial_and_control_source', len(calls('build_trial','parse_geometry'))==1 and len(calls('correctness','parse_geometry'))==1)
check('one_build_site_each_loop', all(len(calls(f,'build_trial'))==1 for f in ['correctness','observe_chain','benchmark']))
check('no_observation_trial_persisted', all('trial' not in read(B/'runs'/('observe_'+s+'_'+v)/'RESULTS.json') for s,v in protocol['observations']['chains']))
check('phase_guard_scope_static', "current.get('passed', True)" in execute and "gate['source_freeze_sha256']" in execute)
check('budget_namespace_not_fixed_root_static', 'if not budget.is_relative_to(HERE)' in engineering)
check('physical_trace_format_declared_by_source', "sort_keys=True, default=str, allow_nan=False, indent=2" in engineering and "trace.write(encoded(" in engineering)
adjustments=[read('review/'+n) for n in ['READBACK_ADJUSTMENT.json','ROOT_READBACK_ADJUSTMENT.json','COST_AUDIT_READBACK_ADJUSTMENT.json']]
check('three_reader_failures_retained', adjustments[0]['execution_exit_code']==1 and adjustments[1]['failed_readback_queries']==1 and adjustments[2]['actual_failed_audit_invocations']==1)
check('failed_cost_reader_SHA_unknown', adjustments[2]['failed_script_sha256'] is None)

phase_sum=sum(p['elapsed_before_result_publication_ns'] for p in phases)
span=phases[-1]['closed_before_result_publication_ns']-phases[0]['started_ns']
prep_ns=prep['closed_before_publication_ns']-prep['marked_preparation_started_ns']
check('phase_time_sums', phase_sum==13317404400 and span==153639477200 and prep_ns==1304332886000)
result={'schema':'root-independent-triangulation-cost-v1','candidate_commit':'b638c499c049604902415965f500f50a9947d34f',
 'check_count':len(CHECKS),'passed':sum(r['passed'] for r in CHECKS),'failed':[r for r in CHECKS if not r['passed']],
 'pairs':pairs,'median_ratio':{'numerator':med.numerator,'denominator':med.denominator,'value':float(med)},
 'full_index_totals_ns':sums,'total_ratio':float(Fraction(sums['candidate'],sums['reference'])),
 'discovery_stage_medians_ns':discovery_medians,'full_time_regressions':[p['pair'] for p in pairs if p['ratio']>1],
 'observations':observations,'payload_totals':totals,'phase_time':{'sum_ns':phase_sum,'span_ns':span,'gap_ns':span-phase_sum,'preparation_ns':prep_ns},
 'actual_recorded_counts':{'phases':5,'legacy':5,'correctness':14,'benchmark_trials':10,'render_intents':8,'PNG':8,'NPZ':8,'trace_events':16,
  'new_parse_discovery_direct_records':20,'new_parse_discovery_by_static_call_flow':8,'new_parse_discovery_total':28},
 'selection':'Registered timing rule passed; actual geometry/arithmetic correctness requires sibling review.',
 'harness':'Actual one-controller sequence and one budget directory established; generic APIs do not independently enforce all prerequisites.',
 'AL':'Own child context bound; parent task read-only.',
 'new_model_CLI_actor_Blender_raster_candidate_calls':0,'checks':CHECKS}
OUT.mkdir(parents=True,exist_ok=True)
for name,obj in [('RESULTS.json',result),('INPUTS.json',INPUTS)]:
    (OUT/name).write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
print(json.dumps({k:v for k,v in result.items() if k not in ['checks','observations','pairs']},ensure_ascii=False))
