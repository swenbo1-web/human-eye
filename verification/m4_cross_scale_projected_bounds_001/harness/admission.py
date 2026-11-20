"""Require immutable registrations and accepted prior pairs before opening a slot."""

from pathlib import Path

from budget import LIMITS
from common import BINDINGS, EXTERNAL, NS, ORDER, read, sha


SCHEMA = 'm4-cross-scale-projected-bounds-v1'
BASELINE = {'commit': '3aa1d1fb43ae9a8207acd17bdab8d2861720c5a6',
            'source_sha256': 'b06f5e85a5d7b2519a09df2d7e5aa92ec2c915e860e58979837545c2851ded0a'}


def registered_products():
    candidate = read(BINDINGS['B'])
    return {'A': BASELINE, 'B': {'commit': candidate['preparation_git'],
                                 'source_sha256': candidate['source_sha256']}}


def verify_freeze():
    path = NS / 'FROZEN.json'
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['products'] != registered_products()):
        raise ValueError('registered_pair_order_or_product_limits_changed')
    pins = set()
    for pin in frozen['direct_inputs']:
        source = Path(pin['path'])
        if not source.is_file() or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']:
            raise ValueError('frozen_evidence_or_runtime_changed/' + str(source))
        pins.add(source.resolve())
    if not pins.issuperset(path.resolve() for path in BINDINGS.values()):
        raise ValueError('both_isolated_arm_bindings_must_be_frozen')
    return sha(path)


def admit(label):
    if label not in ORDER:
        raise ValueError('unknown_registered_slot')
    frozen_sha = verify_freeze()
    slots = EXTERNAL / 'slots'
    prior = ORDER[:ORDER.index(label)]
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(prior):
        raise ValueError('slot_order_or_replacement_changed')

    result_hashes = {}
    for predecessor in prior:
        folder = slots / predecessor
        result = folder / 'SLOT_RESULT.json'
        result_hashes[predecessor] = sha(result)
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if (pub['label'] != predecessor or pub['status'] != 'completed'
                or pub['result_sha256'] != result_hashes[predecessor]
                or read(result)['freeze_sha256'] != frozen_sha):
            raise ValueError('previous_slot_not_closed_and_passed/' + predecessor)
    for number in range(len(prior) // 2):
        path = EXTERNAL / 'preflight/pair_checks' / f'AFTER_PAIR_{number + 1:02d}.json'
        expected = {key: result_hashes[key] for key in ORDER[number * 2:number * 2 + 2]}
        if not path.is_file():
            raise ValueError('previous_pair_has_no_quality_gate')
        quality = read(path)
        if (quality['passed'] is not True or quality['freeze_sha256'] != frozen_sha
                or quality['slot_result_sha256'] != expected):
            raise ValueError('previous_pair_quality_gate_failed_or_stale')

    arm = label[0]
    binding = read(BINDINGS[arm])
    expected = registered_products()[arm]
    if (binding['preparation_git'] != expected['commit']
            or binding['source_sha256'] != expected['source_sha256']):
        raise ValueError('wrong_installed_arm/' + arm)
    return frozen_sha, arm, binding
