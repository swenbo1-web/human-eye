"""Bounded owner-only QA: prepare exact existing helpers, then one real run.

No model consumer. One NativeSession, five execute_code requests including the
profile fixture, one close. Original stdio bootstrap and NativeSession execute.
"""
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
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
ROOT = FOLDER.parents[1]
OUT = FOLDER / 'qa_01'
CANDIDATE = '24bfe492c4888caf1d989ddb22f36e5752829d46'
SOURCE_SHA = '74263d8b18aec48fac21e3c3b25e26c890739c6b697503a9f6b91acf7c30c0e3'
TOKEN = 'M1-NAME-NEAREST-001-20261108T093739Z-QA-ONLY'
COORD = Path('D:/hefe/verification/fixes/20261107_nearest_contract')
STATE = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
ASSIGNMENT = COORD / 'M1_NAME_NEAREST_ASSIGNMENT.md'
ASSIGNMENT_SHA = 'd4049e0166f841d287550a44f28c78fa1554148f0775058d111d08d9fdd36f6f'
OLD = ROOT / 'verification/surface_nearest_entry_001/qa_prepare'
HELPER = ROOT / 'verification/consumption_run_001/materials/admin/visual004_native.py'
HELPER_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
BOOTSTRAP_SHA = '45363af4e6763589dee638ba3a0bc1ee6a9cc00eca9da950736b2ae6fabe39a6'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
ASSET = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_qa_001/run_01/assets/all_overlap.blend')
ASSET_SHA = '574bcf2b5b636625ef3aa96e1c42af2a1d3fb83e75c6a04a30e83ff42882292a'
PYTHON = ROOT / 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False)+'\n').encode())


