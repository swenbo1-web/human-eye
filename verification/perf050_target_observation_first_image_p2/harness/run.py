"""Drive the actual frozen P2 MCP startup and outer owner with archival producer-only observations."""

import argparse
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archives import GOOD_SOURCE, current_reference, digest, images, ordinary_original, pin, read, region_original, require, target_original

HERE = Path(__file__).resolve().parent
LABEL = 'P2'
BAD = {'id': 'reject-P2', 'jsonrpc': '2.0', 'method': 'tools/call',
       'params': {'name': 'human_eye_scene_observe', 'arguments': {
           'include_image': True, 'query': {'mode': 'task', 'objects': [{'name': 'M09'}, {'name': 'M03'}],
                                           'requested_facts': ['surface_proximity']}}}}


def invoke(path, *args):
    return json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', str(path), *args], timeout=45))


def config_check(path, root, current):
    data = read(path)
    require(Path(data['state_file']) == root / 'slots' / LABEL / 'product_state.json'
            and Path(data['state_file']).is_absolute()
            and data['expected_identity']['source_sha256'] == current.SOURCE_SHA, 'temporary_state_not_canonical')


def prepare_held(root, runtime, current):
    folder = root / 'slots' / LABEL
    folder.mkdir(parents=True)
    now = perf_counter_ns()
    original = runtime.Runtime.__mro__[2]
    with patch.dict(original.__init__.__globals__, EXTERNAL=root):
        held = runtime.Runtime(folder, LABEL, now + 90_000_000_000, now + 120_000_000_000)
    held.prepare_device(current.ASSET_SHA256)
    return held


def startup_with_client(held, runtime, current, constructor):
    loaded, reads = [], []

    def loader(name, path):
        loaded.append((name, Path(path)))
        return SimpleNamespace(StdioClient=constructor)

    def watched(path):
        reads.append(Path(path).resolve())
        return read(path)

    startup = runtime.Runtime._start_public_mcp
    globals_ = dict(startup.__globals__, load=loader, read=watched)
    with patch.object(held, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
            held, '_retain', return_value=object()) as retained:
        FunctionType(startup.__code__, globals_)(held, current.PRODUCT_BINDING, read(current.PRODUCT_BINDING))
    retained.assert_called_once_with(held.client.process, 'MCP_RUNTIME_PROOF.json')
    require(loaded == [('_live_stdio_client', current.DISPLAY / 'harness/reused/stdio_checks.py')]
            and reads == [current.PRODUCT_SCHEMA.resolve(), current.CATALOGUE.resolve()],
            'actual_startup_schema_loader_does_not_match_current_install')


def real_writer(root, runtime, current):
    held = prepare_held(root, runtime, current)
    transport_path = current.DISPLAY / 'harness/reused/stdio_checks.py'
    transport = current.load_retained('_target_preflight_actual_stdio', transport_path)
    client = None

    def constructor(command, folder, destination, deadline):
        nonlocal client
        require(Path(command[5]).resolve() == current.HERE / 'mcp_entry.py'
                and Path(command[command.index('--binding')+1]) == current.PRODUCT_BINDING
                and command[command.index('--label')+1] == LABEL, 'actual_P2_startup_wrong_argv')
        # Redirect only its expected root to our local preflight folder. The
        # actual wrapper, recorder and installed serializer run in the child.
        launcher = ('from pathlib import Path; import runpy, sys; '
                    f'sys.path.insert(0, {str(current.HERE)!r}); import common; '
                    'common.EXTERNAL=Path(sys.argv[1]); sys.argv=sys.argv[2:]; '
                    'runpy.run_path(sys.argv[0], run_name="__main__")')
        client = transport.StdioClient(
            command[:5]+['-c', launcher, str(root)]+command[5:], folder, destination, deadline)
        return client

    try:
        startup_with_client(held, runtime, current, constructor)
        rejection = client.call(BAD)
        require(rejection['result']['isError'] and not json.loads(
            rejection['result']['content'][0]['text'])['executed'] and not images(rejection['result']),
            'invalid_product_request_reached_installed_producer')
    finally:
        close = client.finish() if client is not None else {}
    config_check(held.folder / 'PRODUCT_CONFIG.json', root, current)
    meter = [row for row in map(json.loads, (held.folder / 'mcp_io/MCP_IO.jsonl').read_bytes().splitlines())
             if row['method'] == 'tools/call']
    proof = read(held.folder / 'mcp_io/RUNTIME.json')
    require(close['confirmed'] and close['exit_code'] == 0 and len(meter) == 1 and meter[0]['raster_actual'] == 0
            and proof['algorithm_monkeypatches'] == 0 and proof['source_sha256'] == current.SOURCE_SHA
            and not list((held.folder / 'product_full').iterdir()),
            'actual_recorder_rejection_or_exit_contract_failed')
    handshake = []
    for index in range(1, 4):
        folder = held.folder / 'mcp' / f'rpc_{index:02d}'
        tx, rx = folder / 'TX.bin', folder / 'RX.bin'
        handshake.append((read(tx), read(rx) if rx.is_file() else None))
    archived = held.folder / 'mcp' / 'rpc_04'
    require(read(archived / 'TX.bin') == BAD and read(archived / 'RX.bin') == rejection,
            'actual_installed_public_rejection_is_not_the_stdio_wire')
    return handshake, rejection, {'actual_installed_source': proof['source_sha256'], 'normal_exit': True,
                                  'rejected_before_archive_or_raster': True,
                                  'rejection_RX_sha256': digest((archived / 'RX.bin').read_bytes())}


