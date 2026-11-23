"""Verify actual closed exchanges, current geometry and per-stage cost."""

import ast
import json
import math
from pathlib import Path
from runpy import run_path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from experiment import HERE, host, LABELS, RUN, TRUTH, CLOSED_REPLAY, read, write, pin, require, verify_freeze


PREVIOUS_METER = run_path(str(host.PREVIOUS/'meter.py'))
CONTROL = run_path(str(HERE/'controls.py'))
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'


def line_records(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line]


def wire_records(slot):
    """Bind actual socket bytes, the fixed host id and its read-only event."""
    directory = slot/'native/WIRE'
    worker = {row['sequence']:row for row in line_records(slot/'native/WORKER_EVENTS.jsonl') if 'm2_work' in row}
    calls = []
    for row in read(directory/'INDEX.json'):
        wire = directory/str(row['sequence']).zfill(3)
        response = read(wire/'RESPONSE.bin')
        value = response.get('result',{}).get('result')
        if not isinstance(value,str) or not value.startswith(PREFIX):
            continue
        inner = json.loads(value[len(PREFIX):])
        request = read(wire/'REQUEST.bin')
        script = request['params']['code']
        token, = [line.split('_json.loads(',1)[1][:-1] for line in script.splitlines() if line.startswith('_request = _json.loads(')]
        fixed = json.loads(ast.literal_eval(token))
        if fixed['command'] not in ('capture','capture_source_region_pair'):
            continue
        tx,rx = (pin(wire/name) for name in ('REQUEST.bin','RESPONSE.bin'))
        native = worker[row['sequence']]
        require(inner['id'] == fixed['id'] and 'result' in inner and row['response_sendall_completed']
                and (row['request_bytes'],row['response_attempted_bytes']) == (tx['bytes'],rx['bytes'])
                and native['status'] == 'completed' and native['terminal_geometry_and_file_checks_passed'],
                'native_wire_or_readonly_command_not_bound')
        calls.append({'sequence':row['sequence'],'tx':tx,'rx':rx,'host_id':inner['id'],
                      'command':fixed['command'],'params':fixed['params'],'packet':inner['result'],
                      'event':native})
    return calls


def replay():
    """Exercise the same closed wire verifier with actual archived A receipts."""
    original = {
        'assembly':Path('D:/he_m4_assembly_cross_asset_product_native_001/slots/P1'),
        'yanyite':Path('D:/he_m4_yanyite_opposite_direction_product_native_001/slots/P1'),
    }
    proven,pins = {},[]
    for name,slot in original.items():
        raw = read(slot/'SLOT_RESULT.json')
        publication = read(slot/'SLOT_PUBLICATION.json')
        calls = wire_records(slot)
        require(raw['status'] == publication['status'] == 'completed' and
                publication['result_sha256'] == pin(slot/'SLOT_RESULT.json')['sha256'] and
                raw['closure_verification']['passed'] and raw['independent_before_after']['passed'] and calls,
                'existing_closed_real_response_not_qualified/'+name)
        require(calls[0]['command'] == 'capture' and calls[0]['sequence'] == 2,
                'existing_exact_cold_wire_not_found/'+name)
        proven[name] = {'source':pin(slot/'TERMINAL_SOURCE.json'),
                        'request':calls[0]['tx'],'response':calls[0]['rx'],'closure':pin(slot/'RUNTIME_CLOSE.json'),
                        'historical_budget':raw['budget']['slots']['P1'],'historical_only':True}
        pins.extend([pin(slot/name) for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json',
                    'native/WIRE/INDEX.json','native/WORKER_EVENTS.jsonl')])
        pins.extend(proven[name][key] for key in ('source','request','response','closure'))
    write(CLOSED_REPLAY,{'passed':True,'historical_only':True,'actual_Blender':0,'runs':proven,'source_pins':pins})


def new_decoder():
    old = host.read(host.BINDINGS['A'])
    sys.path[:0] = [old['install_root'],old['dependency_root']]
    from human_eye_plugin.scene_residency import SceneDeltaDecoder

    return SceneDeltaDecoder()


