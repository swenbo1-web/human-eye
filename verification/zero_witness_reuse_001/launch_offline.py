"""Record the single bounded exact-byte directed test invocation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
assert not (OUT/'OFFLINE_INVOCATION.json').exists()
command=[sys.executable,'-B',str(OUT/'run_offline.py'),'offline_01']
record=dict(argv=command,started_utc=datetime.now(timezone.utc).isoformat(),started_ns=time.perf_counter_ns())
with (OUT/'OFFLINE_STDOUT.raw.bin').open('wb') as stdout, (OUT/'OFFLINE_STDERR.raw.bin').open('wb') as stderr:
    process=subprocess.Popen(command,cwd=OUT.parents[1],stdout=stdout,stderr=stderr,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    record['pid']=process.pid
    record['exit_code']=process.wait(timeout=180)
record.update(ended_utc=datetime.now(timezone.utc).isoformat(),ended_ns=time.perf_counter_ns(),process_reaped=process.poll() is not None)
record['wall_ns']=record['ended_ns']-record['started_ns']
(OUT/'OFFLINE_INVOCATION.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record))
raise SystemExit(record['exit_code'])
