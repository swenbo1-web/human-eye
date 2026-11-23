"""Check both endpoints and the current source without replaying a formal slot."""

import ast
from hashlib import sha256
import json
import math
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
V = HERE.parent
PRIOR = V/'m2_source_region_cold_selective_transport_001'
STDIO = run_path(str(V/'m2_source_region_shared_normalization_live_001/meter.py'))
CONTROL = run_path(str(PRIOR/'controls.py'))
COMMON = run_path(str(HERE/'common.py'))
HOST = run_path(str(HERE/'host.py'))
RUN, REPLAY, LABELS, ASSETS, BINDINGS, PRIVATE_TOOL = (
    HOST[key] for key in ('RUN','REPLAY','LABELS','ASSETS','BINDINGS','PRIVATE_TOOL'))
query_from_record, arguments = (COMMON[key] for key in ('query_from_record','arguments'))
normalize_result = CONTROL['normalize_result']
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
SCOPE = 'selected_source_region_and_reference'
COMPLETE = 'complete_scene_meshes'
COMMANDS = {'A':'capture','B':'capture_source_region_pair'}
TOOLS = {'A':'human_eye_scene_observe','B':PRIVATE_TOOL}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line]


def indexed(records, key, name):
    table = {row[key]:row for row in records}
    require(len(table)==len(records), 'duplicate_evidence_'+name)
    return table


def _assigned(node, name):
    return (isinstance(node,ast.Assign) and len(node.targets)==1 and
            isinstance(node.targets[0],ast.Name) and node.targets[0].id==name)


def _named_call(node, base, attribute):
    return (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
            isinstance(node.func.value,ast.Name) and node.func.value.id==base and
            node.func.attr==attribute and len(node.args)==1 and not node.keywords)


def fixed_script(script):
    """Recover the resident command by assignment target; the script is never executed."""
    tree = ast.parse(script, filename='observed_blender_request')
    assigns = [node.value for node in tree.body if _assigned(node,'_request')]
    require(len(assigns)==1 and _named_call(assigns[0],'_json','loads')
            and isinstance(assigns[0].args[0],ast.Constant) and type(assigns[0].args[0].value) is str,
            'actual_fixed_host_request_literal_missing')
    literal = assigns[0].args[0].value
    fixed = json.loads(literal)
    require(type(fixed) is dict and set(fixed)=={'id','command','params'}
            and type(fixed['id']) is str and len(fixed['id'])==32
            and all(char in '0123456789abcdef' for char in fixed['id'])
            and type(fixed['command']) is str and type(fixed['params']) is dict,
            'actual_fixed_host_request_literal_shape')
    inline = [item.args[0].value for item in ast.walk(tree) if _named_call(item,'_b64','b64decode')
              and isinstance(item.args[0],ast.Constant) and type(item.args[0].value) is str]
    expert = []
    for node in ast.walk(tree):
        if (isinstance(node,ast.Assign) and len(node.targets)==1
                and isinstance(node.targets[0],ast.Attribute)
                and node.targets[0].attr=='_arm_twist_dependency_sources'
                and isinstance(node.value,ast.DictComp)):
            iterator, = node.value.generators
            require(isinstance(iterator.iter,ast.Call) and isinstance(iterator.iter.func,ast.Attribute)
                    and iterator.iter.func.attr=='items' and isinstance(iterator.iter.func.value,ast.Dict),
                    'actual_native_bootstrap_expert_literal_shape')
            bundle = ast.literal_eval(iterator.iter.func.value)
            require(all(type(key) is str and type(value) is str for key,value in bundle.items()),
                    'actual_native_bootstrap_expert_literal_shape')
            expert.extend(bundle.values())
    require(len(inline) in (0,2) and (not expert or len(inline)==2), 'actual_native_bootstrap_literal_shape')
    return fixed, {'script_utf8_bytes':len(script.encode('utf8')), 'request_json_utf8_bytes':len(literal.encode('utf8')),
                   'bootstrap_base64_bytes':sum(len(value.encode('ascii')) for value in (*inline,*expert)),
                   'bootstrap_core_base64_bytes':sum(len(value.encode('ascii')) for value in inline),
                   'bootstrap_expert_base64_bytes':sum(len(value.encode('ascii')) for value in expert)}


