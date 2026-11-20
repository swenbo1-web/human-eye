"""Recheck original score gates and actual retained tool transcripts without live execution."""

from copy import deepcopy
from pathlib import Path
import runpy
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from followups import compare, reviewed_attempt, slot_review
from score import ORIGINAL, SLOTS, digest, prior, read, require, write


LEGACY_RUN = Path('D:/he_m4_rail_blocker_consumption_001')


def failing(call, reason):
    try:
        call()
    except (ValueError, OSError) as exc:
        require(str(exc).startswith(reason), 'wrong_control_failure/' + str(exc))
    else:
        raise ValueError('negative_control_accepted/' + reason)


def exact(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}


def inspect_actual_tool(slot, ordinal):
    result = read(slot / 'SLOT_RESULT.json')
    index = result['diagnostic_calls'][ordinal - 1]['transport_index']
    route = slot / 'client/transport' / f'rpc_{index:02d}'
    txp, rxp = route / 'TX.bin', route / 'RX.bin'
    forwarded, = (slot / 'client/attachments').glob(f'bridge_*/{index:03d}')
    owner = slot / 'owner' / f'tool_{ordinal:02d}'
    for raw, relay, host in ((txp, 'TX.bin', 'REQUEST.json'), (rxp, 'RX.bin', 'RESPONSE.json')):
        require(raw.read_bytes() == (forwarded / relay).read_bytes() == (owner / host).read_bytes(),
                'retained_three_layer_original_mismatch')
    tx, rx = read(txp), read(rxp)
    receipt = read(route / 'RECEIPT.json')
    require(tx['id'] == rx['id'] == receipt['id'] and 'TX_sha256' not in receipt and
            receipt['TX_bytes'] == txp.stat().st_size and receipt['RX_sha256'] == exact(rxp)['sha256'],
            'historical_missing_tx_digest_case_not_replayed')
    content = rx['result']['content']
    return {'attempt': ordinal, 'tool': tx['params']['name'], 'TX': exact(txp), 'RX': exact(rxp),
            'is_error': rx['result']['isError'], 'model_visible_as_public_CLI_tool_result': False,
            'text_UTF8_bytes': sum(len(item['text'].encode()) for item in content if item['type'] == 'text'),
            'image_blocks': [index for index, item in enumerate(content) if item['type'] == 'image']}


def bind_note(call, **tags):
    return {'attempt': call['attempt'], 'request_sha256': call['TX']['sha256'],
            'response_sha256': call['RX']['sha256'], **tags}


def historical_controls(targets):
    receipts = []
    for label in ('QA', 'QB'):
        slot = LEGACY_RUN / 'slots' / label
        first, second = [inspect_actual_tool(slot, ordinal) for ordinal in (1, 2)]
        primary = bind_note(first, increment='initial', aim='initial', reason='retained common starting request',
                            request_anchor='region_task', blocker_targets=[], independent_reproof_targets=[])
        extra = bind_note(second, increment='new_evidence', aim='blocker_proof', reason='retained LEFT proof in ordinary tool',
                          request_anchor='check_left(TARGETS)', response_anchor='M12', blocker_targets=sorted(targets),
                          independent_reproof_targets=[], from_attempts=[1])
        first_review = reviewed_attempt(first, primary, slot, targets, {})
        second_review = reviewed_attempt(second, extra, slot, targets, {1: first_review})
        require(not first_review['counts_toward_primary_metric'] and second_review['counts_toward_primary_metric'] and
                second_review['route'] == 'ordinary', 'initial_or_actual_ordinary_followup_misclassified')
        bad = {**extra, 'response_sha256': first['RX']['sha256']}
        failing(lambda: reviewed_attempt(second, bad, slot, targets, {1: first_review}), 'review_not_bound_to_attempt_wire')
        bad = {**extra, 'response_anchor': 'absent'}
        failing(lambda: reviewed_attempt(second, bad, slot, targets, {1: first_review}),
                'tool_review_response_anchor_not_in_original')
        bad = {**extra, 'from_attempts': [2]}
        failing(lambda: reviewed_attempt(second, bad, slot, targets, {1: first_review}),
                'followup_dependency_is_absent_or_not_earlier')
        bad = {**extra, 'independent_reproof_targets': sorted(targets)}
        failing(lambda: reviewed_attempt(second, bad, slot, targets, {1: first_review}),
                'independent_reproof_not_actually_delivered')
        bad = {**extra, 'increment': 'error_recovery'}
        intact = {**first_review, 'CLI_result_bound': True}
        failing(lambda: reviewed_attempt(second, bad, slot, targets, {1: intact}),
                'recovery_without_original_error_or_truncated_context')
        receipts.extend({'slot': label, 'name': call['tool'], 'TX': call['TX'], 'RX': call['RX'],
                         'actual_model_visible': False} for call in (first, second))
    return receipts


