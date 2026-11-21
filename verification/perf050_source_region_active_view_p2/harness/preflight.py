"""Replay original candidate evidence through the P2 host without Blender or a model."""

import base64
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission
from budget import LIMITS
from common import (ACTIVE_VIEW, ASSET, ASSET_SHA256, CATALOGUE, DISPLAY, EXTERNAL, FORMAL, NS, PILOT,
                    PRIOR, PRODUCT_BINDING, PRODUCT_SCHEMA, RECOVERY, SEAL, asset_identity,
                    load_retained, read, save, sha)


LABEL = 'P2'


def require(value, reason):
    if not value:
        raise ValueError(reason)


@contextmanager
def original_archive(namespace, pins):
    index_path = namespace / 'RUNTIME_INDEX.json'
    index = read(index_path)
    archive_path = Path(index['archive']['path'])
    require(sha(archive_path) == index['archive']['sha256'], 'sealed_original_runtime_changed')
    rows = {row['path']: row for row in index['files']}
    pins.update((index_path, archive_path))
    with ZipFile(archive_path) as archive:
        require(set(archive.namelist()) == rows.keys(), 'sealed_original_membership_changed')

        def fetch(name):
            path = archive_path.parent / name
            payload = path.read_bytes()
            row = rows[name]
            require(len(payload) == row['bytes'] and sha(path) == row['sha256'] and payload == archive.read(name),
                    'sealed_original_payload_changed/' + name)
            pins.add(path)
            return payload

        yield fetch


def stdio_original(fetch, slot, index):
    folder = f'slots/{slot}/mcp/rpc_{index:02d}'
    tx = fetch(folder + '/TX.bin')
    request = json.loads(tx)
    receipt = json.loads(fetch(folder + '/RECEIPT.json'))
    require((receipt['index'], receipt['method'], receipt['id'], receipt['TX_bytes'], receipt['error'])
            == (index, request['method'], request.get('id'), len(tx), None), 'archived_stdio_tx_mismatch')
    response = None
    if 'id' in request:
        from hashlib import sha256
        rx = fetch(folder + '/RX.bin')
        response = json.loads(rx)
        require((sha256(rx).hexdigest(), len(rx), response['id']) == (
                receipt['RX_sha256'], receipt['RX_bytes'], request['id'])
                and response == json.loads(fetch(folder + '/RESPONSE.json')), 'archived_stdio_rx_mismatch')
    return request, response


