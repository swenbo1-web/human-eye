"""Three pair-relation CLI deliveries in one existing control asset session."""
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


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def check_payload(payload, state, mesh, truth, baseline):
    require(payload['schema_version'] == 'task-query-v3', 'Task schema migration')
    require(set(payload['facts']) == {'pair_relation'}, 'Exact composite fact request')
    require('source_sha256' not in payload['binding'], 'No duplicate runtime hash alias')
    pair = payload['facts']['pair_relation']
    require(payload['status'] == 'observed' and pair['status'] == 'measured', 'Required relation evidence complete')
    require(pair['relation_tolerance_m'] == 0, 'Explicit zero-tolerance relation')
    value = pair['value']
    expected = truth['states']['changed' if state == 'changed' else 'initial']['probes']['Object_02']
    if state != 'changed':
        require(value['relation'] == 'separated', 'Separated relation')
        gap = value['surface_gap_m']
        require(gap > 0 and abs(gap - expected['minimum_gap_m']) + expected['distance_error_bound_m'] <= 1e-6,
                'Certified separated answer tolerance')
        require(gap == baseline['facts']['surface_clearance']['value'], 'Legacy scalar agreement')
        points = value['nearest_witness']
        require(points == baseline['facts']['nearest_witness']['value'], 'Legacy original witness agreement')
        require(abs(math.dist(points['a'], points['b']) - gap) <= 1e-9, 'World point distance')
        require(points['direction_a_to_b'] == [1, 0, 0], 'Actual A-to-B +X direction')
        for point, name in ((points['a'], 'Object_01'), (points['b'], 'Object_02')):
            bounds = [(min(v[k] for v in mesh[name]['vertices']), max(v[k] for v in mesh[name]['vertices']))
                      for k in range(3)]
            require(all(lo - 1e-9 <= point[k] <= hi + 1e-9 for k, (lo, hi) in enumerate(bounds)),
                    'Point inside unchanged original face extents')
            require(any(abs(point[k] - bound) <= 1e-9 for k, pair_bounds in enumerate(bounds) for bound in pair_bounds),
                    'Point on unchanged original box surface')
    else:
        require(expected['relation'] == value['relation'] == 'penetrating', 'Actual strict penetration')
        require('surface_gap_m' not in value and 'nearest_witness' not in value,
                'Overlap metric carries no surface-distance or nearest-witness claim')
        evidence = value['evidence']
        old_evidence = baseline['facts']['solid_relation']['evidence']
        require(evidence == old_evidence, 'Reused strict SAT evidence unchanged')
        require(evidence['zero_tolerance_is_penetrating'] is True, 'Strict overlap certificate')
        require(evidence['method'] == 'convex_sat' and evidence['world_apply_verified'] is False,
                'Existing unapplied SAT method evidence')
        require(abs(evidence['escape_distance_m'] + baseline['facts']['surface_clearance']['value']) <= 1e-15,
                'Legacy certified escape magnitude agreement')
    return dict(relation=value['relation'], complete=True, independent_truth_consistent=True,
                legacy_numeric_evidence_consistent=True,
                mesh_evidence_scope='sealed control asset same-byte original readback; no new native read')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reuse', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--pin', required=True)
    parser.add_argument('--service-entry', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    workspace = args.output / 'session'
    purelib = Path(sysconfig.get_path('purelib'))
    tool = purelib / 'verification/perf000_scene_tool.py'
    author = args.reuse / 'run_01/author/control'
    baseline_config = native.load(args.baseline / 'session/CONFIG.json')
    require(native.sha(author / 'scene.blend') == baseline_config['asset_sha256'], 'Same-byte control asset')
    require(native.sha(author / 'qa_patch.json') == baseline_config['qa_vertex_patch']['sha256'], 'Same-byte control patch')
    truth_path = args.reuse / 'run_02/author/control/TRUTH.json'
    truth = native.load(truth_path)
    started = time.perf_counter_ns()
    deadline = time.monotonic() + 180
    command = [sys.executable, '-I', '-B', str(args.service_entry), '--asset', str(author / 'scene.blend'),
               '--workspace', str(workspace), '--blender', 'D:/Tools/blender5.2/blender.exe',
               '--condition', 'P', '--pin', args.pin, '--expected-asset-sha256', native.sha(author / 'scene.blend'),
               '--seconds', '180', '--qa-vertex-patch', str(author / 'qa_patch.json')]
    record = dict(started_utc=utc(), argv=command, states=[], passed=False, model_consumers=0,
                  observes_started=0, operator_readbacks_started=0, qa_updates_started=0,
                  source_pin=args.pin, truth_path=str(truth_path), truth_sha256=native.sha(truth_path),
                  cli_wall_scope='subprocess.run start through returned and reaped CLI process; excludes response checks, file writes and counter reads')
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
                receipt = native.NativeSession.open(workspace).qa_advance()
                native.save(args.output / 'QA_UPDATE.json', receipt)
                require(receipt['response']['status'] == 'success', 'One QA patch acknowledgement')
            query = dict(mode='task', objects=[dict(name='Object_01'), dict(name='Object_02')],
                         requested_facts=['pair_relation'])
            cli = [sys.executable, '-I', '-B', str(tool), 'observe', '--workspace', str(workspace),
                   '--query-literal', repr(query), '--detail', 'brief']
            record['observes_started'] += 1
            call_start = time.perf_counter_ns()
            result = subprocess.run(cli, capture_output=True, timeout=min(30, deadline - time.monotonic()))
            cli_wall_ns = time.perf_counter_ns() - call_start
            (args.output / (state + '.CLI.stdout')).write_bytes(result.stdout)
            (args.output / (state + '.CLI.stderr')).write_bytes(result.stderr)
            row = dict(state=state, argv=cli, cli_wall_ns=cli_wall_ns, cli_exit_code=result.returncode,
                cli_stdout_bytes=len(result.stdout), cli_stderr_bytes=len(result.stderr))
            record['states'].append(row)
            require(result.returncode == 0, 'Actual thin CLI failed')
            payload = json.loads(result.stdout.decode('utf-8'))
            row['payload'] = payload
            require(payload['binding']['runtime_source_sha256'] == args.pin, 'Candidate runtime binding')
            baseline_path = args.baseline / (state + '.CLI.stdout')
            old_stdout = baseline_path.read_bytes()
            baseline = json.loads(old_stdout.decode('utf-8'))
            mesh_path = args.baseline / (state + '.OPERATOR_REPLY.json')
            mesh = json.loads(native.load(mesh_path)['result']['stdout'])
            row['verified'] = check_payload(payload, state, mesh, truth, baseline)
            counts = native.load(workspace / 'QA_COUNTS.json')
            native.save(args.output / (state + '.COUNTS.json'), counts)
            row.update(counters=counts, baseline_cli_stdout_bytes=len(old_stdout),
                baseline_cli_path=str(baseline_path), baseline_cli_sha256=native.sha(baseline_path),
                baseline_mesh_path=str(mesh_path), baseline_mesh_sha256=native.sha(mesh_path))
            require(len(result.stdout) <= len(old_stdout), 'Same-state public CLI bytes did not grow')
        a, b, c = record['states']
        for key in ('scene_revision', 'scene_fingerprint'):
            require(a['payload']['binding'][key] == b['payload']['binding'][key], 'Current unchanged ' + key)
            require(c['payload']['binding'][key] != b['payload']['binding'][key], 'Current changed ' + key)
        require(sum(row['cli_stdout_bytes'] for row in record['states']) <
                sum(row['baseline_cli_stdout_bytes'] for row in record['states']), 'Total public CLI bytes decreased')
        expected_counts = dict(pair_measurements=2, scalar_surface_traversals=0,
            witness_surface_traversals=1, paired_sat_calls=2, fallback_sat_calls=0,
            selected_captures=3, full_captures=0, task_content_encodings=3)
        require(c['counters']['counts'] == expected_counts, 'Demanded work and encoding counts')
        require(b['counters']['counts']['pair_measurements'] == 1, 'Unchanged pair cache reuse')
        require(record['observes_started'] == 3 and record['qa_updates_started'] == 1 and
                record['operator_readbacks_started'] == 0, 'Bounded three-state execution')
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
        native.save(args.output / 'RESULT.json', record)
    print(json.dumps(dict(passed=record['passed'], error=record.get('error'), observes=record['observes_started'])))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
