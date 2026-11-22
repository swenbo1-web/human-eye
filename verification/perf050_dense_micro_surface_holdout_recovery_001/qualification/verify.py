"""Admit the recovery qualification only on real closed and connected evidence."""

import base64
from pathlib import Path
from runpy import run_path
from hashlib import sha256
import json


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PRIOR = V / 'perf050_dense_micro_surface_holdout_001/qualification'
PRODUCT = run_path(str(PRIOR / 'product_qa.py'))
FRAME = run_path(str(HERE / 'frame.py'))
read, digest, require = (PRODUCT[name] for name in ('read','digest','require'))
TOOL = PRODUCT['TOOL']
NAMES = ('render_local', TOOL, 'read_images', 'read_images', TOOL)


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def within(folder, name):
    path = Path(name).resolve(strict=True)
    require(path.is_relative_to(folder.resolve(strict=True)), 'same_slot_original_path_required/' + path.name)
    return path


def closed_wire(folder):
    folder = Path(folder)
    close = read(folder / 'native/WORKER_CLOSED.json')
    runtime = read(folder / 'RUNTIME_CLOSE.json')
    native = runtime['Blender_close']
    require(runtime['Blender_status']['closed'] == close and close['poisoned'] is False
            and native['process_reaped'] is True and native['exit_code'] == 0
            and native['pid'] == close['pid'] and runtime['Blender_exit']['confirmed'] is True
            and runtime['Blender_exit']['exit_code'] == 0
            and close['closed_ns'] < runtime['Blender_exit']['observed_ns'], 'actual_owned_worker_close_and_flush_required')
    wire = folder / 'native/WIRE'
    require((wire / 'INDEX.json').is_file(), 'native_wire_not_yet_flushed')
    rows = read(wire / 'INDEX.json')
    require(type(rows) is list and rows and [row['sequence'] for row in rows] == list(range(1,len(rows)+1))
            and {item.name for item in wire.iterdir()} == {'INDEX.json',*(f'{i+1:03d}' for i in range(len(rows)))},
            'native_wire_sequence_missing_or_ambiguous')
    events = jsonl(folder / 'native/WORKER_EVENTS.jsonl')
    require([event['sequence'] for event in events] == [row['sequence'] for row in rows], 'native_wire_worker_event_sequence_changed')
    observations = {}
    for row, event in zip(rows,events,strict=True):
        entry = wire / f'{row["sequence"]:03d}'
        require({item.name for item in entry.iterdir()} == {'REQUEST.bin','RESPONSE.bin'}, 'native_wire_pair_incomplete')
        tx, rx = ((entry / file).read_bytes() for file in ('REQUEST.bin','RESPONSE.bin'))
        require(len(tx) == row['request_bytes'] > 0 and len(rx) == row['response_attempted_bytes'] > 0
                and len(tx)+len(rx) == row['request_response_attempted_bytes']
                and row['response_sendall_completed'] is True, 'native_wire_raw_length_or_flush_invalid')
        request, response = json.loads(tx),json.loads(rx)
        if request['type'] == 'execute_code':
            require(digest(request['params']['code'].encode()) == event['script_sha256'], 'native_wire_code_did_not_match_worker')
        observations[row['sequence']] = {'request':request,'response':response,'raw_tx_sha256':digest(tx),
                                         'raw_rx_sha256':digest(rx),'worker_event':event}
    last = observations[rows[-1]['sequence']]
    require(last['request'] == {'type':'close'} and last['response'] == native['response']
            and last['response']['status'] == 'closed', 'native_wire_final_close_receipt_changed')
    return observations


def rpc_pair(root, receipt, request, response):
    directory = root / f'rpc_{receipt["index"]:02d}'
    tx, rx = ((directory / file).read_bytes() for file in ('TX.bin','RX.bin'))
    require(read(directory / 'RECEIPT.json') == receipt and len(tx) == receipt['TX_bytes']
            and len(rx) == receipt['RX_bytes'] and digest(rx) == receipt['RX_sha256']
            and receipt['error'] is None and json.loads(tx) == request and json.loads(rx) == response,
            'original_public_RPC_pair_changed/' + root.name)
    return tx, rx


