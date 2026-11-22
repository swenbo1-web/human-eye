"""Audit natural tool delivery and source follow-ups after each owned slot closes."""

import argparse
from functools import lru_cache
import json
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUNTIME = Path('D:/he_m3_whole_object_rounded_witness_consumption_001')
PRIOR = V / 'm3_whole_object_witness_triangle_consumption_001'
ENGINE = V / 'm3_whole_object_rounded_witness_001/checks/evidence.py'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TARGET, REFERENCES = 'N02', ('N04', 'N05')
LABELS = ('A1', 'B1')
SIDES = ('a', 'b')
BINDINGS = {
    'A1': V / 'm3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json',
    'B1': V / 'm3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json',
}
OLD = run_path(str(PRIOR / 'checks/consumption_trace.py'))
P, M, D, C = OLD['previous']()
require, read, digest = (OLD[key] for key in ('require', 'read', 'digest'))
EXACT, STRICT = 'exact_source_triangles', 'source_triangles'
BOUND = ('bound_whole_measurement', 'bound_narrow_scope_measurement')
REVIEW = 'ordinary_read_or_calculation_content_review_required'
KINDS = OLD['ORDINARY'] | {'first_geometry_solution', 'independent_membership_verification_same_fact'}
STAGES = ('host.capture', 'observation.task_facts', 'surface_proximity.rounded_source_membership',
          'surface_proximity.exact_source_membership', 'task_query.exact_source_encode',
          'mcp.content_encode', 'mcp.wire_encode', 'mcp.stdio_write')


@lru_cache(maxsize=1)
def exact_verifier():
    return run_path(str(ENGINE))['verify_certificate']


def source_state(slot, source):
    initial, terminal = [
        json.loads(P['checked'](P['inside'](slot, source[key]['path']), source[key]['sha256']))
        for key in ('initial_source', 'terminal_source')
    ]
    require(source['asset_sha256'] == terminal['source']['asset_sha256'] == ASSET_SHA
            and initial['source'] == terminal['source'] and initial['objects'] == terminal['objects'],
            'owned_initial_and_terminal_sources_differ')
    rows = {item['name']: item for item in terminal['objects']}
    require(len(rows) == len(terminal['objects']) == 28 and {TARGET, *REFERENCES} <= rows.keys()
            and sum(len(item['evaluated']['triangles']) for item in rows.values()) == 744
            and sum(len(item['evaluated']['vertices_world_m']) for item in rows.values()) == 416,
            'unexpected_capture_population')
    return terminal, rows


def verify_exact(capture, body, order):
    witness = D['witnesses'](body)
    require(EXACT in witness and STRICT not in witness, 'expected_single_exact_source_variant')
    proof = exact_verifier()(capture, body, expect_exact=True, expected_order=order, prove_global=True)
    indices = proof['indices'] if order[0] == TARGET else proof['indices'][::-1]
    return proof, dict(zip(SIDES, ([index] for index in indices), strict=True))


def trace_attempt(slot, row, item, objects, terminal, binding, audit):
    proof = OLD['trace_attempt'](slot, row, item, objects, terminal, binding, audit,
                                 target=TARGET, references=REFERENCES)
    ask = proof['requested_pair']
    if ask is None and row['tool'] == OLD['TOOL'] and proof['classification'] == 'other_successful_tool_delivery':
        query = row['arguments'].get('query', {}) if isinstance(row['arguments'], dict) else {}
        if query.get('mode') in ('task', 'active_observation', 'source_region', 'surface_scan', 'surface_nearest'):
            return {**proof, 'classification': REVIEW}
    if proof['classification'] not in BOUND or not ask['ordinary_whole_entry']:
        return proof
    body = OLD['exact_public'](row, item)
    witness = D['witnesses'](body)
    if EXACT not in witness:
        return proof
    request = read(Path(row['product']['request_file']['path']))
    envelope, = [line for line in OLD['lines'](slot / 'PUBLIC_REQUESTS.jsonl')
                 if line['request']['id'] == request['id']]
    producer = read(Path(row['product']['producer_archive']['path']))
    sequence, capture = D['H']['slot_capture'](slot, binding, {**envelope, 'producer': producer},
                                              lambda path: P['inside'](slot, path).read_bytes())
    require(sequence == proof['source_capture']['sequence'] and
            body['binding']['runtime_source_sha256'] == binding['source_sha256'],
            'exact_packet_detached_from_verified_own_source')
    certificate, membership = verify_exact(capture, body, ask['order'])
    proof['fact']['membership'] = membership
    proof['exact_source_verification'] = certificate
    proof['current_triangle_source'] = certificate
    return proof


