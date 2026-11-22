"""Admit the one recovery qualification and six original-order formal slots."""

from pathlib import Path

from common import ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, NS, ORDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, SLOTS, read, sha


SCHEMA = 'perf050-dense-micro-surface-holdout-recovery-001-v1'
QN_DERIVED = NS / 'qualification/QN_DERIVED_ADMISSION.json'


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
            or frozen['product'] != registered_product() or Path(frozen['asset_path']) != ASSET
            or frozen['asset_sha256'] != ASSET_SHA256
            or frozen['passed_offline_preflight'] is not True):
        raise ValueError('pilot_candidate_order_asset_or_preflight_changed')
    paths = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve()
        if (source in paths or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']):
            raise ValueError('frozen_input_changed/' + str(source))
        paths.add(source)
    required = (ASSET, PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, NS / 'harness/HOST_PREFLIGHT.json',
                NS / 'consumer/PREFLIGHT.json', QN_DERIVED, NS / 'qualification/PREFLIGHT.json',
                NS / 'checks/SCORER_PREFLIGHT.json')
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
            or result['asset_sha256'] != read(NS / 'FROZEN.json')['asset_sha256'] or result['product_binding_sha256'] != sha(PRODUCT_BINDING)):
        raise ValueError('original_slot_receipt_identity_mismatch/' + label)
    return result, receipt


def can_continue(result, receipt):
    closure = result.get('closure_verification')
    if not isinstance(closure, dict):
        return False
    safe = (receipt.get('owned_budget_passed') is True and result['status'] == receipt['status']
            and result.get('paid_API_calls') == 0 and closure.get('passed') is True)
    if not safe:
        return False
    if closure.get('status') == 'startup_failed_clean':
        return result.get('model_consumers') == 0 and not result.get('owner_close')
    consumer = result.get('consumer') or {}
    close = result.get('owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (closure.get('status') == 'ready_closed' and closure.get('mcp_closure_required') is (result['group'] == 'P')
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
        result, receipt = publication('QP', frozen)
        verify_qp_gate(EXTERNAL, frozen, result, receipt)
    return {'freeze_sha256': frozen}


def verify_qp_gate(root, frozen, result, receipt):
    gate = read(root / 'preflight/QP_CLOSED_GATE.json')
    proof_path = root / 'preflight/QP_CLOSED_PROOF.json'
    proof = read(proof_path)
    positive = gate['passed'] is True and proof['passed'] is True and read(QN_DERIVED)['passed'] is True
    matching = (gate['freeze_sha256']==frozen and gate['result_sha256']==receipt['result_sha256']
                and gate['qn_derived_sha256']==sha(QN_DERIVED) and gate['proof_sha256']==sha(proof_path))
    complete = (result['status']=='completed' and result['model_consumers']==0
                and (result.get('qualification_pending') or {}).get('phase')=='public_calls_completed_pending_owned_close'
                and result['closure_verification']['status']=='ready_closed' and can_continue(result,receipt)
                and gate['verified_ns'] < result['owned_deadline_ns'])
    images = proof['images']
    original_images = set(images)=={'S021','S055'} and all(row['complete'] and sha(row['path'])==row['sha256']
         and Path(row['path']).stat().st_size==row['bytes'] for row in images.values())
    if not (positive and matching and complete and original_images):
        raise ValueError('current_closed_QP_and_archived_QN_qualification_required')
    return gate
