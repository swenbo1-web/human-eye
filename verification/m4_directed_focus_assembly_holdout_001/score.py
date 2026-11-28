"""Score actual directed-focus images against frozen task source rows.

This is an evidence reader. It neither starts Blender nor runs a renderer.
"""
import argparse
import base64
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys


BATCH = 'M4-DIRECTED-FOCUS-ASSEMBLY-HOLDOUT-001'
SOURCE_SHA = '00ba6e251415847878e7ed028a5ba704f6e8ee6ba4bd567dd3fea0e8076bb72e'
SOURCE_FILES = 146
FROZEN_LABELS_SHA = '03f11dae6aff1428cff5e751c959900a6be1ddaed5d6d29c05290519e991b39e'
ORDER = {'rail': ('M19', 'M21'), 'assembly': ('N19', 'N25')}
ARMS = ('auto', 'explicit')
THRESHOLD = 16
ARRAY_SHAPE = (512, 512)
TRIANGLE_SCOPE = 'zero-based-global-source-triangles-in-mesh-order'
OWNER_SCHEMA = 'active-dual-owner-v1'
PATCH_SCHEMA = 'active-patch-owner-v1'
RENDER_EVENT = 'active_observation_render_attempt'


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def fingerprint(value, *, ensure_ascii=True):
    return digest(json.dumps(value, default=str, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=ensure_ascii, allow_nan=False).encode('utf8'))


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes':len(raw),'sha256':digest(raw)}


def check_pin(info):
    p = Path(info['path'])
    need(pin(p) == {key: info[key] for key in ('bytes','sha256')}, 'historic_input_bytes_changed')
    return p


def slot_file(folder, supplied, suffix):
    p = Path(supplied)
    need(p.is_absolute() and p.suffix == suffix and p.is_file(), 'frame_file_missing_or_wrong_suffix')
    resolved = p.resolve(strict=True)
    need(resolved == p and resolved.is_relative_to(folder.resolve(strict=True))
         and resolved.is_relative_to((folder/'state.json.active_observation').resolve(strict=True))
         and not p.is_symlink(), 'frame_file_outside_current_slot')
    return resolved


