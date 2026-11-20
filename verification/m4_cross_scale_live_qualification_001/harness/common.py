"""Pinned qualification identities and reused test transport paths."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
V = ROOT / 'verification'
EXTERNAL = Path('D:/he_m4_cross_scale_live_qualification_001')
SLOT = EXTERNAL / 'slots/Q1'
GLOBAL = V / 'm4_global_local_qualification_001'
GLOBAL_HARNESS = GLOBAL / 'harness'
IMAGE_BRIDGE = V / 'm4_live_source_region_task_003'
BINDING = V / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
ASSET = Path('D:/he_m4_global_local_001/fixture/main.blend')
ASSET_SHA = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'


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
