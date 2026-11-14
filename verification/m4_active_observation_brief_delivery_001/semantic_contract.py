"""Independent, pure semantic decoder for the frozen active brief contract.

This verification module never imports the product projector. File paths,
timers and work trees belong to full diagnostics and are compared separately.
"""

import base64
import copy
import hashlib
import json
import struct


SCHEMA = 'active-observation-brief-v1'
TOP_FIELDS = ('status', 'result_kind', 'observation_status', 'session_id',
              'read_only', 'execution_authority')
BINDING_FIELDS = ('scene_revision', 'document_epoch', 'capture_scope', 'unit',
                  'coordinate_frame', 'source', 'capture_state',
                  'source_binding_sha256', 'geometry_identity', 'camera_identity',
                  'binding_sha256', 'runtime_source_sha256', 'source_status',
                  'disk_status', 'source_check_scope')
OBJECT_COLUMNS = ('object_index', 'host_id', 'instance_id', 'object_name')
REGION_COLUMNS = ('roi_id', 'object_index', 'status', 'reason')
IMAGE_COLUMNS = ('view_name', 'image_ref', 'image_sha256', 'native_content_block_index')
OBSERVATION_COLUMNS = ('image_index', 'readable_region_indices')
PIXEL_COLUMNS = ('image_index', 'region_index', 'front_facing',
                 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable')
UNKNOWN_COLUMNS = ('object_index', 'status')
RULE_FIELDS = ('minimum_surface_pixels', 'minimum_boundary_pixels',
               'minimum_rgb_boundary_contrast')
DELIVERY_FIELDS = ('local_verified_image_count', 'mcp_content_constructed_image_count',
                   'consumer_read_status', 'frame_reuses', 'new_raster_attempts')
COVERAGE_FIELDS = ('observed_views', 'covered_roi_ids', 'unresolved_roi_ids',
                   'candidate_pool_uncovered_roi_ids', 'state_updates', 'scope')
SCOPE_FIELDS = ('capture_object_count', 'supported_roi_object_count',
                'objects_without_supported_roi', 'domain', 'all_objects_participate_in_occlusion')


class ContractError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise ContractError(reason)


def _keys(value, required, optional=()):
    _require(type(value) is dict, 'object_required')
    _require(set(required) <= set(value) <= set(required) | set(optional),
             'missing_or_unknown_fields:' + ','.join(required))


def _integer(value, reason):
    _require(type(value) is int and value >= 0, reason)
    return value


def _text(value, reason):
    _require(type(value) is str, reason)
    return value


def _list(value, reason):
    _require(type(value) is list, reason)
    return value


def _copy_fields(value, fields):
    _require(type(value) is dict and set(fields) <= set(value), 'required_fields_missing')
    return {key: copy.deepcopy(value[key]) for key in fields}


def _strict_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _table(value, name, columns):
    if name not in value:
        return []
    table = value[name]
    _keys(table, ('columns', 'rows'))
    _require(table['columns'] == list(columns), 'table_columns:' + name)
    rows = _list(table['rows'], 'table_rows:' + name)
    result = []
    for row in rows:
        _require(type(row) is list and len(row) == len(columns), 'table_width:' + name)
        result.append(dict(zip(columns, copy.deepcopy(row))))
    return result


def _reference(index, rows, reason):
    _integer(index, reason)
    _require(index < len(rows), reason)
    return rows[index]


def _references(indices, rows, field):
    _list(indices, 'reference_list')
    _require(all(type(index) is int for index in indices), 'reference_index_type')
    _require(len(indices) == len(set(indices)), 'duplicate_reference')
    return [_reference(index, rows, 'dangling_reference')[field] for index in indices]


def _binding(value, full):
    result = _copy_fields(value, BINDING_FIELDS)
    if not full:
        _keys(value, BINDING_FIELDS)
    state = result['capture_state']
    if state is not None:
        required = ('instance_id', 'epoch', 'revision')
        _keys(state, required, ('selection_key',) if full else ())
        result['capture_state'] = _copy_fields(state, required)
        _text(state['instance_id'], 'capture_instance')
        _integer(state['epoch'], 'capture_epoch')
        _integer(state['revision'], 'capture_revision')
    for key in BINDING_FIELDS:
        if key != 'capture_state':
            _text(result[key], 'binding_string:' + key)
    return result


def _validate(value):
    """Validate the complete canonical semantic graph, including negatives."""
    for key in TOP_FIELDS[:4]:
        _text(value[key], 'top_string:' + key)
    _require(value['result_kind'] == 'active_observation', 'active_result_required')
    _require(type(value['read_only']) is bool and type(value['execution_authority']) is bool,
             'authority_booleans')
    objects, regions, images = value['objects'], value['regions'], value['images']
    host_ids, instances, roi_ids, region_objects = set(), set(), set(), set()
    for index, obj in enumerate(objects):
        _keys(obj, OBJECT_COLUMNS)
        _require(type(obj['object_index']) is int and obj['object_index'] == index, 'ordered_object_index')
        for key in OBJECT_COLUMNS[1:]:
            _text(obj[key], 'object_string:' + key)
        _require(obj['host_id'] not in host_ids and obj['instance_id'] not in instances, 'duplicate_object_identity')
        host_ids.add(obj['host_id'])
        instances.add(obj['instance_id'])
    for region in regions:
        _keys(region, ('roi_id', 'object_index', 'object_name', 'host_id', 'instance_id', 'status', 'reason'))
        obj = _reference(region['object_index'], objects, 'region_object_reference')
        _require(all(region[key] == obj[key] for key in ('object_name', 'host_id', 'instance_id')), 'region_object_conflict')
        for key in ('roi_id', 'status', 'reason'):
            _text(region[key], 'region_string')
        _require(region['roi_id'] not in roi_ids and region['object_index'] not in region_objects, 'duplicate_region')
        roi_ids.add(region['roi_id'])
        region_objects.add(region['object_index'])
    coverage = value['coverage']
    _keys(coverage, COVERAGE_FIELDS)
    for key in COVERAGE_FIELDS[:4]:
        rows = _list(coverage[key], 'coverage_list')
        _require(all(type(item) is str for item in rows) and len(rows) == len(set(rows)), 'duplicate_coverage_reference')
        if key != 'observed_views':
            _require(set(rows) <= roi_ids, 'dangling_coverage_reference')
    covered, unresolved = set(coverage['covered_roi_ids']), set(coverage['unresolved_roi_ids'])
    _require(not covered.intersection(unresolved) and covered | unresolved == roi_ids, 'coverage_partition')
    _require(set(coverage['candidate_pool_uncovered_roi_ids']) <= unresolved, 'finite_pool_scope')
    _require(_integer(coverage['state_updates'], 'state_updates') == len(coverage['observed_views']), 'state_update_count')
    _text(coverage['scope'], 'coverage_scope')
    for region in regions:
        _require(region['status'] == ('covered' if region['roi_id'] in covered else 'unknown'), 'region_coverage_conflict')
    scope = value['scope']
    _keys(scope, SCOPE_FIELDS)
    _require(_integer(scope['capture_object_count'], 'capture_count') == len(objects), 'capture_count_mismatch')
    _require(_integer(scope['supported_roi_object_count'], 'supported_count') == len(regions), 'supported_count_mismatch')
    _text(scope['domain'], 'supported_domain')
    _require(type(scope['all_objects_participate_in_occlusion']) is bool, 'occlusion_scope_boolean')
    unknown_indices = []
    for row in _list(scope['objects_without_supported_roi'], 'unknown_object_rows'):
        _keys(row, (*OBJECT_COLUMNS, 'status'))
        obj = _reference(row['object_index'], objects, 'unknown_object_reference')
        _require(all(row[key] == obj[key] for key in OBJECT_COLUMNS), 'unknown_object_conflict')
        _text(row['status'], 'unknown_object_status')
        unknown_indices.append(row['object_index'])
    _require(len(unknown_indices) == len(set(unknown_indices)) and set(unknown_indices) == set(range(len(objects))) - region_objects,
             'unsupported_object_partition')
    refs, views = set(), set()
    for index, image in enumerate(images):
        _keys(image, IMAGE_COLUMNS)
        for key in IMAGE_COLUMNS[:3]:
            _text(image[key], 'image_string')
        _require(image['image_ref'] not in refs and image['view_name'] not in views, 'duplicate_image_reference')
        _require(type(image['native_content_block_index']) is int and image['native_content_block_index'] == index + 1,
                 'native_image_order')
        refs.add(image['image_ref'])
        views.add(image['view_name'])
    _require(coverage['observed_views'] == [image['view_name'] for image in images], 'observation_view_order')
    _require(images or not covered, 'covered_without_observation')
    _require(len(value['observations']) == len(images), 'observation_image_count')
    rules = None
    for image, observation in zip(images, value['observations']):
        _keys(observation, ('view_name', 'image_ref', 'image_sha256', 'readable_roi_ids', 'pixel_rows'))
        _require(all(observation[key] == image[key] for key in ('view_name', 'image_ref', 'image_sha256')), 'observation_image_conflict')
        seen = []
        readable = []
        for pixel in _list(observation['pixel_rows'], 'pixel_rows'):
            _keys(pixel, ('roi_id', 'object_index', 'view', 'front_facing', 'visible_surface_pixels',
                          'contrasting_boundary_pixels', 'readable', *RULE_FIELDS, 'host_id', 'object_name'))
            _require(pixel['roi_id'] in roi_ids and pixel['roi_id'] not in seen, 'duplicate_or_dangling_pixel_region')
            region = next(row for row in regions if row['roi_id'] == pixel['roi_id'])
            _require(pixel['object_index'] == region['object_index'] and type(pixel['object_index']) is int and
                     pixel['host_id'] == region['host_id'] and pixel['object_name'] == region['object_name'] and
                     pixel['view'] == image['view_name'], 'pixel_reference_conflict')
            _require(type(pixel['front_facing']) is bool and type(pixel['readable']) is bool, 'pixel_booleans')
            _integer(pixel['visible_surface_pixels'], 'surface_count')
            _integer(pixel['contrasting_boundary_pixels'], 'boundary_count')
            current = _copy_fields(pixel, RULE_FIELDS)
            _require(all(type(current[key]) is int for key in RULE_FIELDS) and list(current.values()) == [16, 4, 24], 'pixel_rules')
            if rules is None:
                rules = current
            _require(current == rules, 'pixel_rule_conflict')
            expected_readable = pixel['front_facing'] and pixel['visible_surface_pixels'] >= 16 and pixel['contrasting_boundary_pixels'] >= 4
            _require(pixel['readable'] is expected_readable, 'pixel_readability_conflict')
            seen.append(pixel['roi_id'])
            if pixel['readable']:
                readable.append(pixel['roi_id'])
        _require(seen == [row['roi_id'] for row in regions], 'incomplete_or_reordered_pixel_grid')
        _require(observation['readable_roi_ids'] == readable, 'readable_reference_conflict')
    delivery = value['image_delivery']
    _keys(delivery, DELIVERY_FIELDS)
    for key in DELIVERY_FIELDS:
        if key != 'consumer_read_status':
            _integer(delivery[key], 'delivery_count')
    _text(delivery['consumer_read_status'], 'consumer_read_status')
    _require(delivery['local_verified_image_count'] == delivery['mcp_content_constructed_image_count'] == len(images), 'delivery_image_count')
    _text(value['image_delivery_scope'], 'image_delivery_scope')
    if not regions:
        _require(value['status'] == 'unknown' and value['observation_status'] == 'no_supported_regions' and not images,
                 'zero_region_unknown_required')
    _strict_json(value)
    return value


def canonicalize_full(value):
    """Project a historical full value onto the explicit frozen task semantics."""
    _keys(value, (*TOP_FIELDS, 'binding', 'facts', 'frames', 'image_delivery'),
          ('work', 'generation_work', 'stages', 'generation_stages'))
    _keys(value['binding'], (*BINDING_FIELDS, 'objects'), ('schema', 'camera_policy'))
    binding = _binding(value['binding'], full=True)
    facts = value['facts']
    _keys(facts, ('scene_identity', 'candidate_identity', 'regions', 'observations',
                  'coverage', 'image_delivery_scope', 'scope'))
    _require(facts['scene_identity'] == binding['geometry_identity'] and facts['candidate_identity'] == binding['camera_identity'],
             'fact_identity_conflict')
    images = []
    for index, frame in enumerate(_list(value['frames'], 'full_frames')):
        _keys(frame, ('scene_identity', 'candidate_identity', *IMAGE_COLUMNS[:3],
                      'host_binding_sha256', 'source_revision'),
              ('image_path', 'PNG_bytes', 'arrays_path', 'arrays_sha256',
               'compressed_array_file_bytes', 'array_payload_bytes', 'stages', 'feedback_stages'))
        _require(frame['scene_identity'] == binding['geometry_identity'] and frame['candidate_identity'] == binding['camera_identity'] and
                 frame['host_binding_sha256'] == binding['binding_sha256'] and frame['source_revision'] == binding['scene_revision'],
                 'frame_source_conflict')
        images.append({**_copy_fields(frame, IMAGE_COLUMNS[:3]), 'native_content_block_index': index + 1})
    observations = []
    for row in facts['observations']:
        _keys(row, ('view_name', 'image_ref', 'image_sha256', 'readable_roi_ids', 'pixel_rows'), ('image_path',))
        observations.append(_copy_fields(row, ('view_name', 'image_ref', 'image_sha256', 'readable_roi_ids', 'pixel_rows')))
    result = {**_copy_fields(value, TOP_FIELDS), 'binding': binding,
              'objects': copy.deepcopy(value['binding']['objects']), 'regions': copy.deepcopy(facts['regions']),
              'coverage': copy.deepcopy(facts['coverage']), 'scope': copy.deepcopy(facts['scope']),
              'images': images, 'observations': observations,
              'image_delivery': copy.deepcopy(value['image_delivery']), 'image_delivery_scope': facts['image_delivery_scope']}
    return _validate(result)


def decode_brief(value):
    """Expand public table references without importing or calling the product."""
    required = ('schema', 'index_base', *TOP_FIELDS, 'binding', 'coverage', 'scope',
                'image_delivery', 'image_delivery_scope')
    _keys(value, required, ('objects', 'regions', 'images', 'observations', 'pixels', 'pixel_rules'))
    _require(value['schema'] == SCHEMA and type(value['index_base']) is int and value['index_base'] == 0, 'brief_schema')
    binding = _binding(value['binding'], full=False)
    objects = _table(value, 'objects', OBJECT_COLUMNS)
    regions = []
    for row in _table(value, 'regions', REGION_COLUMNS):
        obj = _reference(row['object_index'], objects, 'region_object_reference')
        regions.append({**row, **_copy_fields(obj, ('host_id', 'instance_id', 'object_name'))})
    images = _table(value, 'images', IMAGE_COLUMNS)
    coverage = value['coverage']
    _keys(coverage, ('scope', 'state_updates'), ('observed_views', 'covered_region_indices', 'unresolved_region_indices', 'candidate_pool_uncovered_region_indices'))
    expanded_coverage = {'scope': coverage['scope'], 'state_updates': coverage['state_updates'],
                         'observed_views': copy.deepcopy(coverage.get('observed_views', []))}
    for old, new in [('covered_roi_ids', 'covered_region_indices'), ('unresolved_roi_ids', 'unresolved_region_indices'),
                     ('candidate_pool_uncovered_roi_ids', 'candidate_pool_uncovered_region_indices')]:
        expanded_coverage[old] = _references(coverage.get(new, []), regions, 'roi_id')
    scope = value['scope']
    _keys(scope, ('capture_object_count', 'supported_roi_object_count', 'domain', 'all_objects_participate_in_occlusion'), ('objects_without_supported_roi',))
    unsupported = []
    for row in _table(scope, 'objects_without_supported_roi', UNKNOWN_COLUMNS):
        unsupported.append({**copy.deepcopy(_reference(row['object_index'], objects, 'unknown_object_reference')), 'status': row['status']})
    expanded_scope = {**_copy_fields(scope, ('capture_object_count', 'supported_roi_object_count', 'domain', 'all_objects_participate_in_occlusion')),
                      'objects_without_supported_roi': unsupported}
    rules = value.get('pixel_rules', {})
    pixel_table = _table(value, 'pixels', PIXEL_COLUMNS)
    if pixel_table:
        _keys(rules, RULE_FIELDS)
    else:
        _require(rules == {}, 'rules_without_pixels')
    by_image = [[] for image in images]
    seen_pixels = set()
    for row in pixel_table:
        image = _reference(row['image_index'], images, 'pixel_image_reference')
        region = _reference(row['region_index'], regions, 'pixel_region_reference')
        pair = (row['image_index'], row['region_index'])
        _require(pair not in seen_pixels, 'duplicate_pixel_reference')
        seen_pixels.add(pair)
        by_image[row['image_index']].append({
            **_copy_fields(region, ('roi_id', 'object_index', 'host_id', 'object_name')),
            'view': image['view_name'], **_copy_fields(row, ('front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable')),
            **copy.deepcopy(rules)})
    observations, seen_images = [], set()
    for row in _table(value, 'observations', OBSERVATION_COLUMNS):
        image = _reference(row['image_index'], images, 'observation_image_reference')
        _require(row['image_index'] not in seen_images, 'duplicate_observation_reference')
        seen_images.add(row['image_index'])
        observations.append({**_copy_fields(image, IMAGE_COLUMNS[:3]),
                             'readable_roi_ids': _references(row['readable_region_indices'], regions, 'roi_id'),
                             'pixel_rows': by_image[row['image_index']]})
    result = {**_copy_fields(value, TOP_FIELDS), 'binding': binding, 'objects': objects, 'regions': regions,
              'coverage': expanded_coverage, 'scope': expanded_scope, 'images': images, 'observations': observations,
              'image_delivery': copy.deepcopy(value['image_delivery']), 'image_delivery_scope': value['image_delivery_scope']}
    return _validate(result)


def compare_semantics(original_full, brief):
    expected, actual = canonicalize_full(original_full), decode_brief(brief)
    return {'passed': _strict_json(expected) == _strict_json(actual), 'expected': expected, 'actual': actual}


def canonicalize_full_diagnostics(value, path_relocations=None):
    """Keep every field, reversing only declared PNG image_path moves."""
    result = copy.deepcopy(value)
    mapping = {} if path_relocations is None else path_relocations
    _require(type(mapping) is dict and all(type(k) is str and type(v) is str for k, v in mapping.items()), 'path_mapping')
    for frame in result.get('frames', []):
        if frame.get('image_path') in mapping:
            frame['image_path'] = mapping[frame['image_path']]
    for observation in result.get('facts', {}).get('observations', []):
        if observation.get('image_path') in mapping:
            observation['image_path'] = mapping[observation['image_path']]
    _strict_json(result)
    return result


def extract_public_value(response):
    _require(type(response) is dict and 'error' not in response and type(response.get('result')) is dict,
             'successful_RPC_response_required')
    result = response['result']
    _require(result.get('isError') is False, 'successful_tool_result_required')
    content = _list(result.get('content'), 'MCP_content_required')
    _require(content and type(content[0]) is dict and set(content[0]) == {'type', 'text'} and
             content[0]['type'] == 'text' and type(content[0]['text']) is str, 'first_text_block_required')
    for block in content[1:]:
        _require(type(block) is dict and set(block) == {'type', 'mimeType', 'data'} and block['type'] == 'image' and
                 block['mimeType'] == 'image/png' and type(block['data']) is str, 'native_PNG_block_required')
    return json.loads(content[0]['text'])


def validate_native_images(response, semantics=None):
    public = extract_public_value(response)
    if semantics is None:
        semantics = decode_brief(public) if public.get('schema') == SCHEMA else canonicalize_full(public)
    else:
        semantics = _validate(semantics)
    images = semantics['images']
    content = response['result']['content']
    _require(len(content) == len(images) + 1, 'native_image_count')
    rows = []
    for image in images:
        index = image['native_content_block_index']
        block = content[index]
        try:
            raw = base64.b64decode(block['data'], validate=True)
        except (ValueError, TypeError) as error:
            raise ContractError('native_image_base64') from error
        _require(len(raw) >= 24 and raw.startswith(b'\x89PNG\r\n\x1a\n'), 'native_PNG_signature')
        width, height = struct.unpack('>II', raw[16:24])
        _require((width, height) == (512, 512), 'native_PNG_dimensions')
        _require(hashlib.sha256(raw).hexdigest() == image['image_sha256'], 'native_image_reference_hash')
        rows.append({'native_content_block_index': index, 'image_ref': image['image_ref'],
                     'image_sha256': image['image_sha256'], 'PNG_bytes': len(raw), 'width': width, 'height': height})
    return {'passed': True, 'native_image_blocks': len(rows), 'images': rows}
