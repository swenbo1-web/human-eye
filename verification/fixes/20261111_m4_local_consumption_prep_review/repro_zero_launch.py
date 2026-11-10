"""Root reproduction: synthetic formally started batch with zero CLI launches."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
SCRIPT = WT/'verification/m4_local_relation_consumption_001/quality_handoff/pack_quality.py'
raw = SCRIPT.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '90f07a6b78457bb7ca9a5b93fbb7d78bf3439b547cfb21ff4fbae0b0c76ab0d4'
module = types.ModuleType('root_zero_launch_packager')
module.__file__ = str(SCRIPT)
exec(compile(raw,str(SCRIPT),'exec',dont_inherit=True),module.__dict__)
source = ROOT/'synthetic_replay/all_nine/e'
destination = ROOT/'zero_launch/e'
destination.mkdir(parents=True,exist_ok=False)
for name in ('PLAN.json','FREEZE.json','private/ANON_MAP.json','input/INITIAL.png','input/PROMPT.txt'):
    p=destination/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((source/name).read_bytes())
plan_raw=(destination/'PLAN.json').read_bytes();plan=json.loads(plan_raw)
digest=hashlib.sha256(plan_raw).hexdigest()
records={
    'SYNTHETIC_SCOPE.json':dict(synthetic=True,real_processes=0,real_consumers=0),
    'GO.json':dict(synthetic=True,task=module.CYCLE,authorized=True,max_consumers=9,plan_sha256=digest),
    'STARTED.json':dict(synthetic=True,started_ns=1,max_consumers=9,plan_sha256=digest),
    'RUN_RESULT.json':dict(synthetic=True,records=[dict(plan['sequence'][0],consumer=None,finish=None,
        errors=[dict(type='SyntheticActorStartupFailure',message='No actual process was attempted')],
        cell_started_ns=2,cell_ended_ns=3,full_cell_wall_ns=1,within_570s=True)],
        stop='owner_backend_close_unconfirmed',started_cells=1,maximum_consumers=9,
        all_planned_dispatched=False,no_replacements=True,batch_started_ns=1,batch_ended_ns=4,batch_wall_ns=3),
}
for name,value in records.items():
    (destination/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
module.EVAL=destination;module.HERE=destination/'q';module.HERE.mkdir()
attempts=[]
def forbidden(*args,**kwargs):
    attempts.append('external_process_or_network');raise AssertionError(attempts[-1])
sys.argv=['synthetic-only-packager','h']
exception=None
with patch.object(subprocess,'Popen',side_effect=forbidden),patch.object(socket,'socket',side_effect=forbidden):
    try:
        with contextlib.redirect_stdout(io.StringIO()):module.main()
    except AssertionError as exc:
        exception=str(exc)
expected='at least one recorded consumer launcher is required; preparation is not a quality run'
assert exception==expected,(exception,expected)
assert not attempts
receipt=dict(reproduced=True,synthetic=True,packager_sha256=hashlib.sha256(raw).hexdigest(),
    exception=exception,entered_cells=1,launched_consumers=0,not_run_tail=8,
    synthetic_GO_and_STARTED_present=True,terminal_batch_record_present=True,
    public_quality_index_created=(destination/'q/h/public/INDEX.json').exists(),
    external_attempts=attempts,product_calls=0,model_consumers=0,Blender_sessions=0)
(ROOT/'ZERO_LAUNCH_REPRO.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
print(json.dumps(receipt))
