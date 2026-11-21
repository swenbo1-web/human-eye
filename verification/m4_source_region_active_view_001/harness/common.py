"""Bind both immutable installations and the originally successful request."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ROOT = V.parent
PILOT = V / 'perf050_readonly_product_pilot_001'
RECOVERY = V / 'm5_joint_brief_source_projection_recovery_001'
GLOBAL = V / 'm5_global_observe_measure_qualification_001'
PIXEL = V / 'm4_cross_scale_pixel_evidence_001'
FORMAL = V / 'm4_dense_panel_sweep_formal_001'
SEAL = V / 'm5_harness_recovery_001'
DISPLAY = V / 'm4_source_region_display_001'
PRIOR = V / 'm4_live_source_region_task_003'
EXTERNAL = Path('D:/he_m4_source_region_active_view_001')
PILOT_RUN = Path('D:/he_perf050_readonly_product_pilot_001')
PILOT_SLOT = PILOT_RUN / 'slots/P1'
REQUEST = PILOT_SLOT / 'owner/tool_03/PRODUCT_REQUEST.json'
ORDER = ('A', 'B')
SLOTS = {label: ('P', 'qualification') for label in ORDER}

spec = spec_from_file_location('_m4_active_view_retained_common', PILOT / 'harness/common.py')
previous = module_from_spec(spec)
spec.loader.exec_module(previous)
ASSET, ASSET_SHA256, BLENDER, GENERIC_WORKER = (
    previous.ASSET, previous.ASSET_SHA256, previous.BLENDER, previous.GENERIC_WORKER)
asset_identity, load, load_retained, read, save, sha, append = (
    previous.asset_identity, previous.load, previous.load_retained, previous.read, previous.save, previous.sha, previous.append)

BINDINGS = {'A': previous.PRODUCT_BINDING, 'B': NS / 'install/PRODUCT_RUN_BINDING.json'}
PRODUCT_SCHEMA, CATALOGUE = previous.PRODUCT_SCHEMA, previous.CATALOGUE
PRODUCT_BINDING = BINDINGS['A']
SOURCE_SHA, PRODUCT_GIT = previous.SOURCE_SHA, previous.PRODUCT_GIT
SLOT_REQUESTS = {label: ('COLD', 'HOT') for label in ORDER}
REQUESTS = {kind: REQUEST for kind in ('COLD', 'HOT')}


def product(label):
    binding = read(BINDINGS[label])
    sources = binding['source_manifest']
    if len(sources) != 143 or len({row['path'] for row in sources}) != len(sources):
        raise ValueError('fixed_143_installed_sources_required')
    return {key: binding[field] for key, field in (('commit', 'preparation_git'),
            ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))}


def select(label):
    """Select an arm only in its own runner or installed child process."""
    global PRODUCT_BINDING, SOURCE_SHA, PRODUCT_GIT
    binding = product(label)
    PRODUCT_BINDING = BINDINGS[label]
    SOURCE_SHA = binding['source_sha256']
    PRODUCT_GIT = binding['commit']
    return binding


def arguments():
    message = read(REQUEST)
    params = message['params']
    query = params['arguments']['query']
    if (message['method'], params['name'], query['mode']) != ('tools/call', 'human_eye_scene_observe', 'source_region'):
        raise ValueError('original_source_region_request_identity_changed')
    return params['arguments']
