"""Sequential same-source real stdio/MCP/default-owned integration evidence.

Run once per new output directory. All assets are generated private fixture
copies. Both successful and failed directories are retained. Timing includes
the explicitly documented, unquantified validation-observer overhead.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from human_eye_plugin.runtime_identity import runtime_identity
from verification.arch_integration_001.prepare_entry import prepare

COMMON = '081252633cdf49b5b35c4dfa33845c7d05438870'
SOURCE = 'd5f3f7d29c201c21611014f0c963afd8c6b5f6fb501b0d94e60f79890d006936'
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')

def read_rows(path):
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def check_source():
    identity = runtime_identity(mode='live')
    assert identity['source_sha256'] == SOURCE, identity['source_sha256']
    assert len(identity['source_files']) == 133
    for row in identity['source_files']:
        assert digest(ROOT / row['path']) == row['sha256'], row['path']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head == COMMON, head
    return identity

def control(port, folder, **params):
    payload = compact({'type': 'test_control', 'params': params})
    started = time.perf_counter_ns()
    with socket.create_connection(('127.0.0.1', port), timeout=20) as client:
        client.sendall(payload)
        raw = bytearray()
        while True:
            block = client.recv(65536)
            if not block: break
            raw.extend(block)
    with (folder / 'fixture_control.jsonl').open('a', encoding='utf8') as stream:
        stream.write(json.dumps({'request': params, 'tx_hex': payload.hex(), 'rx_hex': raw.hex(),
                                 'duration_ms': (time.perf_counter_ns() - started) / 1e6,
                                 'scope': 'validation control outside measured tool'}, ensure_ascii=False) + '\n')
    response = json.loads(raw)
    assert 'control' in response, response
    return response['control']

def delta_dict(after, before):
    return {key: after[key] - before.get(key, 0) for key in after
            if type(after[key]) is int and after[key] != before.get(key, 0)}

def oracle(snapshot, target='BluePart', candidate='GreyBase'):
    rows = {row['name']: row for row in snapshot['meshes']}
    left, right = rows[target]['vertices'], rows[candidate]['vertices']
    scale = snapshot['scale']
    gaps = [max(0., min(p[i] for p in left) - max(p[i] for p in right),
                    min(p[i] for p in right) - max(p[i] for p in left)) * scale for i in range(3)]
    # For this generated fixture the nearest faces/vertex lie within the other
    # object's overlapping axes: boxes and a single bottom-corner mesh edit.
    return {'distance_m': math.sqrt(sum(g * g for g in gaps)), 'axis_gaps_m': gaps,
            'target': target, 'candidate': candidate,
            'basis': 'independent native world-coordinate support intervals; exact for these fixture faces/corner edit'}

def task_args(target='BluePart', candidate='GreyBase', narrow=False):
    if narrow:
        return {'target': {'name': target}, 'candidates': [{'name': candidate}], 'include_aabb': True}
    return {'session_id': 'integration', 'include_image': False,
            'query': {'mode': 'task', 'target': {'name': target}, 'candidates': [{'name': candidate}],
                      'requested_facts': ['closed_solid_relation', 'surface_proximity', 'aabb']}}

def nearest_args(target='BluePart'):
    return {'session_id': 'integration', 'include_image': False,
            'query': {'mode': 'surface_nearest', 'objects': [{'name': target}]}}

class Client:
    def __init__(self, run, label, config, mode, python, blender, scene=None, narrow=False):
        self.run, self.label, self.mode, self.narrow = run, label, mode, narrow
        self.folder = run / label
        self.folder.mkdir()
        self.responses = queue.Queue()
        self.sequence = 0
        self.config = Path(config)
        self.state = Path(json.loads(self.config.read_text(encoding='utf8'))['state_file'])
        self.error_log = (self.folder / 'stderr.log').open('wb')
        command = [str(python), '-X', 'utf8', '-B', str(HERE / 'instrumented_stdio.py'),
                   '--mode', mode, '--config', str(config), '--directory', str(self.folder)]
        if narrow: command.append('--spatial-task-only')
        if scene: command.extend(['--blender', str(blender), '--scene', str(scene)])
        (self.folder / 'command.json').write_bytes(compact(command))
        self.process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.error_log, bufsize=0, creationflags=HIDDEN)
        def reader():
            while True:
                line = self.process.stdout.readline()
                if not line: break
                with (self.folder / 'stdio_rx.bin').open('ab') as stream: stream.write(line)
                try: self.responses.put((line, json.loads(line)))
                except ValueError: self.responses.put((line, None))
            self.responses.put((b'', None))
        self.thread = threading.Thread(target=reader, daemon=True)
        self.thread.start()
        self.request('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                    'clientInfo': {'name': 'arch-integration-validation', 'version': '1'}})
        _, listing, _ = self.request('tools/list', {})
        names = [tool['name'] for tool in listing['result']['tools']]
        assert names == ['human_eye_spatial_relations'] if narrow else 'human_eye_scene_observe' in names, names

    def request(self, method, params):
        self.sequence += 1
        payload = compact({'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': params}) + b'\n'
        started = time.perf_counter_ns()
        self.process.stdin.write(payload)
        self.process.stdin.flush()
        line, value = self.responses.get(timeout=65)
        elapsed = (time.perf_counter_ns() - started) / 1e6
        with (self.folder / 'stdio_tx.bin').open('ab') as stream: stream.write(payload)
        assert value is not None and value.get('id') == self.sequence, (line[:1000], self.process.poll())
        assert 'error' not in value, value
        return {'stdio_tx_bytes': len(payload), 'stdio_rx_bytes': len(line), 'full_tool_rtt_ms': elapsed,
                'timing_scope': 'before stdin write through complete stdout line, including final JSON encode/flush/read'}, value, self.sequence

    def tool(self, name, arguments):
        ledger_before = digest(self.state)
        before_rows = read_rows(self.folder / 'worker_observer.jsonl')
        cost, response, request_id = self.request('tools/call', {'name': name, 'arguments': arguments})
        assert not response['result'].get('isError'), response
        value = json.loads(next(row['text'] for row in response['result']['content'] if row['type'] == 'text'))
        metrics = [row for row in read_rows(self.folder / 'metrics.jsonl')
                   if row.get('event') == 'tool' and row.get('request_id') == request_id]
        assert len(metrics) == 1, metrics
        metric = metrics[0]
        for token in ('capture_state', '_scene_resource', 'vertices_local', 'live_resources', 'human-eye-scene-delta-v1'):
            assert token not in json.dumps(value, ensure_ascii=False), token
        record = {'client': self.label, 'request_id': request_id, 'tool': name, 'arguments': arguments,
                  **cost, 'metric': metric, 'result': value,
                  'ledger_before_sha256': ledger_before, 'ledger_after_sha256': digest(self.state)}
        rows = read_rows(self.folder / 'worker_observer.jsonl')[len(before_rows):]
        if rows:
            record['owned_worker_events'] = rows
            snapshots = [row for row in rows if row.get('event') == 'worker_snapshot']
            if snapshots: record['native_snapshot'] = snapshots[-1]['native']
        if name != 'human_eye_transform':
            assert record['ledger_after_sha256'] == ledger_before, record
            for key in ('live_service.py:_locked', 'live_service.py:_save', 'live_service.py:_runtime'):
                assert metric['calls'].get(key, 0) == 0, (key, metric)
        return record

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try: self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=10)
        self.thread.join(timeout=2)
        self.error_log.close()
        (self.folder / 'exit.json').write_bytes(compact({'returncode': self.process.returncode}))
        assert self.process.returncode == 0, (self.label, self.process.returncode)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', default='D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe')
    parser.add_argument('--blender', default='D:/Tools/blender5.2/blender.exe')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists(): raise ValueError('Refusing to overwrite existing evidence directory: ' + str(output))
    output.mkdir(parents=True)
    records, clients = [], []
    result = {'passed': False, 'common_commit': COMMON, 'runtime_source_sha256': SOURCE,
              'observation_overhead': 'profile callbacks, exact wire recording, worker native snapshot and append; measured but not subtracted; no performance target claim',
              'original_user_assets_accessed': 0, 'records': records}
    fixture_process = fixture_log = None
    started = time.perf_counter_ns()
    def persist():
        (output / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    def accept(client, label, arguments=None, kind='task', target='BluePart', candidate='GreyBase', port=None, warm=False):
        name = 'human_eye_transform' if kind == 'transform' else 'human_eye_spatial_relations' if client.narrow else 'human_eye_scene_observe'
        if arguments is None: arguments = nearest_args(target) if kind == 'nearest' else task_args(target, candidate, client.narrow)
        before = control(port, output, op='stats') if port else None
        record = client.tool(name, arguments)
        record['label'] = label
        records.append(record)
        persist()  # retain even a subsequent correctness failure
        if port:
            record['host_before'] = before
            record['host_after'] = control(port, output, op='stats')
            record['native_snapshot'] = control(port, output, op='native_snapshot')
        if kind != 'transform':
            expected = oracle(record['native_snapshot'], target, candidate)
            value = record['result']
            actual = value['sets']['nearest_separated']['distance_m'] if client.narrow else value['distance_m'] if kind == 'nearest' else value['summary']['distance_m']
            record['oracle'] = {**expected, 'reported_distance_m': actual, 'abs_error_m': abs(actual - expected['distance_m'])}
            assert record['oracle']['abs_error_m'] < 1e-7, record['oracle']
            if kind == 'nearest': assert any(row['name'] == candidate for row in value['nearest_objects']), value
            if warm:
                calls = record['metric']['calls']
                for suffix in (':_validated_scene', ':from_dict', ':task_result', ':classify_closed_solids', ':measure_surface_proximity', ':measure_pair_geometry'):
                    assert not any(key.endswith(suffix) and n for key, n in calls.items()), (label, suffix, calls)
                assert record['metric']['decoder_after'] == record['metric']['decoder_before'], record['metric']
        persist()
        print(label + ' PASS ' + str(round(record['full_tool_rtt_ms'], 3)) + 'ms', flush=True)
        return record
    def new_client(label, config, mode, scene=None, narrow=False):
        client = Client(output, label, config, mode, args.python, args.blender, scene, narrow)
        clients.append(client)
        return client
    try:
        identity = check_source()
        (output / 'identity_before.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf8')
        for name in ('run_actual.py', 'instrumented_stdio.py', 'observe_worker.py', 'actual_fixture.py', 'owned_service_stdio.py', 'prepare_entry.py'):
            shutil.copyfile(HERE / name, output / (name + '.txt'))
        fixture, ready = output / 'fixture.blend', output / 'ready.json'
        fixture_log = (output / 'fixture_blender.log').open('wb')
        fixture_command = [str(args.blender), '--factory-startup', '--disable-autoexec', '--background',
                           '--python', str(HERE / 'actual_fixture.py'), '--', str(fixture), str(ready)]
        (output / 'fixture_command.json').write_bytes(compact(fixture_command))
        fixture_process = subprocess.Popen(fixture_command, stdout=fixture_log, stderr=subprocess.STDOUT, creationflags=HIDDEN)
        deadline = time.monotonic() + 45
        while not ready.exists():
            assert fixture_process.poll() is None and time.monotonic() < deadline, 'Fixture startup failed'
            time.sleep(.05)
        port = json.loads(ready.read_text(encoding='utf8'))['port']
        configs, commands = prepare(output / 'configs', port)
        result['entrypoints'] = commands
        fixture_hash = digest(fixture)
        result['generated_fixture_before_sha256'] = fixture_hash
        # Existing opaque ledger must stay byte-identical throughout pure reads.
        Path(json.loads(Path(configs['mcp']).read_text())['state_file']).write_bytes(b'opaque action ledger: pending/committed/quarantine\n')
        shared = new_client('shared_narrow', configs['mcp'], 'shared', narrow=True)
        accept(shared, 'shared_cold_AB', port=port)
        accept(shared, 'shared_repeat_AB', port=port, warm=True)
        accept(shared, 'shared_switch_AD', candidate='Far00', port=port)
        accept(shared, 'shared_return_AB', port=port, warm=True)
        accept(shared, 'shared_return_AD', candidate='Far00', port=port, warm=True)
        accept(shared, 'shared_return_AB_again', port=port, warm=True)
        control(port, output, op='color', name='BluePart', color=[1, 0, 0, 1])
        accept(shared, 'shared_metadata_color', port=port)
        control(port, output, op='translate', name='BluePart', dz=.002)
        accept(shared, 'shared_pose', port=port)
        control(port, output, op='mesh', name='BluePart', dz=-.001)
        accept(shared, 'shared_geometry', port=port)
        control(port, output, op='rename', name='BluePart', new_name='蓝色零件')
        accept(shared, 'shared_utf8_name', target='蓝色零件', port=port)
        control(port, output, op='rename', name='蓝色零件', new_name='BluePart')
        control(port, output, op='frame', frame=2)
        accept(shared, 'shared_frame_epoch', port=port)
        control(port, output, op='units', scale=.01)
        accept(shared, 'shared_units_epoch', port=port)
        shared.close(); clients.remove(shared)
        reconnect = new_client('shared_reconnect', configs['mcp'], 'shared', narrow=True)
        accept(reconnect, 'shared_reconnect_cold', port=port)
        accept(reconnect, 'shared_reconnect_repeat', port=port, warm=True)
        control(port, output, op='scene')
        accept(reconnect, 'shared_scene_lifecycle', port=port)
        control(port, output, op='load', path=str(fixture))
        accept(reconnect, 'shared_load_lifecycle', port=port)
        reconnect.close(); clients.remove(reconnect)
        ordinary = new_client('shared_ordinary', configs['mcp'], 'shared')
        accept(ordinary, 'ordinary_task_cold', port=port)
        accept(ordinary, 'ordinary_task_repeat', port=port, warm=True)
        accept(ordinary, 'ordinary_nearest_cold', kind='nearest', port=port)
        accept(ordinary, 'ordinary_nearest_repeat', kind='nearest', port=port, warm=True)
        accept(ordinary, 'ordinary_task_after_nearest', port=port, warm=True)
        ordinary.close(); clients.remove(ordinary)
        assert digest(fixture) == fixture_hash
        fixture_process.terminate(); fixture_process.wait(timeout=20)
        result['shared_fixture_process_exit'] = fixture_process.returncode
        fixture_process = None
        fixture_log.close(); fixture_log = None
        # Shared background process is gone before starting default owned worker.
        owned_scene = output / 'owned_fixture_copy.blend'
        shutil.copyfile(fixture, owned_scene)
        owned = new_client('owned_ordinary', configs['owned'], 'owned', owned_scene)
        cold = accept(owned, 'owned_task_cold')
        accept(owned, 'owned_task_repeat', warm=True)
        accept(owned, 'owned_switch_AD', candidate='Far00')
        accept(owned, 'owned_return_AB', warm=True)
        accept(owned, 'owned_nearest_cold', kind='nearest')
        accept(owned, 'owned_nearest_repeat', kind='nearest', warm=True)
        ids = cold['result']['binding']['objects']
        action = {'session_id': 'integration', 'action': {'focal_id': ids[0]['object_id'],
                  'reference_id': ids[1]['object_id'], 'translation': [0, 0, .002]}}
        moved = accept(owned, 'owned_real_transform', action, kind='transform')
        assert moved['result']['status'] == 'verified', moved['result']
        accept(owned, 'owned_task_after_transform')
        accept(owned, 'owned_task_after_transform_repeat', warm=True)
        accept(owned, 'owned_nearest_after_transform', kind='nearest')
        accept(owned, 'owned_nearest_after_transform_repeat', kind='nearest', warm=True)
        assert owned.state.exists(), 'Transform must establish the real action ledger'
        result['owned_action_ledger_sha256'] = digest(owned.state)
        owned.close(); clients.remove(owned)
        owned_narrow = new_client('owned_narrow', configs['owned'], 'owned', owned_scene, True)
        accept(owned_narrow, 'owned_narrow_cold')
        accept(owned_narrow, 'owned_narrow_repeat', warm=True)
        owned_narrow.close(); clients.remove(owned_narrow)
        assert digest(owned_scene) == fixture_hash, 'Default owned worker must not save its in-memory transform'
        result['generated_fixture_after_sha256'] = digest(fixture)
        result['owned_fixture_copy_after_sha256'] = digest(owned_scene)
        after = check_source()
        (output / 'identity_after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf8')
        result['passed'] = True
    except BaseException as exc:
        result['failure'] = repr(exc)
        result['traceback'] = traceback.format_exc()
        (output / 'failure.txt').write_text(result['traceback'], encoding='utf8')
        print(result['traceback'], flush=True)
    finally:
        for client in reversed(clients):
            try: client.close()
            except BaseException as exc: result.setdefault('cleanup_errors', []).append(repr(exc))
        if fixture_process is not None:
            fixture_process.terminate()
            try: fixture_process.wait(timeout=15)
            except subprocess.TimeoutExpired: fixture_process.kill(); fixture_process.wait(timeout=10)
        if fixture_log: fixture_log.close()
        result['complete_command_ms'] = (time.perf_counter_ns() - started) / 1e6
        result['record_count'] = len(records)
        persist()
    return 0 if result['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
