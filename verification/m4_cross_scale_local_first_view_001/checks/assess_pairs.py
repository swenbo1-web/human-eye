"""Reconcile six owned MCP observations with the independent fixture and actual wire."""

import argparse
import base64
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
VERIFICATION = NS.parent
FORMAL = VERIFICATION / 'm4_cross_scale_live_task_formal_001'
RUN = Path('D:/he_m4_cross_scale_local_first_view_001')
TRUTH_SHA256 = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
BASELINE_SHA256 = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
BASELINE_BINDING = VERIFICATION / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
CANDIDATE_BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
VIEWS = {'M02': 'SCENE', 'M09': 'LEFT'}
SELECTED = [(None, 'SCENE'), ('M02', 'SCENE'), ('M09', 'LEFT')]
EXPECTED_CONSTRUCTION = {
    'A': [*SELECTED[:2], ('M09', 'SCENE'), SELECTED[2]],
    'B': SELECTED,
}
PRODUCT = 'human_eye_scene_observe'
FIELD_GEOMETRY = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')


sys.path.insert(0, str(FORMAL / 'scoring'))
from formal import in_frame, pixels, read, require, terminal, verified, write


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def milliseconds(start, end):
    require(type(start) is int and type(end) is int and start <= end, 'invalid_monotonic_clock')
    return (end - start) / 1e6


def stage_ms(stage):
    return milliseconds(stage['started_ns'], stage['closed_ns'])


def binding_objects(binding, current):
    objects = binding['objects']
    require([row['object_index'] for row in objects] == list(range(len(current))) and
            {row['object_name'] for row in objects} == set(current), 'incomplete_current_product_object_roster')
    require(all((row['host_id'], row['instance_id']) ==
                (current[row['object_name']]['object_id'], current[row['object_name']]['instance_id'])
                for row in objects), 'product_object_identity_does_not_resolve_to_owned_current_source')
    return objects


def scope_objects(product, parent, current):
    scopes = {scope['scope_id']: scope for scope in product['scopes']}
    require(len(scopes) == 3 and len(scopes) == len(product['scopes']) and 'global' in scopes,
            'unexpected_scope_roster')
    require(scopes['global']['binding'] == parent, 'whole_scene_binding_drift')
    for key, scope in scopes.items():
        binding = scope['binding']
        for field in ('scene_revision', 'geometry_identity', 'document_epoch', 'capture_state', 'objects',
                      'runtime_source_sha256', 'unit', 'coordinate_frame'):
            require(binding[field] == parent[field], 'scope_does_not_share_current_parent/' + field)
        binding_objects(binding, current)
        if key != 'global':
            require(binding['parent_binding_sha256'] == parent['binding_sha256'] and
                    binding['parent_source_binding_sha256'] == parent['source_binding_sha256'],
                    'local_scope_parent_identity_drift')
    return scopes


