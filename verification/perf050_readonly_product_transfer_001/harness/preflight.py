"""Check both actual host entries against a bound archival scene without launching Blender."""

import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import FunctionType, SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, CATALOGUE, DISPLAY, EXTERNAL, FORMAL, NS, ORDER, PRIOR, PRODUCT_BINDING,
                    PRODUCT_SCHEMA, SEAL, SLOTS, asset_identity, load_retained, read, save, sha)


P3 = NS.parent / 'perf050_source_region_final_image_p3'
SOURCE = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1/TERMINAL_SOURCE.json')
SOURCE_DIGEST = 'aae8ad86e3c79032346853360d212c4614c71d20cc50b7b1375786860166e927'


def require(value, problem):
    if not value:
        raise ValueError(problem)


def entry(path, *arguments):
    return json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(path), *arguments], timeout=35))


def start_product(held, runtime, window, binding, archived, rejected):
    startup = runtime.Runtime._start_public_mcp
    real_transport = load_retained('_perf050_transfer_stdio_probe', DISPLAY / 'harness/reused/stdio_checks.py')
    reads = []
    original = None

    def probe_client(command, folder, destination, deadline):
        require(Path(command[5]) == HERE / 'mcp_entry.py', 'wrong_actual_mcp_entry')
        require(Path(command[command.index('--binding') + 1]) == PRODUCT_BINDING, 'wrong_actual_mcp_binding')
        # Redirect only the expected run-root identity to the disposable namespace.
        launcher = ('from pathlib import Path; import runpy, sys; '
                    f'sys.path.insert(0, {str(HERE)!r}); import common; '
                    'common.EXTERNAL=Path(sys.argv[1]); sys.argv=sys.argv[2:]; '
                    'runpy.run_path(sys.argv[0], run_name="__main__")')
        nonlocal original
        original = real_transport.StdioClient(command[:5] + ['-c', launcher, str(window)] + command[5:],
                                             folder, destination, deadline)
        return original

    def watched_read(path):
        reads.append(Path(path).resolve())
        return read(path)

    def transport_loader(name, path):
        require(name == '_live_stdio_client' and path == DISPLAY / 'harness/reused/stdio_checks.py',
                'wrong_actual_mcp_transport')
        return SimpleNamespace(StdioClient=probe_client)

    checks = dict(startup.__globals__, load=transport_loader, read=watched_read)
    try:
        with patch.object(held, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
                held, '_retain', return_value=object()) as retained:
            FunctionType(startup.__code__, checks)(held, PRODUCT_BINDING, binding)
        retained.assert_called_once_with(original.process, 'MCP_RUNTIME_PROOF.json')
        rx = original.call(rejected[0])
        proof = read(held.folder / 'mcp_io/RUNTIME.json')
        require(rx == rejected[1] and proof['algorithm_monkeypatches'] == 0
                and proof['source_sha256'] == binding['source_sha256']
                and reads == [PRODUCT_SCHEMA.resolve(), CATALOGUE.resolve()],
                'actual_candidate_startup_identity_or_rejection_changed')
        for index, (request, reply) in enumerate(archived, 1):
            call = held.folder / 'mcp' / f'rpc_{index:02d}'
            require(read(call / 'TX.bin') == request
                    and (reply is None or read(call / 'RX.bin') == reply), 'archived_candidate_handshake_changed')
        meter = [row for row in map(json.loads, (held.folder / 'mcp_io/MCP_IO.jsonl').read_bytes().splitlines())
                 if row['method'] == 'tools/call']
        require(len(meter) == 1 and meter[0]['raster_actual'] == 0, 'actual_rejection_reached_raster')
    finally:
        closed = original.finish() if original is not None else {}
    require(closed['confirmed'] and closed['exit_code'] == 0, 'actual_candidate_early_exit_unconfirmed')
    return {'actual_writer_invoked': True, 'source_sha256': binding['source_sha256'],
            'schema_read': str(PRODUCT_SCHEMA), 'archived_handshake_matches': True, 'reject_matches': True,
            'rejection_rasters': 0, 'exit_confirmed': True}


