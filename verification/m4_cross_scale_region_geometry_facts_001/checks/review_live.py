"""Review the single geometry-facts slot against the prior fresh brief slot."""

import argparse
from collections import Counter
from fractions import Fraction
import json
import math
from pathlib import Path
import runpy


NS = Path(__file__).resolve().parents[1]
RUN = Path('D:/he_m4_cross_scale_region_geometry_facts_001')
OLD = NS.parent / 'm4_cross_scale_brief_entry_001'
OLD_RUN = Path('D:/he_m4_cross_scale_brief_entry_001')
P1 = 'P1'
TOOL = 'human_eye_scene_observe'
ROSTER = ('M02', 'M06', 'M09')
NUMERIC_WORK = {'none', 'independent_source_geometry', 'rederived_from_product', 'exact_expression_from_prior'}


def numeric(value):
    return float(Fraction(value))


def near(left, right):
    return math.isclose(numeric(left), numeric(right), rel_tol=1e-8, abs_tol=1e-10)


def first_details(review, helpers, ledger, truth, packet):
    first = review['product_first'](ledger, helpers, truth)
    exec_record = first['first_installed_product_execution']
    export = packet['first_installed_product']
    require, read = helpers['require'], helpers['read']
    if exec_record is None or export is None:
        require(not (export and export.get('exact_CLI_delivery')) and
                not (exec_record and exec_record.get('public_CLI_envelope_bound') and not exec_record['is_error']),
                'successful_first_export_and_product_ledger_differ')
        return first
    attempt = ledger['attempts'][exec_record['attempt'] - 1]
    require(export['attempt'] == exec_record['attempt']
            and export['requested_detail'] == exec_record['response_detail']
            and export['request']['sha256'] == exec_record['request']['sha256']
            and export['exact_CLI_delivery'] == exec_record['public_CLI_envelope_bound'],
            'first_packet_does_not_bind_reviewed_product_execution')
    if export['response']:
        require(exec_record['response']['sha256'] == export['response']['sha256']
                and export['text_UTF8_bytes'] == exec_record['text_UTF8_bytes']
                and [image['sha256'] for image in export['original_PNGs']] == exec_record['image_block_sequence'],
                'first_packet_response_or_PNG_sequence_differs')
    response = review['wire'](attempt, 'RX', read)
    public = helpers['facts_from_first']((response.get('result') or {}).get('content', []))
    task = (public.get('region_task') or (public.get('facts') or {}).get('region_task') or {})
    rows = {row.get('object_name'): row for row in task.get('rows', [])}
    expected = {row['object_name']: row for row in truth['eligible']}
    for summary in exec_record['region_rows']:
        name = summary['object_name']
        original, target = rows[name], expected.get(name)
        normal = original.get('unit_normal_world')
        summary['direct_unit_normal_world'] = normal
        summary['geometry_fact_unknowns'] = original.get('geometry_fact_unknowns')
        summary['direct_area_matches_truth'] = bool(target and summary['direct_area_m2'] is not None
                                                   and near(summary['direct_area_m2'], target['area_m2']))
        summary['direct_unit_normal_matches_truth'] = bool(target and normal and len(normal) == 3
            and all(near(a, b) for a, b in zip(normal, target['unit_normal'], strict=True)))
    exec_record['all_three_direct_geometry_facts_delivered'] = (
        set(rows) == set(ROSTER) and exec_record['public_CLI_envelope_bound'] and not exec_record['is_error']
        and all(row['direct_area_matches_truth'] and row['direct_unit_normal_matches_truth']
                for row in exec_record['region_rows']))
    return first


def increments(review, helpers, ledger, answer, notes):
    require, read = helpers['require'], helpers['read']
    checked = review['bind_observations'](helpers, ledger, answer, notes)
    for record in checked:
        note = record['editorial_assessment']
        request = review['wire'](record, 'TX', read)
        args = request['params']['arguments']
        code_anchors = note.get('request_code_anchors', [])
        activity = note.get('area_normal_activity')
        require(activity in NUMERIC_WORK and all(anchor and anchor in args.get('code', '')
                                                for anchor in code_anchors),
                'numeric_use_or_request_source_anchor_not_supported/' + str(record['attempt']))
        if activity != 'none':
            require(bool(code_anchors and note['response_anchors']), 'numeric_work_requires_code_and_output_anchors')
        record['product_detail_requested'] = args.get('response_detail') if record['tool'] == TOOL else None
        record['product_image_requested'] = args.get('include_image') if record['tool'] == TOOL else None
    return checked


