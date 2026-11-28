"""Run a single frozen A/B of nearest-surface first focus using owned Blender and MCP."""
import argparse
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import registration_replay as registry_fixture
from registration import encode, fingerprint, registration_scope

diag = registry_fixture.old.diagnostic
pipeline, prior = diag.pipeline, diag.prior
need, pin, read, save, confirm = diag.need, diag.pin, diag.read, diag.save, diag.confirm
BATCH = registry_fixture.BATCH
ORDER = ('A', 'B')
LABELS = ('K', 'T')
PLAN = 'preflight/FORMAL_PLAN.json'
COLD = 'preflight/FORMAL_COLD.json'
PHASE1 = 'preflight/PHASE1_ACCEPTANCE.json'
FINAL = 'preflight/FROZEN_EXECUTION.json'


def phase1(root):
    gate = read(root / PHASE1)
    need(gate['batch'] == BATCH and gate['passed'] is True and gate['real_registration_completed'] == 2
         and gate['negative_controls_without_product_dispatch'] == 7
         and gate['models'] == gate['Blender'] == 0
         and gate['budgets'] == {'candidate_builds': 1, 'isolated_installs': 1, 'formal_Blender': 2,
             'formal_business': 4, 'rasters_per_request': 2, 'substitutes': 0}, 'phase1_gate_not_accepted')
    evidence = {confirm(record) for record in gate['pins']}
    need({root/'preflight/ADMIN_PLAN.md', root/'preflight/CLOSE_RESULT.json',
          root/'preflight/registration/RESULT.json'} <= evidence, 'unbound_phase1_evidence')
    return pin(root / PHASE1)


def prepare(root):
    gate = phase1(root)
    source, freeze, scene, expected, initial = registry_fixture.source_custody(root)
    old = diag.frozen(source)
    a = old['jobs']['DIAGNOSTIC']
    fixture = confirm(a['fixture'])
    candidate_path = root / 'preflight/CANDIDATE_INSTALL_CUSTODY.json'
    custody = read(candidate_path)
    need(custody['passed'] is True and custody['candidate_commit'] != diag.PRODUCT
         and custody['source_sha256'] != a['candidate_source_sha256']
         and custody['runtime_sources'] == len(custody['source_manifest'])
         and custody['python'] == old['python'] and custody['blender'] == old['blender'],
         'unexpected_candidate_install_for_formal_gate')
    for field in ('build', 'wheel', 'python', 'blender'):
        confirm(custody[field])
    for dep in custody['dependencies'].values():
        confirm(dep['module'])
    need(Path(sys.executable).resolve() == Path(custody['python']['path']) and sys.flags.isolated
         and sys.dont_write_bytecode and pin(fixture)['sha256'] == freeze['fixture']['blend']['sha256'],
         'wrong_formal_runtime_or_fixture')
    job_b = {'candidate_site': str(Path(custody['installation']['path']).resolve(strict=True)),
             'candidate_source_sha256': custody['source_sha256'], 'runtime_sources': custody['source_manifest'],
             'candidate_commit': custody['candidate_commit']}
    jobs = {}
    for arm, patch in (('A', {}), ('B', job_b)):
        job = {**a, **patch, 'arm': arm.lower(), 'requests': []}
        for row in expected:
            label, request_id = row['label'], row['id']
            path = source / 'slots/DIAGNOSTIC' / f'{request_id:02d}-{label}.tx'
            packet = copy.deepcopy(read(path))
            if arm == 'B':
                packet['params']['arguments']['query']['focus']['task_region']['relation'] = 'nearest_surface'
            job['requests'].append({'id': request_id, 'label': label, 'request': packet,
                                    'arguments': packet['params']['arguments'], 'old_wire': pin(path)})
        jobs[arm] = job
    floor = root / 'preflight/registration/RESULT.json'
    registered = read(floor)
    need(registered['passed'] is True and registered['product_completed_and_delivered'] == 2
         and registered['rejected_controls_without_product_dispatch'] == 7, 'real_registration_preflight_not_bound')
    tools = [Path(__file__), HERE / 'registration.py', HERE / 'registration_replay.py',
             *(path for path, _ in diag.HELPER_PINS)]
    return {'batch': BATCH, 'jobs': jobs, 'order': list(ORDER), 'phase1': gate,
            'registration_preflight': pin(floor), 'inputs': [pin(p) for p in [*tools, candidate_path]],
            'blender': old['blender'], 'python': old['python'], 'fixture': pin(fixture),
            'limits': {'Blender': 2, 'business': 4, 'raster_per_request': 2, 'models': 0, 'substitutes': 0,
                       'slot_ns': prior.LIMIT_NS}}


