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
                for block in content:
                    if block.get('type') != 'text':
                        continue
                    bodies.append(block['text'])
                    try:
                        public = json.loads(block['text'])
                    except ValueError:
                        continue
                    if type(public) is dict:
                        bodies.extend(public[key] for key in ('stdout', 'stderr') if type(public.get(key)) is str)
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


def validate_reference_resolutions(normalized, final, sources, evidence):
    resolutions = normalized.get('source_reference_resolution', [])
    if type(resolutions) is not list:
        raise ValueError('source_reference_resolution_array')
    for row in resolutions:
        excerpt = row.get('final_reference_excerpt')
        attempt = row.get('tool_attempt')
        canonical = row.get('canonical_ref')
        support = row.get('support', [])
        support = support if type(support) is list else [support]
        if (type(excerpt) is not str or not excerpt or excerpt not in final
                or type(attempt) is not int or not 1 <= attempt <= len(evidence['actual_tool_results'])
                or canonical not in evidence['current_source_references']
                or row.get('unique_current_call') is not True
                or normalized.get('semantic_review', {}).get('reference_resolutions_entailed') is not True
                or not sources.support(support, allow_request=True)
                or not any(sources.paths.get(item.get('source_id')) == Path(evidence['actual_tool_results'][attempt-1]).resolve()
                           for item in support)):
            raise ValueError('unproved_current_tool_reference_resolution')
        request = json.loads(Path(evidence['actual_tool_requests'][attempt-1]).read_bytes())
        expected_tool_ref = 'current-tool:' + str(attempt) + ':' + request['params']['name']
        if canonical.startswith('current-tool:'):
            if canonical != expected_tool_ref:
                raise ValueError('canonical_tool_reference_attempt_mismatch')
        elif not any(canonical in body for item in support
                     if sources.paths.get(item.get('source_id')) == Path(evidence['actual_tool_results'][attempt-1]).resolve()
                     for body in sources.text[item['source_id']]):
            raise ValueError('canonical_hash_or_ref_not_publicly_delivered')
    if normalized.get('semantic_review', {}).get('no_missing_source_references_filled') is not True:
        raise ValueError('source_reference_nonempty_final_review_required')
    answer = normalized.get('answer', {})
    containers = list(answer.get('regions', []))
    if type(answer.get('measurement')) is dict:
        containers.append(answer['measurement'])
        containers.extend(answer['measurement'].get('object_source_bindings', []))
    if type(answer.get('observation_measurement_correspondence')) is dict:
        containers.append(answer['observation_measurement_correspondence'])
    containers.append(answer)
    for container in containers:
        for reference in container.get('source_references', []):
            if reference not in final and not any(row.get('canonical_ref') == reference for row in resolutions):
                raise ValueError('canonical_reference_without_final_citation')


