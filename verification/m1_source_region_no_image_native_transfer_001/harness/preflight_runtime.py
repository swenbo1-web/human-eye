"""No-live N/P transport, common Python computation and production preflight.

Archived native reads are explicitly replayed; ordinary Python and installed
product geometry run normally. This is not a real Blender qualification.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from types import FunctionType
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path[:0] = [str(HERE), str(NS), str(NS / 'qualification')]
from common import (ASSET_SHA256, EXTERNAL, ORDER, PRODUCT_BINDING, PROMPT_SHAS, SEAL, SLOTS,
                    binding_for, catalogue_for, product_for, prompt_for, read, save)

PREVIOUS = V / 'm1_source_region_no_image_measurement_consumption_001/harness/preflight_runtime.py'
paths = sys.path[:]
try:
    old = run_path(str(PREVIOUS))
finally:
    sys.path[:] = paths
pin, require = old['pin'], old['require']


def archive(label):
    require(label in ('QN', 'QP'), 'fixed_native_transfer_preflight_arm_required')
    record = old['archive']('QA' if label == 'QN' else 'QB')
    source, = [row for row in record['pins'] if row['path'].endswith('initial_capture\\TERMINAL_SOURCE.json')
               or row['path'].endswith('initial_capture/TERMINAL_SOURCE.json')]
    record['terminal'] = read(source['path'])
    return record


def offline_worker(root, label):
    require(label == 'QP', 'no_product_worker_for_N')
    original = old['offline_worker']
    scope = dict(original.__globals__, archive=archive)
    return FunctionType(original.__code__, scope, original.__name__,
                        original.__defaults__, original.__closure__)(root, label)


def native_read_payload(record):
    source = record['terminal']
    names = ('M12', 'M17', 'M19', 'M15', 'M08', 'M02')
    by_name = {obj['name']: obj for obj in source['objects']}
    return {'meshes': {name: {'vertices': deepcopy(by_name[name]['evaluated']['vertices_world_m']),
                             'faces': deepcopy(by_name[name]['evaluated']['triangles'])} for name in names},
            'frame': source['source']['frame'], 'scale_length': source['source']['scale_length']}


def cell(root, label):
    import diagnostic
    from bridge import Owner, TOOL_NAMES
    from frame_device import FrameDevice
    from runtime import ProductionStdioClient, Runtime as LiveRuntime

    record = archive(label)
    root.mkdir()
    group = SLOTS[label][0]
    deadline = time.perf_counter_ns() + 120_000_000_000
    client = owner = None
    native_reads = []
    listed = []
    try:
        if group == 'P':
            client = ProductionStdioClient(
                [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
                 '--worker', str(root / 'worker'), '--label', label], root, root / 'producer_stdio', deadline,
                worker_evidence=root / 'worker/mcp_io', expected_source_sha256=product_for(label)['source_sha256'])
            initialized = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'native-transfer-capture-preflight', 'version': '1'}}})
            require(initialized['result']['_meta']['human_eye']['source_sha256'] == product_for(label)['source_sha256'],
                    'actual_fixed_installed_identity')
            client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            listed = client.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})['result']['tools']
            require(listed == read(catalogue_for(label)), 'actual_current_product_directory')

        class Runtime:
            public_request = LiveRuntime.public_request
            scene_data = LiveRuntime.scene_data

            def __init__(self):
                self.folder, self.group, self.label, self.phase = root / 'worker', group, label, 'qualification'
                self.client, self.task_deadline = client, deadline
                self.product_tools, self.public_requests = listed, []
                self.device = FrameDevice(runroot=root, asset_sha256=ASSET_SHA256, group=group,
                    label=label, native_call=self.no_host, phase='qualification')
                self.buffers, self.cameras = self.device.buffers, self.device.cameras
                self.image_specification = self.device.image_specification

            def check(self):
                require(time.perf_counter_ns() < deadline, 'original_offline_deadline')

            def no_host(self, *args, **kwargs):
                raise AssertionError('no_live_native_or_renderer_in_offline_preflight')

            def native_run(self, code, timeout_s=30):
                require(code == diagnostic.read_code(), 'only_exact_diagnostic_native_read_is_replayed')
                payload = native_read_payload(record)
                native_reads.append({'code_sha256': hashlib.sha256(code.encode('utf8')).hexdigest(),
                    'source_pins': record['pins'], 'substitution': 'native bpy read transport only; sealed exact evaluated arrays',
                    'native_bpy_script_executed': False})
                return {'stdout': json.dumps(payload) + '\n', 'stderr': '', 'error': None}

            def render_local(self, *args, **kwargs):
                return self.device.render_local(*args, **kwargs)

        runtime = Runtime()
        owner = Owner(runtime, {'label': label, 'group': group, 'phase': 'qualification',
            'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
        require({tool['name'] for tool in owner.tools} == TOOL_NAMES[group], 'actual_native_tools_contract')
        require(('human_eye_scene_observe' in TOOL_NAMES[group]) is (group == 'P'), 'N_product_tool_leak')
        endpoint = owner.start(root / 'ENDPOINT.json')
        result = {'label': label, 'diagnostic_calls': []}
        diagnostic.run_diagnostic(root, endpoint, deadline, group, owner, result)
        expected_calls = 4 if group == 'N' else 10
        require(len(result['diagnostic_calls']) == expected_calls and len(native_reads) == 1,
                'actual_common_compute_or_product_call_count_changed')
        expected_product = 6 if group == 'P' else 0
        require(len(runtime.public_requests) == expected_product, 'actual_NP_product_boundary_changed')
        for offset, actual in enumerate(runtime.public_requests, 5):
            request = read(root / 'client' / ('call_' + str(offset).zfill(2)) / 'REQUEST.json')
            require(actual['request']['params'] == request['params'], 'original_public_arguments_changed')
            require(all(item['type'] == 'text' for item in actual['response']['result']['content']), 'unexpected_image')
        save(root / 'DIAGNOSTIC.json', result)
        save(root / 'NATIVE_READ_TRANSPORT_REPLAY.json', native_reads)
    finally:
        try:
            if owner is not None:
                closed_owner = owner.close()
                save(root / 'OWNER_CLOSE.json', closed_owner)
                require(closed_owner['confirmed'] and not closed_owner['errors'] and not closed_owner['transport_errors'],
                        'actual_owner_close_unconfirmed')
        finally:
            if client is not None:
                closed = client.finish()
                save(root / 'PRODUCER_CLOSE.json', closed)
                require(closed['confirmed'], 'actual_production_stdout_EOF_or_exit_unconfirmed')
    if group == 'P':
        replay = read(root / 'worker/REPLAY_CLOSE.json')
        require(replay['host_closed'] and replay['old_inputs_unchanged'] and replay['capture_calls'] == 6
                and replay['socket_attempts'] == replay['PNG_open_attempts'] == replay['old_write_attempts'] == 0,
                'actual_product_capture_replay_or_no_artifact_contract_failed')
    require(not list(root.rglob('*.png')) and not list(root.rglob('*.npz')), 'unexpected_image_artifact')
    return {'passed': True, 'group': group, 'product': product_for(label), 'product_calls': expected_product,
        'consumer_calls': expected_calls, 'ordinary_native_read_replays': len(native_reads),
        'actual_ordinary_Python_computations': 2, 'product_worker_started': client is not None,
        'actual_product_process_closed': None if client is None else closed['confirmed'],
        'actual_stdout_EOF': None if client is None else closed['stdout_eof_seen'],
        'evidence': str(root), 'pending': result['qualification_pending'], 'actual_Blender_starts': 0,
        'actual_models': 0, 'actual_rasters': 0, 'actual_qualification_slots': 0,
        'scope': 'native bpy read replayed; common Python solver executes; P installed solver executes; not actual Blender qualification'}


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    cells = {label: cell(root / label, label) for label in ('QN', 'QP')}
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

    local = {}
    for label in driver.FORMAL_LABELS:
        with patch.object(driver, 'PROMPT', prompt_for(label)):
            local[label] = retained['local_exit'](label, root / (label + '_exit_probe'), turn,
                adapter, metadata, pilot['normalize'], checked_pin)
    for row in adapter['execution_sources']:
        checked_pin(row['path'], row['sha256'], row['bytes'])
    for path in [Path(__file__), PREVIOUS, NS / 'qualification/diagnostic.py',
                 NS / 'qualification/native_read.py', NS / 'qualification/native_solve.py',
                 V / 'perf050_dense_micro_surface_holdout_001/consumer/preflight.py',
                 V / 'perf050_readonly_product_pilot_001/consumer/preflight.py']:
        checked_pin(path)
    for label in ('QN', 'QP'):
        checked_pin(binding_for(label))
        for row in archive(label)['pins']:
            checked_pin(row['path'], row['sha256'], row['bytes'])
    for question, expected in PROMPT_SHAS.items():
        checked_pin(NS / 'inputs' / ('PROMPT_' + str(question) + '.txt'), expected)
    checked_pin(catalogue_for('QP'))
    receipt = {'passed': True, 'cells': cells, 'local_exit': local,
        'source_pins': list(pins.values()), 'actual_Blender_starts': 0, 'actual_model_starts': 0,
        'actual_rasters': 0, 'actual_qualification_slots': 0, 'actual_formal_slots': 0,
        'scope': 'actual Owner/thin, persistent ordinary Python, P installed service/solvers on sealed capture; native bpy transport replay and local CLI exit substitutes only'}
    save(HERE / 'RUNTIME_PREFLIGHT.json', receipt)
    print(json.dumps({'passed': True, 'cells': cells, 'local_exit_count': len(local),
                      'path': str(HERE / 'RUNTIME_PREFLIGHT.json')}))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    if len(sys.argv) == 5 and sys.argv[1] == '--worker' and sys.argv[3] == '--label':
        raise SystemExit(offline_worker(Path(sys.argv[2]), sys.argv[4]))
    run(EXTERNAL / 'offline_runtime_03')