def frozen(root):
    recorded = read(root / PLAN)
    need(recorded == prepare(root), 'formal_plan_changed')
    return recorded


def admission(root):
    approved = read(root / FINAL)
    need(approved['batch'] == BATCH and approved['formal_plan'] == pin(root / PLAN)
         and approved['formal_cold'] == pin(root / COLD)
         and approved['phase1'] == phase1(root), 'formal_not_in_unified_freeze')
    gate = read(root / COLD)
    need(gate['passed'] is True and gate['actual_Blender'] == 0 and gate['plan'] == pin(root / PLAN)
         and [s['arm'] for s in gate['slots']] == list(ORDER), 'wrong_formal_cold_receipt')
    for slot in gate['slots']:
        need(slot['exit'] == 0, 'formal_cold_failed_slot')
        for receipt in slot['receipts']:
            confirm(receipt)
    for record in approved.get('inputs', ()):
        confirm(record)
    return pin(root / FINAL)


def subprocess_args(root, arm, mode):
    return [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), str(root), 'worker', arm, mode]


def request_packets(job):
    for i, (label, method, params) in enumerate(prior.sequence(job), 1):
        yield {'id': i, 'jsonrpc': '2.0', 'method': method, 'params': params}


def cold_registry(folder, service, module, job):
    calls = list(request_packets(job))
    incoming = io.StringIO(''.join(encode(req).decode('utf8') + '\n' for req in calls))
    outgoing = io.StringIO()
    accepted = []
    real = service._observe_active_observation

    def reached(session_id, **options):
        permit = recorder.active
        need(permit is not None, 'unregistered_cold_normalization')
        accepted.append({'id': permit['request_id'], 'label': permit['label'], 'options': options})
        recorder.service_event('cold_service_boundary_reached')
        raise ValueError('formal_cold_service_boundary')

    service._observe_active_observation = reached
    try:
        with registration_scope(module, folder/'COLD_ATTEMPTS.jsonl', job['requests']) as recorder:
            module.run_stdio_mcp_server(service, input_stream=incoming, output_stream=outgoing)
    finally:
        service._observe_active_observation = real
    (folder/'REGISTRY.tx').write_bytes(incoming.getvalue().encode())
    (folder/'REGISTRY.rx').write_bytes(outgoing.getvalue().encode())
    save(folder/'COLD_SERVICE.json', accepted)
    replies = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    need([r['id'] for r in replies] == [1, 2, 3, 4]
         and replies[0]['result']['_meta']['human_eye']['source_sha256'] == job['candidate_source_sha256'],
         'wrong_actual_formal_registry')
    tool, = [i for i in replies[1]['result']['tools'] if i['name'] == 'human_eye_scene_observe']
    focus = tool['inputSchema']['properties']['query']['properties']['focus']
    need(('nearest_surface' in json.dumps(focus)) == (job['arm'] == 'b'), 'wrong_model_visible_focus_relation')
    need([case['label'] for case in accepted] == list(LABELS)
         and all([case['options']['selector']] == row['arguments']['query']['objects']
                 and case['options']['focus'] == row['arguments']['query']['focus']
                 and case['options']['include_image'] is True
                 for case, row in zip(accepted, job['requests'], strict=True))
         and all('formal_cold_service_boundary' in r['result']['content'][0]['text'] for r in replies[2:]),
         'registered_requests_did_not_reach_expected_cold_boundary')


