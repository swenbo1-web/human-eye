"""Independent stdlib audit of fixed owned-entry evidence; no product imports.

Reads the completed run only. It does not start Blender, invoke a preview,
import the author's geometric oracle, or submit any command to the worker.
"""
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUN=HERE/'native_01'
OUT=HERE/'INDEPENDENT_NATIVE_AUDIT.json'
GATES={'angle_deg':.001,'position_m':5e-6,'area_error':2e-5}
FIXED=(('round_120','satisfied',120.,120.),('round_minus150','satisfied',-150.,-150.),
       ('elliptic_120','satisfied',120.,120.),('elliptic_minus150','satisfied',-150.,-150.),
       ('balanced_120','no_op',120.,60.),('small_twist_30','no_op',30.,30.),
       ('unreachable_120','unreachable',120.,120.),('noncoaxial','not_applicable',None,None))
checks=0

def need(value,label):
    global checks
    checks+=1
    if not value:raise AssertionError(label)

def reject(value):raise ValueError('Nonfinite JSON constant: '+value)
def read(path):return json.loads(Path(path).read_text(encoding='utf8'),parse_constant=reject)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def norm(v):return math.sqrt(math.fsum(x*x for x in v))
def sub(a,b):return [x-y for x,y in zip(a,b)]
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def maximum(a,b):
    if isinstance(a,list):
        need(isinstance(b,list) and len(a)==len(b),'numeric array lengths')
        return max((maximum(x,y) for x,y in zip(a,b)),default=0.)
    return abs(a-b)
def distance(a,b):
    need(len(a)==len(b),'point array lengths')
    return max((norm(sub(x,y)) for x,y in zip(a,b)),default=0.)
def center(points):return [math.fsum(p[k] for p in points)/len(points) for k in range(3)]
def area(points):
    # Newell's polygon area vector, independently summed by coordinates.
    o=center(points);p=[sub(v,o) for v in points];terms=[]
    for k,l in ((1,2),(2,0),(0,1)):
        terms.append(.5*math.fsum((p[i][k]-p[(i+1)%len(p)][k])*(p[i][l]+p[(i+1)%len(p)][l]) for i in range(len(p))))
    return norm(terms)
def ratios(rest,current,sections):return [area([current[i] for i in row])/area([rest[i] for i in row]) for row in sections]
def objective(rest,current,sections):
    values=ratios(rest,current,sections)
    return values,max(0.,max(1-v for v in values))
