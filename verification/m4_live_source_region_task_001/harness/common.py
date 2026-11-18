"""Batch identity and durable evidence helpers."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
EXTERNAL = Path('D:/he_m4_live_source_region_task_001')
DISPLAY = ROOT / 'verification/m4_source_region_display_001'
PRIOR = ROOT / 'verification/m1_source_region_facts_first_001'
ORIGINAL_POSE_SOURCE = Path('D:/he_m4_source_region_display_001/sessions/main/product_full/call_001/SERVICE_RESULT.json')
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA256 = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
BASELINE = '544cf4f123c35fbca24b8f425acc30fd3308b178'
PLAN_COMMIT = 'a2658860696ed6d03e4fcd3b1a8b165628b2c8c7'
PLAN_SHA = 'f3df175cfb57a36f0fd7579af75abcddd64633245762059b11f6d06b57a17e14'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