def observe_slot(folder, service, module, images, task_query, host, job):
    real_observe = service._observe_active_observation
    real_capture = host.capture_scene
    real_raster = images.rasterize_attention
    real_solve = task_query.measure_surface_proximity
    active = None

    def operation(kind, fn, *args, **kwargs):
        need(active is not None, 'operation_without_registered_service_request/' + kind)
        events = active[kind]
        if kind == 'raster_calls' and len(events) >= 2:
            active['limit_exceeded'] = True
            raise ValueError('formal_raster_budget')
        event = {'started_ns': time.perf_counter_ns(), 'completed': False}
        events.append(event)
        try:
            value = fn(*args, **kwargs)
            event['completed'] = True
            return value
        finally:
            event['closed_ns'] = time.perf_counter_ns()

    def capture(*args, **kwargs):
        if active is None:
            return real_capture(*args, **kwargs)
        return operation('capture_calls', real_capture, *args, **kwargs)

    def raster(*args, **kwargs):
        return operation('raster_calls', real_raster, *args, **kwargs)

    def solve(*args, **kwargs):
        return operation('m3_actual_solver_calls', real_solve, *args, **kwargs)

    def observed(session_id, *, include_image, selector=None, task_query=None, region_task=None, focus=None):
        nonlocal active
        permit = recorder.active
        need(permit is not None and active is None, 'product_observation_without_sole_registration')
        expected, = [row for row in job['requests'] if row['id'] == permit['request_id']]
        wanted = expected['arguments']
        need(include_image is wanted['include_image'] and [selector] == wanted['query']['objects']
             and focus == wanted['query']['focus'] and task_query is None and region_task is None,
             'actual_normalized_formal_request_drift')
        key, label = expected['id'], expected['label']
        active = {'id': key, 'label': label, 'service_started_ns': time.perf_counter_ns(),
                  'raster_calls': [], 'capture_calls': [], 'm3_actual_solver_calls': [], 'limit_exceeded': False}
        recorder.service_event('product_service_started', selector=selector, focus=focus)
        try:
            result = real_observe(session_id, include_image=include_image, selector=selector, focus=focus)
            active['service_returned_ns'] = time.perf_counter_ns()
            product_path = folder / f'producer_{key:02d}.json'
            save(product_path, result)
            active['result_recorded'] = True
            recorder.service_event('product_service_returned', producer=pin(product_path))
            return result
        finally:
            active.setdefault('service_returned_ns', time.perf_counter_ns())
            save(folder / f'construction_{key:02d}.json', active)
            active = None

    service._observe_active_observation = observed
    host.capture_scene = capture
    images.rasterize_attention = raster
    task_query.measure_surface_proximity = solve
    try:
        with registration_scope(module, folder / 'REGISTRATION_ATTEMPTS.jsonl', job['requests']) as recorder:
            module.run_stdio_mcp_server(service)
    finally:
        host.capture_scene = real_capture
        service._observe_active_observation = real_observe
        images.rasterize_attention = real_raster
        task_query.measure_surface_proximity = real_solve


