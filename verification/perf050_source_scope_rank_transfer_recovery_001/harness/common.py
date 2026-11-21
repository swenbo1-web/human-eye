"""Fixed read-only pilot identities and the retained experiment helpers."""

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ROOT = V.parent
FORMAL = V / 'm4_dense_panel_sweep_formal_001'
RECOVERY = V / 'm5_joint_brief_source_projection_recovery_001'
ACTIVE_VIEW = V / 'm4_source_region_active_view_001'
PILOT = V / 'perf050_readonly_product_pilot_001'
SEAL = V / 'm5_harness_recovery_001'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GLOBAL = V / 'm5_global_observe_measure_qualification_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
EXTERNAL = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
SOURCE_RUN = Path('D:/he_m4_m5_source_region_001')
ASSET = SOURCE_RUN / 'fixture/main.blend'
ASSET_SHA256 = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm1_joint_full_task_tail_scope_001'
PRODUCT_BINDING = FINAL_IMAGE / 'install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = PRODUCT_BINDING.with_name('PRODUCT_SCHEMA.json')
CATALOGUE = PRODUCT_BINDING.with_name('TOOLS_SCHEMA.json')
PRODUCT_GIT = '4e4c653a4d4726576f4f4d2a9d7b9decede44cbf'
SOURCE_SHA = 'a436539e9f5389b9ebaa5ccacc0a4845d53d2429923b4443b15e3f49e2a6e846'
WHEEL_SHA = '72fc32b8ccce647047b9fada49238b69521fa41551069bae3d20d542768fbc53'
SLOTS = {'QN': ('N', 'qualification'), 'QP': ('P', 'qualification'), 'N1': ('N', 'formal'), 'P1': ('P', 'formal')}
ORDER = tuple(SLOTS)
PRODUCT = {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}  # Retained startup module import only.
SLOT_REQUESTS = {label: () for label in SLOTS}  # Pilot dispatch never uses an old query list.


spec = importlib.util.spec_from_file_location('_perf050_transfer_base_common', FORMAL / 'harness/common.py')
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)
load, read, sha, save, append = retained.load, retained.read, retained.sha, retained.save, retained.append


def load_retained(name, path):
    import sys

    original_path = sys.path[:]
    try:
        return load(name, path)
    finally:
        sys.path[:] = original_path


def asset_identity():
    if sha(ASSET) != ASSET_SHA256:
        raise ValueError('fixed_readonly_pilot_asset_changed')
    return ASSET.resolve(), ASSET_SHA256
