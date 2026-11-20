"""Admit the original dense request once with the frozen candidate installation."""

from pathlib import Path

import common
from budget import LIMITS
from common import (ASSET, BASE_COMMIT, BASE_SOURCE_SHA, DENSE, EXTERNAL, GEOMETRY, NS, ORDER,
                    PRODUCT_BINDING, PROJECTED, read, sha)


SCHEMA = 'm4-dense-region-brief-v1'
CATALOGUE = NS / 'install/TOOLS_SCHEMA.json'
BASE_CATALOGUE = PROJECTED / 'install/TOOLS_SCHEMA.json'
REQUEST = NS / 'inputs/REQUEST.json'
BASE_REQUEST = DENSE / 'inputs/REQUEST.json'
CHANGED = ['human_eye_plugin/live_spatial_mcp.py']


def registered_product():
    binding = read(PRODUCT_BINDING)
    if (binding['historical_preparation_git'] != BASE_COMMIT
            or binding['historical_source_sha256'] != BASE_SOURCE_SHA
            or binding['changed_product_sources'] != CHANGED
            or binding['preparation_git'] == BASE_COMMIT or binding['source_sha256'] == BASE_SOURCE_SHA
            or len(binding['source_manifest']) != 143):
        raise ValueError('candidate_installation_not_bound_to_single_formatter_change')
    return {'commit': binding['preparation_git'], 'source_sha256': binding['source_sha256']}


def verify_freeze():
    path = NS / 'FROZEN.json'
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['product'] != registered_product()):
        raise ValueError('registered_dense_brief_scope_or_limits_changed')
    binding = read(PRODUCT_BINDING)
    wheel = Path(binding['wheel_path'])
    required = {
        ASSET, GEOMETRY, PRODUCT_BINDING, wheel, CATALOGUE, BASE_CATALOGUE, REQUEST, BASE_REQUEST,
        NS / 'inputs/PRODUCT_SCHEMA.json', NS / 'harness/run_slot.py',
        DENSE / 'harness/run_slot.py', DENSE / 'harness/budget.py', DENSE / 'harness/common.py',
    }
    pins = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path'])
        if not source.is_file() or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']:
            raise ValueError('frozen_evidence_or_runtime_changed/' + str(source))
        pins.add(source.resolve())
    if not pins.issuperset(source.resolve() for source in required):
        raise ValueError('required_dense_brief_inputs_not_frozen')
    if (sha(wheel) != binding['wheel_sha256'] or CATALOGUE.read_bytes() != BASE_CATALOGUE.read_bytes()
            or REQUEST.read_bytes() != BASE_REQUEST.read_bytes()):
        raise ValueError('registered_wheel_tool_catalogue_or_dense_request_changed')
    return sha(path)


def admit(label):
    if label != ORDER[0]:
        raise ValueError('registered_zero_model_product_qualification_required')
    frozen = verify_freeze()
    slots = EXTERNAL / 'slots'
    if slots.exists() and any(slots.iterdir()):
        raise ValueError('qualification_already_consumed_or_slot_order_changed')
    binding = read(PRODUCT_BINDING)
    # The retained runtime imports its installed identity when the slot starts.
    common.SOURCE_SHA = binding['source_sha256']
    return frozen, binding
