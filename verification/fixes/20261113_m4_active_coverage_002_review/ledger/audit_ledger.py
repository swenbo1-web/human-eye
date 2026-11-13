"""Independent retained-record audit. Never executes the tested runner/runtime."""
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
SRC=ROOT/'verification/m4_active_coverage_002'
OLD=ROOT/'verification/m4_active_coverage_001'
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'))
import numpy as np
from PIL import Image
checks=[];inputs={}
def raw(path):
    path=Path(path);b=path.read_bytes();inputs[str(path)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return b
def sha(b):return hashlib.sha256(b).hexdigest()
def read(path):return json.loads(raw(path))
def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail})
def counts(rows):return {s:sum(r['status']==s for r in rows)for s in ('completed','failed','not_run')}
def elapsed(name,row):
    check(name+'_delta',row['closed_ns']-row['started_ns']==row['elapsed_ns'])
    check(name+'_nonnegative',row['closed_ns']>=row['started_ns'])

batch=read(SRC/'RESULTS.json');progress=read(SRC/'PROGRESS.json');plan=read(SRC/'PREREGISTRATION.json')
run=SRC/'runs/main_p01_A';child=read(run/'RESULT.json');pub=read(run/'RESULT_PUBLICATION.json')
trace=[json.loads(line)for line in raw(run/'TRACE.jsonl').splitlines()]
row=batch['rows'][0]
check('12_main_2_control',len(batch['rows'])==12 and len(batch['controls'])==2)
check('fixed_order',[(r['id'],r['arm'],r['pair'],r['scenario'])for r in batch['rows']]==[(r['id'],r['arm'],r['pair'],r['scenario'])for r in plan['main']])
check('progress_exact',all(progress[k]==batch[k]for k in ('rows','controls','stop')))
check('main_0_completed_1_failed_11_not_run',counts(batch['rows'])=={'completed':0,'failed':1,'not_run':11}==batch['summary']['main_counts'])
check('control_0_completed_0_failed_2_not_run',counts(batch['controls'])=={'completed':0,'failed':0,'not_run':2}==batch['summary']['control_counts'])
check('only_one_run_directory',[p.name for p in (SRC/'runs').iterdir()if p.is_dir()]==['main_p01_A'])
check('not_run_no_time_or_pid',all('started_ns'not in r and 'process_id'not in r for r in batch['rows'][1:]+batch['controls']))
check('net_benefit_null',batch['summary']['net_time_benefit']is None and not batch['summary']['full_cost_gate'])
check('frozen_failed_reason',row['status']=='failed' and row['error']['message']=='child_process_or_output_binding')
check('child_success_is_separate',child['status']=='completed' and child['exceptions']==[] and row['returncode']==0)
check('observed_PID_mismatch',row['process_id']==23456 and child['process_id']==20368 and row['process_id']!=child['process_id'])
check('same_output_directory',Path(child['output_directory']).resolve()==Path(row['output_directory']).resolve()==run.resolve())
check('trace_sequence', [r['sequence']for r in trace]==list(range(1,len(trace)+1)))
check('trace_same_runtime_pid',all(r['process_id']==child['process_id']for r in trace))
check('trace_order',all(a['monotonic_ns']<=b['monotonic_ns']for a,b in zip(trace,trace[1:])))
check('trace_arm_scenario',all(r['arm']=='A' and r['scenario']=='main' for r in trace))
check('trace_final_success',trace[-1]['event']=='process_complete' and trace[-1]['status']=='completed')
elapsed('main_failed_slot',row);elapsed('shared_parent_setup',batch['common_parent_setup']);elapsed('result_publication',pub)
check('batch_delta',batch['batch_closed_before_publication_ns']-batch['batch_started_ns']==batch['whole_batch_through_analysis_ns'])
check('child_work_delta',child['work_closed_ns']-child['started_ns']==child['elapsed_before_result_publication_ns'])
check('nested_monotonic_windows',batch['batch_started_ns']<=batch['common_parent_setup']['started_ns']<=batch['common_parent_setup']['closed_ns']<=row['started_ns']<=child['started_ns']<=trace[0]['monotonic_ns']<=child['work_closed_ns']<=pub['started_ns']<=pub['closed_ns']<=trace[-1]['monotonic_ns']<=row['process_exited_ns']<=row['closed_ns']<=batch['batch_closed_before_publication_ns'])
check('publication_result_binding',pub['RESULT_bytes']==len(raw(run/'RESULT.json')) and pub['RESULT_sha256']==sha(raw(run/'RESULT.json'))==trace[-1]['RESULT_sha256'])
for name in ('STDOUT','STDERR'):
    b=raw(run/(name+'.bin'));check(name+'_empty_hash',len(b)==0==row[name.lower()+'_bytes']and sha(b)==row[name.lower()+'_sha256'])
