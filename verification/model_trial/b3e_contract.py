"""Common read-only question and arm-blind factual grading for finite B3e.

Truth is supplied by a separately bound native SAT/NumPy acquisition. This
module validates bindings and grades answers; it does not certify geometry or
create native truth from an engine report. Legacy rigid A/B/C stays separate.
"""
import copy,hashlib,json,math

ARMS=('ordinary_primary','fixed_core_compact','native_independent')
EXTREMA=('max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio')
STATES=('measured','collapsed','unknown')
FACT_FIELDS={'core_status','core_triangle_count','core_states','core_unknown_reasons','core_extrema'}
SCOPE=dict(scope='whole_original_triangles_not_clipped_integrals',damage_conclusion='not_determined',
    volume_conclusion='not_measured',total_task_speedup='not_established')
ANSWER_FIELDS={'task_id','answer_status'}|FACT_FIELDS|set(SCOPE)
COMMON_SYSTEM_PROMPT='''你处理只读三维事实任务，不移动、不保存、不改变任务核心。三角形属于核心，指当前世界闭框与完整原始三角凸包相交，包括点/边接触和塌缩。回答核心完整面数、measured/collapsed/unknown计数、unknown原因与四个完整核心的指标极值；指标仅覆盖measured/collapsed面。所有原始三角事实都是整面事实，不是裁剪积分，不证明损伤、体积、解剖或整任务加速。不能把primary/外围的计数或极值冒充core；摘要没有足够核心事实时，使用允许的共同原生补查工具；仍不足则报告insufficient_evidence并将未知字段置null。unknown指标和无法作答不同：已完整确认核心的unknown计数与原因仍可answered，核心指标在无可测成员时为null。不隐藏省略、失败或unknown。只返回一个符合给定答案schema的JSON对象，不加Markdown。'''
ANSWER_TEMPLATE=dict(task_id='<copy task_id>',answer_status='answered|insufficient_evidence|unsupported',core_status='observed|partial|empty|null',
    core_triangle_count=None,core_states={state:None for state in STATES},core_unknown_reasons=None,
    core_extrema={key:None for key in EXTREMA},**SCOPE)