def wire_records(slot, *, offline=False):
    """Pair raw socket TX/RX with the exact native worker event."""
    directory = slot/'native/WIRE'
    ledger = read(directory/'INDEX.json')
    indexed(ledger,'sequence','native_wire')
    worker = indexed(lines(slot/'native/WORKER_EVENTS.jsonl'),'sequence','native_worker')
    calls, ids = [], set()
    for row in ledger:
        wire = directory/str(row['sequence']).zfill(3)
        request_path, response_path = wire/'REQUEST.bin', wire/'RESPONSE.bin'
        reply = read(response_path)
        value = reply.get('result',{}).get('result')
        if not isinstance(value,str) or not value.startswith(PREFIX):
            continue
        request = read(request_path)
        require(request.get('type')=='execute_code' and reply.get('status')=='success', 'native_not_executed')
        fixed, allocation = fixed_script(request['params']['code'])
        if fixed['command'] not in COMMANDS.values():
            continue
        inner = json.loads(value[len(PREFIX):])
        tx,rx = pin(request_path),pin(response_path)
        event = worker[row['sequence']]
        require(inner['id']==fixed['id'] and fixed['id'] not in ids and 'result' in inner
                and row['response_sendall_completed'] is True
                and (row['request_bytes'],row['response_attempted_bytes'])==(tx['bytes'],rx['bytes'])
                and event['status']=='completed' and event['terminal_geometry_and_file_checks_passed'] is True
                and event['script_sha256']==sha256(request['params']['code'].encode('utf8')).hexdigest()
                and event.get('offline_fixture',False) is offline, 'native_wire_or_readonly_command_not_bound')
        ids.add(fixed['id'])
        calls.append({'sequence':row['sequence'],'tx':tx,'rx':rx,'host_id':inner['id'],
                      'command':fixed['command'],'params':fixed['params'],'packet':inner['result'],
                      'event':event,**allocation})
    return calls


def new_decoder():
    # This is the original baseline wire contract. The selected candidate
    # does not replace it and the verifier never applies a private packet here.
    old = read(BINDINGS['A'])
    incoming = sys.path[:]
    try:
        sys.path[:0] = [old['install_root'],old['dependency_root']]
        from human_eye_plugin import scene_residency
    finally:
        sys.path[:] = incoming
    manifest = {row['path']:row['sha256'] for row in old['source_manifest']}
    require(pin(scene_residency.__file__)['sha256']==manifest['human_eye_plugin/scene_residency.py'],
            'actual_scene_delta_decoder_source_changed')
    return scene_residency.SceneDeltaDecoder()


def _matches(path, receipt):
    return pin(path)=={key:receipt[key] for key in ('path','bytes','sha256')}


