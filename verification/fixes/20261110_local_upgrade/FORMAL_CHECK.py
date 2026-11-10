"""Fresh process validation of the actual configured default, read-only scene use."""
from pathlib import Path
import json
import queue
import subprocess
import sys
import threading
import time
import tomllib

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent / ('FORMAL_PROTOCOL_RECHECK' if '--protocol-only' in sys.argv else 'FORMAL_FRESH_PROCESS')
BUILD = '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd'
OUT.mkdir(exist_ok=False)
cfg = tomllib.loads((ROOT / '.codex/config.toml').read_text('utf8'))['mcp_servers']['human_eye_live']
assert '9.7.2+20261110.scale.opt.r1' in ' '.join(cfg['args'])
stderr = (OUT / 'STDERR.txt').open('wb')
p = subprocess.Popen([cfg['command'], *cfg['args']], cwd=cfg['cwd'], stdin=subprocess.PIPE,
    stdout=subprocess.PIPE, stderr=stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
responses = queue.Queue()


def read():
    while True:
        line = p.stdout.readline()
        responses.put(line)
        if not line:
            return


thread = threading.Thread(target=read, daemon=True)
thread.start()
rows = []
summary = dict(source_sha256=BUILD, pid=p.pid, fresh_process_only=True)
calls = [('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'local-upgrade-review', 'version': '1'}}),
         ('ping', {}), ('tools/list', {}),
         ('tools/call', {'name': 'human_eye_connection_status', 'arguments': {}}),
         ('tools/call', {'name': 'human_eye_scene_observe', 'arguments': {
             'session_id': 'local-upgrade-read-only-20261110', 'include_image': False,
             'task_instruction': 'Observe the current Blender scene only; do not move, edit or save.'}}),
         ('ping', {}), ('tools/call', {'name': 'human_eye_connection_status', 'arguments': {}})]
if '--protocol-only' in sys.argv:
    calls = [call for call in calls if call[1].get('name') != 'human_eye_scene_observe']
    summary['live_scene_observation'] = 'not_retried; first formal attempt retained Blender-unavailable result'
try:
    for i, (method, params) in enumerate(calls, 1):
        req = dict(jsonrpc='2.0', id=i, method=method, params=params)
        start = time.perf_counter_ns()
        p.stdin.write(json.dumps(req).encode() + b'\n')
        p.stdin.flush()
        raw = responses.get(timeout=40)
        elapsed = time.perf_counter_ns() - start
        (OUT / f'{i}.json').write_bytes(raw)
        value = json.loads(raw)
        assert value.get('id') == i and 'error' not in value, value
        row = dict(id=i, method=method, elapsed_ns=elapsed, response_bytes=len(raw))
        if method == 'initialize':
            identity = value['result']['_meta']['human_eye']
            assert identity['source_sha256'] == BUILD
            row['identity_verified'] = True
        elif method == 'tools/list':
            listing = value['result']['tools']
            row['tools'] = [tool['name'] for tool in listing]
            observe = next(t for t in listing if t['name'] == 'human_eye_scene_observe')
            row['task_mode_published'] = 'task' in json.dumps(observe['inputSchema'])
            row['surface_nearest_published'] = 'surface_nearest' in json.dumps(observe['inputSchema'])
            assert row['task_mode_published'] and row['surface_nearest_published']
        elif method == 'tools/call':
            envelope = value['result']
            text = [x['text'] for x in envelope['content'] if x['type'] == 'text']
            assert len(text) == 1
            metadata = json.loads(text[0])
            identity = metadata.get('runtime_identity', {})
            if identity:
                assert identity.get('source_sha256') == BUILD
            row.update(tool=params['name'], status=metadata.get('status'), code=metadata.get('code'),
                       isError=envelope.get('isError', False))
            if params['name'] == 'human_eye_connection_status':
                assert identity.get('source_sha256') == BUILD
                assert not metadata.get('inflight_operation') and not metadata.get('quarantined')
            else:
                summary['live_scene_observation_status'] = metadata.get('status')
                summary['live_scene_observation_passed'] = (
                    not envelope.get('isError', False) and metadata.get('status') in ('observed', 'partial'))
        rows.append(row)
    summary['protocol_and_identity_passed'] = True
except BaseException as exc:
    summary.update(protocol_and_identity_passed=False, error=type(exc).__name__ + ': ' + str(exc))
    raise
finally:
    p.stdin.close()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=5)
        summary['forced_close'] = True
    stderr.close()
    summary.update(exit_code=p.returncode, calls=rows)
    (OUT / 'RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
