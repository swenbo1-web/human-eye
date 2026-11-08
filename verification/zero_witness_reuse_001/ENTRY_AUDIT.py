"""Audit finished complex-entry raw evidence only; no product import or RPC.

Preparation may AST-parse this file. main requires a terminal controller result.
It never enumerates/queries/signals processes and never computes solid truth.
"""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
QA = None
OUTER = None
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())
SOURCE_SHA = None
TOKEN = 'ZERO-WITNESS-REUSE-001-20261108T152216Z-ONLY'


def canon(value, *, ascii=False):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=ascii, allow_nan=False).encode('utf8')


def git_blobs(revision, paths):
    raw = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT,
        input=b''.join((revision + ':' + path + '\n').encode() for path in paths))
    offset = 0
    result = {}
    for path in paths:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        assert len(header) == 3 and header[1] == b'blob', path
        size = int(header[2]); start = end + 1
        result[path] = raw[start:start + size]
        assert raw[start + size:start + size + 1] == b'\n'
        offset = start + size + 1
    assert offset == len(raw)
    return result


def literal_request(code):
    for node in ast.parse(code).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_request' for t in node.targets):
            return json.loads(ast.literal_eval(node.value.args[0]))
    return None


def capture_from_response(response):
    text = response.get('result', {}).get('result')
    if type(text) is not str:
        return None, None
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        return None, None
    envelope = json.loads(lines[0][len(prefix):])
    packet = envelope.get('result')
    scene = packet.get('capture') if type(packet) is dict and 'capture' in packet else packet
    return envelope, scene


def expected_world(obj, scale):
    matrix = obj['matrix_world']
    return [[(sum(matrix[r][k] * vertex[k] for k in range(3)) + matrix[r][3]) * scale
             for r in range(3)] for vertex in obj['vertices_local']]


def oriented_triangles(faces):
    assert all(len(row)==3 and len(set(row))==3 for row in faces), 'fixed assembly original faces are triangles'
    return Counter(min(tuple(row[k:]+row[:k]) for k in range(3)) for row in faces)


