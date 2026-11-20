"""Bind the blocker diagnostic slot to the original dense asset."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
DENSE = V / 'm4_dense_panel_sweep_001'
BRIEF = V / 'm4_dense_region_brief_001'
PRODUCT_BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
BASE_BINDING = BRIEF / 'install/PRODUCT_RUN_BINDING.json'
BASE_COMMIT = '278fd3003758299379f6d87b7e9174c577f5bb88'
BASE_SOURCE_SHA = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
EXTERNAL = Path('D:/he_m4_bound_blocker_evidence_001')
ORDER = ('QP',)
SLOTS = {'QP': ('P', 'qualification')}

_spec = spec_from_file_location('_bound_blocker_base_common', DENSE / 'harness/common.py')
_retained = module_from_spec(_spec)
_spec.loader.exec_module(_retained)
ASSEMBLY, PIXEL, FORMAL = _retained.ASSEMBLY, _retained.PIXEL, _retained.FORMAL
PRIOR, DISPLAY, GENERIC_WORKER = _retained.PRIOR, _retained.DISPLAY, _retained.GENERIC_WORKER
ASSET, ASSET_SHA256, BLENDER = _retained.ASSET, _retained.ASSET_SHA256, _retained.BLENDER
GEOMETRY, GEOMETRY_SHA256 = _retained.GEOMETRY, _retained.GEOMETRY_SHA256
load, read, sha, save, append = _retained.load, _retained.read, _retained.sha, _retained.save, _retained.append
asset_identity = _retained.asset_identity
