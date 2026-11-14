"""Bind fixed delivery bytes and private artifacts to a reviewer-owned snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT = '9b016c8720b709a6382438ddd505c7b154d4fac2'
BASE = '8a99c344caf4560ee87fbb9f7540bf67ff3f2469'
REL = 'verification/m6_shape_pairs_001'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=AUTHOR)


def place(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, str(path)
    else:
        path.write_bytes(data)


assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
assert not git('status', '--porcelain=v1').strip()
changed = git('diff', '--name-only', BASE, COMMIT).decode().splitlines()
assert len(changed) == 21 and all(x.startswith(REL + '/') for x in changed)
paths = git('ls-tree', '-r', '--name-only', COMMIT, REL).decode().splitlines()
paths += ['verification/m6_coupled_probe_002/evaluate.py', 'human_eye_plugin/surface_geometry.py']
out = {'delivery_commit': COMMIT, 'base_commit': BASE, 'changed_files': changed, 'source_files': [], 'manifest_checks': []}
for rel in paths:
    data = git('show', COMMIT + ':' + rel)
    assert (AUTHOR / rel).read_bytes() == data
    target = HERE / 'snapshot' / rel
    place(target, data)
    out['source_files'].append({'relative': rel, 'bytes': len(data), 'sha256': sha(data)})
manifest = json.loads((HERE / 'snapshot' / REL / 'EVIDENCE_MANIFEST.json').read_bytes())
for group in ['source_inputs', 'public_delivery_files', 'private_local_files']:
    for row in manifest[group]:
        source = Path(row['path'])
        data = source.read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256'], str(source)
        out['manifest_checks'].append({'group': group, **row})
        if group == 'private_local_files':
            relative = source.relative_to(AUTHOR)
            place(HERE / 'snapshot' / relative, data)
for group in ['original_asset', 'fixed_reused_contact_evaluator']:
    row = manifest[group]
    data = Path(row['path']).read_bytes()
    assert len(data) == row['bytes'] and sha(data) == row['sha256']
    out['manifest_checks'].append({'group': group, **row})
for rel in ['CASE_PLAN.json', 'method.py', 'generate.py']:
    assert git('show', 'ce5b2fd38e0a362ecc90df03586dbc139c9dc8ef:' + REL + '/' + rel) == (HERE/'snapshot'/REL/rel).read_bytes()
out['preregistered_plan_and_method_identical'] = True
out['private_artifact_count'] = len(manifest['private_local_files'])
(HERE / 'SNAPSHOT.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'changed_files': len(changed), 'source_files': len(paths), 'manifest_checks': len(out['manifest_checks']), 'private_artifacts': out['private_artifact_count']}))
