"""Bind published region witnesses and optional paths to their own original frames."""

import base64
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path


V = Path(__file__).resolve().parents[2]
RECOVERY = V / 'm1_region_task_first_packet_consumption_holdout_recovery_001'
BRIEF = 'active-observation-region-task-brief-v2'
WITNESS_BINDING_ERROR = 'public_witness_wrong_producer_scope_frame'
PIXEL_FIELDS = ('visible_surface_pixels', 'contrasting_boundary_pixels',
                'visible_pixel_bounds', 'visible_pixel_anchor')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def records(value):
    columns = value['columns']
    require(type(columns) is list and len(columns)==len(set(columns)), 'bad_public_table_column_names')
    require(type(value['rows']) is list, 'bad_public_table_rows')
    return [dict(zip(columns,row,strict=True)) for row in value['rows']]


@lru_cache(maxsize=None)
def module(path):
    return run_path(str(path))


def _raw_result(reply):
    view = reply['result'] if 'result' in reply else reply
    require(view.get('isError') is False and view['content'] and view['content'][0]['type']=='text',
            'no_successful_public_region_task_evidence')
    return view


def _path_proof(path,frame,slot,authoritative_paths):
    require(slot is not None and authoritative_paths is not None,
            'optional_witness_path_has_no_authoritative_original')
    known = authoritative_paths.get(frame['image_ref'])
    require(known is not None, 'optional_witness_path_has_no_authoritative_original')
    evidence = {'path':str(known)} if isinstance(known,(str,Path)) else known
    require(type(path) is str and path, 'optional_witness_path_is_not_a_file_string')
    original = Path(frame['image_path']).resolve(strict=True)
    registered = Path(evidence['path']).resolve(strict=True)
    root = Path(slot).resolve(strict=True)
    require(original.is_relative_to(root) and registered==original,
            'optional_witness_path_wrong_original_slot_or_generation')
    require(path==original.as_posix() and path==Path(path).resolve(strict=True).as_posix()
            and original.is_file(), 'optional_witness_path_wrong_or_noncanonical')
    raw = original.read_bytes()
    checksum = digest(raw)
    require(checksum==frame['image_sha256'] and len(raw)==frame['PNG_bytes']
            and evidence.get('sha256',checksum)==checksum and evidence.get('bytes',len(raw))==len(raw),
            'optional_witness_path_does_not_read_original_PNG')
    return {'path':path,'bytes':len(raw),'sha256':checksum}