def multiply(a,b):return [[math.fsum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def inverse(a):
    # Independent Gauss-Jordan inverse, unlike the product's cofactor kernel.
    rows=[list(row)+[float(i==j) for j in range(4)] for i,row in enumerate(a)]
    for column in range(4):
        pivot=max(range(column,4),key=lambda k:abs(rows[k][column]))
        need(abs(rows[pivot][column])>1e-14,'invertible recorded matrix')
        rows[pivot],rows[column]=rows[column],rows[pivot]
        denominator=rows[column][column];rows[column]=[v/denominator for v in rows[column]]
        for row in range(4):
            if row!=column:
                factor=rows[row][column];rows[row]=[v-factor*w for v,w in zip(rows[row],rows[column])]
    return [row[4:] for row in rows]
def point(a,p):return [math.fsum(a[k][i]*p[i] for i in range(3))+a[k][3] for k in range(3)]
def skin(rest,weights,rests,poses):
    matrices=[multiply(p,inverse(r)) for r,p in zip(rests,poses)]
    result=[]
    for p,row in zip(rest,weights):
        mapped=[point(m,p) for m in matrices]
        result.append([math.fsum(w*v[k] for w,v in zip(row,mapped)) for k in range(3)])
    return result
def quaternion(a):
    # Trace/diagonal extraction normalized independently for float32 RNA.
    candidates=[1+a[0][0]+a[1][1]+a[2][2],1+a[0][0]-a[1][1]-a[2][2],
                1-a[0][0]+a[1][1]-a[2][2],1-a[0][0]-a[1][1]+a[2][2]]
    i=max(range(4),key=candidates.__getitem__);v=math.sqrt(max(0.,candidates[i]))/2;d=4*v
    if i==0:q=[v,(a[2][1]-a[1][2])/d,(a[0][2]-a[2][0])/d,(a[1][0]-a[0][1])/d]
    elif i==1:q=[(a[2][1]-a[1][2])/d,v,(a[0][1]+a[1][0])/d,(a[0][2]+a[2][0])/d]
    elif i==2:q=[(a[0][2]-a[2][0])/d,(a[0][1]+a[1][0])/d,v,(a[1][2]+a[2][1])/d]
    else:q=[(a[1][0]-a[0][1])/d,(a[0][2]+a[2][0])/d,(a[1][2]+a[2][1])/d,v]
    length=norm(q);return [v/length for v in q]
def angle(a,b):
    q=quaternion(a);p=quaternion(b)
    scalar=math.fsum(x*y for x,y in zip(q,p))
    vector=[q[0]*p[1]-p[0]*q[1]-q[2]*p[3]+q[3]*p[2],
            q[0]*p[2]-p[0]*q[2]-q[3]*p[1]+q[1]*p[3],
            q[0]*p[3]-p[0]*q[3]-q[1]*p[2]+q[2]*p[1]]
    return math.degrees(2*math.atan2(norm(vector),abs(scalar)))
def cyclic(face):return min(tuple(face[i:]+face[:i]) for i in range(3))

def main():
    parent=read(RUN/'RESULT.json');freeze=read(RUN/'SOURCE_FREEZE.json');state=read(RUN/'state.json')
    need(parent['passed'] and len(parent['cases'])==len(FIXED),'fixed native entry result')
    need(freeze['native_gates']==GATES and freeze['new_effect_assets']==0,'native gates unchanged')
    identity=freeze['runtime_identity']
    literals={}
    for node in ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes()).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
                    literals[target.id]=ast.literal_eval(node.value)
    names=set(literals['_ROOT_MODULES'])
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT/package).glob('*.py'))
    manifest=[{'path':name,'sha256':sha(ROOT/name)} for name in sorted(names)]
    need(len(manifest)==137 and manifest==identity['source_files'],'independent complete runtime source enumeration')
    source_hash=digest({'base_version':literals['BASE_VERSION'],'implementation_revision':literals['IMPLEMENTATION_REVISION'],'files':manifest})
    need(source_hash==identity['source_sha256'] and identity['build_id']=='sha256:'+source_hash,'canonical source identity')
    need(parent['source_before']==parent['source_after']==identity,'parent fixed source identity')
    for row in manifest:need(sha(ROOT/row['path'])==row['sha256'],'source member '+row['path'])
    for name,expected in freeze['qa_scripts'].items():need(sha(ROOT/name)==expected,'frozen QA source '+name)
    need(sha(freeze['blend_path'])==freeze['blend_sha256']==parent['blend_sha256_before']==parent['blend_sha256_after'],'existing blend unchanged')
    fixtures=read(RUN/'FIXTURE_INPUTS.json')['cases']
    need(sha(RUN/'FIXTURE_INPUTS.json')==freeze['fixture_input_sha256'] and len(fixtures)==8,'fixture input binding')
    tx=[json.loads(line) for line in (RUN/'RPC_TX.txt').read_text().splitlines() if line.strip()]
    prefix='HUMAN_EYE_RPC:'
    rx=[json.loads(line[len(prefix):]) for line in (RUN/'RPC_RX.txt').read_text().splitlines() if line.startswith(prefix)]
    need(len(tx)==len(rx)==10 and [v['id'] for v in tx]==list(range(1,11)),'ten complete unique RPC transactions')
    need([v['id'] for v in tx]==[v['id'] for v in rx] and all('result' in v and 'error' not in v for v in rx),'RPC response ordering/results')
    commands=[v['command'] for v in tx]
    need(commands==['capabilities']+['correct_arm_axial']*8+['shutdown'],'no control-side source capture or observation RPC')
    cap=rx[0]['result'];pid=parent['process_exit']['pid']
    need(cap==parent['capabilities'] and cap['process_id']==pid and cap['connection']=='owned_headless_process'
         and cap['generic_code_execution'] is False and cap['attaches_to_open_window'] is False
         and cap['arm_axial_execution_protocol']=='owned-arm-axial-execution-v1','fixed owned writable worker capability')
    need(cap['native_observation_capabilities']['host_source_sha256']==sha(ROOT/'human_eye_plugin/blender_host.py'),'worker loaded host source hash')
    records=state['arm_axial_events']['records']
    need(state['inflight'] is None and len(records)==8 and state['config_fingerprint']==digest(read(RUN/'config.json')),'durable complete state and config binding')
    summaries=[];totals=Counter()
    for index,(expected,entry,fixture) in enumerate(zip(FIXED,parent['cases'],fixtures),1):
        case_id,status,theta,initial_u=expected;raw=read(RUN/('case_'+str(index).zfill(2)+'.json'))
        audit=raw['product_audit'];task=audit['task'];receipt=raw['receipt'];before=raw['native_before'];after=raw['native_after']
        positive=status=='satisfied';count=2 if positive else 0
        need(raw['case_id']==entry['case_id']==fixture['case_id']==case_id,'fixed case order')
        need(raw['passed'] and raw['product_error'] is None and receipt==audit['receipt']==rx[index]['result'],'actual worker/host receipt binding')
        need(tx[index]['params']=={'task':task} and entry['event_id']==task['event_id']==raw['event_id'],'one typed submitted task')
        need('fixed_end_pose_matrices' not in task and 'candidate' not in task,'caller supplies no end/candidate matrices')
        need((receipt['status'],receipt['setter_attempts'],receipt['setter_returns'],receipt['executed'],receipt['task_succeeded'])
             ==(status,count,count,positive,status in ('satisfied','no_op')),'actual status and true pair counts')
        for key,value in receipt.items():need(entry['result'][key]==value,'caller consumed actual receipt '+key)
        before_cap=audit['before_capture'];patch=audit['input_patch'];static=audit['static_patch'];resolved=audit['resolved_task']
        need(before_cap['static_patch'] is None and patch['current_vertices']==before_cap['current_vertices']==before['current_vertices'],'actual before current without static export/extra capture')
        need(before_cap['pose_matrices']==before['poses']==[b['pose_matrix'] for b in patch['bone_chain']],'actual before pose input')
        need(resolved['fixed_end_pose_matrices']==[before_cap['pose_matrices'][i] for i in (0,2)],'starting ends resolved in first worker capture')
        for key in ('u_interval_deg','max_section_area_loss','protected_vertex_ids','angle_tolerance_deg','position_tolerance_m','area_tolerance'):
            need(resolved[key]==task[key]==fixture[key],'unchanged task target/limits '+key)
        need(task['area_tolerance']==1e-6 and task['max_section_area_loss']==.4,'product success gates not QA tolerance')
        for key in ('rest_vertices','weights','triangles','vertex_ids','sections'):need(patch[key]==static[key],'shared static source field '+key)
        need(static['vertex_ids']==list(range(402)) and len(before['static']['rest_vertices'])==402,'whole selected generated mesh')
        need(static['sections']==task['selection']['sections'] and len(static['sections'])==25,'all 25 selected sections')
        need(sorted(cyclic(face) for face in static['triangles'])==sorted(cyclic(face) for face in before['static']['triangles']),'oriented native topology binding')
        need(static['rest_vertices']==before['static']['rest_vertices'],'actual native rest, no regenerated replacement')
        need(before['static']['unit_scale_m']==1. and before['static']==after['static'] and before['sentinel']==after['sentinel'],'full native static/sentinel bookends')
        rests=[b['rest_matrix'] for b in before['static']['bones']]
        need(rests==[b['rest_matrix'] for b in static['bone_chain']],'native rest bone binding')
        for weights,effective in zip(before['static']['raw_weights'],static['weights']):
            total=math.fsum(weights);need(total>0 and abs(total-1.)<=1e-6,'native raw effective-weight domain')
            need([w/total for w in weights]==effective,'existing source normalization, not QA replacement')
        source=before_cap['source']
        need(source==receipt['before_source'] and source['selected_vertices']==402 and source['selected_bones']==task['selection']['bone_names']
             and source['unit']=='m' and source['coordinate_frame']=='armature_local' and source['tracking']=='scene_residency','current before source identity')
        preview=audit['preview'];need(preview['status']==('candidate' if positive else status),'exact preview status')
        work=receipt['work'];need(work['preview_calls']==1 and work['model_calls']==0 and work['source_captures']==(2 if positive else 1),'one solve/shared after capture work')
        need(work['source_capture_attempts']==work['source_captures'] and work['source']['captures']==work['source_captures'],'source attempt/return work')
        totals.update(mutation_rpc=1,setter_attempts=count,setter_returns=count,preview_calls=work['preview_calls'],source_captures=work['source_captures'])
        sections=static['sections'];area_before,j_before=objective(static['rest_vertices'],before['current_vertices'],sections)
        area_after,j_after=objective(static['rest_vertices'],after['current_vertices'],sections)
        for actual,recorded in ((area_before,raw['actual_before']['section_area_ratios']),(area_after,raw['actual_after']['section_area_ratios'])):
            need(maximum(actual,recorded)<1e-12,'independent Newell actual areas reproduce saved observations')
        protected=task['protected_vertex_ids'];need(len(protected)==194,'194 protected endpoint points')
        need(raw['protected_points_before']==[before['current_vertices'][i] for i in protected]
             and raw['protected_points_after']==[after['current_vertices'][i] for i in protected],'full protected arrays tied to native points')
        protected_delta=distance(raw['protected_points_before'],raw['protected_points_after'])
        center_delta=distance([center([before['current_vertices'][i] for i in row]) for row in sections],
                              [center([after['current_vertices'][i] for i in row]) for row in sections])
        head_tail=max(distance(before['heads'],after['heads']),distance(before['tails'],after['tails']))
        end_angle=max(angle(before['world_poses'][i],after['world_poses'][i]) for i in (0,2))
        end_translation=distance([[before['world_poses'][i][k][3] for k in range(3)] for i in (0,2)],
                                 [[after['world_poses'][i][k][3] for k in range(3)] for i in (0,2)])
        need(max(protected_delta,center_delta,head_tail,end_translation)<=GATES['position_m'] and end_angle<=GATES['angle_deg'],'independent actual preservation gates')
        lbs_before=distance(skin(static['rest_vertices'],static['weights'],rests,before['poses']),before['current_vertices'])
        lbs_after=distance(skin(static['rest_vertices'],static['weights'],rests,after['poses']),after['current_vertices'])
        need(max(lbs_before,lbs_after)<=GATES['position_m'],'independent actual LBS')
        if positive:
            after_cap=audit['after_capture'];need(after_cap['source']==receipt['after_source'],'after source result identity')
            need(after_cap['current_vertices']==after['current_vertices'] and after_cap['pose_matrices']==after['poses'],'single actual after current/pose consumed')
            need(after_cap['static_patch'] is None and audit['after_static_patch']==static,'same static source identity after pose')
            for key in source:
                if key not in ('revision','max_lbs_readback_error_m'):need(source[key]==after_cap['source'][key],'held source identity '+key)
            need(after_cap['source']['revision']>source['revision'],'actual mutation source revision advanced')
            need(j_after<=task['max_section_area_loss']+task['area_tolerance'],'actual product area target')
            need(abs(receipt['feedback']['max_section_area_loss']-j_after)<1e-12 and receipt['feedback']['source']=='actual_after_capture','feedback is measured after geometry')
            candidate=preview['candidate'];need(candidate['pose_matrices'][0]==before['poses'][0] and candidate['pose_matrices'][2]==before['poses'][2],'solver kept exact initial end matrices')
            need([c['name'] for c in candidate['bone_changes']]==task['selection']['bone_names'][1:],'only middle/last declared')
            for bone_index,change in zip((1,2),candidate['bone_changes']):
                need(maximum(change['basis_matrix'],after['basis'][bone_index])<=GATES['position_m'],'actual absolute basis matches declared product assignment')
            need(before['basis'][0]==after['basis'][0],'root basis untouched')
        else:
            need(receipt['after_source'] is None and 'after_capture' not in audit and 'side_after' not in audit,'no unnecessary after source capture')
            need(before==after and preview['candidate'] is None,'zero-write task preserved entire native state')
            expected_reason={'no_op':'area_target_already_met','unreachable':'best_allowed_u_exceeds_area_target','not_applicable':'non_axial_or_ambiguous_pose'}[status]
            need(receipt['reason']==expected_reason,'negative/no-op precise reason')
        if theta is not None:
            u=theta/2 if positive else initial_u
            for number,section in enumerate(sections):
                w=static['weights'][section[0]];angles=(0.,u,theta)
                analytic=math.fsum(weight*math.cos(math.radians(a)) for weight,a in zip(w,angles))**2+math.fsum(weight*math.sin(math.radians(a)) for weight,a in zip(w,angles))**2
                need(abs(area_after[number]-analytic)<=GATES['area_error'],'independent axial section determinant '+str(number))
        record=records[task['event_id']]
        need(record['state']=='complete' and record['request']==task and record['request_fingerprint']==digest(task),'durable event/task binding')
        need(type(record['operation_id']) is str and bool(record['operation_id']),'durable operation identity')
        for key,value in receipt.items():need(record['result'][key]==value,'durable actual host receipt '+key)
        summaries.append({'case_id':case_id,'status':status,'before_j':j_before,'actual_after_j':j_after,
            'setter_returns':count,'source_captures':work['source_captures'],'protected_max_m':protected_delta,
            'ring_centers_max_m':center_delta,'heads_tails_max_m':head_tail,'endpoint_angle_deg':end_angle,
            'endpoint_translation_m':end_translation,'LBS_max_m':max(lbs_before,lbs_after),'raw_sha256':sha(RUN/('case_'+str(index).zfill(2)+'.json'))})
    need(dict(totals)==parent['product_work']=={'mutation_rpc':8,'setter_attempts':8,'setter_returns':8,'preview_calls':8,'source_captures':12},'complete actual product work denominator')
    replay=parent['replay'];need(replay['rpc_delta']==0 and replay['cost_delta']==0 and replay['result']['historical_receipt']
        and replay['result']['replayed'] and replay['result']['new_setter_count']==0 and replay['result']['executed_this_call'] is False,'same-event replay has no new RPC/action')
    cleanup=read(RUN/'CHILD_CLEANUP.json');ready=read(RUN/'OBSERVER_READY.json')
    need(cleanup==parent['child_cleanup'] and cleanup['pid']==ready['pid']==pid,'one owned PID identity')
    need(all(cleanup[k] for k in ('profile_none','host_residency_closed','owned_objects_removed','owned_meshes_removed','owned_rigs_removed','all_handlers_removed','file_unsaved')),'cleanup and no-save evidence')
    need(cleanup['work']=={'fixtures':8,'initial_basis_assignments':24,'candidate_assignments':0,'product_calls':8,'native_reads':16},'QA initialization only, product called once per task')
    need(parent['process_exit']=={'pid':pid,'returncode':0,'closed':True},'owned process reaped')
    need(ready['profile_none'] and ready['product_method_source_sha256']==sha(ROOT/'human_eye_plugin/blender_host.py'),'observer retained actual product method source')
    host_tree=ast.parse((ROOT/'human_eye_plugin/blender_host.py').read_bytes())
    host_class=next(n for n in host_tree.body if isinstance(n,ast.ClassDef) and n.name=='BlenderSceneHost')
    method=next(n for n in host_class.body if isinstance(n,ast.FunctionDef) and n.name=='correct_arm_axial')
    need(ready['product_method_firstlineno']==method.lineno and Path(ready['product_method_filename']).resolve()==(ROOT/'human_eye_plugin/blender_host.py').resolve(),'actual method origin')
    setters=[n for n in ast.walk(method) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='matrix_basis' for t in n.targets)]
    need(len(setters)==1,'product has one finite pair setter site')
    initializer=ROOT/'verification/arm_correction_execution_001/native_initializer.py';tree=ast.parse(initializer.read_bytes())
    qa_setters=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='matrix_basis' for t in n.targets)]
    need(len(qa_setters)==1 and ast.unparse(qa_setters[0].value)=='Matrix(basis)','initializer only has initial basis assignment site')
    attached=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_qa_attach')
    need(not any(isinstance(n,ast.Attribute) and n.attr=='matrix_basis' for n in ast.walk(attached)),'QA observer does not assign a candidate')
    need(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='original' for n in ast.walk(attached))==1,'observer delegates once to original product method')
    command=read(RUN/'COMMAND.json');actual=command['actual'];position=actual.index('--python-expr')
    need(actual[:position]+actual[position+2:]==command['original'] and command['verified_expression_unchanged'],'QA initializer precedes unchanged fixed worker expression')
    need('--disable-autoexec' in actual and '--background' in actual,'owned native startup flags')
    events=[json.loads(line) for line in (RUN/'OBSERVER_EVENTS.jsonl').read_text().splitlines()]
    need(len(events)==8 and all(v['passed'] for v in events) and [v['event_id'] for v in events]==[r['event_id'] for r in parent['cases']],'complete finite observer records')
    cpu=read(HERE/'cpu_final_03/RESULT.json');log=(HERE/'cpu_final_03/TESTS.log').read_text()
    need(cpu['passed'] and cpu['tests']==47 and cpu['failures']==cpu['errors']==cpu['skips']==0 and cpu['sources_unchanged'],'frozen CPU47 receipt, not rerun')
    for path,value in cpu['after_sha256'].items():need(sha(ROOT/path)==value,'final CPU source '+path)
    for name in ('test_structured_partial_mutation_error_preserves_known_counts','test_completion_save_failure_keeps_known_outcome_and_durable_pending',
                 'test_lost_receipt_pending_blocks_same_and_other_events_after_restart','test_unchanged_clearance_success','test_unchanged_clearance_unknown_without_retry'):
        need(any(line.startswith(name+' ') and line.endswith(' ... ok') for line in log.splitlines()),'recorded CPU failure/replay/legacy check '+name)
    need(parent['model_calls']==parent['qa_candidate_assignments']==0,'no model or QA candidate work')
    return {'schema':'arm-execution-independent-native-audit-v1','passed':True,'checks':checks,
        'runtime_source_count':137,'runtime_source_sha256':source_hash,'cases':summaries,'actual_product_work':dict(totals),
        'cpu_methods_reported_passed_not_rerun':47,'process_exit':parent['process_exit'],'gates':GATES,
        'new_product_calls':0,'new_Blender_runs':0,'new_effect_cases':0,'model_calls':0,'producer_imports':0,
        'script_sha256':sha(Path(__file__)),'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in
            (RUN/'RESULT.json',RUN/'SOURCE_FREEZE.json',RUN/'state.json',RUN/'RPC_TX.txt',RUN/'RPC_RX.txt')},
        'scope':'independent_recompute_of_recorded_generated_owned_entry_only_not_new_effect_trials',
        'limitations':['Input/bytecode origin is corroborated by frozen source, controlled-worker metadata, AST and full raw RNA; not external hardware attestation.',
            'CPU faults are checked from their fixed result/log/source binding, not independently re-executed in this audit.',
            'This verifies eight generated fixed-frame tasks, not character animation, volume or learned correction benefit.']}


if __name__=='__main__':
    history=[]
    if OUT.exists():history=read(OUT).get('audit_attempt_history',[])+[{k:v for k,v in read(OUT).items() if k!='audit_attempt_history'}]
    try:result=main()
    except BaseException as exc:
        result={'schema':'arm-execution-independent-native-audit-v1','passed':False,'checks':checks,
            'failure':{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()},
            'script_sha256':sha(Path(__file__)),'new_product_calls':0,'new_Blender_runs':0,'producer_imports':0}
    if history:result['audit_attempt_history']=history
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({k:result[k] for k in ('passed','checks','new_product_calls','new_Blender_runs')}))
    if not result['passed']:raise SystemExit(result['failure']['traceback'])
