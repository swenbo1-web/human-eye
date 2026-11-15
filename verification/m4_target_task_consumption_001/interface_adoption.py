"""Pure source-quotation/adoption regressions using explicit synthetic text."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    path = HERE / 'quoted_sources.py'
    spec = importlib.util.spec_from_file_location('_synthetic_adoption_checks', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.Sources.__new__(module.Sources)
    source.paths = {'product': (HERE / 'admin/SYNTHETIC_PRODUCT_RESPONSE.json').resolve(),
                    'other': (HERE / 'admin/SYNTHETIC_OTHER_RESPONSE.json').resolve()}
    source.text = {'final': ['current-ref actual task fact'], 'product': ['actual task fact current-ref'],
                   'other': ['actual task fact current-ref']}
    source.kinds = {'final': 'final', 'product': 'tool_result', 'other': 'tool_result'}
    final = source.text['final'][0]
    evidence = {'actual_product_responses': [str(source.paths['product'])],
                'current_source_references': ['current-ref'], 'initial_product_entry': True,
                'actual_business_tool_count': 1}
    normalized = {'semantic_review': {'adoption_claims_entailed': True},
                  'product_adoption': {'claims': [{'region_identity': {},
                    'product_support': [{'source_id': 'product', 'excerpt': 'actual task fact'}],
                    'final_use_excerpt': 'actual task fact', 'source_reference_excerpt': 'current-ref'}]},
                  'extra_tool_classification': [], 'process_diagnostics': {}}

    def evaluate(row, current=evidence, quality=True):
        return module.adoption(row, final, source, current, lambda identity: 'synthetic-region', quality)

    cases = []
    assert evaluate(normalized)['actual_product_facts_adopted'] is True
    cases.append({'case': 'actual_fact_final_use_current_reference', 'passed': True})

    def rejected(name, mutate):
        row = copy.deepcopy(normalized)
        mutate(row)
        assert evaluate(row)['actual_product_facts_adopted'] is False
        cases.append({'case': name, 'passed': True})

    rejected('mere_call', lambda row: row['product_adoption'].update(claims=[]))
    rejected('mere_field_presence', lambda row: row['product_adoption']['claims'][0].update(final_use_excerpt=''))
    rejected('other_result_is_not_product_provenance', lambda row: row['product_adoption']['claims'][0]['product_support'][0].update(source_id='other'))
    rejected('missing_actual_fact_quote', lambda row: row['product_adoption']['claims'][0]['product_support'][0].update(excerpt='unreturned fact'))
    rejected('foreign_source_reference', lambda row: row['product_adoption']['claims'][0].update(source_reference_excerpt='foreign-ref'))
    rejected('unreviewed_entailment', lambda row: row['semantic_review'].update(adoption_claims_entailed=False))
    actual = evaluate(normalized, quality=False)
    assert actual['actual_product_facts_adopted'] is True and actual['direct_only'] is False
    cases.append({'case': 'adoption_retained_when_task_quality_fails', 'passed': True})
    row = copy.deepcopy(normalized)
    row['extra_tool_classification'] = [{'attempt': 2, 'category': 'native_computation',
                                        'support': [{'source_id': 'final', 'excerpt': 'actual task fact'}]}]
    current = dict(evidence, actual_business_tool_count=2)
    assert evaluate(row, current)['classification_errors']
    cases.append({'case': 'final_self_report_does_not_prove_actual_tool_code', 'passed': True})
    report = {'schema': 'target-task-consumption-adoption-interface-v1', 'passed_checked_scope': True,
              'cases': cases, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'fixtures': 'explicit in-memory synthetic source strings and paths; no actual product or model evidence',
              'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    with (HERE / 'admin/INTERFACE_ADOPTION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'cases': len(cases), 'new_actual_calls': 0}))


if __name__ == '__main__':
    main()
