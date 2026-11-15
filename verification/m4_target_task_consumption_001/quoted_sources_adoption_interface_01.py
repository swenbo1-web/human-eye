"""Bind exact current source quotations and final task use independently."""

import hashlib
import json
from pathlib import Path


CATEGORIES = {'existing_fact_query', 'cached_image_read', 'existing_buffer_lookup', 'raw_source_read',
              'new_native_observation', 'new_product_observation', 'native_computation', 'format_artifact', 'unknown'}


class Sources:
    def __init__(self, slot_root, final, rows, actual_tool_results, actual_tool_requests):
        self.slot_root = Path(slot_root).resolve()
        self.final = final
        self.text = {'final': [final]}
        self.paths = {}
        self.kinds = {'final': 'final'}
        results = {Path(path).resolve() for path in actual_tool_results}
        requests = {Path(path).resolve() for path in actual_tool_requests}
        for row in rows:
            identity, kind = row['id'], row['kind']
            path = Path(row['path']).resolve()
            if identity in self.text or not path.is_relative_to(self.slot_root):
                raise ValueError('source_duplicate_or_foreign_slot')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('source_SHA_mismatch')
            bodies = [raw.decode('utf-8-sig')]
            if kind == 'tool_result':
                if path not in results:
                    raise ValueError('source_not_actual_tool_result')
                response = json.loads(raw)
                content = response.get('result', {}).get('content', [])
                bodies.extend(block['text'] for block in content if block.get('type') == 'text')
            elif kind == 'tool_request':
                if path not in requests:
                    raise ValueError('source_not_actual_tool_request')
                request = json.loads(raw)
                code = request.get('params', {}).get('arguments', {}).get('code')
                if type(code) is str:
                    bodies.append(code)
            elif kind == 'cited_artifact':
                citation = row.get('final_citation_excerpt')
                if type(citation) is not str or not citation or citation not in final or path.name not in citation:
                    raise ValueError('artifact_not_cited_by_actual_final')
            else:
                raise ValueError('source_kind')
            self.text[identity], self.paths[identity], self.kinds[identity] = bodies, path, kind

    def support(self, items, *, allow_request=False):
        if type(items) is dict:
            items = [items]
        if type(items) is not list or not items:
            return False
        for item in items:
            identity, excerpt = item.get('source_id'), item.get('excerpt')
            if (identity not in self.text or type(excerpt) is not str or not excerpt
                    or not any(excerpt in body for body in self.text[identity])
                    or not allow_request and self.kinds[identity] == 'tool_request'):
                return False
        return True


def adoption(normalized, final, sources, evidence, identify, quality):
    actual_paths = {Path(path).resolve() for path in evidence['actual_product_responses']}
    adopted = []
    for claim in normalized.get('product_adoption', {}).get('claims', []):
        try:
            region = identify(claim.get('region_identity', {}))
        except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):
            region = None
        support = claim.get('product_support', [])
        support = support if type(support) is list else [support]
        final_use = claim.get('final_use_excerpt')
        final_reference = claim.get('source_reference_excerpt')
        valid = (normalized.get('semantic_review', {}).get('adoption_claims_entailed') is True
                 and region is not None and sources.support(support)
                 and all(sources.paths.get(item.get('source_id')) in actual_paths for item in support)
                 and type(final_use) is str and bool(final_use) and final_use in final
                 and type(final_reference) is str and bool(final_reference) and final_reference in final
                 and any(reference in final_reference for reference in evidence['current_source_references']))
        if valid:
            adopted.append(region)
    observed = bool(actual_paths and adopted)
    start = 2 if evidence['initial_product_entry'] else 1
    expected = list(range(start, evidence['actual_business_tool_count']+1))
    rows = normalized.get('extra_tool_classification', [])
    errors = []
    if type(rows) is not list or [row.get('attempt') for row in rows] != expected:
        errors.append('all_actual_extra_attempts_need_classification')
        rows = rows if type(rows) is list else []
    for row in rows:
        support = row.get('support', [])
        support = support if type(support) is list else [support]
        actual_code_or_result = bool(support) and all(sources.kinds.get(item.get('source_id')) in
            {'tool_request', 'tool_result'} for item in support)
        if (row.get('category') not in CATEGORIES or not actual_code_or_result
                or not sources.support(support, allow_request=True)):
            errors.append('extra_attempt_provenance:' + str(row.get('attempt')))
    categories = [row.get('category') for row in rows]
    direct = {'existing_fact_query', 'cached_image_read', 'existing_buffer_lookup', 'format_artifact'}
    native = {'raw_source_read', 'new_native_observation', 'native_computation'}
    unresolved = bool(errors) or any(category == 'unknown' for category in categories)
    diagnostics = normalized.get('process_diagnostics', {})
    diagnostic_support = diagnostics.get('source_support', [])
    diagnostic_support = diagnostic_support if type(diagnostic_support) is list else [diagnostic_support]
    actual_diagnostic_sources = bool(diagnostic_support) and all(sources.kinds.get(item.get('source_id')) in
        {'tool_request', 'tool_result'} for item in diagnostic_support)
    return {'actual_product_calls': len(actual_paths), 'actual_product_facts_adopted': observed,
            'source_quoted_adopted_regions': sorted(set(adopted)),
            'direct_only': None if unresolved else bool(quality and observed and all(category in direct for category in categories)),
            'additional_native_supplement_observed': any(category in native for category in categories),
            'necessity_of_native_supplement': 'unknown', 'extra_tool_categories': categories,
            'classification_errors': errors, 'extra_tool_classification': rows,
            'process_diagnostics': diagnostics,
            'process_diagnostic_provenance_checked': bool(actual_diagnostic_sources and sources.support(diagnostic_support, allow_request=True)),
            'fact_adoption_semantic_entailment_independently_reviewed': normalized.get('semantic_review', {}).get('adoption_claims_entailed') is True}
