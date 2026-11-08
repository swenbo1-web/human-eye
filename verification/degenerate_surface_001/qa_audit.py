"""Read existing QA bytes and recorded PIDs only; no product imports or replay."""
import ast
from collections import Counter
import ctypes
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import time

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
QA = FOLDER / 'qa_01'
OUTER = FOLDER / 'qa_invocation_01'
load = lambda path: json.loads(Path(path).read_bytes())
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def observe_known_pid(pid):
    """SYNCHRONIZE-only handles, zero-time waits, recorded PIDs only."""
    assert type(pid) is int and 0 < pid < 2**32
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    row = dict(pid=pid, observed_utc=datetime.now(timezone.utc).isoformat(),
        method='OpenProcess(SYNCHRONIZE) + WaitForSingleObject(handle,0); recorded PID only',
        process_stopped=None, exit_code=None, owner_reaped=None)
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        row.update(open_error=error, process_stopped=True if error == 87 else None,
                   observation='PID absent' if error == 87 else 'OS state unavailable')
        return row
    try:
        waited = kernel.WaitForSingleObject(handle, 0)
        row.update(wait_result=waited, process_stopped=True if waited == 0 else False if waited == 258 else None,
                   observation='signaled' if waited == 0 else 'live' if waited == 258 else 'OS state unavailable')
    finally:
        kernel.CloseHandle(handle)
    return row