def closed_source(slot, label, result, publication, *, offline):
    """Keep live scene proof distinct from read-only historical replay custody."""
    source_path = slot/'HOST_RECEIPT.json'
    receipt = read(source_path)
    live_root = RUN/'slots'/label
    replay_root = REPLAY/label
    require(slot==(replay_root/'slots'/label if offline else live_root).resolve()
            and result['label']==publication['label']==receipt['label']==label
            and result['status']==publication['status']==receipt['status']=='completed'
            and publication['result']==pin(slot/'SLOT_RESULT.json') and result['closure']==receipt
            and result['offline_fixture'] is publication['offline_fixture'] is offline,
            'actual_closed_result_not_bound/'+label)
    budget = receipt['budget']
    counts = budget['counts']
    row = budget['slots'][label]
    require(all(counts.get(key,0)==0 for key in (
            'consumer_admissions','all_raster_actual','all_raster_upper','pending_raster_reservations',
            'Blender_spawned_unknown')) and row['business_admissions']==3
            and row.get('raster_actual',0)==row.get('raster_upper',0)==0,
            'actual_business_or_raster_budget_changed/'+label)
    close = receipt['runtime_close']['public_MCP_close']
    require(close['confirmed'] is True and close['stdout_eof_seen'] is True
            and close['production_eof_and_exit_verified'] is True and close['exit_code']==0,
            'mcp_eof_not_confirmed/'+label)
    pins = [pin(path) for path in (source_path,slot/'SLOT_RESULT.json',slot/'SLOT_PUBLICATION.json',
                                  slot/'mcp/HELD_CLOSE.json')]
    require(close==read(slot/'mcp/HELD_CLOSE.json'),'recorded_MCP_close_differs_from_actual_receipt')
    if offline:
        ready_path,close_path = (replay_root/name for name in ('REPLAY_READY.json','REPLAY_CLOSE.json'))
        ready,replayed = read(ready_path),read(close_path)
        terminal_pin = ready['terminal_source']
        require(result['replay']=={'ready':pin(ready_path),'close':pin(close_path)} and replayed['ready']==pin(ready_path)
                and replayed['terminal_source']==terminal_pin==pin(terminal_pin['path'])
                and ready['offline_fixture'] is replayed['offline_fixture'] is True
                and ready['pid']==replayed['pid'] and ready['label']==replayed['label']==label
                and ready['product_source_sha256']==replayed['product_source_sha256']==read(BINDINGS[LABELS[label][1]])['source_sha256']
                and replayed['passed'] is replayed['listener_closed'] is replayed['actual_stdin_EOF'] is True
                and replayed['connections_completed']==3 and replayed['error'] is None
                and all(replayed[key]==0 for key in ('actual_Blender','actual_models','actual_rasters'))
                and not Path(terminal_pin['path']).is_relative_to(RUN)
                and counts.get('Blender_start_attempts',0)==0 and receipt.get('independent_before_after') is None,
                'offline_capture_claims_live_or_unbound_terminal_source/'+label)
        pins.extend((pin(ready_path),pin(close_path),terminal_pin))
        for row in replayed['wire_pins']:
            require(Path(row['path']).is_relative_to(slot/'native') and row==pin(row['path']),
                    'actual_replay_closed_wire_pin_mismatch')
        require(len(replayed['wire_pins'])==8,'actual_replay_close_wire_pin_count_changed')
        pins.extend(replayed['wire_pins'])
        terminal = read(terminal_pin['path'])
        independent = None
    else:
        current = pin(HERE/'FROZEN.json')['sha256']
        require(result['freeze_sha256']==publication['freeze_sha256']==current
                and counts.get('Blender_start_attempts',0)>=1
                and receipt['closure_verification']['passed'] is True,
                'live_slot_missing_actual_frozen_close/'+label)
        initial = slot/'initial_capture/TERMINAL_SOURCE.json'
        terminal_path = slot/'TERMINAL_SOURCE.json'
        require(_matches(initial,receipt['initial_source']) and _matches(terminal_path,receipt['terminal_source'])
                and result['initial']==pin(initial), 'current_source_is_not_original_slot_capture/'+label)
        independent = receipt['independent_before_after']
        begin,terminal = read(initial),read(terminal_path)
        require(independent['passed'] is True and independent['same_owned_scene'] is True
                and independent['initial_sha256']==pin(initial)['sha256']
                and independent['terminal_sha256']==pin(terminal_path)['sha256']
                and begin['source']['pid']==terminal['source']['pid']==receipt['closure_verification']['pid']
                and all(begin[key]==terminal[key] for key in ('source','objects','source_face_offsets',
                            'display_object_mask','layer_collections','scene_cameras')),
                'live_initial_terminal_readonly_equality_changed/'+label)
        pins.extend((pin(initial),pin(terminal_path),pin(slot/'RUNTIME_CLOSE.json'),pin(slot/'NATIVE_RUNTIME_PROOF.json')))
        require(receipt['runtime_close']==read(slot/'RUNTIME_CLOSE.json'),'runtime_close_not_same_original')
    require(terminal['source']['asset_sha256']==ASSETS[LABELS[label][0]][1], 'terminal_asset_does_not_match_arm')
    return receipt,terminal,independent,pins


