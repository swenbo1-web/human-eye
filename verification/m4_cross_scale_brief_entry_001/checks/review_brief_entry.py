"""Review the sealed brief-entry run against the historical P1 tool ledger."""

import argparse
from collections import Counter
from fractions import Fraction
import json
import math
from pathlib import Path
import runpy


NS = Path(__file__).resolve().parents[1]
HISTORY = NS.parent / 'm4_cross_scale_live_task_formal_001'
RUNTIME = Path('D:/he_m4_cross_scale_brief_entry_001')
HISTORICAL_RUNTIME = Path('D:/he_m4_cross_scale_live_task_formal_001')
PRODUCT_TOOL = 'human_eye_scene_observe'
P1 = 'P1'
TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
LABELS = (
    'primary_observation', 'source_or_buffer_inspection', 'derived_required_numeric_fact',
    'independent_geometry_confirmation', 'additional_occluder_evidence',
    'independent_same_fact_recheck', 'additional_witness', 'error_recovery',
    'repeated_observation', 'no_evidence',
)
# These tags classify the existing historical review. Several calls had more than one effect.
HISTORICAL_LABELS = (
    ('primary_observation',),
    ('source_or_buffer_inspection',),
    ('independent_geometry_confirmation', 'derived_required_numeric_fact'),
    ('error_recovery',),
    ('source_or_buffer_inspection', 'error_recovery'),
    ('additional_occluder_evidence', 'error_recovery'),
    ('repeated_observation',),
    ('source_or_buffer_inspection',),
    ('independent_same_fact_recheck',),
    ('no_evidence',),
    ('repeated_observation',),
)


def p1(rows, key):
    matching = [row for row in rows if row[key] == P1]
    if len(matching) != 1:
        raise ValueError('expected_exactly_one_P1')
    return matching[0]


def audit(namespace, runtime):
    # Reuse the original checker without changing the historical code or files.
    old = runpy.run_path(str(HISTORY / 'checks/review_actual_tools.py'))
    check = old['audit_slot']
    check.__globals__.update(NS=namespace, RUNTIME=runtime)
    seal = p1(old['read'](namespace / 'ANSWERS_SEALED.json')['answers'], 'slot')
    ledger, answer = check(seal)
    old['require']([row['attempt'] for row in ledger['attempts']] ==
                   list(range(1, len(ledger['attempts']) + 1)), 'incomplete_business_attempt_sequence')
    return old, ledger, answer


def wire(attempt, side, read):
    return read(Path(attempt[side]['path']))


def text_blocks(response):
    return [row['text'] for row in (response.get('result') or {}).get('content', []) if row['type'] == 'text']


def numeric_near(left, right):
    return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-8)


def first_region_rows(public, truth):
    task = public.get('region_task') or (public.get('facts') or {}).get('region_task') or {}
    expected = {row['object_name']: row for row in truth['eligible']}
    rows = []
    for row in task.get('rows', []):
        name = row.get('object_name')
        current = expected.get(name, {})
        u, v = row.get('half_edge_u_world_m'), row.get('half_edge_v_world_m')
        area = None
        if u and v:
            a, b, c = (float(Fraction(x)) for x in u)
            d, e, f = (float(Fraction(x)) for x in v)
            area = 4 * math.hypot(b*f - c*e, c*d - a*f, a*e - b*d)
        normal = row.get('front_direction_world')
        unit = None
        if normal:
            direction = [float(Fraction(x)) for x in normal]
            length = math.hypot(*direction)
            if length:
                unit = [x / length for x in direction]
        center = row.get('center_world_m')
        source = row.get('source')
        rows.append({
            'object_name': name, 'source_triangle_indices': row.get('source_triangle_indices'),
            'center_world_m': center, 'direct_area_m2': row.get('area_m2'), 'derived_area_m2': area,
            'direct_front_direction_world': normal, 'normalized_front_direction_world': unit,
            'derived_area_matches_frozen_truth': bool(current and area is not None and
                                                     numeric_near(area, current['area_m2'])),
            'normalized_direction_matches_frozen_unit_normal': bool(current and unit and len(unit) == 3 and
                all(numeric_near(a, b) for a, b in zip(unit, current['unit_normal'], strict=True))),
            'center_matches_frozen_truth': bool(current and center and len(center) == 3 and
                all(numeric_near(float(Fraction(a)), float(Fraction(b)))
                    for a, b in zip(center, current['center_world_m'], strict=True))),
            'source_triangle_indices_match_frozen_truth': bool(current and
                row.get('source_triangle_indices') == current['source_triangle_indices']),
            'source_binding_present': bool(source), 'status': row.get('status'), 'reason': row.get('reason'),
            'complete_witness': row.get('complete_witness'), 'view_reasons': row.get('view_reasons'),
        })
    return rows


