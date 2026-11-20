"""Bind each owned slot to the isolated products and fixed pair order."""

from pathlib import Path

from budget import LIMITS
from common import BINDINGS, EXTERNAL, NS, ORDER, read, sha


SCHEMA = 'm4-cross-scale-global-index-reuse-v1'
PRODUCTS = {
    'A': {'commit': '1dd2f77ecf19d51ba52aa5757e861ed930a58135',
          'source_sha256': '58c310d53abbf6ceac9a7c5273fc3119ffbedc1b632b27eb8c49988ca90a7d33'},
    'B': {'commit': '0802a532b4bce6465dd7647c0d68dcb2246c5ed3',
          'source_sha256': '82c525ec4fbc28aa0e282158bdfde94446bce83e6e4e8854ed7c5ae9c1748ff2'},
}


def verify_freeze():
    path = NS / 'FROZEN.json'
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['products'] != PRODUCTS):
        raise ValueError('registered_pair_order_or_product_limits_changed')
    for pin in frozen['direct_inputs']:
        source = Path(pin['path'])
        if not source.is_file() or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']:
            raise ValueError('frozen_evidence_or_runtime_changed/' + str(source))
    return sha(path)


def admit(label):
    if label not in ORDER:
        raise ValueError('unknown_registered_slot')
    frozen_sha = verify_freeze()
    slots = EXTERNAL / 'slots'
    prior = ORDER[:ORDER.index(label)]
    if (set(path.name for path in slots.iterdir()) if slots.exists() else set()) != set(prior):
        raise ValueError('slot_order_or_replacement_changed')
    for predecessor in prior:
        folder = slots / predecessor
        result = folder / 'SLOT_RESULT.json'
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if (pub['label'] != predecessor or pub['status'] != 'completed' or sha(result) != pub['result_sha256']
                or read(result)['freeze_sha256'] != frozen_sha):
            raise ValueError('previous_slot_not_closed_and_passed/' + predecessor)
    for number in range(1, len(prior) // 2 + 1):
        path = EXTERNAL / 'preflight/pair_checks' / f'AFTER_PAIR_{number:02d}.json'
        if not path.is_file() or read(path)['passed'] is not True:
            raise ValueError('previous_pair_has_not_passed_quality_gate')
    arm = label[0]
    binding = read(BINDINGS[arm])
    expected = PRODUCTS[arm]
    if (binding['preparation_git'] != expected['commit']
            or binding['source_sha256'] != expected['source_sha256']):
        raise ValueError('wrong_installed_arm/' + arm)
    return frozen_sha, arm, binding
