import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('D:/hefe/verification/fixes/20261112_m4_selected_consumption_review')
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = WT/'verification/m4_selected_geometry_consumption_001'
PUBLIC = BATCH/'runtime/handoff_01/public'
COMMIT = 'de35ceda1f5e3f5af2c9ec02f0e4646808f417c2'
EXPECTED_INDEX = '1471432083e17dc6508da7cb074f58c40e0eb4bc651abf1e9e2e647ff79670f5'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write('\n')

index = json.loads((PUBLIC/'INDEX.json').read_bytes())
assert sha((PUBLIC/'INDEX.json').read_bytes()) == EXPECTED_INDEX
rows = index['answers']
assert len(rows) == 9 and len({r['anonymous_id'] for r in rows}) == 9
pins = []
for path in sorted(PUBLIC.rglob('*')):
    if not path.is_file():
        continue
    raw = path.read_bytes()
    rel = path.relative_to(WT).as_posix()
    git_raw = subprocess.check_output(['git', '-C', str(WT), 'show', COMMIT+':'+rel])
    assert raw == git_raw, rel
    pins.append({'path': str(path), 'sha256': sha(raw), 'bytes': len(raw)})
for row in rows:
    folder = PUBLIC/row['directory']
    assert folder.resolve().parent == PUBLIC.resolve()
    assert row['answer_state'] == 'present'
    assert sha((folder/row['answer_file']).read_bytes()) == row['answer_original_sha256']

contract_path = BATCH/'scoring/SCORING_CONTRACT.json'
old_path = BATCH/'scoring/SCORING_CONTRACT_BASELINE.json'
contract = json.loads(contract_path.read_bytes())
old = json.loads(old_path.read_bytes())
omitted = {'cycle_id','fixed_sample_policy','sample_metadata','scope'}
semantic = {k:v for k,v in contract.items() if k not in omitted}
assert len(semantic) == 17
assert semantic == {k:v for k,v in old.items() if k not in omitted}
save(ROOT/'quality_inputs/SEMANTIC_CONTRACT.json', semantic)
for name in ('TRUTH.json','INPUT_BINDING.json','SOURCE_BINDING.json','REFERENCE_REPLAY.json'):
    src = BATCH/'scoring'/name
    raw = src.read_bytes()
    rel = src.relative_to(WT).as_posix()
    assert raw == subprocess.check_output(['git','-C',str(WT),'show',COMMIT+':'+rel])
    out = ROOT/'quality_inputs'/name
    with out.open('xb') as f:
        f.write(raw)
    pins.append({'path': str(src), 'sha256': sha(raw), 'bytes': len(raw)})
save(ROOT/'quality_inputs/PROVENANCE.json', {
    'implementation_commit': COMMIT,
    'public_path': str(PUBLIC),
    'public_INDEX_sha256': EXPECTED_INDEX,
    'public_file_count': len(pins)-4,
    'answer_count': 9,
    'original_contract_sha256': sha(contract_path.read_bytes()),
    'omitted_metadata_keys': sorted(omitted),
    'semantic_fields': 17,
    'files': pins,
    'private_map_or_raw_cost_read': False,
    'runtime_calls': 0,
})
print(json.dumps({'public_files':len(pins)-4,'answers':9,'semantic_fields':17,'passed':True}))