starts={r['stage']:r for r in trace if r['event']=='stage_start'}
ends={r['stage']:r for r in trace if r['event']=='stage_complete'}
for name,stage in child['stages'].items():
    elapsed('stage_'+name,stage)
    check('stage_inside_child_'+name,child['started_ns']<=stage['started_ns']<=stage['closed_ns']<=child['work_closed_ns'])
    if name!='stdlib_import':
        e=ends[name];check('trace_stage_'+name,all(stage[k]==e[k]for k in ('started_ns','closed_ns','elapsed_ns'))and starts[name]['monotonic_ns']<=stage['closed_ns'])
intervals=sorted((v['started_ns'],v['closed_ns'])for v in child['stages'].values())
check('top_level_stages_disjoint',all(a[1]<=b[0]for a,b in zip(intervals,intervals[1:])))
intents=[r for r in trace if r['event']=='render_attempt'];returns=[r for r in trace if r['event']=='render_complete'];frames=[r for r in trace if r['event']=='frame_complete']
order=['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']
check('six_attempts_returns_frames',len(intents)==len(returns)==len(frames)==len(child['frames'])==6)
check('correct_call_order',[r['view_name']for r in intents]==[r['view_name']for r in returns]==[r['view_name']for r in frames]==order)
check('attempt_count_accounting',child['metrics']['raster_attempts']==child['metrics']['raster_completed']==row['render_attempts']==batch['summary']['main_render_attempts']==6)
check('preparation_control_zero',batch['preparation_render_attempts']==batch['summary']['control_render_attempts']==0)
for i,(a,b,c,d)in enumerate(zip(intents,returns,frames,child['render_attempts']),1):
    check('attempt_identity_'+str(i),a['attempt_id']==b['attempt_id']==c['attempt_id']==d['attempt_id']==i)
    check('intent_before_return_'+str(i),a['monotonic_ns']<b['started_ns']<=b['closed_ns']<=b['monotonic_ns']<c['monotonic_ns'])
    check('record_attempt_'+str(i),d['intent_ns']==a['monotonic_ns']and d['intent_trace_sequence']==a['sequence']and d['render_started_ns']==b['started_ns']and d['render_closed_ns']==b['closed_ns']and d['status']=='completed')
    check('render_delta_'+str(i),b['closed_ns']-b['started_ns']==b['elapsed_ns'])

old_result=read(OLD/'benchmark/OUTPUT_OPTIMIZED.json')['semantic']
for key in ('scene_identity','candidate_identity','view_masks','classifications','view_order'):
    check('index_same_accepted001_'+key,child['index'][key]==old_result[key])
