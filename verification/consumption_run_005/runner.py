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
import re
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
BASE=ROOT/'verification/consumption_run_001'
PYTHON=ROOT/'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe'
SOURCE_COMMIT='24bfe492c4888caf1d989ddb22f36e5752829d46'
SOURCE_SHA='74263d8b18aec48fac21e3c3b25e26c890739c6b697503a9f6b91acf7c30c0e3'
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
    assert approval['cycle_id']=='CONSUMPTION-RUN-005' and approval['plan_sha256']==sha((HERE/'PLAN.json').read_bytes())
    assert approval['model_answers']==approval['native_sessions']==8 and approval['max_physical_rpc']==1032
    window=load('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')['performance_window']
    assert window['token']==approval['window_token'] and window['cycle_id']=='CONSUMPTION-RUN-005'
    assert str(window.get('status','')).startswith('granted'),'window_not_granted'
    expiry=window.get('expires_utc',window.get('deadline_utc'))
    assert expiry is not None,'explicit_window_expiry_required'
    now_ns=time.perf_counter_ns();now_utc=datetime.now(timezone.utc)
    end=datetime.fromisoformat(expiry.replace('Z','+00:00'))
    assert now_utc<end,'window_expired'
    assert window['owner']=='W-ENTRY' and window['max_sessions']==8 and window['max_RPC']==1032
    assert sha(PYTHON.read_bytes())==plan['python']['sha256'] and sys.version==plan['python']['version'],'changed_Python_runtime'
    return now_ns+int((end-now_utc).total_seconds()*1e9)


def argv_for(plan,cell,work,final):
    c=plan['codex']
    assert sha(Path(c['executable']).read_bytes())==c['sha256']
    settings=dict(c['settings'])
    common=dict(command=str(PYTHON),args=['-I',str(HERE/'bridge.py'),'--kind','native','--cell',str(cell)],
        cwd=str(work),required=True,startup_timeout_sec=20,tool_timeout_sec=180,
        tools={'execute_blender_code':{'approval_mode':'approve'}})
    settings['mcp_servers.native']=common
    if load(cell)['arm']=='P':
        settings['mcp_servers.human_eye']=dict(command=str(PYTHON),
            args=['-I',str(HERE/'bridge.py'),'--kind','he','--cell',str(cell)],cwd=str(work),
            required=True,enabled_tools=['human_eye_scene_observe'],startup_timeout_sec=20,tool_timeout_sec=180,
            tools={'human_eye_scene_observe':{'approval_mode':'approve'}})
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
COLLAB_TOOLS={'spawn_agent','send_input','wait','close_agent'}
COLLAB_STATUSES={'in_progress','completed','failed'}
COLLAB_AGENT_STATUSES={'pending_init','running','interrupted','completed','errored','shutdown','not_found'}


def collab_id(value):
    return value if type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value) else None


def collab_event(event):
    """Project only known public collaboration metadata; never copy a body."""
    if type(event) is not dict or event.get('type') not in ('item.started','item.updated','item.completed'):return None
    item=event.get('item')
    if type(item) is not dict or item.get('type')!='collab_tool_call':return None
    def enum(value,allowed):return value if type(value) is str and value in allowed else None
    receivers=item.get('receiver_thread_ids');states=item.get('agents_states')
    receiver_ids=None;receiver_ids_complete=False;agent_states=None;agent_states_complete=False
    if type(receivers) is list:
        receiver_ids=[identity for value in receivers if (identity:=collab_id(value)) is not None]
        receiver_ids_complete=len(receiver_ids)==len(receivers)
        receiver_ids=sorted(set(receiver_ids))
    if type(states) is dict:
        agent_states={};agent_states_complete=True
        for identity,value in states.items():
            safe_id=collab_id(identity)
            if safe_id is None:agent_states_complete=False;continue
            status=enum(value.get('status'),COLLAB_AGENT_STATUSES) if type(value) is dict else None
            agent_states[safe_id]={'status':status}
            if status is None:agent_states_complete=False
    return dict(phase=event['type'],item_id=collab_id(item.get('id')),call_key_source='item.id within this consume only',
        tool=enum(item.get('tool'),COLLAB_TOOLS),status=enum(item.get('status'),COLLAB_STATUSES),
        sender_thread_id=collab_id(item.get('sender_thread_id')),receiver_thread_ids=receiver_ids,
        receiver_ids_complete=receiver_ids_complete,agents_states=agent_states,agent_states_complete=agent_states_complete,
        extra_usage=None,usage_coverage='not exposed by verified public collab schema')


