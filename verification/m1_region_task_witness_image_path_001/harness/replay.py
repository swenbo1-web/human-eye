"""Real production/stdin replay with archived capture and one renderer substitute.

No Blender is contacted. The actual service performs capture binding, normal
ReadContext.result publication and later hot lookup. Only the original raster
producer is replaced, once, by its authenticated closed-slot observation.
"""

import argparse
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
from runpy import run_path
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
EXTERNAL = Path('D:/he_m1_region_task_witness_image_path_001')
ORIGINAL = V / 'm1_region_task_first_packet_consumption_holdout_001'
RECOVERY = V / 'm1_region_task_first_packet_consumption_holdout_recovery_001'
OLD_ROOT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001')
RECOVERY_ROOT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001')
INDEX_PINS = {
    'QA': '625295c4b26bb18033a9ca8c4ad5ffee730fc84fe1e85ba1c14911795159bb7e',
    'recovery': '70e786eadeedeb369eb0a409d487d0c79175c7089fdc6e920e89e9c15c5214ef',
}
SLOTS = ('QA', 'QB', 'A1', 'B1')
TOOL = 'human_eye_scene_observe'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(compact(value) + b'\n')


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(compact(value) + b'\n')


def pin(path, raw=None):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes() if raw is None else raw
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def archived(slot):
    require(slot in SLOTS, 'registered_closed_slot_required')
    namespace, external = (ORIGINAL, OLD_ROOT) if slot == 'QA' else (RECOVERY, RECOVERY_ROOT)
    index_path = namespace / 'RAW_INDEX.json'
    index_raw = index_path.read_bytes()
    expected = INDEX_PINS['QA' if slot == 'QA' else 'recovery']
    require(hashlib.sha256(index_raw).hexdigest() == expected, 'closed_slot_index_changed')
    index = json.loads(index_raw)
    sources = [pin(index_path, index_raw)]

    def checked(path):
        path = Path(path).resolve(strict=True)
        raw = path.read_bytes()
        row = pin(path, raw)
        key = 'runtime/' + path.relative_to(external.resolve()).as_posix()
        require(index['members'][key] == {'bytes': row['bytes'], 'sha256': row['sha256']},
                'closed_slot_member_changed/' + key)
        sources.append(row)
        return json.loads(raw)

    folder = external / 'slots' / slot
    producer = checked(folder / 'product_full/call_001/SERVICE_RESULT.json')
    request = checked(folder / 'product_calls/call_001/REQUEST.json')
    device = checked(folder / 'DEVICE_EVIDENCE.json')
    config = checked(folder / 'PRODUCT_CONFIG.json')
    tools = checked(folder / 'owner/TOOLS.json')
    reads = [row for row in tools['tools'] if row['name'] == 'read_images']
    require(len(reads) == 1, 'one_original_public_image_read_required')
    read_folder = folder / 'owner' / ('tool_' + str(reads[0]['attempt']).zfill(2))
    read_request = checked(read_folder / 'REQUEST.json')
    read_response = checked(read_folder / 'RESPONSE.json')
    deltas = []
    for name in ('002', '003'):
        reply = checked(folder / 'native/WIRE' / name / 'RESPONSE.bin')
        text = reply['result']['result']
        require(text.startswith('HUMAN_EYE_BLENDER_MCP:'), 'closed_capture_protocol_missing')
        envelope = json.loads(text.split(':', 1)[1])
        require(envelope['result']['schema'] == 'human-eye-scene-delta-v1', 'closed_capture_delta_required')
        deltas.append(envelope['result'])
    require(request['params']['name'] == TOOL and producer['facts'].get('region_task') is not None,
            'closed_region_task_discovery_required')
    original_images = {}
    for frame in producer['frames']:
        path = Path(frame['image_path']).resolve(strict=True)
        key = 'runtime/' + path.relative_to(external.resolve()).as_posix()
        require(index['members'][key]['sha256'] == frame['image_sha256'], 'closed_frame_index_binding_changed')
        original_images[frame['image_ref']] = {'path': str(path), **index['members'][key]}
    return {'slot': slot, 'folder': folder, 'request': request, 'producer': producer,
            'device': device, 'config': config, 'deltas': deltas,
            'read_images_request': read_request, 'read_images_response': read_response,
            'read_images_folder': read_folder,
            'original_images': original_images, 'pins': sources}


def generation_observation(producer):
    value = deepcopy(producer)
    value['work'] = value.pop('generation_work')
    value['stages'] = value.pop('generation_stages')
    for key in ('session_id', 'request_trace'):
        value.pop(key, None)
    for binding in [value['binding'], *(scope['binding'] for scope in value['scopes'])]:
        for key in ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'):
            binding.pop(key, None)
    return value