def rebase_frames(archive, slot):
    value = deepcopy(archive['producer'])
    for frame in value['frames']:
        old_png = frame['image_path']
        for key in ('image_path', 'arrays_path'):
            previous = frame[key]
            relative = Path(previous).relative_to(Path(previous).parents[3])
            destination = slot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive['frames'][previous])
            frame[key] = str(destination)
        for row in value['facts']['observations']:
            if row['image_path'] == old_png:
                row['image_path'] = frame['image_path']
    return value


def install_ordinary(held, archive):
    import numpy as np

    row = deepcopy(archive['row'])
    folder = held.folder / 'archived_common_native'
    folder.mkdir()
    for field, content in [('PNG', archive['png']), ('NPZ', archive['npz'])]:
        path = folder / Path(row[field]).name
        path.write_bytes(content)
        row[field] = str(path.resolve())
    with np.load(BytesIO(archive['npz']), allow_pickle=False) as buffers:
        arrays = {name: buffers[name] for name in ('color', 'depth', 'owners', 'triangle_ids')}
    held.device._register(row, arrays)
    return row


def same_target(result, reference, state):
    body = json.loads(result['content'][0]['text'])
    expected = json.loads(reference['result']['content'][0]['text'])
    column = expected['images']['columns'].index('local_image_path')
    target = body['images']['rows'][1][column]
    require(body['images']['rows'][0][column] is None and target is not None
            and Path(target).is_absolute() and Path(target).resolve(strict=True).as_posix() == target
            and Path(target).is_relative_to(state.parent)
            and Path(target).read_bytes() == images(result)[1]
            and images(result) == images(reference['result']), 'new_owner_reply_lost_bound_LEFT_path_or_originals')
    expected['images']['rows'][1][column] = target
    require(body == expected, 'current_installed_target_facts_or_measurement_changed')
    return target


