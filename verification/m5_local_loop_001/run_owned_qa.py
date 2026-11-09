"""One bounded 0/1/multiple-step owned QA sequence on an explicitly pinned root.

This uses real default BlenderProcessHost + OwnedGoalScheduler. Run separately
for accepted Git baseline and candidate; never switches or edits a checkout.
Observers add unquantified overhead, included in recorded times.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE=Path(__file__).resolve().parent
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)
COUNTS=Counter()
TIMES=Counter()
ACTIVE={}
RUNTIME_ROOT=None
NAMES={'_validated_scene','from_dict','measure_pair_geometry','solve_segment_candidate',
       'solve_clearance_candidate','solve_support_plane_candidate','_first_step_plan',
       'evaluate_spatial_goal','_save','_runtime','_locked','_capture','_discover',
       'execute_action','_capture_request','capture_evidence','capture_scene',
       '_before_model_on_captured_scene'}

def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def append(path,value):
    with Path(path).open('a',encoding='utf8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')

def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line] if Path(path).exists() else []

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def profile(frame,event,arg):
    code=frame.f_code
    if code.co_name=='__init__':
        instance=frame.f_locals.get('self')
        if instance is None or type(instance).__name__!='MeshEntity3D': return
        module=sys.modules.get(type(instance).__module__)
        filename=getattr(module,'__file__','').replace('\\','/')
        qualified='MeshEntity3D.__init__'
    else:
        if code.co_name not in NAMES: return
        filename=code.co_filename.replace('\\','/')
        qualified=code.co_qualname
    if not filename.startswith(str(RUNTIME_ROOT).replace('\\','/')+'/'): return
    key=filename.rsplit('/',1)[-1]+':'+qualified
    if event=='call':
        COUNTS[key]+=1
        ACTIVE[id(frame)]=time.perf_counter_ns()
    elif event=='return':
        begin=ACTIVE.pop(id(frame),None)
        if begin is not None: TIMES[key]+=time.perf_counter_ns()-begin

def diff(after,before):
    return {key:after[key]-before.get(key,0) for key in after
            if type(after[key]) is int and after[key]!=before.get(key,0)}

class Wire:
    def __init__(self,folder): self.folder,self.lock,self.counts=folder,threading.Lock(),Counter()
    def record(self,name,data):
        with self.lock:
            with (self.folder/name).open('ab') as stream: stream.write(data)
            self.counts[name]+=len(data)

class BinaryTee(io.BufferedIOBase):
    def __init__(self,stream,wire,name):
        super().__init__();self.stream,self.wire,self.name=stream,wire,name
    def readable(self): return self.stream.readable()
    def writable(self): return self.stream.writable()
    def seekable(self): return False
    def fileno(self): return self.stream.fileno()
    def read(self,size=-1):
        data=self.stream.read(size);self.wire.record(self.name,data);return data
    def read1(self,size=-1):
        data=self.stream.read1(size);self.wire.record(self.name,data);return data
    def readinto(self,buffer):
        count=self.stream.readinto(buffer)
        if count: self.wire.record(self.name,bytes(memoryview(buffer)[:count]))
        return count
    def write(self,data):
        count=self.stream.write(data)
        if count: self.wire.record(self.name,bytes(memoryview(data)[:count]))
        return count
    def flush(self):
        if not self.stream.closed: return self.stream.flush()
    def close(self):
        if not self.closed: super().close();self.stream.close()

def observe_text(stream,wire,name):
    encoding,errors=stream.encoding,stream.errors
    line_buffering,write_through=stream.line_buffering,stream.write_through
    raw=stream.detach()
    return io.TextIOWrapper(BinaryTee(raw,wire,name),encoding=encoding,errors=errors,
        newline=None,line_buffering=line_buffering,write_through=write_through)

def native_check(before,after,target,expected_steps):
    old={obj['name']:obj for obj in before['meshes']}
    new={obj['name']:obj for obj in after['meshes']}
    assert set(old)==set(new)
    for name in old:
        if name!='BluePart': assert new[name]==old[name],name
    focal,previous=new['BluePart'],old['BluePart']
    for key in ('local_vertices','faces','color'): assert focal[key]==previous[key],key
    zdelta=focal['matrix'][2][3]-previous['matrix'][2][3]
    for r in range(4):
        for c in range(4):
            if (r,c)!=(2,3): assert focal['matrix'][r][c]==previous['matrix'][r][c]
    for left,right in zip(previous['vertices'],focal['vertices']):
        assert left[:2]==right[:2]
        assert abs((right[2]-left[2])-zdelta)<1e-7
    gap=min(v[2] for v in focal['vertices'])-max(v[2] for v in new['GreyBase']['vertices'])
    assert abs(gap-target)<=1e-6,(gap,target)
    if expected_steps=='zero': assert zdelta==0.
    else: assert zdelta<0.
    return {'gap_m':gap,'target_m':target,'error_m':abs(gap-target),'focal_z_translation_m':zdelta,
            'other_objects_unchanged':len(old)-1,'basis':'direct native RNA world points, rigid fixture horizontal faces'}

def main():
    global RUNTIME_ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',type=Path,required=True)
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fixture-root',type=Path,help='Copy byte-identical generated baseline case fixtures')
    parser.add_argument('--blender',type=Path,default=Path('D:/Tools/blender5.2/blender.exe'))
    args=parser.parse_args()
    RUNTIME_ROOT=args.runtime_root.resolve()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(RUNTIME_ROOT))
    # Imports occur only once the caller has fixed and authorized this root.
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
    from human_eye_plugin.goal_budget import GoalBudgetLimits
    from human_eye_plugin.task_authority import ClearanceTaskSpec,TaskApproval,TrustedTaskAuthority
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity(mode='live')
    assert identity['source_sha256']==args.expected_source_sha256,identity['source_sha256']
    for row in identity['source_files']: assert sha(RUNTIME_ROOT/row['path'])==row['sha256'],row['path']
    save(output/'identity_before.json',identity)
    for name in ('run_owned_qa.py','worker_observer.py','create_fixture.py'):
        shutil.copyfile(HERE/name,output/(name+'.txt'))
    result={'passed':False,'runtime_root':str(RUNTIME_ROOT),'source_sha256':identity['source_sha256'],
        'source_count':len(identity['source_files']),'cases':[],
        'timing_scope':'loop_ms strictly scheduler.run call; lifecycle includes owned host startup/setup/verification/close; observer overhead included, not subtracted',
        'geometry_scope':'actual Python host capture/setter entries and resident counters; nonresident to_mesh/triangulation unknown',
        'model_calls':0,'user_assets':0}
    batch_started=time.perf_counter_ns()
    try:
        for label,target in [('zero',.004),('one',.0035),('multi',.001)]:
            folder=output/label;folder.mkdir()
            fixture=folder/'fixture.blend'
            if args.fixture_root is not None:
                fixture_origin=args.fixture_root.resolve()/label/'fixture.blend'
                shutil.copyfile(fixture_origin,fixture)
                assert sha(fixture_origin)==sha(fixture)
                save(folder/'fixture_copy.json',{'origin':str(fixture_origin),'sha256':sha(fixture)})
            else:
                creation_command=[str(args.blender),'--factory-startup','--disable-autoexec','--background',
                    '--python',str(HERE/'create_fixture.py'),'--',str(fixture)]
                created=subprocess.run(creation_command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,timeout=45,creationflags=HIDDEN)
                (folder/'fixture_create.stdout').write_bytes(created.stdout)
                (folder/'fixture_create.stderr').write_bytes(created.stderr)
                save(folder/'fixture_create_command.json',creation_command)
                assert created.returncode==0 and fixture.is_file(),created.stderr[-2000:]
            fixture_sha=sha(fixture)
            config={'schema_version':'1.0','enabled':True,'project_root':str(RUNTIME_ROOT),
                'state_file':str(folder/'state.json'),'audit_file':str(folder/'audit.jsonl'),
                'quad_size':64,'max_sessions':4,
                'expected_identity':{k:identity[k] for k in ('source_sha256','build_id','implementation_revision')}}
            save(folder/'connector.json',config)
            wire=Wire(folder)
            original_popen=subprocess.Popen
            def popen(command,*a,**kw):
                command=list(command)
                if Path(command[0]).resolve()==args.blender.resolve() and '--python-expr' in command:
                    index=command.index('--python-expr')
                    original_expression=command[index+1]
                    command[index:index]=['--python',str(HERE/'worker_observer.py')]
                    assert command[command.index('--python-expr')+1]==original_expression
                    env=dict(os.environ if kw.get('env') is None else kw['env'])
                    env['M5_QA_WORKER_OBSERVER']=str(folder/'worker_observer.jsonl');kw['env']=env
                    save(folder/'default_worker_command.json',{'command':command,'worker_path_override':False,
                        'observer_precedes_unchanged_default_expression':True})
                    process=original_popen(command,*a,**kw)
                    process.stdin=observe_text(process.stdin,wire,'owned_tx.bin')
                    process.stdout=observe_text(process.stdout,wire,'owned_rx.bin')
                    return process
                return original_popen(command,*a,**kw)
            subprocess.Popen=popen
            case={'label':label,'target_clearance_m':target,'passed':False,'fixture_sha256_before':fixture_sha}
            result['cases'].append(case)
            save(output/'RESULTS.json',result)
            lifecycle_started=time.perf_counter_ns()
            host=None
            try:
                with BlenderProcessHost(args.blender,fixture,timeout=30.) as host:
                    case['worker_pid']=host._process.pid
                    original_request=host._request
                    request_index=[0]
                    def request(command,params,**kw):
                        request_index[0]+=1;index=request_index[0];started=time.perf_counter_ns()
                        try:
                            value=original_request(command,params,**kw)
                            append(folder/'host_requests.jsonl',{'index':index,'rpc_id':host._sequence,'command':command,
                                'params':params,'result':value,'duration_ms':(time.perf_counter_ns()-started)/1e6})
                            return value
                        except BaseException as exc:
                            append(folder/'host_requests.jsonl',{'index':index,'rpc_id':host._sequence,'command':command,
                                'params':params,'error':repr(exc),'duration_ms':(time.perf_counter_ns()-started)/1e6})
                            raise
                    host._request=request
                    before_packet=host.capture_evidence()
                    save(folder/'before_packet.json',before_packet)
                    by_name={mesh['name']:mesh['object_id'] for mesh in before_packet['capture']['meshes']}
                    before_native=[row for row in rows(folder/'worker_observer.jsonl') if row['event']=='native_snapshot'][-1]
                    spec=ClearanceTaskSpec(by_name['BluePart'],by_name['GreyBase'],target,
                        limits=GoalBudgetLimits(max_steps=8,max_segments=3,max_duration_s=30.))
                    approvals=[]
                    def approve(resolved,scope):
                        assert resolved.focal_id==spec.focal_id and resolved.reference_id==spec.reference_id
                        assert resolved.target_clearance_m==target and scope['process_id']==host._process.pid
                        approvals.append({'spec':resolved.to_dict(),'scope':copy.deepcopy(scope)})
                        return TaskApproval('m5-qa-'+label,'explicit-isolated-qa-'+label)
                    scheduler=OwnedGoalScheduler(folder/'connector.json',host,
                        TrustedTaskAuthority('m5-owned-verification',approve))
                    original_save=scheduler.service._save
                    def observed_save(value,runtime,*a,**kw):
                        started=time.perf_counter_ns()
                        entry={'inflight':copy.deepcopy(value.get('inflight')),
                            'segments':copy.deepcopy(value.get('goal_segments'))}
                        try:
                            saved=original_save(value,runtime,*a,**kw)
                            entry['committed']=True
                            return saved
                        except BaseException as exc:
                            entry.update(committed=False,error=repr(exc));raise
                        finally:
                            entry['duration_ms']=(time.perf_counter_ns()-started)/1e6
                            append(folder/'save_events.jsonl',entry)
                    scheduler.service._save=observed_save
                    before_requests=request_index[0]
                    before_wire=wire.counts.copy()
                    COUNTS.clear();TIMES.clear();ACTIVE.clear()
                    sys.setprofile(profile)
                    started=time.perf_counter_ns()
                    try: receipt=scheduler.run(spec)
                    finally:
                        case['loop_ms']=(time.perf_counter_ns()-started)/1e6
                        sys.setprofile(None)
                    case['calls']=dict(COUNTS)
                    case['inclusive_profile_ms']={k:v/1e6 for k,v in TIMES.items()}
                    case['loop_transport_bytes']=diff(wire.counts,before_wire)
                    case['loop_host_requests']=request_index[0]-before_requests
                    case['loop_host_commands']=dict(Counter(row['command'] for row in rows(folder/'host_requests.jsonl')
                        if before_requests < row['index'] <= request_index[0]))
                    case['receipt']=receipt
                    save(folder/'approvals.json',approvals)
                    save(output/'RESULTS.json',result)
                    after_loop=[row for row in rows(folder/'worker_observer.jsonl') if row['event']=='native_snapshot'][-1]
                    if receipt.get('status')=='completed':
                        assert after_loop['method']=='end_motion_goal',after_loop['method']
                    case['loop_worker_counter_boundary']=after_loop['method']
                    case['loop_worker_calls']=diff(after_loop['host_calls'],before_native['host_calls'])
                    case['loop_resident_work']=diff(after_loop['resident_work'],before_native['resident_work'])
                    after_packet=host.capture_evidence()
                    save(folder/'after_packet.json',after_packet)
                    after_native=[row for row in rows(folder/'worker_observer.jsonl') if row['event']=='native_snapshot'][-1]
                    case['native_check']=native_check(before_native['native'],after_native['native'],target,label)
                    assert receipt['status']=='completed' and receipt['task_succeeded'] is True,receipt
                    expected=receipt['new_setter_count']
                    if label=='multi': assert expected>=2,receipt
                    else: assert expected==(0 if label=='zero' else 1),receipt
                    case['setter_count']=expected
                    case['save_events']=len(rows(folder/'save_events.jsonl'))
                    case['state_sha256']=sha(folder/'state.json')
                    case['passed']=True
                case['worker_returncode']=host._process.returncode
                case['worker_closed']=not host.is_alive
                assert case['worker_returncode']==0 and case['worker_closed']
            finally:
                sys.setprofile(None)
                subprocess.Popen=original_popen
                case['lifecycle_ms']=(time.perf_counter_ns()-lifecycle_started)/1e6
                case['whole_host_transport_bytes']=dict(wire.counts)
                case['fixture_sha256_after']=sha(fixture)
                assert case['fixture_sha256_after']==fixture_sha
                save(output/'RESULTS.json',result)
            print(label+' PASS '+str(round(case['loop_ms'],3))+'ms '+str(case['setter_count'])+' setters',flush=True)
        after=runtime_identity(mode='live')
        assert after==identity
        for row in after['source_files']: assert sha(RUNTIME_ROOT/row['path'])==row['sha256'],row['path']
        save(output/'identity_after.json',after)
        result['passed']=True
    except BaseException as exc:
        result.update(failure=repr(exc),traceback=traceback.format_exc())
        (output/'failure.txt').write_text(result['traceback'],encoding='utf8')
        print(result['traceback'],flush=True)
    finally:
        result['runner_sequence_ms']=(time.perf_counter_ns()-batch_started)/1e6
        save(output/'RESULTS.json',result)
    return 0 if result['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
