"""Score production source-region replies against owned Blender snapshots."""

import argparse
from base64 import b64decode
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'm4_yanyite_dual_curved_region_native_001/score/oracle.py'
ORACLE = run_path(str(PRIOR))
ASSET = ORACLE['ASSET']
TARGET = ORACLE['TARGET']
REFERENCE = ORACLE['REFERENCE']
INDEX_DOMAIN = ORACLE['INDEX_DOMAIN']
read, pin, require, write = (ORACLE[key] for key in ('load', 'pin', 'require', 'write'))
ORDER = [('upper', False), ('lower', False), ('upper', True), ('upper', True)]
SAME_SCENE = ('source', 'objects', 'source_face_offsets', 'display_object_mask',
              'layer_collections', 'scene_cameras')
EXPECTED_DISTANCE = {'upper': 0.37011719389236364, 'lower': 0.4355468820753541}


def canonical_sha(value):
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return sha256(body.encode('utf8')).hexdigest()


def near(a, b, tolerance=1e-7):
    return (isinstance(a, (list, tuple)) and len(a) == len(b)
            and all(type(x) in (int, float) and abs(x-y) <= tolerance for x, y in zip(a, b, strict=True)))


def selection(snapshot):
    """Select ordered triangle rows independently in both host coordinate domains."""
    target, cube = ({row['name']: row for row in snapshot['objects']}[name]
                    for name in (TARGET, REFERENCE))
    scale = snapshot['source']['scale_length']
    tm, cm = target['evaluated'], cube['evaluated']
    native = ORACLE['truths'](tm['vertices_world_m'], tm['triangles'],
                              cm['vertices_world_m'], cm['triangles'])
    matrix = ORACLE['truths'](ORACLE['transform'](tm['vertices'], target['matrix_world'], scale),
                              tm['triangles'],
                              ORACLE['transform'](cm['vertices'], cube['matrix_world'], scale),
                              cm['triangles'])
    for name, row in matrix.items():
        require(row['triangle_ids'] == native[name]['triangle_ids']
                and row['vertex_ids'] == native[name]['vertex_ids']
                and abs(row['distance_m'] - EXPECTED_DISTANCE[name]) <= 1e-7,
                'independent_current_selection_or_distance_changed/' + name)
    return {name: row['triangle_ids'] for name, row in matrix.items()}


def original(slot, path, digest):
    item = pin(path)
    require(Path(item['path']).is_relative_to(slot) and item['sha256'] == digest,
            'original_not_bound_to_closed_slot/' + Path(path).name)
    return item