def candidate_original(pins):
    from hashlib import sha256
    with original_archive(ACTIVE_VIEW, pins) as fetch:
        exchange = [stdio_original(fetch, 'B', index) for index in range(1, 6)]
        meters = [row for row in map(json.loads, fetch('slots/B/mcp_io/MCP_IO.jsonl').splitlines())
                  if row['method'] == 'tools/call']
        require([row['raster_actual'] for row in meters] == [2, 0], 'original_candidate_raster_meter_changed')
        core = json.loads(fetch('slots/B/mcp_io/RUNTIME.json'))
        require(core['source_sha256'] == admission.registered_product()['source_sha256']
                and core['binding_sha256'] == sha(PRODUCT_BINDING), 'original_candidate_install_changed')
        pair = []
        for ordinal, step in enumerate(('cold', 'hot'), 1):
            inner_tx, inner_rx = exchange[ordinal + 2]
            folder = f'slots/B/batch/rpc_{ordinal + 2:02d}'
            tx, rx = (fetch(folder + name) for name in ('/TCP_TX.bin', '/TCP_RX.bin'))
            receipt = json.loads(fetch(folder + '/RECEIPT.json'))
            outer_tx, outer_rx = json.loads(tx), json.loads(rx)
            message = {**inner_tx, 'id': 'source-region-' + step}
            require(outer_tx == {'operation': 'attached_mcp', 'request_id': message['id'],
                    'args': {'message': message, 'kind': 'native', 'attempt': ordinal}},
                    'archived_outer_attempt_or_payload_changed')
            require(outer_rx.get('ok') is True and outer_rx['request_id'] == message['id']
                    and outer_rx['result'] == receipt['response'] == {**inner_rx, 'id': message['id']}
                    and (len(tx), len(rx), sha256(tx).hexdigest(), sha256(rx).hexdigest()) ==
                    tuple(receipt[key] for key in ('TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')),
                    'archived_outer_text_png_or_meter_receipt_changed')
            pair.append({'ord': ordinal, 'kind': step, 'request_sha256': receipt['TX_sha256'],
                         'reply_sha256': receipt['RX_sha256'], 'rasters': meters[ordinal - 1]['raster_actual']})
        producer_bytes = fetch('slots/B/product_full/call_001/SERVICE_RESULT.json')
        producer = json.loads(producer_bytes)
        proof = json.loads(fetch('slots/B/product_calls/call_001/ARCHIVE_AFTER.bin'))
        require(proof['sha256'] == sha256(producer_bytes).hexdigest(), 'archived_original_producer_link_changed')
        frame, = producer['frames']
        frames = {frame[key]: fetch(Path(frame[key]).relative_to(EXTERNAL.parent /
                        'he_m4_source_region_active_view_001').as_posix()) for key in ('image_path', 'arrays_path')}
        content = exchange[3][1]['result']['content']
        body = json.loads(content[0]['text'])
        witness = body['visibility']['complete_witness']
        packed = body['image_scope']['objects']
        directory = [dict(zip(packed['columns'], row, strict=True)) for row in packed['rows']]
        require(body['schema'] == 'source-region-brief-v3' and witness['view_name'] == frame['view_name'] == 'RIGHT'
                and witness['frame_identity'] == frame['frame_identity']
                and witness['selected_surface_pixels'] == 86955 and witness['contrasting_boundary_pixels'] == 1300
                and directory == producer['binding']['image_scope']['objects'] and len(directory) == 28
                and len(content) == 2 and base64.b64decode(content[1]['data'], validate=True) == frames[frame['image_path']]
                and sha256(frames[frame['image_path']]).hexdigest() == frame['image_sha256']
                and sha256(frames[frame['arrays_path']]).hexdigest() == frame['arrays_sha256'],
                'archived_candidate_witness_or_lossless_directory_changed')
        scene = json.loads(fetch('slots/B/TERMINAL_SOURCE.json'))
        require(scene['source']['asset_sha256'] == ASSET_SHA256 and len(scene['objects']) == 28,
                'archived_current_assembly_changed')
        closing = (json.loads(fetch('slots/B/RUNTIME_CLOSE.json')),
                   json.loads(fetch('slots/B/NATIVE_RUNTIME_PROOF.json')))
    return exchange[:4], producer, frames, scene, pair, closing


def reject_original(pins):
    with original_archive(PILOT, pins) as fetch:
        rejection = stdio_original(fetch, 'P1', 6)
        require(rejection == (json.loads(fetch('slots/P1/owner/tool_04/PRODUCT_REQUEST.json')),
                              json.loads(fetch('slots/P1/owner/tool_04/PRODUCT_RESPONSE.json')))
                and rejection[1]['result']['isError'] and not json.loads(
                    rejection[1]['result']['content'][0]['text'])['executed'],
                'archived_product_validation_failure_changed')
        before, after = (fetch('slots/P1/product_calls/call_003/ARCHIVE_' + phase + '.bin')
                         for phase in ('BEFORE', 'AFTER'))
        require(before == after, 'rejected_request_had_unexpected_producer_record')
    return rejection


