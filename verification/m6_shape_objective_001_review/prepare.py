"""Freeze the delivery and its explicitly reused files for independent review."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

START, CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
HEAD = 'e2d163159bd9c3110395304b16ac9cd43a0da905'
BASE = '29e81ed1d1b2fde2464cdbf856f96086f9ae4b46'
PLAN = '38d772333cc8daf2fcf61585a4af1d65ba19d974'
REL = Path('verification/m6_shape_objective_001')
SNAP = HERE / 'snapshot'

def git(*args):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *args])

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

records = {}
def save(rel, blob, expected=None):
    rel = Path(rel)
    assert not rel.is_absolute() and '..' not in rel.parts
    assert 'Bunny' not in str(rel)
    value = {'path': rel.as_posix(), 'bytes': len(blob), 'sha256': sha(blob)}
    if expected:
        assert value['bytes'] == expected['bytes'] and value['sha256'] == expected['sha256'], str(rel)
    if rel.as_posix() in records:
        assert records[rel.as_posix()] == value
    target = SNAP / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    records[rel.as_posix()] = value

assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert not git('status', '--porcelain').strip()
delta = [line.split('\t') for line in git('diff', '--name-status', BASE, HEAD).decode().splitlines()]
assert len(delta) == 32 and all(s == 'A' and p.startswith(REL.as_posix() + '/') for s, p in delta)
git('merge-base', '--is-ancestor', PLAN, HEAD)
for _, path in delta:
    blob = git('show', HEAD + ':' + path)
    assert blob == (AUTHOR / path).read_bytes()
    save(path, blob)
manifest = json.loads((SNAP / REL / 'EVIDENCE_MANIFEST.json').read_bytes())
assert (len(manifest['public_files']), len(manifest['private_files'])) == (31, 389)
for row in manifest['public_files'] + manifest['private_files']:
    rel = REL / row['path']
    save(rel, (AUTHOR / rel).read_bytes(), row)
reused = json.loads((SNAP / REL / 'REUSED_INPUTS.json').read_bytes())['reused_input_files']
assert len(reused) == 1088
tracked = set(git('ls-tree', '-r', '--name-only', BASE).decode().splitlines())
tracked_reused = 0
for row in reused:
    rel = Path(row['path']).relative_to(AUTHOR)
    blob = (AUTHOR / rel).read_bytes()
    if rel.as_posix() in tracked:
        assert blob == git('show', BASE + ':' + rel.as_posix())
        tracked_reused += 1
    save(rel, blob, row)
frozen = json.loads((SNAP / REL / 'PLAN_FREEZE.json').read_bytes())
for row in frozen['files']:
    rel = REL / row['path']
    assert (SNAP / rel).read_bytes() == git('show', PLAN + ':' + rel.as_posix())
    assert sha((SNAP / rel).read_bytes()) == row['sha256']
result = {'status': 'passed', 'author_commit': HEAD, 'base_commit': BASE, 'plan_commit': PLAN,
          'new_public_files': len(delta), 'manifest_files': 420, 'reused_files': len(reused),
          'tracked_reused_identical_to_base': tracked_reused, 'frozen_plan_files': len(frozen['files']),
          'snapshot_files': len(records), 'snapshot_bytes': sum(r['bytes'] for r in records.values()),
          'records': list(records.values()), 'body_wall_s': time.perf_counter()-START,
          'body_CPU_s': time.process_time()-CPU, 'arrays_deserialized': 0}
(HERE / 'SNAPSHOT.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='records'}))
