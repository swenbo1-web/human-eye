"""Bind world-box replay to the two original bilateral product transactions."""

import ast
import json
from pathlib import Path
import re
from runpy import run_path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
SOURCE_GIT = '25e82445e1b4385033b2e60fd92f0f54c6178318'
BASE_GIT = '4104add44251b03a1eafc5af69502aa2575b632c'
BASE_SOURCE = '5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9'
BASE_BINDING = V/'m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json'
ORIGIN = Path('D:/he_m4_yanyite_bilateral_region_native_001')
RECORD = V/'m4_yanyite_bilateral_region_native_001/RESULT.json'
BASE_EVIDENCE = '48899b41f592fc60b266b4b278bd7e4b9d5c8daa'
PREVIOUS_INPUTS = V/'m2_source_region_shared_normalization_001/harness/inputs.py'
GEOMETRY_HELPER = V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py'
ORACLE_PATH = V/'m4_yanyite_dual_curved_region_native_001/score/oracle.py'
original = run_path(str(GEOMETRY_HELPER))
read, write, pin, digest, require, committed, verify_geometry = (
    original[key] for key in ('read', 'write', 'pin', 'digest', 'require', 'committed', 'verify_geometry')
)
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
REGIONS = ('left', 'right')
BOXES = (
    {'min': [-.10,-.09,.65], 'max': [-.025,.09,.80]},
    {'min': [ .025,-.09,.65], 'max': [ .10, .09,.80]},
)
EXPECTED = ((178,125,.20166015758396572), (155,98,.20019531184902473))
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'


def source_paths():
    return (Path(__file__), BASE_BINDING, RECORD, PREVIOUS_INPUTS, GEOMETRY_HELPER, ORACLE_PATH)


def load_previous(name='dual'):
    return run_path(str(PREVIOUS_INPUTS))['sealed_inputs'](name)


def recorded_delta(slot, key, count, index, take):
    folder = slot/'native/WIRE'/key
    tx, rx = (take(folder/name) for name in ('REQUEST.bin', 'RESPONSE.bin'))
    request, response = json.loads(tx), json.loads(rx)
    expression = re.search(r'^_request = _json.loads\((.+)\)$', request['params']['code'], re.MULTILINE)
    require(expression is not None and request['type']=='execute_code', 'original_native_capture_dispatch_changed')
    sent = json.loads(ast.literal_eval(expression[1]))
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    stdout = response['result']['result']
    require(response['status']=='success' and response['result']['executed'] is True
            and stdout.startswith(prefix) and len(stdout.splitlines())==1, 'original_native_response_not_fixed_envelope')
    outer = json.loads(stdout[len(prefix):])
    packet = outer['result']
    wire = {row['sequence']:row for row in index}[int(key)]
    require(sent['id']==outer['id'] and sent['command']=='capture' and sent['params']=={}
            and packet['schema']=='human-eye-scene-delta-v1' and len(packet['resources'])==count
            and wire['response_sendall_completed'] is True and wire['request_bytes']==len(tx)
            and wire['response_attempted_bytes']==len(rx), 'original_native_capture_or_wire_count_changed/'+key)
    return packet, {'wire':key, 'command':sent['command'], 'params':sent['params'], 'host_request_id':sent['id'],
                    'TX':digest(tx), 'RX':digest(rx), 'resource_count':count}


def installed_decoder(binding_path, pins):
    require(Path(binding_path).resolve(strict=True)==BASE_BINDING.resolve(strict=True)
            and BASE_BINDING.read_bytes()==committed(BASE_BINDING, BASE_EVIDENCE), 'fixed_4104add4_decoder_binding_required')
    binding = read(binding_path)
    require(binding['preparation_git']==BASE_GIT and binding['source_sha256']==BASE_SOURCE
            and len(binding['source_manifest'])==143, 'fixed_4104add4_decoder_identity_required')
    name = 'human_eye_plugin/scene_residency.py'
    wheel = Path(binding['wheel_path'])
    decoder = Path(binding['install_root'])/name
    actual, wheel_pin = pin(decoder), pin(wheel)
    expected, = [row for row in binding['source_manifest'] if row['path']==name]
    require(actual['sha256']==expected['sha256'] and wheel_pin['sha256']==binding['wheel_sha256'],
            'installed_decoder_or_accepted_wheel_changed')
    with ZipFile(wheel) as pack:
        require(pack.read(name)==decoder.read_bytes(), 'accepted_decoder_wheel_bytes_changed')
    pins.extend((actual, wheel_pin))
    # The installed decoder has no package imports. Load it privately so this
    # proof cannot pre-populate the later isolated product worker's modules.
    return run_path(str(decoder))['SceneDeltaDecoder']()


