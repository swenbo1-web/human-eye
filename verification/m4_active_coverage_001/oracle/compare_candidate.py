"""Administrator comparison side. Candidate runners must not import this file."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cross(first, second):
    return (first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0])


def compare(candidate_path, answer, scene):
    candidate = read(candidate_path)
    target_by_name = {row['object_id']: row for row in answer['targets']}
    regions = candidate['regions']
    roi_ids = candidate['roi_ids']
    checks, failures = [], []

    def check(label, valid, detail=None):
        checks.append({'check': label, 'passed': bool(valid)})
        if not valid:
            failures.append({'check': label, 'detail': detail})

    check('independent_geometric_discovery_set', {row['object_name'] for row in regions} == set(target_by_name)
          and len(regions) == len(roi_ids) == len(target_by_name) == len(set(roi_ids)))
    region_by_id = {row['roi_id']: row for row in regions}
    check('ROI_identity_order_binding', set(region_by_id) == set(roi_ids))
    for region in regions:
        expected = target_by_name.get(region['object_name'])
        if expected is None:
            continue
        normal = tuple(map(F, region['normal']))
        front = tuple(map(F, expected['front_normal_from_winding']))
        check('front_winding_' + region['roi_id'], not any(cross(normal, front))
              and sum(first * second for first, second in zip(normal, front)) > 0)
        check('whole_scene_object_binding_' + region['roi_id'],
              scene['objects'][region['object_index']]['name'] == region['object_name'])
    expected_matrix = {(row['direction'], row['target']): row for row in answer['matrix']}
    check('six_candidate_views', set(candidate['view_masks']) == set(answer['visibility_by_direction'])
          and set(candidate['classifications']) == set(candidate['view_masks']))
    rows_checked = 0
    for view, mask in candidate['view_masks'].items():
        check(view + '_bounded_bitset', type(mask) is int and 0 <= mask < (1 << len(roi_ids)))
        check(view + '_classification_scope', set(candidate['classifications'][view]) == set(roi_ids))
        for index, roi_id in enumerate(roi_ids):
            region = region_by_id[roi_id]
            expected = expected_matrix.get((view, region['object_name']))
            if expected is None:
                check('unexpected_matrix_entry', False, {'view': view, 'region': region})
                continue
            actual = candidate['classifications'][view][roi_id]
            expected_complete = expected['full_interior_visible']
            bit_complete = bool(mask & (1 << index))
            check('matrix_' + view + '_' + roi_id, actual['complete'] is expected_complete
                  and bit_complete == expected_complete, {'expected': expected, 'actual': actual})
            check('status_' + view + '_' + roi_id, actual['status']
                  == ('complete' if expected_complete else 'positive_area_occlusion'))
            witness = actual['first_blocker']
            check('blocker_presence_' + view + '_' + roi_id,
                  (witness is None) if expected_complete else
                  (type(witness) is dict and bool(witness['triangle_geometry_id']) and F(witness['overlap_area_screen_exact']) > 0))
            rows_checked += 1
    return {'candidate_path': str(candidate_path.resolve()), 'candidate_sha256': sha(candidate_path),
            'passed': all(row['passed'] for row in checks), 'checks': checks, 'private_failures': failures,
            'rows_checked': rows_checked, 'candidate_identity': candidate['candidate_identity'],
            'scene_identity': candidate['scene_identity'],
            'scope': 'Discovery set, front orientation, all 36 continuous complete flags, bitsets/status and witness-presence consistency. Individual triangle witness area is not independently reconstructed by this box oracle.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidates', nargs='*', type=Path)
    args = parser.parse_args()
    paths = args.candidates or [BATCH / 'development/reference.json', BATCH / 'development/optimized.json']
    answer_path = HERE / 'ADMIN_ORACLE.json'
    scene_path = HERE / 'original/SCENE_GEOMETRY_RATIONAL.json'
    answer, scene = read(answer_path), read(scene_path)
    reports = [compare(path, answer, scene) for path in paths]
    private = {'administrator_only': True, 'reports': reports, 'oracle_sha256': sha(answer_path),
               'source_sha256': sha(Path(__file__)), 'scene_sha256': sha(scene_path)}
    (HERE / 'CANDIDATE_COMPARISON_PRIVATE.json').write_text(json.dumps(private, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                                        encoding='utf8', newline='\n')
    public = {'passed': all(row['passed'] for row in reports), 'candidates_checked': len(reports),
              'matrix_rows_checked': [row['rows_checked'] for row in reports],
              'failures': [len(row['private_failures']) for row in reports],
              'candidate_sources': {row['candidate_path']: row['candidate_sha256'] for row in reports},
              'private_binding_sha256': sha(HERE / 'CANDIDATE_COMPARISON_PRIVATE.json'),
              'oracle_source_sha256': sha(answer_path), 'comparison_source_sha256': sha(Path(__file__)),
              'privacy': 'Only aggregate qualification is public. No target IDs, matrix, blockers or optimal subset supplied to the candidate.',
              'new_model_Blender_product_API_runs': 0}
    (HERE / 'CANDIDATE_COMPARISON_PUBLIC.json').write_text(json.dumps(public, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                                       encoding='utf8', newline='\n')
    print(json.dumps(public, ensure_ascii=False))


if __name__ == '__main__':
    main()
