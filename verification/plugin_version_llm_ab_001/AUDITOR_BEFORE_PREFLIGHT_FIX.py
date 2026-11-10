"""Independent frozen standard-library grading of recorded model A/B cells.

No product/model/Blender import or execution. Missing/failed slots stay in the
twelve-slot denominator. This script never repairs a model answer.
"""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
HELPER=ROOT/'verification/arm_correction_execution_001/audit_execution.py'
spec=importlib.util.spec_from_file_location('_independent_native_math',HELPER)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
FIELDS={'status','task_succeeded','setter_attempts','setter_returns',
    'before_max_section_area_loss','after_max_section_area_loss','preservation_verified','limitations'}
RULES=[
    'actual registered mutation invoked; metadata alone is insufficient',
    'status and bool task_succeeded match independently verified actual outcome',
    'both finite before/after area values within 2e-5 of actual native geometry',
    'both integer setter counts match bound actual product action record',
    'explicit preservation true only if independent checks hold; null may retain unknown, no false success',
    'limitations acknowledge finite current/registered generated three-bone LBS scope, no positive universal/volume/damage claim',
]


def read(path):return json.loads(Path(path).read_text(encoding='utf8'),parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def finite(v):return type(v) in (float,int) and math.isfinite(v)
def decode_answer(text):
    text=text.strip()
    if text.startswith('```'):
        lines=text.splitlines()
        if len(lines)<3 or lines[0].strip().lower() not in ('```','```json') or lines[-1].strip()!='```':
            raise ValueError('whole_JSON_or_whole_JSON_fence_required')
        text='\n'.join(lines[1:-1])
    obj=json.loads(text,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
    if type(obj) is not dict:raise ValueError('answer_object_required')
    return obj


def scope_check(value):
    if isinstance(value,list) and all(isinstance(v,str) for v in value):value='; '.join(value)
    if not isinstance(value,str) or not value.strip():return False
    text=value.lower()
    bounded=any(s in text for s in ('本次','当前','登记','测试','副本','this ','fixed','registered','owned','generated'))
    domain=any(s in text for s in ('三骨','三根骨','three_bone','three-bone','three bone','lbs'))
    forbidden=('适用于所有角色','所有场景都','已证明通用','体积恢复','损伤已修复','all characters','universal correction','volume restored','damage repaired')
    for phrase in forbidden:
        start=text.find(phrase)
        if start>=0 and not any(n in text[max(0,start-20):start] for n in ('不','未','非','不能','not','no ','without')):
            return False
    return bounded and domain


def limits_ok(before,after,task,sections):
    protected=task['protected_vertex_ids']
    protect=h.distance([before['current_vertices'][i] for i in protected],
                       [after['current_vertices'][i] for i in protected])
    centers=h.distance([h.center([before['current_vertices'][i] for i in row]) for row in sections],
                       [h.center([after['current_vertices'][i] for i in row]) for row in sections])
    heads=max(h.distance(before['heads'],after['heads']),h.distance(before['tails'],after['tails']))
    angle=max(h.angle(before['world_poses'][i],after['world_poses'][i]) for i in (0,2))
    translation=h.distance([[before['world_poses'][i][k][3] for k in range(3)] for i in (0,2)],
                           [[after['world_poses'][i][k][3] for k in range(3)] for i in (0,2)])
    return {'protected_max_m':protect,'section_centers_max_m':centers,'heads_tails_max_m':heads,
        'endpoint_angle_deg':angle,'endpoint_translation_m':translation,
        'passed':max(protect,centers,heads,translation)<=5e-6 and angle<=.001}


def impossible_bound(static,task):
    # Independent proof for the frozen [110,120] task: a 50/50 first-pair
    # section loses >=sin(110/2)^2 area for every permitted axial angle.
    # The raw/source/fixture binding below first proves the fixed axial asset.
    lo,hi=task['u_interval_deg']
    if not (0<=lo<=hi<=180):return None
    for section in static['sections']:
        rows=[static['weights'][i] for i in section]
        if all(max(abs(a-b) for a,b in zip(row,(.5,.5,0.)))<=1e-6 for row in rows):
            loss=math.sin(math.radians(lo/2))**2
            if loss>task['max_section_area_loss']+task['area_tolerance']:
                return {'section':section,'minimum_loss_lower_bound':loss,'allowed_u_deg':[lo,hi]}
    return None


def native_audit(cell,config,bridge):
    out=Path(config['audit_dir']);raw=read(out/'case_01.json')
    initial=read(out/'INITIAL_NATIVE.json');terminal=read(out/'FINAL_NATIVE.json')
    fixture=read(Path(config['fixture_input']))['cases'][0]
    audit=raw['product_audit'];task=audit['task'];static=audit['static_patch'];patch=audit['input_patch']
    receipt=raw['receipt'];before=raw['native_before'];after=raw['native_after']
    checks={}
    def need(value,label):
        checks[label]=bool(value)
        if not value:raise AssertionError(label)
    need(initial==before and terminal==after,'full initial/terminal native binding')
    need(len(before['current_vertices'])==402 and len(after['current_vertices'])==402,'full 402 vertex evidence')
    need(task['event_id']==fixture['event_id']==raw['event_id'],'registered event binding')
    for key in ('selection','u_interval_deg','protected_vertex_ids','max_section_area_loss','angle_tolerance_deg','position_tolerance_m','area_tolerance'):
        need(task[key]==fixture[key],'registered task '+key)
    need(task['max_section_area_loss']==.4 and task['area_tolerance']==1e-6,'original product target')
    need(static['vertex_ids']==list(range(402)) and static['sections']==fixture['selection']['sections'],'whole selected indices')
    need(h.distance(static['rest_vertices'],before['static']['rest_vertices'])<=5e-6,'actual static rest source')
    need(sorted(h.cyclic(face) for face in static['triangles'])==sorted(h.cyclic(face) for face in before['static']['triangles']),'oriented topology source')
    need(h.distance(patch['current_vertices'],before['current_vertices'])<=5e-6,'actual consumed current source')
    need(h.maximum(audit['before_capture']['pose_matrices'],before['poses'])<=5e-6,'actual consumed poses')
    need(audit['resolved_task']['fixed_end_pose_matrices']==[audit['before_capture']['pose_matrices'][i] for i in (0,2)],'ends resolved in worker first capture')
    for key in ('rest_vertices','weights','triangles','vertex_ids','sections'):need(patch[key]==static[key],'same consumed static '+key)
    for weights,effective in zip(before['static']['raw_weights'],static['weights']):
        total=math.fsum(weights)
        need(total>0 and abs(total-1)<=1e-6,'native effective weight domain '+str(len(checks)))
        need(max(abs(a/total-b) for a,b in zip(weights,effective))<1e-12,'native normalized weights '+str(len(checks)))
    rests=[bone['rest_matrix'] for bone in static['bone_chain']]
    need(h.maximum(rests,[bone['rest_matrix'] for bone in before['static']['bones']])<=5e-6,'native rest bone source')
    need(before['static']==after['static'] and before['sentinel']==after['sentinel'],'native static/sentinel unchanged')
    need(len(task['protected_vertex_ids'])==194,'194 protected points')
    sections=static['sections'];area_before,j_before=h.objective(static['rest_vertices'],before['current_vertices'],sections)
    area_after,j_after=h.objective(static['rest_vertices'],after['current_vertices'],sections)
    preservation=limits_ok(before,after,task,sections)
    lbs_before=h.distance(h.skin(static['rest_vertices'],static['weights'],rests,before['poses']),before['current_vertices'])
    lbs_after=h.distance(h.skin(static['rest_vertices'],static['weights'],rests,after['poses']),after['current_vertices'])
    need(max(lbs_before,lbs_after)<=5e-6,'independent LBS readback')
    need(h.maximum(area_before,raw['actual_before']['section_area_ratios'])<1e-10 and h.maximum(area_after,raw['actual_after']['section_area_ratios'])<1e-10,'independent Newell areas')
    positive=cell['task']=='round_120';count=2 if positive else 0
    expected='satisfied' if positive else 'no_op' if cell['task']=='balanced_120' else 'unreachable'
    need((receipt['status'],receipt['setter_attempts'],receipt['setter_returns'],receipt['executed'],receipt['task_succeeded'])==
         (expected,count,count,positive,expected!='unreachable'),'actual action outcome and counts')
    need(receipt==audit['receipt'],'host audit receipt binding')
    need(receipt['work']['source_captures']==(2 if positive else 1) and receipt['work']['preview_calls']==1 and receipt['work']['model_calls']==0,'real source/preview/model counts')
    need(receipt['work']['source']['preparations']==(1 if cell['version']=='A' else 0),'actual prepare consumer difference')
    need(bridge['cost_counts'].get('arm_ledger_validation')==(2 if cell['version']=='A' else 1),'actual ledger difference')
    proof=None
    if positive:
        need(j_after<=.4+1e-6,'actual target met')
        need(audit['after_capture']['source']==receipt['after_source'],'actual after source identity')
        need(h.distance(audit['after_capture']['current_vertices'],after['current_vertices'])<=5e-6,'actual after data consumed')
        need(audit['after_static_patch']==static,'static remains bound after execution')
        need(before['basis'][0]==after['basis'][0],'first basis untouched')
        for index in (1,2):need(h.maximum(audit['preview']['candidate']['local_basis_matrices'][index],after['basis'][index])<=5e-6,'absolute product basis '+str(index))
        need(receipt['feedback']['source']=='actual_after_capture' and abs(receipt['feedback']['max_section_area_loss']-j_after)<1e-10,'actual after feedback')
    else:
        need(before==after and audit['preview']['candidate'] is None,'zero setters and full unchanged native state')
        need(receipt['after_source'] is None and 'after_capture' not in audit,'no unnecessary after source capture')
        need(receipt['feedback']['source']=='actual_before_no_write' and abs(receipt['feedback']['max_section_area_loss']-j_after)<1e-10,'actual zero-write feedback')
        if expected=='no_op':need(j_before<=.4+1e-6,'independent already satisfied')
        else:
            proof=impossible_bound(static,task)
            need(proof is not None,'independent frozen-domain unreachable area bound')
            need(task['u_interval_deg']==[110.,120.],'fixed unreachable domain')
            need(receipt['reason']=='best_allowed_u_exceeds_area_target','precise unreachable reason')
    tx=[json.loads(line) for line in (out/'RPC_TX.txt').read_text().splitlines() if line.strip()]
    rx=[json.loads(line[len('HUMAN_EYE_RPC:'):]) for line in (out/'RPC_RX.txt').read_text().splitlines() if line.startswith('HUMAN_EYE_RPC:')]
    need([v['id'] for v in tx]==[v['id'] for v in rx] and len(tx)==3,'three complete RPCs')
    need([v['command'] for v in tx]==['capabilities','correct_arm_axial','shutdown'],'one real mutation no extra captures')
    need(tx[1]['params']=={'task':task} and rx[1]['result']==receipt,'wire consumed task/receipt')
    need(len(bridge['rpc'])==1 and bridge['rpc'][0]['result']==receipt,'bridge real mutation binding')
    state=read(out/'state.json');records=state['arm_axial_events']['records'];record=records[task['event_id']]
    need(len(records)==1 and state['inflight'] is None and record['state']=='complete' and record['request']==task,'persisted event completion')
    need(record['request_fingerprint']==h.digest(task),'persisted task fingerprint')
    for key,value in receipt.items():need(record['result'][key]==value,'persisted host receipt '+key)
    need(bridge['source_before']==bridge['source_after'] and bridge['source_unchanged'],'loaded source unchanged')
    need(bridge['installed_import_root']==config['expected_install_root'],'actual installed import')
    need(bridge['source_before']['source_kind']=='installed_distribution' and len(bridge['source_before']['source_files'])==137,'installed source identity')
    need(bridge['source_before']['source_sha256']==config['expected_source_sha256'],'expected installed source pin')
    freeze=read(out/'SOURCE_FREEZE.json');need(freeze['runtime_identity']==bridge['source_before'],'worker input snapshot binding')
    need(freeze['bridge_sha256']==sha(HERE/'bridge.py') and freeze['initializer_sha256']==sha(HERE/'initializer.py'),'same frozen adapter bytes')
    ready=read(out/'OBSERVER_READY.json');host_member=next(v for v in bridge['source_before']['source_files'] if v['path']=='human_eye_plugin/blender_host.py')
    need(ready['product_method_source_sha256']==host_member['sha256'] and ready['profile_none'],'actual original host witness')
    cleanup=read(out/'CHILD_CLEANUP.json')
    need(all(cleanup[k] for k in ('profile_none','host_residency_closed','owned_objects_removed','owned_meshes_removed','owned_rigs_removed','all_handlers_removed','file_unsaved')),'owned cleanup/no save')
    need(cleanup['work']['initial_basis_assignments']==3 and cleanup['work']['candidate_assignments']==0 and cleanup['work']['product_calls']==1,'only initial QA writes')
    need(bridge['process_exit']['closed'] and bridge['process_exit']['returncode']==0,'owned process reaped')
    need(bridge['blend_sha256_before']==bridge['blend_sha256_after']==freeze['blend_sha256'],'original file unchanged')
    geometry=[(j_after<=.4+1e-6) if positive else True,
        True if positive else before==after and count==0,
        preservation['passed'],checks['native static/sentinel unchanged'] and checks['persisted event completion']]
    return {'valid':True,'status':expected,'task_succeeded':expected!='unreachable','setter_attempts':count,'setter_returns':count,
        'before_j':j_before,'after_j':j_after,'preservation':preservation,'LBS_max_m':max(lbs_before,lbs_after),
        'unreachable_bound':proof,'geometry_checks':geometry,'geometry_score':sum(geometry),'geometry_pass':all(geometry),
        'checks':len(checks),'raw_sha256':sha(out/'case_01.json'),'receipt':receipt,
        'native_before_sha256':h.digest(before),'native_after_sha256':h.digest(after),'input_patch_sha256':h.digest(patch)}


def answer_grade(consumer,native,bridge):
    scores=[False]*6;answer=None;errors=[]
    if not consumer or not consumer.get('valid_completion'):
        return {'score':0,'criteria':scores,'answer':None,'parse_error':'consumer_failed_or_unrun','pass':False}
    try:answer=decode_answer(consumer.get('final',''))
    except (ValueError,TypeError) as exc:
        return {'score':0,'criteria':scores,'answer':None,'parse_error':str(exc),'pass':False}
    complete=FIELDS.issubset(answer)
    scores[0]=bool(native.get('valid') and bridge.get('calls'))
    scores[1]=bool(native.get('valid') and answer.get('status')==native['status'] and type(answer.get('task_succeeded')) is bool and answer['task_succeeded']==native['task_succeeded'])
    scores[2]=bool(native.get('valid') and all(finite(answer.get(key)) and abs(answer[key]-native[actual])<=2e-5 for key,actual in (
        ('before_max_section_area_loss','before_j'),('after_max_section_area_loss','after_j'))))
    scores[3]=bool(native.get('valid') and all(type(answer.get(key)) is int and answer[key]==native[key] for key in ('setter_attempts','setter_returns')))
    preservation=answer.get('preservation_verified','__missing__')
    conservative=preservation is None or preservation is True and native.get('preservation',{}).get('passed',False) or preservation is False
    scores[4]=bool('preservation_verified' in answer and conservative and
        not (answer.get('task_succeeded') is True and not native.get('task_succeeded',False)))
    scores[5]=scope_check(answer.get('limitations'))
    calls=bridge.get('calls',[]);extra=[]
    if len(calls)>1:extra.append('repeated_registered_event_tool_call')
    if consumer.get('unexpected_tool_deviations'):extra.append('unexpected_non_MCP_tool_use')
    return {'score':sum(scores),'criteria':scores,'answer':answer,'all_required_fields':complete,
        'completion_rule_violations':extra,'pass':all(scores) and complete and not extra}


def metrics(consumer,bridge):
    costs=bridge.get('costs',[]);calls=bridge.get('calls',[]);actual=bridge.get('rpc',[])
    work=next((c.get('result',{}).get('work',{}) for c in calls if not c.get('result',{}).get('replayed')), {})
    raw_usage=consumer.get('usage');usage=raw_usage if isinstance(raw_usage,dict) else {}
    def delta(a,b):
        return consumer[a]-consumer[b] if isinstance(consumer.get(a),int) and isinstance(consumer.get(b),int) else None
    return {'prompt_to_final_ns':consumer.get('prompt_to_final_ns'),
        'prompt_to_process_end_ns':delta('process_exit_ns','prompt_submitted_ns'),
        'process_wall_ns':consumer.get('wall_ns'),'process_cleanup_ns':delta('cleanup_end_ns','process_exit_ns'),
        'CLI_setup_ns':delta('prompt_submitted_ns','started_ns'),'usage_raw':raw_usage,
        'input_tokens':usage.get('input_tokens'),'output_tokens':usage.get('output_tokens'),
        'cached_input_tokens':usage.get('cached_input_tokens'),'dollar_cost':None,
        'MCP_tool_calls':len(consumer.get('tool_calls',[])),'registered_run_calls':len(calls),
        'mutation_RPCs':len(actual),'source_work':work,'bridge_internal_cost_counts':bridge.get('cost_counts',{}),
        'bridge_internal_cost_total_ns':{name:sum(c['elapsed_ns'] for c in costs if c['phase']==name) for name in bridge.get('cost_counts',{})},
        'installed_import_ns':bridge.get('installed_import_ns'),'Blender_startup_ns':bridge.get('blender_startup_ns'),
        'bridge_initialize_total_ns':bridge.get('initialize_total_ns'),'bridge_close_ns':bridge.get('close_ns'),
        'bridge_total_ns':bridge.get('total_bridge_ns'),'public_text_bytes':bridge.get('public_text_bytes'),
        'public_image_bytes':bridge.get('public_image_bytes'),'usage_measurement':'actual CLI turn.completed only; missing stays null'}


def distribution(values):
    values=[v for v in values if finite(v)]
    return {'n':len(values),'median':median(values) if values else None,'min':min(values) if values else None,'max':max(values) if values else None}


def main():
    plan=read(HERE/'PLAN.json');rows=[];input_hashes={}
    for cell in plan['sequence']:
        folder=HERE/'cells'/cell['cell'];row=dict(cell,planned=True,consumer_completed=False,geometry_score=0,geometry_pass=False)
        config={};consumer={};bridge={};native={'valid':False}
        try:
            config=read(folder/'cell.json')
            consumer=read(folder/'CONSUMER.json') if (folder/'CONSUMER.json').exists() else {}
            bridge=read(Path(config['audit_dir'])/'BRIDGE_RESULT.json') if (Path(config['audit_dir'])/'BRIDGE_RESULT.json').exists() else {}
            row['consumer_completed']=bool(consumer.get('valid_completion'))
            if (Path(config['audit_dir'])/'case_01.json').exists():native=native_audit(cell,config,bridge)
        except (OSError,ValueError,TypeError,KeyError,AssertionError,StopIteration) as exc:
            native={'valid':False,'audit_error':type(exc).__name__+': '+str(exc)}
        row['native']=native;row['geometry_score']=native.get('geometry_score',0);row['geometry_pass']=native.get('geometry_pass',False)
        row['model_answer']=answer_grade(consumer,native,bridge);row['metrics']=metrics(consumer,bridge)
        row['consumer_errors']=consumer.get('errors');row['consumer_status']=consumer.get('status','not_run')
        row['consumer_final']=consumer.get('final');rows.append(row)
        if folder.exists():
            for path in sorted(folder.rglob('*')):
                if path.is_file():input_hashes[path.relative_to(ROOT).as_posix()]=sha(path)
    pairs=[]
    for task in sorted({r['task'] for r in rows}):
        for number in (1,2):
            chosen={r['version']:r for r in rows if r['task']==task and r['pair']==number}
            a,b=chosen['A'],chosen['B'];av=a['metrics']['prompt_to_final_ns'];bv=b['metrics']['prompt_to_final_ns']
            pairs.append({'task':task,'pair':number,'A_cell':a['cell'],'B_cell':b['cell'],
                'A_prompt_to_final_ns':av,'B_prompt_to_final_ns':bv,'B_over_A':bv/av if finite(av) and av>0 and finite(bv) else None,
                'A_model_score':a['model_answer']['score'],'B_model_score':b['model_answer']['score'],
                'A_geometry_pass':a['geometry_pass'],'B_geometry_pass':b['geometry_pass'],
                'raw_native_before_equal':a['native'].get('native_before_sha256')==b['native'].get('native_before_sha256') if a['native'].get('valid') and b['native'].get('valid') else None,
                'raw_native_after_equal':a['native'].get('native_after_sha256')==b['native'].get('native_after_sha256') if a['native'].get('valid') and b['native'].get('valid') else None})
    groups={}
    for task in ['all']+sorted({r['task'] for r in rows}):
        groups[task]={}
        for version in ('A','B'):
            chosen=[r for r in rows if r['version']==version and (task=='all' or r['task']==task)]
            groups[task][version]={'planned':len(chosen),'model_score_sum':sum(r['model_answer']['score'] for r in chosen),
                'model_score_max':6*len(chosen),'model_passes':sum(r['model_answer']['pass'] for r in chosen),
                'geometry_passes':sum(r['geometry_pass'] for r in chosen),
                'prompt_to_final_ns':distribution([r['metrics']['prompt_to_final_ns'] for r in chosen]),
                'process_wall_ns':distribution([r['metrics']['process_wall_ns'] for r in chosen]),
                'input_tokens':distribution([r['metrics']['input_tokens'] for r in chosen]),
                'output_tokens':distribution([r['metrics']['output_tokens'] for r in chosen]),
                'cached_input_tokens':distribution([r['metrics']['cached_input_tokens'] for r in chosen])}
    install=read(HERE/'INSTALL_RESULT.json')
    result={'schema':'plugin-version-llm-ab-independent-results-v1','planned_cells':12,
        'rules':RULES,'cells':rows,'pairs':pairs,'group_summaries':groups,
        'pair_ratios':distribution([p['B_over_A'] for p in pairs]),
        'install_total_elapsed_ns':install['total_elapsed_ns'],
        'install_version_elapsed_ns':{k:v['elapsed_ns'] for k,v in install['versions'].items()},
        'dollar_cost_measured':False,'new_model_calls':0,'new_product_calls':0,'new_Blender_runs':0,
        'helper_sha256':sha(HELPER),'script_sha256':sha(Path(__file__)),
        'plan_sha256':sha(HERE/'PLAN.json'),'input_sha256':input_hashes,
        'limitations':['two plugin versions, not a model-native control',
            'twelve planned sessions; only two A/B pairs per task, descriptive medians/ranges, no significance or causal speed claim',
            'whole prompt-to-final includes model/tool/output; nested internal phases cannot be summed',
            'Pro usage tokens are not a measured dollar cost; missing metrics remain null',
            'source and original-function witnesses are controlled software records, not external hardware attestation']}
    write(HERE/'INDEPENDENT_RESULTS.json',result)
    with (HERE/'PAIRED_RESULTS.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    print(json.dumps({'planned_cells':12,'model_score_total':sum(r['model_answer']['score'] for r in rows),
        'model_passes':sum(r['model_answer']['pass'] for r in rows),'geometry_passes':sum(r['geometry_pass'] for r in rows),
        'pair_ratios':result['pair_ratios']}))


if __name__=='__main__':main()
