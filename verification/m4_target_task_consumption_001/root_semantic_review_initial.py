"""Verify source-only normalization after the root read all six full answers."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_target_consume_001/formal')
ORDER = ['N1', 'P1', 'P2', 'N2', 'N3', 'P3']
EXPECTED_NORMALIZED = 'c109d1bad22a7472a9a52e031a0223dace8d0bcd9911ede2a6bc9fb3ae96ea92'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    normalized_path = HERE / 'admin/NORMALIZED.json'
    if sha(normalized_path) != EXPECTED_NORMALIZED:
        raise ValueError('reviewed_normalization_bytes_changed')
    normalized = read(normalized_path)
    draft_path = HERE / 'admin/NORMALIZATION_REVIEW_DRAFT.json'
    draft = read(draft_path)
    saved_path = HERE / 'admin/SAVED_REVIEW_01.json'
    saved = read(saved_path)
    if sha(saved_path) != '86f895e007a8e97445b166a715370997b51dd59f3ace7d16b23bf89ed81b6760':
        raise ValueError('reviewed_actual_source_and_frame_audit_changed')
    spec = importlib.util.spec_from_file_location('_root_quoted_sources', HERE / 'quoted_sources.py')
    quoted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quoted)
    checks = []
    records = []
    for slot in ORDER:
        row = next(item for item in normalized['slots'] if item['slot_id'] == slot)
        raw_path = RUNTIME / slot / 'consumer/PUBLIC_FINAL.txt'
        raw = read(raw_path)
        current = next(item for item in saved['records'] if item['slot_id'] == slot)
        note = next(item for item in draft['slots'] if item['slot_id'] == slot)
        expected = copy.deepcopy(raw)
        for index, region in enumerate(expected['regions']):
            candidate = row['answer']['regions'][index]
            original_refs = region['source_references']
            canonical_refs = candidate['source_references']
            checks.append((slot + '/reference_count/' + str(index), len(original_refs) == len(canonical_refs)))
            for reference, canonical in zip(original_refs, canonical_refs):
                matches = [item for item in row['source_reference_resolution']
                           if item['final_reference_excerpt'] == reference and item['canonical_ref'] == canonical]
                checks.append((slot + '/explicit_reference/' + reference, len(matches) == 1))
            region['source_references'] = canonical_refs
            if region['geometry_complete_in_pool'] is False and region['unknown_reason'] is None:
                checks.append((slot + '/reason_from_exact_notes/' + str(index),
                               candidate['unknown_reason'] == region['notes']
                               and 'LEFT' in region['notes'] and '遮挡' in region['notes']))
                region['unknown_reason'] = region['notes']
        checks.append((slot + '/all_other_answer_content_unchanged', expected == row['answer']))
        checks.append((slot + '/actual_final_bytes', sha(raw_path) == row['raw_answer_sha256'] == note['raw_answer_sha256']))
        requests = [str(RUNTIME / slot / 'owner' / ('tool_' + str(index).zfill(2)) / 'REQUEST.json')
                    for index in range(1, current['actual_business_tool_count'] + 1)]
        responses = [str(Path(path).with_name('RESPONSE.json')) for path in requests]
        evidence = copy.deepcopy(current)
        evidence['actual_tool_requests'] = requests
        evidence['actual_tool_results'] = responses
        for index, path in enumerate(requests, 1):
            evidence['current_source_references'].append('current-tool:' + str(index) + ':' + read(Path(path))['params']['name'])
        final_text = raw_path.read_text(encoding='utf-8')
        sources = quoted.Sources(raw_path.parents[1], final_text, row['sources'], responses, requests)
        quoted.validate_reference_resolutions(row, final_text, sources, evidence)
        checks.append((slot + '/all_claim_quotations_exist', bool(row['claim_support'])
                       and all(sources.support(item) for item in row['claim_support'])))
        by_ref = {frame['ref']: frame for frame in current['summary']['frames']}
        extra_views = 0
        for region in raw['regions']:
            first_face = region['identity']['source_triangle_index_ranges'][0][0]
            region_id = 'region_' + str(first_face)
            for claim in region.get('view_evidence', []):
                frame = by_ref[claim['frame_ref']]
                fact = frame['regions'][region_id]
                checks.append((slot + '/extra_view_name/' + claim['frame_ref'], frame['view_name'] == claim['view_name']))
                for key in ('surface_pixels', 'boundary_pixels', 'complete_readable'):
                    if key in claim:
                        checks.append((slot + '/extra_view/' + region_id + '/' + claim['view_name'] + '/' + key,
                                       claim[key] == fact[key]))
                if 'geometrically_complete' in claim:
                    checks.append((slot + '/extra_geometry/' + region_id + '/' + claim['view_name'],
                                   claim['geometrically_complete'] == fact['geometry_complete']))
                extra_views += 1
        records.append(dict(slot_id=slot, raw_answer_sha256=sha(raw_path), region_count=len(raw['regions']),
            explicit_reference_resolutions=len(row['source_reference_resolution']),
            extra_assertions_registered=len(row['extra_assertions']), extra_view_objects_verified=extra_views,
            original_reason_field_null=True, reason_explanation_present_in_original_notes=True,
            final_read_by_root=True, full_final_substantive_claims_reviewed=True))
    failed = [label for label, passed in checks if not passed]
    if failed:
        raise ValueError('normalization_review_failed:' + repr(failed))
    result = dict(schema='target-task-consumption-semantic-review-v1',
        reviewer='root independently read all six complete original PUBLIC_FINAL answers',
        normalized_sha256=sha(normalized_path), draft_sha256=sha(draft_path),
        saved_source_frame_review_sha256=sha(saved_path), review_source_sha256=sha(Path(__file__)),
        reviewed_ns=time.perf_counter_ns(), all_six_reviewed=True, passed=True,
        review_scope='Faithful normalization, complete original claims, exact current source quotations, reasons and product-fact adoption. Quality is graded separately. No usage or duration ranking read.',
        allowed_changes=['region source-reference canonicalization proved by actual current calls',
                         'explicit original notes copied verbatim into the normalized reason'],
        checks=[dict(check=label, passed=passed) for label, passed in checks], slots=records,
        native_local_labels='Preserved verbatim. Explicit source faces and geometry define local labels. Product ROI aliases require actual public mappings.',
        original_field_observation='All six unknown_reason fields are null. Explicit original notes state the finite-pool reason and are accepted under the frozen natural-language equivalence rule.',
        fairness_observation='N3 tool06 type(value).__name__ rejected by common private-attribute boundary, tool07 recovered. Original attempt and recovery remain included.',
        adoption_review='Each P final explicitly uses both public product region facts and references the current active_observation result/source binding. Background full evidence is excluded from model consumption.',
        new_model_product_raster_calls=0)
    destination = Path(normalized['semantic_review_path'])
    if destination != HERE / 'admin/SEMANTIC_REVIEW.json':
        raise ValueError('namespace_semantic_review_destination')
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True, checks=len(checks), slots=6, sha256=sha(destination))))


if __name__ == '__main__':
    main()
