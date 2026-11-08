"""Fix the single tested candidate; reference the accepted baseline in place."""
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
OLD = ROOT / 'verification/closed_solid_read_001'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
save = lambda p,v: p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
git = lambda *args, data=None: subprocess.check_output(['git',*args],cwd=ROOT,input=data)
start=json.loads((OUT/'TASK_START.json').read_bytes())
assert git('rev-parse','HEAD').decode().strip()==start['starting_HEAD']
assert not git('diff','--cached','--name-only')
proof=OUT/'offline_01/RESULTS.json'
result=json.loads(proof.read_bytes()); assert result['passed']
identity=json.loads((OUT/'offline_01/EXECUTION_IDENTITY.json').read_bytes())
assert identity['guard_verify_loaded'] and result['runtime_source_sha256']==identity['runtime_source_sha256']
manifest=identity['manifest']
for r in manifest:
    assert sha(ROOT/r['path'])==sha(OUT/'offline_01/engine'/r['path'])==r['sha256']
paths=['human_eye_plugin/'+p for p in ('surface_geometry.py','surface_proximity.py','task_query.py')]
assert set(git('diff','--name-only').decode().splitlines())==set(paths)
git('-c','core.autocrlf=false','add','--pathspec-from-file=-','--pathspec-file-nul',data=b''.join(p.encode()+b'\0' for p in paths))
for p in paths: assert git('show',':'+p)==(ROOT/p).read_bytes()
git('commit','--quiet','-m','Reuse exact same-query boundary witness for zero surface distance')
candidate=git('rev-parse','HEAD').decode().strip()
base=json.loads((OLD/'SOURCE_FREEZE.json').read_bytes())
for arm in ('baseline','candidate'):
    frozen=dict(base)
    frozen.update(baseline_HEAD=start['starting_HEAD'],implementation_commit=candidate,
        implementation_deadline_epoch_seconds=start['implementation_deadline_epoch_seconds'],
        inputs_root=str((OLD/'inputs').resolve()),arm=arm)
    if arm=='candidate':
        frozen.update(candidate_commit=candidate,source_sha256=result['runtime_source_sha256'],
            product_manifest=manifest,source_root=str((OUT/'offline_01/engine').resolve()),
            offline_proof=dict(path=str(proof),sha256=sha(proof)),
            identity_proof=dict(path=str(OUT/'offline_01/EXECUTION_IDENTITY.json'),sha256=sha(OUT/'offline_01/EXECUTION_IDENTITY.json')))
    for r in frozen['product_manifest']:
        assert git('cat-file','blob',frozen['candidate_commit']+':'+r['path'])==(Path(frozen['source_root'])/r['path']).read_bytes()
    save(OUT/('SOURCE_FREEZE_'+arm.upper()+'.json'),frozen)
print(json.dumps(dict(candidate_commit=candidate,source_sha256=result['runtime_source_sha256'],source_count=len(manifest),baseline_reused=str(base['source_root']))))
