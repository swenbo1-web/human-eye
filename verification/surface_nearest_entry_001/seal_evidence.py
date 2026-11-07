"""Package redundant frozen bytes and index reviewable evidence, stdlib only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUN=HERE/'qa_prepare/run_01'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(RUN/'PLAN.json')
archive=RUN/'FROZEN_SOURCE_AND_FIXTURE_BYTES.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as output:
    for row in plan['product_manifest']:
        raw=(Path(plan['source_root'])/row['path']).read_bytes()
        assert sha(raw)==row['sha256']
        output.writestr('product/'+row['path'],raw)
    helper=Path(plan['helper']).read_bytes()
    asset=(RUN/'owned/input.blend').read_bytes()
    assert sha(helper)==plan['helper_sha256'] and sha(asset)==plan['asset_sha256']
    output.writestr('fixture/visual004_native.py',helper)
    output.writestr('fixture/input.blend',asset)
    output.writestr('PRODUCT_MANIFEST.json',json.dumps(plan['product_manifest'],indent=2)+'\n')
with zipfile.ZipFile(archive) as packaged:
    for row in plan['product_manifest']:
        assert sha(packaged.read('product/'+row['path']))==row['sha256']
    assert sha(packaged.read('fixture/input.blend'))==plan['asset_sha256']

excluded_prefixes=('offline_run_01/engine/','offline_run_02/engine/',
    'offline_run_01/tmp/','offline_run_02/tmp/','qa_prepare/run_01/sources/')
excluded_exact={'EVIDENCE_INDEX.json','qa_prepare/run_01/owned/input.blend'}
members=[]
for path in sorted(HERE.rglob('*')):
    if not path.is_file():continue
    relative=path.relative_to(HERE).as_posix()
    if relative in excluded_exact or relative.startswith(excluded_prefixes) or '__pycache__' in path.parts:continue
    raw=path.read_bytes()
    members.append(dict(path=relative,bytes=len(raw),sha256=sha(raw)))
now=datetime.now(timezone.utc)
index=dict(task='SURFACE-NEAREST-ENTRY-001',candidate_commit=plan['candidate_commit'],
    source_sha256=plan['source_sha256'],source_count=131,members=members,
    member_count=len(members),member_bytes=sum(row['bytes'] for row in members),
    indexed_utc=now.isoformat(),host_turn_id='01a1b6ae-5812-7a61-a8a3-06581600e552',
    host_turn_started_epoch_seconds=1794066241,
    turn_elapsed_through_index_ms=round((now.timestamp()-1794066241)*1000),
    final_host_turn_completion='read completedAt after delivery for the full final turn; indexed elapsed is not a final duration',
    excluded_redundant_disk_prefixes=list(excluded_prefixes),excluded_exact=sorted(excluded_exact),
    redundant_bytes_authority='offline EXECUTED_BYTES.zip and QA FROZEN_SOURCE_AND_FIXTURE_BYTES.zip preserve exact excluded source/asset bytes',
    self_index_scope='index excludes itself; its SHA256 is reported in delivery')
(HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
for row in members:
    raw=(HERE/row['path']).read_bytes()
    assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
print(json.dumps(dict(member_count=len(members),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'EVIDENCE_INDEX.json').read_bytes()),elapsed_through_index_ms=index['turn_elapsed_through_index_ms'])))
if '--stage' in sys.argv:
    import subprocess
    paths=[str(HERE/row['path']) for row in members]+[str(HERE/'EVIDENCE_INDEX.json')]
    for start in range(0,len(paths),40):
        subprocess.run(['git','add','-f','--',*paths[start:start+40]],cwd=ROOT,check=True)