def new_collaboration():
    return dict(events=[],calls={},event_count=0,identifiable_call_count=0,unattributed_event_count=0,
        observed_thread_ids=[],observed_thread_id_count=0,extra_participant_count=None,
        extra_usage=None,accounting_complete=False,
        scope='public metadata in this consume; observed IDs include senders, not created-agent counts',
        incompleteness='collaboration usage/total participant coverage not exposed; no main-usage addition')


def retain_collaboration(record,projected,received_ns):
    state=record.setdefault('collaboration',new_collaboration())
    metadata=dict(projected,received_ns=received_ns if type(received_ns) is int and received_ns>=0 else None)
    state['events'].append(metadata);state['event_count']+=1
    observed=set(metadata['receiver_thread_ids'] or [])|set(metadata['agents_states'] or {})
    if metadata['sender_thread_id'] is not None:observed.add(metadata['sender_thread_id'])
    state['observed_thread_ids']=sorted(set(state['observed_thread_ids'])|observed)
    state['observed_thread_id_count']=len(state['observed_thread_ids'])
    identity=metadata['item_id']
    if identity is None:
        state['unattributed_event_count']+=1;return
    call=state['calls'].setdefault(identity,dict(phases=[],tools=[],statuses=[],terminal_statuses=[],
        observed_thread_ids=[],terminal_observed=False,terminal_status_conflict=False,tool_conflict=False))
    for field,value in [('phases',metadata['phase']),('tools',metadata['tool']),('statuses',metadata['status'])]:
        if value is not None and value not in call[field]:call[field].append(value)
    if metadata['phase']=='item.completed' and metadata['status'] in ('completed','failed'):
        if metadata['status'] not in call['terminal_statuses']:call['terminal_statuses'].append(metadata['status'])
        call['terminal_observed']=True
    call['terminal_status_conflict']=len(call['terminal_statuses'])>1;call['tool_conflict']=len(call['tools'])>1
    call['observed_thread_ids']=sorted(set(call['observed_thread_ids'])|observed)
    state['identifiable_call_count']=len(state['calls'])


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
    record=dict(parent_reaped=process is None,tree_reaped=process is None,parent_exit_code=None,
        taskkill_returncode=None,errors=[],scope='owned parent and reported live-PID taskkill tree; fallback parent reap is not tree proof')
    if process is None:return record
    if process.poll() is None:
        try:
            result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
            record['taskkill_returncode']=result.returncode
            record['tree_reaped']=result.returncode==0
        except (OSError,subprocess.TimeoutExpired) as exc:
            record['errors'].append(dict(stage='taskkill',type=type(exc).__name__,message=str(exc)))
        if not record['tree_reaped']:
            try:process.kill()
            except OSError as exc:record['errors'].append(dict(stage='parent_kill',type=type(exc).__name__,message=str(exc)))
    try:process.wait(timeout=5)
    except (OSError,subprocess.TimeoutExpired) as exc:
        record['errors'].append(dict(stage='parent_wait',type=type(exc).__name__,message=str(exc)))
        try:process.kill();process.wait(timeout=5)
        except (OSError,subprocess.TimeoutExpired) as final:
            record['errors'].append(dict(stage='parent_fallback',type=type(final).__name__,message=str(final)))
    record['parent_exit_code']=process.poll();record['parent_reaped']=record['parent_exit_code'] is not None
    return record


def process_exited(pid,timeout_ms=1000):
    """Read-only registered-PID wait: stopped/live/unknown; never signal a PID."""
    if type(pid) is not int or not 0<pid<2**32:return None
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=(ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong);kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_ulong)
    kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
    handle=kernel.OpenProcess(0x100000,False,int(pid))
    if not handle:return True if ctypes.get_last_error()==87 else None
    try:
        waited=kernel.WaitForSingleObject(handle,timeout_ms)
        return True if waited==0 else False if waited==258 else None
    finally:kernel.CloseHandle(handle)


