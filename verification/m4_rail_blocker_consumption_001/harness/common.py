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
EXTERNAL = Path('D:/he_m4_rail_blocker_consumption_001')
BRIEF = V / 'm4_dense_region_brief_001'
BLOCKER = V / 'm4_bound_blocker_evidence_001'
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
ASSET_SHA256 = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
GEOMETRY = Path('D:/he_m4_cross_scale_cold_frustum_001/slots/B1/TERMINAL_SOURCE.json')
GEOMETRY_SHA256 = '31e69a857baf1f66e33722dec5ef63086565c0fbf3029c39071415782c7a0233'
TRUTH = NS / 'truth/CURRENT_TRUTH.json'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
PRODUCTS = {
    'A': {'commit': '278fd3003758299379f6d87b7e9174c577f5bb88',
          'source_sha256': '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'},
    'B': {'commit': 'e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c',
          'source_sha256': '84bf65eedbc0866375d760025437993b90ec54325af09b4e1f36b74abe233d62'},
}
BINDINGS = {arm: base / 'install/PRODUCT_RUN_BINDING.json' for arm, base in (('A', BRIEF), ('B', BLOCKER))}
# The retained superclass imports this name. Its two identity-sensitive methods are overridden.
SOURCE_SHA = PRODUCTS['A']['source_sha256']
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
GENERIC_WORKER = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
ORDER = ('QA', 'QB', 'A1', 'B1', 'B2', 'A2', 'A3', 'B3')
SLOTS = {label: ('P', 'qualification' if label in ORDER[:2] else 'formal') for label in ORDER}
ARMS = {label: label[1] if phase == 'qualification' else label[0] for label, (_, phase) in SLOTS.items()}


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


def product_for(label):
    arm = ARMS[label]
    path = BINDINGS[arm]
    binding = read(path)
    product = PRODUCTS[arm]
    if (binding['preparation_git'] != product['commit']
            or binding['source_sha256'] != product['source_sha256']
            or len(binding['source_manifest']) != 143):
        raise ValueError('fixed_143_source_install_required/' + arm)
    return path, binding
