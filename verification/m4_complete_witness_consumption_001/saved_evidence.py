"""Read actual owner artifacts and independently bind complete/readable facts."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_witness_saved_oracle', HERE / 'oracle.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)

def table(value):
    if value is None:
        return []
    columns = value['columns']
    if len(set(columns)) != len(columns) or any((len(row) != len(columns) for row in value['rows'])):
        raise ValueError('public_table_shape')
    return [dict(zip(columns, row)) for row in value['rows']]

class ProductFactError(ValueError):
    pass

def bind_public_regions(regions, raw, truth):
    """Bind geometry to actual public names, retaining private oracle labels."""
    private_by_object = {region['object_index']: region for region in truth['regions']}
    if len(regions) != len(private_by_object) or len({row['roi_id'] for row in regions}) != len(regions):
        raise ProductFactError('supported_region_cardinality_or_duplicate_identity')
    full_regions = {region['roi_id']: region for region in raw['facts']['regions']}
    source_regions = {region['roi_id']: region for region in raw['facts']['scope']['patch_support']['regions']}
    bound = copy.deepcopy(truth)
    aliases = []
    for public in regions:
        expected = private_by_object.get(public['object_index'])
        if expected is None:
            raise ProductFactError('unexpected_source_object')
        for field in ('center_world_m', 'front_direction_world'):
            if public[field] != expected[field]:
                raise ProductFactError('source_world_description:' + field)
        center = [oracle.fraction(value) for value in public['center_world_m']]
        u = [oracle.fraction(value) for value in public['half_edge_u_world_m']]
        v = [oracle.fraction(value) for value in public['half_edge_v_world_m']]
        actual_corners = {tuple((center[k] + a * u[k] + b * v[k] for k in range(3))) for a,
            b in [(-1,
                    -1),
                (1,
                    -1),
                (1,
                    1),
                (-1,
                    1)]}
        expected_corners = {tuple((oracle.fraction(value) for value in point)) for point in expected['quad_world_m']}
        cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        if actual_corners != expected_corners or cross[0] != 0 or cross[1] != 0 or (cross[2] <= 0):
            raise ProductFactError('source_quad_or_front_winding')
        full = full_regions.get(public['roi_id'])
        source = source_regions.get(public['roi_id'])
        if full is None or source is None or full['object_index'] != expected['object_index'] or (full['object_name'] != expected['object_name']) or (full['host_id'] != expected['host_id']) or (source['object_index'] != expected['object_index']) or (source['triangle_indices'] != expected['source_triangle_indices']) or (public['triangle_count'] != len(expected['source_triangle_indices'])):
            raise ProductFactError('actual_public_source_triangle_binding')
        replacement = next((region for region in bound['regions'] if region['object_index'] == expected['object_index']))
        replacement['private_oracle_label'] = replacement['roi_id']
        replacement['roi_id'] = public['roi_id']
        aliases.append({'private_label': expected['roi_id'],
                'public_roi_id': public['roi_id'],
                'object_index': expected['object_index'],
                'object_name': expected['object_name']})
        if expected['roi_id'] == truth['target_roi_id']:
            bound['target_roi_id'] = public['roi_id']
    if len({row['object_index'] for row in regions}) != len(private_by_object):
        raise ProductFactError('duplicate_source_object_region')
    return (bound, aliases)

def evaluate(owner, truth):
    owner = Path(owner).resolve()
    raw = oracle.read(owner / 'product_call_01/SERVICE_RESULT.json')
    response = oracle.read(owner / 'tool_01/RESPONSE.json')
    request = oracle.read(owner / 'tool_01/REQUEST.json')
    observation = oracle.read(owner / 'OBSERVATIONS.json')
    arguments = request['params']['arguments']
    if request['params']['name'] != 'active_observation' or type(arguments) is not dict or set(arguments) - {'include_images'} or (arguments.get('include_images',
            True) is not True):
        raise ValueError('first_actual_active_images_request_required')
    if response['result']['isError'] is not False:
        raise ValueError('actual_active_product_tool_error')
    public = json.loads(response['result']['content'][0]['text'])
    if public['schema'] != 'active-observation-brief-v4' or raw['binding']['runtime_source_sha256'] != 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02':
        raise ValueError('fixed_candidate_and_brief_required')
    if len(observation['active']) < 1 or len(observation['render_attempts']) > 6:
        raise ValueError('actual_observation_and_six_attempt_contract')
    for key, wanted in truth['input_sha256'].items():
        if observation['source_inputs'][key + '_sha256'] != wanted:
            raise ValueError('owner_source_differs_from_truth:' + key)
    expected_binding = {key: copy.deepcopy(value) for key,
        value in raw['binding'].items() if key not in ('camera_specification',
            'schema',
            'objects',
            'camera_policy')}
    if isinstance(expected_binding.get('capture_state'), dict):
        expected_binding['capture_state'].pop('selection_key', None)
    if public['binding'] != expected_binding:
        raise ValueError('public_to_actual_producer_source_binding')
    regions = table(public.get('regions'))
    pixels = table(public.get('pixels'))
    images = table(public.get('images'))
    truth, aliases = bind_public_regions(regions, raw, truth)
    truth_by_id = {r['roi_id']: r for r in truth['regions']}
    input_manifest = oracle.read(oracle.read(HERE / 'PLAN.json')['inputs']['input_manifest'])
    camera_spec = input_manifest['cameras']
    camera_path = Path(camera_spec['path'])
    if oracle.sha(camera_path) != truth['input_sha256']['cameras']:
        raise ValueError('frozen_external_camera_source_changed')
    cameras = oracle.read(camera_path)
    if raw['binding'].get('camera_specification') != cameras:
        raise ValueError('actual_product_camera_pool_differs_from_frozen_input')
    cameras_by_name = {camera['name']: camera for camera in cameras['views']}
    frame_names = [f['view_name'] for f in raw['frames']]
    if len(set(frame_names)) != len(frame_names) or frame_names != [r['view_name'] for r in images] or len(pixels) != len(regions) * len(images):
        raise ValueError('actual_frame_pixel_cardinality_and_order')
    product_errors = []

    def check(label, value):
        if not value:
            product_errors.append(label)
    for row in regions:
        expected = truth_by_id[row['roi_id']]
        for name in ('object_index', 'center_world_m', 'front_direction_world'):
            check('world_region:' + row['roi_id'] + ':' + name, row[name] == expected[name])
        check('two_source_faces:' + row['roi_id'], row['triangle_count'] == 2)
    independent = []
    actual_by_ref = {}
    for index, frame in enumerate(raw['frames']):
        if not Path(frame['image_path']).resolve().is_relative_to(owner) or not Path(frame['arrays_path']).resolve().is_relative_to(owner):
            raise ValueError('current_owner_frame_files_required')
        if frame['view_name'] not in truth['view_names'] or frame['pose'] != cameras_by_name[frame['view_name']]:
            raise ValueError('registered_actual_view')
        measured = oracle.frame_pixels(frame, truth)
        independent.append(measured)
        actual_by_ref[frame['image_ref']] = measured
        if images[index]['image_ref'] != frame['image_ref'] or images[index]['image_sha256'] != frame['image_sha256']:
            raise ValueError('public_image_source_binding')
        block = response['result']['content'][images[index]['native_content_block_index']]
        if block['type'] != 'image' or block['mimeType'] != 'image/png' or base64.b64decode(block['data'],
            validate=True) != Path(frame['image_path']).read_bytes():
            raise ValueError('actual_public_image_block_bytes')
        by_roi = {r['roi_id']: r for r in measured['rows']}
        for region_index, region in enumerate(regions):
            p = pixels[index * len(regions) + region_index]
            m = by_roi[region['roi_id']]
            if p['image_index'] != index or p['region_index'] != region_index:
                raise ValueError('public_pixel_order_identity')
            check('actual_pixels:' + str(index) + ':' + region['roi_id'],
                (p['visible_surface_pixels'],
                    p['contrasting_boundary_pixels'],
                    p['front_facing'],
                    p['readable'],
                    p['visible_pixel_bounds'],
                    p['visible_pixel_anchor']) == (m['surface_pixels'],
                    m['boundary_pixels'],
                    m['front_facing'],
                    m['readable'],
                    m['bounds'],
                    m['anchor']))
    covered = {m['roi_id'] for frame in independent for m in frame['rows'] if m['complete_readable']}
    covered_indices = public['coverage'].get('covered_region_indices', [])
    unresolved_indices = public['coverage'].get('unresolved_region_indices', [])
    declared = {regions[i]['roi_id'] for i in covered_indices}
    unresolved = {regions[i]['roi_id'] for i in unresolved_indices}
    check('independent_covered_set', declared == covered)
    check('independent_remaining_set', unresolved == set(truth_by_id) - covered)
    check('coverage_index_partition',
        len(covered_indices) == len(declared) and len(unresolved_indices) == len(unresolved) and declared.isdisjoint(unresolved) and (declared | unresolved == set(truth_by_id)))
    check('candidate_pool_uncovered',
        public['coverage'].get('candidate_pool_uncovered_region_indices',
            []) == [])
    observed_names = set(frame_names)
    pending = {roi for roi in unresolved if any((description['complete'] and view not in observed_names for view,
                description in truth_by_id[roi]['views'].items()))}
    inspection = public['inspection']
    check('inspection_supported_counts',
        inspection['counts']['supported'] == len(truth_by_id) and inspection['counts']['covered'] == len(covered) and (inspection['counts']['unobserved'] == len(unresolved)) and (inspection['counts']['pending_geometric_candidate'] == len(pending)))
    check('finite_pool_stop_scope', not pending or inspection['state'] != 'finite_pool_exhausted')
    for row in regions:
        check('region_status:' + row['roi_id'],
            row['status'] == ('covered' if row['roi_id'] in covered else 'unknown'))
    check('all_supported_faces_accounted',
        len(raw['facts']['scope']['patch_support']['regions']) == 2 and sum((len(r['triangle_indices']) for r in raw['facts']['scope']['patch_support']['regions'])) == 4 and all((not row['unsupported_components'] for row in raw['facts']['scope']['patch_support']['objects'])))
    valid_witnesses = {}
    for region_index, region in enumerate(regions):
        witness = region['complete_witness_pixel_index']
        if region['roi_id'] not in covered:
            check('uncovered_has_no_witness:' + region['roi_id'], witness is None)
            continue
        if type(witness) is not int or not 0 <= witness < len(pixels):
            product_errors.append('covered_witness_index_missing_or_invalid:' + region['roi_id'])
            continue
        p = pixels[witness]
        if p['region_index'] != region_index:
            product_errors.append('witness_target_binding:' + region['roi_id'])
            continue
        frame = independent[p['image_index']]
        m = next((r for r in frame['rows'] if r['roi_id'] == region['roi_id']))
        check('independent_complete_witness:' + region['roi_id'], m['complete_readable'])
        valid_witnesses[region['roi_id']] = dict(pixel_index=witness,
            view_name=frame['view_name'],
            image_ref=frame['image_ref'],
            surface_pixels=m['surface_pixels'],
            boundary_pixels=m['boundary_pixels'],
            anchor=m['anchor'])
    target = truth['target_roi_id']
    ordered = []
    for image_index, frame in enumerate(independent):
        region_index = next((i for i, r in enumerate(regions) if r['roi_id'] == target))
        m = next((r for r in frame['rows'] if r['roi_id'] == target))
        ordered.append(dict(pixel_index=image_index * len(regions) + region_index,
                view_name=frame['view_name'],
                image_ref=frame['image_ref'],
                **m))
    readable = [r for r in ordered if r['readable']]
    complete = [r for r in ordered if r['complete_readable']]
    realized = bool(readable and (not readable[0]['complete']) and complete)
    return dict(public=public,
        raw=raw,
        regions=regions,
        pixels=pixels,
        images=images,
        frames=independent,
        aliases=aliases,
        bound_truth=truth,
        by_ref=actual_by_ref,
        independent_covered_roi_ids=sorted(covered),
        independent_remaining_roi_ids=sorted(set(truth_by_id) - covered),
        product_errors=product_errors,
        realized=realized,
        target_ordered_rows=ordered,
        target_first_readable=readable[0] if readable else None,
        target_actual_complete_rows=complete,
        public_complete_witnesses=valid_witnesses,
        actual_rasters=len(observation['render_attempts']),
        actual_product_calls=len(observation['active']),
        actual_owner_pid=observation['process_id'])

def summary(value):
    return {key: value[key] for key in ('independent_covered_roi_ids',
            'independent_remaining_roi_ids',
            'product_errors',
            'realized',
            'target_ordered_rows',
            'target_first_readable',
            'target_actual_complete_rows',
            'public_complete_witnesses',
            'actual_rasters',
            'actual_product_calls',
            'actual_owner_pid',
            'aliases')}
