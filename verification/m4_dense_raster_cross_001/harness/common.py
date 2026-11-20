"""Bind the reviewed six-slot harness to this candidate and a fresh run root."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PIXEL_BASE = NS.parent / 'm4_global_pixel_bound_short_circuit_001'
spec = spec_from_file_location('_dense_raster_previous_common', PIXEL_BASE / 'harness/common.py')
previous = module_from_spec(spec)
spec.loader.exec_module(previous)

ROOT, V, BLOCKER, DENSE = previous.ROOT, previous.V, previous.BLOCKER, previous.DENSE
ASSEMBLY, FORMAL, PRIOR, DISPLAY = previous.ASSEMBLY, previous.FORMAL, previous.PRIOR, previous.DISPLAY
ASSET, ASSET_SHA256, BLENDER = previous.ASSET, previous.ASSET_SHA256, previous.BLENDER
GEOMETRY, GEOMETRY_SHA256 = previous.GEOMETRY, previous.GEOMETRY_SHA256
GENERIC_WORKER, asset_identity = previous.GENERIC_WORKER, previous.asset_identity
REQUEST, TRUTH, PRODUCT_SCHEMA = previous.REQUEST, previous.TRUTH, previous.PRODUCT_SCHEMA
ORDER, SLOTS, ARMS = previous.ORDER, previous.SLOTS, previous.ARMS
load, read, sha, save, append = previous.load, previous.read, previous.sha, previous.save, previous.append
EXTERNAL = Path('D:/he_m4_dense_raster_cross_001')
BINDINGS = {'A': PIXEL_BASE / 'install/PRODUCT_RUN_BINDING.json',
            'B': NS / 'install/PRODUCT_RUN_BINDING.json'}
CATALOGUE = BINDINGS['A'].with_name('TOOLS_SCHEMA.json')
PRODUCT_BINDING = BINDINGS['A']
SOURCE_SHA = '0e71932b2bccbf8a6583460875cea8bdc55b092b7d8f3391c9b0124aef986d4f'


def load_retained(name, path):
    # Historical entrypoints prepend their own directory in standalone mode.
    first = sys.path[:]
    try:
        return load(name, path)
    finally:
        sys.path[:] = first