def paired_controls(targets):
    empty = {'slot': 'B3', 'status': 'unrun'}
    scored = {'passed_quality': False, 'blocker_facts_adopted': False, 'rows': []}
    unrun = slot_review(empty, scored, None, LEGACY_RUN / 'slots/B3', targets)
    require(unrun['blocker_followups'] is None and not unrun['comparison_eligible'], 'unrun_counted_as_zero_followups')
    rows = [{'slot': label, 'blocker_followups': int(label[0] == 'A'), 'comparison_eligible': True} for label in SLOTS]
    good = compare(rows)
    require(good['followup_gate_passed'] and good['B_fewer_blocker_followup_pairs'] == 3, 'actual_pair_direction_reversed')
    rows = deepcopy(rows)
    rows[-1] = unrun
    rows[1]['comparison_eligible'] = False
    partial = compare(rows)
    require(not partial['followup_gate_passed'] and partial['B_fewer_blocker_followup_pairs'] == 1,
            'incomplete_pairs_dropped_from_denominator')


def adoption_controls(targets):
    slot = LEGACY_RUN / 'slots/QB'
    first, second = [inspect_actual_tool(slot, ordinal) for ordinal in (1, 2)]
    # The chronology transformation below is a synthetic accounting control.
    trusted = {**second, 'model_visible_as_public_CLI_tool_result': True}
    proofs = sorted(targets)
    initial = bind_note(first, increment='initial', aim='initial', reason='initial product observation',
                        request_anchor='region_task', blocker_targets=[], independent_reproof_targets=[])
    recheck = bind_note(trusted, increment='recheck', aim='blocker_proof', reason='independent exact proof',
                        request_anchor='check_left(TARGETS)', response_anchor='M12', blocker_targets=proofs,
                        independent_reproof_targets=proofs, from_attempts=[1])
    original = {'slot': 'B1', 'status': 'completed', 'answer_sha256': None,
                'tools': {'attempts': [first, trusted]}, 'first_actual_tool_is_frozen_brief': True}
    grade = {'rows': [{'region': label, 'blocker': {'region': label}, 'evidence_passed': True} for label in targets],
             'passed_quality': True, 'blocker_facts_adopted': True, 'first_candidate_blocker_regions_used': proofs}
    paired = slot_review(original, grade, {'answer_sha256': None, 'attempts': [initial, recheck]}, slot, targets)
    require(paired['blocker_followups'] == 1 and paired['first_packet_blocker_facts_adopted'] and
            all(row['classification'] == 'matches_first_packet_and_later_independently_rechecked'
                for row in paired['target_use']), 'recheck_erased_first_packet_match_or_repeated_call_count')
    original['tools']['attempts'] = [first]
    direct = slot_review(original, grade, {'answer_sha256': None, 'attempts': [initial]}, slot, targets)
    require(direct['blocker_followups'] == 0 and
            all(row['classification'] == 'matches_first_packet_without_observed_blocker_followup'
                for row in direct['target_use']), 'direct_first_packet_use_misclassified')


def main():
    reused = runpy.run_path(str(ORIGINAL / 'controls.py'))
    truth = prior.rail_truth()
    source = prior.read(prior.SOURCE)
    reused['grade_controls'](truth, {row['name']: len(row['evaluated']['triangles']) for row in source['objects']})
    reused['retained_pixels'](truth)
    targets = {prior.region_label(prior.region_key(region)) for region in truth['eligible']
               if not region['eligible_complete_views']}
    historical = historical_controls(targets)
    paired_controls(targets)
    adoption_controls(targets)
    write(HERE / 'PREFLIGHT.json', {'passed': True, 'actual_model_attempts': 0, 'actual_Blender_launches': 0,
          'original_grade_controls': True, 'original_png_npz_controls': True,
          'wire_anchor_corruption_rejected': True, 'unseen_independent_reproof_rejected': True,
          'unbound_recovery_rejected': True, 'forward_dependency_rejected': True,
          'candidate_match_preserved_with_independent_recheck': True,
          'unrun_is_not_zero_followups': True, 'retained_actual_wire_controls': historical,
          'source_pins': [exact(path) for path in (HERE / 'score.py', HERE / 'followups.py', Path(__file__).resolve(),
                         HERE / 'FOLLOWUP_RUBRIC.md', ORIGINAL / 'score.py', ORIGINAL / 'RUBRIC.md',
                         ORIGINAL / 'controls.py')]})
    print('Verified four retained actual tool deliveries and scored untouched historical controls')


if __name__ == '__main__':
    main()
