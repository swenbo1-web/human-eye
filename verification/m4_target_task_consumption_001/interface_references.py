"""Offline reference-resolution checks over actual no-model tool originals."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    path = HERE / 'quoted_sources.py'
    spec = importlib.util.spec_from_file_location('_reference_resolution_interface', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = Path('D:/he_m4_target_consume_001/qualification/P_qual')
    request = root / 'owner/tool_01/REQUEST.json'
    response = root / 'owner/tool_01/RESPONSE.json'
    brief = json.loads(json.loads(response.read_bytes())['result']['content'][0]['text'])
    public_hash = brief['binding']['binding_sha256']
    rows = [{'id': name, 'kind': kind, 'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
            for name, kind, source in (('request', 'tool_request', request), ('response', 'tool_result', response))]
    final = 'Source reference active_observation#1.'
    sources = module.Sources(root, final, rows, [response], [request])
    canonical = 'current-tool:1:active_observation'
    evidence = {'actual_tool_results': [str(response)], 'actual_tool_requests': [str(request)],
                'current_source_references': [canonical, public_hash, 'private-undelivered-hash']}
    normalized = {'answer': {'regions': [{'source_references': [canonical]}]},
        'semantic_review': {'reference_resolutions_entailed': True, 'no_missing_source_references_filled': True},
        'source_reference_resolution': [{'final_reference_excerpt': 'active_observation#1', 'canonical_ref': canonical,
            'tool_attempt': 1, 'unique_current_call': True, 'support': [{'source_id': 'response', 'excerpt': public_hash}]}]}
    module.validate_reference_resolutions(normalized, final, sources, evidence)
    cases = [{'case': 'explicit_current_call_needs_no_private_hash_in_final', 'passed': True}]

    def reject(name, mutate):
        row = copy.deepcopy(normalized)
        mutate(row)
        try:
            module.validate_reference_resolutions(row, final, sources, evidence)
        except ValueError as error:
            cases.append({'case': name, 'passed': True, 'reason': str(error)})
        else:
            raise AssertionError(name)

    reject('ambiguous_current_call', lambda row: row['source_reference_resolution'][0].update(unique_current_call=False))
    reject('foreign_final_reference', lambda row: row['source_reference_resolution'][0].update(final_reference_excerpt='other-slot-call'))
    reject('wrong_attempt', lambda row: row['source_reference_resolution'][0].update(tool_attempt=2))
    reject('no_actual_response_support', lambda row: row['source_reference_resolution'][0]['support'][0].update(source_id='request'))
    reject('unreturned_private_hash', lambda row: (row['source_reference_resolution'][0].update(canonical_ref='private-undelivered-hash'), row['answer']['regions'][0].update(source_references=['private-undelivered-hash'])))
    reject('missing_field_filled_from_truth', lambda row: row['semantic_review'].update(no_missing_source_references_filled=False))
    reject('canonical_reference_added_without_final_citation', lambda row: row.update(source_reference_resolution=[]))
    report = {'schema': 'target-task-consumption-reference-interface-v1', 'passed_checked_scope': True,
              'cases': cases, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'actual_request_sha256': rows[0]['sha256'], 'actual_response_sha256': rows[1]['sha256'],
              'fixture_scope': 'Actual closed no-model P tool response with synthetic final reference text. No final answer or model completion is claimed.',
              'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    with (HERE / 'admin/INTERFACE_REFERENCES.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'cases': len(cases), 'new_actual_calls': 0}))


if __name__ == '__main__':
    main()
