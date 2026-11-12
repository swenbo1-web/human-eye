"""Evidence utilities with no imports from the product under verification."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
QUAL = BATCH / 'qualification'
WORKER = BATCH / 'worker'


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
