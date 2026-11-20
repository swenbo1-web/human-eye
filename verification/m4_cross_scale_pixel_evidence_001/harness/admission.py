"""Admit the one engineering slot bound to the original products and asset."""

from pathlib import Path

from budget import LIMITS
from common import BINDINGS, EXTERNAL, NS, ORDER, read, sha


SCHEMA = 'm4-cross-scale-pixel-evidence-v1'
PRODUCTS = {'P': {'commit': '3aa1d1fb43ae9a8207acd17bdab8d2861720c5a6',
                  'source_sha256': 'b06f5e85a5d7b2519a09df2d7e5aa92ec2c915e860e58979837545c2851ded0a'}}


def verify_freeze():
    path = NS / 'FROZEN.json'
    frozen = read(path)
    if (frozen['schema'] != SCHEMA or frozen['slots'] != list(ORDER)
            or frozen['ledger_limits'] != LIMITS or frozen['products'] != PRODUCTS):
        raise ValueError('original_pixel_evidence_product_or_limits_changed')
    for pin in frozen['direct_inputs']:
        source = Path(pin['path'])
        if not source.is_file() or source.stat().st_size != pin['bytes'] or sha(source) != pin['sha256']:
            raise ValueError('registered_input_changed/' + str(source))
    return sha(path)


def admit(label):
    if label not in ORDER or (EXTERNAL / 'slots').exists() or (EXTERNAL / 'budget').exists():
        raise ValueError('only_one_original_zero_model_slot_is_registered')
    frozen = verify_freeze()
    binding = read(BINDINGS['P'])
    if (binding['preparation_git'] != PRODUCTS['P']['commit']
            or binding['source_sha256'] != PRODUCTS['P']['source_sha256']):
        raise ValueError('wrong_installed_pixel_evidence_candidate')
    return frozen, 'P', binding
