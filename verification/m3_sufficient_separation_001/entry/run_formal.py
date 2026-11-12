"""Record the one authorized installed four-business MCP execution."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYTHON = 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
COMMAND = [PYTHON, '-I', '-B', '-X', 'utf8', str(HERE / 'run_entry.py'),
           '--output', str(HERE / 'run_01'), '--commit', 'e836e03f4b3821f869c72ac3e50df5204f28b50f',
           '--source-sha256', '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390', '--run']


def main():
    assert not (HERE / 'FORMAL_PROCESS.json').exists()
    assert not (HERE / 'FORMAL_STARTED.json').exists()
    started = time.perf_counter_ns()
    record = {'command': COMMAND, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'timeout_s': 600, 'pid': None, 'exit_code': None, 'timed_out': False}
    process = subprocess.Popen(COMMAND, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    record['pid'] = process.pid
    try:
        output, error = process.communicate(timeout=600)
    except subprocess.TimeoutExpired:
        record['timed_out'] = True
        stop = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                              timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['owned_tree_stop_returncode'] = stop.returncode
        output, error = process.communicate(timeout=15)
    record.update(exit_code=process.returncode, elapsed_ns=time.perf_counter_ns() - started,
                  ended_utc=datetime.now(timezone.utc).isoformat())
    (HERE / 'FORMAL.stdout.txt').write_bytes(output)
    (HERE / 'FORMAL.stderr.txt').write_bytes(error)
    with (HERE / 'FORMAL_PROCESS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(record))
    return 0 if process.returncode == 0 and not record['timed_out'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