check('same_geometry_input',raw(SRC/'inputs/SCENE_GEOMETRY_RATIONAL.json')==raw(OLD/'inputs/SCENE_GEOMETRY_RATIONAL.json'))
check('same_camera_input',raw(SRC/'inputs/CAMERAS.json')==raw(OLD/'inputs/CAMERAS.json'))
scene=read(SRC/'inputs/SCENE_GEOMETRY_RATIONAL.json');cameras=read(SRC/'inputs/CAMERAS.json')
poses={x['name']:x for x in cameras['views']};ids=child['index']['roi_ids'];covered=set();pixels=[];totals={'PNG_bytes':0,'NPZ_bytes':0,'array_payload_bytes':0,'frame_metadata_bytes':0}
for frame in child['frames']:
    name=frame['view_name']; png=Path(frame['PNG']);npz=Path(frame['owner_depth_RGB_arrays']);metadata=Path(frame['metadata_path'])
    pbytes,nbytes,mbytes=raw(png),raw(npz),raw(metadata);meta=json.loads(mbytes)
    check('PNG_content_001_'+name,pbytes==raw(OLD/'render'/f'{name}.png'))
    check('NPZ_content_001_'+name,nbytes==raw(OLD/'render'/f'{name}.npz'))
    check('PNG_record_'+name,len(pbytes)==frame['PNG_bytes']and sha(pbytes)==frame['PNG_sha256'])
    check('NPZ_record_'+name,len(nbytes)==frame['compressed_array_file_bytes']and sha(nbytes)==frame['arrays_sha256'])
    check('metadata_record_'+name,len(mbytes)==frame['metadata_bytes']and sha(mbytes)==frame['metadata_sha256'])
    check('frame_pose_'+name,frame['pose']==meta['pose']==poses[name])
    check('frame_pixel_rows_'+name,frame['pixel_rows']==meta['pixel_rows'])
    check('frame_state_record_'+name,frame['state_update']==meta['state_update'])
    arrays=np.load(npz,allow_pickle=False);color,depth,owner=(arrays[x]for x in ('color','depth','owners'))
    check('PNG_decodes_actual_color_'+name,np.array_equal(np.asarray(Image.open(png)),color))
    check('shape_'+name,color.shape==(512,512,3)and depth.shape==owner.shape==(512,512))
    check('owner_range_'+name,np.all((owner>=-1)&(owner<28)))
    check('foreground_depth_'+name,np.array_equal(owner>=0,np.isfinite(depth)&(depth>0))and np.all(np.isposinf(depth[owner<0])))
    check('array_payload_'+name,sum(x.nbytes for x in (color,depth,owner))==frame['array_payload_bytes'])
    for key,a in zip(('color','depth','owners'),(color,depth,owner)):
        recorded=frame['arrays'][key]
        check('array_binding_'+name+'_'+key,list(a.shape)==recorded['shape']and str(a.dtype)==recorded['dtype']and a.nbytes==recorded['nbytes']and sha(a.tobytes())==recorded['sha256'])
    boundary=np.zeros(owner.shape,dtype=bool)
    for axis in (0,1):
        changed=np.diff(owner,axis=axis)!=0
        delta=np.diff(color.astype(np.int32),axis=axis)
        qualified=changed&(np.sum(delta*delta,axis=2)>=576)
        if axis==0:boundary[:-1,:]|=qualified;boundary[1:,:]|=qualified
        else:boundary[:,:-1]|=qualified;boundary[:,1:]|=qualified
    readable=set()
    for region in child['index']['regions']:
        index=region['object_index'];identity=region['roi_id'];mask=owner==index
        vertices=np.array([[float(Fraction(v))for v in pt]for pt in scene['objects'][index]['vertices']])
        triangle=scene['objects'][index]['triangles'][0];a,b,c=vertices[triangle]
        front=bool(np.cross(b-a,c-a)@np.array(poses[name]['target_to_eye_unit'])>0)
        visible=int(mask.sum());edges=int((mask&boundary).sum());passed=front and visible>=16 and edges>=4
        stored=next(x for x in frame['pixel_rows']if x['roi_id']==identity)
        check('pixel_counts_'+name+'_'+identity,(front,visible,edges,passed)==(stored['front_facing'],stored['visible_surface_pixels'],stored['contrasting_boundary_pixels'],stored['readable']))
        check('pixel_thresholds_'+name+'_'+identity,(stored['minimum_surface_pixels'],stored['minimum_boundary_pixels'],stored['minimum_rgb_boundary_contrast'])==(16,4,24))
        pixels.append({'view':name,'roi_id':identity,'visible_pixels':visible,'boundary_pixels':edges,'readable':passed})
        if passed:readable.add(identity)
    geometric={identity for i,identity in enumerate(ids)if child['index']['view_masks'][name]&(1<<i)}
    received=readable&geometric;new=received-covered;covered|=received
    check('receipt_readable_'+name,set(frame['receipt']['readable_roi_ids'])==readable)
    check('actual_step_coverage_'+name,set(frame['state_update']['new_roi_ids'])==new and set(frame['state_update']['covered_roi_ids'])==covered and set(frame['state_update']['unresolved_roi_ids'])==set(ids)-covered)
    totals['PNG_bytes']+=len(pbytes);totals['NPZ_bytes']+=len(nbytes);totals['array_payload_bytes']+=sum(x.nbytes for x in (color,depth,owner));totals['frame_metadata_bytes']+=len(mbytes)
    arrays.close()
