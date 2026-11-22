"""Qualify the real installed discovery and selected measurement across the public bridge."""

import base64
from fractions import Fraction
from hashlib import sha256
import json
from os.path import commonprefix
from pathlib import Path
from runpy import run_path


V = Path(__file__).resolve().parents[2]
TOOL = 'human_eye_scene_observe'
VIEWS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
         'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
CENTERS = {'S021': [4.5, 0.5, 1.875], 'S034': [1.5, 0.5, 1.875], 'S055': [7.5, 0.5, 1.875]}
TARGET, REFERENCE = 'S034', 'M4_Far_00'
CONDITIONS = {'area_min_m2': 7/2048, 'area_max_m2': 9/2048, 'normal_z_min': 1}
DISCOVER = {'query': {'mode': 'active_observation', 'region_task': CONDITIONS}, 'include_image': True,
            'response_detail': 'brief'}
MEASURE = {'query': {'mode': 'source_region', 'region': {'object': {'name': TARGET}, 'source_triangle_indices': [0, 1]},
                     'reference': {'name': REFERENCE}, 'requested_facts': ['surface_proximity']}, 'include_image': False}
REQUIRED_CLI_KEYS = {
    'discovery': ('schema', 'status', 'binding', 'objects', 'region_task', 'scopes', 'frames', 'witnesses',
                  'pixel_requirements', 'blocker_evidence'),
    'measurement': ('schema', 'status', 'task_result', 'binding', 'region', 'region_ref'),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())


def body(result):
    content = result.get('content', [])
    require(result.get('isError') is False and content and content[0]['type'] == 'text',
            'qualification_product_error/' + str(result)[:800])
    return json.loads(content[0]['text'])


def check_cli(result, folder, label):
    helpers, limits = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    require((limits['MCP_bytes'], limits['history_approximate_tokens']) == (12000, 3000), 'fixed_cli_budget_changed')
    stages = []
    for clock, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        original = helpers['model_items'](result, clock)
        require(len(original[0]['text'].encode()) == header, 'fixed_cli_header_changed')
        text = [item['text'] for item in original if item['type'] == 'input_text']
        images = [item for item in original if item['type'] == 'input_image']
        mcp = helpers['truncate_items'](original, limits['MCP_bytes'])
        history = helpers['truncate_items'](mcp, limits['history_approximate_tokens'], token_mode=True)
        row = {'clock': clock, 'header_bytes': header}
        for stage, actual in (('mcp', mcp), ('history', history)):
            path = folder/f'{label}_{header}_{stage}.json'
            save(path, actual)
            texts = [item['text'] for item in actual if item['type'] == 'input_text']
            retained_images = [item for item in actual if item['type'] == 'input_image']
            missing = []
            if texts != text:
                if (label in REQUIRED_CLI_KEYS and len(texts) == len(text) == 2 and texts[0] == text[0]
                        and 'truncated…' in texts[1]):
                    wanted, retained = text[1].encode(), texts[1].encode()
                    head = len(commonprefix((wanted, retained)))
                    tail = len(wanted) - len(commonprefix((wanted[::-1], retained[::-1])))
                    require(head < tail, 'fixed_cli_middle_truncation_needed')
                    for key in REQUIRED_CLI_KEYS[label]:
                        span = helpers['path_byte_span'](text[1], [key])
                        if not (span['end'] <= head or span['start'] >= tail):
                            missing.append(key)
                else:
                    missing.append('body_or_image_caption')
            row[stage] = {'exact': actual == original, 'body_bytes': sum(len(item.encode()) for item in texts[1:]),
                          'PNG_exact': images == retained_images, 'required_text_missing': missing,
                          'representation_sha256': digest(path.read_bytes())}
        stages.append(row)
    outcome = {'original_text_bytes': sum(len(item['text'].encode()) for item in result['content']
                                         if item['type'] == 'text'), 'stages': stages,
               'passed': all(row[stage]['PNG_exact'] and not row[stage]['required_text_missing']
                             for row in stages for stage in ('mcp', 'history'))}
    save(folder/f'{label}_CLI.json', outcome)
    return outcome


def tables(table, columns):
    require(table['columns'] == columns, 'product_unexpected_table_columns/' + columns[0])
    return [dict(zip(columns, row, strict=True)) for row in table['rows']]


