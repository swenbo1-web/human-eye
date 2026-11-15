"""Source-bound saved full-result qualification for the two frozen inputs.

This checker reads actual producer records and arrays. It never observes a
scene, constructs an image, or invokes a renderer.
"""

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
PRIOR_BASE = Path('C:/Users/Administrator/.codex/worktrees')
Q_PATH = PRIOR_BASE / 'm4-target-001/hefe/verification/m4_target_acquisition_001/quality_normalize.py'
Q_SHA = 'ee730439d2a511868c13d15973d7ca825606b5f5a43a2ad1d846e4c5c48f8635'
PREVIOUS = PRIOR_BASE / 'm4-camera-001/hefe/verification/m4_target_camera_reliability_001'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dependencies():
    assert sha(Q_PATH) == Q_SHA
    delivery = read(PREVIOUS / 'SCORING_DELIVERY.json')
    prior_path = PREVIOUS / 'review_owned_controls.py'
    assert sha(prior_path) == next(row['sha256'] for row in delivery['files'] if Path(row['path']).name == prior_path.name)
    return load(Q_PATH, '_target002_saved_primitives'), load(prior_path, '_target002_saved_metrics')


def decode_capture(pin, cache):
    response = read(pin['wire_response'])
    assert sha(pin['wire_response']) == pin['wire_response_sha256']
    assert sha(pin['wire_request']) == pin['wire_request_sha256']
    lines = [line for line in response['result']['result'].splitlines() if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
    assert len(lines) == 1
    packet = json.loads(lines[0].split(':', 1)[1])['result']
    for resource in packet.get('resources', []):
        cache[(resource['id'], resource['revision'])] = resource
    capture = copy.deepcopy(packet.get('capture', packet))
    for mesh in capture['meshes']:
        ref = mesh.pop('_scene_resource', None)
        if ref is None:
            continue
        resource = cache[(ref['id'], ref['revision'])]
        matrix, scale = ref['matrix'], ref['scale']
        mesh.update(vertices=[[(sum(matrix[r][k]*point[k] for k in range(3))+matrix[r][3])*scale
                               for r in range(3)] for point in resource['vertices_local']],
                    faces=resource['faces'], edges=resource['edges'])
    assert capture == read(pin['capture'])
    assert sha(pin['capture']) == pin['capture_sha256']
    return capture


def check_frame(frame, observation, response_image, capture, mapping, region_sources, q, metrics, np, Image):
    assert sha(frame['arrays_path']) == frame['arrays_sha256']
    assert sha(frame['image_path']) == frame['image_sha256']
    assert base64.b64decode(response_image['data'], validate=True) == Path(frame['image_path']).read_bytes()
    normalized = q.saved_frame_arrays(frame['arrays_path'], frame['arrays_sha256'], mapping, frame)
    with np.load(frame['arrays_path'], allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    with Image.open(frame['image_path']) as png:
        png.load()
        assert png.mode == 'RGB' and png.size == (512, 512)
        assert np.array_equal(np.asarray(png), arrays['color'])
    roi_ids = frame['patch_roi_ids']
    assert roi_ids == sorted(region_sources)
    face_ids = [[-1]*len(mesh['faces']) for mesh in capture['meshes']]
    for index, roi in enumerate(roi_ids):
        source = region_sources[roi]
        for face in source['triangle_indices']:
            assert face_ids[source['object_index']][face] == -1
            face_ids[source['object_index']][face] = index
    geometry = [(tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices']),
                 tuple(tuple(face) for face in mesh['faces'])) for mesh in capture['meshes']]
    expected_patch = q.fingerprint({'version': 'active-patch-owner-v1', 'roi_ids': tuple(roi_ids),
                                    'ordered_geometry': geometry, 'face_patch_ids': face_ids})
    assert frame['patch_mapping_identity'] == expected_patch
    flat_ids = [value for row in face_ids for value in row]
    assert arrays['face_patch_ids'].tolist() == flat_ids
    offsets = arrays['face_patch_offsets'].tolist()
    expected_owner = q.fingerprint((frame['owner_schema'], frame['triangle_id_scope'], expected_patch, offsets))
    assert frame['owner_mapping_identity'] == expected_owner
    object_keys = []
    for vertices, faces in geometry:
        triangles = []
        for face in faces:
            points = tuple(vertices[index] for index in face)
            triangles.append(min(points[index:] + points[:index] for index in range(3)))
        object_keys.append((tuple(sorted(vertices)), tuple(sorted(triangles))))
    assert frame['mesh_order_identity'] == q.fingerprint(tuple(object_keys))
    sequence = int(Path(frame['image_path']).stem.split('-', 1)[0])
    core_binding = (frame['scene_identity'], frame['candidate_identity'])
    assert frame['frame_identity'] == q.fingerprint((core_binding, frame['owner_schema'], expected_owner,
        frame['view_name'], sequence, frame['image_sha256']))
    assert frame['image_ref'] == 'active-host-image:' + q.fingerprint((frame['host_binding_sha256'], frame['view_name'],
        frame['image_sha256'], expected_patch, frame['owner_schema'], expected_owner, frame['frame_identity']))
    expected_owners = np.full(arrays['owners'].shape, -1, dtype=np.int32)
    fg = arrays['owners'] >= 0
    expected_owners[fg] = np.asarray(flat_ids, dtype=np.int32)[arrays['triangle_ids'][fg]]
    assert np.array_equal(expected_owners, arrays['patch_owners'])
    for key in ('view_name', 'image_ref', 'image_path', 'image_sha256'):
        assert observation[key] == frame[key]
    assert {row['roi_id'] for row in observation['pixel_rows']} == set(roi_ids)
    pixel_rows = []
    for row in observation['pixel_rows']:
        region_index = roi_ids.index(row['roi_id'])
        measured = metrics.pixel_metrics(np, arrays['color'], arrays['patch_owners'], region_index)
        assert all(row[key] == value for key, value in measured.items())
        assert row['minimum_surface_pixels'] == 16 and row['minimum_boundary_pixels'] == 4
        assert row['minimum_rgb_boundary_contrast'] == 24
        front = row['front_facing']
        assert row['readable'] is (front and measured['visible_surface_pixels'] >= 16 and measured['contrasting_boundary_pixels'] >= 4)
        pixel_rows.append({'roi_id': row['roi_id'], **measured, 'front_facing': front, 'readable': row['readable']})
    normalized['patch_owners'] = arrays['patch_owners']
    return {'view': frame['view_name'], 'producer_NPZ_sha256': frame['arrays_sha256'],
            'producer_PNG_sha256': frame['image_sha256'], 'identity_chain_checked': True,
            'pixels': pixel_rows}, normalized


def audit_slot(slot, scene_kind, expected_source=None):
    q, metrics = dependencies()
    result = read(slot / 'RESULT.json')
    public = read(slot / 'PUBLIC_01.json')
    response = read(slot / 'RESPONSE_01.json')
    owner = read(slot / 'OWNER_BINDING.json')
    assert result['passed'] and not result['errors']
    assert sha(result['binding_file']) == result['binding_sha256']
    build = read(result['binding_file'])
    assert result['source_sha256'] == build['source_sha256']
    if expected_source is not None:
        assert result['source_sha256'] == expected_source
    assert q.validate_source_proof(owner['source_proof'])['source_sha256'] == result['source_sha256']
    assert sha(result['asset']['asset']) == result['asset']['asset_sha256']
    assert sha(result['asset']['geometry']) == result['asset']['geometry_sha256']
    cache = {}
    decoded = [(pin, decode_capture(pin, cache)) for pin in owner['captures']]
    main = [(pin, capture) for pin, capture in decoded if pin['role'] == 'main_target_capture']
    assert len(main) == owner['main_capture_count'] == 1
    pin, capture = main[0]
    binding = q.reconstruct_target_binding(capture)
    expected_binding = {key: value for key, value in binding.items() if key != 'camera_specification'}
    expected_binding.update(runtime_source_sha256=result['source_sha256'], source_status='loaded_generation',
                            disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
    assert public['binding'] == expected_binding
    mapping = q.validate_object_mapping(capture, binding, owner['asset_manifest'], owner['source_proof'])
    assert response['result']['isError'] is False and json.loads(response['result']['content'][0]['text']) == public
    request = read(slot / 'REQUEST_01.json')['params']['arguments']
    assert request['query'] == {'mode': 'active_observation', 'objects': [{'name': 'M4_Far_00'}]}
    assert request['include_image'] is True and request['response_detail'] == 'full'
    frozen = read(HERE / 'reference/FROZEN_GEOMETRY.json')
    assert sha(HERE / 'reference/FROZEN_GEOMETRY.json') == 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da'
    by_name = {row['name']: row for row in frozen['objects']}
    for mesh in capture['meshes']:
        expected = by_name[mesh['name']]
        assert mesh['vertices'] == [[float(Fraction(value)) for value in point] for point in expected['world_vertices_m']]
        assert mesh['faces'] == expected['triangles']
    facts = public['facts']
    sources = {row['roi_id']: row for row in facts['scope']['patch_support']['regions']}
    assert len(facts['regions']) == len(sources) == 2
    kinds = {}
    for region in facts['regions']:
        source = sources[region['roi_id']]
        faces = source['triangle_indices']
        kind = 'vertical' if faces == list(range(512)) else 'horizontal' if faces == [512, 513] else None
        assert kind is not None and kind not in kinds.values()
        kinds[region['roi_id']] = kind
        q.validate_region_geometry(region, faces, capture['meshes'][region['object_index']])
        assert region['front_direction_world'] == ([-1, 0, 0] if kind == 'vertical' else [0, 0, 1])
    oracle = read(HERE / 'ANALYTIC_REVIEW.json')
    classes = public['target_view_classifications']
    for roi, kind in kinds.items():
        expected = oracle['horizontal_main_geometric_classifications'] if kind == 'horizontal' else oracle[
            'vertical_main_geometric_classifications' if scene_kind == 'main' else 'vertical_target_only_geometric_classifications']
        for view, status in expected.items():
            assert classes[view][roi]['status'] == status
            assert classes[view][roi]['complete'] is (status == 'complete')
    if scene_kind == 'main':
        vertical = next(roi for roi, kind in kinds.items() if kind == 'vertical')
        assert Fraction(classes['LEFT'][vertical]['first_blocker']['overlap_area_screen_exact']) == Fraction(oracle['near_shadow']['area_exact'])
    target = next(row for row in capture['meshes'] if row['name'] == 'M4_Far_00')
    assert len(target['vertices']) == 293 and len(target['faces']) == 514
    numeric = load(PREVIOUS / 'camera_numeric.py', '_target002_camera_enclosure')
    matrix_rows = metrics.matrix_review(numeric, target['vertices'], binding['camera_specification'])
    assert all(row['exact_inside'] and row['execution_gamma6_inside'] for row in matrix_rows)
    audit = [json.loads(line) for line in (slot / 'audit.jsonl').read_bytes().splitlines() if line]
    observe = [row for row in audit if row.get('event') == 'observe' and row.get('observation_mode') == 'active_observation']
    assert len(observe) == 1 and observe[0]['target_view_classifications'] == classes
    sys.path.insert(0, build['dependency_root'])
    import numpy as np
    from PIL import Image
    assert len(public['frames']) == len(facts['observations']) == len(response['result']['content']) - 1
    frame_reviews, normalized_arrays = [], []
    for index, (frame, observation) in enumerate(zip(public['frames'], facts['observations'])):
        review, arrays = check_frame(frame, observation, response['result']['content'][index + 1], capture,
                                     mapping, sources, q, metrics, np, Image)
        frame_reviews.append(review)
        normalized_arrays.append(arrays)
    evidence = {row['roi_id']: row for row in facts['region_evidence']}
    required = 1 if scene_kind == 'main' else 2
    counts = facts['inspection']['counts']
    assert counts['supported'] == 2 and counts['covered'] == required and counts['unobserved'] == 2 - required
    witnesses = []
    for region in facts['regions']:
        roi, kind = region['roi_id'], kinds[region['roi_id']]
        witness = evidence[roi]['complete_witness']
        covered = scene_kind == 'target_only' or kind == 'horizontal'
        assert region['status'] == ('covered' if covered else 'unknown')
        if covered:
            assert witness is not None
            observation = next(row for row in facts['observations'] if row['view_name'] == witness['view_name'])
            pixel = observation['pixel_rows'][witness['pixel_row_index']]
            assert pixel['roi_id'] == roi and pixel['readable'] is True and classes[witness['view_name']][roi]['complete'] is True
        else:
            assert witness is None and evidence[roi]['unobserved_reason'] == 'positive_area_occlusion_all_front_views'
        witnesses.append({'kind': kind, 'roi_id': roi, 'source_faces': sources[roi]['triangle_indices'],
                          'status': region['status'], 'actual_witness': witness, 'unobserved_reason': evidence[roi]['unobserved_reason']})
    assert facts['coverage']['observed_views'] == [row['view_name'] for row in public['frames']]
    assert all(row['view_name'] != 'TOP' for row in public['frames'])
    pins = [slot / name for name in ('RESULT.json', 'OWNER_BINDING.json', 'PUBLIC_01.json', 'REQUEST_01.json', 'RESPONSE_01.json', 'audit.jsonl')]
    pins += [Path(row['capture']) for row in owner['captures']]
    pins += [Path(frame[key]) for frame in public['frames'] for key in ('image_path', 'arrays_path')]
    summary = {'slot': str(slot), 'scene_kind': scene_kind, 'source_sha256': result['source_sha256'],
               'loaded_host_sha256': owner['source_proof']['actual_loaded_host_sha256'],
               'counts': counts, 'original_main_request_only': True, 'diagnostic_images_used_for_qualification': 0,
               'view_sequence': [row['view_name'] for row in public['frames']], 'frames': frame_reviews,
               'regions': witnesses, 'actual_six_view_classifications': classes, 'actual_matrix_enclosure': matrix_rows,
               'source_binding_sha256': binding['source_binding_sha256'], 'binding_sha256': binding['binding_sha256'],
               'producer_hash_and_owner_identity_chain_checked': True,
               'input_pins': [{'path': str(path), 'sha256': sha(path)} for path in pins], 'passed_checked_scope': True}
    comparison = {'facts': metrics.canonical_facts(facts, mapping, public['frames']), 'classes': classes,
                  'cameras': binding['camera_specification'], 'arrays': normalized_arrays, 'scope_audit': facts['scope']}
    return summary, comparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = read(HERE / 'BASELINE.json')
    summaries = [audit_slot(args.qualification / name, kind, baseline['A_source141_sha256'])[0]
                 for name, kind in (('A_main', 'main'), ('A_target_only', 'target_only'))]
    result = {'schema': 'm4-target-002-A-qualification-v1', 'qualification': 'PASS',
              'passed_checked_scope': True, 'original_main_requests': 2, 'diagnostic_images_used': 0,
              'records': summaries, 'frozen_geometry_sha256': baseline['frozen_geometry_sha256'],
              'analytic_review_sha256': sha(HERE / 'ANALYTIC_REVIEW.json'), 'checker_sha256': sha(Path(__file__)),
              'reference_quality_primitive_sha256': Q_SHA,
              'scope': 'The two original A public requests and their saved producer/source/pixel evidence. No renderer invocation or additional view.',
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'qualification': 'PASS', 'original_main_requests': 2,
                      'counts': [row['counts'] for row in summaries], 'new_rasters': 0}))


if __name__ == '__main__':
    main()
