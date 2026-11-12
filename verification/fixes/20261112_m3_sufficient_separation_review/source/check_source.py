"""Root byte audit only: fixed Git artifacts, wheel RECORD and installed sources."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
EVIDENCE = '189ecdb84185d96c3ed0d75ca268bc16d6d4999b'
PRODUCT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
PREVIOUS = '743a484f16f1dadff8dedcf1abad8d0a14398d17'
BASE = 'verification/m3_sufficient_separation_001/'
INDEX_SHA = '5313a20433d76263bced43ab0fab0119d7cd53ab40e6522c2d88a549d05afa65'
PLAN_SHA = '2011d38aade474a7f862d324a2fa883ac701064976cc2a87059f01d249b30f10'

def sha(data): return hashlib.sha256(data).hexdigest()
def git(*args): return subprocess.check_output(['git', '-C', str(REPO), *args])

reader = subprocess.Popen(['git', '-C', str(REPO), 'cat-file', '--batch'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE)
def blob(commit, path):
    reader.stdin.write((commit + ':' + path + '\n').encode())
    reader.stdin.flush()
    header = reader.stdout.readline().split()
    assert len(header) == 3 and header[1] == b'blob', (commit, path, header)
    data = reader.stdout.read(int(header[2]))
    assert reader.stdout.read(1) == b'\n'
    return data

try:
    assert git('rev-parse', 'HEAD').decode().strip() == EVIDENCE
    assert git('status', '--porcelain') == b''
    indexed = blob(EVIDENCE, BASE + 'INDEX.json')
    assert sha(indexed) == INDEX_SHA
    index = json.loads(indexed)
    assert index['count'] == len(index['files']) == 623
    rows = []
    seen = set()
    for row in index['files']:
        path = BASE + row['path']
        assert path not in seen and '..' not in Path(row['path']).parts
        seen.add(path)
        data = blob(EVIDENCE, path)
        assert len(data) == row['bytes'] and sha(data) == row['sha256'], path
        assert (REPO / path).read_bytes() == data, path
        rows.append({'path': path, 'bytes': len(data), 'sha256': sha(data)})
    assert sum(r['bytes'] for r in rows) == index['bytes']
    for name in ('INDEX.json', 'COMPLETE.json'):
        data = blob(EVIDENCE, BASE + name)
        assert (REPO / (BASE + name)).read_bytes() == data
        rows.append({'path': BASE + name, 'bytes': len(data), 'sha256': sha(data)})
    complete = json.loads(blob(EVIDENCE, BASE + 'COMPLETE.json'))
    assert complete['index_sha256'] == INDEX_SHA
    assert complete['report_sha256'] == sha(blob(EVIDENCE, BASE + 'REPORT.md'))
    assert complete['saved_verification_sha256'] == sha(blob(EVIDENCE, BASE + 'SAVED_VERIFICATION.json'))
    assert sha(blob(EVIDENCE, BASE + 'ROOT_PLAN.md')) == PLAN_SHA
    candidate = json.loads(blob(EVIDENCE, BASE + 'CANDIDATE_FREEZE.json'))
    ready = json.loads(blob(EVIDENCE, BASE + 'installation/READY.json'))
    manifest = candidate['manifest']
    assert len(manifest) == candidate['source_count'] == ready['source_count'] == 137
    assert complete['product_commit'] == ready['commit'] == PRODUCT
    assert candidate['source_sha256'] == ready['source_sha256'] == complete['source_sha256']
    installed = Path(ready['install_root'])
    wheel_name = BASE + 'installation/run_01/bundle/human_eye_spatial_plugin-9.7.2+m3.sufficient.r1-py3-none-any.whl'
    wheel_raw = blob(EVIDENCE, wheel_name)
    assert sha(wheel_raw) == ready['wheel_sha256']
    wheel = zipfile.ZipFile(io.BytesIO(wheel_raw))
    assert len(wheel.namelist()) == len(set(wheel.namelist()))
    for row in manifest:
        path = row['path']
        data = blob(PRODUCT, path)
        assert sha(data) == row['sha256'], path
        assert blob(EVIDENCE, path) == data
        assert (REPO / path).read_bytes() == data
        assert (installed / path).read_bytes() == data
        assert wheel.read(path) == data
    records = next(n for n in wheel.namelist() if n.endswith('.dist-info/RECORD'))
    record_rows = list(csv.reader(io.StringIO(wheel.read(records).decode())))
    for path, encoded_hash, size in record_rows:
        data = wheel.read(path)
        if not encoded_hash:
            assert path == records and not size
            continue
        scheme, digest = encoded_hash.split('=', 1)
        assert scheme == 'sha256'
        assert base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode() == digest
        assert len(data) == int(size)
    assert {r[0] for r in record_rows} == set(wheel.namelist())
    admin_rows = []
    for name, key in [('target_runtime_entry.py','launcher_sha256'), ('RUNTIME_BINDING.json','binding_sha256')]:
        data = (Path(ready['release']) / 'admin' / name).read_bytes()
        assert sha(data) == ready[key]
        admin_rows.append({'name': name, 'sha256': sha(data)})
    changed_product = git('diff', '--name-only', '3beb3f809674658b086e50af194adaa16e226111', PRODUCT, '--', 'human_eye_plugin').decode().splitlines()
    assert changed_product == ['human_eye_plugin/live_spatial_mcp.py', 'human_eye_plugin/surface_geometry.py', 'human_eye_plugin/surface_proximity.py', 'human_eye_plugin/task_query.py']
    changed_all = git('diff', '--name-only', PREVIOUS, EVIDENCE).decode().splitlines()
    result = {'passed': True, 'evidence_commit': EVIDENCE, 'product_commit': PRODUCT,
              'index_sha256': INDEX_SHA, 'plan_sha256': PLAN_SHA,
              'indexed_artifacts': 623, 'evidence_files': len(rows),
              'source_files_git_worktree_wheel_install_equal': len(manifest),
              'wheel_record_members_verified': len(record_rows), 'admin_files_verified': admin_rows,
              'changed_product': changed_product, 'changed_files': changed_all,
              'artifacts': rows, 'manifest': manifest,
              'scope': 'Independent bytes and RECORD audit. No product/Blender/model executed.'}
    (HERE/'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','indexed_artifacts','evidence_files','source_files_git_worktree_wheel_install_equal','wheel_record_members_verified','changed_product']}))
finally:
    reader.stdin.close()
    reader.stdout.close()
    assert reader.wait(timeout=20) == 0
