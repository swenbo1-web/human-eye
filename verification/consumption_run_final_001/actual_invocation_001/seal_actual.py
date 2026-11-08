"""Seal the completed single attempt; no runner/consumer/host invocation."""
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

HERE=Path(__file__).resolve().parent;FINAL=HERE.parent;ROOT=FINAL.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(FINAL/'PLAN.json');result=load(FINAL/'actual_01/RESULTS.json');outer=load(HERE/'RESULT.json')
assert len(result['cells'])==result['scheduled']==8
assert [s['status'] for s in result['cells']]==['error']+['not_run']*7
assert outer['process_reaped'] and outer['exit_code']==0
assert result['cells'][0]['consumer']['exit_code']==1 and result['cells'][0]['consumer']['public_events']==[]
assert result['cells'][0]['consumer']['registered_tree_cleanup']['confirmed'] is False
for row in plan['runtime_components']:assert sha((FINAL/row['path']).read_bytes())==row['sha256'],row['path']
assert sha((FINAL/'PLAN.json').read_bytes())=='cb78e4f754c7988d26296bbce7be34d8456e41329d11cd51e718cad1e4b49196'
oldpaths=[r['path'] for r in plan['product_manifest']]
for folder in ('consumption_run_001','consumption_run_fix_001','consumption_run_final_001'):
    directory=ROOT/'verification'/folder;index=load(directory/'EVIDENCE_INDEX.json');prefix=directory.relative_to(ROOT).as_posix()+'/'
    oldpaths += [prefix+r['path'] for r in index['members']]+[prefix+'EVIDENCE_INDEX.json']
raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=''.join('c4b55647bedc259d2adda8abcba8c2d195cd6f62:'+p+'\n' for p in oldpaths).encode())
stream=io.BytesIO(raw)
for path in oldpaths:
    header=stream.readline().decode().split();assert header[1]=='blob'
    b=stream.read(int(header[2]));assert stream.read(1)==b'\n' and b==(ROOT/path).read_bytes(),path
assert stream.read()==b'' and len(oldpaths)==286
neutral=Path(plan['neutral_run_root']);members=[]
with zipfile.ZipFile(HERE/'NEUTRAL_SESSION_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(neutral.rglob('*')):
        if not file.is_file():continue
        b=file.read_bytes();name=file.relative_to(neutral).as_posix();archive.writestr(name,b)
        members.append(dict(path=name,original_path=str(file),bytes=len(b),sha256=sha(b)))
(HERE/'NEUTRAL_SOURCE_INDEX.json').write_text(json.dumps(dict(root=str(neutral),members=members,PNG_files=len(list(neutral.rglob('*.png')))),indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(HERE/'NEUTRAL_SESSION_BYTES.zip') as archive:
    for row in members:assert sha(archive.read(row['path']))==row['sha256']
paths=list((FINAL/'actual_01').rglob('*'))+list(HERE.rglob('*'));rows=[]
for file in sorted(paths):
    if not file.is_file() or '__pycache__' in file.parts:continue
    name=file.relative_to(FINAL).as_posix()
    if name=='actual_invocation_001/ACTUAL_EVIDENCE_INDEX.json':continue
    b=file.read_bytes();rows.append(dict(path=name,bytes=len(b),sha256=sha(b)))
index=dict(cycle_id='CONSUMPTION-RUN-001',indexed_utc=datetime.now(timezone.utc).isoformat(),candidate_commit='c4b55647bedc259d2adda8abcba8c2d195cd6f62',
    plan_sha256=sha((FINAL/'PLAN.json').read_bytes()),product_source_sha256=plan['source_sha256'],old_blobs_unchanged=286,
    scheduled_slots=8,cell_states=[s['status'] for s in result['cells']],CLI_process_attempts=1,returned_answers=0,
    native_sessions=1,physical_RPC=1,execute_code_RPC=0,observed_public_tool_events=0,
    registered_tree_confirmed=False,provider_requests=None,usage=None,fees=None,quality_scoring=None,retries=0,
    members=rows,member_count=len(rows),member_bytes=sum(r['bytes'] for r in rows),self_index='excluded;SHAreportedindelivery',
    frozen_result_policy='original files unmodified; observations missing remain missing; no replay or score')
(HERE/'ACTUAL_EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(member_count=len(rows),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'ACTUAL_EVIDENCE_INDEX.json').read_bytes()),old_blobs_unchanged=286,scheduled=8,returned_answers=0)))
if '--stage' in sys.argv:
    files=[str(FINAL/r['path']) for r in rows]+[str(HERE/'ACTUAL_EVIDENCE_INDEX.json')]
    subprocess.run(['git','add','-f','--',*files],cwd=ROOT,check=True)
