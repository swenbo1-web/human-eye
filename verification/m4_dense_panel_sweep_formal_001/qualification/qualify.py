"""Qualify the original QN path from source, stdio and independent PNG/NPZ evidence."""

import argparse
import io
import json
from pathlib import Path
import runpy
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from diagnostic import NS, TYPED, V, diagnostic_plan


RUN = Path('D:/he_m4_dense_panel_sweep_formal_001')
BASELINE = V / 'm4_dense_panel_sweep_001'
TRUTH_PATH = BASELINE / 'truth/CURRENT_TRUTH.json'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
PRODUCT = V / 'm4_dense_region_brief_001/install/PRODUCT_RUN_BINDING.json'
SHARED = V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
CURRENT = BASELINE / 'checks/qualify_product.py'
POLICY = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
CURRENT_CHECK = runpy.run_path(str(CURRENT))
TYPED_CHECK = runpy.run_path(str(TYPED))
POLICY_CHECK = runpy.run_path(str(POLICY))
PIXELS = CURRENT_CHECK['FORMAL']
ASSET_SHA = CURRENT_CHECK['ASSET_SHA']
read, require, verified, digest, write = (CURRENT_CHECK[name] for name in ('read', 'require', 'verified', 'digest', 'write'))


def sha(path):
    return digest(Path(path).read_bytes())


def ms(start, close):
    require(type(start) is int and type(close) is int and start <= close, 'ordered_microstage_clock_required')
    return (close - start) / 1e6


def wire(slot, ordinal, frozen, expected):
    client = slot / 'client'
    call = client / f'call_{ordinal:02d}'
    owner = slot / 'owner' / f'tool_{ordinal:02d}'
    index = frozen['transport_index']
    transport = client / 'transport' / f'rpc_{index:02d}'
    relay, = (client / 'attachments').glob(f'bridge_*/{index:03d}')
    request_file, response_file = call / 'REQUEST.json', call / 'RESPONSE.json'
    request, reply = read(request_file), read(response_file)
    require(request['params'] == expected and request['id'] == reply['id'] and
            frozen['request_sha256'] == sha(request_file) and frozen['response_sha256'] == sha(response_file) and
            frozen['readback_sha256'] == sha(call / 'delivered/READBACK.json') and frozen['tool_error'] is False,
            'original_native_diagnostic_request_or_result_changed')
    raw_tx, raw_rx = (transport / 'TX.bin').read_bytes(), (transport / 'RX.bin').read_bytes()
    for raw, direction, name, value in ((raw_tx, 'TX', 'REQUEST.json', request), (raw_rx, 'RX', 'RESPONSE.json', reply)):
        require(raw == (relay / f'{direction}.bin').read_bytes() == (owner / name).read_bytes() and
                json.loads(raw) == value, 'owner_thin_and_consumer_disagree/' + direction)
    meter, bridge, owned = read(transport / 'RECEIPT.json'), read(relay / 'RECEIPT.json'), read(owner / 'RECEIPT.json')
    require(meter == read(call / 'RECEIPT.json') and meter['error'] is None and
            meter['RX_sha256'] == digest(raw_rx) and meter['RX_bytes'] == bridge['response_bytes'] == owned['response_bytes'] == len(raw_rx) and
            meter['TX_bytes'] == bridge['request_bytes'] == len(raw_tx) and bridge['origin'] == 'owner' and
            request['id'] == bridge['RPC_id'] == owned['RPC_id'] == meter['id'] and
            owned['status'] == 'returned' and owned['is_error'] is False,
            'native_stdio_meters_disagree')
    result = reply['result']
    fact, texts, images = TYPED_CHECK['verify_content'](reply, contract='ordinary', fact_index=0)
    attachments = owned['image_attachments']
    require(len(images) == frozen['images'] == len(attachments) and
            sum(row['UTF8_bytes'] for row in texts) == frozen['text_UTF8_bytes'] and
            sum(len(raw) for _, raw in images) == frozen['delivered_PNG_bytes'],
            'typed_ordinary_public_bytes_disagree')
    for (row, raw), attachment in zip(images, attachments, strict=True):
        require(attachment['delivery_ready'] and row['ref'] == attachment['ref'] and
                row['PNG_sha256'] == attachment['PNG_sha256'] == digest(raw) and
                row['PNG_bytes'] == attachment['PNG_bytes_read'],
                'ordinary_native_caption_and_original_attachment_disagree')
    duration = {'wire_elapsed_ms': ms(meter['started_ns'], meter['closed_ns']),
                'owner_business_ms': ms(owned['started_ns'], owned['closed_ns']),
                'owner_response_prefix_and_work_ms': ms(owned['started_ns'], owned['response_ready_ns']),
                'TX_bytes': len(raw_tx), 'RX_bytes': len(raw_rx), 'text_UTF8_bytes': frozen['text_UTF8_bytes'],
                'PNG_bytes': frozen['delivered_PNG_bytes'], 'ordinal': ordinal,
                'RX_sha256': digest(raw_rx), 'TX_sha256': digest(raw_tx)}
    return result, json.loads(fact['stdout']), images, duration