def score_and_adopt(helpers, ledger, answer, first, quality, evidence):
    require = helpers['require']
    require(ledger['answer_sha256'] == quality['answer_sha256'] == evidence['answer_sha256'],
            'answer_score_and_independent_readback_differ')
    first_product = first['first_installed_product_execution'] or {}
    product_index = first_product.get('attempt')
    originals = {image['sha256']: image['content_index'] for attempt in ledger['attempts']
                 if attempt['attempt'] == product_index for image in attempt['image_blocks']}
    adopted = {}
    for name in ('M02', 'M09'):
        criterion = quality['criteria'].get('witness_' + name) or {}
        ref = criterion.get('resolved_delivered_ref')
        frame = evidence.get('frames', {}).get(ref) or {}
        witness = frame.get('witnesses', {}).get(name)
        deliveries = frame.get('delivery', [])
        if criterion.get('status') == 'pass':
            require(answer and criterion['quote'] in answer and witness and witness['qualifies'] and deliveries,
                    'adopted_original_frame_not_supported_by_answer_or_pixel_readback/' + name)
        used_first = [entry for entry in deliveries if entry['attempt'] == product_index]
        for entry in used_first:
            require(originals.get(entry['PNG_sha256']) == entry['MCP_content_block'],
                    'scored_PNG_not_at_same_first_packet_content_index/' + name)
        adopted[name] = {'score_status': criterion.get('status'), 'resolved_delivered_ref': ref,
                         'first_product_image_adopted': bool(used_first and criterion.get('status') == 'pass'),
                         'same_slot_delivery_attempts': [entry['attempt'] for entry in deliveries],
                         'independent_pixels': witness}
    return adopted


def review_use(first, quality, calls, notes, answer):
    executed = first['first_installed_product_execution'] or {}
    rows = {row['object_name']: row for row in executed.get('region_rows', [])}
    matches = {}
    for name in ROSTER:
        row = rows.get(name, {})
        criterion = quality['criteria'].get('geometry_' + name) or {}
        area = row.get('direct_area_m2')
        normal = row.get('direct_unit_normal_world')
        matches[name] = bool(criterion.get('status') == 'pass' and area is not None and normal
            and near(area, criterion['area_m2'])
            and all(near(a, b) for a, b in zip(normal, criterion['unit_normal'], strict=True)))
    explicit = notes.get('explicit_product_numeric_use_quote')
    if explicit is not None and (not answer or explicit not in answer):
        raise ValueError('explicit_first_packet_use_quote_not_in_original_answer')
    operations = {kind: [call['attempt'] for call in calls
                          if call['editorial_assessment']['area_normal_activity'] == kind]
                  for kind in sorted(NUMERIC_WORK - {'none'})}
    return {'answer_values_agree_with_delivered_direct_values': matches,
            'explicit_first_packet_numeric_use_quote': explicit,
            'observed_recomputation_attempts_by_source': operations,
            'first_packet_sufficient_for_scored_area_normal': bool(
                executed.get('all_three_direct_geometry_facts_delivered') and all(matches.values())),
            'every_value_agrees_without_observed_recomputation': all(matches.values()) and not any(operations.values()),
            'scope': 'Numerical agreement and observable tool use cannot determine internal model calculations.'}


