"""Supplement saved-frame checks with exact producer identity commitments."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def main():
    review = json.loads((HERE / 'ACTUAL_CAMERA_REVIEW.json').read_bytes())
    assert review['passed_checked_scope'] is True
    build = json.loads((HERE / 'build/RUN_BINDING.json').read_bytes())
    sys.path.insert(0, build['dependency_root'])
    import numpy as np
    records = []
    for slot_review in review['actual_slots']:
        paths = {Path(row['path']).name: row for row in slot_review['input_pins']}
        for row in slot_review['input_pins']:
            assert sha(row['path']) == row['sha256']
        public = json.loads(Path(paths['PUBLIC_01.json']['path']).read_bytes())
        if slot_review['main_capture_count'] == 0:
            assert slot_review['slot'] == 'NEW_extreme' and 'frames' not in public
            continue
        capture_pin = next(row for row in slot_review['input_pins'] if Path(row['path']).name.startswith('MAIN_CAPTURE_'))
        capture = json.loads(Path(capture_pin['path']).read_bytes())
        keys = []
        for mesh in capture['meshes']:
            vertices = tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices'])
            faces = []
            for face in mesh['faces']:
                points = tuple(vertices[index] for index in face)
                faces.append(min(points[index:] + points[:index] for index in range(3)))
            keys.append((tuple(sorted(vertices)), tuple(sorted(faces))))
        order_identity = fingerprint(tuple(keys))
        for frame in public['frames']:
            with np.load(frame['arrays_path'], allow_pickle=False) as archive:
                offsets = archive['face_patch_offsets'].tolist()
            expected_owner = fingerprint((frame['owner_schema'], frame['triangle_id_scope'],
                                          frame['patch_mapping_identity'], offsets))
            assert frame['owner_mapping_identity'] == expected_owner
            assert frame['mesh_order_identity'] == order_identity
            image_path = Path(frame['image_path'])
            sequence = int(image_path.stem.split('-', 1)[0])
            binding = (frame['scene_identity'], frame['candidate_identity'])
            assert image_path.stem == str(sequence).zfill(3) + '-' + fingerprint(
                (binding, expected_owner, frame['view_name']))[:24]
            expected_frame = fingerprint((binding, frame['owner_schema'], expected_owner, frame['view_name'],
                                          sequence, frame['image_sha256']))
            assert frame['frame_identity'] == expected_frame
            expected_ref = 'active-host-image:' + fingerprint((frame['host_binding_sha256'], frame['view_name'],
                frame['image_sha256'], frame['patch_mapping_identity'], frame['owner_schema'], expected_owner, expected_frame))
            assert frame['image_ref'] == expected_ref
            records.append({'slot': slot_review['slot'], 'view': frame['view_name'],
                            'producer_frame_identity': expected_frame, 'producer_owner_identity': expected_owner,
                            'ordered_geometry_identity': order_identity, 'producer_image_reference_matches': True,
                            'producer_NPZ_sha256': frame['arrays_sha256'], 'producer_NPZ_sha_matches': sha(frame['arrays_path']) == frame['arrays_sha256']})
    assert len(records) == review['observed_producer_frames'] == 7
    assert all(row['producer_NPZ_sha_matches'] for row in records)
    old = json.loads((HERE / 'OLD_REPRO.json').read_bytes())
    new = json.loads((HERE / 'CANDIDATE_NUMERIC_SOURCE_01.json').read_bytes())
    invariant = []
    for a, b in zip(old['records'], new['records']):
        if not b['cameras_returned']:
            continue
        same = True
        for x, y in zip(a['camera_specification']['views'], b['camera_specification']['views']):
            for key in ('view_matrix', 'projection_matrix'):
                same &= [[float(value).hex() for value in row] for row in x[key]] == [
                    [float(value).hex() for value in row] for row in y[key]]
        assert same
        invariant.append({'case': b['id'], 'view_and_projection_binary64_hex_equal_old': True})
    result = {'schema': 'camera-producer-frame-identity-supplement-v1', 'passed_checked_scope': True,
              'actual_review_sha256': sha(HERE / 'ACTUAL_CAMERA_REVIEW.json'), 'frame_count': 7,
              'records': records, 'frozen_normal_matrix_invariance': invariant,
              'source_sha256': sha(Path(__file__)), 'new_Blender_starts': 0, 'new_rasters': 0,
              'scope': 'Exact producer identity and current file hashes. No reconstruction of a missing main frame or independent raster.'}
    with (HERE / 'FRAME_IDENTITY_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'actual_frames': 7, 'normal_matrix_invariance_cases': len(invariant)}))


if __name__ == '__main__':
    main()
