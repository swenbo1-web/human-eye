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
EXTERNAL = Path('D:/he_m4_cross_scale_pixel_evidence_001')
RECOVERY_EXTERNAL = Path('D:/he_m4_cross_scale_live_task_recovery_001')
RECOVERY = V / 'm4_cross_scale_live_task_recovery_001'
ASSET = Path('D:/he_m4_assembly_evidence_consumption_001/slots/A1/native/input.blend')
ASSET_SHA256 = None  # Supplied at runtime by the frozen fixture binding.
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BINDINGS = {'P': NS / 'install/PRODUCT_RUN_BINDING.json'}
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
ORDER = ('P1',)
SLOTS = {label: ('P', 'formal') for label in ORDER}


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
    manifest = read(ASSEMBLY / 'fixture/ASSET_BINDING.json')
    path = Path(manifest['asset_path']).resolve()
    if path != ASSET.resolve() or sha(path) != manifest['asset_sha256']:
        raise ValueError('frozen_fixture_asset_mismatch')
    return path, manifest['asset_sha256']
