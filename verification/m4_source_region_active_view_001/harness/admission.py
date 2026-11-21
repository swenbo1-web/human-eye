"""Admit only the two frozen, ordered, zero-model source-region slots."""

from pathlib import Path

from budget import LIMITS
from common import (ASSET, ASSET_SHA256, BINDINGS, CATALOGUE, EXTERNAL, NS, ORDER,
                    PRODUCT_SCHEMA, REQUEST, SLOTS, product, read, sha)


SCHEMA = 'm4-source-region-active-view-v1'


def registered_products():
    products = {label: product(label) for label in ORDER}
    if (products['A']['commit'], products['A']['source_sha256']) != (
            '3e6a41afc151162bdde1d4ba2247541a4c9616b4',
            '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd'):
        raise ValueError('original_active_view_baseline_changed')
    if any(products['A'][key] == value for key, value in products['B'].items()):
        raise ValueError('candidate_must_have_a_distinct_installed_identity')
    return products


def verify_freeze(path=None):
    expected = NS / 'FROZEN.json'
    path = expected if path is None else Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError('only_current_active_view_freeze_is_admissible')
    record = read(path)
    if (record['schema'] != SCHEMA or record['slots'] != list(ORDER)
            or record['products'] != registered_products()
            or record['asset_sha256'] != ASSET_SHA256
            or record['passed_offline_preflight'] is not True
            or record.get('ledger_limits', LIMITS) != LIMITS):
        raise ValueError('fixed_active_view_candidate_order_or_preflight_changed')
    pins = {}
    for item in record['direct_inputs']:
        path = Path(item['path']).resolve()
        if (path in pins or not path.is_file() or path.stat().st_size != item['bytes']
                or sha(path) != item['sha256']):
            raise ValueError('frozen_active_view_input_changed/' + str(path))
        pins[path] = item['sha256']
    required = {ASSET, REQUEST, PRODUCT_SCHEMA, CATALOGUE, *BINDINGS.values(), NS / 'harness/HOST_PREFLIGHT.json'}
    required.update(Path(read(path)['wheel_path']) for path in BINDINGS.values())
    if not {p.resolve() for p in required} <= pins.keys() or pins[ASSET.resolve()] != ASSET_SHA256:
        raise ValueError('critical_active_view_input_not_frozen')
    return sha(expected)


def publication(label, frozen):
    if label not in ORDER:
        raise ValueError('registered_active_view_slot_required')
    directory = EXTERNAL / 'slots' / label
    result_path = directory / 'SLOT_RESULT.json'
    result, receipt = read(result_path), read(directory / 'SLOT_PUBLICATION.json')
    binding = product(label)
    if (receipt['result_sha256'] != sha(result_path) or result['freeze_sha256'] != frozen
            or result['label'] != receipt['label'] or result['label'] != label or result['arm'] != label
            or (result['group'], result['phase']) != SLOTS[label]
            or result['asset_sha256'] != ASSET_SHA256 or result['product_binding_sha256'] != sha(BINDINGS[label])
            or (result['product_git'], result['product_source_sha256']) != (binding['commit'], binding['source_sha256'])):
        raise ValueError('original_active_view_publication_identity_mismatch/' + label)
    return result, receipt


def can_continue(result, receipt):
    owner = result.get('outer_owner_close') or {}
    closure = result.get('closure_verification') or {}
    geometry = result.get('independent_before_after') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    if (result['status'] != receipt['status'] or receipt.get('owned_budget_passed') is not True
            or result['model_consumers'] != 0 or result['paid_API_calls'] != 0
            or closure.get('passed') is not True):
        return False
    if closure.get('status') == 'startup_failed_clean':
        return result['status'] == 'failed' and not owner
    return (closure.get('status') == 'ready_closed' and closure.get('mcp_closure_required') is True
            and owner.get('confirmed') is True and owner.get('errors') == owner.get('transport_errors') == []
            and geometry.get('passed') is True and geometry.get('same_owned_scene') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0)


def admit(label):
    if label not in ORDER:
        raise ValueError('only_registered_active_view_label')
    frozen = verify_freeze()
    slots = EXTERNAL / 'slots'
    preceding = ORDER[:ORDER.index(label)]
    names = {p.name for p in slots.iterdir()} if slots.is_dir() else set()
    if names != set(preceding) or any(not can_continue(*publication(name, frozen)) for name in preceding):
        raise ValueError('active_view_order_or_previous_closure_failed')
    return frozen, read(BINDINGS[label])
