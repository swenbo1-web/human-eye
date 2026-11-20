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
EXTERNAL = Path('D:/he_m4_cross_scale_live_task_recovery_001')
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
ASSET_SHA256 = None  # Supplied at runtime by the frozen fixture binding.
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
PRODUCT_BINDING = V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
SLOTS = {'QN': ('N', 'qualification'), 'QP': ('P', 'qualification'),
         'N1': ('N', 'formal'), 'P1': ('P', 'formal')}


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
    manifest = read(NS / 'fixture/ASSET_BINDING.json')
    path = Path(manifest['asset_path']).resolve()
    if path != ASSET.resolve() or sha(path) != manifest['asset_sha256']:
        raise ValueError('frozen_fixture_asset_mismatch')
    return path, manifest['asset_sha256']
