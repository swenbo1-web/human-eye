"""Bind the dense region task to the six isolated engineering slots."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
BLOCKER = V / 'm4_bound_blocker_evidence_001'
DENSE = V / 'm4_dense_panel_sweep_001'
PIXEL = V / 'm4_cross_scale_pixel_evidence_001'
EXTERNAL = Path('D:/he_m4_global_pixel_bound_short_circuit_001')
BINDINGS = {'A': BLOCKER / 'install/PRODUCT_RUN_BINDING.json',
            'B': NS / 'install/PRODUCT_RUN_BINDING.json'}
REQUEST = BLOCKER / 'inputs/REQUEST.json'
TRUTH = DENSE / 'truth/CURRENT_TRUTH.json'
CATALOGUE = BINDINGS['A'].with_name('TOOLS_SCHEMA.json')
PRODUCT_SCHEMA = BLOCKER / 'inputs/PRODUCT_SCHEMA.json'
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
SLOTS = {label: ('P', 'formal') for label in ORDER}
ARMS = {label: label[0] for label in ORDER}


def load(name, path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_retained = load('_pixel_bound_retained_dense_common', DENSE / 'harness/common.py')
ASSEMBLY, FORMAL, PRIOR, DISPLAY = _retained.ASSEMBLY, _retained.FORMAL, _retained.PRIOR, _retained.DISPLAY
GENERIC_WORKER = _retained.GENERIC_WORKER
ASSET, ASSET_SHA256, BLENDER = _retained.ASSET, _retained.ASSET_SHA256, _retained.BLENDER
GEOMETRY, GEOMETRY_SHA256 = _retained.GEOMETRY, _retained.GEOMETRY_SHA256
asset_identity = _retained.asset_identity
read, sha, save, append = _retained.read, _retained.sha, _retained.save, _retained.append
PRODUCT_BINDING = BINDINGS['A']
SOURCE_SHA = '84bf65eedbc0866375d760025437993b90ec54325af09b4e1f36b74abe233d62'
