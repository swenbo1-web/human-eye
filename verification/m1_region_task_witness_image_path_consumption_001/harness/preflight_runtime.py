"""Actual new production worker/Owner/thin replay, with zero live scene work."""

import argparse
from copy import deepcopy
from functools import partial
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path[:0] = [str(HERE), str(NS), str(NS / 'qualification')]
from common import (EXTERNAL, PRODUCT_BINDING, SEAL, SLOTS, binding_for, catalogue_for,
                    load_retained, product_for, read, save, sha)


def archive_api():
    return SimpleNamespace(**run_path(str(V / 'm1_region_task_witness_image_path_001/harness/replay.py')))


def offline_worker(root, label):
    import mcp_entry

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    records = archive_api()
    record = records.archived(label)
    binding_path = binding_for(label)
    binding = read(binding_path)
    state = {'host': None, 'restore': None, 'counters': {
        'capture_calls': 0, 'archived_compute_substitutions': 0,
        'socket_attempts': 0, 'blocked_original_writes': 0}}

    def install_after_bootstrap(verified_binding):
        if verified_binding != binding:
            raise ValueError('preflight_injection_binding_changed')
        from human_eye_plugin import active_observation_host, live_service
        from human_eye_plugin.active_observation import fingerprint, geometry
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        counters = state['counters']
        original_root = record['folder'].resolve()

        def audit(event, args):
            if event == 'socket.connect':
                counters['socket_attempts'] += 1
                raise AssertionError('no_live_socket_in_offline_production_preflight')
            if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
                path, mode, flags = args
                path = Path(os.fsdecode(path)).resolve()
                writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if path.is_relative_to(original_root) and writing:
                    counters['blocked_original_writes'] += 1
                    raise AssertionError('original_closed_slot_write_forbidden')

        sys.addaudithook(audit)

        class ArchivedHost(BlenderMCPHost):
            def _request(self, command, params):
                records.require(command == 'capture' and params == {}, 'offline_capture_only')
                self._ensure_live()
                packet = record['deltas'][min(counters['capture_calls'], 1)]
                value = self._scene_decoder.apply(deepcopy(packet))
                self._record_observation_document(value)
                counters['capture_calls'] += 1
                return value

        host = ArchivedHost(binding['install_root'])
        state['host'] = host
        original_service = live_service.LiveSpatialService
        original_producer = active_observation_host.observe_capture

        class WithArchivedHost(original_service):
            def __init__(self, *args, **kwargs):
                records.require('host' not in kwargs, 'single_offline_host_injection')
                super().__init__(*args, host=host, **kwargs)

        def producer(captured, output_directory, **options):
            counters['archived_compute_substitutions'] += 1
            expected = record['producer']['binding']
            actual = active_observation_host.source_binding(captured)
            records.require(counters['archived_compute_substitutions'] == 1 and options['include_image'] is True,
                            'one_archived_observation_compute')
            for key in ('document_epoch', 'capture_state', 'source_binding_sha256', 'objects'):
                records.require(actual[key] == expected[key], 'archived_capture_binding/' + key)
            objects, _, identity = geometry(active_observation_host.scene_from_capture(captured))
            records.require(identity == expected['geometry_identity'], 'archived_geometry_identity')
            options['_geometry_ids_callback'](tuple('geometry:' + fingerprint(obj[2]) for obj in objects))
            return records.generation_observation(record['producer'])

        def restore():
            live_service.LiveSpatialService = original_service
            active_observation_host.observe_capture = original_producer
        state['restore'] = restore
        live_service.LiveSpatialService = WithArchivedHost
        active_observation_host.observe_capture = producer
    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': record['config']['state_file'],
        'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
        'expected_identity': {'source_sha256': binding['source_sha256']}})
    options = argparse.Namespace(binding=binding_path, config=config, ledger=root / 'budget',
        evidence=root / 'mcp_io', archive=root / 'product_full', phase='qualification', label=label,
        region_task_evidence=True, _preflight_setup=install_after_bootstrap, _replay_overrides={
            'scope': 'sealed capture/producer replay, not an actual qualification slot',
            'host_override': 'BlenderMCPHost._request capture through original SceneDeltaDecoder',
            'producer_override': 'observe_capture once from authenticated sealed observation',
            'actual_Blender_starts': 0, 'actual_rasters': 0, 'actual_models': 0})
    try:
        return mcp_entry.worker(options)
    finally:
        if state['restore'] is not None:
            state['restore']()
        host = state['host']
        save(root / 'REPLAY_CLOSE.json', {**state['counters'],
            'host_closed': None if host is None else not host.is_alive,
            'actual_Blender_starts': 0, 'actual_new_rasters': 0, 'actual_models': 0,
            'old_inputs_unchanged': all(records.pin(row['path']) == row for row in record['pins'])})