def public_calls(folder, result):
    order = result.get('diagnostic_calls') or []
    pending = result.get('qualification_pending') or {}
    require([row['name'] for row in order] == list(NAMES) and pending.get('phase') == 'public_calls_completed_pending_owned_close'
            and pending.get('passed') is False, 'closed_QP_required_business_sequence_incomplete')
    require(read(folder/'QUALIFICATION_PENDING.json') == pending, 'original_pending_receipt_changed')
    refs = pending['read_refs']
    require(set(refs) == {'S021','S055'} and len(set(refs.values())) == 2, 'two_original_public_same_slot_refs_required')
    args = ({'direction':'TOP','view_span_m':0}, PRODUCT['DISCOVER'], {'refs':[refs['S021']]}, {'refs':[refs['S055']]}, PRODUCT['MEASURE'])
    archive = folder / 'client/attachments'
    bridge, = list(archive.glob('bridge_*'))
    endpoint_close = read(bridge/'EXIT.json')
    require(endpoint_close['normal_exit'] is True and endpoint_close['attempts'] == len(NAMES), 'original_consumer_bridge_close_failed')
    proof = []
    for index,(row,name,arguments) in enumerate(zip(order,NAMES,args,strict=True),1):
        call = folder / 'client' / f'call_{index:02d}'
        req, res, receipt = (read(call / name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        expected = {'jsonrpc':'2.0','id':f'qualification-{index}','method':'tools/call',
                    'params':{'name':name,'arguments':arguments}}
        require(row['index'] == index and req == expected and digest((call/'REQUEST.json').read_bytes()) == row['request_sha256']
                and digest((call/'RESPONSE.json').read_bytes()) == row['response_sha256'] and res['id'] == req['id']
                and res['result']['isError'] is (index==1), 'actual_business_request_or_rejection_recovery_changed')
        tx, rx = rpc_pair(folder/'client/transport',receipt,req,res)
        br = bridge / f'{receipt["index"]:03d}'
        bt, brx = ((br/file).read_bytes() for file in ('TX.bin','RX.bin'))
        require(bt == tx and brx == rx, 'transparent_consumer_bridged_wire_changed')
        owner = folder / 'owner' / f'tool_{index:02d}'
        a,b,c = (read(owner / name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(a == req and b == res and c['attempt'] == index and c['RPC_id'] == req['id'], 'actual_owner_business_pair_changed')
        proof.append({'request':req,'response':res['result'],'owner':owner,'TX_sha256':digest(tx),'RX_sha256':digest(rx)})
    return proof, refs


def product_result(folder, observed, ordinal):
    call = folder / 'product_calls' / f'call_{ordinal:03d}'
    request,response,receipt = (read(call/file) for file in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
    tx, rx = rpc_pair(folder/'mcp',receipt,request,response)
    require(request['params'] == observed['request']['params'] and response['result'] == observed['response']
            and read(observed['owner']/'PRODUCT_REQUEST.json') == request
            and read(observed['owner']/'PRODUCT_RESPONSE.json') == response,
            'original_installed_MCP_forwarding_changed')
    counters = [row for row in jsonl(folder/'mcp_io/MCP_IO.jsonl') if row['sequence']==receipt['index']]
    row, = counters
    require(row['TX_bytes']==len(tx) and row['TX_sha256']==digest(tx)
            and row['RX_text_UTF8_LF_sha256']==digest(rx.replace(b'\r\n', b'\n')),
            'actual_installed_MCP_original_wire_hash_changed')
    before, after = ((call/file).read_bytes() for file in ('ARCHIVE_BEFORE.bin','ARCHIVE_AFTER.bin'))
    entries = [json.loads(line) for line in after[len(before):].splitlines() if line.strip()]
    require(after.startswith(before) and len(entries) == 1, 'original_producer_archive_delta_not_unique')
    original, = entries
    attached = read(observed['owner']/'PRODUCT_RECEIPT.json')['producer_archive']
    require(attached['index'] == original['index'] == ordinal and attached['sha256']==original['sha256']
            and attached['path']==original['path'] and original['new_observations_for_archive']==0
            and receipt['started_ns'] <= original['started_ns'] <= original['producer_returned_ns'] <= original['saved_ns']
            <= receipt['received_complete_ns'], 'archived_producer_not_bound_to_original_request')
    producer = within(folder, original['path'])
    require(digest(producer.read_bytes()) == original['sha256'] and original in jsonl(folder/'product_full/INDEX.jsonl'),
            'actual_producer_digest_mismatch')
    return read(producer), row['raster_actual']


def current_capture_for(commands, captures, wire, producer):
    # Only genuine host capture requests in the measured producer stage can supply source arrays.
    stage = producer['stages']['host_capture']
    capture_calls = [item for item in commands if item['command']['command'] in ('capture','capture_scene')]
    require(len(capture_calls) == len(captures), 'current_capture_wire_to_payload_pairing_changed')
    choices = []
    for item, capture in zip(capture_calls,captures,strict=True):
        event = wire[item['wire_sequence']]['worker_event']
        if stage['started_ns'] <= event['started_ns'] and event['started_ns']+event['elapsed_ns'] <= stage['closed_ns']:
            choices.append((item,capture))
    require(len(choices)==1, 'actual_producer_host_capture_not_uniquely_within_origin_request')
    item,capture = choices[0]
    details = producer['binding']
    require(capture['capture_state'] == details['capture_state'] and capture['revision']==details['scene_revision']
            and capture['host_identity']['document_epoch']==details['document_epoch'], 'producer_capture_current_binding_changed')
    return item,capture


def discovery(folder, result, producer, source, capture, *, downloads=None):
    """Verify actual product rows and mixed inline media against a closed host capture."""
    packet = PRODUCT['body'](result)
    decode = run_path(str(V/'m4_dense_region_brief_001/checks/brief_schema.py'))['decode_body']
    rows_raw = decode(packet,len(result['content']))['region_task']
    rows = rows_raw['rows']
    by_name = {row['object_name']:row for row in rows}
    target = PRODUCT['TARGET']
    require(rows_raw['conditions']==PRODUCT['CONDITIONS'] and rows_raw['summary']['source_triangle_count']==6162
            and set(by_name)==set(PRODUCT['CENTERS']) and len(rows)==len(by_name)==3
            and rows_raw['summary']['observed_region_count']==2 and rows_raw['summary']['unknown_region_count']==1
            and all(row['center_world_m']==PRODUCT['CENTERS'][row['object_name']] and row['front_direction_world']==[0,0,1]
                    and row['source_triangle_indices']==[0,1] for row in rows)
            and by_name[target]['reason']=='positive_area_occlusion_all_front_views'
            and set(by_name[target]['view_reasons']['positive_area_occlusion'])==set(PRODUCT['VIEWS']),
            'actual_product_discovery_candidate_geometry_or_unknown_changed')
    meshes = {mesh['name']:mesh for mesh in capture['meshes']}
    for row in rows:
        mesh = meshes[row['object_name']]
        require(row['source']['ordered_geometry_sha256']==FRAME['fingerprint']({'vertices':mesh['vertices'],'faces':mesh['faces']}),
                'public_discovery_row_ordered_source_digest_changed')
    table = PRODUCT['tables']
    scopes = table(packet['scopes'], ['scope_id','camera_identity','binding_sha256','constructed_frame_count',
                                     'locally_covered_region_count'])
    frames = table(packet['frames'], ['scope_index','view_name','frame_identity','image_ref','image_sha256','native_content_block_index'])
    objects = table(packet['objects'], ['object_index','host_id','instance_id','object_name'])
    binding = producer['binding']
    require(objects==binding['objects'] and packet['binding']['capture_state']==binding['capture_state']
            and packet['binding']['document_epoch']==binding['document_epoch']
            and scopes[packet['blocker_evidence']['scope_index']]['scope_id']=='global', 'public_discovery_parent_capture_changed')
    blockers = PRODUCT['verify_blockers'](packet,rows,objects,capture)

    original_frames = {frame['frame_identity']:frame for frame in producer['frames']}
    original_scopes = {scope['scope_id']:scope for scope in producer['scopes']}
    device_frames = {row['frame_identity']:row for row in read(folder/'DEVICE_EVIDENCE.json')['frames']}
    require(3 <= len(frames) <= 6 and len(frames)==len(original_frames)==len(producer['frames'])==producer['work']['raster_attempts']
            and {row['frame_identity'] for row in frames}==set(original_frames)
            and set(original_scopes)=={row['scope_id'] for row in scopes}
            and original_scopes['global']['binding']==binding, 'product_discovery_frame_count_or_scope_changed')
    geom = FRAME['NATIVE']['certify_geometry'](source)

    def verify_image(row, target_name, content=None):
        identity = row['frame_identity']
        original = original_frames[identity]
        scoped = scopes[row['scope_index']]
        scope_id = scoped['scope_id']
        scope = original_scopes[scope_id]
        parent = binding if scope_id != 'global' else None
        require(identity in scope['frame_refs'] and scoped['binding_sha256']==scope['binding']['binding_sha256']
                and scoped['camera_identity']==scope['binding']['camera_identity']
                and original['scope_id']==scope_id and original['image_ref']==row['image_ref']
                and original['view_name']==row['view_name'] and original['image_sha256']==row['image_sha256'],
                'public_original_frame_scope_or_camera_changed')
        photo = FRAME['prove_frame'](folder,device_frames[identity],original,scope['binding'],capture,source,target_name,
                                     content,geometry=geom,parent=parent)
        index = row['native_content_block_index']
        require(type(index) is int and 0 < index < len(result['content']), 'public_mixed_image_index_missing')
        image = result['content'][index]
        require(image['type']=='image' and image['mimeType']=='image/png'
                and digest(base64.b64decode(image['data'],validate=True))==photo['sha256'], 'original_inline_PNG_changed')
        return photo

    global_frame, = [row for row in frames if scopes[row['scope_index']]['scope_id']=='global' and row['view_name']=='SCENE']
    shortfall = verify_image(global_frame,'S021')
    require(shortfall['geometrically_unoccluded'] and shortfall['all_corners_in_frame'] and not shortfall['pixel_gate_passed'],
            'actual_global_open_patch_must_show_pixel_shortfall')
    images = {}
    for name in ('S021','S055'):
        witness = by_name[name]['complete_witness']
        require(witness is not None and (name!='S021' or witness['scope_id']!='global')
                and (name!='S055' or witness['view_name'] not in ('SCENE','TOP')), 'complete_scope_or_view_not_changed/' + name)
        row, = [row for row in frames if row['frame_identity']==witness['frame_identity']]
        require(witness['scope_id']==scopes[row['scope_index']]['scope_id'] and row['image_ref']==witness['image_ref']
                and row['view_name']==witness['view_name'], 'published_local_witness_mixed_frame_changed/' + name)
        images[name] = image = verify_image(row,name,downloads[name] if downloads else None)
        require(image['complete'], 'original_complete_local_frame_pixel_or_geometry_failed/' + name)
    return {'images':images,'shortfall':shortfall,'blockers':blockers,'source_capture_state':binding['capture_state'],
            'observed_regions':len(rows),'raster_attempts':len(frames)}


def verify_closed(folder, result):
    folder = Path(folder).resolve(strict=True)
    calls,refs = public_calls(folder,result)
    closed = result['closure_verification']
    runtime = read(folder/'RUNTIME_CLOSE.json')
    worker_wire = closed_wire(folder)
    require(closed.get('passed') is True and closed.get('status')=='ready_closed'
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0
            and runtime['public_MCP_close']['confirmed'] and runtime['public_MCP_close']['exit_code']==0
            and runtime['public_MCP_exit']['confirmed'] and runtime['public_MCP_exit']['exit_code']==0
            and result['independent_before_after']['passed'] and not result['actual_model_admitted']
            and result['model_consumers']==result['paid_API_calls']==0, 'closed_QP_lifecycle_or_readonly_not_proven')
    ordinary, measured = (read(folder/name) for name in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
    require(ordinary['source']==measured['source'] and ordinary['objects']==measured['objects']
            and ordinary['display_object_mask']==measured['display_object_mask'] and ordinary['source']['pid']==closed['pid']
            and ordinary['source']['asset_sha256']==result['asset_sha256']
            and digest(Path(ordinary['source']['asset_copy']).read_bytes())==result['asset_sha256'],
            'closed_QP_native_capture_source_or_display_changed')

    discovery_producer, discovery_rasters = product_result(folder,calls[1],1)
    measurement_producer, measurement_rasters = product_result(folder,calls[4],2)
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    install = read(V/'m4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json')
    audit = oracle['Audit']()
    captures, commands = oracle['decode_captures'](folder,install,audit)
    d_row,d_capture = current_capture_for(commands,captures,worker_wire,discovery_producer)
    m_row,m_capture = current_capture_for(commands,captures,worker_wire,measurement_producer)
    require(d_row['wire_sequence'] < m_row['wire_sequence']
            and d_capture['capture_state'] == m_capture['capture_state']
            and d_capture['display_snapshot'] == m_capture['display_snapshot']
            and d_capture['meshes'] == m_capture['meshes'], 'selected_distance_lost_actual_same_generation_capture')
    oracle['source_binding_checks'](d_capture,discovery_producer['binding'],install,audit)
    product_geometry = discovery(folder,calls[1]['response'],discovery_producer,measured,d_capture,
                                 downloads={name:calls[i]['response'] for i,name in ((2,'S021'),(3,'S055'))})
    require(refs=={name:row['ref'] for name,row in product_geometry['images'].items()}
            and discovery_rasters==product_geometry['raster_attempts'] and measurement_rasters==0
            and result['budget']['counts']['all_raster_actual']==discovery_rasters
            and result['budget']['counts']['pending_raster_reservations']==0,
            'public_readback_reference_or_budget_attempts_changed')
    measurement = PRODUCT['verify_measurement'](calls[4]['response'],measurement_producer,discovery_producer['binding'])
    backing = measurement_producer['binding']
    require(backing['display_identity']==m_capture['display_snapshot']['sha256']
            and backing['runtime_source_sha256']==install['source_sha256']
            and backing['objects']==discovery_producer['binding']['objects']
            and backing['capture_scope']=='complete_scene_meshes', 'selected_measurement_whole_reference_capture_not_bound')
    output = folder / 'closed_qualification_CLI'
    output.mkdir(exist_ok=True)
    cli = {label:PRODUCT['check_cli'](calls[index]['response'],output,label) for index,label in
           ((1,'discovery'),(2,'read_S021'),(3,'read_S055'),(4,'measurement'))}
    require(all(row['passed'] for row in cli.values()), 'actual_closed_QP_required_CLI_evidence_clipped')
    return {'passed':True,'closure_bound':True,'images':product_geometry['images'],'discovery':product_geometry,
            'measurement':measurement,'CLI':cli,'capture_wire_sequence':{'discovery':d_row['wire_sequence'],'measurement':m_row['wire_sequence']},
            'outer_calls':[{key:row[key] for key in ('TX_sha256','RX_sha256')} for row in calls],
            'original_wire_index_sha256':digest((folder/'native/WIRE/INDEX.json').read_bytes())}
