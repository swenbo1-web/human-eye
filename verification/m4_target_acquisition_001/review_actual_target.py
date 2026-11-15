"""Independently inspect one saved A peripheral episode without observing it.

This bounded reviewer reads the already produced capture, source bootstrap,
audit, public response, PNG and NPZ.  It performs scalar source/occlusion and
saved-pixel checks and never invokes product observation or raster functions.
"""

import argparse
import base64
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_affine(matrix, point):
    return tuple(sum(Fraction(matrix[row][axis]) * point[axis] for axis in range(3))
                 + Fraction(matrix[row][3]) for row in range(3))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    slot = args.slot.resolve()
    spec = importlib.util.spec_from_file_location('_actual_saved_target_quality', HERE / 'quality_normalize.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    capture = read_json(slot / 'CAPTURE_01.json')
    public = read_json(slot / 'PUBLIC_01.json')
    owner = read_json(slot / 'OWNER_BINDING.json')
    episode = read_json(slot / 'RESULT.json')
    build_path = Path(episode['binding_file'])
    build = read_json(build_path)
    assert sha(build_path) == episode['binding_sha256']
    assert build['build_id'] == 'sha256:' + owner['source_proof']['expected_source_sha256']
    assert episode['source_sha256'] == owner['source_proof']['expected_source_sha256']
    host_row = next(row for row in build['source_manifest'] if row['path'] == 'human_eye_plugin/blender_host.py')
    assert host_row['sha256'] == owner['source_proof']['expected_host_source_sha256']
    assert episode['asset']['name'] == 'peripheral' and episode['asset']['target'] == 'M4_Far_00'
    binding = adapter.reconstruct_target_binding(capture)
    mapping = adapter.validate_object_mapping(capture, binding, owner['asset_manifest'], owner['source_proof'])
    adapter.validate_public_binding(public, binding, mapping)
    events = [json.loads(line) for line in (slot / 'audit.jsonl').read_bytes().splitlines() if line]
    actual_events = [row for row in events if row.get('event') == 'observe'
                     and row.get('observation_mode') == 'active_observation'
                     and 'target_view_classifications' in row]
    assert len(actual_events) == 1
    event = actual_events[0]
    assert event['identity_check']['actual']['source_sha256'] == episode['source_sha256']
    classifications = event['target_view_classifications']
    regions = adapter.table(public['regions'])
    assert len(regions) == 1
    region = regions[0]
    roi = region['roi_id']
    assert region['triangle_count'] == 512 and region['source_triangle_index_ranges'] == [[0, 511]]
    target_mesh = capture['meshes'][region['object_index']]
    assert target_mesh['name'] == 'M4_Far_00'
    adapter.validate_region_geometry(region, list(range(512)), target_mesh)

    # Independent special-case geometry follows directly from the frozen raw
    # coordinates.  No production clipping, index or region finder is called.
    assert all(Fraction(point[0]) == 1 for point in target_mesh['vertices'])
    assert [min(Fraction(point[k]) for point in target_mesh['vertices']) for k in (1, 2)] == [0, 0]
    assert [max(Fraction(point[k]) for point in target_mesh['vertices']) for k in (1, 2)] == [1, 1]
    assert region['front_direction_world'] == [-1, 0, 0]
    near = next(mesh for mesh in capture['meshes'] if mesh['name'] == 'M4_Near')
    focal = next(mesh for mesh in capture['meshes'] if mesh['name'] == 'M4_Focal')
    assert near['faces'] == focal['faces'] == [[0, 1, 2]]
    d = Fraction(near['vertices'][0][0])
    assert 0 < d < 1
    assert [tuple(Fraction(value) for value in point) for point in near['vertices']] == [
        (d, 0, 0), (d, 1, 0), (d, 0, 1)]
    assert [tuple(Fraction(value) for value in point) for point in focal['vertices']] == [
        (0, 0, 0), (0, 1, 0), (0, 0, 1)]
    triangle = tuple(tuple(Fraction(value) for value in near['vertices'][index]) for index in near['faces'][0])
    key = min(triangle[index:] + triangle[:index] for index in range(3))
    blocker_hash = adapter.fingerprint(key)
    area = d * d / 2
    expected_statuses = {'SCENE': 'back_facing', 'TOP': 'edge_on', 'LEFT': 'positive_area_occlusion',
                         'RIGHT': 'back_facing', 'FRONT': 'edge_on', 'BACK': 'edge_on'}
    for name, direction in zip(adapter.VIEW_ORDER, adapter.DIRECTIONS):
        facing = sum(Fraction(value) * axis for value, axis in zip(region['front_direction_world'], direction))
        assert expected_statuses[name] == ('back_facing' if facing < 0 else 'edge_on' if facing == 0 else 'positive_area_occlusion')
        row = classifications[name][roi]
        assert row['status'] == expected_statuses[name] and row['complete'] is False
    blocker = classifications['LEFT'][roi]['first_blocker']
    assert blocker['triangle_geometry_id'] == blocker_hash
    assert Fraction(blocker['overlap_area_screen_exact']) == area
    left = next(pose for pose in binding['camera_specification']['views'] if pose['name'] == 'LEFT')
    for y in (Fraction(0), Fraction(1)):
        for z in (Fraction(0), Fraction(1)):
            camera = exact_affine(left['view_matrix'], (Fraction(1), y, z))
            ndc = exact_affine(left['projection_matrix'], camera)
            assert all(-1 <= value <= 1 for value in ndc)
            assert Fraction(left['near']) < -camera[2] < Fraction(left['far'])

    sys.path.insert(0, build['dependency_root'])
    import numpy as np
    from PIL import Image

    response = read_json(slot / 'RESPONSE_01.json')
    content = response['result']['content']
    assert json.loads(content[0]['text']) == public
    delivered_images = adapter.table(public['images'])
    assert len(delivered_images) == 1 and delivered_images[0]['view_name'] == 'SCENE'
    image_row = delivered_images[0]
    png_bytes = base64.b64decode(content[image_row['native_content_block_index']]['data'], validate=True)
    assert hashlib.sha256(png_bytes).hexdigest() == image_row['image_sha256']
    candidates = list((slot / 'state.json.active_observation').rglob('*.png'))
    matching = [path for path in candidates if path.read_bytes() == png_bytes]
    assert len(matching) == 1
    png_path = matching[0]
    array_path = png_path.with_suffix('.npz')
    assert png_path.parent.name == binding['binding_sha256']
    with np.load(array_path, allow_pickle=False) as arrays:
        arrays = {name: arrays[name] for name in arrays.files}
    frame = {name: arrays[name].item() for name in
             ('owner_schema', 'owner_mapping_identity', 'triangle_id_scope',
              'patch_mapping_version', 'patch_mapping_identity')}
    frame.update(scene_identity=binding['geometry_identity'], candidate_identity=binding['camera_identity'],
                 host_binding_sha256=binding['binding_sha256'], source_revision=binding['scene_revision'],
                 view_name=image_row['view_name'], image_ref=image_row['image_ref'],
                 image_sha256=image_row['image_sha256'], patch_roi_ids=arrays['patch_roi_ids'].tolist(),
                 arrays_sha256=sha(array_path))
    core_binding = (binding['geometry_identity'], binding['camera_identity'])
    sequence = int(png_path.stem.split('-', 1)[0])
    assert png_path.stem == str(sequence).zfill(3) + '-' + adapter.fingerprint(
        (core_binding, frame['owner_mapping_identity'], frame['view_name']))[:24]
    frame_identity = adapter.fingerprint((core_binding, frame['owner_schema'], frame['owner_mapping_identity'],
                                          frame['view_name'], sequence, frame['image_sha256']))
    reference = (binding['binding_sha256'], frame['view_name'], frame['image_sha256'],
                 frame['patch_mapping_identity'], frame['owner_schema'], frame['owner_mapping_identity'], frame_identity)
    assert frame['image_ref'] == 'active-host-image:' + adapter.fingerprint(reference)

    offsets = [0]
    face_ids = []
    ordered_geometry = []
    for index, mesh in enumerate(capture['meshes']):
        vertices = tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices'])
        faces = tuple(tuple(face) for face in mesh['faces'])
        ordered_geometry.append((vertices, faces))
        face_ids.append([0 if index == region['object_index'] else -1 for _ in faces])
        offsets.append(offsets[-1] + len(faces))
    expected_patch = adapter.fingerprint({'version': 'active-patch-owner-v1', 'roi_ids': (roi,),
                                           'ordered_geometry': ordered_geometry, 'face_patch_ids': face_ids})
    assert expected_patch == frame['patch_mapping_identity'] == image_row['patch_mapping_identity']
    assert arrays['face_patch_offsets'].tolist() == offsets
    flat_ids = [value for object_ids in face_ids for value in object_ids]
    assert arrays['face_patch_ids'].tolist() == flat_ids
    assert frame['patch_roi_ids'] == [roi]
    assert frame['owner_mapping_identity'] == adapter.fingerprint((frame['owner_schema'], frame['triangle_id_scope'], expected_patch, offsets))
    normalized_arrays = adapter.saved_frame_arrays(array_path, sha(array_path), mapping, frame)
    expected_patches = np.full(arrays['owners'].shape, -1, dtype=np.int32)
    foreground = arrays['owners'] >= 0
    expected_patches[foreground] = np.asarray(flat_ids, dtype=np.int32)[arrays['triangle_ids'][foreground]]
    assert np.array_equal(expected_patches, arrays['patch_owners'])
    with Image.open(png_path) as actual_png:
        actual_png.load()
        assert actual_png.mode == 'RGB' and actual_png.size == (512, 512)
        assert np.array_equal(np.asarray(actual_png), arrays['color'])

    pixels = []
    patches = arrays['patch_owners']
    color = arrays['color']
    for y, x in np.argwhere(patches == 0):
        pixels.append((int(x), int(y)))
    bounds = [min(x for x, y in pixels), min(y for x, y in pixels),
              max(x for x, y in pixels), max(y for x, y in pixels)]
    anchor = min(pixels, key=lambda point: ((2*point[0]-bounds[0]-bounds[2])**2
                                           + (2*point[1]-bounds[1]-bounds[3])**2, point[1], point[0]))
    boundary = 0
    for x, y in pixels:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < 512 and 0 <= yy < 512 and patches[yy, xx] != 0:
                squared = sum((int(color[y, x, channel])-int(color[yy, xx, channel]))**2 for channel in range(3))
                if squared >= 24*24:
                    boundary += 1
                    break
    pixel = adapter.table(public['pixels'])[0]
    assert pixel['visible_surface_pixels'] == len(pixels)
    assert pixel['contrasting_boundary_pixels'] == boundary
    assert pixel['visible_pixel_bounds'] == bounds and pixel['visible_pixel_anchor'] == list(anchor)
    assert pixel['front_facing'] is False and pixel['readable'] is False
    assert public['pixel_rules'] == {'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4,
                                     'minimum_rgb_boundary_contrast': 24}
    normalized = adapter.normalize_public_target(public, capture, binding, mapping, classifications, [normalized_arrays])
    assert region['complete_witness_pixel_index'] is None
    assert region['status'] == 'unknown' and region['unobserved_reason'] == 'positive_area_occlusion_all_front_views'
    assert public['inspection']['counts']['covered'] == 0
    assert public['inspection']['counts']['no_geometric_complete_candidate'] == 1
    assert public['coverage']['observed_views'] == ['SCENE']

    pins = [slot / filename for filename in ('CAPTURE_01.json', 'PUBLIC_01.json', 'OWNER_BINDING.json',
                                              'RESULT.json', 'RESPONSE_01.json', 'audit.jsonl')]
    pins += [build_path, png_path, array_path]
    report = {
        'schema': 'm4-target-actual-A-independent-review-v1', 'slot': str(slot), 'passed_checked_scope': True,
        'current_source': {'installed_source_sha256': episode['source_sha256'],
                           'loaded_host_sha256': owner['source_proof']['actual_loaded_host_sha256'],
                           'independent_reconstructed_source_binding_sha256': binding['source_binding_sha256'],
                           'independent_reconstructed_binding_sha256': binding['binding_sha256'],
                           'objects_validated': len(mapping['objects']), 'target_source_faces': 512,
                           'wire_material': mapping['source']['verified_material']},
        'actual_classifications': classifications, 'independent_expected_statuses': expected_statuses,
        'all_six_complete_flags_expected_false': True,
        'analytic_blocker': {'object_name': 'M4_Near', 'triangle_geometry_id': blocker_hash,
                             'plane_x_exact': str(d), 'target_plane_x': 1,
                             'target_patch': '0 <= y <= 1, 0 <= z <= 1, front=-X',
                             'LEFT_ray': '(1,y,z)+t*(-1,0,1), t=1-d at blocker plane',
                             'shadow_region': 'y >= 0, z >= 0, y+z <= d',
                             'exact_positive_area': str(area), 'actual_reported_area': blocker['overlap_area_screen_exact'],
                             'M4_Focal_at_x0': 'y+z <= 0 gives boundary contact only, zero positive area',
                             'LEFT_target_inside_actual_frustum': True},
        'saved_buffers': {'image_reference_reconstructed_and_matched': True,
                          'NPZ_patch_and_owner_mapping_reconstructed_and_matched': True,
                          'RGB_matches_actual_MCP_PNG': True,
                          'actual_owner_and_local_triangle_bounds_validated': True,
                          'visible_surface_pixels': len(pixels), 'contrasting_boundary_pixels': boundary,
                          'visible_pixel_bounds': bounds, 'visible_pixel_anchor': list(anchor),
                          'actual_view': 'SCENE', 'front_facing': False, 'readable': False,
                          'metadata_provenance': 'Current raw capture, saved NPZ metadata, sibling PNG bytes and delivered image_ref were independently cross-bound. No full-result frame dict or original NPZ hash was delivered in brief.',
                          'NPZ_current_sha256': sha(array_path)},
        'target_outcome': {'inspection_state': public['inspection']['state'],
                           'stop_reason': public['inspection']['stop_reason'], 'covered': 0,
                           'complete_witness': None, 'remaining_unknown': region['unobserved_reason'],
                           'new_capability_realized': False, 'candidate_disposition': 'not_realized',
                           'B_and_formal_status': 'not_run_by_predeclared_input_gate'},
        'planning_limitation': 'Input preflight did not establish an unobstructed complete witness in the fixed six directions before freezing the target. The existing Near triangle already creates a strictly positive-area shadow in the only front view.',
        'review_limitations': ['The result applies to this fixed engineering input and the existing strict complete-witness contract.',
                               'Saved pixels were checked, not regenerated. This is not an independent reraster of every pixel.',
                               'B was not implemented or measured, so this is not an optimization performance failure.',
                               'No other control scenes, changed layouts or camera strategies were run by this reviewer.'],
        'normalized_public_comparison_sha256': adapter.fingerprint(normalized['comparison']),
        'input_pins': [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in pins],
        'reviewer_source_sha256': sha(Path(__file__)), 'normalizer_sha256': sha(HERE / 'quality_normalize.py'),
        'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0,
    }
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'source_bound_objects': len(mapping['objects']),
                      'target_faces': 512, 'blocker_hash': blocker_hash, 'exact_area': str(area),
                      'target_disposition': 'not_realized', 'new_rasters': 0}))


if __name__ == '__main__':
    main()