def cell(root, label):
    import diagnostic
    from bridge import Owner
    from frame_device import FrameDevice
    from runtime import ProductionStdioClient

    records = archive_api()
    record = records.archived(label)
    root.mkdir()
    deadline = time.perf_counter_ns() + 120_000_000_000
    client = ProductionStdioClient(
        [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
         '--worker', str(root / 'worker'), '--label', label], root, root / 'producer_stdio', deadline,
        worker_evidence=root / 'worker/mcp_io', expected_source_sha256=product_for(label)['source_sha256'])
    owner = None
    try:
        initialized, listed = records.hello(client)
        diagnostic.require(initialized['result']['_meta']['human_eye']['source_sha256'] ==
                           product_for(label)['source_sha256'], 'actual_per_arm_installed_identity')
        diagnostic.require(listed['result']['tools'] == read(catalogue_for(label)), 'same_actual_public_directory')

        class Runtime:
            def __init__(self):
                self.folder = record['folder'].resolve()
                self.product_tools = listed['result']['tools']
                self.public_requests = []
                self.device = FrameDevice(runroot=root, asset_sha256=record['device']['asset_sha256'],
                    group='P', label=label, native_call=self.no_host, phase='qualification')
                self.buffers, self.cameras = self.device.buffers, self.device.cameras
                self.image_specification = self.device.image_specification
                by_ref = {row['ref']: row for row in record['device']['frames']}
                for frame in record['producer']['frames']:
                    old = by_ref[frame['image_ref']]
                    diagnostic.require(Path(old['PNG']).resolve() == Path(frame['image_path']).resolve()
                        and (old['PNG_sha256'], old['frame_identity']) ==
                            (frame['image_sha256'], frame['frame_identity']), 'authenticated_original_frame_resource')
                    self.device.by_ref[frame['image_ref']] = old

            def no_host(self, *args, **kwargs):
                raise AssertionError('no_live_host_or_renderer_in_offline_owner')

            def public_request(self, arguments):
                request = records.rpc('public-' + str(len(self.public_requests) + 1), 'tools/call',
                                      name='human_eye_scene_observe', arguments=deepcopy(arguments))
                response = client.call(request)
                self.public_requests.append({'request': request, 'response': response, 'receipt': client.records[-1]})
                return response

        runtime = Runtime()
        owner = Owner(runtime, {'label': label, 'group': 'P', 'phase': 'qualification',
            'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
        endpoint = owner.start(root / 'ENDPOINT.json')
        result = {'label': label, 'diagnostic_calls': []}
        plan = partial(diagnostic.run_calls, discover=record['request']['params']['arguments'])
        diagnostic.run_diagnostic(root, endpoint, deadline, 'P', owner, result, plan=plan)
        for response in runtime.public_requests:
            source = read(root / 'client/call_01/REQUEST.json')
            diagnostic.require(response['request']['params'] == source['params'], 'actual_arguments_rewritten')
        save(root / 'DIAGNOSTIC.json', result)
    finally:
        try:
            if owner is not None:
                closed = owner.close()
                save(root / 'OWNER_CLOSE.json', closed)
                diagnostic.require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
                                   'offline_owner_close_unconfirmed')
        finally:
            closed = client.finish()
            save(root / 'PRODUCER_CLOSE.json', closed)
            diagnostic.require(closed['confirmed'], 'same_worker_actual_stdout_EOF_exit_unconfirmed')
    return {'passed': True, 'product': product_for(label), 'product_calls': len(runtime.public_requests),
        'consumer_calls': len(result['diagnostic_calls']), 'pending': result['qualification_pending'],
        'actual_process_closed': True, 'actual_stdout_EOF': closed['stdout_eof_seen'],
        'evidence': str(root), 'actual_qualification_slots': 0, 'actual_models': 0, 'actual_rasters': 0}


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    cells = {label: cell(root / label, label) for label in ('QA', 'QB')}
    from consumer import driver
    turn, adapter, metadata = driver.consumer_adapter()
    old = V / 'perf050_dense_micro_surface_holdout_001'
    sys.modules['driver'] = driver
    retained = run_path(str(old / 'consumer/preflight.py'))
    with patch.object(driver, 'DENSE', V / 'm4_dense_panel_sweep_formal_001', create=True):
        pilot = run_path(str(V / 'perf050_readonly_product_pilot_001/consumer/preflight.py'))
    pins = {}
    records = archive_api()

    def pin(path, digest=None, size=None):
        row = records.pin(path)
        if digest is not None and row['sha256'] != digest or size is not None and row['bytes'] != size:
            raise ValueError('actual_preflight_source_changed/' + str(path))
        pins[row['path']] = row
        return row

    local = {label: retained['local_exit'](label, root / (label + '_exit_probe'), turn, adapter, metadata,
                                          pilot['normalize'], pin) for label in ('A1', 'B1')}
    for row in adapter['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    for path in [Path(__file__), NS / 'qualification/diagnostic.py', driver.PROMPT,
                 V / 'm1_region_task_witness_image_path_001/harness/replay.py']:
        pin(path)
    for label in ('QA', 'QB'):
        pin(binding_for(label))
        for row in records.archived(label)['pins']:
            pin(row['path'], row['sha256'], row['bytes'])
    receipt = {'passed': True, 'cells': cells, 'local_exit': local, 'source_pins': list(pins.values()),
        'actual_Blender_starts': 0, 'actual_model_starts': 0, 'actual_rasters': 0,
        'actual_qualification_slots': 0, 'actual_formal_slots': 0,
        'scope': 'this namespace production worker, actual installed service/cache over sealed capture, original Owner/current thin/diagnostic and CLI stdin/exit'}
    save(HERE / 'RUNTIME_PREFLIGHT.json', receipt)
    print(json.dumps({'passed': True, 'cells': {label: {'product_calls': row['product_calls'],
          'consumer_calls': row['consumer_calls']} for label, row in cells.items()},
          'path': str(HERE / 'RUNTIME_PREFLIGHT.json')}))


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('fixed_isolated_interpreter_required')
    if len(sys.argv) == 5 and sys.argv[1] == '--worker' and sys.argv[3] == '--label':
        raise SystemExit(offline_worker(Path(sys.argv[2]), sys.argv[4]))
    run(EXTERNAL / 'offline_runtime_02')
