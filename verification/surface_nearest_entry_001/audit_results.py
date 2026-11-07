"""Read-only stdlib audit of the sealed actual wire/evaluation evidence."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = HERE/'qa_prepare/run_01'
load = lambda path: json.loads(Path(path).read_bytes())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
result, plan, freeze = (load(RUN/name) for name in ('RESULTS.json','PLAN.json','FREEZE.json'))
assert result['passed'] and result['source_sha256'] == plan['source_sha256']
assert sha((RUN/'PLAN.json').read_bytes()) == freeze['plan_sha256']
for row in freeze['controllers']:
    assert sha(Path(row['path']).read_bytes()) == row['sha256']
for row in plan['product_manifest']:
    actual = (ROOT/row['path']).read_bytes()
    assert sha(actual) == sha((Path(plan['source_root'])/row['path']).read_bytes()) == row['sha256']
    assert actual == subprocess.check_output(['git','show',plan['candidate_commit']+':'+row['path']],cwd=ROOT)
offline = load(HERE/'offline_run_02/RESULTS.json')
assert offline['passed'] and offline['tests_run'] == 99 and offline['runtime_source_sha256'] == plan['source_sha256']
assert load(HERE/'offline_run_02/EXECUTION_IDENTITY.json')['guard_verify_loaded']
assert not load(HERE/'offline_run_01/RESULTS.json')['passed']
assert load(HERE/'offline_run_01/RESULTS.json')['tests_run'] == 0
base = '497a9dfb88e7ca114bc6706f40eb7e513da82062'
changed = subprocess.check_output(['git','diff','--name-only',base,plan['candidate_commit']],cwd=ROOT,text=True).splitlines()
assert sorted(changed) == sorted('human_eye_plugin/'+name+'.py' for name in
    ('query_policy','live_service','live_spatial_mcp','runtime_identity'))

events = [json.loads(line) for line in (RUN/'owned/WORKER_EVENTS.jsonl').read_text('utf8').splitlines()]
assert [e['sequence'] for e in events] == list(range(1,11))
assert all(e['status']=='completed' and e['terminal_geometry_and_file_checks_passed']
    and e['script_error'] is None and e['render_events_before']==e['render_events_after']==0
    and not e['changed_or_new_PNG_files'] for e in events[:9])
prefix = 'HUMAN_EYE_BLENDER_MCP:'
packets, product_rows, public_rows = [], [], []
for index in (1,2,3):
    folder = RUN/'stdio'/('socket_'+str(index))
    tx, rx = ((folder/name).read_bytes() for name in ('TX.bin','RX.bin'))
    meter = load(folder/'METER.json')
    assert meter['send_completed_bytes']==meter['send_attempted_bytes']==len(tx)
    assert meter['received_bytes']==len(rx)
    request = json.loads(tx)
    assert set(request)=={'type','params'} and request['type']=='execute_code'
    code = request['params']['code']
    tree = ast.parse(code)
    assignment = next(n for n in tree.body if isinstance(n,ast.Assign)
        and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='_request')
    embedded = json.loads(ast.literal_eval(assignment.value.args[0]))
    assert embedded['command']=='capture_nearest_candidates'
    assert embedded['params']['focal_id']==plan['static_object_ids']['M4_Focal']
    assert set(embedded['params'])=={'focal_id','deadline_ns','max_response_bytes'}
    assert embedded['params']['max_response_bytes']==64*1024*1024
    outer = json.loads(rx)
    assert set(outer)=={'status','result'} and outer['status']=='success'
    executed = outer['result']
    assert set(executed)=={'executed','result'} and executed['executed'] is True
    stdout = executed['result']
    assert stdout.startswith(prefix) and stdout.endswith('\n') and stdout.count('\n')==1
    envelope = json.loads(stdout[len(prefix):-1])
    assert envelope['id']==embedded['id'] and envelope['protocol_version']=='1.0'
    packet = envelope['result']
    assert packet['protocol']=='single-read-surface-candidates-v1'
    assert packet['result_kind']=='acquisition_only_not_nearest_result'
    assert packet['capture']['capture_scope']=='surface_nearest_candidates'
    assert packet['binding']['host_source_sha256']==plan['host_sha256']
    assert packet['focal_id']==embedded['params']['focal_id']
    sequence = 3*index-1
    assert events[sequence-1]['script_sha256']==sha(code.encode())
    worker = RUN/'owned'/('call_'+str(sequence))
    assert (worker/'SCRIPT.py').read_text('utf8')==code
    assert (worker/'stdout.txt').read_text('utf8')==stdout
    fixture = load(RUN/'owned'/('fixture_'+str(index))/'FIXTURE.json')
    assert fixture['calls']==fixture['returns']==1 and fixture['restored'] and fixture['finally_disarmed']
    assert fixture['before']==fixture['after']==fixture['after_finally']
    assert not fixture.get('hook_error')
    assert fixture['events'][0]['filename']==str(Path(plan['source_root'])/'human_eye_plugin/blender_host.py')
    native_objects = {r['name']:r for r in fixture['during']}
    far = native_objects['M4_Far_00']['vertices_local']
    assert far[3]==([100.,2.,0.] if index==1 else [.25,.25,.25] if index==2 else [1.,2.,0.])
    if index==3: assert far[4:]==[[1.,3.,0.],[1.,4.,0.]]
    for mesh in packet['capture']['meshes']:
        assert mesh['vertices']==native_objects[mesh['name']]['vertices_world_m']
        assert mesh['faces']==native_objects[mesh['name']]['faces']
    public = result['states'][index-1]['public']
    names = {m['object_id']:m['name'] for m in packet['capture']['meshes']}
    for obj in [public['focal']]+public['best_known_objects']+public['unresolved']:
        assert obj['name']==names[obj['id']]
    assert public['status']==('complete' if index<3 else 'partial')
    assert public['distance_m']==(2. if index==1 else .25 if index==2 else None)
    assert public['best_known_distance_m']==(.25 if index==2 else 2.)
    assert public['nearest_objects'] is None if index==3 else public['nearest_objects']==public['best_known_objects']
    if index==3:
        assert public['unresolved']==[dict(id=plan['static_object_ids']['M4_Far_00'],name='M4_Far_00',reason='surface_degenerate_triangle')]
    else: assert not public['unresolved']
    assert all(key not in public for key in ('excluded','capture','meshes','_exact_distance_sq','routing'))
    packets.append(packet)
    product_rows.append(dict(state=index,tx_bytes=len(tx),rx_bytes=len(rx),native_sequence=sequence,
        packet_json_bytes=len(json.dumps(packet,separators=(',',':')).encode()),host_work=packet['work']))

calls = result['stdio_cleanup']['calls']
assert [r['method'] for r in calls]==['initialize','notifications/initialized','tools/list','tools/call','ping','tools/call','tools/call','tools/call']
tx_total = rx_total = text_total = 0
for row in calls:
    frame = RUN/'mcp_frames'/str(row['sequence']).zfill(2)
    tx = (frame/'TX.bin').read_bytes()
    assert len(tx)==row['tx_bytes']
    tx_total += len(tx)
    if row['notification']: assert not (frame/'RX.bin').exists(); continue
    rx = (frame/'RX.bin').read_bytes()
    assert len(rx)==row['rx_bytes']
    rx_total += len(rx)
    response = json.loads(rx)
    assert response['id']==row['sequence']
    if row['sequence']==4: assert response.get('result',{}).get('isError') or 'error' in response
    if row['sequence']>=6:
        content=response['result']
        assert set(content)=={'content','isError'} and content['isError'] is False
        assert len(content['content'])==1 and content['content'][0]['type']=='text'
        text=content['content'][0]['text']; text_total += len(text.encode())
        public=json.loads(text); assert public==result['states'][row['sequence']-6]['public']
        public_rows.append(dict(state=row['sequence']-5,frame_RX_bytes=len(rx),text_utf8_bytes=len(text.encode()),wall_ns=row['elapsed_ns']))
assert tx_total==result['boundary_totals']['complete_stdio_TX_bytes']
assert rx_total==result['boundary_totals']['complete_stdio_RX_bytes']
assert not (RUN/'STDIO_EXTRA_RX.bin').read_bytes()
controls=[]
for folder in sorted(RUN.glob('rpc_*')):
    tx,rx=((folder/name).read_bytes() for name in ('TX.bin','RX.bin'))
    meter=load(folder/'METER.json')
    assert len(tx)==meter['send_attempted_bytes']==meter['send_completed_bytes']
    assert len(rx)==meter['received_bytes']
    controls.append(dict(name=folder.name,tx_bytes=len(tx),rx_bytes=len(rx),wall_ns=meter['elapsed_ns']))
assert len(controls)==7
assert sum(r['tx_bytes'] for r in controls)==result['boundary_totals']['native_control_TX_completed_bytes']
assert sum(r['rx_bytes'] for r in controls)==result['boundary_totals']['native_control_RX_bytes']
counts=Counter(r['name'] for r in result['bootstrap']['calls'])
assert [counts[n] for n in ('capture_nearest_candidates','surface_nearest_result','_surface_pair_measurement','measure_surface_proximity','_nearest','_rank_surface_results')]==[3,3,5,3,2,3]
diagnostics=[r['diagnostics'] for r in result['bootstrap']['calls'] if r['name']=='surface_nearest_result']
assert sum(d['cache_hits'] for d in diagnostics)==2
state=load(RUN/'state.json')['runtime']
assert state['sessions']==[] and state['router']['scene_memory']['frames']==[]
closed=load(RUN/'owned/WORKER_CLOSED.json')
assert closed['poisoned'] is False and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint']==result['ready']['initial_fingerprint']
assert result['owned_process_reaped'] and result['owned_exit_code']==0 and result['stdio_cleanup']['process_reaped'] and result['stdio_cleanup']['exit_code']==0
assert sha(Path(plan['asset']).read_bytes())==sha((RUN/'owned/input.blend').read_bytes())==plan['asset_sha256']
assert not list(RUN.rglob('*.png'))
audit=dict(passed=True,source_sha256=plan['source_sha256'],candidate_commit=plan['candidate_commit'],product_changes=changed,
    offline_passed_methods=99,initial_import_failure_methods=0,Blender_sessions=1,stdio_processes=1,native_RPC=10,
    product_capture_count=3,complete_packet_return_on_real_socket=True,packet_file_input=False,
    product_socket_rows=product_rows,control_rows=controls,stdio_rows=public_rows,boundary_totals=result['boundary_totals'],
    native_total_TX_bytes=sum(r['tx_bytes'] for r in controls+product_rows),native_total_RX_bytes=sum(r['rx_bytes'] for r in controls+product_rows),
    selected_public_text_utf8_bytes=text_total,product_counts=dict(counts),cache_hits=2,
    product_constructed_meshes=sum(p['work']['expanded_objects'] for p in packets),
    product_constructed_vertices=sum(p['work']['expanded_vertices'] for p in packets),
    product_constructed_faces=sum(p['work']['expanded_faces'] for p in packets),
    zero_images=True,no_full_scene_history=True,cleanup_verified=True,
    oracle='independent fixture coordinates: Near x=2; Far min x=.25 with focal-plane projection inside triangle; collinear Far x=1 at y=2..4 is unsupported and can beat Near (sqrt(2)<2)',
    model_consumers=0,external_API_calls=0,tokens_and_money='not_measured',formal_performance_AB=False)
(HERE/'AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(passed=True,native_RPC=10,native_TX=audit['native_total_TX_bytes'],native_RX=audit['native_total_RX_bytes'],stdio_TX=tx_total,stdio_RX=rx_total,text_bytes=text_total)))