def registered_tree_cleanup(cell):
    evidence=[]
    for kind in (['native','he'] if cell['arm']=='P' else ['native']):
        folder=Path(cell['audit_root'])/('bridge_'+kind)
        row=dict(kind=kind,confirmed=False,process_stopped=None,graceful_exit_receipt=None)
        evidence.append(row)
        try:
            started=load(folder/'STARTED.json')
            row['started']=started
            if (type(started) is not dict or type(started.get('pid')) is not int or not 0<started['pid']<2**32
                    or started.get('kind')!=kind or not isinstance(cell['ledger_path'],str) or not cell['ledger_path']
                    or started.get('ledger_path')!=cell['ledger_path']):
                raise ValueError('STARTED_identity_or_ledger_mismatch')
            row['process_stopped']=process_exited(started['pid'])
            try:row['graceful_exit_receipt']=load(folder/'EXIT.json')
            except FileNotFoundError:pass  # Optional receipt; retain the independent OS observation.
            else:
                if type(row['graceful_exit_receipt']) is not dict:raise ValueError('EXIT_receipt_invalid')
            ended=row['graceful_exit_receipt']
            if ended is not None and (type(ended.get('pid')) is not int or ended.get('pid')!=started['pid']
                    or ended.get('kind')!=kind or ended.get('ledger_path')!=cell['ledger_path']):
                raise ValueError('EXIT_identity_or_ledger_mismatch')
            if kind=='he':
                child=dict(process_stopped=None,graceful_exit_receipt=None)
                row['he_child']=child
                # This existing child identity belongs to the already-bound bridge audit directory.
                child['started']=load(folder/'HE_CHILD_STARTED.json')
                identity=child['started']
                if (type(identity) is not dict or type(identity.get('pid')) is not int or not 0<identity['pid']<2**32
                        or identity['pid']==started['pid']):
                    raise ValueError('HE_CHILD_STARTED_identity_invalid')
                child['process_stopped']=process_exited(identity['pid'])
                try:child['graceful_exit_receipt']=load(folder/'HE_CHILD_EXIT.json')
                except FileNotFoundError:pass
                else:
                    if type(child['graceful_exit_receipt']) is not dict:raise ValueError('HE_CHILD_EXIT_receipt_invalid')
                closed=child['graceful_exit_receipt']
                if closed is not None and (type(closed.get('pid')) is not int or closed.get('pid')!=identity['pid']):
                    raise ValueError('HE_CHILD_EXIT_identity_mismatch')
                if ended is not None and (type(ended.get('he_child_pid')) is not int or ended.get('he_child_pid')!=identity['pid']):
                    raise ValueError('EXIT_HE_child_identity_mismatch')
                row['confirmed']=row['process_stopped'] is True and child['process_stopped'] is True
            else:row['confirmed']=row['process_stopped'] is True
        except (OSError,ValueError,KeyError,TypeError) as exc:row['error']=str(exc)
    return dict(confirmed=all(e['confirmed'] for e in evidence),evidence=evidence,
        scope='registered native/HE bridge processes and HE-owned production child; arbitrary user-created Python descendants are not sandboxed')


def safe_environment(source):
    bindings={'CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID','APP_TOOLS_PIPE_PATH',
        'CODEX_APP_TOOLS_PIPE_PATH','CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY','CODEX_PERMISSION_PROFILE'}
    env={}
    for key in source:
        upper=key.upper()
        if key in bindings or upper.endswith(('_API_KEY','_ACCESS_TOKEN')) or upper in (
                'OPENAI_API_KEY','CODEX_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY'):
            continue  # Never read an excluded credential's value.
        env[key]=source[key]
    return env


