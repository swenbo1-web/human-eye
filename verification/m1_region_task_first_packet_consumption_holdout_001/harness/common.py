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
ORIGINAL = V / 'perf050_dense_micro_surface_holdout_001'
ORIGINAL_RUN = Path('D:/he_perf050_dense_micro_surface_holdout_001')
EXTERNAL = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001')
SOURCE_RUN = EXTERNAL / 'fixture'
ASSET = SOURCE_RUN / 'main.blend'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm4_source_region_blocker_frame_list_001'
PRODUCT_BINDING = V / 'm1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
CATALOGUE = NS / 'inputs/STANDARD_TOOLS_SCHEMA.json'
PRODUCT_GIT = '24b8855746dfe9eeee7fa7d374bec2da86c21a2e'
SOURCE_SHA = '704742071fd1d2722b952e6fa0d4f9a497b8a33ed567ce8f510657d8c1b379fe'
WHEEL_SHA = '2cd2bc3607fd5b8744d760f88ad23008f3faae153efa4ccd49dfa22538547572'
QUALIFICATION = ('QA', 'QB')
FORMAL_LABELS = ('A1', 'B1')
SLOTS = {label: ('P', 'qualification') for label in QUALIFICATION}
SLOTS.update({label: ('P', 'formal') for label in FORMAL_LABELS})
ORDER = tuple(SLOTS)
PRODUCT = {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}  # Retained startup module import only.
SLOT_REQUESTS = {label: () for label in SLOTS}  # Pilot dispatch never uses an old query list.


spec = importlib.util.spec_from_file_location('_perf050_transfer_base_common', FORMAL / 'harness/common.py')
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)
load, read, sha, save, append = retained.load, retained.read, retained.sha, retained.save, retained.append


ASSET_BINDING = NS / 'fixture/ASSET_BINDING.json'
ASSET_SHA256 = read(ASSET_BINDING)['asset']['sha256'] if ASSET_BINDING.is_file() else None


def load_retained(name, path):
    import sys

    original_path = sys.path[:]
    try:
        return load(name, path)
    finally:
        sys.path[:] = original_path


def asset_identity():
    expected = read(NS / 'FROZEN.json')['asset_sha256']
    if sha(ASSET) != expected:
        raise ValueError('fixed_readonly_pilot_asset_changed')
    return ASSET.resolve(), expected


def evidence_enabled(label):
    if label not in SLOTS:
        raise ValueError('registered_region_task_holdout_slot_required')
    return label in ('QB', 'B1')


def catalogue_for(label):
    return NS / 'inputs' / ('EVIDENCE_TOOLS_SCHEMA.json' if evidence_enabled(label) else 'STANDARD_TOOLS_SCHEMA.json')