def verify_public_witnesses(reply, producer, *, slot=None, authoritative_paths=None, require_paths=False):
    """Verify the compact packet against a current producer and, if present, original paths.

    A caller enabling paths supplies a separately bound publication/read-back map of
    image_ref to path or path/sha256/bytes receipt from the same owned slot.
    """
    view = _raw_result(reply)
    body = json.loads(view['content'][0]['text'])
    require(body.get('schema')==BRIEF and body['read_only'] is True
            and body['execution_authority'] is False, 'wrong_public_evidence_schema_or_read_only_scope')
    evidence = module(RECOVERY/'checks/evidence.py')
    decode = module(V/'m4_dense_region_brief_001/checks/brief_schema.py')['decode_body']
    regions = decode(body,len(view['content']))['region_task']['rows']
    scopes = records(body['scopes'])
    frames = records(body['frames'])
    witnesses = records(body['witnesses'])
    original_rows = producer['facts']['region_task']['rows']
    original_regions = {row['roi_id']:row for row in original_rows}
    original_frames = producer['frames']
    original_scopes = {scope['scope_id']:scope for scope in producer['scopes']}
    require(len(original_regions)==len(original_rows)==len(regions)
            and {row['roi_id'] for row in regions}==original_regions.keys(),
            'public_region_roster_not_current_producer')
    require(len(original_scopes)==len(producer['scopes'])==len(scopes)
            and {scope['scope_id'] for scope in scopes}==original_scopes.keys(),
            'public_scopes_do_not_match_producer')
    require(all(producer['binding'].get(key)==value for key,value in body['binding'].items())
            and records(body['objects'])==producer['binding']['objects'],
            'public_source_binding_or_object_indices_changed')
    for scope in scopes:
        original = original_scopes[scope['scope_id']]['binding']
        require(all(scope[key]==original[key] for key in ('binding_sha256','camera_identity')),
                'public_scope_not_own_producer_binding')
    require(len(frames)==len(original_frames), 'public_frames_do_not_match_producer')
    native = []
    for composed_index,(published,source) in enumerate(zip(frames,original_frames,strict=True)):
        scope = scopes[published['scope_index']]
        require(scope['scope_id']==source['scope_id']
                and scope['binding_sha256']==source['host_binding_sha256']
                and all(published[key]==source[key] for key in ('frame_identity','view_name','image_ref','image_sha256')),
                'public_frame_not_own_producer_scope_ref_view_or_SHA')
        block_index = published['native_content_block_index']
        if block_index is None:
            continue
        block = view['content'][block_index]
        require(block['type']=='image' and block['mimeType']=='image/png','public_frame_index_does_not_address_native_PNG')
        data = base64.b64decode(block['data'],validate=True)
        require(digest(data)==source['image_sha256'] and len(data)==source['PNG_bytes'],
                'public_native_PNG_differs_from_own_producer_frame')
        native.append(block_index)
    require(native==list(range(1,len(view['content']))), 'public_native_block_order_not_current_producer_order')
    checked = []
    eligible = {}
    by_region = {row['region_index']:row for row in witnesses}
    for index,region in enumerate(regions):
        original = original_regions[region['roi_id']]
        keys = ('object_name','object_index','host_id','instance_id','source','source_triangle_indices','status','reason','view_reasons')
        require(all(region[key]==original[key] for key in keys), 'public_witness_region_not_own_producer_ROI')
        published = region['complete_witness']
        raw_witness = original['complete_witness']
        if raw_witness is None:
            require(published is None and index not in by_region, 'public_witness_exists_for_unverified_region')
            continue
        require(published is not None and index in by_region, 'public_witness_missing_current_complete_ROI')
        witness = by_region[index]
        frame_index = witness['frame_index']
        require(all(published[key]==raw_witness[key] for key in
                    ('scope_id','frame_identity','image_ref','view_name','selected_for_delivery'))
                and original_frames[frame_index]['frame_identity']==raw_witness['frame_identity'],
                WITNESS_BINDING_ERROR)
        require(published['pixel_row_index']==raw_witness['pixel_row_index'],
                'public_witness_wrong_current_pixel_row_index')
        pixel = evidence['scoped_witness_pixel'](producer,raw_witness,original['roi_id'])
        require(all(witness[key]==pixel[key] for key in PIXEL_FIELDS),
                'public_witness_pixels_do_not_match_own_scoped_ROI')
        checked.append({'object_name':region['object_name'],'roi_id':original['roi_id'],'region_index':index,
                        'frame_index':frame_index,'scope_id':published['scope_id'],'frame_identity':published['frame_identity'],
                        'image_ref':published['image_ref'],'view_name':published['view_name'],
                        'pixel_row_index':published['pixel_row_index'],
                        'native_content_block_index':published['native_content_block_index']})
        if published['selected_for_delivery'] and published['scope_id']!='global':
            eligible[frame_index] = original_frames[frame_index]
    paths = {}
    if 'witness_image_paths' in body:
        table = body['witness_image_paths']
        require(table['columns']==['frame_index','local_image_path'] and bool(table['rows']),
                'optional_witness_path_table_wrong_schema_or_empty')
        for row in records(table):
            index = row['frame_index']
            require(type(index) is int and index in eligible,
                    'optional_witness_path_does_not_refer_to_delivered_complete_local_frame')
            require(index not in paths,'optional_witness_path_has_duplicate_frame_index')
            proof = _path_proof(row['local_image_path'],eligible[index],slot,authoritative_paths)
            paths[index] = {'frame_index':index,'image_ref':eligible[index]['image_ref'],**proof}
    if require_paths:
        require(bool(eligible) and paths.keys()==eligible.keys(),'missing_path_for_delivered_complete_local_frame')
    return {'passed':True,'public_witnesses':checked,
            'eligible_unique_path_frame_indices':sorted(eligible),
            'paths':list(paths.values()),'original_native_PNG_blocks':len(native)}