def review_calls(trace, live_items, notes):
    expected = {row['attempt'] for row in trace if row['classification'] == REVIEW}
    pending = set(expected)
    verified = []
    for note in notes:
        call = note['attempt']
        refs = note['pairs']
        excerpt = note['result_excerpt']
        item = live_items.get(call) or {}
        require(call in pending and note['classification'] in KINDS
                and isinstance(refs, list) and len(set(refs)) == len(refs) and set(refs) <= set(REFERENCES)
                and isinstance(excerpt, str) and excerpt.strip()
                and any(excerpt in text for text in M['strings'](item.get('result')))
                and isinstance(note['reason'], str) and note['reason'].strip(),
                f'ordinary_review_not_bound_to_original_delivery/{call}')
        pending.remove(call)
        verified.append(note)
    return {'verified': verified, 'unreviewed': sorted(pending)}


def refs_eligible(trace, reference, step):
    """Only a prior same-pair metric missing a requested face can motivate required source work."""
    prior = [row for row in trace if row['attempt'] < step and row['classification'] == BOUND[0]
             and row['requested_pair']['reference'] == reference]
    return bool(prior) and not any(all(row['fact']['membership'][side] for side in SIDES) for row in prior)


def summarize_pairs(trace, quality, answer, review, *, candidate):
    reports = {}
    for reference in REFERENCES:
        pair_requests = [row for row in trace if (row['requested_pair'] or {}).get('reference') == reference]
        first = next((row for row in pair_requests if row['classification'] == BOUND[0]), None)
        notes = [note for note in review['verified'] if reference in note['pairs']]
        for note in notes:
            if note['classification'] == 'standalone_new_source_membership':
                require(refs_eligible(trace, reference, note['attempt']),
                        f'source_specific_supplement_requires_prior_measured_pair_missing_source/{reference}')
        report = OLD['pair_report'](trace, reference, quality, quality.get('all_quality_passed') is True,
                                    notes, answer, qualifying_candidate=False)
        quote = None
        matches = (candidate and quality.get('all_quality_passed') is True and first
                   and first.get('exact_source_verification') and first['requested_pair']['ordinary_whole_entry']
                   and first['requested_pair']['explicit_no_image']
                   and OLD['fits_scored_points'](quality, reference, first['fact'], require_source=True))
        if matches:
            graded = quality['checks'][f'{reference}_actual_point_pair_and_triangle_membership']['verified']
            quote = graded['point_pair_quote']
            require(isinstance(quote, str) and quote.strip() and quote in answer,
                    'final_adoption_quote_does_not_bind_original_final')
        basis = None if not matches else graded.get('source_basis_kind')
        explicit_exact_basis = basis == 'exact_bound_points'
        ordinary_proof = any(note['classification'] in (
            'standalone_new_source_membership', 'independent_membership_verification_same_fact',
            'recomputation_with_new_evidence', 'first_geometry_solution', 'new_required_evidence') for note in notes)
        later_product_source = bool(first and any(
            row['attempt'] > first['attempt'] and row.get('fact')
            and all(row['fact']['membership'][side] for side in SIDES) for row in pair_requests))
        other_proof = ordinary_proof or later_product_source
        reports[reference] = {
            **report,
            'earliest_pair_request_attempt': pair_requests[0]['attempt'] if pair_requests else None,
            'earliest_pair_request': pair_requests[0]['requested_pair'] if pair_requests else None,
            'first_whole_has_exact_source': bool(first and first.get('exact_source_verification')),
            'first_whole_is_exact_answer_match': bool(matches),
            'candidate_first_whole_adopted': bool(matches and explicit_exact_basis
                                                  and not other_proof and not review['unreviewed']),
            'verified_answer_source_basis': basis,
            'alternative_verified_source_work_present': other_proof,
            'verified_answer_point_source_quote': quote,
        }
    return reports