def worker(root, arm, mode):
    settings = frozen(root)
    job = settings['jobs'][arm]
    folder = root / 'slots' / arm if mode == 'formal' else root / 'preflight/formal_cold' / arm
    if mode == 'formal':
        start, registered = read(root / 'FORMAL_START.json'), read(folder / 'REGISTERED.json')
        need(start['freeze'] == admission(root) and arm in start['order']
             and registered['slot'] == arm and registered['planned'] == job['requests'], 'formal_child_not_registered')
    fixture = prior.copied_input(folder, job)
    site = Path(job['candidate_site'])
    sys.path.insert(0, str(site))
    from human_eye_plugin import active_observation_images, blender_process, live_spatial_mcp, task_query
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    need(identity['source_kind'] == 'installed_distribution'
         and identity['source_sha256'] == job['candidate_source_sha256']
         and identity['source_files'] == job['runtime_sources']
         and Path(blender_process.__file__).resolve().parent.parent == site, 'formal_worker_source_drift')
    config = folder / 'config.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                  'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': identity['source_sha256']}})
    if mode == 'cold':
        cold_registry(folder, LiveSpatialService(config, host=object(), production_mode=True), live_spatial_mcp, job)
    launch = pipeline.Launch(folder, mode, {**settings, 'candidate_site': str(site)}, fixture)
    real = blender_process.subprocess
    blender_process.subprocess = launch
    host, post, failure = None, None, None
    begin = time.perf_counter_ns()
    try:
        try:
            host = blender_process.BlenderProcessHost(settings['blender']['path'], fixture,
                                                       timeout=25, startup_timeout=45)
        except prior.AtReservation:
            need(mode == 'cold' and launch.process is None, 'incorrect_no_launch_boundary')
            return 0
        need(mode == 'formal' and launch.process is host._process, 'non_owned_formal_process')
        service = LiveSpatialService(config, host=host, production_mode=True)
        save(folder / 'ready.json', {'pid': host._process.pid, 'startup_ns': time.perf_counter_ns() - begin,
             'source_sha256': identity['source_sha256'], 'source_files': len(identity['source_files']),
             'source_kind': identity['source_kind'], 'fixture_before': diag.digest(fixture),
             'asset': job['asset'], 'arm': job['arm']})

        def finish():
            nonlocal post
            before = time.perf_counter_ns()
            value = host.capture_scene()
            after = time.perf_counter_ns()
            packet = folder / 'post_capture.json'
            save(packet, value)
            post = {'started_ns': before, 'closed_ns': after, 'path': pin(packet)}

        service.close = finish
        observe_slot(folder, service, live_spatial_mcp, active_observation_images, task_query, host, job)
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        blender_process.subprocess = real
        if mode == 'formal':
            before_close = time.perf_counter_ns()
            proc = launch.process
            try:
                if host is not None:
                    host.close()
                elif proc is not None:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=3)
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        if stream is not None:
                            try:
                                stream.close()
                            except (OSError, ValueError):
                                pass
                if launch.wire is not None:
                    launch.wire.publish()
            finally:
                save(folder / 'closed.json', {'pid': proc.pid if proc else None,
                     'blender_exit': proc.poll() if proc else None, 'native_spawned': proc is not None,
                     'fixture_after': diag.digest(fixture), 'closed_ns': time.perf_counter_ns(),
                     'native_close_started_ns': before_close, 'post_capture': post, 'failure': failure})
    return 0


def cold(root):
    settings = frozen(root)
    reports = []
    for arm in settings['order']:
        folder = root / 'preflight/formal_cold' / arm
        folder.mkdir(parents=True)
        with (folder / 'stdout.bin').open('xb') as output, (folder / 'stderr.bin').open('xb') as errors:
            try:
                result = subprocess.run(subprocess_args(root, arm, 'cold'), cwd=folder, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=errors, env=prior.process_env(),
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=45)
                status = result.returncode
            except subprocess.TimeoutExpired:
                status = None
        spawn = (folder / 'Blender_SPAWN.json').is_file()
        appointment = folder / 'AT_APPOINTMENT.json'
        files = ('stdout.bin', 'stderr.bin', 'REGISTRY.tx', 'REGISTRY.rx', 'COLD_SERVICE.json',
                 'COLD_ATTEMPTS.jsonl', 'AT_APPOINTMENT.json')
        receipts = [pin(folder / name) for name in files if (folder / name).is_file()]
        passed = status == 0 and len(receipts) == len(files) and not spawn and not (folder / 'stdout.bin').stat().st_size
        if passed:
            receipt = read(appointment)
            passed = (receipt['attempt'] is False and receipt['geometry_preflight_reads'] == 0
                      and receipt['fixture']['sha256'] == settings['fixture']['sha256'])
        reports.append({'arm': arm, 'exit': status, 'passed': passed, 'Blender_spawned': spawn, 'receipts': receipts})
    save(root / COLD, {'passed': all(r['passed'] for r in reports),
         'actual_Blender': sum(r['Blender_spawned'] for r in reports), 'slots': reports, 'plan': pin(root / PLAN)})
    return int(not all(r['passed'] for r in reports))


