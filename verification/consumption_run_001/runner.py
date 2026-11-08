"""Finite normal-Codex/MCP consumption runner; prepare phase never launches it.

The readiness guard intentionally refuses execution until known blockers are
resolved and the coordinator grants a source-matched, single-use window.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import types
import zipfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
ROOT=HERE.parents[1]
PYTHON=ROOT/'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe'
SOURCE_COMMIT='17db41c481397965a9bae3f4571c59a5a80939c9'
SOURCE_SHA='01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de'
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=True)+'\n',encoding='utf8')


def validate_plan(plan):
    assert plan['source_sha256']==SOURCE_SHA and plan['source_commit']==SOURCE_COMMIT
    assert [(x['task_id'],x['arm']) for x in plan['cells']]==[
        ('T01','N'),('T01','P'),('T02','P'),('T02','N'),('T03','N'),('T03','P'),('T04','P'),('T04','N')]
    assert plan['limits']==dict(answer_seconds=180,chain_seconds=600,cleanup_reserve_seconds=60,
        model_answers=8,native_sessions=8,action_observation_threshold=8,public_text_bytes_per_answer=1048576,
        execute_rpc_per_answer=128,close_rpc_per_answer=1,total_physical_rpc=1032,output_tokens_hard_limit=None)


def require_ready(plan,approval):
    validate_plan(plan)
    assert plan['execution_ready'] is True,'PREPARATION_ONLY: effective-context/output contract awaits root review; no consumer/session may start'
    assert not plan['execution_blockers'],'unresolved_dependencies'
    for component in plan['runtime_components']:
        assert sha((HERE/component['path']).read_bytes())==component['sha256'],'changed_frozen_component:'+component['path']
    assert sha(Path(plan['codex']['executable']).read_bytes())==plan['codex']['sha256'],'changed_Codex_binary'
    assert sha(Path(plan['blender']).read_bytes())==plan['blender_sha256'],'changed_Blender_binary'
    assert approval['cycle_id']=='CONSUMPTION-RUN-001' and approval['plan_sha256']==sha((HERE/'PLAN.json').read_bytes())
    assert approval['model_answers']==approval['native_sessions']==8 and approval['max_physical_rpc']==1032
    window=load('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')['performance_window']
    assert window['token']==approval['window_token'] and window['cycle_id']=='CONSUMPTION-RUN-001'
    assert str(window.get('status','')).startswith('granted'),'window_not_granted'
    expiry=window.get('expires_utc',window.get('deadline_utc'))
    if expiry is not None:assert datetime.now(timezone.utc)<datetime.fromisoformat(expiry.replace('Z','+00:00')),'window_expired'
    assert window['owner']=='W-ENTRY' and window['max_sessions']==8 and window['max_RPC']==1032
    assert sha(PYTHON.read_bytes())==plan['python']['sha256'] and sys.version==plan['python']['version'],'changed_Python_runtime'


def argv_for(plan,cell,work,final):
    c=plan['codex']
    assert sha(Path(c['executable']).read_bytes())==c['sha256']
    settings=dict(c['settings'])
    common=dict(command=str(PYTHON),args=['-I',str(HERE/'bridge.py'),'--kind','native','--cell',str(cell)],
        cwd=str(work),required=True,startup_timeout_sec=20,tool_timeout_sec=180)
    settings['mcp_servers.native']=common
    if load(cell)['arm']=='P':
        settings['mcp_servers.human_eye']=dict(command=str(PYTHON),
            args=['-I',str(HERE/'bridge.py'),'--kind','he','--cell',str(cell)],cwd=str(work),
            required=True,enabled_tools=['human_eye_scene_observe'],startup_timeout_sec=20,tool_timeout_sec=180)
    argv=[c['executable'],'exec','--ignore-user-config','--ephemeral','--json','--strict-config',
        '--skip-git-repo-check','-C',str(work),'-m',c['model'],'--color','never','-o',str(final)]
    # JSON scalar/array/inline table syntax is accepted by the frozen local
    # command's TOML override parser only after the config preflight confirms it.
    for key,value in settings.items():argv.extend(['-c',key+'='+toml_value(value)])
    argv.append('-')
    return argv


def toml_value(value):
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+'='+toml_value(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+','.join(toml_value(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=True)


PUBLIC_TOOL_TYPES={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view'}
def public_event(event):
    """Allowlist public tools/errors/numeric usage; discard reasoning/system."""
    kind=event.get('type')
    if kind in ('item.started','item.completed'):
        item=event.get('item',{})
        if item.get('type') in PUBLIC_TOOL_TYPES:
            return dict(type=kind,item={k:v for k,v in item.items() if k in
                ('id','type','server','tool','name','arguments','command','aggregated_output','exit_code','status','result','error','duration_ms')})
        return None
    if kind=='turn.completed':
        usage=event.get('usage',{})
        allowed=('input_tokens','cached_input_tokens','output_tokens','total_tokens','reasoning_tokens')
        return dict(type=kind,usage={k:v for k,v in usage.items() if k in allowed and type(v) is int and v>=0})
    if kind in ('turn.failed','error'):
        return dict(type=kind,message=str(event.get('message',event.get('error','')))[:4096])
    return None


def kill_tree(process):
    if process is None:return
    if process.poll() is None:
        try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        except subprocess.TimeoutExpired:process.kill()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def safe_environment(source):
    bindings={'CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID','APP_TOOLS_PIPE_PATH',
        'CODEX_APP_TOOLS_PIPE_PATH','CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY'}
    env={}
    for key in source:
        upper=key.upper()
        if key in bindings or upper.endswith(('_API_KEY','_ACCESS_TOKEN')) or upper in (
                'OPENAI_API_KEY','CODEX_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY'):
            continue  # Never read an excluded credential's value.
        env[key]=source[key]
    return env


def consume(plan,cell,work,prompt):
    from bridge import Budget
    budget=Budget(cell);folder=Path(cell['audit_root']);final=folder/'final.txt'
    cell_path=folder/'CELL.json';argv=argv_for(plan,cell_path,work,final)
    env=safe_environment(os.environ)
    record=dict(argv=argv,started_ns=time.perf_counter_ns(),public_events=[],discarded_event_types={},
        tool_actions_observed=0,provider_requests=None,fees=None,backend='unexposed',usage=None,
        complete=False,deadline_enforcement='controller kill from original dispatch deadline',
        action_policy='8 is observation threshold only; all actions/costs retained without threshold failure')
    process=None;threads=[];timer=None;deadline_fired=threading.Event();reap_lock=threading.Lock()
    def reap():
        with reap_lock:kill_tree(process)
    def expire():
        deadline_fired.set()
        try:reap()
        except BaseException:pass  # main finally records the actual reap outcome
    lines=queue.Queue()
    def read(stream,label):
        for raw in iter(stream.readline,b''):lines.put((label,raw))
        lines.put((label,None))
    closed=0;candidate=None;seen=set()
    try:
        # Original absolute deadline also interrupts blocking I/O/parse paths;
        # it never depends on coordinator polling or a new relative timeout.
        timer=threading.Timer(budget.remaining(),expire);timer.daemon=True;timer.start()
        budget.remaining()
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=work,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if deadline_fired.is_set():raise TimeoutError('deadline_during_process_start')
        threads=[threading.Thread(target=read,args=(stream,label),daemon=True) for stream,label in
            ((process.stdout,'stdout'),(process.stderr,'stderr'))]
        for thread in threads:thread.start()
        process.stdin.write(prompt);process.stdin.close()
        while closed<2:
            remaining=(cell['deadline_perf_ns']-time.perf_counter_ns())/1e9
            if remaining<=0:raise TimeoutError('original_answer_180s_deadline')
            try:label,raw=lines.get(timeout=min(.05,remaining))
            except queue.Empty:
                if load(cell['ledger_path'])['halted']:raise RuntimeError('shared_budget_halted')
                continue
            if raw is None:closed+=1;continue
            if label=='stderr':
                # Do not export arbitrary stderr that could contain model input
                # or runtime internals; byte count/exit status retain failures.
                record['stderr_bytes']=record.get('stderr_bytes',0)+len(raw);continue
            record['stdout_bytes']=record.get('stdout_bytes',0)+len(raw)
            try:event=json.loads(raw)
            except ValueError:raise ValueError('unsupported_non_JSON_exec_event')
            public=public_event(event)
            if public is not None:
                record['public_events'].append(public)
                if public['type']=='turn.completed':record['usage']=public['usage'];record['complete']=True
            else:
                tag=event.get('item',{}).get('type',event.get('type','unknown'))
                record['discarded_event_types'][tag]=record['discarded_event_types'].get(tag,0)+1
            item=event.get('item',{})
            if event.get('type')=='item.completed' and item.get('type')=='agent_message':candidate=item.get('text','')
            if event.get('type')=='item.started' and item.get('type') in PUBLIC_TOOL_TYPES:
                identity=item.get('id', 'anonymous-'+str(record['tool_actions_observed']+1))
                if identity not in seen:
                    seen.add(identity);record['tool_actions_observed']+=1
                    record['above_action_observation_threshold']=record['tool_actions_observed']>8
            if event.get('type')=='item.completed' and item.get('type')=='command_execution':
                budget.charge_public(len(str(item.get('aggregated_output','')).encode()),'builtin_shell_observed_after_delivery')
        process.wait(timeout=max(.01,(cell['deadline_perf_ns']-time.perf_counter_ns())/1e9))
        if deadline_fired.is_set() or time.perf_counter_ns()>=cell['deadline_perf_ns']:raise TimeoutError('late_final')
        if candidate is not None:
            budget.charge_public(len(candidate.encode()),'final_text');final.write_text(candidate,encoding='utf8')
        ledger=load(cell['ledger_path'])
        record['valid_completion']=(record['complete'] and candidate is not None and process.returncode==0
            and not deadline_fired.is_set() and time.perf_counter_ns()<cell['deadline_perf_ns']
            and not ledger['halted'] and not ledger['inflight_rpc']
            and ledger['physical_rpc']<=128 and ledger['public_text_bytes']<=1048576)
    except BaseException as exc:
        record.update(valid_completion=False,error_type=type(exc).__name__,error=str(exc))
    finally:
        if timer is not None:timer.cancel();timer.join(timeout=15)
        try:reap()
        except BaseException as exc:record['reap_error']=dict(type=type(exc).__name__,message=str(exc))
        for thread in threads:thread.join(timeout=1)
        record.update(exit_code=None if process is None else process.poll(),
            process_spawned=process is not None,process_reaped=process is not None and process.poll() is not None,finished_ns=time.perf_counter_ns())
        record['deadline_timer_fired']=deadline_fired.is_set()
        record['wall_ns']=record['finished_ns']-record['started_ns']
        save(folder/'CONSUMER.json',record)
    return record


def close_meter(native,owner,folder):
    """Transparent owner-held cleanup wire; cleanup is not a model action."""
    original=native.socket.create_connection
    meters=dict(tx_attempted=0,tx_completed=0,rx=0,started_ns=time.perf_counter_ns())
    class Connection:
        def __init__(self,sock):self.sock=sock
        def __getattr__(self,key):return getattr(self.sock,key)
        def __enter__(self):return self
        def __exit__(self,*args):return self.sock.__exit__(*args)
        def sendall(self,raw):
            with (folder/'CLOSE_TX.bin').open('ab') as stream:stream.write(raw)
            meters['tx_attempted']+=len(raw);value=self.sock.sendall(raw);meters['tx_completed']+=len(raw);return value
        def recv(self,size):
            raw=self.sock.recv(size)
            with (folder/'CLOSE_RX.bin').open('ab') as stream:stream.write(raw)
            meters['rx']+=len(raw);return raw
    native.socket.create_connection=lambda *args,**kwargs:Connection(original(*args,**kwargs))
    try:return owner.close()
    finally:
        native.socket.create_connection=original;meters['ended_ns']=time.perf_counter_ns();save(folder/'CLOSE_METER.json',meters)


def run(approval_path):
    run_started=time.perf_counter_ns()
    plan=load(HERE/'PLAN.json');approval=load(approval_path)
    require_ready(plan,approval)  # before any process, helper import or asset copy
    output=HERE/'actual_01';output.mkdir(exist_ok=False)
    save(output/'STARTED.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),approval=approval,
        run_started_ns=run_started,preflight_management_ns=time.perf_counter_ns()-run_started))
    material=load(HERE/'materials/MATERIAL_MANIFEST.json')
    spec_by_id={t['task_id']:t for t in material['tasks']}
    helper_path=HERE/'materials'/material['neutral_helper']['local_path']
    raw=helper_path.read_bytes();assert sha(raw)==material['neutral_helper']['sha256']
    native=types.ModuleType('_consumption_owned_native');native.__file__=str(helper_path)
    sys.modules[native.__name__]=native;exec(compile(raw,str(helper_path),'exec',dont_inherit=True),native.__dict__)
    from bridge import Budget
    records=[]
    for index,entry in enumerate(plan['cells'],1):
        began=time.perf_counter_ns()
        task=spec_by_id[entry['task_id']];folder=output/str(index).zfill(2);folder.mkdir()
        public_root=Path(plan['neutral_run_root'])/str(index).zfill(2)
        public_root.mkdir(parents=True,exist_ok=False);work=public_root/'work';work.mkdir()
        chain_deadline=began+600_000_000_000
        # The 180 seconds start when this cell is dispatched, before asset/host
        # startup, MCP discovery, queueing and tools. Cleanup has its own reserve.
        answer_deadline=min(began+180_000_000_000,chain_deadline-60_000_000_000)
        prompt=(HERE/'materials'/task['prompt_path']).read_bytes()
        assert sha(prompt)==task['prompt_utf8_sha256']
        owner=None;record=dict(task_id=entry['task_id'],arm=entry['arm'],dispatch_ns=began,denominator=1)
        try:
            asset=public_root/'input.blend'
            shutil.copyfile(task['source_asset_path'],asset)
            assert sha(asset.read_bytes())==task['asset_sha256']
            owner=native.NativeSession.start(blender=plan['blender'],asset=asset,
                workspace=public_root/'native',deadline_ns=chain_deadline,condition=entry['arm'],
                expected_asset_sha256=task['asset_sha256'],max_calls=128)
            cell=dict(entry,audit_root=str(folder),ledger_path=str(folder/'BUDGET.json'),deadline_perf_ns=answer_deadline,
                endpoint=dict(host=owner.host,port=owner.port),native_workspace=str(owner.workspace),native_helper=str(helper_path),
                native_helper_sha256=material['neutral_helper']['sha256'],source_sha256=SOURCE_SHA,
                source_root=str(public_root/'sources'),product_manifest=plan['product_manifest'],
                action_observation_threshold=8,max_native_rpc=128,max_public_text_bytes=1048576,
                image_limits=dict(max_images=1,max_single_pixels=589824,max_total_pixels=589824),
                max_image_dimension=768,max_constructed_images=1,
                he_config=str(folder/'he_config.json'),he_argv=[str(PYTHON),'-I',str(HERE/'he_bootstrap.py'),str(folder/'CELL.json')],he_cwd=str(folder))
            if entry['arm']=='P':
                with zipfile.ZipFile(HERE/'PRODUCT_BYTES.zip') as archive:archive.extractall(public_root/'sources')
                save(cell['he_config'],dict(schema_version='1.0',enabled=True,project_root=cell['source_root'],
                    state_file=str(folder/'state.json'),audit_file=str(folder/'he_audit.jsonl'),
                    expected_identity=dict(source_sha256=SOURCE_SHA),blender=dict(host=owner.host,port=owner.port,timeout_s=30),request_budget_s=30))
            save(folder/'CELL.json',cell);Budget.create(cell)
            Budget(cell).charge_public(len(prompt),'exact_question_prompt')
            record['consumer']=consume(plan,cell,work,prompt)
        except BaseException as exc:record.update(error_type=type(exc).__name__,error=str(exc),valid_completion=False)
        finally:
            if owner is not None:
                try:record['close']=close_meter(native,owner,folder)
                except BaseException as exc:
                    record['close_error']=dict(type=type(exc).__name__,message=str(exc));owner._kill()
                    record['close']={}
                record['closed_worker']=load(owner.workspace/'WORKER_CLOSED.json') if (owner.workspace/'WORKER_CLOSED.json').exists() else None
                record['native_session']=owner.config
                closed=record['closed_worker'] or {}
                receipt=record['close']
                record['cleanup_verified']=(receipt.get('response',{}).get('status')=='closed'
                    and receipt.get('error') is None and receipt.get('process_reaped')
                    and receipt.get('exit_code')==0 and receipt.get('source_file_unchanged')
                    and receipt.get('protected_files_unchanged') and closed.get('poisoned') is False
                    and closed.get('initial_geometry_fingerprint')==closed.get('final_geometry_fingerprint'))
            record['valid_comparison']=None
            record['comparison_review']='requires independent fixed scoring, context/source/access/image audit; tool threshold8 is never a failure'
            record['finished_ns']=time.perf_counter_ns();record['whole_cell_ns']=record['finished_ns']-began
            save(folder/'RESULT.json',record);records.append(record)
    save(output/'RESULTS.json',dict(scheduled=8,cells=records,provider_requests=None,fees=None,no_retries=True,
        run_started_ns=run_started,run_wall_through_result_construction_ns=time.perf_counter_ns()-run_started,
        clock_scope='includes preflight/cells/close; excludes controller interpreter startup and final record write; outer invocation wall recorded by coordinator'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--approval',type=Path,required=True)
    args=parser.parse_args();run(args.approval)