def actual_work(slot):
    """Count actual product attempts from service work, including calls outside the two direct pairs."""
    events = OLD['lines'](slot / 'product_audit.jsonl')
    observed = [row for row in events if row.get('event') == 'observe' and 'task_work' in row]
    requests = [row['trace'] for row in events if row.get('event') == 'request_trace']
    work_keys = ('surface_pair_count', 'closed_solid_pair_count', 'spatial_pair_count', 'exact_pair_count')
    stages = [span for r in requests for span in r.get('spans', [])]
    by_stage = {stage: [span['duration_ns']/1e6 for span in stages if span['name'] == stage] for stage in STAGES}
    return {'observed_task_work_events': len(observed),
            **{key: sum(row['task_work'].get(key, 0) for row in observed) for key in work_keys},
            'result_cache_hits': sum(row['task_work'].get('result_cache_hit') is True for row in observed),
            'recorded_host_capture_spans': len(by_stage['host.capture']),
            'trace_spans_ms': {stage: {'count': len(values), 'total_ms': sum(values)}
                               for stage, values in by_stage.items() if values}}


def summarize(slot, freeze, quality, judgments):
    try:
        ledger = C['summarize'](slot, freeze['sha256'])
    except OLD['ERRORS'] as err:
        original = read(slot / 'SLOT_RESULT.json', read(slot / 'SLOT_STARTED.json', {}))
        return {'label': slot.name, 'status': 'unverifiable', 'formal_slot_created': slot.is_dir(),
                'model_consumers_launched': original.get('model_consumers', 0), 'verification_errors': [str(err)]}
    ledger['formal_slot_created'] = slot.is_dir()
    ledger['quality'] = M['quality_identity'](ledger, quality)
    ledger['verification_errors'] = []
    if ledger['status'] != 'completed':
        return ledger
    ledger['totals'] = OLD['account_active_costs'](ledger)
    ledger['work'] = actual_work(slot)
    ledger['trace'] = []
    try:
        source = read(slot / 'SLOT_RESULT.json')
        published = read(slot / 'SLOT_PUBLICATION.json')
        cfg = ledger['requested_consumer_configuration']
        binding = read(BINDINGS[slot.name])
        require(ledger['cost_evidence_verified'] and ledger['initial_prompt_sha256'] == freeze['prompt_sha256']
                and source['closure_verification']['passed'] and source['independent_before_after']['passed']
                and source['product_source_sha256'] == binding['source_sha256']
                and ledger['thread_id'] and ledger['model_consumers_launched'] == 1
                and published['owned_budget_passed']
                and published['complete_slot_ns']/1e6 == ledger['totals']['complete_slot_ms']
                and (cfg['requested_model'], cfg['requested_effort'], cfg['requested_service_tier'])
                == ('gpt-6.1-sol', 'medium', 'default')
                and any(p.startswith('0.152.1-') for p in Path(cfg['requested_cli_overrides_and_argv'][0]).parts),
                'actual_formal_prompt_identity_model_request_owned_close_or_clock_changed')
        terminal, objects = source_state(slot, source)
        items, audit = M['event_bindings'](slot), OLD['audit_work'](slot)
        for row in ledger['actual_requests']:
            try:
                ledger['trace'].append(trace_attempt(slot, row, items.get(row['attempt']), objects,
                                                     terminal, binding, audit))
            except OLD['ERRORS'] as err:
                ledger['verification_errors'].append(f'attempt {row["attempt"]}: {err}')
        ledger['review'] = review_calls(ledger['trace'], items, judgments.get('ordinary', []))
        answer = Path(ledger['answer_file']['path']).read_text(encoding='utf8')
        bound_grade = (quality or {}) if ledger['quality']['passed'] else {}
        ledger['pairs'] = summarize_pairs(ledger['trace'], bound_grade, answer, ledger['review'],
                                          candidate=slot.name == 'B1')
    except OLD['ERRORS'] as err:
        ledger['verification_errors'].append(str(err))
    return ledger


