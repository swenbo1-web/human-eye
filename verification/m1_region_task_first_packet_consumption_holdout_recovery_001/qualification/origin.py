"""Read-only provenance and lifecycle verification for the sealed QA slot."""

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile


OLD_COMMIT = '0b754de85f21e1ec12cb74a08211ac19cfd4fa0d'
OLD_NAME = 'm1_region_task_first_packet_consumption_holdout_001'
VERIFICATION = Path(__file__).resolve().parents[2]
OLD = VERIFICATION / OLD_NAME
ROOT = Path('D:/he_' + OLD_NAME)
SLOT = ROOT / 'slots' / 'QA'
MEMBER_COUNT = 1000
FREEZE = '2342ecb10d104ee000999b1d0d67e35545cf2516b50a45ac642a7ed6d54b14fc'
INDEX = '625295c4b26bb18033a9ca8c4ad5ffee730fc84fe1e85ba1c14911795159bb7e'
ARCHIVE = 'e4e1ce943c3a0fdbd96100d8fbcb7269b849f62de4146d5743d4d5dfca75c6aa'
RESULT = '60b8226ac165ff5d0086833ed3f7e21571fb4706275b20dec9ab99527bdfda9e'
PUBLICATION = 'f87e0209e646a9087c55ee3c30e2e8a8675ff1c8713dbd1b1dd8b8f3df0a293d'
SEQUENCE = 'dae6ae8500231596ee184c463df28c12c765eba1d923bebdc03cc33300ed9b0e'
ASSET = '219541e921666ddf6c406507afb5e59168415a14b8ea7b3d8eca28c6dacbe12f'
PRODUCT = {
    'commit': '24b8855746dfe9eeee7fa7d374bec2da86c21a2e',
    'source_sha256': '704742071fd1d2722b952e6fa0d4f9a497b8a33ed567ce8f510657d8c1b379fe',
    'wheel_sha256': '2cd2bc3607fd5b8744d760f88ad23008f3faae153efa4ccd49dfa22538547572',
}


def require(condition, message):
    if not condition:
        raise ValueError('old_QA_origin/' + message)


def checked(path, expected):
    data = path.read_bytes()
    require(sha256(data).hexdigest() == expected, 'fixed_digest_changed/' + str(path))
    return data


def read(path):
    return json.loads(path.read_bytes())


def hash_file(path):
    digest = sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def record(path):
    return {'path': path.resolve(strict=True).as_posix(), 'bytes': path.stat().st_size, 'sha256': hash_file(path)}


def verify_archive(index):
    archive_path = OLD / 'ORIGINAL_RUNTIME.zip'
    archive = record(archive_path)
    require(index['archive'] == {
        'name': archive_path.name, 'bytes': archive['bytes'], 'sha256': archive['sha256'],
    } and archive['sha256'] == ARCHIVE and index['freeze_sha256'] == FREEZE, 'archive_identity_changed')
    members = index['members']
    root = ROOT.resolve(strict=True)
    disk = {'runtime/' + path.relative_to(root).as_posix(): path for path in root.rglob('*') if path.is_file()}
    require(index['member_count'] == len(members) == len(disk) == MEMBER_COUNT
            and members.keys() == disk.keys(), 'unsealed_or_missing_runtime_member')
    with ZipFile(archive_path) as bundle:
        infos = bundle.infolist()
        require(len(infos) == len(members) and {info.filename for info in infos} == members.keys(),
                'duplicate_or_missing_ZIP_member')
        for info in infos:
            name = info.filename
            path, expected = disk[name], members[name]
            require(path.resolve(strict=True).is_relative_to(root) and not info.is_dir(),
                    'runtime_member_outside_original_root/' + name)
            raw = bundle.read(info)
            require({'bytes': len(raw), 'sha256': sha256(raw).hexdigest()} == expected
                    and info.file_size == expected['bytes'] and path.read_bytes() == raw,
                    'archived_member_not_equal_to_index_and_disk/' + name)
    return archive


