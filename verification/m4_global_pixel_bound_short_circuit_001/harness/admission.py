"""Admit only the frozen symmetric engineering experiment."""

from pathlib import Path

from budget import LIMITS
from common import (ARMS, ASSET, ASSET_SHA256, BINDINGS, CATALOGUE, EXTERNAL, GEOMETRY, GEOMETRY_SHA256,
                    NS, ORDER, PRODUCT_SCHEMA, REQUEST, SLOTS, TRUTH, read, sha)


SCHEMA = 'm4-global-pixel-bound-short-circuit-v1'
BASELINE = {'commit': 'e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c',
            'source_sha256': '84bf65eedbc0866375d760025437993b90ec54325af09b4e1f36b74abe233d62'}
CHANGED = ['human_eye_plugin/active_observation_region_task.py']


def registered_products():
    baseline, candidate = (read(BINDINGS[arm]) for arm in ('A', 'B'))
    if (baseline['preparation_git'] != BASELINE['commit'] or baseline['source_sha256'] != BASELINE['source_sha256']
            or candidate['historical_preparation_git'] != BASELINE['commit']
            or candidate['historical_source_sha256'] != BASELINE['source_sha256']
            or candidate['changed_product_sources'] != CHANGED
            or candidate['preparation_git'] == BASELINE['commit']
            or candidate['source_sha256'] == BASELINE['source_sha256']
            or len(baseline['source_manifest']) != 143 or len(candidate['source_manifest']) != 143
            or baseline['dependency_root'] != candidate['dependency_root']):
        raise ValueError('isolated_pixel_bound_product_identity_changed')
    before, after = ({row['path']: row['sha256'] for row in item['source_manifest']} for item in (baseline, candidate))
    if (len(before) != 143 or before.keys() != after.keys()
            or [name for name in before if before[name] != after[name]] != CHANGED):
        raise ValueError('single_installed_source_delta_required')
    return {'A': BASELINE, 'B': {'commit': candidate['preparation_git'], 'source_sha256': candidate['source_sha256']}}


def verify_freeze(path=None):
    expected = NS / 'FROZEN.json'
    path = expected if path is None else Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError('registered_pixel_bound_freeze_required')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['products'] != registered_products()):
        raise ValueError('pixel_bound_frozen_schedule_or_product_identity_changed')
    pins = {}
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve()
        if (source in pins or not source.is_file() or source.stat().st_size != pin['bytes']
                or sha(source) != pin['sha256']):
            raise ValueError('frozen_runtime_or_evidence_changed/' + str(source))
        pins[source] = pin['sha256']
    required = {ASSET, GEOMETRY, TRUTH, *BINDINGS.values(), CATALOGUE, PRODUCT_SCHEMA, REQUEST,
                NS / 'harness/DISPATCH_PREFLIGHT_RECOVERY.json',
                *(Path(read(item)['wheel_path']) for item in BINDINGS.values())}
    if not {item.resolve() for item in required} <= pins.keys():
        raise ValueError('required_pixel_bound_direct_inputs_not_frozen')
    if pins[ASSET.resolve()] != ASSET_SHA256 or pins[GEOMETRY.resolve()] != GEOMETRY_SHA256:
        raise ValueError('dense_asset_or_geometry_pin_changed')
    return sha(path)


def publication(label, frozen):
    if label not in SLOTS:
        raise ValueError('unregistered_pixel_bound_slot')
    folder = EXTERNAL / 'slots' / label
    path = folder / 'SLOT_RESULT.json'
    result, receipt = read(path), read(folder / 'SLOT_PUBLICATION.json')
    binding_path = BINDINGS[ARMS[label]]
    binding = read(binding_path)
    if (result['label'] != label or receipt['label'] != label or receipt['result_sha256'] != sha(path)
            or result['freeze_sha256'] != frozen or result['asset_sha256'] != ASSET_SHA256
            or result['product_git'] != binding['preparation_git'] or result['product_source_sha256'] != binding['source_sha256']
            or result['product_binding_sha256'] != sha(binding_path) or result['arm'] != ARMS[label]
            or (result['group'], result['phase']) != SLOTS[label]):
        raise ValueError('actual_slot_result_mismatches_frozen_product_or_publication/' + label)
    return result, receipt


def can_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    readback = result.get('independent_before_after') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (result['status'] == receipt['status'] and receipt.get('owned_budget_passed') is True
            and result['model_consumers'] == result['paid_API_calls'] == 0
            and closure.get('passed') is True and closure.get('status') == 'ready_closed'
            and closure.get('mcp_closure_required') is True
            and readback.get('passed') is True and readback.get('same_owned_scene') is True
            and counts.get('Blender_spawned_unknown') == counts.get('pending_raster_reservations') == 0)


def admit(label):
    if label not in SLOTS:
        raise ValueError('unregistered_pixel_bound_slot')
    frozen = verify_freeze()
    prior = ORDER[:ORDER.index(label)]
    slots = EXTERNAL / 'slots'
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(prior):
        raise ValueError('slot_order_or_replacement_changed')
    for predecessor in prior:
        result, receipt = publication(predecessor, frozen)
        if not can_continue(result, receipt):
            raise ValueError('previous_slot_has_unconfirmed_lifecycle/' + predecessor)
    return frozen, read(BINDINGS[ARMS[label]])
