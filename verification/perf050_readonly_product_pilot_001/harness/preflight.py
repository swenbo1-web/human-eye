"""Replay frozen production inputs through both pilot host paths without spawning Blender."""

import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, FORMAL, HERE, NS, ORDER,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, RECOVERY, SEAL, SLOTS, SOURCE_RUN,
                    asset_identity, load_retained, read, save, sha)
import run_slot


def require(value, reason):
    if not value:
        raise ValueError(reason)


def frozen_recovery(pins):
    directory = SOURCE_RUN.parents[1]
    index_path = RECOVERY / 'RUNTIME_INDEX.json'
    index = read(index_path)
    archive = Path(index['archive']['path'])
    require(archive.parent.resolve() == directory.resolve() and sha(archive) == index['archive']['sha256'],
            'archived_recovery_identity_changed')
    members = {row['path']: row for row in index['files']}
    pins.update((index_path, archive))

    def fetch(zipfile, path):
        path = path.resolve()
        key = path.relative_to(directory.resolve()).as_posix()
        raw = path.read_bytes()
        row = members[key]
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
                and raw == zipfile.read(key), 'original_recovery_payload_changed/' + key)
        pins.add(path)
        return raw

    with ZipFile(archive) as archived:
        exchange = []
        for index in range(1, 5):
            folder = SOURCE_RUN / 'mcp' / f'rpc_{index:02d}'
            raw = fetch(archived, folder / 'TX.bin')
            request = json.loads(raw)
            receipt = json.loads(fetch(archived, folder / 'RECEIPT.json'))
            require((receipt['index'], receipt['method'], receipt['id'], receipt['TX_bytes'], receipt['error'])
                    == (index, request['method'], request.get('id'), len(raw), None), 'archived_recovery_TX_mismatch')
            response = None
            if 'id' in request:
                rx = folder / 'RX.bin'
                received = fetch(archived, rx)
                response = json.loads(received)
                require(receipt['RX_sha256'] == sha(rx) and len(received) == receipt['RX_bytes']
                        and response['id'] == request['id']
                        and response == json.loads(fetch(archived, folder / 'RESPONSE.json')),
                        'archived_recovery_RX_mismatch')
            exchange.append((request, response))
        producer = json.loads(fetch(archived, SOURCE_RUN / 'product_full/call_001/SERVICE_RESULT.json'))
        proof_index = json.loads(fetch(archived, SOURCE_RUN / 'product_calls/call_001/ARCHIVE_AFTER.bin'))
        require(proof_index['sha256'] == sha(SOURCE_RUN / 'product_full/call_001/SERVICE_RESULT.json'),
                'archived_real_producer_mismatch')
        frames = {}
        for frame in producer['frames']:
            for path_key, sha_key in (('image_path', 'image_sha256'), ('arrays_path', 'arrays_sha256')):
                path = Path(frame[path_key])
                frames[str(path)] = fetch(archived, path)
                require(sha(path) == frame[sha_key], 'archived_original_visual_mismatch')
        scene_path = SOURCE_RUN / 'TERMINAL_SOURCE.json'
        scene = json.loads(fetch(archived, scene_path))
        require(scene['source']['asset_sha256'] == ASSET_SHA256 and len(scene['objects']) == 28
                and {obj['name'] for obj in scene['objects']} >= {'N15', 'N23'},
                'wrong_ordinary_probe_source')
        return exchange, producer, frames, scene


