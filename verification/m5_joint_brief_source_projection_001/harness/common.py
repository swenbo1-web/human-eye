"""Bind the verified assembly fixture and single joint slot to this installation."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = NS.parent
GLOBAL = V / 'm5_global_observe_measure_qualification_001'
spec = spec_from_file_location('_m5_projection_common_source', GLOBAL / 'harness/common.py')
retained = module_from_spec(spec)
spec.loader.exec_module(retained)

FORMAL, RASTER, PIXEL, ASSEMBLY = retained.FORMAL, retained.RASTER, retained.PIXEL, retained.ASSEMBLY
SEAL, DISPLAY, PRIOR, DENSE = retained.SEAL, retained.DISPLAY, retained.PRIOR, retained.DENSE
GENERIC_WORKER, BLENDER, TRUTH = retained.GENERIC_WORKER, retained.BLENDER, retained.TRUTH
ASSET, ASSET_SHA256 = retained.ASSET, retained.ASSET_SHA256
GEOMETRY, GEOMETRY_SHA256 = retained.GEOMETRY, retained.GEOMETRY_SHA256
load, load_retained, read, save, sha, append, asset_identity = (
    retained.load, retained.load_retained, retained.read, retained.save, retained.sha, retained.append,
    retained.asset_identity,
)

EXTERNAL = Path('D:/he_m5_joint_brief_source_projection_001')
PRODUCT_BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
CATALOGUE = PRODUCT_BINDING.with_name('TOOLS_SCHEMA.json')
PRODUCT_SCHEMA = PRODUCT_BINDING.with_name('PRODUCT_SCHEMA.json')
binding = read(PRODUCT_BINDING)
PRODUCT_GIT, SOURCE_SHA, WHEEL_SHA = binding['preparation_git'], binding['source_sha256'], binding['wheel_sha256']
ORDER = ('B',)
SLOTS = {'B': ('P', 'qualification')}
ARMS = {'B': 'B'}
BINDINGS = {'B': PRODUCT_BINDING}
REQUESTS = {'JOINT': GLOBAL / 'inputs/JOINT.json'}
SLOT_REQUESTS = {'B': ('JOINT',)}
