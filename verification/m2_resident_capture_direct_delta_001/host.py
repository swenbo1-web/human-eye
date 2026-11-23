"""Bind the retained owned Blender and MCP runtime to the direct-delta pair."""

import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
V = HERE.parent
PREVIOUS = V/'m2_source_region_shared_normalization_live_001'
RUN = Path('D:/he_m2_resident_capture_direct_delta_001')
BINDINGS = {
    'A': V/'m2_source_region_shared_normalization_001/install/PRODUCT_RUN_BINDING.json',
    'B': HERE/'install/PRODUCT_RUN_BINDING.json',
}
CHANGES = {'human_eye_plugin/blender_host.py', 'human_eye_plugin/blender_mcp_host.py'}

spec = importlib.util.spec_from_file_location('_resident_delta_retained_host', PREVIOUS/'host.py')
retained = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = retained
spec.loader.exec_module(retained)

BASELINE = retained.PRODUCTS['B']
SLOTS, WORKER, read, sha, require, load = (retained.SLOTS, retained.WORKER, retained.read,
                                        retained.sha, retained.require, retained.load)
ASSET, ASSET_SHA256, BLENDER = retained.ASSET, retained.ASSET_SHA256, retained.BLENDER


def binding_identity(label, path):
    require(label in SLOTS and Path(path).resolve(strict=True) == BINDINGS[label].resolve(strict=True),
            'direct_delta_fixed_arm_binding_path_required')
    keys = ('preparation_git', 'source_sha256', 'wheel_sha256')
    baseline = read(BINDINGS['A'])
    require(tuple(baseline[key] for key in keys) == BASELINE and len(baseline['source_manifest']) == 143,
            'direct_delta_fixed_baseline_identity_required')
    binding = baseline if label == 'A' else read(path)
    wheel = Path(binding['wheel_path']).resolve(strict=True)
    require(sha(wheel) == binding['wheel_sha256'], 'direct_delta_arm_wheel_changed')
    if label == 'B':
        install = RUN.resolve()/'candidate_install'
        require(wheel.parent == install and Path(binding['install_root']).resolve(strict=True) == install/'product'
                and binding['historical_preparation_git'] == BASELINE[0]
                and binding['historical_source_sha256'] == BASELINE[1]
                and binding['preparation_git'] != BASELINE[0]
                and binding['dependency_root'] == baseline['dependency_root'],
                'direct_delta_candidate_install_or_base_binding_changed')
        previous = {row['path']: row['sha256'] for row in baseline['source_manifest']}
        current = {row['path']: row['sha256'] for row in binding['source_manifest']}
        require(len(binding['source_manifest']) == len(current) == len(previous) == 143
                and current.keys() == previous.keys()
                and {name for name in current if current[name] != previous[name]} == CHANGES,
                'direct_delta_candidate_two_file_scope_changed')
    return binding


# Reuse the original slot and native worker with globals local to this loaded
# module instance. The prior experiment and its original launch files stay fixed.
retained.HERE = HERE
retained.RUN = RUN
retained.BINDINGS = BINDINGS
retained.binding_identity = binding_identity
Slot, assemble, owned_root = retained.Slot, retained.assemble, retained.owned_root


def retained_sources():
    paths = set(retained.retained_sources())
    paths.discard(HERE/'meter.py')
    paths.update((Path(__file__).resolve(), PREVIOUS/'mcp_entry.py', PREVIOUS/'meter.py'))
    return tuple(sorted(paths))
