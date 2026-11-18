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
EXTERNAL = Path('D:/he_m4_live_assembly_relation_task_001')
DISPLAY = ROOT / 'verification/m4_source_region_display_001'
PRIOR = ROOT / 'verification/m1_source_region_facts_first_001'
ASSEMBLY_INPUTS = ROOT / 'verification/closed_solid_read_001/inputs'
ASSET = ASSEMBLY_INPUTS / 'scene.blend'
ASSET_SHA256 = 'a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
BASELINE = 'a82437ca1cf113fcc7b7f9a0f181c3377b3c8348'
PLAN_COMMIT = '51ff1af4ab47621f528ceb02f9aa2a24bf2f6431'
PLAN_SHA = 'b44630a0353af9f8943f56e50c80f710830143bb1f720dcf81bcf8787ae8bee7'


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