def error_info(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def window():
    value = json.loads(STATE.read_bytes())['performance_window']
    assert value['token'] == TOKEN and value['owner'] == 'W-ENTRY'
    assert value['max_sessions'] == 1 and value['max_RPC'] == 6
    assert str(value['status']).startswith('granted')
    end = datetime.fromisoformat(value.get('expires_utc', value.get('deadline_utc')).replace('Z', '+00:00'))
    assert datetime.now(timezone.utc) < end-timedelta(seconds=660), 'leave_original_600s_plus_cleanup'
    return value


def check_sources(plan):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == CANDIDATE
    for row in plan['product_manifest']:
        assert sha(ROOT/row['path']) == sha(Path(plan['source_root'])/row['path']) == row['sha256'], row['path']
    assert sha(HELPER) == HELPER_SHA and sha(ASSET) == ASSET_SHA and sha(BLENDER) == BLENDER_SHA
    assert sha(ASSIGNMENT) == ASSIGNMENT_SHA
    assert Path(sys.executable).resolve() == PYTHON.resolve(), 'existing_interpreter_required'


def existing_helpers():
    """Load old controller definitions only; its guarded main is not run."""
    path = OLD/'controller.py'
    spec = importlib.util.spec_from_file_location('_m1_existing_entry_QA_controller',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    module.FOLDER = OUT
    return module


def prepare():
    begun = time.perf_counter_ns()
    assert not OUT.exists(), 'fresh_bounded_QA_directory_required'
    assert sha(ASSIGNMENT) == ASSIGNMENT_SHA
    identity_path = FOLDER/'offline_02/EXECUTION_IDENTITY.json'
    offline_path = FOLDER/'offline_02/RESULTS.json'
    identity = json.loads(identity_path.read_bytes())
    offline = json.loads(offline_path.read_bytes())
    assert identity['guard_verify_loaded'] is True and offline['passed'] is True
    assert identity['runtime_source_sha256'] == offline['runtime_source_sha256'] == SOURCE_SHA
    assert offline['tests_run'] == 23
    manifest = identity['manifest']
    assert len(manifest) == len({row['path'] for row in manifest}) == 131
    plan = dict(candidate_commit=CANDIDATE, source_sha256=SOURCE_SHA, product_manifest=manifest,
        source_root=str(FOLDER/'offline_02/engine'), run_root=str(OUT), native_workspace=str(OUT/'owned'),
        blender=str(BLENDER), blender_sha256=BLENDER_SHA, asset=str(ASSET), asset_sha256=ASSET_SHA,
        helper=str(HELPER), helper_sha256=HELPER_SHA, max_sessions=1, max_total_RPC=6,
        max_execute_RPC=5, max_close_RPC=1, model_consumers=0, retries=0,
        request_budget_s=20., native_visual_timeout_s=10., original_worker_seconds=600,
        offline_proof=dict(path=str(offline_path),sha256=sha(offline_path)),
        identity_proof=dict(path=str(identity_path),sha256=sha(identity_path)), window=window())
    plan['host_sha256'] = next(row['sha256'] for row in manifest if row['path']=='human_eye_plugin/blender_host.py')
    check_sources(plan)
    for row in manifest:
        assert subprocess.check_output(['git', 'cat-file', 'blob', CANDIDATE+':'+row['path']], cwd=ROOT) == (ROOT/row['path']).read_bytes()
    assert sha(OLD/'stdio_bootstrap.py') == BOOTSTRAP_SHA
    OUT.mkdir()
    (OUT/'stdio_bootstrap.py').write_bytes((OLD/'stdio_bootstrap.py').read_bytes())
    profile = dict(host_source_path=str(Path(plan['source_root'])/'human_eye_plugin/blender_host.py'),
        host_source_sha256=plan['host_sha256'],profile_output_path=str(OUT/'owned/PROFILE.json'),expected_nearest_calls=4)
    code = 'QA_PLAN = '+repr(profile)+'\n'+(FOLDER/'qa_profile_setup.py').read_text(encoding='utf8')
    compile(code, '<fixed-profile-setup>', 'exec')
    assert len(code.encode()) <= 256*1024
    (OUT/'PROFILE_SETUP.py').write_text(code,encoding='utf8',newline='\n')
    plan.update(prepared_utc=datetime.now(timezone.utc).isoformat(), prepare_elapsed_ns=time.perf_counter_ns()-begun)
    save(OUT/'PLAN.json',plan)
    save(OUT/'FREEZE.json',dict(plan_sha256=sha(OUT/'PLAN.json'), no_session_started=True,
        controllers=[dict(path=str(path),sha256=sha(path)) for path in
            (Path(__file__),HELPER,OLD/'controller.py',OUT/'stdio_bootstrap.py',OUT/'PROFILE_SETUP.py',identity_path,offline_path)]))
    print(json.dumps(dict(status='prepared_no_session',source_sha256=SOURCE_SHA,plan_sha256=sha(OUT/'PLAN.json'))))


def semantic(value):
    fields=('result_kind','status','scope','focal','nearest_objects','best_known_objects',
            'distance_m','best_known_distance_m','unit','coverage','unresolved','execution_authority')
    return {key:value.get(key) for key in fields}


def run():
    plan=json.loads((OUT/'PLAN.json').read_bytes()); freeze=json.loads((OUT/'FREEZE.json').read_bytes())
    assert sha(OUT/'PLAN.json')==freeze['plan_sha256']
    for row in freeze['controllers']: assert sha(row['path'])==row['sha256']
    assert sha(plan['offline_proof']['path'])==plan['offline_proof']['sha256']
    check_sources(plan); active_window=window()
    assert active_window['token']==plan['window']['token']
    helpers=existing_helpers()
    native=types.ModuleType('_m1_owned_native');native.__file__=str(HELPER);sys.modules[native.__name__]=native
    exec(compile(HELPER.read_bytes(),str(HELPER),'exec',dont_inherit=True),native.__dict__)
    begun=time.perf_counter_ns(); plan['deadline_ns']=begun+600_000_000_000
    record=dict(started_utc=datetime.now(timezone.utc).isoformat(), original_deadline_ns=plan['deadline_ns'],
        candidate_commit=CANDIDATE,source_sha256=SOURCE_SHA,primary_error=None,owned_sessions_attempted=0,
        control_RPC_attempts=0,product_attempts=0,public_calls=[],retries=0,model_consumers=0,
        actual_external_API=0,original_asset_write=False)
    with (OUT/'STARTED.json').open('xb') as stream:
        stream.write((json.dumps(dict(started_utc=record['started_utc'],started_ns=begun,
            argv=sys.argv,python=sys.executable,freeze_sha256=sha(OUT/'FREEZE.json'),window=active_window),indent=2)+'\n').encode())
    owner=None;stdio=None
    def sockets_count(): return len(list((OUT/'stdio').glob('socket_*')))
    def transaction(label,call):
        assert record['control_RPC_attempts']+sockets_count()<6, 'physical_RPC_cap'
        folder=OUT/label;folder.mkdir();meter=dict(send_attempted_bytes=0,send_completed_bytes=0,received_bytes=0)
        original=native.socket.create_connection
        def connect(*args,**kwargs): return helpers.MeterSocket(original(*args,**kwargs),folder,meter)
        native.socket.create_connection=connect;record['control_RPC_attempts']+=1;start=time.perf_counter_ns()
        try:
            response=call();save(folder/'RESPONSE.json',response);return response
        finally:
            native.socket.create_connection=original
            save(folder/'METER.json',dict(**meter,elapsed_ns=time.perf_counter_ns()-start))
    def observe(label,arguments):
        before=sockets_count();assert record['control_RPC_attempts']+before<5,'reserve_close_RPC'
        row=dict(label=label,started_ns=time.perf_counter_ns(),arguments=arguments);record['public_calls'].append(row)
        record['product_attempts']+=1
        try:
            response=stdio.call('tools/call',dict(name='human_eye_scene_observe',arguments=arguments))
            row['response']=response;assert sockets_count()-before==1,'one_physical_capture_per_public_request'
            return response
        finally: row['elapsed_ns']=time.perf_counter_ns()-row['started_ns'];row['physical_RPC_delta']=sockets_count()-before
    try:
        record['owned_sessions_attempted']=1;start=time.perf_counter_ns()
        owner=native.NativeSession.start(blender=plan['blender'],asset=plan['asset'],workspace=OUT/'owned',
            deadline_ns=plan['deadline_ns'],condition='N',expected_asset_sha256=ASSET_SHA,max_calls=5)
        record['native_startup_ns']=time.perf_counter_ns()-start;record['ready']=owner.ready
        save(OUT/'NATIVE_COMMAND.json',dict(pid=owner.process.pid,argv=[plan['blender'],'--factory-startup','--disable-autoexec',
            '--background',str(OUT/'owned/input.blend'),'--python-exit-code','1','--python',str(HELPER),'--','--worker',str(OUT/'owned/CONFIG.json')]))
        setup=transaction('rpc_profile_setup',lambda:owner.run((OUT/'PROFILE_SETUP.py').read_text(encoding='utf8'),timeout_s=30))
        record['fixture_setup']=setup;assert setup['response']['status']=='success','profile_setup_failed_no_replay'
        assert (OUT/'owned/PROFILE.json').exists()
        plan['endpoint']=dict(host=owner.host,port=owner.port);plan['config_path']=str(OUT/'live-connector.json')
        save(plan['config_path'],dict(schema_version='1.0',enabled=True,observe_on_prompt=False,project_root=plan['source_root'],
            state_file=str(OUT/'state.json'),audit_file=str(OUT/'audit.jsonl'),expected_identity=dict(source_sha256=SOURCE_SHA),
            blender=dict(host=owner.host,port=owner.port,timeout_s=10),request_budget_s=20.,native_visual_timeout_s=10.))
        save(OUT/'RUNTIME_PLAN.json',plan)
        save(OUT/'ENDPOINT_FREEZE.json',dict(runtime_plan_sha256=sha(OUT/'RUNTIME_PLAN.json'),config_sha256=sha(plan['config_path']),ready=owner.ready))
        stdio=helpers.Stdio(plan);save(OUT/'STDIO_PROCESS.json',dict(pid=stdio.process.pid,owner='controller Popen',command=json.loads((OUT/'STDIO_COMMAND.json').read_bytes())))
        assert 'result' in stdio.call('initialize',dict(protocolVersion='2024-11-05',capabilities={},clientInfo=dict(name='m1-name-nearest-QA',version='1')))
        stdio.call('notifications/initialized',{},notification=True)
        tools=stdio.call('tools/list',{});assert any(t['name']=='human_eye_scene_observe' for t in tools['result']['tools'])
        assert sockets_count()==0,'initialize_and_list_must_not_capture'
        args=dict(session_id='m1-direct-read',include_image=False,query=dict(mode='surface_nearest',objects=[dict(name='M4_Focal')]))
        first=helpers.public_result(observe('direct_name',args))
        assert first['result_kind']=='surface_nearest' and first['status']=='complete' and first['execution_authority'] is False
        assert first['binding']['runtime_source_sha256']==SOURCE_SHA
        focal=first['focal']['id'];assert type(focal)is str and focal
        legacy=helpers.public_result(observe('legacy_id',dict(session_id='m1-legacy-read',focal_id=focal,include_image=False,query=dict(mode='surface_nearest'))))
        assert semantic(first)==semantic(legacy),'direct_name_legacy_ID_mismatch'
        missing=observe('missing_name',dict(session_id='m1-missing-read',include_image=False,
            query=dict(mode='surface_nearest',objects=[dict(name='__M1_QA_MISSING_00000000000000000000000000000000__')])))
        assert ('error' in missing or missing.get('result',{}).get('isError') is True),'missing_name_not_refused'
        assert 'acquisition_selector_not_found' in json.dumps(missing),'missing_name_wrong_failure'
        recovered=helpers.public_result(observe('name_after_refusal',args))
        assert semantic(first)==semantic(recovered),'post_refusal_read_not_equivalent'
        profile=json.loads((OUT/'owned/PROFILE.json').read_bytes());record['profile']=profile
        assert profile['disarmed'] is True and not profile.get('hook_error') and len(profile['calls'])==4
        assert [r['counts']['_objects'] for r in profile['calls']]==[2,2,1,2]
        assert [r['counts']['_capture'] for r in profile['calls']]==[1,1,0,1]
        assert all(r['counts']['capture_task_scene']==r['counts']['capture_scene']==0 for r in profile['calls'])
        assert profile['all_host_counts']['capture_task_scene']==profile['all_host_counts']['capture_scene']==0
        record['entry_assertions_passed']=True
    except BaseException as error: record['primary_error']=error_info(error)
    finally:
        if stdio is not None:
            try: record['stdio_cleanup']=stdio.close()
            except BaseException as error: record['stdio_cleanup_error']=error_info(error)
        if owner is not None:
            try: record['native_cleanup']=transaction('rpc_close',owner.close)
            except BaseException as error: record['native_cleanup_error']=error_info(error);owner._kill()
            record['owned_process_reaped']=owner.process.poll() is not None;record['owned_exit_code']=owner.process.poll()
            closed=OUT/'owned/WORKER_CLOSED.json'
            if closed.exists():record['worker_closed']=json.loads(closed.read_bytes());record['worker_closed_sha256']=sha(closed)
        bootstrap_path=OUT/'stdio/BOOTSTRAP_RESULT.json'
        if bootstrap_path.exists():record['bootstrap']=json.loads(bootstrap_path.read_bytes())
        record['product_socket_count']=sockets_count();record['total_RPC_attempts']=record['control_RPC_attempts']+sockets_count()
        record['asset_sha256_after']=sha(ASSET);record['helper_sha256_after']=sha(HELPER)
        record['source_drift']=[r['path'] for r in plan['product_manifest'] if sha(ROOT/r['path'])!=r['sha256'] or sha(Path(plan['source_root'])/r['path'])!=r['sha256']]
        record['whole_controller_ns']=time.perf_counter_ns()-begun;record['ended_utc']=datetime.now(timezone.utc).isoformat()
        bootstrap=record.get('bootstrap',{});witness=bootstrap.get('execution_witness',{});cleanup=record.get('native_cleanup',{})
        control=[json.loads(p.read_bytes()) for p in OUT.glob('rpc_*/METER.json')];sockets=bootstrap.get('sockets',[])
        record['boundary_totals']=dict(control_TX_attempted_bytes=sum(r['send_attempted_bytes'] for r in control),control_TX_completed_bytes=sum(r['send_completed_bytes'] for r in control),
            control_RX_bytes=sum(r['received_bytes'] for r in control),product_TX_attempted_bytes=sum(r['send_attempted_bytes'] for r in sockets),
            product_TX_completed_bytes=sum(r['send_completed_bytes'] for r in sockets),product_RX_bytes=sum(r['received_bytes'] for r in sockets),
            complete_stdio_TX_bytes=record.get('stdio_cleanup',{}).get('complete_TX_bytes'),complete_stdio_RX_bytes=record.get('stdio_cleanup',{}).get('complete_RX_bytes'))
        record['timing_note']='prepare, fixture setup, product requests, close, profile and whole controller are nested; do not add or subtract QA overhead as free work'
        record['passed']=bool(record['primary_error'] is None and record.get('entry_assertions_passed') and record['owned_sessions_attempted']==1
            and record['product_attempts']==4 and record['product_socket_count']==4 and record['total_RPC_attempts']==6
            and witness.get('guard_verified') and witness.get('bound_generation',{}).get('compatible')
            and witness.get('every_loaded_module_has_execution_or_namespace_witness')
            and record.get('stdio_cleanup',{}).get('exit_code')==0 and record.get('stdio_cleanup',{}).get('extra_rx_bytes')==0
            and record.get('owned_process_reaped') and record.get('owned_exit_code')==0
            and cleanup.get('response',{}).get('status')=='closed' and cleanup.get('error') is None
            and cleanup.get('original_deadline_ns')==plan['deadline_ns']
            and cleanup.get('response',{}).get('deadline_ns')==plan['deadline_ns']
            and cleanup.get('source_file_unchanged') and cleanup.get('protected_files_unchanged')
            and record.get('worker_closed',{}).get('poisoned') is False
            and record.get('worker_closed',{}).get('original_deadline_ns')==plan['deadline_ns']
            and record.get('worker_closed',{}).get('initial_geometry_fingerprint')==record.get('worker_closed',{}).get('final_geometry_fingerprint')==record.get('ready',{}).get('initial_fingerprint')
            and record['asset_sha256_after']==ASSET_SHA and record['helper_sha256_after']==HELPER_SHA and not record['source_drift'])
        record['status']='bounded_real_entry_complete' if record['passed'] else 'incomplete_no_replay'
        save(OUT/'RESULTS.json',record)
        print(json.dumps(dict(status=record['status'],passed=record['passed'],total_RPC_attempts=record['total_RPC_attempts'],result=str(OUT/'RESULTS.json'))))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','run'));args=parser.parse_args()
    try:{'prepare':prepare,'run':run}[args.command]()
    except BaseException as error:
        if OUT.exists() and not (OUT/'STARTED.json').exists():save(OUT/'PREFLIGHT_FAILURE.json',error_info(error))
        raise
