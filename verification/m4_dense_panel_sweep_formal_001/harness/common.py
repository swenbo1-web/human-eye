"""Batch paths, file identities and retained experiment records."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
EXTERNAL = Path('D:/he_m4_dense_panel_sweep_formal_001')
QP_EXTERNAL = Path('D:/he_m4_dense_region_brief_001')
DENSE = V / 'm4_dense_panel_sweep_001'
BRIEF = V / 'm4_dense_region_brief_001'
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
ASSET_SHA256 = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY = ASSET.with_name('main.GEOMETRY.json')
GEOMETRY_SHA256 = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
TRUTH = DENSE / 'truth/CURRENT_TRUTH.json'
TRUTH_SHA256 = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
SOURCE_SHA = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
PRODUCT_GIT = '278fd3003758299379f6d87b7e9174c577f5bb88'
PRODUCT_BINDING = BRIEF / 'install/PRODUCT_RUN_BINDING.json'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
SLOTS = {'QN': ('N', 'qualification'), 'N1': ('N', 'formal'), 'P1': ('P', 'formal'),
         'P2': ('P', 'formal'), 'N2': ('N', 'formal'), 'N3': ('N', 'formal'), 'P3': ('P', 'formal')}
ORDER = tuple(SLOTS)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True).encode() + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def asset_identity():
    path = ASSET.resolve()
    if sha(path) != ASSET_SHA256:
        raise ValueError('frozen_fixture_asset_mismatch')
    return path, ASSET_SHA256