def cli_replay(result):
    helpers, limits = POLICY_CHECK['budget_helpers']()
    require((limits['MCP_bytes'], limits['history_approximate_tokens']) == (12000, 3000),
            'fixed_CLI_budget_changed')
    stages = []
    for seconds, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        original = helpers['model_items'](result, seconds)
        require(len(original[0]['text'].encode()) == header, 'fixed_CLI_header_changed')
        mcp = helpers['truncate_items'](original, limits['MCP_bytes'])
        history = helpers['truncate_items'](mcp, limits['history_approximate_tokens'], token_mode=True)
        stage = {'header_bytes': header}
        for name, values in (('MCP', mcp), ('history', history)):
            stage[name] = {kind: [row for row in values if row['type'] == 'input_' + kind] ==
                           [row for row in original if row['type'] == 'input_' + kind] for kind in ('text', 'image')}
        stages.append(stage)
    return {'limits': limits, 'stages': stages, 'live_model_or_provider_input_observed': False,
            'passed': all(stage[name] == {'text': True, 'image': True} for stage in stages for name in ('MCP', 'history'))}


def raw_source(slot, ledger, terminal, answer, repeat):
    source_ref = answer['source_ref']
    counts = answer['counts']
    require(counts == {'objects': 14, 'vertices': 3478, 'triangles': 6148} and
            repeat == {'source_ref': source_ref, 'persistent_source_ref': source_ref, **counts},
            'ordinary_batch_read_or_persistent_source_failed')
    receipt, = [row for row in ledger['sources'] if not row['terminal']]
    packet = json.loads(verified(receipt['path'], receipt['sha256'], slot))
    worker = receipt['worker']
    require(receipt['source_ref'] == source_ref and receipt['status'] == 'complete' and
            worker['pid'] == terminal['source']['pid'] and worker['sha256'] == receipt['sha256'] and
            receipt['bytes'] == worker['bytes'] == Path(receipt['path']).stat().st_size,
            'one_ordinary_current_scene_read_required')
    by_name = {obj['name']: obj for obj in terminal['objects']}
    require(len(packet['objects']) == len(by_name) == counts['objects'] and
            {mesh['name'] for mesh in packet['objects']} == set(by_name) and
            packet['display_object_mask'] == [mesh['visible_get'] for mesh in packet['objects']],
            'ordinary_raw_mesh_names_or_ordered_display_changed')
    for mesh in packet['objects']:
        source = by_name[mesh['name']]
        require(mesh['object_id'] == source['object_id'] and mesh['instance_id'] == source['instance_id'] and
                mesh['visible_get'] == source['visible_get'] and mesh['vertices'] == source['evaluated']['vertices_world_m'] and
                mesh['triangles'] == source['evaluated']['triangles'], 'ordinary_evaluated_arrays_changed/' + mesh['name'])
    require(packet['source_face_offsets'] == [0, *accumulate_face_counts(packet['objects'])],
            'ordinary_source_face_offsets_disagree')
    return packet, receipt


def accumulate_face_counts(meshes):
    count = 0
    for mesh in meshes:
        count += len(mesh['triangles'])
        yield count


def object_region_keys(targets):
    return {(row['object_name'], tuple(row['source_triangle_indices'])): row for row in targets}


