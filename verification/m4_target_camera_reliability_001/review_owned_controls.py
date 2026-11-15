"""Read-only audit of the six already-closed camera reliability controls."""

import argparse
import base64
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
PRIOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe/verification/m4_target_acquisition_001/quality_normalize.py')
PRIOR_SHA = 'ee730439d2a511868c13d15973d7ca825606b5f5a43a2ad1d846e4c5c48f8635'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrix_review(oracle, points, cameras):
    rows = []
    for pose in cameras['views']:
        exact, lower, upper = [], [], []
        for point in points:
            camera, error = oracle.affine_error(pose['view_matrix'], tuple(map(Fraction, point)), (Fraction(0),) * 3)
            projected, error = oracle.affine_error(pose['projection_matrix'], camera, error)
            exact.append(projected)
            lower.append(tuple(value - bound for value, bound in zip(projected, error)))
            upper.append(tuple(value + bound for value, bound in zip(projected, error)))
        rows.append({'name': pose['name'], 'points_checked': len(points),
                     'exact_inside': all(all(-1 <= value <= 1 for value in point) for point in exact),
                     'execution_gamma6_inside': all(all(-1 <= lo and hi <= 1 for lo, hi in zip(a, b)) for a, b in zip(lower, upper)),
                     'exact_max_abs_ndc': [str(max(abs(point[axis]) for point in exact)) for axis in range(3)]})
    return rows


def pixel_metrics(np, color, patches, region_index):
    positions = np.argwhere(patches == region_index)
    if not len(positions):
        return {'visible_surface_pixels': 0, 'contrasting_boundary_pixels': 0,
                'visible_pixel_bounds': None, 'visible_pixel_anchor': None}
    pixels = [(int(x), int(y)) for y, x in positions]
    bounds = [min(x for x, y in pixels), min(y for x, y in pixels),
              max(x for x, y in pixels), max(y for x, y in pixels)]
    anchor = min(pixels, key=lambda point: ((2*point[0]-bounds[0]-bounds[2])**2
                                           + (2*point[1]-bounds[1]-bounds[3])**2, point[1], point[0]))
    boundary = 0
    for x, y in pixels:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < 512 and 0 <= yy < 512 and patches[yy, xx] != region_index:
                if sum((int(color[y, x, c])-int(color[yy, xx, c]))**2 for c in range(3)) >= 24*24:
                    boundary += 1
                    break
    return {'visible_surface_pixels': len(pixels), 'contrasting_boundary_pixels': boundary,
            'visible_pixel_bounds': bounds, 'visible_pixel_anchor': list(anchor)}


def canonical_facts(facts, mapping, frames):
    objects = mapping['objects']
    by_view = {row['view_name']: row for row in frames}

    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        row = copy.deepcopy(value)
        if 'object_index' in row:
            source = objects[row['object_index']]
            for key in ('host_id', 'instance_id', 'object_name'):
                if key in row:
                    assert row[key] == source[key]
            row['object_index'] = source['asset_key']
            if 'instance_id' in row:
                row['instance_id'] = source['asset_key'] + ':current-instance-validated'
        if 'image_ref' in row and 'view_name' in row:
            frame = by_view[row['view_name']]
            for key in ('image_ref', 'image_path', 'image_sha256'):
                assert row[key] == frame[key]
            row['image_ref'] = 'validated-view:' + row['view_name']
            row['image_path'] = 'validated-view:' + row['view_name']
        return {key: visit(item) for key, item in row.items()}

    return visit(facts)


