"""Independently audit the closed, fixed vertex move/restore cache control.

Only saved source packets, public replies, producer arrays and setup receipts
are read. No product, Blender, camera planner or renderer is invoked.
"""

import argparse
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
B_SOURCE = '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be'
FIXTURE_SHA = '3616bc5868eaa0755936ee355c38ffa5d0a1506d4ea5bb083a8b4790ebbe72e0'
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
              'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def clipped_area(points):
    """Exact polygon intersection with the horizontal target's unit rectangle."""
    polygon = list(points)
    for axis, limit, keep_high in ((0, F(1), True), (0, F(2), False),
                                  (1, F(0), True), (1, F(1), False)):
        result = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            inside_a = a[axis] >= limit if keep_high else a[axis] <= limit
            inside_b = b[axis] >= limit if keep_high else b[axis] <= limit
            if inside_a:
                result.append(a)
            if inside_a != inside_b:
                weight = (limit-a[axis])/(b[axis]-a[axis])
                result.append(tuple(a[k]+weight*(b[k]-a[k]) for k in range(2)))
        polygon = result
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(polygon, polygon[1:] + polygon[:1])))/2


def blocker_proofs(capture, classes, horizontal, q):
    far = next(mesh for mesh in capture['meshes'] if mesh['name'] == 'M4_Far_11')
    points = [tuple(F(value) for value in row) for row in far['vertices']]
    triangles = {}
    for index, face in enumerate(far['faces']):
        triangle = tuple(points[vertex] for vertex in face)
        canonical = min(triangle[k:] + triangle[:k] for k in range(3))
        triangles[q.fingerprint(canonical)] = (index, triangle)
    proofs = []
    for view, direction in DIRECTIONS.items():
        row = classes[view][horizontal]
        assert row['status'] == 'positive_area_occlusion' and row['complete'] is False
        blocker = row['first_blocker']
        face_index, triangle = triangles[blocker['triangle_geometry_id']]
        shadow = []
        for point in triangle:
            t = (point[2]-2)/direction[2]
            assert t > 0
            shadow.append((point[0]-t*direction[0], point[1]-t*direction[1]))
        area = clipped_area(shadow)
        assert area > 0
        negative = tuple(-value for value in direction)
        right = cross(negative, (0, 1, 0) if view == 'TOP' else (0, 0, 1))
        up = cross(right, negative)
        jacobian = abs(right[0]*up[1]-right[1]*up[0])
        assert area*jacobian == F(blocker['overlap_area_screen_exact'])
        proofs.append({'view': view, 'actual_blocker_source_face': face_index,
                       'actual_blocker_geometry_sha256': blocker['triangle_geometry_id'],
                       'physical_xy_intersection_area_exact': str(area),
                       'screen_jacobian_exact': str(jacobian),
                       'reported_screen_area_exact': blocker['overlap_area_screen_exact']})
    return proofs


