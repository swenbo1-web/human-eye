"""Seal only this preparation evidence; no consumer or product execution."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(HERE/'PLAN.json')
assert load(HERE/'FINAL_PREP_CHECKS.json')['passed']
assert not (HERE/'actual_01').exists()
excluded=('entry_check/app_schema/','entry_check/desktop_schema/')
rows=[]
for file in sorted(HERE.rglob('*')):
    if not file.is_file():continue
    name=file.relative_to(HERE).as_posix()
    if name=='EVIDENCE_INDEX.json' or name.startswith(excluded) or '__pycache__' in file.parts:continue
    raw=file.read_bytes();rows.append(dict(path=name,bytes=len(raw),sha256=sha(raw)))
now=datetime.now(timezone.utc)
index=dict(cycle_id='CONSUMPTION-RUN-PREP-001',indexed_utc=now.isoformat(),
    source_commit=plan['source_commit'],source_count=131,source_sha256=plan['source_sha256'],
    plan_sha256=sha((HERE/'PLAN.json').read_bytes()),member_count=len(rows),member_bytes=sum(r['bytes'] for r in rows),members=rows,
    runtime_components=plan['runtime_components'],excluded_redundant_schema_directories=list(excluded),
    schema_archive='entry_check/GENERATED_SCHEMAS.zip preserves all884 generated schema members',
    host_turn_id='01a1b8b6-7e09-7270-bc26-edacddb32ec6',host_turn_started_epoch_seconds=1794100330,
    elapsed_through_seal_ms=round((now.timestamp()-1794100330)*1000),
    complete_turn_cost='read host completedAt after delivery; through-seal duration is not final turn duration',
    activity=dict(model_answers=0,Blender_sessions=0,native_RPC=0,product_RPC=0,model_API_calls=0,product_imports=0),
    execution_ready=False,self_index='excluded; SHA reported in completion callback')
(HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
for row in rows:
    raw=(HERE/row['path']).read_bytes();assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
print(json.dumps(dict(member_count=len(rows),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'EVIDENCE_INDEX.json').read_bytes()),plan_sha256=index['plan_sha256'],elapsed_through_seal_ms=index['elapsed_through_seal_ms'])))
if '--stage' in sys.argv:
    names=[str(HERE/r['path']) for r in rows]+[str(HERE/'EVIDENCE_INDEX.json')]
    for start in range(0,len(names),40):subprocess.run(['git','add','-f','--',*names[start:start+40]],cwd=ROOT,check=True)