def scene_evidence(slot, arm, result):
    historical, prior = ORACLE['history']()
    initial_path = slot / 'initial_capture/TERMINAL_SOURCE.json'
    terminal_path = slot / 'TERMINAL_SOURCE.json'
    initial, terminal = read(initial_path), read(terminal_path)
    ORACLE['verify_terminal'](initial, historical, prior)
    geometry = ORACLE['verify_terminal'](terminal, historical, prior)
    require(all(initial[k] == terminal[k] for k in SAME_SCENE),
            'owned_initial_terminal_geometry_or_display_changed')
    target, cube = ({row['name']: row for row in terminal['objects']}[name]
                    for name in (TARGET, REFERENCE))
    require(target['visible_get'] is True and cube['visible_get'] is False
            and len(cube['evaluated']['triangles']) == 12, 'hidden_cube_not_complete_reference')

    device = read(slot / 'DEVICE_EVIDENCE.json')
    close = read(slot / 'RUNTIME_CLOSE.json')
    fp = close['Blender_status']['closed']
    config = close['Blender_status']['config']
    retained = close['Blender_close']
    mcp = close['public_MCP_close']
    receipt = device['terminal_source']
    end = original(slot, receipt['path'], receipt['sha256'])
    require(Path(end['path']) == terminal_path and end['bytes'] == receipt['bytes']
            and receipt['status'] == 'complete' and device['label'] == arm
            and receipt['worker']['pid'] == terminal['source']['pid'] == fp['pid'] == retained['pid']
            and not fp['poisoned'] and fp['initial_geometry_fingerprint'] == fp['final_geometry_fingerprint'],
            'current_terminal_receipt_or_fingerprint_mismatch')
    require(close['errors'] == [] and not retained['error'] and retained['exit_code'] == 0
            and retained['process_reaped'] is True and retained['source_file_unchanged'] is True
            and retained['protected_files_unchanged'] is True and close['installed_module_guard'] is True
            and mcp['production_eof_and_exit_verified'] is True and mcp['confirmed'] is True
            and mcp['exit_code'] == 0 and mcp['stdout_eof_seen'] is True
            and mcp['reader_stopped'] is True and mcp['process_handle_closed'] is True
            and mcp['errors'] == mcp['reader_errors'] == [] and mcp['unconsumed_response_lines'] == 0
            and mcp['pipes_closed'] == {'stdin': True, 'stdout': True, 'stderr': True},
            'real_blender_or_mcp_did_not_close_cleanly')
    for method in ('Blender_exit', 'public_MCP_exit'):
        row = close[method]
        require(row['confirmed'] and row['exited'] and row['handle_closed'] and row['exit_code'] == 0,
                'real_retained_process_handle_not_closed/' + method)
    eof = read(Path(original(slot, mcp['worker_eof']['path'], mcp['worker_eof']['sha256'])['path']))
    exited = read(Path(original(slot, mcp['worker_exit']['path'], mcp['worker_exit']['sha256'])['path']))
    require(eof['pid'] == exited['pid'] == mcp['pid'] != retained['pid']
            and eof['source_sha256'] == exited['source_sha256'] == config_source(slot)
            and eof['input_eof_observed'] is True and exited['input_eof_observed'] is True
            and eof['closed'] is True and exited['production_returned'] is True
            and exited['production_return_code'] == 0, 'worker_eof_record_is_not_current_exit')
    asset_copy = original(slot, terminal['source']['asset_copy'], ASSET)
    require(asset_copy == original(slot, config['asset_copy'], ASSET)
            and pin(config['asset'])['sha256'] == ASSET
            and pin(config['blender'])['sha256'] == config['blender_sha256']
            and result['window']['opened_ns'] <= close['started_ns'] <= close['closed_ns']
            <= result['window']['closed_ns'], 'source_copy_or_closure_window_changed')
    return terminal, geometry, device, {
        'initial': pin(initial_path), 'terminal': end, 'closure': pin(slot/'RUNTIME_CLOSE.json'),
        'asset_copy': asset_copy, 'Blender_pid': retained['pid'], 'MCP_pid': mcp['pid'],
        'Blender_sha256': config['blender_sha256'], 'asset_sha256': ASSET}


def config_source(slot):
    config = read(slot / 'PRODUCT_CONFIG.json')
    identity = read(slot / 'MCP_IDENTITY.json')
    require(identity['source_kind'] == 'installed_distribution'
            and config['expected_identity']['source_sha256'] == identity['source_sha256'],
            'actual_installed_product_source_not_bound')
    return identity['source_sha256']


