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
EXTERNAL = Path('D:/he_m4_assembly_evidence_consumption_001')
DISPLAY = ROOT / 'verification/m4_source_region_display_001'
PRIOR = ROOT / 'verification/m1_source_region_facts_first_001'
LIVE = ROOT / 'verification/m4_live_assembly_relation_task_001'
ASSEMBLY_INPUTS = ROOT / 'verification/m4_local_relation_consumption_001/input'
ASSET = ASSEMBLY_INPUTS / 'scene.blend'
ASSET_SHA256 = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
TASK = 'M4-ASSEMBLY-EVIDENCE-CONSUMPTION-001'
BASELINE = 'ed9fad2a22b9733197a65dd23f874e8214740862'
PLAN_COMMIT = '80cf61667dbc0f0e8e0420faf6e48154d1689ba1'
PLAN_SHA = '26e07cdbe90403b10dd4f2b23b5c4cf0b9f05f6b7c1745b7aa7875f84899aeb9'
BINDINGS = {
    'A1': {'path': LIVE / 'PRODUCT_RUN_BINDING.json',
           'source_sha256': '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b',
           'binding_sha256': 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'},
    'B1': {'path': ROOT / 'verification/m4_assembly_evidence_first_001/install/OPTIMIZED_BINDING.json',
           'source_sha256': '99d9b5e93ae10294309df2258b0582405861c0189ab15d659ae9b9e26df6ec9a',
           'binding_sha256': '4ec94ff30668330483e24ac8a9169c6cc3cb080fb93ea717adddf482dee33bc9'},
}
ALL_NAMES = tuple(f'N{number:02d}' for number in range(1, 29))
TASK_NAMES = ('N16', 'N13', 'N08', 'N28')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def product_binding(label):
    pinned = BINDINGS[label]
    path = pinned['path']
    if sha(path) != pinned['binding_sha256']:
        raise ValueError('fixed_product_binding_bytes_required/' + label)
    value = read(path)
    if len(value['source_manifest']) != 143 or value['source_sha256'] != pinned['source_sha256']:
        raise ValueError('fixed_product_source_required/' + label)
    return path, value


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
