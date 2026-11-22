"""Actual production/Owner/thin preflight over the sealed f5469 capture.

Only host capture transport is replaced. Both installed measurement algorithms,
the production entry, service, formatter and public argument paths are real.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path[:0] = [str(HERE), str(NS), str(NS / 'qualification')]
from common import (ASSET_SHA256, EXTERNAL, PRODUCT_BINDING, SEAL, binding_for,
                    catalogue_for, product_for, read, save, sha)

ARCHIVE_NS = V / 'm1_region_task_witness_image_path_consumption_001'
ARCHIVE_ROOT = Path('D:/he_m1_region_task_witness_image_path_consumption_001')
INDEX_SHA = 'e234542215b21f8210b91a5b9beccc963ef58d458e4f9a1b8adfa35d9ddadab9'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def archive(label):
    require(label in ('QA', 'QB'), 'two_original_qualification_captures_only')
    index_path = ARCHIVE_NS / 'RAW_INDEX.json'
    require(sha(index_path) == INDEX_SHA, 'f5469_archive_index_changed')
    index = read(index_path)
    zip_path = ARCHIVE_NS / index['archive']['name']
    zp = pin(zip_path)
    require((zp['bytes'], zp['sha256']) == (index['archive']['bytes'], index['archive']['sha256']),
            'f5469_archive_bytes_changed')
    pins = [pin(index_path), zp]

    def member(relative):
        path = ARCHIVE_ROOT / 'slots' / label / relative
        actual = pin(path)
        key = 'runtime/slots/' + label + '/' + relative
        require(index['members'][key] == {'bytes': actual['bytes'], 'sha256': actual['sha256']},
                'sealed_capture_member_changed/' + key)
        raw = path.read_bytes()
        with ZipFile(zip_path) as package:
            require(package.read(key) == raw, 'sealed_capture_disk_zip_mismatch/' + key)
        pins.append(actual)
        return json.loads(raw)

    device = member('DEVICE_EVIDENCE.json')
    require(device['asset_sha256'] == ASSET_SHA256, 'exact_f5469_archived_asset_required')
    reply = member('native/WIRE/002/RESPONSE.bin')
    text = reply['result']['result']
    require(text.startswith('HUMAN_EYE_BLENDER_MCP:'), 'original_capture_protocol_required')
    delta = json.loads(text.split(':', 1)[1])['result']
    require(delta['schema'] == 'human-eye-scene-delta-v1' and len(delta['resources']) == 21,
            'first_complete_f5469_scene_delta_required')
    terminal = member('initial_capture/TERMINAL_SOURCE.json')
    require(len(terminal['objects']) == 21 and terminal['source']['asset_sha256'] == ASSET_SHA256,
            'same_asset_initial_source_required')
    return {'delta': delta, 'device': device, 'pins': pins, 'folder': ARCHIVE_ROOT / 'slots' / label}


def offline_worker(root, label):
    import mcp_entry

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = archive(label)
    binding_path = binding_for(label)
    binding = read(binding_path)
    state = {'host': None, 'restore': None, 'capture_calls': 0,
             'socket_attempts': 0, 'old_write_attempts': 0, 'PNG_open_attempts': 0}

    def install_after_bootstrap(verified_binding):
        require(verified_binding == binding, 'current_arm_bootstrap_binding_required')
        from human_eye_plugin import live_service
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        def audit(event, args):
            if event == 'socket.connect':
                state['socket_attempts'] += 1
                raise AssertionError('no_live_socket_in_capture_replay')
            if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
                return
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1:3]
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if path.is_relative_to(ARCHIVE_ROOT.resolve()) and writing:
                state['old_write_attempts'] += 1
                raise AssertionError('sealed_old_capture_write_forbidden')
            if path.suffix.lower() == '.png':
                state['PNG_open_attempts'] += 1
                raise AssertionError('no_image_read_or_write_in_no_image_preflight')

        sys.addaudithook(audit)

        selected_path = NS / 'fixture/selected.py'
        selected = run_path(str(selected_path))['build_selected_capture']

        class ArchivedHost(BlenderMCPHost):
            def _request(self, command, params):
                allowed = [row['query']['objects'] for row in read(NS / 'inputs/QUALIFICATION_PAIRS.json')]
                require(command == 'capture_task' and set(params) == {'selectors'}
                        and params['selectors'] in allowed,
                        'only_the_two_registered_ordered_task_captures_are_replayed')
                self._ensure_live()
                reference = params['selectors'][1]['name']
                derived = selected(self._complete_capture, reference)
                value = self._scene_decoder.apply(derived)
                self._record_observation_document(value)
                state['capture_calls'] += 1
                save(root / ('CAPTURE_' + str(state['capture_calls']).zfill(2) + '.json'), value)
                return value

        host = ArchivedHost(binding['install_root'])
        host._complete_capture = host._scene_decoder.apply(deepcopy(record['delta']))
        save(root / 'DERIVED_HOST_REPLAY.json', {
            'complete_capture_source_pins': record['pins'], 'selected_helper': pin(selected_path),
            'derivation': 'source arrays/version/instances from sealed full f5469 capture; selected scope and selection_key derived offline',
            'actual_live_selected_capture': False,
            'actual_Blender_starts': 0, 'geometry_algorithm_substitutions': 0})
        state['host'] = host
        original = live_service.LiveSpatialService

        class WithArchivedHost(original):
            def __init__(self, *args, **kwargs):
                require('host' not in kwargs, 'one_archived_host_injection')
                super().__init__(*args, host=host, **kwargs)

        def restore():
            live_service.LiveSpatialService = original

        state['restore'] = restore
        live_service.LiveSpatialService = WithArchivedHost

    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': str(root / 'product_state.json'),
        'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
        'expected_identity': {'source_sha256': binding['source_sha256']}})
    save(root / 'INPUTS.json', {'source_pins': record['pins'], 'binding': pin(binding_path),
        'asset_sha256': ASSET_SHA256, 'override_scope': 'capture RPC through actual SceneDeltaDecoder; selected metadata derived by fixture/selected.py',
        'geometry_algorithm_substitutions': 0, 'legacy_whole_capture': 'derived selected scope, normal current instance/source arrays; explicitly offline'})
    options = argparse.Namespace(binding=binding_path, config=config, ledger=root / 'budget',
        evidence=root / 'mcp_io', archive=root / 'product_full', phase='qualification', label=label,
        region_task_evidence=True, _preflight_setup=install_after_bootstrap, _replay_overrides={
            'scope': 'sealed first complete f5469 capture, not an actual qualification',
            'host_override': 'BlenderMCPHost._request exact task pairs, independently derived selected capture through normal SceneDeltaDecoder',
            'producer_algorithm_overrides': 0, 'actual_Blender_starts': 0, 'actual_rasters': 0, 'actual_models': 0})
    try:
        return mcp_entry.worker(options)
    finally:
        if state['restore'] is not None:
            state['restore']()
        host = state['host']
        save(root / 'REPLAY_CLOSE.json', {key: value for key, value in state.items() if key not in ('host', 'restore')}
             | {'host_closed': None if host is None else not host.is_alive,
                'old_inputs_unchanged': all(pin(row['path']) == row for row in record['pins']),
                'actual_Blender_starts': 0, 'actual_new_rasters': 0, 'actual_models': 0})


def cell(root, label):
    import diagnostic
    from bridge import Owner
    from frame_device import FrameDevice
    from runtime import ProductionStdioClient, Runtime as LiveRuntime

    record = archive(label)
    root.mkdir()
    deadline = time.perf_counter_ns() + 120_000_000_000
    client = ProductionStdioClient(
        [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
         '--worker', str(root / 'worker'), '--label', label], root, root / 'producer_stdio', deadline,
        worker_evidence=root / 'worker/mcp_io', expected_source_sha256=product_for(label)['source_sha256'])
    owner = None
    try:
        for request in (
            {'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'no-image-capture-preflight', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}):
            response = client.call(request)
            if request.get('id') == 'initialize':
                require(response['result']['_meta']['human_eye']['source_sha256'] == product_for(label)['source_sha256'],
                        'actual_arm_installed_identity')
            elif request.get('id') == 'list':
                listed = response['result']['tools']
        require(listed == read(catalogue_for(label)), 'actual_arm_product_directory')

        class Runtime:
            public_request = LiveRuntime.public_request

            def __init__(self):
                self.folder, self.group, self.label, self.phase = root / 'worker', 'P', label, 'qualification'
                self.client, self.task_deadline = client, deadline
                self.product_tools, self.public_requests = listed, []
                self.device = FrameDevice(runroot=root, asset_sha256=ASSET_SHA256,
                    group='P', label=label, native_call=self.no_host, phase='qualification')
                self.buffers, self.cameras = self.device.buffers, self.device.cameras
                self.image_specification = self.device.image_specification

            def check(self):
                require(time.perf_counter_ns() < deadline, 'original_offline_deadline')

            def no_host(self, *args, **kwargs):
                raise AssertionError('no_live_native_or_renderer_in_no_image_preflight')

        runtime = Runtime()
        owner = Owner(runtime, {'label': label, 'group': 'P', 'phase': 'qualification',
            'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
        endpoint = owner.start(root / 'ENDPOINT.json')
        result = {'label': label, 'diagnostic_calls': []}
        diagnostic.run_diagnostic(root, endpoint, deadline, 'P', owner, result)
        require(len(runtime.public_requests) == len(result['diagnostic_calls']) == 3,
                'three_original_public_requests_required')
        for index, actual in enumerate(runtime.public_requests, 1):
            request = read(root / 'client' / ('call_' + str(index).zfill(2)) / 'REQUEST.json')
            require(actual['request']['params'] == request['params'], 'original_public_arguments_changed')
            result_blocks = actual['response']['result']['content']
            require(all(row['type'] == 'text' for row in result_blocks), 'no_native_image_blocks_expected')
        save(root / 'DIAGNOSTIC.json', result)
    finally:
        try:
            if owner is not None:
                owner_close = owner.close()
                save(root / 'OWNER_CLOSE.json', owner_close)
                require(owner_close['confirmed'] and not owner_close['errors'] and not owner_close['transport_errors'],
                        'actual_owner_close_unconfirmed')
        finally:
            closed = client.finish()
            save(root / 'PRODUCER_CLOSE.json', closed)
            require(closed['confirmed'], 'actual_production_stdout_EOF_or_exit_unconfirmed')
    close = read(root / 'worker/REPLAY_CLOSE.json')
    require(close['host_closed'] and close['old_inputs_unchanged'] and close['capture_calls'] == 2
            and close['socket_attempts'] == close['PNG_open_attempts'] == close['old_write_attempts'] == 0,
            'capture_transport_or_no_artifact_contract_failed')
    require(not list(root.rglob('*.png')) and not list(root.rglob('*.npz')), 'preflight_generated_image_artifact')
    return {'passed': True, 'product': product_for(label), 'product_calls': 3, 'consumer_calls': 3,
        'capture_calls': close['capture_calls'], 'pending': result['qualification_pending'],
        'actual_stdout_EOF': closed['stdout_eof_seen'], 'actual_process_closed': closed['confirmed'],
        'evidence': str(root), 'actual_qualification_slots': 0, 'actual_models': 0, 'actual_rasters': 0,
        'geometry_algorithm_substitutions': 0, 'original_arguments_preserved': True}


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    cells = {label: cell(root / label, label) for label in ('QA', 'QB')}
    from consumer import driver
    turn, adapter, metadata = driver.consumer_adapter()
    sys.modules['driver'] = driver
    retained = run_path(str(V / 'perf050_dense_micro_surface_holdout_001/consumer/preflight.py'))
    with patch.object(driver, 'DENSE', V / 'm4_dense_panel_sweep_formal_001', create=True):
        pilot = run_path(str(V / 'perf050_readonly_product_pilot_001/consumer/preflight.py'))
    pins = {}

    def checked_pin(path, digest=None, size=None):
        row = pin(path)
        require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                'preflight_source_identity_changed/' + str(path))
        pins[row['path']] = row
        return row

    local = {label: retained['local_exit'](label, root / (label + '_exit_probe'), turn, adapter, metadata,
                                          pilot['normalize'], checked_pin) for label in ('A1', 'B1')}
    for row in adapter['execution_sources']:
        checked_pin(row['path'], row['sha256'], row['bytes'])
    for path in [Path(__file__), NS / 'qualification/diagnostic.py', driver.PROMPT,
                 NS / 'fixture/selected.py', NS / 'inputs/QUALIFICATION_PAIRS.json',
                 V / 'perf050_dense_micro_surface_holdout_001/consumer/preflight.py',
                 V / 'perf050_readonly_product_pilot_001/consumer/preflight.py']:
        checked_pin(path)
    for label in ('QA', 'QB'):
        checked_pin(binding_for(label))
        checked_pin(catalogue_for(label))
        for row in archive(label)['pins']:
            checked_pin(row['path'], row['sha256'], row['bytes'])
    receipt = {'passed': True, 'cells': cells, 'local_exit': local, 'source_pins': list(pins.values()),
        'actual_Blender_starts': 0, 'actual_model_starts': 0, 'actual_rasters': 0,
        'actual_qualification_slots': 0, 'actual_formal_slots': 0,
        'scope': 'actual installed production/service/geometry/Owner/thin; derived selected capture from sealed f5469 full geometry; local CLI exit substitute only'}
    save(HERE / 'RUNTIME_PREFLIGHT.json', receipt)
    print(json.dumps({'passed': True, 'cells': cells, 'path': str(HERE / 'RUNTIME_PREFLIGHT.json')}))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    if len(sys.argv) == 5 and sys.argv[1] == '--worker' and sys.argv[3] == '--label':
        raise SystemExit(offline_worker(Path(sys.argv[2]), sys.argv[4]))
    run(EXTERNAL / 'offline_runtime_01')
