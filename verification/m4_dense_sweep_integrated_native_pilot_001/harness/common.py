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
EXTERNAL = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
SOURCE_RUN = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001/fixture')
ASSET = SOURCE_RUN / 'main.blend'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
PRODUCT_BINDING = V / 'm3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
CATALOGUE = NS / 'inputs/EVIDENCE_TOOLS_SCHEMA.json'
PRODUCT_GIT = 'cee6fe78a65c1534361228641743aa83d6d72b61'
SOURCE_SHA = '75e6b8b40ccb221c0a7720e19ab29ca0bb8df80f5a57b27e71df2d3e675656f3'
WHEEL_SHA = '53255eb9a7c9affe3523d39c13bba6c8f4560f5ce817ab7cd08679ae5a67291c'
QUALIFICATION = ('QN', 'QP')
FORMAL_LABELS = ('N1', 'P1')
SLOTS = {label: (label[-1], 'qualification') for label in QUALIFICATION}
SLOTS.update({label: (label[0], 'formal') for label in FORMAL_LABELS})
ORDER = tuple(SLOTS)
PRODUCT = {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}  # Retained startup module import only.
SLOT_REQUESTS = {label: () for label in SLOTS}  # Pilot dispatch never uses an old query list.


spec = importlib.util.spec_from_file_location('_perf050_transfer_base_common', FORMAL / 'harness/common.py')
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)
load, read, sha, save, append = retained.load, retained.read, retained.sha, retained.save, retained.append


ASSET_SHA256 = '219541e921666ddf6c406507afb5e59168415a14b8ea7b3d8eca28c6dacbe12f'


def load_retained(name, path):
    import sys

    original_path = sys.path[:]
    try:
        return load(name, path)
    finally:
        sys.path[:] = original_path


def evidence_enabled(label):
    return SLOTS[label][0] == 'P'


def catalogue_for(label):
    if not evidence_enabled(label):
        raise ValueError('native_slot_has_no_installed_product_catalogue')
    return CATALOGUE


def asset_identity():
    expected = read(NS / 'FROZEN.json')['asset_sha256']
    if sha(ASSET) != expected:
        raise ValueError('fixed_readonly_pilot_asset_changed')
    return ASSET.resolve(), expected