def transport():
    path = V / 'm4_source_region_display_001/harness/reused/stdio_checks.py'
    return SimpleNamespace(**run_path(str(path)))


def rpc(identifier, method, **params):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}


def hello(client):
    initial = client.call(rpc('initialize', 'initialize', protocolVersion='2025-03-26', capabilities={},
                              clientInfo={'name': 'witness-original-path-replay', 'version': '1'}))
    client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    listed = client.call(rpc('catalogue', 'tools/list'))
    require(initial['result']['_meta']['human_eye']['source_kind'] == 'installed_distribution',
            'actual_installed_production_required')
    return initial, listed


def run_case(root, binding_path, slot, *, evidence=True):
    """One cold/public and one real hot/public lookup, then original read_images.

    This returns evidence locations and transport facts, not a product gate.
    Renderer counts in the archived generation remain historical; actual new
    construction here is always zero and is reported separately.
    """
    root = Path(root).resolve()
    record = archived(slot)
    arguments = deepcopy(record['request']['params']['arguments'])
    require(arguments.get('response_detail') in ('brief', 'full')
            and arguments.get('include_image', True) is True,
            'closed_actual_image_request_required')
    observations = {}
    try:
        with stock(root, binding_path, slot, evidence=evidence) as client:
            initial, catalogue = hello(client)
            save(root / 'INITIALIZE.json', initial)
            save(root / 'CATALOGUE.json', catalogue)
            for name in ('cold', 'hot'):
                request = rpc(name, 'tools/call', name=TOOL, arguments=deepcopy(arguments))
                response = client.call(request)
                save(root / (name.upper() + '_RESPONSE.json'), response)
                result = response.get('result', {})
                require(result.get('isError') is False, 'actual_production_replay_error/' + name)
                text = result['content'][0]['text']
                public = json.loads(text)
                (root / (name.upper() + '_PUBLIC.json')).write_bytes(text.encode('utf8'))
                images = []
                for block in result['content']:
                    if block['type'] == 'image':
                        raw = base64.b64decode(block['data'], validate=True)
                        images.append({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
                wire = client.output / ('rpc_' + str(client.records[-1]['index']).zfill(2))
                ordinal = 1 if name == 'cold' else 2
                observations[name] = {
                    'response_path': str(root / (name.upper() + '_RESPONSE.json')),
                    'public_path': str(root / (name.upper() + '_PUBLIC.json')),
                    'public_UTF8_bytes': len(text.encode('utf8')), 'images': images,
                    'TX_path': str(wire / 'TX.bin'), 'RX_path': str(wire / 'RX.bin'),
                    'receipt_path': str(wire / 'RECEIPT.json'),
                    'service_result_path': str(root / 'worker' / ('SERVICE_RESULT_' + str(ordinal).zfill(2) + '.json')),
                    'public_schema': public.get('schema'),
                }
            sys.path.insert(0, str(HERE))
            from readback import public_read_images

            refs = deepcopy(record['read_images_request']['params']['arguments']['refs'])
            reread = public_read_images(root / 'read_images', record, catalogue['result']['tools'], refs)
        cache_path = root / 'worker/ACTUAL_CACHE.jsonl'
        cache = [json.loads(line) for line in cache_path.read_bytes().splitlines()]
        eof = read(root / 'worker/EOF.json')
        output = {'status': 'completed', 'slot': slot, 'binding': pin(binding_path),
                  'production_evidence_option': evidence, 'original_slot_root': str(record['folder']),
                  'original_arguments_sha256': hashlib.sha256(compact(arguments)).hexdigest(),
                  **observations, 'read_images': reread,
                  'actual_cache_path': str(cache_path), 'actual_cache_rows': cache,
                  'held_close_path': str(root / 'STOCK_CLOSE.json'),
                  'held_eof_path': str(root / 'HELD_EOF.json'),
                  'worker_EOF_path': str(root / 'worker/EOF.json'),
                  'actual_captures_from_archived_delta': eof['captures'],
                  'actual_renderer_substitutions': eof['compute_substitutions'],
                  'actual_product_PNG_open_reads': eof['png_reads'],
                  'scope_root_original_PNGs': record['original_images'],
                  'actual_new_rasters': 0, 'new_PNG_files': 0, 'new_models': 0,
                  'platform': os.name,
                  'scope': 'closed capture/producer replay, same live service cold publication and normal hot lookup; original public image reader'}
        save(root / 'RESULT.json', output)
        return output
    except BaseException as error:
        if root.exists():
            save(root / 'CASE_FAILURE.json', {'slot': slot, 'type': type(error).__name__, 'message': str(error),
                'completed_observations': observations, 'actual_new_rasters': 0, 'new_models': 0})
        raise


@contextmanager
def stock(root, binding_path, slot, *, evidence=True, deadline_ns=None):
    root = Path(root).resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'private_replay_output_root_required')
    root.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
               '--worker', str(root / 'worker'), '--binding', str(Path(binding_path).resolve(strict=True)),
               '--slot', slot]
    if evidence:
        command.append('--region-task-evidence')
    deadline = deadline_ns or time.perf_counter_ns() + 120_000_000_000
    client = transport().StdioClient(command, root, root / 'wire', deadline)
    try:
        yield client
    finally:
        closed = client.finish()
        save(root / 'STOCK_CLOSE.json', closed)
        require(closed['confirmed'] and closed['exit_code'] == 0 and closed['process_handle_closed'],
                'actual_held_production_not_closed')
        eof = read(root / 'worker/EOF.json')
        events = []
        while True:
            try:
                kind, value, observed_ns = client.events.get_nowait()
            except queue.Empty:
                break
            events.append({'kind': kind, 'observed_ns': observed_ns,
                           'error': value if kind == 'error' else None})
        save(root / 'HELD_EOF.json', {'pid': client.process.pid, 'platform': os.name,
            'stdout_reader_events': events, 'stdout_eof_observed': any(row['kind'] == 'eof' for row in events),
            'input_eof_observed': eof['input_eof_observed'], 'exit_code': closed['exit_code'],
            'process_handle_closed': closed['process_handle_closed'], 'reader_stopped': closed['reader_stopped']})
        require(eof['closed'] and eof['input_eof_observed'] and eof['socket_attempts'] == 0,
                'actual_production_EOF_unverified')


