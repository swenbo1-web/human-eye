"""One fixed install, eight fresh N/P slots and three paired natural prompts."""

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
OLD_NS = V / 'm1_source_region_no_image_measurement_consumption_001'
OLD_EXTERNAL = Path('D:/he_m1_source_region_no_image_measurement_consumption_001')
EXTERNAL = Path('D:/he_m1_source_region_no_image_native_transfer_001')
SOURCE_RUN = Path('D:/he_m4_cross_scale_live_task_001/fixture')
ASSET = SOURCE_RUN / 'main.blend'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
FINAL_IMAGE = V / 'm4_source_region_blocker_frame_list_001'
PRODUCT_BINDING = V / 'm1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
CATALOGUE = NS / 'inputs/TOOLS_SCHEMA.json'
PRODUCT_GIT = '34372f04143535b6990a45956aa74d210e726b29'
SOURCE_SHA = '338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac'
WHEEL_SHA = '481c873cc061de4a3a5e99562609ba4e27574b44240b5b6429f97131d65d867c'
PRODUCT = {'commit': PRODUCT_GIT, 'source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA}
QUALIFICATION = ('QN', 'QP')
FORMAL_LABELS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
SLOTS = {label: (label[-1], 'qualification') for label in QUALIFICATION}
SLOTS.update({label: (label[0], 'formal') for label in FORMAL_LABELS})
ORDER = tuple(SLOTS)
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}
SLOT_REQUESTS = {label: () for label in SLOTS}
ASSET_BINDING = V / 'm4_cross_scale_live_task_formal_001/fixture/ASSET_BINDING.json'
ASSET_SHA256 = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
PROMPT_SHAS = {
    1: '28c9df0157e6926f2fc18c28aa9f1ec9fb0545b5ff5b66d0ac09a3596f5d7203',
    2: '8d22f9e476c9c787fbe912e6aa3cfafd10289c5b48beda6842059aa8c7af21da',
    3: '1f2be5f8937a09866425afd80c53a2dd44e279abd7bae59da1e739b5ce59eabe',
}

spec = importlib.util.spec_from_file_location('_native_transfer_retained_common', FORMAL / 'harness/common.py')
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
    expected = read(NS / 'FROZEN.json')['asset_sha256']
    if expected != ASSET_SHA256 or sha(ASSET) != expected:
        raise ValueError('fixed_native_transfer_readonly_asset_changed')
    return ASSET.resolve(), expected


def group_for(label):
    if label not in SLOTS:
        raise ValueError('registered_native_transfer_slot_required')
    return SLOTS[label][0]


def evidence_enabled(label):
    return group_for(label) == 'P'


def catalogue_for(label):
    return CATALOGUE if evidence_enabled(label) else None


def binding_for(label):
    group_for(label)
    return PRODUCT_BINDING


def product_for(label):
    binding = read(binding_for(label))
    actual = {'commit': binding['preparation_git'], 'source_sha256': binding['source_sha256'],
              'wheel_sha256': binding['wheel_sha256']}
    if actual != PRODUCT or len(binding['source_manifest']) != 143:
        raise ValueError('fixed_native_transfer_installed_product_required')
    return actual


def question_for(label):
    if label not in FORMAL_LABELS:
        raise ValueError('formal_question_slot_required')
    return int(label[-1])


def prompt_for(label):
    return NS / 'inputs' / ('PROMPT_' + str(question_for(label)) + '.txt')
