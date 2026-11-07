"""Freeze one committed candidate, then run the preregistered real entry batch.

Preparation does not import product modules or start any process/session.
"""
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import traceback
import types

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
OUT = FOLDER/'run_01'
HELPER = Path('D:/hefe/verification/fixes/20261106_perf010_r2/installed/verification/visual004_native.py')
HELPER_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
ASSET_SHA = '9a7671bb202720b09311f313363bc0e5267017f2af155a9167fff4cf2d96d1b6'
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
ASSIGNMENT = Path('D:/hefe/verification/fixes/20261107_nearest_contract/SURFACE_NEAREST_ENTRY_ASSIGNMENT.md')
ASSIGNMENT_SHA = '4c7655d5a34866344f934bb16488690de8af08b73160259a7bac838e4456c06e'
DEADLINE = datetime(2026,11,7,17,0,tzinfo=timezone.utc)
FILES = ('controller.py','launch.py','stdio_bootstrap.py','fixture_setup.py','fixture_restore.py','PREREGISTRATION.json')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value): Path(path).write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
def error_info(error): return dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
def check_sources(plan):
    for row in plan['product_manifest']:
        assert sha(ROOT/row['path']) == sha(Path(plan['source_root'])/row['path']) == row['sha256'], row['path']

def prepare(args):
    assert not OUT.exists(), 'single_frozen_run_no_retry'
    assert sha(ASSIGNMENT) == ASSIGNMENT_SHA
    identity = json.loads(args.identity.read_bytes()); identity = identity.get('identity',identity)
    manifest = sorted([dict(path=r['path'],sha256=r['sha256']) for r in identity.get('source_files',identity.get('files',identity.get('manifest',[])))],key=lambda r:r['path'])
    product_sha = identity.get('runtime_source_sha256',identity.get('candidate_source_sha256',identity.get('source_sha256')))
    assert len(manifest) == len({r['path'] for r in manifest}) == 131
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    blobs = {}
    for row in manifest:
        target = (ROOT/row['path']).resolve(); assert target.is_relative_to(ROOT) and target.suffix == '.py'
        blob = target.read_bytes(); assert hashlib.sha256(blob).hexdigest() == row['sha256']
        assert subprocess.check_output(['git','show',commit+':'+row['path']],cwd=ROOT) == blob, 'uncommitted_product_candidate'
        blobs[row['path']] = blob
    constants = {}
    for node in ast.parse(blobs['human_eye_plugin/runtime_identity.py']).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION'):
                    constants[target.id] = ast.literal_eval(node.value)
    digest = dict(base_version=constants['BASE_VERSION'],implementation_revision=constants['IMPLEMENTATION_REVISION'],files=manifest)
    assert hashlib.sha256(json.dumps(digest,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest() == product_sha
    offline = json.loads(args.offline_proof.read_bytes())
    assert offline.get('passed') is True or offline.get('successful') is True, 'offline_pass_required'
    assert identity.get('guard_verify_loaded') is True, 'offline_original_loader_execution_witness_required'
    proof_sha = offline.get('runtime_source_sha256',offline.get('candidate_source_sha256',offline.get('source_sha256')))
    assert proof_sha == product_sha, 'offline_candidate_identity_mismatch'
    registry = ROOT/'verification/m4_capture_qa_001/run_01/assets/ASSETS.json'
    asset = next(r for r in json.loads(registry.read_bytes())['cases'] if r['case'] == 'far_second_degenerate')
    registration = json.loads((FOLDER/'PREREGISTRATION.json').read_bytes())
    assert registration['asset_recipe'] == asset['recipe']
    assert sha(asset['asset']) == asset['sha256'] == ASSET_SHA
    assert sha(HELPER) == HELPER_SHA and sha(args.blender) == BLENDER_SHA
    state_path = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
    window = json.loads(state_path.read_bytes())['performance_window']
    assert window['token'] == 'SURFACE-NEAREST-ENTRY-001-ONLY' and window['max_sessions'] == 1 and window['max_RPC'] == 12
    OUT.mkdir(); source_root = OUT/'sources'
    for name,blob in blobs.items():
        target = source_root/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(blob)
    plan = dict(root=str(ROOT),run_root=str(OUT),native_workspace=str(OUT/'owned'),source_root=str(source_root),
        candidate_commit=commit,source_sha256=product_sha,product_manifest=manifest,host_sha256=sha(source_root/'human_eye_plugin/blender_host.py'),
        blender=str(args.blender.resolve()),blender_sha256=BLENDER_SHA,asset=asset['asset'],asset_sha256=ASSET_SHA,
        asset_recipe=asset['recipe'],static_object_ids=registration['object_ids'],helper=str(HELPER),helper_sha256=HELPER_SHA,
        assignment_sha256=ASSIGNMENT_SHA,window=window,state_file_sha256=sha(state_path),
        offline_proof=dict(path=str(args.offline_proof.resolve()),sha256=sha(args.offline_proof)),
        identity_proof=dict(path=str(args.identity.resolve()),sha256=sha(args.identity)),
        max_sessions=1,max_execute_code_RPC=9,max_close_RPC=1,max_total_RPC=10,max_product_captures=3,
        original_worker_seconds=600,cleanup_reserve_seconds=60,original_asset_write=False,retries=0,
        request_budget_s=20.,native_visual_timeout_s=10.,prepared_utc=datetime.now(timezone.utc).isoformat())
    save(OUT/'PLAN.json',plan)
    save(OUT/'FREEZE.json',dict(plan_sha256=sha(OUT/'PLAN.json'),controllers=[dict(path=str(FOLDER/name),sha256=sha(FOLDER/name)) for name in FILES],no_session_started=True))
    print(json.dumps(dict(status='prepared_no_session_started',candidate_commit=commit,source_sha256=product_sha,freeze_sha256=sha(OUT/'FREEZE.json'))))

class MeterSocket:
    def __init__(self,sock,folder,meter): self.sock,self.folder,self.meter = sock,folder,meter
    def __getattr__(self,key): return getattr(self.sock,key)
    def __enter__(self): return self
    def __exit__(self,*args): return self.sock.__exit__(*args)
    def sendall(self,raw):
        with (self.folder/'TX.bin').open('ab') as stream: stream.write(raw)
        self.meter['send_attempted_bytes'] += len(raw)
        result = self.sock.sendall(raw); self.meter['send_completed_bytes'] += len(raw); return result
    def recv(self,size):
        raw = self.sock.recv(size)
        with (self.folder/'RX.bin').open('ab') as stream: stream.write(raw)
        self.meter['received_bytes'] += len(raw); return raw

class Stdio:
    def __init__(self,plan):
        self.folder = OUT/'mcp_frames'; self.folder.mkdir(); self.events=[]; self.next_id=0; self.queue=queue.Queue()
        self.stderr = (OUT/'stdio_stderr.bin').open('wb')
        self.started_ns = time.perf_counter_ns()
        command = [sys.executable,str(FOLDER/'stdio_bootstrap.py'),str(OUT/'RUNTIME_PLAN.json')]
        save(OUT/'STDIO_COMMAND.json',dict(argv=command,cwd=str(OUT),started_ns=self.started_ns))
        self.process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,cwd=OUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def read():
            while True:
                raw = self.process.stdout.readline()
                self.queue.put(raw)
                if not raw: break
        self.thread = threading.Thread(target=read,daemon=True); self.thread.start()
    def call(self,method,params=None,notification=False):
        self.next_id += 1; row = dict(sequence=self.next_id,method=method,notification=notification,started_ns=time.perf_counter_ns())
        request = dict(jsonrpc='2.0',method=method)
        if params is not None: request['params'] = params
        if not notification: request['id'] = self.next_id
        raw = (json.dumps(request,separators=(',',':'),allow_nan=False)+'\n').encode()
        folder = self.folder/str(self.next_id).zfill(2); folder.mkdir(); (folder/'TX.bin').write_bytes(raw)
        row['tx_bytes'] = len(raw); row['request'] = request; self.events.append(row)
        try:
            self.process.stdin.write(raw); self.process.stdin.flush()
            if notification: return None
            response_raw = self.queue.get(timeout=45)
            (folder/'RX.bin').write_bytes(response_raw); row['rx_bytes'] = len(response_raw)
            assert response_raw, 'stdio_EOF_no_replay'
            response = json.loads(response_raw); assert response.get('id') == self.next_id
            save(folder/'RESPONSE.json',response); return response
        finally:
            row['elapsed_ns'] = time.perf_counter_ns()-row['started_ns']; save(folder/'METER.json',row)
    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=15)
        except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=10)
        self.stderr.close(); self.thread.join(timeout=2)
        extras=[]
        while not self.queue.empty(): extras.append(self.queue.get_nowait())
        (OUT/'STDIO_EXTRA_RX.bin').write_bytes(b''.join(extras))
        return dict(pid=self.process.pid,exit_code=self.process.returncode,process_reaped=True,elapsed_ns=time.perf_counter_ns()-self.started_ns,
            calls=self.events,extra_rx_bytes=sum(map(len,extras)),complete_TX_bytes=sum(r.get('tx_bytes',0) for r in self.events),complete_RX_bytes=sum(r.get('rx_bytes',0) for r in self.events)+sum(map(len,extras)))