def original_transactions(slot, take, previous):
    read_raw = lambda path: json.loads(take(path))
    lines = lambda path: [json.loads(line) for line in take(path).splitlines()]
    worker_rows = {row['id']: row for row in lines(slot/'mcp_io/MCP_IO.jsonl') if row['method']=='tools/call'}
    traces = {row['trace']['trace_id']:row['trace'] for row in lines(slot/'product_audit.jsonl')
              if row['event']=='request_trace'}
    cli_bindings = read_raw(slot/'consumer/BUSINESS_SOURCE_BINDING.json')
    require(not cli_bindings['binding_errors'], 'old_cli_delivery_bindings_not_reconciled')
    cli_items = [row['item'] for row in lines(slot/'consumer/stdout.raw.bin')
                 if row['type']=='item.completed' and row['item']['type']=='mcp_tool_call']
    for pos, attempt in enumerate((4,5),1):
        public = previous['tools'][attempt-1]
        require(public['attempt']==attempt and public['tool']=='human_eye_scene_observe', 'old_product_attempt_index_changed')
        outer_tx, outer_rx = (take(Path(public[key]['path'])) for key in ('TX','RX'))
        outer_request, outer_response = map(json.loads,(outer_tx,outer_rx))
        owner = slot/'owner'/f'tool_{attempt:02d}'
        outer_owner = read_raw(owner/'REQUEST.json')
        outer_result = read_raw(owner/'RESPONSE.json')
        require(outer_request==outer_owner and outer_response==outer_result, 'old_owner_forwarded_request_or_response_changed')
        cli, = [row for row in cli_bindings['result_contracts'] if row['attempt']==attempt]
        args = outer_request['params']['arguments']
        delivered = cli_items[attempt-1]
        require(cli['TX_sha256']==digest(outer_tx)['sha256']==public['TX']['sha256']
                and cli['RX_sha256']==digest(outer_rx)['sha256']==public['RX']['sha256']
                and delivered['tool']=='human_eye_scene_observe' and delivered['arguments']==args
                and delivered['result']['content']==outer_response['result']['content'], 'old_consumer_attempt_or_delivery_changed')

        receipt = read_raw(owner/'PRODUCT_RECEIPT.json')
        inner = slot/'mcp'/f"rpc_{receipt['receipt']['index']:02d}"
        tx, rx = (take(inner/key) for key in ('TX.bin','RX.bin'))
        request, response = map(json.loads,(tx,rx))
        producer_path = slot/'product_full'/f'call_{pos:03d}'/'SERVICE_RESULT.json'
        producer_bytes = take(producer_path)
        producer = json.loads(producer_bytes)
        worker = worker_rows[request['id']]
        rx_lf = rx[:-2]+b'\n' if rx.endswith(b'\r\n') else rx
        require(ticket_ok(read_raw(inner/'RECEIPT.json'), receipt['receipt'], request, worker, tx, rx, rx_lf)
                and receipt['index']==pos and receipt['id']==request['id']==response['id']
                and request==read_raw(owner/'PRODUCT_REQUEST.json')
                and response==read_raw(owner/'PRODUCT_RESPONSE.json')
                and args==request['params']['arguments']==read_raw(owner/'PRODUCT_ARGUMENTS.json')
                and response['result']==outer_response['result'] and response['result']['isError'] is False
                and receipt['producer_archive']['sha256']==digest(producer_bytes)['sha256']
                and Path(receipt['producer_archive']['path'])==producer_path
                and receipt['producer_archive']['new_observations_for_archive']==0,
                'old_product_call_or_same_producer_archive_unbound')
        trace = traces[producer['request_trace']['trace_id']]
        blocks = response['result']['content']
        require(trace['outcome']=='complete' and trace['request_id']==producer['request_trace']['request_id']
                and trace['annotations']['mcp_request_id']==request['id']
                and len(blocks)==1 and blocks[0]['type']=='text' and worker['raster_actual']==0,
                'old_producer_or_brief_response_not_observed')
        yield request, response, producer, json.loads(blocks[0]['text'])


def ticket_ok(actual, repeated, request, worker, tx, rx, rx_lf):
    return (actual==repeated and worker['id']==worker['response_id']==request['id']==actual['id']
            and actual['error'] is None and actual['TX_bytes']==worker['TX_bytes']==len(tx)
            and worker['TX_sha256']==digest(tx)['sha256'] and actual['RX_bytes']==len(rx)
            and actual['RX_sha256']==digest(rx)['sha256'] and worker['RX_text_UTF8_LF_bytes']==len(rx_lf)
            and worker['RX_text_UTF8_LF_sha256']==digest(rx_lf)['sha256'])


