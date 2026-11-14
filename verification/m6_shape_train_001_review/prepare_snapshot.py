"""Read and freeze TRAIN001 evidence without executing author code."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT = '9c29a9f0990421c607ee821e838394e73dcaa9f3'
PRE = '074104b5a9a09bf423b7e12d3cb52c590ce610b3'
BASE = 'efce450c1da372642010871994588a69799e268c'
REL = 'verification/m6_shape_train_001'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=AUTHOR)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, str(path)
    else:
        path.write_bytes(data)

def check(item):
    data = Path(item['path']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256'], item['path']
    return data

assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
assert not git('status', '--porcelain=v1').strip()
changed = git('diff', '--name-only', BASE, COMMIT).decode().splitlines()
assert len(changed) == 54 and all(x.startswith(REL + '/') for x in changed)
out = {'commit': COMMIT, 'pretraining_commit': PRE, 'changed_files': changed, 'sources': [], 'checked_records': []}
for rel in changed:
    data = git('show', COMMIT + ':' + rel)
    assert data == (AUTHOR / rel).read_bytes()
    put(HERE / 'snapshot' / rel, data)
    out['sources'].append({'relative': rel, 'bytes': len(data), 'sha256': sha(data)})
manifest = json.loads((HERE / 'snapshot' / REL / 'EVIDENCE_MANIFEST.json').read_bytes())
for group in ('public_delivery_files', 'private_artifacts_excluding_venv'):
    for item in manifest[group]:
        data = check(item)
        out['checked_records'].append({'group': group, **item})
        if group == 'private_artifacts_excluding_venv':
            put(HERE / 'snapshot' / Path(item['path']).relative_to(AUTHOR), data)
freeze = json.loads((HERE / 'snapshot' / REL / 'TRAIN_FREEZE.json').read_bytes())
for item in freeze['files']:
    data = check(item)
    rel = Path(item['path']).relative_to(AUTHOR).as_posix()
    assert git('show', PRE + ':' + rel) == data
out['pretraining_files_identical'] = len(freeze['files'])
old = json.loads((AUTHOR / 'verification/m6_shape_data_001/EVIDENCE_MANIFEST.json').read_bytes())
for group in ('public_delivery_files', 'private_local_files', 'source_originals', 'reused_previous_inputs'):
    for item in old[group]:
        check(item)
        out['checked_records'].append({'group': 'DATA001/' + group, **item})
out['venv'] = manifest['venv_summary']['path']
out['weights'] = manifest['weights']
out['Bunny_scoring'] = 0
(HERE / 'SNAPSHOT.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'sources': len(out['sources']), 'manifest_records': len(out['checked_records']), 'pretraining_files': out['pretraining_files_identical'], 'weights_sha256': out['weights']['sha256']}))