def isolated_writer(work, binding, requests, rejected):
    """Start the real installed Python recorder in temp, with no available Blender host."""
    work.mkdir()
    config = work / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': str(work / 'state.json'),
        'audit_file': str(work / 'audit.jsonl'), 'expected_identity': {'source_sha256': binding['source_sha256']},
        'request_budget_s': 30, 'blender': {'host': '127.0.0.1', 'port': 1, 'timeout_s': 1}})
    recorder = PRIOR / 'harness/mcp_entry.py'
    invoke = ('import runpy, sys; entry=sys.argv[1]; sys.argv=sys.argv[1:]; '
              f'sys.path.insert(0,{str(HERE)!r}); import budget; runpy.run_path(entry, run_name="__main__")')
    command = [sys.executable, '-I', '-B', '-X', 'utf8', '-c', invoke, str(recorder),
        '--binding', str(PRODUCT_BINDING), '--config', str(config), '--ledger', str(work / 'budget'),
        '--evidence', str(work / 'mcp_io'), '--archive', str(work / 'archive'),
        '--phase', 'formal', '--label', LABEL]
    transport = load_retained('_perf050_p2_probe_writer_transport', DISPLAY / 'harness/reused/stdio_checks.py')
    client = transport.StdioClient(command, work, work / 'mcp', time.perf_counter_ns() + 35_000_000_000)
    try:
        exchange = [(request, client.call(request)) for request in requests]
        refusal = client.call(rejected[0])
    finally:
        closure = client.finish()
    proof = read(work / 'mcp_io/RUNTIME.json')
    require(closure['confirmed'] and closure['exit_code'] == 0 and proof['algorithm_monkeypatches'] == 0
            and proof['source_sha256'] == binding['source_sha256']
            and exchange[0][1]['result']['_meta']['human_eye']['source_sha256'] == binding['source_sha256']
            and exchange[2][1]['result']['tools'] == read(CATALOGUE)
            and refusal == rejected[1] and not list((work / 'archive').iterdir()),
            'actual_candidate_writer_identity_rejection_or_early_exit_changed')
    meters = [row for row in map(json.loads, (work / 'mcp_io/MCP_IO.jsonl').read_bytes().splitlines())
              if row['method'] == 'tools/call']
    one, = meters
    require(one['raster_actual'] == 0, 'candidate_validation_rejection_reached_raster')
    return exchange, {'source_sha256': proof['source_sha256'], 'closed': True,
                      'real_candidate_rejection': True, 'rejected_rasters': 0,
                      'recorder_binding_sha256': proof['binding_sha256']}


