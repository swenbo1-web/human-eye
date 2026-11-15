"""Source-only transcriptions using explicit, independently reviewable annotations.

The algorithm reads actual finals, owner tool records and SOURCE_ANNOTATIONS.
It reads no truth, usage or timing/ranking file and executes no product/model.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def literal(value, final):
    if value in final:
        return value
    encoded = json.dumps(value, ensure_ascii=False)[1:-1]
    require(bool(encoded) and encoded in final, 'annotation_excerpt_not_in_actual_final')
    return encoded


def extract_answer(final):
    candidates = []
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', final):
        try:
            value, length = decoder.raw_decode(final[match.start():])
        except ValueError:
            continue
        if type(value) is dict and ('regions' in value or 'measurement' in value):
            candidates.append((value, match.start(), match.start()+length))
    if len(candidates) != 1:
        return {}, final, {'parser_status': 'missing_or_ambiguous_structured_answer', 'candidate_count': len(candidates)}
    value, start, end = candidates[0]
    return value, final[start:end], {'parser_status': 'one_structured_answer',
                                    'text_before_json': final[:start], 'text_after_json': final[end:]}


def leaves(value, path='$'):
    if type(value) is dict:
        return [row for key, item in value.items() for row in leaves(item, path+'.'+key)]
    if type(value) is list:
        return [row for index, item in enumerate(value) for row in leaves(item, path+'['+str(index)+']')]
    return [{'json_path': path, 'actual_value': value, 'binding': 'Original parsed JSON value bound to raw_answer_sha256.'}]


def location(answer, path):
    require(path.startswith('$.'), 'annotation_JSON_path')
    tokens = re.findall(r'([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]', path[2:])
    current = answer
    keys = [int(index) if index else key for key, index in tokens]
    require(bool(keys), 'annotation_empty_JSON_path')
    for key in keys[:-1]:
        current = current[key]
    return current, keys[-1]


def normalize_slot(slot, root, annotation):
    folder = root / slot
    final_path = folder / 'consumer/PUBLIC_FINAL.txt'
    if not final_path.is_file():
        return {'slot_id': slot, 'raw_answer_path': None, 'raw_answer_sha256': None, 'answer': {},
                'answer_excerpt': '', 'sources': [], 'claim_support': [], 'execution_observation': 'raw_final_missing'}
    final = final_path.read_bytes().decode('utf-8')
    original, excerpt, parser = extract_answer(final)
    answer = copy.deepcopy(original)
    sources = []
    tools = read(folder / 'owner/TOOLS.json')['tools']
    requests, responses = {}, {}
    for tool in tools:
        attempt = tool['attempt']
        for kind, name in (('tool_request', 'REQUEST'), ('tool_result', 'RESPONSE')):
            path = folder / 'owner' / f'tool_{attempt:02}' / (name+'.json')
            sources.append({'id': f'tool_{attempt:02}_' + ('request' if kind == 'tool_request' else 'result'),
                            'kind': kind, 'path': str(path), 'sha256': sha(path)})
            (requests if kind == 'tool_request' else responses)[attempt] = read(path)
    sources.extend(copy.deepcopy(annotation.get('cited_artifact_sources', [])))
    changes, resolutions = [], []
    for row in annotation.get('source_reference_resolution', []):
        row = copy.deepcopy(row)
        container, key = location(answer, row['json_path'])
        require(type(container[key]) is str and bool(container[key]) and container[key] == row['original_reference'],
                'reference_transcription_must_start_from_actual_nonempty_citation')
        row['final_reference_excerpt'] = literal(row['original_reference'], final)
        container[key] = row['canonical_ref']
        resolutions.append(row)
        changes.append({'json_path': row['json_path'], 'raw_value': row['original_reference'],
                        'normalized_value': row['canonical_ref'], 'kind': 'explicit_current_reference_canonicalization'})
    reason_codes = {}
    for row in annotation.get('region_reasons', []):
        region = answer['regions'][row['region_index']]
        source_region = original['regions'][row['region_index']]
        reason = source_region.get('unknown_reason')
        if reason is None:
            reason = source_region.get('notes')
            require(type(reason) is str and bool(reason), 'missing_reason_cannot_be_filled')
            region['unknown_reason'] = reason
            changes.append({'json_path': f"$.regions[{row['region_index']}].unknown_reason", 'raw_value': None,
                            'normalized_value': reason, 'source_excerpt': literal(reason, final),
                            'kind': 'explicit_notes_reason_equivalence'})
        require(type(reason) is str and bool(reason), 'reason_must_be_asserted_in_actual_final')
        reason_codes[row['source_region_id']] = row['reason_code']
    adoption = copy.deepcopy(annotation.get('product_adoption', {'claims': []}))
    for claim in adoption.get('claims', []):
        if claim.get('kind') == 'observation':
            claim['region_identity'] = copy.deepcopy(answer['regions'][claim.pop('region_index')])
        for key in ('final_use_excerpt', 'source_reference_excerpt'):
            claim[key] = literal(claim[key], final)
    diagnostics = copy.deepcopy(annotation.get('process_diagnostics', {}))
    diagnostic_support = []
    for attempt, request in requests.items():
        code = request.get('params', {}).get('arguments', {}).get('code')
        diagnostic_support.append({'source_id': f'tool_{attempt:02}_request',
                                   'excerpt': code if type(code) is str else
                                   (folder/'owner'/f'tool_{attempt:02}'/'REQUEST.json').read_bytes().decode('utf-8')})
    diagnostics['source_support'] = diagnostic_support
    return {'slot_id': slot, 'raw_answer_path': str(final_path), 'raw_answer_sha256': sha(final_path),
            'answer': answer, 'answer_excerpt': excerpt, 'sources': sources,
            'claim_support': [{'source_id': 'final', 'excerpt': final}],
            'source_reference_resolution': resolutions, 'region_reason_codes': reason_codes,
            'normalization_changes': changes, 'raw_field_observations': parser,
            'entire_final_json_leaves': leaves(original),
            'extra_assertions': copy.deepcopy(annotation.get('extra_assertions', [])),
            'extra_assertion_errors': copy.deepcopy(annotation.get('extra_assertion_errors', [])),
            'contradictions': copy.deepcopy(annotation.get('contradictions', [])),
            'semantic_review': copy.deepcopy(annotation.get('semantic_review', {})),
            'product_adoption': adoption,
            'declared_hash_schemes': copy.deepcopy(annotation.get('declared_hash_schemes', {})),
            'extra_tool_classification': copy.deepcopy(annotation.get('extra_tool_classification', [])),
            'process_diagnostics': diagnostics}


def normalize(runtime, annotations):
    data = read(annotations)
    rows = data['slots']
    require(len(rows) == 6 and {row['slot_id'] for row in rows} == set(ORDER), 'six_unique_source_annotations')
    return {'schema': 'm5-task-consumption-normalized-v1',
            'semantic_review_path': str(HERE / 'admin/SEMANTIC_REVIEW.json'),
            'slots': [normalize_slot(slot, runtime, next(row for row in rows if row['slot_id'] == slot)) for slot in ORDER],
            'source_annotation_path': str(annotations), 'source_annotation_sha256': sha(annotations),
            'source_only_no_truth_fill': True, 'normalizer_sha256': sha(Path(__file__)),
            'cost_analysis_performed': False, 'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_m5_task_consume_001/formal'))
    parser.add_argument('--annotations', type=Path, default=HERE/'admin/SOURCE_ANNOTATIONS.json')
    parser.add_argument('--output', type=Path, default=HERE/'admin/NORMALIZED.json')
    args = parser.parse_args()
    report = normalize(args.runtime_root, args.annotations)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'slots': 6, 'normalized_sha256': sha(args.output), 'cost_analysis_performed': False}))
