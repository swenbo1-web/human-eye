"""Bind the sole dense qualification to its original asset and candidate install."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
DENSE = V / 'm4_dense_panel_sweep_001'
PROJECTED = V / 'm4_cross_scale_projected_bounds_001'
PRODUCT_BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
EXTERNAL = Path('D:/he_m4_dense_region_brief_001')
ORDER = ('QP',)
SLOTS = {'QP': ('P', 'qualification')}

_spec = spec_from_file_location('_dense_region_brief_base_common', DENSE / 'harness/common.py')
_retained = module_from_spec(_spec)
_spec.loader.exec_module(_retained)
ASSEMBLY, PIXEL, FORMAL = _retained.ASSEMBLY, _retained.PIXEL, _retained.FORMAL
PRIOR, DISPLAY, GENERIC_WORKER = _retained.PRIOR, _retained.DISPLAY, _retained.GENERIC_WORKER
ASSET, ASSET_SHA256, BLENDER = _retained.ASSET, _retained.ASSET_SHA256, _retained.BLENDER
GEOMETRY, GEOMETRY_SHA256 = _retained.GEOMETRY, _retained.GEOMETRY_SHA256
BASE_COMMIT, BASE_SOURCE_SHA = _retained.PRODUCT_COMMIT, _retained.SOURCE_SHA
load, read, sha, save, append = _retained.load, _retained.read, _retained.sha, _retained.save, _retained.append
asset_identity = _retained.asset_identity
