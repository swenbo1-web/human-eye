"""Record the one authorized description candidate and protected evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
BASE='bfcde7e739d61049271cc715e448fe849b10ef3e'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT)
assert git('rev-parse','HEAD').decode().strip()==BASE
assert set(git('diff','--name-only').decode().splitlines())=={'human_eye_plugin/live_spatial_mcp.py'}
assert not (OUT/'TASK_START.json').exists()
save(OUT/'TASK_START.json',dict(cycle_id='TOOL-AFFORDANCE-001',baseline_HEAD=BASE,
    turn_id='01a1bc43-4790-79b3-8ec9-da9cd69b5555',receipt_epoch_seconds=1794159888,
    implementation_deadline_epoch_seconds=1794161388,one_candidate=True,
    baseline_source_sha256='ec3ac8c9dd83137e1d6cb5371fe4c2bc15ac56d34aafcb6933e8f76c07e897ae',
    permitted_product_path='human_eye_plugin/live_spatial_mcp.py',model_calls=0,Blender_sessions=0,field_RPC=0,performance_samples=0))
for p,name,expected in (
    ('D:/hefe/verification/fixes/20261108_complex_reentry/TOOL_AFFORDANCE_ASSIGNMENT.md','ASSIGNMENT.md','09dd96e0e30bbbf06ae58789a9ba197effc2367931fae0bb06c45483abcc5b10'),
    ('D:/hefe/verification/fixes/20261108_complex_reentry/COMPLEX001_REVIEW.md','ROOT_REVIEW.md',None)):
    p=Path(p)
    if expected:assert sha(p)==expected
    (OUT/name).write_bytes(p.read_bytes())
product='human_eye_plugin/live_spatial_mcp.py'
(OUT/'live_spatial_mcp.before.py').write_bytes(git('cat-file','blob',BASE+':'+product))
(OUT/'live_spatial_mcp.candidate.py').write_bytes((ROOT/product).read_bytes())
(OUT/'DESCRIPTION_SOURCE.diff').write_bytes(git('diff','--no-ext-diff','--',product))
prior=json.loads((ROOT/'verification/zero_witness_reuse_001/PROTECTED_BEFORE.json').read_bytes())['files']
paths=[r['path'] for r in prior]+['verification/zero_witness_reuse_001/'+p for p in ('REPORT.md','EVIDENCE_INDEX.json','ENTRY_AUDIT.json','GATES.json')]
save(OUT/'PROTECTED_BEFORE.json',dict(files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths]))
print(json.dumps(dict(baseline_HEAD=BASE,protected_count=len(paths),candidate_sha256=sha(ROOT/product))))
