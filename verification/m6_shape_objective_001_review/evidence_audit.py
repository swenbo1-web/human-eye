"""Check grouping, raw cost ledgers, preserved failures and final snapshot identity."""
import copy
import hashlib
import json
from pathlib import Path
import time

START, CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
S = HERE/'snapshot'
V = S/'verification'
B = V/'m6_shape_objective_001'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
checks = 0

def read(p): return json.loads(Path(p).read_bytes())
def mapped(p): return S/Path(p).relative_to(AUTHOR)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(test,name):
    global checks
    checks += 1
    if not test: raise AssertionError(name)

# Independently select group membership from the old source metadata.
development=read(V/'m6_shape_data_001/DATASET_INDEX.json')['cases']
public=read(V/'m6_shape_train_001/PUBLIC_DATASET_INDEX.json')['cases']
cases=[r for r in development+[r for r in public if r['purpose']=='validation'] if not r['normal_control']]
groups={}
for case in cases:
    p='development_center' if case['purpose']=='development_train_pool' else 'validation_'+case.get('position_group','center')
    source='source_'+case['source']; a=case['amplitude_ratio']; r=case['radius_ratio']
    for group in ('all',p,source,f'{p}_amplitude_{a}',f'{p}_r{r}_a{a}',f'{source}_amplitude_{a}',f'amplitude_{a}'):
        groups.setdefault(group,[]).append(case)
reported=read(B/'DECOMPOSITION.json')['summaries']
check(set(groups)==set(reported),'group_names')
for name, rows in groups.items():
    r=reported[name]
    check(set(r['case_ids'])=={x['id'] for x in rows},name+'_members')
    check(r['patch_count']==len({x['patch_id'] for x in rows}),name+'_patches')
    check(r['source_count']==len({x['source'] for x in rows}),name+'_sources')

# The original report remains available. Only counters and attribution overlaps were added.
repair=read(B/'SURFACE_METADATA_REPAIR.json')
initial=read(mapped(repair['original_report_path']))
current=read(B/'SURFACE_RESULTS.json')
check(sha(mapped(repair['original_report_path']))==repair['original_report_sha256'],'initial_report_sha')
check(sha(mapped(repair['executed_source_snapshot_path']))==repair['executed_source_sha256'],'executed_surface_source_sha')
check(initial['code_sha256']['evaluate_surface.py']==repair['executed_source_sha256'],'initial_source_binding')
check(sha(B/'evaluate_surface.py')==repair['current_corrected_caller_sha256'],'corrected_source_sha')
before, after=copy.deepcopy(initial['cases']),copy.deepcopy(current['cases'])
detail_files=0
for old,new in zip(before,after):
    check(old['case_id']==new['case_id'],'case_order')
    for method in old['methods']:
        for direction in ('candidate_to_reference','reference_to_candidate'):
            a,b=old['methods'][method][direction],new['methods'][method][direction]
            check(a['metric_domain_diagnostics']=={},'original_counter_defect_preserved')
            check(bool(b['metric_domain_diagnostics']),'repaired_counter_populated')
            a.pop('metric_domain_diagnostics'); b.pop('metric_domain_diagnostics')
            b.pop('boundary_classification_overlap',None)
            check(a==b,'distance_and_boundary_payload_unchanged')
            check(sha(mapped(a['detail_path']))==a['detail_sha256'],'unchanged_detail_sha')
            detail_files+=1
check(before==after,'all_scientific_case_payload_unchanged')
check(repair['new_nearest_points_calls']==0 and repair['new_boundary_queries']==0,'repair_scope')

costs=read(B/'COSTS.json'); phases=costs['phases']
check(len(phases)==8,'cost_phase_count')
wall=cpu=controller_cpu=0.0; failure=[]
source_paths={'decompose':'decompose.py','qa':'meter_qa.py','repair':'repair_surface_metadata.py','verify':'verify.py',
              'summary_final':'summarize.py',
              'surface':'private/recovery/evaluate_surface_initial_executed.py',
              'summary':'private/recovery/summarize_initial_failed.py'}
recovery_source=(B/'private/recovery/summarize_initial_failed.py').read_bytes().decode('utf-8')
recovery_source=recovery_source.replace('verification["status"] != "passed"',
    'verification["status"] != "passed_independent_saved_result_verification"')
recovery_paragraph=next(line for line in (B/'summarize.py').read_text(encoding='utf-8').splitlines()
    if line.startswith('汇总入口首试'))
recovery_source=recovery_source.replace('新模型前向、训练、新修复候选',
    recovery_paragraph+'\n\n新模型前向、训练、新修复候选')
recovery_sha=hashlib.sha256(recovery_source.encode('utf-8')).hexdigest()
check(recovery_sha==read(B/'SUMMARY_RECOVERY.json')['final_source_sha256'],'reconstructed_summary_recovery_source')
(HERE/'private/summarize_recovery_reconstructed.py').write_bytes(recovery_source.encode('utf-8'))
for label,phase in phases.items():
    controller=read(B/'private/processes'/(label+'.controller.json'))
    tree=read(B/'private/processes'/(label+'.json'))
    check(controller==phase['controller'] and tree==phase['worker_tree'],label+'_raw_process_records')
    expected=recovery_sha if label=='summary_recovery01' else sha(B/source_paths[label])
    check(controller['worker_source_sha256']==expected,label+'_actual_executed_source')
    check(controller['returncode']==tree['returncode'],label+'_exit')
    if tree['returncode']!=0: failure.append(label)
    wall+=controller['main_wall_s_including_worker_before_write']
    cpu+=tree['tree_cpu_s']
    controller_cpu+=controller['process_lifetime_before_final_write']['cpu_s']
check(failure==['summary'],'failed_summary_retained')
for value,key in [(wall,'sequential_controller_main_wall_sum_s'),(cpu,'phase_worker_tree_CPU_sum_s'),(controller_cpu,'phase_outer_controller_lifetime_CPU_before_final_write_sum_s')]:
    check(abs(value-costs[key])<1e-10,key)
summary_repair=read(B/'SUMMARY_RECOVERY.json')
check(summary_repair['scientific_results_unchanged'] and summary_repair['new_distance_or_decomposition_runs']==0,'summary_recovery_scope')
check(sha(mapped(summary_repair['old_source_path']))==summary_repair['old_summary_source_sha256'],'failed_summary_source')
check(len(costs['missing'])>0 and bool(costs['measurement_limits']),'cost_missing_disclosed')

# None of the 1509 copied evidence files was changed by our numeric review.
snapshot=read(HERE/'SNAPSHOT.json')
for row in snapshot['records']:
    p=S/row['path']
    check(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'snapshot_'+row['path'])

result={'status':'passed','assertions':checks,'group_memberships':len(groups),'preserved_distance_details':detail_files,
        'raw_process_phases':len(phases),'failed_processes_preserved':failure,
        'reconstructed_summary_recovery_sha256':recovery_sha,
        'author_phase_wall_sum_s':wall,'author_worker_tree_CPU_sum_s':cpu,'author_controller_CPU_sum_s':controller_cpu,
        'immutable_snapshot_files':len(snapshot['records']),
        'author_freeze_caveat':'three old arrays schema-read after PLAN written but before final freeze; disclosed, no recorded metric/model work',
        'body_wall_s_before_write':time.perf_counter()-START,'body_CPU_s_before_write':time.process_time()-CPU,
        'new_arrays_deserialized':0,'new_inference_or_training':0}
(HERE/'EVIDENCE_RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