def row_keys(table, terminal):
    columns = ['object_name', 'source_triangle_ranges', 'center_world_m', 'area_m2', 'unit_normal',
               'directions', 'pixel_counts', 'witness_frame', 'reason']
    require(table['columns'] == columns, 'current_native_fact_columns_changed')
    totals = {row['name']: len(row['evaluated']['triangles']) for row in terminal['objects']}
    result = {}
    for values in table['rows']:
        row = dict(zip(columns, values, strict=True))
        name = row['object_name']
        indices, previous = [], -2
        for start, end in row['source_triangle_ranges']:
            require(type(start) is int and type(end) is int and previous + 1 < start <= end < totals[name],
                    'invalid_current_source_triangle_range')
            indices.extend(range(start, end + 1))
            previous = end
        key = name, tuple(indices)
        require(indices and key not in result, 'empty_or_repeated_native_region')
        result[key] = row
    return result


def frame_support(slot, metadata, truth, terminal, packet, captures, original_images):
    import numpy as np
    from PIL import Image

    encode = lambda value: (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                      allow_nan=False) + '\n').encode('utf8')
    require(len(captures) == len(original_images) and 2 <= len(captures) <= 4 and
            metadata['frames'] == [[frame[key] for key in ('ref', 'view', 'scope_id', 'frame_identity')] for frame in captures],
            'original_frame_order_or_denominator_changed')
    output = []
    for ordinal, (frame, (image, raw)) in enumerate(zip(captures, original_images, strict=True), 1):
        pose, view = frame['pose'], frame['view']
        camera = {key: pose[key] for key in ('name', 'size_px', 'view_matrix', 'projection_matrix')}
        png = verified(frame['PNG'], frame['PNG_sha256'], slot / 'native_frames')
        npz = verified(frame['NPZ'], frame['NPZ_sha256'], slot / 'native_frames')
        identity = digest(encode([packet['source'], ordinal, digest(encode(camera)), digest(png), digest(npz)]))
        require(frame['origin'] == 'common_native' and frame['source_ref'] == metadata['source_ref'] and
                frame['frame_identity'] == identity and frame['ref'] == 'native-image:' + identity == image['ref'] and
                frame['camera_sha256'] == digest(encode(camera)) and frame['direction_rational'] == truth['directions'][view] and
                pose['direction_rational'] == truth['directions'][view] and pose['scope_id'] == frame['scope_id'] and
                pose['name'] == view and frame['view_name'] == view and frame['size_px'] == pose['size_px'] == [512, 512] and
                frame['triangle_id_scope'] == 'zero-based-global-source-triangles-in-mesh-order' and
                png == raw and len(png) == frame['PNG_bytes'] and len(npz) == frame['NPZ_bytes'],
                'current_ordinary_camera_or_original_PNG_binding_disagrees')
        if frame['scope_id'].startswith('local:'):
            top, = [target for target in truth['eligible'] if target['unit_normal'][2] > 0]
            key = (view, tuple(top['center_world_m']), 2.0)
            require(frame['scope_id'] == 'local:' + digest(encode(key)) and
                    pose['target_world_m'] == top['center_world_m'] and pose['view_span_m'] == 2.0,
                    'native_local_top_pose_differs_from_frozen_fallback')
        pixels = []
        with Image.open(io.BytesIO(png)) as decoded, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
            owners, triangle_ids, depth = arrays['owners'], arrays['triangle_ids'], arrays['depth']
            require(decoded.format == 'PNG' and decoded.size == (512, 512) and
                    np.array_equal(np.asarray(decoded.convert('RGB')), arrays['color'][:, :, :3]) and
                    arrays['face_patch_offsets'].tolist() == frame['source_face_offsets'] and
                    arrays['display_object_mask'].tolist() == frame['display_object_mask'] and
                    owners.shape == triangle_ids.shape == depth.shape == (512, 512) and
                    np.all(np.isposinf(depth[owners == -1])) and np.all(triangle_ids[owners == -1] == -1) and
                    np.all(np.isfinite(depth[owners >= 0]) & (depth[owners >= 0] > 0)) and
                    np.all((owners >= -1) & (owners < len(frame['object_names']))),
                    'native_original_RGB_NPZ_or_depth_binding_failed')
            for index, (first, end) in enumerate(zip(frame['source_face_offsets'], frame['source_face_offsets'][1:])):
                ids = triangle_ids[owners == index]
                require(np.all((ids >= first) & (ids < end)), 'native_original_triangle_owner_offset_failed')
            for target in truth['eligible']:
                surface, contrast, points = PIXELS['pixels'](frame, target, terminal, arrays)
                in_frame = PIXELS['in_frame'](pose, points, truth['directions'][view])
                pixels.append({'object_name': target['object_name'], 'source_triangle_ranges': target['source_triangle_id_ranges'],
                               'surface_pixels': surface, 'contrasting_boundary_pixels': contrast, 'wholly_in_frame': in_frame,
                               'qualifies': view in target['eligible_complete_views'] and in_frame and surface >= 16 and contrast >= 4})
        output.append({'ref': frame['ref'], 'frame_identity': identity, 'view': view, 'scope_id': frame['scope_id'],
                       'PNG_sha256': digest(png), 'PNG_bytes': len(png), 'NPZ_sha256': digest(npz), 'NPZ_bytes': len(npz),
                       'native_content_block_index': image['content_index'], 'caption_index': image['caption_index'],
                       'pixels': pixels, 'stages': frame['stages']})
    return output