def replay_client(instance, runtime, folder, binding, startup_exchange, successful, rejected, producer, frames):
    expected = {'--binding': PRODUCT_BINDING, '--config': folder / 'PRODUCT_CONFIG.json',
                '--ledger': instance.budget.root, '--evidence': folder / 'mcp_io',
                '--archive': folder / 'product_full', '--phase': 'formal', '--label': LABEL}
    used, checked_paths = [], []

    class ReplayStdio:
        def __init__(self, argv, actual_folder, wire_dir, deadline):
            require(actual_folder == folder and wire_dir == folder / 'mcp' and deadline == instance.task_deadline
                    and Path(argv[5]).resolve() == HERE / 'mcp_entry.py'
                    and dict(zip(argv[6::2], argv[7::2], strict=True)) == {k: str(v) for k, v in expected.items()},
                    'formal_P2_startup_argv_changed')
            self.process = object()
            self.records = []

        def call(self, request):
            offset = len(used)
            used.append(request['method'])
            if offset < len(startup_exchange):
                tx, rx = startup_exchange[offset]
                require(request == tx, 'new_candidate_startup_differs_from_archived_request')
                return deepcopy(rx)
            if offset == len(startup_exchange):
                require(request == successful[0], 'cold_candidate_product_request_changed')
                started = time.perf_counter_ns()
                record = deepcopy(producer)
                original = record['frames'][0]
                cache = folder / 'sealed_actual_frame'
                cache.mkdir()
                for key in ('image_path', 'arrays_path'):
                    path = cache / Path(original[key]).name
                    path.write_bytes(frames[original[key]])
                    original[key] = str(path)
                archive = folder / 'product_full'
                path = archive / 'call_001/SERVICE_RESULT.json'
                path.parent.mkdir(parents=True)
                save(path, record)
                row = {'index': 1, 'path': str(path), 'started_ns': started, 'sha256': sha(path),
                       'producer_returned_ns': time.perf_counter_ns()}
                (archive / 'INDEX.jsonl').write_text(json.dumps(row) + '\n', encoding='utf8')
                reply = successful[1]
            else:
                require(offset == len(startup_exchange) + 1 and request['params'] == rejected[0]['params'],
                        'formal_rejection_provenance_changed')
                reply = rejected[1]
            self.records.append({'id': request['id'], 'method': request['method']})
            return {**deepcopy(reply), 'id': request['id']}

    def loader(name, path):
        require(name == '_live_stdio_client' and path == DISPLAY / 'harness/reused/stdio_checks.py',
                'formal_P2_loaded_another_transport')
        return SimpleNamespace(StdioClient=ReplayStdio)

    def watched_read(path):
        checked_paths.append(Path(path).resolve())
        return read(path)

    startup = runtime.Runtime._start_public_mcp
    globals_ = dict(startup.__globals__, load=loader, read=watched_read)
    with patch.object(instance, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
            instance, '_retain', return_value=object()) as retained:
        FunctionType(startup.__code__, globals_)(instance, PRODUCT_BINDING, binding)
    retained.assert_called_once_with(instance.client.process, 'MCP_RUNTIME_PROOF.json')
    require(checked_paths == [PRODUCT_SCHEMA.resolve(), CATALOGUE.resolve()]
            and used == ['initialize', 'notifications/initialized', 'tools/list']
            and read(folder / 'PRODUCT_CONFIG.json')['expected_identity']['source_sha256'] == binding['source_sha256'],
            'formal_P2_canonical_schema_or_candidate_identity_not_exercised')
    return used