def host_source(folder, binding, native, *, require_full):
    retained = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    installed = read(V/'m4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json')
    audit = retained['Audit']()
    captures, _ = retained['decode_captures'](folder, installed, audit)
    capture = retained['current_capture'](captures, binding, audit)
    if require_full:
        retained['source_binding_checks'](capture, binding, installed, audit)
    require(capture['host_identity']['document_epoch'] == binding['document_epoch'], 'raw_capture_document_epoch_mismatch')
    by_name = {row['name']: row for row in native['objects']}
    require(len(capture['meshes']) == len(by_name) == 21, 'whole_product_actual_geometry_missing')
    for mesh in capture['meshes']:
        row = by_name[mesh['name']]
        require((mesh['object_id'], mesh['vertices'], mesh['faces']) == (
                row['object_id'], row['evaluated']['vertices_world_m'], row['evaluated']['triangles'])
                and capture['host_identity']['object_instances'][row['object_id']] == row['instance_id'],
                'product_source_not_same_owned_evaluated_scene/' + mesh['name'])
    return capture


def verify_blockers(packet, rows, objects, capture):
    block = packet['blocker_evidence']
    blockers = tables(block, ['region_index', 'view_name', 'blocker_object_index', 'source_triangle_index'])
    idx = next(i for i, row in enumerate(rows) if row['object_name'] == TARGET)
    require(len(blockers) == len(VIEWS) and {r['view_name'] for r in blockers} == VIEWS.keys()
            and all(row['region_index'] == idx for row in blockers), 'qualified_product_six_forward_sources_missing')
    checker = run_path(str(V/'m4_cross_scale_discovery_001/oracle/geometry_witness.py'))['prove']
    meshes = {mesh['name']: {'name': mesh['name'],
               'vertices': [tuple(map(Fraction, point)) for point in mesh['vertices']], 'triangles': mesh['faces']}
              for mesh in capture['meshes']}
    region = {'object_name': TARGET, 'boundary_loops': [[0,1,2,3]], 'plane_normal_integer': (0,0,1),
              'source_triangle_indices': [0,1]}
    proof = {}
    for row in blockers:
        name = objects[row['blocker_object_index']]['object_name']
        index = row['source_triangle_index']
        require(name == REFERENCE and 0 <= index < len(meshes[name]['triangles']), 'unexpected_old_cover_source')
        mesh = {**meshes[name], 'triangles': [meshes[name]['triangles'][index]]}
        direction = row['view_name']
        try:
            checker([meshes[TARGET], mesh], region, VIEWS[direction])
        except ValueError as error:
            require(str(error) == 'positive_area_front_occluder/' + name + '/0', 'wrong_panel_shadow/' + str(error))
        else:
            raise ValueError('published_named_source_has_no_positive_area/' + direction)
        proof[direction] = {'object': name, 'triangle': index, 'positive_projected_area': True}
    return proof


