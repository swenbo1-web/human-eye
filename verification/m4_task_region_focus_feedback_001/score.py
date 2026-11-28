"""Independently score the focused task A/B from its closed Blender and MCP records."""
import argparse
import base64
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys

BATCH = 'M4-TASK-REGION-FOCUS-FEEDBACK-001'
INPUT_SHA = '62a022cea2cc8f820ea8eaecc7d4750e69ed90d545d6c5fd31dda6592441d93c'
OLD_SCORE = Path(__file__).resolve().parent.parent / 'm4_directed_focus_assembly_holdout_001/score.py'
spec = importlib.util.spec_from_file_location('holdout_score', OLD_SCORE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
need, pin, read, fingerprint = old.need, old.pin, old.read, old.fingerprint
MINIMUM = old.THRESHOLD


def request_focus(label, arm, task, request):
    query = {'mode': 'active_observation', 'objects': [{'name': task['target']}],
             'focus': 'auto' if arm == 'auto' else {'task_region': {
                 'reference': {'name': task['reference']}, 'world_box_m': task['world_box_m']}}}
    need(request['jsonrpc'] == '2.0' and request['method'] == 'tools/call'
         and request['params'] == {'name': 'human_eye_scene_observe', 'arguments': {
             'query': query, 'include_image': True, 'response_detail': 'full'}},
         'actual_request_differs_from_frozen_task/' + label)
    return query['focus']


def first_frame_decisions(result):
    frames = result['private_frames']
    result['first_frame_decisions'] = None
    if frames:
        first = frames[0]
        primary = first['first_source_pixels'] >= MINIMUM
        group = first['task_pixels'] >= MINIMUM
        result['first_frame_decisions'] = {'primary_would_stop': primary, 'task_group_would_stop': group,
            'different': primary != group, 'actual_second_raster': result['raster_attempts'] == 2}


def task_reply(folder, request, reply, task, row, expected, domain, audit, producer, construction):
    import numpy as np
    if expected == 'auto':
        result, files = old_auto_reply(folder, request, reply, task, row, expected, domain, audit,
                                       producer, construction)
        if result['status'] == 'observed':
            for info, frame in zip(result['private_frames'],producer['constructed_frames'],strict=True):
                for key, field in (('PNG','image_path'),('NPZ','arrays_path')):
                    info['original_'+key+'_path'] = Path(frame[field]).relative_to(folder).as_posix()
            result['stage_elapsed_ns'] = stage_times(producer)
            first_frame_decisions(result)
        return result, files
    if reply.get('result', {}).get('isError') is True or 'error' in reply:
        return old_auto_reply(folder, request, reply, task, row, expected, domain, audit,
                              producer, construction)
    trace, related = old.trace_for(audit, request['id'])
    renders = [event['view_name'] for event in related if event.get('event') == old.RENDER_EVENT]
    raw_blocks = reply['result']['content']
    textual, images = ([block for block in raw_blocks if block['type'] == kind]
                       for kind in ('text', 'image'))
    need(len(textual) == 1 and len(textual) + len(images) == len(raw_blocks), 'invalid_public_content')
    body = json.loads(textual[0]['text'])
    focus, binding, published = body['facts']['focus'], body['binding'], body['frames']
    capture = domain['capture']
    need(body['result_kind'] == 'active_observation' and body['observation_status'] == 'directed_focus'
         and body['read_only'] is True and body['execution_authority'] is False
         and len(published) == len(images) <= 1
         and len(published) == body['image_delivery']['mcp_content_constructed_image_count']
         == trace['annotations']['mcp_native_image_block_count'], 'invalid_read_only_public_frame')
    need(focus['selection'] == expected and focus['scope'] == 'multiple_current_evaluated_source_triangles'
         and focus['minimum_sample_pixels'] == MINIMUM and focus['complete_surface_visibility'] == 'unknown',
         'invalid_task_scope_or_threshold')
    need(binding['document_epoch'] == capture['host_identity']['document_epoch']
         and binding['capture_scope'] == 'complete_scene_meshes' and binding['scene_revision'] == capture['revision']
         and binding['capture_state'] == capture['capture_state'] and binding['display_identity'] == domain['display_sha'],
         'task_capture_not_current')
    for obj, name in ((focus['object'], task['target']), (focus['reference'], task['reference'])):
        index = obj['object_index']
        need(type(index) is int and 0 <= index < len(domain['ids'])
             and domain['ids'][index] == obj['host_id'] and obj['instance_id'] == domain['instances'][obj['host_id']]
             and obj['object_name'] == name == capture['meshes'][index]['name'], 'invalid_task_object_binding')
    target = focus['object']['object_index']
    need(focus['object']['host_id'] == task['host_id'] and focus['reference']['object_index'] != target,
         'wrong_target_or_same_reference')
    policy = {'group': 'all_three_vertices_in_world_closed_box',
              'primary': 'minimum_centroid_distance_to_reference_world_aabb_then_source_order',
              'reference_effect': 'primary_only'}
    need(focus['selection_policy'] == policy, 'task_selection_policy_changed')
    ref, primary = focus['region_ref'], focus['primary_source_triangle_index']
    group = focus['task_source_triangle_indices']
    need(type(group) is list and group == sorted(set(group))
         and all(type(i) is int and 0 <= i < len(capture['meshes'][target]['faces']) for i in group)
         and (primary in group if primary is not None else ref is None), 'invalid_task_selection_rows')
    if ref is not None:
        obj = focus['object']
        need(ref['schema'] == 'human-eye-source-region-ref-v1' and ref['source_triangle_indices'] == group
             and ref['document_epoch'] == binding['document_epoch'] and ref['host_id'] == obj['host_id']
             and ref['instance_id'] == obj['instance_id']
             and ref['capture_generation'] == {k: capture['capture_state'][k] for k in ('instance_id','epoch','revision')}
             and ref['ordered_geometry_sha256'] == domain['geometry_sha']
             and ref['region_id'] == 'source-region:' + fingerprint({k:v for k,v in ref.items() if k!='region_id'}),
             'invalid_task_region_reference')
    need(producer is not None and producer['facts']['focus'] == focus
         and all(producer[k] == body[k] for k in ('binding','status','session_id','work')),
         'public_task_reply_not_same_producer')
    frames, physical = producer['constructed_frames'], construction['raster_calls']
    views = focus['views']
    need(len(producer['frames']) == len(published)
         and all(all(raw[k] == v for k,v in public.items())
                 for raw,public in zip(producer['frames'],published,strict=True))
         and len({frame['frame_identity'] for frame in frames}) == len(frames)
         and [frame['view_name'] for frame in frames] == [v['view_name'] for v in views if v['verified_pixels'] is not None]
         and [v['view_name'] for v in views] == renders
         and len(renders) <= 2 and renders == ['SCENE','FOCUS'][:len(renders)]
         and len(renders) == len(physical) == body['work']['raster_attempts'] == row['new_rasters']
         == body['image_delivery']['new_raster_attempts']
         and len(frames) == body['work']['raster_completed'] == body['image_delivery']['local_verified_image_count'],
         'wrong_raster_order_or_inventory')
    stage = producer['stages']['service_total']
    need(stage['elapsed_ns'] == stage['closed_ns'] - stage['started_ns']
         and row['started_ns'] <= stage['started_ns'] <= stage['closed_ns'] <= row['returned_ns']
         and construction['id'] == request['id'] and construction['label'] == task['target']
         and construction['result_recorded'] is True and not construction['limit_exceeded']
         and row['started_ns'] <= construction['service_started_ns'] <= construction['service_returned_ns']
         <= row['returned_ns']
         and all(v['completed'] and construction['service_started_ns'] <= v['started_ns'] <= v['closed_ns']
                 <= construction['service_returned_ns'] for v in physical), 'unbound_per_request_raster_intervals')
    truth = task['source_triangle_indices']
    verified, winner, winner_data, files = [], None, None, set()
    for frame in frames:
        delivered = bool(published and published[0]['frame_identity'] == frame['frame_identity'])
        if delivered:
            need(images[0]['mimeType'] == 'image/png', 'delivered_task_block_not_png')
        image = base64.b64decode(images[0]['data'],validate=True) if delivered else None
        pixels, _, png, npz = old.independent_frame(folder,frame,domain,target,sorted(set(truth)|set(group)),
                                                   primary,ref,image)
        per_row = pixels['task_pixels_by_source_row']
        pixels['task_pixels'] = sum(per_row[str(i)] for i in truth)
        pixels['declared_group_pixels'] = sum(per_row[str(i)] for i in group)
        pixels['delivered'] = delivered
        pixels['original_PNG_path'] = png.relative_to(folder).as_posix()
        pixels['original_NPZ_path'] = npz.relative_to(folder).as_posix()
        view, = [v for v in views if v['view_name'] == frame['view_name']]
        need(view['verified_pixels'] == pixels['declared_group_pixels']
             and view['primary_verified_pixels'] == pixels['first_source_pixels'], 'task_pixel_count_differed')
        need(not {png,npz} & files, 'duplicate_task_frame_paths')
        files.update((png,npz))
        verified.append(pixels)
        if delivered:
            winner, winner_data = pixels,npz
    sample, reason = focus['sample'], focus['stop_reason']
    if published:
        frame, = published
        need(winner is not None and sample is not None and sample['view_name'] == winner['view']
             and all(sample[k] == winner[k] for k in ('frame_identity','image_ref'))
             and sample['selected_surface_pixels'] == winner['declared_group_pixels']
             and sample['primary_surface_pixels'] == winner['first_source_pixels']
             and frame['host_binding_sha256'] == binding['binding_sha256']
             and frame['candidate_identity'] == binding['camera_identity'], 'unbound_public_task_sample')
        need(winner is max(verified,key=lambda p:p['declared_group_pixels']), 'did_not_deliver_best_observed_group')
        anchor = sample['sampled_pixel']
        if winner['declared_group_pixels']:
            need(type(anchor) is dict and anchor['source_triangle_index'] in group
                 and all(type(anchor[k]) is int and 0 <= anchor[k] < old.ARRAY_SHAPE[i]
                         for i,k in enumerate(('row','column'))), 'invalid_task_anchor_dimensions_or_source')
            r,c = anchor['row'],anchor['column']
            with np.load(BytesIO(winner_data.read_bytes()),allow_pickle=False) as arrays:
                mask = (arrays['owners'] == target) & np.isfinite(arrays['depth'])
                local = arrays['triangle_ids'] - int(domain['offsets'][target])
                hits = np.flatnonzero(mask & np.isin(local,group))
                need(len(hits) == winner['declared_group_pixels']
                     and int(hits[0]) == r * old.ARRAY_SHAPE[1] + c
                     and int(local[r,c]) == anchor['source_triangle_index'], 'anchor_not_actual_group_pixel')
        else:
            need(anchor is None, 'zero_group_pixels_with_claimed_anchor')
    else:
        need(sample is None and winner is None, 'unpublished_task_sample')
    if verified:
        best = max(p['declared_group_pixels'] for p in verified)
        need((reason == 'sample_target_met' and winner is not None) if best >= MINIMUM
             else reason == 'view_budget_exhausted', 'bad_actual_group_stop_reason')
        if verified[0]['declared_group_pixels'] >= MINIMUM:
            need(len(renders) == 1, 'constructed_after_first_group_already_met_threshold')
        elif len(verified) == 1 and reason == 'view_budget_exhausted':
            normal = np.asarray(focus['front_normal_world'],dtype=np.float64)
            pose = np.asarray(frames[0]['pose']['target_to_eye_unit'],dtype=np.float64)
            need(normal.shape == pose.shape == (3,) and np.linalg.norm(normal-pose) <= 1e-12,
                 'exhausted_before_available_corrective_view')
    delivered_pixels = winner['task_pixels'] if winner is not None else 0
    result = {'status':'observed','group_hit':group == truth,'group_size':len(group),
              'first_source_triangle':primary,'first_hit':primary in truth,'delivered_task_pixels':delivered_pixels,
              'delivered_primary_pixels':winner['first_source_pixels'] if winner is not None else 0,
              'delivered_hit':delivered_pixels >= MINIMUM,'joint_hit':primary in truth and delivered_pixels >= MINIMUM,
              'delivered_view':winner['view'] if winner is not None else None,'private_frames':verified,
              'stop_reason':reason,'raster_attempts':len(renders),'render_views':renders,
              'actual_raster_calls':len(physical),'actual_raster_total_ns':sum(v['closed_ns']-v['started_ns'] for v in physical),
              'service_core_ns':stage['elapsed_ns'],'service_inclusive_ns':trace['duration_ns'],
              'client_rtt_ms':row.get('rtt_ms'),'product_status':body['status'],'stage_elapsed_ns':stage_times(producer)}
    first_frame_decisions(result)
    return result, files


old_auto_reply = old.score_reply


def stage_times(producer):
    return {k:v['elapsed_ns'] for k,v in producer['stages'].items()
            if isinstance(v,dict) and isinstance(v.get('elapsed_ns'),int)}


def worker_custody(folder):
    receipt = read(folder/'WORKER_ADMISSION.json')
    need(receipt['passed'] is True, 'worker_receipt_rejected')
    payloads = {}
    for side in ('TX','RX'):
        raw = folder/'worker_wire'/f'{side}.bin'
        need(old.check_pin(receipt[side]) == raw, 'worker_wire_outside_current_slot')
        payloads[side] = raw.read_bytes()
    need(old.check_pin(receipt['index']) == folder/'worker_wire/INDEX.json', 'worker_index_outside_current_slot')
    ledger = read(folder/'ledger.json')
    measured = {}
    for name, pairs in receipt['business_pairs'].items():
        row, = (r for r in ledger['requests'] if r['label'] == name)
        need(pairs and all(pair in receipt['actual_worker_pairs'] for pair in pairs), 'unpaired_worker_exchange')
        for pair in pairs:
            tx, rx = (payloads[side][pair[side]['offset']:pair[side]['offset']+pair[side]['bytes']]
                      for side in ('TX','RX'))
            need(rx.startswith(b'HUMAN_EYE_RPC:'), 'worker_reply_protocol_marker_missing')
            request, reply = json.loads(tx), json.loads(rx.removeprefix(b'HUMAN_EYE_RPC:'))
            need(request['id'] == reply['id'] == pair['id'] and 'result' in reply
                 and row['started_ns'] < pair['tx_end_ns'] < pair['rx_end_ns'] < row['returned_ns'],
                 'worker_wire_not_inside_formal_observation')
        measured[name] = {side+'_bytes':sum(pair[side]['bytes'] for pair in pairs) for side in ('TX','RX')}
    need(set(measured) == {x['label'] for x in ledger['requests'] if x['id'] >= 3}, 'worker_wire_incomplete')
    return measured


def evaluate(root):
    preflight = root / 'preflight'
    inputs_path = preflight / 'TASK_INPUTS.json'
    need(pin(inputs_path)['sha256'] == INPUT_SHA, 'frozen_task_input_changed')
    inputs = read(inputs_path)
    labels_path = old.check_pin(inputs['prior_labels'])
    need(pin(labels_path)['sha256'] == old.FROZEN_LABELS_SHA, 'independent_truth_changed')
    labels = read(labels_path)
    need(labels['task_order'] == inputs['task_order'], 'task_inventory_changed')
    for name, task in inputs['tasks'].items():
        need(all(labels['tasks'][name][k] == task[k] for k in ('asset','target')), 'task_target_changed')
        labels['tasks'][name].update(reference=task['reference'],world_box_m=task['world_box_m'])
    old.observation_request, old.score_reply = request_focus, task_reply
    results = {}
    for arm, receipt in (('auto','BASELINE'),('task','CANDIDATE')):
        identity = read(preflight/f'{receipt}_INSTALL_CUSTODY.json')
        old.SOURCE_SHA,old.SOURCE_FILES = identity['source_sha256'],identity['runtime_sources']
        results[arm] = {}
        for asset in old.ORDER:
            folder = root/'slots'/f'{asset.upper()}_{arm.upper()}'
            slot = old.review_slot(folder,asset,arm,labels)
            results[arm][asset] = slot
            if slot['closure_verified']:
                try:
                    measured = worker_custody(folder)
                    for name,native in measured.items():
                        slot['cases'][name]['worker_wire'] = native
                    slot['worker_wire_verified'] = True
                except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
                    slot['worker_wire_verified'] = False
                    slot['worker_wire_error'] = str(error)
    counts = {}
    for arm, slots in results.items():
        cells = [cell for slot in slots.values() for cell in slot['cases'].values()]
        counts[arm] = {name:sum(c.get(name) is True for c in cells if c['status'] == 'observed')
                       for name in ('group_hit','first_hit','delivered_hit','joint_hit')}
        if arm == 'auto':
            counts[arm].pop('group_hit')
        counts[arm].update(registered=len(cells),verified=sum(c['status']=='observed' for c in cells),
                           unrun=sum(c['status']=='unrun' for c in cells),
                           failed=sum(c['status'] not in ('observed','unrun') for c in cells),
                           rasters=sum(slot.get('raster_attempts_verified',0) for slot in slots.values()))
    valid = all(v['verified'] == v['registered'] == 4 and all(s['closure_verified'] and s.get('worker_wire_verified') for s in results[arm].values())
                for arm,v in counts.items())
    task, auto = counts['task'], counts['auto']
    gates = {'all_eight_verified':valid,'correct_groups':task['group_hit']==4,
             'correct_primaries':task['first_hit']==4,'all_delivered':task['delivered_hit']==4,
             'rasters_at_most_auto':valid and task['rasters']<=auto['rasters']}
    return {'batch':BATCH,'task_input_sha256':INPUT_SHA,'frozen_labels_sha256':old.FROZEN_LABELS_SHA,
            'slots':results,'counts':counts,'gates':gates,'passed':all(gates.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--deps',type=Path,action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(p.resolve(strict=True)) for p in args.deps]
    scored = evaluate(args.root.resolve(strict=True))
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(scored,stream,indent=2,sort_keys=True,ensure_ascii=False)
        stream.write('\n')


if __name__ == '__main__':
    main()

