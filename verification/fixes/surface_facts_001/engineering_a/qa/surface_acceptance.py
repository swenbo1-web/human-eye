"""Four actual surface-fact deliveries in two owned sessions."""
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

READBACK = """import json
print(json.dumps({obj.name:dict(vertices=[list(v.co) for v in obj.data.vertices],
faces=[list(p.vertices) for p in obj.data.polygons], matrix=[list(r) for r in obj.matrix_world],
modifiers=len(obj.modifiers)) for obj in bpy.data.objects if obj.type=='MESH'}))
"""
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
kernel.OpenProcess.restype = ctypes.c_void_p
kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel.CloseHandle.argtypes = [ctypes.c_void_p]

def utc():
    return datetime.now(timezone.utc).isoformat()

def require(value, reason):
    if not value:
        raise ValueError(reason)

def dot(a, b):
    return sum(x*y for x,y in zip(a,b))

def point_on_triangles(point, mesh):
    for face in mesh['faces']:
        a,b,c = [mesh['vertices'][i] for i in face]
        ab = [b[k]-a[k] for k in range(3)]
        ac = [c[k]-a[k] for k in range(3)]
        offset = [point[k]-a[k] for k in range(3)]
        aa,cc,bc = dot(ab,ab),dot(ac,ac),dot(ab,ac)
        determinant = aa*cc-bc*bc
        if determinant <= 0:
            continue
        u = (dot(offset,ab)*cc-dot(offset,ac)*bc)/determinant
        v = (dot(offset,ac)*aa-dot(offset,ab)*bc)/determinant
        residual = [offset[k]-u*ab[k]-v*ac[k] for k in range(3)]
        if u >= -1e-10 and v >= -1e-10 and u+v <= 1+1e-10 and math.hypot(*residual) <= 1e-9:
            return True
    return False

def check_payload(payload, expected, mesh):
    require(payload['result_kind'] == 'task_query', 'Existing task response')
    require(set(payload['facts']) == {'surface_proximity'}, 'Exact explicit surface fact request')
    fact = payload['facts']['surface_proximity']
    require(payload['status'] == 'observed' and fact['status'] == 'measured', 'Surface fact complete')
    value = fact['value']
    require(abs(value['distance_m']-expected['distance_m']) <= 1e-12, 'Independent exact answer')
    require(value['distance_m'] >= 0, 'Nonnegative surface distance')
    require(len(value['topology']) == 2, 'Ordered topology')
    require([row['boundary_edge_count'] for row in value['topology']] == expected['boundary_edges'],
            'Actual boundary-edge counts')
    require([row['nonmanifold_edge_count'] for row in value['topology']] == expected['nonmanifold_edges'],
            'Actual nonmanifold-edge counts')
    require(fact['witness_status'] == 'measured', 'Original surface witnesses')
    witness = value['nearest_witness']
    a,b = witness['a'], witness['b']
    require(abs(math.dist(a,b)-value['distance_m']) <= 1e-9, 'Witness distance publication')
    for point,name in zip((a,b),expected['objects']):
        require(point_on_triangles(point,mesh[name]), 'Witness on current original triangle surface')
    if expected['distance_m'] == 0:
        require(fact['direction_status'] == 'not_applicable' and witness['direction_a_to_b'] is None,
                'Zero-distance direction applicability')
        require(a == b, 'Common zero-distance witness')
    else:
        require(fact['direction_status'] == 'measured', 'Positive-distance direction')
        require(all(abs(x-y) <= 1e-12 for x,y in zip(witness['direction_a_to_b'],expected['direction_a_to_b'])),
                'Ordered current surface direction')
    require(fact['semantics'] == 'current_evaluated_triangle_surfaces_world_metres', 'Current surface provenance')
    return dict(complete=True, independent_expected_distance_m=expected['distance_m'],
        independent_exact_squared_distance=expected['exact_squared_distance'],
        witnesses_on_current_triangles=True, original_surface_distance_consistent=True)

