from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path('D:/hefe/verification/fixes/20261111_m4_observation_prep_review')
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = WT / 'verification/m4_observation_baseline_001'
PREP = '9c85ab9a0518e1fe2369113f59ce308a2d97b8d3'
PRODUCT = '107641ec19919d56aa843c1949261590fc338148'
PINS = {
    'PLAN.json': 'a3be58d51b274470ddbbb46ae07b2706328606bf9a09823c6e09dbe757d37ac2',
    'FREEZE.json': '32cdb111df16428f1576820fa813fe0fbe5adc9a5555ea78a834ca6c4dd2199d',
    'ARTIFACT_INDEX.json': '693f3a6615080398bd239faab633dbe9707be00ef74de55c0f4a982231cdc98e',
}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def git(*args, input=None):
    return subprocess.run(['git', '-C', str(WT), *args], input=input, check=True, capture_output=True).stdout

out = {'review_kind': 'independent read-only bytes and Git audit; no product/Blender/model execution', 'prep_commit': PREP, 'product_commit': PRODUCT}
out['head'] = git('rev-parse', 'HEAD').decode().strip()
assert out['head'] == PREP
out['tracked_worktree_status'] = git('status', '--short').decode()
assert not out['tracked_worktree_status']
out['pins'] = {}
for name, expected in PINS.items():
    actual = digest((B / name).read_bytes())
    assert actual == expected, name
    out['pins'][name] = actual
index = read(B / 'ARTIFACT_INDEX.json')
seen = set()
total = 0
for row in index['files']:
    p = WT / row['path']
    assert p.resolve().is_relative_to(B.resolve()), row['path']
    assert row['path'] not in seen
    seen.add(row['path'])
    raw = p.read_bytes()
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256'], row['path']
    total += len(raw)
assert len(seen) == index['file_count'] == 303
assert total == index['bytes'] == 4791802
out['indexed_files'] = len(seen)
out['indexed_bytes'] = total
prefix = 'verification/m4_observation_baseline_001/'
changed = git('diff', '--name-only', PRODUCT, PREP).decode().splitlines()
assert len(changed) == 305 and all(p.startswith(prefix) for p in changed)
paths = sorted(seen | {prefix+'ARTIFACT_INDEX.json', prefix+'FREEZE.json'})
assert set(paths) == set(changed)
requests = ''.join(PREP+':'+p+'\n' for p in paths).encode()
batch = git('cat-file', '--batch', input=requests)
offset = 0
for rel in paths:
    end = batch.index(b'\n', offset)
    header = batch[offset:end].decode().split()
    assert header[1] == 'blob'
    size = int(header[2]); offset = end + 1
    blob = batch[offset:offset+size]; offset += size
    assert batch[offset:offset+1] == b'\n'; offset += 1
    assert blob == (WT / rel).read_bytes(), rel
assert offset == len(batch)
out['git_blobs_equal_current_files'] = len(paths)
out['changes_only_new_preparation_materials'] = True
plan = read(B/'PLAN.json')
for rel, expected in plan['dispatch_input_sha256'].items():
    p = (B/rel).resolve()
    assert p.is_relative_to(WT.resolve())
    assert digest(p.read_bytes()) == expected, rel
out['dispatch_pins_verified'] = len(plan['dispatch_input_sha256'])
out['anonymous_mapping'] = 'digest only; no parse or exposure'
for name in ('GO.json', 'STARTED.json', 'RUN_RESULT.json', 'cells'):
    assert not (B/name).exists(), name
out['formal_markers_absent'] = ['GO.json','STARTED.json','RUN_RESULT.json','cells']
original = Path('D:/hefe/verification/fixes/20261103_spatial_perception_qual002/shared')
preserved = []
for path in sorted(original.iterdir()):
    if not path.is_file():
        continue
    matches = [row['path'] for row in index['files'] if row['sha256'] == digest(path.read_bytes()) and row['bytes'] == path.stat().st_size]
    assert matches, path.name
    preserved.append({'name':path.name,'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size,'matching_preparation_paths':matches})
assert len(preserved) == 7
out['preserved_original_shared_files'] = preserved
freeze = read(B/'FREEZE.json')
old_checks = []
for old in freeze['old_evidence_unchanged']:
    ip = WT/old['index']
    assert digest(ip.read_bytes()) == old['sha256']
    ix = read(ip)
    rows = ix['files'] + ix.get('duplicate_input_assets_retained_local_and_in_private_zip', [])
    for row in rows:
        p = WT / row['path']
        assert digest(p.read_bytes()) == row['sha256'], row['path']
    assert len(rows) == old['unchanged_files']
    old_checks.append({'index':old['index'],'verified_records':len(rows)})
out['old_evidence_records_verified'] = old_checks
out['passed'] = True
(ROOT/'INTEGRITY.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='preserved_original_shared_files'}, ensure_ascii=False, indent=2))
