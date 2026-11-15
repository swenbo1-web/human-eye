"""Pure grading regressions. Fixtures are private and contain no actual frames."""

import copy
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    grader = load(HERE / 'grade_claims.py', '_task_claim_interface')
    truth = json.loads((HERE / 'admin/TRUTH.json').read_bytes())
    answer = {'object_name': truth['object_name'], 'coordinate_frame': 'world', 'unit': 'm',
              'finite_view_pool_only': True, 'regions': [], 'limitations': []}
    normalized = {'region_reason_codes': {}, 'semantic_review': {'entire_final_reviewed': True, 'all_claims_entailed': True},
                  'extra_assertion_errors': [], 'contradictions': []}
    evidence = {'aliases': {}, 'current_source_references': ['synthetic-current-source'],
                'by_ref': {'synthetic-current-frame': {'view_name': 'synthetic-view', 'current_source_verified': True, 'regions': {}}}}
    for target in truth['regions']:
        complete = target['geometry_complete_in_pool']
        witness = {'frame_ref': 'synthetic-current-frame', 'view_name': 'synthetic-view',
                   'surface_pixels': 17, 'boundary_pixels': 5} if complete else None
        answer['regions'].append({'identity': {'object_name': truth['object_name'], 'source_triangle_indices': target['source_triangle_indices']},
            'center_world_m': target['center_world_m'], 'bounds_world_m': target['bounds_world_m'],
            'unit_normal_world': target['unit_normal_world'], 'geometry_complete_in_pool': complete,
            'complete_readable': complete, 'complete_witness': witness,
            'unknown_reason': None if complete else 'synthetic explicit bounded reason', 'source_references': ['synthetic-current-source']})
        normalized['region_reason_codes'][target['id']] = target['unknown_reason_code']
        evidence['by_ref']['synthetic-current-frame']['regions'][target['id']] = {
            'geometry_complete': complete, 'front_facing': True, 'readable': True, 'surface_pixels': 17, 'boundary_pixels': 5}
    assert grader.grade_answer(answer, normalized, truth, evidence)['passed']
    cases = []

    def reject(name, mutate):
        a, n, e = copy.deepcopy(answer), copy.deepcopy(normalized), copy.deepcopy(evidence)
        mutate(a, n, e)
        result = grader.grade_answer(a, n, truth, e)
        assert result['passed'] is False
        cases.append({'case': name, 'rejected': True, 'failed_checks': result['errors']})

    covered = next(index for index, row in enumerate(answer['regions']) if row['complete_readable'])
    unknown = 1-covered
    reject('partial_readable_is_not_complete_witness', lambda a, n, e: e['by_ref']['synthetic-current-frame']['regions'][truth['regions'][covered]['id']].update(geometry_complete=False))
    reject('foreign_frame_ref', lambda a, n, e: a['regions'][covered]['complete_witness'].update(frame_ref='other-slot-frame'))
    reject('wrong_actual_pixel_count', lambda a, n, e: a['regions'][covered]['complete_witness'].update(surface_pixels=18))
    reject('omitted_region', lambda a, n, e: a['regions'].pop())
    reject('duplicate_region', lambda a, n, e: a['regions'].__setitem__(unknown, copy.deepcopy(a['regions'][covered])))
    reject('normal_wrong_length', lambda a, n, e: a['regions'][covered].update(unit_normal_world=[0, 0, 2]))
    reject('wrong_extra_extent_alias', lambda a, n, e: a['regions'][covered].update(boundary_vertices_world_m=[[0, 0, 0]]*4))
    reject('wrong_reason', lambda a, n, e: n['region_reason_codes'].update({truth['regions'][unknown]['id']: 'pixel_evidence_insufficient'}))
    reject('missing_current_source', lambda a, n, e: a['regions'][covered].update(source_references=['other-slot-source']))
    reject('unretracted_extra_error', lambda a, n, e: n.update(extra_assertion_errors=['synthetic wrong extra fact']))
    reject('unreviewed_final', lambda a, n, e: n['semantic_review'].update(entire_final_reviewed=False))
    output = {'schema': 'target-task-consumption-claim-interface-v1', 'passed_checked_scope': True,
              'synthetic_positive': True, 'negative_cases': cases, 'source_only_no_actual_frame_fixture': True,
              'new_models': 0, 'new_product_calls': 0, 'new_rasters': 0,
              'checker_sha256': __import__('hashlib').sha256((HERE / 'grade_claims.py').read_bytes()).hexdigest()}
    with (HERE / 'admin/INTERFACE_CLAIMS.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'synthetic_positive': 1, 'negative_cases': len(cases)}))


if __name__ == '__main__':
    main()
