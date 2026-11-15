"""Pure grader, quotation and source-only normalization counterexamples."""

import copy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('_m5_interface_' + name, HERE / (name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def numbers(value):
    if type(value) is list:
        return [numbers(item) for item in value]
    if type(value) is str:
        return float(F(value))
    return value


def fixture():
    truth = json.loads((HERE/'admin/TRUTH.json').read_bytes())
    answer = {'object_name': truth['object_name'], 'coordinate_frame': 'world', 'unit': 'm',
              'finite_view_pool_only': True, 'regions': [], 'limitations': []}
    evidence = {'aliases': {}, 'current_source_references': ['fixture-current'],
                'by_ref': {'fixture-frame': {'view_name': 'SCENE', 'current_source_verified': True, 'regions': {}}},
                'whole_object_sources': {}, 'observation_measurement_current_source_consistent': True,
                'observation_binding_sha256s': ['fixture-parent'], 'observation_source_binding_sha256s': ['fixture-parent-source']}
    normalized = {'semantic_review': {'entire_final_reviewed': True, 'all_claims_entailed': True},
                  'region_reason_codes': {}, 'extra_assertion_errors': [], 'contradictions': []}
    for region in truth['regions']:
        complete = region['geometry_complete_in_pool']
        answer['regions'].append({'identity': {'object_name': truth['object_name'], 'source_triangle_indices': region['source_triangle_indices']},
            'center_world_m': numbers(region['center_world_m']), 'bounds_world_m': numbers(region['bounds_world_m']),
            'unit_normal_world': numbers(region['unit_normal_world']), 'geometry_complete_in_pool': complete,
            'complete_readable': complete, 'complete_witness': {'frame_ref': 'fixture-frame', 'view_name': 'SCENE',
                'surface_pixels': 16, 'boundary_pixels': 4} if complete else None,
            'unknown_reason': region['unknown_reason_code'], 'source_references': ['fixture-current']})
        normalized['region_reason_codes'][region['id']] = region['unknown_reason_code']
        evidence['by_ref']['fixture-frame']['regions'][region['id']] = {
            'geometry_complete': complete, 'front_facing': complete, 'readable': complete,
            'surface_pixels': 16, 'boundary_pixels': 4}
    for index, row in enumerate(truth['whole_measurement_objects']):
        evidence['whole_object_sources'][row['object_name']] = {'object_id': row['reference_object_id'],
            'instance_id': 'fixture-'+str(index), 'vertices': numbers(row['vertices_world_m']), 'faces': row['source_triangles']}
    answer['measurement'] = {'object_a_name': 'M4_Far_00', 'object_b_name': 'M4_Near', 'measurement_scope': 'whole_objects',
        'status': 'measured', 'distance_m': truth['measurement']['distance_binary64_m'],
        'nearest_witness': {**truth['measurement']['one_legal_witness'], 'direction_a_to_b': [-1, 0, 0]},
        'unknown_reason': None, 'source_references': ['fixture-current'],
        'object_source_bindings': [{'object_name': row['object_name'], 'source_triangle_count': row['source_triangle_count'],
            'source_triangle_index_ranges': row['source_triangle_index_ranges'], 'source_references': ['fixture-current']}
            for row in truth['whole_measurement_objects']]}
    answer['observation_measurement_correspondence'] = {'observation_object_name': truth['object_name'],
        'measurement_object_names': ['M4_Far_00', 'M4_Near'], 'same_current_source': True,
        'explanation': 'Actual current fixture objects and complete source faces are associated.', 'source_references': ['fixture-current']}
    return answer, normalized, truth, evidence


def main():
    claims, quoted, normalizer = [load(name) for name in ('grade_claims', 'quoted_sources', 'normalize_saved')]
    cases = []

    def check(name, operation, expected):
        try:
            actual = bool(operation())
            reason = None
        except (ValueError, KeyError, TypeError, IndexError) as error:
            actual = False
            reason = type(error).__name__ + ':' + str(error)
        cases.append({'case': name, 'expected': expected, 'actual': actual, 'passed': actual == expected, 'reason': reason})
        assert actual == expected, name

    def claim_case(name, change=None, expected=False):
        value = copy.deepcopy(fixture())
        if change:
            change(value)
        check(name, lambda: claims.grade_answer(*value)['passed'], expected)

    claim_case('valid_complete_source_bound_answer', expected=True)
    claim_case('consumer_decimal_0_996_accepted', lambda x: x[0]['measurement'].update(distance_m=.996), True)
    def rounded_points(value):
        value[0]['measurement']['nearest_witness']['b'] = [.004, 0, 0]
        value[0]['measurement']['distance_m'] = .996
    claim_case('consumer_points_original_publication_tolerance', rounded_points, True)
    def nonunique(value):
        value[0]['measurement']['nearest_witness']['a'][1:] = [.25, .25]
        value[0]['measurement']['nearest_witness']['b'][1:] = [.25, .25]
    claim_case('another_legal_nearest_pair', nonunique, True)
    claim_case('scalar_beyond_publication_tolerance', lambda x: x[0]['measurement'].update(distance_m=1.0))
    claim_case('wrong_unit_direction', lambda x: x[0]['measurement']['nearest_witness'].update(direction_a_to_b=[1, 0, 0]))
    claim_case('YZ_mismatch_despite_close_scalar_length', lambda x: x[0]['measurement']['nearest_witness']['b'].__setitem__(1, .000001))
    claim_case('point_outside_actual_source_triangle', lambda x: x[0]['measurement']['nearest_witness'].update(b=[.004, 2, 2]))
    claim_case('region_measurement_scope_rejected', lambda x: x[0]['measurement'].update(measurement_scope='region'))
    claim_case('incomplete_measurement_object_bindings', lambda x: x[0]['measurement']['object_source_bindings'].pop())
    claim_case('incomplete_whole_target_source_faces', lambda x: x[0]['measurement']['object_source_bindings'][0].update(source_triangle_index_ranges=[[0, 511]]))
    claim_case('false_optional_face_count', lambda x: x[0]['measurement']['object_source_bindings'][0].update(source_triangle_count=513))
    claim_case('false_optional_geometry_hash', lambda x: x[0]['measurement']['object_source_bindings'][0].update(ordered_geometry_sha256='wrong'))
    claim_case('foreign_measurement_reference', lambda x: x[0]['measurement'].update(source_references=['foreign-slot']))
    claim_case('A_requires_no_B_parent_hash', expected=True)
    claim_case('false_optional_parent_hash', lambda x: x[0]['observation_measurement_correspondence'].update(parent_binding_sha256='wrong'))
    claim_case('false_correspondence', lambda x: x[0]['observation_measurement_correspondence'].update(same_current_source=False))
    claim_case('region_omission', lambda x: x[0]['regions'].pop())
    claim_case('unretracted_extra_error', lambda x: x[1]['extra_assertion_errors'].append('false extra view claim'))
    claim_case('unretracted_contradiction', lambda x: x[1]['contradictions'].append('opposed assertions'))
    horizontal = next(index for index, row in enumerate(fixture()[0]['regions']) if row['complete_readable'])
    claim_case('wrong_actual_image_reference', lambda x: x[0]['regions'][horizontal]['complete_witness'].update(frame_ref='foreign-frame'))
    claim_case('wrong_actual_pixel_count', lambda x: x[0]['regions'][horizontal]['complete_witness'].update(surface_pixels=17))

    answer, norm, truth, evidence = fixture()
    directory = HERE/'admin/interface_sources/slot'
    directory.mkdir(parents=True)
    request = {'id': 1, 'params': {'name': 'execute_python', 'arguments': {'code': 'observe current source'}}}
    final = json.dumps(answer, separators=(',', ':'))
    response = {'id': 1, 'result': {'content': [{'type': 'text', 'text': final}], 'isError': False}}
    paths = {}
    source_rows = []
    for kind, name, value in (('tool_request', 'REQUEST', request), ('tool_result', 'RESPONSE', response)):
        path = directory/(name+'.json')
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream)
        identity = name.lower()
        source_rows.append({'id': identity, 'kind': kind, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        paths[name] = str(path)
    sources = quoted.Sources(directory, final, source_rows, [paths['RESPONSE']], [paths['REQUEST']])
    support = [{'source_id': 'response', 'excerpt': final}]
    normalized = {'slot_id': 'B1', 'answer': answer, 'semantic_review': {'adoption_claims_entailed': True},
        'product_adoption': {'claims': [
            {'kind': 'observation', 'public_call_index': 1, 'region_identity': answer['regions'][horizontal],
             'product_support': support, 'final_use_excerpt': '"complete_readable":true', 'source_reference_excerpt': 'fixture-current'},
            {'kind': 'measurement', 'public_call_index': 1, 'fact': 'surface_proximity',
             'product_support': support, 'final_use_excerpt': '"distance_m":'+str(answer['measurement']['distance_m']), 'source_reference_excerpt': 'fixture-current'}]},
        'extra_tool_classification': [{'attempt': 1, 'category': 'new_product_observation', 'support': support}],
        'process_diagnostics': {'source_support': support}}
    evidence.update(actual_product_responses=[paths['RESPONSE']], actual_public_calls=[{'index': 1, 'mode': 'active_observation',
        'outer_attempt': 1, 'outer_result_path': paths['RESPONSE'], 'is_error': False, 'measurement': {'valid': True}}],
        actual_joint_public_call_indices=[1], actual_batch_outer_attempts=[], actual_business_tool_count=1,
        actual_tool_requests=[paths['REQUEST']], actual_tool_results=[paths['RESPONSE']], initial_product_entry=True)
    identify = lambda value: claims.identify(value, truth, evidence['aliases'])
    def adopt(value=normalized, current=evidence):
        return quoted.adoption(value, final, sources, current, identify, True)['actual_product_facts_adopted']
    check('both_joint_facts_actual_final_use', adopt, True)
    value = copy.deepcopy(normalized)
    value['product_adoption']['claims'] = []
    check('mere_call_is_not_adoption', lambda: adopt(value), False)
    value = copy.deepcopy(normalized)
    value['product_adoption']['claims'].pop()
    check('observation_only_is_not_joint_adoption', lambda: adopt(value), False)
    value = copy.deepcopy(normalized)
    value['answer']['measurement']['measurement_scope'] = 'region'
    check('whole_objects_required_for_joint_adoption', lambda: adopt(value), False)
    value = copy.deepcopy(normalized)
    value['product_adoption']['claims'][1]['final_use_excerpt'] = 'never asserted'
    check('missing_actual_final_use_is_not_adoption', lambda: adopt(value), False)
    current = copy.deepcopy(evidence)
    current['actual_joint_public_call_indices'] = []
    check('separate_APIs_are_not_joint_adoption', lambda: adopt(current=current), False)
    check('one_JSON_with_prose_retains_both_prose_sides', lambda: normalizer.extract_answer('before '+final+' after')[2]['text_after_json'] == ' after', True)
    check('two_JSON_answers_are_ambiguous', lambda: bool(normalizer.extract_answer(final+'\n'+final)[0]), False)
    report = {'schema': 'm5-task-consumption-pure-scoring-interface-v1', 'passed_checked_scope': all(row['passed'] for row in cases),
        'cases': cases, 'case_count': len(cases), 'actual_runtime_or_model_records': False,
        'source_pins': [{'path': str(HERE/(name+'.py')), 'sha256': hashlib.sha256((HERE/(name+'.py')).read_bytes()).hexdigest()}
                        for name in ('grade_claims', 'quoted_sources', 'normalize_saved', 'interface_scoring')],
        'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    path = HERE/'admin/INTERFACE_SCORING.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': report['passed_checked_scope'], 'case_count': len(cases),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