def check_content(reply, frame):
    body, caption, block = reply['content'] if frame else (None, *reply['content'])
    caption_prefix, detail_text = caption['text'].split('\n', 1)
    detail = json.loads(detail_text)
    ref = caption_prefix.split(' (512x512, image/png)')[0]
    path = Path(detail['local_image_path'])
    raw = base64.b64decode(block['data'], validate=True)
    require(not reply['isError'] and path.is_absolute() and path.resolve() == path
            and path.read_bytes() == raw and sha(path) == detail['image_sha256']
            and block['mimeType'] == 'image/png' and detail['local_image_path'] == path.as_posix(),
            'ordinary_current_slot_path_does_not_reopen_exact_transmitted_png')
    if body:
        value = json.loads(body['text'])
        metadata = value['frame'] if 'frame' in value else value['frames'][0]
        require(ref == metadata['ref'] and detail['image_sha256'] == metadata['PNG_sha256'],
                'ordinary_caption_does_not_bind_original_ref_and_hash')
    return ref, detail, raw


def verify_ordinary(window, held, bridge, source, label):
    held.prepare_device(ASSET_SHA256)
    held.device._scene = deepcopy(source)
    slot = held.folder
    owner = bridge.Owner(held, {'label': label, 'group': SLOTS[label][0], 'phase': 'formal',
                               'worker_deadline_ns': held.task_deadline, 'output': str(slot / 'owner')},
                         budget=held.budget)
    endpoint = owner.start(slot / 'ENDPOINT.json')
    audit = slot / 'consumer_audit'
    sequence = [
        ('initialize', None), ('tools/list', None),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code':
            'subset=scene_data(["M09","M03"])\n'
            'v=np.asarray(next(row["vertices"] for row in subset["objects"] if row["name"]=="M09"))\n'
            'centre=v.mean(axis=0).tolist()\n'
            'span=float(np.linalg.norm(np.ptp(v,axis=0))*1.12)\n'
            'probe=shapely.Point(0,0).buffer(1)\n'
            'print(len(subset["objects"]), probe.contains(shapely.Point(0,0)), Fraction(15,64))'}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': 'print(v.shape, probe.is_empty)'}}),
        ('tools/call', {'name': 'render_views', 'arguments': {'names': ['SCENE'], 'include_images': True}}),
    ]

    def call(number, method, params):
        request = {'jsonrpc': '2.0', 'id': number, 'method': method}
        if params is not None:
            request['params'] = params
        return request

    def shell(requests, output):
        process = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
                                  '--endpoint', str(endpoint), '--audit', str(output)],
                                 input=b''.join(bridge.encoded(row)+b'\n' for row in requests),
                                 capture_output=True, timeout=35)
        if process.returncode:
            raise ValueError('ordinary_stdio_failure/' + process.stderr.decode(errors='replace')[-2000:])
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        require([row['id'] for row in replies] == [row['id'] for row in requests], 'ordinary_wire_id_changed')
        return [row['result'] for row in replies]

    # Ask the final three calls in the same process by incorporating the published
    # deterministic geometry-derived local pose and refs only after a host response.
    target = next(row['vertices'] for row in source['objects'] if row['name'] == 'M09')
    centre = [sum(row[axis] for row in target)/len(target) for axis in range(3)]
    span = sum((max(row[axis] for row in target)-min(row[axis] for row in target))**2
               for axis in range(3))**.5*1.12
    sequence.extend([
        ('tools/call', {'name': 'render_local', 'arguments': {'direction': 'LEFT', 'target_world_m': centre,
                       'view_span_m': span, 'include_image': True}}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code':
            'z=render_local("LEFT", centre, span)\n'
            'print(z["ref"])\nread_images([z["ref"]])'}}),
        ('tools/call', {'name': 'render_local', 'arguments': {'direction': 'LEFT', 'target_world_m': centre}}),
        ('tools/call', {'name': 'read_images', 'arguments': {'refs': ['native-image:other-run']}}),
    ])
    requests = [call(index, method, params) for index, (method, params) in enumerate(sequence, 1)]
    try:
        replies = shell(requests, audit)
    finally:
        closed = owner.close()
    require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
            'ordinary_host_close_unconfirmed')
    require(replies[0]['serverInfo']['name'] == 'perf050-readonly-product-transfer'
            and 'instructions' not in replies[0]
            and replies[1]['tools'] == bridge.TOOLS + ([read(PRODUCT_SCHEMA)] if label == 'P1' else [])
            and json.loads(replies[2]['content'][0]['text'])['stdout'].strip() == '2 True 15/64'
            and json.loads(replies[3]['content'][0]['text'])['stdout'].strip() == '(4, 3) False',
            'ordinary_tool_parity_decoder_or_persistent_python_changed')
    _, whole, whole_raw = check_content(replies[4], True)
    ref, local, local_raw = check_content(replies[5], True)
    decoded = json.loads(replies[6]['content'][0]['text'])
    reref, reopened, reopened_raw = check_content({**replies[6], 'content': replies[6]['content'][1:]}, False)
    require(ref == reref == decoded['stdout'].strip() and reopened == local and reopened_raw == local_raw
            and whole_raw != local_raw and replies[7]['isError'] and replies[8]['isError'],
            'ordinary_cached_read_or_negative_arguments_changed')
    # A registered byte-identical image in another directory must stay private.
    registered = held.device.by_ref[ref]
    external = window / (label + '.png')
    external.write_bytes(local_raw)
    with patch.dict(registered, PNG=str(external)):
        try:
            owner.images([ref], {'image_attachments': []})
        except ValueError as error:
            require(str(error) == 'current_slot_original_png_path_required', 'wrong_foreign_png_rejection')
        else:
            raise ValueError('foreign_png_escaped_its_owner')
    with patch.dict(registered, PNG_sha256='0'*64):
        try:
            owner.images([ref], {'image_attachments': []})
        except ValueError as error:
            require(str(error) == 'current_image_bytes_changed', 'wrong_modified_png_rejection')
        else:
            raise ValueError('wrong_png_digest_accepted')
    journal, = audit.iterdir()
    attempts, rx_sizes = [], []
    for index, request in enumerate(requests, 1):
        folder = journal / f'{index:03d}'
        receipt = read(folder / 'RECEIPT.json')
        require(read(folder / 'TX.bin') == request and read(folder / 'RX.bin')['result'] == replies[index-1]
                and receipt['origin'] == 'owner' and receipt['attempt'] == (index - 2 if index > 2 else None)
                and receipt['response_bytes'] == (folder / 'RX.bin').stat().st_size,
                'ordinary_wire_journal_or_attempt_budget_changed')
        if receipt['attempt'] is not None:
            attempts.append(receipt['attempt'])
        rx_sizes.append(receipt['response_bytes'])
    exit_record = read(journal / 'EXIT.json')
    counts = held.budget.snapshot()['slots'][label]
    require(exit_record['normal_exit'] and not exit_record['backend_close_requested']
            and counts['business_admissions'] == len(attempts) and counts['raster_actual'] == 2,
            'ordinary_meter_or_early_exit_contract_changed')
    return {'attempts': attempts, 'rx_bytes': rx_sizes, 'actual_offline_rasters': 2, 'owner_closed': True,
            'ordinary_cached_read_retained_original_png': True, 'foreign_and_wrong_digest_rejected': True,
            'whole_png_sha256': whole['image_sha256'], 'local_png_sha256': local['image_sha256']}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and not EXTERNAL.exists(),
            'new_isolated_transfer_preflight_required')
    require(sha(SOURCE) == SOURCE_DIGEST and read(SOURCE)['source']['asset_sha256'] == ASSET_SHA256,
            'sealed_own_fixture_source_changed')
    asset_identity()
    binding = read(PRODUCT_BINDING)
    shared = SEAL / 'SHARED_DEPENDENCY.json'
    sys.path[:0] = [str(NS), binding['install_root'], binding['dependency_root'], read(shared)['dependency_root']]
    import bridge
    import runtime
    from closure import startup_closure
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == binding['source_sha256'], 'offline_runtime_not_candidate')
    dispatch = {label: entry(HERE / 'run_slot.py', label, '--dispatch-smoke') for label in ORDER}
    mcp = entry(HERE / 'mcp_entry.py', '--dispatch-smoke')
    require(mcp['label'] == 'P1' and Path(mcp['absolute_state_file']) == EXTERNAL / 'slots/P1/product_state.json'
            and all(Path(row['actual_product_schema']) == PRODUCT_SCHEMA and row['group'] == SLOTS[label][0]
                    and row['product'] == admission.registered_product() for label, row in dispatch.items()),
            'current_P_N_entrypoints_not_bound_to_candidate')

    pins = {ASSET, SOURCE, PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, Path(binding['wheel_path']), shared,
            *(HERE.glob('*.py')), *(FORMAL / 'harness').glob('*.py'), FORMAL / 'bridge.py',
            FORMAL / 'frame_device.py', PRIOR / 'harness/mcp_entry.py', PRIOR / 'harness/owned_runtime.py',
            PRIOR / 'thin_stdio.py', NS / 'consumer/driver.py', NS / 'consumer/thin_stdio.py',
            DISPLAY / 'harness/reused/stdio_checks.py', Path(runtime.Runtime._start_public_mcp.__code__.co_filename),
            P3 / 'harness/preflight.py'}
    sealed = load_retained('_perf050_transfer_original_reader', P3 / 'harness/preflight.py')
    with sealed.original_archive(P3, pins) as fetch:
        archived = [sealed.stdio_original(fetch, 'P3', index) for index in range(1, 4)]
    rejected = sealed.reject_original(pins)
    source = read(SOURCE)
    source['source_ref'] = 'sealed-21-object-transfer-preflight'
    source['objects'] = [{**row, **row['evaluated']} for row in source['objects']]
    began = time.perf_counter_ns()
    with TemporaryDirectory(prefix='perf050_transfer_preflight_') as directory:
        window = Path(directory).resolve()
        ordinary = {}
        for label in ORDER:
            slot = window / 'slots' / label
            slot.mkdir(parents=True)
            original = runtime.Runtime.__mro__[2]
            with patch.dict(original.__init__.__globals__, EXTERNAL=window):
                held = runtime.Runtime(slot, label, began+100_000_000_000, began+120_000_000_000)
            if label == 'P1':
                plugin = start_product(held, runtime, window, binding, archived, rejected)
            ordinary[label] = verify_ordinary(window, held, bridge, source, label)
    fields = ('attempts', 'actual_offline_rasters', 'whole_png_sha256', 'local_png_sha256')
    require(all(ordinary['N1'][key] == ordinary['P1'][key] for key in fields), 'ordinary_frame_parity_changed')

    failure = {'status': 'failed', 'model_consumers': 0, 'paid_API_calls': 0}
    early = {'spawn': None, 'failure': None, 'launch_cleanup': None, 'settlement': None,
             'asset_matches': True, 'copy_matches': None}
    receipt = {'status': 'failed', 'owned_budget_passed': True}
    require(admission.can_continue({**failure, 'closure_verification': startup_closure(
                **early, startup_entered=False)}, receipt)
            and not admission.can_continue({**failure, 'closure_verification': startup_closure(**early)}, receipt),
            'early_cleanup_unverified_or_wrongly_admitted')
    require(not EXTERNAL.exists(), 'offline_preflight_touched_actual_transfer_run_root')
    output = HERE / 'HOST_PREFLIGHT.json'
    save(output, {'passed': True, 'Blender_launches': 0, 'model_calls': 0, 'actual_owned_slots': 0,
                  'ledger_limits': LIMITS, 'entrypoints': {**dispatch, 'MCP': mcp}, 'plugin': plugin,
                  'ordinary': ordinary, 'same_archival_geometry': SOURCE_DIGEST,
                  'early_cleanup_checked': True, 'offline_elapsed_ns': time.perf_counter_ns()-began,
                  'source_pins': [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                                  for path in sorted({path.resolve() for path in pins})]})
    print(sha(output), flush=True)


if __name__ == '__main__':
    main()