def audit_slot(slot, q, oracle, inputs, np, Image):
    episode = read(slot / 'RESULT.json')
    owner = read(slot / 'OWNER_BINDING.json')
    public = read(slot / 'PUBLIC_01.json')
    response = read(slot / 'RESPONSE_01.json')
    assert episode['passed'] and not episode['errors']
    assert episode['MCP_runtime_exit']['confirmed'] and episode['MCP_runtime_exit']['exited']
    assert episode['MCP_runtime_exit']['exit_code'] == 0
    assert episode['native_close']['process_reaped'] and episode['native_close']['exit_code'] == 0
    build_path = Path(episode['binding_file'])
    build = read(build_path)
    assert sha(build_path) == episode['binding_sha256']
    assert episode['source_sha256'] == build['source_sha256'] == owner['source_proof']['expected_source_sha256']
    assert sha(episode['asset']['asset']) == episode['asset']['asset_sha256'] == owner['asset_manifest']['asset_sha256']
    assert sha(episode['asset']['geometry']) == episode['asset']['geometry_sha256']
    proof = q.validate_source_proof(owner['source_proof'])
    assert proof['source_sha256'] == episode['source_sha256']
    assert json.loads(response['result']['content'][0]['text']) == public
    for number in (2, 4):
        assert read(slot / ('RESPONSE_' + str(number).zfill(2) + '.json'))['result'] == {}
    assert read(slot / 'RESPONSE_03.json')['result']['isError'] is False
    main_rows = [row for row in owner['captures'] if row['role'] == 'main_target_capture']
    readbacks = [row for row in owner['captures'] if row['role'] == 'post_main_source_readback']
    assert len(readbacks) == owner['post_main_readback_count'] == 1
    assert len(main_rows) == owner['main_capture_count']
    for row in owner['captures']:
        assert sha(row['capture']) == row['capture_sha256']
        assert sha(row['wire_request']) == row['wire_request_sha256']
        assert sha(row['wire_response']) == row['wire_response_sha256']
    readback = read(readbacks[0]['capture'])
    assert len(readback['meshes']) == 1
    mesh = readback['meshes'][0]
    asset_target = next(row for row in owner['asset_manifest']['objects'] if row['asset_key'] == owner['asset_manifest']['target_asset_key'])
    assert mesh['object_id'] == asset_target['object_id'] and mesh['name'] == asset_target['object_name']
    assert q._vertex_bytes(mesh['vertices']) == q._vertex_bytes(asset_target['vertices_world'])
    assert mesh['faces'] == asset_target['triangles']
    asset = episode['asset']['name']
    if asset in ('extreme', 'origin'):
        fixed = next(row for row in inputs['camera_cases'] if row['id'] == ('reachable_binary32' if asset == 'extreme' else 'origin_quantized_control'))
        assert q._vertex_bytes(mesh['vertices']) == q._vertex_bytes(fixed['world_vertices'])
        assert mesh['faces'] == fixed['faces']
    pins = [slot / name for name in ('RESULT.json', 'OWNER_BINDING.json', 'PUBLIC_01.json', 'RESPONSE_01.json', 'audit.jsonl')]
    pins.append(build_path)
    pins += [Path(row['capture']) for row in owner['captures']]
    output = {'slot': slot.name, 'variant': episode['variant'], 'asset': asset,
              'source_sha256': proof['source_sha256'], 'loaded_host_sha256': proof['host_source_sha256'],
              'main_capture_count': len(main_rows), 'separate_post_main_readback_count': 1,
              'readback_geometry_matches_frozen_input': True, 'alive_after_main': True,
              'current_source_and_local_face_order_validated': True}
    if not main_rows:
        assert slot.name == 'NEW_extreme'
        assert response['result']['isError'] is True
        assert public['status'] == 'unknown' and public['observation_status'] == 'numeric_insufficient'
        assert public['reason'] == 'active_observation_target_camera_numeric_insufficient'
        assert public['automatic_retry'] is False and public['retry_authorized'] is False
        assert public['host_mutation_started'] is False and public['connector_state_write_commits'] == 0
        assert 'producer_frames' not in episode or episode['producer_frames'] == []
        assert 'frames' not in public and len(response['result']['content']) == 1
        output.update(outcome='explicit_numeric_insufficient', capability_restored=False,
                      main_camera_specification=None, main_fraction_projection=None, main_witness=None,
                      producer_frame_count=0,
                      producer_receipt_field='absent' if 'producer_frames' not in episode else 'present_empty',
                      readback_scope='later task source only, not a main capture or camera')
        output['input_pins'] = [{'path': str(path), 'sha256': sha(path)} for path in pins]
        return output, None
    assert len(main_rows) == 1 and response['result']['isError'] is False
    capture = read(main_rows[0]['capture'])
    assert capture['host_identity']['document_epoch'] == readback['host_identity']['document_epoch']
    assert capture['host_identity']['object_instances'][mesh['object_id']] == readback['host_identity']['object_instances'][mesh['object_id']]
    binding = q.reconstruct_target_binding(capture)
    expected_public_binding = {key: value for key, value in binding.items() if key != 'camera_specification'}
    expected_public_binding.update(runtime_source_sha256=episode['source_sha256'], source_status='loaded_generation',
                                   disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
    assert public['binding'] == expected_public_binding
    mapping = q.validate_object_mapping(capture, binding, owner['asset_manifest'], owner['source_proof'])
    facts = public['facts']
    assert facts['scene_identity'] == binding['geometry_identity'] and facts['candidate_identity'] == binding['camera_identity']
    assert len(facts['regions']) == len(facts['scope']['patch_support']['regions']) == 1
    region = facts['regions'][0]
    declaration = facts['scope']['patch_support']['regions'][0]
    target = mapping['objects'][region['object_index']]
    assert target['asset_key'] == mapping['target_asset_key']
    assert declaration == {'roi_id': region['roi_id'], 'object_index': region['object_index'],
                           'triangle_indices': list(range(target['face_count']))}
    q.validate_region_geometry(region, declaration['triangle_indices'], capture['meshes'][region['object_index']])
    for row, source in zip(facts['scope']['patch_support']['objects'], mapping['objects']):
        assert row['source_triangle_count'] == source['face_count']
        if row['object_index'] != region['object_index']:
            assert row['coverage_role'] == row['support_status'] == 'occluder_only'
            assert row['supported_triangle_count'] == row['unsupported_triangle_count'] == 0
    events = [json.loads(line) for line in (slot / 'audit.jsonl').read_bytes().splitlines() if line]
    observed = [row for row in events if row.get('event') == 'observe' and row.get('observation_mode') == 'active_observation']
    assert len(observed) == 1 and observed[0]['target_view_classifications'] == public['target_view_classifications']
    classes = public['target_view_classifications']
    roi = region['roi_id']
    matrices = matrix_review(oracle, capture['meshes'][region['object_index']]['vertices'], binding['camera_specification'])
    if asset == 'extreme':
        assert slot.name == 'OLD_extreme'
        assert classes['LEFT'][roi]['status'] == 'outside_frustum'
        assert next(row for row in matrices if row['name'] == 'LEFT')['exact_inside'] is False
    else:
        assert all(row['exact_inside'] and row['execution_gamma6_inside'] for row in matrices)
    if asset == 'peripheral':
        near = next(row for row in capture['meshes'] if row['name'] == 'M4_Near')
        d = Fraction(near['vertices'][0][0])
        triangle = tuple(tuple(Fraction(value) for value in near['vertices'][index]) for index in near['faces'][0])
        key = min(triangle[index:] + triangle[:index] for index in range(3))
        blocker = classes['LEFT'][roi]['first_blocker']
        assert blocker['triangle_geometry_id'] == q.fingerprint(key)
        assert Fraction(blocker['overlap_area_screen_exact']) == d*d/2 == Fraction(inputs['negative_regression']['exact_Near_shadow_area'])
        assert facts['inspection']['counts']['covered'] == 0
        assert facts['region_evidence'][0]['complete_witness'] is None
    if asset == 'origin':
        assert classes['LEFT'][roi]['complete'] is True
        assert facts['inspection']['counts']['covered'] == 1
        assert facts['region_evidence'][0]['complete_witness'] == {'pixel_row_index': 0, 'view_name': 'LEFT'}
    frame_arrays, frame_reviews = [], []
    offsets = [0]
    expected_face_ids = []
    ordered_geometry = []
    for index, source in enumerate(capture['meshes']):
        ordered_geometry.append((tuple(tuple(Fraction(value) for value in point) for point in source['vertices']),
                                 tuple(tuple(face) for face in source['faces'])))
        expected_face_ids.append([0 if index == region['object_index'] else -1 for _ in source['faces']])
        offsets.append(offsets[-1] + len(source['faces']))
    patch_id = q.fingerprint({'version': 'active-patch-owner-v1', 'roi_ids': (roi,),
                              'ordered_geometry': ordered_geometry, 'face_patch_ids': expected_face_ids})
    flat_patch_ids = [value for row in expected_face_ids for value in row]
    assert len(public['frames']) == len(facts['observations']) == len(response['result']['content']) - 1
    for index, (frame, observation) in enumerate(zip(public['frames'], facts['observations'])):
        assert frame['patch_mapping_identity'] == patch_id
        assert frame['patch_roi_ids'] == [roi]
        assert sha(frame['image_path']) == frame['image_sha256']
        assert sha(frame['arrays_path']) == frame['arrays_sha256']
        delivered = base64.b64decode(response['result']['content'][index + 1]['data'], validate=True)
        assert delivered == Path(frame['image_path']).read_bytes()
        normalized = q.saved_frame_arrays(frame['arrays_path'], frame['arrays_sha256'], mapping, frame)
        with np.load(frame['arrays_path'], allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        assert arrays['face_patch_ids'].tolist() == flat_patch_ids
        assert arrays['face_patch_offsets'].tolist() == offsets
        expected_owners = np.full(arrays['owners'].shape, -1, dtype=np.int32)
        foreground = arrays['owners'] >= 0
        expected_owners[foreground] = np.asarray(flat_patch_ids, dtype=np.int32)[arrays['triangle_ids'][foreground]]
        assert np.array_equal(expected_owners, arrays['patch_owners'])
        with Image.open(frame['image_path']) as png:
            png.load()
            assert png.mode == 'RGB' and png.size == (512, 512)
            assert np.array_equal(np.asarray(png), arrays['color'])
        assert observation['image_ref'] == frame['image_ref'] and observation['image_sha256'] == frame['image_sha256']
        assert len(observation['pixel_rows']) == 1
        pixel = observation['pixel_rows'][0]
        metrics = pixel_metrics(np, arrays['color'], arrays['patch_owners'], 0)
        assert all(pixel[key] == value for key, value in metrics.items())
        direction = next(pose['direction_rational'] for pose in binding['camera_specification']['views'] if pose['name'] == frame['view_name'])
        front = sum(Fraction(value)*axis for value, axis in zip(region['front_direction_world'], direction)) > 0
        readable = front and metrics['visible_surface_pixels'] >= 16 and metrics['contrasting_boundary_pixels'] >= 4
        assert pixel['front_facing'] is front and pixel['readable'] is readable
        assert pixel['minimum_surface_pixels'] == 16 and pixel['minimum_boundary_pixels'] == 4
        assert pixel['minimum_rgb_boundary_contrast'] == 24
        frame_reviews.append({'view_name': frame['view_name'], 'producer_NPZ_sha256': frame['arrays_sha256'],
                              'PNG_sha256': frame['image_sha256'], 'producer_hashes_matched_current_files': True,
                              **metrics, 'front_facing': front, 'readable': readable})
        normalized['patch_owners'] = arrays['patch_owners']
        frame_arrays.append(normalized)
        pins += [Path(frame['image_path']), Path(frame['arrays_path'])]
    output.update(outcome='actual_complete_witness' if asset == 'origin' else 'actual_geometry_unknown',
                  source_binding_sha256=binding['source_binding_sha256'], binding_sha256=binding['binding_sha256'],
                  target_faces=target['face_count'], main_camera_specification=binding['camera_specification'],
                  main_fraction_projection=matrices, actual_classifications=classes,
                  main_witness=facts['region_evidence'][0]['complete_witness'],
                  actual_inspection=facts['inspection'], remaining_unknown=facts['region_evidence'][0]['unobserved_reason'],
                  producer_frame_count=len(frame_reviews), frame_reviews=frame_reviews)
    output['input_pins'] = [{'path': str(path), 'sha256': sha(path)} for path in pins]
    comparable = {'facts': canonical_facts(facts, mapping, public['frames']),
                  'classifications': classes, 'cameras': binding['camera_specification'],
                  'arrays': frame_arrays, 'views': [row['view_name'] for row in public['frames']]}
    return output, comparable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert sha(PRIOR) == PRIOR_SHA
    q = load(PRIOR, '_accepted_saved_quality_primitives')
    oracle = load(HERE / 'camera_numeric.py', '_frozen_matrix_quality_oracle')
    inputs = read(HERE / 'INPUTS.json')
    assert sha(HERE / 'INPUTS.json') == read(HERE / 'INPUT_FREEZE.json')['inputs_sha256']
    sys.path.insert(0, read(HERE / 'build/RUN_BINDING.json')['dependency_root'])
    import numpy as np
    from PIL import Image
    records, comparable = [], {}
    for asset in ('extreme', 'origin', 'peripheral'):
        for variant in ('OLD', 'NEW'):
            name = variant + '_' + asset
            result, values = audit_slot(args.controls / name, q, oracle, inputs, np, Image)
            records.append(result)
            comparable[name] = values
    pairs = []
    for asset in ('origin', 'peripheral'):
        old, new = comparable['OLD_' + asset], comparable['NEW_' + asset]
        assert old['facts'] == new['facts']
        assert old['classifications'] == new['classifications']
        assert old['cameras'] == new['cameras']
        assert old['views'] == new['views']
        buffers = []
        for left, right in zip(old['arrays'], new['arrays']):
            arrays = q.compare_normalized_buffers(left, right)
            assert arrays['equal'] and np.array_equal(left['patch_owners'], right['patch_owners'])
            buffers.append(arrays)
        pairs.append({'asset': asset, 'all_target_facts_equal_after_current_source_validation': True,
                      'all_six_classifications_equal': True, 'actual_camera_specifications_equal': True,
                      'actual_view_sequence': old['views'], 'normalized_buffers': buffers,
                      'patch_owners_equal': True})
    numeric = read(HERE / 'CANDIDATE_NUMERIC_SOURCE_01.json')
    installed = read(HERE / 'CANDIDATE_NUMERIC_INSTALLED_01.json')
    micro = read(HERE / 'MICRO_CAMERA_01.json')
    replay = read(HERE / 'PRIOR_384_REPLAY_01.json')
    assert numeric['passed'] and installed['passed'] and replay['passed_checked_scope']
    assert numeric['source_sha256'] == installed['source_sha256'] == micro['source_sha256']['new']
    report = {
        'schema': 'target-camera-reliability-actual-review-v1', 'passed_checked_scope': True,
        'inputs_sha256': sha(HERE / 'INPUTS.json'), 'input_freeze_sha256': sha(HERE / 'INPUT_FREEZE.json'),
        'actual_slots': records, 'ordinary_and_negative_pairs': pairs,
        'extreme_resolution': {'old': 'actual final LEFT matrix clips target, outside_frustum and no witness',
                               'new': 'explicit numeric_insufficient, no main capture/matrix/producer image/witness',
                               'capability_restored': False, 'separate_readback_matches_original_binary32_source': True},
        'pure_checks': {'unique_frozen_camera_cases': 6, 'source_execution_cases': 6, 'installed_execution_cases': 6,
                         'new_source_sha256': numeric['source_sha256'],
                         'results': [{'id': row['id'], 'outcome': row['outcome']} for row in numeric['records']]},
        'legacy_384_replay': replay['counts'],
        'legacy_replay_interpretation': 'Old exact XY clipping is 14. The 67 gamma6 failures are inability to certify execution enclosure, not 67 observed clipping errors. New 273 accepted fits and 111 explicit numeric rejections remain separate.',
        'microbenchmark': {'timed_calls': micro['timed_calls'], 'warmup_calls': micro['warmup_calls'],
                            'closed_ns': micro['closed_ns'], 'paired_results': micro['summaries'],
                            'not_task_or_MCP_benefit': True},
        'observed_producer_frames': sum(row['producer_frame_count'] for row in records),
        'limitations': ['Extreme geometry was not restored to a complete readable witness.',
                        'Saved owner/depth buffers were checked and compared, not independently rerasterized.',
                        'Fresh runtime identities were validated within each slot before asset-key normalization.',
                        'Only the three predeclared real inputs and six closed slots were audited.',
                        'No B implementation, extra model consumer or new performance task was introduced.'],
        'reference_primitive_sha256': PRIOR_SHA, 'review_source_sha256': sha(Path(__file__)),
        'evidence_pins': [{'path': str(HERE / name), 'sha256': sha(HERE / name)} for name in
                          ('INPUTS.json', 'INPUT_FREEZE.json', 'OLD_REPRO.json', 'CANDIDATE_NUMERIC_SOURCE_01.json',
                           'CANDIDATE_NUMERIC_INSTALLED_01.json', 'PRIOR_384_REPLAY_01.json', 'MICRO_CAMERA_01.json')],
        'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0,
    }
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'actual_slots': len(records),
                      'producer_frames': report['observed_producer_frames'], 'extreme_capability_restored': False,
                      'normal_and_negative_pair_buffers_equal': True, 'new_rasters': 0}))


if __name__ == '__main__':
    main()
