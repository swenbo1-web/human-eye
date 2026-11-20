"""Use the registered rail truth, image audit, and quality rules in the new runtime."""

import argparse
import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ORIGINAL = NS.parent / 'm4_rail_blocker_consumption_001/scoring'


def load_prior():
    path = ORIGINAL / 'score.py'
    spec = importlib.util.spec_from_file_location('_rail_original_quality', path)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    # Evidence root is used for the original answer seal. Inputs stay at their original paths.
    prior.NS = NS
    return prior


prior = load_prior()
read, require, digest, verified, write = prior.read, prior.require, prior.digest, prior.verified, prior.write
SLOTS = prior.SLOTS


def evidence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import publication, verify_freeze
    from common import EXTERNAL

    freeze_path = NS / 'FROZEN.json'
    freeze = verify_freeze(freeze_path)
    frozen = read(freeze_path)
    pins = {Path(row['path']).resolve(): row['sha256'] for row in frozen['direct_inputs']}
    gate_path = NS / 'qualification/DERIVED.json'
    gate = digest(gate_path.read_bytes())
    require(gate == frozen['derived_qualification_sha256'], 'formal_scoring_derived_qualification_changed')
    truth = prior.rail_truth()
    for path in (HERE / 'score.py', HERE / 'followups.py', HERE / 'FOLLOWUP_RUBRIC.md',
                 ORIGINAL / 'score.py', ORIGINAL / 'RUBRIC.md', prior.TRUTH, prior.ASSET, prior.SOURCE,
                 *prior.BINDINGS.values()):
        require(pins.get(path.resolve()) == digest(path.read_bytes()), 'unfrozen_formal_scoring_input/' + path.name)
    seals = NS / 'ANSWERS_SEALED.json'
    sealed = read(seals)
    require(sealed['freeze_sha256'] == freeze and tuple(row['slot'] for row in sealed['answers']) == SLOTS,
            'sealed_formal_denominator_or_freeze_changed')
    records = []
    for seal in sealed['answers']:
        label = seal['slot']
        arm = label[0]
        slot = EXTERNAL / 'slots' / label
        record = {'slot': label, 'arm': arm, 'status': seal['status'], 'answer_sha256': seal['sha256']}
        records.append(record)
        if seal['status'] in ('unrun', 'unconfirmed'):
            require(slot.exists() is (seal['status'] == 'unconfirmed') and seal['path'] is None,
                    'unrun_or_unconfirmed_slot_binding_changed/' + label)
            continue
        try:
            result, receipt = publication(label, freeze)
            binding_path = prior.BINDINGS[arm]
            installed = read(binding_path)
            require(receipt['result_sha256'] == seal['slot_result_sha256'] and
                    receipt['published_ns'] == seal['published_ns'] and receipt['status'] == seal['status'] and
                    result['qualification_sha256'] == gate and result['asset_sha256'] == truth['asset_sha256'] and
                    result['product_binding_sha256'] == pins[binding_path.resolve()] and result['paid_API_calls'] == 0,
                    'sealed_answer_not_current_formal_publication')
            if installed['dependency_root'] not in sys.path:
                sys.path.insert(0, installed['dependency_root'])
            packet, read_only = prior.current_source(slot, result)
            record['current_read_only'] = read_only
            record['frames'], record['tools'] = prior.audit_slot(slot, seal, packet, truth, installed, arm)
            attempts = record['tools']['attempts']
            require([call['attempt'] for call in attempts] == list(range(1, len(attempts) + 1)),
                    'formal_attempt_sequence_has_gaps')
            record['first_actual_tool_is_frozen_brief'] = bool(attempts) and (
                attempts[0].get('product') or {}).get('arguments') == prior.REQUEST
        except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as error:
            record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return {'schema': 'm4-rail-blocker-formal-evidence-v1', 'freeze_sha256': freeze,
            'qualification_sha256': gate, 'qualification_passed': True,
            'answers_sealed_sha256': digest(seals.read_bytes()),
            'independent_truth_sha256': pins[prior.TRUTH.resolve()], 'formal_denominator': len(SLOTS), 'slots': records}


def grade(ledger, claims):
    require(ledger == evidence(), 'formal_evidence_does_not_match_originals')
    truth = prior.rail_truth()
    source = read(prior.SOURCE)  # Its bytes are pinned by evidence().
    sizes = {row['name']: len(row['evaluated']['triangles']) for row in source['objects']}
    seals = {row['slot']: row for row in read(NS / 'ANSWERS_SEALED.json')['answers']}
    expected = {label for label, seal in seals.items() if seal['path'] is not None}
    require(claims.keys() == expected, 'manual_claims_must_cover_the_actual_original_answers')
    outputs = []
    for record in ledger['slots']:
        label = record['slot']
        if label in expected:
            seal = seals[label]
            answer = verified(seal['path'], seal['sha256'], NS).decode('utf-8')
            outputs.append(prior.grade_slot(record, claims[label], answer, truth, sizes))
        else:
            outputs.append({'slot': label, 'arm': record['arm'], 'status': record['status'], 'passed_quality': False,
                            'blocker_facts_adopted': False, 'reason': 'no_sealed_answer', 'rows': []})
    return {'schema': 'm4-rail-blocker-formal-quality-v1', 'formal_denominator': len(SLOTS),
            'answers_sealed_sha256': ledger['answers_sealed_sha256'],
            'evidence_sha256': digest((HERE / 'FORMAL_EVIDENCE.json').read_bytes()),
            'independent_truth_sha256': ledger['independent_truth_sha256'], 'slots': outputs,
            'complete_counts': {arm: sum(row['passed_quality'] for row in outputs if row['arm'] == arm) for arm in ('A', 'B')},
            'blocker_adoption_count': sum(row['blocker_facts_adopted'] for row in outputs if row['arm'] == 'B')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade', 'followups'))
    parser.add_argument('--claims', type=Path)
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    elif args.action == 'grade':
        require(args.claims is not None, 'sealed_manual_claim_transcriptions_required')
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims)))
    else:
        require(args.claims is not None and args.notes is not None, 'bound_claims_and_followup_notes_required')
        sys.path.insert(0, str(HERE))
        from followups import followups

        ledger = read(HERE / 'FORMAL_EVIDENCE.json')
        quality = read(HERE / 'QUALITY.json')
        require(quality == grade(ledger, read(args.claims)), 'followups_quality_does_not_replay')
        write(HERE / 'FOLLOWUPS.json', followups(ledger, quality, args.notes, HERE))


if __name__ == '__main__':
    main()