def wrapper(window, held, bridge, runtime, current, target, reference, native, handshake, reject, serializer):
    state = held.folder / 'product_state.json'
    captured = rebase_frames(target, held.folder)
    source = deepcopy(target['scene'])
    source['source_ref'] = 'archived-current-source-readonly-P2-preflight'
    source['objects'] = [{**row, **row['evaluated']} for row in source['objects']]
    held.device._scene = source
    ordinary = install_ordinary(held, native)
    seen, evidence = [], {}

    class Replay:
        def __init__(self, command, folder, destination, deadline):
            require(folder == held.folder and destination == held.folder / 'mcp' and deadline == held.task_deadline
                    and Path(command[5]) == current.HERE / 'mcp_entry.py'
                    and dict(zip(command[6::2], command[7::2], strict=True)) == {
                        '--label': LABEL, '--phase': 'formal', '--config': str(folder / 'PRODUCT_CONFIG.json'),
                        '--binding': str(current.PRODUCT_BINDING), '--ledger': str(held.budget.root),
                        '--evidence': str(folder / 'mcp_io'), '--archive': str(folder / 'product_full')},
                    'actual_startup_replay_argv_mismatch')
            self.process, self.records = object(), []

        def call(self, request):
            index = len(seen)
            seen.append(request)
            if index < 3:
                expected, reply = handshake[index]
                require(request == expected, 'same_installed_startup_handshake_changed')
                return deepcopy(reply)
            if index == 3:
                require(request['params'] == target['request']['params'], 'archived_target_actual_dispatch_args_changed')
                start = perf_counter_ns()
                result = serializer['call'](serializer['server'], request, captured, state)
                location = same_target(result, reference, state)
                outside = serializer['call'](serializer['server'], request, captured, state.with_name('foreign.json'))
                require(not serializer['paths'](outside)
                        and images(outside) == images(result), 'cross_slot_injected_path_escaped_current_binding')
                archive = held.folder / 'product_full'
                qualified = archive / 'call_001/SERVICE_RESULT.json'
                qualified.parent.mkdir(parents=True)
                qualified.write_bytes(json.dumps(captured, ensure_ascii=False).encode())
                index_row = {'index': 1, 'started_ns': start, 'path': str(qualified),
                             'producer_returned_ns': perf_counter_ns(), 'sha256': pin(qualified)['sha256'],
                             'new_observations_for_archive': 0}
                (archive / 'INDEX.jsonl').write_bytes(json.dumps(index_row).encode() + b'\n')
                reply = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
                evidence.update(result=result, location=location, producer_frame_image_rebound=True)
            else:
                require(index == 4 and request['params'] == BAD['params'], 'unexpected_P2_preflight_product_request')
                reply = {**deepcopy(reject), 'id': request['id']}
            self.records.append({'method': request['method'], 'id': request['id']})
            return reply

    startup_with_client(held, runtime, current, Replay)
    config_check(held.folder / 'PRODUCT_CONFIG.json', window, current)
    owner = bridge.Owner(held, {'label': LABEL, 'group': 'P', 'phase': 'formal',
                        'worker_deadline_ns': held.task_deadline, 'output': str(held.folder / 'owner')}, budget=held.budget)
    endpoint = owner.start(held.folder / 'ENDPOINT.json')
    packet = [
        ('initialize', None), ('tools/list', None),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code':
            'observed=scene_data(["M09","M03"])\n'
            'check=shapely.Point(0,0).buffer(1)\n'
            'print(len(observed["objects"]), check.is_empty)'}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code':
            'print(len(observed["objects"]), check.contains(shapely.Point(0,0)))'}}),
        ('tools/call', target['request']['params']),
        ('tools/call', {'name': 'read_images', 'arguments': {
            'refs': [captured['frames'][1]['image_ref'], ordinary['ref']]}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'unexpected': True}}),
        ('tools/call', BAD['params']),
        ('tools/call', {'name': 'read_images', 'arguments': {'refs': ['native-image:foreign-source']}}),
    ]
    requests = []
    for index, (method, params) in enumerate(packet, 1):
        request = {'jsonrpc': '2.0', 'id': index, 'method': method}
        if params is not None:
            request['params'] = params
        requests.append(request)
    audit = held.folder / 'consumer_audit'
    child = [sys.executable, '-I', '-B', '-X', 'utf8', str(current.NS / 'consumer/thin_stdio.py'),
             '--endpoint', str(endpoint), '--audit', str(audit)]
    try:
        proc = subprocess.run(child, input=b''.join(bridge.encoded(message)+b'\n' for message in requests),
                              capture_output=True, timeout=45)
    finally:
        closed = owner.close()
    require(proc.returncode == 0 and closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
            'actual_owner_or_thin_stdio_close_failed/' + proc.stderr.decode(errors='replace')[-1500:])
    responses = [json.loads(line) for line in proc.stdout.splitlines()]
    require([row['id'] for row in responses] == list(range(1, len(requests)+1)), 'actual_stdio_output_identity_changed')
    replies = [row['result'] for row in responses]
    require(replies[1]['tools'] == bridge.TOOLS + [read(current.PRODUCT_SCHEMA)]
            and json.loads(replies[2]['content'][0]['text'])['stdout'].strip() == '2 False'
            and json.loads(replies[3]['content'][0]['text'])['stdout'].strip() == '2 True'
            and replies[4] == evidence['result'] and len(held.public_requests) == 2
            and replies[5]['isError'] is False
            and images(replies[5]) == [images(replies[4])[1], native['png']]
            and replies[6]['isError'] and 'code_string_required' in replies[6]['content'][0]['text']
            and replies[7] == reject['result'] and replies[8]['isError'],
            'actual_owner_target_or_ordinary_or_malformed_input_changed')
    for item in replies[5]['content'][::2]:
        item_body = json.loads(item['text'].splitlines()[1])
        path = Path(item_body['local_image_path'])
        require(path.is_relative_to(held.folder) and path.resolve(strict=True).as_posix() == item_body['local_image_path']
                and digest(path.read_bytes()) == item_body['image_sha256'], 'actual_owner_reread_original_path_bad')
    foreign = window / 'outside_original.png'
    foreign.write_bytes(native['png'])
    registered = held.device.by_ref[ordinary['ref']]
    with patch.dict(registered, PNG=str(foreign)):
        try:
            owner.images([ordinary['ref']], {'image_attachments': []})
        except ValueError as error:
            require(str(error) == 'current_slot_original_png_path_required', 'wrong_cross_slot_ordinary_rejection')
        else:
            raise ValueError('cross_slot_ordinary_path_published')
    with patch.dict(registered, PNG_sha256='0' * 64):
        try:
            owner.images([ordinary['ref']], {'image_attachments': []})
        except ValueError as error:
            require(str(error) == 'current_image_bytes_changed', 'wrong_ordinary_digest_rejection')
        else:
            raise ValueError('invalid_ordinary_file_digest_published')
    journal, = audit.iterdir()
    attempts = []
    for index, (tx, rx) in enumerate(zip(requests, responses, strict=True), 1):
        folder = journal / f'{index:03}'
        receipt = read(folder / 'RECEIPT.json')
        expected_attempt = index - 2 if index > 2 else None
        require(receipt['attempt'] == expected_attempt and receipt['origin'] == 'owner'
                and read(folder / 'TX.bin') == tx and read(folder / 'RX.bin') == rx
                and receipt['response_bytes'] == (folder / 'RX.bin').stat().st_size,
                'actual_args_attempt_or_thin_stdio_receipt_changed')
        if expected_attempt is not None:
            attempts.append(expected_attempt)
    terminal = read(journal / 'EXIT.json')
    counts = held.budget.snapshot()['slots'][LABEL]
    require(terminal['normal_exit'] and not terminal['backend_close_requested'] and terminal['attempts'] == len(attempts)
            and counts['business_admissions'] == len(attempts) and counts['raster_actual'] == 0,
            'actual_P2_preflight_ledger_or_EOF_changed')
    return {'attempts': attempts, 'first_packet_image_binding': True, 'ordinary_reread_binding': True,
            'cross_slot_both_paths_refused': True, 'malformed_arguments_refused': True, 'normal_owner_EOF': True,
            'actual_rasters': 0,
            'first_packet_body_bytes': len(replies[4]['content'][0]['text'].encode()),
            'original_actual_N1_reopened_sha256': native['row']['PNG_sha256']}