def worker(root, binding_path, slot, evidence):
    root = Path(root).resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'private_worker_output_root_required')
    root.mkdir(parents=True, exist_ok=False)
    record = archived(slot)
    binding = read(binding_path)
    base = Path(binding['install_root']).resolve(strict=True)
    sys.path[:0] = [str(base), binding['dependency_root']]
    bootstrap = run_path(str(V / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'))
    guard = bootstrap['bootstrap'](binding)
    from human_eye_plugin import active_observation_host, live_service, production_server
    from human_eye_plugin.active_observation import fingerprint, geometry
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    from human_eye_plugin.query_policy import validate_query
    from human_eye_plugin.read_context import query_key

    query = validate_query(record['request']['params']['arguments']['query'])
    require(query.get('mode') == 'active_observation' and set(query) == {'mode', 'region_task'},
            'fixed_archived_discovery_query_required')
    counters = {'captures': 0, 'compute_substitutions': 0, 'socket_attempts': 0,
                'blocked_old_writes': 0, 'png_reads': []}

    def old_path(path):
        if not isinstance(path, (str, bytes, os.PathLike)):
            return False
        candidate = Path(os.fsdecode(path)).resolve()
        return any(candidate.is_relative_to(parent.resolve()) for parent in (OLD_ROOT, RECOVERY_ROOT))

    def audit(event, args):
        if event == 'socket.connect':
            counters['socket_attempts'] += 1
            raise AssertionError('no_socket_or_Blender_in_archived_replay')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if old_path(path):
                if writing:
                    counters['blocked_old_writes'] += 1
                    raise AssertionError('closed_runtime_is_read_only')
                if str(path).lower().endswith('.png'):
                    counters['png_reads'].append({'path': str(path), 'service_call': counters.get('service_calls', 0)})
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.replace'):
            for path in args[:2 if event in ('os.rename', 'os.replace') else 1]:
                if old_path(path):
                    counters['blocked_old_writes'] += 1
                    raise AssertionError('closed_runtime_is_read_only')

    sys.addaudithook(audit)

    class ArchivedHost(BlenderMCPHost):
        def _request(self, command, params):
            require(command == 'capture' and params == {}, 'no_unarchived_host_operation')
            self._ensure_live()
            ordinal = counters['captures']
            packet = record['deltas'][min(ordinal, len(record['deltas']) - 1)]
            captured = self._scene_decoder.apply(deepcopy(packet))
            self._record_observation_document(captured)
            counters['captures'] += 1
            append(root / 'HOST_CAPTURE.jsonl', {'index': counters['captures'],
                'capture_state': captured['capture_state'],
                'source_binding': active_observation_host.source_binding(captured)})
            return captured

    host = ArchivedHost(base)
    holder = {}
    original_service = live_service.LiveSpatialService
    original_producer = active_observation_host.observe_capture

    def produce(captured, output_directory, **options):
        counters['compute_substitutions'] += 1
        require(counters['compute_substitutions'] == 1 and options.get('include_image') is True
                and options.get('region_task') == query['region_task'], 'one_archived_raster_producer_only')
        actual = active_observation_host.source_binding(captured)
        expected = record['producer']['binding']
        for key in ('document_epoch', 'capture_state', 'scene_revision', 'source_binding_sha256', 'objects'):
            require(actual[key] == expected[key], 'actual_capture_does_not_bind_archived_producer/' + key)
        objects, _, scene_identity = geometry(active_observation_host.scene_from_capture(captured))
        require(scene_identity == expected['geometry_identity'], 'archived_geometry_identity_mismatch')
        geometry_ids = tuple('geometry:' + fingerprint(item[2]) for item in objects)
        callback = options.get('_geometry_ids_callback')
        require(callable(callback), 'actual_service_geometry_callback_required')
        callback(geometry_ids)
        append(root / 'GENERATOR_SUBSTITUTION.jsonl', {'actual_compute_directory': str(output_directory),
            'archived_existing_frame_directories': sorted({str(Path(frame['image_path']).parent)
                for frame in record['producer']['frames']}),
            'geometry_identity': scene_identity, 'geometry_ids': geometry_ids,
            'actual_new_rasters': 0, 'new_PNG_files': 0})
        return generation_observation(record['producer'])

    class Service(original_service):
        def __init__(self, config_path, *, production_mode=False):
            require(production_mode is True and not holder, 'one_actual_production_service')
            super().__init__(config_path, host=host, production_mode=production_mode)
            holder['service'] = self

        def observe(self, *args, **kwargs):
            counters['service_calls'] = counters.get('service_calls', 0) + 1
            raw = super().observe(*args, **kwargs)
            ordinal = counters['service_calls']
            save(root / ('SERVICE_RESULT_' + str(ordinal).zfill(2) + '.json'), raw)
            context = self._read_context
            cached = context._results[query_key({'mode': 'active_observation', 'include_image': True,
                                                'region_task': query['region_task']})]
            append(root / 'ACTUAL_CACHE.jsonl', {'service_call': ordinal,
                'reported_product_work': raw['work'], 'actual_new_rasters': 0, 'context_python_id': id(context),
                'cache_value_python_id': id(cached), 'cache_observation_python_id': id(cached[0]),
                'generation_repr': repr(context._generation), 'selection_repr': repr(context._capture),
                'source_generation': raw['binding']['capture_state']})
            return raw

        def close(self):
            host.close()
            unchanged = all(pin(row['path']) == row for row in record['pins'])
            save(root / 'EOF.json', {'closed': not host.is_alive, 'pid': os.getpid(),
                'input_eof_observed': streams.eof, **counters,
                'archived_nonimage_inputs_unchanged': unchanged,
                'actual_rasters': 0, 'actual_models': 0,
                'override_scope': ['BlenderMCPHost._request capture via sealed scene delta',
                                   'active_observation_host.observe_capture once from sealed producer']})

    class Streams:
        def __init__(self):
            self.buffer = self
            self.eof = False

        def readline(self, size=-1):
            raw = incoming.buffer.readline(size)
            if not raw:
                self.eof = True
            return raw

        def write(self, text):
            return outgoing.write(text)

        def flush(self):
            return outgoing.flush()

    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': str(base), 'state_file': record['config']['state_file'],
        'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
        'expected_identity': {'source_sha256': binding['source_sha256']}})
    arguments = ['--config', str(config)] + (['--region-task-evidence'] if evidence else [])
    save(root / 'INPUTS.json', {'binding': pin(binding_path), 'archived_slot': slot,
        'source_sha256': binding['source_sha256'], 'source_pins': record['pins'],
        'original_state_path': record['config']['state_file'], 'production_argv': arguments,
        'actual_new_rasters': 0, 'actual_models': 0})
    incoming, outgoing = sys.stdin, sys.stdout
    streams = Streams()
    try:
        live_service.LiveSpatialService = Service
        active_observation_host.observe_capture = produce
        sys.stdin = sys.stdout = streams
        return production_server.main(arguments)
    finally:
        sys.stdin, sys.stdout = incoming, outgoing
        live_service.LiveSpatialService = original_service
        active_observation_host.observe_capture = original_producer
        guard.verify_loaded()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_bytecode_disabled_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--slot', choices=SLOTS, required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    raise SystemExit(worker(args.worker, args.binding, args.slot, args.region_task_evidence))
