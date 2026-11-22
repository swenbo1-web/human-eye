"""Reconcile formal H1–H3 native/plugin observations and evaluate the frozen gates."""

import argparse
from fractions import Fraction
import importlib.util
import json
from math import isclose
from pathlib import Path
from statistics import median


NS = Path(__file__).resolve().parents[1]
V = NS.parent
OLD = V/'m1_source_region_no_image_measurement_consumption_001/checks/consumption_trace.py'
ROOT = Path('D:/he_m1_source_region_no_image_native_transfer_001')
PRODUCT = '338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac'
LABELS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
TOLERANCE = 5e-5
EXCEPTIONS = (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, ArithmeticError)
ORDINARY_KINDS = {'setup_only', 'new_required_evidence', 'repeat_same_evidence',
                  'recomputation_with_new_evidence', 'other_relevant_work', 'unrelated_work'}


def read(path, default=None):
    return json.loads(path.read_bytes()) if path.is_file() else default


def load_previous(case):
    spec = importlib.util.spec_from_file_location('_pinned_previous_consumption_trace', OLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TARGET, module.REFERENCE, module.FACES = case['target'], case['reference'], case['faces']
    return module


def event_bindings(slot):
    source = read(slot/'consumer/BUSINESS_SOURCE_BINDING.json', {})
    events = {}
    timeline = slot/'consumer/events.jsonl'
    if timeline.is_file():
        for line in timeline.read_bytes().splitlines():
            row = json.loads(line)
            e = row['event']
            item = e.get('item', {})
            if e.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
                key = (item['id'], row['perf_ns'])
                if key in events:
                    raise ValueError('duplicate_public_completed_CLI_item')
                events[key] = item
    return {row['attempt']: events.get(((row.get('caller_identity') or {}).get('CLI_event_item_id'),
                                       row.get('CLI_received_ns')))
            for row in source.get('result_contracts', []) if row.get('matched') is True}


def actual_selected_packet(row, item):
    """Require the adjudicated facts in the exact public CLI event after transport."""
    observed = row.get('observed') or {}
    if not (row['classification'] == 'bound_selected_region_measurement' and item
            and item.get('tool') == row['tool'] and item.get('error') is None):
        return False
    for block in ((item.get('result') or {}).get('content') or []):
        if block.get('type') != 'text':
            continue
        try:
            body = json.loads(block['text'])
        except (ValueError, TypeError):
            continue
        if not isinstance(body, dict):
            continue
        task = body.get('task_result') or {}
        facts = task.get('facts') or {}
        mapping = task.get('source_mapping') or {}
        if (body.get('region_ref') == observed['region_ref']
                and facts.get('surface_proximity') == observed['fact']
                and mapping.get('nearest_witness') == observed['source_mapping']):
            return True
    return False


def quality_identity(account, quality):
    if not quality:
        return {'passed': False, 'reason': 'independent_grade_not_available'}
    original = quality.get('original_answer') or {}
    answer = account.get('answer_file') or {}
    checks = quality.get('checks') or {}
    passed = (account['status'] == 'completed' and quality.get('slot') == account['label']
              and quality.get('all_quality_passed') is True and type(quality.get('planned')) is int
              and quality['planned'] > 0 and quality.get('score') == quality['planned'] == len(checks)
              and all(row.get('passed') is True for row in checks.values())
              and isinstance(original.get('sha256'), str) and original['sha256'] == answer.get('sha256'))
    return {'passed': passed, 'score': quality.get('score'), 'planned': quality.get('planned'),
            'answer_sha256': original.get('sha256'),
            'reason': None if passed else 'incomplete_grade_or_unbound_public_answer'}


def claimed_values(quality):
    proof = quality['checks']
    point = proof['selected_actual_point_pair_and_triangle_membership']['verified']
    metric = proof['selected_distance_and_world_direction']['verified']
    return {'distance': metric['metres'], 'direction': metric['direction_a_to_b'],
            'points': [point['point_a'], point['point_b']], 'source_faces': point['stated_source_triangle_indices']}


def quantity(value):
    return float(Fraction(str(value)))


def close_vector(left, right):
    return len(left) == len(right) == 3 and all(
        isclose(quantity(a), quantity(b), rel_tol=0, abs_tol=TOLERANCE) for a, b in zip(left, right, strict=True))


def answer_matches(claim, observed):
    fact = observed['fact']['value']
    point = fact['nearest_witness']
    members = observed['source_mapping']
    return (isclose(quantity(claim['distance']), quantity(fact['distance_m']), rel_tol=0, abs_tol=TOLERANCE)
            and close_vector(claim['direction'], point['direction_a_to_b'])
            and all(close_vector(claim['points'][i], point[key]) for i, key in enumerate(('a', 'b')))
            and all(claim['source_faces'][key] and set(claim['source_faces'][key]) <= set(members[key]['source_triangle_indices'])
                    for key in ('a', 'b')))


def strings(value):
    if isinstance(value, str):
        yield value
        try:
            nested = json.loads(value)
        except ValueError:
            return
        if isinstance(nested, (list, dict)):
            yield from strings(nested)
    elif isinstance(value, dict):
        for nested in value.values():
            yield from strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from strings(nested)


def ordinary_review(trace, by_attempt, judgments):
    records, errors = [], []
    pending = {row['attempt']: row for row in trace
               if row['classification'] == 'ordinary_read_or_calculation_content_review_required'}
    used = set()
    for note in judgments.get('ordinary', []):
        attempt = note.get('attempt')
        citation = note.get('result_excerpt')
        result = (by_attempt.get(attempt) or {}).get('result')
        if (attempt not in pending or attempt in used or note.get('classification') not in ORDINARY_KINDS
                or not isinstance(citation, str) or not citation.strip()
                or not any(citation in content for content in strings(result))
                or not isinstance(note.get('reason'), str) or not note['reason'].strip()):
            errors.append(f'ordinary_review_missing_or_mismatched_original_event/{attempt}')
            continue
        used.add(attempt)
        records.append(note)
    return {'reviewed': records, 'unreviewed_attempts': sorted(pending.keys() - used), 'errors': errors}


def source_trace(account, quality, checked_quality, by_attempt, judgments):
    candidates = [row for row in account.get('scope_trace', [])
                  if actual_selected_packet(row, by_attempt.get(row['attempt']))]
    matched = []
    if checked_quality['passed'] and account['label'].startswith('P'):
        claim = claimed_values(quality)
        matched = [row['attempt'] for row in candidates if answer_matches(claim, row['observed'])]
    answer_excerpt = judgments.get('answer_excerpt')
    if answer_excerpt is not None:
        answer = Path(account['answer_file']['path']).read_bytes().decode('utf-8')
        if not isinstance(answer_excerpt, str) or not answer_excerpt.strip() or answer_excerpt not in answer:
            raise ValueError('selected_adoption_review_excerpt_missing_from_original_answer')
    if judgments.get('selected_source_attempts') is not None:
        reviewed = judgments['selected_source_attempts']
        if (not isinstance(reviewed, list) or any(type(item) is not int for item in reviewed)
                or len(reviewed) != len(set(reviewed)) or not set(reviewed) <= set(matched)):
            raise ValueError('adoption_review_unrelated_to_actual_bound_selected_tool_result')
        matched = reviewed
    proof = [row for row in candidates if row['attempt'] in matched]
    return {'passed': bool(proof), 'exact_public_selected_attempts': [row['attempt'] for row in candidates],
            'answer_matches_attempts': matched, 'ambiguous_between_equal_product_packets': len(matched) > 1,
            'support': [{'attempt': row['attempt'], 'TX': row['original_public_TX'], 'RX': row['original_public_RX'],
                         'inner': row.get('inner_wire'), 'no_image_fact': row['observed']['image_not_requested']}
                        for row in proof],
            'origin_scope': 'Matches the scored public answer to actual delivered source facts. '
                            'Internal model use is unobserved.'}


def summarize_slot(slot, case, *, freeze_digest, expected_prompt, quality=None, judgments=None):
    label = slot.name
    historical = load_previous(case)
    try:
        account = historical.analyze_slot(slot, freeze_digest, expected_prompt)
    except (*EXCEPTIONS, StopIteration) as exc:
        answer = read(slot/'SLOT_RESULT.json', {})
        return {'label': label, 'status': 'unverifiable', 'host_status': answer.get('status'),
                'formal_slot_created': slot.is_dir(), 'gate_errors': [str(exc)],
                'model_consumers_launched': answer.get('model_consumers', 0)}
    if not account['formal_slot_created']:
        return account
    account['receipt'] = read(slot/'SLOT_PUBLICATION.json', {})
    result = read(slot/'SLOT_RESULT.json', {})
    account['group'] = result.get('group')
    account['closure_verified'] = (result.get('closure_verification') or {}).get('passed') is True
    account['same_read_only_scene'] = (result.get('independent_before_after') or {}).get('passed') is True
    errors = account['gate_errors'] = list(account['scope_trace_errors'])
    total = account['totals']
    cached, raw_in, raw_out = (total[key] for key in ('CLI_cached_input_tokens', 'CLI_input_tokens', 'CLI_output_tokens'))
    valid_cache = type(cached) is int and type(raw_in) is int and type(raw_out) is int and 0 <= cached <= raw_in
    total['CLI_uncached_input_tokens'] = raw_in - cached if valid_cache else None
    total['CLI_uncached_input_plus_output_tokens'] = raw_in - cached + raw_out if valid_cache else None
    account['quality'] = quality_identity(account, quality)
    try:
        by_attempt = event_bindings(slot)
        account['selected_answer_source'] = source_trace(account, quality, account['quality'], by_attempt, judgments or {})
        account['ordinary_review'] = ordinary_review(account['scope_trace'], by_attempt, judgments or {})
        errors.extend(account['ordinary_review']['errors'])
    except EXCEPTIONS as exc:
        errors.append(str(exc))
    if account['status'] != 'completed':
        return account
    argv = (account.get('requested_consumer_configuration') or {}).get('requested_cli_overrides_and_argv') or []
    cfg = account.get('requested_consumer_configuration') or {}
    profile = tuple(cfg.get(key) for key in ('requested_model', 'requested_effort', 'requested_service_tier'))
    if profile != ('gpt-6.1-sol', 'medium', 'default') or not argv or not any(
            part.startswith('0.152.1-') for part in Path(argv[0]).parts):
        errors.append('incorrect_frozen_model_or_CLI_request')
    if account['model_consumers_launched'] != 1 or not account['thread_id']:
        errors.append('fresh_CLI_consumer_receipt_missing')
    publication = account['receipt']
    owned_ns = publication.get('complete_slot_ns')
    wall = total['complete_slot_ms']
    if (publication.get('owned_budget_passed') is not True or type(owned_ns) is not int or owned_ns <= 0
            or wall is None or owned_ns / 1e6 != wall):
        errors.append('complete_owned_wall_clock_or_deadline_unproven')
    if not account['closure_verified'] or not account['same_read_only_scene']:
        errors.append('closed_read_only_scene_unproven')
    if type(total['CLI_input_plus_output_tokens']) is not int:
        errors.append('raw_CLI_input_plus_output_tokens_unproven')
    return account


def pair_row(number, slots):
    native, plugin = (slots[f'{arm}{number}'] for arm in ('N', 'P'))
    n, p = (row.get('totals', {}) for row in (native, plugin))
    n_ms, p_ms = (item.get('complete_slot_ms') for item in (n, p))
    completed = native['status'] == plugin['status'] == 'completed'
    ratio = 100 * (n_ms-p_ms)/n_ms if completed and n_ms and p_ms else None
    quality = completed and all(row.get('quality', {}).get('passed') is True for row in (native, plugin))
    parity = quality and native['quality']['score'] == plugin['quality']['score']
    return {'case': number, 'native': native['label'], 'plugin': plugin['label'], 'completed': completed,
            'same_prompt_observed': (completed and bool(native.get('initial_prompt_sha256'))
                                     and native['initial_prompt_sha256'] == plugin.get('initial_prompt_sha256')),
            'quality_equal_and_complete': parity, 'plugin_faster': None if ratio is None else ratio > 0,
            'complete_owned_savings_percent': ratio,
            'plugin_minus_native': {key: p[key]-n[key] for key in n.keys() & p.keys()
                                    if type(n[key]) in (int, float) and type(p[key]) in (int, float)}}


def chronological(slots):
    prior = None
    for label in LABELS:
        row = slots[label]['receipt']
        started, stopped = row.get('started_ns'), row.get('published_ns')
        if type(started) is not int or type(stopped) is not int or not started <= stopped:
            return False
        if prior is not None and started < prior:
            return False
        prior = stopped
    return True


def analyze(root=ROOT, *, freeze_path=None, quality=None, judgments=None):
    root = Path(root)
    freeze_path = NS/'FROZEN.json' if freeze_path is None else Path(freeze_path)
    frozen = read(freeze_path, {})
    cases = {str(row['id']): row for row in read(NS/'inputs/CASES.json', [])}
    if set(cases) != {'1', '2', '3'}:
        raise ValueError('incorrect_frozen_case_roster')
    token = load_previous(cases['1']).raw_sha(freeze_path.read_bytes()) if frozen else None
    case_prompts = frozen.get('prompt_sha256_by_case', {})
    slot_prompts = frozen.get('prompt_sha256_by_slot', {})
    prompts_verified = bool(token) and all(case_prompts.get(label[-1]) == slot_prompts.get(label)
        == cases[label[-1]]['prompt_sha256'] for label in LABELS)
    slots = {}
    for label in LABELS:
        case = cases[label[-1]]
        slots[label] = summarize_slot((root/'slots'/label).resolve(), case, freeze_digest=token,
                                      expected_prompt=case['prompt_sha256'], quality=(quality or {}).get(label),
                                      judgments=(judgments or {}).get(label))
    pairs = [pair_row(i, slots) for i in (1, 2, 3)]
    # Failed and unrun slots stay in the denominator. Aggregates that require a
    # complete panel are reported as unavailable until all named records exist.
    complete = all(row.get('status') == 'completed' and row.get('cost_evidence_verified') is True
                   and not row.get('gate_errors') for row in slots.values())
    identities = complete and all(row['product_source_sha256'] == PRODUCT and row['group'] == label[0]
        and (label.startswith('P') or not any(tool['product'] is not None for tool in row['actual_requests']))
        for label, row in slots.items())
    threads = [row['thread_id'] for row in slots.values() if row.get('thread_id')]
    observed_pcts = [row['complete_owned_savings_percent'] for row in pairs
                     if row['complete_owned_savings_percent'] is not None]
    all_pct = median(observed_pcts) if len(observed_pcts) == 3 else None
    faster = sum(row['plugin_faster'] is True for row in pairs)
    count_quality = {arm: sum(row.get('quality', {}).get('passed') is True
                              for label,row in slots.items() if label.startswith(arm)) for arm in ('N','P')}
    traceable = sum(row.get('selected_answer_source', {}).get('passed') is True
                    for label,row in slots.items() if label.startswith('P'))
    token_keys = ('CLI_input_tokens', 'CLI_cached_input_tokens', 'CLI_output_tokens',
                  'CLI_input_plus_output_tokens', 'CLI_uncached_input_tokens', 'CLI_uncached_input_plus_output_tokens')
    usage = {}
    for arm in ('N', 'P'):
        rows = [row.get('totals', {}) for label, row in slots.items() if label.startswith(arm)]
        usage[arm] = {key: sum(row[key] for row in rows) if all(type(row.get(key)) is int for row in rows) else None
                      for key in token_keys}
    key = 'CLI_input_plus_output_tokens'
    raw_n, raw_p = usage['N'][key], usage['P'][key]
    checks = {'frozen_actual_provenance_and_closed_slots': prompts_verified and complete and identities
              and len(threads) == len(set(threads)) == 6 and chronological(slots)
              and all(row['same_prompt_observed'] for row in pairs),
              'each_arm_3_of_3_equal_and_complete_quality': all(row['quality_equal_and_complete'] for row in pairs),
              'P_3_of_3_actual_selected_fact_traceable': traceable == 3,
              'paired_complete_owned_savings_median_at_least_10_percent': all_pct is not None and all_pct >= 10,
              'plugin_faster_in_at_least_two_pairs': faster >= 2,
              'raw_CLI_input_plus_output_did_not_increase': raw_n is not None and raw_p is not None and raw_p <= raw_n}
    return {'schema': 'm1-source-region-no-image-native-transfer-formal-trace-v1', 'freeze_sha256': token,
            'passed': all(checks.values()), 'gates': checks, 'slots': slots, 'pairs': pairs,
            'denominator': {'planned_formal': 6, 'created': sum(row['formal_slot_created'] for row in slots.values()),
                            'completed': sum(row['status'] == 'completed' for row in slots.values()),
                            'failed_or_unconfirmed': sum(row['status'] not in ('completed','unrun') for row in slots.values()),
                            'unrun': sum(row['status'] == 'unrun' for row in slots.values()),
                            'model_launches_observed': sum(row['model_consumers_launched'] for row in slots.values()),
                            'quality_passed_N_of_3': count_quality['N'], 'quality_passed_P_of_3': count_quality['P'],
                            'P_actual_selected_answer_source_of_3': traceable},
            'complete_owned_median_paired_savings_percent': all_pct, 'plugin_faster_pairs_of_3': faster,
            'observed_CLI_usage_totals': usage, 'actual_provider_time': None, 'actual_provider_billing': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--freeze', type=Path)
    parser.add_argument('--quality', type=Path)
    parser.add_argument('--judgments', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.root, freeze_path=args.freeze, quality=read(args.quality) if args.quality else None,
                     judgments=read(args.judgments) if args.judgments else None)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
