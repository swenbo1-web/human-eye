"""Admit the fixed A then B qualification under the current file identities."""

from pathlib import Path

from budget import LIMITS
from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, GEOMETRY, GEOMETRY_SHA256, NS, ORDER,
                    PRODUCT_BINDING, PRODUCT_GIT, PRODUCT_SCHEMA, REQUESTS, SOURCE_SHA, TRUTH, WHEEL_SHA, read, sha)


SCHEMA = 'm5-global-observe-measure-qualification-v1'


def registered_product():
    binding = read(PRODUCT_BINDING)
    fields = binding['preparation_git'], binding['source_sha256'], binding['wheel_sha256'], len(binding['source_manifest'])
    if fields != (PRODUCT_GIT, SOURCE_SHA, WHEEL_SHA, 143):
        raise ValueError('fixed_same_installed_product_required')
    return {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}


def verify_freeze(path=None):
    expected = NS / 'FROZEN.json'
    path = expected if path is None else Path(path)
    if path.resolve() != expected.resolve():
        raise ValueError('only_current_qualification_freeze_is_admissible')
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['product'] != registered_product()):
        raise ValueError('registered_qualification_scope_changed')
    pinned = {}
    for pin in frozen['direct_inputs']:
        source = Path(pin['path']).resolve()
        if (source in pinned or not source.is_file() or source.stat().st_size != pin['bytes']
                or sha(source) != pin['sha256']):
            raise ValueError('frozen_input_changed/' + str(source))
        pinned[source] = pin['sha256']
    required = {ASSET, GEOMETRY, TRUTH, PRODUCT_BINDING, CATALOGUE, PRODUCT_SCHEMA, *REQUESTS.values(),
                Path(read(PRODUCT_BINDING)['wheel_path']), NS / 'harness/DISPATCH_PREFLIGHT.json'}
    if not {path.resolve() for path in required} <= pinned.keys():
        raise ValueError('qualification_required_inputs_missing')
    if (pinned[ASSET.resolve()] != ASSET_SHA256 or pinned[GEOMETRY.resolve()] != GEOMETRY_SHA256
            or pinned[Path(read(PRODUCT_BINDING)['wheel_path']).resolve()] != WHEEL_SHA):
        raise ValueError('qualified_asset_geometry_or_wheel_changed')
    return sha(path)


def publication(label, frozen):
    if label not in ORDER:
        raise ValueError('unregistered_qualification_label')
    slot = EXTERNAL / 'slots' / label
    result_path = slot / 'SLOT_RESULT.json'
    result, receipt = read(result_path), read(slot / 'SLOT_PUBLICATION.json')
    if (receipt['label'] != label or receipt['result_sha256'] != sha(result_path)
            or result['label'] != label or result['arm'] != label or result['freeze_sha256'] != frozen
            or result['group'] != 'P' or result['phase'] != 'qualification' or result['product_git'] != PRODUCT_GIT
            or result['product_source_sha256'] != SOURCE_SHA or result['product_binding_sha256'] != sha(PRODUCT_BINDING)
            or result['asset_sha256'] != ASSET_SHA256):
        raise ValueError('closed_slot_result_mismatches_fixed_identity/' + label)
    return result, receipt


def can_continue(result, receipt):
    closure = result.get('closure_verification') or {}
    before_after = result.get('independent_before_after') or {}
    owner = result.get('outer_owner_close') or {}
    counts = (result.get('budget') or {}).get('counts') or {}
    return (result['status'] == receipt['status'] and receipt.get('owned_budget_passed') is True
            and result['model_consumers'] == result['paid_API_calls'] == 0
            and closure.get('passed') is True and closure.get('status') == 'ready_closed'
            and closure.get('mcp_closure_required') is True and before_after.get('passed') is True
            and before_after.get('same_owned_scene') is True and owner.get('confirmed') is True
            and owner.get('errors') == [] and counts.get('Blender_spawned_unknown') == 0
            and counts.get('pending_raster_reservations') == 0)


def admit(label):
    if label not in ORDER:
        raise ValueError('only_registered_qualification_label')
    frozen = verify_freeze()
    slots = EXTERNAL / 'slots'
    expected = ORDER[:ORDER.index(label)]
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(expected):
        raise ValueError('qualification_order_or_replacement_changed')
    for predecessor in expected:
        result, receipt = publication(predecessor, frozen)
        if not can_continue(result, receipt):
            raise ValueError('previous_slot_has_unconfirmed_lifecycle/' + predecessor)
    return frozen, read(PRODUCT_BINDING)