def _within(interval, outer):
    return (outer['started_ns'] <= interval['started_ns'] <= interval['closed_ns'] <= outer['closed_ns']
            and interval['elapsed_ns']==interval['closed_ns']-interval['started_ns'])


def _normal_public(result):
    require(result['result_kind']=='source_region' and result['binding']['capture_scope']==COMPLETE
            and 'region_ref' in result and 'source_mapping' in result['task_result']
            and result['read_only'] is True and result['execution_authority'] is False and not result['frames'],
            'standard_full_source_region_reply_required')
    return normalize_result(result)


def _published_value(stdio, producer, arm):
    body = read(stdio['rx']['path'])['result']
    blocks = body['content']
    require(body['isError'] is False and len(blocks)==1 and blocks[0]['type']=='text',
            'actual_no_image_measurement_must_return_one_text_result')
    public = json.loads(blocks[0]['text'])
    archived = read(producer)
    if arm=='A':
        require(_normal_public(public)==_normal_public(archived)
                and all(public[key]==archived[key] for key in ('binding','region_ref')),
                'standard_full_public_reply_does_not_bind_original_service_result')
    else:
        require(public==archived, 'private_reply_does_not_bind_original_service_result')
    return archived


def _whole_meshes(capture, terminal):
    meshes = indexed(capture['meshes'],'name','full_mesh_name')
    authored = indexed(terminal['objects'],'name','terminal_mesh_name')
    require(meshes.keys()==authored.keys(), 'full_source_object_roster_changed')
    for name,row in meshes.items():
        current = authored[name]
        require(row['object_id']==current['object_id']
                and capture['host_identity']['object_instances'][row['object_id']]==current['instance_id']
                and row['faces']==current['evaluated']['triangles']
                and len(row['vertices'])==len(current['evaluated']['vertices_world_m']),
                'full_source_current_instance_or_triangle_order_changed/'+name)
    return meshes


def _private(work, archive, params, terminal, tx, rx, native, query):
    region,reference,binding = (work[key] for key in ('region','reference','binding'))
    listed = indexed(terminal['objects'],'name','private_terminal_mesh')
    target,whole = (listed[binding[key]['name']] for key in ('target','reference'))
    for role,obj,selector in (('target',target,query['region']['object']),('reference',whole,query['reference'])):
        identifier = {key:obj[key] for key in ('object_id','name','instance_id')}
        require(binding[role]==identifier and binding[role+'_selector']==selector,
                'private_bound_instance_or_selector_changed/'+role)
    expected = {'target':query['region']['object'],'reference':query['reference'],
                'world_box_m':query['region']['world_box_m']}
    require(set(params)==set(expected)|{'deadline_ns','max_response_bytes'}, 'private_host_request_field_shape')
    require({key:params[key] for key in expected}==expected and binding['world_box_m']==expected['world_box_m']
            and binding['world_matrices']=={'target':target['matrix_world'],'reference':whole['matrix_world']}
            and type(params['deadline_ns']) is int and native['envelope_encoding']['closed_ns']<=params['deadline_ns']
            and type(params['max_response_bytes']) is int and 0<rx['bytes']<=params['max_response_bytes']
            and tx['bytes']>0, 'private_host_request_bound_or_original_pose_changed')
    count = work['work']
    carried = {'objects':2,'vertices':len(region['vertices'])+len(reference['vertices']),
               'triangles':len(region['faces'])+len(reference['faces'])}
    stable = {key:work[key] for key in ('schema','binding','region','reference')}
    payload_sha = sha256(json.dumps(stable,sort_keys=True,separators=(',',':'),ensure_ascii=False,
                                   allow_nan=False).encode('utf8')).hexdigest()
    require(work['schema']=='human-eye-selective-source-region-capture-v1'
            and archive['schema']=='human-eye-selective-source-region-measurement-v1'
            and binding=={key:archive['binding'][key] for key in binding}
            and archive['payload_sha256']==work['payload_sha256']==payload_sha
            and 'region_ref' not in archive and 'ordered_geometry_sha256' not in binding
            and binding['capture_scope']==SCOPE and 'decoder' not in archive
            and count['candidate_objects']==len(listed) and count['expanded_objects']==2
            and count['expanded_vertices']==len(target['evaluated']['vertices_world_m'])+len(reference['vertices'])
            and count['expanded_triangles']==len(target['evaluated']['triangles'])+len(reference['faces'])
            and count['private_cache_retained_objects']==0
            and all(count['transmitted_'+key]==value for key,value in carried.items()),
            'private_capture_scope_or_actual_work_count_changed')
    return count,carried