def adoption(normalized, final, sources, evidence, identify, quality):
    actual_paths = {Path(path).resolve() for path in evidence['actual_product_responses']}
    calls = {row['index']: row for row in evidence['actual_public_calls']}
    observations, measurements, accepted, errors = [], [], [], []
    for claim in normalized.get('product_adoption', {}).get('claims', []):
        call = calls.get(claim.get('public_call_index'))
        support = claim.get('product_support', [])
        support = support if type(support) is list else [support]
        final_use = claim.get('final_use_excerpt')
        final_reference = claim.get('source_reference_excerpt')
        current_reference_used = (type(final_reference) is str and any(
            reference in final_reference for reference in evidence['current_source_references']))
        if type(final_reference) is str:
            current_reference_used = current_reference_used or any(
                row.get('final_reference_excerpt') in final_reference
                and row.get('canonical_ref') in evidence['current_source_references']
                for row in normalized.get('source_reference_resolution', []))
        valid = (normalized.get('semantic_review', {}).get('adoption_claims_entailed') is True
                 and call is not None and not call['is_error'] and sources.support(support)
                 and all(sources.paths.get(item.get('source_id')) in actual_paths for item in support)
                 and any(sources.paths.get(item.get('source_id')) == Path(call['outer_result_path']).resolve() for item in support)
                 and type(final_use) is str and bool(final_use) and final_use in final
                 and type(final_reference) is str and bool(final_reference) and final_reference in final
                 and current_reference_used)
        kind = claim.get('kind')
        if kind == 'observation':
            try:
                region = identify(claim.get('region_identity', {}))
            except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):
                region = None
            valid = valid and call['mode'] == 'active_observation' and region is not None
            if valid:
                observations.append((call['index'], region))
        elif kind == 'measurement':
            valid = valid and call['measurement'] is not None and claim.get('fact') == 'surface_proximity'
            if valid:
                measurements.append(call['index'])
        else:
            valid = False
        if valid:
            accepted.append({'kind': kind, 'public_call_index': call['index'], 'outer_attempt': call['outer_attempt']})
    observation_indices = {index for index, _ in observations}
    measurement_indices = set(measurements)
    joint_indices = observation_indices & measurement_indices & set(evidence['actual_joint_public_call_indices'])
    whole = normalized.get('answer', {}).get('measurement', {}).get('measurement_scope') == 'whole_objects'
    observed = bool(observations and measurements)
    joint = bool(joint_indices and whole)
    batch_used = bool(evidence['actual_batch_outer_attempts'])
    batch_fact_adoption = any(
        any(row['kind'] == 'observation' and row['outer_attempt'] == attempt for row in accepted)
        and any(row['kind'] == 'measurement' and row['outer_attempt'] == attempt for row in accepted)
        for attempt in evidence['actual_batch_outer_attempts'])
    expected = list(range(1, evidence['actual_business_tool_count']+1))
    rows = normalized.get('extra_tool_classification', [])
    if type(rows) is not list or [row.get('attempt') for row in rows] != expected:
        errors.append('all_actual_outer_attempts_need_classification')
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
    direct = {'existing_fact_query', 'cached_image_read', 'existing_buffer_lookup', 'format_artifact', 'new_product_observation'}
    native = {'raw_source_read', 'new_native_observation', 'native_computation'}
    unresolved = bool(errors) or any(category == 'unknown' for category in categories)
    diagnostics = normalized.get('process_diagnostics', {})
    diagnostic_support = diagnostics.get('source_support', [])
    diagnostic_support = diagnostic_support if type(diagnostic_support) is list else [diagnostic_support]
    actual_diagnostic_sources = bool(diagnostic_support) and all(sources.kinds.get(item.get('source_id')) in
        {'tool_request', 'tool_result'} for item in diagnostic_support)
    return {'actual_product_calls': len(calls), 'actual_product_outer_tool_results': len(actual_paths),
            'actual_product_facts_adopted': joint if normalized['slot_id'].startswith('B') else observed,
            'observation_facts_adopted': bool(observations), 'measurement_facts_adopted': bool(measurements),
            'whole_objects_scope_correct': whole, 'actual_joint_fact_adoption': joint,
            'source_quoted_joint_public_call_indices': sorted(joint_indices),
            'source_quoted_adopted_regions': sorted({region for _, region in observations}),
            'accepted_fact_adoption_claims': accepted,
            'actual_A_batch_used': batch_used, 'actual_A_batch_facts_adopted': batch_fact_adoption,
            'actual_batch_outer_attempts': evidence['actual_batch_outer_attempts'],
            'actual_joint_public_call_indices': evidence['actual_joint_public_call_indices'],
            'direct_only': None if unresolved else bool(quality and observed and all(category in direct for category in categories)),
            'additional_native_supplement_observed': any(category in native for category in categories),
            'necessity_of_native_supplement': 'unknown', 'extra_tool_categories': categories,
            'classification_errors': errors, 'extra_tool_classification': rows,
            'process_diagnostics': diagnostics,
            'process_diagnostic_provenance_checked': bool(actual_diagnostic_sources and sources.support(diagnostic_support, allow_request=True)),
            'fact_adoption_semantic_entailment_independently_reviewed': normalized.get('semantic_review', {}).get('adoption_claims_entailed') is True}
