"""Derived terminal-capture replay. This never opens Blender or replaces any slot."""
import copy
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit
import diagnostic

PREFIXES = ('01-init', '02-tools', '03-K', '04-T')
need, read, save, pin = diagnostic.need, diagnostic.read, diagnostic.save, diagnostic.pin
prior = diagnostic.prior


def inputs(root):
    freeze, geometry, truth = audit.admission(root)
    source = root / 'slots/DIAGNOSTIC'
    executed = read(root / 'DIAGNOSTIC_EXECUTION.json')
    status = read(source / 'closed.json')
    ledger = read(source / 'ledger.json')
    need(executed['status'] == 'failed' and executed['Blender_launches'] == 1
         and ledger['status'] == 'failed' and ledger['server_exit'] == status['blender_exit'] == 0
         and ledger['stdout_eof'] is True and status['fixture_after'] == truth['asset_sha256'],
         'recorded_original_failed_diagnostic_drift')
    capture_path = diagnostic.confirm(status['post_capture']['path'])
    need(capture_path == source / 'post_capture.json'
         and executed['freeze'] == pin(root / 'preflight/FROZEN_EXECUTION.json')
         and status['post_capture']['closed_ns'] <= status['native_close_started_ns'],
         'capture_not_bound_to_true_closed_slot')
    scene = read(capture_path)
    domain = audit.bind_geometry(scene, geometry)
    rows = []
    for idx, prefix in enumerate(PREFIXES, 1):
        call = source / (prefix + '.tx')
        original = source / (prefix + '.rx')
        stat = ledger['requests'][idx - 1]
        need(pin(call)['sha256'] == stat['tx_sha'] and pin(original)['sha256'] == stat['rx_sha'],
             'original_outer_packet_not_bound')
        request, reply = read(call), read(original)
        need(request['id'] == reply['id'] == idx, 'original_rpc_identity')
        if idx >= 3:
            label = prefix[-1]
            registered = read(source / 'REGISTERED.json')['planned'][idx - 3]
            shape = request['params']['arguments']['query']
            need(reply['result']['isError'] is True and stat['status'] == 'failed'
                 and request['params']['arguments'] == registered['arguments'] and registered['label'] == label
                 and shape['objects'] == [{'name': truth['target_name']}]
                 and shape['focus'] == {'task_region': {'reference': {'name': truth['cases'][label]['reference_name']}}},
                 'original_business_request_or_failure_drift')
            rows.append(registered)
    return freeze, truth, scene, domain, rows


def serve(root, folder):
    freeze, truth, scene, domain, expected = inputs(root)
    job = diagnostic.frozen(root)['jobs'][diagnostic.SLOT]
    site = Path(job['candidate_site'])
    sys.path.insert(0, str(site))
    from human_eye_plugin import active_observation_images
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    need(identity['source_kind'] == 'installed_distribution'
         and identity['source_sha256'] == freeze['product']['runtime_sha256'] == job['candidate_source_sha256']
         and identity['source_files'] == job['runtime_sources'], 'unexpected_live_replay_product')

    class TerminalCaptureReplay:
        captures = 0

        def capture_scene(self):
            need(active is not None, 'capture_without_bound_request')
            self.captures += 1
            need(self.captures <= 2, 'too_many_replay_captures')
            return copy.deepcopy(scene)

    config = folder / 'config.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                  'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': job['candidate_source_sha256']}})
    host = TerminalCaptureReplay()
    service = LiveSpatialService(config, host=host, production_mode=True)
    handle = service._observe_active_observation
    rasterize = active_observation_images.rasterize_attention
    admitted = []
    active = None

    def raster(*args, **kwargs):
        need(active is not None, 'raster_without_bound_request')
        if len(active['raster_calls']) >= 2:
            active['limit_exceeded'] = True
            raise ValueError('replay_raster_limit')
        item = {'started_ns': time.perf_counter_ns(), 'completed': False}
        active['raster_calls'].append(item)
        try:
            value = rasterize(*args, **kwargs)
            item['completed'] = True
            return value
        finally:
            item['closed_ns'] = time.perf_counter_ns()

    def wrapped(session_id, *, include_image, selector=None, task_query=None, region_task=None, focus=None):
        nonlocal active
        match, = [item for item in expected if item['arguments']['query']['objects'] == [selector]
                  and item['arguments']['query']['focus'] == focus]
        need(active is None and match['id'] not in admitted and include_image is True
             and task_query is None and region_task is None, 'unregistered_replayed_focus')
        admitted.append(match['id'])
        item = {'id': match['id'], 'label': match['label'], 'service_started_ns': time.perf_counter_ns(),
                'raster_calls': [], 'limit_exceeded': False}
        active = item
        try:
            result = handle(session_id, include_image=include_image, selector=selector, focus=focus)
            item['service_returned_ns'] = time.perf_counter_ns()
            save(folder / f"producer_{match['id']:02d}.json", result)
            item['result_recorded'] = True
            return result
        finally:
            active = None
            item.setdefault('service_returned_ns', time.perf_counter_ns())
            save(folder / f"construction_{match['id']:02d}.json", item)

    service._observe_active_observation = wrapped
    active_observation_images.rasterize_attention = raster
    try:
        run_stdio_mcp_server(service)
    finally:
        active_observation_images.rasterize_attention = rasterize
        save(folder / 'REPLAY_SERVICE_CLOSE.json', {'capture_replays': host.captures, 'admitted': admitted,
             'source_sha256': identity['source_sha256'], 'actual_Blender': 0, 'models': 0,
             'terminal_record_replay': True, 'clock_ns': time.perf_counter_ns()})


