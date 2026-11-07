"""Two bounded ordinary adapter qualifications for the frozen author fixtures."""
import ctypes
from datetime import datetime, timezone
import importlib.util
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
PIN='fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509'
truth_spec=importlib.util.spec_from_file_location('evidence_fixture_truth',ROOT/'qa/fixture_truth.py')
fixture_truth=importlib.util.module_from_spec(truth_spec)
truth_spec.loader.exec_module(fixture_truth)
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

def dot(a,b):return sum(x*y for x,y in zip(a,b))
def point_on_triangles(point,mesh):
    for face in mesh['faces']:
        a,b,c=[mesh['vertices'][i] for i in face]
        ab=[b[k]-a[k] for k in range(3)]
        ac=[c[k]-a[k] for k in range(3)]
        q=[point[k]-a[k] for k in range(3)]
        aa,cc,bc=dot(ab,ab),dot(ac,ac),dot(ab,ac)
        determinant=aa*cc-bc*bc
        if determinant<=0:continue
        u=(dot(q,ab)*cc-dot(q,ac)*bc)/determinant
        v=(dot(q,ac)*aa-dot(q,ab)*bc)/determinant
        residual=[q[k]-u*ab[k]-v*ac[k] for k in range(3)]
        if u>=-1e-10 and v>=-1e-10 and u+v<=1+1e-10 and math.hypot(*residual)<=1e-9:
            return True
    return False

def check_surface(payload,truth,current,case):
    expected=truth['expected']
    need(payload['result_kind']=='task_query' and payload['schema_version']=='task-query-v3','Existing task response')
    need(payload['unit']=='m' and payload['coordinate_frame']=='world' and payload['pair_order']=='A_to_B','World metres and order')
    need(payload['status']==('observed' if case=='S' else 'partial'),'Complete S or genuinely mixed G task status')
    need(set(payload['facts'])==({'surface_proximity'} if case=='S' else {'surface_proximity','solid_relation'}),'Exactly requested facts')
    need(payload['binding']['runtime_source_sha256']==PIN,'Qualification source pin')
    need(payload['binding']['capture_scope']=='selected_objects' and payload['binding']['selected_count']==2,'Selected-object binding')
    need([row['name'] for row in payload['binding']['objects']]==expected['objects'],'Current ordered object binding')
    fact=payload['facts']['surface_proximity']
    need(fact['status']=='measured' and fact['witness_status']=='measured','Known surface fact and original witnesses')
    need(fact['method']=='exact_binary64_triangle_surface_features_v2','Accepted B math identity')
    need(fact['semantics']=='current_evaluated_triangle_surfaces_world_metres','Surface provenance')
    value=fact['value']
    need(value['distance_m']>=0 and abs(value['distance_m']-expected['distance_m'])<=1e-12,'Independent surface distance')
    need([row['boundary_edge_count'] for row in value['topology']]==expected['boundary_edges'],'Boundary-edge counts')
    need([row['nonmanifold_edge_count'] for row in value['topology']]==expected['nonmanifold_edges'],'Nonmanifold-edge counts')
    witness=value['nearest_witness'];a,b=witness['a'],witness['b']
    need(abs(math.dist(a,b)-expected['distance_m'])<=1e-9,'Published witness distance')
    for point,name in zip((a,b),expected['objects']):
        need(point_on_triangles(point,current[name]),'Witness on current original triangle surface')
    if expected['distance_m']==0:
        need(a==b and fact['direction_status']=='not_applicable' and witness['direction_a_to_b'] is None,'True zero and inapplicable direction')
    else:
        need(fact['direction_status']=='measured','Positive-distance direction known')
        need(len(witness['direction_a_to_b'])==3,'Three-component direction')
        need(all(abs(x-y)<=1e-12 for x,y in zip(witness['direction_a_to_b'],expected['direction_a_to_b'])),'Independent A-to-B direction')
    if case=='G':
        solid=payload['facts']['solid_relation']
        need(solid['status']=='unknown' and bool(solid.get('reason')),'Open-surface solid remains unknown with reason')
    return dict(complete=True,independent_distance_m=expected['distance_m'],
        independent_exact_squared_distance=expected['exact_squared_distance'],
        original_surface_witnesses=True,known_surface_retained=True,
        direction_status=fact['direction_status'],solid_status=None if case=='S' else payload['facts']['solid_relation']['status'])

def run_case(case):
    folder=ROOT/'qualification'/case
    folder.mkdir(parents=True,exist_ok=False)
    workspace=folder/'session'
    author=ROOT/'author'/case
    launcher=Path(sysconfig.get_path('purelib'))/'verification/perf010_qualification.py'
    tool=launcher.with_name('perf000_scene_tool.py')
    command=[sys.executable,'-I','-B',str(launcher),'--asset',str(author/'scene.blend'),
        '--workspace',str(workspace),'--blender','D:/Tools/blender5.2/blender.exe',
        '--condition','P','--pin',PIN,'--source-count','131',
        '--expected-asset-sha256',native.sha(author/'scene.blend'),'--seconds','120']
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
        record['assignment_geometry']=fixture_truth.validate_readback(case,current)
        native.save(folder/'RAW_ASSIGNMENT_CHECK.json',record['assignment_geometry'])
        need(set(current)=={'Object_01','Object_02'},'Only the assigned two meshes')
        expected_counts=(12,12) if case=='S' else (25,32)
        for mesh in current.values():
            need((len(mesh['vertices']),len(mesh['faces']))==expected_counts,'Fixed new mesh size')
            need(all(len(face)==3 for face in mesh['faces']),'Frozen triangle faces')
            need(mesh['matrix']==[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
                 and mesh['modifiers']==0,'Identity transform and no modifiers')
        truth=native.load(author/'TRUTH.json')
        states=('initial',)
        for state in states:
            requested=['surface_proximity'] if case=='S' else ['surface_proximity','solid_relation']
            query=dict(mode='task',objects=[dict(name='Object_01'),dict(name='Object_02')],requested_facts=requested)
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
            row['verified']=check_surface(payload,truth,current,case)
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
            and record.get('watchdog_joined') and record['launcher_exit_code']==record.get('worker_exit_code')==0
            and record.get('close_reply',{}).get('result',{}).get('process_reaped') is True
            and record.get('close_reply',{}).get('result',{}).get('source_file_unchanged') is True
            and record.get('close_reply',{}).get('result',{}).get('protected_files_unchanged') is True)
        native.save(folder/'RESULT.json',record)
    return record

results=[]
for case in ('S','G'):
    result=run_case(case);results.append(result)
summary=dict(passed=len(results)==2 and all(row['passed'] for row in results),
    observe_count=sum(row['observes_started'] for row in results),
    raw_readback_count=sum(row['raw_readbacks_started'] for row in results),
    qa_update_count=sum(row['updates_started'] for row in results),cases=results)
native.save(ROOT/'QUALIFICATION.json',summary)
print(json.dumps(dict(passed=summary['passed'],observe_count=summary['observe_count'],
    raw_readback_count=summary['raw_readback_count'],qa_update_count=summary['qa_update_count'],
    errors=[row.get('error') for row in results])))
raise SystemExit(0 if summary['passed'] else 1)
