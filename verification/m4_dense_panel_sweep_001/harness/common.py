"""Bind the dense-panel qualification to the accepted isolated product."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
PROJECTED = V / 'm4_cross_scale_projected_bounds_001'
PIXEL = V / 'm4_cross_scale_pixel_evidence_001'
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
EXTERNAL = Path('D:/he_m4_dense_panel_sweep_001')
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
GEOMETRY = ASSET.with_suffix('.GEOMETRY.json')
ASSET_SHA256 = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY_SHA256 = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
PRODUCT_BINDING = PROJECTED / 'install/PRODUCT_RUN_BINDING.json'
PRODUCT_BINDING_SHA256 = 'a43b471280b4b3da1a0e289c688adf45bd3b032d9af454edc140bc140bece13e'
PRODUCT_COMMIT = '3cbf240562b61cff18c2818c6d134904259b36b7'
SOURCE_SHA = '6f2fc9762f9410f968c4768545c14077ca944f75416fb04aa9d14145a4c630d8'
WHEEL_SHA = 'a763f75d3a705ac51295b642ad9a1375b7f0d6fc13e40a30bbb7c8fe766c7c94'
ORDER = ('QP', 'QN', 'N1', 'P1', 'P2', 'N2', 'N3', 'P3')
SLOTS = {label: (label[-1] if label.startswith('Q') else label[0],
                 'qualification' if label.startswith('Q') else 'formal') for label in ORDER}


_spec = spec_from_file_location('_dense_panel_retained_common', PIXEL / 'harness/common.py')
_retained = module_from_spec(_spec)
_spec.loader.exec_module(_retained)
load, read, sha, save, append = (_retained.load, _retained.read, _retained.sha, _retained.save, _retained.append)


def asset_identity():
    path = ASSET.resolve()
    if sha(path) != ASSET_SHA256:
        raise ValueError('frozen_dense_panel_asset_mismatch')
    return path, ASSET_SHA256
