"""Independent decoding of patch brief delivery and stored native PNG blocks.

This harness imports no product module. Expected semantics come from the full
actual service result saved before MCP projection.
"""

import base64
import copy
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image


OBJECT_COLUMNS = ['object_index', 'host_id', 'instance_id', 'object_name']
REGION_COLUMNS = ['roi_id', 'object_index', 'status', 'reason', 'triangle_count']
WORLD_FIELDS = ['center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world']
LOCATION_FIELDS = ['visible_pixel_bounds', 'visible_pixel_anchor']
PIXEL_COLUMNS = ['image_index', 'region_index', 'front_facing', 'visible_surface_pixels',
                 'contrasting_boundary_pixels', 'readable']
RULES = ['minimum_surface_pixels', 'minimum_boundary_pixels', 'minimum_rgb_boundary_contrast']
ENVELOPE = ['status', 'result_kind', 'observation_status', 'session_id', 'read_only', 'execution_authority']
FRAME_FIELDS = ['scene_identity', 'candidate_identity', 'view_name', 'image_ref', 'image_path',
                'image_sha256', 'PNG_bytes', 'arrays_path', 'arrays_sha256',
                'compressed_array_file_bytes', 'array_payload_bytes', 'host_binding_sha256',
                'source_revision', 'stages', 'feedback_stages', 'patch_mapping_version',
                'patch_roi_ids', 'patch_mapping_identity', 'patch_owner_array_bytes',
                'patch_mapping_array_bytes']


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('ascii')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def table(value, columns):
    require(type(value) is dict and set(value) == {'columns', 'rows'} and value['columns'] == columns,
            'table_columns_or_fields_changed')
    require(type(value['rows']) is list and all(type(row) is list and len(row) == len(columns) for row in value['rows']),
            'table_row_width_changed')
    return [dict(zip(columns, row)) for row in value['rows']]


def reference(value, count):
    require(type(value) is int and 0 <= value < count, 'invalid_table_reference')
    return value


def delivery(raw):
    return {'local_verified_image_count': len(raw['frames']),
            'mcp_content_constructed_image_count': len(raw['frames']),
            'consumer_read_status': 'unconfirmed',
            'frame_reuses': raw['work'].get('frame_reuses', 0),
            'new_raster_attempts': raw['work'].get('raster_attempts', 0)}


def binding_semantics(binding):
    result = {key: copy.deepcopy(value) for key, value in binding.items()
              if key not in {'schema', 'objects', 'camera_policy', 'camera_specification'}}
    if isinstance(result.get('capture_state'), dict):
        result['capture_state'].pop('selection_key', None)
    return result


def full_public(raw):
    result = {key: copy.deepcopy(raw[key]) for key in ENVELOPE + ['facts', 'work', 'generation_work',
              'stages', 'generation_stages'] if key in raw}
    result['binding'] = {key: copy.deepcopy(value) for key, value in raw['binding'].items()
                         if key != 'camera_specification'}
    result['frames'] = [{key: copy.deepcopy(frame[key]) for key in FRAME_FIELDS if key in frame}
                        for frame in raw['frames']]
    result['image_delivery'] = delivery(raw)
    return result