def absolute_close(slot,result,label,digest):
    receipt = read(slot/'HOST_RECEIPT.json')
    publish = read(slot/'SLOT_PUBLICATION.json')
    require(result['status'] == publish['status'] == receipt['status'] == 'completed'
            and publish['result'] == pin(slot/'SLOT_RESULT.json') and result['freeze_sha256'] == digest
            and receipt == result['closure'] and receipt['independent_before_after']['passed']
            and receipt['closure_verification']['passed'], 'actual_closed_slot_not_frozen/'+label)
    budget = receipt['budget']
    counts = budget['counts']
    require(not any(counts.get(key,0) for key in ('consumer_admissions','all_raster_upper','pending_raster_reservations',
                'Blender_spawned_unknown')) and budget['slots'][label]['business_admissions'] == 3,
            'actual_private_public_business_or_raster_budget_changed/'+label)
    require(receipt['runtime_close']['public_MCP_close']['production_eof_and_exit_verified']
            and receipt['runtime_close']['public_MCP_close']['exit_code']==0,
            'mcp_eof_not_confirmed/'+label)
    return receipt


def legacy_stage(stage,outer):
    return outer['started_ns'] <= stage['started_ns'] <= stage['closed_ns'] <= outer['closed_ns']


def live(label,digest):
    slot = RUN/'slots'/label
    result = read(slot/'SLOT_RESULT.json')
    close = absolute_close(slot,result,label,digest)
    arm = host.LABELS[label][1]
    term = read(slot/'TERMINAL_SOURCE.json')
    meter = read(slot/'mcp_io/REAL_HOST_STAGES.json')
    worker = read(slot/'mcp_io/RUNTIME.json')
    calls = wire_records(slot)
    stdio = {row['id']:row for row in line_records(slot/'mcp_io/MCP_IO.jsonl') if row['method']=='tools/call'}
    require(meter['pid']==worker['pid'] and meter['source_sha256']==worker['source_sha256']
            and meter['open_pause'] is None and meter['gc_before']==meter['gc_after']
            and len(calls)==len(stdio)==len(meter['requests'])==len(result['observations'])==3,
            'actual_transport_stage_denominator/'+label)
    decoder = new_decoder() if arm=='A' else None
    scores = []
    for index,(wire,client,observation) in enumerate(zip(calls,meter['requests'],result['observations'],strict=True),1):
        command = 'capture' if arm=='A' else 'capture_source_region_pair'
        production = PREVIOUS_METER['_raw_stdio'](slot,stdio[observation['response_id']])
        packet = wire['packet']
        require(client['outcome']=='success' and client['command']==wire['command']==command
                and client['host_request_id']==wire['host_id'] and client['request_bytes']==wire['tx']['bytes']
                and client['response_bytes']==wire['rx']['bytes'] and production['is_error'] is False
                and production['arguments']['include_image'] is False and production['rasters']==0,
                'actual_TCP_MCP_identity_or_budget_changed/'+label)
        require(production['tool']==('human_eye_scene_observe' if arm=='A' else host.PRIVATE_TOOL),
                'actual_public_private_dispatch_changed/'+label)
        producer = (slot/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json' if arm=='A'
                    else slot/'mcp_io'/f'PRIVATE_RESULT_{index}.json')
        result_body = read(producer)
        truth = CONTROL['normalize_result'](result_body)
        require(not result_body.get('frames') and result_body.get('read_only') is True,
                'unexpected_image_or_write_authority')
        native = wire['event']['m2_work']['native_work']
        span = client['stages']['tcp_exchange_including_outer_json']
        require(native['intervals'] and legacy_stage(native['envelope_encoding'],span),
                'actual_in_Blender_encoding_not_timed')
        if arm == 'A':
            expanded = {key:native['residency_after'][key]-native['residency_before'][key] for key in
                        ('resource_faces_read','resource_vertices_read','to_mesh','world_vertices_transformed','capture_cache_hits')}
            transmitted = packet.get('resources')
            require(type(transmitted) is list,'original_complete_capture_protocol_not_observed')
            carried = {'objects':len(transmitted),'vertices':sum(len(row['vertices_local']) for row in transmitted),
                       'triangles':sum(len(row['faces']) for row in transmitted)}
            captured = decoder.apply(packet)
            require(captured['capture_state']==result_body['binding']['capture_state']
                    and client['decoder']['resources_sent']==carried['objects'],'full_delta_binding_changed')
        else:
            expanded = packet['work']
            captured = None
            carried = {'objects':expanded['transmitted_objects'],'vertices':expanded['transmitted_vertices'],
                       'triangles':expanded['transmitted_triangles']}
            require(packet['binding']=={key:result_body['binding'][key] for key in packet['binding']}
                    and packet['payload_sha256']==result_body['payload_sha256']
                    and 'region_ref' not in result_body and 'ordered_geometry_sha256' not in packet['binding'],
                    'private_capture_escaped_scoped_binding')
        scores.append({'index':index,'query':production['arguments']['query'],'measurement':truth,
           'producer':pin(producer),'stdio':production,'host':client,'host_native':native,'transport':
               {key:wire[key] for key in ('tx','rx','command','sequence','host_id')},
           'host_wire_total_bytes':wire['tx']['bytes']+wire['rx']['bytes'],'expanded':expanded,
           'transmitted':carried,'local_stages':result_body['stages'],'wall_ns':observation['wall_ns'],
           'decoded_full':captured,'scoped_packet':packet if arm=='B' else None})
    return {'label':label,'window_ns':result['window_ns'],'calls':scores,'terminal':term,
            'before_after':close['independent_before_after'],'close':pin(slot/'HOST_RECEIPT.json'),'budget':close['budget']['slots'][label]}