def public_result(response):
    assert 'error' not in response
    result = response['result']; assert not result.get('isError',False)
    content = result.get('content',[]); assert content and all(r['type']=='text' for r in content), 'no_images'
    values = [json.loads(r['text']) for r in content]
    assert len(values) == 1, 'one_compact_text_payload'
    assert 'structuredContent' not in result, 'no_duplicate_full_payload'
    return values[0]

def check_answer(state,result,plan):
    ids=plan['static_object_ids']; near=ids['M4_Near']; far=ids['M4_Far_00']; focal=ids['M4_Focal']
    assert result['result_kind']=='surface_nearest'
    assert result['focal']==dict(id=focal,name='M4_Focal')
    assert result.get('unit')=='m'
    assert result.get('execution_authority') is False
    assert '_exact_distance_sq' not in json.dumps(result) and 'vertices' not in json.dumps(result)
    coverage=result['coverage']; assert coverage['targets_excluding_focal']==2
    assert (coverage['distance_valid'],coverage['strictly_excluded'],coverage['unresolved'])==((1,1,0) if state==1 else (2,0,0) if state==2 else (1,0,1))
    if state in (1,2):
        expected=dict(id=near if state==1 else far,name='M4_Near' if state==1 else 'M4_Far_00')
        assert result['status']=='complete' and result['nearest_objects']==[expected]
        assert result['distance_m']==(2. if state==1 else .25) and not result['unresolved']
        if state==1: assert far not in json.dumps(result), 'excluded_ID_not_dumped'
    else:
        assert result['status']=='partial' and result['nearest_objects'] is None and result['distance_m'] is None
        assert result['best_known_objects']==[dict(id=near,name='M4_Near')] and result['best_known_distance_m']==2.
        assert result['unresolved']==[dict(id=far,name='M4_Far_00',reason='surface_degenerate_triangle')]
    assert result['binding']['runtime_source_sha256']==plan['source_sha256']

