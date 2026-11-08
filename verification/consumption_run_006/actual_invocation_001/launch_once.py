"""Single authorized006 invocation with outer owned-process/wall evidence."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;FINAL=HERE.parent;ROOT=FINAL.parents[1]
approval_path=Path('D:/hefe/verification/fixes/20261107_nearest_contract/CONSUMPTION_RUN_006_APPROVAL.json')
approval=json.loads(approval_path.read_bytes())
assert hashlib.sha256((FINAL/'PLAN.json').read_bytes()).hexdigest()==approval['plan_sha256']
assert not (HERE/'STARTED.json').exists() and not (FINAL/'actual_01').exists()
command=[sys.executable,'-I',str(FINAL/'runner.py'),'--approval',str(approval_path)]
record=dict(argv=command,cwd=str(ROOT),started_utc=datetime.now(timezone.utc).isoformat(),
    started_ns=time.perf_counter_ns(),approval_sha256=hashlib.sha256(approval_path.read_bytes()).hexdigest(),
    plan_sha256=approval['plan_sha256'],retries=0)
(HERE/'STARTED.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
with (HERE/'CONTROLLER_STDOUT.raw.bin').open('wb') as out,(HERE/'CONTROLLER_STDERR.raw.bin').open('wb') as err:
    process=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    record['pid']=process.pid
    (HERE/'OWNED_PROCESS.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    expiry=datetime.fromisoformat(approval['expires_utc'].replace('Z','+00:00'))
    try:record['exit_code']=process.wait(timeout=max(.01,(expiry-datetime.now(timezone.utc)).total_seconds()))
    except subprocess.TimeoutExpired:
        record['outer_window_timeout']=True
        try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        except (OSError,subprocess.TimeoutExpired) as error:record['tree_stop_error']=str(error)
        if process.poll() is None:process.kill()
        process.wait(timeout=5);record['exit_code']=process.returncode
record['finished_ns']=time.perf_counter_ns();record['ended_utc']=datetime.now(timezone.utc).isoformat()
record['wall_ns']=record['finished_ns']-record['started_ns'];record['process_reaped']=process.poll() is not None
record['stdout_bytes']=(HERE/'CONTROLLER_STDOUT.raw.bin').stat().st_size
record['stderr_bytes']=(HERE/'CONTROLLER_STDERR.raw.bin').stat().st_size
(HERE/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2))
raise SystemExit(record['exit_code'])
