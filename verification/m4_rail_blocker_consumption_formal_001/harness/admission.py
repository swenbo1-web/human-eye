"""Verify the sealed derived qualification and strictly ordered formal slots."""

from pathlib import Path

from budget import LIMITS
from common import (ARMS, ASSET, ASSET_SHA256, BINDINGS, EXTERNAL, GEOMETRY, GEOMETRY_SHA256,
                    INPUTS, NS, OLD, ORDER, PRODUCTS, SLOTS, TRUTH, load, product_for, read, sha)


SCHEMA = 'm4-rail-blocker-consumption-formal-v1'
DERIVED = NS / 'qualification/DERIVED.json'
_retained = load('_rail_original_admission', OLD / 'harness/admission.py')
host_clean, can_continue = _retained.host_clean, _retained.can_continue


def verify_freeze(path):
    if path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_rail_formal_freeze_required')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER) or frozen['ledger_limits'] != LIMITS
            or frozen['products'] != PRODUCTS):
        raise ValueError('rail_formal_schedule_limits_or_products_changed')
    pins = {}
    for row in frozen['direct_inputs']:
        source = Path(row['path']).resolve()
        if (source in pins or not source.is_file() or source.stat().st_size != row['bytes']
                or sha(source) != row['sha256']):
            raise ValueError('rail_formal_frozen_input_changed/' + str(source))
        pins[source] = row['sha256']
    required = {ASSET, GEOMETRY, TRUTH, *BINDINGS.values(), INPUTS / 'REQUEST.json', INPUTS / 'PROMPT_COMMON.txt',
                INPUTS / 'PRODUCT_SCHEMA.json', INPUTS / 'TOOLS_SCHEMA.json', OLD / 'scoring/RUBRIC.md', DERIVED,
                NS / 'qualification/PREFLIGHT.json', NS / 'harness/DISPATCH_PREFLIGHT.json'}
    if not {item.resolve() for item in required} <= pins.keys():
        raise ValueError('rail_formal_required_inputs_not_pinned')
    if pins[ASSET.resolve()] != ASSET_SHA256 or pins[GEOMETRY.resolve()] != GEOMETRY_SHA256:
        raise ValueError('rail_formal_asset_or_source_identity_changed')
    digest = pins[DERIVED.resolve()]
    if frozen['derived_qualification_sha256'] != digest:
        raise ValueError('rail_formal_freeze_derived_qualification_mismatch')
    derive = load('_rail_formal_qualification', DERIVED.with_name('derive.py'))
    evidence = derive.verify_sealed()
    if evidence.get('passed') is not True or sha(DERIVED) != digest:
        raise ValueError('rail_formal_derived_qualification_invalid')
    if any(pins.get(Path(row['path']).resolve()) != row['sha256'] for row in evidence['source_pins']):
        raise ValueError('rail_formal_derived_original_not_pinned')
    return sha(path)


def publication(label, frozen):
    if label not in SLOTS:
        raise ValueError('registered_formal_slot_required/' + label)
    folder = EXTERNAL / 'slots' / label
    raw = folder / 'SLOT_RESULT.json'
    result = read(raw)
    receipt = read(folder / 'SLOT_PUBLICATION.json')
    binding_path, binding = product_for(label)
    if (result['label'] != label or receipt['label'] != label or receipt['result_sha256'] != sha(raw)
            or result['freeze_sha256'] != frozen or result['qualification_sha256'] != sha(DERIVED)
            or result['asset_sha256'] != ASSET_SHA256 or result['arm'] != ARMS[label]
            or result['product_git'] != binding['preparation_git']
            or result['product_source_sha256'] != binding['source_sha256']
            or result['product_binding_sha256'] != sha(binding_path)
            or (result['group'], result['phase']) != SLOTS[label]):
        raise ValueError('rail_formal_result_publication_or_qualification_changed/' + label)
    return result, receipt


def check_schedule(label, frozen):
    if label not in SLOTS:
        raise ValueError('registered_formal_slot_required/' + label)
    expected = ORDER[:ORDER.index(label)]
    slots = EXTERNAL / 'slots'
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(expected):
        raise ValueError('rail_formal_schedule_or_replacement_changed')
    for earlier in expected:
        result, receipt = publication(earlier, frozen)
        if not can_continue(result, receipt):
            raise ValueError('previous_slot_has_host_or_unknown_state/' + earlier)


def validate_admission(label, freeze_path):
    frozen = verify_freeze(freeze_path)
    check_schedule(label, frozen)
    return {'freeze_sha256': frozen, 'qualification_sha256': sha(DERIVED)}
