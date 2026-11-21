"""Admit one serial N/P pair and attest original closed publications."""

from pathlib import Path

from common import ASSET_SHA256, CATALOGUE, EXTERNAL, NS, ORDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, SLOTS, read, sha


SCHEMA = 'perf050-source-scope-rank-transfer-001-v1'


def registered_product():
    binding = read(PRODUCT_BINDING)
    if ({'commit': binding['preparation_git'], 'source_sha256': binding['source_sha256'],
            'wheel_sha256': binding['wheel_sha256']} != PRODUCT or len(binding['source_manifest']) != 143):
        raise ValueError('fixed_existing_pilot_install_required')
    return dict(PRODUCT)


def verify_freeze(path=None):
    expected = NS / 'FROZEN.json'
    path = expected if path is None else Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError('only_current_pilot_freeze_is_admissible')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['product'] != registered_product() or frozen['asset_sha256'] != ASSET_SHA256
            or frozen['passed_offline_preflight'] is not True):
        raise ValueError('pilot_candidate_order_asset_or_preflight_changed')
    paths = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve()
        if (source in paths or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']):
            raise ValueError('frozen_input_changed/' + str(source))
        paths.add(source)
    required = (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, NS / 'harness/HOST_PREFLIGHT.json',
                NS / 'consumer/PREFLIGHT.json', NS / 'checks/TRUTH.json')
    if not {item.resolve() for item in required} <= paths:
        raise ValueError('candidate_install_or_preflight_not_pinned')
    return sha(path)


def publication(label, frozen):
    if label not in SLOTS:
        raise ValueError('registered_serial_pilot_slot_required')
    slot = EXTERNAL / 'slots' / label
    raw = slot / 'SLOT_RESULT.json'
    result, receipt = read(raw), read(slot / 'SLOT_PUBLICATION.json')
    if (receipt['result_sha256'] != sha(raw) or result['freeze_sha256'] != frozen
            or result['label'] != label or receipt['label'] != label
            or (result['group'], result['phase']) != SLOTS[label]
            or result['asset_sha256'] != ASSET_SHA256 or result['product_binding_sha256'] != sha(PRODUCT_BINDING)):
        raise ValueError('original_slot_receipt_identity_mismatch/' + label)
    return result, receipt


def can_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    safe = (receipt.get('owned_budget_passed') is True and result['status'] == receipt['status']
            and result.get('paid_API_calls') == 0 and closure.get('passed') is True)
    if not safe:
        return False
    if closure['status'] == 'startup_failed_clean':
        return result.get('model_consumers') == 0 and not result.get('owner_close')
    consumer = result.get('consumer') or {}
    close = result.get('owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (closure['status'] == 'ready_closed' and closure['mcp_closure_required'] == (result['group'] == 'P')
            and close.get('confirmed') is True and not close.get('errors') and not close.get('transport_errors')
            and (result.get('independent_before_after') or {}).get('passed') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0
            and (not result.get('actual_model_admitted') or consumer.get('safe_to_continue') is True))


def validate_admission(label, path):
    if label not in SLOTS:
        raise ValueError('registered_serial_pilot_slot_required')
    frozen = verify_freeze(path)
    slots = EXTERNAL / 'slots'
    prior = list(ORDER[:ORDER.index(label)])
    names = {item.name for item in slots.iterdir()} if slots.is_dir() else set()
    if names != set(prior) or any(not can_continue(*publication(name, frozen)) for name in prior):
        raise ValueError('unexpected_pilot_slot_order_or_unconfirmed_predecessor')
    if SLOTS[label][1] == 'formal':
        for name in ('QN', 'QP'):
            result, receipt = publication(name, frozen)
            reopens = read(EXTERNAL / 'preflight' / f'{name}_CLOSED_IMAGES.json')
            proofs = {'common': result['qualification']['common_image']}
            if name == 'QP':
                proofs['product'] = result['qualification']['product_image']
            if (result['status'] != 'completed' or result.get('model_consumers') != 0
                    or result.get('qualification') != read(EXTERNAL / 'slots' / name / 'QUALIFICATION.json')
                    or result['qualification'].get('passed') is not True or reopens['passed'] is not True
                    or reopens['freeze_sha256'] != frozen or reopens['result_sha256'] != receipt['result_sha256']
                    or reopens['reopened'] != proofs or any(sha(row['path']) != row['sha256'] for row in proofs.values())):
                raise ValueError('current_source_scope_qualification_required/' + name)
    return {'freeze_sha256': frozen}
