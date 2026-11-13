"""Per-turn thin-client boundary for one externally owned continuity episode.

The original stdio attach client owns no backend. These engineering turns use
that exact client, including initialize/list/ping and EOF, without a model.
The future real consumer uses the separately frozen CLI-resume adapter.
"""

import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / 'm4_surface_scan_compact_consumption_001/runtime/consumer_transport.py'
spec = importlib.util.spec_from_file_location('_continuity_previous_consumer', PREVIOUS)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
ATTACH_PATH = previous.ATTACH_PATH
TOOLS_BY_GROUP = previous.TOOLS_BY_GROUP
settings = previous.settings
safe_environment = previous.safe_environment
wait_bridge_closed = previous.wait_bridge_closed
read = previous.read
save = previous.save
sha = previous.sha
toml = previous.toml


def thin_turn(*, python, endpoint, folder, requests, deadline_ns):
    """Start, use and close one real stdio client, preserving the outer owner.

    Requests are the future consumer's ordinary MCP messages. No finish, pose
    operation or direct owner invocation is added. The caller owns the turn
    barrier and original episode deadline. Unknown transport is never replayed.
    """
    started = time.perf_counter_ns()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    endpoint_value = read(endpoint) if not isinstance(endpoint, dict) else dict(endpoint)
    if type(deadline_ns) is not int or not started < deadline_ns <= endpoint_value['chain_deadline_ns']:
        raise ValueError('thin_turn_original_deadline')
    if type(requests) is not list or not requests:
        raise ValueError('thin_turn_requests_required')
    request_ids = [row['id'] for row in requests if 'id' in row]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError('thin_turn_duplicate_request_id')
    endpoint_path = folder / 'ENDPOINT.json'
    save(endpoint_path, endpoint_value)
    wire = b''.join((json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode('utf8') for row in requests)
    (folder / 'TX.bin').write_bytes(wire)
    command = [str(python), '-I', '-B', '-X', 'utf8', str(ATTACH_PATH), '--endpoint', str(endpoint_path),
               '--kind', 'native', '--audit', str(folder / 'attachments')]
    record = {'started_ns': started, 'deadline_ns': deadline_ns, 'argv': command,
              'requests': requests, 'request_ids': request_ids, 'responses': [], 'error': None,
              'model_or_API_calls': 0, 'backend_lifetime': 'external owner; stdin EOF closes this client only',
              'pid': None, 'exit_code': None, 'confirmed': False}
    process = None
    stdout = b''
    stderr = b''
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['pid'] = process.pid
        save(folder / 'STARTED.json', record)
        left = (deadline_ns - time.perf_counter_ns()) / 1e9
        if left <= 0:
            raise TimeoutError('thin_turn_original_deadline')
        stdout, stderr = process.communicate(wire, timeout=left)
        record['process_exit_ns'] = time.perf_counter_ns()
        record['responses'] = [json.loads(line) for line in stdout.splitlines()]
        if [row.get('id') for row in record['responses']] != request_ids:
            raise ValueError('thin_turn_response_sequence_binding')
        if process.returncode != 0:
            raise RuntimeError('thin_turn_process_failed')
        if time.perf_counter_ns() >= deadline_ns:
            raise TimeoutError('thin_turn_original_deadline')
    except BaseException as exc:
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if isinstance(exc, subprocess.TimeoutExpired):
            stdout = exc.stdout or b''
            stderr = exc.stderr or b''
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                tail_out, tail_err = process.communicate(timeout=5)
                stdout = tail_out or stdout
                stderr = tail_err or stderr
            record['exit_code'] = process.poll()
            record['process_reaped'] = process.poll() is not None
        else:
            record['process_reaped'] = False
        (folder / 'RX.bin').write_bytes(stdout)
        (folder / 'stderr.bin').write_bytes(stderr)
        record['bridge_cleanup'] = wait_bridge_closed({'endpoint': str(endpoint_path),
                                                       'attachments_dir': str(folder / 'attachments')})
        record['ended_ns'] = time.perf_counter_ns()
        record['wall_ns'] = record['ended_ns'] - started
        record['confirmed'] = bool(record['error'] is None and record['exit_code'] == 0
                                   and record['process_reaped'] and record['bridge_cleanup']['confirmed'] is True
                                   and record['ended_ns'] < deadline_ns)
        save(folder / 'THIN_TURN.json', record)
    return record
