"""Verify current-slot geometry, delivered images, owner rows and qualification replies."""

import argparse
from base64 import b64decode
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import sys

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from oracle import ASSET, TARGET, REFERENCE, REPO, digest, history, load, pin, require, verify_closed_source, write

CLI_ORACLE = REPO/'verification/m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'


def receipt(slot, path, sha):
    actual = pin(path)
    require(Path(actual['path']).is_relative_to(slot) and actual['sha256']==sha,
            'artifact_not_original_same_slot/'+str(path))
    return actual


def canonical_sha(value):
    return digest(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,
                             allow_nan=False).encode())['sha256']


def near_point(a,b,tol=1e-7):
    return isinstance(a,(list,tuple)) and len(a)==3 and all(
        type(x) in (int,float) and abs(x-y)<=tol for x,y in zip(a,b,strict=True))


def project_to_feature(point, points, tolerance):
    vertices=np.asarray(points,dtype=np.float64)
    a=vertices[0]
    if len(vertices)==1:
        return near_point(point,a,tolerance)
    edges=(vertices[1:]-a).T
    coordinates=np.linalg.lstsq(edges,np.asarray(point)-a,rcond=None)[0]
    return bool(np.min(coordinates)>=-1e-8 and np.sum(coordinates)<=1+1e-8
                and near_point(point,a+edges@coordinates,tolerance))


def numeric_pair(dist, direction, a, b, truth, tolerance=1e-7):
    require(type(dist) in (int,float) and abs(dist-truth['distance_m'])<=tolerance
            and near_point(direction,[0,0,1],tolerance)
            and all(type(value) in (int,float) for value in (*a,*b)) and len(a)==len(b)==3
            and near_point(b,[a[0],a[1],1],tolerance) and
            any(project_to_feature(a,item['vertices_world_m'],tolerance) for item in truth['attaining_features']),
            'pair_not_current_attaining_selected_surface_to_Cube')


