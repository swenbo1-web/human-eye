"""Bind the retained read-only runtime to the fixed Yanyite experiment."""

from pathlib import Path
import sys


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/common.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))

EXTERNAL = Path('D:/he_m4_yanyite_dual_curved_region_native_001')
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA256 = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
PRODUCT_BINDING = V/'m4_region_task_global_first_frame_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_GIT = '7e096daf3bb24596905f76abefa5e07a96a9f5d1'
SOURCE_SHA = '3941eaaa911256a5b8876cf5e9fc9926a15cba3583bd3d38f2e960f41626b5d8'
WHEEL_SHA = 'fe8080d14f82964f5af3cdb49da7779e71498cc1280f5a0c3514b86ef0792994'
PRODUCT = {'commit':PRODUCT_GIT,'source_sha256':SOURCE_SHA,'wheel_sha256':WHEEL_SHA}
SCHEMA_ORIGIN = V/'m4_dense_sweep_integrated_native_startup_001/inputs'
PRODUCT_SCHEMA = SCHEMA_ORIGIN/'PRODUCT_SCHEMA.json'
CATALOGUE = SCHEMA_ORIGIN/'EVIDENCE_TOOLS_SCHEMA.json'
PLAN = '9eb4d8f8563961b7fea44eb0a004d26c7832b207:docs/M4_YANYITE_DUAL_CURVED_REGION_NATIVE_001_PLAN.md'
SLOTS = {'QN':('N','qualification'),'QP':('P','qualification'),'N1':('N','formal'),'P1':('P','formal')}
ORDER = tuple(SLOTS)
SLOT_REQUESTS = {label:() for label in SLOTS}
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
NATIVE = NS/'native'


def add_paths():
    binding = read(PRODUCT_BINDING)
    shared = read(SEAL/'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(HERE),str(NATIVE),str(NS),binding['dependency_root'],shared['dependency_root']]


def asset_identity():
    if ASSET.stat().st_size != 3_415_766 or sha(ASSET) != ASSET_SHA256:
        raise ValueError('original_yanyite_asset_changed')
    return ASSET.resolve(strict=True), ASSET_SHA256
