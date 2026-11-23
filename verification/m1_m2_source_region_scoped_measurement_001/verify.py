"""Join the closed public observations with the installed host wires and original meshes."""

from fractions import Fraction
import math
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'m2_source_region_selective_residency_001'
OLD = run_path(str(PREVIOUS/'verify.py'))
FULL = OLD['OLD']
HOST = run_path(str(HERE/'host.py'))
COMMON = run_path(str(HERE/'common.py'))
RUN, REPLAY, LABELS, ASSETS, BINDINGS = (
    HOST[name] for name in ('RUN', 'REPLAY', 'LABELS', 'ASSETS', 'BINDINGS'))
require, read, pin, lines, indexed, stable, normalize_result = (
    OLD[name] for name in ('require', 'read', 'pin', 'lines', 'indexed', 'stable', 'normalize_result'))
order, arguments, query_from_record = (COMMON[name] for name in ('order', 'arguments', 'query_from_record'))
closed_source, wire_records, new_decoder = (
    FULL[name] for name in ('closed_source', 'wire_records', 'new_decoder'))
for function in (closed_source, wire_records, new_decoder):
    function.__globals__.update(HERE=HERE, RUN=RUN, REPLAY=REPLAY, LABELS=LABELS, ASSETS=ASSETS, BINDINGS=BINDINGS)
OLD['verify_core'].__globals__['BINDINGS'] = BINDINGS

TOOL = 'human_eye_scene_observe'
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
PUBLIC_SCHEMA = 'human-eye-source-region-scoped-measurement-v1'
COMMAND = {'A': 'capture', 'B': 'capture_source_region_pair'}


def _subtract(a, b):
    return [left-right for left, right in zip(a, b, strict=True)]


def _dot(a, b):
    return sum(left*right for left, right in zip(a, b, strict=True))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def point_in_face(point, vertices, *, exact=False):
    """Check the witness independently against the original triangle in world space."""
    numeric = Fraction if exact else float
    a, b, c = ([numeric(value) for value in row] for row in vertices)
    point = [numeric(value) for value in point]
    x, y, offset = _subtract(b, a), _subtract(c, a), _subtract(point, a)
    normal = _cross(x, y)
    norm2 = _dot(normal, normal)
    scale = max(abs(value) for row in (a,b,c,point) for value in row)
    epsilon = 0 if exact else max(64*math.ulp(float(scale)), 1e-14)
    if not norm2:
        for origin, end in ((a,b),(a,c),(b,c)):
            edge, delta = _subtract(end, origin), _subtract(point, origin)
            along, length2 = _dot(edge, delta), _dot(edge, edge)
            if not length2:
                if _dot(delta, delta) <= epsilon**2:
                    return True
                continue
            boundary = 0 if exact else epsilon*math.sqrt(length2)
            cross = _cross(edge, delta)
            if -boundary <= along <= length2+boundary and _dot(cross, cross) <= boundary**2:
                return True
        return False
    normal_length = 0 if exact else math.sqrt(norm2)
    if abs(_dot(offset, normal)) > epsilon*normal_length:
        return False
    for origin, end in ((a,b),(b,c),(c,a)):
        edge = _subtract(end, origin)
        side = _dot(_cross(edge, _subtract(point, origin)), normal)
        if side < -(0 if exact else epsilon*math.sqrt(_dot(edge, edge))*normal_length):
            return False
    return True


