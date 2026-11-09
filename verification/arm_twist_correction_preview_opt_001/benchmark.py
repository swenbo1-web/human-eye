"""One fixed old/new pure-preview comparison; run only in the granted window.

Plan: eight existing tasks, one warmup per implementation/task, five timed
pairs/task with alternating order, then one untimed trace per implementation/
task. Total preview calls are 16 warmups + 80 timed + 16 traced = 112.
Primary timing has no profiler or per-call wrapper. No post-hoc latency gate.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from cpu_verify import ROOT,HERE,OLD_COMMIT,OLD_SOURCE_SHA256,configure_imports,encoded,load_product,save,sha

SAMPLES_PER_STATE=5
WARMUPS_PER_IMPLEMENTATION_STATE=1
NUMERIC_OUTPUT_ATOL=1e-11
PLAN={'scope':'pure_preview_function_only_no_Blender_source_capture_MLP_training_network',
    'existing_effect_tasks':8,'warmups_per_implementation_state':WARMUPS_PER_IMPLEMENTATION_STATE,
    'paired_samples_per_state':SAMPLES_PER_STATE,'timed_order':'old/new when (case_index+sample_index) is even; new/old otherwise',
    'warmup_preview_calls':16,'timed_preview_calls':80,'untimed_trace_preview_calls':16,'total_preview_calls':112,
    'primary_profiler_enabled':False,'numeric_old_output_absolute_tolerance':NUMERIC_OUTPUT_ATOL,
    'new_only_certificate_field':'objective.minimum_loss_lower_bound; retain its value separately from comparison of old fields',
    'performance_adoption_gate':'none_added; report every state and observed tradeoff',
    'additional_retries_or_performance_trials':0,'baseline_commit':OLD_COMMIT}


def compare_output(old,new,path='result'):
    """Compare every old field except work; report any additive new metadata."""
    maximum=0.;additions=[]
    def visit(a,b,at):
        nonlocal maximum
        if isinstance(a,dict):
            if not isinstance(b,dict):raise AssertionError(at+':dict_required')
            for key in a:
                if key=='work' and at=='result':continue
                if key not in b:raise AssertionError(at+':missing_field:'+key)
                visit(a[key],b[key],at+'.'+key)
            additions.extend(at+'.'+key for key in b.keys()-a.keys())
        elif isinstance(a,list):
            if not isinstance(b,list) or len(a)!=len(b):raise AssertionError(at+':list_shape')
            for i,(x,y) in enumerate(zip(a,b)):visit(x,y,at+'['+str(i)+']')
        elif isinstance(a,(int,float)) and not isinstance(a,bool):
            if not isinstance(b,(int,float)) or isinstance(b,bool) or not math.isfinite(b):
                raise AssertionError(at+':finite_numeric_required')
            delta=abs(float(a)-float(b));maximum=max(maximum,delta)
            if delta>NUMERIC_OUTPUT_ATOL:raise AssertionError(at+':numeric_delta='+str(delta))
        elif a!=b:raise AssertionError(at+':value_changed')
    visit(old,new,path)
    objective=new.get('objective') or {}
    return {'old_fields_equivalent_excluding_work':True,'maximum_absolute_numeric_delta':maximum,
            'additive_new_fields':additions,
            'new_only_minimum_loss_lower_bound':deepcopy(objective.get('minimum_loss_lower_bound'))}


def trace_points(module,case):
    """Untimed actual call trace, separating bone transforms from frame maps."""
    calls=[];code=module._points.__code__;count=len(case['patch']['rest_vertices'])
    def profiler(frame,event,arg):
        if event=='call' and frame.f_code is code:
            vertices=frame.f_locals['vertices'];caller=frame.f_back.f_code.co_name
            size=len(vertices);full=size==count
            if full and caller in ('_lbs','preview_axial_redistribution'):role='full_vertex_bone_transform'
            elif full and caller=='_domain':role='full_vertex_rest_coordinate_frame'
            else:role='other_point_transform'
            calls.append({'caller':caller,'vertices':size,'role':role})
    if sys.getprofile() is not None:raise AssertionError('unexpected_existing_profiler')
    try:
        sys.setprofile(profiler)
        result=module.preview_axial_redistribution(case['patch'],case['task'])
    finally:sys.setprofile(None)
    bone=sum(call['role']=='full_vertex_bone_transform' for call in calls)
    return result,{'points_calls':calls,'full_vertex_bone_transforms':bone,
                   'profiling_in_primary_timing':False,'work':deepcopy(result['work'])}


def main():
    if len(sys.argv)!=2:raise ValueError('usage: benchmark.py NEW_OUTPUT_DIRECTORY')
    out=Path(sys.argv[1]).resolve()
    if out.exists():raise ValueError('new_output_directory_required')
    out.mkdir(parents=True);configure_imports()
    from verification.arm_twist_correction_preview_001.cases import make_cases
    from verification.arm_twist_correction_preview_001.test_preview import validate_result
    source=ROOT/'human_eye_plugin/arm_twist_correction.py';raw=source.read_bytes()
    old_raw=subprocess.check_output(['git','show',OLD_COMMIT+':human_eye_plugin/arm_twist_correction.py'],cwd=ROOT)
    assert sha(old_raw)==OLD_SOURCE_SHA256
    # The old function's shared matrix/parser dependencies must be the same.
    for filename in ('arm_twist_expert.py','rig_pose.py'):
        assert (ROOT/'human_eye_plugin'/filename).read_bytes()==subprocess.check_output(
            ['git','show',OLD_COMMIT+':human_eye_plugin/'+filename],cwd=ROOT)
    watched=[source,HERE/'cpu_verify.py',HERE/'benchmark.py']
    watched.extend(ROOT/'verification/arm_twist_correction_preview_001'/name for name in ('cases.py','oracle.py','test_preview.py'))
    watched.extend(ROOT/'human_eye_plugin'/name for name in ('arm_twist_expert.py','arm_twist_weights.py','rig_pose.py'))
    watched.append(ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz')
    hashes=lambda:{str(p):sha(p.read_bytes()) for p in watched}
    before=hashes();assert sha(raw)==before[str(source)]
    modules={'old':load_product('human_eye_plugin._arm_twist_correction_old_benchmark',old_raw,HERE/'OLD_FROM_GIT.py'),
             'new':load_product('human_eye_plugin.arm_twist_correction',raw,source)}
    cases=make_cases();assert len(cases)==8
    input_digests={case['case_id']:sha(encoded([case['patch'],case['task']])) for case in cases}
    save(out,'PLAN.json',PLAN)
    save(out,'INPUT_FREEZE.json',{'files':before,'old_module_sha256':sha(old_raw),'new_module_sha256':sha(raw),
        'old_source_origin':'git:'+OLD_COMMIT+':human_eye_plugin/arm_twist_correction.py',
        'case_inputs_sha256':input_digests,'both_implementations_receive_same_objects':True,
        'model_imports':'Parser module imported, no model initialized or called.'})
    record={'schema':'arm-correction-preview-fixed-paired-benchmark-v1','passed':False,'plan':PLAN,
        'old_module_sha256':sha(old_raw),'new_module_sha256':sha(raw),'warmups':[],'pairs':[],
        'per_case':[],'untimed_point_traces':[],
        'actual_calls':{'warmup':0,'timed':0,'untimed_trace':0,'model':0,'Blender':0,'source_capture':0,'training':0,'external_API':0},
        'limitations':['Five pairs per fixed state; this is not a latency distribution or model-task speed guarantee.',
            'Each timing encloses the complete pure preview call only; imports, fixture construction, independent checks and source capture are outside.',
            'Warmup and untimed profiler calls are explicitly additional, not silently included in the timed denominator.',
            'No adoption threshold is inferred after seeing timings; slower cases remain in the output.',
            'Fewer vertex/bone transforms do not imply a 33 percent complete preview or full task speedup.']}
    error=None;started=time.perf_counter_ns()
    def forbidden(*args,**kwargs):raise AssertionError('No network or child process during preview benchmark')
    try:
        with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
            for index,case in enumerate(cases):
                for label in (('old','new') if index%2==0 else ('new','old')):
                    record['actual_calls']['warmup']+=1
                    result=modules[label].preview_axial_redistribution(case['patch'],case['task'])
                    validate_result(case,result)
                    record['warmups'].append({'case_id':case['case_id'],'implementation':label,
                        'status':result['status'],'work':deepcopy(result['work']),'output_sha256':sha(encoded(result))})
                for sample in range(SAMPLES_PER_STATE):
                    order=('old','new') if (index+sample)%2==0 else ('new','old')
                    pair={'case_id':case['case_id'],'sample_index':sample,'order':list(order),'measurements':{}}
                    record['pairs'].append(pair)
                    results={}
                    for label in order:
                        record['actual_calls']['timed']+=1
                        call_started=time.perf_counter_ns()
                        result=modules[label].preview_axial_redistribution(case['patch'],case['task'])
                        elapsed=time.perf_counter_ns()-call_started
                        results[label]=result
                        pair['measurements'][label]={'elapsed_ns':elapsed,'status':result['status'],
                            'work':deepcopy(result['work']),'output_sha256':sha(encoded(result))}
                    pair['output_comparison']=compare_output(results['old'],results['new'])
                    for result in results.values():validate_result(case,result)
                    assert input_digests[case['case_id']]==sha(encoded([case['patch'],case['task']]))
                    pair['new_minus_old_ns']=pair['measurements']['new']['elapsed_ns']-pair['measurements']['old']['elapsed_ns']
            # Trace only after every primary timing is complete.
            for case in cases:
                expected_old=0 if case['expected_status']=='not_applicable' else 3 if case['expected_status']=='no_op' else 6
                expected_new=0 if case['expected_status']=='not_applicable' else 3 if case['expected_status']=='no_op' else 4
                for label,expected in (('old',expected_old),('new',expected_new)):
                    record['actual_calls']['untimed_trace']+=1
                    result,trace=trace_points(modules[label],case);validate_result(case,result)
                    trace.update(case_id=case['case_id'],implementation=label)
                    record['untimed_point_traces'].append(trace)
                    assert trace['full_vertex_bone_transforms']==expected,trace
                    if label=='new':assert result['work']['full_vertex_bone_transforms']==expected
        for case in cases:
            pairs=[pair for pair in record['pairs'] if pair['case_id']==case['case_id']]
            old_values=[pair['measurements']['old']['elapsed_ns'] for pair in pairs]
            new_values=[pair['measurements']['new']['elapsed_ns'] for pair in pairs]
            old_median=statistics.median(old_values);new_median=statistics.median(new_values)
            record['per_case'].append({'case_id':case['case_id'],'status':case['expected_status'],
                'old_ns':old_values,'new_ns':new_values,'old_median_ns':old_median,'new_median_ns':new_median,
                'new_minus_old_median_ns':new_median-old_median,'relative_change':new_median/old_median-1.,
                'new_faster_in_pairs':sum(pair['new_minus_old_ns']<0 for pair in pairs),
                'old_work':pairs[0]['measurements']['old']['work'],'new_work':pairs[0]['measurements']['new']['work']})
        assert record['actual_calls']['warmup']==16 and record['actual_calls']['timed']==80 and record['actual_calls']['untimed_trace']==16
        record['passed']=True
    except BaseException as exc:
        error=exc;record['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        record['benchmark_body_elapsed_ns']=time.perf_counter_ns()-started
        record['after_sha256']=hashes();record['inputs_sources_unchanged']=before==record['after_sha256']
        record['all_case_inputs_unchanged']=all(input_digests[case['case_id']]==sha(encoded([case['patch'],case['task']])) for case in cases)
        record['passed']=bool(record['passed'] and record['inputs_sources_unchanged'] and record['all_case_inputs_unchanged'])
        save(out,'RESULT.json',record)
        print(json.dumps({'passed':record['passed'],'actual_calls':record['actual_calls'],
            'per_case':record['per_case'],'result':str(out/'RESULT.json')}))
    if error is not None:raise error
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':main()