def verify_frozen_inputs(frozen):
    require(frozen['slots'] == ['QA', 'QB', 'A1', 'B1'] and frozen['qualification_slots'] == ['QA', 'QB']
            and frozen['formal_slots'] == ['A1', 'B1'] and frozen['passed_offline_preflight'] is True
            and frozen['product'] == PRODUCT and frozen['asset_sha256'] == ASSET
            and frozen['task_s'] == 450 and frozen['owned_s'] == 600
            and frozen['argument_rewrites'] == frozen['product_builds'] == frozen['product_installs'] == 0,
            'frozen_inputs_or_budgets_changed')
    pins = {}
    for expected in frozen['direct_inputs']:
        source = Path(expected['path']).resolve(strict=True)
        require(source not in pins and source.stat().st_size == expected['bytes']
                and hash_file(source) == expected['sha256'], 'frozen_input_changed/' + str(source))
        pins[source] = expected['sha256']
    asset = ROOT / 'fixture' / 'main.blend'
    require(Path(frozen['asset_path']).resolve() == asset.resolve()
            and pins.get(asset.resolve()) == ASSET and hash_file(SLOT / 'native/input.blend') == ASSET,
            'original_fixture_or_native_copy_changed')
    prompt = OLD / 'inputs/PROMPT.txt'
    require(pins.get(prompt.resolve()) == frozen['prompt_sha256'], 'original_prompt_changed')
    binding_file = VERIFICATION / 'm1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
    binding = read(binding_file)
    require(binding_file.resolve() in pins and binding['preparation_git'] == PRODUCT['commit']
            and binding['source_sha256'] == PRODUCT['source_sha256'] and binding['wheel_sha256'] == PRODUCT['wheel_sha256']
            and len(binding['source_manifest']) == 143
            and hash_file(Path(binding['wheel_path'])) == PRODUCT['wheel_sha256'],
            'original_installed_product_changed')
    identity = read(SLOT / 'MCP_IDENTITY.json')
    require(identity['source_sha256'] == PRODUCT['source_sha256'] and identity['source_file_count'] == 143
            and identity['production_mode'] is True and identity['source_kind'] == 'installed_distribution',
            'original_MCP_invalid_product_identity')
    return record(asset), record(binding_file), len(pins)


def ordered(values, reason):
    require(all(type(value) is int for value in values)
            and all(a <= b for a, b in zip(values, values[1:])), 'clock_order/' + reason)


def wire(path):
    receipt = read(path / 'RECEIPT.json')
    tx, rx = (path / 'TX.bin').read_bytes(), (path / 'RX.bin').read_bytes()
    req, response = json.loads(tx), json.loads(rx)
    require(receipt['error'] is None and req['id'] == response['id'] == receipt['id']
            and receipt['method'] == req['method'] and len(tx) == receipt['TX_bytes']
            and len(rx) == receipt['RX_bytes'] and sha256(rx).hexdigest() == receipt['RX_sha256'],
            'wire_receipt_changed/' + str(path))
    ordered([receipt[name] for name in ('started_ns', 'stdin_flushed_ns', 'received_complete_ns',
                                       'consumer_json_decoded_ns', 'closed_ns')], str(path))
    require(receipt['closed_ns'] - receipt['started_ns'] == receipt['elapsed_ns'], 'wire_elapsed_changed/' + str(path))
    return tx, rx, req, response, receipt