def check_public(parsed, archive, query, arm):
    blocks = read(parsed['rx']['path'])['result']['content']
    require(type(blocks) is list and len(blocks) == 1 and blocks[0]['type'] == 'text',
            'actual_no_image_must_deliver_one_text_message')
    text = blocks[0]['text']
    import json
    public = json.loads(text)
    require(type(public) is dict and archive['read_only'] is True
            and archive['execution_authority'] is False and archive['frames'] == [],
            'no_image_readonly_producer_required')
    if arm == 'A':
        task = public['task_result']
        raw_task = archive['task_result']
        require(public['schema'] == 'source-region-brief-v2' and public['result_kind'] == 'source_region'
                and public['images'] == [] and public['read_only'] is True and public['execution_authority'] is False
                and public['region_ref'] == archive['region_ref'] == raw_task['region_ref']
                and public['region']['host_id'] == archive['facts']['region']['host_id']
                and public['region']['instance_id'] == archive['facts']['region']['instance_id']
                and all(task[key] == raw_task[key] for key in ('status','reference','measurement_scope','facts'))
                and task['source_mapping']['nearest_witness'] == raw_task['source_mapping']['nearest_witness']
                and all(task[key] == archive['binding'][key] for key in ('unit','coordinate_frame')),
                'actual_legacy_brief_not_bound_to_original_service_result')
        return public, len(text.encode('utf8'))
    fields = {'schema','status','measurement_scope','coordinate_frame','unit','world_box_m','region_object',
              'reference_object','selected_triangle_count','distance_m','direction_a_to_b','direction_status',
              'point_a_m','point_b_m','source_triangle_a','source_triangle_b','source_triangle_index_domain','read_only'}
    require(set(public) in (fields, fields|{'exact_points_m'})
            and public['schema'] == PUBLIC_SCHEMA and public['status'] == 'complete' and public['read_only'] is True
            and public['measurement_scope'] == archive['measurement_scope'] == SCOPE,
            'scoped_public_shape_or_readonly_scope_changed')
    binding, mapping = archive['binding'], archive['source_mapping']
    fact = archive['facts']['surface_proximity']
    distance, witness = (fact['value'][key] for key in ('distance_m','nearest_witness'))
    require(all(public[key] == binding[key] for key in ('coordinate_frame','unit'))
            and stable(public['world_box_m']) == stable(binding['world_box_m'])
            and public['region_object'] == binding['target'] and public['reference_object'] == binding['reference']
            and public['selected_triangle_count'] == len(mapping['region']['submesh_to_source_triangle_indices'])
            and public['distance_m'] == distance and public['direction_status'] == fact['direction_status']
            and public['direction_a_to_b'] == witness['direction_a_to_b']
            and public['point_a_m'] == witness['a'] and public['point_b_m'] == witness['b']
            and public['source_triangle_index_domain'] == mapping['region']['index_domain'],
            'scoped_public_fact_or_frame_not_bound_to_its_producer')
    provenance = archive['witness_provenance']
    for side in ('a','b'):
        column = 'source_triangle_'+side
        proof = mapping['nearest_witness'][side]
        require(type(public[column]) is int and public[column] == provenance[column]
                and proof['status'] == 'measured' and proof['exact_membership'] is True
                and public[column] in proof['source_triangle_indices']
                and public['source_triangle_index_domain'] == proof['index_domain'],
                'scoped_public_source_triangle_not_certified/'+side)
    require(public.get('exact_points_m') == provenance.get('exact_points_m'),
            'scoped_public_exact_witness_not_bound')
    return public, len(text.encode('utf8'))


def full_capture(decoder, wire, client, terminal, archive, native, index):
    resources = wire['packet']['resources']
    require(wire['params'] == {} and type(resources) is list, 'baseline_not_actual_complete_scene_capture')
    captured = decoder.apply(wire['packet'])
    meshes = FULL['_whole_meshes'](captured, terminal)
    require(all(row['vertices'] == original['evaluated']['vertices_world_m']
                for original in terminal['objects'] for row in (meshes[original['name']],)),
            'full_source_world_coordinates_disagree_with_current_terminal_source')
    carried = {'objects': len(resources), 'vertices': sum(len(row['vertices_local']) for row in resources),
               'triangles': sum(len(row['faces']) for row in resources)}
    require(captured['capture_state'] == archive['binding']['capture_state']
            and archive['binding']['capture_scope'] == 'complete_scene_meshes'
            and (client['decoder']['resources_sent'] == carried['objects'])
            and ((index == 1 and carried['objects'] == len(meshes))
                 or (index > 1 and not any(carried.values()))), 'baseline_full_delta_not_currently_bound')
    work = {key: native['residency_after'][key]-native['residency_before'][key] for key in (
        'resource_faces_read','resource_vertices_read','to_mesh','triangulations','world_transforms',
        'world_vertices_transformed','capture_cache_hits')}
    return captured, work, carried