def compare(slots):
    a, b = (slots[label] for label in LABELS)
    completed = all(row['status'] == 'completed' and row.get('cost_evidence_verified')
                    and not row['verification_errors'] for row in slots.values()) and a.get('thread_id') != b.get('thread_id')
    equal = (completed and all(row['quality']['passed'] for row in slots.values())
             and a['quality']['score'] == b['quality']['score'])
    reviews_closed = completed and all(not row['review']['unreviewed'] for row in slots.values())
    pairs = {ref: {label: row.get('pairs', {}).get(ref) for label, row in slots.items()} for ref in REFERENCES}
    adopted = sum((item['B1'] or {}).get('candidate_first_whole_adopted') is True for item in pairs.values())
    supported = all(
        (item['B1'] or {}).get('candidate_first_whole_adopted')
        and (item['A1'] or {}).get('first_whole_attempt') is not None for item in pairs.values()
    )
    # One ordinary computation can close the provenance of both pairs.
    unique = {label: sorted({attempt for item in row.get('pairs', {}).values()
                             for attempt in item['required_source_followups']}) for label, row in slots.items()}
    comparable = bool(equal and reviews_closed and supported)
    delta = (len(unique['A1']) - len(unique['B1'])) if comparable else None
    totals = a.get('totals', {}), b.get('totals', {})
    return {'same_closed_quality': bool(equal), 'ordinary_evidence_review_complete': bool(reviews_closed),
            'candidate_first_packet_adopted_pairs_of_2': adopted,
            'required_distinct_provenance_followup_attempts': unique,
            'paired_provenance_followups_A_minus_B': delta,
            'single_task_mechanism_supported': bool(delta is not None and delta > 0),
            'pairs': pairs, 'slots': slots,
            'denominator': {'planned': 2, 'created': sum(row['formal_slot_created'] for row in slots.values()),
                            'completed': sum(row['status'] == 'completed' for row in slots.values()),
                            'failed_or_unconfirmed': sum(row['status'] not in ('completed', 'unrun')
                                                         for row in slots.values()),
                            'unrun': sum(row['status'] == 'unrun' for row in slots.values()),
                            'model_launches_observed': sum(row['model_consumers_launched'] for row in slots.values())},
            'cost_deltas_B_minus_A': {k: totals[1][k]-v for k,v in totals[0].items()
                                      if type(v) in (int,float) and type(totals[1].get(k)) in (int,float)},
            'actual_provider_timing': None, 'actual_provider_billing': None}


def analyze(root, freeze_path, quality=None, judgments=None):
    frozen = read(freeze_path)
    prompt = digest((NS / 'inputs/PROMPT.txt').read_bytes())
    require(frozen['prompt_sha256'] == prompt, 'analysis_prompt_no_longer_matches_frozen_prompt')
    freeze = {**frozen, 'sha256': digest(freeze_path.read_bytes())}
    slots = {label: summarize((root / 'slots' / label).resolve(), freeze, (quality or {}).get(label),
                              (judgments or {}).get(label, {})) for label in LABELS}
    return {'schema': 'm3-rounded-witness-actual-consumption-v1', 'freeze_sha256': freeze['sha256'], **compare(slots)}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root', type=Path, default=RUNTIME)
    cli.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    cli.add_argument('--quality', type=Path)
    cli.add_argument('--judgments', type=Path)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    result = analyze(args.root, args.freeze, read(args.quality) if args.quality else None,
                     read(args.judgments) if args.judgments else None)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