def replay_startup(instance, runtime, folder, exchange, binding, producer, frames):
    started = []
    archived_producer = deepcopy(producer)
    startup = runtime.Runtime._start_public_mcp

    class RecordClient:
        def __init__(self, argv, actual, wire_dir, deadline):
            expected = {'--binding': PRODUCT_BINDING, '--config': folder / 'PRODUCT_CONFIG.json',
                        '--ledger': instance.budget.root, '--evidence': folder / 'mcp_io',
                        '--archive': folder / 'product_full', '--phase': 'formal', '--label': 'P1'}
            require(Path(argv[5]).resolve() == HERE / 'mcp_entry.py' and deadline == instance.task_deadline
                    and actual == folder and wire_dir == folder / 'mcp'
                    and dict(zip(argv[6::2], argv[7::2], strict=True)) ==
                    {key: str(value) for key, value in expected.items()}, 'real_P_startup_argv_changed')
            self.process = object()
            self.records = []

        def call(self, request):
            original, response = exchange[len(started)]
            require(request == original, 'original_P_request_changed')
            started.append(request['method'])
            if request['method'] == 'tools/call':
                begin = time.perf_counter_ns()
                for frame in archived_producer['frames']:
                    for key in ('image_path', 'arrays_path'):
                        path = folder / 'offline_relocated_original_frames' / Path(frame[key]).name
                        path.parent.mkdir(exist_ok=True)
                        path.write_bytes(frames[frame[key]])
                        frame[key] = str(path)
                archive = folder / 'product_full'
                result = archive / 'call_001/SERVICE_RESULT.json'
                result.parent.mkdir(parents=True)
                save(result, archived_producer)
                entry = {'index': 1, 'path': str(result), 'sha256': sha(result),
                         'started_ns': begin, 'producer_returned_ns': time.perf_counter_ns()}
                (archive / 'INDEX.jsonl').write_text(json.dumps(entry) + '\n', encoding='utf-8')
                self.records.append({'id': request['id'], 'method': request['method']})
            return deepcopy(response)

    def transport(name, path):
        require(name == '_live_stdio_client' and path.name == 'stdio_checks.py', 'wrong_P_startup_transport')
        return SimpleNamespace(StdioClient=RecordClient)

    paths = []

    def track_read(path):
        paths.append(Path(path).resolve())
        return read(path)

    scope = dict(startup.__globals__, load=transport, read=track_read)
    with patch.object(instance, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
            instance, '_retain', return_value=object()) as retained:
        FunctionType(startup.__code__, scope)(instance, PRODUCT_BINDING, binding)
    retained.assert_called_once_with(instance.client.process, 'MCP_RUNTIME_PROOF.json')
    require(paths == [PRODUCT_SCHEMA.resolve(), CATALOGUE.resolve()] and
            started == ['initialize', 'notifications/initialized', 'tools/list'] and
            read(folder / 'PRODUCT_CONFIG.json')['expected_identity']['source_sha256'] == binding['source_sha256'],
            'canonical_P_startup_not_exercised')
    return started