def verify_operations(result, ready, diagnostic_close):
    task_deadline = result['task_deadline_ns']
    business = (
        ('render_local', None, True), ('human_eye_scene_observe', 'full', False), ('read_images', None, False),
        ('human_eye_scene_observe', 'brief', False), ('human_eye_scene_observe', None, False),
    )
    original = result['diagnostic_calls']
    require(len(original) == len(business), 'original_business_call_count_changed')
    inner_by_outer = {2: 1, 4: 2, 5: 3}
    operations = []
    previous = ready
    for i, (logged, (name, detail, is_error)) in enumerate(zip(original, business, strict=True), 1):
        owner = SLOT / 'owner' / f'tool_{i:02}'
        client = SLOT / 'client' / f'call_{i:02}'
        transport = SLOT / 'client/transport' / f'rpc_{i + 3:02}'
        tx, rx, req, response, received = wire(transport)
        forwarded = read(owner / 'RECEIPT.json')
        require((logged['index'], logged['name']) == (i, name)
                and (req['id'], req['params']['name']) == (f'qualification-{i}', name)
                and req['params']['arguments'].get('response_detail') == detail
                and response['result']['isError'] is is_error
                and forwarded['attempt'] == i and forwarded['RPC_id'] == req['id']
                and forwarded['name'] == name and forwarded['is_error'] is is_error
                and forwarded['response_bytes'] == len(rx) and received == read(client / 'RECEIPT.json')
                and tx == (owner / 'REQUEST.json').read_bytes() and rx == (owner / 'RESPONSE.json').read_bytes()
                and req == json.loads(checked(client / 'REQUEST.json', logged['request_sha256']))
                and response == json.loads(checked(client / 'RESPONSE.json', logged['response_sha256'])),
                'original_business_delivery_changed/' + str(i))
        window = [previous, logged['started_ns'], received['started_ns'], forwarded['started_ns']]
        inner = None
        if i in inner_by_outer:
            j = inner_by_outer[i]
            inner_path = SLOT / 'mcp' / f'rpc_{j + 3:02}'
            call = SLOT / 'product_calls' / f'call_{j:03}'
            inner_tx, inner_rx, inner_req, inner_response, inner_receipt = wire(inner_path)
            require(inner_req['id'] == f'observe-{j}'
                    and req['params'] == inner_req['params'] == read(call / 'REQUEST.json')['params']
                    and inner_req == read(call / 'REQUEST.json')
                    and inner_response == read(call / 'RESPONSE.json')
                    and inner_response['result'] == response['result']
                    and inner_receipt == read(call / 'RECEIPT.json'),
                    'installed_product_forwarding_changed/' + str(i))
            window += [inner_receipt['started_ns'], inner_receipt['closed_ns']]
            inner = {'index': j, 'wire_path': inner_path.as_posix(), 'TX_sha256': sha256(inner_tx).hexdigest(),
                     'RX_sha256': sha256(inner_rx).hexdigest(),
                     'started_ns': inner_receipt['started_ns'], 'closed_ns': inner_receipt['closed_ns']}
        window += [forwarded['response_ready_ns'], forwarded['closed_ns'], received['received_complete_ns'],
                   received['closed_ns'], logged['returned_ns'], diagnostic_close, task_deadline]
        ordered(window, f'business_{i}')
        previous = logged['returned_ns']
        operations.append({
            'index': i, 'name': name, 'detail': detail, 'is_error': is_error,
            'started_ns': logged['started_ns'], 'returned_ns': logged['returned_ns'],
            'wire_path': transport.as_posix(), 'TX_sha256': sha256(tx).hexdigest(),
            'RX_sha256': sha256(rx).hexdigest(), 'product': inner,
        })
    return operations