def retain_startup_diagnostic(record,raw):
    """Small ordinary CLI templates only; never arbitrary stderr or values."""
    record['stderr_bytes']=record.get('stderr_bytes',0)+len(raw)
    state=record.setdefault('stderr_diagnostics',dict(lines=[],raw_bytes=0,retained_utf8_bytes=0,
        redacted_bytes=0,redacted_lines=0,truncated=False,unavailable=False,limit_bytes=4096))
    state['raw_bytes']+=len(raw)
    text=raw.decode('utf8',errors='replace').strip();safe=None
    forbidden=re.search(r'(?i)(bearer|authorization|api[_-]?key|access[_-]?token|password|secret|sk-|system|developer|reasoning|encrypted|<analysis|BEGIN.*KEY)',text)
    if len(raw)<=512 and not forbidden and not any(ord(c)<32 for c in text):
        if text in ('Error: failed to load bootstrap configuration','Error: failed to load configuration',
                    'Error loading configuration: invalid transport','Caused by:','invalid transport'):
            safe=text
        elif re.fullmatch(r'in `[A-Za-z_][A-Za-z0-9_.-]{0,159}`',text):safe=text
        elif re.fullmatch(r'Usage: (?:codex|codex.exe)(?: [A-Za-z0-9_<>{}\[\]|=-]+){0,24}',text):safe=text
        else:
            field=re.fullmatch(r'(?:Error: )?(unknown|missing|duplicate) field [`\'\"]([A-Za-z_][A-Za-z0-9_.-]{0,127})[`\'\"](?:, expected .*)?',text)
            flag=re.fullmatch(r'(?:error|Error): unexpected argument [\'`](--[A-Za-z0-9_-]{1,80})[\'`] found',text)
            if field:safe='configuration: '+field[1]+' field `'+field[2]+'`'
            elif flag:safe='error: unexpected argument `'+flag[1]+'` found'
            elif text.startswith('Error:') and 'permission profile' in text.lower() and 'sandbox' in text.lower():
                safe='Error: permission-profile/sandbox configuration conflict (details redacted)'
    if safe is not None:
        size=len(safe.encode('utf8'))+1
        if state['retained_utf8_bytes']+size<=state['limit_bytes']:
            state['lines'].append(safe);state['retained_utf8_bytes']+=size;return
        state['truncated']=True
    if text:
        state['redacted_bytes']+=len(raw);state['redacted_lines']+=1;state['unavailable']=True


