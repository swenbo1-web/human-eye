"""Run the unchanged installed thin CLI and retain actual process delivery."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import time
import uuid

def main():
    arguments = sys.argv[1:]
    if not arguments or arguments[0] not in ('native', 'observe') or '--workspace' not in arguments:
        raise ValueError('Use native or observe with the assigned workspace')
    workspace = Path(arguments[arguments.index('--workspace') + 1]).resolve()
    root = Path(__file__).resolve().parents[1]
    if not workspace.is_relative_to(root / 'runs') or not workspace.is_dir():
        raise ValueError('Assigned existing run workspace required')
    folder = workspace / 'cli_process_calls' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    tool = Path(sysconfig.get_path('purelib')) / 'verification/perf000_scene_tool.py'
    command = [sys.executable, '-I', '-B', str(tool), *arguments]
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter_ns()
    try:
        result = subprocess.run(command, capture_output=True, timeout=40)
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
        error = None
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, exit_code = exc.stdout or b'', exc.stderr or b'', 124
        error = 'CLI process timeout, no retry'
    elapsed = time.perf_counter_ns() - started
    (folder / 'stdout.bin').write_bytes(stdout)
    (folder / 'stderr.bin').write_bytes(stderr)
    record = dict(argv=command, started_utc=started_utc,
        finished_utc=datetime.now(timezone.utc).isoformat(),
        cli_process_wall_ns=elapsed, exit_code=exit_code,
        stdout_bytes=len(stdout), stderr_bytes=len(stderr), error=error,
        automatic_retries=0, scope='subprocess.run startup through exit/reap; recording and wrapper delivery excluded')
    (folder / 'PROCESS.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return exit_code

if __name__ == '__main__':
    raise SystemExit(main())