def actual_calls(slot):
    owner=slot/'owner'
    fifo={}
    for folder in sorted(owner.glob('rpc_*')):
        rx,tx=folder/'TCP_RX.bin',folder/'TCP_TX.bin'
        if not (rx.is_file() and tx.is_file()):
            continue
        envelope,return_envelope=load(tx),load(rx)
        require(envelope['request_id']==return_envelope['request_id'] and return_envelope['ok'] is True,
                'owner_envelope_or_closed_response_changed')
        request=envelope.get('args',{}).get('message',{})
        response=return_envelope['result']
        if request.get('method')=='tools/call':
            require(request['id']==response['id'] and request['id'] not in fifo,
                    'owner_raw_transaction_id_conflict')
            fifo[request['id']]=(request,response,pin(tx),pin(rx))
    calls=[]
    for folder in sorted(owner.glob('tool_*')):
        request,response,rec=(load(folder/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        raw_request,raw_response,tx,rx=fifo[request['id']]
        # Some bridge releases decorate broker-only params with an attempt separately.
        require(raw_request['id']==request['id']==response['id']==rec['RPC_id']
                and raw_request['params']['name']==request['params']['name']==rec['name']
                and raw_request['params'].get('arguments',{})==request['params'].get('arguments',{})
                and raw_response==response,'owner_tool_wire_not_actual_closed_exchange')
        result=response['result']
        images=[(index,b64decode(block['data'],validate=True)) for index,block in enumerate(result['content'])
                if block['type']=='image']
        body=[block['text'] for block in result['content'] if block['type']=='text']
        calls.append({'attempt':rec['attempt'],'name':rec['name'],'folder':folder,'request':request,
                      'reply':response,'is_error':result['isError'],'images':images,'text':body,'TX':tx,'RX':rx})
    require(calls and len(calls)==len(fifo),'missing_same_slot_business_wire')
    return calls


def source_binding(frame,slot,terminal,device,upper):
    objects=terminal['objects']
    if frame['origin']=='common_native':
        resource,=[row for row in device['sources'] if row['source_ref']==frame['source_ref']]
        reported=receipt(slot,resource['path'],resource['sha256'])
        current=load(Path(reported['path']))
        require(not resource['terminal'] and resource['status']=='complete' and
                current['source']==terminal['source'],'native_image_current_source_missing')
        for source,terminal_object in zip(current['objects'],objects,strict=True):
            require(all(source[key]==terminal_object[key] for key in
                        ('name','instance_id','object_id','matrix_world','visible_get'))
                    and all(source[key]==terminal_object['evaluated'][nested] for key,nested in
                            (('vertices','vertices_world_m'),('vertices_local','vertices'),('triangles','triangles'))),
                    'native_image_current_geometry_or_display_changed')
        require(frame['scope_id'].startswith('local:'),'native_image_is_not_rendered_local_scope')
        return {'scope_id':frame['scope_id'],'original_source':reported}

    require(frame['origin']=='product','frame_origin_unsupported')
    entry=frame['full_result']
    report=receipt(slot,entry['path'],entry['sha256'])
    full=load(Path(report['path']))
    require(full['result_kind']=='source_region' and full['read_only'] is True and full['execution_authority'] is False,
            'product_frame_not_current_readonly_source_region')
    player,=[row for row in full['frames'] if row['image_ref']==frame['ref']]
    require(player==frame['producer'] and player['frame_identity']==frame['frame_identity']
            and player['image_sha256']==frame['PNG_sha256'] and player['arrays_sha256']==frame['NPZ_sha256'],
            'product_frame_is_not_its_own_producer')
    target,cube=({o['name']:o for o in objects}[name] for name in (TARGET,REFERENCE))
    parent,region=full['binding'],full['region_ref']
    records=[{'host_id':o['object_id'],'instance_id':o['instance_id'],
              'vertices':o['evaluated']['vertices_world_m'],'faces':o['evaluated']['triangles']} for o in objects]
    require(parent['capture_scope']=='complete_scene_meshes' and parent['coordinate_frame']=='world' and parent['unit']=='m'
            and parent['ordered_geometry_sha256']==region['ordered_geometry_sha256']==canonical_sha(records)
            and region['host_id']==target['object_id'] and region['instance_id']==target['instance_id']
            and region['source_triangle_indices']==upper['triangle_ids']
            and parent['image_scope']['participation_mask']==terminal['display_object_mask']
            and player['image_scope']['participation_mask']==terminal['display_object_mask']
            and player['host_binding_sha256']==parent['binding_sha256'] and player['source_revision']==parent['scene_revision'],
            'product_image_capture_or_upper_region_binding_changed')
    return {'scope_id':'source_region','region_ref':region['region_id'],'original_source':report}


def frame_truth(frame,slot,terminal,device,upper,calls):
    png=receipt(slot,frame['PNG'],frame['PNG_sha256'])
    archive=receipt(slot,frame['NPZ'],frame['NPZ_sha256'])
    current=source_binding(frame,slot,terminal,device,upper)
    require(png['bytes']==frame['PNG_bytes'] and archive['bytes']==frame['NPZ_bytes'],'frame_byte_counts_changed')
    objects=terminal['objects']
    offsets=terminal['source_face_offsets']
    mask=terminal['display_object_mask']
    for name,key in (('object_names','name'),('object_ids','object_id'),('object_instance_ids','instance_id')):
        require(frame[name]==[o[key] for o in objects],'frame_object_domain_changed/'+name)
    require(frame['display_object_mask']==mask and frame['source_face_offsets']==offsets,'frame_display_or_face_offsets_changed')
    pixels=Path(png['path']).read_bytes()
    with np.load(Path(archive['path']),allow_pickle=False) as saved:
        tri,owners,depth,color=(saved[key] for key in ('triangle_ids','owners','depth','color'))
        require(saved['face_patch_offsets'].tolist()==offsets,'NPZ_face_offsets_changed')
        if 'display_object_mask' in saved:
            require(saved['display_object_mask'].tolist()==mask,'NPZ_display_mask_changed')
        else:
            require(frame['origin']=='product','native_NPZ_lacks_display_mask')
    w,h=frame['size_px']
    with Image.open(BytesIO(pixels)) as display:
        require(display.format=='PNG' and display.size==(w,h) and
                np.array_equal(np.asarray(display.convert('RGB')),color),'closed_PNG_differs_from_saved_RGB')
    require(tri.shape==owners.shape==depth.shape==(h,w) and color.shape==(h,w,3)
            and tri.dtype==owners.dtype==np.dtype('int32') and color.dtype==np.dtype('uint8')
            and np.all((tri>=-1)&(tri<offsets[-1])),'NPZ_type_shape_or_source_faces_changed')
    foreground=tri>=0
    remap=np.full((h,w),-1,dtype=np.int32)
    remap[foreground]=np.searchsorted(offsets[1:],tri[foreground],side='right')
    require(np.array_equal(remap,owners) and np.all(np.asarray(mask)[remap[foreground]])
            and np.all(np.isfinite(depth[foreground]) & (depth[foreground]>0))
            and np.all(np.isposinf(depth[~foreground])),'current_triangle_object_mask_or_depth_invalid')
    target_index=[o['name'] for o in objects].index(TARGET)
    target=tri[remap==target_index]-offsets[target_index]
    counts=np.bincount(target,minlength=offsets[target_index+1]-offsets[target_index])
    observed={i:int(counts[i]) for i in upper['triangle_ids'] if counts[i]>0}
    require(observed,'local_frame_has_no_pixels_from_upper_selection')
    delivery=[]
    for call in calls:
        # Accept an exact public PNG only when the same reply binds the reference or
        # the actual read_images request requested that reference.
        matched_ref=any(frame['ref'] in text or Path(png['path']).as_posix() in text for text in call['text'])
        if call['name']=='read_images':
            matched_ref |= frame['ref'] in call['request']['params']['arguments'].get('refs',[])
        blocks=[i for i,value in call['images'] if value==pixels]
        if not call['is_error'] and matched_ref and blocks:
            require(len(blocks)==1,'original_PNG_public_block_ambiguous')
            delivery.append({'attempt':call['attempt'],'public_block_index':blocks[0],
                             'wire_RX':call['RX'],'wire_TX':call['TX']})
    require(bool(delivery),'PNG_not_actually_delivered_with_own_current_reference')
    return {'ref':frame['ref'],'frame_identity':frame['frame_identity'],'view':frame['view_name'],
            'origin':frame['origin'],'source':current,'public_delivery':delivery,'PNG':png,'NPZ':archive,
            'upper_triangle_pixel_counts':observed,
            'upper_sampled_triangles':len(observed),'upper_unsampled_triangles':len(upper['triangle_ids'])-len(observed),
            'upper_selected_pixels':sum(observed.values()),'actual_sample_scope_only':True}


def json_packet(call):
    require(not call['is_error'] and len(call['text'])==1,'no_single_successful_JSON_tool_packet')
    return json.loads(call['text'][0])


def numeric_qualification(first, geometry):
    compact=json.loads(json_packet(first)['stdout'])
    require(compact['nearer']=='upper','native_numeric_nearer_changed')
    for name,row in geometry['regions'].items():
        data=compact[name]
        require((data['triangles'],data['vertices'],data['meets_0_40'])==
                (row['triangle_count'],row['vertex_count'],row['at_least_0_40_m']),'native_box_counts_or_threshold_changed/'+name)
        numeric_pair(data['distance_m'],data['direction'],data['a'],data['b'],geometry['matrix64_regions'][name])
    return compact


def product_qualification(call, geometry, which, slot):
    packet=json_packet(call)
    args=call['request']['params']['arguments']
    require(args==load(call['folder']/'PRODUCT_ARGUMENTS.json')
            and args==load(call['folder']/'PRODUCT_REQUEST.json')['params']['arguments'],
            'qualification_product_arguments_changed_in_bridge')
    require(load(call['folder']/'PRODUCT_RESPONSE.json')['result']==call['reply']['result'],
            'actual_public_product_reply_changed_in_bridge')
    probe=load(call['folder']/'PRODUCT_RECEIPT.json')
    downstream=slot/'mcp'/f"rpc_{probe['receipt']['index']:02d}"
    require(pin(downstream/'RX.bin')['sha256']==probe['receipt']['RX_sha256']
            and load(downstream/'TX.bin')['params']['arguments']==args,
            'product_wire_not_actual_same_slot_transaction')
    att=probe['producer_archive']
    local=receipt(slot,att['path'],att['sha256'])
    raw=load(Path(local['path']))
    expected=geometry['matrix64_regions'][which]
    selected,cube=({o['name']:o for o in geometry['meshes']}[name] for name in (TARGET,REFERENCE))
    ref=raw['region_ref']
    reference=raw['task_result']['reference']
    parent=raw['binding']
    require(raw['read_only'] is True and raw['execution_authority'] is False and
            raw['result_kind']=='source_region' and
            ref['source_triangle_indices']==expected['triangle_ids'] and
            ref['host_id']==selected['object_id'] and ref['instance_id']==selected['instance_id'] and
            reference['object_id']==cube['object_id'] and reference['instance_id']==cube['instance_id'] and
            raw['task_result']['binding']==parent and parent['capture_scope']=='complete_scene_meshes' and
            parent['document_epoch']==ref['document_epoch'] and
            all(parent['capture_state'][key]==ref['capture_generation'][key] for key in ('instance_id','epoch','revision')) and
            packet['region_ref']==ref and
            packet['task_result']['reference']['name']==raw['task_result']['reference']['name']==REFERENCE,
            'product_measured_scope_no_longer_current_frozen_selection/'+which)
    fact=packet['task_result']['facts']['surface_proximity']
    require(fact==raw['task_result']['facts']['surface_proximity'] and fact['status']=='measured',
            'product_public_surface_fact_not_producer_measurement/'+which)
    see=fact['value']['nearest_witness']
    numeric_pair(fact['value']['distance_m'],see['direction_a_to_b'],see['a'],see['b'],expected)
    has_image = which=='upper'
    require(len(raw['frames'])==int(has_image) and len(call['images'])==int(has_image),
            'qualification_product_image_scope_changed/'+which)
    return {'producer':local,'downstream_RX':pin(downstream/'RX.bin'),'downstream_TX':pin(downstream/'TX.bin'),
            'outer_RX':call['RX'],'outer_TX':call['TX'],'distance_m':fact['value']['distance_m']}


def verify_qualification(slot):
    snapshot, prior=history()
    geometry,terminal,device=verify_closed_source(slot,snapshot,prior)
    calls=actual_calls(slot)
    upper=geometry['regions']['upper']
    frames=[frame_truth(row,slot,terminal,device,upper,calls) for row in device['frames']]
    require(len(frames)==1,'qualification_needs_one_current_local_original')
    frame=frames[0]
    fixed_cli=run_path(str(CLI_ORACLE))['fixed_cli']
    numeric=numeric_qualification(calls[0],geometry)
    product={}
    if slot.name=='QN':
        require(len(calls)==3 and frame['origin']=='common_native','native_qualification_call_or_origin_changed')
        native=json.loads(json_packet(calls[1])['stdout'])
        require(native['frame_ref']==frame['ref'] and native['source_triangle_index'] in frame['upper_triangle_pixel_counts']
                and native['selected_sampled_triangle_count']==frame['upper_sampled_triangles'],
                'common_native_public_selected_row_not_actual_current_PNG')
        relevant=calls
    else:
        require(slot.name=='QP' and len(calls)==4 and frame['origin']=='product','plugin_qualification_call_or_origin_changed')
        product={name:product_qualification(call,geometry,name,slot) for name,call in zip(('lower','upper'),calls[1:3],strict=True)}
        relevant=calls
    require(calls[-1]['name']=='read_images' and any(row['attempt']==calls[-1]['attempt'] for row in frame['public_delivery']),
            'same_slot_closed_read_images_original_not_verified')
    caption=json.loads(calls[-1]['text'][0].splitlines()[1])
    local=Path(caption['local_image_path']).resolve(strict=True)
    require(caption['image_sha256']==frame['PNG']['sha256'] and str(local)==frame['PNG']['path']
            and local.read_bytes()==calls[-1]['images'][0][1],'actual_read_images_path_and_wire_PNG_differ')
    cli=[{'attempt':call['attempt'],'RX':call['RX'],'CLI':fixed_cli(call['reply'],require_all=True)} for call in relevant]
    return {'passed':True,'label':slot.name,'slot':slot.name,'asset_sha256':ASSET,'geometry':geometry,'frame':frame,
            'native_independent_calculation_delivery':numeric,'actual_product_measurements':product,'fixed_CLI':cli,
            'terminal':pin(slot/'TERMINAL_SOURCE.json'),'slot_result':pin(slot/'SLOT_RESULT.json'),
            'slot_publication':pin(slot/'SLOT_PUBLICATION.json'),'device':pin(slot/'DEVICE_EVIDENCE.json'),
            'sources':prior['histories']}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    opt=cli.parse_args()
    try:
        verdict=verify_qualification(opt.slot.resolve(strict=True))
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        verdict={'passed':False,'slot':opt.slot.name,'label':opt.slot.name,'error':str(exc),
                 'error_type':type(exc).__name__}
    write(opt.output,verdict)
    print(json.dumps({key:verdict[key] for key in ('passed','label','error') if key in verdict}),flush=True)
    raise SystemExit(0 if verdict['passed'] else 1)