def raw_semantics(raw):
    facts = raw['facts']
    regions = facts['regions']
    region_index = {row['roi_id']: index for index, row in enumerate(regions)}
    require(len(region_index) == len(regions), 'duplicate_raw_region')
    support = facts['scope']['patch_support']
    require([row['roi_id'] for row in support['regions']] == list(region_index), 'raw_patch_mapping_order_changed')
    image_index = {frame['image_ref']: index for index, frame in enumerate(raw['frames'])}
    result = {key: copy.deepcopy(raw[key]) for key in ENVELOPE}
    result.update(binding=binding_semantics(raw['binding']), objects=copy.deepcopy(raw['binding']['objects']),
                  regions=[{**{key: row[key] for key in REGION_COLUMNS[:-1]},
                            'triangle_count': len(mapping['triangle_indices'])}
                           for row, mapping in zip(regions, support['regions'])],
                  coverage=copy.deepcopy(facts['coverage']),
                  scope={key: copy.deepcopy(value) for key, value in facts['scope'].items()
                         if key != 'patch_support'},
                  images=[], observations=[], pixels=[], pixel_rules=None,
                  image_delivery_scope=facts['image_delivery_scope'], image_delivery=delivery(raw))
    located = 'location_conventions' in facts
    if located:
        result['location_conventions'] = copy.deepcopy(facts['location_conventions'])
        for target, source in zip(result['regions'], regions):
            target.update({key: copy.deepcopy(source[key]) for key in WORLD_FIELDS})
    summaries, components = [], []
    for source in support['objects']:
        summaries.append({key: source[key] for key in ['object_index', 'source_triangle_count',
                          'supported_triangle_count', 'unsupported_triangle_count', 'support_status']})
        for index, component in enumerate(source['unsupported_components']):
            components.append({'object_index': source['object_index'], 'component_index': index,
                               'triangle_count': len(component['triangle_indices']),
                               'reason': component['reason'], 'status': component['status'],
                               'triangle_indices': sorted(component['triangle_indices'])})
    result['scope']['patch_support'] = {key: support[key] for key in
        ['schema', 'triangle_index_scope', 'all_triangles_participate_in_occlusion']}
    result['scope']['patch_support'].update(objects=summaries, unsupported_components=components)
    for index, frame in enumerate(raw['frames']):
        require(frame['patch_roi_ids'] == list(region_index), 'raw_frame_patch_order_changed')
        result['images'].append({key: frame[key] for key in ['view_name', 'image_ref', 'image_sha256', 'patch_mapping_identity']})
        result['images'][-1]['native_content_block_index'] = index + 1
    result['patch_mapping_version'] = raw['frames'][0]['patch_mapping_version'] if raw['frames'] else None
    for observation in facts['observations']:
        index = image_index[observation['image_ref']]
        result['observations'].append({'image_index': index,
            'readable_region_indices': [region_index[identity] for identity in observation['readable_roi_ids']]})
        require(len(observation['pixel_rows']) == len(regions), 'raw_pixel_rows_missing')
        for pixel in observation['pixel_rows']:
            rules = {key: pixel[key] for key in RULES}
            if result['pixel_rules'] is None:
                result['pixel_rules'] = rules
            require(encoded(result['pixel_rules']) == encoded(rules), 'raw_pixel_rules_differ')
            result['pixels'].append({'image_index': index, 'region_index': region_index[pixel['roi_id']],
                                    **{key: copy.deepcopy(pixel[key]) for key in
                                       PIXEL_COLUMNS[2:] + (LOCATION_FIELDS if located else [])}})
    return result