def consume(plan,cell,work,prompt):
    from bridge import Budget
    budget=Budget(cell);folder=Path(cell['audit_root']);final=folder/'final.txt'
    cell_path=folder/'CELL.json';argv=argv_for(plan,cell_path,work,final)
    env=safe_environment(os.environ)
    record=dict(argv=argv,started_ns=time.perf_counter_ns(),public_events=[],discarded_event_types={},
        collaboration=new_collaboration(),
        tool_actions_observed=0,provider_requests=None,fees=None,backend='unexposed',usage=None,
        complete=False,deadline_enforcement='controller kill from original dispatch deadline',
        action_policy='8 is observation threshold only; all actions/costs retained without threshold failure')
    record.update(consumer_pid=None,consumer_popen_ns=None,first_public_tool_ns=None,final_received_ns=None,turn_completed_ns=None,
        process_exit_ns=None,cleanup_end_ns=None,timestamp_scope='same perf counter, local receive/wait observations, not server generation')
    process=None;threads=[];timer=None;deadline_fired=threading.Event();reap_lock=threading.Lock();cleanup_receipts=[]
    def reap():
        with reap_lock:
            receipt=kill_tree(process)
            if isinstance(receipt,dict):cleanup_receipts.append(receipt)
    def expire():
        deadline_fired.set()
        try:reap()
        except BaseException:pass  # main finally records the actual reap outcome
    lines=queue.Queue()
    def read(stream,label):
        for raw in iter(stream.readline,b''):lines.put((label,raw,time.perf_counter_ns()))
        lines.put((label,None,time.perf_counter_ns()))
    closed=0;candidate=None;seen=set()
    try:
        # Original absolute deadline also interrupts blocking I/O/parse paths;
        # it never depends on coordinator polling or a new relative timeout.
        timer=threading.Timer(budget.remaining(),expire);timer.daemon=True;timer.start()
        budget.remaining()
        record['consumer_popen_ns']=time.perf_counter_ns()
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=work,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        record['consumer_pid']=process.pid
        if deadline_fired.is_set():raise TimeoutError('deadline_during_process_start')
        threads=[threading.Thread(target=read,args=(stream,label),daemon=True) for stream,label in
            ((process.stdout,'stdout'),(process.stderr,'stderr'))]
        for thread in threads:thread.start()
        process.stdin.write(prompt);process.stdin.close()
        while closed<2:
            remaining=(cell['deadline_perf_ns']-time.perf_counter_ns())/1e9
            if remaining<=0:raise TimeoutError('original_answer_180s_deadline')
            try:label,raw,received_ns=lines.get(timeout=min(.05,remaining))
            except queue.Empty:
                if load(cell['ledger_path'])['halted']:raise RuntimeError('shared_budget_halted')
                continue
            if raw is None:closed+=1;continue
            if label=='stderr':
                retain_startup_diagnostic(record,raw);continue
            record['stdout_bytes']=record.get('stdout_bytes',0)+len(raw)
            try:event=json.loads(raw)
            except ValueError:raise ValueError('unsupported_non_JSON_exec_event')
            collaboration=collab_event(event)
            if collaboration is not None:retain_collaboration(record,collaboration,received_ns)
            public=public_event(event)
            if public is not None:
                public['received_ns']=received_ns
                record['public_events'].append(public)
                if public['type']=='turn.completed':
                    record['usage']=public['usage'];record['complete']=True;record['turn_completed_ns']=received_ns
            else:
                tag=event.get('item',{}).get('type',event.get('type','unknown'))
                record['discarded_event_types'][tag]=record['discarded_event_types'].get(tag,0)+1
            item=event.get('item',{})
            if event.get('type')=='item.completed' and item.get('type')=='agent_message':
                candidate=item.get('text','');record['final_received_ns']=received_ns
            if event.get('type')=='item.started' and item.get('type') in PUBLIC_TOOL_TYPES:
                if record['first_public_tool_ns'] is None:record['first_public_tool_ns']=received_ns
                identity=item.get('id', 'anonymous-'+str(record['tool_actions_observed']+1))
                if identity not in seen:
                    seen.add(identity);record['tool_actions_observed']+=1
                    record['above_action_observation_threshold']=record['tool_actions_observed']>8
            if event.get('type')=='item.completed' and item.get('type')=='command_execution':
                budget.charge_public(len(str(item.get('aggregated_output','')).encode()),'builtin_shell_observed_after_delivery')
        process.wait(timeout=max(.01,(cell['deadline_perf_ns']-time.perf_counter_ns())/1e9))
        record['process_exit_ns']=time.perf_counter_ns()
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
        if process is not None and process.poll() is not None and record['process_exit_ns'] is None:
            record['process_exit_ns']=time.perf_counter_ns()
        record['cleanup_receipts']=cleanup_receipts
        tree=any(r.get('tree_reaped') for r in cleanup_receipts)
        if not tree and process is not None and process.poll() is not None and cell.get('arm') in ('N','P'):
            record['registered_tree_cleanup']=registered_tree_cleanup(cell)
            tree=record['registered_tree_cleanup']['confirmed']
        record['tree_reaped']=bool(tree or process is None)
        record['cleanup_end_ns']=time.perf_counter_ns()
        record.update(exit_code=None if process is None else process.poll(),
            process_spawned=process is not None,process_reaped=process is not None and process.poll() is not None,finished_ns=time.perf_counter_ns())
        record['deadline_timer_fired']=deadline_fired.is_set()
        record['safe_to_continue']=record['tree_reaped'] and (process is None or record['process_reaped'])
        if not record['safe_to_continue']:record['valid_completion']=False
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


