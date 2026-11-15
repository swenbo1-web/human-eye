"""Independently validate saved source, frame and public facts for this batch.

Imports only the task's administrator oracle. No product entry, renderer or
consumer is called. Public ROI names are aliases for independently fixed
object/local-triangle sets, including multiple regions on the same object.
"""

import base64
import copy
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
PRODUCT_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'


class ProductFactError(ValueError):
    pass


def load_oracle():
    spec = importlib.util.spec_from_file_location('_occluded_transfer_oracle', HERE / 'oracle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table(value):
    if value is None:
        return []
    columns = value['columns']
    if len(set(columns)) != len(columns) or any(len(row) != len(columns) for row in value['rows']):
        raise ValueError('public_table_shape')
    return [dict(zip(columns, row)) for row in value['rows']]


def vec(value):
    if len(value) != 3:
        raise ValueError('three_coordinate_vector_required')
    return tuple(Fraction.from_float(x) if type(x) is float else Fraction(x) for x in value)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def same_normal(a, b):
    a, b = vec(a), vec(b)
    if cross(a, b) == (0, 0, 0):
        return sum(x*y for x, y in zip(a, b)) > 0
    # World unit normals may contain an irrational normalization factor.
    # Source triangle binding and corners remain exact. Here compare only
    # orientation after unit normalization, within double-rounding error.
    a, b = tuple(map(float, a)), tuple(map(float, b))
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    return bool(na and nb and all(abs(x/na-y/nb) <= 2e-14 for x, y in zip(a, b)))


def region_key(region):
    return region['roi_id']


def unknown_reason(region, pixel_rows):
    """The actual finite-pool reason, with occlusion distinct from no front."""
    views = list(region['views'].values())
    if not any(row['front_facing'] for row in views):
        return 'no_front_facing_candidate'
    if any(row['complete_readable'] for row in pixel_rows):
        return None
    if not any(row['complete'] for row in views):
        fronts = [row for row in views if row['front_facing']]
        if all(row['fully_in_view'] and Fraction(row['positive_shadow_area']) > 0 for row in fronts):
            return 'positive_area_occlusion_all_front_views'
        return 'no_complete_geometric_candidate'
    return 'pixel_evidence_insufficient'


def bind_regions(public_regions, raw, truth):
    source = {r['roi_id']: r for r in raw['facts']['scope']['patch_support']['regions']}
    full = {r['roi_id']: r for r in raw['facts']['regions']}
    independent = {(r['object_index'], tuple(sorted(r['source_triangle_indices']))): r
                   for r in truth['regions']}
    if (len(public_regions) != len(independent) or len({r['roi_id'] for r in public_regions}) != len(independent)
            or len(source) != len(independent) or len(full) != len(independent)):
        raise ProductFactError('product_region_cardinality_or_duplicate')
    aliases = {}
    for row in public_regions:
        identity = row['roi_id']
        if identity not in source or identity not in full:
            raise ProductFactError('product_missing_source_region_binding')
        original = source[identity]
        key = (original['object_index'], tuple(sorted(original['triangle_indices'])))
        expected = independent.get(key)
        if expected is None:
            raise ProductFactError('product_source_triangles_not_independent_rectangle')
        if expected['roi_id'] in aliases.values():
            raise ProductFactError('product_duplicate_source_rectangle')
        aliases[identity] = expected['roi_id']
        if (row['object_index'] != expected['object_index']
                or full[identity]['object_name'] != expected['object_name']
                or row['triangle_count'] != len(expected['source_triangle_indices'])
                or vec(row['center_world_m']) != vec(expected['center_world_m'])
                or not same_normal(row['front_direction_world'], expected['front_direction_world'])):
            raise ProductFactError('product_source_world_description')
        center, u, v = (vec(row[k]) for k in ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m'))
        corners = {tuple(center[k]+a*u[k]+b*v[k] for k in range(3))
                   for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))}
        if corners != set(map(vec, expected['quad_world_m'])) or not same_normal(cross(u, v), expected['front_direction_world']):
            raise ProductFactError('product_source_world_extent')
    return aliases


