"""Fixed same-install qualification bindings."""

from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = NS.parent
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
RASTER = V / 'm4_dense_raster_cross_001'
PIXEL = V / 'm4_cross_scale_pixel_evidence_001'
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
SEAL = V / 'm5_harness_recovery_001'
DISPLAY = V / 'm4_source_region_display_001'
PRIOR = V / 'm4_live_source_region_task_003'
DENSE = V / 'm4_dense_panel_sweep_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
EXTERNAL = Path('D:/he_m5_global_observe_measure_qualification_001')
ASSET = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/QP/native/input.blend')
ASSET_SHA256 = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
GEOMETRY = Path('D:/he_m4_cross_scale_pixel_evidence_001/slots/P1/TERMINAL_SOURCE.json')
GEOMETRY_SHA256 = 'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b'
TRUTH = ASSEMBLY / 'fixture/CURRENT_TRUTH.json'
PRODUCT_BINDING = RASTER / 'install/PRODUCT_RUN_BINDING.json'
SOURCE_SHA = '301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6'
PRODUCT_GIT = '9552d5c7103d9d8a08799adde96534990c6815f9'
WHEEL_SHA = '289cd77e16eb56bbcee3442db5e882b7ce3650732420c0a1e081ee737f3bf177'
CATALOGUE = PRODUCT_BINDING.with_name('TOOLS_SCHEMA.json')
PRODUCT_SCHEMA = PRODUCT_BINDING.with_name('PRODUCT_SCHEMA.json')
ORDER = ('A', 'B')
SLOTS = {label: ('P', 'qualification') for label in ORDER}
ARMS = {label: label for label in ORDER}
BINDINGS = {label: PRODUCT_BINDING for label in ORDER}
REQUESTS = {name: NS / f'inputs/{name}.json' for name in ('OBSERVE', 'MEASURE', 'JOINT')}
SLOT_REQUESTS = {'A': ('OBSERVE', 'MEASURE'), 'B': ('JOINT',)}


from importlib.util import module_from_spec, spec_from_file_location
_spec = spec_from_file_location('_m5_global_retained_common', PIXEL / 'harness/common.py')
_previous = module_from_spec(_spec)
_spec.loader.exec_module(_previous)
load, read, sha, save, append = _previous.load, _previous.read, _previous.sha, _previous.save, _previous.append


def load_retained(name, path):
    original_path = sys.path[:]
    try:
        return load(name, path)
    finally:
        sys.path[:] = original_path


def asset_identity():
    path = ASSET.resolve()
    if sha(path) != ASSET_SHA256:
        raise ValueError('fixed_assembly_asset_changed')
    return path, ASSET_SHA256
