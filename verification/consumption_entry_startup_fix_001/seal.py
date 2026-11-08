"""Seal this offline-only small startup fix; no model/backend or CLI parse."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
plan=load(HERE/'PLAN.json');tests=load(HERE/'check_01/RESULTS.json');parses=load(HERE/'config_parse_001/RESULTS.json')
assert plan['execution_ready'] is False and tests['passed'] and tests['methods']==6
assert len(parses['cases'])==2 and all(c['exit_code']==0 for c in parses['cases'])
for row in plan['runtime_components']:assert sha((HERE/row['path']).read_bytes())==row['sha256'],row['path']
assert len(plan['runtime_components'])==17
commit='2195ac8110e4044b1c3ff904ca9b4cde974c11b9'
old=load(ROOT/'verification/consumption_run_final_001/PLAN.json')
removed=set(load(HERE/'REMOVED_DISABLED_ONLY.json'))
settings=dict(old['codex']['settings'])
for key in removed:assert settings.pop(key) is False
assert plan['codex']['settings']==settings and len(removed)==4
for key in ('limits','cells','source_sha256','source_commit','product_manifest','materials_source_commit','neutral_run_root'):
    assert plan[key]==old[key],key
for name in ('bridge.py','he_bootstrap.py'):
    assert (HERE/name).read_bytes()==subprocess.check_output(['git','show',commit+':verification/consumption_run_final_001/'+name],cwd=ROOT)
old_diff=subprocess.check_output(['git','diff','--name-only',commit,'--','human_eye_plugin','human_eye_module1_operators',
    'verification/consumption_run_001','verification/consumption_run_fix_001','verification/consumption_run_final_001'],cwd=ROOT,text=True)
assert not old_diff.strip(),'old sealed content changed'
result_path='verification/consumption_run_final_001/actual_01/RESULTS.json'
assert (ROOT/result_path).read_bytes()==subprocess.check_output(['git','show',commit+':'+result_path],cwd=ROOT)
runtime=[dict(path=n,sha256=sha((HERE/n).read_bytes())) for n in ('runner.py','bridge.py','he_bootstrap.py')]
proof=dict(baseline_commit=commit,runtime=runtime,components_checked=17,old_sealed_git_diff=[],old_batch_result_unchanged=True,
    old_batch_permanent_states=['error']+['not_run']*7,plan_sha256=sha((HERE/'PLAN.json').read_bytes()),
    product_source_sha256=plan['source_sha256'],mock_methods=6,mock_failures=0,CLI_config_parses=2,
    parse_exits=[c['exit_code'] for c in parses['cases']],root_cause_scope='disabled-only transport defect proven; old71B body unavailable, not unique-cause recovery',
    actual_exec_consumers=0,Blender=0,MCP_services=0,RPC=0,model_API=0,execution_ready=False)
(HERE/'SOURCE_PROOF.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
rows=[]
for file in sorted(HERE.rglob('*')):
    if not file.is_file() or '__pycache__' in file.parts:continue
    name=file.relative_to(HERE).as_posix()
    if name=='EVIDENCE_INDEX.json':continue
    b=file.read_bytes();rows.append(dict(path=name,bytes=len(b),sha256=sha(b)))
index=dict(cycle_id='CONSUMPTION-ENTRY-STARTUP-FIX-001',indexed_utc=datetime.now(timezone.utc).isoformat(),
    source_proof=proof,members=rows,member_count=len(rows),member_bytes=sum(r['bytes'] for r in rows),self_index='excluded;SHAreported')
(HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(member_count=len(rows),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'EVIDENCE_INDEX.json').read_bytes()),plan_sha256=proof['plan_sha256'],runtime=runtime)))
if '--stage' in sys.argv:
    files=[str(HERE/r['path']) for r in rows]+[str(HERE/'EVIDENCE_INDEX.json')]
    subprocess.run(['git','add','-f','--',*files],cwd=ROOT,check=True)