def same_geometry(row, expected, owned, binding):
    name = row['object_name']
    source = row['source']
    require(row['source_triangle_indices'] == expected['source_triangle_indices'] == source['source_triangle_indices'],
            'wrong_evaluated_triangle_rows/' + name)
    mesh = owned['evaluated']
    raw = json.dumps({'vertices': mesh['vertices_world_m'], 'faces': mesh['triangles']},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    require(digest(raw) == source['ordered_geometry_sha256'], 'source_mesh_not_current/' + name)
    require((row['host_id'], row['instance_id']) == (owned['object_id'], owned['instance_id']) ==
            (source['host_id'], source['instance_id']) and
            binding['objects'][row['object_index']]['object_name'] == name and
            row['object_index'] == source['object_index'] and
            source['parent_binding_sha256'] == binding['binding_sha256'] and
            source['parent_source_binding_sha256'] == binding['source_binding_sha256'] and
            all(source[k] == binding[k] for k in ('scene_revision', 'document_epoch', 'capture_state')),
            'task_row_current_source_drift/' + name)

    center, u, v, front = [tuple(map(Fraction, row[key])) for key in FIELD_GEOMETRY]
    require(center == tuple(map(Fraction, expected['center_world_m'])), 'wrong_region_center/' + name)
    corners = {tuple(c + i * a + j * b for c, a, b in zip(center, u, v, strict=True))
               for i in (-1, 1) for j in (-1, 1)}
    expected_corners = {tuple(map(Fraction, mesh['vertices_world_m'][i])) for i in expected['vertex_indices']}
    require(corners == expected_corners, 'wrong_region_corners/' + name)
    cross = tuple(u[(i + 1) % 3] * v[(i + 2) % 3] - u[(i + 2) % 3] * v[(i + 1) % 3] for i in range(3))
    require(16 * sum(x*x for x in cross) == Fraction(expected['area_squared_m4']), 'wrong_region_area/' + name)
    normal = tuple(map(Fraction, expected['plane_normal_integer']))
    for vector in (front, cross):
        major = max(range(3), key=lambda i: abs(normal[i]))
        scale = vector[major] / normal[major]
        require(scale > 0 and vector == tuple(x*scale for x in normal), 'wrong_oriented_region_normal/' + name)
    return {'triangles': row['source_triangle_indices'], 'center_world_m': [str(x) for x in center],
            'area_squared_m4': expected['area_squared_m4'], 'plane_normal_integer': list(map(int, normal)),
            'status': row['status'], 'reason': row['reason'], 'ordered_geometry_sha256': digest(raw)}


def frame_payload(slot, frame, scope, terminal_source, truth, image=None):
    import numpy as np
    from PIL import Image

    binding = scope['binding']
    require(frame['host_binding_sha256'] == binding['binding_sha256'] and
            frame['camera_identity'] == binding['camera_identity'] == frame['candidate_identity'] and
            frame['source_revision'] == binding['scene_revision'] and
            frame['scene_identity'] == binding['geometry_identity'] and frame['scope_id'] == scope['scope_id'],
            'frame_not_tied_to_current_scope_or_camera')
    png = verified(frame['image_path'], frame['image_sha256'], slot)
    npz = verified(frame['arrays_path'], frame['arrays_sha256'], slot)
    require((len(png), len(npz)) == (frame['PNG_bytes'], frame['compressed_array_file_bytes']) and
            (image is None or image == png), 'wire_image_or_array_byte_count_changes')
    view = frame['view_name']
    pose = frame['pose']
    require(view == pose['name'] and pose['direction_rational'] == truth['directions'][view], 'wrong_frame_pose')
    source = binding.get('region_source')
    with Image.open(io.BytesIO(png)) as picture, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
        require(picture.format == 'PNG' and picture.size == (512, 512) and
                np.array_equal(np.asarray(picture.convert('RGB')), arrays['color'][:, :, :3]),
                'png_does_not_match_native_array')
        objects = binding['objects']
        # This installed active renderer falls back to the complete object mask
        # when the archive contains no separate display-participation array.
        display_mask = binding.get('image_scope', {}).get('participation_mask', [True] * len(objects))
        if 'display_object_mask' in arrays:
            require(display_mask == arrays['display_object_mask'].tolist(), 'npz_display_mask_disagrees_with_binding')
        frame_source = {'object_names': [row['object_name'] for row in objects],
                        'object_ids': [row['host_id'] for row in objects],
                        'object_instance_ids': [row['instance_id'] for row in objects],
                        'display_object_mask': display_mask,
                        'source_face_offsets': arrays['face_patch_offsets'].tolist()}
        detailed = {}
        for region in truth['eligible']:
            name = region['object_name']
            count, boundary, vertices = pixels(frame_source, region, terminal_source, arrays)
            detailed[name] = {
                'target_surface_pixels': count,
                'contrasting_boundary_pixels': boundary,
                'qualifies': (view in region['eligible_complete_views'] and count >= 16 and boundary >= 4
                              and in_frame(pose, vertices, truth['directions'][view])),
            }
        npz_arrays = {name: int(arrays[name].nbytes) for name in ('owners', 'triangle_ids', 'color', 'depth')}
    return {'view': view, 'scope_id': scope['scope_id'], 'frame_identity': frame['frame_identity'],
            'object_name': None if source is None else binding['objects'][source['object_index']]['object_name'],
            'ref': frame['image_ref'], 'image_sha256': digest(png), 'source_sha256': binding['binding_sha256'],
            'camera_sha256': frame['camera_identity'], 'NPZ_sha256': digest(npz), 'png_bytes': len(png),
            'npz_bytes': len(npz), 'named_array_bytes': npz_arrays,
            'declared_array_payload_bytes': frame['array_payload_bytes'], 'independent_pixels': detailed,
            'raster_ms': stage_ms(frame['stages']['actual_raster']),
            'publish_png_npz_ms': stage_ms(frame['stages']['PNG_NPZ_publication']),
            'metadata_ms': stage_ms(frame['stages']['frame_metadata']),
            'feedback_stages_ms': {name: stage_ms(stage) for name, stage in frame['feedback_stages'].items()}}


def audit_wire(slot, event, meter, audit, req):
    ident = event['request']['id']
    receipt = event['receipt']
    require(event['request']['method'] == 'tools/call' and event['request']['params'] ==
            {'arguments': req, 'name': PRODUCT}, 'candidate_or_control_request_differs')
    require(receipt['id'] == ident == meter['response_id'] and receipt['error'] is None,
            'unmatched_or_failed_mcp_receipt')
    number = event['index']
    rpc = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    record = slot / 'product_calls' / f'call_{number:03d}'
    tx = (rpc / 'TX.bin').read_bytes()
    rx = (rpc / 'RX.bin').read_bytes()
    require(digest(tx) == meter['TX_sha256'] and len(tx) == meter['TX_bytes'] == receipt['TX_bytes'] and
            json.loads(tx) == read(record / 'REQUEST.json') == event['request'],
            'archived_request_and_mcp_stdio_differ')
    wire = json.loads(rx)
    require(digest(rx) == receipt['RX_sha256'] and len(rx) == receipt['RX_bytes'] and
            digest(rx.replace(b'\r\n', b'\n')) == meter['RX_text_UTF8_LF_sha256'] and
            len(rx.replace(b'\r\n', b'\n')) == meter['RX_text_UTF8_LF_bytes'] and
            wire == read(record / 'RESPONSE.json') == event['response'] and wire['id'] == ident and
            wire['result']['isError'] is False,
            'archived_response_and_mcp_stdio_differ')
    blocks = wire['result']['content']
    require(len(blocks) == 4 and blocks[0]['type'] == 'text' and
            all(x['type'] == 'image' and x['mimeType'] == 'image/png' for x in blocks[1:]), 'wrong_public_envelope')
    text = blocks[0]['text'].encode()
    images = [base64.b64decode(x['data'], validate=True) for x in blocks[1:]]
    trace, = [row for row in audit if row['event'] == 'request_trace'
              and row['trace']['annotations'].get('mcp_request_id') == ident]
    relevant = [row for row in audit if row.get('request_id') == trace['request_id']]
    formatter, = [row['image_delivery'] for row in relevant if row['event'] == 'active_observation_mcp_content']
    attempts = [row for row in relevant if row['event'] == 'active_observation_render_attempt']
    require(formatter['projection_status'] == 'brief' and formatter['native_blocks_constructed'] == 3 and
            formatter['public_text_bytes'] == len(text) and formatter['PNG_bytes'] == sum(map(len, images)) and
            all(row['identity_check']['compatible'] is True for row in relevant),
            'formatter_or_installed_source_identity_differs')
    archive = event['producer_archive']
    require(archive['index'] == number and archive['new_observations_for_archive'] == 0,
            'archive_did_not_retain_same_returned_producer_object')
    producer_raw = verified(archive['path'], archive['sha256'], slot)
    context_path = Path(archive['read_context']).resolve()
    require(context_path.is_relative_to(slot.resolve()), 'archive_context_outside_owned_slot')
    context = read(context_path)
    timings = {'server_rpc_ms': milliseconds(meter['request_received_ns'], meter['reply_completed_ns']),
               'client_rpc_ms': milliseconds(receipt['started_ns'], receipt['closed_ns']),
               'caller_window_ms': milliseconds(event['started_ns'], event['closed_ns']),
               'archive_producer_snapshot_ms': milliseconds(archive['producer_returned_ns'], archive['saved_ns']),
               'public_formatter_ms': stage_ms(formatter),
               'selected_png_read_ms': sum(row['read_ns'] for row in formatter['frames']) / 1e6}
    return json.loads(text), images, json.loads(producer_raw), attempts, timings, {
        'producer_archive_sha256': digest(producer_raw), 'wire_response_sha256': digest(rx),
        'wire_request_sha256': digest(tx), 'public_body_sha256': digest(text),
        'producer_archive_bytes': len(producer_raw), 'rpc_bytes': len(rx), 'public_text_bytes': len(text),
        'public_png_bytes': sum(map(len, images)), 'request_id': ident,
        'read_context_sha256': digest(context_path.read_bytes()),
        'public_png_hashes': [digest(raw) for raw in images],
        'retained_mesh_array_bytes': sum(
            array.get('bytes', array.get('nbytes', 0)) for selection in context['after'].get('selections', [])
            for array in selection['mesh_arrays'])}


def assess_call(slot, event, meter, audit, req, truth, terminal_source, product_sha, arm, hot):
    public, images, product, attempts, timing, wire = audit_wire(slot, event, meter, audit, req)
    require(public['schema'] == 'active-observation-region-task-brief-v1' and public['read_only'] is True and
            product['read_only'] is True and public['status'] == product['status'] == 'complete' and
            public['session_id'] == product['session_id'] and not product['execution_authority'], 'unexpected_observe_result')
    binding = product['binding']
    require(binding['capture_scope'] == 'complete_scene_meshes' and binding['runtime_source_sha256'] == product_sha and
            all(public['binding'][k] == binding[k] for k in ('runtime_source_sha256', 'source_binding_sha256',
                'binding_sha256', 'document_epoch', 'geometry_identity', 'scene_revision', 'capture_state')),
            'public_body_current_source_or_installed_sha_drift')
    current = {row['name']: row for row in terminal_source['objects']}
    scopes = scope_objects(product, binding, current)
    product_rows = {row['object_name']: row for row in product['facts']['region_task']['rows']}
    public_rows = {row['object_name']: row for row in public['region_task']['rows']}
    require(set(product_rows) == set(public_rows) == {'M02', 'M06', 'M09'} and len(product['facts']['region_task']['rows'])
            == len(public['region_task']['rows']) == 3, 'task_roster_or_denominator_changed')
    expected = {row['object_name']: row for row in truth['eligible']}
    quantities = {}
    for name, row in product_rows.items():
        source_row = public_rows[name]
        require(set(row) == set(source_row) and all(row[k] == source_row[k] for k in row if k != 'complete_witness'),
                'producer_and_public_task_facts_differ/' + name)
        require('area_m2' not in row and 'unit_normal_world' not in row, 'unexpected_numeric_overlay')
        quantities[name] = same_geometry(row, expected[name], current[name], binding)
    unknown = product_rows['M06']
    require(unknown['status'] == 'unknown' and unknown['complete_witness'] is public_rows['M06']['complete_witness'] is None and
            unknown['reason'] == expected['M06']['expected_unknown_reason'] and
            set(unknown['view_reasons']['positive_area_occlusion']) == set(truth['directions']) and
            all(any(Fraction(x['rectangle_overlap_fraction']) > 0 for x in item['positive_area_occluders'])
                for item in expected['M06']['finite_direction_proofs'].values()),
            'M06_unknown_is_not_supported_in_all_registered_directions')
    selected = product['frames']
    constructed = product['constructed_frames']
    by_id = {row['frame_identity']: row for row in constructed}
    require(len(by_id) == len(constructed) and all(by_id.get(row['frame_identity']) == row for row in selected) and
            len({row['image_ref'] for row in constructed}) == len(constructed), 'duplicate_or_unconstructed_frame_reference')
    image_by_id = {frame['frame_identity']: img for frame, img in zip(selected, images, strict=True)}
    checked = [frame_payload(slot, frame, scopes[frame['scope_id']], terminal_source, truth,
                             image_by_id.get(frame['frame_identity'])) for frame in constructed]
    require([(r['object_name'], r['view']) for r in checked] == EXPECTED_CONSTRUCTION[arm], 'construction_sequence_drift')
    selected_ms = {item['frame_identity']: item for item in checked}
    delivered = [selected_ms[frame['frame_identity']] for frame in selected]
    require([(row['object_name'], row['view']) for row in delivered] == SELECTED, 'selected_frame_sequence_drift')
    image_rows = public['images']['rows']
    public_columns = ['scope_id', 'camera_identity', 'view_name', 'frame_identity', 'image_ref',
                      'image_sha256', 'native_content_block_index']
    require(public['images']['columns'] == public_columns and
            image_rows == [[row[key] for key in public_columns[:-1]] + [i]
                           for i, row in enumerate(selected, start=1)], 'brief_image_index_order_or_reference_drift')
    for scope_id, scope in scopes.items():
        ids = [r['frame_identity'] for r in checked if r['scope_id'] == scope_id]
        require(scope['frame_refs'] == ids and [x['frame_identity'] for x in scope['steps']] == ids and
                [x['frame_identity'] for x in scope['facts']['observations']] == ids and
                scope['facts']['coverage']['state_updates'] == len(ids), 'actual_observation_history_mismatch')
    for name, view in VIEWS.items():
        row = product_rows[name]
        proof = row['complete_witness']
        resolved = selected_ms[proof['frame_identity']]
        scope = scopes[proof['scope_id']]
        require(row['status'] == 'covered' and row['reason'] == 'observed_readable' and
                scope['binding']['region_source'] == row['source'] and
                resolved['scope_id'] == proof['scope_id'] and resolved['object_name'] == name and
                resolved['view'] == view == proof['view_name'] and resolved['ref'] == proof['image_ref'] and
                proof['selected_for_delivery'] is True and resolved['independent_pixels'][name]['qualifies'],
                'invalid_or_stale_complete_witness/' + name)
        idx = delivered.index(resolved) + 1
        require(public_rows[name]['complete_witness'] == {**proof, 'native_content_block_index': idx},
                'brief_witness_reference_does_not_resolve/' + name)
        observation, = [x for x in scope['facts']['observations'] if x['frame_identity'] == proof['frame_identity']]
        pixel = observation['pixel_rows'][proof['pixel_row_index']]
        independent = resolved['independent_pixels'][name]
        require(pixel['roi_id'] == row['roi_id'] and pixel['readable'] is True and
                (pixel['visible_surface_pixels'], pixel['contrasting_boundary_pixels']) ==
                (independent['target_surface_pixels'], independent['contrasting_boundary_pixels']),
                'native_pixel_claim_differs_from_independent_recomputation/' + name)
    if arm == 'A':
        hidden, = [row for row in checked if (row['object_name'], row['view']) == ('M09', 'SCENE')]
        require(hidden['independent_pixels']['M09']['target_surface_pixels'] == 0 and
                not hidden['independent_pixels']['M09']['qualifies'], 'baseline_M09_SCENE_does_not_demonstrate_occlusion')
    actual = 0 if hot else len(EXPECTED_CONSTRUCTION[arm])
    work = product['work']
    require(len(attempts) == meter['raster_actual'] == work['raster_attempts'] == work['raster_completed'] == actual and
            work['result_cache_hit'] is hot and work['frame_reuses'] == (3 if hot else 0) and
            work['index_calls'] == (0 if hot else 3) and work['capture_calls'] == 1,
            'producer_wire_render_attempt_or_hot_cache_disagreement')
    require([event['view_name'] for event in attempts] ==
            ([] if hot else [frame['view'] for frame in checked]) and
            all(event['session_id'] == product['session_id'] for event in attempts), 'raster_attempt_order_or_session_differs')
    require(public['image_delivery']['selected_image_count'] == 3 and
            public['image_delivery']['new_raster_attempts'] == actual and
            public['image_delivery']['frame_reuses'] == work['frame_reuses'],
            'brief_image_delivery_work_mismatch')
    stages = {name: stage_ms(value) for name, value in product['stages'].items()}
    timing.update({
        'service_ms': stages['service_total'],
        'capture_ms': stages['host_capture'],
        'index_ms': sum(duration for name, duration in stages.items() if name.startswith('index_')),
        'global_index_ms': stages.get('index_global', 0),
        'raster_ms': 0 if hot else sum(row['raster_ms'] for row in checked),
        'render_publish_ms': sum(duration for name, duration in stages.items() if name.startswith('render_and_publish_')),
        'PNG_NPZ_publication_ms': 0 if hot else sum(row['publish_png_npz_ms'] for row in checked),
        'feedback_ms': sum(duration for name, duration in stages.items() if name.startswith('feedback_')),
        'scoped_stages_ms': stages})
    return {'new_constructed': actual, 'cached_generation_construction': len(constructed), 'cache_hit': hot,
            'session_id': product['session_id'], 'source_binding': binding['source_binding_sha256'],
            'capture_state': binding['capture_state'], 'work': work, 'timing': timing, 'wire': wire,
            'geometry': quantities, 'frames': checked, 'selected_frame_ids': [r['frame_identity'] for r in selected],
            'selected': [{k: f[k] for k in ('object_name', 'view', 'ref', 'image_sha256', 'png_bytes',
                          'camera_sha256', 'independent_pixels')} for f in delivered]}


def assess_slot(slot, label, request, truth, installed):
    outcome_path = slot / 'SLOT_RESULT.json'
    raw_result = outcome_path.read_bytes()
    result = json.loads(raw_result)
    started = read(slot / 'SLOT_STARTED.json')
    publication = read(slot / 'SLOT_PUBLICATION.json')
    arm = label[0]
    require(result['status'] == publication['status'] == 'completed' and
            not result['errors'] and publication['owned_budget_passed'] is True and
            publication['result_sha256'] == digest(raw_result) and all(row['label'] == label for row in
                                                                     (result, started, publication)),
            'original_owned_slot_not_successfully_published')
    require(result['arm'] == started['arm'] == arm and
            result['model_consumers'] == 0 and not (slot / 'consumer').exists(), 'model_or_wrong_arm_in_owned_slot')
    require(result['asset_sha256'] == truth['asset_sha256'] and
            result['task_deadline_ns'] - result['started_ns'] == 450_000_000_000 and
            result['owned_deadline_ns'] - result['started_ns'] == 600_000_000_000,
            'original_asset_or_absolute_deadline_differs')
    asset = Path(truth['asset_path'])
    source_sha = installed[arm]['source_sha256']
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    require(ready['product_source_sha256'] == identity['source_sha256'] == result['product_source_sha256'] ==
            source_sha and identity['source_kind'] == 'installed_distribution' and
            identity['source_file_count'] == 143 and len(installed[arm]['source_manifest']) == 143 and
            asset.read_bytes() == (slot / 'native/input.blend').read_bytes(),
            'wrong_live_product_install_or_asset_copy')
    closure = read(slot / 'RUNTIME_CLOSE.json')
    require(not closure['errors'] and closure['public_MCP_exit']['confirmed'] and closure['public_MCP_exit']['exited']
            and closure['public_MCP_exit']['handle_closed'] and closure['public_MCP_exit']['exit_code'] == 0,
            'installed_mcp_did_not_close_cleanly')
    terminal_source, native = terminal(slot, result, truth['asset_sha256'])

    events = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    meter_rows = [row for row in rows(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    meter = {row['id']: row for row in meter_rows}
    require(len(events) == len(meter_rows) == len(meter) == 2 and [r['index'] for r in events] == [1, 2] and
            [r['request']['id'] for r in events] == list(meter),
            'cold_and_warm_original_calls_required')
    require(result['ready_ns'] <= events[0]['started_ns'] <= events[0]['closed_ns'] <=
            events[1]['started_ns'] <= events[1]['closed_ns'] <= min(result['task_deadline_ns'], result['cleanup_started_ns']) <=
            publication['published_ns'] <= result['owned_deadline_ns'], 'owned_process_or_request_window_not_closed')
    audit = rows(slot / 'product_audit.jsonl')
    cold, hot = [assess_call(slot, event, meter[event['request']['id']], audit, request, truth, terminal_source,
                            source_sha, arm, hot=ordinal == 1) for ordinal, event in enumerate(events)]
    require(cold['session_id'] == hot['session_id'] and cold['capture_state'] == hot['capture_state'] and
            cold['source_binding'] == hot['source_binding'] and cold['geometry'] == hot['geometry'] and
            cold['selected_frame_ids'] == hot['selected_frame_ids'] and cold['selected'] == hot['selected'] and
            cold['frames'] == hot['frames'], 'hot_revisit_failed_exact_selected_image_or_generation_reuse')
    require(cold['wire']['public_png_hashes'] == hot['wire']['public_png_hashes'], 'hot_wire_changed_original_PNGs')
    budget = result['budget']
    current = budget['slots'][label]
    claims = [row['claim']['kind'] for row in budget['records'] if row['claim']['label'] == label]
    require(current['business_admissions'] == claims.count('business_tool') == 2 and
            current['raster_actual'] == current['raster_upper'] == cold['new_constructed'] and
            claims.count('Blender_start') == 1 and claims.count('consumer_task') == 0,
            'retained_attempt_budget_differs_from_verified_observations')
    owned_ms = milliseconds(result['started_ns'], publication['published_ns'])
    return {'label': label, 'arm': arm, 'status': 'completed', 'passed': True, 'source_sha256': source_sha,
            'product_distribution_version': identity['distribution_version'],
            'native_PID': ready['native_pid'], 'product_PID': ready['product_PID'],
            'slot_result_sha256': digest(raw_result), 'publication_sha256': digest((slot / 'SLOT_PUBLICATION.json').read_bytes()),
            'native': native, 'business_attempts': 2, 'raster_attempts': current['raster_actual'],
            'owned_awake_window': [result['started_ns'], publication['published_ns']], 'owned_window_ms': owned_ms,
            'startup_to_ready_ms': milliseconds(result['started_ns'], result['ready_ns']),
            'finished_last_request_to_publication_ms': milliseconds(events[1]['closed_ns'], publication['published_ns']),
            'cold': cold, 'hot': hot}


def compare_pair(baseline, candidate):
    cold1, cold2 = baseline['cold'], candidate['cold']
    hot1, hot2 = baseline['hot'], candidate['hot']
    require(cold1['geometry'] == cold2['geometry'] and hot1['geometry'] == hot2['geometry'],
            'paired_current_geometry_or_region_reason_changed')
    require(cold1['wire']['public_png_hashes'] == cold2['wire']['public_png_hashes'] ==
            hot1['wire']['public_png_hashes'] == hot2['wire']['public_png_hashes'],
            'paired_selected_PNGs_changed')
    selected_quality = ('view', 'object_name', 'image_sha256', 'png_bytes', 'camera_sha256', 'independent_pixels')
    require(all(all(a[key] == b[key] for key in selected_quality)
                for a, b in zip(cold1['selected'], cold2['selected'], strict=True)),
            'paired_actual_camera_or_independent_pixel_evidence_changed')
    require((cold1['new_constructed'], cold2['new_constructed'], hot1['new_constructed'], hot2['new_constructed']) ==
            (4, 3, 0, 0), 'paired_new_construction_reduction_not_demonstrated')
    removed, = [row for row in cold1['frames'] if (row['object_name'], row['view']) == ('M09', 'SCENE')]
    scope_id = removed['scope_id']
    stages = cold1['timing']['scoped_stages_ms']
    separable = {'render_publish_ms': stages[f'render_and_publish_{scope_id}_SCENE'],
                 'feedback_ms': stages[f'feedback_{scope_id}_SCENE'], 'raster_ms': removed['raster_ms'],
                 'npz_bytes': removed['npz_bytes'], 'png_bytes': removed['png_bytes'],
                 'array_payload_bytes': removed['declared_array_payload_bytes']}
    timing_keys = sorted(k for k in cold1['timing'] if k.endswith('_ms') and k != 'scoped_stages_ms')
    return {'A': baseline['label'], 'B': candidate['label'], 'passed': True, 'cold_new_construction': [4, 3],
            'hot_new_construction': [0, 0], 'owned_window_A_B_ms': [baseline['owned_window_ms'], candidate['owned_window_ms']],
            'owned_candidate_minus_baseline_ms': candidate['owned_window_ms'] - baseline['owned_window_ms'],
            'cold_candidate_minus_baseline_ms': {k: cold2['timing'][k] - cold1['timing'][k] for k in timing_keys},
            'hot_candidate_minus_baseline_ms': {k: hot2['timing'][k] - hot1['timing'][k] for k in timing_keys},
            'cold_candidate_minus_baseline_bytes': {
                k: after[k] - before[k]
                for before, after, keys in ((cold1['wire'], cold2['wire'], ('rpc_bytes', 'public_text_bytes',
                  'public_png_bytes', 'producer_archive_bytes', 'retained_mesh_array_bytes')),
                    (cold1['work'], cold2['work'], ('PNG_bytes', 'NPZ_bytes', 'array_payload_bytes')))
                for k in keys},
            'candidate_removed_M09_SCENE_observation': separable,
            'selected_PNG_hashes': cold1['wire']['public_png_hashes'],
            'selected_refs_A_B': [[row['ref'] for row in item['selected']] for item in (cold1, cold2)],
            'independent_pixels': {name: next(row['independent_pixels'][name] for row in cold2['selected']
                                              if row['object_name'] == name) for name in VIEWS}}


def assess(run, request_path, pair_count):
    truth_path = FORMAL / 'fixture/CURRENT_TRUTH.json'
    truth = json.loads(verified(truth_path, TRUTH_SHA256, FORMAL))
    request = read(request_path)
    require(request == {'include_image': True, 'query': {'mode': 'active_observation', 'region_task': {
        'area_min_m2': 0.0078125, 'area_max_m2': 0.03125, 'normal_z_min': 0.75}}},
        'registered_default_brief_request_required')
    installed = {'A': read(BASELINE_BINDING), 'B': read(CANDIDATE_BINDING)}
    require(installed['A']['source_sha256'] == BASELINE_SHA256 and
            installed['B']['source_sha256'] != BASELINE_SHA256, 'registered_installed_arms_required')
    sys.path.insert(0, installed['A']['dependency_root'])
    names = ORDER[:pair_count * 2]
    slots, pairs = {}, []
    for label in names:
        slot = run / 'slots' / label
        try:
            slots[label] = assess_slot(slot, label, request, truth, installed)
        except Exception as error:
            result_path = slot / 'SLOT_RESULT.json'
            slots[label] = {'label': label, 'arm': label[0], 'status': 'failed' if slot.exists() else 'unrun',
                            'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                            'slot_result_sha256': digest(result_path.read_bytes()) if result_path.exists() else None}
    for pair in range(1, pair_count + 1):
        a, b = slots[f'A{pair}'], slots[f'B{pair}']
        try:
            require(a['passed'] and b['passed'], 'incomplete_or_failed_original_pair')
            pairs.append(compare_pair(a, b))
        except Exception as error:
            pairs.append({'A': a['label'], 'B': b['label'], 'passed': False,
                          'error_type': type(error).__name__, 'error': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    total_attempts = sum(row['raster_attempts'] for row in complete)
    order_ok = all(a['owned_awake_window'][1] <= b['owned_awake_window'][0]
                   for a, b in zip(complete, complete[1:]))
    passed = order_ok and all(row['passed'] for row in pairs)
    report = {'schema': 'm4-cross-scale-local-first-view-paired-review-v1', 'passed': passed,
              'registered_order': list(ORDER), 'reviewed_slot_count': len(names), 'attempted_slot_order': list(slots),
              'closed_qualifying_slot_count': len(complete), 'pair_denominator': 3,
              'reviewed_pair_count': pair_count, 'reviewed_passing_pairs': sum(row['passed'] for row in pairs),
              'order_nonoverlap': order_ok, 'model_consumers': 0, 'completed_verified_raster_attempts': total_attempts,
              'completed_verified_business_attempts': sum(row['business_attempts'] for row in complete),
              'current_truth_sha256': TRUTH_SHA256, 'request_sha256': digest(request_path.read_bytes()),
              'scope': 'Zero-model paired wall observations. Inclusive and nested stage times are separate.',
              'slots': list(slots.values()), 'pairs': pairs}
    if passed:
        report['median_candidate_minus_baseline_ms'] = {
            'owned_window': median(row['owned_candidate_minus_baseline_ms'] for row in pairs),
            **{phase: {k: median(row[f'{phase}_candidate_minus_baseline_ms'][k] for row in pairs)
                       for k in pairs[0][f'{phase}_candidate_minus_baseline_ms']}
               for phase in ('cold', 'hot')}}
    return report


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--runtime', type=Path, default=RUN)
    args.add_argument('--pairs', type=int, choices=(1, 2, 3), default=3)
    args.add_argument('--request', type=Path, default=NS / 'inputs/REQUEST.json')
    args.add_argument('--output', type=Path, default=HERE / 'PAIR_REVIEW.json')
    cfg = args.parse_args()
    result = assess(cfg.runtime, cfg.request, cfg.pairs)
    write(cfg.output, result)
    print(json.dumps({'passed': result['passed'], 'pairs': result['pairs'],
                      'failed_slots': [row for row in result['slots'] if not row['passed']]}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
