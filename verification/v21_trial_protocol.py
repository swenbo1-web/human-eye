"""Finite preregistration and hash-bound static CLI transport for trial003.

This verification adapter never starts Blender or changes product state. Its
stdout is a transport candidate; actual host stdout must independently match.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,random,sys,time
from datetime import datetime,timezone
from pathlib import Path

CYCLE='V21-REFACTOR-003'
RUNTIME='6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382'
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=('verification/v21_trial_protocol.py','verification/v21_trial_acquire.py',
    'verification/v21_trial_native.py','verification/v21_trial_scoring.py',
    'verification/test_v21_trial_scoring.py','verification/test_v21_trial_native.py',
    'verification/test_v21_trial_protocol.py','verification/deformation_region_oracle.py',
    'verification/deformation_anchor_oracle.py','verification/model_trial/b3e_native.py',
    'verification/run_deformation_closure_preflight.py')
SOURCE_KEYS=('source_ref','source_observation_sha256','original_topology_sha256','anchor_id','core_half_extents_m')
ANSWER_SCHEMA=dict(task_sha256='exact supplied digest',selected_triangle='one original integer face ID',
    frames=[dict(label='each exact source label',file_sha256='exact source file SHA',
        principal_stretches='[high, low] or null for unknown',area_ratio='number or null for unknown',
        state='measured/collapsed/unknown',reason='exact reason or null',in_core='boolean',
        has_confirmed_mixed_witness='whole required core true/false/null')],
    interpretation='Explain each fixed frame, same-face threshold evidence, full core/global unknown, scope and limitations.')
CONSUMER_RULES='''You are one independent consumer of a fixed post-anchor geometry task. Use only this message and the frozen CLI outputs in this assignment. Do not read project files/source, other conditions, prior answers, private reference data, history, web, or learning knowledge. Do not edit files, launch Blender, change frames, save assets, or call any provider. Isolation is soft; your entire host tool trajectory will be audited.
Use your own Hook-issued Agent Learning session_context only to obtain your host agent_id. If already obtained for launch, do not repeat it. Do not borrow a handle or query knowledge. Include that agent_id in your final response.
Then execute INITIAL_COMMAND exactly through exec_command (workdir D:/hefe), with max_output_tokens=24000. In functions.exec forward the full command result using text(result); use max_output_tokens=26000 there. Every stdout must be complete; if truncated, abstain and report it. Do not process or rewrite the report with another script.
The CLI returns the actual initial report plus source-bound rows already present in that report and full summaries already reported. You may answer final or abstain immediately. If needed you may call the same CLI with --lookup replacing --read, supplying a comma-separated list of 1 to 4 original triangle indices. At most two optional lookup calls are allowed. These are charged hash-bound static-snapshot retrievals, not fresh Blender targeted inspections. No joint/native supplement or extra source read is available. Never repair a rejected request or reset the budget.
The unique nonroot bone HEAD and world-axis closed box halfwidth 0.5 m have already been supplied and validated as a common prefix. Answer the original geometric question using any reliable acceptable same-face witness, not necessarily any particular extremum. Thresholds are inclusive high>=1.1 and low<=0.9 on the SAME measured original face. Both fixed files must use that same face index. Distinguish a face being mixed from the whole core having a confirmed mixed witness. Unknown does not mean false; global partial need not invalidate a fully known local core. Whole intersecting triangles are measured, not clipped-area or volume integrals. Source replay consistency does not certify physical measurement error, animation timing, damage, anatomy, volume or editing authority.
Return one JSON object only, no Markdown: {"agent_id":"your actual host ID","consumer_id":"exact assigned ID","task_sha256":"exact supplied hash","status":"final or abstain","answer":ANSWER_OR_NULL,"reason":"short reason or null"}. ANSWER must have exactly task_sha256, selected_triangle, frames, interpretation. Each of the two frames must have exactly label,file_sha256,principal_stretches,area_ratio,state,reason,in_core,has_confirmed_mixed_witness. Use exact source labels/hash/metrics and JSON booleans/null; interpretation must explain which saved frame confirms the mixed fact, core/global reliability, and evidence limitations. If evidence is insufficient, abstain honestly. No extra tools beyond your one identity call and the frozen CLI read/lookup commands.'''
LAUNCH_TEMPLATE='''Consume assignment {consumer} for cycle V21-REFACTOR-003. First obtain your own host agent_id using your own Hook-issued Agent Learning session_context (identity only; no knowledge query). Then run exactly this command through exec_command in D:/hefe with max_output_tokens=24000, using functions.exec max_output_tokens=26000 and text(result) to preserve the complete result:
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B 'D:/hefe/verification/v21_trial_protocol.py' --root 'D:/hefe/verification/fixes/20261104_v21_refactor003' --consumer {consumer} --read
The initial stdout contains the task, rules and answer schema. Use only that input and at most two optional calls of this same CLI replacing --read with --lookup original_face_ids. Do not read any other files, source, history, conditions, references, web or learning knowledge; do not edit or launch Blender. You may final or abstain immediately. Return only the requested JSON including your actual agent_id. Your immutable 600-second session started immediately before this spawn; do not request retries or deadline extensions.'''

def need(value,reason):
    if not value:raise ValueError('v21_trial_'+reason)
def blob(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(blob(value));stream.flush();os.fsync(stream.fileno())
    need(path.read_bytes()==blob(value),'persist_readback')
def replace(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.next')
    save(temporary,value);os.replace(temporary,path)
def now():return datetime.now(timezone.utc).isoformat()

def register(root):
    root=Path(root).resolve();common=load(root/'COMMON.json')
    need(common['source_runtime_sha256']==RUNTIME,'runtime_pin')
    costs=load(root/'SOURCE_COSTS.json')
    paths=['COMMON.json','SOURCE_COSTS.json','PREPARE_COSTS.json','NATIVE_REFERENCE.json']
    for mode in 'ABC':paths.extend([mode+'/REPORT.json',mode+'/BACKEND.json'])
    members=[dict(path=name,sha256=sha(root/name),bytes=(root/name).stat().st_size) for name in paths]
    modes=list('ABC');random.Random(20261104003).shuffle(modes)
    mapping=dict(zip(('consumer_17','consumer_42','consumer_68'),modes))
    script_pins=[dict(path=name,sha256=sha(ROOT/name)) for name in SCRIPTS]
    frozen=dict(schema='v21-post-anchor-preregistration-v1',cycle_id=CYCLE,created_utc=now(),
        registered_ns=time.perf_counter_ns(),execution_window_seconds=2400,consumer_window_seconds=600,
        runtime_source_sha256=RUNTIME,baseline_commit='fc8305887d9e5f7d08bdaffe181c7ba2e9ae8279',
        task=common['spec'],task_sha256=common['task_sha256'],run_nonce=common['run_nonce'],
        common_prefix='directory selection complete: unique public nonroot HEAD, world halfwidth0.5m; qualification charged separately',
        case='one familiar regression case; two fixed saved frames, not held-out generalization',
        mapping=mapping,condition_order=list(mapping),condition_forms=dict(A='existing ordinary anchor/region report',
            B='audited task-witness view v2',C='common trusted acquisition plus independent native SAT/QR-SVD'),
        model=dict(model='inherit_parent_no_override',reasoning='inherit_parent_no_override',
            backend_independently_verified=False,consumer_context='fresh fork_turns=none',
            isolation='soft only: filesystem/system/tools/AL remain shared; all actual trajectories audited'),
        protocol=dict(first_report_may_final_or_abstain=True,initial_report_reads=1,max_optional_lookups=2,
            max_faces_per_lookup=4,lookup='local hash-bound validated static rows, not fresh targeted worker inspect',
            independent_joint_supplement='unsupported equally; no mock, free answer or worker revival',
            extra_source_reads=0,host_consumer_turns_max=1,provider_call_count=None,automatic_consumer_retry=0,
            starts='SESSION started_ns immediately before consumer spawn; deadline immutable',
            timeout='CLI checks before/after output; host final receipt must also arrive before deadline; interrupt observed separately'),
        answer_schema=ANSWER_SCHEMA,scoring=dict(module='verification/v21_trial_scoring.py',
            source='complete independent SAT/QR-SVD reference, all acceptable faces',
            evidence='actual full host stdout SHA must equal sealed payload, delivered same-face dual-source rows',
            old_targeted_grader='not_applicable; no targeted_triangle_indices fabrication',
            tolerance=dict(relative=1e-9,absolute=1e-9),interpretation='separate mapping-blind independent review',
            unknown_not_false=True),members=members,script_pins=script_pins,
        consumer_rules=CONSUMER_RULES,consumer_launch_template=LAUNCH_TEMPLATE,
        costs=dict(shared_qualification='one actual shared prefix, separate, never repeatedly allocated as observed cold start',
            per_path='measured preparation/compute/storage, transport bytes/tools, host turn and observed consumer wall',
            cold_start_to_final='null when only cached report consumer path actually run; never add nested/disjoint spans',
            token_input=None,token_output=None,token_cache=None,token_reasoning=None,provider_calls=None,
            USD=None,account_percent_not_used_as_token_or_cost=True),
        restrictions=['no private truth or prior answers for selection','no tuning after first official consumer',
            'no product/asset/GUI/default MCP/Hook/install/paid/Google/key/learning changes'])
    save(root/'PREREGISTERED.json',frozen)
    save(root/'PREREGISTERED_SEAL.json',dict(sha256=sha(root/'PREREGISTERED.json'),bytes=(root/'PREREGISTERED.json').stat().st_size))
    return frozen

def frozen(root):
    root=Path(root).resolve();seal=load(root/'PREREGISTERED_SEAL.json')
    need(sha(root/'PREREGISTERED.json')==seal['sha256'],'registration_changed')
    reg=load(root/'PREREGISTERED.json')
    need(time.perf_counter_ns()<reg['registered_ns']+reg['execution_window_seconds']*10**9,'execution_window')
    for row in reg['script_pins']:need(sha(ROOT/row['path'])==row['sha256'],'script_changed')
    for row in reg['members']:need(sha(root/row['path'])==row['sha256'],'static_input_changed')
    return reg

def start(root,consumer):
    root=Path(root).resolve();reg=frozen(root);need(consumer in reg['mapping'],'consumer')
    at=time.perf_counter_ns()
    need(at+reg['consumer_window_seconds']*10**9<=reg['registered_ns']+reg['execution_window_seconds']*10**9,
        'insufficient_global_window')
    folder=root/'consumers'/consumer;folder.mkdir(parents=True,exist_ok=False)
    session=dict(schema='v21-consumer-session-v1',cycle_id=CYCLE,
        consumer_id=consumer,run_nonce=reg['run_nonce'],task_sha256=reg['task_sha256'],
        started_ns=at,deadline_ns=at+reg['consumer_window_seconds']*10**9,initial_attempts=0,lookup_attempts=0,events=[])
    save(folder/'SESSION.json',session)
    save(folder/'LAUNCH_INPUT.json',dict(message=reg.get('consumer_launch_template',LAUNCH_TEMPLATE).format(consumer=consumer),
        fork_turns='none',model_override=None,reasoning_override=None))
    return session

def _bindings(common,backend):
    return {label:dict(source_ref=copy.deepcopy(frame['source_ref']),
        source_observation_sha256=frame['source_observation_sha256'],
        original_topology_sha256=backend['original_topology_sha256'],anchor_id=frame['anchor_id'],
        core_half_extents_m=common['sources'][label]['core_half_extents_m']) for label,frame in backend['frames'].items()}

def _frame_payload(label,frame,binding,indices,*,initial):
    rows=[]
    for index in indices:
        original=frame['rows'][index];need(original['triangle']==index,'row_index')
        rows.append({key:copy.deepcopy(original[key]) for key in ('triangle','state','reason','principal_stretches','area_ratio')}
            |dict(in_core=index in frame['members']))
    out=dict(label=label,**binding,rows=rows)
    # Full counts and explicit confirmation are copied only when those facts
    # were already public in the raw report, not supplied from another path.
    if initial:
        for key in ('core_states','global_states','core_confirmation','core_extrema'):
            if key in frame.get('initial_summary',{}):out[key]=copy.deepcopy(frame['initial_summary'][key])
    return out

def emit(root,consumer,indices=None):
    root=Path(root).resolve();reg=frozen(root);need(consumer in reg['mapping'],'consumer')
    folder=root/'consumers'/consumer;initial=indices is None
    lock=folder/'ACTIVE';lock.mkdir();event=None;session=None
    try:
        # Load only after acquiring the non-waiting lock. A process paused
        # before mkdir must not overwrite another request's spent reservation.
        session=load(folder/'SESSION.json')
        need(session['consumer_id']==consumer and session['run_nonce']==reg['run_nonce']
            and session['task_sha256']==reg['task_sha256'],'session_binding')
        need(time.perf_counter_ns()<session['deadline_ns'],'consumer_deadline')
        need(session['initial_attempts']==0 if initial else session['initial_attempts']==1,'initial_read_state')
        if not initial:
            need(session['lookup_attempts']<2,'lookup_budget')
            need(type(indices) is list and 1<=len(indices)<=4 and len(set(indices))==len(indices)
                and all(type(i) is int and i>=0 for i in indices),'lookup_indices')
        number=len(session['events'])+1
        # Reserve before filesystem access. Failed attempts are not refunded.
        session['initial_attempts' if initial else 'lookup_attempts']+=1
        event=dict(event_id=consumer+'-event-'+str(number),kind='initial_report' if initial else 'snapshot_lookup',
            requested_indices=indices,started_ns=time.perf_counter_ns(),state='reserved')
        session['events'].append(event);replace(folder/'SESSION.json',session)
        mode=reg['mapping'][consumer];common=load(root/'COMMON.json');backend=load(root/mode/'BACKEND.json')
        need(backend['task_sha256']==reg['task_sha256'] and backend['run_nonce']==reg['run_nonce'],'backend_binding')
        need(backend['report_sha256']==sha(root/mode/'REPORT.json'),'report_binding')
        bindings=_bindings(common,backend);frames=[]
        for label,frame in sorted(backend['frames'].items()):
            selected=frame['initial_row_indices'] if initial else indices
            need(all(index<len(frame['rows']) for index in selected),'lookup_domain')
            frames.append(_frame_payload(label,frame,bindings[label],selected,initial=initial))
        payload=dict(schema='v21-delivered-facts-v1',task_sha256=reg['task_sha256'],run_nonce=reg['run_nonce'],
            consumer_id=consumer,channel=event['kind'],frames=frames,
            provenance=dict(kind='validated_static_snapshot_lookup_not_fresh_Blender_targeted_query',
                original_topology_sha256=backend['original_topology_sha256'],extra_source_reads=0,
                helper_stdout_is_not_model_consumption_proof=True))
        if initial:
            payload['raw_report']=load(root/mode/'REPORT.json')
            payload['task']=common.get('spec')
            payload['instructions']=reg.get('consumer_rules',CONSUMER_RULES)
            payload['answer_schema']=ANSWER_SCHEMA
            payload['original_consumer_deadline_ns']=session['deadline_ns']
        raw=blob(payload);need(len(raw)<=256*1024,'stdout_size')
        save(folder/(event['event_id']+'_PAYLOAD.json'),payload)
        need(time.perf_counter_ns()<session['deadline_ns'],'consumer_deadline')
        event.update(state='stdout_prepared',payload_sha256=hashlib.sha256(raw).hexdigest(),payload_bytes=len(raw),
            preparation_ns=time.perf_counter_ns()-event['started_ns'])
        replace(folder/'SESSION.json',session)
        event['stdout_attempted']=True
        stream=getattr(sys.stdout,'buffer',None)
        if stream is None:sys.stdout.write(raw.decode('ascii'));sys.stdout.flush()
        else:stream.write(raw);stream.flush()
        event['stdout_completed']=True
        need(time.perf_counter_ns()<session['deadline_ns'],'consumer_deadline')
        event.update(state='stdout_written_host_receipt_required',finished_ns=time.perf_counter_ns())
        replace(folder/'SESSION.json',session)
    except BaseException as exc:
        if event is not None:
            event.update(state='failed_or_unknown',error_type=type(exc).__name__,reason=str(exc),finished_ns=time.perf_counter_ns())
            replace(folder/'SESSION.json',session)
        raise
    finally:lock.rmdir()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--register',action='store_true');group.add_argument('--start',action='store_true')
    group.add_argument('--read',action='store_true');group.add_argument('--lookup',type=str)
    parser.add_argument('--consumer');args=parser.parse_args()
    if args.register:print(json.dumps(dict(registered=register(args.root)['cycle_id'])))
    elif args.start:print(json.dumps(start(args.root,args.consumer)))
    else:emit(args.root,args.consumer,None if args.read else [int(x) for x in args.lookup.split(',')])

if __name__=='__main__':main()