def audit_arm(arm):
    global QA, OUTER
    QA=OUT/('qa_'+arm)
    OUTER=OUT/('qa_invocation_'+arm)
    begun = time.perf_counter_ns()
    result = load(QA / 'RESULTS.json')
    assert result.get('ended_utc') is not None, 'terminal-only audit'
    global SOURCE_SHA
    fixed = load(OUT / ('SOURCE_FREEZE_'+arm.upper()+'.json'))
    SOURCE_SHA = fixed['source_sha256']
    plan = load(QA / 'PLAN.json')
    runtime = load(QA / 'RUNTIME_PLAN.json')
    bootstrap = load(QA / 'stdio/BOOTSTRAP_RESULT.json')
    outer = load(OUTER / 'RESULT.json')
    raw_paths = sorted(path for base in (QA, OUTER) for path in base.rglob('*') if path.is_file())
    before = {p: p.read_bytes() for p in raw_paths}
    checks = []

    def expect(name, condition, **evidence):
        checks.append(dict(name=name, passed=bool(condition), **evidence))

    prepared = load(QA/'FREEZE.json')
    expect('frozen_plan', SHA((QA/'PLAN.json').read_bytes())==prepared['plan_sha256']==outer['plan_sha256'])
    for row in prepared['controllers']:
        expect('frozen_input:'+row['path'], SHA(Path(row['path']).read_bytes())==row['sha256'])
    adaptation = None
    if (OUT/'prepare_failures/ADAPTATION_RECORD.json').exists():
        adaptation = load(OUT/'prepare_failures/ADAPTATION_RECORD.json')
    truth = load(Path(plan['truth_path']))
    expect('fixed_independent_truth', SHA((Path(plan['truth_path'])).read_bytes())=='d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff'
        and SHA(Path(plan['truth_path']).read_bytes())==plan['truth_sha256'])
    manifest = sorted(fixed['product_manifest'], key=lambda r: r['path'])
    paths = [r['path'] for r in manifest]
    blobs = git_blobs(fixed['candidate_commit'], paths)
    sources = []
    for row in manifest:
        disk = (Path(fixed['source_root']) / row['path']).read_bytes()
        frozen = (Path(fixed['source_root']) / row['path']).read_bytes()
        sources.append(dict(path=row['path'], sha256=SHA(disk), matches=SHA(disk)==SHA(frozen)==SHA(blobs[row['path']])==row['sha256']))
    expect('exact_131_source_bytes', len(sources)==len(manifest) and len(sources)==131 and all(r['matches'] for r in sources))
    tree = ast.parse(blobs['human_eye_plugin/runtime_identity.py'])
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    digest = SHA(canon(dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest), ascii=True))
    expect('canonical_source', digest==SOURCE_SHA==fixed['source_sha256']==plan['source_sha256']==result['source_sha256']==bootstrap['source_sha256'])
    original_rows = []
    for row in fixed['originals']:
        original = Path(row['source_path']).read_bytes(); copy = Path(row['copy_path']).read_bytes()
        item = dict(path=row['source_path'], sha256=SHA(original), copy_sha256=SHA(copy), expected=row['sha256'])
        original_rows.append(item)
        expect('original_and_copy:'+Path(row['copy_path']).name, original==copy and SHA(copy)==row['sha256'])
    expect('owned_asset_exact', SHA((QA/'owned/input.blend').read_bytes())=='a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb')
    snapshots = load(Path(plan['snapshots']))
    frames = []; public = []
    for folder in sorted((QA/'mcp_frames').iterdir()):
        tx = (folder/'TX.bin').read_bytes(); request = json.loads(tx)
        rx = (folder/'RX.bin').read_bytes() if (folder/'RX.bin').exists() else None
        response = json.loads(rx) if rx else None
        meter = load(folder/'METER.json')
        expect('MCP_bytes:'+folder.name, len(tx)==meter['tx_bytes'] and (rx is None or len(rx)==meter['rx_bytes']))
        frame = dict(method=request['method'], request=request, TX_bytes=len(tx), RX_bytes=None if rx is None else len(rx), elapsed_ns=meter['elapsed_ns'])
        if request['method']=='tools/call':
            value = None
            if type(response) is dict and type(response.get('result')) is dict:
                blocks = response['result'].get('content', [])
                if len(blocks)==1 and blocks[0].get('type')=='text':
                    value = json.loads(blocks[0]['text'])
            public.append(dict(request=request, response=response, value=value))
        frames.append(frame)
    expect('public_denominator', 1<=len(public)<=9)
    first_args = public[0]['request']['params']['arguments']
    expect('first_legal_required_task', public[0]['request']['params']['name']=='human_eye_scene_observe'
        and first_args['query']['mode']=='task' and first_args['query']['objects']==[{'name':'Object_01'},{'name':'Object_03'}]
        and first_args['query']['requested_facts']==['closed_solid_relation','surface_proximity'] and first_args['include_image'] is False)
    events = [json.loads(line) for line in (QA/'owned/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    used_execution_sequences=set()
    captures = []; sockets = sorted((QA/'stdio').glob('socket_*'))
    for index, folder in enumerate(sockets):
        tx = (folder/'TX.bin').read_bytes(); rx = (folder/'RX.bin').read_bytes()
        request, response = json.loads(tx), json.loads(rx); meter = load(folder/'METER.json')
        code = request['params']['code'].encode('utf8'); host_request = literal_request(code)
        expect('frozen_host_execution:'+folder.name, plan['host_sha256'] in code.decode('utf8')
            and 'exec(compile(_source_bytes' in code.decode('utf8'))
        matches = sorted([e for e in events if e.get('script_sha256')==SHA(code) and e['sequence'] not in used_execution_sequences], key=lambda e:e['sequence'])
        matches = matches[:1]
        if matches: used_execution_sequences.add(matches[0]['sequence'])
        expect('wire_execution_event:'+folder.name, request['type']=='execute_code' and len(matches)==1
            and matches[0]['status']=='completed' and matches[0]['script_error'] is None
            and matches[0]['terminal_geometry_and_file_checks_passed'] is True)
        event = matches[0]
        call = QA/'owned'/('call_'+str(event['sequence']))
        script = (call/'SCRIPT.py').read_bytes()
        logical_stdout = response['result']['result'].encode('utf8')
        expect('SCRIPT_storage:'+folder.name, script==code.replace(b'\n',b'\r\n'), logical_bytes=len(code),disk_bytes=len(script),logical_sha256=SHA(code),disk_sha256=SHA(script))
        expect('stdout_storage:'+folder.name, (call/'stdout.txt').read_bytes()==logical_stdout.replace(b'\n',b'\r\n') and event['stdout_bytes']==len(logical_stdout))
        expect('socket_bytes:'+folder.name, len(tx)==meter['send_attempted_bytes']==meter['send_completed_bytes'] and len(rx)==meter['received_bytes'])
        envelope, scene = capture_from_response(response)
        expect('actual_selected_capture:'+folder.name, host_request['command']=='capture_task' and envelope['id']==host_request['id']
            and scene.get('capture_scope')=='selected_objects' and scene.get('unit')=='m' and scene.get('coordinate_frame')=='world' and scene.get('source')=='blender')
        # The fixed controller labels states. Only the actual labels, never a
        # presumed successful update, choose the archived expected geometry.
        row = result.get('public_calls', [])[index] if index<len(result.get('public_calls', [])) else {}
        label = str(row.get('state', row.get('label', 'initial')))
        state = 'changed' if 'changed' in label and 'unchanged' not in label else 'initial'
        expected = {obj['name']: obj for obj in snapshots[state]['objects']}
        actual = {obj['name']: obj for obj in scene['meshes']}
        selectors = host_request['params']['selectors']; names = [r['name'] for r in selectors]
        expect('selected_names:'+folder.name, set(actual)==set(names) and len(actual)==2 and names[0]=='Object_01')
        geometry = []
        for name, obj in actual.items():
            old = expected[name]; computed = expected_world(old, snapshots[state]['unit_scale_m'])
            geometry.append(dict(name=name, vertices=len(obj['vertices']),faces=len(obj['faces']),world_sha256=SHA(canon(obj['vertices'])),expected_world_sha256=SHA(canon(computed)),
                exact_face_list=obj['faces']==old['faces'],oriented_triangle_multiset_match=oriented_triangles(obj['faces'])==oriented_triangles(old['faces']),
                matches=obj['vertices']==computed==old['world_vertices'] and oriented_triangles(obj['faces'])==oriented_triangles(old['faces'])))
        expect('original_geometry:'+folder.name, all(r['matches'] for r in geometry), state=state, objects=geometry)
        value = public[index]['value']; binding = value.get('binding', {}) if type(value) is dict else {}
        selection = scene['task_selection']
        expect('binding_revision_objects_source:'+folder.name, value.get('result_kind')=='task_query'
            and value.get('unit')=='m' and value.get('coordinate_frame')=='world' and value.get('execution_authority') is False
            and binding.get('runtime_source_sha256')==SOURCE_SHA and binding.get('scene_revision')==scene['revision']
            and binding.get('capture_scope')=='selected_objects' and binding.get('candidate_count')==selection['candidate_count']==4
            and binding.get('selected_count')==len(actual)==2 and selection['pair_reason'] is None
            and binding.get('objects')==selection['bindings'])
        expect('raw_scene_canonical_public_fingerprint:'+folder.name, binding.get('scene_fingerprint')==SHA(canon(scene)),
            raw_scene_canonical_sha256=SHA(canon(scene)),public_fingerprint=binding.get('scene_fingerprint'))
        captures.append(dict(label=label,state=state,host_request=host_request,public=value,geometry=geometry,raw_scene_sha256=SHA(canon(scene)),TX_bytes=len(tx),RX_bytes=len(rx)))
    expect('one_capture_each_observation', len(sockets)==len(public))
    fact = public[0]['value'].get('facts', {}).get('closed_solid_relation', {})
    first_bound = all(r['passed'] for r in checks if r['name'].startswith(('first_legal','actual_selected','selected_names','original_geometry','binding_revision','raw_scene_canonical')))
    classification = ('valid_bound_unknown' if first_bound and fact.get('status')=='unknown'
        else 'supported' if first_bound and fact.get('status')=='measured' else 'error_or_unverified')
    if result.get('capability_gap_observed'):
        expect('stop_after_bound_unknown', len(public)>=1 and len(sockets)==len(public) and result.get('capability_gap_observed') is True)
        expect('remaining_schedule_not_run', len(result['schedule'])==9 and all(r['status']=='not_run' for r in result['schedule'][len(public):]))
    config, ready, closed = load(QA/'owned/CONFIG.json'), load(QA/'owned/READY.json'), load(QA/'owned/WORKER_CLOSED.json')
    started = load(QA/'STARTED.json')
    expect('original_deadline', config['deadline_ns']==ready['deadline_ns']==closed['original_deadline_ns']==result['original_deadline_ns']==runtime['deadline_ns'])
    expect('fixed_session_max_600_seconds', runtime['deadline_ns']-started['started_ns']==600_000_000_000)
    expect('fixed_window_and_implementation_limit', started['window']['token']==TOKEN
        and started['window']['max_sessions']==2 and started['window']['max_RPC']==32 and started['window']['max_public_observations']==18
        and datetime.fromisoformat(result['ended_utc'])<datetime.fromisoformat(started['window']['expires_utc'])
        and datetime.fromisoformat(result['ended_utc']).timestamp()<fixed['implementation_deadline_epoch_seconds'])
    expect('helper_unchanged', SHA(Path(plan['helper']).read_bytes())==plan['helper_sha256']==ready['helper_sha256'])
    controls = []
    for folder in sorted(QA.glob('rpc_*')):
        if not (folder/'TX.bin').exists(): continue
        tx=(folder/'TX.bin').read_bytes(); rx=(folder/'RX.bin').read_bytes() if (folder/'RX.bin').exists() else b''
        controls.append(dict(label=folder.name,request=json.loads(tx),response=json.loads(rx) if rx else None,TX_bytes=len(tx),RX_bytes=len(rx)))
    native_readbacks=[]
    for row in controls:
        label=row['label']; request=row['request']; response=row['response']
        if not label.startswith('rpc_readback_'): continue
        state=label[len('rpc_readback_'):]; reference=snapshots['changed' if state=='changed_current' else 'initial']
        code=request['params']['code'].encode('utf8')
        matched=[event for event in events if event.get('script_sha256')==SHA(code)]
        expect('native_readback_execution:'+state, request['type']=='execute_code' and '# closed_solid_qa_state:'+state in code.decode('utf8') and len(matched)==1 and matched[0]['status']=='completed'
            and matched[0].get('terminal_geometry_and_file_checks_passed') is True and response.get('status')=='success')
        prefix,text=response['result']['result'].split('COMPLEX_NATIVE_READBACK:',1)
        actual=json.loads(text); by_name={obj['name']:obj for obj in actual['objects']}
        expected={obj['name']:obj for obj in reference['objects']}
        expect('native_readback_original_geometry:'+state, not prefix.strip() and actual['unit_scale_m']==reference['unit_scale_m']
            and set(by_name)==set(expected) and all(all(by_name[name][key]==obj[key] for key in ('vertices_local','matrix_world','faces'))
            and by_name[name]['world_vertices']==expected_world(obj,reference['unit_scale_m']) for name,obj in expected.items()))
        event=matched[0]; call=QA/'owned'/('call_'+str(event['sequence']))
        logical=response['result']['result'].encode('utf8')
        expect('native_readback_storage:'+state, (call/'SCRIPT.py').read_bytes()==code.replace(b'\n',b'\r\n')
            and (call/'stdout.txt').read_bytes()==logical.replace(b'\n',b'\r\n') and event['stdout_bytes']==len(logical))
        native_readbacks.append(dict(state=state,current_geometry_exact=True,objects=len(by_name),worker_sequence=event['sequence']))
    physical = len(sockets)+len(controls)
    expect('physical_caps', physical<=16 and result['total_RPC_attempts']==physical)
    expect('source_guard', bootstrap['execution_witness']['guard_verified'] is True
        and bootstrap['execution_witness']['every_loaded_module_has_execution_or_namespace_witness'] is True
        and bootstrap['execution_witness']['bound_generation']['compatible'] is True
        and bootstrap['execution_witness']['bound_generation']['loaded_build_id']=='sha256:'+SOURCE_SHA)
    expect('no_packet_substitution', bootstrap.get('original_request_unchanged') is True and bootstrap.get('no_packet_file_input') is True)
    expect('outer_owner', outer['exit_code']==(0 if result.get('passed') is True else 1) and outer['process_reaped'] is True, actual_exit_code=outer['exit_code'])
    stdio=result.get('stdio_cleanup', {}); native=result.get('native_cleanup', {})
    expect('stdio_owner',stdio.get('exit_code')==0 and stdio.get('process_reaped') is True)
    expect('native_owner',native.get('exit_code')==0 and native.get('process_reaped') is True and (native.get('response') or {}).get('status')=='closed')
    patch_controls=[row for row in controls if row['request'].get('type')=='qa_advance']
    patch_applied=closed.get('qa_patch_applied') is True
    expect('native_close_accepted_geometry', native.get('source_file_unchanged') is True and native.get('protected_files_unchanged') is True
        and closed['initial_geometry_fingerprint']==ready['initial_fingerprint'] and closed['poisoned'] is False
        and closed['final_geometry_fingerprint']==closed['accepted_geometry_fingerprint'])
    expect('patch_exactly_once_or_not_run', len(patch_controls)==int(patch_applied))
    if patch_applied:
        advance=load(QA/'owned/QA_ADVANCE_RECEIPT.json')
        update=advance['response']['result']
        expect('original_patch_binding', update['patch_sha256']==plan['patch_sha256'] and update['stage']==1
            and update['original_fingerprint']==ready['initial_fingerprint']
            and update['after_fingerprint']==closed['accepted_geometry_fingerprint']
            and advance['original_deadline_ns']==runtime['deadline_ns'])
    else:
        expect('unpatched_geometry_unchanged', closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'])
    contract=[]
    state_map={'initial':'initial','unchanged_current':'unchanged','changed_current':'changed'}
    for index,row in enumerate(public):
        result_row=result['public_calls'][index]; state=result_row['state']; candidate=result_row['candidate']
        value=row['value']; facts=value.get('facts',{}); closed_fact=facts.get('closed_solid_relation',{})
        relation=closed_fact.get('value'); known=closed_fact.get('status')=='measured'
        if type(relation) is dict: relation=relation.get('relation')
        expected=truth['states'][state_map[state]]['probes'][candidate]
        surface=facts.get('surface_proximity',{}); distance=(surface.get('value') or {}).get('distance_m')
        interval_ok=None
        if known and relation=='separated' and expected['relation']=='separated':
            low,high=expected['distance_interval_m']
            interval_ok=type(distance) in (int,float) and math.isfinite(distance) and Decimal(str(low))<=Decimal(str(distance))<=Decimal(str(high))
        match=known and relation==expected['relation'] and interval_ok is not False
        expect('zero_tolerance_fact_contract:'+str(index+1), closed_fact.get('relation_tolerance_m')==0.0
            and type(closed_fact.get('geometry_scope')) is str and closed_fact.get('value') is None if not known else
            closed_fact.get('relation_tolerance_m')==0.0 and type(closed_fact.get('geometry_scope')) is str and relation in ('separated','touching','penetrating'))
        contract.append(dict(ordinal=index+1,state=state,candidate=candidate,known=known,relation=relation,expected_relation=expected['relation'],
            surface_distance_m=distance,independent_distance_interval=expected.get('distance_interval_m'),
            inside_independent_interval=interval_ok,matches_original_contract=bool(match)))
    aggregates=[]
    for state in ('initial','unchanged_current','changed_current'):
        rows=[row for row in contract if row['state']==state]; expected=truth['states'][state_map[state]]
        if len(rows)!=3 or not all(row['known'] for row in rows):
            aggregates.append(dict(state=state,complete=False,matches_original_contract=False));continue
        penetrating=sorted(row['candidate'] for row in rows if row['relation']=='penetrating')
        expected_penetrating=sorted(name for name,pair in expected['probes'].items() if pair['relation']=='penetrating')
        separated=[row for row in rows if row['relation']=='separated' and type(row['surface_distance_m']) in (int,float)]
        best=min((row['surface_distance_m'] for row in separated),default=None)
        nearest=sorted(row['candidate'] for row in separated if row['surface_distance_m']==best)
        aggregates.append(dict(state=state,complete=True,penetrating=penetrating,expected_penetrating=expected_penetrating,
            nearest_separated=nearest,expected_nearest_separated=expected['nearest_separated_probe'],
            matches_original_contract=penetrating==expected_penetrating and nearest==[expected['nearest_separated_probe']]))
    profile_pairs=[row for row in bootstrap.get('calls',[]) if row.get('name')=='_closed_solid_pair_measurement']
    kernels=[row for row in bootstrap.get('calls',[]) if row.get('name')=='classify_closed_solids']
    costs=[]
    for i,row in enumerate(result.get('public_calls',[])):
        pair=profile_pairs[i] if len(profile_pairs)==len(public) else None
        kernel_rows=[] if pair is None else [entry for entry in kernels if pair['started_ns']<=entry['started_ns']<=pair['started_ns']+pair.get('elapsed_ns',0)]
        meter=load(QA/('stdio/socket_'+str(i+1))/'METER.json')
        costs.append(dict(ordinal=i+1,state=row['state'],candidate=row['candidate'],public_observation_ns=row.get('elapsed_ns'),
            acquisition_socket_ns=None if 'ended_ns' not in meter else meter['ended_ns']-meter['started_ns'],
            closed_pair_elapsed_ns=None if pair is None else pair.get('elapsed_ns'),closed_pair_diagnostics=None if pair is None else pair.get('diagnostics'),
            observed_kernel_calls=None if pair is None else len(kernel_rows),observed_kernel_work=[entry.get('work') for entry in kernel_rows]))
    if result.get('capability_gap_observed'):
        last_sequence=max(event['sequence'] for event in events if event.get('script_sha256')==SHA(json.loads((sockets[-1]/'TX.bin').read_bytes())['params']['code'].encode('utf8')))
        following=[event for event in events if event['sequence']>last_sequence]
        expect('no_action_after_necessary_unknown_except_close', len(following)==1 and following[0]['status']=='unknown' and 'script_sha256' not in following[0])
    expect('raw_files_unchanged', all(path.read_bytes()==raw for path, raw in before.items()))
    payload=dict(cycle_id='ZERO-WITNESS-REUSE-001',arm=arm,audited_utc=datetime.now(timezone.utc).isoformat(),passed=all(r['passed'] for r in checks),
        checks=checks,check_count=len(checks),check_failures=[r for r in checks if not r['passed']],source_sha256=digest,source_checks=sources,
        original_bytes=original_rows,first_probe_classification=classification,first_closed_solid_fact=fact,public_observation_count=len(public),physical_RPC=physical,
        MCP_frames=frames,captures=captures,controls=controls,source_guard=bootstrap['execution_witness'],worker_events=events,
        native_readbacks=native_readbacks,original_contract=dict(complete=len(contract)==9 and all(x['known'] for x in contract),
            passed=len(contract)==9 and all(x['matches_original_contract'] for x in contract) and all(x['matches_original_contract'] for x in aggregates),
            observations=contract,aggregates=aggregates),cold_unchanged_changed_costs=costs,
        profile_scope='two added function targets in copied bootstrap; counters/timings include real instrumentation overhead; no model benefit claim',
        owner_receipts=dict(outer=outer,stdio=stdio,native=native),controller_self_PID=result.get('controller_pid'),
        preparation_adaptation=adaptation,original_schedule=result['schedule'],
        raw_files=[dict(path=str(p.relative_to(OUT)),bytes=len(raw),sha256=SHA(raw)) for p,raw in before.items()],
        boundary_totals=result.get('boundary_totals'),whole_outer_ns=outer['wall_ns'],whole_controller_ns=result.get('whole_controller_ns'),
        limitation='No process queries; a Popen owner receipt is not invented for a different controller self PID. Worker unknown events remain unknown. No product kernel is executed by this audit; independent sealed truth is compared separately from structural source/entry/closure validity.',
        additional_product_imports=0,additional_Blender_sessions=0,additional_RPC=0,additional_models=0,additional_PID_queries=0,audit_elapsed_ns=time.perf_counter_ns()-begun)
    return payload


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def segment_distance_sq(p,a,b):
    d=sub(b,a); length=dot(d,d)
    t=max(0.,min(1.,dot(sub(p,a),d)/length)) if length else 0.
    q=tuple(x+t*y for x,y in zip(a,d))
    return dot(sub(p,q),sub(p,q))


def triangle_distance_sq(p,a,b,c):
    # Independent Euclidean projection plus closed edge distances; no product code.
    u,v=sub(b,a),sub(c,a); n=cross(u,v); nn=dot(n,n)
    best=min(segment_distance_sq(p,a,b),segment_distance_sq(p,b,c),segment_distance_sq(p,c,a))
    if nn:
        w=sub(p,a); height=dot(w,n)/nn
        q=tuple(x-height*y for x,y in zip(w,n))
        uu,uv,vv,qu,qv=dot(u,u),dot(u,v),dot(v,v),dot(q,u),dot(q,v)
        det=uu*vv-uv*uv
        if det:
            s,t=(qu*vv-qv*uv)/det,(qv*uu-qu*uv)/det
            if s>=0 and t>=0 and s+t<=1:
                best=min(best,dot(w,n)**2/nn)
    return best


def aabb(vertices):
    return [[min(p[k] for p in vertices),max(p[k] for p in vertices)] for k in range(3)]


def extra_checks(payload):
    import struct
    arm=payload['arm']; qa=OUT/('qa_'+arm)
    plan=load(qa/'PLAN.json'); snapshots=load(plan['snapshots'])
    checks=payload['checks']
    def expect(name,condition,**evidence):
        checks.append(dict(name=name,passed=bool(condition),**evidence))
    expect('exact_arm_denominators',payload['public_observation_count']==9 and payload['physical_RPC']==14
        and len(payload['native_readbacks'])==3 and payload['original_contract']['passed'] is True)
    public_frames=[f for f in payload['MCP_frames'] if f['method']=='tools/call']
    for i,frame in enumerate(public_frames):
        request=frame['request']; args=request['params']['arguments']; query=args['query']
        names=[r['name'] for r in payload['captures'][i]['host_request']['params']['selectors']]
        expect('every_public_request:'+str(i+1),request['params']['name']=='human_eye_scene_observe'
            and args['include_image'] is False and query['mode']=='task'
            and query['objects']==[{'name':n} for n in names]
            and query['requested_facts']==['closed_solid_relation','surface_proximity'])
    for folder in sorted((qa/'mcp_frames').iterdir()):
        request=load(folder/'TX.bin')
        if not (folder/'RX.bin').exists():
            expect('notification_has_no_response:'+folder.name,'id' not in request and request['method']=='notifications/initialized')
            continue
        response=load(folder/'RX.bin')
        expect('public_response_id:'+folder.name,request.get('id')==response.get('id') and 'error' not in response)
    expect('expected_fixed_source',payload['source_sha256']=={
        'baseline':'1545da06b415864cf3f666f3a56432e91689d1a0565ea8589a19e3ecfff2b459',
        'candidate':'ec3ac8c9dd83137e1d6cb5371fe4c2bc15ac56d34aafcb6933e8f76c07e897ae'}[arm]
        and plan['candidate_commit']=={'baseline':'b60dd327e3926a06b73d77b37be7b63c50a3939a',
        'candidate':'c08d882b030ad08390fd4b3e28c068dd5ea6251d'}[arm])
    if arm=='candidate':
        expect('candidate_current_disk_exact',all(SHA((ROOT/row['path']).read_bytes())==row['sha256'] for row in payload['source_checks']))
    initial={o['name']:o for o in snapshots['initial']['objects']}
    changed={o['name']:o for o in snapshots['changed']['objects']}
    patch=load(plan['patch']); edits=[]
    for name,a in initial.items():
        b=changed[name]
        differences=[i for i,(x,y) in enumerate(zip(a['vertices_local'],b['vertices_local'])) if x!=y]
        edits.append(dict(name=name,indices=differences,aabb_initial=aabb(expected_world(a,snapshots['initial']['unit_scale_m'])),
            aabb_changed=aabb(expected_world(b,snapshots['changed']['unit_scale_m']))))
        expect('patch_static_invariants:'+name,a['matrix_world']==b['matrix_world'] and a['faces']==b['faces']
            and len(a['vertices_local'])==len(b['vertices_local']) and edits[-1]['aabb_initial']==edits[-1]['aabb_changed'])
        expect('patch_only_four_original_vertices:'+name,differences==([r['index'] for r in patch['vertices']] if name==patch['target_name'] else []))
    for row in patch['vertices']:
        rounded=[struct.unpack('f',struct.pack('f',x))[0] for x in row['co']]
        expect('patch_float32_coordinate:'+str(row['index']),changed[patch['target_name']]['vertices_local'][row['index']]==rounded)
    payload['independent_patch_checks']=edits
    witnesses=[]
    for capture in payload['captures']:
        value=capture['public']; facts=value['facts']; surface=facts['surface_proximity']; measurement=surface['value']
        names=[r['name'] for r in capture['host_request']['params']['selectors']]
        ref=changed if capture['state']=='changed' else initial
        pair=measurement['nearest_witness']; distance=measurement['distance_m']; rows=[]
        for name,point in zip(names,(pair['a'],pair['b'])):
            obj=ref[name]; vertices=expected_world(obj,snapshots[capture['state']]['unit_scale_m'])
            distances=[triangle_distance_sq(point,*(vertices[i] for i in face)) for face in obj['faces']]
            ordinal=min(range(len(distances)),key=distances.__getitem__)
            rows.append(dict(name=name,point=point,minimum_surface_distance_m=math.sqrt(max(0.,distances[ordinal])),triangle_ordinal=ordinal))
        expect('independent_original_witness:'+str(len(witnesses)+1),surface['status']=='measured'
            and surface.get('witness_status')=='measured' and all(r['minimum_surface_distance_m']<=1e-9 for r in rows)
            and abs(math.dist(pair['a'],pair['b'])-distance)<=1e-9,objects=rows)
        if distance==0:
            expect('zero_distance_direction:'+str(len(witnesses)+1),surface.get('direction_status')=='not_applicable'
                and pair['direction_a_to_b'] is None and surface.get('direction_reason')=='undefined_zero_distance')
        witnesses.append(dict(state=capture['label'],distance_m=distance,objects=rows))
    payload['independent_witnesses']=witnesses
    events=payload['worker_events']; unknown=[e for e in events if e['status']=='unknown']
    expect('complete_worker_denominator_no_retry',len(events)==14 and [e['sequence'] for e in events]==list(range(1,15))
        and len(unknown)==1 and unknown[0]['sequence']==14 and 'script_sha256' not in unknown[0]
        and all(e['status']==('qa_patch_applied' if e['sequence']==9 else 'completed') for e in events[:-1])
        and events[8].get('vertices_written')==4 and events[8].get('patch_sha256')==plan['patch_sha256'])
    expect('worker_no_render_or_PNG',all(e.get('render_events_before')==0 and e.get('render_events_after',0)==0
        and e.get('changed_or_new_PNG_files',[])==[] for e in events))
    expect('worker_before_original_deadline',all(e['started_ns']+e['elapsed_ns']<=load(qa/'RUNTIME_PLAN.json')['deadline_ns'] for e in events))
    expect('outer_no_retry',payload['owner_receipts']['outer']['retries']==0)
    payload['controller_self_PID_is_owned_Popen_PID']=(payload['controller_self_PID']==payload['owner_receipts']['outer']['pid'])
    payload['honest_unknown_events']=unknown
    payload['check_count']=len(checks);payload['check_failures']=[r for r in checks if not r['passed']]
    payload['passed']=not payload['check_failures']
    return payload


def main():
    import traceback,sys
    assert not (OUT/'ENTRY_AUDIT.json').exists(),'preserve every audit attempt'
    start=time.perf_counter_ns(); script_sha=SHA(Path(__file__).read_bytes())
    try:
        arms=[extra_checks(audit_arm(arm)) for arm in ('baseline','candidate')]
        seal=load(OUT/'RAW_FREEZE.json')
        sealed=[dict(path=row['path'],passed=(len((ROOT/row['path']).read_bytes())==row['bytes']
            and SHA((ROOT/row['path']).read_bytes())==row['sha256'])) for row in seal['files']]
        raw_ok=seal['file_count']==len(sealed)==461 and all(r['passed'] for r in sealed)
        payload=dict(cycle_id='ZERO-WITNESS-REUSE-001',passed=all(a['passed'] for a in arms) and raw_ok,
            audited_utc=datetime.now(timezone.utc).isoformat(),arms=arms,script_sha256=script_sha,
            public_observations=sum(a['public_observation_count'] for a in arms),physical_RPC=sum(a['physical_RPC'] for a in arms),
            additional_product_imports=0,additional_Blender_sessions=0,additional_RPC=0,additional_models=0,
            additional_PID_queries=0,audit_elapsed_ns=time.perf_counter_ns()-start,
            raw_freeze_sha256=SHA((OUT/'RAW_FREEZE.json').read_bytes()),sealed_raw_file_count=len(sealed),sealed_raw_unchanged=raw_ok,
            sealed_raw_checks=sealed,audit_attempts_preserved=['ENTRY_AUDIT_ATTEMPT_01.py','ENTRY_AUDIT_ATTEMPT_01.json','ENTRY_AUDIT_ATTEMPT_01.md'],
            audit_correction='Attempt 01 incorrectly required completed for the successful qa_patch_applied event at sequence9. Raw evidence retained; final check requires that exact typed patch event, patch hash and four vertices.',
            method='Adapted read-only closed_solid_read_001 audit plus independent stdlib projection/edge triangle distances; no product imports.',
            limitation='Owner receipts prove the recorded Popen children reaped. Controller self PID differs from that recorded Popen PID; no invented ownership or PID lookup. Each final worker close event remains unknown despite separate closed/reap receipts. Terminal guards do not prove absence of reverted transient mutation.')
        (OUT/'ENTRY_AUDIT.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
        lines=['# Zero-witness paired entry audit','',f"passed={payload['passed']}; 18 public observations; 28 physical RPC; no extra live calls.",'']
        for a in arms:
            lines += [f"{a['arm']}: {a['check_count']} checks, {len(a['check_failures'])} failures; source {a['source_sha256']}; 131 exact Git/frozen product files; 9 observations and 14 RPC.",'']
            if a['check_failures']:lines.append(json.dumps(a['check_failures'],ensure_ascii=False))
        lines += ['All original state readbacks, selected captures, public bindings, independent truth/distance intervals, four-vertex patch invariants, and public witnesses were audited from archived bytes. Each witness was independently checked against every original world triangle with a 1e-9 m maximum distance. Logical socket code and stored CRLF scripts were matched to worker execution hashes. Raw QA/invocation files remained byte-identical.',f"All {len(sealed)} RAW_FREEZE original files unchanged={raw_ok}.",'',payload['audit_correction'],'',payload['limitation'],'','Source audit is separate from the preregistered performance decision.']
        (OUT/'ENTRY_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
        print(json.dumps(dict(passed=payload['passed'],checks=sum(a['check_count'] for a in arms),failures=[dict(arm=a['arm'],checks=a['check_failures']) for a in arms],json_sha256=SHA((OUT/'ENTRY_AUDIT.json').read_bytes()))))
    except BaseException:
        number=1
        while (OUT/f'ENTRY_AUDIT_FAILURE_{number:02}.json').exists():number+=1
        failure=dict(script_sha256=script_sha,argv=sys.argv,python=sys.executable,traceback=traceback.format_exc(),elapsed_ns=time.perf_counter_ns()-start)
        (OUT/f'ENTRY_AUDIT_FAILURE_{number:02}.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf8')
        raise


if __name__=='__main__':main()
