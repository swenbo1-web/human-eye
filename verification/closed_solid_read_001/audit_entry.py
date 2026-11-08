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
QA = OUT / 'qa_01'
OUTER = OUT / 'qa_invocation_01'
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())
SOURCE_SHA = None
TOKEN = 'CLOSED-SOLID-READ-001-20261108T141714Z-ONLY'


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


def main():
    begun = time.perf_counter_ns()
    assert not (OUT / 'ENTRY_AUDIT.json').exists(), 'preserve every audit attempt'
    result = load(QA / 'RESULTS.json')
    assert result.get('ended_utc') is not None, 'terminal-only audit'
    global SOURCE_SHA
    fixed = load(OUT / 'SOURCE_FREEZE.json')
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
    truth = load(OUT/'inputs/TRUTH.json')
    expect('fixed_independent_truth', SHA((OUT/'inputs/TRUTH.json').read_bytes())=='d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff'
        and SHA(Path(plan['truth_path']).read_bytes())==plan['truth_sha256'])
    manifest = sorted(fixed['product_manifest'], key=lambda r: r['path'])
    paths = [r['path'] for r in manifest]
    blobs = git_blobs(fixed['candidate_commit'], paths)
    sources = []
    for row in manifest:
        disk = (ROOT / row['path']).read_bytes()
        frozen = (Path(fixed['source_root']) / row['path']).read_bytes()
        sources.append(dict(path=row['path'], sha256=SHA(disk), matches=SHA(disk)==SHA(frozen)==SHA(blobs[row['path']])==row['sha256']))
    expect('exact_131_source_bytes', len(sources)==len(manifest) and len(sources)>=131 and all(r['matches'] for r in sources))
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
    snapshots = load(OUT / 'inputs/author_mesh_snapshots.json')
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
        and started['window']['max_sessions']==1 and started['window']['max_RPC']==16 and started['window']['max_public_observations']==9
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
    payload=dict(cycle_id='CLOSED-SOLID-READ-001',audited_utc=datetime.now(timezone.utc).isoformat(),passed=all(r['passed'] for r in checks),
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
    (OUT/'ENTRY_AUDIT.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    lines=['# Closed-solid read-only raw audit','',f"passed={payload['passed']}; {len(checks)} checks; {len(payload['check_failures'])} failed.",'',
        f"First probe: {classification}; closed_solid_relation={fact}. Public observations={len(public)}; all physical RPC={physical}.",'',
        'Sources, original inputs/truth, logical/wire/worker-script bindings, selected geometry, public revision/object/source bindings, exact capture fingerprints, original deadlines and owner receipts are checked from existing bytes. No product/kernel/Blender/RPC/model/PID call was added.','',
        payload['limitation'],'',f"All {len(before)} original QA/outer files remained byte-identical. Original contract completion is reported separately from structural audit validity. A required unknown is incomplete, and surface distance is never substituted for solid overlap. No model benefit is measured."]
    (OUT/'ENTRY_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(dict(passed=payload['passed'],check_count=len(checks),failures=payload['check_failures'],first_probe_classification=classification,
        public_observations=len(public),physical_RPC=physical,JSON_sha256=SHA((OUT/'ENTRY_AUDIT.json').read_bytes()),MD_sha256=SHA((OUT/'ENTRY_AUDIT.md').read_bytes()))))


if __name__=='__main__':
    main()