def replay_outer(window, bridge, runtime, binding, startup, successful, rejected, producer, frames, scene):
    folder = window / 'slots' / LABEL
    folder.mkdir(parents=True)
    began = time.perf_counter_ns()
    original = runtime.Runtime.__mro__[2]
    with patch.dict(original.__init__.__globals__, EXTERNAL=window):
        held = runtime.Runtime(folder, LABEL, began + 90_000_000_000, began + 120_000_000_000)
    held.prepare_device(ASSET_SHA256)
    source = deepcopy(scene)
    source['source_ref'] = 'sealed-current-assembly-replay'
    source['objects'] = [{**row, **row['evaluated']} for row in source['objects']]
    held.device._scene = source
    seen = replay_client(held, runtime, folder, binding, startup, successful, rejected, producer, frames)
    owner = bridge.Owner(held, {'label': LABEL, 'group': 'P', 'phase': 'formal',
                        'worker_deadline_ns': held.task_deadline, 'output': str(folder / 'owner')}, budget=held.budget)
    endpoint = owner.start(folder / 'ENDPOINT.json')
    image_ref = producer['frames'][0]['image_ref']
    messages = [
        ('initialize', None),
        ('tools/list', None),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code':
         'selected = scene_data(["N15","N23"])\n'
         'point = shapely.Point(0,0).buffer(1)\n'
         'print(type(selected).__name__, len(selected["objects"]), point.contains(shapely.Point(0,0)), Fraction(1,3))'}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': 'print(len(selected["objects"]), point.is_empty)'}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'unexpected': True}}),
        ('tools/call', successful[0]['params']),
        ('tools/call', {'name': 'read_images', 'arguments': {'refs': [image_ref]}}),
        ('tools/call', rejected[0]['params']),
    ]
    shell = []
    for index, (method, params) in enumerate(messages, 1):
        message = {'jsonrpc': '2.0', 'id': index, 'method': method}
        if params is not None:
            message['params'] = params
        shell.append(message)
    request_bytes = b''.join(bridge.encoded(row) + b'\n' for row in shell)
    audit = folder / 'consumer_attachments'
    try:
        process = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
                                  '--endpoint', str(endpoint), '--audit', str(audit)],
                                 input=request_bytes, capture_output=True, timeout=45)
        process.check_returncode()
    finally:
        closed = owner.close()
    require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
            'actual_preflight_owner_close_unconfirmed')
    entry, = audit.iterdir()
    shapes = [json.loads(line) for line in process.stdout.splitlines()]
    require([row['id'] for row in shapes] == list(range(1, len(shell) + 1)), 'outer_response_ids_do_not_match')
    replies = [row['result'] for row in shapes]
    require(replies[0]['serverInfo']['name'] == 'perf050-readonly-product-pilot'
            and 'instructions' not in replies[0]
            and replies[1]['tools'] == read(folder / 'owner/TOOLS_SCHEMA.json')
            and replies[1]['tools'] == bridge.TOOLS + [read(PRODUCT_SCHEMA)]
            and not {'region', 'observe', 'task'} & owner.session.namespace.keys(), 'original_natural_tool_directory_changed')
    expected_stdout = ("dict 2 True 1/3", "2 False")
    require(all(not row['isError'] and json.loads(row['content'][0]['text'])['stdout'].strip() == expected
                for row, expected in zip(replies[2:4], expected_stdout, strict=True))
            and replies[4]['isError'] and 'code_string_required' in replies[4]['content'][0]['text'],
            'ordinary_geometry_cross_call_or_parameter_rejection_changed')
    transmitted = replies[5]
    source_png = frames[producer['frames'][0]['image_path']]
    image_blocks = [base64.b64decode(row['data'], validate=True) for row in replies[6]['content'] if row['type'] == 'image']
    require(transmitted == successful[1]['result'] and replies[7] == rejected[1]['result']
            and image_blocks == [source_png] and seen[3:] == ['tools/call', 'tools/call']
            and len(held.public_requests) == 2, 'real_outer_candidate_text_ORIGINAL_PNG_or_rejection_changed')
    attempts = []
    for index, (message, response) in enumerate(zip(shell, shapes, strict=True), 1):
        wire = entry / f'{index:03d}'
        row = read(wire / 'RECEIPT.json')
        expected_attempt = index - 2 if index > 2 else None
        require(row['attempt'] == expected_attempt and row['origin'] == 'owner'
                and row['response_bytes'] == (wire / 'RX.bin').stat().st_size
                and row['request_bytes'] == (wire / 'TX.bin').stat().st_size
                and read(wire / 'TX.bin') == message and read(wire / 'RX.bin') == response,
                'real_thin_stdio_attempt_or_meter_changed')
        if expected_attempt is not None:
            attempts.append(expected_attempt)
    terminal = read(entry / 'EXIT.json')
    counts = held.budget.snapshot()['slots'][LABEL]
    require(terminal['normal_exit'] and not terminal['backend_close_requested'] and terminal['attempts'] == len(attempts)
            and counts['business_admissions'] == len(attempts) and counts['raster_actual'] == 0,
            'actual_preflight_ledger_or_clean_EOF_changed')
    return {'tools': sorted(row['name'] for row in replies[1]['tools']), 'attempts': attempts,
            'candidate_returned_original_text_and_PNG': True, 'original_png_reopened': True,
            'actual_tool_rejection_preserved': True, 'closed': True, 'business_replayed': len(attempts)}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and not EXTERNAL.exists(),
            'fresh_P2_isolated_preflight_required')
    binding = read(PRODUCT_BINDING)
    shared = SEAL / 'SHARED_DEPENDENCY.json'
    sys.path[:0] = [str(NS), binding['dependency_root'], read(shared)['dependency_root']]
    import bridge
    import runtime
    from closure import ready_closure, startup_closure

    pins = {ASSET, PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, Path(binding['wheel_path']), shared,
            *(HERE.glob('*.py')), *(FORMAL / 'harness').glob('*.py'), FORMAL / 'bridge.py',
            FORMAL / 'frame_device.py', RECOVERY / 'harness/runtime.py', SEAL / 'native_tools.py',
            PRIOR / 'harness/mcp_entry.py', PRIOR / 'harness/owned_runtime.py',
            PRIOR / 'harness/reused/verified_bootstrap.py', PRIOR / 'thin_stdio.py',
            DISPLAY / 'harness/reused/stdio_checks.py', Path(runtime.Runtime._start_public_mcp.__code__.co_filename),
            NS / 'consumer/driver.py', NS / 'consumer/thin_stdio.py'}
    run_smoke = [sys.executable, '-I', '-B', str(HERE / 'run_slot.py'), LABEL, '--dispatch-smoke']
    mcp_smoke = [sys.executable, '-I', '-B', str(HERE / 'mcp_entry.py'), '--dispatch-smoke']
    dispatch = json.loads(subprocess.check_output(run_smoke, timeout=45))
    writer = json.loads(subprocess.check_output(mcp_smoke, timeout=45))
    require(dispatch['slot'] == writer['label'] == LABEL and dispatch['product'] == admission.registered_product()
            and Path(dispatch['actual_product_schema']) == PRODUCT_SCHEMA
            and Path(writer['current_binding']) == PRODUCT_BINDING and dispatch['consumer_driver'] == str(NS / 'consumer/driver.py')
            and dispatch['fresh_process_prepared_only'] and writer['fresh_process_prepared_only'],
            'new_actual_entrypoints_do_not_resolve_frozen_candidate_and_consumer')
    asset_identity()
    archive, producer, frames, scene, past_pair, original_close = candidate_original(pins)
    reject = reject_original(pins)
    with TemporaryDirectory(prefix='perf050_p2_host_preflight_') as name:
        temporary = Path(name).resolve()
        live, writer_close = isolated_writer(temporary / 'stdio', binding, [row[0] for row in archive[:3]], reject)
        require(live == archive[:3], 'actual_candidate_handshake_differs_from_its_archived_qualification')
        outer = replay_outer(temporary, bridge, runtime, binding, live, archive[3], reject, producer, frames, scene)
    require(ready_closure(original_close[0], 'P', original_close[1])['passed'], 'original_candidate_close_changed')
    closed_early = startup_closure(spawn=None, failure=None, launch_cleanup=None, settlement=None,
                                  asset_matches=True, copy_matches=None, startup_entered=False)
    unconfirmed = startup_closure(spawn=None, failure=None, launch_cleanup=None, settlement=None,
                                  asset_matches=True, copy_matches=None)
    early = {'status': 'failed', 'closure_verification': closed_early, 'actual_model_admitted': False,
             'model_consumers': 0, 'paid_API_calls': 0}
    receipt = {'status': 'failed', 'owned_budget_passed': True}
    require(admission.can_continue(early, receipt)
            and not admission.can_continue({**early, 'closure_verification': unconfirmed}, receipt),
            'early_cleanup_escape_or_unconfirmed_host_accepted')
    require(not EXTERNAL.exists(), 'offline_preflight_touched_actual_P2_runtime')
    output = HERE / 'HOST_PREFLIGHT.json'
    save(output, {'passed': True, 'actual_Blender_launches': 0, 'actual_model_calls': 0,
        'actual_rasters': 0, 'actual_pilot_owned_slots': 0, 'ledger_limits': LIMITS,
        'entrypoints': {'P2': dispatch, 'MCP': writer},
        'archived_candidate_outer_attempts': past_pair, 'lossless_original_display_rows': 28,
        'candidate_recorder': writer_close, 'actual_P2_outer_thin_stdio_replay': outer,
        'original_candidate_closure_and_early_cleanup_verified': True,
        'source_pins': [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                        for path in sorted({p.resolve() for p in pins})]})
    print('Source-region P2 host preflight passed', sha(output), len(pins), flush=True)


if __name__ == '__main__':
    main()
