"""Root child offline semantic reconstruction; imports neither product nor author decoder."""
from pathlib import Path
import copy
import hashlib
import json

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = REPO / 'verification/m4_active_observation_brief_delivery_001'
OUT = Path(__file__).parent / 'semantics_result.json'
checks = []
inputs_read = {}

def check(name, actual, expected):
    ok = type(actual) is type(expected) and actual == expected
    checks.append({'check': name, 'passed': ok})
    if not ok:
        raise AssertionError((name, actual, expected))

def load(path):
    data = path.read_bytes()
    inputs_read[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)

def public(response):
    check('response_not_error', response['result']['isError'], False)
    check('initial_content_is_text', response['result']['content'][0]['type'], 'text')
    return json.loads(response['result']['content'][0]['text'])

def table(value, key):
    if key not in value:
        return []
    spec = value[key]
    check(key + '_unique_columns', len(set(spec['columns'])), len(spec['columns']))
    result = []
    for row in spec['rows']:
        check(key + '_row_width', len(row), len(spec['columns']))
        result.append(dict(zip(spec['columns'], row)))
    return result

def restore(brief, old):
    check('schema', brief['schema'], 'active-observation-brief-v1')
    check('index_base', brief['index_base'], 0)
    top = ('status', 'result_kind', 'observation_status', 'session_id', 'read_only', 'execution_authority')
    for key in top:
        check('top_' + key, brief[key], old[key])
    binding = copy.deepcopy(old['binding'])
    objects = table(brief, 'objects')
    check('all_objects', objects, binding.pop('objects'))
    binding.pop('schema')
    binding.pop('camera_policy')
    if binding['capture_state'] is not None:
        binding['capture_state'].pop('selection_key')
    check('all_retained_binding', brief['binding'], binding)
    regions = table(brief, 'regions')
    for region in regions:
        i = region['object_index']
        check('object_reference_int', type(i).__name__, 'int')
        region.update({key: objects[i][key] for key in ('host_id', 'instance_id', 'object_name')})
    check('all_regions_restored', regions, old['facts']['regions'])
    scope = copy.deepcopy(brief['scope'])
    unsupported = table(scope, 'objects_without_supported_roi')
    for row in unsupported:
        i = row['object_index']
        row.update({key: objects[i][key] for key in ('host_id', 'instance_id', 'object_name')})
    scope['objects_without_supported_roi'] = unsupported
    check('entire_scope_restored', scope, old['facts']['scope'])
    check('unsupported_partition', {row['object_index'] for row in unsupported},
          set(range(len(objects))) - {row['object_index'] for row in regions})
    images = table(brief, 'images')
    for i, image in enumerate(images):
        check('native_block_index', image['native_content_block_index'], i + 1)
        for key in ('view_name', 'image_ref', 'image_sha256'):
            check('frame_' + key, image[key], old['frames'][i][key])
        for left, right in (('scene_identity', 'geometry_identity'), ('candidate_identity', 'camera_identity'),
                            ('host_binding_sha256', 'binding_sha256'), ('source_revision', 'scene_revision')):
            check('omitted_frame_alias_' + left, old['frames'][i][left], binding[right])
    check('complete_image_count', len(images), len(old['frames']))
    pixels = table(brief, 'pixels')
    observations = []
    for observation in table(brief, 'observations'):
        image_index = observation['image_index']
        image = images[image_index]
        item = {key: image[key] for key in ('view_name', 'image_ref', 'image_sha256')}
        item['readable_roi_ids'] = [regions[i]['roi_id'] for i in observation['readable_region_indices']]
        item['pixel_rows'] = []
        for pixel in pixels:
            if pixel['image_index'] != image_index:
                continue
            region = regions[pixel['region_index']]
            row = {key: pixel[key] for key in ('front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable')}
            row.update({key: region[key] for key in ('roi_id', 'object_index', 'host_id', 'object_name')})
            row['view'] = image['view_name']
            row.update(brief['pixel_rules'])
            item['pixel_rows'].append(row)
            check('readability_consistent', row['readable'],
                  row['front_facing'] and row['visible_surface_pixels'] >= row['minimum_surface_pixels']
                  and row['contrasting_boundary_pixels'] >= row['minimum_boundary_pixels'])
        observations.append(item)
    old_observations = copy.deepcopy(old['facts']['observations'])
    for item in old_observations:
        item.pop('image_path')
    check('all_observation_fields_and_negative_pixels', observations, old_observations)
    coverage = {key: brief['coverage'][key] for key in ('scope', 'state_updates')}
    coverage['observed_views'] = brief['coverage'].get('observed_views', [])
    for key in ('covered', 'unresolved', 'candidate_pool_uncovered'):
        coverage[key + '_roi_ids'] = [regions[i]['roi_id'] for i in brief['coverage'].get(key + '_region_indices', [])]
    check('entire_coverage', coverage, old['facts']['coverage'])
    check('delivery_scope', brief['image_delivery_scope'], old['facts']['image_delivery_scope'])
    check('delivery_counts_and_status', brief['image_delivery'], old['image_delivery'])
    check('omitted_scene_alias', old['facts']['scene_identity'], binding['geometry_identity'])
    check('omitted_camera_alias', old['facts']['candidate_identity'], binding['camera_identity'])
    if not regions:
        check('empty_roi_remains_unknown', brief['status'], 'unknown')
        check('no_invented_covered_rois', coverage['covered_roi_ids'], [])
    return {'objects': len(objects), 'regions': len(regions), 'unknown_non_roi': len(unsupported),
            'observations': len(observations), 'pixels': len(pixels),
            'negative_pixel_rows': sum(not row['readable'] for row in pixels),
            'unknown_regions': sum(row['status'] == 'unknown' for row in regions)}

