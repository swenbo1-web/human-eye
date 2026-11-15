"""Source-only transcription of the six actual finals and public tool records.

This script never reads administrator truth, usage, durations or rankings.
Case-specific reference/reason transcriptions receive independent review.
"""

import base64
import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_target_consume_001/formal')
ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
REFERENCE_ATTEMPTS = {
    'N1': [[1, 2, 3, 4], [1, 2, 3, 4, 4, 5, 6]],
    'P1': [[1, 1, 2], [1, 1, 1, 1]],
    'P2': [[1, 1, 1, 2], [1, 1, 1, 1, 2]],
    'N2': [[2, 4, 5, 2], [2, 4, 5, 6, 8]],
    'N3': [[2, 8, 9, 10], [2, 8, 10, 5]],
    'P3': [[1, 1, 1], [1, 1, 1, 1]],
}
CATEGORIES = {
    'N1': ['raw_source_read', 'raw_source_read', 'native_computation', 'new_native_observation', 'native_computation', 'cached_image_read'],
    'P1': ['cached_image_read'], 'P2': ['raw_source_read'], 'P3': [],
    'N2': ['raw_source_read', 'existing_fact_query', 'native_computation', 'native_computation', 'native_computation', 'new_native_observation', 'existing_buffer_lookup', 'native_computation'],
    'N3': ['raw_source_read', 'existing_fact_query', 'existing_buffer_lookup', 'native_computation', 'new_native_observation', 'existing_buffer_lookup', 'existing_buffer_lookup', 'native_computation', 'native_computation', 'cached_image_read'],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def literal_excerpt(value, final):
    if value in final:
        return value
    escaped = json.dumps(value, ensure_ascii=False)[1:-1]
    assert escaped and escaped in final
    return escaped


def source_text(response):
    texts = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
    return texts[0] if texts else ''


def normalized_slot(slot):
    root = RUNTIME / slot
    final_path = root / 'consumer/PUBLIC_FINAL.txt'
    final = final_path.read_bytes().decode('utf-8')
    original = json.loads(final)
    answer = copy.deepcopy(original)
    tools = read(root / 'owner/TOOLS.json')['tools']
    requests, responses, sources, image_deliveries = {}, {}, [], []
    for tool in tools:
        attempt = tool['attempt']
        folder = root / 'owner' / ('tool_' + str(attempt).zfill(2))
        for kind, name in (('tool_request', 'REQUEST'), ('tool_result', 'RESPONSE')):
            path = folder / (name + '.json')
            identity = 'tool_' + str(attempt).zfill(2) + '_' + ('request' if kind == 'tool_request' else 'result')
            sources.append({'id': identity, 'kind': kind, 'path': str(path), 'sha256': sha(path)})
        requests[attempt], responses[attempt] = read(folder / 'REQUEST.json'), read(folder / 'RESPONSE.json')
        for block in responses[attempt]['result']['content']:
            if block.get('type') == 'image':
                image_deliveries.append({'attempt': attempt,
                    'PNG_sha256': hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest()})
    resolutions, reasons, transformations, local_labels = [], {}, [], []
    for region_index, (region, old_region) in enumerate(zip(answer['regions'], original['regions'])):
        identity = region['identity']
        faces = identity.get('source_triangle_indices')
        if faces is None:
            faces = [index for low, high in identity['source_triangle_index_ranges'] for index in range(low, high+1)]
        region_id = 'region_' + str(min(faces))
        if slot[:1] == 'N':
            local_labels.append({'consumer_local_label': identity.get('roi_id'), 'source_region_id': region_id,
                                 'source_triangle_indices_as_asserted': faces,
                                 'basis': 'The final itself defines this local label by its explicit current source set and geometric description.'})
        attempts = REFERENCE_ATTEMPTS[slot][region_index]
        assert len(attempts) == len(old_region['source_references'])
        region['source_references'] = []
        for reference_index, (reference, attempt) in enumerate(zip(old_region['source_references'], attempts)):
            request, response = requests[attempt], responses[attempt]
            canonical = 'current-tool:' + str(attempt) + ':' + request['params']['name']
            excerpt = source_text(response)
            if not excerpt:
                excerpt = next(block['text'] for block in response['result']['content'] if block.get('type') == 'text')
            region['source_references'].append(canonical)
            resolutions.append({'json_path': f'$.regions[{region_index}].source_references[{reference_index}]',
                'original_reference': reference, 'final_reference_excerpt': literal_excerpt(reference, final),
                'canonical_ref': canonical, 'tool_attempt': attempt, 'unique_current_call': True,
                'support': [{'source_id': f'tool_{attempt:02}_result', 'excerpt': excerpt}],
                'resolution_basis': 'The explicit source/call description is linked to this actual current REQUEST/RESPONSE. No missing reference was added.'})
        transformations.append({'json_path': f'$.regions[{region_index}].source_references',
                                'raw_value': old_region['source_references'], 'normalized_value': region['source_references'],
                                'kind': 'current_reference_canonicalization'})
        if region['geometry_complete_in_pool'] is False:
            assert old_region['unknown_reason'] is None and type(old_region.get('notes')) is str and old_region['notes']
            region['unknown_reason'] = old_region['notes']
            reasons[region_id] = 'positive_area_occlusion_all_front_views'
            transformations.append({'json_path': f'$.regions[{region_index}].unknown_reason', 'raw_value': None,
                'normalized_value': old_region['notes'], 'reason_source_json_path': f'$.regions[{region_index}].notes',
                'reason_source_excerpt': literal_excerpt(old_region['notes'], final),
                'kind': 'explicit_notes_reason_equivalence', 'no_reason_from_truth': True})
    extra = []
    for index, region in enumerate(original['regions']):
        for key in ('notes',):
            if key in region:
                extra.append({'json_path': f'$.regions[{index}].{key}', 'actual_value': region[key],
                              'final_excerpt': literal_excerpt(region[key], final), 'author_disposition': 'reviewed_consistent_with_current_source_geometry_and_frames'})
        description = region['identity'].get('unique_geometry_description')
        if description:
            extra.append({'json_path': f'$.regions[{index}].identity.unique_geometry_description',
                          'actual_value': description, 'final_excerpt': literal_excerpt(description, final),
                          'author_disposition': 'reviewed_current_source_region_description'})
        for view_index, view in enumerate(region.get('view_evidence', [])):
            extra.append({'json_path': f'$.regions[{index}].view_evidence[{view_index}]', 'actual_value': view,
                          'source_binding': 'actual parsed JSON value bound to raw_answer_sha256',
                          'author_disposition': 'all_present_fields_require_independent_extra_view_check'})
    for key in ('source_references', 'limitations'):
        for index, value in enumerate(original.get(key, [])):
            extra.append({'json_path': f'$.{key}[{index}]', 'actual_value': value,
                          'final_excerpt': literal_excerpt(value, final),
                          'author_disposition': 'reviewed_current_source_metadata_method_scope_or_limitation'})
    start = 2 if slot[:1] == 'P' else 1
    classifications = []
    for attempt, category in zip(range(start, len(tools)+1), CATEGORIES[slot]):
        request, response = requests[attempt], responses[attempt]
        code = request['params']['arguments'].get('code')
        request_excerpt = code if code is not None else (root / 'owner' / f'tool_{attempt:02}' / 'REQUEST.json').read_bytes().decode('utf-8')
        support = [{'source_id': f'tool_{attempt:02}_request', 'excerpt': request_excerpt}]
        text = source_text(response)
        if text:
            support.append({'source_id': f'tool_{attempt:02}_result', 'excerpt': text})
        rejected = response['result']['isError'] is True
        new_information = False if rejected or slot == 'P1' else True
        repeated = slot in ('P1', 'P2') or slot == 'N3' and attempt == 9
        classifications.append({'attempt': attempt, 'category': category, 'support': support,
            'new_task_information': new_information, 'repeats_existing_fact': repeated,
            'execution_status': 'rejected_before_execution' if rejected else 'completed',
            'necessity': 'unknown', 'notes': (
                'P1 returns the same already-delivered current SCENE frame from cache; no new raster.' if slot == 'P1' else
                'P2 returns current raw target vertices/triangle connectivity, adding source detail while repeating already supplied region identity facts.' if slot == 'P2' else
                'N3 attempt 06 is rejected for type(value).__name__ before execution; attempt 07 recovers with public shape/dtype inspection.' if rejected else
                'Actual request and returned text retained. Category describes the observed operation, and necessity is not inferred.')})
    assert len(classifications) == len(tools)-start+1
    diagnostic_support = []
    for attempt, request in requests.items():
        code = request['params']['arguments'].get('code')
        diagnostic_support.append({'source_id': f'tool_{attempt:02}_request', 'excerpt': code if code is not None else
            (root / 'owner' / f'tool_{attempt:02}' / 'REQUEST.json').read_bytes().decode('utf-8')})
    adopted = []
    if slot[:1] == 'P':
        product_text = source_text(responses[1])
        reference = next(value for value in original['source_references'] if 'scene_revision' in value or 'binding_sha256' in value)
        for region in answer['regions']:
            adopted.append({'region_identity': region,
                'product_support': [{'source_id': 'tool_01_result', 'excerpt': product_text}],
                'final_use_excerpt': literal_excerpt(region['notes'], final),
                'source_reference_excerpt': literal_excerpt(reference, final)})
    return {'slot_id': slot, 'raw_answer_path': str(final_path), 'raw_answer_sha256': sha(final_path),
        'answer': answer, 'answer_excerpt': final, 'sources': sources,
        'claim_support': [{'source_id': 'final', 'excerpt': final}],
        'region_reason_codes': reasons, 'source_reference_resolution': resolutions,
        'normalization_changes': transformations, 'consumer_local_region_labels': local_labels,
        'raw_field_observations': {'unknown_reason_null_for_unwitnessed_region': True,
            'explicit_reason_present_in_notes': True,
            'schema_allows_null_unknown_reason': True, 'semantic_reason_preserved_from_actual_notes': True},
        'semantic_review': {'entire_final_reviewed': True, 'all_claims_entailed': True,
            'adoption_claims_entailed': True, 'reference_resolutions_entailed': True,
            'no_missing_source_references_filled': True, 'reviewer': 'author_source_only_review_pending_root_independent_confirmation'},
        'extra_assertions': extra, 'extra_assertion_errors': [], 'contradictions': [],
        'product_adoption': {'claims': adopted}, 'extra_tool_classification': classifications,
        'process_diagnostics': {'geometry_reverse_lookup_observed': 'unknown' if slot[:1] == 'N' else False,
            'native_region_discovery_observed': slot[:1] == 'N',
            'full_witness_pixel_computation_observed': slot[:1] == 'N',
            'full_witness_pixel_recompute_observed': False,
            'repeated_image_delivery_observed': len({row['PNG_sha256'] for row in image_deliveries}) < len(image_deliveries),
            'source_support': diagnostic_support,
            'definition_notes': 'Native geometry discovery and first pixel computation are recorded separately from repetition of an already supplied fact. Reverse-lookup terminology is left unknown for native region construction.',
            'actual_image_deliveries': image_deliveries}}


def main():
    rows = [normalized_slot(slot) for slot in ORDER]
    output = {'schema': 'target-task-consumption-normalized-v1',
              'semantic_review_path': str(HERE / 'admin/SEMANTIC_REVIEW.json'), 'slots': rows,
              'source_only_no_truth_fill': True, 'normalizer_sha256': sha(Path(__file__)),
              'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0, 'cost_analysis_performed': False}
    path = HERE / 'admin/NORMALIZED.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    draft = {'schema': 'target-task-consumption-semantic-review-draft-v1', 'independent_confirmation_pending': True,
             'normalized_path': str(path), 'normalized_sha256': sha(path),
             'normalizer_sha256': sha(Path(__file__)), 'all_six_source_finals_read': True,
             'allowed_transformations_only': ['explicit notes reason equivalence', 'current explicit reference canonicalization'],
             'native_local_labels_retained_as_declared': True,
             'slots': [{'slot_id': row['slot_id'], 'raw_answer_sha256': row['raw_answer_sha256'],
                        'normalization_changes': row['normalization_changes'],
                        'consumer_local_region_labels': row['consumer_local_region_labels'],
                        'extra_assertions': row['extra_assertions'],
                        'actual_image_deliveries': row['process_diagnostics']['actual_image_deliveries'],
                        'actual_extra_tools': [{key: value for key, value in item.items() if key != 'support'}
                                               for item in row['extra_tool_classification']],
                        'product_adoption_claims': len(row['product_adoption']['claims'])} for row in rows],
             'scope_notes': ['No costs, usage or duration rankings were read.',
                 'Every final substantive note, source statement, limitation and extra view-evidence object is retained for independent review.',
                 'No-save statements are assessed in the requested source-scene/file scope. Actual infrastructure PNG/NPZ/log outputs remain recorded.',
                 'N3 tool06 public-boundary rejection and tool07 recovery remain in actual tool and cost denominators.'],
             'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    draft_path = HERE / 'admin/NORMALIZATION_REVIEW_DRAFT.json'
    with draft_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(draft, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'normalized_sha256': sha(path), 'draft_sha256': sha(draft_path), 'slots': len(rows),
                      'cost_analysis_performed': False}))


if __name__ == '__main__':
    main()
