"""Existing outer Popen/wait logging pattern; starts the one frozen QA only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
OUT = FOLDER / 'qa_invocation_01'
assert not OUT.exists() and not (FOLDER/'qa_01/STARTED.json').exists()
OUT.mkdir()
command = [sys.executable, '-I', str(FOLDER/'qa_control.py'), 'run']
record = dict(argv=command, cwd=str(ROOT), started_utc=datetime.now(timezone.utc).isoformat(),
              started_ns=time.perf_counter_ns(), retries=0,
              plan_sha256=hashlib.sha256((FOLDER/'qa_01/PLAN.json').read_bytes()).hexdigest())
(OUT/'STARTED.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
with (OUT/'STDOUT.raw.bin').open('wb') as stdout, (OUT/'STDERR.raw.bin').open('wb') as stderr:
    process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    record['pid'] = process.pid
    (OUT/'OWNED_PROCESS.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
    try:
        record['exit_code'] = process.wait(timeout=660)
    except subprocess.TimeoutExpired:
        record['outer_timeout_unknown_no_replay'] = True
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        except (OSError, subprocess.TimeoutExpired) as error:
            record['owned_tree_stop_error'] = str(error)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        record['exit_code'] = process.returncode
record.update(ended_utc=datetime.now(timezone.utc).isoformat(), finished_ns=time.perf_counter_ns(),
              process_reaped=process.poll() is not None)
record['wall_ns'] = record['finished_ns']-record['started_ns']
record['stdout_bytes'] = (OUT/'STDOUT.raw.bin').stat().st_size
record['stderr_bytes'] = (OUT/'STDERR.raw.bin').stat().st_size
(OUT/'RESULT.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
print(json.dumps(record))
raise SystemExit(record['exit_code'])
