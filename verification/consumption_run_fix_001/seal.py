"""Verify immutable baseline/new checks and seal only this fix directory."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];BASE=ROOT/'verification/consumption_run_001'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(HERE/'PLAN.json');tests=load(HERE/'check_02/RESULTS.json');first=load(HERE/'check_01/RESULTS.json')
assert plan['execution_ready'] is False
assert tests['passed'] and tests['methods']==32 and tests['candidate_unchanged']
assert first['passed'] and first['methods']==31
for row in plan['runtime_components']:assert sha((HERE/row['path']).read_bytes())==row['sha256'],row['path']
old=load(BASE/'EVIDENCE_INDEX.json');oldplan=load(BASE/'PLAN.json')
baseline=['verification/consumption_run_001/'+r['path'] for r in old['members']]+['verification/consumption_run_001/EVIDENCE_INDEX.json']
baseline += [r['path'] for r in oldplan['product_manifest']]
for name in baseline:
    assert (ROOT/name).read_bytes()==subprocess.check_output(['git','show','54b2622526e36779cf0f1911c5db2b75d4797b7f:'+name],cwd=ROOT),name
candidate=[dict(path=n,sha256=sha((HERE/n).read_bytes())) for n in ('runner.py','bridge.py','he_bootstrap.py')]
record=dict(cycle_id='CONSUMPTION-RUN-FIX-001',baseline_commit='54b2622526e36779cf0f1911c5db2b75d4797b7f',
    candidate=candidate,candidate_sha256=sha(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()),
    plan_sha256=sha((HERE/'PLAN.json').read_bytes()),product_source_sha256=plan['source_sha256'],
    baseline_verified_blobs=len(baseline),final_candidate_methods=32,current_method_executions=63,current_failures=0,
    historical76='author claim; root saw6 complete outputs totalling51 method executions; not rerun or independently upgraded here',
    activity=dict(consumers=0,scorers=0,Blender=0,MCP_services=0,real_RPC=0,model_API=0,product_imports=0),execution_ready=False)
(HERE/'CANDIDATE.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
rows=[]
for file in sorted(HERE.rglob('*')):
    if not file.is_file() or '__pycache__' in file.parts:continue
    name=file.relative_to(HERE).as_posix()
    if name=='EVIDENCE_INDEX.json':continue
    raw=file.read_bytes();rows.append(dict(path=name,sha256=sha(raw),bytes=len(raw)))
now=datetime.now(timezone.utc)
index=dict(cycle_id='CONSUMPTION-RUN-FIX-001',indexed_utc=now.isoformat(),
    members=rows,member_count=len(rows),member_bytes=sum(r['bytes'] for r in rows),candidate=record,
    self_index='excluded; delivery reports SHA',baseline_policy='old102evidence+131product blobs unchanged; referenced not copied',
    host_turn_id='01a1b8e6-aad3-7fa2-95ba-f9a3d8372353',host_turn_started_epoch_seconds=1794103487,
    elapsed_through_seal_ms=round((now.timestamp()-1794103487)*1000),
    final_turn_duration='read completedAt after delivery; through-seal duration is not final whole-turn cost')
(HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(member_count=len(rows),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'EVIDENCE_INDEX.json').read_bytes()),
    plan_sha256=record['plan_sha256'],candidate_sha256=record['candidate_sha256'],baseline_verified_blobs=len(baseline))))
if '--stage' in sys.argv:
    names=[str(HERE/r['path']) for r in rows]+[str(HERE/'EVIDENCE_INDEX.json')]
    subprocess.run(['git','add','-f','--',*names],cwd=ROOT,check=True)
