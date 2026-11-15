"""Post-run saved-format regressions, with synthetic fixtures only."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('_m5_saved_regression_'+name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    original = load('interface_scoring')
    claims, quoted = load('grade_claims_saved_R1'), load('quoted_sources_saved_R1')
    cases = []

    def check(name, actual, expected):
        cases.append({'case': name, 'actual': bool(actual), 'expected': expected, 'passed': bool(actual) == expected})
        assert bool(actual) == expected, name

    answer, normalized, truth, evidence = copy.deepcopy(original.fixture())
    check('canonical_hash_scheme_still_optional', claims.grade_answer(answer, normalized, truth, evidence)['passed'], True)
    for row in answer['measurement']['object_source_bindings']:
        source = evidence['whole_object_sources'][row['object_name']]
        raw = json.dumps({'vertices': source['vertices'], 'triangles': source['faces']}, separators=(',', ':')).encode()
        row['ordered_geometry_sha256'] = hashlib.sha256(raw).hexdigest()
    normalized['declared_hash_schemes'] = {name: {'scheme': 'source_order_vertices_triangles_json_compact',
        'explicit_final_definition_quoted': True} for name in evidence['whole_object_sources']}
    normalized['semantic_review']['declared_hash_definitions_entailed'] = True
    check('explicitly_declared_hash_definition_independently_replayed', claims.grade_answer(answer, normalized, truth, evidence)['passed'], True)
    bad = copy.deepcopy(answer)
    bad['measurement']['object_source_bindings'][0]['ordered_geometry_sha256'] = 'incorrect'
    check('declared_but_incorrect_hash_rejected', claims.grade_answer(bad, normalized, truth, evidence)['passed'], False)
    missing = copy.deepcopy(normalized)
    missing['semantic_review']['declared_hash_definitions_entailed'] = False
    check('unreviewed_custom_hash_definition_rejected', claims.grade_answer(answer, missing, truth, evidence)['passed'], False)

    answer, _, truth, evidence = original.fixture()
    directory = HERE/'admin/interface_sources/slot'
    request_path, response_path = directory/'REQUEST.json', directory/'RESPONSE.json'
    response = json.loads(response_path.read_bytes())
    final = response['result']['content'][0]['text']
    source_rows = [{'id': name.lower(), 'kind': kind, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for name, kind, path in (('REQUEST', 'tool_request', request_path), ('RESPONSE', 'tool_result', response_path))]
    sources = quoted.Sources(directory, final, source_rows, [str(response_path)], [str(request_path)])
    support = [{'source_id': 'response', 'excerpt': final}]
    horizontal = next(row for row in answer['regions'] if row['complete_readable'])
    value = {'slot_id': 'B1', 'answer': answer, 'semantic_review': {'adoption_claims_entailed': True},
        'product_adoption': {'claims': [
            {'kind': 'observation', 'public_call_index': 1, 'region_identity': horizontal,
             'product_support': support, 'final_use_excerpt': '"complete_readable":true', 'source_reference_excerpt': 'fixture-current'},
            {'kind': 'measurement', 'public_call_index': 1, 'fact': 'surface_proximity',
             'product_support': support, 'final_use_excerpt': '"distance_m":'+str(answer['measurement']['distance_m']), 'source_reference_excerpt': 'fixture-current'}]},
        'extra_tool_classification': [{'attempt': 1, 'category': 'new_product_observation', 'support': support}],
        'process_diagnostics': {'source_support': support}}
    evidence.update(actual_product_responses=[str(response_path)], actual_public_calls=[{'index': 1,
        'mode': 'active_observation', 'is_error': False, 'outer_attempt': 1, 'outer_result_path': str(response_path),
        'measurement': {'valid': True}, 'delivered_to_model': True}], actual_joint_public_call_indices=[1],
        actual_batch_outer_attempts=[], actual_business_tool_count=1)
    identify = lambda row: claims.identify(row, truth, evidence['aliases'])
    check('delivered_same_joint_facts_adopted', quoted.adoption(value, final, sources, evidence, identify, True)['actual_product_facts_adopted'], True)
    evidence['actual_public_calls'][0]['delivered_to_model'] = False
    check('background_success_behind_outer_error_not_adopted', quoted.adoption(value, final, sources, evidence, identify, True)['actual_product_facts_adopted'], False)
    report = {'schema': 'm5-saved-format-R1-pure-interface-v1', 'passed_checked_scope': all(row['passed'] for row in cases),
        'cases': cases, 'case_count': len(cases), 'synthetic_fixtures_only': True,
        'formal_content_scores_executed': 0, 'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0,
        'source_pins': [{'path': str(HERE/(name+'.py')), 'sha256': hashlib.sha256((HERE/(name+'.py')).read_bytes()).hexdigest()}
                        for name in ('grade_claims_saved_R1', 'quoted_sources_saved_R1', 'interface_saved_R1')]}
    path = HERE/'admin/INTERFACE_SAVED_R1.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'cases': len(cases), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