result = {'method': 'independent JSON table reconstruction, no product/author decoder imports',
          'new_product_model_Blender_raster_calls': 0, 'findings': [], 'cases': []}
try:
    archive = load(BASE / 'EXTERNAL_ARCHIVE.json')
    entries = {row['original_relative_path']: row for row in archive['files']}
    def archived(relative):
        row = entries[relative]
        path = REPO / row['archive_path']
        check('archived_source_sha', hashlib.sha256(path.read_bytes()).hexdigest(), row['sha256'])
        return load(path)
    for ci, case in enumerate(load(BASE / 'inputs/INPUTS.json')['cases']):
        name = case['case']
        old_response = load(BASE / 'inputs' / case['raw_response'])
        old = public(old_response)
        responses = []
        for di, detail in enumerate(('default', 'brief', 'full')):
            rpc = ci * 3 + di + 3
            prefix = f'run/replay_01/stdio/rpc_{rpc:02}'
            response = archived(prefix + '/RX.bin')
            request = archived(prefix + '/TX.bin')
            check('request_response_id', response['id'], request['id'])
            check('recorded_case_detail', response['id'], name + '__' + detail)
            check('response_detail_arg', request['params']['arguments'].get('response_detail'),
                  None if detail == 'default' else detail)
            value = public(response)
            if detail != 'full':
                counts = restore(value, old)
            else:
                # Reverse only the registered PNG read-location changes, nowhere else.
                restored = copy.deepcopy(value)
                mapping = {str(Path('D:/he_brief_001/payload/inputs') / image['file']): image['source_image_path']
                           for image in case['images']}
                for frame in restored['frames']:
                    check('registered_full_frame_path', frame['image_path'] in mapping, True)
                    frame['image_path'] = mapping[frame['image_path']]
                for observation in restored['facts']['observations']:
                    check('registered_full_observation_path', observation['image_path'] in mapping, True)
                    observation['image_path'] = mapping[observation['image_path']]
                check('full_entire_value', restored, old)
            responses.append(value)
        check('default_equals_brief', responses[0], responses[1])
        result['cases'].append({'case': name, **counts})
    result['passed'] = True
except Exception as error:
    result.update(passed=False, error={'type': type(error).__name__, 'message': str(error)[:4000]})
finally:
    result['checks'] = checks
    result['checks_passed'] = sum(row['passed'] for row in checks)
    result['checks_total'] = len(checks)
    result['inputs_read'] = inputs_read
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key not in ('checks', 'inputs_read')}, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)