def json_lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def production_calls(slot):
    """Bind actual stdio request and response bytes to same-call producer archives."""
    records = json_lines(slot / 'PUBLIC_REQUESTS.jsonl')
    require(len(records) == len(ORDER), 'wrong_direct_production_call_count')
    journal = json_lines(slot / 'mcp_io/MCP_IO.jsonl')
    worker = [row for row in journal if row['method'] == 'tools/call']
    require(len(worker) == len(records), 'wrong_production_worker_tool_count')
    calls = []
    for index, (rec, log) in enumerate(zip(records, worker, strict=True), 1):
        wire = rec['receipt']
        tx_path = slot/'mcp'/f"rpc_{wire['index']:02d}"/'TX.bin'
        rx_path = tx_path.with_name('RX.bin')
        tx_bytes, rx_bytes = tx_path.read_bytes(), rx_path.read_bytes()
        tx, rx = json.loads(tx_bytes), json.loads(rx_bytes)
        worker_lf = rx_bytes.removesuffix(b'\r\n') + b'\n' if rx_bytes.endswith(b'\r\n') else rx_bytes
        require(rec['index'] == index and wire['error'] is None and wire['method'] == tx['method'] == 'tools/call'
                and tx['params']['name'] == 'human_eye_scene_observe'
                and tx['id'] == rx['id'] == rec['id'] == wire['id'] == log['id'] == log['response_id']
                and len(tx_bytes) == wire['TX_bytes'] == log['TX_bytes']
                and len(rx_bytes) == wire['RX_bytes']
                and sha256(tx_bytes).hexdigest() == log['TX_sha256']
                and sha256(rx_bytes).hexdigest() == wire['RX_sha256']
                and len(worker_lf) == log['RX_text_UTF8_LF_bytes']
                and sha256(worker_lf).hexdigest() == log['RX_text_UTF8_LF_sha256']
                and wire['closed_ns']-wire['started_ns'] == wire['elapsed_ns'] > 0
                and log['reply_completed_ns']-log['request_received_ns'] == log['request_to_reply_ns'] > 0,
                'mcp_actual_wire_or_worker_record_mismatch')
        bound = rec['producer_archive']
        producer = original(slot, bound['path'], bound['sha256'])
        require(bound['index'] == index and bound['new_observations_for_archive'] == 0
                and Path(producer['path']) == slot/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json',
                'wrong_producer_archive_or_repeated_observation')
        full = read(Path(producer['path']))
        require(rx['result']['isError'] is False, 'legitimate_live_observation_rejected')
        blocks = rx['result']['content']
        require(blocks[0]['type'] == 'text' and all(block['type'] == 'image' for block in blocks[1:]),
                'unexpected_live_content_blocks')
        packet = json.loads(blocks[0]['text'])
        calls.append((tx['params']['arguments'], packet, blocks,
                      full, {'TX': pin(tx_path), 'RX': pin(rx_path), 'producer': producer,
                             'wire_ns': wire['elapsed_ns'], 'worker_ns': log['request_to_reply_ns'],
                             'raster_actual': log['raster_actual'], 'id': rec['id']}))
    return calls


def optional_attachment(slot, recorded):
    wire = recorded.get('optional_read_images')
    if wire is None:
        return None
    root = slot/'attachment_stdio'/f"rpc_{wire['index']:02d}"
    tx, rx = read(root/'TX.bin'), read(root/'RX.bin')
    require(wire['error'] is None and wire['method'] == tx['method'] == 'tools/call'
            and tx['id'] == rx['id'] == wire['id'] == 'image-read'
            and pin(root/'RX.bin')['sha256'] == wire['RX_sha256']
            and tx['params']['name'] == 'read_images' and rx['result']['isError'] is False,
            'optional_attachment_not_actual_public_wire')
    text, image = rx['result']['content']
    capsule = json.loads(text['text'].splitlines()[1])
    ref, = tx['params']['arguments']['refs']
    capsule['ref'] = ref
    capsule['bytes'] = b64decode(image['data'], validate=True)
    require(text['type'] == 'text' and image['type'] == 'image' and image['mimeType'] == 'image/png'
            and sha256(capsule['bytes']).hexdigest() == capsule['image_sha256']
            and recorded['closure']['attachment_stdio_close']['confirmed']
            and recorded['closure']['owner_close']['confirmed'],
            'optional_attachment_image_or_closure_changed')
    return capsule


def check_point(mapping, point, mesh, known_faces):
    faces = mapping['source_triangle_indices']
    vertices = mapping['source_vertex_indices']
    require(mapping['exact_membership'] is True and mapping['status'] == 'measured'
            and mapping['index_domain'] == INDEX_DOMAIN and faces and len(set(faces)) == len(faces)
            and set(faces).issubset(known_faces)
            and all(ORACLE['triangle_contains'](point, [mesh['vertices_world_m'][v]
                                                        for v in mesh['triangles'][i]]) for i in faces)
            and all(point == mesh['vertices_world_m'][v] for v in vertices),
            'reported_nearest_point_not_on_its_true_current_source_rows')


