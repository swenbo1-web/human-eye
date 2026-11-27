"""042 offline replay identity helpers; no native host or product imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BASE = Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK')
RAW = Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/replay')
PYTHON = Path('D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe')
ASSET = Path('D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/native/input.blend')
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
SOURCE = Path('D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/initial_capture/TERMINAL_SOURCE.json')
TRUTH = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_same_frame_scoped_batch_034/private/inputs/FROZEN.json')
TARGET = {'name': '0135bbc4-c6c7-4003-a402-6f2e0283497d'}
REFERENCE = {'name': 'Cube'}
BOX = {'min': [-0.03, -0.055, 0.81], 'max': [0.03, 0.055, 0.855]}
SOURCES = {'032': 'a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d',
           'r3': 'ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e'}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def dump(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def verify(ref):
    need(pin(ref['path']) == ref, 'file_identity_changed: ' + ref['path'])


def installation(arm):
    pins_path = BASE / 'install/PINS.json'
    pins = read(pins_path)
    ref = pins['binding'][arm]
    verify(ref)
    binding = read(ref['path'])
    need(binding['identity'] == pins['identities'][arm], 'installation_identity')
    need(binding['identity']['source_sha256'] == SOURCES[arm], 'frozen_source_identity')
    need(len(binding['source_files']) == 143, 'frozen_source_count')
    site = Path(binding['site_packages'])
    for source in binding['source_files']:
        need(pin(site / source['path'])['sha256'] == source['sha256'], 'installed_source_drift')
    return {'arm': arm, 'site_packages': str(site), 'identity': binding['identity'],
            'binding': ref, 'pins': pin(pins_path), 'source_files_verified': 143}
