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
EXTERNAL = Path('D:/he_perf050_dual_region_occlusion_transfer_001')
SOURCE_RUN = Path('D:/he_m4_cross_scale_live_qualification_001')
ASSET = SOURCE_RUN / 'slots/Q1/native/input.blend'
ASSET_SHA256 = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm1_source_region_default_measurement_entry_001'
PRODUCT_BINDING = FINAL_IMAGE / 'install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = PRODUCT_BINDING.with_name('PRODUCT_SCHEMA.json')
CATALOGUE = PRODUCT_BINDING.with_name('TOOLS_SCHEMA.json')
PRODUCT_GIT = '1cb43fd35e680169c0a6275b52e47513de638624'
SOURCE_SHA = '73e28f8e9b334a386c95b785aa3698e5171795fae9bffc9ea4e73403344f33b4'
WHEEL_SHA = 'e011c0b917cc64713004d63dccc6358cc14e68d552f20f8e9a32ffb81990a3e6'
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