def evaluate_owner(owner, truth):
    oracle = load_oracle()
    owner = Path(owner).resolve()
    observations = oracle.read(owner / 'OBSERVATIONS.json')
    manifest = oracle.read(HERE / 'inputs/SOURCES.json')
    cameras = oracle.read(manifest['cameras']['path'])
    by_camera = {camera['name']: camera for camera in cameras['views']}
    for name in ('capture', 'scene', 'cameras', 'product_binding'):
        if (observations['source_inputs'][name+'_sha256'] != manifest[name]['sha256']
                or oracle.sha(manifest[name]['path']) != manifest[name]['sha256']):
            raise ValueError('saved_owner_input_binding:' + name)
    for name, expected in truth['input_sha256'].items():
        if manifest[name]['sha256'] != expected:
            raise ValueError('truth_input_binding:' + name)
    attempts = observations['render_attempts']
    if len(attempts) > 6 or len({r['attempt_id'] for r in attempts}) != len(attempts):
        raise ValueError('actual_six_attempt_budget_or_duplicate')
    by_attempt = {r['attempt_id']: r for r in attempts}
    frames = []
    by_ref = {}
    for frame in observations['frames']:
        if frame['ref'] in by_ref or frame['status'] != 'completed':
            raise ValueError('current_frame_ref_or_status')
        if frame['pose'] != by_camera[frame['view_name']]:
            raise ValueError('current_frame_camera_binding')
        attempt = by_attempt[frame['attempt_id']]
        if attempt['ref'] != frame['ref'] or attempt['view_name'] != frame['view_name']:
            raise ValueError('current_frame_attempt_binding')
        times = [attempt.get('intent_ns', attempt.get('started_ns'))] + [
            attempt[k] for k in ('render_started_ns', 'render_closed_ns', 'completed_ns')]
        if (any(type(t) is not int for t in times) or times != sorted(times)
                or not observations['stages'][0]['started_ns'] <= times[0] <= times[-1] < observations['deadline_ns']):
            raise ValueError('current_frame_deadline')
        for path_key, digest_key in (('PNG', 'PNG_sha256'), ('NPZ', 'NPZ_sha256')):
            path = Path(frame[path_key]).resolve()
            if not path.is_relative_to(owner) or oracle.sha(path) != frame[digest_key]:
                raise ValueError('current_frame_artifact_binding')
        measured = oracle.frame_pixels(frame, truth)
        measured['origin'] = frame['origin']
        frames.append(measured)
        by_ref[frame['ref']] = measured
    by_id = {r['roi_id']: r for r in truth['regions']}
    covered = {r['roi_id'] for f in frames for r in f['rows'] if r['complete_readable']}
    result = {'frames': frames, 'by_ref': by_ref, 'product_errors': [], 'aliases': {},
              'public_complete_witnesses': {}, 'independent_covered_roi_ids': sorted(covered),
              'independent_remaining_roi_ids': sorted(set(by_id)-covered),
              'actual_rasters': len(attempts), 'actual_product_calls': len(observations['active']),
              'actual_owner_pid': observations['process_id']}
    if not observations['active']:
        return result
    raw = oracle.read(owner / 'product_call_01/SERVICE_RESULT.json')
    request = oracle.read(owner / 'tool_01/REQUEST.json')
    response = oracle.read(owner / 'tool_01/RESPONSE.json')
    if (request['params']['name'] != 'active_observation'
            or request['params']['arguments'].get('include_images', True) is not True
            or response['result']['isError'] is not False):
        raise ValueError('first_active_images_actual_request')
    public = json.loads(response['result']['content'][0]['text'])
    if public['schema'] != 'active-observation-brief-v4' or raw['binding']['runtime_source_sha256'] != PRODUCT_SHA256:
        raise ValueError('product_candidate_or_public_schema')
    if raw['binding']['camera_specification'] != cameras:
        raise ValueError('product_camera_pool_binding')
    expected_binding = {key: copy.deepcopy(value) for key, value in raw['binding'].items()
                        if key not in ('camera_specification', 'schema', 'objects', 'camera_policy')}
    if isinstance(expected_binding.get('capture_state'), dict):
        expected_binding['capture_state'].pop('selection_key', None)
    if public['binding'] != expected_binding:
        raise ValueError('public_actual_producer_binding')
    regions, pixels, images = (table(public.get(k)) for k in ('regions', 'pixels', 'images'))
    aliases = bind_regions(regions, raw, truth)
    result.update(aliases=aliases, public=public)
    errors = result['product_errors']

    def check(name, passed):
        if not passed:
            errors.append(name)

    support = raw['facts']['scope']['patch_support']
    check('all_triangles_participate_in_occlusion', support['all_triangles_participate_in_occlusion'] is True)
    expected_unsupported = {(r['object_index'], r['source_triangle_index'])
                            for r in truth['unsupported_source_triangles']}
    actual_unsupported = {(obj['object_index'], face) for obj in support['objects']
                          for component in obj['unsupported_components'] for face in component['triangle_indices']}
    check('unsupported_source_remainder', actual_unsupported == expected_unsupported
          and sum(len(obj['unsupported_components']) for obj in support['objects']) == 1)
    all_source_count = len(truth['source_triangle_object_indices'])
    check('complete_source_triangle_partition', sum(o['source_triangle_count'] for o in support['objects']) == all_source_count
          and sum(o['supported_triangle_count'] for o in support['objects'])
          == sum(len(r['source_triangle_indices']) for r in truth['regions'])
          and sum(o['unsupported_triangle_count'] for o in support['objects']) == len(expected_unsupported))

    raw_frames = raw['frames']
    if len(raw_frames) != len(images) or len(pixels) != len(regions)*len(images):
        raise ValueError('public_frame_pixel_cardinality')
    product_frames = []
    product_covered = set()
    for index, (frame, image) in enumerate(zip(raw_frames, images)):
        measured = by_ref.get(frame['image_ref'])
        if measured is None or measured['view_name'] != frame['view_name'] or image['image_ref'] != frame['image_ref']:
            raise ValueError('public_frame_current_reference')
        product_frames.append(measured)
        if oracle.sha(frame['image_path']) != image['image_sha256']:
            raise ValueError('public_image_SHA')
        block = response['result']['content'][image['native_content_block_index']]
        if (block['type'] != 'image' or block['mimeType'] != 'image/png'
                or base64.b64decode(block['data'], validate=True) != Path(frame['image_path']).read_bytes()):
            raise ValueError('public_actual_image_bytes')
        rows = {r['roi_id']: r for r in measured['rows']}
        for region_index, region in enumerate(regions):
            independent = rows[aliases[region['roi_id']]]
            p = pixels[index*len(regions)+region_index]
            if p['image_index'] != index or p['region_index'] != region_index:
                raise ValueError('public_pixel_order')
            check(f'pixel:{index}:{region_index}',
                  (p['visible_surface_pixels'], p['contrasting_boundary_pixels'], p['front_facing'], p['readable'],
                   p['visible_pixel_bounds'], p['visible_pixel_anchor']) ==
                  (independent['surface_pixels'], independent['boundary_pixels'], independent['front_facing'],
                   independent['readable'], independent['bounds'], independent['anchor']))
            if independent['complete_readable']:
                product_covered.add(independent['roi_id'])
    expected_missing = set(by_id)-product_covered
    geometric_missing = {identity for identity, region in by_id.items()
                         if not any(v['complete'] for v in region['views'].values())}
    for key, expected in (('covered_region_indices', product_covered),
                          ('unresolved_region_indices', expected_missing),
                          ('candidate_pool_uncovered_region_indices', geometric_missing)):
        indices = public['coverage'].get(key, [])
        if any(type(i) is not int or not 0 <= i < len(regions) for i in indices):
            raise ValueError('public_coverage_index_domain')
        actual = [aliases[regions[i]['roi_id']] for i in indices]
        check(key, len(set(actual)) == len(actual) and set(actual) == expected)
    observed_names = {f['view_name'] for f in product_frames}
    pending = {identity for identity in expected_missing
               if any(v['complete'] and name not in observed_names for name, v in by_id[identity]['views'].items())}
    counts = public['inspection']['counts']
    check('inspection_counts', counts['supported'] == len(by_id) and counts['covered'] == len(product_covered)
          and counts['unobserved'] == len(expected_missing) and counts['pending_geometric_candidate'] == len(pending))
    check('inspection_stop', not pending or public['inspection']['state'] != 'finite_pool_exhausted')
    for index, region in enumerate(regions):
        identity = aliases[region['roi_id']]
        check('status:' + identity, region['status'] == ('covered' if identity in product_covered else 'unknown'))
        witness = region['complete_witness_pixel_index']
        if identity not in product_covered:
            check('unknown_witness:' + identity, witness is None)
            if identity in pending:
                reason = 'unobserved_geometric_candidates'
            else:
                reason = unknown_reason(by_id[identity], [r for f in product_frames for r in f['rows'] if r['roi_id'] == identity])
            check('unknown_reason:' + identity, region['unobserved_reason'] == reason)
            continue
        if type(witness) is not int or not 0 <= witness < len(pixels):
            errors.append('complete_witness_missing:' + identity)
            continue
        p = pixels[witness]
        f = product_frames[p['image_index']]
        row = next(r for r in f['rows'] if r['roi_id'] == identity)
        valid = p['region_index'] == index and row['complete_readable']
        check('complete_witness:' + identity, valid)
        if valid:
            result['public_complete_witnesses'][identity] = {
                'pixel_index': witness, 'view_name': f['view_name'], 'image_ref': f['image_ref'],
                'surface_pixels': row['surface_pixels'], 'boundary_pixels': row['boundary_pixels']}
    return result


def summary(value):
    return {key: value[key] for key in ('product_errors', 'aliases', 'public_complete_witnesses',
            'independent_covered_roi_ids', 'independent_remaining_roi_ids', 'actual_rasters',
            'actual_product_calls', 'actual_owner_pid')}