def replay(root, folder):
    freeze, truth, scene, domain, requests = inputs(root)
    source = root / 'slots/DIAGNOSTIC'
    folder.mkdir(parents=True)
    items, eof = queue.Queue(), threading.Event()
    rows = []
    with (folder / 'STDERR.bin').open('xb') as errors:
        process = subprocess.Popen([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__)), str(root), str(folder), 'worker'],
                                   cwd=folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   env=prior.process_env(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

        def collect():
            for line in process.stdout:
                items.put(line)
            eof.set()

        reader = threading.Thread(target=collect, daemon=True)
        try:
            reader.start()
            for idx, prefix in enumerate(PREFIXES, 1):
                older = source / (prefix + '.tx')
                payload = older.read_bytes()
                tx = folder / (prefix + '.tx')
                tx.write_bytes(payload)
                before = time.perf_counter_ns()
                process.stdin.write(payload)
                process.stdin.flush()
                reply = items.get(timeout=45)
                after = time.perf_counter_ns()
                rx = folder / (prefix + '.rx')
                rx.write_bytes(reply)
                need(read(rx)['id'] == idx and read(rx)['jsonrpc'] == '2.0', 'unexpected_derived_rpc_id')
                row = {'id': idx, 'started_ns': before, 'returned_ns': after, 'rtt_ms': (after - before) / 1e6,
                       'tx': len(payload), 'rx': len(reply)}
                if idx >= 3 and not read(rx).get('result', {}).get('isError'):
                    row['new_rasters'] = len(read(folder / f'construction_{idx:02d}.json')['raster_calls'])
                rows.append(row)
        finally:
            process.stdin.close()
            try:
                returncode = process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait(timeout=8)
            reader.join(timeout=5)
            process.stdout.close()
    need(returncode == 0 and eof.is_set() and items.empty(), 'replay_stdio_not_closed')
    receipt = read(folder / 'REPLAY_SERVICE_CLOSE.json')
    need(receipt['capture_replays'] <= 2 and receipt['actual_Blender'] == receipt['models'] == 0,
         'derived_replay_budget')
    events = [json.loads(line) for line in (folder / 'audit.jsonl').read_bytes().splitlines()]
    cells = {}
    for row, request in zip(rows[2:], requests, strict=True):
        idx, label = row['id'], request['label']
        prefix = f'{idx:02d}-{label}'
        producer = folder / f'producer_{idx:02d}.json'
        physical = folder / f'construction_{idx:02d}.json'
        cell, _ = audit.diag_cell(folder, read(folder / (prefix + '.tx')), read(folder / (prefix + '.rx')),
                                  read(producer) if producer.is_file() else None,
                                  read(physical) if physical.is_file() else None,
                                  scene, domain, truth['target_name'], truth['cases'][label], row, events)
        cells[label] = cell
    save(folder / 'DERIVED_RESULT.json', {
        'kind': 'derived_zero_blender_replay_from_real_closed_terminal_capture', 'replaces_original': False,
        'historical_observation_slots_dispatched_to_algorithm': '0/2', 'original': pin(root / 'DIAGNOSTIC_EXECUTION.json'),
        'source': pin(source / 'post_capture.json'), 'source_matches_frozen_evaluated_geometry': True,
        'formal_Blender': 0, 'models': 0, 'replayed_requests': len(rows) - 2,
        'replayed_rasters': sum(row.get('new_rasters', 0) for row in rows), 'transport_eof': True,
        'runtime_source_sha256': receipt['source_sha256'], 'rows': rows, 'cases': cells})
    print({key:{'status':cell['status'],'primary':cell.get('primary_source_triangle_index'),
                'nearest':cell.get('primary_is_nearest_piece'),'actual_nearest_pixels':cell.get('delivered_pixels_of_nearest_piece'),
                'rasters':cell.get('rasters')} for key,cell in cells.items()})


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve(strict=True)
    folder = Path(sys.argv[2]).resolve()
    if len(sys.argv) == 4 and sys.argv[3] == 'worker':
        serve(root, folder)
    else:
        need(len(sys.argv) == 3 and folder == root / 'postflight/diagnostic_replay', 'derived_output_out_of_scope')
        replay(root, folder)
