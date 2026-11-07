"""Measure the sole controller subprocess, including its interpreter startup."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

folder=Path(__file__).resolve().parent
out=folder/'run_01'
freeze=json.loads((out/'FREEZE.json').read_bytes())
for row in freeze['controllers']:
    assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256']
assert not (out/'OUTER_STARTED.json').exists(), 'no_second_command_or_retry'
command=[sys.executable,'-I',str(folder/'controller.py'),'run']
record=dict(argv=command,cwd=str(folder.parents[2]),started_utc=datetime.now(timezone.utc).isoformat())
begun=time.perf_counter_ns(); record['started_ns']=begun
(out/'OUTER_STARTED.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
with (out/'CONTROLLER_STDOUT.bin').open('wb') as stdout,(out/'CONTROLLER_STDERR.bin').open('wb') as stderr:
    process=subprocess.Popen(command,cwd=folder.parents[2],stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        record['pid']=process.pid
        record['exit_code']=process.wait(timeout=660)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=10); record['exit_code']=process.returncode; record['outer_timeout']=True
record['elapsed_ns']=time.perf_counter_ns()-begun
record['ended_utc']=datetime.now(timezone.utc).isoformat()
record['stdout_bytes']=(out/'CONTROLLER_STDOUT.bin').stat().st_size
record['stderr_bytes']=(out/'CONTROLLER_STDERR.bin').stat().st_size
(out/'OUTER_COMMAND.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2))
raise SystemExit(record['exit_code'])
