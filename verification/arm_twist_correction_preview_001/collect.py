"""One fixed eight-task CPU collection; diagnostics cannot select the solution."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import types

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
out=Path(sys.argv[1]).resolve()
if out.exists():raise ValueError('new_output_directory_required')
out.mkdir(parents=True)
names=['human_eye_plugin/'+name for name in ('arm_twist_correction.py','arm_twist_source.py',
    'arm_twist_expert.py','arm_twist_weights.py','rig_pose.py')]
names+=['verification/m6_arm_expert_001/'+name for name in ('synthetic.py','run_01/dataset.json.gz')]
names+=['verification/arm_twist_correction_preview_001/'+name for name in
        ('cases.py','oracle.py','test_preview.py','collect.py')]
hashes=lambda:{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
before=hashes();source=ROOT/'human_eye_plugin/arm_twist_correction.py';raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()==before['human_eye_plugin/arm_twist_correction.py']
spec=importlib.util.spec_from_file_location('human_eye_plugin.arm_twist_correction',source)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
exec(compile(raw,str(source),'exec'),module.__dict__)
from verification.arm_twist_correction_preview_001.cases import make_cases,joint_weight_proof
from verification.arm_twist_correction_preview_001.test_preview import validate_result
from human_eye_plugin.arm_twist_expert import get_default_expert,prepare_patch

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def save(name,value):
    (out/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')

cases=make_cases()
save('INPUT_FREEZE.json',{'files':before,'cases':[{'case_id':case['case_id'],'asset_id':case['asset_id'],
    'patch_sha256':digest(case['patch']),'task_sha256':digest(case['task']),'task':case['task'],
    'expected_status':case['expected_status'],'oracle_only_theta_deg':case['theta_deg'],
    'oracle_only_u_deg':case['expected_u_deg'],'oracle_only_before_j':case['expected_before_j'],
    'oracle_only_after_j':case['expected_after_j']} for case in cases],
    'candidate_call_arguments':'case.patch and case.task only; metadata/known answers are oracle-only'})
result={'schema':'arm-correction-preview-fixed-cpu-v1','passed':False,'source_sha256':before,
    'cases':[],'work':{'preview_calls':0,'model_initializations':0,'model_static_preparations':0,
        'model_calls':0,'product_setters':0,'external_api_calls':0,'training_calls':0},
    'learning_benefit':'not_demonstrated; geometry solves the candidate, model does not change it'}
started=time.perf_counter_ns();error=None
try:
    model_started=time.perf_counter_ns();model=get_default_expert()
    result['model_load_elapsed_ns']=time.perf_counter_ns()-model_started
    result['work']['model_initializations']+=1
    for case in cases:
        patch,task=case['patch'],case['task'];frozen=digest([patch,task])
        record={'case_id':case['case_id'],'asset_id':case['asset_id'],'input_sha256':frozen}
        result['cases'].append(record);preview_started=time.perf_counter_ns()
        result['work']['preview_calls']+=1
        preview=module.preview_axial_redistribution(patch,task)
        record['preview_elapsed_ns']=time.perf_counter_ns()-preview_started
        record['preview']=preview
        record['independent_geometry']=validate_result(case,preview)
        record['joint_weight_proof']=joint_weight_proof(patch)
        record['input_unchanged']=frozen==digest([patch,task]);assert record['input_unchanged']
        observations={'role':'frozen_diagnostic_only_not_solver_or_acceptance','before':None,'after':None}
        if preview['status']!='not_applicable':
            preparation_started=time.perf_counter_ns();prepared=prepare_patch(patch)
            observations['static_prepare_elapsed_ns']=time.perf_counter_ns()-preparation_started
            result['work']['model_static_preparations']+=1
            poses=[bone['pose_matrix'] for bone in patch['bone_chain']]
            call_started=time.perf_counter_ns();result['work']['model_calls']+=1
            observations['before']=prepared.analyze(patch['current_vertices'],poses,model=model)
            observations['before_elapsed_ns']=time.perf_counter_ns()-call_started
            if preview['status']=='candidate':
                candidate=preview['candidate'];call_started=time.perf_counter_ns()
                result['work']['model_calls']+=1
                observations['after']=prepared.analyze(candidate['current_vertices'],candidate['pose_matrices'],model=model)
                observations['after_elapsed_ns']=time.perf_counter_ns()-call_started
            elif preview['status']=='no_op':
                observations['after']=deepcopy(observations['before'])
                observations['after_reused_without_model_call']=True
        record['model_observation']=observations
    assert len(result['cases'])==8 and result['work']['model_calls']==11
    result['passed']=True
except BaseException as exc:
    error=exc;result['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
finally:
    result['elapsed_ns']=time.perf_counter_ns()-started
    result['source_sha256_after']=hashes();result['inputs_sources_unchanged']=before==result['source_sha256_after']
    result['passed']=result['passed'] and result['inputs_sources_unchanged']
    save('RESULT.json',result)
    print(json.dumps({'passed':result['passed'],'cases':len(result['cases']),'work':result['work'],
                      'result':str(out/'RESULT.json')}))
if error is not None:raise error