def expected_domain(capture, historic):
    import numpy as np

    ident, state = capture['host_identity'], capture['capture_state']
    need(capture['source']=='blender' and capture['unit']=='m' and capture['coordinate_frame']=='world'
         and ident['capture_scope']=='complete_scene_meshes' and type(state) is dict,
         'post_capture_complete_current_source_required')
    meshes, original = capture['meshes'], historic['objects']
    need(len(meshes)==len(original) and bool(meshes), 'post_capture_complete_geometry_count_changed')
    display = capture['display_snapshot']
    need(display['status']=='captured' and display['schema']=='blender-viewport-display-v1'
         and display['scope']=='active_view_layer' and display['view_layer']['name']==historic['source']['view_layer']
         and fingerprint({k:v for k,v in display.items() if k!='sha256'},ensure_ascii=False)==display['sha256'],
         'post_capture_display_digest_or_layer_changed')
    instances = ident['object_instances']
    ids = [m['object_id'] for m in meshes]
    display_rows = {row['host_id']:row for row in display['objects']}
    need(len(ids)==len(set(ids))==len(instances)==len(display['objects'])==len(display_rows)
         and len(set(instances.values()))==len(ids) and set(ids)==set(instances)==set(display_rows),
         'post_capture_ordered_current_instance_domain_incomplete')
    keys, vertices, faces, geometry, vis = [], [], [], [], []
    for mesh, previous in zip(meshes, original, strict=True):
        oid = mesh['object_id']
        current, old = np.asarray(mesh['vertices'],dtype=np.float64),np.asarray(previous['evaluated']['vertices_world_m'],dtype=np.float64)
        need(oid==previous['object_id'] and mesh['name']==previous['name'] and current.shape==old.shape
             and np.isfinite(current).all() and current.tobytes()==old.tobytes()
             and mesh['faces']==previous['evaluated']['triangles'], 'post_capture_historic_evaluated_source_changed/'+mesh['name'])
        dr = display_rows[oid]
        need(dr['instance_id']==instances[oid] and dr['visible_get'] is previous['visible_get']
             and all(dr.get(k)==previous['display'].get(k) for k in ('hide_get','hide_viewport','hide_render')),
             'post_capture_display_participation_changed/'+mesh['name'])
        exact_points = tuple(tuple(Fraction(v) for v in point) for point in mesh['vertices'])
        def canonical_face(face):
            points = tuple(exact_points[k] for k in face)
            return min(points[i:]+points[:i] for i in range(3))
        key = (tuple(sorted(exact_points)),tuple(sorted(canonical_face(f) for f in mesh['faces'])))
        keys.append(key)
        vertices.append(exact_points)
        faces.append(mesh['faces'])
        geometry.append({'host_id':oid,'instance_id':instances[oid],'vertices':mesh['vertices'],'faces':mesh['faces']})
        vis.append(dr['visible_get'])
    offsets = np.cumsum([0,*(len(f) for f in faces)],dtype=np.int64)
    patch = fingerprint({'version':PATCH_SCHEMA,'roi_ids':[],
                  'ordered_geometry':list(zip(vertices,faces,strict=True)),
                  'face_patch_ids':[[-1]*len(face_rows) for face_rows in faces]})
    return {'capture':capture,'ids':ids,'instances':instances,'vis':vis,'offsets':offsets,
            'display_sha':display['sha256'],'patch_sha':patch,
            'owner_sha':fingerprint((OWNER_SCHEMA,TRIANGLE_SCOPE,patch,offsets.tolist())),
            'ordering_sha':fingerprint(tuple((k,oid,instances[oid]) for k,oid in zip(keys,ids,strict=True))),
            'geometry_sha':fingerprint(geometry), 'scene_sha':fingerprint(tuple(sorted(keys)))}


def observation_request(label, arm, task, request):
    query = {'mode':'active_observation','objects':[{'name':task['target']}],
             'focus':'auto' if arm=='auto' else {'source_triangle_index':task['explicit_source_triangle_index']}}
    required = {'name':'human_eye_scene_observe','arguments':{
        'query':query,'include_image':True,'response_detail':'full'}}
    need(request['jsonrpc']=='2.0' and request['method']=='tools/call'
         and request['params']==required, 'actual_request_differs_from_frozen_task/'+label)
    return query['focus']


