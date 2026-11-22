"""Enforce the fixed qualification and consumer sequence."""

from pathlib import Path

from common import ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, NS, ORDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, QUALIFICATION, SLOTS, read, sha


SCHEMA = 'm4-dense-sweep-integrated-native-pilot-001-v1'
PROMPT_SHA256 = '254f79b43eaf77a305a2372a77f26454a3aac75882591b845533ca6c805ce771'
ASSET_SHA = ASSET_SHA256


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def registered_product():
    binding = read(PRODUCT_BINDING)
    current = {'commit': binding['preparation_git'], 'source_sha256': binding['source_sha256'],
               'wheel_sha256': binding['wheel_sha256']}
    require(current == PRODUCT and len(binding['source_manifest']) == 143, 'fixed_existing_pilot_install_required')
    return current


def verify_freeze(path=None):
    expected = NS / 'FROZEN.json'
    chosen = expected if path is None else Path(path)
    require(chosen.resolve() == expected.resolve(), 'only_current_pilot_freeze_is_admissible')
    frozen = read(chosen)
    prompt = NS / 'inputs/PROMPT.txt'
    require(frozen['schema'] == SCHEMA and frozen['slots'] == list(ORDER)
            and frozen['product'] == registered_product()
            and Path(frozen['asset_path']).resolve() == ASSET.resolve()
            and frozen['asset_sha256'] == sha(ASSET) == ASSET_SHA256
            and frozen['prompt_sha256'] == sha(prompt) == PROMPT_SHA256
            and frozen['passed_offline_preflight'] is True, 'pilot_candidate_order_asset_or_preflight_changed')
    paths = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve(strict=True)
        require(source not in paths and source.stat().st_size == pin['bytes'] and sha(source) == pin['sha256'],
                'frozen_source_changed/' + str(source))
        paths.add(source)
    needed = (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, ASSET, prompt, NS / 'harness/RUNTIME_PREFLIGHT.json')
    require({item.resolve() for item in needed} <= paths, 'incomplete_frozen_pilot_inputs')
    return sha(chosen)


def publication(label, freeze):
    require(label in SLOTS, 'registered_slot_required')
    slot = EXTERNAL / 'slots' / label
    path = slot / 'SLOT_RESULT.json'
    result, receipt = read(path), read(slot / 'SLOT_PUBLICATION.json')
    require(result['label'] == receipt['label'] == label and receipt['result_sha256'] == sha(path)
            and (result['group'], result['phase']) == SLOTS[label]
            and result['asset_sha256'] == ASSET_SHA256 and result['freeze_sha256'] == freeze
            and result['product_binding_sha256'] == sha(PRODUCT_BINDING)
            and result['product_source_sha256'] == PRODUCT['source_sha256'],
            'original_slot_publication_binding_changed/' + label)
    return result, receipt


def safe_to_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    owner = result.get('owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    independent = result.get('independent_before_after') or {}
    consumer = result.get('consumer') or {}
    return (receipt.get('owned_budget_passed') is True and result['status'] == receipt['status'] == 'completed'
            and result['paid_API_calls'] == 0 and closure.get('passed') is True
            and closure.get('status') == 'ready_closed' and closure.get('mcp_closure_required') is (result['group'] == 'P')
            and owner.get('confirmed') is True and not owner.get('errors') and not owner.get('transport_errors')
            and independent.get('passed') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0
            and (not result.get('actual_model_admitted') or consumer.get('safe_to_continue') is True))


def qualified(label, freeze):
    require(label in QUALIFICATION, 'active_qualification_slot_required')
    result, receipt = publication(label, freeze)
    folder = EXTERNAL / 'preflight'
    proof = folder / f'{label}_CLOSED_PROOF.json'
    gate = read(folder / f'{label}_CLOSED_GATE.json')
    require(safe_to_continue(result, receipt) and result['model_consumers'] == 0
            and gate['passed'] is True and read(proof)['passed'] is True and gate['freeze_sha256'] == freeze
            and gate['result_sha256'] == receipt['result_sha256'] and gate['proof_sha256'] == sha(proof)
            and receipt['published_ns'] <= gate['verified_ns'] < result['owned_deadline_ns'],
            'active_slot_missing_closed_qualification/' + label)
    return gate


def validate_admission(label, path):
    require(label in SLOTS, 'registered_slot_required')
    freeze = verify_freeze(path)
    prior = ORDER[:ORDER.index(label)]
    slots = EXTERNAL / 'slots'
    names = {item.name for item in slots.iterdir()} if slots.is_dir() else set()
    require(names == set(prior) and all(safe_to_continue(*publication(name, freeze)) for name in prior),
            'unexpected_slot_order_or_unconfirmed_predecessor')
    for name in prior:
        if name in QUALIFICATION:
            qualified(name, freeze)
    return {'freeze_sha256': freeze}