def run_arm(tmp, label, binding, bridge, runtime, exchange, producer, frames, scene):
    group, phase = SLOTS[label]
    folder = tmp / 'slots' / label
    folder.mkdir(parents=True)
    original_runtime = runtime.Runtime.__mro__[2]
    with patch.dict(original_runtime.__init__.__globals__, {'EXTERNAL': tmp}):
        runtime_instance = runtime.Runtime(folder, label, time.perf_counter_ns() + 90_000_000_000,
                                           time.perf_counter_ns() + 120_000_000_000)
    runtime_instance.prepare_device(ASSET_SHA256)
    source = deepcopy(scene)
    source['source_ref'] = 'sealed-current-assembly-replay'
    source['objects'] = [{**row, **row['evaluated']} for row in source['objects']]
    runtime_instance.device._scene = source
    if group == 'P':
        startup_calls = replay_startup(runtime_instance, runtime, folder, exchange, binding, producer, frames)
    else:
        startup_calls = []
    owner = bridge.Owner(runtime_instance, {'label': label, 'group': group, 'phase': phase,
                         'worker_deadline_ns': runtime_instance.task_deadline, 'output': str(folder / 'owner')},
                         budget=runtime_instance.budget)
    endpoint = read(Path(owner.start(folder / 'ENDPOINT.json')))
    transport = load_retained('_perf050_offline_stdio_exchange', FORMAL.parent /
                              'm4_live_source_region_task_003/thin_stdio.py')
    count = 0
    attempts = 0

    def rpc(method, params=None):
        nonlocal count, attempts
        count += 1
        request = {'jsonrpc': '2.0', 'id': count, 'method': method}
        if params is not None:
            request['params'] = params
        if method == 'tools/call':
            attempts += 1
        return transport.exchange(endpoint, request, attempts if method == 'tools/call' else None, bridge)

    def tool(name, arguments):
        return rpc('tools/call', {'name': name, 'arguments': arguments})['result']

    try:
        init = rpc('initialize')['result']
        require(init['serverInfo']['name'] == 'perf050-readonly-product-pilot' and 'instructions' not in init,
                'unexpected_first_tool_or_arm_hint')
        catalogue = rpc('tools/list')['result']['tools']
        require(catalogue == read(folder / 'owner/TOOLS_SCHEMA.json') and
                {row['name'] for row in catalogue} == bridge.TOOL_NAMES[group], 'actual_P_N_tool_catalogue_changed')
        require(not {'region', 'observe', 'task'} & owner.session.namespace.keys(),
                'private_scoring_or_product_shortcut_exposed')
        measure = tool('execute_python', {'code': 'selected = scene_data(["N15","N23"])\n'
            'first = selected["objects"][0]\n'
            'p = shapely.Point(0,0).buffer(1)\n'
            'print(type(selected).__name__, sorted([o["name"] for o in selected["objects"]]), '
            'int(np.asarray(first["triangles"]).shape[1]), p.contains(shapely.Point(0,0)), Fraction(1,3))'})
        retained = tool('execute_python', {'code': 'print(len(selected["objects"]), p.is_empty)'})
        require(not measure['isError'] and not retained['isError']
                and json.loads(measure['content'][0]['text'])['stdout'].strip() == "dict ['N15', 'N23'] 3 True 1/3"
                and json.loads(retained['content'][0]['text'])['stdout'].strip() == '2 False',
                'ordinary_type_geometry_library_or_cross_call_state_failed')
        rejected = tool('execute_python', {'unexpected': 'param'})
        require(rejected['isError'] and 'code_string_required' in rejected['content'][0]['text'],
                'ordinary_invalid_argument_accepted')
        forbidden = tool('execute_python', {'code': f'open({str(NS / "PLAN.md")!r}, "rb").read()'})
        require(forbidden['isError'] and 'consumer_private_file' in forbidden['content'][0]['text'],
                'private_qualification_context_readable')
        arguments = exchange[-1][0]['params']['arguments']
        if group == 'P':
            forwarded = tool(bridge.PRODUCT_TOOL, arguments)
            require(forwarded == exchange[-1][1]['result'] and len(runtime_instance.public_requests) == 1
                    and startup_calls[-1] == 'tools/call', 'original_P_body_not_transparently_forwarded')
            frame_ref = producer['frames'][0]['image_ref']
        else:
            refused = tool(bridge.PRODUCT_TOOL, arguments)
            require(refused['isError'] and not runtime_instance.public_requests, 'P_tool_accessible_in_native_arm')
            frame = producer['frames'][0]
            copy = folder / 'archived_PNG_replay.png'
            copy.write_bytes(frames[frame['image_path']])
            frame_ref = 'archived-read-image-test'
            runtime_instance.device.by_ref[frame_ref] = {'PNG': str(copy), 'PNG_sha256': sha(copy),
              'size_px': [512, 512], 'origin': 'common_native', 'view': 'SCENE'}
        original_rows = tool('read_images', {'refs': [frame_ref]})
        images = [base64.b64decode(row['data'], validate=True) for row in original_rows['content']
                  if row['type'] == 'image']
        require(not original_rows['isError'] and images == [frames[producer['frames'][0]['image_path']]],
                'ordinary_original_PNG_attachment_changed')
    finally:
        closure = owner.close()
    require(closure['confirmed'] and not closure['errors'] and not closure['transport_errors'],
            'actual_outer_loopback_closure_failed')
    return {'label': label, 'tool_catalogue': catalogue, 'both_ordinary_probes': True, 'private_read_rejected': True,
            'bad_arguments_rejected': True, 'original_PNG_replayed': True, 'outer_closure_passed': True,
            'product_startup_requests': startup_calls, 'product_original_wire_replayed': group == 'P'}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and not EXTERNAL.exists(), 'fresh_pilot_preflight_required')
    binding = read(PRODUCT_BINDING)
    shared_path = SEAL / 'SHARED_DEPENDENCY.json'
    shared = read(shared_path)
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    import bridge
    import runtime
    from closure import ready_closure, startup_closure

    entries = {label: json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(HERE / 'run_slot.py'),
                        label, '--dispatch-smoke'], timeout=45)) for label in ORDER}
    entries['MCP'] = json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(HERE / 'mcp_entry.py'),
                                                       '--dispatch-smoke'], timeout=45))
    asset_identity()
    pins = {ASSET, PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, shared_path,
            *(HERE.glob('*.py')), *(FORMAL / 'harness').glob('*.py'),
            FORMAL / 'bridge.py', FORMAL / 'frame_device.py', RECOVERY / 'harness/runtime.py',
            FORMAL.parent / 'm4_live_source_region_task_003/thin_stdio.py', SEAL / 'native_tools.py',
            Path(runtime.Runtime._start_public_mcp.__code__.co_filename)}
    exchange, producer, frames, scene = frozen_recovery(pins)
    with tempfile.TemporaryDirectory(prefix='perf050_host_preflight_') as name:
        tmp = Path(name).resolve()
        arms = [run_arm(tmp, label, binding, bridge, runtime, exchange, producer, frames, scene) for label in ORDER]
    require([row for row in arms[1]['tool_catalogue'] if row['name'] != bridge.PRODUCT_TOOL] ==
            arms[0]['tool_catalogue'] and [row for row in arms[1]['tool_catalogue'] if row['name'] == bridge.PRODUCT_TOOL] ==
            [read(PRODUCT_SCHEMA)], 'ordinary_catalogues_differ_or_extra_product_tool')
    closure_paths = ((Path('D:/he_m4_dense_panel_sweep_formal_001/slots/N1'), 'N'), (SOURCE_RUN, 'P'))
    for folder, group in closure_paths:
        rp, proof = folder / 'RUNTIME_CLOSE.json', folder / 'NATIVE_RUNTIME_PROOF.json'
        require(ready_closure(read(rp), group, read(proof))['passed'], 'original_ready_close_failed')
        pins.update((rp, proof))
    clean = startup_closure(spawn=None, failure=None, launch_cleanup=None, settlement=None,
                            asset_matches=True, copy_matches=None, startup_entered=False)
    unconfirmed = startup_closure(spawn=None, failure=None, launch_cleanup=None, settlement=None,
                                  asset_matches=True, copy_matches=None)
    record = {'status': 'failed', 'closure_verification': clean, 'actual_model_admitted': False,
              'model_consumers': 0, 'paid_API_calls': 0}
    receipt = {'status': 'failed', 'owned_budget_passed': True}
    require(admission.can_continue(record, receipt) and
            not admission.can_continue(dict(record, closure_verification=unconfirmed), receipt),
            'early_return_or_unconfirmed_host_admission_changed')
    require(not EXTERNAL.exists(), 'offline_probe_touched_real_pilot_root')
    path = HERE / 'HOST_PREFLIGHT.json'
    save(path, {'passed': True, 'actual_Blender_launches': 0, 'actual_model_calls': 0,
                'actual_rasters': 0, 'ledger_limits': LIMITS, 'entrypoints': entries, 'arms': arms,
                'startup_cleanup_rejection': True, 'original_readonly_closure_controls': True,
                'source_pins': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                                for p in sorted({p.resolve() for p in pins})]})
    print('Read-only host preflight passed', sha(path))


if __name__ == '__main__':
    main()