def run_cell(plan, entry, task, native, folder, *, window_deadline_ns):
    from bridge import Budget
    began=time.perf_counter_ns();owner=None;start_attempted=False;consumer_attempted=False
    public_root=Path(plan['neutral_run_root'])/str(entry['ordinal']).zfill(2)
    record=dict(entry,status='running',dispatch_ns=began,host_ready_ns=None,denominator=1,
        safe_to_continue=True,consumer=None,cleanup_verified=None)
    try:
        if window_deadline_ns-began<240_000_000_000:
            record.update(status='not_run',reason='insufficient_window_for_original_answer_and_cleanup');return record
        folder.mkdir(exist_ok=False)
        public_root.mkdir(parents=True,exist_ok=False);work=public_root/'work';work.mkdir()
        chain_deadline=min(began+600_000_000_000,window_deadline_ns)
        answer_deadline=min(began+180_000_000_000,chain_deadline-60_000_000_000)
        prompt=(BASE/'materials'/task['prompt_path']).read_bytes()
        assert sha(prompt)==task['prompt_utf8_sha256']
        asset=public_root/'input.blend';shutil.copyfile(task['source_asset_path'],asset)
        assert sha(asset.read_bytes())==task['asset_sha256']
        material=load(BASE/'materials/MATERIAL_MANIFEST.json')
        helper_path=BASE/'materials'/material['neutral_helper']['local_path']
        start_attempted=True
        owner=native.NativeSession.start(blender=plan['blender'],asset=asset,workspace=public_root/'native',
            deadline_ns=chain_deadline,condition=entry['arm'],expected_asset_sha256=task['asset_sha256'],max_calls=128)
        record['host_ready_ns']=time.perf_counter_ns()
        cell=dict(entry,dispatch_ns=began,audit_root=str(folder),ledger_path=str(folder/'BUDGET.json'),
            deadline_perf_ns=answer_deadline,endpoint=dict(host=owner.host,port=owner.port),
            native_workspace=str(owner.workspace),native_helper=str(helper_path),
            native_helper_sha256=material['neutral_helper']['sha256'],source_sha256=SOURCE_SHA,
            source_root=str(public_root/'sources'),product_manifest=plan['product_manifest'],
            action_observation_threshold=8,max_native_rpc=128,max_public_text_bytes=1048576,
            image_limits=dict(max_images=1,max_single_pixels=589824,max_total_pixels=589824),
            max_image_dimension=768,max_constructed_images=1,he_config=str(folder/'he_config.json'),
            he_argv=[str(PYTHON),'-I',str(HERE/'he_bootstrap.py'),str(folder/'CELL.json')],he_cwd=str(folder))
        if entry['arm']=='P':
            with zipfile.ZipFile(HERE/'PRODUCT_BYTES.zip') as archive:archive.extractall(public_root/'sources')
            save(cell['he_config'],dict(schema_version='1.0',enabled=True,project_root=cell['source_root'],
                state_file=str(folder/'state.json'),audit_file=str(folder/'he_audit.jsonl'),
                expected_identity=dict(source_sha256=SOURCE_SHA),blender=dict(host=owner.host,port=owner.port,timeout_s=30),request_budget_s=30))
        save(folder/'CELL.json',cell);Budget.create(cell);Budget(cell).charge_public(len(prompt),'exact_question_prompt')
        consumer_attempted=True;record['safe_to_continue']=False
        record['consumer']=consume(plan,cell,work,prompt)
        record['safe_to_continue']=record['consumer']['safe_to_continue']
        record['status']='completed' if record['consumer']['valid_completion'] else 'error'
    except BaseException as exc:
        record.update(status='error',error_type=type(exc).__name__,reason=str(exc),valid_completion=False)
        if consumer_attempted:record['safe_to_continue']=False
        if start_attempted and owner is None:
            failure=public_root/'native/START_FAILURE.json'
            receipt=load(failure) if failure.exists() else None
            record['native_start_failure']=receipt
            record['safe_to_continue']=receipt is not None and receipt.get('cleanup_errors')==[]
    finally:
        if owner is not None:
            try:record['close']=close_meter(native,owner,folder)
            except BaseException as exc:
                record['close_error']=dict(type=type(exc).__name__,message=str(exc));record['close']={}
                try:owner._kill()
                except BaseException as stop:record['kill_error']=str(stop)
            closed_path=owner.workspace/'WORKER_CLOSED.json'
            closed=load(closed_path) if closed_path.exists() else {}
            record['closed_worker']=closed;record['native_session']=owner.config
            receipt=record['close']
            record['cleanup_verified']=(receipt.get('response',{}).get('status')=='closed' and receipt.get('error') is None
                and receipt.get('process_reaped') and receipt.get('exit_code')==0 and receipt.get('source_file_unchanged')
                and receipt.get('protected_files_unchanged') and closed.get('poisoned') is False
                and closed.get('initial_geometry_fingerprint')==closed.get('final_geometry_fingerprint'))
            record['safe_to_continue']=record['safe_to_continue'] and bool(record['cleanup_verified'])
        record['cleanup_end_ns']=time.perf_counter_ns();record['whole_cell_ns']=record['cleanup_end_ns']-began
        consumer=record.get('consumer') or {}
        for key in ('consumer_popen_ns','first_public_tool_ns','final_received_ns','turn_completed_ns','process_exit_ns'):
            record[key]=consumer.get(key)
        final=record['final_received_ns']
        record['answer_receive_latency_ns']=None if final is None else final-began
        record['valid_comparison']=None
        record['comparison_review']='independent quality/context/access/image review;8actions threshold never failure'
        if folder.is_dir():save(folder/'RESULT.json',record)
    return record