def need(value,reason):
    if not value:raise ValueError('b3e_contract_'+reason)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def sha(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def identifier(value):return type(value) is str and 1<=len(value)<=128 and all(c.isascii() and (c.isalnum() or c in '_.:-') for c in value)


def validate_task(task):
    need(type(task) is dict and set(task)=={'schema','task_id','source_ref','core_region'} and task['schema']=='b3e-core-task-v1' and identifier(task['task_id']),'task')
    source=task['source_ref'];need(type(source) is dict and set(source)=={'scene_sha256','rig_object_id','mesh_object_id','frame'} and sha(source['scene_sha256']),'source')
    need(all(type(source[key]) is str and 1<=len(source[key])<=256 for key in ('rig_object_id','mesh_object_id')),'roles')
    frame=source['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and finite(frame['subframe']) and 0<=frame['subframe']<1,'frame')
    region=task['core_region'];need(type(region) is dict and set(region)=={'kind','coordinate_space','bounds'}
        and region['kind']=='closed_aabb' and region['coordinate_space']=='current_world_m','core_region')
    bounds=region['bounds'];need(type(bounds) is list and len(bounds)==2 and all(type(row) is list and len(row)==3 and all(finite(x) and abs(x)<=1e9 for x in row) for row in bounds)
        and all(bounds[0][axis]<bounds[1][axis] for axis in range(3)),'core_bounds')
    need(len(encoded(task))<=4096,'task_bytes');return copy.deepcopy(task)


def user_prompt(task,observation):
    task=validate_task(task);need(type(observation) is dict and len(encoded(observation))<=512*1024,'observation')
    return encoded(dict(task=task,observation=observation,answer_schema=ANSWER_TEMPLATE,
        common_native_supplement='If supplied by the runner, the same read-only native core query and budget is available to every condition; it cannot modify core/source.')).decode('utf8')


def validate_answer(answer,task_id):
    need(type(answer) is dict and set(answer)==ANSWER_FIELDS and answer['task_id']==task_id,'answer_binding_or_fields')
    need(answer['answer_status'] in ('answered','insufficient_evidence','unsupported'),'answer_status')
    need(answer['core_status'] in ('observed','partial','empty',None),'core_status')
    count=answer['core_triangle_count'];need(count is None or type(count) is int and 0<=count<=256,'core_count')
    states=answer['core_states'];need(states is None or type(states) is dict and set(states)==set(STATES)
        and all(value is None or type(value) is int and 0<=value<=256 for value in states.values()),'core_states')
    reasons=answer['core_unknown_reasons'];need(reasons is None or type(reasons) is dict and len(reasons)<=256
        and all(type(key) is str and 1<=len(key)<=256 and type(value) is int and 1<=value<=256 for key,value in reasons.items()),'unknown_reasons')
    extrema=answer['core_extrema'];need(extrema is None or type(extrema) is dict and set(extrema)==set(EXTREMA)
        and all(value is None or finite(value) and value>=0 for value in extrema.values()),'core_extrema')
    need(all(type(answer[key]) is str and len(answer[key])<=128 for key in SCOPE),'scope_fields')
    need(len(encoded(answer))<=8192,'answer_bytes');return copy.deepcopy(answer)


def bind_truth(task,facts,*,source_observation_sha256,independent_checker_sha256,acquisition_receipt_sha256):
    """Bind externally computed full-core facts; no self-qualified input flag."""
    task=validate_task(task);need(type(facts) is dict and set(facts)==FACT_FIELDS,'truth_fields')
    need(all(sha(value) for value in (source_observation_sha256,independent_checker_sha256,acquisition_receipt_sha256)),'truth_provenance')
    value=validate_answer(dict(task_id=task['task_id'],answer_status='answered',**facts,**SCOPE),task['task_id'])
    count=value['core_triangle_count'];states=value['core_states'];reasons=value['core_unknown_reasons'];extrema=value['core_extrema']
    need(type(count) is int and type(states) is dict and all(type(v) is int for v in states.values()) and count==sum(states.values()),'truth_counts_complete')
    need(type(reasons) is dict and sum(reasons.values())==states['unknown'],'truth_reasons_complete')
    need(value['core_status']==('empty' if not count else 'partial' if states['unknown'] else 'observed'),'truth_status')
    measurable=states['measured']+states['collapsed']
    need(type(extrema) is dict and (all(finite(v) and v>=0 for v in extrema.values()) if measurable
        else all(v is None for v in extrema.values())),'truth_metric_completeness')
    return dict(task_id=task['task_id'],task_sha256=digest(task),facts=copy.deepcopy(facts),source_observation_sha256=source_observation_sha256,
        independent_checker_sha256=independent_checker_sha256,acquisition_receipt_sha256=acquisition_receipt_sha256)


def _flat(facts):
    rows={key:facts[key] for key in ('core_status','core_triangle_count','core_unknown_reasons')}
    rows.update({'state_'+key:(facts['core_states'] or {}).get(key) for key in STATES})
    rows.update({'extrema_'+key:(facts['core_extrema'] or {}).get(key) for key in EXTREMA});return rows


def grade_answer(task,truth,answer,*,metric_atol=1e-9,metric_rtol=1e-9):
    task=validate_task(task);need(truth['task_id']==task['task_id'] and truth['task_sha256']==digest(task),'truth_task_binding')
    need(finite(metric_atol) and finite(metric_rtol) and 0<=metric_atol<=1e-9 and 0<=metric_rtol<=1e-9,'metric_tolerance')
    try:answer=validate_answer(answer,task['task_id'])
    except ValueError as exc:return dict(valid_answer=False,complete_correct=False,safe_incomplete=False,answerable=True,reason=str(exc),missing_fields=10,false_facts=None)
    expected=_flat(truth['facts']);actual=_flat(answer);missing=[];wrong=[];correct_unknown=0
    for key,target in expected.items():
        value=actual[key]
        if value is None and target is not None:missing.append(key)
        elif target is None:
            if value is not None:wrong.append(key)
            else:correct_unknown+=1
        elif key.startswith('extrema_'):
            if not finite(value) or not math.isclose(value,target,abs_tol=metric_atol,rel_tol=metric_rtol):wrong.append(key)
        elif type(value) is not type(target) or value!=target:wrong.append(key)
    scope_errors=[key for key,value in SCOPE.items() if answer[key]!=value]
    complete=answer['answer_status']=='answered' and not missing and not wrong and not scope_errors
    return dict(valid_answer=True,complete_correct=complete,safe_incomplete=answer['answer_status']!='answered' and not wrong and not scope_errors,
        answerable=True,missing_fields=len(missing),missing_field_names=missing,false_facts=len(wrong),false_fact_names=wrong,
        scope_errors=scope_errors,correct_unknown_fields=correct_unknown,requested_summary_omitted=bool(missing or wrong))


def grade_registered(registered,task_truths,answers):
    """Exact row/ID/binding matching; anonymous episode IDs expose no arm."""
    need(type(registered) is list and type(answers) is list and len(registered)==len(answers)>0,'row_count')
    ids=[row['episode_id'] for row in registered];actual=[row['episode_id'] for row in answers]
    need(all(identifier(value) for value in ids) and len(set(ids))==len(ids) and len(set(actual))==len(actual) and set(ids)==set(actual),'episode_ids')
    rows=[]
    for record in registered:
        task,truth=task_truths[record['task_id']];need(record['task_sha256']==digest(validate_task(task)),'registered_task_binding')
        response=next(row for row in answers if row['episode_id']==record['episode_id'])
        need(set(response)=={'episode_id','task_sha256','answer'} and response['task_sha256']==record['task_sha256'],'response_task_binding')
        rows.append(dict(episode_id=record['episode_id'],task_id=record['task_id'],grade=grade_answer(task,truth,response['answer'])))
    return dict(episodes=len(rows),complete_correct=sum(row['grade']['complete_correct'] for row in rows),
        answerable=len(rows),answerable_coverage=sum(row['grade']['complete_correct'] for row in rows)/len(rows),results=rows,
        model_tokens=None,model_cost_usd=None,model_measurement_reason='not_supplied_by_host_not_estimated',formal_statistical_comparison=False)
