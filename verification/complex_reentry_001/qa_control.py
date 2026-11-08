"""Prepare fixed current bytes, then one bounded public assembly entry check.

The first public request asks only solid_relation. A correctly bound unknown
ends the session; continuation uses the original QA-only vertex patch helper.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import types

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
OUT = FOLDER / 'qa_01'
COORD = Path('D:/hefe/verification/fixes/20261108_complex_reentry')
STATE = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
TOKEN = 'COMPLEX-REENTRY-001-20261108T133303Z-ONLY'
BASELINE = 'a4465a388b73ce144035d9139afb48f61519163a'
PRODUCT = '0ad59befeee43c2fad752e3bad2ee69f87af3136'
SOURCE = '82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6'
ASSIGNMENT_SHA = '204aeb8cf206c5a1dfd3a781e720b274a5ae2528f59e3e94a562f860ac94be33'
WINDOW_SHA = '2c1dc866c0b9ae46a1ff367ee2f95080b18d41c5f4413f95e20c8edbbea0bbbb'
OLD = ROOT / 'verification/surface_nearest_entry_001/qa_prepare'
HELPER = ROOT / 'verification/visual004_native.py'
HELPER_SHA = '13887e30d9f08309102e17704b91603325df13c490bdcc6bcda8b74ac01c59b8'
BOOTSTRAP_SHA = '45363af4e6763589dee638ba3a0bc1ee6a9cc00eca9da950736b2ae6fabe39a6'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
PYTHON = ROOT / 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe'
AUTHOR = ROOT / 'verification/fixes/perf_integrated_001/run_01/author/assembly'
INPUT_HASHES = {
    'scene.blend': 'a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb',
    'qa_patch.json': 'c349f2043f9c75aa194076eb6fb12dfb336ea1139fc9b0dcf1c0cf90876e842a',
    'author_mesh_snapshots.json': '5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14',
    'tasks.json': '921298e2da3275812d7a7a64befa42ce91aa95022192534927c4a373423e4f7e'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf8'))


def error_info(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def window(implementation_deadline):
    assert sha(COORD / 'WINDOW.json') == WINDOW_SHA
    assert sha(COORD / 'ENTRY_ASSIGNMENT.md') == ASSIGNMENT_SHA
    value = json.loads((COORD / 'WINDOW.json').read_bytes())
    current = json.loads(STATE.read_bytes())['performance_window']
    assert current['token'] == value['token'] == TOKEN
    assert current['owner'] == value['owner'] == 'W-ENTRY'
    assert str(current['status']).startswith('granted') or current['status'] == 'active_dispatched'
    assert value['max_sessions'] == current['max_sessions'] == 1
    assert value['max_RPC'] == current['max_RPC'] == 16
    assert value['max_public_observations'] == 9 and value['model_answers'] == 0
    end = datetime.fromisoformat(value['expires_utc'].replace('Z', '+00:00')).timestamp()
    assert time.time() < min(end, implementation_deadline) - 660, 'leave_original_worker_and_cleanup'
    return value


def check_sources(plan):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == BASELINE
    for row in plan['product_manifest']:
        assert sha(ROOT / row['path']) == sha(Path(plan['source_root']) / row['path']) == row['sha256']
    assert sha(HELPER) == HELPER_SHA and sha(BLENDER) == BLENDER_SHA
    for name, digest in INPUT_HASHES.items():
        assert sha(FOLDER / 'inputs' / name) == digest
        original = ROOT / 'verification/fixtures/perf_integrated_001_tasks.json' if name == 'tasks.json' else AUTHOR / name
        assert sha(original) == digest
    assert Path(sys.executable).resolve() == PYTHON.resolve()


def prepare(args):
    begun = time.perf_counter_ns()
    assert not OUT.exists(), 'fresh_QA_only'
    frozen_path = args.source_freeze.resolve()
    frozen = json.loads(frozen_path.read_bytes())
    assert frozen['source_sha256'] == SOURCE
    manifest = sorted([dict(path=r['path'], sha256=r['sha256']) for r in frozen['product_manifest']], key=lambda r:r['path'])
    assert len(manifest) == len({r['path'] for r in manifest}) == 131
    source_root = Path(frozen['source_root']).resolve()
    assert source_root.is_relative_to(FOLDER)
    deadline = frozen['implementation_deadline_epoch_seconds']
    plan = dict(baseline_HEAD=BASELINE, candidate_commit=PRODUCT, source_sha256=SOURCE,
        product_manifest=manifest, source_root=str(source_root), run_root=str(OUT),
        asset=str(FOLDER / 'inputs/scene.blend'), asset_sha256=INPUT_HASHES['scene.blend'],
        patch=str(FOLDER / 'inputs/qa_patch.json'), patch_sha256=INPUT_HASHES['qa_patch.json'],
        snapshots=str(FOLDER / 'inputs/author_mesh_snapshots.json'),
        blender=str(BLENDER), blender_sha256=BLENDER_SHA, helper=str(HELPER), helper_sha256=HELPER_SHA,
        implementation_deadline_epoch_seconds=deadline, window=window(deadline),
        max_sessions=1, max_total_RPC=16, max_public_observations=9,
        original_worker_seconds=600, request_budget_s=20., native_visual_timeout_s=10.,
        model_consumers=0, new_product_candidates=0, source_freeze=dict(path=str(frozen_path), sha256=sha(frozen_path)))
    check_sources(plan)
    for row in manifest:
        assert subprocess.check_output(['git', 'cat-file', 'blob', PRODUCT + ':' + row['path']], cwd=ROOT) == (ROOT / row['path']).read_bytes()
    assert subprocess.check_output(['git', 'cat-file', 'blob', BASELINE + ':verification/visual004_native.py'], cwd=ROOT) == HELPER.read_bytes()
    constants = {}
    for node in ast.parse((source_root / 'human_eye_plugin/runtime_identity.py').read_bytes()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION'):
                    constants[target.id] = ast.literal_eval(node.value)
    canonical = dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest)
    assert hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest() == SOURCE
    assert sha(OLD / 'stdio_bootstrap.py') == BOOTSTRAP_SHA
    OUT.mkdir()
    (OUT / 'stdio_bootstrap.py').write_bytes((OLD / 'stdio_bootstrap.py').read_bytes())
    plan['host_sha256'] = sha(source_root / 'human_eye_plugin/blender_host.py')
    plan.update(prepared_utc=datetime.now(timezone.utc).isoformat(), prepare_elapsed_ns=time.perf_counter_ns()-begun)
    save(OUT / 'PLAN.json', plan)
    paths = [Path(__file__), HELPER, OLD / 'controller.py', OUT / 'stdio_bootstrap.py', frozen_path]
    paths += [FOLDER / 'inputs' / name for name in INPUT_HASHES]
    paths += [COORD / name for name in ('WINDOW.json', 'ENTRY_ASSIGNMENT.md', 'PLAN.md')]
    save(OUT / 'FREEZE.json', dict(plan_sha256=sha(OUT / 'PLAN.json'), no_session_started=True,
        controllers=[dict(path=str(path),sha256=sha(path)) for path in paths]))
    print(json.dumps(dict(status='prepared_no_session', source_sha256=SOURCE, max_RPC=16, first_fact='solid_relation_only')))


def existing_helpers():
    spec = importlib.util.spec_from_file_location('_complex_existing_stdio_controller', OLD / 'controller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    module.FOLDER = OUT
    return module


def world_points(obj, scale):
    matrix = obj['matrix_world']
    return [[(sum(matrix[r][k] * point[k] for k in range(3)) + matrix[r][3]) * scale for r in range(3)]
            for point in obj['vertices_local']]


def check_face_partition(triangles, polygons):
    groups = [[] for _ in polygons]
    for triangle in triangles:
        assert len(triangle) == len(set(triangle)) == 3
        candidates = [i for i,p in enumerate(polygons) if set(triangle).issubset(p)]
        assert len(candidates) == 1, 'captured_triangle_original_polygon_binding'
        groups[candidates[0]].append(triangle)
    for polygon, group in zip(polygons, groups):
        assert len(group) == len(polygon)-2
        edges = Counter(tuple(sorted((t[i], t[(i+1)%3]))) for t in group for i in range(3))
        boundary = {tuple(sorted((polygon[i],polygon[(i+1)%len(polygon)]))) for i in range(len(polygon))}
        assert {edge for edge,count in edges.items() if count == 1} == boundary
        assert all(count in (1,2) for count in edges.values())


def public_value(response):
    assert 'error' not in response, 'JSONRPC_error_not_capability_gap'
    result = response['result']
    content = result.get('content', [])
    assert len(content) == 1 and content[0]['type'] == 'text'
    value = json.loads(content[0]['text'])
    assert value.get('result_kind') == 'task_query', 'non_task_result_not_capability_gap'
    return value, result.get('isError')


def bind_capture(socket_ordinal, value, plan, state, candidate):
    response = json.loads((OUT / f'stdio/socket_{socket_ordinal}/RX.bin').read_bytes())
    assert response['status'] == 'success' and response['result']['executed'] is True
    prefix, text = response['result']['result'].split('HUMAN_EYE_BLENDER_MCP:', 1)
    assert not prefix.strip()
    envelope = json.loads(text)
    assert envelope['protocol_version'] == '1.0' and 'error' not in envelope
    scene = envelope['result']
    assert scene['unit'] == 'm' and scene['coordinate_frame'] == 'world' and scene['source'] == 'blender'
    assert scene['capture_scope'] == 'selected_objects'
    selection = scene['task_selection']
    assert selection['candidate_count'] == 4 and selection['pair_reason'] is None
    assert selection['selectors'] == [{'name':'Object_01'}, {'name':candidate}]
    meshes = scene['meshes']; assert len(meshes) == 2
    snapshots = json.loads(Path(plan['snapshots']).read_bytes())['changed' if state == 'changed_current' else 'initial']
    expected = {obj['name']:obj for obj in snapshots['objects']}
    assert {mesh['name'] for mesh in meshes} == {'Object_01',candidate}
    for mesh in meshes:
        obj = expected[mesh['name']]
        assert mesh['vertices'] == world_points(obj, snapshots['unit_scale_m']), 'current_geometry_mismatch'
        check_face_partition(mesh['faces'], obj['faces'])
    binding = value['binding']
    assert binding['runtime_source_sha256'] == SOURCE and binding['source'] == 'blender'
    assert binding['capture_scope'] == 'selected_objects' and binding['candidate_count'] == 4 and binding['selected_count'] == 2
    assert {row['name']:row['object_id'] for row in binding['objects']} == {m['name']:m['object_id'] for m in meshes}
    assert value['unit'] == 'm' and value['coordinate_frame'] == 'world' and value['execution_authority'] is False
    return dict(source_bound=True, selected_meshes=2, vertices=sum(len(m['vertices']) for m in meshes),
        triangles=sum(len(m['faces']) for m in meshes), candidate_count=4,
        original_snapshot_state='changed' if state == 'changed_current' else 'initial', current_geometry_exact=True)


READBACK = '''import json
rows=[]
for obj in sorted(bpy.context.scene.objects,key=lambda value:value.name):
    if obj.type!='MESH': continue
    matrix=[[float(x) for x in row] for row in obj.matrix_world]
    local=[[float(x) for x in v.co] for v in obj.data.vertices]
    world=[[(sum(matrix[r][k]*p[k] for k in range(3))+matrix[r][3])*float(bpy.context.scene.unit_settings.scale_length) for r in range(3)] for p in local]
    rows.append(dict(name=obj.name,vertices_local=local,matrix_world=matrix,world_vertices=world,faces=[list(p.vertices) for p in obj.data.polygons]))
print('COMPLEX_NATIVE_READBACK:'+json.dumps(dict(unit_scale_m=float(bpy.context.scene.unit_settings.scale_length),objects=rows),separators=(',',':'),allow_nan=False))
'''


def run():
    plan = json.loads((OUT / 'PLAN.json').read_bytes())
    frozen = json.loads((OUT / 'FREEZE.json').read_bytes())
    assert sha(OUT / 'PLAN.json') == frozen['plan_sha256']
    for row in frozen['controllers']:
        assert sha(row['path']) == row['sha256']
    check_sources(plan); active_window = window(plan['implementation_deadline_epoch_seconds'])
    assert not (OUT / 'STARTED.json').exists(), 'one_session_no_replay'
    helpers = existing_helpers()
    native = types.ModuleType('_complex_owned_native'); native.__file__ = str(HELPER)
    sys.modules[native.__name__] = native
    exec(compile(HELPER.read_bytes(),str(HELPER),'exec',dont_inherit=True),native.__dict__)
    begun = time.perf_counter_ns(); plan['deadline_ns'] = begun + 600_000_000_000
    schedule = [('initial','Object_03'),('initial','Object_02'),('initial','Object_04')]
    schedule += [(state,name) for state in ('unchanged_current','changed_current') for name in ('Object_02','Object_03','Object_04')]
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), original_deadline_ns=plan['deadline_ns'],
        controller_pid=os.getpid(), source_sha256=SOURCE, product_candidate=PRODUCT,
        owned_sessions_attempted=0, control_RPC_attempts=0, product_attempts=0, primary_error=None,
        public_calls=[], schedule=[dict(state=s,candidate=n,status='not_run') for s,n in schedule],
        model_consumers=0, new_product_candidates=0, adapter_corrections=0, retries=0,
        original_asset_write=False, profile_setup_RPC=0, capability_gap_observed=False)
    with (OUT / 'STARTED.json').open('xb') as stream:
        stream.write((json.dumps(dict(started_ns=begun, started_utc=record['started_utc'],
            argv=sys.argv, python=sys.executable, controller_pid=os.getpid(), window=active_window),indent=2)+'\n').encode())
    owner = stdio = None
    def socket_count(): return len(list((OUT / 'stdio').glob('socket_*')))
    def budget(close=False):
        assert record['control_RPC_attempts'] + socket_count() < (16 if close else 15), 'reserve_close_RPC'
        assert time.perf_counter_ns() < plan['deadline_ns'], 'original_deadline'
    def transaction(label, call, close=False):
        budget(close); folder = OUT / label; folder.mkdir()
        meter = dict(send_attempted_bytes=0,send_completed_bytes=0,received_bytes=0)
        original = native.socket.create_connection
        native.socket.create_connection = lambda *a,**k: helpers.MeterSocket(original(*a,**k),folder,meter)
        record['control_RPC_attempts'] += 1; started = time.perf_counter_ns()
        try:
            response=call(); save(folder/'RESPONSE.json',response); return response
        finally:
            native.socket.create_connection=original
            save(folder/'METER.json',dict(**meter,elapsed_ns=time.perf_counter_ns()-started))
    def observe(ordinal, facts):
        budget(); assert record['product_attempts'] < 9
        state,candidate=schedule[ordinal]; before=socket_count()
        args=dict(session_id='complex-entry-read',include_image=False,
            query=dict(mode='task',objects=[dict(name='Object_01'),dict(name=candidate)],requested_facts=facts))
        row=dict(ordinal=ordinal+1,state=state,candidate=candidate,arguments=args,started_ns=time.perf_counter_ns())
        record['public_calls'].append(row); record['product_attempts']+=1
        record['schedule'][ordinal]['status']='attempted'
        try:
            response=stdio.call('tools/call',dict(name='human_eye_scene_observe',arguments=args));row['response']=response
            assert socket_count()-before == 1, 'one_current_capture_per_observation'
            value,is_error=public_value(response); row['public_isError']=is_error; row['public_value']=value
            assert set(value['facts']) == set(facts)
            row['binding_check']=bind_capture(before+1,value,plan,state,candidate)
            record['schedule'][ordinal]['status']='bound_public_result'
            return value
        finally:
            row['elapsed_ns']=time.perf_counter_ns()-row['started_ns'];row['physical_RPC_delta']=socket_count()-before
    def readback(state):
        response=transaction('rpc_readback_'+state,lambda:owner.run(READBACK,timeout_s=10))
        wire=response['response']; assert wire['status']=='success'
        prefix,text=wire['result']['result'].split('COMPLEX_NATIVE_READBACK:',1);assert not prefix.strip()
        observed=json.loads(text)
        reference=json.loads(Path(plan['snapshots']).read_bytes())['changed' if state=='changed_current' else 'initial']
        assert observed['unit_scale_m']==reference['unit_scale_m']
        by_name={o['name']:o for o in observed['objects']}; assert set(by_name)=={o['name'] for o in reference['objects']}
        for expected in reference['objects']:
            actual=by_name[expected['name']]
            assert all(actual[key]==expected[key] for key in ('vertices_local','matrix_world','faces'))
            assert actual['world_vertices']==world_points(expected,reference['unit_scale_m'])
        return dict(state=state,current_geometry_exact=True,objects=len(by_name))
    try:
        record['owned_sessions_attempted']=1; started=time.perf_counter_ns()
        owner=native.NativeSession.start(blender=plan['blender'],asset=plan['asset'],workspace=OUT/'owned',
            deadline_ns=plan['deadline_ns'],condition='N',expected_asset_sha256=plan['asset_sha256'],
            max_calls=15,qa_vertex_patch=plan['patch'])
        record['native_startup_ns']=time.perf_counter_ns()-started; record['ready']=owner.ready
        plan['endpoint']=dict(host=owner.host,port=owner.port); plan['config_path']=str(OUT/'live-connector.json')
        save(plan['config_path'],dict(schema_version='1.0',enabled=True,observe_on_prompt=False,
            project_root=plan['source_root'],state_file=str(OUT/'state.json'),audit_file=str(OUT/'audit.jsonl'),
            expected_identity=dict(source_sha256=SOURCE),blender=dict(host=owner.host,port=owner.port,timeout_s=10),
            request_budget_s=20.,native_visual_timeout_s=10.))
        save(OUT/'RUNTIME_PLAN.json',plan); stdio=helpers.Stdio(plan)
        save(OUT/'STDIO_PROCESS.json',dict(pid=stdio.process.pid,owner='controller Popen',command=json.loads((OUT/'STDIO_COMMAND.json').read_bytes())))
        assert 'result' in stdio.call('initialize',dict(protocolVersion='2024-11-05',capabilities={},clientInfo=dict(name='complex-reentry-QA',version='1')))
        stdio.call('notifications/initialized',{},notification=True); tools=stdio.call('tools/list',{})
        assert any(t['name']=='human_eye_scene_observe' for t in tools['result']['tools'])
        assert socket_count()==0, 'initialization_must_not_capture'
        first=observe(0,['solid_relation']); fact=first['facts']['solid_relation']
        if fact.get('status') in ('unknown','unsupported'):
            record['capability_gap_observed']=True; record['gap_fact']=fact
            record['stop_reason']='bound_initial_required_solid_relation_unavailable'
            for item in record['schedule'][1:]: item['reason']='not_run_after_first_bound_unknown'
        else:
            assert fact.get('status')=='measured' and fact.get('value') in ('penetrating','not_penetrating')
            record['first_relation_vs_old_expected']=dict(expected='penetrating',observed=fact['value'],matches=fact['value']=='penetrating')
            record['first_probe_distance_fact']='not_requested_by_minimal_probe; penetrating requires no separation distance; if not_penetrating this first-pair distance remains unmeasured publicly'
            record['native_readbacks']=[readback('initial')]
            for ordinal in (1,2): observe(ordinal,['solid_relation','surface_proximity'])
            record['native_readbacks'].append(readback('unchanged_current'))
            for ordinal in (3,4,5): observe(ordinal,['solid_relation','surface_proximity'])
            record['qa_patch']=transaction('rpc_qa_advance',lambda:owner.qa_advance(timeout_s=10))
            record['native_readbacks'].append(readback('changed_current'))
            for ordinal in (6,7,8): observe(ordinal,['solid_relation','surface_proximity'])
            record['stop_reason']='supported_first_probe_bounded_three_states_completed'
    except BaseException as error:
        record['primary_error']=error_info(error);record['stop_reason']='error_not_capability_confirmation'
    finally:
        if stdio is not None:
            try: record['stdio_cleanup']=stdio.close()
            except BaseException as error: record['stdio_cleanup_error']=error_info(error)
        if owner is not None:
            try: record['native_cleanup']=transaction('rpc_close',owner.close,close=True)
            except BaseException as error:
                record['native_cleanup_error']=error_info(error);owner._kill()
            record['owned_process_reaped']=owner.process.poll() is not None;record['owned_exit_code']=owner.process.poll()
            if (OUT/'owned/WORKER_CLOSED.json').exists():record['worker_closed']=json.loads((OUT/'owned/WORKER_CLOSED.json').read_bytes())
        if (OUT/'stdio/BOOTSTRAP_RESULT.json').exists():record['bootstrap']=json.loads((OUT/'stdio/BOOTSTRAP_RESULT.json').read_bytes())
        record['product_socket_count']=socket_count();record['total_RPC_attempts']=record['control_RPC_attempts']+socket_count()
        record['source_drift']=[r['path'] for r in plan['product_manifest'] if sha(ROOT/r['path'])!=r['sha256'] or sha(Path(plan['source_root'])/r['path'])!=r['sha256']]
        record['original_input_hashes_after']={name:sha(FOLDER/'inputs'/name) for name in INPUT_HASHES}
        record['helper_sha256_after']=sha(HELPER)
        record['whole_controller_ns']=time.perf_counter_ns()-begun;record['ended_utc']=datetime.now(timezone.utc).isoformat()
        witness=record.get('bootstrap',{}).get('execution_witness',{}); generation=witness.get('bound_generation') or {}
        native_close=record.get('native_cleanup') or {}; close_response=native_close.get('response') or {}
        record['source_execution_verified']=bool(witness.get('guard_verified') and witness.get('every_loaded_module_has_execution_or_namespace_witness') and generation.get('compatible'))
        record['closure_verified']=bool(record.get('stdio_cleanup',{}).get('exit_code')==0 and record.get('stdio_cleanup',{}).get('process_reaped') and record.get('owned_process_reaped') and record.get('owned_exit_code')==0 and close_response.get('status')=='closed' and native_close.get('error') is None and native_close.get('original_deadline_ns')==plan['deadline_ns'] and close_response.get('deadline_ns')==plan['deadline_ns'])
        record['passed']=bool(record['primary_error'] is None and record['source_execution_verified'] and record['closure_verified'] and not record['source_drift'] and record['total_RPC_attempts']<=16 and record['product_attempts']<=9)
        record['status']=('bound_required_fact_unknown_batch_ended' if record['capability_gap_observed'] else 'supported_first_probe_three_states_recorded') if record['passed'] else 'incomplete_no_replay'
        controls=[json.loads(p.read_bytes()) for p in OUT.glob('rpc_*/METER.json')]
        sockets=record.get('bootstrap',{}).get('sockets',[])
        record['boundary_totals']=dict(control_TX_bytes=sum(r['send_completed_bytes'] for r in controls),control_RX_bytes=sum(r['received_bytes'] for r in controls),
            product_TX_bytes=sum(r['send_completed_bytes'] for r in sockets),product_RX_bytes=sum(r['received_bytes'] for r in sockets),
            stdio_TX_bytes=record.get('stdio_cleanup',{}).get('complete_TX_bytes'),stdio_RX_bytes=record.get('stdio_cleanup',{}).get('complete_RX_bytes'))
        save(OUT/'RESULTS.json',record)
        print(json.dumps(dict(status=record['status'],passed=record['passed'],public_observations=record['product_attempts'],physical_RPC=record['total_RPC_attempts'],result=str(OUT/'RESULTS.json'))))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','run'));parser.add_argument('--source-freeze',type=Path);args=parser.parse_args()
    try: prepare(args) if args.command=='prepare' else run()
    except BaseException as error:
        if not (OUT/'STARTED.json').exists():
            folder=FOLDER/'prepare_failures';folder.mkdir(exist_ok=True);save(folder/(str(time.time_ns())+'.json'),error_info(error))
        raise