def verify_slot(slot, label, expected_records, *, offline=False):
    slot = Path(slot).resolve(strict=True)
    require(len(expected_records)==2,'two_registered_source_regions_required')
    expected = (expected_records[0],expected_records[0],expected_records[1])
    result = read(slot/'SLOT_RESULT.json')
    publication = read(slot/'SLOT_PUBLICATION.json')
    close,terminal,independent,pins = closed_source(slot,label,result,publication,offline=offline)
    arm = LABELS[label][1]
    meter_path,worker_path = (slot/'mcp_io'/name for name in ('REAL_HOST_STAGES.json','RUNTIME.json'))
    sys_wire = slot/'mcp_io/MCP_IO.jsonl'
    meter,worker = read(meter_path),read(worker_path)
    calls = wire_records(slot,offline=offline)
    stdio = indexed([row for row in lines(sys_wire) if row['method']=='tools/call'],'id','public_stdio')
    require(meter['pid']==worker['pid'] and meter['source_sha256']==worker['source_sha256']
            ==read(BINDINGS[arm])['source_sha256'] and meter['open_pause'] is None
            and meter['gc_before']==meter['gc_after']
            and len(calls)==len(stdio)==len(meter['requests'])==len(result['observations'])==len(expected),
            'actual_transport_stage_denominator/'+label)
    pins.extend(pin(path) for path in (meter_path,worker_path,sys_wire,slot/'native/WIRE/INDEX.json',
                                     slot/'native/WORKER_EVENTS.jsonl'))
    decoder = new_decoder() if arm=='A' else None
    checked = []
    for index,(wire,client,observation,record) in enumerate(
            zip(calls,meter['requests'],result['observations'],expected,strict=True),1):
        query = query_from_record(record)
        production = STDIO['_raw_stdio'](slot,stdio[observation['response_id']])
        packet = wire['packet']
        require(client['outcome']=='success' and client['command']==wire['command']==COMMANDS[arm]
                and client['host_request_id']==wire['host_id'] and client['request_bytes']==wire['tx']['bytes']
                and client['response_bytes']==wire['rx']['bytes'] and production['is_error'] is False
                and production['tool']==TOOLS[arm] and production['arguments']==arguments(record,arm)
                and production['rasters']==0 and type(observation['wall_ns']) is int and observation['wall_ns']>0
                and client['resident_before'] is (index!=1) and client['resident_after'] is True
                and (wire['bootstrap_base64_bytes']>0) is (index==1),
                'actual_TCP_MCP_identity_or_budget_changed/'+label)
        producer = (slot/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json' if arm=='A'
                    else slot/'mcp_io'/f'PRIVATE_RESULT_{index}.json')
        archive = _published_value(production,producer,arm)
        require(archive['read_only'] is True and archive['execution_authority'] is False
                and archive['frames']==[],'unexpected_image_or_write_authority')
        measurement = normalize_result(archive)
        native = wire['event']['m2_work']['native_work']
        span = client['stages']['tcp_exchange_including_outer_json']
        require(native['intervals'] and _within(native['envelope_encoding'],span)
                and all(_within(item,span) for item in native['intervals'])
                and _within(span,client['stages']['host_request'])
                and _within(client['stages']['outer_strict_json'],span),
                'actual_nested_Blender_or_exchange_stages_not_timed')
        if arm=='A':
            resources = packet['resources']
            require(wire['params']=={} and type(resources) is list,
                    'baseline_not_the_original_complete_capture_command')
            captured = decoder.apply(packet)
            meshes = _whole_meshes(captured,terminal)
            carried = {'objects':len(resources),'vertices':sum(len(row['vertices_local']) for row in resources),
                       'triangles':sum(len(row['faces']) for row in resources)}
            require(captured['capture_state']==archive['binding']['capture_state']
                    and client['decoder']['resources_sent']==carried['objects']
                    and ((index==1 and carried['objects']==len(meshes)) or
                         (index>1 and all(value==0 for value in carried.values()))), 'full_delta_binding_changed')
            expanded = {key:native['residency_after'][key]-native['residency_before'][key] for key in
                        ('resource_faces_read','resource_vertices_read','to_mesh','world_vertices_transformed','capture_cache_hits')}
        else:
            require('decoder' not in client and not any(row['name'] in ('_resident_capture','capture_delta')
                        for row in native['intervals']), 'private_call_used_complete_scene_delta_or_cache')
            captured = None
            expanded,carried = _private(packet,archive,wire['params'],terminal,wire['tx'],wire['rx'],native,query)
        transport = {key:value for key,value in wire.items() if key not in ('params','packet','event')}
        staged = {'index':index,'query':query,'measurement':measurement,'producer':pin(producer),
                  'stdio':production,'host':client,'host_native':native,'transport':transport,
                  'host_wire_total_bytes':wire['tx']['bytes']+wire['rx']['bytes'],'expanded':expanded,
                  'transmitted':carried,'local_stages':archive['stages'],'wall_ns':observation['wall_ns'],
                  'decoded_full':captured,'scoped_packet':packet if arm=='B' else None}
        pins.extend((wire['tx'],wire['rx'],production['tx'],production['rx'],staged['producer']))
        checked.append(staged)
    return {'label':label,'window_ns':result['window_ns'],'calls':checked,'terminal':terminal,
            'before_after':independent,'close':pin(slot/'HOST_RECEIPT.json'),'budget':close['budget']['slots'][label],
            'offline_fixture':offline,'source_pins':pins}