def _process_samples(observation):
    for key in ('Blender','engine'):
        before, after = (observation['process_'+when][key] for when in ('before','after'))
        require(before['pid'] == after['pid'] and before['sampled_ns'] <= after['sampled_ns']
                and all(before[field] <= after[field] for field in ('kernel_cpu_ns','user_cpu_ns'))
                and all(type(sample['working_set_bytes']) is int and sample['working_set_bytes'] > 0
                        for sample in (before,after)), 'invalid_actual_process_resource_window')


def verify_slot(slot, label, expected_records, *, offline=False):
    slot = Path(slot).resolve(strict=True)
    result = read(slot/'SLOT_RESULT.json')
    closure, terminal, independent, pins = closed_source(
        slot,label,result,read(slot/'SLOT_PUBLICATION.json'),offline=offline)
    arm = LABELS[label][1]
    meter_path, worker_path = (slot/'mcp_io'/name for name in ('REAL_HOST_STAGES.json','RUNTIME.json'))
    sys_wire = slot/'mcp_io/MCP_IO.jsonl'
    meter, worker = read(meter_path), read(worker_path)
    native = wire_records(slot,offline=offline)
    streams = indexed([row for row in lines(sys_wire) if row['method']=='tools/call'],
                      'id','actual_production_tools')
    expected = order(expected_records)
    require(meter['pid'] == worker['pid']
            and meter['source_sha256'] == worker['source_sha256'] == read(BINDINGS[arm])['source_sha256']
            and meter['gc_before'] == meter['gc_after'] and meter['open_pause'] is None
            and len(native)==len(meter['requests'])==len(streams)==len(result['observations'])==len(expected)==3,
            'three_actual_production_measurements_required/'+label)
    pins.extend(pin(path) for path in (meter_path,worker_path,sys_wire,slot/'native/WIRE/INDEX.json',
                                     slot/'native/WORKER_EVENTS.jsonl'))
    decoder = new_decoder() if arm == 'A' else None
    checked, preceding = [], None
    for index,(wire,client,observation,record) in enumerate(
            zip(native,meter['requests'],result['observations'],expected,strict=True),1):
        parsed = FULL['STDIO']['_raw_stdio'](slot,streams[observation['response_id']])
        query = query_from_record(record)
        require(parsed['tool'] == TOOL and stable(parsed['arguments']) == stable(arguments(record,arm))
                and parsed['is_error'] is False and parsed['rasters'] == 0
                and type(observation['wall_ns']) is int and observation['wall_ns'] > 0
                and client['outcome'] == 'success' and client['command'] == wire['command'] == COMMAND[arm]
                and client['host_request_id'] == wire['host_id']
                and client['request_bytes'] == wire['tx']['bytes'] and client['response_bytes'] == wire['rx']['bytes']
                and client['resident_before'] is (index > 1) and client['resident_after'] is True
                and (wire['bootstrap_base64_bytes'] > 0) is (index == 1),
                'actual_scoped_blender_and_production_stdio_identity_changed/'+label)
        producer = slot/'mcp_io'/f'PRODUCER_RESULT_{index}.json'
        archive = read(producer)
        public, body_bytes = check_public(parsed,archive,query,arm)
        native_stage = wire['event']['m2_work']['native_work']
        span = client['stages']['tcp_exchange_including_outer_json']
        require(FULL['_within'](native_stage['envelope_encoding'],span)
                and all(FULL['_within'](row,span) for row in native_stage['intervals'])
                and FULL['_within'](span,client['stages']['host_request'])
                and FULL['_within'](client['stages']['outer_strict_json'],span),
                'actual_host_stages_not_nested_in_recorded_tcp')
        if arm == 'A':
            capture, work, carried = full_capture(decoder,wire,client,terminal,archive,native_stage,index)
            core, lease, connector = None, None, None
        else:
            require('decoder' not in client and not any(row['name'] in ('_capture','capture_delta')
                        for row in native_stage['intervals']), 'new_route_used_whole_capture_or_decoder')
            capture = None
            core, work, lease = OLD['materialization'](wire,preceding,'B')
            carried = OLD['verify_core'](core,work,archive,wire,terminal,query,'B')
            before, after = (native_stage['residency_'+when] for when in ('before','after'))
            if work['mode'] != 'uncached_capture':
                require(all(after[name]-before[name] == work[name] for name in (
                    'to_mesh','triangulations','world_transforms','world_vertices_transformed')),
                    'new_route_actual_native_counters_disagree_with_confirmed_packet')
            connector = {key:value for key,value in archive['work']['host_capture'].items() if key not in work}
            require(connector['connector_retained_bytes'] <= connector['connector_cache_limit_bytes']
                    and connector['connector_reused_payload'] is (work['mode'] == 'lease_hit'),
                    'candidate_actual_connector_work_or_cap_not_bound')
            preceding = (lease,core) if lease is not None else None
        if not offline:
            _process_samples(observation)
        checked.append({
            'index':index,'query':query,'measurement':normalize_result(archive),'producer':pin(producer),
            'public':public,'public_body_bytes':body_bytes,'stdio':parsed,'host':client,'host_native':native_stage,
            'transport':{key:value for key,value in wire.items() if key not in ('params','packet','event')},
            'host_wire_total_bytes':wire['tx']['bytes']+wire['rx']['bytes'],
            'expanded':work,'transmitted':carried,'local_stages':archive['stages'],'wall_ns':observation['wall_ns'],
            'process_samples':{k:v for k,v in observation.items() if k.startswith('process_')},
            'connector_work':connector,'lease':lease,'known_lease_sent':wire['params'].get('known'),
            'decoded_full':capture,'scoped_packet':core,
            'exact_points':public.get('exact_points_m') if arm=='B' else None,
        })
        pins.extend((wire['tx'],wire['rx'],parsed['tx'],parsed['rx'],pin(producer)))
    return {'label':label,'window_ns':result['window_ns'],'calls':checked,'terminal':terminal,
            'before_after':independent,'close':pin(slot/'HOST_RECEIPT.json'),
            'budget':closure['budget']['slots'][label],'offline_fixture':offline,'source_pins':pins}