def planned_result(plan):
    return dict(scheduled=8,cells=[dict(entry,status='planned',reason=None,denominator=1,
        dispatch_ns=None,host_ready_ns=None,consumer_popen_ns=None,first_public_tool_ns=None,
        final_received_ns=None,turn_completed_ns=None,process_exit_ns=None,cleanup_end_ns=None)
        for entry in plan['cells']],provider_requests=None,fees=None,no_retries=True)


def execute_slots(plan,approval,material,native,output,*,window_deadline_ns,result=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result=planned_result(plan) if result is None else result;save(output/'RESULTS.json',result)
    specs={task['task_id']:task for task in material['tasks']};stop=None
    for index,slot in enumerate(result['cells']):
        if stop or window_deadline_ns-time.perf_counter_ns()<240_000_000_000:
            slot.update(status='not_run',reason=stop or 'insufficient_window_for_original180s_plus60s_cleanup')
            save(output/'RESULTS.json',result);continue
        slot['status']='running';save(output/'RESULTS.json',result)
        try:
            entry=plan['cells'][index]
            record=run_cell(plan,entry,specs[entry['task_id']],native,output/str(index+1).zfill(2),window_deadline_ns=window_deadline_ns)
            slot.update(record)
            if not record.get('safe_to_continue',False):stop='previous_slot_cleanup_not_confirmed_no_further_start'
        except BaseException as exc:
            slot.update(status='error',error_type=type(exc).__name__,reason=str(exc),safe_to_continue=False)
            stop='previous_slot_unhandled_preparation_or_cleanup_error'
        save(output/'RESULTS.json',result)
    return result


def run(approval_path):
    run_started=time.perf_counter_ns();plan=load(HERE/'PLAN.json');approval=load(approval_path)
    window_deadline_ns=require_ready(plan,approval)
    output=HERE/'actual_01';output.mkdir(exist_ok=False)
    result=planned_result(plan);save(output/'RESULTS.json',result)
    save(output/'STARTED.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),approval=approval,
        run_started_ns=run_started,window_deadline_ns=window_deadline_ns,preflight_management_ns=time.perf_counter_ns()-run_started))
    try:
        material=load(BASE/'materials/MATERIAL_MANIFEST.json')
        helper_path=BASE/'materials'/material['neutral_helper']['local_path']
        raw=helper_path.read_bytes();assert sha(raw)==material['neutral_helper']['sha256']
        native=types.ModuleType('_consumption_owned_native');native.__file__=str(helper_path)
        sys.modules[native.__name__]=native;exec(compile(raw,str(helper_path),'exec',dont_inherit=True),native.__dict__)
        result=execute_slots(plan,approval,material,native,output,window_deadline_ns=window_deadline_ns,result=result)
    except BaseException as exc:
        for slot in result['cells']:
            if slot['status'] in ('planned','running'):slot.update(status='not_run',reason='batch_setup_error:'+str(exc))
        result['batch_error']=dict(type=type(exc).__name__,message=str(exc))
    finally:
        result.update(run_started_ns=run_started,run_wall_through_result_construction_ns=time.perf_counter_ns()-run_started,
            clock_scope='local observations; includes preflight/cells/close, excludes interpreter startup/final record write')
        save(output/'RESULTS.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--approval',type=Path,required=True)
    args=parser.parse_args();run(args.approval)