def measurement(args, packet, full, terminal, truth, name, has_image):
    query = args['query']
    region, parent, task = full['region_ref'], full['binding'], full['task_result']
    target, cube = ({row['name']: row for row in terminal['objects']}[key]
                    for key in (TARGET, REFERENCE))
    rows = truth['triangle_ids']
    capture = parent['capture_state']
    geometry = [{'host_id': obj['object_id'], 'instance_id': obj['instance_id'],
                 'vertices': obj['evaluated']['vertices_world_m'], 'faces': obj['evaluated']['triangles']}
                for obj in terminal['objects']]
    observed = [(x['object_name'], x['host_id'], x['instance_id']) for x in parent['objects']]
    require(query['mode'] == 'source_region' and query['requested_facts'] == ['surface_proximity']
            and query['reference'] == {'name': REFERENCE} and args['include_image'] is has_image
            and query['region'] == {'object': {'name': TARGET}, 'source_triangle_indices': rows}
            and observed == [(o['name'], o['object_id'], o['instance_id']) for o in terminal['objects']]
            and task['binding'] == parent and task['region_ref'] == region == packet['region_ref']
            and full['read_only'] is packet['read_only'] is task['read_only'] is True
            and full['execution_authority'] is packet['execution_authority'] is task['execution_authority'] is False
            and full['result_kind'] == packet['result_kind'] == 'source_region'
            and task['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
            and parent['capture_scope'] == 'complete_scene_meshes'
            and parent['ordered_geometry_sha256'] == region['ordered_geometry_sha256'] == canonical_sha(geometry)
            and parent['coordinate_frame'] == 'world' and parent['unit'] == 'm'
            and parent['image_scope']['participation_mask'] == terminal['display_object_mask']
            and parent['document_epoch'] == region['document_epoch']
            and {k: capture[k] for k in ('instance_id', 'epoch', 'revision')} == region['capture_generation']
            and type(capture['epoch']) is int and type(capture['revision']) is int and bool(capture['instance_id'])
            and (region['host_id'], region['instance_id']) == (target['object_id'], target['instance_id'])
            and region['source_triangle_indices'] == rows, 'public_selected_source_or_parent_changed/' + name)
    public = packet['task_result']
    ref = task['reference']
    fact = task['facts']['surface_proximity']
    val = fact['value']
    witness = val['nearest_witness']
    require(public['reference'] == ref and public['measurement_scope'] == task['measurement_scope']
            and (ref['name'], ref['object_id'], ref['instance_id'])
            == (REFERENCE, cube['object_id'], cube['instance_id'])
            and terminal['objects'][ref['object_index']]['object_id'] == cube['object_id']
            and fact == public['facts']['surface_proximity'] and fact['status'] == 'measured'
            and near([val['distance_m']], [truth['distance_m']])
            and near(witness['direction_a_to_b'], [0, 0, 1])
            and near(witness['b'], [*witness['a'][:2], 1.0])
            and near([witness['b'][2] - witness['a'][2]], [val['distance_m']]),
            'public_measurement_not_attaining_complete_cube_surface/' + name)
    mapping = task['source_mapping']
    compact = mapping['region']
    real = target['evaluated']
    vertices = compact['submesh_to_source_vertex_indices']
    indexed = [real['triangles'][i] for i in rows]
    require(compact['index_domain'] == INDEX_DOMAIN and compact['submesh_to_source_triangle_indices'] == rows
            and compact['triangles_source_vertices'] == indexed
            and vertices == truth['vertex_ids']
            and [[vertices[i] for i in row] for row in compact['triangles_submesh_vertices']] == indexed,
            'compact_region_mapped_to_different_source_rows')
    check_point(mapping['nearest_witness']['a'], witness['a'], real, set(truth['source_witness_triangle_ids']))
    check_point(mapping['nearest_witness']['b'], witness['b'], cube['evaluated'],
                set(range(len(cube['evaluated']['triangles']))))
    return {'distance_m': val['distance_m'], 'point_pair': witness,
            'nearest_witness_source': mapping['nearest_witness'], 'source_triangles': rows,
            'source_vertices': vertices, 'camera_identity': parent['camera_identity'],
            'region_ref': region, 'binding': parent}


def frame_evidence(slot, terminal, packet, blocks, full, device_frame, selected, read_image):
    frame, = full['frames']
    image, = packet['images']
    binding = full['binding']
    association = ('image_ref', 'view_name', 'frame_identity', 'image_sha256', 'host_binding_sha256',
                   'display_identity', 'image_scope_identity')
    require(all(image[k] == frame[k] for k in association)
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['source_revision'] == binding['scene_revision']
            and frame['image_scope']['participation_mask'] == terminal['display_object_mask']
            and device_frame['producer'] == frame and device_frame['origin'] == 'product'
            and device_frame['ref'] == frame['image_ref']
            and device_frame['object_ids'] == [o['object_id'] for o in terminal['objects']]
            and device_frame['object_instance_ids'] == [o['instance_id'] for o in terminal['objects']]
            and device_frame['source_face_offsets'] == terminal['source_face_offsets'],
            'image_public_device_or_producer_binding_mismatch')
    png = original(slot, frame['image_path'], frame['image_sha256'])
    npz = original(slot, frame['arrays_path'], frame['arrays_sha256'])
    require(str(Path(device_frame['PNG'])) == png['path'] and str(Path(device_frame['NPZ'])) == npz['path']
            and device_frame['PNG_sha256'] == png['sha256'] and device_frame['NPZ_sha256'] == npz['sha256']
            and device_frame['PNG_bytes'] == png['bytes'] == frame['PNG_bytes']
            and device_frame['NPZ_bytes'] == npz['bytes'], 'rendered_original_changed_in_device')
    local = image.get('local_image_path')
    if local is None and read_image:
        local = read_image['local_image_path']
        require(read_image['ref'] == frame['image_ref']
                and read_image['image_sha256'] == png['sha256'], 'public_read_image_returned_other_frame')
    require(local is not None and Path(local).is_absolute() and str(Path(local)) == png['path']
            and image['image_block_index'] == 1 and len(blocks) == 2 and blocks[1]['mimeType'] == 'image/png',
            'public_original_path_or_block_not_same_frame')
    pixels = Path(png['path']).read_bytes()
    require(b64decode(blocks[1]['data'], validate=True) == pixels, 'real_stdout_png_bytes_differ')
    require(not read_image or read_image['bytes'] == pixels, 'optional_attachment_png_bytes_differ')

    mask, offsets = terminal['display_object_mask'], terminal['source_face_offsets']
    with np.load(npz['path'], allow_pickle=False) as archive:
        tri, owners, depth, color = [archive[name] for name in ('triangle_ids', 'owners', 'depth', 'color')]
        require(archive['face_patch_offsets'].tolist() == offsets
                and archive['display_object_mask'].tolist() == mask
                and all(archive[k].item() == frame[k] for k in
                        ('display_identity', 'image_scope_identity', 'owner_mapping_identity', 'triangle_id_scope')),
                'npz_display_or_producer_metadata_not_current')
    w, h = device_frame['size_px']
    require(tri.shape == owners.shape == depth.shape == (h, w) and color.shape == (h,w,3)
            and tri.dtype == owners.dtype == np.dtype('int32') and color.dtype == np.dtype('uint8')
            and np.all((tri >= -1) & (tri < offsets[-1])), 'npz_owner_index_or_image_shape_invalid')
    with Image.open(BytesIO(pixels)) as display:
        require(display.format == 'PNG' and display.size == (w,h)
                and np.array_equal(np.asarray(display.convert('RGB')), color), 'npz_RGB_not_published_PNG')
    foreground = tri >= 0
    expected = np.full((h,w), -1, dtype=np.int32)
    expected[foreground] = np.searchsorted(offsets[1:], tri[foreground], side='right')
    require(np.array_equal(expected, owners) and np.all(np.asarray(mask)[expected[foreground]])
            and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))
            and np.all(np.isposinf(depth[~foreground])), 'npz_pixel_owners_or_depth_not_current_source')
    target = [o['name'] for o in terminal['objects']].index(TARGET)
    picked = (owners == target) & np.isin(tri - offsets[target], selected)
    y, x = np.nonzero(picked)
    rows, counts = np.unique(tri[picked]-offsets[target], return_counts=True)
    visible = packet['visibility']
    private = full['facts']['visibility']
    require(len(rows) > 0
            and all(visible[field] == private[field] for field in visible
                    if field not in ('visible_source_triangle_count', 'unseen_source_triangle_count'))
            and private['visible_source_triangle_indices'] == rows.tolist()
            and private['unseen_source_triangle_indices'] == sorted(set(selected)-set(rows.tolist()))
            and visible['selected_surface_pixels'] == len(x) and visible['visible_source_triangle_count'] == len(rows)
            and visible['selected_source_triangle_count'] == len(selected)
            and visible['unseen_source_triangle_count'] == len(selected) - len(rows)
            and visible['visible_pixel_bounds'] == [int(x.min()), int(y.min()), int(x.max()), int(y.max())]
            and visible['image_ref'] == frame['image_ref'] and visible['frame_identity'] == frame['frame_identity']
            and visible['status'] == 'observed_samples' and visible['complete_witness'] is None
            and 'complete_surface_visibility' in visible['unknown'], 'public_visibility_not_actual_selected_npz_samples')
    return {'PNG': png, 'NPZ': npz, 'frame_identity': frame['frame_identity'],
            'view': frame['view_name'], 'reference': frame['image_ref'], 'pixel_bounds': visible['visible_pixel_bounds'],
            'selected_surface_pixels': len(x), 'visible_source_triangle_count': len(rows),
            'source_pixel_counts': dict(zip(map(str, rows), map(int, counts), strict=True))}