def decode_brief(value):
    located = value.get('schema') == 'active-observation-brief-v3'
    require(value.get('schema') in {'active-observation-brief-v2', 'active-observation-brief-v3'}
            and type(value.get('index_base')) is int
            and value['index_base'] == 0,
            'region_brief_v2_or_v3_required_no_full_fallback')
    objects = table(value['objects'], OBJECT_COLUMNS)
    require([row['object_index'] for row in objects] == list(range(len(objects))), 'object_order_changed')
    regions = table(value['regions'], REGION_COLUMNS + (WORLD_FIELDS if located else [])) if 'regions' in value else []
    require(len({row['roi_id'] for row in regions}) == len(regions), 'duplicate_brief_region')
    for region in regions:
        reference(region['object_index'], len(objects))
        if located:
            for key in WORLD_FIELDS:
                require(type(region[key]) is list and len(region[key]) == 3
                        and all(type(v) in (int, float, str) for v in region[key]), 'lossless_world_vector_required')
                for scalar in region[key]:
                    Fraction(scalar)
    images = table(value['images'], ['view_name', 'image_ref', 'image_sha256', 'native_content_block_index',
                                    'patch_mapping_identity']) if 'images' in value else []
    require([row['native_content_block_index'] for row in images] == list(range(1, len(images) + 1)),
            'native_block_index_changed')
    coverage = copy.deepcopy(value['coverage'])
    for source, target in [('covered_region_indices', 'covered_roi_ids'),
                           ('unresolved_region_indices', 'unresolved_roi_ids'),
                           ('candidate_pool_uncovered_region_indices', 'candidate_pool_uncovered_roi_ids')]:
        coverage[target] = [regions[reference(index, len(regions))]['roi_id'] for index in coverage.pop(source, [])]
    coverage.setdefault('observed_views', [])
    scope = copy.deepcopy(value['scope'])
    unsupported = table(scope.pop('objects_without_supported_roi'), ['object_index', 'status']) if 'objects_without_supported_roi' in scope else []
    scope['objects_without_supported_roi'] = [dict(objects[reference(row['object_index'], len(objects))],
                                                  status=row['status']) for row in unsupported]
    support = scope['patch_support']
    support['objects'] = table(support.pop('object_support'), ['object_index', 'source_triangle_count',
        'supported_triangle_count', 'unsupported_triangle_count', 'support_status'])
    components = table(support.pop('unsupported_components'), ['object_index', 'component_index',
        'triangle_count', 'reason', 'status', 'triangle_index_ranges']) if 'unsupported_components' in support else []
    for component in components:
        reference(component['object_index'], len(objects))
        indices = []
        for bounds in component.pop('triangle_index_ranges'):
            require(type(bounds) is list and len(bounds) == 2 and all(type(x) is int for x in bounds)
                    and 0 <= bounds[0] <= bounds[1], 'bad_unknown_triangle_range')
            indices.extend(range(bounds[0], bounds[1] + 1))
        require(indices == sorted(set(indices)) and len(indices) == component['triangle_count'],
                'overlapping_or_missing_unknown_triangles')
        component['triangle_indices'] = indices
    support['unsupported_components'] = components
    observations = table(value['observations'], ['image_index', 'readable_region_indices']) if 'observations' in value else []
    for observation in observations:
        reference(observation['image_index'], len(images))
        for index in observation['readable_region_indices']:
            reference(index, len(regions))
    pixels = table(value['pixels'], PIXEL_COLUMNS + (LOCATION_FIELDS if located else [])) if 'pixels' in value else []
    for pixel in pixels:
        reference(pixel['image_index'], len(images))
        reference(pixel['region_index'], len(regions))
    require(len(pixels) == len(images) * len(regions), 'pixel_matrix_incomplete')
    require(len({(row['image_index'], row['region_index']) for row in pixels}) == len(pixels), 'duplicate_pixel_fact')
    result = {key: copy.deepcopy(value[key]) for key in ENVELOPE}
    result.update(binding=copy.deepcopy(value['binding']), objects=objects, regions=regions,
                  coverage=coverage, scope=scope, images=images, observations=observations, pixels=pixels,
                  pixel_rules=copy.deepcopy(value.get('pixel_rules')),
                  patch_mapping_version=value.get('patch_mapping_version'),
                  image_delivery_scope=value['image_delivery_scope'], image_delivery=copy.deepcopy(value['image_delivery']))
    if located:
        conventions = value['location_conventions']
        require(conventions == {
            'coordinate_frame': 'world', 'unit': 'm',
            'corner_order': ['center-u-v', 'center+u-v', 'center+u+v', 'center-u+v'],
            'front_direction_normalization': 'maximum absolute component is 1',
            'pixel_origin': 'top-left', 'pixel_index_base': 0, 'pixel_axis_order': ['x', 'y'],
            'image_size_px': [512, 512],
            'visible_pixel_bounds': 'inclusive bounds of actual ROI-owned pixels',
            'visible_pixel_anchor': 'ROI-owned pixel nearest bounds center; row-major ties'},
            'registered_location_conventions_changed')
        require(type(conventions['pixel_index_base']) is int, 'integer_pixel_index_base_required')
        result['location_conventions'] = copy.deepcopy(conventions)
        for pixel in pixels:
            bounds, anchor = (pixel[key] for key in LOCATION_FIELDS)
            if pixel['visible_surface_pixels'] == 0:
                require(bounds is None and anchor is None, 'zero_surface_locations_must_be_null')
            else:
                require(type(bounds) is list and len(bounds) == 4 and type(anchor) is list and len(anchor) == 2
                        and all(type(x) is int for x in bounds + anchor)
                        and 0 <= bounds[0] <= anchor[0] <= bounds[2] < 512
                        and 0 <= bounds[1] <= anchor[1] <= bounds[3] < 512, 'visible_owned_pixel_location_required')
    expected_keys = set(ENVELOPE) | {'schema', 'index_base', 'binding', 'objects', 'coverage', 'scope',
        'image_delivery_scope', 'image_delivery', 'regions', 'images', 'observations', 'pixels',
        'pixel_rules', 'patch_mapping_version'}
    if located:
        expected_keys.add('location_conventions')
    require(not set(value) - expected_keys, 'unexpected_brief_fields')
    return result