def independent_frame(folder, frame, domain, target, task_rows, first, ref, frame_bytes):
    import numpy as np
    from PIL import Image

    png_path = slot_file(folder,frame['image_path'],'.png')
    npz_path = slot_file(folder,frame['arrays_path'],'.npz')
    image, archive = png_path.read_bytes(), npz_path.read_bytes()
    need(png_path.with_suffix('.npz')==npz_path and digest(image)==frame['image_sha256']
         and digest(archive)==frame['arrays_sha256'] and len(image)==frame['PNG_bytes']
         and len(archive)==frame['compressed_array_file_bytes'], 'original_frame_or_array_pin_mismatch')
    if frame_bytes is not None:
        need(image==frame_bytes, 'delivered_MCP_PNG_not_original_slot_PNG')
    need(frame['source_revision']==domain['capture']['revision']
         and frame['scene_identity']==domain['scene_sha']
         and frame['mesh_order_identity']==domain['ordering_sha']
         and frame['owner_mapping_identity']==domain['owner_sha']
         and frame['owner_schema']==OWNER_SCHEMA and frame['triangle_id_scope']==TRIANGLE_SCOPE
         and frame['patch_mapping_version']==PATCH_SCHEMA and frame['patch_mapping_identity']==domain['patch_sha'],
         'frame_source_geometry_order_or_owner_identity_mismatch')
    with np.load(BytesIO(archive),allow_pickle=False) as raw:
        need(len(raw.files)==len(set(raw.files)), 'duplicate_NPZ_array_names')
        if 'arrays' in frame:
            need(set(raw.files)==set(frame['arrays']), 'frame_NPZ_array_inventory_mismatch')
            for name,a in frame['arrays'].items():
                row = raw[name]
                need(a=={'dtype':str(row.dtype),'shape':list(row.shape),'nbytes':row.nbytes,
                         'sha256':digest(row.tobytes(order='C'))}, 'frame_NPZ_individual_array_pin_mismatch/'+name)
        for key,saved in (('owner_schema',OWNER_SCHEMA),('triangle_id_scope',TRIANGLE_SCOPE),
                          ('owner_mapping_identity',domain['owner_sha']),('patch_mapping_identity',domain['patch_sha']),
                          ('patch_mapping_version',PATCH_SCHEMA),('display_identity',domain['display_sha'])):
            need(raw[key].shape==() and raw[key].item()==saved,'NPZ_current_metadata_binding_changed/'+key)
        offsets, display_mask = raw['face_patch_offsets'], raw['display_object_mask']
        need(offsets.dtype==np.int64 and np.array_equal(offsets,domain['offsets'])
             and display_mask.dtype==np.bool_ and np.array_equal(display_mask,domain['vis'])
             and raw['patch_roi_ids'].size==0 and raw['face_patch_ids'].shape==(int(offsets[-1]),)
             and np.all(raw['face_patch_ids']==-1), 'NPZ_original_object_ranges_or_display_mask_changed')
        color, depth, owners, triangles = (raw[k] for k in ('color','depth','owners','triangle_ids'))
        need(color.shape==(*ARRAY_SHAPE,3) and color.dtype==np.uint8 and depth.dtype==np.float64
             and owners.dtype==triangles.dtype==np.int32
             and owners.shape==triangles.shape==depth.shape==ARRAY_SHAPE,
             'actual_RGB_float64_depth_owner_triangle_buffers_required')
        with Image.open(BytesIO(image)) as opened:
            need(opened.format=='PNG' and opened.mode=='RGB'
                 and opened.size==tuple(reversed(ARRAY_SHAPE))
                 and np.array_equal(np.asarray(opened),color), 'PNG_and_NPZ_RGB_differ')
        fg = owners>=0
        need(np.all(owners>=-1) and np.all(owners<len(domain['ids']))
             and np.array_equal(fg,triangles>=0) and np.all(triangles>=-1)
             and np.all(np.isposinf(depth[~fg])) and np.all(np.isfinite(depth[fg])&(depth[fg]>0)),
             'NPZ_common_owner_and_depth_invalid')
        winners = owners[fg]
        need(np.all(display_mask[winners]) and np.all(triangles[fg]>=offsets[winners])
             and np.all(triangles[fg]<offsets[winners+1]), 'pixel_source_triangle_is_outside_winning_object')
        image_scope = raw['image_scope_identity'].item()
        need(re.fullmatch(r'[0-9a-f]{64}',image_scope) is not None, 'NPZ_image_scope_digest_invalid')
        if 'image_scope' in frame:
            need(image_scope==frame['image_scope_identity']==fingerprint(frame['image_scope'])
                 and frame['image_scope']['participation_mask']==domain['vis']
                 and frame['image_scope']['identity']==domain['display_sha'],
                 'producer_current_image_scope_mismatch')
        sequence_text = png_path.stem.split('-',1)[0]
        need(sequence_text.isdecimal(), 'frame_sequence_path_invalid')
        frame_binding = (frame['scene_identity'],frame['candidate_identity'],domain['display_sha'],
                         image_scope,tuple(domain['vis']))
        implied_identity = fingerprint((frame_binding,OWNER_SCHEMA,domain['owner_sha'],
                                        frame['view_name'],int(sequence_text),digest(image)))
        need(frame['frame_identity']==implied_identity
             and frame['image_ref']=='source-region-image:'+fingerprint((ref['region_id'],implied_identity,digest(image))),
             'frame_identity_not_bound_to_png_NPZ_view_and_selected_source')
        target_owned = (owners==target)&np.isfinite(depth)
        local_source = triangles - int(offsets[target])
        task_pixels = int(np.count_nonzero(target_owned&np.isin(local_source, task_rows)))
        per_row = {str(i):int(np.count_nonzero(target_owned&(local_source==i))) for i in task_rows}
        first_mask = target_owned&(local_source==first)
        return ({'view':frame['view_name'],'frame_identity':implied_identity,
                 'image_ref':frame['image_ref'],'task_pixels':task_pixels,'task_pixels_by_source_row':per_row,
                 'first_source_pixels':int(np.count_nonzero(first_mask)),
                 'original_PNG':pin(png_path),'original_NPZ':pin(npz_path),
                 'actual_raster_ns':frame.get('stages',{}).get('actual_raster',{}).get('elapsed_ns')},
                first_mask,png_path,npz_path)