def interval(row):
    value = row['elapsed_ns']
    require(type(value) is int and row['closed_ns']-row['started_ns'] == value >= 0,
            'invalid_service_phase_clock')
    return value


def verify_slot(slot, arm):
    slot = Path(slot).resolve(strict=True)
    result, published = (read(slot/name) for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
    result_pin = pin(slot/'SLOT_RESULT.json')
    require(slot.name == result['label'] == published['label'] == arm and arm in ('A', 'B')
            and result['status'] == published['status'] == 'completed'
            and result['freeze_sha256'] == published['freeze_sha256']
            and published['result_sha256'] == result_pin['sha256'],
            'finished_slot_publication_not_bound')
    window = result['window']
    require(window['closed_ns']-window['opened_ns'] == window['wall_ns'] > 0, 'wrong_full_slot_window')
    terminal, geometry, device, source = scene_evidence(slot, arm, result)
    rows = production_calls(slot)
    meter_file = slot/'mcp_io/REAL_HOST_STAGES.json'
    hosts = read(meter_file)['requests']
    require(len(hosts) == len(result['observations']) == len(ORDER)
            and len(device['frames']) == 1, 'wrong_capture_or_device_frame_count')
    attachment = optional_attachment(slot, result)
    measurements, images, captures = [], [], []
    for n, ((name, has_image), call, host, declared) in enumerate(
            zip(ORDER, rows, hosts, result['observations'], strict=True)):
        args, packet, blocks, full, evidence = call
        require((declared['region'], declared['include_image']) == (name, has_image)
                and declared['host_record']['id'] == evidence['id'],
                'declared_sequence_differs_from_actual_wire')
        value = measurement(args, packet, full, terminal, geometry['matrix64_regions'][name], name, has_image)
        work = full['work']
        expect_capture = work['capture_calls'] == work['capture_source_validation_calls'] == 1
        shared = arm == 'B' and n == 1
        expected_prepare = int(n < 2)
        expected_raster = int(n == 2)
        require(expect_capture and work['prepare_cache_hit'] is (not expected_prepare)
                and work.get('geometry_normalization_shared_hit', False) is shared
                and work['geometry_normalization_calls'] == expected_prepare - int(shared)
                and work['prepare_calls'] == work['region_array_preparation_calls']
                == work['camera_preparation_calls'] == expected_prepare
                and work['raster_attempts'] == work['raster_completed'] == evidence['raster_actual'] == expected_raster
                and work['frame_reuses'] == int(n == 3)
                and len(full['frames']) == len(packet['images']) == len(blocks)-1 == int(has_image),
                'capture_normalization_preparation_or_raster_contract_changed')
        details = full['stages'].get('region_preparation')
        require(bool(details) == bool(expected_prepare)
                and (not shared or interval(details['scene_validation']) > 0),
                'borrowed_scene_skipped_own_validation_or_preparation')
        decoder = host['decoder']
        capture = value['binding']['capture_state']
        require(decoder['capture_state'] == capture and decoder['resources_sent'] == (2 if n == 0 else 0),
                'current_host_capture_state_or_resource_count_changed')
        captures.append(capture)
        if has_image:
            images.append(frame_evidence(slot, terminal, packet, blocks, full, device['frames'][0],
                                         value['source_triangles'], attachment))
        measurements.append({'region': name, 'include_image': has_image, 'evidence': evidence,
                             'measurement': value, 'resources_sent': decoder['resources_sent'],
                             'normalizations': work['geometry_normalization_calls'],
                             'shared_normalization': shared,
                             'individual_preparations': expected_prepare, 'raster_actual': expected_raster,
                             'stage_ns': {k: interval(v) for k,v in full['stages'].items() if 'elapsed_ns' in v},
                             'prepare_parts_ns': {k: interval(v) for k,v in (details or {}).items()}})
    require(all(state == captures[0] for state in captures)
            and images[0] == images[1] and len({row['host_request_id'] for row in hosts}) == 4,
            'independent_observations_or_exact_heat_reuse_not_same_generation')
    values = [row['measurement'] for row in measurements]
    require(values[0] == values[2] == values[3]
            and values[0]['camera_identity'] != values[1]['camera_identity']
            and values[0]['region_ref']['region_id'] != values[1]['region_ref']['region_id'],
            'same_region_identity_drift_or_distinct_regions_shared_camera')
    return {'passed': True, 'arm': arm, 'slot_result': result_pin, 'state': captures[0],
            'source': source, 'worker_meter': pin(meter_file), 'window_ns': window['wall_ns'],
            'engine_sha256': config_source(slot), 'measurements': measurements, 'image': images[0]}


def verify_pair(a, b):
    require((a['arm'], b['arm']) == ('A', 'B') and a['passed'] and b['passed']
            and all(a['source'][k] == b['source'][k] for k in ('Blender_sha256', 'asset_sha256'))
            and all(a['source'][k] != b['source'][k] for k in ('asset_copy', 'Blender_pid', 'MCP_pid'))
            and a['state']['instance_id'] != b['state']['instance_id']
            and a['engine_sha256'] != b['engine_sha256'],
            'paired_slots_not_separate_fixed_installation_and_same_asset')
    common = ('distance_m', 'point_pair', 'nearest_witness_source', 'source_triangles', 'source_vertices')
    for x, y in zip(a['measurements'], b['measurements'], strict=True):
        require(all(x['measurement'][key] == y['measurement'][key] for key in common)
                and x['measurement']['binding']['ordered_geometry_sha256']
                == y['measurement']['binding']['ordered_geometry_sha256'],
                'live_candidate_measurement_or_geometry_changed')
    prev, cand = a['image'], b['image']
    require(all(prev[key]['sha256'] == cand[key]['sha256'] for key in ('PNG', 'NPZ'))
            and all(prev[key] == cand[key] for key in ('view', 'pixel_bounds', 'source_pixel_counts')),
            'live_candidate_png_npz_or_source_pixel_mapping_changed')
    first, second = ([row['stage_ns']['service_total'] for row in x['measurements'][:2]] for x in (a,b))
    return {'passed': True, 'normalizations': [sum(row['normalizations'] for row in x['measurements'])
                                                for x in (a,b)],
            'first_service_ns': [first[0], second[0]], 'second_service_ns': [first[1], second[1]],
            'two_services_ns': [sum(first),sum(second)], 'window_ns': [a['window_ns'], b['window_ns']],
            'two_service_reduction': 1-sum(second)/sum(first),
            'full_window_reduction': 1-b['window_ns']/a['window_ns'],
            'same_asset_distance_witness_and_originals': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    scored = {}
    try:
        for label in ('A', 'B'):
            scored[label] = verify_slot(options.runtime / 'slots' / label, label)
        verdict = {**verify_pair(scored['A'], scored['B']), 'arms': scored}
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        verdict = {'passed': False, 'error': str(exc), 'error_type': type(exc).__name__, 'arms': scored}
    write(options.output, verdict)
    print(json.dumps({key: value for key, value in verdict.items() if key != 'arms'}))
    raise SystemExit(0 if verdict['passed'] else 1)