def assess_geometry(answer, truth, terminal, frames):
    targets = object_region_keys(truth['eligible'])
    actual = row_keys(answer, terminal)
    require(actual.keys() == targets.keys() and len(actual) == len(truth['eligible']) == 13 and
            answer['order'] == ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK'] and
            answer['counts'] == truth['counts'] and answer['component_count'] == truth['component_count'] and
            answer['dependencies'] == {'Fraction': '1/2', 'NumPy': 6, 'Shapely': 1.0}, 'native_exact_region_or_math_support_failed')
    top, = [index for index, target in enumerate(truth['eligible']) if target['unit_normal'][2] > 0]
    scheduled = [('LEFT', 'global'), ('SCENE', 'global')]
    if not any(frame['pixels'][top]['qualifies'] for frame in frames[:2]):
        scheduled.append(('TOP', 'global'))
        if not any(frame['pixels'][top]['qualifies'] for frame in frames[:3]):
            require(len(frames) == 4 and frames[3]['scope_id'].startswith('local:'), 'native_local_top_fallback_not_realized')
            scheduled.append(('TOP', frames[3]['scope_id']))
    require([(frame['view'], frame['scope_id']) for frame in frames] == scheduled,
            'native_TOP_fallback_raster_attempt_not_warranted')
    output, positive, blocked = [], set(), 0
    for index, (key, target) in enumerate(targets.items()):
        row = actual[key]
        pixels = [frame['pixels'][index] for frame in frames]
        selected = next((index for index, value in enumerate(pixels) if value['qualifies']), None)
        directions = [target['finite_direction_proofs'][view]['status'] for view in answer['order']]
        reason = ('observed_readable' if selected is not None else target['expected_unknown_reason'] or
                  'pixel_evidence_insufficient')
        require(row['center_world_m'] == target['center_world_m'] and row['unit_normal'] == target['unit_normal'] and
                row['area_m2'] == target['area_m2'] and row['directions'] == directions and
                row['pixel_counts'] == [[v['surface_pixels'], v['contrasting_boundary_pixels']] for v in pixels] and
                row['witness_frame'] == selected and row['reason'] == reason, 'native_observation_or_independent_truth_differs/' + key[0])
        if selected is not None:
            positive.add('top' if index == top else 'side')
        if reason == 'positive_area_occlusion_all_front_views':
            blocked += 1
        output.append(row | {'complete_witness': None if selected is None else frames[selected]['ref']})
    require(positive == {'top', 'side'} and blocked == 2, 'native_side_top_or_occlusion_prerequisite_failed')
    return output, sorted(positive), blocked


