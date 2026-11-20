"""Enforce the frozen two-arm, eight-slot schedule and qualification gate."""

from pathlib import Path

from budget import LIMITS
from common import (ARMS, ASSET, ASSET_SHA256, BINDINGS, EXTERNAL, GEOMETRY, GEOMETRY_SHA256, NS,
                    ORDER, PRODUCTS, SLOTS, TRUTH, product_for, read, sha)


SCHEMA = 'm4-rail-blocker-consumption-v1'
GATE_SCHEMA = 'm4-rail-blocker-consumption-qualification-v1'


def verify_freeze(path):
    if path.resolve() != (NS / 'FROZEN.json').resolve():
        raise ValueError('registered_rail_blocker_freeze_required')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER) or frozen['ledger_limits'] != LIMITS
            or frozen['products'] != PRODUCTS):
        raise ValueError('original_rail_blocker_limits_or_products_changed')
    pins = {}
    for row in frozen['direct_inputs']:
        source = Path(row['path']).resolve()
        if (source in pins or not source.is_file() or source.stat().st_size != row['bytes']
                or sha(source) != row['sha256']):
            raise ValueError('rail_blocker_frozen_input_changed/' + str(source))
        pins[source] = row['sha256']
    required = {ASSET, GEOMETRY, TRUTH, *BINDINGS.values(), NS / 'inputs/REQUEST.json',
                NS / 'inputs/PROMPT_COMMON.txt', NS / 'inputs/PRODUCT_SCHEMA.json',
                NS / 'harness/DISPATCH_PREFLIGHT.json'}
    if not {item.resolve() for item in required} <= pins.keys():
        raise ValueError('rail_blocker_required_inputs_not_pinned')
    if pins[ASSET.resolve()] != ASSET_SHA256 or pins[GEOMETRY.resolve()] != GEOMETRY_SHA256:
        raise ValueError('rail_blocker_asset_or_source_identity_changed')
    return sha(path)


def publication(label, frozen):
    folder = EXTERNAL / 'slots' / label
    raw = folder / 'SLOT_RESULT.json'
    result = read(raw)
    receipt = read(folder / 'SLOT_PUBLICATION.json')
    binding_path, binding = product_for(label)
    if (result['label'] != label or receipt['label'] != label or receipt['result_sha256'] != sha(raw)
            or result['freeze_sha256'] != frozen or result['asset_sha256'] != ASSET_SHA256
            or result['arm'] != ARMS[label] or result['product_git'] != binding['preparation_git']
            or result['product_source_sha256'] != binding['source_sha256']
            or result['product_binding_sha256'] != sha(binding_path)
            or (result['group'], result['phase']) != SLOTS[label]):
        raise ValueError('original_slot_result_publication_changed/' + label)
    return result, receipt


def host_clean(result, receipt):
    owner = result.get('owner_close') or {}
    closure = result.get('closure_verification') or {}
    before_after = result.get('independent_before_after') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (receipt.get('owned_budget_passed') is True and owner.get('confirmed') is True
            and owner.get('errors') == owner.get('transport_errors') == []
            and closure.get('status') == 'ready_closed' and closure.get('passed') is True
            and closure.get('mcp_closure_required') is True
            and before_after.get('passed') is True and before_after.get('same_owned_scene') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0)


def can_continue(result, receipt):
    if not host_clean(result, receipt) or not result.get('consumer'):
        return False
    consumer = result['consumer']
    exit_ = consumer.get('runtime_exit') or {}
    actual_consumer = (result.get('model_consumers') == 1 and consumer.get('safe_to_continue') is True
                       and consumer.get('process_reaped') is True and consumer.get('readers_stopped') is True
                       and all(exit_.get(key) is True for key in ('confirmed', 'exited', 'handle_closed')))
    if not actual_consumer:
        return False
    if result['status'] == receipt['status'] == 'completed':
        return consumer.get('valid_completion') is True and result.get('errors') == []
    return (result['status'] == receipt['status'] == 'failed' and bool(result.get('errors'))
            and all(error.get('stage') == 'consumer' for error in result['errors'])
            and not any(error.get('stage') in ('raw_archive', 'business_original_binding')
                        for error in consumer.get('errors', [])))


def clean_qualification(result, receipt):
    return (result['model_consumers'] == result['paid_API_calls'] == 0
            and result['actual_model_admitted'] is False and result['status'] == receipt['status']
            and host_clean(result, receipt))


def check_schedule(label, frozen):
    expected = ORDER[:ORDER.index(label)]
    slots = EXTERNAL / 'slots'
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(expected):
        raise ValueError('original_schedule_or_replacement_changed')
    for earlier in expected:
        result, receipt = publication(earlier, frozen)
        if SLOTS[earlier][1] == 'qualification':
            if not clean_qualification(result, receipt):
                raise ValueError('qualification_not_safely_closed/' + earlier)
        elif not can_continue(result, receipt):
            raise ValueError('previous_slot_has_host_or_unknown_state/' + earlier)


def qualification_rows(frozen):
    rows = []
    for label in ORDER[:2]:
        result, receipt = publication(label, frozen)
        path = NS / 'qualification' / f'{label}_REVIEW.json'
        review = read(path)
        publication_sha = sha(EXTERNAL / 'slots' / label / 'SLOT_PUBLICATION.json')
        if (result['status'] != 'completed' or not clean_qualification(result, receipt)
                or review['label'] != label or review['passed'] is not True or review['freeze_sha256'] != frozen
                or review['slot_result_sha256'] != receipt['result_sha256'] or review['publication_sha256'] != publication_sha):
            raise ValueError('original_qualification_review_failed/' + label)
        rows.append({'label': label, 'passed': True, 'result_sha256': receipt['result_sha256'],
                     'publication_sha256': publication_sha, 'review_sha256': sha(path)})
    return rows


def validate_admission(label, freeze_path):
    frozen = verify_freeze(freeze_path)
    check_schedule(label, frozen)
    if SLOTS[label][1] == 'qualification':
        return {'freeze_sha256': frozen}
    gate_path = NS / 'QUALIFICATION.json'
    gate = read(gate_path)
    if (gate['schema'] != GATE_SCHEMA or gate['passed'] is not True or gate['freeze_sha256'] != frozen
            or gate['slots'] != qualification_rows(frozen)):
        raise ValueError('original_A_and_B_qualifications_required')
    return {'freeze_sha256': frozen, 'qualification_sha256': sha(gate_path)}