def trace_for(events, req_id):
    matched = [row for row in events if row.get('event')=='request_trace'
               and row.get('trace',{}).get('annotations',{}).get('mcp_request_id')==req_id]
    need(len(matched)==1, 'audit_request_trace_not_uniquely_bound')
    event = matched[0]
    related = [row for row in events if row.get('trace_id')==event['trace_id']
               and row.get('request_id')==event['request_id']]
    return event['trace'], related


def score_reply(folder, request, reply, task, row, expected_focus, domain, events, producer,
                construction=None):
    import numpy as np

    trace, related = trace_for(events,request['id'])
    renders = [event['view_name'] for event in related if event.get('event')==RENDER_EVENT]
    need(len(renders)<=2,'raster_attempt_budget_exceeded')
    out = {'status':'rejected' if reply.get('result',{}).get('isError') is True or 'error' in reply else 'observed',
           'raster_attempts':len(renders),'render_views':renders,
           'service_inclusive_ns':trace['duration_ns'],'client_rtt_ms':row.get('rtt_ms'),
           'first_source_triangle':None,'first_hit':None,'delivered_task_pixels':None,
           'delivered_hit':None,'joint_hit':None,'internal_only_hit':None,
           'render_object_hint':task['target'],'stop_reason':None}
    need(request['id']==reply['id'] and reply['jsonrpc']=='2.0', 'MCP_request_reply_id_changed')
    if out['status']=='rejected':
        text = [x.get('text') for x in reply.get('result',{}).get('content',[]) if x.get('type')=='text']
        out['stop_reason'] = 'mcp_rejected'
        out['product_rejection'] = text
        return out,set()
    result = reply['result']
    blocks = result['content']
    textual = [x for x in blocks if x['type']=='text']
    image_blocks = [x for x in blocks if x['type']=='image']
    need(len(textual)==1 and len(textual)+len(image_blocks)==len(blocks),'unexpected_directed_focus_content')
    body = json.loads(textual[0]['text'])
    focus, binding = body['facts']['focus'], body['binding']
    need(body['result_kind']=='active_observation' and body['observation_status']=='directed_focus'
         and body['read_only'] is True and body['execution_authority'] is False
         and len(body['frames'])==len(image_blocks)<=1
         and len(image_blocks)==body['image_delivery']['mcp_content_constructed_image_count']
         and len(image_blocks)==trace['annotations']['mcp_native_image_block_count'],
         'delivered_directed_read_only_frame_contract_changed')
    need(focus['selection']==expected_focus and focus['scope']=='one_current_evaluated_source_triangle'
         and focus['minimum_sample_pixels']==THRESHOLD and focus['complete_surface_visibility']=='unknown',
         'directed_focus_rule_scope_threshold_changed')
    current = domain['capture']
    need(binding['document_epoch']==current['host_identity']['document_epoch']
         and binding['capture_scope']=='complete_scene_meshes' and binding['scene_revision']==current['revision']
         and binding['capture_state']==current['capture_state'] and binding['display_identity']==domain['display_sha'],
         'focus_binding_not_same_current_closed_slot_source')
    obj = focus['object']
    index = obj['object_index']
    need(type(index) is int and 0<=index<len(domain['ids']) and domain['ids'][index]==task['host_id']==obj['host_id']
         and obj['object_name']==task['target']==current['meshes'][index]['name']
         and obj['instance_id']==domain['instances'][task['host_id']],
         'focus_target_not_same_object_instance_as_current_source')
    refs = focus['region_ref']
    first = None
    if refs is not None:
        state = current['capture_state']
        expected_generation = {key:state[key] for key in ('instance_id','epoch','revision')}
        need(refs['schema']=='human-eye-source-region-ref-v1'
             and refs['document_epoch']==binding['document_epoch'] and refs['host_id']==obj['host_id']
             and refs['instance_id']==obj['instance_id'] and refs['capture_generation']==expected_generation
             and refs['ordered_geometry_sha256']==domain['geometry_sha']
             and refs['region_id']=='source-region:'+fingerprint({k:v for k,v in refs.items() if k!='region_id'}),
             'focus_source_reference_is_stale_or_inconsistent')
        first, = refs['source_triangle_indices']
        need(type(first) is int and 0<=first<len(current['meshes'][index]['faces'])==task['total_source_triangles'],
             'focus_first_source_triangle_invalid')
        if isinstance(expected_focus,dict):
            need(first==expected_focus['source_triangle_index'],'explicit_arm_substituted_source_face')
    need(producer is not None,'private_producer_frames_missing')
    need(producer['facts']['focus']==focus and producer['binding']==binding and producer['status']==body['status']
         and producer['session_id']==body['session_id'] and producer['work']==body['work'],
         'producer_reply_focus_or_capture_binding_changed')
    all_frames = producer['constructed_frames']
    public_frames = body['frames']
    need(len(producer['frames'])==len(public_frames) and len(all_frames)<=2
         and len({f['frame_identity'] for f in all_frames})==len(all_frames),
         'private_constructed_frame_inventory_invalid')
    for raw,public in zip(producer['frames'],public_frames,strict=True):
        need(all(raw[k]==v for k,v in public.items()), 'delivered_frame_metadata_not_same_producer')
    need([f['view_name'] for f in all_frames]==[v['view_name'] for v in focus['views'] if v['verified_pixels'] is not None],
         'internal_verified_view_order_differed')
    need(body['work']['raster_attempts']==len(renders)==body['image_delivery']['new_raster_attempts']
         and body['work']['raster_completed']==len(all_frames)
         and body['image_delivery']['local_verified_image_count']==len(all_frames),
         'actual_new_raster_audit_or_private_archive_count_mismatch')
    render_attempts = [v['view_name'] for v in focus['views']]
    need(render_attempts==renders,'per_focus_render_order_differs_from_real_audit')
    if construction is not None:
        native = construction['raster_calls']
        need(construction['id']==request['id'] and construction['label']==task['target']
             and construction.get('result_recorded') is True and not construction['limit_exceeded']
             and row['new_rasters']==len(native)==len(renders)
             and row['started_ns']<=construction['service_started_ns']
             <=construction['service_returned_ns']<=row['returned_ns']
             and all(v['completed'] and construction['service_started_ns']
                     <=v['started_ns']<=v['closed_ns']<=construction['service_returned_ns']
                     for v in native), 'raw_actual_raster_calls_not_same_assigned_request_or_budget')
        out['actual_raster_calls'] = len(native)
        out['actual_raster_total_ns'] = sum(v['closed_ns']-v['started_ns'] for v in native)
    else:
        need('started_ns' not in row,'actual_raster_call_ledger_missing')
    if 'started_ns' in row and 'returned_ns' in row:
        stages = producer['stages']['service_total']
        need(row['started_ns']<=stages['started_ns']<=stages['closed_ns']<=row['returned_ns']
             and stages['elapsed_ns']==stages['closed_ns']-stages['started_ns'],
             'service_timing_not_inside_assigned_MCP_call')
        out['service_core_ns'] = stages['elapsed_ns']
    published = public_frames[0] if public_frames else None
    verified, winner, winning_mask, files = [],None,None,set()
    for raw in all_frames:
        need(refs is not None and first is not None,'constructed_frame_without_selected_source')
        is_delivered = published is not None and raw['frame_identity']==published['frame_identity']
        original_image = None
        if is_delivered:
            image, = image_blocks
            need(image['mimeType']=='image/png','delivered_tool_block_not_PNG')
            original_image = base64.b64decode(image['data'],validate=True)
        pixels, first_mask, png, npz = independent_frame(folder,raw,domain,index,
            task['source_triangle_indices'],first,refs,original_image)
        counts, = [v['verified_pixels'] for v in focus['views'] if v['view_name']==raw['view_name']]
        need(counts==pixels['first_source_pixels'],'claimed_primary_pixels_differ_from_actual_finite_depth')
        pixels['delivered'] = is_delivered
        verified.append(pixels)
        need(png not in files and npz not in files,'repeated_frame_file_in_single_request')
        files.update((png,npz))
        if is_delivered:
            winner,winning_mask = pixels,first_mask
    sample = focus['sample']
    if published is not None:
        need(winner is not None and sample is not None and
             all(sample[k]==winner[k if k!='view_name' else 'view'] for k in ('view_name','frame_identity','image_ref'))
             and sample['selected_surface_pixels']==winner['first_source_pixels']
             and published['host_binding_sha256']==binding['binding_sha256']
             and published['candidate_identity']==binding['camera_identity'],
             'delivered_sample_not_bound_to_actual_private_frame')
        anchor = sample.get('sampled_pixel')
        if winner['first_source_pixels']>0:
            need(type(anchor) is dict and anchor['source_triangle_index']==first
                 and all(type(anchor[k]) is int and 0<=anchor[k]<512 for k in ('row','column'))
                 and bool(winning_mask[anchor['row'],anchor['column']]),'reported_anchor_not_actual_primary_winning_pixel')
        else:
            need(anchor is None,'zero_primary_pixels_with_claimed_anchor')
    else:
        need(sample is None and winner is None,'hidden_delivered_result')
    reason = focus['stop_reason']
    if reason=='sample_target_met':
        need(winner is not None and winner['first_source_pixels']>=THRESHOLD,'reported_stop_target_not_met')
    if reason=='view_budget_exhausted':
        need((winner is None or winner['first_source_pixels']<THRESHOLD),'reported_exhaustion_despite_primary_threshold')
    first_hit = first in task['source_triangle_indices']
    delivered_pixels = winner['task_pixels'] if winner is not None else 0
    internal = [v['task_pixels'] for v in verified if not v['delivered']]
    out.update(first_source_triangle=first, first_hit=first_hit,
               delivered_view=winner['view'] if winner else None, delivered_task_pixels=delivered_pixels,
               delivered_primary_pixels=winner['first_source_pixels'] if winner else 0,
               delivered_hit=delivered_pixels>=THRESHOLD, joint_hit=first_hit and delivered_pixels>=THRESHOLD,
               wrong_primary_neighbor_pixels=delivered_pixels if not first_hit else 0,
               wrong_primary_neighbor_hit=not first_hit and delivered_pixels>=THRESHOLD,
               internal_only_hit=delivered_pixels<THRESHOLD and any(n>=THRESHOLD for n in internal),
               internal_only_any_pixels=delivered_pixels==0 and any(n>0 for n in internal),
               best_internal_task_pixels=max(internal,default=0),
               private_frames=verified, stop_reason=reason, product_status=body['status'])
    return out,files


