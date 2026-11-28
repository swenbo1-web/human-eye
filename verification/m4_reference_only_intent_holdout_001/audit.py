"""Check diagnosis and public consumer artifacts for the reference-only holdout."""
import argparse
import base64
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from hashlib import sha256

BATCH = 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'm4_task_region_focus_feedback_001/score.py'
spec = importlib.util.spec_from_file_location('previous_focus_score', PREVIOUS)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
old = previous.old
need, pin, read = old.need, old.pin, old.read
ORDER = ('K', 'T')
MINIMUM = 16


def save(path, body):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(body, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def checked_pin(record):
    path = Path(record['path'])
    need(path.resolve(strict=True) == path and pin(path) == {'bytes': record['bytes'], 'sha256': record['sha256']},
         'frozen_source_changed')
    return path


def admission(root):
    frozen = read(root/'preflight/FROZEN_EXECUTION.json')
    need(frozen['batch'] == BATCH, 'wrong_holdout')
    inputs = frozen['fixture']
    geometry = read(checked_pin(inputs['source']))
    truth = read(checked_pin(inputs['truth']))
    need(truth['asset_sha256'] == geometry['asset_sha256'] == inputs['blend']['sha256']
         and truth['evaluated_source_sha256'] == inputs['source']['sha256']
         and set(truth['cases']) == set(ORDER), 'truth_not_bound_to_frozen_evaluated_source')
    return frozen, geometry, truth


def bind_geometry(capture, geometry):
    import numpy as np
    original = {obj['name']:obj for obj in geometry['objects']}
    current_names = [obj['name'] for obj in capture['meshes']]
    need(len(current_names) == len(set(current_names)) == len(original)
         and set(current_names) == set(original), 'wrong_current_fixture_inventory')
    historic = {'source':{'view_layer':geometry['view_layer']}, 'objects':[]}
    for obj in capture['meshes']:
        source = original[obj['name']]
        need(np.asarray(obj['vertices'], dtype='<f8').tobytes() ==
             np.asarray(source['vertices'], dtype='<f8').tobytes() and obj['faces'] == source['faces'],
             'evaluated_source_changed/' + obj['name'])
        flags = source.get('display', {'hide_get':not source['displayed'], 'hide_viewport':False, 'hide_render':False})
        historic['objects'].append({'object_id':obj['object_id'], 'name':obj['name'],
            'visible_get':source['displayed'], 'display':flags,
            'evaluated':{'vertices_world_m':source['vertices'],'triangles':source['faces']}})
    return old.expected_domain(capture,historic)


def diag_cell(folder, request, response, producer, construction, capture, domain, target_name, case, row, audit):
    wanted = {'query':{'mode':'active_observation','objects':[{'name':target_name}],
              'focus':{'task_region':{'reference':{'name':case['reference_name']}}}},
              'include_image':True,'response_detail':'full'}
    need(request['method']=='tools/call' and request['id']==response['id']==row['id']
         and request['params']=={'name':'human_eye_scene_observe','arguments':wanted},
         'unexpected_diagnostic_request')
    result = response.get('result', {})
    if result.get('isError') is True or 'error' in response:
        return {'status':'rejected','original_error':result.get('content',response.get('error'))}, set()
    chunks = result['content']
    bodies = [json.loads(v['text']) for v in chunks if v['type']=='text']
    images = [v for v in chunks if v['type']=='image']
    need(len(bodies)==1 and len(chunks)==len(bodies)+len(images), 'unexpected_diagnostic_envelope')
    body, = bodies
    focus = body['facts']['focus']
    binding = body['binding']
    obj, ref_obj = focus['object'],focus['reference']
    target = obj['object_index']
    need(obj['object_name']==target_name and ref_obj['object_name']==case['reference_name']
         and all(capture['meshes'][o['object_index']]['object_id']==o['host_id']
                 and domain['instances'][o['host_id']]==o['instance_id'] for o in (obj,ref_obj))
         and target!=ref_obj['object_index'], 'invalid_current_target_reference')
    need(focus['selection']==wanted['query']['focus'] and body['read_only'] is True
         and body['execution_authority'] is False and focus['minimum_sample_pixels']==MINIMUM
         and focus['complete_surface_visibility']=='unknown'
         and focus['scope']=='multiple_current_evaluated_source_triangles'
         and focus['selection_policy']=={'group':'minimum_centroid_distance_to_reference_world_aabb',
             'primary':'minimum_centroid_distance_to_reference_world_aabb_then_source_order',
             'reference_effect':'group_and_primary'}, 'unexpected_diagnostic_policy')
    current = capture['capture_state']
    ref = focus['region_ref']
    group, primary = focus['task_source_triangle_indices'],focus['primary_source_triangle_index']
    need(group==ref['source_triangle_indices'] and group==sorted(set(group)) and primary in group
         and all(type(i) is int and 0<=i<len(capture['meshes'][target]['faces']) for i in group)
         and ref['capture_generation']=={k:current[k] for k in ('instance_id','epoch','revision')}
         and ref['host_id']==obj['host_id'] and ref['instance_id']==obj['instance_id']
         and ref['document_epoch']==binding['document_epoch']==capture['host_identity']['document_epoch']
         and ref['ordered_geometry_sha256']==domain['geometry_sha']
         and ref['region_id']=='source-region:'+old.fingerprint({k:v for k,v in ref.items() if k!='region_id'})
         and binding['capture_state']==current and binding['display_identity']==domain['display_sha']
         and binding['scene_revision']==capture['revision'], 'stale_or_unbound_diagnostic_source')
    need(producer['facts']['focus']==focus
         and all(producer[k]==body[k] for k in ('binding','session_id','status','work')),
         'diagnostic_producer_disagrees')
    public, frames = body['frames'], producer['constructed_frames']
    need(len(producer['frames'])==len(public)==len(images)<=1
         and all(all(raw[k]==v for k,v in small.items())
                 for raw,small in zip(producer['frames'],public,strict=True)), 'diagnostic_frame_delivery_changed')
    trace, events = old.trace_for(audit,request['id'])
    rasters = [item['view_name'] for item in events if item.get('event')==old.RENDER_EVENT]
    views = focus['views']
    physical = construction['raster_calls']
    need(rasters==[v['view_name'] for v in views] and
         [f['view_name'] for f in frames]==[v['view_name'] for v in views if v['verified_pixels'] is not None]
         and construction['id']==row['id'] and construction['result_recorded'] is True
         and not construction['limit_exceeded'] and 0<len(physical)==len(rasters)==len(frames)<=2
         and len(rasters)==body['work']['raster_attempts']==row['new_rasters']
         and len(images)==trace['annotations']['mcp_native_image_block_count'],
         'diagnostic_actual_raster_or_publication_unbound')
    truth = case['nearest_source_triangle_indices']
    files, samples, winner = set(), [], None
    for frame,view in zip(frames,views,strict=True):
        delivered = bool(public and public[0]['frame_identity']==frame['frame_identity'])
        image = None
        if delivered:
            need(images[0]['mimeType']=='image/png','diagnostic_image_not_png')
            image = base64.b64decode(images[0]['data'], validate=True)
        entry,_,png,npz = old.independent_frame(folder,frame,domain,target,sorted(set(truth)|set(group)),
                                               primary,ref,image)
        values = entry.pop('task_pixels_by_source_row')
        entry.update(task_pixels=sum(values[str(i)] for i in truth),
                     nominee_pixels=sum(values[str(i)] for i in group),
                     png=png.relative_to(folder).as_posix(), npz=npz.relative_to(folder).as_posix(),
                     delivered=delivered)
        need(entry['nominee_pixels']==view['verified_pixels']
             and entry['first_source_pixels']==view['primary_verified_pixels'],
             'diagnostic_reported_pixel_counts_differed')
        if delivered:
            winner = entry
        files.update((png,npz))
        samples.append(entry)
    sample = focus['sample']
    if winner is not None:
        need(sample is not None and winner['frame_identity']==sample['frame_identity']
             and winner['image_ref']==sample['image_ref'] and winner['nominee_pixels']==sample['selected_surface_pixels']
             and winner['first_source_pixels']==sample['primary_surface_pixels'],
             'diagnostic_sample_not_the_delivered_frame')
        if winner['nominee_pixels']:
            a = sample['sampled_pixel']
            pixel = prove_pixel(folder/winner['npz'],capture,target,a['row'],a['column'])
            need(pixel['source_triangle_index']==a['source_triangle_index'] and
                 pixel['source_triangle_index'] in group, 'invalid_diagnostic_public_pixel_anchor')
    reason = focus['stop_reason']
    need((reason=='sample_target_met') == bool(winner and winner['nominee_pixels']>=MINIMUM)
         and (samples[0]['nominee_pixels']<MINIMUM or len(rasters)==1), 'wrong_diagnostic_stop')
    return {'status':'observed','primary_source_triangle_index':primary,
            'nominated_rows':group,'matches_independent_aabb_nomination':
                group==case['candidate_aabb_nominee_source_triangle_indices'],
            'primary_is_nearest_piece':primary in truth, 'delivered_pixels_of_nearest_piece':
                winner['task_pixels'] if winner is not None else 0, 'image_has_16_nearest_pixels':
                bool(winner and winner['task_pixels']>=MINIMUM), 'rasters':len(rasters),'stop_reason':reason,
            'frames':samples,'delivered_view':winner['view'] if winner else None,
            'evidence':{'producer':pin(folder/f"producer_{row['id']:02d}.json"),
                        'physical_rasters':pin(folder/f"construction_{row['id']:02d}.json")},
            'mcp_rtt_ms':row['rtt_ms'],'mcp_rx_bytes':row['rx'],'mcp_tx_bytes':row['tx']}, files


def prove_pixel(npz, capture, target_index, r, c):
    import numpy as np
    with np.load(npz,allow_pickle=False) as arrays:
        owners,depth,ids = (arrays[k] for k in ('owners','depth','triangle_ids'))
        need(owners.shape==depth.shape==ids.shape and len(depth.shape)==2
             and type(r) is int and type(c) is int and 0<=r<depth.shape[0] and 0<=c<depth.shape[1],
             'pixel_outside_frame')
        offset=sum(len(x['faces']) for x in capture['meshes'][:target_index])
        source=int(ids[r,c])-offset
        need(owners[r,c]==target_index and math.isfinite(float(depth[r,c])) and depth[r,c]>0
             and 0<=source<len(capture['meshes'][target_index]['faces']),
             'pixel_not_a_current_target_source_sample')
        return {'row':r,'column':c,'source_triangle_index':source,'depth':float(depth[r,c])}


def diagnose(root):
    frozen, geometry, truth = admission(root)
    folder = root/'slots/DIAGNOSTIC'
    if not (folder/'ledger.json').is_file():
        return {'passed_custody':False,'cases':{k:{'status':'unrun'} for k in ORDER}}
    ledger = read(folder/'ledger.json')
    try:
        ready,closed=read(folder/'ready.json'),read(folder/'closed.json')
        need(ledger['stdout_eof'] is True and ledger['server_exit']==closed['blender_exit']==0
             and ready['pid']==closed['pid'] and ready['fixture_before']==closed['fixture_after']
             ==pin(folder/'input.blend')['sha256']==truth['asset_sha256']
             and ready['source_sha256']==frozen['product']['runtime_sha256'],
             'diagnostic_slot_not_closed_or_bound')
        capture=read(folder/'post_capture.json')
        need(checked_pin(closed['post_capture']['path'])==folder/'post_capture.json'
             and closed['post_capture']['closed_ns']<=closed['native_close_started_ns'],
             'diagnostic_terminal_read_not_bound')
        domain=bind_geometry(capture,geometry)
        worker=previous.worker_custody(folder)
        need(set(worker)==set(ORDER),'missing_real_diagnostic_worker_pairs')
        audit=[json.loads(line) for line in (folder/'audit.jsonl').read_bytes().splitlines()]
    except (KeyError,ValueError,IndexError,TypeError,OSError) as error:
        return {'passed_custody':False,'failure':str(error),'cases':{k:{'status':'unverified'} for k in ORDER}}
    cells, all_artifacts={},set()
    for row in ledger['requests'][2:]:
        name=row['label']
        try:
            prefix=folder/f"{row['id']:02d}-{name}"
            tx,rx=(prefix.with_suffix(s) for s in ('.tx','.rx'))
            need(pin(tx)=={'bytes':row['tx'],'sha256':row['tx_sha']}
                 and pin(rx)=={'bytes':row['rx'],'sha256':row['rx_sha']},'unbound_diagnostic_outer_wire')
            cell,files=diag_cell(folder,read(tx),read(rx),read(folder/f"producer_{row['id']:02d}.json"),
                read(folder/f"construction_{row['id']:02d}.json"),capture,domain,truth['target_name'],
                truth['cases'][name],row,audit)
            need(not files & all_artifacts,'diagnostic_cross_request_frame')
            cell.update(worker_wire=worker[name], tx=pin(tx), rx=pin(rx))
            all_artifacts.update(files)
            cells[name]=cell
        except (KeyError,ValueError,IndexError,TypeError,OSError) as error:
            cells[name]={'status':'unverified','reason':str(error)}
    for k in ORDER:
        cells.setdefault(k,{'status':'unrun'})
    passed=all(cells[k]['status']=='observed' for k in ORDER)
    if passed:
        frame_dir=folder/'state.json.active_observation'
        passed=all_artifacts==set(frame_dir.glob('**/*.png'))|set(frame_dir.glob('**/*.npz'))
    return {'passed_custody':passed,'cases':cells,'closure':pin(folder/'closed.json'),
            'evaluated_source':pin(folder/'post_capture.json')}


_PUBLIC_TOP = re.compile(rb'^\s*\{\s*"type"\s*:\s*"(?:thread\.started|turn\.(?:started|completed|failed)|error)"')
_PUBLIC_ITEM = re.compile(rb'^\s*\{\s*"type"\s*:\s*"item\.(?:started|updated|completed)"\s*,\s*"item"\s*:\s*\{\s*"id"\s*:\s*"[^"]+"\s*,\s*"type"\s*:\s*"(?:agent_message|mcp_tool_call)"')


def public_cli(raw_path):
    with raw_path.open('rb') as stream:
        return [json.loads(line) for line in stream if _PUBLIC_TOP.match(line) or _PUBLIC_ITEM.match(line)]


def json_lines(path):
    with path.open('rb') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def file_in_slot(folder, path, suffix):
    p=Path(path)
    need(p.is_absolute() and p.suffix.lower()==suffix and p.resolve(strict=True).is_relative_to(folder)
         and p.resolve(strict=True)==p and not p.is_symlink(), 'raw_consumer_file_outside_current_slot')
    return p


_LINK = re.compile(r'!?\[[^\r\n\]]*\]\(\s*(?:<([^>\r\n]+)>|([^()\s\r\n]+))\s*\)', re.I)


def markdown_paths(text):
    from urllib.parse import unquote
    paths=set()
    for bracket,inline in _LINK.findall(text):
        raw=unquote(bracket or inline)
        if re.match(r'^(?:/[A-Z]:|[A-Z]:)[/\\]',raw,re.I) and raw.lower().endswith('.png'):
            if raw[0]=='/':
                raw=raw[1:]
            paths.add(Path(raw))
    return paths


def response_blocks(value):
    if isinstance(value,dict):
        if value.get('type')=='image' and isinstance(value.get('data'),str):
            try:
                yield sha256(base64.b64decode(value['data'],validate=True)).hexdigest()
            except ValueError:
                return
        elif 'result' in value:
            yield from response_blocks(value['result'])
        elif 'content' in value:
            yield from response_blocks(value['content'])
    elif isinstance(value,list):
        for item in value:
            yield from response_blocks(item)


def first_focus(calls, target, reference):
    for ordinal, tool, arguments, result in calls:
        if tool!='human_eye_scene_observe':
            continue
        query = arguments.get('query',{})
        focus = query.get('focus')
        if focus is None:
            continue
        selection=focus.get('task_region') if isinstance(focus,dict) else None
        return {'ordinal':ordinal,'selection':focus,'reference_only':
                query.get('objects')==[{'name':target}] and selection=={'reference':{'name':reference}}}
    return None


def verify_review(final, claim, truth, by_path, folder, capture, target):
    need(isinstance(claim,dict) and claim['final_sha256']==sha256(final.encode('utf8')).hexdigest()
         and type(claim['understood_target_reference']) is bool
         and type(claim['selected_correct_piece']) is bool
         and type(claim['qualifies_frame_scope']) is bool
         and all(isinstance(quote,str) and quote and quote in final for quote in claim['quotations']),
         'human_observations_not_bound_to_original_final')
    result={k:claim[k] for k in ('understood_target_reference','selected_correct_piece','qualifies_frame_scope')}
    alleged=claim.get('pixel')
    result.update(original_png_link=False, same_frame_pixel_in_nearest_piece=False)
    if alleged is None:
        return result
    path=file_in_slot(folder,alleged['image_path'],'.png')
    need(path in markdown_paths(final), 'claimed_final_link_missing')
    need(path in by_path, 'path_never_delivered_by_this_slot')
    item=by_path[path]
    result['original_png_link']=True
    pixel=prove_pixel(item['arrays'],capture,target,alleged['row'],alleged['column'])
    pixel['reported_source_triangle_index']=alleged['source_triangle_index']
    result['same_frame_pixel_in_nearest_piece']=(pixel['source_triangle_index']==alleged['source_triangle_index']
        and pixel['source_triangle_index'] in truth['nearest_source_triangle_indices'])
    result.update(pixel=pixel, image_sha256=item['image_sha256'],
                  image_path=path.relative_to(folder).as_posix(), frame_request=item['ordinal'])
    return result


def natural_case(folder, frozen, geometry, truth, topic, review):
    import numpy as np
    from PIL import Image
    if not (folder/'consumer/stdout.raw.bin').is_file():
        return {'status':'unrun'}
    raw=folder/'consumer/stdout.raw.bin'
    events=public_cli(raw)
    started=[row for row in events if row['type']=='thread.started']
    completions=[row for row in events if row['type']=='turn.completed']
    if not completions:
        return {'status':'failed','reason':'no_public_turn_completed','public_thread_starts':len(started),
                'raw_public_stream':pin(raw)}
    need(len(started)==len(completions)==1,'replayed_or_duplicate_consumer_session')
    usage=completions[0]['usage']
    need(all(type(usage[key]) is int and usage[key]>=0 for key in ('input_tokens','cached_input_tokens','output_tokens'))
         and usage['cached_input_tokens']<=usage['input_tokens'],'invalid_original_CLI_usage')
    finals=[row['item']['text'] for row in events if row['type']=='item.completed'
        and row['item']['type']=='agent_message']
    final=(folder/'consumer/final.txt').read_bytes().decode('utf8')
    need(finals and final.rstrip('\r\n')==finals[-1].rstrip('\r\n'), 'final_output_not_original_public_message')
    closed=read(folder/'closed.json')
    producer=read(folder/'consumer/RESULT.json')
    transport=closed['transport']
    need(producer['passed_transport'] is True and producer['raw_public_final_match'] is True
         and checked_pin(producer['native_closure'])==folder/'closed.json'
         and producer['stdin_prompt']==frozen['fixture']['prompts'][topic]
         and producer['consumer_exit']==closed['cli_exit']==closed['blender_exit']==0
         and closed['fixture_sha256_before']==closed['fixture_sha256_after']==pin(folder/'input.blend')['sha256']
         ==frozen['fixture']['blend']['sha256'] and closed['same_before_after_capture'] is True
         and checked_pin(closed['post_capture'])==folder/'post_capture.json'
         and transport['transport_eof'] is True and transport['closed'] is True and not transport['error']
         and closed['closed_ns']<=closed['owned_deadline_ns'], 'natural_slot_not_normally_closed_and_bound')
    capture=read(folder/'post_capture.json')
    bind_geometry(capture,geometry)
    target=next(i for i,v in enumerate(capture['meshes']) if v['name']==truth['target_name'])
    calls, wire_bytes, rendered=[], {},[]
    frame_names={}
    wire_dir=folder/'wire'
    index=json_lines(wire_dir/'INDEX.jsonl')
    need([x['ordinal'] for x in index]==list(range(1,len(index)+1)), 'natural_wire_order_not_contiguous')
    for entry in index:
        ordinal=entry['ordinal']
        directory=wire_dir/f'{ordinal:03d}'
        tx,rx=directory/'TX.bin',directory/'RX.bin'
        raw_tx,raw_rx=tx.read_bytes(),rx.read_bytes()
        need(checked_pin(entry['tx'])==tx and checked_pin(entry['rx'])==rx
             and entry['started_ns']<=entry['returned_ns'], 'unbound_natural_wire_pair')
        args=json.loads(raw_tx)
        wire_bytes[ordinal]={'TX':pin(tx),'RX':pin(rx)}
        if 'id' not in args:
            need(not raw_rx,'notification_has_a_response')
            continue
        reply=json.loads(raw_rx)
        need(args['id']==reply['id']==entry['id'],'natural_wire_request_response_id_differed')
        if args['method']=='tools/call':
            params=args['params']
            calls.append((ordinal,params['name'],params.get('arguments',{}),reply))
            rendered.extend((ordinal,sha) for sha in response_blocks(reply))
            frame_names[ordinal]=[v['text'] for v in reply.get('result',{}).get('content',[])
                                  if v.get('type')=='text']
    accepted_calls=sum(entry['business'] for entry in index)
    need(accepted_calls==transport['business']<=8,'natural_business_budget_exceeded')
    actual_rasters=sum(entry['rasters'] for entry in index)
    need(actual_rasters==len(transport['rasters']),'unbound_natural_physical_raster_ledger')
    raw_rows=json_lines(folder/'frames.jsonl') if (folder/'frames.jsonl').is_file() else []
    frames={}
    for frame in raw_rows:
        duplicate=frames.setdefault(frame['image_path'],frame)
        need(all(frame[k]==duplicate[k] for k in ('frame_identity','image_sha256','arrays_sha256','image_ref')),
             'ambiguous_same_path_natural_frame')
    rows=list(frames.values())
    need(len(rows)<=actual_rasters<=4,'natural_raster_budget_or_archive_invalid')
    images=[]
    by_path={}
    correct_rows=truth['cases'][topic]['nearest_source_triangle_indices']
    for f in rows:
        ordinal=f['request_ordinal']
        png=file_in_slot(folder,f['image_path'],'.png')
        npz=file_in_slot(folder,f['arrays_path'],'.npz')
        png_sha=pin(png)['sha256']
        need(png_sha==f['image_sha256'] and pin(npz)['sha256']==f['arrays_sha256']
             and f['source_revision']==capture['revision'], 'stale_or_wrong_natural_frame')
        with np.load(npz,allow_pickle=False) as arrays, Image.open(png) as image:
            owners,depth,triangles=(arrays[k] for k in ('owners','depth','triangle_ids'))
            offsets=np.cumsum([0,*(len(o['faces']) for o in capture['meshes'])],dtype=np.int64)
            offset=int(offsets[target])
            need(image.format=='PNG' and image.mode=='RGB' and np.array_equal(np.array(image),arrays['color'])
                 and owners.shape==depth.shape==triangles.shape and np.array_equal(offsets,arrays['face_patch_offsets'])
                 and arrays['display_identity'].item()==capture['display_snapshot']['sha256'],
                 'natural_frame_original_arrays_differ')
            truth_mask=(owners==target)&np.isfinite(depth)&(depth>0)&np.isin(triangles-offset,correct_rows)
            pixels=int(np.count_nonzero(truth_mask))
        bound_deliveries={f2['request_ordinal'] for f2 in raw_rows if f2['image_path']==f['image_path'] and f2['delivered']}
        delivered=sorted({site for site, image_sha in rendered if image_sha==png_sha and site in bound_deliveries
                          and any(f['image_ref'] in text or f['frame_identity'] in text
                                  for text in frame_names.get(site,()))})
        need(set(delivered)==bound_deliveries, 'natural_claimed_delivery_missing_raw_image')
        img={'ordinal':ordinal,'introduced_by':f['source'],'pixels_of_nearest_piece':pixels,
             'image_sha256':png_sha,'png':png.relative_to(folder).as_posix(),
             'npz':npz.relative_to(folder).as_posix(),'delivery_ordinals':delivered}
        images.append(img)
        if delivered:
            need(png not in by_path,'ambiguous_natural_png_path')
            by_path[png]=dict(img,arrays=npz)
    try:
        verified=verify_review(final,review,truth['cases'][topic],by_path,folder,capture,target)
    except (ValueError,KeyError,TypeError,OSError) as failure:
        verified={'verification_error':str(failure),'understood_target_reference':bool((review or {}).get('understood_target_reference')),
                  'selected_correct_piece':bool((review or {}).get('selected_correct_piece')),
                  'qualifies_frame_scope':bool((review or {}).get('qualifies_frame_scope')),
                  'original_png_link':False,'same_frame_pixel_in_nearest_piece':False}
    first=first_focus(calls,truth['target_name'],truth['cases'][topic]['reference_name'])
    if first is not None:
        first_reply=next(reply for ordinal,_,_,reply in calls if ordinal==first['ordinal'])
        observed=[json.loads(v['text']) for v in first_reply.get('result',{}).get('content',[])
                  if v.get('type')=='text']
        facts=next((v.get('facts',{}).get('focus') for v in observed
                    if isinstance(v,dict) and v.get('facts',{}).get('focus')),None)
        first['returned_primary']=None if facts is None else facts.get('primary_source_triangle_index')
        first['returned_primary_is_nearest_piece']=None if facts is None else first['returned_primary'] in correct_rows
    return {'status':'observed','evidence_pass':all(verified[k] for k in
        ('understood_target_reference','selected_correct_piece','qualifies_frame_scope','original_png_link',
         'same_frame_pixel_in_nearest_piece')),'answer':verified,
        'closed_record':pin(folder/'closed.json'),'evaluated_source':pin(folder/'post_capture.json'),
        'raw_public_stream':pin(raw),'first_tool':calls[0][1] if calls else None,
        'first_focus':first,'first_effective_delivered_image':next((x for x in images
            if x['pixels_of_nearest_piece']>=MINIMUM and x['delivery_ordinals']),None),'images':images,
        'business_calls':[{'ordinal':o,'tool':t,'arg_schema':list(sorted(a)),
            'mcp_error':bool(reply.get('error') or reply.get('result',{}).get('isError'))} for o,t,a,reply in calls],
        'business_accepts':accepted_calls,'actual_rasters':actual_rasters,'wire':wire_bytes,'usage':usage,
        'wall_ns':producer['closed_ns']-producer['started_ns'],
        'consumer_wall_ns':producer['cli_closed_ns']-producer['cli_started_ns'],
        'business_wall_ns':sum(entry['returned_ns']-entry['started_ns'] for entry in index if entry['method']=='tools/call'),
        'discounting_cached_total_tokens':usage['input_tokens']-usage['cached_input_tokens']+usage['output_tokens'],
        'original_total_tokens':usage['input_tokens']+usage['output_tokens'],
        'final_pin':pin(folder/'consumer/final.txt')}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=Path)
    cli.add_argument('phase',choices=('diagnostic','natural'))
    cli.add_argument('output',type=Path)
    cli.add_argument('--answers',type=Path)
    args=cli.parse_args()
    root=args.root.resolve(strict=True)
    if args.phase=='diagnostic':
        result=diagnose(root)
    else:
        frozen,geometry,truth=admission(root)
        reviews=read(args.answers) if args.answers else {}
        result={}
        for label in ORDER:
            try:
                result[label]=natural_case(root/'slots'/('NATURAL_'+label),frozen,geometry,truth,label,
                                           reviews.get(label))
            except (ValueError,TypeError,KeyError,IndexError,OSError) as failure:
                result[label]={'status':'unverified','reason':str(failure)}
    save(args.output,result)


if __name__=='__main__':
    main()

