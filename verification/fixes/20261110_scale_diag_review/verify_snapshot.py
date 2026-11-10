"""Read-only stdlib verification of the fixed author evidence and installation."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT / 'verification/scale_diag_001'
COMMIT = 'b39a5d9f58aed2782225287738413982beac4920'
BASE = 'd01d49bc0ec82583b24a8faf22e622e6f6ea8c5d'
PREFIX = 'verification/scale_diag_001/'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blobs(commit, paths):
    proc = subprocess.Popen(['git', '-C', str(ROOT), 'cat-file', '--batch'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    raw, _ = proc.communicate(''.join(f'{commit}:{p}\n' for p in paths).encode())
    assert proc.returncode == 0
    offset = 0
    for path in paths:
        end = raw.index(b'\n', offset)
        head = raw[offset:end].split()
        assert len(head) == 3 and head[1] == b'blob', (path, head)
        size = int(head[2])
        start = end + 1
        yield path, raw[start:start + size]
        offset = start + size + 1
    assert offset == len(raw)


seal_bytes = (BATCH / 'SEAL.json').read_bytes()
seal = json.loads(seal_bytes)
paths = sorted(seal['files'])
assert len(paths) == seal['file_count'] == 1436
disk_bytes = 0
for path in paths:
    content = (BATCH / path).read_bytes()
    assert sha(content) == seal['files'][path], path
    disk_bytes += len(content)
assert disk_bytes == seal['raw_bytes']
tracked = set(git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines())
expected = {PREFIX + p for p in paths} | {PREFIX + 'SEAL.json'}
assert tracked == expected, (tracked - expected, expected - tracked)
for path, content in blobs(COMMIT, sorted(expected)):
    assert content == (ROOT / path).read_bytes(), path
changed = git('diff', '--name-only', COMMIT + '^', COMMIT).decode().splitlines()
assert set(changed) == expected
assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
assert not git('status', '--porcelain').strip()

freeze = json.loads((BATCH / 'FREEZE.json').read_bytes())
for path, digest in freeze['files'].items():
    assert sha((BATCH / path).read_bytes()) == digest, path
identities = []
for file in sorted((BATCH / 'measurements').glob('*/IDENTITY.json')):
    data = json.loads(file.read_bytes())
    if isinstance(data, dict) and data.get('source_kind') == 'installed_distribution':
        identities.append(data)
assert len(identities) == 9, len(identities)
manifest = identities[0]['source_files']
assert len(manifest) == 137
for identity in identities:
    assert identity['source_files'] == manifest
    assert identity['source_sha256'] == freeze['source_canonical']
installed = ROOT / '.plugin_ab_runtime/B/venv/Lib/site-packages'
manifest_map = {row['path']: row['sha256'] for row in manifest}
for path, content in blobs(BASE, sorted(manifest_map)):
    assert sha(content) == manifest_map[path], path
    assert (installed / path).read_bytes() == content, path
    assert (ROOT / path).read_bytes() == content, path

print(json.dumps({
    'passed': True, 'author_commit': COMMIT, 'product_commit': BASE,
    'seal_sha256': sha(seal_bytes), 'evidence_files_excluding_seal': len(paths),
    'evidence_bytes_excluding_seal': disk_bytes, 'git_blobs_exact': len(expected),
    'changed_paths_only_batch': True, 'worktree_clean': True,
    'freeze_files_verified': len(freeze['files']),
    'installed_identities': len(identities), 'product_sources_verified': len(manifest),
    'scope': 'stdlib hashes/bytes and records only; no product imports, model or Blender run'
}, indent=2))