def registration_admission(folder, job, ledger):
    evidence = folder / 'REGISTRATION_ATTEMPTS.jsonl'
    events = [json.loads(row) for row in evidence.read_bytes().splitlines()]
    expected = {'attempt_registered', 'product_dispatch_started', 'product_service_started',
                'product_service_returned', 'product_dispatch_returned'}
    for phase in expected:
        need([r['label'] for r in events if r['phase'] == phase] == list(LABELS), 'registered_product_sequence/' + phase)
    need(len(events) == len(expected) * len(LABELS), 'extra_registered_product_attempts')
    rows = {}
    for row, model in zip(ledger['requests'][2:], job['requests'], strict=True):
        label, key = row['label'], row['id']
        prefix = folder / f'{key:02d}-{label}'
        tx, rx = prefix.with_suffix('.tx'), prefix.with_suffix('.rx')
        related = [r for r in events if r['label'] == label]
        terminal = related[-1]
        need(row['status'] == 'returned' and read(tx) == model['request']
             and (job['arm'] != 'a' or tx.read_bytes() == confirm(model['old_wire']).read_bytes())
             and all(r['registered'] and r['request_id'] == key and r['request_sha256'] == fingerprint(read(tx)) for r in related)
             and terminal['phase'] == 'product_dispatch_returned' and not terminal['product_is_error']
             and terminal['product_reply_sha256'] == fingerprint(read(rx)), 'split_formal_registration_custody')
        metered = read(folder / f'construction_{key:02d}.json')
        rows[label] = {'id': key, 'tx': pin(tx), 'rx': pin(rx),
                       'm3_actual_solver_calls': len(metered['m3_actual_solver_calls']),
                       'capture_calls': len(metered['capture_calls']), 'raster_calls': len(metered['raster_calls'])}
    return {'passed': True, 'attempts': pin(evidence), 'dispatches': rows}


def formal(root):
    settings = frozen(root)
    approved = admission(root)
    start = {'order': list(ORDER), 'freeze': approved, 'started_ns': time.perf_counter_ns(),
             'max_Blender': 2, 'max_business': 4, 'max_rasters_per_request': 2}
    save(root / 'FORMAL_START.json', start)
    (root / 'slots').mkdir(exist_ok=False)
    results = []
    try:
        for arm in ORDER:
            folder = root / 'slots' / arm
            outcome = pipeline.run_slot(root, arm, settings)
            results.append(outcome)
            if outcome['status'] == 'closed':
                try:
                    receipt = registration_admission(folder, settings['jobs'][arm], outcome)
                except Exception as error:
                    receipt = {'passed': False, 'reason': str(error)}
                    outcome['status'] = 'failed'
                    outcome['issues'].append({'reason': 'registered_product_custody/' + str(error)})
            else:
                receipt = {'passed': False, 'reason': 'outer_lifecycle_failed'}
            save(folder / 'REGISTRATION_ADMISSION.json', receipt)
            if not outcome['safe_to_continue']:
                break
    except BaseException as error:
        results.append({'slot': arm, 'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc()})
    finally:
        save(root / 'FORMAL_EXECUTION.json', {'batch': BATCH, 'freeze': approved,
             'slots': results, 'unrun_slots': [name for name in ORDER if name not in {r['slot'] for r in results}],
             'closed_ns': time.perf_counter_ns(), 'models': 0, 'substitutes': 0})
    return int(len(results) != 2 or any(r['status'] != 'closed' for r in results))


prior.child_args = subprocess_args

if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root', type=lambda path: Path(path).resolve(strict=True))
    cli.add_argument('action', choices=('plan', 'cold', 'formal', 'worker'))
    cli.add_argument('arm', nargs='?', choices=ORDER)
    cli.add_argument('mode', nargs='?', choices=('cold', 'formal'))
    options = cli.parse_args()
    if options.action == 'plan':
        save(options.root / PLAN, prepare(options.root))
    elif options.action == 'cold':
        raise SystemExit(cold(options.root))
    elif options.action == 'formal':
        raise SystemExit(formal(options.root))
    else:
        need(options.arm and options.mode, 'formal_worker_action_requires_arm_and_mode')
        raise SystemExit(worker(options.root, options.arm, options.mode))
