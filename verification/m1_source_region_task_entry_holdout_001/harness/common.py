"""Per-arm installed identities and the unchanged owned-runtime helpers."""

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
DUAL = V / 'perf050_dual_region_occlusion_transfer_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
EXTERNAL = Path('D:/he_m1_source_region_task_entry_holdout_001')
SOURCE_RUN = Path('D:/he_m4_m5_source_region_001')
ASSET = SOURCE_RUN / 'fixture/main.blend'
ASSET_SHA256 = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm4_source_region_blocker_frame_list_001'
PRODUCT_BINDING = FINAL_IMAGE / 'install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = PRODUCT_BINDING.with_name('PRODUCT_SCHEMA.json')
CATALOGUE = PRODUCT_BINDING.with_name('TOOLS_SCHEMA.json')
PRODUCT_GIT = '8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b'
SOURCE_SHA = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
WHEEL_SHA = '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'
CANDIDATE_BINDING = V / 'm1_source_region_task_entry_001/install/PRODUCT_RUN_BINDING.json'
NARROW_TOOL = 'human_eye_source_region_measure'
SLOTS = {'QA': ('P', 'qualification'), 'QB': ('P', 'qualification'),
         'A1': ('P', 'formal'), 'B1': ('P', 'formal')}
ORDER = tuple(SLOTS)
PRODUCT = {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}  # Retained startup import only.
SLOT_REQUESTS = {label: () for label in SLOTS}


spec = importlib.util.spec_from_file_location('_task_entry_base_common', FORMAL / 'harness/common.py')
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


def product_for(label):
    """Resolve the fixed A installation and the previously accepted B installation."""
    if label not in SLOTS:
        raise ValueError('registered_task_entry_slot_required')
    binding = PRODUCT_BINDING if label in ('QA', 'A1') else CANDIDATE_BINDING
    value = read(binding)
    if label in ('QA', 'A1') and (value['source_sha256'] != SOURCE_SHA
            or value['preparation_git'] != PRODUCT_GIT or value['wheel_sha256'] != WHEEL_SHA):
        raise ValueError('task_entry_baseline_identity_changed')
    return {
        'binding': binding, 'schema': binding.with_name('PRODUCT_SCHEMA.json'),
        'catalogue': binding.with_name('TOOLS_SCHEMA.json'),
        'source_sha256': value['source_sha256'], 'commit': value['preparation_git'],
        'wheel_sha256': value['wheel_sha256'],
    }


def asset_identity():
    if sha(ASSET) != ASSET_SHA256:
        raise ValueError('fixed_task_entry_asset_changed')
    return ASSET.resolve(), ASSET_SHA256
