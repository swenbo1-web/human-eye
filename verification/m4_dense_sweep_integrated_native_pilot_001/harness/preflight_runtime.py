"""Replay closed dense captures through the current actual MCP and ordinary bridge."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
NS, V = HERE.parent, HERE.parents[1]
sys.path.insert(0, str(HERE))

from admission import require
from common import (ASSET_SHA256, CATALOGUE, EXTERNAL, ORDER, PRIOR, PRODUCT_BINDING,
                    SEAL, SOURCE_SHA, load_retained, read, save, sha)

RECOVERY = V / 'm1_region_task_first_packet_consumption_holdout_recovery_001'
ORIGINAL_RUNTIME = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001')
PREFIX = 'runtime/slots/QB/'
INIT = {'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'offline-preflight', 'version': '1'}}}
NOTIFY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}


def pin(path):
    p = Path(path).resolve(strict=True)
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}


def sealed_inputs():
    index_path = RECOVERY / 'RAW_INDEX.json'
    index = read(index_path)
    archive_path = RECOVERY / index['archive']['name']
    archive = pin(archive_path)
    require(archive['sha256'] == index['archive']['sha256'], 'archived_dense_runtime_changed')
    pins = [pin(index_path), archive]
    def original(name, zip_file):
        path = ORIGINAL_RUNTIME / 'slots/QB' / name
        raw = path.read_bytes()
        evidence = pin(path)
        require(zip_file.read(PREFIX + name) == raw
                and index['members'][PREFIX + name] == {k: evidence[k] for k in ('bytes', 'sha256')},
                'original_dense_member_changed/' + name)
        pins.append(evidence)
        return json.loads(raw)
    with ZipFile(archive_path) as package:
        response = original('native/WIRE/002/RESPONSE.bin', package)
        terminal = original('TERMINAL_SOURCE.json', package)
        discover = original('product_calls/call_002/REQUEST.json', package)['params']['arguments']
    text = response['result']['result']
    require(text.startswith('HUMAN_EYE_BLENDER_MCP:'), 'actual_prior_capture_not_decodable')
    delta = json.loads(text.split(':', 1)[1])['result']
    require(delta['schema'] == 'human-eye-scene-delta-v1' and len(delta['resources']) == len(terminal['objects']) == 20
            and terminal['source']['asset_sha256'] == ASSET_SHA256
            and sum(len(row['evaluated']['vertices']) for row in terminal['objects']) == 3502
            and sum(len(row['evaluated']['triangles']) for row in terminal['objects']) == 6160,
            'closed_dense_geometry_identity_changed')
    return delta, terminal, discover, pins


def worker(root):
    import mcp_entry

    root.mkdir(parents=True, exist_ok=False)
    delta, _, _, pins = sealed_inputs()
    config = root / 'PRODUCT_CONFIG.json'
    binding = read(PRODUCT_BINDING)
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(root / 'product_state.json'),
                  'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': SOURCE_SHA}})
    calls, restore = [], []

    def setup(verified):
        require(verified == binding, 'fixed_offline_install_required')
        from human_eye_plugin import live_service
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        def guard_socket(event, args):
            if event == 'socket.connect':
                raise AssertionError('offline_capture_replay_must_not_connect_to_Blender')
        sys.addaudithook(guard_socket)
        class ArchivedHost(BlenderMCPHost):
            def _request(self, command, params):
                require(command == 'capture' and not params and not calls, 'only_one_archived_dense_capture')
                self._ensure_live()
                current = self._scene_decoder.apply(deepcopy(delta))
                calls.append({'command': command, 'params': params})
                self._record_observation_document(current)
                save(root / 'CAPTURE.json', current)
                return current

        host = ArchivedHost(binding['install_root'])
        original = live_service.LiveSpatialService
        restore.append(lambda: setattr(live_service, 'LiveSpatialService', original))
        class ReplayService(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, host=host, **kwargs)
        live_service.LiveSpatialService = ReplayService
    args = argparse.Namespace(binding=PRODUCT_BINDING, config=config, ledger=root / 'budget',
        evidence=root / 'mcp_io', archive=root / 'product_full', phase='qualification', label='QP',
        region_task_evidence=True, _offline_capture_setup=setup)
    try:
        return mcp_entry.worker(args)
    finally:
        for undo in restore:
            undo()
        save(root / 'REPLAY_CLOSE.json', {'calls': calls, 'source_pins': pins,
             'old_sources_unchanged': all(pin(row['path']) == row for row in pins),
             'actual_Blender_starts': 0, 'actual_models': 0})


def request(client, index, name, args):
    return client.call({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': args}})['result']


def output_text(result):
    require(result['isError'] is False and result['content'][0]['type'] == 'text', 'actual_tool_text_success')
    return json.loads(result['content'][0]['text'])


def images(result):
    require(result['isError'] is False, 'actual_image_read_success')
    return [base64.b64decode(item['data'], validate=True) for item in result['content'] if item['type'] == 'image']


def table(value):
    return [dict(zip(value['columns'], row, strict=True)) for row in value['rows']]


def image_proof(root, path, expected, raw):
    p = Path(path).resolve(strict=True)
    require(p.is_relative_to(root) and p.read_bytes() == raw and sha256(raw).hexdigest() == expected,
            'original_closed_slot_PNG_bytes_required')
    return pin(p)


def cell(root, label, terminal, discover, binding):
    from bridge import Owner, TOOL_NAMES
    from frame_device import FrameDevice
    from runtime import ProductionStdioClient, Runtime as Live, transport

    root.mkdir(parents=True, exist_ok=False)
    group = label[-1]
    worker_root = root / 'worker'
    deadline = time.perf_counter_ns() + 120_000_000_000
    producer = front = owner = None
    observed = {}
    try:
        tools = []
        if group == 'P':
            producer = ProductionStdioClient(
                [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), '--worker', str(worker_root)],
                root, root / 'producer_stdio', deadline, worker_evidence=worker_root / 'mcp_io')
            identity = producer.call(INIT)['result']['_meta']['human_eye']
            producer.call(NOTIFY)
            tools = producer.call(LIST)['result']['tools']
            require(identity['source_sha256'] == SOURCE_SHA and identity['source_kind'] == 'installed_distribution'
                    and tools == read(CATALOGUE), 'real_evidence_catalogue_and_identity_required')
        else:
            worker_root.mkdir()
        class ReplayRuntime:
            public_request = Live.public_request
            scene_data = Live.scene_data
            render_views = Live.render_views
            render_local = Live.render_local

            def __init__(self):
                self.folder, self.label, self.group, self.phase = worker_root, label, group, 'qualification'
                self.client, self.task_deadline = producer, deadline
                self.product_tools, self.public_requests = tools, []
                self.device = FrameDevice(self.folder, ASSET_SHA256, group, label, self.no_host, phase=self.phase)
                self.device._scene = {**deepcopy(terminal), 'source_ref': 'archived-closed-blender-source',
                    'objects': [{**row, **row['evaluated']} for row in deepcopy(terminal['objects'])]}
                self.buffers, self.cameras = self.device.buffers, self.device.cameras
                self.image_specification = self.device.image_specification

            def check(self):
                require(time.perf_counter_ns() < deadline, 'offline_probe_deadline')

            def no_host(self, *args, **kwargs):
                raise AssertionError('offline_no_live_Blender')

        runtime = ReplayRuntime()
        owner = Owner(runtime, {'label': label, 'group': group, 'phase': 'qualification',
            'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
        endpoint = owner.start(root / 'ENDPOINT.json')
        front = transport.StdioClient([sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
            '--endpoint', str(endpoint), '--audit', str(root / 'attachments')], root, root / 'thin_stdio', deadline)
        front.call(INIT)
        front.call(NOTIFY)
        public_tools = front.call(LIST)['result']['tools']
        require(set(tool['name'] for tool in public_tools) == TOOL_NAMES[group], 'actual_N_P_public_tools_changed')
        save(root / 'TOOLS.json', public_tools)
        invalid = request(front, 1, 'render_local', {'direction': 'INVALID'})
        require(invalid['isError'] is True, 'actual_bad_request_rejection_missing')
        init = request(front, 2, 'execute_python', {
            'code': "rows=scene_data()['objects']\nprint(len(rows))"})
        calc = request(front, 3, 'execute_python', {
            'code': "print(int(np.sum([len(row['triangles']) for row in rows])), shapely.Polygon([(0,0),(1,0),(0,1)]).area)"})
        require(output_text(init)['stdout'].strip() == '20'
                and output_text(calc)['stdout'].strip() == '6160 0.5', 'persistent_read_and_shared_libraries_required')
        if group == 'N':
            args = {'direction': 'LEFT', 'target_world_m': [7.5234375, 2.048828125, 1.509765625],
                    'view_span_m': 0.22, 'include_image': True}
            initial = request(front, 4, 'render_local', args)
            frame = output_text(initial)['frame']
            issued, = images(initial)
            final = request(front, 5, 'read_images', {'refs': [frame['ref']]})
            repeated, = images(final)
            require(issued == repeated and frame['scope_id'].startswith('local:') and frame['view_name'] == 'LEFT',
                    'same_local_original_native_image_required')
            require(final['content'][0]['text'].startswith(frame['ref']), 'expected_path_on_original_image_caption')
            caption = json.loads(final['content'][0]['text'].split('\n', 1)[1])
            observed = {'frames': [frame], 'rasters': 1, 'ordinary_PNGs': 1,
                        'image_inputs': [(caption['local_image_path'], caption['image_sha256'], repeated)],
                        'product_calls': 0, 'business_calls': 5}
        else:
            answer = request(front, 4, 'human_eye_scene_observe', discover)
            body = output_text(answer)
            frames = table(body['frames'])
            paths = table(body['witness_image_paths'])
            witness = table(body['witnesses'])
            require(len(paths) == len(witness) == 2 and len(frames) == 3, 'actual_scope_witness_paths_missing')
            require({row['frame_index'] for row in paths} == {row['frame_index'] for row in witness},
                    'actual_product_paths_must_be_witness_frames')
            refs = [frames[row['frame_index']]['image_ref'] for row in paths]
            require(len(set(refs)) == 2 and all(frames[row['frame_index']]['scope_index'] != 0 for row in paths),
                    'actual_product_local_frame_identity_required')
            received = [base64.b64decode(answer['content'][frames[row['frame_index']]['native_content_block_index']]['data'],
                                        validate=True) for row in paths]
            readback = images(request(front, 5, 'read_images', {'refs': refs}))
            require(received == readback and len(runtime.public_requests) == 1
                    and runtime.public_requests[0]['request']['params']['arguments'] == discover,
                    'actual_product_args_or_replayed_PNG_changed')
            observed = {'frames': [frames[row['frame_index']] for row in paths], 'rasters': 3,
                        'image_inputs': [(row['local_image_path'], frames[row['frame_index']]['image_sha256'], raw)
                                         for row, raw in zip(paths, received, strict=True)],
                        'ordinary_PNGs': 2, 'public_text_bytes': len(answer['content'][0]['text'].encode()),
                        'product_calls': 1, 'business_calls': 5}
    finally:
        try:
            if front is not None:
                closing = front.finish()
                require(closing['confirmed'] is True and closing['exit_code'] == 0, 'actual_consumer_stdio_did_not_close')
        finally:
            try:
                if owner is not None:
                    owner_close = owner.close()
                    save(root / 'OWNER_CLOSE.json', owner_close)
                    require(owner_close['confirmed'] and not owner_close['errors'] and not owner_close['transport_errors'],
                            'actual_owner_close_unconfirmed')
            finally:
                if producer is not None:
                    closed = producer.finish()
                    require(closed['confirmed'] is True and closed['exit_code'] == 0
                            and closed['production_eof_and_exit_verified'] is True, 'actual_installed_eof_unconfirmed')
    original_pngs = [image_proof(root, *item) for item in observed.pop('image_inputs')]
    if group == 'P':
        worker_close = read(worker_root / 'REPLAY_CLOSE.json')
        require(worker_close['calls'] == [{'command': 'capture', 'params': {}}]
                and worker_close['old_sources_unchanged'], 'one_original_full_dense_capture_replay_required')
    else:
        require(not (root / 'producer_stdio').exists(), 'native_arm_cannot_start_the_production_endpoint')
    return {**observed, 'passed': True, 'actual_consumer_process_closed': True,
            'actual_product_process_closed': group == 'P', 'actual_product_stdout_EOF': group == 'P',
            'post_close_original_PNGs': original_pngs}


def main(root):
    from run_slot import prepare_dispatch

    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    binding = read(PRODUCT_BINDING)
    sys.path[:0] = [binding['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    bootstrap_path = PRIOR / 'harness/reused/verified_bootstrap.py'
    bootstrap = load_retained('_dense_pilot_offline_bootstrap', bootstrap_path)
    guard = bootstrap.bootstrap(binding)
    _, terminal, discover, pins = sealed_inputs()
    cells = {label: cell(root / label, label, terminal, discover, binding) for label in ('QN', 'QP')}
    guard.verify_loaded()
    dispatch = {label: prepare_dispatch(label) for label in ORDER}
    ordinary = read(root / 'QN/TOOLS.json')
    product = read(root / 'QP/TOOLS.json')
    require([row for row in product if row['name'] != 'human_eye_scene_observe'] == ordinary
            and set(dispatch['QP']['tools']) - set(dispatch['QN']['tools']) == {'human_eye_scene_observe'},
            'actual_ordinary_N_P_roster_or_schema_differed')
    used = [Path(__file__), bootstrap_path, PRODUCT_BINDING, CATALOGUE,
            *[HERE / name for name in ('admission.py', 'common.py', 'runtime.py', 'mcp_entry.py', 'bridge.py',
                'budget.py', 'closure.py', 'frame_device.py', 'run_slot.py')],
            *[RECOVERY/'harness'/name for name in ('runtime.py',)],
            *[V/'perf050_dense_micro_surface_holdout_recovery_001/harness'/name
              for name in ('runtime.py', 'bridge.py', 'closure.py', 'frame_device.py')],
            NS / 'consumer/thin_stdio.py']
    seen = {pin(path)['path']: pin(path) for path in used}
    seen.update({row['path']: row for row in pins})
    for row in dispatch.values():
        for path in row['workspace_sources']:
            evidence = pin(path)
            seen[evidence['path']] = evidence
    receipt = {'passed': True, 'cells': cells, 'dispatch': dispatch, 'source_pins': list(seen.values()),
                'actual_Blender_starts': 0, 'actual_model_starts': 0, 'actual_qualification_slots': 0,
                'actual_formal_slots': 0, 'actual_offline_rasters': sum(row['rasters'] for row in cells.values()),
                'scope': 'Archived dense input and current actual production, ordinary rendering/PNG/stdio. Live captures, full QA and tamper scoring remain separate.'}
    save(HERE / 'RUNTIME_PREFLIGHT.json', receipt)
    print(json.dumps({'passed': True, 'calls': {key: row['business_calls'] for key, row in cells.items()},
                      'actual_offline_rasters': receipt['actual_offline_rasters'], 'frozen_source_count': len(seen)}))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path)
    action.add_argument('--worker', type=Path)
    options = parser.parse_args()
    if options.worker is not None:
        raise SystemExit(worker(options.worker.resolve()))
    main(options.output.resolve())
