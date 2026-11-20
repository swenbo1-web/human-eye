"""Bind the six-slot batch while retaining the proven assembly harness."""

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
PIXEL = V / 'm4_cross_scale_pixel_evidence_001'
EXTERNAL = Path('D:/he_m4_cross_scale_projected_bounds_001')
BINDINGS = {'A': PIXEL / 'install/PRODUCT_RUN_BINDING.json',
            'B': NS / 'install/PRODUCT_RUN_BINDING.json'}
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
SLOTS = {label: ('P', 'formal') for label in ORDER}

_spec = importlib.util.spec_from_file_location('_projected_bounds_retained_common', PIXEL / 'harness/common.py')
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
ASSEMBLY, FORMAL, PRIOR, DISPLAY = _common.ASSEMBLY, _common.FORMAL, _common.PRIOR, _common.DISPLAY
ASSET, ASSET_SHA256, BLENDER = _common.ASSET, _common.ASSET_SHA256, _common.BLENDER
GENERIC_WORKER = _common.GENERIC_WORKER
asset_identity = _common.asset_identity
load, read, sha, save, append = _common.load, _common.read, _common.sha, _common.save, _common.append
