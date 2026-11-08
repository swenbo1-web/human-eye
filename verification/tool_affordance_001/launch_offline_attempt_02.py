"""Run the original-source schema proof once, retaining owned process receipts."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
prefix='OFFLINE_02' if len(sys.argv)==2 and sys.argv[1]=='corrected' else 'OFFLINE'
assert not (OUT/(prefix+'_INVOCATION.json')).exists()
runner=OUT/'verify_offline.py'
bootstrap='import hashlib,sys; p=sys.argv[1]; raw=open(p,"rb").read(); scope={"__name__":"_tool_affordance_verification","__file__":p}; exec(compile(raw,"offline-runner:"+hashlib.sha256(raw).hexdigest(),"exec"),scope)'
command=[sys.executable,'-B','-c',bootstrap,str(runner)]
record=dict(argv=command,runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),
    started_utc=datetime.now(timezone.utc).isoformat(),started_ns=time.perf_counter_ns())
with (OUT/(prefix+'_STDOUT.raw.bin')).open('wb') as stdout,(OUT/(prefix+'_STDERR.raw.bin')).open('wb') as stderr:
    process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    record['pid']=process.pid;record['exit_code']=process.wait(timeout=120)
record.update(ended_utc=datetime.now(timezone.utc).isoformat(),ended_ns=time.perf_counter_ns(),process_reaped=process.poll() is not None)
record['wall_ns']=record['ended_ns']-record['started_ns']
(OUT/(prefix+'_INVOCATION.json')).write_bytes((json.dumps(record,indent=2)+'\n').encode())
print(json.dumps(record))
raise SystemExit(record['exit_code'])