def compare(asset,left,right):
    truth = read(TRUTH)['fixtures'][asset]
    require([row['query'] for row in left['calls']] == [row['query'] for row in right['calls']] ==
            [truth['requests'][0],truth['requests'][0],truth['requests'][1]],'actual_query_pair_changed/'+asset)
    doc = [row['scoped_packet']['binding']['document_epoch'] for row in right['calls']]
    scopes = [row['scoped_packet']['payload_sha256'] for row in right['calls']]
    require(len(set(doc))==1 and scopes[0]==scopes[1]!=scopes[2], 'private_repeat_or_other_region_binding_changed')
    for index,(a,b) in enumerate(zip(left['calls'],right['calls'],strict=True)):
        require(a['measurement']==b['measurement'],'private_original_exact_point_pair_or_source_changed')
        fact = a['measurement']['facts']['surface_proximity']['value']
        expected = truth['regions'][int(index==2)]
        require(math.isclose(fact['distance_m'],expected['distance_m'],rel_tol=1e-12,abs_tol=1e-10)
                and math.dist(fact['nearest_witness']['direction_a_to_b'],expected['direction']) <= 1e-6,
                'private_distance_or_direction_not_independent_truth')
        packet = b['scoped_packet']
        authored = {row['name']:row for row in right['terminal']['objects']}
        other = {row['name']:row for row in left['terminal']['objects']}
        require(all(row['evaluated']==other[name]['evaluated'] and row['visible_get'] is other[name]['visible_get']
                    and row['matrix_world']==other[name]['matrix_world'] for name,row in authored.items()),
                'cross_arm_current_source_arrays_changed')
        full = a['decoded_full']
        # The reference capture belongs to another owned Blender. Its arrays
        # are equal, while the private packet keeps this slot's actual epoch.
        full = {**full,'host_identity':{**full['host_identity'],'document_epoch':doc[index]}}
        CONTROL['prove_transmitted'](packet,right['terminal'],full,a['query'],
                 {'triangle_ids':expected['source_triangle_indices'],'vertex_ids':expected['source_vertex_indices']})
    a,b = left['calls'][0],right['calls'][0]
    return {'source_and_exact_witness_equal':True,'cold_transmission_reduced':all((
                   b['transmitted']['vertices'] < a['transmitted']['vertices'],
                   b['transmitted']['triangles'] < a['transmitted']['triangles'],
                   b['host_wire_total_bytes'] < a['host_wire_total_bytes'])),
            'complete_slot_ns':[left['window_ns'],right['window_ns']]}


def score():
    digest = verify_freeze()
    outcomes,errors = {},{}
    for label in LABELS:
        try:
            outcomes[label] = live(label,digest)
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            errors[label] = {'type':type(error).__name__,'message':str(error)}
    pairs = {}
    for asset,prefix in (('assembly','A'),('yanyite','Y')):
        if prefix+'A' in outcomes and prefix+'B' in outcomes:
            try:
                pairs[asset] = compare(asset,outcomes[prefix+'A'],outcomes[prefix+'B'])
            except (ValueError,KeyError,TypeError,IndexError) as error:
                errors[asset] = {'type':type(error).__name__,'message':str(error)}
    for row in outcomes.values():
        del row['terminal']
        for call in row['calls']:
            del call['decoded_full'],call['scoped_packet']
    report = {'freeze_sha256':digest,'passed':len(pairs)==2 and not errors and
                all(row['cold_transmission_reduced'] for row in pairs.values()),
              'pairs':pairs,'arms':outcomes,'errors':errors}
    write(RUN/'SCORE.json',report)
    print({key:report[key] for key in ('passed','pairs','errors')},flush=True)
    return int(not report['passed'])


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv)==2
            and sys.argv[1] in ('replay','score'), 'one_closed_wire_verification_mode')
    raise SystemExit(globals()[sys.argv[1]]())
