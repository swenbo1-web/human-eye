"""Verify the registered product, asset and first zero-model slot before launch."""

from pathlib import Path

from budget import LIMITS
from common import (
    ASSET, EXTERNAL, GEOMETRY, NS, ORDER, PRODUCT_BINDING, PRODUCT_BINDING_SHA256,
    PRODUCT_COMMIT, PROJECTED, SOURCE_SHA, WHEEL_SHA, read, sha,
)


SCHEMA = 'm4-dense-panel-sweep-v1'
PRODUCT = {'commit': PRODUCT_COMMIT, 'source_sha256': SOURCE_SHA}
REQUEST = {'query': {'mode': 'active_observation', 'region_task': {
    'area_min_m2': 1, 'area_max_m2': 1, 'normal_z_min': 0}},
    'include_image': True, 'response_detail': 'brief'}
CATALOGUE = PROJECTED / 'install/TOOLS_SCHEMA.json'


def verify_freeze():
    path = NS / 'FROZEN.json'
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['product'] != PRODUCT):
        raise ValueError('registered_dense_sweep_scope_or_limits_changed')
    expected = {ASSET, GEOMETRY, PRODUCT_BINDING, CATALOGUE,
                NS / 'inputs/REQUEST.json', NS / 'inputs/PRODUCT_SCHEMA.json'}
    pins = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path'])
        if not source.is_file() or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']:
            raise ValueError('frozen_evidence_or_runtime_changed/' + str(source))
        pins.add(source.resolve())
    if not pins.issuperset(p.resolve() for p in expected):
        raise ValueError('required_dense_sweep_inputs_not_frozen')
    return sha(path)


def admit(label):
    if label != ORDER[0]:
        raise ValueError('this_entry_opens_only_first_zero_model_product_qualification')
    frozen = verify_freeze()
    root = EXTERNAL / 'slots'
    if root.exists() and any(root.iterdir()):
        raise ValueError('qualification_already_consumed_or_slot_order_changed')
    binding = read(PRODUCT_BINDING)
    if (sha(PRODUCT_BINDING) != PRODUCT_BINDING_SHA256 or binding['source_sha256'] != SOURCE_SHA
            or binding['wheel_sha256'] != WHEEL_SHA or binding['preparation_git'] != PRODUCT_COMMIT
            or len(binding['source_manifest']) != 143):
        raise ValueError('expected_isolated_product_installation_changed')
    if read(NS / 'inputs/REQUEST.json') != REQUEST:
        raise ValueError('registered_read_only_product_request_changed')
    return frozen, binding
