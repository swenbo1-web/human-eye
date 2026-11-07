"""Prepare, then run one frozen three-state NativeSession; never retry a state."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import types
from types import MappingProxyType

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
OUT = FOLDER / 'run_01'
HELPER = Path('D:/hefe/verification/fixes/20261106_perf010_r2/installed/verification/visual004_native.py')
HELPER_SHA = '5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3'
ASSET_SHA = '9a7671bb202720b09311f313363bc0e5267017f2af155a9167fff4cf2d96d1b6'
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
ASSIGNMENT = Path('D:/hefe/verification/fixes/20261107_nearest_contract/NEAREST_INTEGRATION_ASSIGNMENT.md')
ASSIGNMENT_SHA = '24285d0b8c5a004064ab5b8893bb9fd4939cefcb7d3d77f573cd197226d8d69b'
DEADLINE = datetime(2026, 11, 7, 15, 40, tzinfo=timezone.utc)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def check_sources(plan):
    for row in plan['product_manifest']:
        assert sha(ROOT/row['path']) == sha(Path(plan['source_root'])/row['path']) == row['sha256'], row['path']


def prepare(args):
    assert not OUT.exists(), 'single_frozen_run_no_retry'
    assert sha(ASSIGNMENT) == ASSIGNMENT_SHA
    identity = json.loads(args.identity.read_bytes())
    identity = identity.get('identity', identity)
    manifest = identity.get('source_files', identity.get('files'))
    manifest = sorted([{'path': r['path'], 'sha256': r['sha256']} for r in manifest], key=lambda r: r['path'])
    product_sha = identity.get('candidate_source_sha256', identity.get('source_sha256'))
    assert len(manifest) == 131 and len(product_sha) == 64
    # Require a committed unique product candidate; QA/report files may remain unstaged.
    candidate_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    blobs = {}
    for row in manifest:
        blob = (ROOT/row['path']).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == row['sha256']
        assert subprocess.check_output(['git', 'show', candidate_commit+':'+row['path']], cwd=ROOT) == blob
        blobs[row['path']] = blob
    offline = json.loads(args.offline_proof.read_bytes())
    assert offline.get('passed') is True or offline.get('successful') is True, 'offline_pass_required'
    assert offline.get('runtime_source_sha256', offline.get('candidate_source_sha256', offline.get('source_sha256'))) == product_sha, 'offline_candidate_identity_mismatch'
    assert sha(HELPER) == HELPER_SHA
    assets_path = ROOT/'verification/m4_capture_qa_001/run_01/assets/ASSETS.json'
    asset = next(r for r in json.loads(assets_path.read_bytes())['cases'] if r['case']=='far_second_degenerate')
    assert sha(asset['asset']) == asset['sha256'] == ASSET_SHA
    registration = json.loads((FOLDER/'PREREGISTRATION.json').read_bytes())
    assert registration['asset_sha256'] == ASSET_SHA
    assert registration['asset_recipe'] == asset['recipe']
    assert sha(args.blender) == BLENDER_SHA
    state = json.loads(Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json').read_bytes())
    window = state['performance_window']
    assert window['token'] == 'NEAREST-INTEGRATION-001-ONLY' and window['max_sessions'] == 1 and window['max_RPC'] == 4
    OUT.mkdir()
    source_root = OUT/'sources'
    for name, blob in blobs.items():
        target = source_root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    plan = dict(root=str(ROOT), source_root=str(source_root), candidate_commit=candidate_commit,
        source_sha256=product_sha, product_manifest=manifest,
        host_sha256=sha(source_root/'human_eye_plugin/blender_host.py'),
        blender=str(args.blender), blender_sha256=BLENDER_SHA,
        asset=asset['asset'], asset_sha256=ASSET_SHA, asset_recipe=asset['recipe'],
        static_object_ids=registration['object_ids'], helper=str(HELPER), helper_sha256=HELPER_SHA,
        assignment_sha256=ASSIGNMENT_SHA, window=window,
        offline_proof=dict(path=str(args.offline_proof), sha256=sha(args.offline_proof)),
        preregistration_sha256=sha(FOLDER/'PREREGISTRATION.json'),
        max_sessions=1, max_state_RPC=3, max_close_RPC=1, max_total_RPC=4,
        original_worker_seconds=600, cleanup_reserve_seconds=60,
        original_asset_write=False, retries=0, prepared_utc=datetime.now(timezone.utc).isoformat())
    save(OUT/'PLAN.json', plan)
    freeze = dict(plan_sha256=sha(OUT/'PLAN.json'),
        controllers=[dict(path=str(FOLDER/name), sha256=sha(FOLDER/name)) for name in
                     ('controller.py', 'worker_body.py', 'PREREGISTRATION.json')],
        no_session_started=True)
    save(OUT/'FREEZE.json', freeze)
    print(json.dumps(dict(status='prepared_no_session_started', candidate_commit=candidate_commit,
                         source_sha256=product_sha, freeze_sha256=sha(OUT/'FREEZE.json'))))


class MeterSocket:
    def __init__(self, sock, folder, meter):
        self.sock, self.folder, self.meter = sock, folder, meter
    def __getattr__(self, key): return getattr(self.sock, key)
    def __enter__(self): return self
    def __exit__(self, *args): return self.sock.__exit__(*args)
    def sendall(self, raw):
        with (self.folder/'TX.bin').open('ab') as stream: stream.write(raw)
        self.meter['send_attempted_bytes'] += len(raw)
        value = self.sock.sendall(raw)
        self.meter['send_completed_bytes'] += len(raw)
        return value
    def recv(self, size):
        raw = self.sock.recv(size)
        with (self.folder/'RX.bin').open('ab') as stream: stream.write(raw)
        self.meter['received_bytes'] += len(raw)
        return raw


def client_entry(plan):
    root = Path(plan['source_root'])
    blobs = MappingProxyType({row['path']: (root/row['path']).read_bytes() for row in plan['product_manifest']})
    loader_path = root/'human_eye_plugin/verified_source_loader.py'
    loader = types.ModuleType('_nearest_client_loader'); loader.__file__ = str(loader_path)
    sys.modules[loader.__name__] = loader
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec', dont_inherit=True), loader.__dict__)
    guard = loader.install(root, plan['product_manifest'], sources=blobs, bootstrap_module=loader)
    package = types.ModuleType('human_eye_plugin'); package.__path__ = [str(root/'human_eye_plugin')]
    guard.allow_namespace(package); sys.modules[package.__name__] = package
    from human_eye_plugin import task_query, surface_proximity, runtime_identity
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.live_service import RequestBudgetError
    assert runtime_identity.runtime_identity()['source_sha256'] == plan['source_sha256']
    assert runtime_identity.check_task_source()['compatible']
    assert callable(task_query.surface_nearest_result)
    assert guard.verify_loaded()
    cache = SpatialSceneCache()
    def summarize(packet):
        counts = dict(pair_calls=0, kernel_calls=0, nearest_calls=0, rank_calls=0,
                      pair_ids=[], kernel_pair_ids=[])
        originals = []
        def instrument(owner, name, count):
            original = getattr(owner, name)
            def call(*args, **kwargs):
                counts[count] += 1
                if count in ('pair_calls', 'kernel_calls'):
                    left = args[0] if args else kwargs['left']
                    right = args[1] if len(args)>1 else kwargs['right']
                    counts['pair_ids' if count=='pair_calls' else 'kernel_pair_ids'].append([left.object_id, right.object_id])
                return original(*args, **kwargs)
            originals.append((owner, name, original))
            setattr(owner, name, call)
        instrument(task_query, '_surface_pair_measurement', 'pair_calls')
        instrument(task_query, 'measure_surface_proximity', 'kernel_calls')
        instrument(surface_proximity, 'measure_surface_proximity', 'kernel_calls')
        instrument(surface_proximity, '_nearest', 'nearest_calls')
        # The task entry imports the private ranker directly.
        if hasattr(task_query, '_rank_surface_results'):
            instrument(task_query, '_rank_surface_results', 'rank_calls')
        instrument(surface_proximity, '_rank_surface_results', 'rank_calls')
        def checkpoint(stage):
            if time.perf_counter_ns() >= plan['deadline_ns']:
                raise RequestBudgetError('expired', stage)
        diagnostics = {}
        before = cache.stats()
        result = None; summary_error = None
        try:
            checkpoint('nearest_QA_before_summary')
            result = task_query.surface_nearest_result(packet, cache, checkpoint, diagnostics=diagnostics)
            checkpoint('nearest_QA_after_summary')
        except BaseException as error:
            summary_error = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        finally:
            for owner, name, original in reversed(originals): setattr(owner, name, original)
        validation = {}
        try:
            if summary_error is None:
                expected_pairs = {(packet['focal_id'], row['object_id']) for row in packet['capture']['meshes'] if row['object_id'] != packet['focal_id']}
                validation = dict(private_key_not_projected='_exact_distance_sq' not in json.dumps(result),
                    rank_called_once=counts['rank_calls']==1,
                    no_extra_solves=counts['kernel_calls']<=counts['pair_calls'] and counts['nearest_calls']<=counts['kernel_calls'],
                    each_retained_pair_once=set(map(tuple,counts['pair_ids']))==expected_pairs and len(counts['pair_ids'])==len(expected_pairs),
                    kernel_pairs_are_retained=set(map(tuple,counts['kernel_pair_ids']))<=expected_pairs,
                    at_most_one_kernel_per_pair=len(set(map(tuple,counts['kernel_pair_ids'])))==len(counts['kernel_pair_ids']))
            validation['guard_verify_loaded'] = bool(guard.verify_loaded())
        except BaseException as error:
            if summary_error is None:
                summary_error = dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
        return dict(result=result, counts=counts, diagnostics=diagnostics,
                    cache_before=before, cache_after=cache.stats(), summary_error=summary_error, validation=validation)
    def witness():
        assert guard.verify_loaded()
        owned = {n: m for n,m in sys.modules.items() if guard._owned_name(n)}
        return dict(guard_protocol=guard.protocol, source_sha256=plan['source_sha256'],
            loaded_engine_module_count=len(owned),
            every_loaded_module_has_execution_or_namespace_witness=all(
                guard._executed.get(id(m), (None,))[0] is m or guard._namespaces.get(id(m)) is m for m in owned.values()),
            bound_generation=runtime_identity.check_task_source())
    return summarize, witness


def check_answer(state, public, plan):
    ids = plan['static_object_ids']; near = ids['M4_Near']; far = ids['M4_Far_00']
    assert public['scope'] == 'surface_nearest_candidates'
    if state in (1, 2):
        assert public['status'] == 'complete'
        assert public['nearest_ids'] == [near if state == 1 else far]
        assert public['distance_m'] == (2. if state == 1 else .25)
        assert not public['unresolved']
    else:
        assert public['status'] == 'partial' and public['nearest_ids'] is None and public['distance_m'] is None
        assert public['best_known_ids'] == [near] and public['best_known_distance_m'] == 2.
        assert public['unresolved'][far] == 'surface_degenerate_triangle'
    c = public['coverage']; assert c['targets_excluding_focal'] == 2
    assert (c['distance_valid'], c['strictly_excluded'], c['unresolved']) == ((1,1,0) if state==1 else (2,0,0) if state==2 else (1,0,1))
    if state == 1:
        excluded, = public['excluded']
        assert excluded['status'] == 'not_evaluated_pruned'
        assert 'distance_m' not in excluded and 'topology' not in excluded


def run(args):
    plan = json.loads((OUT/'PLAN.json').read_bytes()); freeze = json.loads((OUT/'FREEZE.json').read_bytes())
    assert sha(OUT/'PLAN.json') == freeze['plan_sha256']
    for row in freeze['controllers']: assert sha(row['path']) == row['sha256']
    assert not (OUT/'STARTED.json').exists(), 'no_second_session_or_retry'
    assert datetime.now(timezone.utc) < DEADLINE-timedelta(seconds=660), 'leave_600s_plus_60s_cleanup'
    check_sources(plan)
    assert sha(HELPER) == HELPER_SHA and sha(plan['asset']) == ASSET_SHA
    plan['start_ns'] = time.perf_counter_ns(); plan['deadline_ns'] = plan['start_ns']+600_000_000_000
    save(OUT/'RUNTIME_PLAN.json', plan)
    body = (FOLDER/'worker_body.py').read_text('utf8')
    scripts = []
    for state in (1, 2, 3):
        code = 'STATE = '+str(state)+'\nPLAN = '+repr(plan)+'\n'+body
        compile(code, '<nearest-frozen-state-'+str(state)+'>', 'exec')
        assert len(code.encode()) <= 256*1024
        path = OUT/('STATE_'+str(state)+'.py'); path.write_bytes(code.encode())
        scripts.append(dict(state=state, path=str(path), sha256=sha(path)))
    save(OUT/'RUNTIME_FREEZE.json', dict(plan_sha256=sha(OUT/'RUNTIME_PLAN.json'), scripts=scripts))
    summarize, source_witness = client_entry(plan)
    native = types.ModuleType('_nearest_qa_native'); native.__file__ = str(HELPER)
    sys.modules[native.__name__] = native
    exec(compile(HELPER.read_bytes(), str(HELPER), 'exec', dont_inherit=True), native.__dict__)
    owner = None
    record = dict(states=[], state_attempts=[], primary_error=None, owned_sessions_attempted=0, transport_attempts=0,
                  capture_calls=0, cleanup=None, started_utc=datetime.now(timezone.utc).isoformat(),
                  zero_performance_samples=True, zero_model_consumers=True, retries=0)
    begun = time.perf_counter_ns()
    def transaction(name, call):
        folder = OUT/name; folder.mkdir()
        meter = dict(send_attempted_bytes=0, send_completed_bytes=0, received_bytes=0)
        original = native.socket.create_connection
        def connect(*args, **kwargs): return MeterSocket(original(*args, **kwargs), folder, meter)
        record['transport_attempts'] += 1; native.socket.create_connection = connect
        start = time.perf_counter_ns()
        try:
            response = call(); save(folder/'RESPONSE.json', response); return response
        finally:
            native.socket.create_connection = original
            save(folder/'TRANSPORT.json', dict(**meter, elapsed_ns=time.perf_counter_ns()-start))
    save(OUT/'STARTED.json', dict(at_ns=begun, runtime_freeze_sha256=sha(OUT/'RUNTIME_FREEZE.json')))
    try:
        record['owned_sessions_attempted'] = 1
        owner = native.NativeSession.start(blender=plan['blender'], asset=plan['asset'], workspace=OUT/'owned',
            deadline_ns=plan['deadline_ns'], expected_asset_sha256=ASSET_SHA, max_calls=3)
        record['ready'] = owner.ready
        assert owner.ready['pid'] == owner.process.pid and owner.ready['helper_sha256'] == HELPER_SHA
        for row in scripts:
            assert sha(row['path']) == row['sha256']
            attempt = dict(state=row['state'], entered_utc=datetime.now(timezone.utc).isoformat())
            record['state_attempts'].append(attempt)
            receipt = transaction('rpc_'+str(row['state']), lambda: owner.run(Path(row['path']).read_text('utf8'), timeout_s=75))
            attempt['response_status'] = receipt['response'].get('status')
            assert receipt['response'].get('status') == 'success', 'state_RPC_error_no_replay'
            state_file = OUT/'owned'/('state_'+str(row['state']))/'STATE_RESULT.json'
            worker = json.loads(state_file.read_bytes())
            item = dict(state=row['state'], worker_file=str(state_file), worker_sha256=sha(state_file))
            record['states'].append(item)
            record['capture_calls'] += int(worker.get('capture_called') is True)
            assert worker['primary_error'] is None and worker['restored'] is True
            assert worker['same_native_geometry_before_after_capture'] is True
            assert worker['capture_called'] and worker['capture']['status'] == 'returned'
            packet = json.loads((state_file.parent/'CAPTURE.json').read_bytes())
            item.update(summarize(packet))
            save(OUT/('SUMMARY_'+str(row['state'])+'.json'), item)
            assert item['summary_error'] is None, 'summary_failed_no_replay'
            assert all(item['validation'].values()), 'summary_validation_failed_no_replay'
            check_answer(row['state'], item['result'], plan)
            item['independent_answer_passed'] = True
    except BaseException as error:
        record['primary_error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    finally:
        if owner is not None:
            try: record['cleanup'] = transaction('rpc_close', owner.close)
            except BaseException as error:
                record['cleanup_error'] = dict(type=type(error).__name__, message=str(error)); owner._kill()
            record['owned_process_reaped'] = owner.process.poll() is not None
            record['owned_exit_code'] = owner.process.poll()
        record['whole_controller_ns'] = time.perf_counter_ns()-begun
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        record['asset_sha256_after'] = sha(plan['asset'])
        record['helper_sha256_after'] = sha(HELPER)
        record['unrun_states'] = [s for s in (1,2,3) if s not in {r['state'] for r in record['state_attempts']}]
        record['attempted_states_without_worker_receipt'] = [r['state'] for r in record['state_attempts'] if r['state'] not in {s['state'] for s in record['states']}]
        record['product_source_drift'] = [r['path'] for r in plan['product_manifest'] if sha(ROOT/r['path']) != r['sha256']]
        try: record['client_execution_witness'] = source_witness()
        except BaseException as error:
            record['client_witness_error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        cleanup = record.get('cleanup') or {}
        record['passed'] = bool(len(record['states'])==3 and record['primary_error'] is None
            and not record.get('client_witness_error') and not record['product_source_drift']
            and record.get('client_execution_witness',{}).get('every_loaded_module_has_execution_or_namespace_witness')
            and record.get('client_execution_witness',{}).get('bound_generation',{}).get('compatible')
            and record['asset_sha256_after']==ASSET_SHA and record.get('owned_process_reaped')
            and record['helper_sha256_after']==HELPER_SHA
            and record.get('owned_exit_code')==0 and cleanup.get('error') is None
            and (cleanup.get('response') or {}).get('status')=='closed'
            and cleanup.get('source_file_unchanged') and cleanup.get('protected_files_unchanged'))
        record['status'] = 'three_state_batch_completed' if record['passed'] else 'incomplete_no_replay'
        save(OUT/'RESULTS.json', record); print(json.dumps(record, indent=2))
    if not record['passed']: raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--identity', type=Path, required=True)
    p.add_argument('--offline-proof', type=Path, required=True); p.add_argument('--blender', type=Path, default=Path('D:/Tools/blender5.2/blender.exe'))
    sub.add_parser('run')
    args = parser.parse_args(); {'prepare': prepare, 'run': run}[args.command](args)
