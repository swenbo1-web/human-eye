"""Verify fixed Git blobs, disk bytes and prior evidence without product imports."""
import hashlib
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = 'aca915f45d57b5e5a3d75e9f8a0beb1e64e8f8c6'
PRODUCT = '201fccc4de85c64e3c0ddb11dfeb3489c976661c'
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)
def sha(value): return hashlib.sha256(value).hexdigest()
def blobs(commit, names):
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
        input=b''.join((commit + ':' + name + '\n').encode() for name in names), capture_output=True, check=True)
    data = result.stdout
    answer = {}
    for name in names:
        header, data = data.split(b'\n', 1)
        oid, kind, size = header.split()
        assert kind == b'blob'
        size = int(size)
        answer[name] = data[:size]
        assert data[size:size+1] == b'\n'
        data = data[size+1:]
    assert not data
    return answer
baseline = json.loads((OUT / 'baseline_checks.json').read_bytes())
candidate = json.loads((OUT / 'candidate_checks.json').read_bytes())
names = [row['path'] for row in baseline['source_files']]
assert len(names) == 131
base_blobs = blobs(BASE, names)
product_blobs = blobs(PRODUCT, names)
baseline_root = Path(baseline['source'])
for row in baseline['source_files']:
    name = row['path']
    assert sha(base_blobs[name]) == row['sha256']
    assert (baseline_root / name).read_bytes() == base_blobs[name]
for row in candidate['source_files']:
    name = row['path']
    assert sha(product_blobs[name]) == row['sha256']
    assert (ROOT / name).read_bytes() == product_blobs[name]
changed = [name for name in names if base_blobs[name] != product_blobs[name]]
assert set(changed) == {'human_eye_plugin/live_service.py', 'human_eye_plugin/host_runtime.py', 'human_eye_plugin/auto_router.py'}
protected = git('ls-tree', '-r', '--name-only', BASE, '--',
    'verification/spatial_task_entry_001', 'verification/task_scope_impl_001',
    'verification/task_scope_entry_opt_001').decode().splitlines()
protected_blobs = blobs(BASE, protected)
assert all((ROOT / name).read_bytes() == value for name, value in protected_blobs.items())
value = {'baseline_commit': BASE, 'product_commit': PRODUCT, 'source_count': 131,
         'baseline_sha256': baseline['source_sha256'], 'candidate_sha256': candidate['source_sha256'],
         'changed_runtime_files': changed, 'all_source_bytes_match_fixed_git': True,
         'prior_evidence_exactly_unchanged': len(protected),
         'product_sha256': {name: sha(product_blobs[name]) for name in changed}}
(OUT / 'SOURCE_AUDIT.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')
print(json.dumps(value, indent=2))