def _witnesses(call, meshes, expected, *, public_only=False):
    result = call['measurement']
    fact = result['facts']['surface_proximity']
    distance, witness = (fact['value'][key] for key in ('distance_m','nearest_witness'))
    require(fact['status'] == 'measured'
            and math.isclose(distance,expected['distance_m'],rel_tol=1e-12,abs_tol=1e-10)
            and math.dist(witness['direction_a_to_b'],expected['direction']) <= 1e-6
            and math.isclose(math.dist(witness['a'],witness['b']),distance,rel_tol=1e-10,abs_tol=1e-10),
            'actual_point_pair_or_direction_disagrees_with_independent_truth')
    exact_pair = call['exact_points']
    for idx,(side, mesh) in enumerate(zip(('a','b'),meshes,strict=True)):
        proof = result['nearest'][side]
        rows = proof['source_triangle_indices']
        allowed = set(expected['source_triangle_indices']) if side == 'a' else range(len(mesh['faces']))
        vertices = set(expected['source_vertex_indices']) if side == 'a' else range(len(mesh['vertices']))
        require(proof['status'] == 'measured' and proof['exact_membership'] is True
                and rows and rows == sorted(set(rows)) and all(type(row) is int and row in allowed for row in rows)
                and all(type(row) is int and row in vertices and math.dist(mesh['vertices'][row],witness[side]) <= 1e-10
                        for row in proof['source_vertex_indices']), 'actual_witness_not_in_current_source_domain/'+side)
        if exact_pair is not None:
            point = tuple(Fraction(component) for component in exact_pair[idx])
            require(len(point)==3 and [float(value) for value in point] == witness[side],
                    'actual_exact_witness_does_not_round_to_displayed_coordinates')
        else:
            point = witness[side]
        rows_to_prove = [call['public']['source_triangle_'+side]] if public_only else rows
        require(all(point_in_face(point, [mesh['vertices'][v] for v in mesh['faces'][row]],
                                  exact=exact_pair is not None) for row in rows_to_prove),
                'actual_public_witness_not_on_source_triangle/'+side)