def run(args):
    plan=json.loads((OUT/'PLAN.json').read_bytes()); freeze=json.loads((OUT/'FREEZE.json').read_bytes())
    assert sha(OUT/'PLAN.json')==freeze['plan_sha256']
    for row in freeze['controllers']: assert sha(row['path'])==row['sha256']
    assert not (OUT/'STARTED.json').exists(), 'no_second_session_or_retry'
    assert datetime.now(timezone.utc)<DEADLINE-timedelta(seconds=660), 'leave_original_600s_plus_60s_cleanup'
    check_sources(plan); assert sha(HELPER)==HELPER_SHA and sha(plan['asset'])==ASSET_SHA
    assert sha(plan['offline_proof']['path'])==plan['offline_proof']['sha256']
    begun=time.perf_counter_ns(); plan['start_ns']=begun; plan['deadline_ns']=begun+600_000_000_000
    scripts=[]
    for state in (1,2,3):
        for kind in ('setup','restore'):
            code='STATE = '+str(state)+'\nPLAN = '+repr(plan)+'\n'+(FOLDER/('fixture_'+kind+'.py')).read_text('utf8')
            compile(code,'<surface-entry-frozen-'+kind+'-'+str(state)+'>','exec')
            assert len(code.encode())<=256*1024
            path=OUT/(kind.upper()+'_'+str(state)+'.py'); path.write_bytes(code.encode())
            scripts.append(dict(state=state,kind=kind,path=str(path),sha256=sha(path)))
    save(OUT/'RUNTIME_FREEZE.json',dict(scripts=scripts,original_deadline_ns=plan['deadline_ns']))
    native=types.ModuleType('_surface_entry_native'); native.__file__=str(HELPER); sys.modules[native.__name__]=native
    exec(compile(HELPER.read_bytes(),str(HELPER),'exec',dont_inherit=True),native.__dict__)
    owner=None; stdio=None
    record=dict(states=[],primary_error=None,owned_sessions_attempted=0,control_RPC_attempts=0,product_capture_attempts=0,
        retries=0,zero_model_consumers=True,zero_external_API=True,zero_images=True,started_utc=datetime.now(timezone.utc).isoformat())
    def transaction(name,call):
        folder=OUT/name; folder.mkdir(); meter=dict(send_attempted_bytes=0,send_completed_bytes=0,received_bytes=0)
        original=native.socket.create_connection
        def connect(*a,**k): return MeterSocket(original(*a,**k),folder,meter)
        native.socket.create_connection=connect; record['control_RPC_attempts']+=1; start=time.perf_counter_ns()
        try:
            response=call(); save(folder/'RESPONSE.json',response); return response
        finally:
            native.socket.create_connection=original
            save(folder/'METER.json',dict(**meter,elapsed_ns=time.perf_counter_ns()-start))
    def control(state,kind):
        row=next(r for r in scripts if r['state']==state and r['kind']==kind); assert sha(row['path'])==row['sha256']
        receipt=transaction('rpc_'+kind+'_'+str(state),lambda:owner.run(Path(row['path']).read_text('utf8'),timeout_s=35))
        assert receipt['response'].get('status')=='success', 'control_RPC_failed_no_replay'
        return receipt
    save(OUT/'STARTED.json',dict(at_ns=begun,runtime_freeze_sha256=sha(OUT/'RUNTIME_FREEZE.json')))
    try:
        record['owned_sessions_attempted']=1
        owner=native.NativeSession.start(blender=plan['blender'],asset=plan['asset'],workspace=OUT/'owned',deadline_ns=plan['deadline_ns'],condition='N',expected_asset_sha256=ASSET_SHA,max_calls=9)
        record['ready']=owner.ready
        assert owner.ready['pid']==owner.process.pid and owner.ready['helper_sha256']==HELPER_SHA
        plan['endpoint']=dict(host=owner.host,port=owner.port)
        plan['config_path']=str(OUT/'live-connector.json')
        save(plan['config_path'],dict(schema_version='1.0',enabled=True,observe_on_prompt=False,project_root=plan['source_root'],
            state_file=str(OUT/'state.json'),audit_file=str(OUT/'audit.jsonl'),expected_identity=dict(source_sha256=plan['source_sha256']),
            blender=dict(host=owner.host,port=owner.port,timeout_s=30),request_budget_s=plan['request_budget_s'],native_visual_timeout_s=plan['native_visual_timeout_s']))
        save(OUT/'RUNTIME_PLAN.json',plan)
        save(OUT/'ENDPOINT_FREEZE.json',dict(runtime_plan_sha256=sha(OUT/'RUNTIME_PLAN.json'),config_sha256=sha(plan['config_path']),owned_ready=owner.ready))
        stdio=Stdio(plan)
        initialize=stdio.call('initialize',dict(protocolVersion='2024-11-05',capabilities={},clientInfo=dict(name='surface-nearest-entry-qa',version='1')))
        assert 'result' in initialize
        stdio.call('notifications/initialized',{},notification=True)
        listed=stdio.call('tools/list',{})
        assert any(t['name']=='human_eye_scene_observe' for t in listed['result']['tools'])
        args0=dict(session_id='surface-nearest-entry-001',focal_id=plan['static_object_ids']['M4_Focal'],include_image=False,query=dict(mode='surface_nearest'))
        bad=dict(args0); bad['include_image']=True
        rejected=stdio.call('tools/call',dict(name='human_eye_scene_observe',arguments=bad))
        assert 'error' in rejected or rejected.get('result',{}).get('isError') is True, 'bad_parameter_must_reject'
        assert 'result' in stdio.call('ping',{})
        for state in (1,2,3):
            item=dict(state=state,entered_ns=time.perf_counter_ns()); record['states'].append(item)
            # Even a setup whose outcome is uncertain is followed by disarm/restore.
            try:
                control(state,'setup'); item['setup_success']=True
                record['product_capture_attempts']+=1
                response=stdio.call('tools/call',dict(name='human_eye_scene_observe',arguments=args0))
                item['public']=public_result(response)
            finally:
                item['restore_receipt']=control(state,'restore')
            fixture_path=OUT/'owned'/('fixture_'+str(state))/'FIXTURE.json'
            fixture=json.loads(fixture_path.read_bytes()); item['fixture_path']=str(fixture_path); item['fixture_sha256']=sha(fixture_path)
            assert fixture['calls']==fixture['returns']==1 and fixture['restored'] and fixture['finally_disarmed']
            assert not fixture.get('hook_error') and fixture['before']==fixture['after']==fixture['after_finally']
            check_answer(state,item['public'],plan); item['independent_answer_passed']=True
    except BaseException as error: record['primary_error']=error_info(error)
    finally:
        if stdio is not None:
            try: record['stdio_cleanup']=stdio.close()
            except BaseException as error: record['stdio_cleanup_error']=error_info(error)
        if owner is not None:
            try: record['native_cleanup']=transaction('rpc_close',owner.close)
            except BaseException as error: record['native_cleanup_error']=error_info(error); owner._kill()
            record['owned_process_reaped']=owner.process.poll() is not None; record['owned_exit_code']=owner.process.poll()
            closed_path=OUT/'owned'/'WORKER_CLOSED.json'
            if closed_path.exists():
                record['worker_closed']=json.loads(closed_path.read_bytes())
                record['worker_closed_sha256']=sha(closed_path)
        record['whole_controller_ns']=time.perf_counter_ns()-begun; record['ended_utc']=datetime.now(timezone.utc).isoformat()
        record['asset_sha256_after']=sha(plan['asset']); record['helper_sha256_after']=sha(HELPER)
        record['product_source_drift']=[r['path'] for r in plan['product_manifest'] if sha(ROOT/r['path'])!=r['sha256']]
        bootstrap_path=OUT/'stdio'/'BOOTSTRAP_RESULT.json'
        if bootstrap_path.exists(): record['bootstrap']=json.loads(bootstrap_path.read_bytes())
        bootstrap=record.get('bootstrap',{}); witness=bootstrap.get('execution_witness',{}); cleanup=record.get('native_cleanup',{})
        control_meters=[json.loads(path.read_bytes()) for path in OUT.glob('rpc_*/METER.json')]
        sockets=bootstrap.get('sockets',[])
        record['boundary_totals']=dict(native_control_TX_attempted_bytes=sum(r['send_attempted_bytes'] for r in control_meters),
            native_control_TX_completed_bytes=sum(r['send_completed_bytes'] for r in control_meters),
            native_control_RX_bytes=sum(r['received_bytes'] for r in control_meters),
            production_socket_TX_attempted_bytes=sum(r['send_attempted_bytes'] for r in sockets),
            production_socket_TX_completed_bytes=sum(r['send_completed_bytes'] for r in sockets),
            production_socket_RX_bytes=sum(r['received_bytes'] for r in sockets),
            complete_stdio_TX_bytes=record.get('stdio_cleanup',{}).get('complete_TX_bytes'),
            complete_stdio_RX_bytes=record.get('stdio_cleanup',{}).get('complete_RX_bytes'))
        record['qa_overhead']=dict(attribution_scope='partial matched callback body only; ignored filters and fixture persistence excluded; all overhead remains in RPC/stdio/outer command walls',
            stdio_profile_ns=bootstrap.get('profile_overhead_ns'),
            fixture_scans=sum(json.loads(Path(r['fixture_path']).read_bytes()).get('qa_oracle_scans',0) for r in record['states'] if 'fixture_path' in r),
            fixture_vertices_read=sum(json.loads(Path(r['fixture_path']).read_bytes()).get('qa_vertices_read',0) for r in record['states'] if 'fixture_path' in r),
            fixture_profile_ns=sum(json.loads(Path(r['fixture_path']).read_bytes()).get('profile_overhead_ns',0) for r in record['states'] if 'fixture_path' in r))
        record['total_RPC_attempts']=record['control_RPC_attempts']+len(bootstrap.get('sockets',[]))
        record['product_socket_count']=len(bootstrap.get('sockets',[]))
        record['passed']=bool(record['primary_error'] is None and len(record['states'])==3 and all(r.get('independent_answer_passed') for r in record['states'])
            and record['total_RPC_attempts']==10 and record['product_socket_count']==3 and record['product_capture_attempts']==3
            and witness.get('guard_verified') and witness.get('every_loaded_module_has_execution_or_namespace_witness') and witness.get('bound_generation',{}).get('compatible')
            and record.get('stdio_cleanup',{}).get('exit_code')==0 and record.get('stdio_cleanup',{}).get('extra_rx_bytes')==0
            and record.get('owned_process_reaped') and record.get('owned_exit_code')==0 and cleanup.get('error') is None
            and cleanup.get('response',{}).get('status')=='closed' and cleanup.get('source_file_unchanged') and cleanup.get('protected_files_unchanged')
            and record.get('worker_closed',{}).get('poisoned') is False
            and record.get('worker_closed',{}).get('final_geometry_fingerprint')==record.get('worker_closed',{}).get('initial_geometry_fingerprint')==record.get('ready',{}).get('initial_fingerprint')
            and record['asset_sha256_after']==ASSET_SHA and record['helper_sha256_after']==HELPER_SHA and not record['product_source_drift'])
        record['source_sha256']=plan['source_sha256']; record['status']='three_state_real_entry_completed' if record['passed'] else 'incomplete_no_replay'
        save(OUT/'RESULTS.json',record)
        print(json.dumps(dict(status=record['status'],passed=record['passed'],total_RPC_attempts=record['total_RPC_attempts'],result_path=str(OUT/'RESULTS.json')),indent=2))
    if not record['passed']: raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--identity',type=Path,required=True); prep.add_argument('--offline-proof',type=Path,required=True)
    prep.add_argument('--blender',type=Path,default=Path('D:/Tools/blender5.2/blender.exe'))
    sub.add_parser('run'); args=parser.parse_args(); {'prepare':prepare,'run':run}[args.command](args)