def review(root):
    checker = load(HERE / 'quality_saved.py', '_cache_saved_quality')
    q, metrics = checker.dependencies()
    viewport = load(HERE / 'viewport_oracle.py', '_cache_independent_viewport')
    result = checker.read(root / 'RESULT.json')
    assert result['passed'] is True and result['errors'] == []
    assert result['source_sha256'] == B_SOURCE
    assert checker.sha(result['binding_file']) == result['binding_sha256']
    build = checker.read(result['binding_file'])
    assert build['source_sha256'] == B_SOURCE
    sys.path.insert(0, build['dependency_root'])
    import numpy as np
    from PIL import Image
    assert result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
    assert result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code'] == 0
    assert result['native_final']['source_file_unchanged'] and result['native_final']['protected_files_unchanged']
    assert result['native_close']['source_file_unchanged'] and result['native_close']['protected_files_unchanged']
    assert result['session_closed_ns'] <= result['original_lifecycle_deadline_ns']
    assert checker.sha(root / 'native/input.blend') == result['asset']['asset_sha256']
    assert checker.sha(result['asset']['asset']) == result['asset']['asset_sha256']
    frozen = checker.read(HERE / 'reference/FROZEN_GEOMETRY.json')
    assert checker.sha(HERE / 'reference/FROZEN_GEOMETRY.json') == 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da'
    originals = {row['name']: row for row in frozen['objects']}
    fixture_path = HERE / 'fixtures/CACHE_VERTEX_PATCH.json'
    assert checker.sha(fixture_path) == FIXTURE_SHA
    fixture = checker.read(fixture_path)
    original_far = [[float(F(value)) for value in row] for row in originals['M4_Far_11']['world_vertices_m']]
    moved_far = [[point[2]+9/8, point[1]-1/8, 67/32] for point in original_far]
    assert fixture['original_vertices'] == original_far and fixture['moved_vertices'] == moved_far
    assert fixture['source_triangles'] == originals['M4_Far_11']['triangles']
    assert fixture['matrix_world'] == IDENTITY
    receipts = []
    for sequence, operation, state in ((3, 'qa_far11_move', 'moved'), (6, 'qa_far11_restore', 'restored')):
        path = root / f'native/{operation.upper()}_RECEIPT.json'
        receipt = checker.read(path)
        actual = checker.read(root / f'native/WIRE/{sequence:03}/RESPONSE.bin')
        request = checker.read(root / f'native/WIRE/{sequence:03}/REQUEST.bin')
        assert request == {'type': operation, 'params': {}}
        assert actual == receipt['response'] and actual['status'] == 'success'
        outcome = actual['result']
        assert outcome['vertices_written'] == 289 and outcome['fixture_sha256'] == FIXTURE_SHA
        assert outcome['matrix_before'] == outcome['matrix_after'] == IDENTITY
        assert outcome['faces_unchanged'] is True and outcome['local_vertices_state'] == state
        assert receipt['protected_files_unchanged'] and receipt['original_deadline_ns'] == result['original_lifecycle_deadline_ns']
        receipts.append(outcome)
    assert receipts[0]['before_fingerprint'] == receipts[1]['after_fingerprint']
    assert receipts[0]['after_fingerprint'] == receipts[1]['before_fingerprint']
    assert receipts[0]['before_fingerprint'] != receipts[0]['after_fingerprint']
    closed = result['native_final']['closed']
    assert closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint'] == receipts[0]['before_fingerprint']
    assert closed['cache_fixture_stage'] == result['fixture_final_stage'] == 2
    helper_path = HERE / 'harness/cache_owned_native.py'
    assert checker.sha(helper_path) == result['native_final']['config']['helper_sha256']
    helper_text = helper_path.read_text(encoding='utf-8')
    assert 'need(after==expected,"cache_fixture_full_state_readback")' in helper_text
    assert 'need(outcome["after_fingerprint"]==initial,"cache_fixture_restore_original_fingerprint")' in helper_text
    audit = [json.loads(line) for line in (root / 'audit.jsonl').read_bytes().splitlines() if line]
    observe = [row for row in audit if row.get('event') == 'observe' and row.get('observation_mode') == 'active_observation']
    assert len(observe) == 3
    oracle = checker.read(HERE / 'ANALYTIC_REVIEW.json')
    phases, comparisons, cache = [], [], {}
    pins = [root / 'RESULT.json', root / 'audit.jsonl', root / 'native/WORKER_EVENTS.jsonl',
            fixture_path, helper_path, HERE / 'CACHE_EXPECTATIONS.json', HERE / 'CACHE_SETUP_AMENDMENT.json']
    for phase_index, phase in enumerate(('baseline', 'moved', 'restored')):
        path = root / 'phases' / phase
        owner = checker.read(path / 'OWNER_BINDING.json')
        public = checker.read(path / 'PUBLIC_01.json')
        response = checker.read(path / 'RESPONSE_01.json')
        assert checker.read(path / 'PHASE_RESULT.json')['passed_operationally'] is True
        assert checker.read(path / 'PHASE_RESULT.json')['errors'] == []
        assert q.validate_source_proof(owner['source_proof'])['source_sha256'] == B_SOURCE
        assert owner['test_setup_phase'] == phase
        assert owner['phase_wire_sequence_range'] == [[1, 2], [4, 5], [7, 8]][phase_index]
        for pin in owner['setup_receipts']:
            assert checker.sha(pin['path']) == pin['sha256']
            pins.append(Path(pin['path']))
        assert checker.sha(owner['expected_phase_geometry']['path']) == owner['expected_phase_geometry']['sha256']
        decoded = [(pin, checker.decode_capture(pin, cache)) for pin in owner['captures']]
        main = [(pin, cap) for pin, cap in decoded if pin['role'] == 'main_target_capture']
        assert len(main) == owner['main_capture_count'] == 1
        _, capture = main[0]
        assert len(decoded) == 2 and owner['post_main_readback_count'] == 1
        for pin, cap in decoded:
            for mesh in cap['meshes']:
                original = originals[mesh['name']]
                expected = moved_far if phase == 'moved' and mesh['name'] == 'M4_Far_11' else [
                    [float(F(value)) for value in point] for point in original['world_vertices_m']]
                assert mesh['vertices'] == expected and mesh['faces'] == original['triangles']
            pins.extend(Path(pin[key]) for key in ('wire_request', 'wire_response', 'capture'))
        assert len(owner['asset_manifest']['objects']) == 14
        for row in owner['asset_manifest']['objects']:
            original = originals[row['object_name']]
            expected = moved_far if phase == 'moved' and row['object_name'] == 'M4_Far_11' else [
                [float(F(value)) for value in point] for point in original['world_vertices_m']]
            assert row['vertices_world'] == expected and row['triangles'] == original['triangles']
            assert row['asset_key'] == 'main/' + row['object_name']
        binding = q.reconstruct_target_binding(capture)
        expected_binding = {key: value for key, value in binding.items() if key != 'camera_specification'}
        expected_binding.update(runtime_source_sha256=B_SOURCE, source_status='loaded_generation',
                                disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
        assert public['binding'] == expected_binding
        mapping = q.validate_object_mapping(capture, binding, owner['asset_manifest'], owner['source_proof'])
        assert response['result']['isError'] is False and json.loads(response['result']['content'][0]['text']) == public
        request = checker.read(path / 'REQUEST_01.json')['params']['arguments']
        assert request['query'] == {'mode': 'active_observation', 'objects': [{'name': 'M4_Far_00'}]}
        assert request['include_image'] is True and request['response_detail'] == 'full'
        meta = capture['observation_target']
        directory = {row['name']: row for row in meta['scene_directory']}
        assert set(directory) == set(originals)
        for name, row in directory.items():
            expected = moved_far if phase == 'moved' and name == 'M4_Far_11' else originals[name]['world_vertices_m']
            assert row['matrix_world'] == IDENTITY
            assert all(all(F(row['bounds_world_m'][0][k]) <= F(point[k]) <= F(row['bounds_world_m'][1][k])
                           for k in range(3)) for point in expected)
        far_id = directory['M4_Far_11']['object_id']
        assert (far_id in meta['retained_object_ids']) is (phase == 'moved')
        exclusion_proofs = []
        for object_id in meta['excluded_object_ids']:
            row = next(row for row in directory.values() if row['object_id'] == object_id)
            outside, views = viewport.outside(row['bounds_world_m'], meta['camera_plan'])
            assert outside
            exclusion_proofs.append({'name': row['name'], 'views': views})
        facts, classes = public['facts'], public['target_view_classifications']
        assert observe[phase_index]['target_view_classifications'] == classes
        sources = {row['roi_id']: row for row in facts['scope']['patch_support']['regions']}
        assert len(sources) == len(facts['regions']) == 2
        kinds = {}
        for region in facts['regions']:
            faces = sources[region['roi_id']]['triangle_indices']
            kind = 'vertical' if faces == list(range(512)) else 'horizontal' if faces == [512, 513] else None
            assert kind is not None and kind not in kinds.values()
            kinds[region['roi_id']] = kind
            q.validate_region_geometry(region, faces, capture['meshes'][region['object_index']])
            assert region['front_direction_world'] == ([-1, 0, 0] if kind == 'vertical' else [0, 0, 1])
            expected = oracle['vertical_main_geometric_classifications' if kind == 'vertical' else 'horizontal_main_geometric_classifications']
            for view, status in expected.items():
                if phase == 'moved' and kind == 'horizontal':
                    status = 'positive_area_occlusion'
                assert classes[view][region['roi_id']]['status'] == status
                assert classes[view][region['roi_id']]['complete'] is (status == 'complete')
        horizontal = next(roi for roi, kind in kinds.items() if kind == 'horizontal')
        vertical = next(roi for roi, kind in kinds.items() if kind == 'vertical')
        assert F(classes['LEFT'][vertical]['first_blocker']['overlap_area_screen_exact']) == F(oracle['near_shadow']['area_exact'])
        blockers = blocker_proofs(capture, classes, horizontal, q) if phase == 'moved' else []
        counts = facts['inspection']['counts']
        expected_covered = 0 if phase == 'moved' else 1
        assert counts['supported'] == 2 and counts['covered'] == expected_covered and counts['unobserved'] == 2-expected_covered
        evidence = {row['roi_id']: row for row in facts['region_evidence']}
        assert len(public['frames']) == len(facts['observations']) == len(response['result']['content'])-1 == 1
        assert public['frames'][0]['view_name'] == 'SCENE' and facts['coverage']['observed_views'] == ['SCENE']
        frame = public['frames'][0]
        assert frame['host_binding_sha256'] == binding['binding_sha256'] and frame['source_revision'] == binding['scene_revision']
        frame_review, arrays = checker.check_frame(frame, facts['observations'][0], response['result']['content'][1],
            capture, mapping, sources, {row['roi_id']: row['front_direction_world'] for row in facts['regions']},
            q, metrics, np, Image)
        for region in facts['regions']:
            covered = phase != 'moved' and kinds[region['roi_id']] == 'horizontal'
            assert region['status'] == ('covered' if covered else 'unknown')
            witness = evidence[region['roi_id']]['complete_witness']
            if covered:
                assert witness == {'view_name': 'SCENE', 'pixel_row_index': 0}
                assert facts['observations'][0]['pixel_rows'][0]['roi_id'] == region['roi_id']
                assert facts['observations'][0]['pixel_rows'][0]['readable'] is True
            else:
                assert witness is None and evidence[region['roi_id']]['unobserved_reason'] == 'positive_area_occlusion_all_front_views'
        target = next(row for row in capture['meshes'] if row['name'] == 'M4_Far_00')
        numeric = load(checker.PREVIOUS / 'camera_numeric.py', '_cache_camera_numeric_' + phase)
        matrix_rows = metrics.matrix_review(numeric, target['vertices'], binding['camera_specification'])
        assert all(row['exact_inside'] and row['execution_gamma6_inside'] for row in matrix_rows)
        phases.append({'phase': phase, 'passed_checked_scope': True, 'capture_state': capture['capture_state'],
                       'source_revision': binding['scene_revision'], 'binding_sha256': binding['binding_sha256'],
                       'source_binding_sha256': binding['source_binding_sha256'], 'counts': counts,
                       'Far11_retained': phase == 'moved', 'actual_expanded_Far11_vertices': 289 if phase == 'moved' else 0,
                       'current_directory_checked': True, 'excluded_math_proofs': exclusion_proofs,
                       'exact_first_blocker_proofs': blockers, 'frame': frame_review,
                       'actual_matrix_enclosure': matrix_rows,
                       'work': public['work']['target_acquisition'], 'actual_six_view_classifications': classes})
        comparisons.append({'binding': binding, 'capture': capture, 'facts': metrics.canonical_facts(facts, mapping, public['frames']),
                            'arrays': arrays, 'classes': classes, 'cameras': binding['camera_specification']})
        pins.extend(path / name for name in ('OWNER_BINDING.json', 'PUBLIC_01.json', 'RESPONSE_01.json', 'REQUEST_01.json', 'PHASE_RESULT.json'))
        pins.extend(Path(frame[key]) for key in ('arrays_path', 'image_path'))
    first, moved, restored = comparisons
    assert first['capture']['capture_state']['instance_id'] == moved['capture']['capture_state']['instance_id'] == restored['capture']['capture_state']['instance_id']
    assert [row['capture']['capture_state']['revision'] for row in comparisons] == [1, 2, 3]
    assert len({row['binding']['binding_sha256'] for row in comparisons}) == 3
    assert first['binding']['scene_revision'] == restored['binding']['scene_revision'] != moved['binding']['scene_revision']
    assert first['facts'] == restored['facts'] and first['classes'] == restored['classes'] and first['cameras'] == restored['cameras']
    restored_buffers = q.compare_normalized_buffers(first['arrays'], restored['arrays'])
    assert restored_buffers['equal'] and np.array_equal(first['arrays']['patch_owners'], restored['arrays']['patch_owners'])
    assert np.array_equal(first['arrays']['color'], moved['arrays']['color'])
    assert not np.array_equal(first['arrays']['depth'], moved['arrays']['depth'])
    assert not np.array_equal(first['arrays']['owners'], moved['arrays']['owners'])
    output = {'schema': 'target-002-cache-source-pixel-review-v1', 'passed_checked_scope': True,
              'session': str(root), 'source_sha256': B_SOURCE, 'phases': phases,
              'fixture_vertex_writes_per_step': [row['vertices_written'] for row in receipts],
              'fixture_vertex_writes_total': sum(row['vertices_written'] for row in receipts),
              'product_setter_calls': 0, 'diagnostic_images_used': 0,
              'original_source_blend_unchanged': True, 'full_scene_fingerprint_restored': True,
              'restored_target_facts_classifications_camera_equal': True, 'restored_buffers': restored_buffers,
              'moved_RGB_same_depth_and_asset_owner_changed': True,
              'proof_boundary': ['This is a local-geometry-change invalidation control. The ideal object-matrix setup was not executed.',
                  'The moved Far11 289 vertices and 512 ordered faces are decoded from its actual main wire resource.',
                  'Baseline/restored Far11 is excluded. Its full local restoration is attested by the pinned fixture helper full-scene readback and final original fingerprint, plus current directory bounds. No excluded mesh packet is invented.',
                  'A pixel can remain visually equal while current depth, owner and geometric witness validity change. All three original main replies were checked.'],
              'checker_sha256': checker.sha(Path(__file__)), 'quality_helper_sha256': checker.sha(HERE / 'quality_saved.py'),
              'input_pins': [{'path': str(path), 'sha256': checker.sha(path)} for path in sorted(set(pins), key=str)],
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = review(args.slot)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'phases': 3, 'covered': [row['counts']['covered'] for row in output['phases']],
                      'fixture_vertex_writes': output['fixture_vertex_writes_total'], 'new_rasters': 0}))


if __name__ == '__main__':
    main()
