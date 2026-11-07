"""Three real thin-CLI observations and separately recorded QA readbacks."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import sysconfig
import threading
import time

from verification import visual004_native as native
from verification.visual004_session import client, load_broker_ready

READBACK = """
import json
rows = {}
for obj in sorted(bpy.data.objects, key=lambda value: value.name):
    if obj.type == 'MESH':
        rows[obj.name] = dict(vertices=[list(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices],
                              faces=[list(face.vertices) for face in obj.data.polygons],
                              matrix=[list(row) for row in obj.matrix_world])
print(json.dumps(rows))
"""


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def save(path, value):
    native.save(path, value)


def check_payload(payload, state, mesh, truth):
    facts = payload['facts']
    require(set(facts) == {'surface_clearance', 'solid_relation', 'nearest_witness'}, 'Exact fact request')
    require(payload['binding']['source_sha256'], 'Actual source binding')
    scalar = facts['surface_clearance']
    relation = facts['solid_relation']
    require(scalar['status'] == relation['status'] == 'measured', 'Scalar and relation must be known')
    value = scalar['value']
    expected = truth['states']['changed' if state == 'changed' else 'initial']['probes']['Object_02']
    if state != 'changed':
        require(abs(value - expected['minimum_gap_m']) + expected['distance_error_bound_m'] <= 1e-6,
                'Certified unchanged answer tolerance')
        require(relation['value'] == 'not_penetrating', 'Separated relation')
        witness = facts['nearest_witness']
        require(witness['status'] == 'measured' and witness['direction_status'] == 'measured', 'Witness and direction')
        points = witness['value']
        require(abs(math.dist(points['a'], points['b']) - value) <= 1e-9, 'World point distance')
        require(all(abs(x - y) <= 1e-12 for x, y in zip(points['direction_a_to_b'], [1, 0, 0])), 'Actual +X direction')
        for point, name in ((points['a'], 'Object_01'), (points['b'], 'Object_02')):
            bounds = [(min(v[k] for v in mesh[name]['vertices']), max(v[k] for v in mesh[name]['vertices']))
                      for k in range(3)]
            require(all(lo - 1e-9 <= point[k] <= hi + 1e-9 for k, (lo, hi) in enumerate(bounds)), 'Point inside face extents')
            require(any(abs(point[k] - bound) <= 1e-9 for k, pair in enumerate(bounds) for bound in pair),
                    'Point on actual original box surface')
    else:
        require(relation['value'] == 'penetrating' and value < 0, 'Actual penetration')
        require(facts['nearest_witness']['status'] == 'unknown', 'No invented nearest witness in overlap')
        evidence = relation.get('evidence')
        require(type(evidence) is dict and evidence, 'SAT numeric evidence available in the same response')
    return dict(single_observation_sufficient=True, scalar=value,
                solid_relation=relation, nearest_witness=facts['nearest_witness'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reuse', required=True, type=Path)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--service-entry', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    workspace = args.output / 'session'
    purelib = Path(sysconfig.get_path('purelib'))
    tool = purelib / 'verification/perf000_scene_tool.py'
    author = args.reuse / 'run_01/author/control'
    truth = native.load(args.reuse / 'run_02/author/control/TRUTH.json')
    started = time.perf_counter_ns()
    deadline = time.monotonic() + 180
    command = [sys.executable, '-I', '-B', str(args.service_entry), '--asset', str(author / 'scene.blend'),
               '--workspace', str(workspace), '--blender', 'D:/Tools/blender5.2/blender.exe',
               '--condition', 'P', '--pin', args.pin, '--expected-asset-sha256', native.sha(author / 'scene.blend'),
               '--seconds', '180', '--qa-vertex-patch', str(author / 'qa_patch.json')]
    record = dict(started_utc=utc(), argv=command, states=[], passed=False, model_consumers=0,
                  observes_started=0, operator_readbacks_started=0, qa_updates_started=0)
    process = None
    timer = None
    worker_handle = None
    forced = []
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    def stop():
        event = dict(at_utc=utc())
        if process is not None and process.poll() is None:
            result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            event['taskkill_returncode'] = result.returncode
        if worker_handle and kernel.WaitForSingleObject(worker_handle, 0) == 258:
            event['worker_terminate'] = bool(kernel.TerminateProcess(worker_handle, 124))
        forced.append(event)

    try:
        with (args.output / 'service.stdout.log').open('xb') as out, (args.output / 'service.stderr.log').open('xb') as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                cwd=str(args.output), creationflags=subprocess.CREATE_NO_WINDOW)
        record['launcher_pid'] = process.pid
        timer = threading.Timer(180, stop)
        timer.daemon = True
        timer.start()
        while not (workspace / 'BROKER_READY.json').exists():
            require(process.poll() is None and time.monotonic() < deadline, 'Startup failed')
            time.sleep(.02)
        ready = load_broker_ready(workspace)
        record['ready'] = ready
        worker_handle = kernel.OpenProcess(0x00100000 | 0x1000 | 1, False, ready['worker_pid'])
        require(worker_handle, 'Worker handle')
        for state in ('initial', 'unchanged', 'changed'):
            require(time.monotonic() < deadline, 'Original acceptance deadline')
            if state == 'changed':
                record['qa_updates_started'] += 1
                save(args.output / 'QA_UPDATE.json', native.NativeSession.open(workspace).qa_advance())
            record['operator_readbacks_started'] += 1
            reply = client(workspace, dict(request_id='operator-' + state, operation='native_run', args=dict(code=READBACK)))
            save(args.output / (state + '.OPERATOR_REPLY.json'), reply)
            require(reply.get('ok') and reply.get('operation_succeeded'), 'Operator readback failed')
            mesh = json.loads(reply['result']['stdout'])
            query = dict(mode='task', objects=[dict(name='Object_01'), dict(name='Object_02')],
                         requested_facts=['surface_clearance', 'solid_relation', 'nearest_witness'])
            cli = [sys.executable, '-I', '-B', str(tool), 'observe', '--workspace', str(workspace),
                   '--query-literal', repr(query), '--detail', 'brief']
            record['observes_started'] += 1
            call_start = time.perf_counter_ns()
            result = subprocess.run(cli, capture_output=True, timeout=min(30, deadline - time.monotonic()))
            (args.output / (state + '.CLI.stdout')).write_bytes(result.stdout)
            (args.output / (state + '.CLI.stderr')).write_bytes(result.stderr)
            require(result.returncode == 0, 'Actual thin CLI failed')
            payload = json.loads(result.stdout.decode('utf-8'))
            require(payload['binding']['source_sha256'] == args.pin, 'Candidate response binding')
            verified = check_payload(payload, state, mesh, truth)
            counts = native.load(workspace / 'QA_COUNTS.json')
            save(args.output / (state + '.COUNTS.json'), counts)
            record['states'].append(dict(state=state, argv=cli, cli_wall_ns=time.perf_counter_ns() - call_start,
                cli_stdout_bytes=len(result.stdout), cli_stderr_bytes=len(result.stderr), payload=payload,
                counters=counts, verified=verified))
        a, b, c = record['states']
        require(a['payload']['binding']['scene_fingerprint'] == b['payload']['binding']['scene_fingerprint'], 'Unchanged fingerprint')
        require(c['payload']['binding']['scene_fingerprint'] != b['payload']['binding']['scene_fingerprint'], 'Changed fingerprint')
        require(c['counters']['counts'] == dict(pair_measurements=2, scalar_surface_traversals=0,
            witness_surface_traversals=1, paired_sat_calls=2, fallback_sat_calls=0,
            selected_captures=3, full_captures=0), 'Demanded work counts')
        record['passed'] = True
    except BaseException as exc:
        record['error'] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        if process is not None and process.poll() is None:
            try:
                record['close_reply'] = client(workspace, dict(request_id='acceptance-close', operation='close', args={}))
            except BaseException as exc:
                record['close_error'] = str(exc)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stop()
                process.wait(timeout=8)
        if timer is not None:
            timer.cancel()
            timer.join(timeout=9)
            record['watchdog_joined'] = not timer.is_alive()
        record['launcher_exit_code'] = None if process is None else process.poll()
        if worker_handle:
            state = kernel.WaitForSingleObject(worker_handle, 0)
            if state == 258:
                stop()
                state = kernel.WaitForSingleObject(worker_handle, 5000)
            code = ctypes.c_uint32()
            record['worker_exit_observed'] = state == 0
            record['worker_exit_code'] = code.value if kernel.GetExitCodeProcess(worker_handle, ctypes.byref(code)) else None
            kernel.CloseHandle(worker_handle)
        record.update(ended_utc=utc(), total_wall_ns=time.perf_counter_ns() - started, forced_cleanup=forced)
        record['passed'] = bool(record['passed'] and not forced and record.get('worker_exit_observed')
                                and record.get('watchdog_joined') and record['launcher_exit_code'] == 0
                                and record.get('worker_exit_code') == 0)
        save(args.output / 'RESULT.json', record)
    print(json.dumps(dict(passed=record['passed'], error=record.get('error'), observes=record['observes_started'])))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