def product_first(ledger, old, truth):
    attempts = ledger['attempts']
    first_business = attempts[0] if attempts else None
    first_requested = next((a for a in attempts if a['tool'] == PRODUCT_TOOL), None)
    first_executed = next((a for a in attempts if a['product']), None)

    def submitted(attempt):
        if not attempt:
            return None
        req = wire(attempt, 'TX', old['read'])
        return {'attempt': attempt['attempt'], 'tool': attempt['tool'], 'wire': attempt['TX'],
                'requested_detail': req['params']['arguments'].get('response_detail'),
                'is_error': attempt['is_error']}

    executed = None
    if first_executed:
        response = wire(first_executed, 'RX', old['read'])
        public = old['facts_from_first']((response.get('result') or {}).get('content', []))
        delivery = first_executed['product']
        executed = {
            'attempt': first_executed['attempt'], 'request': delivery['request'],
            'response': delivery.get('response'), 'response_detail': delivery['arguments'].get('response_detail'),
            'arguments': delivery['arguments'], 'top_level_keys': list(public),
            'response_schema': public.get('schema'),
            'public_CLI_envelope_bound': first_executed['model_visible_as_public_CLI_tool_result'],
            'text_UTF8_bytes': first_executed['text_UTF8_bytes'],
            'image_block_sequence': [row['sha256'] for row in first_executed['image_blocks']],
            'region_rows': first_region_rows(public, truth), 'binding_present': bool(public.get('binding')),
            'is_error': first_executed['is_error'],
        }
    # A later brief does not repair an initial implicit or explicit non-brief product request.
    requested = submitted(first_requested)
    reached = bool(requested and executed and requested['attempt'] == executed['attempt'] and
                   requested['requested_detail'] == executed['response_detail'] == 'brief')
    return {
        'first_business_attempt': submitted(first_business), 'first_product_attempt': requested,
        'first_installed_product_execution': executed, 'explicit_brief_treatment_received': reached,
        'explicit_brief_on_first_business_attempt': bool(reached and
            first_business['attempt'] == executed['attempt']),
        'brief_successfully_delivered_to_public_CLI': bool(reached and
            not executed['is_error'] and executed['public_CLI_envelope_bound']),
    }


def bind_observations(old, ledger, answer, notes):
    attempts = ledger['attempts']
    increments = notes['increments']
    old['require']([row['attempt'] for row in increments] == [a['attempt'] for a in attempts],
                   'increment_rubric_does_not_cover_actual_business_attempts')
    old['require'](all(answer and s in answer for s in notes['quoted_final_anchors']),
                   'provided_adoption_anchors_not_in_same_slot_answer')
    used_images = {}
    reviewed = []
    for raw, note in zip(attempts, increments, strict=True):
        response = wire(raw, 'RX', old['read'])
        bodies = text_blocks(response)
        labels = note['labels']
        old['require'](labels and len(set(labels)) == len(labels) and not set(labels) - set(LABELS),
                       'unknown_or_duplicate_increment_label')
        old['require'](all(anchor and any(anchor in body for body in bodies) for anchor in note['response_anchors']),
                       'increment_anchor_not_in_original_response')
        repeated_images = []
        for image in raw['image_blocks']:
            key = image['sha256']
            if key in used_images:
                repeated_images.append({'PNG_sha256': key, 'first_attempt': used_images[key]})
            used_images.setdefault(key, raw['attempt'])
        reviewed.append({**raw, 'editorial_assessment': note, 'identical_earlier_PNGs': repeated_images})
    return reviewed


def adoption(ledger, answer, quality, evidence, first, old):
    old['require'](ledger['answer_sha256'] == quality['answer_sha256'] == evidence['answer_sha256'],
                   'same_slot_answer_grade_or_evidence_sha_differs')
    first_number = (first['first_installed_product_execution'] or {}).get('attempt')
    adopted = {}
    for name in ('M02', 'M09'):
        criterion = quality['criteria'][f'witness_{name}']
        ref = criterion.get('resolved_delivered_ref')
        frame = evidence.get('frames', {}).get(ref)
        if criterion['status'] == 'pass':
            old['require'](answer and ref and ref in answer and frame and frame['witnesses'][name]['qualifies'],
                           'graded_witness_is_not_an_adopted_verified_original/' + name)
        receipts = frame.get('delivery', []) if frame else []
        adopted[name] = {'score_status': criterion['status'], 'ref': ref,
                         'delivery_attempts': [r['attempt'] for r in receipts],
                         'first_installed_product_image_adopted': any(
                            r['attempt'] == first_number for r in receipts),
                         'independent_pixels': (frame['witnesses'][name] if frame else None)}
    return adopted


def costs(ledger, runtime):
    attempts = runtime['attempts']
    raw_usage = runtime['original_CLI_usage']
    ledger_attempts = ledger['attempts']
    span_keys = (
        'full_window_ms', 'startup_to_ready_ms', 'startup_to_answer_ms', 'answer_to_publish_ms',
        'prompt_to_first_successful_evidence_ms', 'first_successful_evidence_to_answer_ms',
        'last_tool_to_answer_ms', 'tool_text_total_bytes', 'tool_image_total_bytes',
    )
    totals = {key: runtime.get(key) for key in span_keys}
    for key, start in (('tool_request_to_CLI_result_ms', 0), ('previous_CLI_result_to_tool_request_ms', 1)):
        values = [a.get(key) for a in attempts[start:]]
        totals[key] = sum(values) if values and all(value is not None for value in values) else None
    totals.update({'business_attempts': len(ledger_attempts), 'tool_errors': sum(a['is_error'] for a in ledger_attempts),
                   'actual_rasters': (runtime.get('budget_slot') or {}).get('raster_actual')})
    for key in ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens',
                'reasoning_output_tokens'):
        totals[f'CLI_{key}'] = sum(row[key] for row in raw_usage) if raw_usage and all(
            key in row for row in raw_usage) else None
    return totals