def verify_measurement(result, producer, previous):
    packet = body(result)
    task, ref = packet['task_result'], packet['region_ref']
    by_name = {row['object_name']: row for row in previous['objects']}
    require(packet['schema'] == 'source-region-brief-v2' and packet['read_only'] is True
            and packet['execution_authority'] is False and packet['images'] == []
            and len(result['content']) == 1 and task['reference']['name'] == REFERENCE
            and packet['region']['object_name'] == TARGET and ref['source_triangle_indices'] == [0,1]
            and all(ref[key] == by_name[TARGET][key] for key in ('host_id', 'instance_id'))
            and ref['document_epoch'] == previous['document_epoch']
            and all(ref['capture_generation'][key] == previous['capture_state'][key]
                    for key in ('instance_id', 'epoch', 'revision'))
            and ref == producer['region_ref']
            and task['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface',
            'product_selected_distance_scope_or_source_changed')
    fact = task['facts']['surface_proximity']
    nearest = fact['value']['nearest_witness']
    a, b = nearest['a'], nearest['b']
    require(fact['status'] == 'measured' and fact['value']['distance_m'] == 1/8
            and nearest['direction_a_to_b'] == [0,0,1] and a[:2] == b[:2]
            and (a[2], b[2]) == (15/8, 2)
            and 47/32 <= a[0] <= 49/32 and 15/32 <= a[1] <= 17/32
            and all(task['source_mapping']['nearest_witness'][key]['exact_membership'] is True for key in ('a','b')),
            'product_selected_distance_point_pair_or_membership_changed')
    return {'distance_m': 1/8, 'point_pair': [a,b], 'direction_world': [0,0,1],
            'scope': task['measurement_scope'], 'source_mapping': task['source_mapping']}


def solve_product(call, owner, source, folder):
    native = run_path(str(Path(__file__).with_name('native.py')))
    certify_geometry, prove_image = native['certify_geometry'], native['prove_image']

    out = folder/'product_qualification'
    out.mkdir()
    discovery = call(TOOL, DISCOVER)
    packet = body(discovery)
    cli = {'discovery': check_cli(discovery, out, 'discovery')}
    decode = run_path(str(V/'m4_dense_region_brief_001/checks/brief_schema.py'))['decode_body']
    decoded = decode(packet, len(discovery['content']))
    event = owner.runtime.public_requests[-1]
    producer = read(event['producer_archive']['path'])
    binding = producer['binding']
    capture = host_source(folder, binding, source, require_full=True)
    task = decoded['region_task']
    rows = task['rows']
    by_name = {r['object_name']: r for r in rows}
    require(task['conditions'] == CONDITIONS and task['summary']['source_triangle_count'] == 6162
            and len(rows) == len(by_name) == 3 and set(by_name) == set(CENTERS)
            and task['summary']['observed_region_count'] == 2 and task['summary']['unknown_region_count'] == 1
            and all(r['center_world_m'] == CENTERS[r['object_name']] and r['front_direction_world'] == [0,0,1]
                    and r['source_triangle_indices'] == [0,1] for r in rows)
            and by_name[TARGET]['reason'] == 'positive_area_occlusion_all_front_views'
            and set(by_name[TARGET]['view_reasons']['positive_area_occlusion']) == VIEWS.keys(),
            'actual_product_candidate_set_geometry_or_unknown_changed')
    meshes = {mesh['name']: mesh for mesh in capture['meshes']}
    for row in rows:
        mesh = meshes[row['object_name']]
        original = {'vertices': mesh['vertices'], 'faces': mesh['faces']}
        ordered = digest(json.dumps(original, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode())
        require(row['source']['ordered_geometry_sha256'] == ordered, 'public_region_did_not_bind_ordered_mesh_source')
    scopes = tables(packet['scopes'], ['scope_id', 'camera_identity', 'binding_sha256', 'constructed_frame_count',
                                     'locally_covered_region_count'])
    frames = tables(packet['frames'], ['scope_index','view_name','frame_identity','image_ref','image_sha256',
                                      'native_content_block_index'])
    objects = tables(packet['objects'], ['object_index','host_id','instance_id','object_name'])
    require(objects == binding['objects'] and packet['binding']['capture_state'] == binding['capture_state']
            and packet['binding']['document_epoch'] == binding['document_epoch']
            and scopes[packet['blocker_evidence']['scope_index']]['scope_id'] == 'global', 'public_capture_binding_changed')
    blockers = verify_blockers(packet, rows, objects, capture)
    require(3 <= len(frames) <= 6 and producer['work']['raster_attempts'] == len(frames), 'product_qualification_raster_contract')
    global_frame, = [frame for frame in frames if scopes[frame['scope_index']]['scope_id'] == 'global'
                     and frame['view_name'] == 'SCENE']
    geometry = certify_geometry(source)
    global_proof = prove_image(folder, owner, global_frame['image_ref'], 'S021', source=source, geometry=geometry)
    require(global_proof['geometrically_unoccluded'] and global_proof['all_corners_in_frame'] and not global_proof['complete']
            and (global_proof['selected_surface_pixels'] < 16 or global_proof['contrasting_boundary_pixels'] < 4),
            'actual_global_open_small_panel_must_fail_pixel_gate')
    images = {}
    for name in ('S021', 'S055'):
        witness = by_name[name]['complete_witness']
        require(witness is not None and (name != 'S021' or witness['scope_id'] != 'global')
                and (name != 'S055' or witness['view_name'] not in ('SCENE', 'TOP')),
                'actual_scope_switch_witness_missing/' + name)
        frame, = [row for row in frames if row['frame_identity'] == witness['frame_identity']]
        ref = frame['image_ref']
        require(ref == witness['image_ref'] and frame['native_content_block_index'] is not None,
                'witness_original_PNG_not_delivered/' + name)
        image = discovery['content'][frame['native_content_block_index']]
        downloaded = call('read_images', {'refs': [ref]})
        cli['read_'+name] = check_cli(downloaded, out, 'read_'+name)
        selected = prove_image(folder, owner, ref, name, downloaded['content'], source=source, geometry=geometry)
        require(selected['complete'] and image['type'] == 'image' and image['mimeType'] == 'image/png'
                and digest(base64.b64decode(image['data'], validate=True)) == frame['image_sha256'] == selected['sha256'],
                'product_qualification_original_local_PNG_or_visibility_changed/' + name)
        images[name] = selected
    measurement = call(TOOL, MEASURE)
    cli['measurement'] = check_cli(measurement, out, 'measurement')
    event = owner.runtime.public_requests[-1]
    measurement_producer = read(event['producer_archive']['path'])
    host_source(folder, measurement_producer['binding'], source, require_full=False)
    measured = verify_measurement(measurement, measurement_producer, binding)
    proof = {'passed': all(row['passed'] for row in cli.values()), 'images': images, 'global_S021': global_proof,
             'candidate_centers': CENTERS, 'blockers': blockers, 'measurement': measured, 'CLI': cli,
             'product_rasters': len(frames), 'source_capture_state': binding['capture_state']}
    save(out/'PRODUCT_QUALIFICATION.json', proof)
    require(proof['passed'], 'actual_product_required_CLI_text_or_PNG_clipped')
    return proof