def compare(candidate, baseline):
    return {key: {'candidate': value, 'historical_fresh_brief': baseline[key],
                  'observed_difference': value - baseline[key] if value is not None and baseline[key] is not None else None}
            for key, value in candidate.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--output', type=Path, default=NS / 'checks/LIVE_REVIEW.json')
    parser.add_argument('--historical-self-check', action='store_true')
    args = parser.parse_args()
    review = runpy.run_path(str(OLD / 'checks/review_brief_entry.py'))
    old, baseline, old_answer = review['audit'](OLD, OLD_RUN)
    read, exact, require = (old[key] for key in ('read', 'exact', 'require'))
    truth_path = OLD / 'fixture/CURRENT_TRUTH.json'
    require(exact(truth_path)['sha256'] == review['TRUTH_SHA'], 'historical_truth_changed')
    truth = read(truth_path)
    old_first = first_details(review, old, baseline, truth, read(OLD / 'FIRST_PACKET.json'))
    old_notes = OLD / 'checks/BRIEF_TOOL_OBSERVATIONS.json'
    old_calls = review['bind_observations'](old, baseline, old_answer, read(old_notes))
    old_cost_path = OLD / 'RUNTIME_REVIEW.json'
    old_cost = review['costs'](baseline, review['p1'](read(old_cost_path)['slots'], 'label'))
    require(old_cost['business_attempts'] == 5 and old_cost['actual_rasters'] == 4
            and old_first['explicit_brief_on_first_business_attempt']
            and old_first['first_installed_product_execution']['text_UTF8_bytes'] == 10728,
            'reference_is_not_the_sealed_fresh_brief_slot')
    if args.historical_self_check:
        print('Fresh brief reference checked', old_cost['business_attempts'], old_cost['actual_rasters'])
        return
    if args.observations is None:
        parser.error('--observations is required after the formal slot')

    current, ledger, answer = review['audit'](NS, RUN)
    packet_path = NS / 'FIRST_PACKET.json'
    first = first_details(review, current, ledger, truth, read(packet_path))
    notes = read(args.observations)
    calls = increments(review, current, ledger, answer, notes)
    new_cost_path = NS / 'RUNTIME_REVIEW.json'
    quality_path = NS / 'scoring/QUALITY.json'
    evidence_path = NS / 'scoring/FORMAL_EVIDENCE.json'
    quality = review['p1'](read(quality_path)['slots'], 'slot')
    evidence = review['p1'](read(evidence_path)['slots'], 'slot')
    historical_tags = Counter(tag for row in old_calls for tag in row['editorial_assessment']['labels'])
    tags = Counter(tag for row in calls for tag in row['editorial_assessment']['labels'])
    first_exec = first['first_installed_product_execution']
    result = {'scope': 'One candidate P1 and one historical fresh brief P1; supplier input, inference and fees unobserved.',
              'original_bindings': ledger['original_bindings'], 'answer_sha256': ledger['answer_sha256'],
              'runtime_status': ledger['status'], 'observations': exact(args.observations),
              'current_first': first, 'current_first_source': exact(packet_path), 'historical_first': old_first,
              'historical_attribution': exact(old_notes), 'current_cost_source': exact(new_cost_path),
              'historical_cost_source': exact(old_cost_path),
              'same_ordered_PNGs_as_historical_first': (first_exec['image_block_sequence'] ==
                  old_first['first_installed_product_execution']['image_block_sequence']) if first_exec else None,
              'quality': {'passed': quality['passed'], 'denominator': quality['denominator']},
              'quality_source': exact(quality_path), 'formal_evidence_source': exact(evidence_path),
              'numeric_fact_use': review_use(first, quality, calls, notes, answer),
              'adopted_witnesses': score_and_adopt(current, ledger, answer, first, quality, evidence),
              'explicit_full_attempts': [row['attempt'] for row in calls if row['product_detail_requested'] == 'full'],
              'exact_PNG_redelivery_attempts': [row['attempt'] for row in calls if row['identical_earlier_PNGs']],
              'observed_cost_comparison': compare(
                  review['costs'](ledger, review['p1'](read(new_cost_path)['slots'], 'label')), old_cost),
              'observed_increment_comparison': compare({label: tags[label] for label in review['LABELS']},
                                                       {label: historical_tags[label] for label in review['LABELS']}),
              'current_attempts': calls}
    with args.output.open('x', encoding='utf8', newline='\n') as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True)
        output.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
