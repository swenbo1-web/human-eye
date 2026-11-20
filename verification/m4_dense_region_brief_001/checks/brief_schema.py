"""Decode a compact region-task packet independently for the two acceptance checkers."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[3]
V = ROOT / 'verification'
TYPED_PATH = V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py'
POLICY_PATH = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
V1 = 'active-observation-region-task-brief-v1'
V2 = 'active-observation-region-task-brief-v2'
OBJECTS = ('object_index', 'host_id', 'instance_id', 'object_name')
SCOPES = ('scope_id', 'camera_identity', 'binding_sha256', 'constructed_frame_count',
          'locally_covered_region_count')
WORLD = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
REGIONS = ('object_index', 'roi_id', *WORLD, 'source_triangle_index_ranges',
           'ordered_geometry_sha256', 'status', 'reason', 'view_reasons')
FRAMES = ('scope_index', 'view_name', 'frame_identity', 'image_ref', 'image_sha256',
          'native_content_block_index')
PIXELS = ('visible_surface_pixels', 'contrasting_boundary_pixels')
LOCATIONS = ('visible_pixel_bounds', 'visible_pixel_anchor')
WITNESSES = ('region_index', 'frame_index', 'pixel_row_index', *PIXELS, *LOCATIONS)
SHORTFALLS = ('region_index', 'frame_index', *PIXELS)
REQ = dict(minimum_surface_pixels=16, minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24)
IMAGES_V1 = ('scope_id', 'camera_identity', 'view_name', 'frame_identity', 'image_ref',
             'image_sha256', 'native_content_block_index')
WITNESSES_V1 = ('scope_id', 'frame_identity', 'roi_id', *PIXELS, *LOCATIONS)


def require(condition, label):
    if not condition:
        raise ValueError(label)


def records(table, columns):
    all_names = tuple(table.get('columns', ()))
    rows = table.get('rows')
    require(all_names == columns and type(rows) is list, 'v2_table_columns/' + columns[0])
    require(all(type(row) is list and len(row) == len(columns) for row in rows),
            'v2_table_row_shape/' + columns[0])
    return [dict(zip(columns, row, strict=True)) for row in rows]


def table(columns, rows):
    return {'columns': list(columns), 'rows': [[row[column] for column in columns] for row in rows]}


def by_index(rows, index, label):
    require(type(index) is int and 0 <= index < len(rows), 'v2_bad_index/' + label)
    return rows[index]


def hex_digest(value):
    return type(value) is str and len(value) == 64 and all(x in '0123456789abcdef' for x in value)


def triangle_indices(ranges, count):
    """Expand canonical zero-based inclusive runs within the source triangle bound."""
    require(type(ranges) is list and ranges and type(count) is int and count > 0,
            'v2_bad_source_triangle_domain')
    result, previous = [], -2
    for pair in ranges:
        require(type(pair) is list and len(pair) == 2 and all(type(x) is int for x in pair),
                'v2_bad_source_triangle_interval')
        low, high = pair
        require(previous + 1 < low <= high < count, 'v2_noncanonical_or_out_of_range_source_triangles')
        result.extend(range(low, high + 1))
        previous = high
    return result


def nonnegative(value):
    return type(value) is int and value >= 0


def decode_body(body, content_count):
    """Restore legacy-shaped facts without reading installer code or producer arrays."""
    require(body['schema'] == V2 and body['index_base'] == 0 and type(body['index_base']) is int and
            body['result_kind'] == 'active_observation' and body['pixel_requirements'] == REQ,
            'v2_result_schema_or_pixel_threshold')
    require(body['source_triangle_index_ranges_semantics'] ==
            'Zero-based inclusive ranges in current object-local triangle order.' and
            body['frame_index_semantics'] ==
            'Zero-based indices in the frame table. A null MCP content index means no image was delivered.',
            'v2_index_semantics_missing_or_wrong')
    binding = body['binding']
    objects = records(body['objects'], OBJECTS)
    scopes = records(body['scopes'], SCOPES)
    require(all(type(obj['object_index']) is int and obj['object_index'] == i
                for i, obj in enumerate(objects)), 'v2_object_row_order')
    require(len({scope['scope_id'] for scope in scopes}) == len(scopes) and
            any(scope['scope_id'] == 'global' for scope in scopes), 'v2_scope_uniqueness')
    for scope in scopes:
        if scope['scope_id'] == 'global':
            require(all(scope[key] == binding[key] for key in ('camera_identity', 'binding_sha256')),
                    'v2_global_scope_binding')
    frames = records(body['frames'], FRAMES)
    selected, used_views = {}, set()
    for frame in frames:
        scope = by_index(scopes, frame['scope_index'], 'scope')
        view_key = scope['scope_id'], frame['view_name']
        require(view_key not in used_views and hex_digest(frame['frame_identity']) and
                hex_digest(frame['image_sha256']), 'v2_frame_scope_view_identity')
        used_views.add(view_key)
        frame.update(scope_id=scope['scope_id'], camera_identity=scope['camera_identity'])
        index = frame['native_content_block_index']
        if index is not None:
            require(type(index) is int and 1 <= index < content_count and index not in selected,
                    'v2_native_block_index')
            selected[index] = frame
    counts = Counter(frame['scope_id'] for frame in frames)
    require(all(counts[row['scope_id']] == row['constructed_frame_count'] for row in scopes) and
            len({row['frame_identity'] for row in frames}) == len({row['image_ref'] for row in frames}) == len(frames) and
            set(selected) == set(range(1, content_count)), 'v2_frame_scope_count_or_selected_coverage')
    image_delivery = body['image_delivery']
    require(image_delivery['local_verified_image_count'] == len(frames) and
            image_delivery['selected_image_count'] == image_delivery['mcp_content_constructed_image_count'] ==
            len(selected), 'v2_delivery_count_mismatch')
    task = body['region_task']
    regions = records(task, REGIONS)
    require(len({region['roi_id'] for region in regions}) == len(regions) ==
            task['summary']['eligible_region_count'], 'v2_region_identity_or_count')
    for row in regions:
        obj = by_index(objects, row['object_index'], 'object')
        indices = triangle_indices(row.pop('source_triangle_index_ranges'), task['summary']['source_triangle_count'])
        geometry_digest = row.pop('ordered_geometry_sha256')
        require(hex_digest(geometry_digest), 'v2_ordered_geometry_digest')
        row.update({key: obj[key] for key in OBJECTS[1:]})
        row['source_triangle_indices'] = indices
        row['complete_witness'] = None
        row['source'] = {**{key: binding[key] for key in ('document_epoch', 'scene_revision', 'capture_state')},
                         **{key: row[key] for key in ('object_index', 'host_id', 'instance_id',
                                                      'source_triangle_indices')},
                         'ordered_geometry_sha256': geometry_digest,
                         'parent_binding_sha256': binding['binding_sha256'],
                         'parent_source_binding_sha256': binding['source_binding_sha256']}

    witnesses = records(body['witnesses'], WITNESSES)
    pixels, used_source_pixels = [], set()
    for evidence in witnesses:
        row = by_index(regions, evidence['region_index'], 'witness_region')
        frame = by_index(frames, evidence['frame_index'], 'witness_frame')
        pixel_index = evidence['pixel_row_index']
        frame_pixel = evidence['frame_index'], pixel_index
        require(row['complete_witness'] is None and row['status'] == 'covered' and
                nonnegative(pixel_index) and frame_pixel not in used_source_pixels and
                all(nonnegative(evidence[key]) for key in PIXELS) and
                evidence[PIXELS[0]] >= REQ['minimum_surface_pixels'] and
                evidence[PIXELS[1]] >= REQ['minimum_boundary_pixels'],
                'v2_witness_state_or_pixel_row')
        used_source_pixels.add(frame_pixel)
        row['complete_witness'] = {key: frame[key] for key in ('scope_id', 'frame_identity', 'image_ref', 'view_name',
                                                               'native_content_block_index')}
        row['complete_witness'].update(pixel_row_index=pixel_index,
                                       selected_for_delivery=frame['native_content_block_index'] is not None)
        pixels.append({'scope_id': frame['scope_id'], 'frame_identity': frame['frame_identity'],
                       'roi_id': row['roi_id'], **{key: evidence[key] for key in (*PIXELS, *LOCATIONS)}})
    require(all((row['status'] == 'covered') is (row['complete_witness'] is not None) for row in regions) and
            task['summary']['observed_region_count'] == len(witnesses), 'v2_covered_row_must_have_witness')

    for evidence in records(body['pixel_shortfalls'], SHORTFALLS):
        row = by_index(regions, evidence['region_index'], 'shortfall_region')
        frame = by_index(frames, evidence['frame_index'], 'shortfall_frame')
        require('pixel_shortfall' not in row and row['status'] == 'unknown' and
                row['reason'] == 'pixel_evidence_insufficient' and
                frame['view_name'] in row['view_reasons']['pixel_evidence_insufficient'] and
                all(nonnegative(evidence[key]) for key in PIXELS) and
                (evidence[PIXELS[0]] < REQ['minimum_surface_pixels'] or
                 evidence[PIXELS[1]] < REQ['minimum_boundary_pixels']), 'v2_shortfall_state_or_pixels')
        index = frame['native_content_block_index']
        row['pixel_shortfall'] = {**{key: evidence[key] for key in PIXELS}, **REQ,
                                  'scope_id': frame['scope_id'], 'view_name': frame['view_name'],
                                  'image_delivered': index is not None, 'native_content_block_index': index}

    region_task = {key: task[key] for key in ('schema', 'conditions', 'summary')}
    region_task['rows'] = regions
    legacy = {key: body[key] for key in ('status', 'result_kind', 'observation_status', 'session_id', 'read_only',
                                       'execution_authority', 'index_base', 'binding', 'objects', 'scopes',
                                       'image_delivery')}
    legacy.update(schema=V1, region_task=region_task,
                  images=table(IMAGES_V1, [selected[i] for i in sorted(selected)]),
                  witness_pixels=table(WITNESSES_V1, pixels),
                  source_triangle_index_semantics='zero_based_object_local; current_capture_order; source_binding_per_scope')
    if 'task_result' in body:
        legacy['task_result'] = body['task_result']
    return legacy


def verify_brief(result, baseline_v1=None):
    """Decode proof-linked values, then bind each selected row to its original wire PNG."""
    require(result['isError'] is False and result['content'][0]['type'] == 'text',
            'v2_successful_typed_body_required')
    raw_body = json.loads(result['content'][0]['text'])
    legacy = decode_body(raw_body, len(result['content']))
    if baseline_v1 is not None:
        require(legacy == baseline_v1, 'v2_decoded_facts_differ_from_v1_baseline')
    typed = runpy.run_path(str(TYPED_PATH))
    unpacked = {**result, 'content': [{'type': 'text', 'text': json.dumps(legacy)}, *result['content'][1:]]}
    _, _, images = typed['verify_content']({'result': unpacked}, contract='active_region_task')
    return legacy, images


def cli_stages(result):
    """Require both fixed CLI budget stages to preserve exact text and PNG order."""
    helpers, limits = runpy.run_path(str(POLICY_PATH))['budget_helpers']()
    stages = []
    for wall in ('0.0000', '10.0000', '100.0000'):
        raw = helpers['model_items'](result, wall)
        first = helpers['truncate_items'](raw, limits['MCP_bytes'])
        second = helpers['truncate_items'](first, limits['history_approximate_tokens'], token_mode=True)
        require(raw == first == second, 'v2_fixed_CLI_budget_changed_original_content/' + wall)
        stages.append({'sample_wall_seconds': wall, 'header_UTF8_bytes': len(raw[0]['text'].encode()),
                       'body_UTF8_bytes': len(result['content'][0]['text'].encode()),
                       'MCP_exact': True, 'history_exact': True,
                       'raw_body_sha256': sha256(result['content'][0]['text'].encode()).hexdigest()})
    return {'limits': limits, 'stages': stages, 'passed': True}