def run_case(args, case):
    folder = args.output / case
    folder.mkdir(parents=True, exist_ok=False)
    workspace = folder / 'session'
    author = args.root / 'author' / case
    launcher = Path(sysconfig.get_path('purelib')) / 'verification/perf010_qualification.py'
    tool = launcher.with_name('perf000_scene_tool.py')
    command = [sys.executable,'-I','-B',str(args.service_entry),'--asset',str(author/'scene.blend'),
        '--workspace',str(workspace),'--blender','D:/Tools/blender5.2/blender.exe',
        '--condition','P','--pin',args.pin,'--source-count',str(args.source_count),
        '--expected-asset-sha256',native.sha(author/'scene.blend'),'--seconds','180']
    if case == 'G':
        command += ['--qa-vertex-patch',str(author/'qa_patch.json')]
    record = dict(case=case,started_utc=utc(),command=command,observes_started=0,
        raw_readbacks_started=0,updates_started=0,states=[],forced_cleanup=[],passed=False)
    native.save(folder/'START.json',record)
    process = None
    handle = None
    timer = None
    started = time.perf_counter_ns()
    def stop():
        event = dict(utc=utc())
        if process is not None and process.poll() is None:
            result = subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
            event['taskkill_exit'] = result.returncode
        if handle and kernel.WaitForSingleObject(handle,0) == 258:
            event['worker_terminate'] = bool(kernel.TerminateProcess(handle,124))
        record['forced_cleanup'].append(event)
    try:
        with (folder/'service.stdout.log').open('xb') as out,(folder/'service.stderr.log').open('xb') as err:
            process = subprocess.Popen(command,stdout=out,stderr=err,stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,cwd=str(folder))
        record['launcher_pid'] = process.pid
        timer = threading.Timer(180,stop)
        timer.daemon = True
        timer.start()
        deadline = time.monotonic()+175
        while not (workspace/'BROKER_READY.json').exists():
            require(process.poll() is None and time.monotonic()<deadline,'Startup failed')
            time.sleep(.02)
        ready = load_broker_ready(workspace)
        record['ready'] = ready
        handle = kernel.OpenProcess(0x00100000|0x1000|1,False,ready['worker_pid'])
        require(handle,'Cannot retain worker handle')
        record['raw_readbacks_started'] += 1
        raw = client(workspace,dict(request_id='acceptance-raw',operation='native_run',args=dict(code=READBACK)))
        native.save(folder/'RAW_READBACK_REPLY.json',raw)
        require(raw.get('ok') and raw.get('operation_succeeded'),'Raw readback failed')
        current = json.loads(raw['result']['stdout'])
        require(current == native.load(author/'BUILD_READBACK.json'), 'Actual asset differs from build readback')
        truth = native.load(author/'TRUTH.json')
        states = ('initial','changed') if case == 'G' else ('edge_crossing','closed_separated')
        for state in states:
            if state == 'changed':
                record['updates_started'] += 1
                receipt = native.NativeSession.open(workspace).qa_advance()
                native.save(folder/'QA_ADVANCE_RECEIPT.json',receipt)
                require(receipt['response']['status'] == 'success'
                        and receipt['response']['result']['vertices_written'] == 4,'One QA update failed')
                current['Object_01']['vertices'] = truth['changed_target_vertices']
            expected = truth['states'][state]
            query = dict(mode='task',objects=[dict(name=name) for name in expected['objects']],
                         requested_facts=['surface_proximity'])
            cli = [sys.executable,'-I','-B',str(tool),'observe','--workspace',str(workspace),
                   '--query-literal',repr(query),'--detail','brief']
            record['observes_started'] += 1
            before = time.perf_counter_ns()
            response = subprocess.run(cli,capture_output=True,timeout=min(35,deadline-time.monotonic()))
            wall = time.perf_counter_ns()-before
            (folder/(state+'.CLI.stdout')).write_bytes(response.stdout)
            (folder/(state+'.CLI.stderr')).write_bytes(response.stderr)
            row = dict(state=state,command=cli,cli_process_wall_ns=wall,exit_code=response.returncode,
                stdout_bytes=len(response.stdout),stderr_bytes=len(response.stderr))
            record['states'].append(row)
            require(response.returncode == 0,'Observe transport failed')
            payload = json.loads(response.stdout.decode('utf8'))
            row['payload'] = payload
            require(payload['binding']['runtime_source_sha256'] == args.pin,'Installed response source pin')
            row['verified'] = check_payload(payload,expected,current)
            row['counters'] = native.load(workspace/'QA_COUNTS.json')
            native.save(folder/(state+'.COUNTS.json'),row['counters'])
        if case == 'G':
            for key in ('scene_revision','scene_fingerprint'):
                require(record['states'][0]['payload']['binding'][key] !=
                        record['states'][1]['payload']['binding'][key], 'Updated current binding')
        expected_counts = dict(surface_measurements=2,strict_pair_measurements=0,paired_sat_calls=0,
            fallback_sat_calls=0,selected_captures=2,full_captures=0,task_content_encodings=2)
        require(record['states'][-1]['counters']['counts'] == expected_counts,
                'Surface-only work and single capture/encoding counts')
        record['passed'] = True
    except BaseException as exc:
        record['error'] = dict(type=type(exc).__name__,message=str(exc))
    finally:
        if process is not None and process.poll() is None:
            try:
                record['close_reply'] = client(workspace,dict(request_id='acceptance-close',operation='close',args={}))
            except BaseException as exc:
                record['close_error'] = dict(type=type(exc).__name__,message=str(exc))
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
        if handle:
            state = kernel.WaitForSingleObject(handle,0)
            if state == 258:
                stop()
                state = kernel.WaitForSingleObject(handle,5000)
            exit_code = ctypes.c_uint32()
            record['worker_exited'] = state == 0
            record['worker_exit_code'] = exit_code.value if kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) else None
            kernel.CloseHandle(handle)
        record.update(ended_utc=utc(),startup_to_reap_ns=time.perf_counter_ns()-started)
        record['passed'] = bool(record['passed'] and not record['forced_cleanup'] and record.get('worker_exited')
            and record.get('watchdog_joined') and record['launcher_exit_code'] == record.get('worker_exit_code') == 0)
        native.save(folder/'RESULT.json',record)
    return record

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--pin',required=True)
    parser.add_argument('--source-count',required=True,type=int)
    parser.add_argument('--service-entry',required=True,type=Path)
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    results = []
    for case in ('G','control'):
        result = run_case(args,case)
        results.append(result)
        if not result['passed']:
            break
    summary = dict(passed=len(results)==2 and all(row['passed'] for row in results),
        source_sha256=args.pin,source_count=args.source_count,
        observe_count=sum(row['observes_started'] for row in results),
        raw_readback_count=sum(row['raw_readbacks_started'] for row in results),
        qa_update_count=sum(row['updates_started'] for row in results),cases=results)
    native.save(args.output/'RESULT.json',summary)
    print(json.dumps(dict(passed=summary['passed'],observe_count=summary['observe_count'],
        raw_readback_count=summary['raw_readback_count'],qa_update_count=summary['qa_update_count'],
        errors=[row.get('error') for row in results])))
    return 0 if summary['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
