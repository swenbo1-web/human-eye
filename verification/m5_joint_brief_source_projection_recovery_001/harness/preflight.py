"""Replay the failed run's real handshake through the corrected startup without launching it."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import FunctionType, SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admission
from budget import LIMITS
from common import (ASSET, CATALOGUE, EXTERNAL, GLOBAL, NS, PRODUCT_BINDING, PRODUCT_SCHEMA, PROJECTION,
                    REQUESTS, load_retained, read, save, sha)
from runtime import Runtime, STARTUP_SOURCE


FAILED_RUN = Path('D:/he_m5_joint_brief_source_projection_001')
FAILED_ARCHIVE_SHA = '9f1896c69c26741b11e97436cdf04ee2a59d741a3d25f06dca5ca88a591cc694'
prior = load_retained('_m5_projection_recovery_preflight_source', PROJECTION / 'harness/preflight.py')
prior.HERE = HERE
require, rejected = prior.require, prior.rejected


def original_handshake(pins):
    wire = prior.load_wire()
    index = PROJECTION / 'RUNTIME_INDEX.json'
    archive = FAILED_RUN / 'ORIGINAL_RUNTIME.zip'
    bound, _ = wire.frozen_archive(index, FAILED_RUN, FAILED_ARCHIVE_SHA)
    pins.update((index, archive))
    source = FAILED_RUN / 'slots/B'
    result_path = source / 'SLOT_RESULT.json'
    publication_path = source / 'SLOT_PUBLICATION.json'
    result, published = map(lambda p: json.loads(bound(p)), (result_path, publication_path))
    pins.update((result_path, publication_path))
    require(result['status'] == published['status'] == 'failed' and sha(result_path) == published['result_sha256']
            and Path(result['asset_path']).resolve() == ASSET.resolve() and not result['business_calls']
            and result['errors'][0]['type'] == 'FileNotFoundError'
            and 'PRODUCT_SCHEMA.json' in result['errors'][0]['message'], 'unexpected_original_failed_slot')
    exchange = []
    for i in (1, 2, 3):
        folder = source / 'mcp' / f'rpc_{i:02d}'
        tx, receipt = folder / 'TX.bin', folder / 'RECEIPT.json'
        tx_bytes = bound(tx)
        req, measured = json.loads(tx_bytes), json.loads(bound(receipt))
        pins.update((tx, receipt))
        require(measured['index'] == i and measured['error'] is None and measured['method'] == req['method']
                and measured['id'] == req.get('id') and measured['TX_bytes'] == len(tx_bytes),
                'original_handshake_request_or_index_mismatch')
        response = None
        if 'id' in req:
            rx, body = folder / 'RX.bin', folder / 'RESPONSE.json'
            raw = bound(rx)
            response = json.loads(raw)
            pins.update((rx, body))
            require(len(raw) == measured['RX_bytes'] and sha256(raw).hexdigest() == measured['RX_sha256']
                    and json.loads(bound(body)) == response and response['id'] == req['id'],
                    'original_handshake_response_mismatch')
        exchange.append((req, response))
    return exchange


def replay_startup(tmp, exchange):
    binding = read(PRODUCT_BINDING)
    startup = Runtime._start_public_mcp
    require(startup.__globals__['PRODUCT_SCHEMA'] == PRODUCT_SCHEMA and startup.__globals__['CATALOGUE'] == CATALOGUE,
            'live_startup_not_using_frozen_canonical_paths')
    expected_catalogue = read(CATALOGUE)
    identity = exchange[0][1]['result']['_meta']['human_eye']
    checks = []
    collected = {}

    def run(name, messages, *, schema=PRODUCT_SCHEMA):
        folder = tmp / name
        folder.mkdir()
        seen, paths = [], []
        process = object()
        handle = object()
        deadline = 123456
        class MemoryClient:
            def __init__(self, argv, actual_folder, rpc, task_deadline):
                require(actual_folder == folder and rpc == folder / 'mcp' and task_deadline == deadline,
                        'actual_retained_client_scope_wrong')
                expected = {'--binding': PRODUCT_BINDING, '--config': folder / 'PRODUCT_CONFIG.json',
                            '--ledger': folder / 'budget', '--evidence': folder / 'mcp_io',
                            '--archive': folder / 'product_full', '--phase': 'qualification', '--label': 'B'}
                require(Path(argv[5]).resolve() == (HERE / 'mcp_entry.py').resolve()
                        and dict(zip(argv[6::2], argv[7::2], strict=True)) == {
                            flag: str(value) for flag, value in expected.items()}, 'actual_retained_client_argv_wrong')
                self.process = process

            def call(self, request):
                old, returned = messages[len(seen)]
                require(request == old, 'actual_startup_request_differs_from_original_TX')
                seen.append(request['method'])
                return deepcopy(returned)

        def loader(name, path):
            require(name == '_live_stdio_client' and path.name == 'stdio_checks.py',
                    'actual_startup_called_unexpected_loader')
            return SimpleNamespace(StdioClient=MemoryClient)

        def retained(child, output):
            require(child is process and output == 'MCP_RUNTIME_PROOF.json', 'actual_startup_child_proof_wrong')
            return handle

        def watched_read(path):
            paths.append(Path(path))
            return read(path)

        stub = SimpleNamespace(folder=folder, label='B', phase='qualification', task_deadline=deadline,
            native=SimpleNamespace(host='127.0.0.1', port=1), budget=SimpleNamespace(root=folder / 'budget'),
            _retain=retained)
        globals_ = dict(startup.__globals__, load=loader, read=watched_read, PRODUCT_SCHEMA=schema)
        FunctionType(startup.__code__, globals_)(stub, PRODUCT_BINDING, binding)
        require(stub.mcp_handle is handle and paths == [PRODUCT_SCHEMA, CATALOGUE]
                and seen == ['initialize', 'notifications/initialized', 'tools/list']
                and stub.product_tools == expected_catalogue and read(folder / 'MCP_IDENTITY.json') == identity
                and read(folder / 'PRODUCT_CONFIG.json')['expected_identity']['source_sha256'] == binding['source_sha256'],
                'actual_retained_startup_acceptance_incomplete')
        collected['handshake_methods'] = seen

    run('exact', exchange)
    missing = PROJECTION / 'inputs/PRODUCT_SCHEMA.json'
    require(not missing.exists(), 'original_missing_schema_path_unexpectedly_exists')
    try:
        run('wrong-path', exchange, schema=missing)
    except FileNotFoundError as error:
        require(Path(error.filename).resolve() == missing.resolve(), 'original_wrong_path_not_reproduced')
        checks.append('reject_original_missing_schema_path')
    else:
        raise ValueError('actual_retained_startup_accepted_missing_schema')
    altered_schema = tmp / 'wrong_schema.json'
    save(altered_schema, {**read(PRODUCT_SCHEMA), 'description': 'wrong pinned schema'})
    rejected(lambda: run('wrong-schema', exchange, schema=altered_schema), 'actual_Human_Eye_schema_changed')
    checks.append('reject_wrong_pinned_schema')
    bad_directory = deepcopy(exchange)
    bad_directory[2][1]['result']['tools'] = [
        row for row in expected_catalogue if row['name'] == 'human_eye_scene_observe']
    rejected(lambda: run('wrong-directory', bad_directory), 'actual_public_catalogue_changed')
    checks.append('reject_wrong_tool_catalogue')
    bad_identity = deepcopy(exchange)
    bad_identity[0][1]['result']['_meta']['human_eye']['source_sha256'] = '0' * 64
    rejected(lambda: run('wrong-identity', bad_identity), 'public_product_identity_changed')
    checks.append('reject_wrong_source_identity')
    return {**collected, 'retained_startup_source': str(STARTUP_SOURCE.resolve()),
            'schema_path': str(PRODUCT_SCHEMA.resolve()), 'schema_sha256': sha(PRODUCT_SCHEMA),
            'catalogue_path': str(CATALOGUE.resolve()), 'catalogue_sha256': sha(CATALOGUE),
            'source_sha256': identity['source_sha256'], 'negative_controls': checks}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode
            and not any((EXTERNAL / relative).exists() for relative in ('slots', 'budget', 'preflight')),
            'fresh_isolated_preflight_required')
    pins = {PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, ASSET, STARTUP_SOURCE, NS / 'run_sequence.py',
            GLOBAL / 'run_sequence.py', GLOBAL / 'FROZEN.json', PROJECTION / 'FROZEN.json',
            *REQUESTS.values(), *HERE.glob('*.py'), *(GLOBAL / 'harness').glob('*.py'),
            *(PROJECTION / 'harness').glob('*.py')}
    entries = prior.verify_entrypoints()
    prior.verify_product_schema(pins)
    archived_handshake = original_handshake(pins)
    protocol, _ = prior.prior.check_archives(pins)
    public, original_outer, source = prior.verify_archive(pins)
    with TemporaryDirectory(prefix='m5-projection-recovery-preflight-') as directory:
        tmp = Path(directory)
        startup = replay_startup(tmp, archived_handshake)
        outer = prior.prior.verify_outer(tmp, {('recovered', 5): public})
        require(read(tmp / 'B/batch/rpc_03/RECEIPT.json')['response'] == original_outer,
                'archived_B_loopback_did_not_preserve_actual_response')
        budget = prior.verify_budget(tmp)
    require(not any((EXTERNAL / relative).exists() for relative in ('slots', 'budget', 'preflight')),
            'preflight_changed_live_run_root')
    output = HERE / 'DISPATCH_PREFLIGHT.json'
    save(output, {'passed': True, 'limits': LIMITS, 'actual_Blender_processes': 0, 'actual_raster_attempts': 0,
         'actual_model_runs': 0, 'actual_public_requests': 0, 'fresh_entrypoints': entries,
         'actual_startup_handshake_replay': startup, 'source_and_wire_current_asset_replay': source,
         'outer_archived_loopback': outer, 'old_rejection_followed_by_success': protocol,
         'ledger_rejection_control': budget,
         'source_pins': [{'path': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size}
                         for p in sorted({p.resolve() for p in pins}, key=str)]})
    print('Recovered dispatch preflight passed', sha(output), len(pins))


if __name__ == '__main__':
    main()
