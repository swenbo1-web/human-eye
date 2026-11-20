"""Route the retained rail harness to the formal-only run directory."""

import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
OLD = V / 'm4_rail_blocker_consumption_001'
INPUTS = OLD / 'inputs'
EXTERNAL = Path('D:/he_m4_rail_blocker_consumption_formal_001')
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
SLOTS = {label: ('P', 'formal') for label in ORDER}
ARMS = {label: label[0] for label in ORDER}
TRUTH = OLD / 'truth/CURRENT_TRUTH.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_retained = load('_rail_original_common', OLD / 'harness/common.py')
ASSET, ASSET_SHA256 = _retained.ASSET, _retained.ASSET_SHA256
GEOMETRY, GEOMETRY_SHA256 = _retained.GEOMETRY, _retained.GEOMETRY_SHA256
BLENDER, GENERIC_WORKER = _retained.BLENDER, _retained.GENERIC_WORKER
PRIOR, DISPLAY = _retained.PRIOR, _retained.DISPLAY
PRODUCTS, BINDINGS, SOURCE_SHA = _retained.PRODUCTS, _retained.BINDINGS, _retained.SOURCE_SHA
read, save, append, sha = _retained.read, _retained.save, _retained.append, _retained.sha
asset_identity = _retained.asset_identity


def product_for(label):
    if label not in SLOTS:
        raise ValueError('registered_formal_slot_required/' + label)
    return _retained.product_for(label)