def verify_closure(result, publication):
    started = read(SLOT / 'SLOT_STARTED.json')
    ready = read(SLOT / 'RUNTIME_READY.json')
    closure = read(SLOT / 'RUNTIME_CLOSE.json')
    native_spawn = read(SLOT / 'native/SPAWN.json')
    native_ready = read(SLOT / 'native/READY.json')
    native_worker = read(SLOT / 'native/WORKER_CLOSED.json')
    mcp_spawn = read(SLOT / 'mcp/SPAWN.json')
    mcp_start = read(SLOT / 'mcp/START.json')
    mcp_close = read(SLOT / 'mcp/CLOSE.json')
    held = read(SLOT / 'mcp/HELD_CLOSE.json')
    eof = read(SLOT / 'mcp_io/EOF.json')
    exit_worker = read(SLOT / 'mcp_io/WORKER_EXIT.json')
    client_start = read(SLOT / 'client/transport/START.json')
    client_spawn = read(SLOT / 'client/transport/SPAWN.json')
    client_close = read(SLOT / 'client/transport/CLOSE.json')
    owner_close = read(SLOT / 'owner/CLOSE.json')
    task, owned = result['task_deadline_ns'], result['owned_deadline_ns']
    start = result['started_ns']
    require(start == started['started_ns'] == publication['started_ns']
            and (task - start, owned - start) == (450_000_000_000, 600_000_000_000)
            and started['task_deadline_ns'] == client_start['deadline_ns'] == mcp_start['deadline_ns']
            == client_spawn['original_deadline_ns'] == mcp_spawn['original_deadline_ns'] == task
            and started['owned_deadline_ns'] == native_spawn['original_deadline_ns'] == native_ready['deadline_ns']
            == native_worker['original_deadline_ns'] == owned
            and started['freeze_sha256'] == FREEZE and native_spawn['asset_sha256'] == ready['asset_copy_sha256'] == ASSET
            and '--region-task-evidence' not in mcp_spawn['command'], 'original_lifecycle_binding_changed')
    native, mcp, client = native_spawn['pid'], mcp_spawn['pid'], client_spawn['pid']
    require(len({native, mcp, client}) == 3
            and native == native_ready['pid'] == native_worker['pid'] == ready['native_pid']
            == closure['Blender_close']['pid'] == result['closure_verification']['pid']
            and mcp == mcp_start['pid'] == ready['product_PID'] == mcp_close['pid'] == held['pid']
            == eof['pid'] == exit_worker['pid']
            and client == client_start['pid'] == client_close['pid'], 'original_process_identity_changed')
    for label, pid, spawned in (('NATIVE', native, native_spawn), ('MCP', mcp, mcp_spawn)):
        proof = read(SLOT / f'{label}_RUNTIME_PROOF.json')
        require(proof['confirmed'] is True and proof['error'] is None
                and proof['launcher_pid'] == proof['runtime_pid'] == pid
                and proof['launcher_created_filetime'] == proof['runtime_created_filetime'],
                'original_retained_runtime_handle_drift/' + label)
        ordered([start, spawned['created_after_ns'], spawned['recorded_ns'], proof['observed_ns'],
                 proof['proved_ns'], ready['ready_ns'], task], 'start_' + label)
    for close in (client_close, mcp_close):
        require(close['confirmed'] is True and close['exit_code'] == 0 and close['forced_kill'] is False
                and close['process_handle_closed'] is True and close['reader_stopped'] is True
                and close['pipes_closed'] == {'stdin': True, 'stdout': True, 'stderr': True} and close['errors'] == [],
                'original_stdio_close_not_confirmed')
    require(client_close == result['diagnostic_close'] and owner_close == result['owner_close']
            and owner_close['confirmed'] is True and owner_close['errors'] == owner_close['transport_errors'] == []
            and held == closure['public_MCP_close'] and held['closed_ns'] == mcp_close['closed_ns']
            and held['production_eof_and_exit_verified'] is True and held['stdout_eof_seen'] is True
            and held['unconsumed_response_lines'] == 0 and held['reader_errors'] == []
            and eof['closed'] is eof['input_eof_observed'] is eof['host_close_called'] is True
            and exit_worker['production_returned'] is True and exit_worker['production_return_code'] == 0
            and exit_worker['installed_source_verified'] is True
            and eof['source_sha256'] == exit_worker['source_sha256'] == PRODUCT['source_sha256']
            and closure['Blender_close']['exit_code'] == 0 and closure['Blender_close']['process_reaped'] is True
            and closure['Blender_close']['protected_files_unchanged'] is True
            and native_worker['poisoned'] is False and native_worker['initial_geometry_fingerprint']
            == native_worker['final_geometry_fingerprint'] == native_ready['initial_fingerprint']
            and not closure['errors'] and result['closure_verification']['passed'] is True
            and result['independent_before_after']['passed'] is True,
            'original_runtime_close_or_unchanged_scene_not_confirmed')
    for key, filename in (('worker_eof', 'EOF.json'), ('worker_exit', 'WORKER_EXIT.json')):
        path = SLOT / 'mcp_io' / filename
        require(Path(held[key]['path']).resolve() == path.resolve() and held[key]['sha256'] == hash_file(path),
                'held_close_worker_receipt_changed/' + key)
    for key in ('public_MCP_exit', 'Blender_exit'):
        exit_receipt = closure[key]
        require(exit_receipt['confirmed'] is exit_receipt['exited'] is exit_receipt['handle_closed'] is True
                and exit_receipt['exit_code'] == 0, 'retained_handle_exit_not_confirmed/' + key)
    initialize = wire(SLOT / 'mcp/rpc_01')[4]
    catalogue = wire(SLOT / 'mcp/rpc_03')[4]
    ordered([start, ready['started_ns'], native_spawn['created_after_ns'], mcp_start['started_ns'],
             mcp_spawn['recorded_ns'], mcp_start['ready_ns'], initialize['started_ns'], initialize['closed_ns'],
             catalogue['started_ns'], catalogue['closed_ns'], ready['ready_ns'], result['ready_ns'],
             client_start['started_ns'], client_spawn['recorded_ns'], client_start['ready_ns'], task], 'QA_startup')
    ordered([client_close['started_ns'], client_close['closed_ns'], result['cleanup_started_ns'], owner_close['closed_ns'],
             closure['started_ns'], held['started_ns'], eof['input_eof_ns'], eof['closed_ns'], exit_worker['closed_ns'],
             held['stdout_eof_observed_ns'], mcp_close['closed_ns'], closure['public_MCP_exit']['observed_ns'],
             native_worker['closed_ns'], closure['Blender_exit']['observed_ns'], closure['closed_ns'],
             result['closed_ns'], publication['published_ns'], task, owned], 'QA_shutdown_and_publication')
    require(publication['complete_slot_ns'] == publication['published_ns'] - start, 'old_slot_elapsed_changed')
    return {
        'started_ns': start, 'native_pid': native, 'production_pid': mcp, 'diagnostic_pid': client,
        'native_started_ns': native_spawn['created_after_ns'], 'production_started_ns': mcp_start['started_ns'],
        'production_initialized_ns': initialize['closed_ns'], 'production_catalogue_ns': catalogue['closed_ns'],
        'runtime_ready_ns': ready['ready_ns'], 'slot_ready_ns': result['ready_ns'], 'diagnostic_ready_ns': client_start['ready_ns'],
        'diagnostic_closed_ns': client_close['closed_ns'], 'owner_closed_ns': owner_close['closed_ns'],
        'production_input_eof_ns': eof['input_eof_ns'], 'production_output_eof_ns': held['stdout_eof_observed_ns'],
        'production_exit_observed_ns': closure['public_MCP_exit']['observed_ns'],
        'native_exit_observed_ns': closure['Blender_exit']['observed_ns'], 'slot_closed_ns': result['closed_ns'],
        'published_ns': publication['published_ns'], 'task_deadline_ns': task, 'owned_deadline_ns': owned,
        'original_admission_verified_ns': None,
    }


