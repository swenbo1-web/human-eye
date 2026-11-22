"""Independently bind current region witness, constructed frame, native block and path."""

import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
PRIOR = V/'m1_region_task_witness_image_path_001'
RECOVERY = V/'m1_region_task_first_packet_consumption_holdout_recovery_001'
CROSS = V/'m4_cross_scale_live_task_formal_001'
DENSE = V/'perf050_dense_micro_surface_holdout_recovery_001'
BRIEF = 'active-observation-region-task-brief-v2'
TARGETS = ('M02','M09')
CONDITIONS = {'area_min_m2':1/128,'area_max_m2':1/32,'normal_z_min':.75}
PIXEL_KEYS = ('visible_surface_pixels','contrasting_boundary_pixels','visible_pixel_bounds','visible_pixel_anchor')
WRONG_WITNESS = 'public_witness_wrong_producer_scope_frame'


def require(ok,why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def pin(path,slot=None):
    path = Path(path).resolve(strict=True)
    require(slot is None or path.is_relative_to(Path(slot).resolve()),'artifact_outside_owned_slot')
    raw = path.read_bytes()
    return {'path':path.as_posix(),'bytes':len(raw),'sha256':digest(raw)}


@lru_cache(maxsize=None)
def module(path):
    return run_path(str(path))


def result(reply):
    result = reply['result'] if 'result' in reply else reply
    require(result.get('isError') is False and result['content'],'actual_public_reply_not_successful')
    return result


def body(reply):
    first = result(reply)['content'][0]
    require(first['type']=='text','missing_original_public_fact_body')
    return json.loads(first['text'])


def rows(table):
    columns = table['columns']
    require(type(columns) is list and len(columns)==len(set(columns)),'bad_compact_table_columns')
    return [dict(zip(columns,row,strict=True)) for row in table['rows']]


def frame_rows(device,slot):
    if device is None:
        device = read(Path(slot)/'DEVICE_EVIDENCE.json')
    if hasattr(device,'by_ref'):
        return device.by_ref
    if 'frames' not in device:
        return device
    result = {row['ref']:row for row in device['frames']}
    require(len(result)==len(device['frames']),'duplicate_current_device_frame_ref')
    return result


def bind_original(frame,slot,registry):
    current = registry[frame['image_ref']]
    require(current['ref']==frame['image_ref'] and current['frame_identity']==frame['frame_identity']
            and current['scope_id']==frame['scope_id'] and current['view_name']==frame['view_name']
            and current['PNG_sha256']==frame['image_sha256']
            and Path(current['PNG']).resolve(strict=True)==Path(frame['image_path']).resolve(strict=True),
            'device_original_frame_scope_ref_or_path_changed')
    proof = pin(current['PNG'],slot)
    require(proof['sha256']==frame['image_sha256'] and proof['bytes']==frame['PNG_bytes'],
            'device_current_original_png_bytes_changed')
    return proof


def bound_path(declared,frame,scope,producer,slot,registry):
    proof = bind_original(frame,slot,registry)
    require(type(declared) is str and declared==proof['path'],
            'path_not_canonical_spelling_of_this_current_frame')
    path = Path(declared)
    base = Path(slot).resolve(strict=True)
    parts = path.relative_to(base).parts
    generation = path.parent.parent
    supported = {Path(row['image_path']).parent.parent.resolve(strict=True)
                 for row in producer['constructed_frames']}
    ordinal = scope['frame_refs'].index(frame['frame_identity'])+1
    require(path.is_absolute() and path.resolve(strict=True).as_posix()==declared and path.is_file()
            and len(parts)==4 and parts[0].endswith('.active_observation')
            and re.fullmatch('[0-9a-f]{32}',parts[1]) and parts[2]==scope['binding']['binding_sha256']
            and re.fullmatch(f'{ordinal:03d}-[0-9a-f]{{24}}[.]png',parts[3])
            and supported=={generation}, 'path_is_not_scope_local_current_construction_file')
    return proof


def verify_public_witnesses(reply,producer,*,slot,device=None,require_paths=False):
    """Validate current v2 source ownership before considering an optional local path."""
    content = result(reply)['content']
    packet = body(reply)
    require(packet.get('schema')==BRIEF and packet['read_only'] is True and packet['execution_authority'] is False,
            'actual_task_reply_is_not_read_only_region_brief')
    decoder = module(V/'m4_dense_region_brief_001/checks/brief_schema.py')['decode_body']
    decoded = decoder(packet,len(content))['region_task']
    expanded = decoded['rows']
    constructed,selected = producer['constructed_frames'],producer['frames']
    frames,scopes = (rows(packet[key]) for key in ('frames','scopes'))
    originals = {row['frame_identity']:row for row in constructed}
    selected_by_id = {row['frame_identity']:(i,row) for i,row in enumerate(selected,1)}
    require(len(originals)==len(constructed)==len(frames)
            and len(selected_by_id)==len(selected)==len(content)-1
            and all(originals.get(k)==v[1] for k,v in selected_by_id.items()),
            'constructed_and_delivered_sets_do_not_share_original_frames')
    scoped = {row['scope_id']:row for row in producer['scopes']}
    require(len(scoped)==len(producer['scopes'])==len(scopes)
            and set(scoped)=={row['scope_id'] for row in scopes},
            'actual_public_and_producer_scope_roster_differs')
    require(rows(packet['objects'])==producer['binding']['objects']
            and all(producer['binding'].get(k)==v for k,v in packet['binding'].items()),
            'compact_scope_current_capture_or_object_indices_disagree')
    registry = frame_rows(device,slot)
    native, constructed_only = {}, []
    for index,(public,frame) in enumerate(zip(frames,constructed,strict=True)):
        scope = scopes[public['scope_index']]
        actual = scoped[scope['scope_id']]
        sid = actual['scope_id']
        require(sid==frame['scope_id'] and scope['binding_sha256']==actual['binding']['binding_sha256']
                ==frame['host_binding_sha256'] and scope['camera_identity']==actual['binding']['camera_identity']
                and all(public[k]==frame[k] for k in ('view_name','frame_identity','image_ref','image_sha256')),
                'public_constructed_frame_does_not_bind_own_scope_ref_view_or_sha')
        actual_selected = selected_by_id.get(frame['frame_identity'])
        block = public['native_content_block_index']
        require(block==(actual_selected[0] if actual_selected is not None else None),
                'public_native_block_index_not_own_selected_frame')
        if block is None:
            constructed_only.append(index)
            continue
        item = content[block]
        require(item['type']=='image' and item['mimeType']=='image/png',
                'public_delivered_frame_does_not_address_PNG_block')
        data = base64.b64decode(item['data'],validate=True)
        original = bind_original(frame,slot,registry)
        require(digest(data)==original['sha256'] and len(data)==original['bytes'],
                'actual_native_PNG_block_does_not_match_owned_original')
        native[index] = {'frame':frame,'scope':actual,'block':block,'file':original}
    require(len(native)==len(selected),'not_every_current_PNG_block_is_bound_once')
    original_task = producer['facts']['region_task']
    original_regions = {r['roi_id']:r for r in original_task['rows']}
    require(len(original_regions)==len(original_task['rows'])==len(expanded)
            and original_regions.keys()=={r['roi_id'] for r in expanded}
            and decoded['conditions']==original_task['conditions'] and decoded['summary']==original_task['summary'],
            'public_region_inventory_invalid_for_current_producer')
    witness_rows = {row['region_index']:row for row in rows(packet['witnesses'])}
    eligible,verified = set(),[]
    lookup = module(RECOVERY/'checks/evidence.py')['scoped_witness_pixel']
    for index,region in enumerate(expanded):
        original = original_regions[region['roi_id']]
        keys = ('object_name','object_index','instance_id','host_id','source_triangle_indices',
                'source','status','reason','view_reasons','center_world_m')
        require(all(region[k]==original[k] for k in keys),'public_ROI_is_not_bound_to_producer')
        real,published = original['complete_witness'],region['complete_witness']
        if real is None:
            require(published is None and index not in witness_rows,'displayed_witness_has_no_original_ROI_evidence')
            continue
        public = witness_rows[index]
        frame_index = public['frame_index']
        identity = ('scope_id','frame_identity','image_ref','view_name','selected_for_delivery')
        require(published is not None and all(real[k]==published[k] for k in identity)
                and constructed[frame_index]['frame_identity']==real['frame_identity'],WRONG_WITNESS)
        require(real['pixel_row_index']==public['pixel_row_index'],'wrong_current_public_witness_pixel_row_index')
        # A witness is a fact about a constructed frame. Publication is checked separately.
        pixel = lookup({**producer,'frames':constructed},real,original['roi_id'])
        require(all(pixel[k]==public[k] for k in PIXEL_KEYS),'public_witness_pixels_not_current_scope_ROI')
        require((frame_index in native) is real['selected_for_delivery'],'public_witness_selection_status_disagrees')
        summary = {'object_name':region['object_name'],'roi_id':region['roi_id'],'region_index':index,'frame_index':frame_index,
                   'pixel_row_index':public['pixel_row_index'],**{k:published[k] for k in identity},
                   'native_content_block_index':published['native_content_block_index'],
                   'visible_surface_pixels':pixel['visible_surface_pixels'],
                   'contrasting_boundary_pixels':pixel['contrasting_boundary_pixels']}
        verified.append(summary)
        if frame_index in native and real['scope_id']!='global':
            eligible.add(frame_index)
    paths = {}
    if 'witness_image_paths' in packet:
        table = packet['witness_image_paths']
        require(table['columns']==['frame_index','local_image_path'] and table['rows'],
                'path_table_empty_or_wrong_columns')
        for record in rows(table):
            i = record['frame_index']
            require(type(i) is int and i in eligible and i not in paths,
                    'path_frame_not_unique_delivered_complete_local_witness')
            item = native[i]
            original = bound_path(record['local_image_path'],item['frame'],item['scope'],producer,slot,registry)
            paths[i] = {'frame_index':i,'ref':item['frame']['image_ref'],**original}
    if require_paths:
        require(len(eligible)==2 and paths.keys()==eligible,'first_packet_missing_two_owned_complete_witness_paths')
    return {'public_witnesses':verified,'constructed_count':len(constructed),'selected_count':len(selected),
            'constructed_not_delivered_indices':constructed_only,
            'allowed_path_indices':sorted(eligible),'first_packet_path_originals':list(paths.values()),
            'original_images':[{'frame_index':i,'ref':item['frame']['image_ref'],
                'scope_id':item['frame']['scope_id'],'view':item['frame']['view_name'],
                'frame_identity':item['frame']['frame_identity'],'native_content_block_index':item['block'],**item['file']}
                               for i,item in native.items()]}


def verify_read_images(slot,reply,producer,refs,*,device=None):
    """Bind original read_images captions, paths and PNG blocks as a separate route."""
    content = result(reply)['content']
    require(len(content)==2*len(refs)==2*len(set(refs)),'ordinary_read_images_original_count_or_refs_changed')
    selected = {item['image_ref']:item for item in producer['frames']}
    registry = frame_rows(device,slot)
    verified = []
    for ref,caption,image in zip(refs,content[::2],content[1::2],strict=True):
        require(ref in selected and caption['type']=='text' and caption['text'].startswith(ref+' ')
                and image['type']=='image' and image['mimeType']=='image/png',
                'ordinary_read_images_caption_or_frame_not_own_selected_original')
        declared = json.loads(caption['text'].split('\n',1)[1])
        frame = selected[ref]
        file = bind_original(frame,slot,registry)
        raw = base64.b64decode(image['data'],validate=True)
        require(declared['local_image_path']==file['path'] and declared['image_sha256']==file['sha256']
                and digest(raw)==file['sha256'] and len(raw)==file['bytes'],
                'ordinary_read_images_does_not_read_own_original')
        verified.append({'ref':ref,'frame_identity':frame['frame_identity'],'scope_id':frame['scope_id'],
                         'view':frame['view_name'],**file})
    return verified


def truth(source, pinned=None):
    frozen = module(CROSS/'scoring/formal.py')['truth']() if pinned is None else pinned
    legacy = type(frozen['eligible']) is list
    asset_sha = frozen['asset_sha256'] if legacy else frozen['sources']['asset']['sha256']
    require(asset_sha==source['source']['asset_sha256'],'wrong_fixed_cross_scale_asset')
    objects = {item['name']:item for item in source['objects']}
    regions = {}
    for region in frozen['eligible'] if legacy else frozen['eligible'].values():
        name = region['object_name']
        points = objects[name]['evaluated']['vertices_world_m']
        ids = region['boundary_loops'][0] if legacy else region['corner_vertex_indices']
        corners = [points[index] for index in ids]
        require(legacy or corners==region['corners_world_m'],'actual_frozen_source_corners_changed/'+name)
        regions[name] = {**region,'directions':region['finite_direction_proofs'],'corners':corners}
    require(set(regions)=={'M02','M06','M09'} and len(objects)==len(source['objects'])==21
            and frozen['counts']=={'objects':21,'vertices':148,'triangles':184}
            and sum(len(row['evaluated']['vertices_world_m']) for row in objects.values())==148
            and sum(len(row['evaluated']['triangles']) for row in objects.values())==184,
            'actual_cross_scale_fixture_or_eligible_truth_changed')
    return {**frozen,'asset_sha256':asset_sha,'regions':regions}


def capture(slot,producer,source,binding):
    handle = module(V/'m4_cross_scale_discovery_001/oracle/check_saved.py')
    installed = binding if isinstance(binding,dict) else read(binding)
    audit = handle['Audit']()
    captured,_ = handle['decode_captures'](Path(slot),installed,audit)
    current = handle['current_capture'](captured,producer['binding'],audit)
    handle['source_binding_checks'](current,producer['binding'],installed,audit)
    geometry = {row['object_id']:row for row in source['objects']}
    require(len(geometry)==len(current['meshes']) and all(
        row['name']==geometry[row['object_id']]['name']
        and row['vertices']==geometry[row['object_id']]['evaluated']['vertices_world_m']
        and row['faces']==geometry[row['object_id']]['evaluated']['triangles']
        for row in current['meshes']),'producer_capture_not_same_current_independent_meshes')
    return current


def product_frame(slot,frame,producer,current,source,target,geometry):
    scope, = [row['binding'] for row in producer['scopes'] if row['scope_id']==frame['scope_id']]
    original, = [row for row in producer['constructed_frames'] if row['image_ref']==frame['ref']]
    prove = module(DENSE/'qualification/frame.py')['prove_frame']
    return prove(slot,frame,original,scope,current,source,target,geometry=geometry,
                 parent=producer['binding'] if frame['scope_id']!='global' else None)


def verify_discovery(slot,reply,producer,source,*,binding,require_paths=False,device=None,pinned_truth=None,require_local=True):
    """Return the two actually delivered complete originals and the finite coverage limit."""
    typed = verify_public_witnesses(reply,producer,slot=slot,device=device,require_paths=require_paths)
    geometry = truth(source,pinned_truth)
    current = capture(slot,producer,source,binding)
    own = {row['object_name']:row for row in producer['facts']['region_task']['rows']}
    require(len(own)==len(producer['facts']['region_task']['rows'])==3 and own.keys()==geometry['regions'].keys()
            and producer['facts']['region_task']['conditions']==CONDITIONS,
            'current_scope_or_candidate_roster_misses_frozen_task')
    for name,row in own.items():
        expected = geometry['regions'][name]
        require(row['source_triangle_indices']==expected['source_triangle_indices']
                and tuple(map(F,row['center_world_m']))==tuple(map(F,expected['center_world_m'])),
                'current_requested_face_or_world_center_changed/'+name)
    unknown = own['M06']
    require(unknown['status']=='unknown' and unknown['complete_witness'] is None
            and unknown['reason']=='positive_area_occlusion_all_front_views'
            and set(unknown['view_reasons']['positive_area_occlusion'])==geometry['directions'].keys()
            and not geometry['regions']['M06']['eligible_complete_views'],
            'current_six_direction_unknown_or_its_cause_not_supported')
    registry = frame_rows(device,slot)
    qualified = []
    for name in TARGETS:
        witnessed, = [row for row in typed['public_witnesses'] if row['object_name']==name]
        proof = product_frame(slot,registry[witnessed['image_ref']],producer,current,source,name,geometry)
        require(witnessed['selected_for_delivery'] and proof['complete']
                and (not require_local or proof['scope_id']!='global')
                and proof['selected_surface_pixels']==witnessed['visible_surface_pixels']
                and proof['contrasting_boundary_pixels']==witnessed['contrasting_boundary_pixels'],
                'real_current_positive_witness_image_is_not_complete/'+name)
        original, = [row for row in typed['original_images'] if row['ref']==witnessed['image_ref']]
        qualified.append({'object_name':name,**original,'independent_pixels':proof})
    require(len({item['ref'] for item in qualified})==len(qualified)==2,'two_distinct_local_witnesses_required')
    if require_paths:
        require({row['ref'] for row in typed['first_packet_path_originals']}=={row['ref'] for row in qualified},
                'first_packet_paths_not_own_two_complete_originals')
    return {**typed,'delivered_original_images':typed['original_images'],'original_images':qualified,
            'unknown':{'object_name':'M06','scope':'registered_finite_views',
                       'views':unknown['view_reasons']['positive_area_occlusion'],'reason':unknown['reason']}}
