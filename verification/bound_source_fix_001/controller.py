"""One frozen private NativeSession, five scripts, one close, no retry."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import types

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
OUT = FOLDER / 'run_01'
HELPER = Path('D:/hefe/verification/fixes/20261106_perf010_r2/installed/verification/visual004_native.py')
HELPER_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
PRODUCT_SHA = 'ae3bd4a30908d104165e0ca5e24d764f72544f49a0f2d54341335a27e0df7769'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def prepare():
    assert not OUT.exists(), 'single_frozen_run_no_retry'
    candidate_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(['git','diff','HEAD','--','human_eye_plugin/blender_host.py'],cwd=ROOT), 'candidate_source_not_committed'
    assignment = Path('D:/hefe/verification/fixes/20261107_nearest_contract/SOURCE_FIX_ASSIGNMENT.md')
    assert sha(assignment) == '0cf47fc460c9e20527ffff82fa8e48d14ae6e854219fb0f09e93fff3a19e917f'
    identity = json.loads((FOLDER / 'CANDIDATE_IDENTITY.json').read_bytes())
    assert identity['source_sha256'] == PRODUCT_SHA and len(identity['files']) == 131
    for row in identity['files']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    assert sha(HELPER) == HELPER_SHA
    assets_path = ROOT / 'verification/m4_capture_qa_001/run_01/assets/ASSETS.json'
    asset = next(row for row in json.loads(assets_path.read_bytes())['cases'] if row['case'] == 'far_second_degenerate')
    assert asset['sha256'] == sha(asset['asset']) == '9a7671bb202720b09311f313363bc0e5267017f2af155a9167fff4cf2d96d1b6'
    blender = 'D:/Tools/blender5.2/blender.exe'
    binary_sha = sha(blender)
    assert binary_sha == '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
    now = datetime.datetime.now(datetime.timezone.utc)
    assert now < datetime.datetime(2026, 11, 7, 13, 45, tzinfo=datetime.timezone.utc), 'leave_600s_60s_and_seal_margin'
    OUT.mkdir()
    plan = dict(root=str(ROOT), baseline_head='d6fdf2a1381c541a54c8326e73b011e9ca80720f', candidate_commit=candidate_commit, source_sha256=PRODUCT_SHA,
                product_manifest=identity['files'], host_sha256=sha(ROOT / 'human_eye_plugin/blender_host.py'),
                blender=blender, blender_sha256=binary_sha, asset=asset['asset'], asset_sha256=asset['sha256'],
                old_assets_manifest_sha256=sha(assets_path), helper=str(HELPER), helper_sha256=HELPER_SHA,
                assignment_sha256=sha(assignment), window='SOURCE-FIX-001-ONLY',
                start_ns=time.perf_counter_ns(), deadline_ns=time.perf_counter_ns()+600_000_000_000,
                max_sessions=1, max_state_RPC=5, max_close_RPC=1, max_total_RPC=6, max_capture_per_state=1,
                started_utc=now.isoformat(), original_asset_write=False, retries=0)
    save(OUT / 'PLAN.json', plan)
    body = (FOLDER / 'worker_body.py').read_bytes().decode('utf-8')
    scripts = []
    for state in range(1, 6):
        code = 'STATE = ' + str(state) + '\nPLAN = ' + repr(plan) + '\n' + body
        compile(code, '<frozen-state-'+str(state)+'>', 'exec')
        path = OUT / ('STATE_'+str(state)+'.py')
        path.write_bytes(code.encode())
        assert len(code.encode()) <= 256*1024
        scripts.append(dict(state=state, path=str(path), sha256=sha(path), bytes=path.stat().st_size))
    freeze = dict(plan_sha256=sha(OUT/'PLAN.json'), scripts=scripts,
                  controllers=[dict(path=str(FOLDER/name), sha256=sha(FOLDER/name)) for name in ('controller.py','worker_body.py','PREREGISTRATION.md','test_source_validation.py','regressions.py','measure_work.py','analyze.py','CANDIDATE_IDENTITY.json')])
    save(OUT/'FREEZE.json', freeze)
    print(json.dumps(dict(status='frozen_no_session_started', freeze_sha256=sha(OUT/'FREEZE.json'))))


class MeterSocket:
    def __init__(self, sock, folder, meter):
        self.sock, self.folder, self.meter = sock, folder, meter
    def __getattr__(self, key):
        return getattr(self.sock, key)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return self.sock.__exit__(*args)
    def sendall(self, raw):
        with (self.folder/'TX.bin').open('ab') as stream: stream.write(raw)
        self.meter['send_attempted_bytes'] += len(raw)
        result = self.sock.sendall(raw)
        self.meter['send_completed_bytes'] += len(raw)
        return result
    def recv(self, size):
        raw = self.sock.recv(size)
        with (self.folder/'RX.bin').open('ab') as stream: stream.write(raw)
        self.meter['received_bytes'] += len(raw)
        return raw


def run():
    plan = json.loads((OUT/'PLAN.json').read_bytes())
    freeze = json.loads((OUT/'FREEZE.json').read_bytes())
    assert sha(OUT/'PLAN.json') == freeze['plan_sha256']
    for row in freeze['scripts'] + freeze['controllers']:
        assert sha(row['path']) == row['sha256']
    assert not (OUT/'STARTED.json').exists(), 'no_second_session_or_retry'
    assert time.perf_counter_ns() < plan['deadline_ns']
    for row in plan['product_manifest']: assert sha(ROOT/row['path']) == row['sha256']
    assert sha(HELPER) == plan['helper_sha256'] and sha(plan['asset']) == plan['asset_sha256']
    save(OUT/'STARTED.json', dict(at_ns=time.perf_counter_ns(), freeze_sha256=sha(OUT/'FREEZE.json')))
    native = types.ModuleType('_bound_qa_native')
    native.__file__ = str(HELPER)
    sys.modules[native.__name__] = native
    exec(compile(HELPER.read_bytes(), str(HELPER), 'exec', dont_inherit=True), native.__dict__)
    owner = None
    result = dict(states=[], primary_error=None, owned_sessions_attempted=0, transport_attempts=0, cleanup=None,
                  zero_performance_samples=True, zero_model_consumers=True)
    start = time.perf_counter_ns()
    def transaction(name, call):
        folder = OUT/name
        folder.mkdir()
        meter = dict(send_attempted_bytes=0, send_completed_bytes=0, received_bytes=0)
        original = native.socket.create_connection
        def connect(*args, **kwargs): return MeterSocket(original(*args, **kwargs), folder, meter)
        result['transport_attempts'] += 1
        native.socket.create_connection = connect
        begun = time.perf_counter_ns()
        try:
            response = call()
            save(folder/'RESPONSE.json', response)
            return response
        finally:
            native.socket.create_connection = original
            save(folder/'TRANSPORT.json', dict(**meter, elapsed_ns=time.perf_counter_ns()-begun))
    try:
        result['owned_sessions_attempted'] = 1
        owner = native.NativeSession.start(blender=plan['blender'], asset=plan['asset'], workspace=OUT/'owned',
                    deadline_ns=plan['deadline_ns'], expected_asset_sha256=plan['asset_sha256'], max_calls=5)
        assert owner.ready['pid'] == owner.process.pid and owner.ready['helper_sha256'] == HELPER_SHA
        assert owner.process.poll() is None and owner.host == '127.0.0.1'
        result['ready'] = owner.ready
        for row in freeze['scripts']:
            code = Path(row['path']).read_bytes().decode()
            receipt = transaction('rpc_'+str(row['state']), lambda: owner.run(code, timeout_s=75))
            result['states'].append(dict(state=row['state'], response_status=receipt['response'].get('status')))
            if receipt['response'].get('status') != 'success':
                raise RuntimeError('state_RPC_error_no_replay')
    except BaseException as error:
        result['primary_error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    finally:
        if owner is not None:
            try: result['cleanup'] = transaction('rpc_close', owner.close)
            except BaseException as error:
                result['cleanup_error'] = dict(type=type(error).__name__,message=str(error))
                owner._kill()
            result['owned_process_reaped'] = owner.process.poll() is not None
            result['owned_exit_code'] = owner.process.poll()
        result['whole_controller_ns'] = time.perf_counter_ns()-start
        result['asset_sha256_after'] = sha(plan['asset'])
        result['product_source_drift'] = [row['path'] for row in plan['product_manifest'] if sha(ROOT/row['path']) != row['sha256']]
        result['helper_sha256_after'] = sha(HELPER)
        result['status'] = 'five_state_batch_completed' if len(result['states'])==5 and result['primary_error'] is None else 'incomplete_no_replay'
        save(OUT/'RESULTS.json', result)
        print(json.dumps(result, indent=2))
    if result['primary_error'] is not None: raise SystemExit(1)


if __name__ == '__main__':
    {'prepare': prepare, 'run': run}[sys.argv[1]]()