def verify_response(response, raw, detail='brief'):
    require(response.get('result', {}).get('isError') is False, 'tool_response_failed')
    content = response['result']['content']
    require(content and content[0]['type'] == 'text' and all(row['type'] == 'image' for row in content[1:]),
            'text_then_native_images_required')
    value = json.loads(content[0]['text'])
    expected = full_public(raw) if detail == 'full' else raw_semantics(raw)
    actual = value if detail == 'full' else decode_brief(value)
    require(encoded(expected) == encoded(actual), 'delivered_semantics_differ_from_actual_raw_result')
    require(len(content) - 1 == len(raw['frames']), 'native_image_count_changed')
    images = []
    for block, frame in zip(content[1:], raw['frames']):
        image_raw = base64.b64decode(block['data'], validate=True)
        require(block['mimeType'] == 'image/png' and image_raw == Path(frame['image_path']).read_bytes()
                and hashlib.sha256(image_raw).hexdigest() == frame['image_sha256'], 'native_PNG_bytes_changed')
        with Image.open(BytesIO(image_raw)) as picture:
            picture.load()
            require(picture.format == 'PNG' and picture.size == (512, 512), 'native_PNG_format_changed')
        images.append({'image_ref': frame['image_ref'], 'image_sha256': frame['image_sha256'],
                       'PNG_bytes': len(image_raw), 'native_content_block_index': len(images) + 1})
        require(block['data'] not in content[0]['text'], 'base64_repeated_in_text')
    return {'passed': True, 'detail': detail, 'schema': value.get('schema'),
            'text_UTF8_bytes': len(content[0]['text'].encode('utf8')), 'native_images': images,
            'object_count': len(raw['binding']['objects']), 'ROI_count': len(raw['facts']['regions']),
            'pixel_rows': sum(len(row['pixel_rows']) for row in raw['facts']['observations']),
            'semantics_sha256': hashlib.sha256(encoded(expected)).hexdigest(),
            'raw_source_binding_sha256': raw['binding']['binding_sha256']}