def review_slot(folder, asset, arm, labels):
    expected = ORDER[asset]
    if not (folder/'ledger.json').exists():
        return {'closure_verified':False,'cases':{name:{'status':'unrun','stop_reason':'no_slot_ledger'} for name in expected}}
    ledger = read(folder/'ledger.json')
    try:
        ready,closed = read(folder/'ready.json'),read(folder/'closed.json')
        fixture = labels['assets'][asset]
        frozen_terminal = check_pin(fixture['terminal'])
        need(ledger['arm']==arm and ledger['asset'].lower()==asset and ledger['stdout_eof']
             and ledger['server_exit']==closed['blender_exit']==0
             and ready['pid']==closed['pid'] and ready['source_kind']=='installed_distribution'
             and (ready['source_sha256'],ready['source_files'])==(SOURCE_SHA,SOURCE_FILES)
             and ready['fixture_before']==closed['fixture_after']==ledger['fixture_sha']==pin(folder/'input.blend')['sha256']
             ==fixture['asset']['sha256']==pin(check_pin(fixture['asset']))['sha256'],
             'isolated_installed_slot_not_closed_or_asset_changed')
        terminal_receipt = closed['post_capture']
        terminal_path = folder/'post_capture.json'
        need(Path(terminal_receipt['path']['path'])==terminal_path and
             pin(terminal_path)=={k:terminal_receipt['path'][k] for k in ('bytes','sha256')}
             and all(row.get('returned_ns',row.get('started_ns',0))<=terminal_receipt['started_ns']
                     for row in ledger['requests'])
             and terminal_receipt['started_ns']<=terminal_receipt['closed_ns']
             <=closed['native_close_started_ns']<=closed['closed_ns']<=ledger['closed_ns'],
             'independent_post_capture_not_after_assigned_measurements')
        domain = expected_domain(read(terminal_path),read(frozen_terminal))
        audit = [json.loads(line) for line in (folder/'audit.jsonl').read_bytes().splitlines()]
        logged = [item['label'] for item in ledger['requests']]
        need(logged[:2]==['init','tools'] and tuple(logged[2:])==expected[:len(logged)-2]
             and len(logged)<=4 and len(set(logged))==len(logged),'formal_slots_duplicate_wrong_or_out_of_order_requests')
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as error:
        dispatched = {row.get('label') for row in ledger.get('requests',[])}
        return {'closure_verified':False,'cases':{name:{'status':'unverified' if name in dispatched else 'unrun',
                    'stop_reason':str(error)} for name in expected}}
    cases,files = {},set()
    count = 0
    for i,row in enumerate(ledger['requests'],1):
        name = row['label']
        try:
            prefix = folder/f'{i:02d}-{name}'
            tx,rx = (prefix.with_suffix(ext).read_bytes() for ext in ('.tx','.rx'))
            need((len(tx),digest(tx),len(rx),digest(rx))==(row['tx'],row['tx_sha'],row['rx'],row['rx_sha']),
                 'unbound_raw_MCP_TX_or_RX')
            request,reply = json.loads(tx),json.loads(rx)
            need(request['id']==reply['id']==i,'MCP_sequence_or_wire_id_mismatch')
            if name=='init':
                hello = reply['result']['_meta']['human_eye']
                need(hello['source_sha256']==SOURCE_SHA,'MCP_handshake_confirmed_different_product')
                continue
            if name=='tools':
                declaration, = [t for t in reply['result']['tools'] if t['name']=='human_eye_scene_observe']
                need('focus' in declaration['inputSchema']['properties']['query']['properties'],
                     'actual_tool_catalogue_lacks_directed_focus')
                continue
            task = labels['tasks'][name]
            need(task['asset']==asset and task['target']==name and task['explicit_source_triangle_index'] in task['source_triangle_indices'],
                 'invalid_frozen_task_source_label')
            expected_focus = observation_request(name,arm,task,request)
            producer_file = folder/f'producer_{i:02d}.json'
            producer = read(producer_file) if producer_file.is_file() else None
            construction_file = folder/f'construction_{i:02d}.json'
            construction = read(construction_file) if construction_file.is_file() else None
            result, artifacts = score_reply(folder,request,reply,task,row,expected_focus,domain,audit,
                                            producer,construction)
            need(not (artifacts&files),'frame_archive_carried_from_different_formal_request')
            result['evidence_pins'] = {'MCP_TX':pin(prefix.with_suffix('.tx')),'MCP_RX':pin(prefix.with_suffix('.rx')),
                                       **({'producer':pin(producer_file)} if producer_file.is_file() else {}),
                                       **({'actual_rasters':pin(construction_file)} if construction_file.is_file() else {})}
            cases[name] = result
            files.update(artifacts)
            count+=result['raster_attempts']
        except (ValueError,KeyError,TypeError,IndexError,OSError,OverflowError) as error:
            if name in ('init','tools'):
                return {'closure_verified':False,'cases':{n:{'status':'unverified' if n in logged else 'unrun',
                        'stop_reason':'slot_admission/'+str(error)} for n in expected}}
            cases[name] = {'status':'failed','stop_reason':str(error),'client_rtt_ms':row.get('rtt_ms')}
    for name in expected:
        cases.setdefault(name,{'status':'unrun','stop_reason':'request_not_recorded'})
    known_files = set((folder/'state.json.active_observation').glob('**/*.npz')) | set(
                     (folder/'state.json.active_observation').glob('**/*.png'))
    if all(c['status']=='observed' for c in cases.values()):
        if files != known_files or count!=sum(e.get('event')==RENDER_EVENT for e in audit):
            for c in cases.values():
                c['status'] = 'failed'
                c['stop_reason'] = 'unassigned_internal_frame_or_raster_in_closed_slot'
    return {'closure_verified':True,'cases':cases,'raster_attempts_verified':count}