def qualify(runtime, freeze_path, outcome):
    slot = runtime / 'slots/QN'
    freeze = sha(freeze_path)
    result_path, publication_path = slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'
    result, publication = read(result_path), read(publication_path)
    counts = (result.get('budget') or {}).get('counts', {})
    outcome.update(freeze_sha256=freeze, slot_result_sha256=sha(result_path), publication_sha256=sha(publication_path),
                   independent_truth_sha256=TRUTH_SHA, asset_sha256=ASSET_SHA, denominator=counts,
                   original_errors=result['errors'], owned_slot_status=publication['status'])
    require(result['asset_sha256'] == ASSET_SHA and result['freeze_sha256'] == freeze and
            result['label'] == publication['label'] == 'QN' and result['group'] == 'N' and
            result['phase'] == 'qualification' and publication['result_sha256'] == sha(result_path) and
            result['model_consumers'] == result['paid_API_calls'] == 0, 'original_native_slot_unbound')
    if result['status'] != 'completed' or publication['status'] != 'completed':
        raise ValueError('original_native_slot_failed_before_qualification')
    diagnostics = result['diagnostic_calls']
    require(result['independent_before_after']['passed'] and result['closure_verification']['passed'] and
            result['owner_close']['confirmed'] and result['diagnostic_close']['confirmed'] and
            publication['owned_budget_passed'] and len(diagnostics) == counts['business_admissions'] == 2 and
            counts['Blender_start_attempts'] == 1 and counts['consumer_admissions'] == counts['pending_raster_reservations'] == 0,
            'original_QN_close_or_budget_unconfirmed')
    product, shared = read(PRODUCT), read(SHARED)
    require(all(row['name'] != 'human_eye_scene_observe' for row in read(slot / 'client/TOOLS.json')['result']['tools']) and
            (slot / 'client/TOOLS.json').is_file(), 'native_qualification_tools_cross_arm_mismatch')
    sys.path[:0] = [product['dependency_root'], shared['dependency_root']]
    terminal, outcome['current_source'] = CURRENT_CHECK['current_source'](slot, result)
    truth = json.loads(verified(TRUTH_PATH, TRUTH_SHA, TRUTH_PATH.parent))
    calls = [wire(slot, ordinal, frozen, expected) for ordinal, (frozen, expected) in enumerate(
        zip(diagnostics, diagnostic_plan('N'), strict=True), 1)]
    initial, repeated = calls
    ledger = read(slot / 'DEVICE_EVIDENCE.json')
    packet, capture = raw_source(slot, ledger, terminal, initial[1], repeated[1])
    frames = frame_support(slot, initial[1], truth, terminal, packet, ledger['frames'], initial[2])
    require(len(frames) == counts['all_raster_actual'] == counts['all_raster_upper'] <= 6 and not repeated[2],
            'ordinary_qualification_raster_bound_or_readback_failed')
    regions, positive, blocked = assess_geometry(initial[1], truth, terminal, frames)
    cli = [cli_replay(row[0]) for row in calls]
    publish = publication['published_ns']
    outcome.update(original_regions=regions, frames=frames, independent_actual_positive_axes=positive,
                   proven_geometric_unknowns=blocked, CLI=cli, actual_tool_catalogue=read(slot / 'client/TOOLS.json')['result']['tools'],
                   current_ordinary_source_sha256=capture['sha256'], ordinary_modules=result['actual_dependency_modules'],
                   timing={'startup_to_ready_ms': ms(result['started_ns'], result['ready_ns']),
                           'ready_to_client_ready_ms': ms(result['ready_ns'], result['diagnostic_ready_ns']),
                           'diagnostic_call_sequence_ms': ms(diagnostics[0]['started_ns'], diagnostics[-1]['returned_ns']),
                           'last_call_to_publication_ms': ms(diagnostics[-1]['returned_ns'], publish),
                           'owned_window_ms': ms(result['started_ns'], publish), 'calls': [row[3] for row in calls],
                           'ordinary_source_parent_read': capture['parent_read'],
                           'frame_camera_fit': [event for event in ledger['events'] if event['event'] == 'native_camera_fit']})
    require(all(value['passed'] for value in cli), 'fixed_CLI_two_stage_replay_lost_ordinary_text_or_original_PNG')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path, default=HERE / 'NATIVE_REVIEW.json')
    args = parser.parse_args()
    started = time.perf_counter_ns()
    outcome = {'schema': 'm4-dense-panel-sweep-formal-QN-review-v1', 'label': 'QN'}
    try:
        qualify(args.runtime, args.freeze, outcome)
    except Exception as error:
        outcome.update(passed=False, reason=str(error), error_type=type(error).__name__)
    else:
        outcome.update(passed=True, reason='qualified')
    outcome['assessment_ms'] = ms(started, time.perf_counter_ns())
    write(args.output, outcome)
    print(json.dumps({key: outcome.get(key) for key in ('label', 'passed', 'reason', 'denominator',
                                                       'independent_actual_positive_axes')}, ensure_ascii=False))
    return 0 if outcome['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