def verify_world_regions(raw, frozen_reference):
    """Compare exact vectors to independent source corners, once per result."""
    require(frozen_reference['schema'] == 'region-anchors-independent-reference-v1', 'world_reference_schema')
    expected = {row['roi_id']: row for row in frozen_reference['world_regions']}
    regions = raw['facts']['regions']
    require(len(regions) == len(expected) == 138 and {row['roi_id'] for row in regions} == set(expected),
            'world_reference_region_set')
    for region in regions:
        wanted = expected[region['roi_id']]
        values = {}
        for key in WORLD_FIELDS:
            values[key] = tuple(Fraction(value) for value in region[key])
            require(values[key] == tuple(Fraction(value) for value in wanted[key]), 'world_reference_' + key)
        center, u, v = (values[key] for key in WORLD_FIELDS[:3])
        corners = [tuple(c + first * a + second * b for c, a, b in zip(center, u, v))
                   for first, second in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        require(corners == [tuple(Fraction(value) for value in point) for point in wanted['source_quad']],
                'world_corner_reconstruction')
    return {'passed': True, 'regions_checked': len(regions), 'source_quad_reconstruction': True,
            'world_product_calls': 0, 'independent_reference_schema': frozen_reference['schema']}


def verify_capture(capture, fixture):
    require(capture['source'] == 'blender' and capture['unit'] == 'm'
            and capture['coordinate_frame'] == 'world', 'actual_world_metre_capture_required')
    require([mesh['name'] for mesh in capture['meshes']] == [obj['name'] for obj in fixture['objects']],
            'actual_host_object_order_differs_from_frozen_fixture')
    triangles = []
    for mesh, obj in zip(capture['meshes'], fixture['objects']):
        require(mesh['faces'] == obj['triangles'] and len(mesh['vertices']) == len(obj['vertices']),
                'actual_faces_or_vertices_changed')
        points = [tuple(Fraction(value) for value in point) for point in mesh['vertices']]
        expected = [tuple(Fraction(value) for value in point) for point in obj['vertices']]
        require(points == expected, 'actual_capture_coordinates_not_exact_fixture')
        triangles.extend([[[str(value) for value in points[index]] for index in face] for face in mesh['faces']])
    draw_bytes = json.dumps(triangles, default=str, sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(draw_bytes).hexdigest()
    return {'passed': True, 'objects': len(capture['meshes']),
            'vertices': sum(len(mesh['vertices']) for mesh in capture['meshes']),
            'triangles': len(triangles), 'world_triangle_sequence_sha256': digest,
            'extra_host_capture_calls': 0, 'product_geometry_calls': 0}


def normalize_index(capture, index, expected, representation):
    wanted = {row['roi_id']: row for row in expected['regions']}
    require(len(index['regions']) == len(wanted) == 138
            and [row['roi_id'] for row in index['regions']] == sorted(wanted), 'expected_patch_count_or_order_changed')
    order = ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK']
    require(index['view_order'] == order and [row['name'] for row in index['cameras']['views']] == order
            and set(index['classifications']) == set(order) == set(index['view_masks']), 'complete_camera_matrix_required')
    blocker_geometry_ids = set()
    for mesh in capture['meshes']:
        vertices = [tuple(Fraction(value) for value in point) for point in mesh['vertices']]
        for face in mesh['faces']:
            triangle = tuple(vertices[index] for index in face)
            canonical = min(triangle[shift:] + triangle[:shift] for shift in range(3))
            raw = json.dumps(canonical, default=str, sort_keys=True, separators=(',', ':')).encode()
            blocker_geometry_ids.add(hashlib.sha256(raw).hexdigest())
    result = {}
    for region in index['regions']:
        original = wanted[region['roi_id']]
        require(region['vertices'] == original['quad'] and region['normal'] == original['normal'],
                'canonical_patch_quad_or_front_changed')
        mesh = capture['meshes'][region['object_index']]
        source_faces = [mesh['faces'][face] for face in region['triangle_indices']]
        points = [tuple(Fraction(value) for value in point) for point in mesh['vertices']]
        world_faces = [tuple(points[i] for i in face) for face in source_faces]
        canonical = sorted(min(face[shift:] + face[:shift] for shift in range(3)) for face in world_faces)
        expected_faces = original[representation + '_triangle_indices']
        require(region['triangle_indices'] == expected_faces, 'actual_patch_triangle_mapping_changed')
        if representation == 'split':
            require(mesh['name'] == original['source_object_name'], 'split_patch_host_object_changed')
        result[region['roi_id']] = {'quad': region['vertices'], 'normal': region['normal'],
                                   'world_face_geometry': [[[str(v) for v in p] for p in face] for face in canonical]}
    classes = copy.deepcopy(index['classifications'])
    for name, view in classes.items():
        require(set(view) == set(wanted), 'classification_matrix_missing_patch')
        require(all(type(row['complete']) is bool for row in view.values()), 'boolean_completeness_required')
        mask = sum(1 << offset for offset, region in enumerate(index['regions']) if view[region['roi_id']]['complete'])
        require(type(index['view_masks'][name]) is int and mask == index['view_masks'][name], 'classification_mask_mismatch')
        for row in view.values():
            blocker = row.get('first_blocker')
            if blocker is None:
                continue
            require(set(blocker) == {'triangle_geometry_id', 'overlap_area_screen_exact'}
                    and blocker['triangle_geometry_id'] in blocker_geometry_ids
                    and Fraction(blocker['overlap_area_screen_exact']) > 0,
                    'actual_blocker_geometry_binding_required')
    return {'regions': result, 'classifications': classes, 'view_masks': index['view_masks'],
            'view_order': index['view_order'], 'cameras': index['cameras']}