def _prove_geometry(full, packet, query, expected):
    by_name = indexed(full['meshes'],'name','decoded_geometry')
    target,reference = (by_name[selector['name']] for selector in (query['region']['object'],query['reference']))
    region = packet['region']
    rows,vertices = expected['source_triangle_indices'],expected['source_vertex_indices']
    full_faces = [target['faces'][row] for row in rows]
    actual_rows = []
    lower,upper = (query['region']['world_box_m'][key] for key in ('min','max'))
    inside = [all(lo<=value<=hi for lo,value,hi in zip(lower,point,upper)) for point in target['vertices']]
    for number,face in enumerate(target['faces']):
        if all(inside[item] for item in face):
            actual_rows.append(number)
    require(rows==actual_rows==region['source_triangle_indices']
            and vertices==region['source_vertex_indices']==sorted({item for face in full_faces for item in face})
            and region['source_triangle_count']==len(target['faces']) and region['source_vertex_count']==len(target['vertices'])
            and region['vertices']==[target['vertices'][index] for index in vertices]
            and region['source_triangle_vertices']==full_faces
            and [[vertices[index] for index in face] for face in region['faces']]==full_faces
            and packet['reference']=={key:reference[key] for key in ('vertices','faces')},
            'private_selected_world_arrays_or_original_rows_not_equivalent')
    return target,reference