def evaluate(root):
    labels_path = root/'preflight/FROZEN_TASK_LABELS.json'
    need(pin(labels_path)['sha256']==FROZEN_LABELS_SHA,'task_labels_not_the_preregistered_bytes')
    labels = read(labels_path)
    need(labels['task_order']==[task for order in ORDER.values() for task in order],'task_grid_changed')
    results = {arm:{asset:review_slot(root/'slots'/f'{asset.upper()}_{arm.upper()}',asset,arm,labels)
                    for asset in ORDER} for arm in ARMS}
    counts = {}
    for arm,assets in results.items():
        cells = [cell for group in assets.values() for cell in group['cases'].values()]
        counts[arm] = {'registered':len(cells),'audited':sum(c['status']=='observed' for c in cells),
                       'failed':sum(c['status'] not in ('observed','unrun') for c in cells),
                       'unrun':sum(c['status']=='unrun' for c in cells),
                       'first_hit':sum(c['status']=='observed' and c.get('first_hit') is True for c in cells),
                       'delivered_hit':sum(c['status']=='observed' and c.get('delivered_hit') is True for c in cells),
                       'joint_hit':sum(c['status']=='observed' and c.get('joint_hit') is True for c in cells)}
    return {'batch':BATCH,'task_labels':pin(labels_path),'minimum_task_pixels':THRESHOLD,
            'slots':results,'counts':counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--deps',type=Path,action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    sys.path[:0]=[str(p.resolve(strict=True)) for p in args.deps]
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(evaluate(args.root.resolve(strict=True)),stream,indent=2,sort_keys=True,ensure_ascii=False)
        stream.write('\n')


if __name__=='__main__':
    main()
