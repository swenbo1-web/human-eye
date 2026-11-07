"""Two bounded ordinary adapter qualifications for the frozen author fixtures."""
import ctypes
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import sysconfig
import threading
import time
from verification import visual004_native as native
from verification.visual004_session import client, load_broker_ready

ROOT=Path(__file__).resolve().parents[1]
PIN='14c22c391b83eb4cb7d4c6523a13d4e36d0609293a502c0a4f40a0ee0a0e3d88'
READBACK="""import json
print(json.dumps({obj.name:dict(vertices=[list(v.co) for v in obj.data.vertices],
faces=[list(p.vertices) for p in obj.data.polygons], matrix=[list(r) for r in obj.matrix_world],
modifiers=len(obj.modifiers)) for obj in bpy.data.objects if obj.type=='MESH'}))
"""
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
kernel.OpenProcess.restype=ctypes.c_void_p
kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
kernel.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
kernel.CloseHandle.argtypes=[ctypes.c_void_p]
def utc():return datetime.now(timezone.utc).isoformat()
def need(value,reason):
    if not value:raise ValueError(reason)
def run_case(case):
    folder=ROOT/'qualification'/case
    folder.mkdir(parents=True,exist_ok=False)
    workspace=folder/'session'
    author=ROOT/'author'/case
    launcher=Path(sysconfig.get_path('purelib'))/'verification/perf010_qualification.py'
    tool=launcher.with_name('perf000_scene_tool.py')
    command=[sys.executable,'-I','-B',str(launcher),'--asset',str(author/'scene.blend'),
        '--workspace',str(workspace),'--blender','D:/Tools/blender5.2/blender.exe',
        '--condition','P','--pin',PIN,'--expected-asset-sha256',native.sha(author/'scene.blend'),'--seconds','120']
    if case=='S':command+=['--qa-vertex-patch',str(author/'qa_patch.json')]
    record=dict(case=case,started_utc=utc(),command=command,observes_started=0,
        raw_readbacks_started=0,updates_started=0,states=[],forced_cleanup=[],passed=False)
    native.save(folder/'START.json',record)
    process=None
    handle=None
    timer=None
    started=time.perf_counter_ns()
    def stop():
        event=dict(utc=utc())
        if process is not None and process.poll() is None:
            result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,text=True,
                timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
            event['taskkill_exit']=result.returncode
        if handle and kernel.WaitForSingleObject(handle,0)==258:
            event['worker_terminate']=bool(kernel.TerminateProcess(handle,124))
        record['forced_cleanup'].append(event)
    try:
        with (folder/'service.stdout.log').open('xb') as out,(folder/'service.stderr.log').open('xb') as err:
            process=subprocess.Popen(command,stdout=out,stderr=err,stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,cwd=str(folder))
        record['launcher_pid']=process.pid
        timer=threading.Timer(120,stop);timer.daemon=True;timer.start()
        deadline=time.monotonic()+115
        while not (workspace/'BROKER_READY.json').exists():
            need(process.poll() is None and time.monotonic()<deadline,'Startup failed')
            time.sleep(.02)
        ready=load_broker_ready(workspace);record['ready']=ready
        handle=kernel.OpenProcess(0x00100000|0x1000|1,False,ready['worker_pid'])
        need(handle,'Cannot retain worker handle')
        record['raw_readbacks_started']+=1
        raw=client(workspace,dict(request_id='qualification-raw',operation='native_run',args=dict(code=READBACK)))
        native.save(folder/'RAW_READBACK_REPLY.json',raw)
        need(raw.get('ok') and raw.get('operation_succeeded'),'Raw readback failed')
        current=json.loads(raw['result']['stdout'])
        need(current==native.load(author/'BUILD_READBACK.json'),'Actual loaded float32 geometry differs from builder readback')
        states=('initial','changed') if case=='S' else ('initial',)
        for state in states:
            if state=='changed':
                record['updates_started']+=1
                receipt=native.NativeSession.open(workspace).qa_advance()
                native.save(folder/'QA_ADVANCE_RECEIPT.json',receipt)
                need(receipt['response']['status']=='success' and receipt['response']['result']['vertices_written']==4,'QA update failed')
            query=dict(mode='task',objects=[dict(name='Object_01'),dict(name='Object_02')],requested_facts=['pair_relation'])
            cli=[sys.executable,'-I','-B',str(tool),'observe','--workspace',str(workspace),
                 '--query-literal',repr(query),'--detail','brief']
            record['observes_started']+=1
            before=time.perf_counter_ns()
            response=subprocess.run(cli,capture_output=True,timeout=25)
            wall=time.perf_counter_ns()-before
            (folder/(state+'.CLI.stdout')).write_bytes(response.stdout)
            (folder/(state+'.CLI.stderr')).write_bytes(response.stderr)
            row=dict(state=state,command=cli,cli_process_wall_ns=wall,exit_code=response.returncode,
                stdout_bytes=len(response.stdout),stderr_bytes=len(response.stderr))
            record['states'].append(row)
            need(response.returncode==0,'Qualification observe transport failed')
            payload=json.loads(response.stdout.decode('utf8'));row['payload']=payload
            need(payload['binding']['runtime_source_sha256']==PIN,'Qualification source pin')
            fact=payload['facts']['pair_relation']
            if case=='S':
                need(payload['status']=='observed' and fact['status']=='measured','Supported fixture fact incomplete')
                value=fact['value']
                if state=='initial':
                    need(value['relation']=='separated' and abs(value['surface_gap_m']-5/128)<=1e-6,'S initial relation or gap')
                    need(all(abs(a-b)<=1e-6 for a,b in zip(value['nearest_witness']['direction_a_to_b'],[-.8,.6,0])),'S initial direction')
                else:
                    need(value['relation']=='penetrating' and value.get('evidence'),'S changed relation or numeric evidence')
                    need(payload['binding']['scene_fingerprint']!=record['states'][0]['payload']['binding']['scene_fingerprint'],'Changed capture not current')
            else:
                need(payload['status']=='partial' and fact['status']=='unknown','G unexpectedly supported')
                need(fact.get('reason'),'G missing unknown reason')
        record['passed']=True
    except BaseException as exc:
        record['error']=dict(type=type(exc).__name__,message=str(exc))
    finally:
        if process is not None and process.poll() is None:
            try:record['close_reply']=client(workspace,dict(request_id='qualification-close',operation='close',args={}))
            except BaseException as exc:record['close_error']=dict(type=type(exc).__name__,message=str(exc))
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stop();process.wait(timeout=8)
        if timer is not None:
            timer.cancel();timer.join(timeout=9);record['watchdog_joined']=not timer.is_alive()
        record['launcher_exit_code']=None if process is None else process.poll()
        if handle:
            state=kernel.WaitForSingleObject(handle,0)
            if state==258:
                stop();state=kernel.WaitForSingleObject(handle,5000)
            exit_code=ctypes.c_uint32()
            record['worker_exited']=state==0
            record['worker_exit_code']=exit_code.value if kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) else None
            kernel.CloseHandle(handle)
        record.update(ended_utc=utc(),startup_to_reap_ns=time.perf_counter_ns()-started)
        record['passed']=bool(record['passed'] and not record['forced_cleanup'] and record.get('worker_exited')
            and record.get('watchdog_joined') and record['launcher_exit_code']==record.get('worker_exit_code')==0)
        native.save(folder/'RESULT.json',record)
    return record

results=[]
for case in ('S','G'):
    result=run_case(case);results.append(result)
    if not result['passed']:break
summary=dict(passed=len(results)==2 and all(row['passed'] for row in results),
    observe_count=sum(row['observes_started'] for row in results),
    raw_readback_count=sum(row['raw_readbacks_started'] for row in results),
    qa_update_count=sum(row['updates_started'] for row in results),cases=results)
native.save(ROOT/'QUALIFICATION.json',summary)
print(json.dumps(dict(passed=summary['passed'],observe_count=summary['observe_count'],
    raw_readback_count=summary['raw_readback_count'],qa_update_count=summary['qa_update_count'],
    errors=[row.get('error') for row in results])))
raise SystemExit(0 if summary['passed'] else 1)
