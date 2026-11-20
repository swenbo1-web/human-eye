"""Grade the current plugin slot with the sealed original nine-item rubric."""

import argparse
from fractions import Fraction
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
HISTORY = NS.parent / 'm4_cross_scale_live_task_formal_001'
RUNTIME = Path('D:/he_m4_cross_scale_brief_entry_001')
SLOT_LABEL = 'P1'

sys.path.insert(0, str(HISTORY / 'scoring'))
from formal import (ASSET_BINDING_SHA, GATES, PRODUCT_SHA, TRUTH_SHA, digest, frame_checks,
                    read, require, rounded, terminal, verified, write)

sys.path.insert(0, str(NS / 'harness'))
from admission import validate_admission


def scoring_context():
    truth_path = HISTORY / 'fixture/CURRENT_TRUTH.json'
    truth_raw = verified(truth_path, TRUTH_SHA, HISTORY)
    truth_copy = verified(NS / 'fixture/CURRENT_TRUTH.json', TRUTH_SHA, NS)
    require(truth_raw == truth_copy, 'current_truth_differs_from_historical_fixture')
    expected = read(truth_path)
    require(expected['current_blender_evaluated_readback'] is True, 'Blender_evaluated_truth_required')
    asset = NS / 'fixture/ASSET_BINDING.json'
    verified(asset, ASSET_BINDING_SHA, NS)
    freeze_path, permit_path = NS / 'FROZEN.json', NS / 'ADMISSION.json'
    freeze, permit = read(freeze_path), read(permit_path)
    pins = {Path(row['path']).resolve(): row for row in freeze['direct_inputs']}
    for pinned in (Path(__file__), HISTORY / 'scoring/formal.py', HISTORY / 'RUBRIC.md'):
        raw = pinned.read_bytes()
        pin = pins.get(pinned.resolve(), {})
        require(pin.get('sha256') == digest(raw) and pin.get('bytes') == len(raw),
                'unfrozen_scoring_input/' + pinned.name)
    binding = {'admission_sha256': digest(permit_path.read_bytes()),
               'freeze_sha256': digest(freeze_path.read_bytes())}
    require(type(permit['passed']) is bool and permit['slots'] == freeze['slots'] == [SLOT_LABEL] and
            permit['asset_sha256'] == expected['asset_sha256'] and permit['product_source_sha256'] == PRODUCT_SHA and
            permit['freeze_sha256'] == binding['freeze_sha256'], 'one_slot_admission_mismatch')
    if permit['passed']:
        require(validate_admission(SLOT_LABEL, freeze_path) == binding, 'scorer_admission_binding_mismatch')
    return expected, binding, permit['passed']


def sealed_original(slot, binding, asset_sha):
    seals = read(NS / 'ANSWERS_SEALED.json')
    require(seals['replacement_consumers'] == 0 and [row['slot'] for row in seals['answers']] == [SLOT_LABEL],
            'answer_denominator_or_replacement_changed')
    row = seals['answers'][0]
    if not (slot / 'SLOT_STARTED.json').is_file():
        require(row['status'] == 'unrun' and not row.get('path') and not row.get('sha256'),
                'seal_claims_unstarted_slot_ran')
        return row, None
    started = read(slot / 'SLOT_STARTED.json')
    result_path = slot / 'SLOT_RESULT.json'
    outcome, publication = read(result_path), read(slot / 'SLOT_PUBLICATION.json')
    require(digest(result_path.read_bytes()) == publication['result_sha256'] == row['slot_result_sha256'] and
            publication['status'] == outcome['status'] == row['status'] and
            publication['published_ns'] == row['published_ns'] and
            all(event['label'] == event['slot'] == SLOT_LABEL for event in (started, outcome, publication)) and
            all(event['asset_sha256'] == asset_sha and event['paid_API_calls'] == 0 and
                all(event[key] == value for key, value in binding.items()) for event in (started, outcome)),
            'original_slot_result_or_admission_mismatch')
    answer = outcome.get('answer')
    if answer is not None:
        path = (slot / 'consumer/PUBLIC_FINAL.txt').resolve()
        require(Path(answer['path']).resolve() == Path(row['original_path']).resolve() == path and
                answer['sha256'] == row['sha256'] and answer['bytes'] == row['bytes'],
                'answer_seal_does_not_identify_original_public_answer')
        raw = verified(path, row['sha256'], slot)
        copy = verified(row['path'], row['sha256'], NS)
        require(raw == copy and len(raw) == row['bytes'], 'sealed_public_answer_changed')
    else:
        require(not row.get('path') and not row.get('sha256'), 'no_original_public_answer_to_seal')
    require(type(outcome['model_consumers']) is int and outcome['model_consumers'] in (0, 1),
            'original_plugin_consumer_count_outside_contract')
    if outcome['status'] == 'completed':
        require(outcome['model_consumers'] == 1 and outcome['actual_model_admitted'] is True and
                publication['owned_budget_passed'] is True and answer is not None,
                'completed_slot_without_original_consumer_answer_or_budget')
    return row, outcome


