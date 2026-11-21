"""Exercise both startup bindings and the original source-region wire offline."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
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
from common import (ASSET, ASSET_SHA256, BINDINGS, CATALOGUE, DISPLAY, EXTERNAL, FORMAL, GLOBAL, ORDER,
                    PILOT, PILOT_RUN, PILOT_SLOT, PRIOR, PRODUCT_SCHEMA, RECOVERY, REQUEST, SEAL,
                    arguments, asset_identity, load_retained, product, read, save, sha)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def originals(pins):
    catalogue = read(CATALOGUE)
    index = PILOT / 'RUNTIME_INDEX.json'
    frozen = read(index)
    archive = Path(frozen['archive']['path'])
    require(archive.parent == PILOT_RUN and sha(archive) == frozen['archive']['sha256'],
            'sealed_natural_pilot_archive_changed')
    members = {row['path']: row for row in frozen['files']}
    pins.update((index, archive))
    with ZipFile(archive) as sealed:
        def raw(path):
            path = path.resolve()
            name = path.relative_to(PILOT_RUN.resolve()).as_posix()
            value = path.read_bytes()
            pin = members[name]
            require(len(value) == pin['bytes'] and sha(path) == pin['sha256'] and value == sealed.read(name),
                    'sealed_natural_pilot_member_changed/' + name)
            pins.add(path)
            return value

        exchange = []
        for index in (1, 2, 3, 5):
            folder = PILOT_SLOT / 'mcp' / f'rpc_{index:02d}'
            tx_bytes = raw(folder / 'TX.bin')
            query = json.loads(tx_bytes)
            receipt = json.loads(raw(folder / 'RECEIPT.json'))
            reply = None
            require((receipt['index'], receipt['method'], receipt['id'], receipt['TX_bytes'], receipt['error']) ==
                    (index, query['method'], query.get('id'), len(tx_bytes), None), 'original_stdio_TX_mismatch')
            if 'id' in query:
                path = folder / 'RX.bin'
                rx_bytes = raw(path)
                reply = json.loads(rx_bytes)
                require(reply['id'] == query['id'] and reply == json.loads(raw(folder / 'RESPONSE.json'))
                        and (len(rx_bytes), sha(path)) == (receipt['RX_bytes'], receipt['RX_sha256']),
                        'original_stdio_RX_mismatch')
            exchange.append((query, reply))
        require(exchange[2][1]['result']['tools'] == catalogue
                and exchange[3][0] == json.loads(raw(REQUEST))
                and exchange[3][1] == json.loads(raw(PILOT_SLOT / 'owner/tool_03/PRODUCT_RESPONSE.json')),
                'original_pilot_product_tool_exchange_changed')
        archive_path = PILOT_SLOT / 'product_full/call_002/SERVICE_RESULT.json'
        producer = json.loads(raw(archive_path))
        product_calls = PILOT_SLOT / 'product_calls/call_002'
        entries = list(map(json.loads, raw(product_calls / 'ARCHIVE_AFTER.bin').splitlines()))
        require(json.loads(raw(product_calls / 'REQUEST.json')) == exchange[3][0]
                and json.loads(raw(product_calls / 'RESPONSE.json')) == exchange[3][1]
                and Path(entries[-1]['path']) == archive_path and entries[-1]['sha256'] == sha(archive_path),
                'original_pilot_service_source_region_archive_changed')
        frame, = producer['frames']
        require(frame['view_name'] == 'SCENE' and producer['work']['raster_attempts'] == 1,
                'original_source_region_default_scope_changed')
        payloads = {key: raw(Path(frame[key])) for key in ('image_path', 'arrays_path')}
        close = json.loads(raw(PILOT_SLOT / 'RUNTIME_CLOSE.json'))
        slot = json.loads(raw(PILOT_SLOT / 'SLOT_RESULT.json'))
        published = json.loads(raw(PILOT_SLOT / 'SLOT_PUBLICATION.json'))
        require(published['status'] == slot['status'] == 'completed'
                and published['result_sha256'] == sha(PILOT_SLOT / 'SLOT_RESULT.json')
                and slot['asset_sha256'] == ASSET_SHA256 and slot['closure_verification']['passed']
                and close['public_MCP_exit']['confirmed'] and close['Blender_exit']['confirmed'],
                'original_pilot_process_or_asset_closure_changed')
    return exchange, producer, payloads


def probe_installed(label, work, requests):
    """Run only initialize/list on the exact installed Python writer in a temp root."""
    work.mkdir()
    binding_path = BINDINGS[label]
    binding = read(binding_path)
    config = work / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': str(work / 'state.json'),
        'audit_file': str(work / 'audit.jsonl'), 'expected_identity': {'source_sha256': binding['source_sha256']},
        'request_budget_s': 30, 'blender': {'host': '127.0.0.1', 'port': 1, 'timeout_s': 1}})
    recorder = PRIOR / 'harness/mcp_entry.py'
    invoke = ('import runpy, sys; from pathlib import Path; '
              'entry=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,' + repr(str(HERE)) +
              '); import budget; runpy.run_path(entry, run_name="__main__")')
    command = [sys.executable, '-I', '-B', '-X', 'utf8', '-c', invoke, str(recorder),
        '--binding', str(binding_path), '--config', str(config), '--ledger', str(work / 'budget'),
        '--evidence', str(work / 'mcp_io'), '--archive', str(work / 'archive'),
        '--phase', 'qualification', '--label', label]
    transport = load_retained('_m4_active_view_probe_transport', DISPLAY / 'harness/reused/stdio_checks.py')
    client = transport.StdioClient(command, work, work / 'mcp', time.perf_counter_ns() + 35_000_000_000)
    try:
        exchange = [(request, client.call(request)) for request in requests]
    finally:
        closed = client.finish()
    proof = read(work / 'mcp_io/RUNTIME.json')
    require(closed['confirmed'] and closed['exit_code'] == 0
            and proof['source_sha256'] == binding['source_sha256'] and proof['algorithm_monkeypatches'] == 0
            and exchange[0][1]['result']['_meta']['human_eye']['source_sha256'] == binding['source_sha256']
            and exchange[2][1]['result']['tools'] == read(CATALOGUE)
            and not (work / 'audit.jsonl').exists() and not list((work / 'archive').iterdir()),
            'real_installed_handshake_or_no_business_probe_failed')
    return exchange, {'source_sha256': proof['source_sha256'], 'closed': True,
        'requests': [{'TX_sha256': sha(work / 'mcp' / f'rpc_{i:02d}/TX.bin'),
                      'RX_sha256': sha(work / 'mcp' / f'rpc_{i:02d}/RX.bin') if reply is not None else None}
                     for i, (_, reply) in enumerate(exchange, 1)]}


def configure_replay(instance, runtime, folder, label, handshake, *, original_tool=None, producer=None, payloads=None):
    startup = runtime.Runtime._start_public_mcp
    seen, checked_paths = [], []
    binding_path = BINDINGS[label]
    binding = read(binding_path)
    expected = {'--binding': binding_path, '--config': folder / 'PRODUCT_CONFIG.json',
                '--ledger': instance.budget.root, '--evidence': folder / 'mcp_io',
                '--archive': folder / 'product_full', '--phase': 'qualification', '--label': label}
    if producer is not None:
        producer = deepcopy(producer)
        copy = folder / 'offline_frame_bytes'
        copy.mkdir()
        for key, data in payloads.items():
            target = copy / Path(producer['frames'][0][key]).name
            target.write_bytes(data)
            producer['frames'][0][key] = str(target)

    class MemoryClient:
        def __init__(self, argv, actual_folder, archive, deadline):
            require(actual_folder == folder and archive == folder / 'mcp' and deadline == instance.task_deadline
                    and Path(argv[5]).resolve() == HERE / 'mcp_entry.py' and
                    dict(zip(argv[6::2], argv[7::2], strict=True)) == {k: str(v) for k, v in expected.items()},
                    'active_view_runtime_bypassed_registered_argv')
            self.process = object()
            self.records = []

        def call(self, request):
            index = len(seen)
            seen.append(request['method'])
            if index < len(handshake):
                expected_request, response = handshake[index]
                require(request == expected_request, 'active_view_startup_changed_original_request')
                return deepcopy(response)
            require(original_tool is not None and request['method'] == 'tools/call'
                    and request['params'] == original_tool[0]['params'],
                    'active_view_product_did_not_receive_the_original_source_region_parameters')
            response = {**deepcopy(original_tool[1]), 'id': request['id']}
            start = time.perf_counter_ns()
            sequence = len(self.records) + 1
            result = folder / 'product_full' / f'call_{sequence:03d}/SERVICE_RESULT.json'
            result.parent.mkdir(parents=True)
            save(result, producer)
            with (folder / 'product_full/INDEX.jsonl').open('ab') as stream:
                stream.write(json.dumps({'index': sequence, 'path': str(result), 'sha256': sha(result),
                    'started_ns': start, 'producer_returned_ns': time.perf_counter_ns()}).encode() + b'\n')
            self.records.append({'id': request['id'], 'method': request['method']})
            return response

    def loader(name, path):
        require(name == '_live_stdio_client' and path == DISPLAY / 'harness/reused/stdio_checks.py',
                'startup_loaded_another_transport')
        return SimpleNamespace(StdioClient=MemoryClient)

    def read_pinned(path):
        checked_paths.append(Path(path).resolve())
        return read(path)

    scope = dict(startup.__globals__, load=loader, read=read_pinned, SOURCE_SHA=binding['source_sha256'])
    with patch.object(instance, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
            instance, '_retain', return_value=object()) as held:
        FunctionType(startup.__code__, scope)(instance, binding_path, binding)
        held.assert_called_once_with(instance.client.process, 'MCP_RUNTIME_PROOF.json')
    require(seen == ['initialize', 'notifications/initialized', 'tools/list']
            and checked_paths == [PRODUCT_SCHEMA.resolve(), CATALOGUE.resolve()]
            and read(folder / 'PRODUCT_CONFIG.json')['expected_identity']['source_sha256'] == binding['source_sha256'],
            'actual_retained_startup_did_not_enforce_canonical_schema_and_identity')
    return seen


def original_loopback(window, runtime, batch, exchange, producer, payloads):
    root = window / 'runtime'
    slot = root / 'slots/A'
    slot.mkdir(parents=True)
    began = time.perf_counter_ns()
    original_runtime_base = runtime.Runtime.__mro__[-2]
    binding = read(BINDINGS['A'])
    with patch.dict(original_runtime_base.__init__.__globals__, EXTERNAL=root):
        held = runtime.Runtime(slot, 'A', began + 60_000_000_000, began + 75_000_000_000, [])
    held.prepare_device(ASSET_SHA256)
    seen = configure_replay(held, runtime, slot, 'A', exchange[:3], original_tool=exchange[3],
                           producer=producer, payloads=payloads)
    owner = batch.owner_for(held, 'A', slot, held.task_deadline)
    endpoint = read(Path(owner.start(slot / 'ENDPOINT.json')))
    try:
        result = batch.execute(owner, 'A', slot, endpoint, held.task_deadline)
        require(result['outer_business_count'] == result['inner_public_count'] == 2
                and [row['kind'] for row in result['calls']] == ['cold', 'hot']
                and held.budget.snapshot()['slots']['A']['business_admissions'] == 2
                and seen[3:] == ['tools/call', 'tools/call'], 'actual_direct_loopback_fake_slot_changed')
    finally:
        closed = owner.close()
    require(closed['confirmed'] and closed['errors'] == closed['transport_errors'] == [],
            'actual_direct_loopback_owner_close_unconfirmed')
    return {'original_tool_and_PNG_replayed': True, 'cold_hot_same_request': True, 'one_image_each': True,
            'owner_confirmed_closed': True, 'offline_replay_has_no_live_raster_or_capture_claims': True,
            'original_body_bytes': len(exchange[3][1]['result']['content'][0]['text'].encode('utf8'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-only', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode and not EXTERNAL.exists(), 'fresh_isolated_host_preflight_required')
    labels = ('A',) if args.baseline_only else ORDER
    base = read(BINDINGS['A'])
    shared_path = SEAL / 'SHARED_DEPENDENCY.json'
    sys.path[1:1] = [str(FORMAL), base['dependency_root'], read(shared_path)['dependency_root']]
    import batch
    import runtime

    pins = {ASSET, REQUEST, PRODUCT_SCHEMA, CATALOGUE, shared_path,
            Path(runtime.Runtime._start_public_mcp.__code__.co_filename),
            *(HERE.glob('*.py')), *(PILOT / 'harness').glob('*.py'),
            *(FORMAL / 'harness').glob('*.py'), *(GLOBAL / 'harness').glob('*.py'),
            FORMAL / 'frame_device.py', FORMAL / 'bridge.py', RECOVERY / 'harness/runtime.py',
            PRIOR / 'bridge.py', PRIOR / 'harness/mcp_entry.py', PRIOR / 'harness/owned_runtime.py',
            PRIOR / 'harness/reused/verified_bootstrap.py', PRIOR / 'harness/budget.py',
            SEAL / 'harness/qual_driver.py', SEAL / 'harness/owned_runtime.py',
            DISPLAY / 'harness/reused/stdio_checks.py', DISPLAY / 'harness/reused/process_proof.py'}
    asset_identity()
    original, producer, payloads = originals(pins)
    entries = {}
    for label in labels:
        path = BINDINGS[label]
        current = read(path)
        pins.update((path, Path(current['wheel_path'])))
        entries[label] = {}
        for kind, argv in (('slot', [label, '--dispatch-smoke']), ('mcp', ['--dispatch-smoke', label])):
            script = 'run_slot.py' if kind == 'slot' else 'mcp_entry.py'
            entry = json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(HERE / script), *argv],
                                                       timeout=30))
            require(entry['fresh_process_prepared_only'] and entry['label'] == label
                    and entry['current_product'] == product(label)
                    and Path(entry['current_binding']).resolve() == path.resolve(),
                    'fresh_slot_or_child_smoke_uses_another_arm')
            if kind == 'slot':
                require(all(row['params']['arguments'] == arguments() for row in entry['wrapper']),
                        'fresh_slot_wrong_original_source_region_request')
            entries[label][kind] = entry

    evidence = {}
    with TemporaryDirectory(prefix='m4-active-view-host-preflight-') as name:
        window = Path(name).resolve()
        loopback = original_loopback(window, runtime, batch, original, producer, payloads)
        if not args.baseline_only:
            for label in ORDER:
                live_handshake, proof = probe_installed(label, window / f'stdio_{label}', [row[0] for row in original[:3]])
                stub = window / f'startup_{label}'
                stub.mkdir()
                instance = SimpleNamespace(folder=stub, native=None, label=label, phase='qualification',
                    budget=SimpleNamespace(root=stub / 'budget'), task_deadline=time.perf_counter_ns() + 60_000_000_000,
                    _retain=lambda *args: None)
                seen = configure_replay(instance, runtime, stub, label, live_handshake)
                evidence[label] = {'same_startup_function_used_frozen_schema': True, 'handshake_methods': seen,
                                   'real_ephemeral_installed_stdio': proof}

    require(not EXTERNAL.exists(), 'offline_preflight_touched_real_runtime')
    if args.baseline_only:
        print(json.dumps({'passed': True, 'baseline_entrypoints': entries, 'real_direct_loopback': loopback}))
        return 0
    output = HERE / 'HOST_PREFLIGHT.json'
    save(output, {'passed': True, 'new_Blender_launches': 0, 'new_rasterizations': 0, 'new_model_runs': 0,
        'new_installed_business_calls': 0, 'new_owned_slots': 0, 'source_asset_sha256': ASSET_SHA256,
        'original_request_path': str(REQUEST.resolve()), 'original_request_sha256': sha(REQUEST), 'limits': LIMITS,
        'fresh_entrypoints': entries, 'real_archived_source_region_loopback': loopback, 'live_installed_startup': evidence,
        'source_pins': [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                        for path in sorted({p.resolve() for p in pins})]})
    print('Host preflight passed', sha(output), len(pins), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
