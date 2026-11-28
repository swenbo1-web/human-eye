"""Run the frozen four-slot task-focus experiment through the installed MCP and worker."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from worker_wire import WorkerWire

PRIOR = HERE.parent / 'm4_directed_focus_assembly_holdout_001/harness.py'
spec = importlib.util.spec_from_file_location('prior_directed_focus_runner', PRIOR)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
need, read, save, pin, confirm, digest, sha = (prior.need, prior.read, prior.save, prior.pin,
                                             prior.confirm, prior.digest, prior.sha)
need(digest(PRIOR) == '3fd1a0ffa770c043c8d1d29083bedcf6901c6a000545b50014d4f0889a89ba5f',
     'reused_runner_identity')
PRODUCT, SOURCE, WHEEL, PYTHON, BLENDER = prior.PRODUCT, prior.SOURCE, prior.WHEEL, prior.PYTHON, prior.BLENDER
BATCH = 'M4-TASK-REGION-FOCUS-FEEDBACK-001'
ADMIN = '6f4baec050d258f8f934dfdb23350610c132a53ffc00047c7ed1068d4a08ea28'
TASK_INPUTS = '62a022cea2cc8f820ea8eaecc7d4750e69ed90d545d6c5fd31dda6592441d93c'
ORDER = ('RAIL_AUTO', 'RAIL_TASK', 'ASSEMBLY_AUTO', 'ASSEMBLY_TASK')


def installed(root, name):
    path = root / 'preflight' / (name + '_INSTALL_CUSTODY.json')
    value = read(path)
    need(value['passed'] and value['python']['sha256'] == PYTHON and value['blender']['sha256'] == BLENDER,
         'wrong_frozen_product_binary')
    for key in ('wheel', 'build', 'python', 'blender'):
        confirm(value[key])
    need(Path(sys.executable).resolve() == Path(value['python']['path']), 'wrong_frozen_interpreter')
    expected = (PRODUCT, SOURCE, WHEEL)
    actual = (value['candidate_commit'], value['source_sha256'], value['wheel']['sha256'])
    if name == 'BASELINE':
        need(actual == expected and value['runtime_sources'] == 146, 'wrong_fixed_baseline')
    else:
        build = read(value['build']['path'])
        need(all(x != y for x, y in zip(actual, expected)) and build['parent_commit'] == PRODUCT
             and build['candidate_commit'] == actual[0] and build['runtime_identity']['source_sha256'] == actual[1]
             and build['wheel'] == value['wheel'] and build['builds'] == build['installs'] == 1
             and value['runtime_sources'] == len(value['source_manifest']), 'wrong_sole_candidate')
    return value, pin(path)


def prepare(root):
    admin = confirm({'path': str((root / 'preflight/ADMIN_PLAN.md').resolve()), 'sha256': ADMIN,
                     'bytes': (root / 'preflight/ADMIN_PLAN.md').stat().st_size})
    path = root / 'preflight/TASK_INPUTS.json'
    need(root.name == BATCH and digest(path) == TASK_INPUTS and sys.flags.isolated and sys.dont_write_bytecode,
         'wrong_record_or_interpreter')
    inputs = read(path)
    need(inputs['passed'] and inputs['admin_plan_sha256'] == ADMIN
         and inputs['task_order'] == ['M19', 'M21', 'N19', 'N25'], 'task_input_record')
    truth = confirm(inputs['prior_labels'])
    prompts = [pin(confirm(value)) for value in inputs['prompts'].values()]
    baseline, base_receipt = installed(root, 'BASELINE')
    candidate, candidate_receipt = installed(root, 'CANDIDATE')
    need(baseline['blender'] == candidate['blender']
         and baseline['dependencies'] == candidate['dependencies'], 'asymmetric_native_runtime')
    for dep in baseline['dependencies'].values():
        confirm(dep['module'])
    jobs = {}
    for slot in ORDER:
        asset, arm = slot.split('_')
        custody = baseline if arm == 'AUTO' else candidate
        fixture_input = inputs['assets'][asset.lower()]['asset']
        fixture = pin(fixture_input['path'])
        need(all(fixture[k] == fixture_input[k] for k in ('bytes', 'sha256')), 'fixture_changed')
        jobs[slot] = {'asset': asset, 'arm': arm.lower(), 'fixture': fixture,
                      'candidate_site': str(Path(custody['installation']['path']).resolve(strict=True)),
                      'candidate_source_sha256': custody['source_sha256'],
                      'runtime_sources': custody['source_manifest'],
                      'candidate_commit': custody['candidate_commit'], 'requests': []}
        for index, label in enumerate(prior.TOPICS[asset], 3):
            task = inputs['tasks'][label]
            need(set(task) == {'asset', 'target', 'reference', 'world_box_m'}
                 and task['asset'] == asset.lower() and task['target'] == label
                 and task['reference'] != label, 'frozen_task_has_unexpected_input')
            focus = 'auto' if arm == 'AUTO' else {'task_region': {
                'reference': {'name': task['reference']}, 'world_box_m': task['world_box_m']}}
            arguments = {'query': {'mode': 'active_observation', 'objects': [{'name': label}], 'focus': focus},
                         'include_image': True, 'response_detail': 'full'}
            jobs[slot]['requests'].append({'id': index, 'label': label, 'arguments': arguments})
    preflight = root / 'preflight'
    control_receipts = [preflight / f'{name}_CONTROLS.json' for name in ('GEOMETRY', 'FEEDBACK')]
    controls = [preflight / f'TASK_REGION_{name}_CONTROLS.py' for name in ('GEOMETRY', 'FEEDBACK')]
    geometry, feedback = (read(receipt) for receipt in control_receipts)
    actual_focus = Path(candidate['installation']['path']) / 'human_eye_plugin/observation_focus.py'
    need(geometry['passed'] == len(geometry['checks']) == 17 and Path(geometry['implementation']) == actual_focus
         and feedback['status'] == 'passed' and feedback['blender_starts'] == feedback['model_calls'] == 0
         and Path(feedback['installed_modules']['human_eye_plugin.observation_focus']) == actual_focus,
         'failed_reference_or_feedback_controls')
    files = [admin, path, truth, PRIOR, PRIOR.with_name('score.py'), Path(__file__), HERE / 'worker_wire.py',
             HERE / 'install_candidate.py', HERE / 'score.py', *controls, *control_receipts]
    return {'batch': BATCH, 'order': list(ORDER), 'jobs': jobs,
            'inputs': [*(pin(p) for p in files), *prompts, base_receipt, candidate_receipt],
            'blender': baseline['blender'], 'python': baseline['python'],
            'two_new_rasters_limit_per_request': 2}


prior.prepare = prepare
prior.ORDER = ORDER
prior.BATCH = BATCH
frozen = prior.frozen
run_prior_slot = prior.run_slot


class Launch(prior.Launch):
    wire = None

    def Popen(self, command, *args, **options):
        process = super().Popen(command, *args, **options)
        self.wire = WorkerWire(self.folder / 'worker_wire')
        self.wire.attach(process)
        return process


def observed_registry(folder, service, run_stdio, job):
    expected = job['requests'][0]['arguments']
    bad = {**expected, 'query': {**expected['query'], 'focus': {'task_region': {'reference': None}}}}
    calls = [('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                            'clientInfo': {'name': 'task-focus-assembly', 'version': '1'}}),
             ('tools/list', {})]
    for arguments in (bad, expected):
        calls.append(('tools/call', {'name': 'human_eye_scene_observe', 'arguments': arguments}))
    requests = '\n'.join(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params},
                                    separators=(',', ':'))
                         for i, (method, params) in enumerate(calls, 1)) + '\n'
    observed = []
    normal = service._observe_active_observation

    def capture_arguments(session_id, **options):
        observed.append(options)
        raise ValueError('zero_host_registry_boundary')

    service._observe_active_observation = capture_arguments
    service.close = lambda: None
    output = io.StringIO()
    try:
        run_stdio(service, input_stream=io.StringIO(requests), output_stream=output)
    finally:
        service._observe_active_observation = normal
        del service.close
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    (folder / 'REGISTRY.tx').write_bytes(requests.encode())
    (folder / 'REGISTRY.rx').write_bytes(output.getvalue().encode())
    save(folder / 'REGISTRY_SERVICE.json', observed)
    need([x.get('id') for x in replies] == [1, 2, 3, 4]
         and replies[0]['result']['_meta']['human_eye']['source_sha256'] == job['candidate_source_sha256'],
         'wrong_actual_registry_or_init_identity')
    tools = replies[1]['result']['tools']
    tool, = [x for x in tools if x['name'] == 'human_eye_scene_observe']
    focus = tool['inputSchema']['properties']['query']['properties']['focus']
    need(('task_region' in json.dumps(focus)) == (job['arm'] == 'task'), 'wrong_task_focus_registry')
    need(len(observed) == 1 and observed[0]['focus'] == expected['query']['focus']
         and all(x.get('error') or x.get('result', {}).get('isError') for x in replies[2:]),
         'cold_dispatched_invalid_or_dropped_frozen_request')


def worker(root, slot, mode):
    settings = frozen(root)
    job = settings['jobs'][slot]
    folder = root / 'slots' / slot if mode == 'formal' else root / 'preflight/cold' / slot
    if mode == 'formal':
        start, registered = read(root / 'FORMAL_START.json'), read(folder / 'REGISTERED.json')
        need(start['freeze'] == pin(root / 'preflight/FROZEN_EXECUTION.json') and registered['slot'] == slot
             and registered['planned'] == job['requests'], 'formal_child_without_parent')
    fixture = prior.copied_input(folder, job)
    settings = {**settings, 'candidate_site': job['candidate_site']}
    site = Path(job['candidate_site'])
    sys.path.insert(0, str(site))
    from human_eye_plugin import blender_process
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity

    ident = runtime_identity()
    need(Path(blender_process.__file__).resolve().parent.parent == site
         and ident['source_sha256'] == job['candidate_source_sha256'] and ident['source_files'] == job['runtime_sources']
         and ident['source_kind'] == 'installed_distribution', 'installed_runtime_drift')
    config = folder / 'config.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                  'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': ident['source_sha256']}})
    if mode == 'cold':
        registry_service = LiveSpatialService(config, host=object(), production_mode=True)
        observed_registry(folder, registry_service, run_stdio_mcp_server, job)
    launched = Launch(folder, mode, settings, fixture)
    real = blender_process.subprocess
    blender_process.subprocess = launched
    host = None
    caught = None
    post = None
    t0 = time.perf_counter_ns()
    try:
        try:
            host = blender_process.BlenderProcessHost(settings['blender']['path'], fixture,
                                                       timeout=25, startup_timeout=45)
        except prior.AtReservation:
            need(mode == 'cold' and launched.process is None, 'unreal_cold_boundary')
            return 0
        need(mode == 'formal' and launched.process is host._process, 'wrong_owned_blender_handle')
        service = LiveSpatialService(config, host=host, production_mode=True)
        save(folder / 'ready.json', {'pid': host._process.pid, 'startup_ns': time.perf_counter_ns() - t0,
             'source_sha256': ident['source_sha256'], 'source_files': len(ident['source_files']),
             'source_kind': ident['source_kind'], 'fixture_before': digest(fixture),
             'asset': job['asset'], 'arm': job['arm']})

        def finish():
            nonlocal post
            started = time.perf_counter_ns()
            value = host.capture_scene()
            ended = time.perf_counter_ns()
            save(folder / 'post_capture.json', value)
            post = {'started_ns': started, 'closed_ns': ended, 'path': pin(folder / 'post_capture.json')}

        service.close = finish
        original, images = prior.emit_focus_source(service, folder, job['requests'])
        try:
            run_stdio_mcp_server(service)
        finally:
            images.rasterize_attention = original
    except BaseException as failure:
        caught = type(failure).__name__ + ': ' + str(failure)
        raise
    finally:
        blender_process.subprocess = real
        if mode == 'formal':
            started = time.perf_counter_ns()
            process = launched.process
            try:
                if host is not None:
                    host.close()
                elif process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except real.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                    for stream in (process.stdin, process.stdout, process.stderr):
                        try:
                            stream.close()
                        except (OSError, ValueError):
                            pass
                if launched.wire is not None:
                    launched.wire.publish()
            finally:
                save(folder / 'closed.json', {'pid': process.pid if process else None,
                     'blender_exit': process.poll() if process else None, 'native_spawned': process is not None,
                     'fixture_after': digest(fixture), 'closed_ns': time.perf_counter_ns(),
                     'native_close_started_ns': started, 'post_capture': post, 'failure': caught})
    return 0


def child_args(root, slot, mode):
    return [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), str(root), 'worker', slot, mode]


def _byte_time(index, direction, position, key):
    chunk, = [span for span in index['raw_event_spans']
              if span['direction'] == direction and span['offset'] <= position < span['offset'] + span['bytes']]
    return chunk[key]


def verify_worker(folder, ledger):
    wire = folder / 'worker_wire'
    index = read(wire / 'INDEX.json')
    tx = [row for row in index['lines']['TX'] if row['kind'] == 'request']
    received = [row for row in index['lines']['RX'] if row['kind'] == 'response']
    rx = {row['id']: row for row in received}
    need(len(tx) == len(received) == len(rx) and len(tx) >= 4
         and [x['id'] for x in tx] == [x['id'] for x in received] == list(range(1, len(tx) + 1))
         and tx[0]['command'] == 'capabilities' and tx[-1]['command'] == 'shutdown'
         and all(row['command'] == 'capture' for row in tx[1:-1])
         and all(row['kind'] == 'request' for row in index['lines']['TX'])
         and all(row['kind'] != 'malformed_rpc' for row in index['lines']['RX'])
         and all(x['terminated'] and rx[x['id']]['terminated'] for x in tx), 'worker_message_pairing_incomplete')
    originals = {}
    for direction in ('TX', 'RX'):
        raw = (wire / (direction + '.bin')).read_bytes()
        originals[direction] = raw
        offset = 0
        for row in index['lines'][direction]:
            need(row['offset'] == offset and sha(raw[offset:offset + row['bytes']]) == row['sha256'],
                 'worker_wire_raw_slice_mismatch')
            offset += row['bytes']
        need(offset == len(raw), 'worker_wire_extra_data')
    pairs = []
    for row in tx:
        response = rx[row['id']]
        start = _byte_time(index, 'TX', row['offset'], 'started_ns')
        end = _byte_time(index, 'TX', row['offset'] + row['bytes'] - 1, 'ended_ns')
        response_end = _byte_time(index, 'RX', response['offset'] + response['bytes'] - 1, 'ended_ns')
        need(start <= end and start < response_end, 'worker_response_time_order')
        pairs.append({'id': row['id'], 'command': row['command'], 'TX': row, 'RX': response,
                      'tx_start_ns': start, 'tx_end_ns': end, 'rx_end_ns': response_end})
    by_topic = {}
    for mcp in ledger['requests']:
        if mcp['id'] < 3 or mcp['status'] != 'returned':
            continue
        service = read(folder / f"construction_{mcp['id']:02d}.json")
        scoped = [row for row in pairs if service['service_started_ns'] < row['tx_end_ns']
                  and row['rx_end_ns'] < service['service_returned_ns']]
        need(scoped and all(row['RX']['state'] == 'result' for row in scoped), 'missing_observation_worker_pair')
        by_topic[mcp['label']] = scoped
    need(len(by_topic) == 2, 'missing_real_request_worker_pairs')
    for row in pairs:
        pair_folder = wire / f"{row['id']:03d}"
        pair_folder.mkdir()
        for direction in ('TX', 'RX'):
            entry = row[direction]
            start = entry['offset']
            path = pair_folder / (direction + '.bin')
            path.write_bytes(originals[direction][start:start + entry['bytes']])
            entry['packet'] = pin(path)
    return {'passed': True, 'index': pin(wire / 'INDEX.json'), 'TX': pin(wire / 'TX.bin'),
            'RX': pin(wire / 'RX.bin'), 'actual_worker_pairs': pairs, 'business_pairs': by_topic}


def run_slot(root, slot, settings):
    prior.SOURCE = settings['jobs'][slot]['candidate_source_sha256']
    ledger = run_prior_slot(root, slot, settings)
    folder = root / 'slots' / slot
    if ledger['status'] == 'closed':
        try:
            receipt = verify_worker(folder, ledger)
        except Exception as error:
            ledger['status'] = 'failed'
            ledger['issues'].append({'reason': type(error).__name__ + ': ' + str(error)})
            receipt = {'passed': False, 'reason': ledger['issues'][-1]['reason']}
    else:
        receipt = {'passed': False, 'reason': 'outer_lifecycle_failed'}
    save(folder / 'WORKER_ADMISSION.json', receipt)
    return ledger


prior.child_args = child_args
prior.run_slot = run_slot

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('action', choices=('freeze', 'cold', 'formal', 'worker'))
    parser.add_argument('slot', nargs='?', choices=ORDER)
    parser.add_argument('mode', nargs='?', choices=('formal', 'cold'))
    options = parser.parse_args()
    if options.action == 'freeze':
        save(options.root / 'preflight/FROZEN_EXECUTION.json', prepare(options.root))
    elif options.action == 'cold':
        prior.cold_slots(options.root)
    elif options.action == 'formal':
        raise SystemExit(prior.formal(options.root))
    else:
        need(options.slot and options.mode, 'worker_requires_slot_and_mode')
        raise SystemExit(worker(options.root, options.slot, options.mode))