def compare(asset, left, right, truth):
    require(left['offline_fixture'] is right['offline_fixture']
            and LABELS[left['label']]==(asset,'A') and LABELS[right['label']]==(asset,'B'),
            'cannot_mix_live_or_replayed_arm_templates')
    first,second = map(query_from_record,truth['requests'])
    require([item['query'] for item in left['calls']]==[item['query'] for item in right['calls']]==[first,first,second],
            'actual_query_pair_changed/'+asset)
    source_a,source_b = left['terminal'],right['terminal']
    roster_a,roster_b = (indexed(data['objects'],'name','paired_terminal_roster') for data in (source_a,source_b))
    require(source_a['source']['asset_sha256']==source_b['source']['asset_sha256']==truth['asset_sha256']
            and roster_a.keys()==roster_b.keys() and source_a['display_object_mask']==source_b['display_object_mask']
            and all(all(row[field]==roster_b[name][field] for field in ('evaluated','visible_get','matrix_world'))
                    for name,row in roster_a.items()), 'cross_arm_current_source_arrays_changed')
    packets = [call['scoped_packet'] for call in right['calls']]
    scopes = [packet['payload_sha256'] for packet in packets]
    require(len({packet['binding']['document_epoch'] for packet in packets})==1 and scopes[0]==scopes[1]!=scopes[2],
            'private_repeat_or_other_region_binding_changed')
    for index,(a,b) in enumerate(zip(left['calls'],right['calls'],strict=True)):
        require(a['measurement']==b['measurement'],'private_original_exact_point_pair_or_source_changed')
        expected = truth['regions'][int(index==2)]
        meshes = _prove_geometry(a['decoded_full'],b['scoped_packet'],a['query'],expected)
        result = a['measurement']
        fact = result['facts']['surface_proximity']
        distance,point_pair = (fact['value'][key] for key in ('distance_m','nearest_witness'))
        require(fact['status']=='measured' and
                math.isclose(distance,expected['distance_m'],rel_tol=1e-12,abs_tol=1e-10)
                and math.dist(point_pair['direction_a_to_b'],expected['direction'])<=1e-6
                and math.isclose(math.dist(point_pair['a'],point_pair['b']),distance,rel_tol=1e-10,abs_tol=1e-10),
                'private_exact_distance_or_direction_not_independent_truth')
        for side,mesh in zip(('a','b'),meshes):
            disclosed = result['nearest'][side]
            witnessed = disclosed['source_triangle_indices']
            allowed = set(expected['source_triangle_indices']) if side=='a' else range(len(mesh['faces']))
            vertex_allowed = set(expected['source_vertex_indices']) if side=='a' else range(len(mesh['vertices']))
            require(disclosed['status']=='measured' and disclosed['exact_membership'] is True and witnessed
                    and witnessed==sorted(set(witnessed)) and all(row in allowed for row in witnessed)
                    and all(row in vertex_allowed and math.dist(mesh['vertices'][row],point_pair[side])<=1e-10
                            for row in disclosed['source_vertex_indices']), 'winning_source_rows_not_bound_to_point_pair')
    a,b = left['calls'][0],right['calls'][0]
    return {'source_and_exact_witness_equal':True,'cold_transmission_reduced':all((
        b['transmitted']['vertices']<a['transmitted']['vertices'],
        b['transmitted']['triangles']<a['transmitted']['triangles'],
        b['host_wire_total_bytes']<a['host_wire_total_bytes'])),
        'complete_slot_ns':[left['window_ns'],right['window_ns']],'offline_fixture':left['offline_fixture']}
