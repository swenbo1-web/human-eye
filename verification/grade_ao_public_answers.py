"""Grade already-produced, isolated public answers against separate source facts.

This process can read private scoring evidence. The public consumer cannot.
No encoder, author consumer, candidate geometry kernel or Blender is imported.
"""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct

import numpy as np

METRICS = ('max_principal_stretch', 'min_principal_stretch', 'max_area_strain',
           'max_normal_angle_deg', 'max_centroid_displacement', 'score')
VIEW = {'camera_type': ('rna', 'type'), 'matrix_world_blender': ('rna', 'matrix_world'),
        'ortho_scale_blender': ('rna', 'ortho_scale'), 'clip_start_blender': ('rna', 'clip_start'),
        'clip_end_blender': ('rna', 'clip_end'), 'shift_x': ('rna', 'shift_x'),
        'shift_y': ('rna', 'shift_y'), 'projection_blender': ('rna', 'projection'),
        'gpu_view_m': ('gpu', 'view'), 'gpu_projection_m': ('gpu', 'projection'),
        'gpu_view_projection_m': ('gpu', 'view_projection')}


def exact(actual, expected):
    if isinstance(expected, dict):
        for key, value in expected.items(): exact(actual[key], value)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for a, b in zip(actual, expected): exact(a, b)
    elif isinstance(expected, float):
        assert isinstance(actual, float) and struct.pack('>d', actual) == struct.pack('>d', expected)
    else:
        assert type(actual) is type(expected) and actual == expected


def on_triangle(point, triangle):
    t, p = np.asarray(triangle), np.asarray(point)
    scale = max(float(np.max(np.abs(t))), float(np.linalg.norm(np.ptp(t, axis=0))), 1e-12)
    basis = np.vstack(((t - t[0]).T / scale, np.ones(3)))
    rhs = np.r_[(p-t[0])/scale, 1.]
    weights = np.linalg.lstsq(basis, rhs, rcond=None)[0]
    assert np.linalg.norm(basis @ weights - rhs) <= 1e-9 and weights.min() >= -1e-9


def grade(package, truth):
    assert package['length_unit'] == 'm'
    ids = package['object_ids']
    assert len(package['observations']) == len(truth['observations'])
    for actual, expected in zip(package['observations'], truth['observations']):
        exact(actual['observation_id'], expected['observation_id'])
        exact(actual['frame_id'], expected['frame_id'])
        objects = {ids[obj['object_index']]: obj for obj in actual['objects']}
        assert objects.keys() == expected['objects'].keys()
        for key, value in expected['objects'].items(): exact(objects[key], value)
        a, b = actual['clearance'], expected['clearance']
        if b is None: assert a is None
        else:
            exact([ids[i] for i in a['target_object_indices']], b['target_ids'])
            exact(a['distance_m'], b['distance_m'])
            if b['distance_m'] is None:
                assert a['status'] == 'empty_surface' and a['witness_a'] is None and a['witness_b'] is None
            else:
                assert a['status'] == ('positive_gap' if b['distance_m'] > 0 else 'zero_distance')
                for side in ('a', 'b'):
                    witness = a['witness_'+side]
                    exact(witness['original_face_id'], b['triangle_'+side])
                    exact(witness['point_m'], b['point_'+side])
                    faces = b['triangles_'+side]
                    assert 0 <= witness['original_face_id'] < len(faces)
                    on_triangle(witness['point_m'], faces[witness['original_face_id']])
                assert abs(np.linalg.norm(np.subtract(a['witness_a']['point_m'], a['witness_b']['point_m'])) - a['distance_m']) <= max(b['analytic_tol_m'], 1e-12)
                assert abs(a['distance_m'] - b['analytic_distance_m']) <= b['analytic_tol_m']
        a, b = actual['deformation'], expected['deformation']
        if b is None: assert a is None
        else:
            exact(ids[a['object_index']], b['object_id'])
            for key in ('reference_frame', 'sample_frames', 'reduced_face_count', 'top_face_ids', 'position_kind', 'position_frame'):
                exact(a[key], b[key])
            assert len(a['faces']) == len(b['faces'])
            for row, reference in zip(a['faces'], b['faces']):
                exact(row['original_face_id'], reference['original_face_id'])
                for key in METRICS: exact(row[key], reference[key])
                np.testing.assert_allclose(row['position_m'], reference['position_m'], atol=1e-12, rtol=1e-12)
                for key, value in b['analytic_metrics'].get(str(row['original_face_id']), {}).items():
                    if value is None: assert row[key] is None
                    else: np.testing.assert_allclose(row[key], value, atol=1e-10, rtol=1e-10)
            if 'analytic_top_face_ids' in b: exact(a['top_face_ids'], b['analytic_top_face_ids'])
        a, b = actual['image'], expected['image']
        if b is None: assert a is None
        else:
            metadata = b['metadata']
            exact(a['path'], b['path'])
            exact([ids[i] for i in a['target_object_indices']], metadata['target_ids'])
            exact([ids[i] for i in a['mesh_object_indices']], metadata['mesh_ids'])
            exact(a['meters_per_blender_unit'], metadata['meters_per_blender_unit'])
            exact(a['mode'], metadata['mode']); exact(a['section'], metadata['section'])
            exact(actual['frame_id'], metadata['frame_id'])
            assert a['opened_png']['sha256'] == b['png_sha256']
            for side in ('global', 'local'):
                view, original = a[side+'_view'], metadata['views'][side]
                exact(view['viewport'], original['viewport'])
                for key, (part, item) in VIEW.items(): exact(view[key], original[part][item])
    a, b = package['outcome'], truth['outcome']
    if b is None: assert a is None
    else:
        for key, value in b.items():
            if key != 'goal': exact(a[key], value)
        goal = a['goal']
        exact(ids[goal['moving_object_index']], b['goal']['moving_id'])
        exact(ids[goal['reference_object_index']], b['goal']['reference_id'])
        for key in ('target_distance_m', 'tolerance_m'): exact(goal[key], b['goal'][key])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--answers', type=Path, required=True)
    parser.add_argument('--oracle-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    answers = json.loads(args.answers.read_bytes())
    cases, negatives = [], []
    for state_id, state in enumerate(answers['states']):
        oracle = json.loads((args.oracle_dir / f'state-{state_id}-oracle.json').read_bytes())
        assert len(state['answers']) == len(oracle) == 20
        for answer, truth in zip(state['answers'], oracle):
            result = {'state': state_id, 'task': answer['task_id'], 'passed': False}
            try:
                assert answer['public_consistency_passed']
                grade(answer['normalized_facts'], truth)
                result['passed'] = True
            except Exception as error: result['error'] = f'{type(error).__name__}: {error}'
            cases.append(result)
        for variant in ('wrong_positive_face_id', 'wrong_frame'):
            bad = deepcopy(state['answers'][0]['normalized_facts'])
            if variant == 'wrong_frame': bad['observations'][0]['frame_id'] += 1
            else: bad['observations'][0]['clearance']['witness_a']['original_face_id'] += 1
            try: grade(bad, oracle[0])
            except (AssertionError, KeyError, IndexError): rejected = True
            else: rejected = False
            negatives.append({'state': state_id, 'variant': variant, 'rejected': rejected})
    report = {'passed': all(c['passed'] for c in cases) and all(n['rejected'] for n in negatives),
              'answers_sha256': sha256(args.answers.read_bytes()).hexdigest(), 'arm': answers['arm'],
              'scope': 'Grading happens after isolated public decoding; no private facts supplied to the consumer',
              'cases': cases, 'negative_controls_with_private_truth': negatives}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