check('36_pixel_evaluations',len(pixels)==child['metrics']['pixel_tests']==child['metrics']['pixel_test_attempts']==36)
check('covered_5_remaining1',len(covered)==5 and len(ids)==6 and set(child['final_state']['covered_roi_ids'])==covered and set(child['final_state']['unresolved_roi_ids'])==set(ids)-covered)
possible=set().union(*({identity for i,identity in enumerate(ids)if mask&(1<<i)}for mask in child['index']['view_masks'].values()))
check('geometric_pool_uncovered',set(child['final_state']['candidate_pool_uncovered_roi_ids'])==set(ids)-possible==set(ids)-covered)
repeat=child['repeat_query'];check('repeat_zero_new_raster',repeat['new_render_attempts']==0 and repeat['render_attempts_before']==repeat['render_attempts_after']==6 and repeat['state_before']==repeat['state_after']==child['final_state']and repeat['reuse_update']['reused']is True and repeat['next_view']is None)
for k,v in totals.items():check('total_'+k,v==child['metrics'][k])
check('source_audit_no_old_evidence',child['audit']['forbidden_old_evidence_reads']==0 and child['audit']['forbidden_old_writes']==0 and child['audit']['installed_before_dynamic_imports']is True)

# Static call order: quality validation succeeded before the rejected PID branch.
source=raw(SRC/'runner.py').decode('utf8');tree=ast.parse(source)
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='execute_one')
validate_line=next(n.lineno for n in ast.walk(fn)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='validate_run')
pid_line=next(n.lineno for n in ast.walk(fn)if isinstance(n,ast.Raise)and isinstance(n.exc,ast.Call)and n.exc.args and isinstance(n.exc.args[0],ast.Constant)and n.exc.args[0].value=='child_process_or_output_binding')
check('validation_precedes_PID_rejection',validate_line==150 and pid_line==153 and validate_line<pid_line)
check('failure_traceback_PID_line',f'line {pid_line},' in row['error']['traceback'])
stage_sums={}
for name,v in child['stages'].items():
    key=name.split('.',1)[1]if name.startswith('frame_')else name
    stage_sums[key]=stage_sums.get(key,0)+v['elapsed_ns']
timing={'primary_ns':row['elapsed_ns'],'Popen_to_wait_return_ns':row['process_exited_ns']-row['started_ns'],
        'after_wait_through_parent_validation_and_error_ns':row['closed_ns']-row['process_exited_ns'],
        'child_work_before_result_publication_ns':child['elapsed_before_result_publication_ns'],'result_publication_ns':pub['elapsed_ns'],
        'child_stages_ns':stage_sums,'unassigned_child_work_ns':child['elapsed_before_result_publication_ns']-sum(stage_sums.values()),
        'whole_recorded_batch_ns':batch['whole_batch_through_analysis_ns'],
        'common_parent_setup_ns':batch['common_parent_setup']['elapsed_ns'],
        'other_batch_ns':batch['whole_batch_through_analysis_ns']-row['elapsed_ns']-batch['common_parent_setup']['elapsed_ns']}
size={**totals,**{n+'_bytes':len(raw(run/f'{n}.json')) for n in ('RESULT','RESULT_PUBLICATION')},'TRACE_bytes':len(raw(run/'TRACE.jsonl'))}
result={'source_commit':'35e9321121e5ca8e9a8414dab859cd6361da4d9c','checks':len(checks),'failed':[x for x in checks if not x['passed']],
        'official_main_counts':counts(batch['rows']),'official_control_counts':counts(batch['controls']),'engine_record_status':child['status'],
        'render_attempts':len(intents),'render_returns':len(returns),'pixel_rows':len(pixels),'covered':len(covered),'finite_pool_uncovered':len(ids)-len(possible),
        'launch_pid':row['process_id'],'runtime_pid':child['process_id'],'ancestry':'not recorded; remains unknown',
        'trace_events':len(trace),'static_validate_line':validate_line,'static_PID_failure_line':pid_line,
        'timing':timing,'bytes':size,'pixels':pixels,'scope':'Independent retained JSON/TRACE/PNG/NPZ arithmetic, decoding and static AST only. No author validator, candidate execution, renderer, process qualification, formal benchmark, Blender/model/API.',
        'unmeasured':['B observation route','BACK64 pixel-feedback control','paired net time benefit','live launcher-runtime ancestry','exceptional interpreter cleanup']}
OUT.mkdir(parents=True,exist_ok=True)
for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUTS.json',inputs)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k]for k in ('checks','failed','official_main_counts','official_control_counts','engine_record_status','render_attempts','render_returns','covered','timing','bytes')},ensure_ascii=False))