def verify_origin():
    """Verify sealed and on-disk old QA bytes and return a JSON-compatible origin binding."""
    freeze_file, index_file = OLD / 'FROZEN.json', OLD / 'RAW_INDEX.json'
    frozen, index = json.loads(checked(freeze_file, FREEZE)), json.loads(checked(index_file, INDEX))
    archive = verify_archive(index)
    asset, binding, input_count = verify_frozen_inputs(frozen)
    result_file, publication_file = SLOT / 'SLOT_RESULT.json', SLOT / 'SLOT_PUBLICATION.json'
    journal = ROOT / 'preflight/SEQUENCE.jsonl'
    pairs = ((result_file, 'QA_SLOT_RESULT.json', RESULT), (publication_file, 'QA_SLOT_PUBLICATION.json', PUBLICATION),
             (journal, 'SEQUENCE.jsonl', SEQUENCE))
    for disk, name, digest in pairs:
        require(checked(disk, digest) == checked(OLD / 'evidence' / name, digest), 'original_evidence_copy_changed/' + name)
    result, publication = read(result_file), read(publication_file)
    events = [json.loads(line) for line in journal.read_bytes().splitlines()]
    require([row['event'] for row in events] == ['start', 'publication', 'blocked']
            and all(row['label'] == 'QA' for row in events) and events[0]['freeze_sha256'] == FREEZE
            and events[1]['status'] == result['status'] == publication['status'] == 'completed'
            and events[1]['result_sha256'] == publication['result_sha256'] == RESULT
            and events[1]['exit_code'] == 0 and events[1]['safe_to_continue'] is True
            and events[2]['remaining'] == ['QB', 'A1', 'B1'] and events[2]['type'] == 'ValueError'
            and events[2]['reason'] == 'not enough values to unpack (expected 1, got 0)'
            and publication['owned_budget_passed'] is True and result['freeze_sha256'] == FREEZE
            and result['slot'] == result['label'] == publication['slot'] == publication['label'] == 'QA'
            and result['phase'] == 'qualification' and result['group'] == 'P'
            and result['product_source_sha256'] == PRODUCT['source_sha256']
            and result['product_binding_sha256'] == binding['sha256'] and result['asset_sha256'] == ASSET,
            'old_slot_or_publication_changed')
    pending = read(SLOT / 'QUALIFICATION_PENDING.json')
    require(pending == result['qualification_pending'] and pending['passed'] is False
            and {path.name for path in (ROOT / 'slots').iterdir()} == {'QA'}
            and not (ROOT / 'preflight/QA_CLOSED_GATE.json').exists()
            and not (ROOT / 'preflight/QA_CLOSED_PROOF.json').exists(), 'old_failed_gate_or_unrun_slots_changed')
    counts = result['budget']['counts']
    require(result['actual_model_admitted'] is False and result['model_consumers'] == events[1]['model_consumers']
            == result['paid_API_calls'] == counts['consumer_admissions'] == counts['Blender_spawned_unknown']
            == counts['pending_raster_reservations'] == 0 and counts['Blender_start_attempts']
            == counts['Blender_spawned_confirmed'] == 1 and counts['business_admissions'] == 5
            and counts['all_raster_actual'] == counts['qualification_raster_actual'] == 3,
            'old_slot_budget_changed')
    original_slots = index['slots']
    require(original_slots['QA'] == {'owned': 'completed', 'qualification': 'failed', 'model_consumers': 0,
                                     'rasters': 3, 'complete_slot_ns': publication['complete_slot_ns'],
                                     'result_sha256': RESULT}
            and all(original_slots[name] == {'owned': 'unrun', 'model_consumers': 0, 'rasters': 0}
                    for name in ('QB', 'A1', 'B1')) and len(original_slots) == 4, 'old_sealed_denominators_changed')
    clocks = verify_closure(result, publication)
    ordered([events[0]['stamp_ns'], clocks['started_ns']], 'sequence_slot_registration')
    operations = verify_operations(result, clocks['diagnostic_ready_ns'], clocks['diagnostic_closed_ns'])
    return {
        'schema': 'region-task-holdout-original-QA-origin-v1', 'old_commit': OLD_COMMIT,
        'original_root': ROOT.as_posix(), 'original_slot': SLOT.as_posix(),
        'freeze_sha256': FREEZE, 'archive_sha256': ARCHIVE, 'slot_result_sha256': RESULT,
        'publication_sha256': PUBLICATION, 'index_sha256': INDEX, 'sequence_sha256': SEQUENCE,
        'freeze_path': freeze_file.as_posix(), 'archive_path': archive['path'], 'index_path': index_file.as_posix(),
        'slot_result_path': result_file.as_posix(), 'publication_path': publication_file.as_posix(),
        'sequence_path': journal.as_posix(), 'validated_members': MEMBER_COUNT, 'validated_frozen_inputs': input_count,
        'old_gate_present': False, 'old_gate_passed': False,
        'clocks': clocks, 'operations': operations, 'product': {**PRODUCT, 'binding': binding}, 'asset': asset,
        'original_denominators': {
            'qualification_starts': {'actual': 1, 'planned': 2}, 'qualification_passed': {'actual': 0, 'planned': 2},
            'formal_starts': {'actual': 0, 'planned': 2}, 'model_starts': {'actual': 0, 'planned': 2},
            'QA_business': 5, 'QA_rasters': 3, 'slots': original_slots,
        },
    }


if __name__ == '__main__':
    print(json.dumps(verify_origin(), ensure_ascii=False, indent=2))