def compare(asset, left, right, truth):
    require(left['offline_fixture'] is right['offline_fixture']
            and LABELS[left['label']] == (asset,'A') and LABELS[right['label']] == (asset,'B')
            and [row['query'] for row in left['calls']] == [row['query'] for row in right['calls']]
                == [query_from_record(record) for record in order(truth['requests'])],
            'actual_assets_arms_or_queries_changed')
    rosters = [indexed(slot['terminal']['objects'],'name','actual_terminal') for slot in (left,right)]
    require(rosters[0].keys() == rosters[1].keys()
            and all(all(obj[key] == rosters[1][name][key] for key in ('evaluated','matrix_world','visible_get'))
                    for name,obj in rosters[0].items()), 'current_arrays_changed_between_arms')
    prior, source = OLD['original_full'](asset)
    for index,(a,b) in enumerate(zip(left['calls'],right['calls'],strict=True)):
        expected = truth['regions'][int(index==2)]
        meshes = FULL['_prove_geometry'](a['decoded_full'],b['scoped_packet'],a['query'],expected)
        FULL['_prove_geometry'](prior,b['scoped_packet'],b['query'],expected)
        require(a['measurement']['region'] == b['measurement']['region'],
                'legacy_and_scoped_current_region_source_mapping_differs')
        _witnesses(a,meshes,expected)
        _witnesses(b,meshes,expected,public_only=True)
    cold, hot, alternate = right['calls']
    require(cold['expanded']['mode'] == alternate['expanded']['mode'] == 'resident_capture'
            and cold['lease'] is not None and alternate['lease'] is not None
            and cold['known_lease_sent'] is None and alternate['known_lease_sent'] is None
            and hot['expanded']['mode'] == 'lease_hit' and hot['lease'] == hot['known_lease_sent'] == cold['lease']
            and cold['host_wire_total_bytes'] > hot['host_wire_total_bytes']
            and cold['lease']['document_epoch'] == alternate['lease']['document_epoch']
            and cold['lease']['payload_sha256'] != alternate['lease']['payload_sha256'],
            'candidate_cold_repeat_or_alternate_contract_failed')
    require(cold['transmitted']['objects'] <= left['calls'][0]['transmitted']['objects']
            and all(cold['transmitted'][key] < left['calls'][0]['transmitted'][key]
                    for key in ('vertices','triangles')), 'candidate_cold_complete_scene_transfer_not_avoided')
    if asset == 'yanyite':
        require(not any(alternate['expanded'][k] for k in ('to_mesh','triangulations','world_transforms'))
                and alternate['expanded']['box_triangles_scanned'] > 0,
                'same_pair_new_box_redid_world_geometry_or_did_not_scan')
    return {
        'scoped_measurement_passed': True, 'selective_residency_passed': True,
        'source_and_measurement_equivalent': True,'same_witness_displays': [
            a['measurement']['facts']['surface_proximity']['value']['nearest_witness']
            == b['measurement']['facts']['surface_proximity']['value']['nearest_witness']
            for a,b in zip(left['calls'],right['calls'],strict=True)],
        'cold_geometry_reduced':True,
        'cold_host_transport_reduced':cold['host_wire_total_bytes'] < left['calls'][0]['host_wire_total_bytes'],
        'original_complete_geometry':source,'complete_slot_ns':[left['window_ns'],right['window_ns']],
        'offline_fixture':left['offline_fixture'],
    }
