"""Bind reviewed task-specific followups to the actual MCP request/result chronology."""

from pathlib import Path

from score import SLOTS, digest, prior, read, require, verified


INCREMENTS = {'initial', 'new_evidence', 'recheck', 'error_recovery', 'failed_attempt', 'other', 'unresolved'}
AIMS = {'initial', 'source_capture', 'partition_or_geometry', 'blocker_identity', 'blocker_proof',
        'witness', 'format_or_schema', 'other', 'unresolved'}
BLOCKER_AIMS = {'blocker_identity', 'blocker_proof'}


def text_fragments(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from text_fragments(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_fragments(child)


def anchored(text, fragments):
    return type(text) is str and bool(text.strip()) and any(text in fragment for fragment in fragments)


def reviewed_attempt(call, note, slot, targets, previous):
    n = call['attempt']
    require(note['attempt'] == n and note['request_sha256'] == call['TX']['sha256'] and
            note['response_sha256'] == call['RX']['sha256'], 'review_not_bound_to_attempt_wire')
    tx = read_wire(call['TX'], slot)
    rx = read_wire(call['RX'], slot)
    name, arguments = tx['params']['name'], tx['params']['arguments']
    require(name == call['tool'] and tx['method'] == 'tools/call', 'review_tool_does_not_match_request')
    category, aim = note['increment'], note['aim']
    require(category in INCREMENTS and aim in AIMS and type(note['reason']) is str and note['reason'].strip(),
            'unclassified_tool_or_empty_reason')
    require((n == 1) == (category == 'initial') and (n == 1) == (aim == 'initial'),
            'initial_classification_must_match_business_ordinal')
    require(anchored(note['request_anchor'], (name, *text_fragments(arguments))), 'tool_review_missing_request_anchor')
    response_text = tuple(block['text'] for block in rx.get('result', {}).get('content', [])
                          if block.get('type') == 'text')
    response_anchor = note.get('response_anchor')
    if response_anchor is not None:
        require(anchored(response_anchor, (*response_text, *text_fragments(rx.get('error')))),
                'tool_review_response_anchor_not_in_original')
    blocked = note['blocker_targets']
    independent = note['independent_reproof_targets']
    require(len(blocked) == len(set(blocked)) and set(blocked) <= targets and
            len(independent) == len(set(independent)) and set(independent) <= set(blocked),
            'invalid_blocker_target_assignment')
    require(bool(blocked) == (aim in BLOCKER_AIMS), 'blocker_followup_requires_explicit_target_and_aim')
    if independent:
        require(aim == 'blocker_proof' and response_anchor and
                call.get('model_visible_as_public_CLI_tool_result') and not call['is_error'],
                'independent_reproof_not_actually_delivered')
    if note.get('from_attempts'):
        origins = note['from_attempts']
        require(len(set(origins)) == len(origins) and all(type(item) is int and item in previous for item in origins),
                'followup_dependency_is_absent_or_not_earlier')
    if category == 'error_recovery':
        sources = note.get('from_attempts', [])
        require(any(previous[i]['is_error'] or previous[i]['context_policy_would_truncate']
                    or not previous[i]['CLI_result_bound'] for i in sources),
                'recovery_without_original_error_or_truncated_context')
    route = ('product_full' if name == 'human_eye_scene_observe' and arguments.get('response_detail', 'full') == 'full'
             else 'product_other' if name == 'human_eye_scene_observe' else 'ordinary')
    return {'attempt': n, 'tool': name, 'route': route, 'is_error': call['is_error'],
            'CLI_result_bound': call.get('model_visible_as_public_CLI_tool_result', False),
            'context_policy_would_truncate': call.get('fixed_CLI_whole_content') is False,
            'text_UTF8_bytes': call['text_UTF8_bytes'], 'image_blocks': len(call['image_blocks']),
            'request_sha256': call['TX']['sha256'], 'response_sha256': call['RX']['sha256'],
            'increment': category, 'aim': aim, 'blocker_targets': blocked, 'independent_reproof_targets': independent,
            'counts_toward_primary_metric': n > 1 and aim in BLOCKER_AIMS, 'review': note}


def read_wire(receipt, slot):
    import json

    raw = verified(receipt['path'], receipt['sha256'], slot)
    require(len(raw) == receipt['bytes'], 'original_review_wire_size_changed')
    return json.loads(raw)


def slot_review(record, score, notes, slot, targets):
    label = record['slot']
    base = {'slot': label, 'arm': label[0], 'status': record['status'],
            'quality_passed': score['passed_quality'],
            'first_actual_tool_is_frozen_brief': record.get('first_actual_tool_is_frozen_brief'),
            'first_packet_blocker_facts_adopted': score['blocker_facts_adopted']}
    if 'tools' not in record:
        require(notes is None, 'annotation_for_slot_without_bound_tool_evidence')
        return {**base, 'evidence_error': record.get('evidence_error'), 'attempts': [], 'comparison_eligible': False,
                'blocker_followups': None, 'ordinary_blocker_followups': None, 'product_full_blocker_followups': None,
                'product_other_blocker_followups': None, 'target_use': []}
    require(notes is not None and notes['answer_sha256'] == record['answer_sha256'], 'followup_note_answer_binding_changed')
    calls = record['tools']['attempts']
    require([call['attempt'] for call in calls] == [note['attempt'] for note in notes['attempts']],
            'followup_notes_do_not_cover_actual_attempts_in_order')
    attempts = {}
    for call, note in zip(calls, notes['attempts'], strict=True):
        attempts[call['attempt']] = reviewed_attempt(call, note, slot, targets, attempts)
    measured = [row for row in attempts.values() if row['counts_toward_primary_metric']]
    orig = {row['region']: row for row in score['rows'] if row.get('blocker') and row.get('evidence_passed')}
    adopted = set(score.get('first_candidate_blocker_regions_used', []))
    results = []
    for label in sorted(targets):
        proof = orig.get(label, {}).get('blocker')
        later = [row['attempt'] for row in measured if label in row['independent_reproof_targets']]
        all_additions = [row['attempt'] for row in measured if label in row['blocker_targets']]
        if not proof:
            status = 'answer_blocker_unproven'
        elif label in adopted and later:
            status = 'matches_first_packet_and_later_independently_rechecked'
        elif label in adopted and not all_additions:
            status = 'matches_first_packet_without_observed_blocker_followup'
        elif label in adopted:
            status = 'matches_first_packet_with_other_blocker_followup'
        elif later:
            status = 'proven_geometric_answer_with_independent_followup'
        else:
            status = 'proven_geometric_answer_actual_evidence_route_unresolved'
        results.append({'region': label, 'valid_scored_blocker': proof,
                        'first_packet_match': label in adopted, 'classification': status,
                        'blocker_followup_attempts': all_additions, 'later_independent_proof_attempts': later})
    complete = record['status'] == 'completed' and not record.get('evidence_error') and bool(calls)
    unresolved = [row['attempt'] for row in attempts.values()
                  if row['aim'] == 'unresolved' or row['increment'] == 'unresolved']
    return {**base, 'attempts': list(attempts.values()), 'comparison_eligible': complete and not unresolved,
            'unresolved_attempts': unresolved, 'target_use': results, 'blocker_followups': len(measured),
            'ordinary_blocker_followups': sum(row['route'] == 'ordinary' for row in measured),
            'product_full_blocker_followups': sum(row['route'] == 'product_full' for row in measured),
            'product_other_blocker_followups': sum(row['route'] == 'product_other' for row in measured)}


def compare(scores):
    indexed = {row['slot']: row for row in scores}
    pairs = []
    for n in range(1, 4):
        a, b = (indexed[f'{arm}{n}'] for arm in ('A', 'B'))
        comparable = all(row['comparison_eligible'] for row in (a, b))
        delta = b['blocker_followups'] - a['blocker_followups'] if comparable else None
        pairs.append({'pair': n, 'A_slot': a['slot'], 'B_slot': b['slot'], 'comparison_eligible': comparable,
                      'A_blocker_followups': a['blocker_followups'], 'B_blocker_followups': b['blocker_followups'],
                      'B_minus_A_blocker_followups': delta})
    fewer = sum(row['B_minus_A_blocker_followups'] is not None and
                row['B_minus_A_blocker_followups'] < 0 for row in pairs)
    return {'pairs': pairs, 'B_fewer_blocker_followup_pairs': fewer, 'followup_gate_passed': fewer >= 2}


def followups(ledger, quality, notes_path, output):
    from common import EXTERNAL

    notes = read(notes_path)
    require(quality['evidence_sha256'] == digest((output / 'FORMAL_EVIDENCE.json').read_bytes()) and
            ledger['answers_sealed_sha256'] == quality['answers_sealed_sha256'],
            'followups_are_not_bound_to_original_score_and_answer')
    require([r['slot'] for r in ledger['slots']] == [r['slot'] for r in quality['slots']] == list(SLOTS),
            'followup_denominator_changed')
    require(notes.keys() == {r['slot'] for r in ledger['slots'] if 'tools' in r},
            'followup_notes_must_cover_each_bound_tool_slot')
    targets = {prior.region_label(prior.region_key(region)) for region in prior.rail_truth()['eligible']
               if not region['eligible_complete_views']}
    slots = [slot_review(original, scored, notes.get(original['slot']), EXTERNAL / 'slots' / original['slot'], targets)
             for original, scored in zip(ledger['slots'], quality['slots'], strict=True)]
    return {'schema': 'm4-rail-blocker-formal-followup-review-v1', 'formal_denominator': len(SLOTS),
            'formal_original_evidence_sha256': quality['evidence_sha256'],
            'answers_sealed_sha256': ledger['answers_sealed_sha256'],
            'quality_sha256': digest((output / 'QUALITY.json').read_bytes()),
            'manual_original_review_sha256': digest(notes_path.read_bytes()),
            'provider_input_observed': False, 'slots': slots, **compare(slots)}