def evidence():
    expected, binding, admitted = scoring_context()
    slot = RUNTIME / 'slots' / SLOT_LABEL
    report = {**binding, 'admission_passed': admitted, 'independent_truth_sha256': TRUTH_SHA,
              'formal_denominator': 1, 'slots': []}
    if not admitted:
        require(not (slot / 'SLOT_STARTED.json').is_file(), 'slot_started_despite_failed_admission')
        report['slots'].append({'slot': SLOT_LABEL, 'status': 'unrun', 'reason': 'admission_failed'})
        return report
    sealed, outcome = sealed_original(slot, binding, expected['asset_sha256'])
    report['answers_sealed_sha256'] = digest((NS / 'ANSWERS_SEALED.json').read_bytes())
    record = {'slot': SLOT_LABEL, 'status': sealed['status'], 'answer_sha256': sealed.get('sha256')}
    report['slots'].append(record)
    if outcome is not None:
        record.update(slot_result_sha256=sealed['slot_result_sha256'], model_consumers=outcome['model_consumers'])
    if sealed.get('path'):
        binding_path = NS.parent / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
        sys.path.insert(0, read(binding_path)['dependency_root'])
        try:
            native, receipt = terminal(slot, outcome, expected['asset_sha256'])
            record.update(current_read_only=receipt, frames=frame_checks(slot, native, expected))
        except Exception as error:
            record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return report


def check_pass(key, row, expected, source):
    if key == 'roster':
        require(sorted(row['objects']) == sorted(expected), 'claimed_region_set_differs')
    elif key.startswith('geometry_'):
        reference = expected[key.split('_', 1)[1]]
        require(row['triangles'] == reference['source_triangle_indices'] and
                rounded(row['area_m2'], reference['area_m2']) and
                all(rounded(a, b) for a, b in zip(row['center_world_m'], reference['center_world_m'], strict=True)) and
                all(rounded(a, b) for a, b in zip(row['unit_normal'], reference['unit_normal'], strict=True)),
                'claimed_geometry_differs_from_exact_current_truth/' + key)
    elif key.startswith('witness_'):
        frame = source['frames'][row['resolved_delivered_ref']]
        witness = frame['witnesses'][key.split('_', 1)[1]]
        require(witness['qualifies'] and row['direction'] == frame['view'], 'cited_delivered_frame_does_not_qualify/' + key)
        for quantity in ('surface_pixels', 'contrasting_boundary_pixels'):
            require(quantity not in row or row[quantity] == witness[quantity], 'cited_pixel_count_differs/' + quantity)
    elif key == 'finite_pool_unknown_M06':
        reference = expected['M06']
        proofs = reference['finite_direction_proofs']
        occluders = [{o['object_name'] for o in proof['positive_area_occluders']
                      if Fraction(o['rectangle_overlap_fraction']) > 0} for proof in proofs.values()]
        require(len(proofs) == 6 and not reference['eligible_complete_views'] and
                all(occluders) and all(proof['whole_region_clear'] is False for proof in proofs.values()) and
                (row.get('blocker') is None or all(row['blocker'] in names for names in occluders)),
                'claimed_finite_occlusion_or_blocker_differs_from_truth')
    elif key == 'read_only_current_identity':
        require(bool(source.get('current_read_only')), 'current_read_only_source_not_verified')


def grade(original, claims):
    expected, binding, admitted = scoring_context()
    require(original['slots'][0]['slot'] == SLOT_LABEL and original == evidence(),
            'grade_does_not_bind_current_original_evidence')
    source = original['slots'][0]
    answer_sha = source.get('answer_sha256')
    if answer_sha is None:
        require(not claims, 'unrun_or_no_answer_has_no_claims')
        gates = {name: {'status': 'unrun', 'reason': source.get('reason', 'original_has_no_sealed_answer')} for name in GATES}
    else:
        require(set(claims) == {SLOT_LABEL}, 'grading_claims_must_bind_only_current_plugin_slot')
        annotation = claims[SLOT_LABEL]
        require(annotation['answer_sha256'] == answer_sha, 'graded_answer_changed')
        sealed = read(NS / 'ANSWERS_SEALED.json')['answers'][0]
        answer = verified(sealed['path'], answer_sha, NS).decode('utf8')
        reference = {row['object_name']: row for row in expected['eligible']}
        gates = annotation['gates']
        require(set(gates) == set(GATES), 'grading_criterion_set_changed')
        for key, row in gates.items():
            state = row['status']
            require(state in {'pass', 'fail', 'unverified'}, 'grade_status_invalid')
            if state == 'pass':
                require(bool(row['quote']) and row['quote'] in answer, 'positive_grade_requires_verbatim_answer_quote/' + key)
                check_pass(key, row, reference, source)
            else:
                require(bool(row.get('reason')), 'negative_grade_requires_reason/' + key)
    return {**binding, 'formal_denominator': 1, 'criteria_per_slot': len(GATES), 'admission_passed': admitted,
            'formal_evidence_sha256': digest((HERE / 'FORMAL_EVIDENCE.json').read_bytes()),
            'slots': [{'slot': SLOT_LABEL, 'runtime_status': source['status'], 'answer_sha256': answer_sha,
                       'passed': sum(row['status'] == 'pass' for row in gates.values()),
                       'denominator': len(GATES), 'criteria': gates}]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims) if args.claims else {}))