def verify_selection(request, producer, brief, current, terminal, box, expected, oracle):
    objects = {mesh['name']:mesh for mesh in current['meshes']}
    target, cube = (objects[name] for name in (TARGET,'Cube'))
    detached = {obj['name']: obj['evaluated'] for obj in terminal['objects']}
    truth = oracle['region_truth'](target['vertices'], target['faces'], cube['vertices'], cube['faces'],
                                   (box['min'],box['max']))
    host_truth = oracle['region_truth'](detached[TARGET]['vertices_world_m'], detached[TARGET]['triangles'],
        detached['Cube']['vertices_world_m'], detached['Cube']['triangles'], (box['min'],box['max']))
    faces = truth['triangle_ids']
    vertices = truth['vertex_ids']
    require(host_truth['triangle_ids']==faces and host_truth['vertex_ids']==vertices
            and (len(faces),len(vertices),truth['distance_m'])==expected,
            'binary64_and_native_world_selection_not_the_frozen_bilateral_truth')
    args = request['params']['arguments']
    ref = producer['region_ref']
    binding = producer['binding']
    public = brief['task_result']
    full = producer['task_result']
    region = producer['facts']['region']
    mapping = producer['source_mapping']
    indexed_faces = [target['faces'][i] for i in faces]
    require(request['params']['name']=='human_eye_scene_observe' and args=={'query':{'mode':'source_region',
                'region':{'object':{'name':TARGET},'source_triangle_indices':faces},'reference':{'name':'Cube'},
                'requested_facts':['surface_proximity']},'include_image':False}
            and producer['read_only'] is brief['read_only'] is True
            and producer['execution_authority'] is brief['execution_authority'] is False
            and binding['unit']==public['unit']==current['unit']=='m'
            and binding['coordinate_frame']==public['coordinate_frame']==current['coordinate_frame']=='world'
            and current['capture_state']==binding['capture_state']
            and ref['capture_generation']=={k:current['capture_state'][k] for k in ('instance_id','epoch','revision')}
            and full['binding']==binding and brief['region_ref']==full['region_ref']==ref
            and binding['capture_scope']=='complete_scene_meshes'
            and full['measurement_scope']==public['measurement_scope']==SCOPE
            and ref['source_triangle_indices']==mapping['submesh_to_source_triangle_indices']==faces
            and mapping['submesh_to_source_vertex_indices']==vertices
            and mapping['index_domain']==region['index_domain']==INDEX_DOMAIN
            and mapping['triangles_source_vertices']==indexed_faces
            and [[vertices[i] for i in row] for row in mapping['triangles_submesh_vertices']]==indexed_faces
            and region['source_triangle_indices']==faces and region['source_vertex_indices']==vertices
            and brief['region']['source_triangle_count']==len(faces) and brief['region']['source_vertex_count']==len(vertices)
            and producer['frames']==brief['images']==[], 'old_query_scope_ordered_region_or_binding_changed')
    fact = full['facts']['surface_proximity']
    value = fact['value']
    witness = value['nearest_witness']
    require(public['facts']['surface_proximity']==fact and fact['status']=='measured'
            and value['distance_m']==truth['distance_m'] and witness['direction_a_to_b']==truth['direction_world']
            and witness['a']==truth['source_point_world_m'] and witness['b']==truth['reference_point_world_m']
            and public['reference']==full['reference'] and full['reference']['object_id']==cube['object_id']
            and binding['image_scope']['participation_mask']==terminal['display_object_mask']==[True,False],
            'old_measurement_missing_or_hidden_reference_changed')
    return truth


