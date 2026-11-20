"""Admit only the two original qualification slots and one formal pair."""

from pathlib import Path

from budget import LIMITS
from common import EXTERNAL, NS, SLOTS, SOURCE_SHA, asset_identity, read, sha


SCHEMA = 'm4-cross-scale-assembly-transfer-v1'
PRODUCT_GIT = '21e608db565cf20d21fca735f913ae780e231470'
QUALIFICATION = ('QN', 'QP')


def verify_freeze(path):
    if path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_transfer_freeze_required')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(SLOTS) or frozen['ledger_limits'] != LIMITS
            or frozen['product_git'] != PRODUCT_GIT or frozen['product_source_sha256'] != SOURCE_SHA):
        raise ValueError('original_assembly_transfer_limits_or_product_changed')
    for row in frozen['direct_inputs']:
        source = Path(row['path'])
        if not source.is_file() or source.stat().st_size != row['bytes'] or sha(source) != row['sha256']:
            raise ValueError('assembly_transfer_frozen_input_changed/' + str(source))
    return sha(path)


def publication(label, frozen):
    folder = EXTERNAL / 'slots' / label
    raw = folder / 'SLOT_RESULT.json'
    result = read(raw)
    receipt = read(folder / 'SLOT_PUBLICATION.json')
    if (result['label'] != label or receipt['label'] != label or receipt['result_sha256'] != sha(raw)
            or result['freeze_sha256'] != frozen):
        raise ValueError('original_slot_result_publication_changed/' + label)
    return result, receipt


def validate_admission(label, freeze_path):
    frozen = verify_freeze(freeze_path)
    slots = EXTERNAL / 'slots'
    expected = tuple(SLOTS)[:tuple(SLOTS).index(label)]
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(expected):
        raise ValueError('original_schedule_or_replacement_changed')
    for earlier in expected:
        publication(earlier, frozen)
    if label in QUALIFICATION:
        return {'freeze_sha256': frozen}
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path)
    asset, asset_sha = asset_identity()
    rows = gate['slots']
    if (gate['passed'] is not True or gate['freeze_sha256'] != frozen
            or [row['label'] for row in rows] != list(QUALIFICATION)):
        raise ValueError('both_original_asset_qualifications_required')
    for row in rows:
        result, receipt = publication(row['label'], frozen)
        if (receipt['status'] != 'completed' or result['status'] != 'completed'
                or result['asset_sha256'] != asset_sha or result['model_consumers'] != 0
                or result.get('independent_before_after', {}).get('passed') is not True
                or row['result_sha256'] != receipt['result_sha256']):
            raise ValueError('qualification_result_not_original_closed_zero_model_slot/' + row['label'])
    return {'freeze_sha256': frozen, 'qualification_sha256': sha(gate_path)}