def comparison(new, historical):
    return {key: {'historical_full': historical[key], 'brief_entry': value,
                  'observed_difference': value - historical[key] if value is not None and
                  historical[key] is not None else None} for key, value in new.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-self-check', action='store_true')
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--output', type=Path, default=NS / 'checks/BRIEF_ENTRY_REVIEW.json')
    args = parser.parse_args()
    old, baseline, base_answer = audit(HISTORY, HISTORICAL_RUNTIME)
    read, exact, require = (old[k] for k in ('read', 'exact', 'require'))
    truth_path = HISTORY / 'fixture/CURRENT_TRUTH.json'
    require(exact(truth_path)['sha256'] == TRUTH_SHA, 'frozen_area_normal_and_source_oracle_changed')
    truth = read(truth_path)
    baseline_first = product_first(baseline, old, truth)
    history_notes = read(HISTORY / 'checks/TOOL_OBSERVATIONS.json')[P1]
    tagged = {
        'quoted_final_anchors': history_notes['quoted_final_anchors'],
        'increments': [{**row, 'labels': tags, 'response_anchors': []} for row, tags in
                       zip(history_notes['increments'], HISTORICAL_LABELS, strict=True)],
    }
    historical = bind_observations(old, baseline, base_answer, tagged)
    historical_runtime_path = HISTORY / 'RUNTIME_REVIEW.json'
    historical_cost = costs(baseline, p1(read(historical_runtime_path)['slots'], 'label'))
    require(baseline_first['first_installed_product_execution']['text_UTF8_bytes'] == 359581 and
            baseline_first['first_installed_product_execution']['response_detail'] == 'full' and
            historical_cost['business_attempts'] == 11 and historical_cost['actual_rasters'] == 12 and
            [a['attempt'] for a in historical if a['identical_earlier_PNGs']] == [11],
            'historical_P1_observed_cost_or_first_product_delivery_differs')
    if args.historical_self_check:
        print(json.dumps({'historical_first': baseline_first, 'historical_cost': historical_cost}, ensure_ascii=False))
        return
    if args.observations is None:
        parser.error('--observations is required for a completed attribution review')

    current, ledger, answer = audit(NS, RUNTIME)
    runtime_path = NS / 'RUNTIME_REVIEW.json'
    quality_path = NS / 'scoring/QUALITY.json'
    evidence_path = NS / 'scoring/FORMAL_EVIDENCE.json'
    quality = p1(read(quality_path)['slots'], 'slot')
    evidence = p1(read(evidence_path)['slots'], 'slot')
    first = product_first(ledger, current, truth)
    current_product = first['first_installed_product_execution'] or {}
    historical_product = baseline_first['first_installed_product_execution']
    review = bind_observations(current, ledger, answer, read(args.observations))
    historical_tags = Counter(tag for a in historical for tag in a['editorial_assessment']['labels'])
    current_tags = Counter(tag for a in review for tag in a['editorial_assessment']['labels'])
    result = {
        'scope': 'One current P1 compared with one historical P1. Costs are observed differences. '
                 'Editorial tags can overlap. Actual supplier input, inference and fees are unmeasured.',
        'original_bindings': ledger['original_bindings'], 'answer_sha256': ledger['answer_sha256'],
        'runtime_status': ledger['status'], 'observations': exact(args.observations),
        'current_cost_source': exact(runtime_path), 'historical_cost_source': exact(historical_runtime_path),
        'historical_first': baseline_first, 'current_first': first,
        'same_ordered_PNG_bytes_as_historical_first': (current_product.get('image_block_sequence') ==
            historical_product['image_block_sequence']) if current_product else None,
        'quality_source': exact(quality_path), 'formal_evidence_source': exact(evidence_path),
        'quality': {'passed': quality['passed'], 'denominator': quality['denominator']},
        'adopted_witnesses': adoption(ledger, answer, quality, evidence, first, current),
        'observed_cost_comparison': comparison(costs(ledger, p1(read(runtime_path)['slots'], 'label')), historical_cost),
        'editorial_increment_comparison': comparison({label: current_tags[label] for label in LABELS},
                                                     {label: historical_tags[label] for label in LABELS}),
        'historical_attribution': exact(HISTORY / 'checks/TOOL_OBSERVATIONS.json'),
        'historical_exact_same_PNG_redelivery': [a['attempt'] for a in historical if a['identical_earlier_PNGs']],
        'current_attempts': review,
    }
    with args.output.open('x', encoding='utf8', newline='\n') as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True)
        output.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