def load_bilateral(binding_path=BASE_BINDING):
    """Use the exact left/right no-image product requests and complete/zero-resource captures."""
    require(RECORD.read_bytes()==committed(RECORD, SOURCE_GIT), 'prior_bilateral_registered_result_changed')
    prior = read(RECORD)
    slot = ORIGIN/'slots/P1'
    index_path = ORIGIN/'sealed/RAW_INDEX.json'
    index = read(index_path)
    archive_path = ORIGIN/'sealed/ORIGINAL_RUNTIME.zip'
    archive_pin = pin(archive_path)
    require(index['archive']==prior['raw_evidence_local']==archive_pin
            and index['member_count']==prior['raw_member_count']==len(index['members'])==887
            and prior['product']['commit']==BASE_GIT and prior['product']['source_sha256']==BASE_SOURCE
            and prior['pair']['P1']['score']=={'passed':17,'total':17}, 'prior_bilateral_archive_git_control_failed')
    pins = [pin(path) for path in (*source_paths(), index_path)] + [archive_pin]
    decoder = installed_decoder(binding_path, pins)
    oracle = run_path(str(ORACLE_PATH))

    with ZipFile(archive_path) as pack:
        def take(path):
            path = Path(path).resolve(strict=True)
            require(path.is_relative_to(slot.resolve()), 'prior_raw_input_outside_registered_slot')
            key = path.relative_to(ORIGIN.resolve()).as_posix()
            raw = path.read_bytes()
            actual = digest(raw)
            require(index['members'][key]==actual and pack.read(key)==raw, 'old_bilateral_archive_member_changed/'+key)
            pins.append({'path':str(path), **actual})
            return raw

        result_bytes = take(slot/'SLOT_RESULT.json')
        result = json.loads(result_bytes)
        end = json.loads(take(slot/'SLOT_PUBLICATION.json'))
        close = json.loads(take(slot/'mcp/HELD_CLOSE.json'))
        terminal_raw = take(slot/'TERMINAL_SOURCE.json')
        terminal = json.loads(terminal_raw)
        require(end['result_sha256']==digest(result_bytes)['sha256'] and end['status']==result['status']=='completed'
                and result['closure_verification']['passed'] is True and result['independent_before_after']['passed'] is True
                and result['terminal_source']['sha256']==digest(terminal_raw)['sha256']
                and result['product_source_sha256']==BASE_SOURCE and close['confirmed'] is True
                and close['production_eof_and_exit_verified'] is True and close['exit_code']==0,
                'prior_bilateral_slot_or_product_process_not_closed')
        wire_index = json.loads(take(slot/'native/WIRE/INDEX.json'))
        probe = json.loads(take(slot/'mcp_io/REAL_HOST_STAGES.json'))
        require(probe['source_sha256']==BASE_SOURCE and len(probe['requests'])==2, 'prior_native_request_meter_changed')
        deltas, transport = zip(*(recorded_delta(slot,key,count,wire_index,take) for key,count in zip(('003','004'),(2,0),strict=True)),strict=True)
        calls, responses, producers, briefs = zip(*original_transactions(slot,take,prior['pair']['P1']),strict=True)
        truth = []
        for packet, wire, meter, call, producer, brief, box, expected in zip(deltas,transport,probe['requests'],calls,
                 producers,briefs,BOXES,EXPECTED,strict=True):
            current = decoder.apply(packet)
            verify_geometry(current,terminal)
            span = producer['stages']['host_capture']
            host = meter['stages']['host_request']
            require(meter['host_request_id']==wire['host_request_id'] and meter['command']=='capture'
                    and meter['request_bytes']==wire['TX']['bytes'] and meter['outcome']=='success'
                    and meter['decoder']['resources_sent']==wire['resource_count']
                    and meter['decoder']['capture_state']==current['capture_state']
                    and span['started_ns']<=host['started_ns']<=host['closed_ns']<=span['closed_ns'],
                    'actual_capture_not_inside_same_producer_service')
            truth.append(verify_selection(call,producer,brief,current,terminal,box,expected,oracle))
        require(deltas[0]['capture']==deltas[1]['capture']
                and set(deltas[0]['live_resources'])==set(deltas[1]['live_resources'])
                and truth[0]['distance_m']>=.201>truth[1]['distance_m'], 'old_current_shared_generation_or_threshold_changed')
    return {'name':'bilateral','source_dimensions':[2,27312,53276],'original_slot':str(slot),'terminal':terminal,
            'producer':producers[0],'producers':list(producers),'frames':[],'deltas':list(deltas),
            'transport':list(transport),'calls':list(calls),'responses':list(responses),'boxes':list(BOXES),
            'regions':list(REGIONS),'truth':dict(zip(REGIONS,truth,strict=True)),
            'capture_plan':[(packet,{'command':'capture','params':{}},terminal) for packet in deltas],
            'source_pins':list({row['path']:row for row in pins}.values())}


if __name__=='__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    fixture = load_bilateral()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write(args.output,{'passed':True, 'regions':fixture['regions'], 'truth':fixture['truth'],
                       'boxes':fixture['boxes'], 'transport':fixture['transport'], 'source_pins':fixture['source_pins'],
                       'actual_Blender_starts':0, 'actual_models':0})
