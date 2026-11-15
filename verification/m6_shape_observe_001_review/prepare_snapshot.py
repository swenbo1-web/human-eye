"""Freeze this diagnostic and its relevant old inputs without editing the author."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT = '66e171ceb72c930ba534e1eb8317791d00bd2dba'
BASE = '36694d0e3730a60b0611376b017f978f809a79c0'
PRE = 'a655121005a8474cc055e1b4e7cba61e3d8c588d'
REL = 'verification/m6_shape_observe_001'
SNAP = HERE / 'snapshot'

def git(*a): return subprocess.check_output(['git', *a], cwd=AUTHOR)
def sha(b): return hashlib.sha256(b).hexdigest()
def put(p, b):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists(): assert p.read_bytes() == b, str(p)
    else: p.write_bytes(b)
def checked(r):
    b = Path(r['path']).read_bytes()
    assert len(b) == r['bytes'] and sha(b) == r['sha256'], r['path']
    return b

start, cpu = time.perf_counter(), time.process_time()
assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
assert not git('status', '--porcelain').strip()
changes = git('diff', '--name-status', BASE, COMMIT).decode().splitlines()
assert len(changes) == 37 and all(c.startswith('A\t' + REL + '/') for c in changes)
dirs = ['verification/m6_shape_data_001', 'verification/m6_shape_train_001',
        'verification/m6_shape_opt_001', REL]
archive = git('archive', '--format=zip', COMMIT, '--', *dirs)
files = []
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    for entry in z.infolist():
        if entry.is_dir(): continue
        p = SNAP / entry.filename
        assert p.resolve().is_relative_to(SNAP.resolve())
        b = z.read(entry)
        assert b == (AUTHOR / entry.filename).read_bytes(), entry.filename
        put(p, b)
        files.append({'relative': entry.filename, 'bytes': len(b), 'sha256': sha(b)})
manifest = json.loads((SNAP / REL / 'EVIDENCE_MANIFEST.json').read_bytes())
new = manifest['public_delivery_files'] + manifest['private_artifacts']
for r in new:
    b = checked(r)
    put(SNAP / Path(r['path']).relative_to(AUTHOR), b)
reuse = json.loads((SNAP / REL / 'REUSED_INPUTS.json').read_bytes())['reused_input_files']
external = []
for r in reuse:
    assert 'Bunny' not in r['path'], r['path']
    b = checked(r)
    p = Path(r['path'])
    if p.is_relative_to(AUTHOR): put(SNAP / p.relative_to(AUTHOR), b)
    else: external.append(r)  # identities only, no duplicate source asset
freeze = json.loads((SNAP / REL / 'PLAN_FREEZE.json').read_bytes())
for r in freeze['files']:
    b = git('show', PRE + ':' + REL + '/' + r['path'])
    assert sha(b) == r['sha256'] and len(b) == r['bytes']
    assert b == (SNAP / REL / r['path']).read_bytes(), r['path']
contract = git('show', 'bc86c84f6019457a3a2d75ee8cdbf7f5a1d00653:docs/M6_SHAPE_OBSERVE_001_TASK.md')
assert contract == (SNAP / REL / 'M6_SHAPE_OBSERVE_001_TASK.md').read_bytes()
out = {'commit': COMMIT, 'base': BASE, 'plan_commit': PRE,
       'tracked_archive_files': files, 'new_manifest_records': len(new),
       'reused_records': len(reuse), 'external_source_identity_only': external,
       'plan_records': len(freeze['files']), 'source_changes': changes,
       'snapshot_files': [{'relative': p.relative_to(SNAP).as_posix(), 'bytes': p.stat().st_size,
                           'sha256': sha(p.read_bytes())} for p in sorted(SNAP.rglob('*')) if p.is_file()],
       'wall_s_before_final_write': time.perf_counter() - start,
       'CPU_s_before_final_write': time.process_time() - cpu,
       'Bunny_arrays': 0}
(HERE / 'SNAPSHOT.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({k: out[k] for k in ('commit','new_manifest_records','reused_records','plan_records','wall_s_before_final_write')}))
