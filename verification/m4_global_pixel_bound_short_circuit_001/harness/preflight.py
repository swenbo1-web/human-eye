"""Replay the archived dense request, actual images, and six inert host routes."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from admission import can_continue, registered_products
from budget import Budget, LIMITS
from common import (ARMS, BINDINGS, BLOCKER, CATALOGUE, DENSE, EXTERNAL, FORMAL, NS, ORDER, PRIOR, REQUEST, V,
                    asset_identity, load, read, save, sha)
from run_slot import prepare_runner


DENSE_FORMAL = V / 'm4_dense_panel_sweep_formal_001'
BRIEF = V / 'm4_dense_region_brief_001/checks/brief_schema.py'
TYPED = FORMAL / 'checks/typed_diagnostic.py'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def reject(call, reason):
    try:
        call()
    except (RuntimeError, ValueError) as error:
        require(str(error) == reason, 'unexpected_preflight_rejection/' + str(error))
    else:
        raise ValueError('preflight_expected_rejection/' + reason)


class Original:
    def __init__(self, namespace, index_sha, bundle_sha, pins):
        index_path = namespace / 'RUNTIME_INDEX.json'
        require(sha(index_path) == index_sha, 'retained_runtime_index_changed')
        index = read(index_path)
        self.bundle = Path(index['archive']['path'])
        require(sha(self.bundle) == bundle_sha == index['archive']['sha256'] and
                self.bundle.stat().st_size == index['archive']['bytes'], 'retained_runtime_archive_changed')
        self.root = self.bundle.parent
        self.files = {row['path']: row for row in index['files']}
        self.pins = pins
        for path in (index_path, self.bundle):
            pins[path.resolve()] = {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}

    def bytes(self, path):
        path = Path(path).resolve()
        relative = path.relative_to(self.root).as_posix()
        row = self.files[relative]
        data = path.read_bytes()
        with ZipFile(self.bundle) as archive:
            require(archive.read(relative) == data and row['bytes'] == len(data) and
                    row['sha256'] == sha256(data).hexdigest(), 'historical_original_changed/' + relative)
        self.pins[path] = {**row, 'path': str(path)}
        return data

    def json(self, path):
        return json.loads(self.bytes(path))


def check_packet(tx, rx, client, request, reply):
    require(json.loads(tx) == request and json.loads(rx) == reply and
            request['jsonrpc'] == reply['jsonrpc'] == '2.0' and request['id'] == reply['id'] == client['id'] and
            request['method'] == client['method'] == 'tools/call', 'original_wire_RPC_or_semantics_mismatch')
    require(len(tx) == client['TX_bytes'] and len(rx) == client['RX_bytes'] and
            sha256(rx).hexdigest() == client['RX_sha256'] and client['error'] is None,
            'original_wire_size_or_rx_sha_mismatch')
    require(client['started_ns'] <= client['stdin_flushed_ns'] <= client['received_complete_ns'] <=
            client['consumer_json_decoded_ns'] <= client['closed_ns'], 'original_wire_client_clock_mismatch')
    digest = sha256(tx).hexdigest()
    if 'TX_sha256' in client:
        require(digest == client['TX_sha256'], 'original_wire_tx_sha_mismatch')
    return {'TX_bytes': len(tx), 'TX_sha256': digest, 'TX_sha256_derived': 'TX_sha256' not in client,
            'RX_bytes': len(rx), 'RX_sha256': client['RX_sha256']}


def product(original):
    folder = original.root / 'slots/QP'
    _, result, published = (original.json(folder / name) for name in
                            ('SLOT_STARTED.json', 'SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
    require(result['status'] == published['status'] == 'completed' and
            published['result_sha256'] == sha(folder / 'SLOT_RESULT.json'), 'old_dense_slot_not_published')
    require(can_continue(result, published), 'old_dense_slot_not_cleanly_closed')
    dirty = deepcopy(result)
    dirty['closure_verification']['passed'] = False
    require(not can_continue(dirty, published), 'unknown_closure_must_stop')
    event, = [json.loads(line) for line in original.bytes(folder / 'PUBLIC_REQUESTS.jsonl').splitlines()]
    meter, = [item for item in map(json.loads, original.bytes(folder / 'mcp_io/MCP_IO.jsonl').splitlines())
              if item['method'] == 'tools/call']
    call = folder / 'product_calls/call_001'
    RPC = folder / 'mcp' / f"rpc_{event['receipt']['index']:02d}"
    req, resp = (original.json(call / name) for name in ('REQUEST.json', 'RESPONSE.json'))
    tx, rx = (original.bytes(RPC / name) for name in ('TX.bin', 'RX.bin'))
    client = original.json(RPC / 'RECEIPT.json')
    require(client == event['receipt'] and req == event['request'] and resp == event['response'] and
            req['params'] == {'name': 'human_eye_scene_observe', 'arguments': read(REQUEST)},
            'old_dense_product_template_mismatch')
    wire = check_packet(tx, rx, client, req, resp)
    require(wire['TX_sha256_derived'] and meter['id'] == meter['response_id'] == req['id'] and
            meter['TX_bytes'] == len(tx) and meter['TX_sha256'] == wire['TX_sha256'] and
            meter['raster_actual'] == 2 and
            sha256(rx.replace(b'\r\n', b'\n')).hexdigest() == meter['RX_text_UTF8_LF_sha256'] and
            client['started_ns'] <= meter['request_received_ns'] <= meter['reply_completed_ns'] <= client['closed_ns'],
            'wrong_dense_server_receipt_binding')
    reject(lambda: check_packet(tx, rx + b' ', client, req, resp), 'original_wire_size_or_rx_sha_mismatch')
    reject(lambda: check_packet(tx.replace(b'observe-1', b'observe-2'), rx, client, req, resp),
           'original_wire_RPC_or_semantics_mismatch')
    reject(lambda: check_packet(tx, rx, dict(client, TX_sha256='0' * 64), req, resp),
           'original_wire_tx_sha_mismatch')
    packet = original.json(Path(event['producer_archive']['path']))
    require(sha(Path(event['producer_archive']['path'])) == event['producer_archive']['sha256'] and
            len(packet['constructed_frames']) == len(packet['frames']) == 2, 'old_dense_producer_binding_mismatch')
    schema = runpy.run_path(str(BRIEF))
    legacy, images = schema['verify_brief'](resp['result'])
    require(len(legacy['region_task']['rows']) == 13 and
            [frame['view_name'] for frame in packet['frames']] == ['SCENE', 'LEFT'], 'dense_product_frame_or_region_count_changed')
    rows = []
    for frame, (image, png) in zip(packet['frames'], images, strict=True):
        raw_png = original.bytes(Path(frame['image_path']))
        arrays = original.bytes(Path(frame['arrays_path']))
        require(raw_png == png and image['ref'] == frame['image_ref'] and
                sha256(arrays).hexdigest() == frame['arrays_sha256'], 'prior_dense_real_png_or_npz_mismatch')
        rows.append({'view': frame['view_name'], 'PNG_sha256': sha256(raw_png).hexdigest(),
                     'NPZ_sha256': sha256(arrays).hexdigest()})
    return req, resp, {'wire': wire, 'bound_reported_frames': rows, 'CLI': schema['cli_stages'](resp['result'])}


def ordinary(original):
    folder = original.root / 'slots/QN'
    slot = original.json(folder / 'SLOT_RESULT.json')
    record = slot['diagnostic_calls'][0]
    owner, call = folder / 'owner/tool_01', folder / 'client/call_01'
    index = record['transport_index']
    wire_path = folder / f'client/transport/rpc_{index:02d}'
    bridge, = (folder / 'client/attachments').glob(f'bridge_*/{index:03d}')
    req, resp = (original.json(call / name) for name in ('REQUEST.json', 'RESPONSE.json'))
    require(req['params']['name'] == 'execute_python' and slot['status'] == 'completed', 'ordinary_dense_source_changed')
    tx, rx = (original.bytes(wire_path / name) for name in ('TX.bin', 'RX.bin'))
    client = original.json(wire_path / 'RECEIPT.json')
    require(tx == original.bytes(bridge / 'TX.bin') == original.bytes(owner / 'REQUEST.json') and
            rx == original.bytes(bridge / 'RX.bin') == original.bytes(owner / 'RESPONSE.json') and
            original.json(call / 'RECEIPT.json') == client, 'actual_native_delivery_layers_mismatch')
    wire = check_packet(tx, rx, client, req, resp)
    owned = original.json(owner / 'RECEIPT.json')
    relay = original.json(bridge / 'RECEIPT.json')
    require(relay['origin'] == 'owner' and req['id'] == relay['RPC_id'] == owned['RPC_id'] and
            relay['request_bytes'] == client['TX_bytes'] and
            relay['response_bytes'] == owned['response_bytes'] == client['RX_bytes'],
            'ordinary_original_attachment_receipt_changed')
    _, _, images = runpy.run_path(str(TYPED))['verify_content'](resp, contract='ordinary', fact_index=0)
    attachments = owned['image_attachments']
    require(len(images) == len(attachments) == record['images'] == 2, 'ordinary_actual_mixed_native_response_missing')
    rows = []
    for (block, png), certificate in zip(images, attachments, strict=True):
        require(block['ref'] == certificate['ref'] and certificate['delivery_ready'] and
                block['PNG_sha256'] == certificate['PNG_sha256'] == sha256(png).hexdigest(),
                'ordinary_original_png_caption_or_reference_changed')
        rows.append({'ref': block['ref'], 'PNG_sha256': block['PNG_sha256'], 'bytes': len(png)})
    return {'wire': wire, 'original_captioned_PNGs': rows}


def replay_mcp_start(label, folder, binding_path, binding, handshake):
    """Call the same retained startup method with a wire-replaying inert subprocess."""
    runtime = load('_pixel_bound_preflight_runtime', FORMAL / 'harness/runtime.py')
    start = runtime.Runtime._start_public_mcp
    expected = deepcopy(handshake)
    expected[0]['result']['_meta']['human_eye']['source_sha256'] = binding['source_sha256']
    commands = []
    rpc = []

    class InertProcess:
        process = object()

        def __init__(self, argv, cwd, trace, deadline):
            require(cwd == folder and trace == folder / 'mcp' and deadline == 11,
                    'retained_mcp_launch_ownership_changed')
            commands.extend(argv)

        def call(self, request):
            rpc.append(request['method'])
            return expected[len(rpc) - 1]

    fake = SimpleNamespace(folder=folder, label=label, phase='formal', task_deadline=11,
        native=SimpleNamespace(host='127.0.0.1', port=12000), budget=SimpleNamespace(root=folder / 'budget'),
        _retain=lambda *_: None)
    with patch.dict(start.__globals__, {'load': lambda *_: SimpleNamespace(StdioClient=InertProcess),
                                       'NS': BLOCKER}):
        start(fake, binding_path, binding)
    require(rpc == ['initialize', 'notifications/initialized', 'tools/list'] and
            fake.product_tools == read(CATALOGUE), 'retained_mcp_handshake_changed')
    require(commands[:6] == [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py')],
            'retained_installed_mcp_entry_command_changed')
    for flag, value in (('--binding', str(binding_path)), ('--label', label), ('--phase', 'formal'),
                        ('--config', str(folder / 'PRODUCT_CONFIG.json')), ('--evidence', str(folder / 'mcp_io')),
                        ('--archive', str(folder / 'product_full')), ('--ledger', str(folder / 'budget'))):
        require(commands.count(flag) == 1 and commands[commands.index(flag) + 1] == value,
                'retained_mcp_dispatch_argument_changed/' + flag)
    require(read(folder / 'PRODUCT_CONFIG.json')['expected_identity'] == {'source_sha256': binding['source_sha256']},
            'retained_mcp_identity_must_follow_its_arm')
    return True


def dispatch(label, folder, actual_request, actual_reply, handshake):
    run = prepare_runner(label)
    arm = ARMS[label]
    binding_path = BINDINGS[arm]
    binding = read(binding_path)
    fake_root = folder / 'dispatch'
    ledger = Budget(fake_root / 'budget')
    opened = []

    class InertRuntime:
        _start_public_mcp = SimpleNamespace(__globals__={})

        def __init__(self, slot, selected, task, owned):
            require(slot == fake_root / 'slots' / label and selected == label and
                    owned - task == 150_000_000_000, 'actual_route_path_label_or_timeout_changed')
            self.budget = ledger
            self.device = self
            self.native = SimpleNamespace()
            self.client = fake_mcp

        def start(self):
            self.product_tools = read(CATALOGUE)

        def capture_initial(self):
            return {'capture': 'before'}

        def public_request(self, arguments):
            opened.append(arguments)
            require(arguments == actual_request['params']['arguments'], 'actual_dispatch_request_changed')
            return actual_reply

        def export_terminal(self):
            return {'capture': 'after'}

        def close(self, status):
            return {'outcome': status}

    fake_mcp = object()
    scope = {'EXTERNAL': fake_root, 'admit': lambda selected: ('offline-freeze', binding),
             'load': lambda name, _: (SimpleNamespace(Runtime=InertRuntime) if 'runtime' in name else
                 SimpleNamespace(ready_closure=lambda closed, group, proof, require_mcp: {
                     'pid': 1, 'status': 'ready_closed', 'passed': group == 'P', 'mcp_closure_required': require_mcp})),
             'match_source': lambda slot, before, after, asset_sha, pid: {
                 'passed': before == {'capture': 'before'} and after == {'capture': 'after'}, 'same_owned_scene': True}}
    with patch.dict(run.__globals__, scope):
        require(run(label) == 0 and opened == [actual_request['params']['arguments']], 'original_slot_launch_or_call_changed')
    startup = replay_mcp_start(label, folder, binding_path, binding, handshake)
    result = read(fake_root / 'slots' / label / 'SLOT_RESULT.json')
    require(result['arm'] == arm and result['group'] == 'P' and result['phase'] == 'formal' and
            result['product_git'] == binding['preparation_git'] and result['product_source_sha256'] == binding['source_sha256'] and
            result['product_binding_sha256'] == sha(binding_path) and len(result['business_calls']) == 1,
            'registered_single_cold_business_slot_changed')
    probe = Budget(folder / 'limit_checks')
    probe.reserve('business_tool', label, 'formal')
    reject(lambda: probe.reserve('business_tool', label, 'formal'), 'business_tool_budget_exhausted')
    reject(lambda: probe.reserve('consumer_task', label, 'formal'), 'model_consumer_budget_exhausted')
    for _ in range(2):
        probe.reserve('raster_attempt', label, 'formal')
    reject(lambda: probe.reserve('raster_attempt', label, 'formal'), 'raster_budget_exhausted')
    return {'slot': label, 'arm': arm, 'phase': 'formal', 'registered_business_calls': 1,
            'raster_limit': 2, 'binding_sha256': sha(binding_path), 'MCP_launch_receipts_replayed': startup, 'passed': True}


def fresh_entrypoints():
    def invoke(file, *args):
        result = subprocess.run([sys.executable, '-I', '-B', str(HERE / file), *args],
            capture_output=True, check=True, timeout=20)
        return json.loads(result.stdout)

    if (EXTERNAL / 'slots').exists():
        raise ValueError('fresh_dispatch_smoke_requires_no_real_slot')
    routes = []
    for label in ORDER:
        result = invoke('run_slot.py', label, '--dispatch-smoke')
        binding = BINDINGS[ARMS[label]]
        require(result == {'slot': label, 'arm': ARMS[label],
            'admission': str((HERE / 'admission.py').resolve()), 'binding': str(binding.resolve()),
            'product_source_sha256': read(binding)['source_sha256'], 'fresh_process_prepared_only': True},
            'fresh_retained_runner_dispatch_changed/' + label)
        routes.append(result)
    server = invoke('mcp_entry.py', '--dispatch-smoke')
    require(server == {'budget': str((HERE / 'budget.py').resolve()),
        'entry': str((PRIOR / 'harness/mcp_entry.py').resolve()), 'fresh_process_prepared_only': True} and
        not (EXTERNAL / 'slots').exists(), 'fresh_MCP_startup_import_or_guard_changed')
    return {'runners': routes, 'MCP_entry': server, 'actual_Blender_processes': 0}


def main():
    fresh = fresh_entrypoints()
    pins = {}
    originals = [Original(ns, index, bundle, pins) for ns, index, bundle in (
        (BLOCKER, 'c4558bea03d6b2dbb01a19057209b8a5efe66f76f5b5c3e519ebc7e6f372fdac',
         '18c91c9903cba5f0c7b40e180e7f6a3b503b221eb80c0512ac1c8c12026423b4'),
        (DENSE_FORMAL, '77aa19ccde90e13c790de13370755f4a6bce76075651e6d91dd583b03ceb463b',
         '31c389c0815507a2a71c01073e99f9f445758e0d4f3afb2409bd3672fecd0dbf'),
    )]
    products = registered_products()
    for path in BINDINGS.values():
        sys.path.insert(0, read(path)['dependency_root'])
        require(read(path.with_name('TOOLS_SCHEMA.json')) == read(CATALOGUE), 'candidate_tools_changed')
    req, resp, dense = product(originals[0])
    native = ordinary(originals[1])
    frozen_mcp = originals[0].root / 'slots/QP/mcp'
    handshake = [originals[0].json(frozen_mcp / 'rpc_01/RESPONSE.json'), None,
                 originals[0].json(frozen_mcp / 'rpc_03/RESPONSE.json')]
    with TemporaryDirectory(prefix='m4_global_pixel_bound_preflight_') as path:
        routes = [dispatch(label, Path(path) / label, req, resp, handshake) for label in ORDER]
    save(HERE / 'DISPATCH_PREFLIGHT_RECOVERY.json', {'passed': all(row['passed'] for row in routes), 'slots': routes,
        'fresh_isolated_entrypoints': fresh,
        'retained_product': dense, 'retained_common_ordinary_attach': native,
        'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
        'products': products, 'ledger_limits': LIMITS, 'source_pins': list(pins.values())})
    print('Replayed six inert routes and two real sealed transmissions; no Blender, raster or model launched.', flush=True)


if __name__ == '__main__':
    main()
