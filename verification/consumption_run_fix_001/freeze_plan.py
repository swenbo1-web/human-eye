"""Freeze the minimal tester delta; reference immutable54b2622 materials."""
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];BASE=ROOT/'verification/consumption_run_001'
sha=lambda b:hashlib.sha256(b).hexdigest()
commit='54b2622526e36779cf0f1911c5db2b75d4797b7f'
plan=json.loads(subprocess.check_output(['git','show',commit+':verification/consumption_run_001/PLAN.json'],cwd=ROOT))
plan.update(cycle_id='CONSUMPTION-RUN-FIX-001',execution_ready=False,execution_blockers=[],
    prepared_utc=datetime.now(timezone.utc).isoformat(),baseline_commit=commit,
    diagnostic_contract='nonblind numeric engineering diagnosis; actual schema/Pro/images/context observed only in original8slots; contamination prevents engine attribution; no cleanN/visual/full-product win claim',
    output_contract='same1MiB value: MCP prepublication admission; builtin postdelivery measurement stops observed overflow and retains consumed cost; no new platform or hardprepublication claim',
    window_contract='explicit batch expiry ->sameperf deadline; each slot requires180s+60s reserve,180original answer never renewed; chain min600/window; no newslot after insufficienttime',
    cleanup_contract='owned parent and registeredMCP tree evidence separate; unresolved cleanup stops later slots asnot_run; full arbitraryPython descendants not sandboxed')
plan['codex']['settings'].update(sandbox_mode='workspace-write',approval_policy='never')
components=[]
local={'runner.py','bridge.py','he_bootstrap.py','freeze_plan.py','tests_runner.py','tests_bridge.py'}
for row in plan['runtime_components']:
    name=row['path'];path=HERE/name if name in local else BASE/name
    assert path.is_file()
    components.append(dict(path=name if name in local else '../consumption_run_001/'+name,sha256=sha(path.read_bytes())))
for name in ('tests_images.py','tests_fix_runner.py','run_checks.py'):
    components.append(dict(path=name,sha256=sha((HERE/name).read_bytes())))
plan['runtime_components']=components
plan['source_documents'] += [dict(path=str(Path('D:/hefe/verification/fixes/20261107_nearest_contract')/name),
    sha256=sha((Path('D:/hefe/verification/fixes/20261107_nearest_contract')/name).read_bytes()))
    for name in ('CONSUMPTION_RUNNER_REVIEW.md','CONSUMPTION_RUN_FIX_ASSIGNMENT.md')]
(HERE/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
diff=[]
for name in ('runner.py','bridge.py','he_bootstrap.py'):
    old=subprocess.check_output(['git','show',commit+':verification/consumption_run_001/'+name],cwd=ROOT).decode('utf8')
    new=(HERE/name).read_text('utf8')
    diff.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='54b2622/'+name,tofile='candidate/'+name))
(HERE/'MINIMAL.diff').write_text(''.join(diff),encoding='utf8')
print(json.dumps(dict(plan_sha256=sha((HERE/'PLAN.json').read_bytes()),components=len(components),execution_ready=False)))