def main():
    begun = time.perf_counter_ns()
    previous = load(FOLDER / 'QA_AUDIT_01.json')
    assert previous['passed'] is False and len(previous['check_failures']) == 4
    assert (FOLDER / 'QA_AUDIT.json').read_bytes() == (FOLDER / 'QA_AUDIT_01.json').read_bytes(), 'preserve_first_audit_before_correction'
    raw_paths = sorted(path for base in (QA, OUTER) for path in base.rglob('*') if path.is_file())
    raw_before = {path: path.read_bytes() for path in raw_paths}
    result, plan, runtime = load(QA/'RESULTS.json'), load(QA/'PLAN.json'), load(QA/'RUNTIME_PLAN.json')
    freeze, endpoint = load(QA/'FREEZE.json'), load(QA/'ENDPOINT_FREEZE.json')
    started, outer = load(QA/'STARTED.json'), load(OUTER/'RESULT.json')
    bootstrap = load(QA/'stdio/BOOTSTRAP_RESULT.json')
    worker_events = [json.loads(line) for line in (QA/'owned/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    config, ready, closed = load(QA/'owned/CONFIG.json'), load(QA/'owned/READY.json'), load(QA/'owned/WORKER_CLOSED.json')
    native_close = load(QA/'rpc_close/RESPONSE.json')
    checks = []

    def expect(name, passed, **evidence):
        checks.append(dict(name=name, passed=bool(passed), **evidence))

    expect('outer_exit_owner_reap', outer['exit_code']==0 and outer['process_reaped'] is True)
    expect('outer_clock_and_bytes', outer['wall_ns']==outer['finished_ns']-outer['started_ns']
           and outer['stdout_bytes']==len(raw_before[OUTER/'STDOUT.raw.bin'])
           and outer['stderr_bytes']==len(raw_before[OUTER/'STDERR.raw.bin']))
    expect('plan_freeze', sha(raw_before[QA/'PLAN.json'])==freeze['plan_sha256']==outer['plan_sha256'])
    expect('started_freeze', sha(raw_before[QA/'FREEZE.json'])==started['freeze_sha256'])
    expect('runtime_endpoint_freeze', sha(raw_before[QA/'RUNTIME_PLAN.json'])==endpoint['runtime_plan_sha256']
           and sha(Path(runtime['config_path']).read_bytes())==endpoint['config_sha256'])
    for row in freeze['controllers']:
        expect('frozen_controller_or_proof:'+row['path'], sha(Path(row['path']).read_bytes())==row['sha256'])
    manifest = plan['product_manifest']
    source_root = Path(plan['source_root'])
    expect('manifest131', len(manifest)==len({r['path'] for r in manifest})==131)
    source_checks = []
    for row in manifest:
        disk = (ROOT/row['path']).read_bytes()
        snapshot = (source_root/row['path']).read_bytes()
        blob = subprocess.check_output(['git','cat-file','blob',plan['candidate_commit']+':'+row['path']], cwd=ROOT)
        source_checks.append(dict(path=row['path'], sha256=sha(disk), matches=sha(disk)==sha(snapshot)==sha(blob)==row['sha256']))
    expect('all_source_copies_and_Git_blobs', all(row['matches'] for row in source_checks))
    constants = {}
    for node in ast.parse((source_root/'human_eye_plugin/runtime_identity.py').read_bytes()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION'):
                    constants[target.id] = ast.literal_eval(node.value)
    canonical = dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'],
                     files=sorted(manifest,key=lambda r:r['path']))
    canonical_sha = sha(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    expect('canonical_identity', canonical_sha==plan['source_sha256']==runtime['source_sha256']==result['source_sha256']==bootstrap['source_sha256'])
    fixed_assets = []
    for label, path, expected in [('source_asset',Path(plan['asset']),plan['asset_sha256']),
            ('owned_asset',QA/'owned/input.blend',plan['asset_sha256']),
            ('helper',Path(plan['helper']),plan['helper_sha256']),('Blender',Path(plan['blender']),plan['blender_sha256'])]:
        item = dict(label=label,path=str(path),sha256=sha(path.read_bytes()),expected_sha256=expected)
        fixed_assets.append(item)
        expect('fixed_bytes:'+label,item['sha256']==expected)
    expect('one_session_caps_no_replay', result['owned_sessions_attempted']==plan['max_sessions']==1
           and result['product_attempts']==2 and result['control_RPC_attempts']==1 and result['total_RPC_attempts']==3
           and result['profile_setup_RPC']==0 and result['retries']==0 and result['model_consumers']==result['actual_external_API']==0
           and config['max_calls']==2 and plan['max_total_RPC']==3 and plan['max_execute_RPC']==2 and plan['max_close_RPC']==1)
    expect('original_deadline_and_budgets', runtime['deadline_ns']==result['original_deadline_ns']==config['deadline_ns']==ready['deadline_ns']==closed['original_deadline_ns']
           and runtime['deadline_ns']-started['started_ns']==600_000_000_000
           and plan['request_budget_s']==20 and plan['native_visual_timeout_s']==10 and plan['original_worker_seconds']==600)
    expect('window_caps', started['window']['token']=='DEGENERATE-SURFACE-001-20261108T110651Z-QA-ONLY'
           and started['window']['max_sessions']==1 and started['window']['max_RPC']==3 and started['window']['model_answers']==0
           and datetime.fromisoformat(result['ended_utc'])<datetime.fromisoformat(started['window']['expires_utc']))
    frames, values = [], []
    for folder in sorted((QA/'mcp_frames').iterdir()):
        tx = (folder/'TX.bin').read_bytes()
        request = json.loads(tx)
        meter = load(folder/'METER.json')
        rx = (folder/'RX.bin').read_bytes() if (folder/'RX.bin').exists() else None
        response = json.loads(rx) if rx is not None else None
        expect('MCP_meter:'+folder.name, len(tx)==meter['tx_bytes'] and request==meter['request']
               and (rx is None or len(rx)==meter['rx_bytes'] and response==load(folder/'RESPONSE.json')))
        if request['method']=='tools/call':
            expect('MCP_observe_name:'+folder.name,request['params']['name']=='human_eye_scene_observe')
            content = response['result']['content']
            expect('MCP_text_only:'+folder.name,not response['result'].get('isError',False)
                   and len(content)==1 and content[0]['type']=='text' and 'structuredContent' not in response['result'])
            values.append(json.loads(content[0]['text']))
        frames.append(dict(sequence=int(folder.name), method=request['method'],
            request=request, tx_bytes=len(tx),rx_bytes=None if rx is None else len(rx),elapsed_ns=meter['elapsed_ns']))
    expect('exact_MCP_sequence',[f['method'] for f in frames]==['initialize','notifications/initialized','tools/list','tools/call','tools/call'])
    direct, legacy = frames[3]['request']['params']['arguments'], frames[4]['request']['params']['arguments']
    expect('direct_name_then_returned_legacy', direct['query']==dict(mode='surface_nearest',objects=[dict(name='M4_Focal')])
           and 'focal_id' not in direct and legacy['query']==dict(mode='surface_nearest')
           and legacy['focal_id']==values[0]['focal']['id'] and direct['include_image'] is legacy['include_image'] is False)
    semantic_keys = ('result_kind','status','scope','focal','nearest_objects','best_known_objects','distance_m',
                     'best_known_distance_m','unit','coverage','unresolved','execution_authority')
    expect('public_semantic_equivalence', {k:values[0].get(k) for k in semantic_keys}=={k:values[1].get(k) for k in semantic_keys})
    scripts, packets, physical = [], [], []
    socket_folders = sorted((QA/'stdio').glob('socket_*'))
    expect('two_product_socket_attempts',len(socket_folders)==2==result['product_socket_count'])
    for sequence,folder in enumerate(socket_folders,1):
        tx,rx=(folder/'TX.bin').read_bytes(),(folder/'RX.bin').read_bytes()
        request,response=json.loads(tx),json.loads(rx)
        meter=load(folder/'METER.json')
        script_path=QA/'owned'/('call_'+str(sequence))/'SCRIPT.py'
        script=script_path.read_bytes()
        script_request=None;host_path=None
        for node in ast.parse(script).body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_request' for t in node.targets):
                script_request=json.loads(ast.literal_eval(node.value.args[0]))
        for node in ast.walk(ast.parse(script)):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_source' for t in node.targets):
                host_path=ast.literal_eval(node.value.args[0])
        event=worker_events[sequence-1]
        logical_code = request['params']['code'].encode('utf8')
        script_storage_projection = logical_code.replace(b'\n', b'\r\n')
        expect('physical_execute_script:'+str(sequence), request['type']=='execute_code'
               and event['sequence']==sequence and event['script_sha256']==sha(logical_code) and event['status']=='completed'
               and event['script_error'] is None and event['terminal_geometry_and_file_checks_passed'] is True)
        expect('script_disk_exact_text_storage_projection:'+str(sequence),script==script_storage_projection,
               logical_code_bytes=len(logical_code),logical_code_sha256=sha(logical_code),
               disk_bytes=len(script),disk_sha256=sha(script),LF_count=logical_code.count(b'\n'),
               logical_CRLF_count=logical_code.count(b'\r\n'),storage_rule='Windows write_text: every LF is written as CRLF')
        expect('owned_meter:'+str(sequence),len(tx)==meter['send_attempted_bytes']==meter['send_completed_bytes'] and len(rx)==meter['received_bytes'])
        expect('worker_capture_only:'+str(sequence),script_request['command']=='capture_nearest_candidates'
               and Path(host_path)==source_root/'human_eye_plugin/blender_host.py'
               and plan['host_sha256'] in script.decode() and 'exec(compile(_source_bytes' in script.decode())
        expect('original_host_deadline:'+str(sequence),0<script_request['params']['deadline_ns']-meter['started_ns']<=10_000_000_000
               and script_request['params']['deadline_ns']<runtime['deadline_ns'])
        stdout=(script_path.parent/'stdout.txt').read_bytes()
        logical_stdout=response['result']['result'].encode('utf8')
        expect('worker_stdout_socket_binding:'+str(sequence),response['status']=='success' and response['result']['executed'] is True
               and len(logical_stdout)==event['stdout_bytes']
               and event['stderr_bytes']==0 and (script_path.parent/'stderr.txt').stat().st_size==0)
        expect('stdout_disk_exact_text_storage_projection:'+str(sequence),stdout==logical_stdout.replace(b'\n',b'\r\n'),
               logical_stdout_bytes=len(logical_stdout),logical_stdout_sha256=sha(logical_stdout),
               disk_bytes=len(stdout),disk_sha256=sha(stdout),LF_count=logical_stdout.count(b'\n'),
               logical_CRLF_count=logical_stdout.count(b'\r\n'),storage_rule='Windows write_text: every LF is written as CRLF')
        text=stdout.decode().strip();prefix='HUMAN_EYE_BLENDER_MCP:'
        assert text.startswith(prefix)
        envelope=json.loads(text[len(prefix):])
        packet=envelope['result']; packets.append(packet)
        expect('host_request_response_binding:'+str(sequence),envelope['id']==script_request['id']
               and packet['protocol']=='single-read-surface-candidates-v1'
               and packet['result_kind']=='acquisition_only_not_nearest_result' and packet['execution_authority'] is False)
        scripts.append(dict(sequence=sequence,path=str(script_path),disk_bytes=len(script),disk_sha256=sha(script),
            logical_code_bytes=len(logical_code),logical_code_sha256=sha(logical_code),worker_event_script_sha256=event['script_sha256'],
            exact_disk_projection=script==script_storage_projection,logical_stdout_bytes=len(logical_stdout),
            logical_stdout_sha256=sha(logical_stdout),stdout_disk_bytes=len(stdout),stdout_disk_sha256=sha(stdout),
            command=script_request['command'],params=script_request['params'],host_source_path=host_path,
            worker_elapsed_ns=event['elapsed_ns'],render_events_before=event['render_events_before'],render_events_after=event['render_events_after']))
        physical.append(dict(kind='execute_code',sequence=sequence,tx_bytes=len(tx),rx_bytes=len(rx),meter=meter))
    expect('selector_then_legacy_host_capture',scripts[0]['params']['selector']==dict(name='M4_Focal')
           and scripts[0]['params']['focal_id'] is None and scripts[1]['params']['focal_id']==values[0]['focal']['id']
           and scripts[1]['params'].get('selector') is None)
    expect('physical_repeat_geometry',packets[0]['capture']['meshes']==packets[1]['capture']['meshes'])
    # Independent closed-form oracle from the actual returned binary64 coordinates.
    meshes=packets[0]['capture']['meshes']; focal=next(m for m in meshes if m['name']=='M4_Focal')
    expect('T04_actual_focal_segment',focal['vertices']==[[0.,0.,0.],[0.,1.,0.],[0.,0.,0.]] and focal['faces']==[[0,1,2]])
    distances=[]
    for mesh in meshes:
        if mesh['name']=='M4_Focal': continue
        x=mesh['vertices'][0][0]
        expect('T04_parallel_actual_target:'+mesh['name'],x>0 and mesh['vertices']==[[x,0.,0.],[x,1.,0.],[x,0.,1.]] and mesh['faces']==[[0,1,2]])
        f=Fraction.from_float(x)
        distances.append(dict(name=mesh['name'],object_id=mesh['object_id'],distance_m=float(f),
                              exact_numerator=f.numerator,exact_denominator=f.denominator))
    minimum=min(Fraction(d['exact_numerator'],d['exact_denominator']) for d in distances)
    names=sorted(d['name'] for d in distances if Fraction(d['exact_numerator'],d['exact_denominator'])==minimum)
    for index,value in enumerate(values,1):
        expect('T04_public_oracle:'+str(index),value['status']=='complete' and value['unit']=='m'
               and value['execution_authority'] is False and value['distance_m']==float(minimum)
               and sorted(row['name'] for row in value['nearest_objects'])==names
               and value['coverage']==dict(targets_excluding_focal=4,distance_valid=4,strictly_excluded=0,unresolved=0)
               and not value['unresolved'] and value['binding']['runtime_source_sha256']==canonical_sha)
    close_tx,close_rx=(QA/'rpc_close/TX.bin').read_bytes(),(QA/'rpc_close/RX.bin').read_bytes()
    close_meter=load(QA/'rpc_close/METER.json')
    expect('physical_close_request',json.loads(close_tx)==dict(type='close') and json.loads(close_rx)==native_close['response'])
    expect('close_meter',len(close_tx)==close_meter['send_attempted_bytes']==close_meter['send_completed_bytes'] and len(close_rx)==close_meter['received_bytes'])
    physical.append(dict(kind='close',sequence=3,tx_bytes=len(close_tx),rx_bytes=len(close_rx),meter=close_meter))
    expect('native_owner_close_receipts',native_close==result['native_cleanup'] and native_close['pid']==ready['pid']==closed['pid']
           and native_close['response']['status']=='closed' and native_close['error'] is None
           and native_close['original_deadline_ns']==native_close['response']['deadline_ns']==runtime['deadline_ns']
           and native_close['exit_code']==0 and native_close['process_reaped'] is True
           and native_close['source_file_unchanged'] and native_close['protected_files_unchanged'] and closed['poisoned'] is False)
    close_files=list((QA/'owned').glob('CLOSE_*.json'))
    expect('one_native_owner_close_file',len(close_files)==1 and load(close_files[0])==native_close)
    expect('geometry_fingerprint_unchanged',ready['initial_fingerprint']==closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'])
    expect('worker_event_denominator',len(worker_events)==3 and [e['sequence'] for e in worker_events]==[1,2,3]
           and [e['status'] for e in worker_events]==['completed','completed','unknown'])
    witness=bootstrap['execution_witness']
    expect('actual_stdio_verified_loader',witness['guard_verified'] is True and witness['loaded_engine_module_count']==57
           and witness['every_loaded_module_has_execution_or_namespace_witness'] is True
           and witness['bound_generation']['compatible'] is True
           and witness['bound_generation']['loaded_build_id']=='sha256:'+canonical_sha)
    expect('no_packet_substitution',bootstrap['original_request_unchanged'] is True and bootstrap['no_packet_file_input'] is True)
    stdio=result['stdio_cleanup']
    stdio_process=load(QA/'STDIO_PROCESS.json')
    expect('stdio_owner_reap',stdio['pid']==stdio_process['pid'] and stdio['exit_code']==0 and stdio['process_reaped'] is True
           and stdio['extra_rx_bytes']==0 and (QA/'STDIO_EXTRA_RX.bin').stat().st_size==0)
    expect('reported_boundary_totals',result['boundary_totals']==dict(control_TX_attempted_bytes=len(close_tx),control_TX_completed_bytes=len(close_tx),
        control_RX_bytes=len(close_rx),product_TX_attempted_bytes=sum(p['tx_bytes'] for p in physical[:2]),
        product_TX_completed_bytes=sum(p['tx_bytes'] for p in physical[:2]),product_RX_bytes=sum(p['rx_bytes'] for p in physical[:2]),
        complete_stdio_TX_bytes=sum(f['tx_bytes'] for f in frames),complete_stdio_RX_bytes=sum(f['rx_bytes'] or 0 for f in frames)))
    actual_surface_calls=[row for row in bootstrap['calls'] if row['name']=='surface_nearest_result']
    expect('capture_cache_profiles',len(actual_surface_calls)==2 and actual_surface_calls[0]['diagnostics']['kernel_calls']==4
           and actual_surface_calls[0]['diagnostics']['cache_hits']==0 and actual_surface_calls[1]['diagnostics']['kernel_calls']==0
           and actual_surface_calls[1]['diagnostics']['cache_hits']==4)
    recorded_roles=dict(outer_Popen=outer['pid'],controller_self=result['controller_pid'],stdio_Popen=stdio['pid'],native_Popen=ready['pid'])
    assert previous['recorded_PID_roles'] == recorded_roles
    pid_observations=previous['PID_observations']
    expect('recorded_PID_queries_stopped',all(row['process_stopped'] is True for row in pid_observations))
    expect('all_original_bytes_stable',all(path.read_bytes()==raw for path,raw in raw_before.items()))
    raw_index=[dict(path=str(path.relative_to(FOLDER)),bytes=len(raw),sha256=sha(raw)) for path,raw in raw_before.items()]
    payload=dict(cycle_id='DEGENERATE-SURFACE-001',audit='independent_existing_raw_QA_only',audited_utc=datetime.now(timezone.utc).isoformat(),
        passed=all(row['passed'] for row in checks),checks=checks,check_count=len(checks),
        check_failures=[row for row in checks if not row['passed']],candidate_commit=plan['candidate_commit'],source_sha256=canonical_sha,
        source_count=len(source_checks),source_checks=source_checks,raw_file_count=len(raw_index),raw_files=raw_index,originals_unchanged=True,
        physical_RPC_count=len(physical),physical_RPC=physical,public_observations=values,MCP_frames=frames,
        worker_scripts=scripts,worker_events=worker_events,source_guard=witness,asset_helper_binary_hashes=fixed_assets,
        independent_T04_oracle=dict(scope='Actual packet binary64 coordinates only; no kernel import/call',
            proof='Focal is x=z=0, y in[0,1]. Each target is the triangle [(x,0,0),(x,1,0),(x,0,1)], x>0. Constant x separation is a lower bound attained at y=z=0, so distance equals x exactly.',
            targets=distances,minimum_distance_m=float(minimum),exact_minimum_numerator=minimum.numerator,
            exact_minimum_denominator=minimum.denominator,nearest_names=names,clearance_3mm_met=minimum>=Fraction(3,1000)),
        clocks=dict(prepare_elapsed_ns=plan['prepare_elapsed_ns'],whole_outer_ns=outer['wall_ns'],whole_controller_ns=result['whole_controller_ns'],
            native_startup_ns=result['native_startup_ns'],public_call_elapsed_ns=[row['elapsed_ns'] for row in result['public_calls']],
            native_close_ns=native_close['elapsed_ns'],close_wrapper_ns=close_meter['elapsed_ns'],stdio_lifetime_ns=stdio['elapsed_ns'],
            profile_overhead_ns=bootstrap['profile_overhead_ns'],outer_started_utc=outer['started_utc'],outer_ended_utc=outer['ended_utc'],
            note='Nested observations; do not sum or subtract overhead as free work. Cold/warm timing does not establish model/task benefit.'),
        boundary_totals=result['boundary_totals'],recorded_PID_roles=recorded_roles,PID_observations=pid_observations,
        owner_receipts=dict(outer=outer,stdio=stdio,native_close=native_close),
        first_audit_preservation=dict(JSON=dict(path='QA_AUDIT_01.json',sha256=sha((FOLDER/'QA_AUDIT_01.json').read_bytes())),
            MD=dict(path='QA_AUDIT_01.md',sha256=sha((FOLDER/'QA_AUDIT_01.md').read_bytes())),
            executed_script=dict(path='qa_audit_01.py',sha256=sha((FOLDER/'qa_audit_01.py').read_bytes())),
            check_count=previous['check_count'],original_failed_checks=previous['check_failures'],
            cause='First audit incorrectly equated wire/logical LF text with Windows write_text CRLF disk artifacts. Corrected audit strictly matches wire-code SHA to worker event, and separately proves exact LF-to-CRLF storage projections byte-for-byte. No QA raw or product execution changed.'),
        PID_observation_source='Preserved QA_AUDIT_01.json observations; corrected bookkeeping audit made zero additional PID queries.',
        unknowns=dict(worker_close_event_status=worker_events[-1]['status'],
            controller_self_owner_wait_receipt=None,unknown_descendant_process_coverage=None,fees=None,author_usage=None,
            note='The outer Popen PID differs from controller self PID; owner receipt attests only its Popen handle. Self PID is separately observed stopped. The unknown worker close-event is not rewritten by independent closed response/owner wait.'),
        limits='Recorded-PID query cannot exclude PID reuse or unknown descendants. Terminal geometry/file checks cannot prove no reverted transient mutation or a Python sandbox.',
        actual_additional_Blender_sessions=0,actual_additional_RPC=0,actual_product_imports=0,actual_models=0,signals_or_global_process_enumeration=0,
        audit_elapsed_ns=time.perf_counter_ns()-begun)
    (FOLDER/'QA_AUDIT.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    seconds=lambda n:n/1e9
    text=f"""# DEGENERATE-SURFACE-001 raw QA audit

Independent existing-byte audit: passed={payload['passed']}; {len(checks)} consistency checks, {len(payload['check_failures'])} failed. All {len(raw_index)} original QA/outer files remained byte-identical. No additional product import, Blender session, RPC, model, process signal or global process enumeration was performed.

Candidate {plan['candidate_commit']}; 131-source canonical {canonical_sha}. Current disk, offline engine snapshot and fixed Git blobs match. Exact frozen controller/proof hashes, original T04 asset/copy, helper and Blender hashes match. The actual production stdio guard reports {witness['loaded_engine_module_count']} loaded modules, every loaded module witnessed, compatible generation. Worker scripts independently bind the expected unchanged readonly host bytes.

One NativeSession; exactly three physical RPCs: name surface_nearest, returned focal.id legacy surface_nearest, owner close. No setup/profile RPC. MCP sequence is initialize, initialized notification, tools/list, two tools/call frames. Both public observations are complete, have unit m, no execution authority, all four targets distance-valid, zero unresolved/strictly-excluded, nearest {names}, distance {float(minimum)}. Semantic fields are identical. The independent oracle uses actual returned binary64 coordinates: target constant x is a lower bound achieved at y=z=0. The exact minimum is {minimum.numerator}/{minimum.denominator} m, above or equal to 3mm={minimum>=Fraction(3,1000)}. This is a QA distance check, not a new consumer answer.

Original worker deadline remains 600 seconds; product request/host budgets remain 20/10 seconds. Two SCRIPT hashes match worker events and physical execute_code payloads, two worker stdout bodies match socket outputs, and both source captures match. Actual profile diagnostics retain first request kernel/cache 4/0 and second request 0/4; cold/warm durations do not establish task benefit.

Time boundaries (nested, not additive): preparation {seconds(plan['prepare_elapsed_ns']):.7f}s; outer Popen/wait {seconds(outer['wall_ns']):.7f}s; controller {seconds(result['whole_controller_ns']):.7f}s; Native startup {seconds(result['native_startup_ns']):.7f}s; public calls {[seconds(r['elapsed_ns']) for r in result['public_calls']]}s; stdio lifetime {seconds(stdio['elapsed_ns']):.7f}s; native close {seconds(native_close['elapsed_ns']):.7f}s; close wrapper {seconds(close_meter['elapsed_ns']):.7f}s; profile overhead {seconds(bootstrap['profile_overhead_ns']):.7f}s. Management/implementation/offline time is outside these QA boundaries. No overhead is removed as free work.

Bytes: product socket TX/RX {result['boundary_totals']['product_TX_completed_bytes']}/{result['boundary_totals']['product_RX_bytes']}; close TX/RX {len(close_tx)}/{len(close_rx)}; complete stdio TX/RX {stdio['complete_TX_bytes']}/{stdio['complete_RX_bytes']}. These transport boundaries overlap and are not provider tokens. Render event counts remain zero; no generated PNG changes were recorded.

Owner receipts: outer Popen {outer['pid']} exit0/reaped; stdio Popen {stdio['pid']} exit0/reaped; Native {ready['pid']} exit0/reaped with closed response, unchanged original deadline, helper/assets and geometry fingerprints, poisoned=false. Controller self PID {result['controller_pid']} differs from the outer Popen handle; no direct owner-wait receipt for that self PID is invented. All {len(pid_observations)} distinct recorded PIDs were independently observed stopped using zero-time SYNCHRONIZE waits. This cannot exclude PID reuse or unknown descendants.

The third worker event remains status={worker_events[-1]['status']!r}. A separate close response and owner wait support closure but do not turn that unknown event into graceful success. Missing owner/descendant coverage, author usage and fees remain unknown. Terminal fingerprint/file checks do not prove absence of reverted transient mutation or a Python sandbox. No model/task benefit claim is made.
"""
    text=text.replace('Two SCRIPT hashes match worker events and physical execute_code payloads',
        'Two logical code hashes match worker events and physical execute_code payloads')
    text += f"\nFirst bookkeeping audit is preserved as QA_AUDIT_01.json/md and qa_audit_01.py: 71 checks, 4 false comparisons caused by conflating LF logical text with CRLF disk artifacts. This corrected audit proves, byte-for-byte, disk SCRIPT == logical wire code with each LF written as CRLF, while worker event SHA == logical code SHA. Script logical/disk bytes are {[ (s['logical_code_bytes'],s['disk_bytes']) for s in scripts ]}; stdout logical/disk bytes are {[ (s['logical_stdout_bytes'],s['stdout_disk_bytes']) for s in scripts ]}. Original CRLF counts and independent hashes are retained. No QA was replayed, no raw file changed, and original four PID observations were reused without additional queries.\n"
    (FOLDER/'QA_AUDIT.md').write_text(text,encoding='utf8',newline='\n')
    print(json.dumps(dict(passed=payload['passed'],checks=len(checks),failures=payload['check_failures'],raw_files=len(raw_index),
        physical_RPC=len(physical),loaded_engine_module_count=witness['loaded_engine_module_count'],
        distinct_recorded_PIDs=len(pid_observations),all_recorded_stopped=all(r['process_stopped'] is True for r in pid_observations),
        JSON_sha256=sha((FOLDER/'QA_AUDIT.json').read_bytes()),MD_sha256=sha((FOLDER/'QA_AUDIT.md').read_bytes()))))


if __name__=='__main__':
    main()
