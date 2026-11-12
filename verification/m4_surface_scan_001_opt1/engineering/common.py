"""Evidence utilities with no imports from the product under verification."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
INITIAL = ROOT / 'verification/m4_surface_scan_001'
QUAL = INITIAL / 'qualification'
WORKER = INITIAL / 'worker'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf8')


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def events(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def request(label):
    return {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call', 'params': {
        'name': 'human_eye_scene_observe', 'arguments': {
            'session_id': 'm4-surface-scan-engineering', 'include_image': False,
            'query': {'mode': 'surface_scan', 'threshold_m': 0.002}}}}


def body(response):
    assert 'error' not in response, response
    result = response['result']
    assert result.get('isError') is not True, result
    assert len(result['content']) == 1 and result['content'][0]['type'] == 'text'
    return json.loads(result['content'][0]['text'])


def bind_snapshot(snapshot, reference):
    # Paths and PIDs are expected to differ between independent owned processes.
    ignored = {'pid', 'blend_filepath'}
    actual = {key: value for key, value in snapshot.items() if key not in ignored}
    expected = {key: value for key, value in reference.items() if key not in ignored}
    assert actual == expected, 'actual geometry or source fields differ from qualified state'
    return {'passed': True, 'ignored_fields': sorted(ignored),
            'geometry_and_source_sha256': hashlib.sha256(encoded(actual)).hexdigest()}


def qualification_binding():
    """Check pre-existing promises before collecting this run's hashes."""
    relative = 'verification/m4_surface_scan_001/qualification/QUALIFICATION_READY.json'
    frozen = subprocess.check_output(['git', 'show',
        '96fce78b98cb749885792112e039a406744d282b:'+relative], cwd=ROOT)
    assert (QUAL/'QUALIFICATION_READY.json').read_bytes() == frozen
    ready = json.loads(frozen)
    assert ready['qualification_status'] == 'passed'
    promised = {'asset_sha256': QUAL/'assembly.blend',
        'base_snapshot_sha256': QUAL/'BASE_SNAPSHOT.json',
        'edit_snapshot_sha256': QUAL/'EDIT_SNAPSHOT.json',
        'base_truth_sha256': QUAL/'BASE_TRUTH.json',
        'edit_truth_sha256': QUAL/'EDIT_TRUTH.json',
        'control_certificates_sha256': QUAL/'CONTROL_CERTIFICATES.json',
        'geometry_freeze_sha256': QUAL/'GEOMETRY_FREEZE.json',
        'pose_helper_sha256': WORKER/'pose_native.py',
        'pose_patch_sha256': WORKER/'POSE_PATCH.json'}
    for field, path in promised.items():
        assert sha(path) == ready[field], field
    manifest_path = QUAL/'SOURCE_OUTPUT_MANIFEST.json'
    committed = subprocess.check_output(['git', 'show',
        '96fce78b98cb749885792112e039a406744d282b:'+
        manifest_path.relative_to(ROOT).as_posix()], cwd=ROOT)
    assert manifest_path.read_bytes() == committed
    manifest = json.loads(committed)
    for row in manifest['files']:
        path = INITIAL/row['path']
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
    return ready, {str(path.resolve()): ready[field] for field, path in promised.items()}
