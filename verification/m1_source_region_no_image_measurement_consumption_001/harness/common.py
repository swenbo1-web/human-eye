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
OLD_NS = V / 'm1_region_task_first_packet_consumption_holdout_001'
OLD_EXTERNAL = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001')
EXTERNAL = Path('D:/he_m1_source_region_no_image_measurement_consumption_001')
SOURCE_RUN = Path('D:/he_m4_cross_scale_live_task_001/fixture')
ASSET = SOURCE_RUN / 'main.blend'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm4_source_region_blocker_frame_list_001'
PRODUCT_BINDING = V / 'm1_region_task_witness_image_path_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
CATALOGUE = NS / 'inputs/A_TOOLS_SCHEMA.json'
CANDIDATE_CATALOGUE = NS / 'inputs/B_TOOLS_SCHEMA.json'
PRODUCT_GIT = '1535d08ac5124b5fe117101806ae3c85d47247fe'
SOURCE_SHA = 'cdee32540b54f3278619305b23f28a646dba90d80212708ed3baf928514e2acd'
WHEEL_SHA = 'c2370f67569d1ac84ad8bf77c09d73942b06d22562bb2bceb34b9cced3b5b814'
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


ASSET_BINDING = V / 'm4_cross_scale_live_task_formal_001/fixture/ASSET_BINDING.json'
ASSET_SHA256 = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'


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
    return True


def catalogue_for(label):
    evidence_enabled(label)
    return CATALOGUE if label in ('QA', 'A1') else CANDIDATE_CATALOGUE


CANDIDATE_BINDING = V / 'm1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = {'commit': '34372f04143535b6990a45956aa74d210e726b29',
             'source_sha256': '338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac',
             'wheel_sha256': '481c873cc061de4a3a5e99562609ba4e27574b44240b5b6429f97131d65d867c'}


def binding_for(label):
    evidence_enabled(label)
    return PRODUCT_BINDING if label in ('QA', 'A1') else CANDIDATE_BINDING


def product_for(label):
    binding = read(binding_for(label))
    actual = {'commit': binding['preparation_git'], 'source_sha256': binding['source_sha256'],
              'wheel_sha256': binding['wheel_sha256']}
    expected = PRODUCT if label in ('QA', 'A1') else CANDIDATE
    if actual != expected or len(binding['source_manifest']) != 143:
        raise ValueError('fixed_witness_path_consumption_arm_install_required')
    return actual