def main(namespace, output):
    sys.path.insert(0, str(namespace / 'harness'))
    import admission
    import bridge
    import common
    import runtime
    from closure import startup_closure
    from budget import LIMITS

    require(common.NS == namespace and not common.EXTERNAL.exists(), 'fresh_P2_namespace_required')
    common.asset_identity()
    binding = read(common.PRODUCT_BINDING)
    require(binding['source_sha256'] == GOOD_SOURCE and len(binding['source_manifest']) == 143,
            'preflight_product_binding_changed')
    dispatch = invoke(common.HERE / 'run_slot.py', LABEL, '--dispatch-smoke')
    writer = invoke(common.HERE / 'mcp_entry.py', '--dispatch-smoke')
    require(dispatch['slot'] == writer['label'] == LABEL
            and Path(dispatch['actual_product_schema']) == common.PRODUCT_SCHEMA
            and Path(writer['current_binding']) == common.PRODUCT_BINDING
            and Path(writer['absolute_state_file']) == common.EXTERNAL / 'slots/P2/product_state.json'
            and dispatch['product'] == admission.registered_product()
            and dispatch['fresh_process_prepared_only'] and writer['fresh_process_prepared_only'],
            'actual_P2_wrappers_not_bound_to_current_product')
    target, native, region = (function(common.ROOT) for function in (target_original, ordinary_original, region_original))
    reference, reference_pins = current_reference(common.ROOT)
    shared = common.SEAL / 'SHARED_DEPENDENCY.json'
    sys.path[:0] = [str(common.NS), binding['install_root'], binding['dependency_root'], read(shared)['dependency_root']]
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin.runtime_identity import runtime_identity
    require(runtime_identity()['source_sha256'] == GOOD_SOURCE
            and runtime_identity()['source_kind'] == 'installed_distribution', 'wrong_actual_candidate_import')
    retained = common.V / 'm1_source_region_final_image_001/checks/serializer.py'
    serializer = run_path(str(retained))
    serializer.update(server=LiveSpatialMCPServer, paths=serializer['path_fields'])
    whole = serializer['call'](LiveSpatialMCPServer, region['request'], region['producer'], region['state'])
    require(serializer['payload'](whole) == serializer['payload'](region['reply'])
            and not serializer['path_fields'](whole), 'whole_scene_archive_wrongly_received_target_path')
    with TemporaryDirectory(prefix='w', dir=HERE) as folder:
        work = Path(folder).resolve()
        handshake, rejection, recorder = real_writer(work / 'a', runtime, common)
        replay = work / 'b'
        held = prepare_held(replay, runtime, common)
        result = wrapper(replay, held, bridge, runtime, common, target, reference, native,
                         handshake, rejection, serializer)
    before = {'spawn': None, 'failure': None, 'launch_cleanup': None, 'settlement': None,
              'asset_matches': True, 'copy_matches': None}
    early = {'status': 'failed', 'actual_model_admitted': False, 'model_consumers': 0, 'paid_API_calls': 0}
    receipt = {'status': 'failed', 'owned_budget_passed': True}
    require(admission.can_continue({**early, 'closure_verification': startup_closure(
                **before, startup_entered=False)}, receipt)
            and not admission.can_continue({**early, 'closure_verification': startup_closure(**before)}, receipt),
            'unconfirmed_prestart_or_cleanup_accepted')
    require(not common.EXTERNAL.exists(), 'preflight_touched_actual_runtime_root')
    sources = {
        tuple((row[key] for key in ('path', 'bytes', 'sha256'))) for row in
        target['pins'] + native['pins'] + region['pins'] + reference_pins +
        [pin(path) for path in (Path(__file__), HERE / 'archives.py', shared, common.ASSET,
                                common.PRODUCT_BINDING, common.PRODUCT_SCHEMA, common.CATALOGUE, retained,
                                Path(binding['wheel_path']), common.NS / 'consumer/thin_stdio.py',
                                Path(runtime.Runtime._start_public_mcp.__code__.co_filename),
                                *common.HERE.glob('*.py'))]
    }
    value = {'schema': 'perf050-target-first-image-P2-host-preflight-v1', 'passed': True,
             'actual_Blender_launches': 0, 'model_consumers': 0, 'actual_rasters': 0, 'formal_slots_owned': 0,
             'entrypoints': {'P2': dispatch, 'MCP': writer}, 'limits': LIMITS,
             'original_archived_target_and_read_images': target['outer'],
             'original_archived_native_view': native['evidence'], 'independent_before_after_archived_sources': True,
             'whole_scene_actual_archive_preserved': True,
             'whole_scene_original_PNG_digests': [digest(raw) for raw in images(whole)],
             'isolated_actual_writer_start_and_rejection': recorder, 'current_actual_P2_owner_stdin_forwarding': result,
             'normal_actual_EOF_and_unconfirmed_startup_control': True,
             'source_pins': [{'path': p, 'bytes': n, 'sha256': d} for p, n, d in sorted(sources)]}
    with output.open('x', encoding='utf8', newline='\n') as sink:
        json.dump(value, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write('\n')
    print(pin(output)['sha256'], len(sources), flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_isolated_Python_-I_-B')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--namespace', type=Path, required=True)
    cli.add_argument('--output', type=Path, default=HERE / 'HOST_PREFLIGHT.json')
    args = cli.parse_args()
    main(args.namespace.resolve(strict=True), args.output)
