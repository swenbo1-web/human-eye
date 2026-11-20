"""Verify actual image transport separately from the offline Codex content replay."""

import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import socket
import sys
import time


NS = Path(__file__).resolve().parents[1]
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_cross_scale_live_qualification_001')
OLD_HARNESS = ROOT / 'verification/m4_source_region_display_001/harness'
BRIDGE = NS / 'harness/bridge.py'
THIN = NS / 'harness/thin_stdio.py'
PRODUCT = ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
PRODUCT_SHA = 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0'
SOURCE_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
SCHEMA = NS / 'inputs/PRODUCT_SCHEMA.json'
OLD_RESPONSE = Path('D:/he_m4_cross_scale_001/sessions/pair1_R1/product_calls/call_001/RESPONSE.json')
OLD_RESPONSE_SHA = '2c052a17c4696096d40417c32866850dbd0698bd0cd12a3ab94ef99cff44369a'
PRIOR = ROOT / 'verification/m1_source_region_facts_first_001/checks'
REPLAY_PINS = {'client_budget_replay.py': '8a59abf2ccdaba3013c7ef3e8180265a3311ca3d5039f8af86b679252be08f4a',
               'CLIENT_BUDGET_REVIEW.json': '0e90ad3df1f74a1977d96b212bd7592e11cdbc4e285a80213a25745fedc57ae8'}
TOOL = 'human_eye_scene_observe'
ARGUMENTS = {'query': {'mode': 'active_observation', 'region_task': {
    'area_min_m2': .0078125, 'area_max_m2': .03125, 'normal_z_min': .75}}, 'include_image': True}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_identity(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': digest(raw)}


def read(path):
    return json.loads(Path(path).read_bytes())


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(compact(value) + b'\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def tables(value, name):
    columns, rows = value[name]['columns'], value[name]['rows']
    require(len(columns) == len(set(columns)) and all(len(row) == len(columns) for row in rows),
            'invalid_public_table/' + name)
    return [dict(zip(columns, row, strict=True)) for row in rows]


def handshake(client):
    initialize = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'cross-scale-diagnostic-client', 'version': '1'}}})
    client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    listing = client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'})
    matches = [entry for entry in listing['result']['tools'] if entry['name'] == TOOL]
    require(len(matches) == 1, 'wrong_tool_registration')
    return initialize['result'], matches[0]


def product_binding():
    require(digest(PRODUCT.read_bytes()) == PRODUCT_SHA, 'product_binding_changed')
    binding = read(PRODUCT)
    require(binding['source_sha256'] == SOURCE_SHA and len(binding['source_manifest']) == 143,
            'product_source_identity_changed')
    return binding


def schema(output):
    binding = product_binding()
    output.mkdir(parents=True, exist_ok=False)
    begin = time.perf_counter_ns()
    name = Path(sys.executable)
    transport = load('_cross_schema_stdio', OLD_HARNESS / 'reused/stdio_checks.py')
    client = None
    with socket.socket() as unavailable_host:
        unavailable_host.bind(('127.0.0.1', 0))
        conf = output / 'PRODUCT_CONFIG.json'
        save(conf, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                    'project_root': binding['install_root'], 'state_file': str(output / 'state.json'),
                    'audit_file': str(output / 'audit.jsonl'), 'expected_identity': {'source_sha256': SOURCE_SHA},
                    'request_budget_s': 10, 'blender': {'host': '127.0.0.1',
                        'port': unavailable_host.getsockname()[1], 'timeout_s': 1}})
        try:
            args = [str(name), '-I', '-B', '-X', 'utf8', str(OLD_HARNESS / 'mcp_entry.py'),
                    '--binding', str(PRODUCT), '--config', str(conf), '--ledger', str(output / 'budget'),
                    '--evidence', str(output / 'mcp_io'), '--phase', 'qualification', '--label', 'main',
                    '--archive', str(output / 'product_full')]
            client = transport.StdioClient(args, output, output / 'stdio', begin + 30_000_000_000)
            initial, tool = handshake(client)
            identity = initial['_meta']['human_eye']
            require(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == SOURCE_SHA,
                    'wrong_runtime_identity')
            require(not list((output / 'product_full').glob('call_*')), 'schema_probe_must_not_observe')
        finally:
            if client is not None:
                close = client.finish()
    require(close['confirmed'], 'schema_stdio_close_failed')
    SCHEMA.parent.mkdir(exist_ok=True)
    with SCHEMA.open('xb') as stream:
        stream.write(compact(tool))

    sys.path.insert(0, binding['dependency_root'])
    loader = load('_cross_qual_schema_loader', OLD_HARNESS / 'reused/verified_bootstrap.py')
    guard = loader.bootstrap(binding)
    from human_eye_plugin.live_spatial_mcp import _validate_arguments
    _validate_arguments(TOOL, ARGUMENTS)
    control_errors = {}
    for field in ('scope_id', 'frame_identity', 'image_ref', 'region_ref', 'objects'):
        candidate = copy.deepcopy(ARGUMENTS)
        candidate['query'][field] = [{'name': 'Obj_02'}] if field == 'objects' else 'opaque-previous-observation-ref'
        try:
            _validate_arguments(TOOL, candidate)
        except ValueError as error:
            control_errors[field] = str(error)
        else:
            raise AssertionError('unexpected region_task continuation selector accepted/' + field)
    guard.verify_loaded()
    save(output / 'SCHEMA_RECEIPT.json', {'passed': True, 'duration_ns': time.perf_counter_ns() - begin,
          'identity': identity, 'tool_schema': file_identity(SCHEMA), 'arguments': ARGUMENTS,
          'runtime_binding': file_identity(PRODUCT), 'stdio': close,
          'region_task_local_continuation': {'selective_scope_frame_roi_reference_available': False,
               'actual_installed_argument_rejections': control_errors,
               'separate_source_region_contract': 'Own emitted region_ref or explicit object/triangle selection, reference object and surface_proximity. Active region_task does not emit that continuation token.'},
          'raster_attempts': 0, 'Blender_started': 0, 'model_started': 0})


def budget_helpers():
    for name, expected in REPLAY_PINS.items():
        require(digest((PRIOR / name).read_bytes()) == expected, 'modified_prior_CLI_policy/' + name)
    return runpy.run_path(str(PRIOR / 'client_budget_replay.py')), read(PRIOR / 'CLIENT_BUDGET_REVIEW.json')['policy']


def decode_image(block):
    from PIL import Image
    require(block.get('mimeType') == 'image/png' and not block.get('_meta'), 'native_image_content_contract')
    raw = base64.b64decode(block['data'], validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        require(image.format == 'PNG' and image.size == (512, 512), 'expected_actual_512_PNG')
        image.load()
    return raw


def inspect_content(result):
    started = time.perf_counter_ns()
    require(result.get('isError') is False and not result.get('_meta')
            and 'structuredContent' not in result and 'structured_content' not in result,
            'MCP_envelope_must_use_plain_content_items')
    blocks = result['content']
    require([item['type'] for item in blocks] == ['text', 'image', 'image', 'image']
            and not blocks[0].get('_meta'), 'MCP_must_deliver_one_plaintext_followed_by_three_images')
    text = blocks[0]['text']
    value = json.loads(text)
    require(value['schema'] == 'active-observation-region-task-brief-v1' and value['read_only'] is True
            and value['execution_authority'] is False and value['binding']['capture_scope'] == 'complete_scene_meshes',
            'default_brief_read_only_whole_scene_contract')
    scopes, images = tables(value, 'scopes'), tables(value, 'images')
    witnesses = tables(value, 'witness_pixels')
    rows = value['region_task']['rows']
    by_name = {row['object_name']: row for row in rows}
    require(len(rows) == len(by_name) == 3 and set(by_name) == {'Obj_02', 'Obj_06', 'Obj_09'}, 'exact_eligible_region_roster')
    require(by_name['Obj_06']['status'] == 'unknown' and by_name['Obj_06']['complete_witness'] is None
            and by_name['Obj_06']['reason'] == 'positive_area_occlusion_all_front_views', 'covered_unknown_required')
    require(value['region_task']['conditions'] == ARGUMENTS['query']['region_task'], 'fixed_conditions_changed')
    ids = {row['scope_id']: row for row in scopes}
    require(len(ids) == len(scopes) == len(images) == 3 and 'global' in ids, 'scope_names_distinct')
    require(all(len({row[key] for row in images}) == 3 for key in (
        'scope_id', 'camera_identity', 'frame_identity', 'image_ref', 'native_content_block_index')),
        'full_scope_and_frame_identity_distinguishes_same_view_name')
    decoded, summaries = [], []
    for index, row in enumerate(images, 1):
        require(row['native_content_block_index'] == index and row['view_name'] == 'SCENE'
                and ids[row['scope_id']]['camera_identity'] == row['camera_identity'], 'actual_MCP_image_index_scope')
        raw = decode_image(blocks[index])
        require(row['image_sha256'] == digest(raw), 'declared_image_SHA_does_not_match_MCP_bytes')
        decoded.append(raw)
        summaries.append({**row, 'size_px': [512, 512], 'PNG_bytes': len(raw), 'base64_UTF8_bytes': len(blocks[index]['data'])})
    require(len(witnesses) == 2 and len({row['roi_id'] for row in witnesses}) == 2, 'two_local_pixel_rows_required')
    witness_images = set()
    for name in ('Obj_02', 'Obj_09'):
        row = by_name[name]
        local = row['complete_witness']
        require(row['status'] == 'covered' and local['selected_for_delivery'] is True
                and local['scope_id'] != 'global', 'expected_actual_local_witness/' + name)
        image = images[local['native_content_block_index'] - 1]
        require(all(local[key] == image[key] for key in (
            'view_name', 'frame_identity', 'scope_id', 'image_ref', 'native_content_block_index')), 'witness_to_native_index/' + name)
        pixel = next(x for x in witnesses if x['roi_id'] == row['roi_id'])
        require(all(pixel[key] == image[key] for key in ('frame_identity', 'scope_id')) and
                pixel['visible_surface_pixels'] >= 16 and pixel['contrasting_boundary_pixels'] >= 4, 'bound_witness_pixel_gates/' + name)
        witness_images.add(local['native_content_block_index'])
    require(len(witness_images) == 2, 'separate_local_witness_image_for_each_open_region')

    helpers, policy = budget_helpers()
    stages = []
    # At most three digits before the decimal for the fixed 600 s window.
    for sample in ('0.0000', '10.0000', '100.0000'):
        original = helpers['model_items'](result, sample)
        after_mcp = helpers['truncate_items'](original, policy['MCP_bytes'])
        after_history = helpers['truncate_items'](after_mcp, policy['history_approximate_tokens'], token_mode=True)
        image_items = [item for item in after_history if item['type'] == 'input_image']
        require(len(image_items) == len(decoded) and all(item['detail'] == 'high' and item['image_url'].startswith('data:image/png;base64,')
                and base64.b64decode(item['image_url'].split(',', 1)[1], validate=True) == raw
                for item, raw in zip(image_items, decoded, strict=True)), 'CLI_reconstruction_changed_image_bytes_or_index')
        stages.append({'header_UTF8_bytes': len(original[0]['text'].encode()),
                       'MCP_all_items_unchanged': after_mcp == original, 'history_all_items_unchanged': after_history == original,
                       'object_refs_indexed_after_separate_header': [i + 2 for i in range(len(decoded))],
                       'MCP_items_sha256': digest(compact(after_mcp)), 'history_items_sha256': digest(compact(after_history)),
                       'model_or_supplier_seen': False})
    return {'text_UTF8_bytes': len(text.encode()), 'text_sha256': digest(text.encode()), 'PNG_total_bytes': sum(map(len, decoded)),
            'images': summaries, 'regions': [{k: item[k] for k in ('object_name', 'status', 'reason', 'source_triangle_indices',
                        'complete_witness')} for item in rows], 'image_delivery': value['image_delivery'],
            'capture_binding': value['binding'], 'witness_pixels': witnesses, 'CLI_offline_replay': stages,
            'offline_item_decode_and_check_ns': time.perf_counter_ns() - started,
            'all_cli_text_and_images_survive': all(r['MCP_all_items_unchanged'] and r['history_all_items_unchanged'] for r in stages)}


def wire_calls(folder):
    calls = {}
    for path in sorted(folder.glob('*/TX.bin')):
        request = read(path)
        if request.get('method') != 'tools/call':
            continue
        key = request['id']
        require(key not in calls, 'duplicated_tool_wire_request_id')
        calls[key] = (request, path, path.with_name('RX.bin'), read(path.with_name('RECEIPT.json')))
    return calls


def call_message(identity):
    return {'jsonrpc': '2.0', 'method': 'tools/call', 'id': identity,
            'params': {'name': TOOL, 'arguments': copy.deepcopy(ARGUMENTS)}}


def preflight(output, schema_path):
    require(read(schema_path)['passed'] is True and read(schema_path)['tool_schema'] == file_identity(SCHEMA),
            'actual_registered_schema_preflight_required')
    require(digest(OLD_RESPONSE.read_bytes()) == OLD_RESPONSE_SHA, 'historical_three_scope_payload_changed')
    started = time.perf_counter_ns()
    output.mkdir(parents=True, exist_ok=False)
    # Use the real bridge binary path. The backend is a controlled saved-result fixture.
    sys.path.insert(0, product_binding()['dependency_root'])
    sys.path.insert(0, str(BRIDGE.parent))
    bridge = load('_cross_formal_bridge_preflight', BRIDGE)
    require(bridge.ARGUMENTS == ARGUMENTS, 'registered_formal_arguments_changed')
    transport = load('_cross_qualification_stdio', OLD_HARNESS / 'reused/stdio_checks.py')
    archived = read(OLD_RESPONSE)
    reviewed = []

    class SavedRuntime:
        product_tools = [read(SCHEMA)]

        def __init__(self):
            self.public_requests = []

        def public_request(self, arguments):
            require(arguments == ARGUMENTS, 'bridge_changed_fixed_arguments')
            index = len(self.public_requests) + 1
            identity = 'mock-installed-' + str(index)
            request = call_message(identity)
            response = {**archived, 'id': identity}
            self.public_requests.append({'index': index, 'request': request, 'response': response,
                                         'scope': 'archived response only, no producer work'})
            return response

    runner = SavedRuntime()
    deadline = time.perf_counter_ns() + 30_000_000_000
    owner = bridge.Owner(runner, config={'label': 'Q1', 'phase': 'qualification',
                        'worker_deadline_ns': deadline, 'output': str(output / 'owner')})
    client = None
    try:
        endpoint = owner.start(output / 'ENDPOINT.json')
        args = [sys.executable, '-I', '-B', '-X', 'utf8', str(THIN), '--endpoint', str(endpoint),
                '--audit', str(output / 'attachments')]
        client = transport.StdioClient(args, output, output / 'stdio', deadline)
        _, tool = handshake(client)
        require(tool == read(SCHEMA), 'owner_did_not_expose_identical_installed_tool_schema')
        for label in ('archived-first', 'archived-repeat'):
            request = call_message(label)
            response = client.call(request)
            require(response['result'] == archived['result'], 'three_image_result_changed_by_owner')
            inspected = inspect_content(response['result'])
            require(inspected['all_cli_text_and_images_survive'], 'historical_three_scope_payload_CLI_truncation')
            reviewed.append(inspected)
    finally:
        if client is not None:
            close = client.finish()
        owner_close = owner.close()
    require(close['confirmed'] and owner_close['confirmed'], 'offline_transport_close_not_confirmed')
    paths = list((output / 'attachments').glob('bridge_*'))
    require(len(paths) == 1 and runner.public_requests[0]['request']['params']
            == runner.public_requests[1]['request']['params'], 'fixed_repeat_registration_changed')
    calls = wire_calls(paths[0])
    require(set(calls) == {'archived-first', 'archived-repeat'}, 'preflight_attachment_receipts_incomplete')
    for label, call in calls.items():
        _, tx, rx, receipt = call
        require(read(rx)['result'] == archived['result'] and receipt['origin'] == 'owner'
                and (tx.stat().st_size, rx.stat().st_size) == (receipt['request_bytes'], receipt['response_bytes']),
                'preflight_stdio_tool_archive_not_exact/' + label)
    # Qualify that a shared view name alone cannot conceal a cross-scope association error.
    malformed = copy.deepcopy(archived['result'])
    text = json.loads(malformed['content'][0]['text'])
    text['images']['rows'][1][0] = text['images']['rows'][2][0]
    malformed['content'][0]['text'] = compact(text).decode()
    try:
        inspect_content(malformed)
    except ValueError as error:
        require('full_scope_and_frame_identity' in str(error), 'unexpected_negative_control_failure')
        control = str(error)
    else:
        raise AssertionError('cross_scope_image_alias_not_rejected')
    save(output / 'PREFLIGHT.json', {'passed': True, 'elapsed_ns': time.perf_counter_ns() - started,
         'binding': file_identity(PRODUCT), 'actual_tool_schema': file_identity(SCHEMA),
         'installed_startup_receipt': file_identity(schema_path), 'historical_payload': file_identity(OLD_RESPONSE),
         'transport_scope': 'Current Owner and original thin MCP bridge using historical response as backend fixture.',
         'CLI_scope': 'Offline verification of prior pinned Codex 0.152.1 source reconstruction.',
         'reviewed': reviewed, 'cross_scope_image_alias_control': control, 'thin_stdio_closed': close,
         'owner_closed': owner_close, 'execution_sources': [file_identity(p) for p in (Path(__file__), BRIDGE,
             THIN, OLD_HARNESS / 'reused/stdio_checks.py', *(PRIOR / name for name in REPLAY_PINS))],
         'no_Blender_model_paid_API_or_raster': True})


def verify(slot, output):
    sys.path.insert(0, product_binding()['dependency_root'])
    started = time.perf_counter_ns()
    paths = list((slot / 'client/attachments').glob('bridge_*'))
    require(len(paths) == 1, 'one_actual_thin_bridge_required')
    thin = sorted(wire_calls(paths[0]).values(), key=lambda call: call[3]['attempt'])
    installed = wire_calls(slot / 'mcp')
    stream = {row.get('id'): row for row in [json.loads(line) for line in
              (slot / 'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()] if row.get('method') == 'tools/call'}
    require(0 < len(thin) <= 2, 'business_request_budget')
    delivered = []
    for request, tx, rx, receipt in thin:
        index = receipt['attempt']
        owner = slot / 'owner' / f'tool_{index:02d}'
        owner_request, owner_response = owner / 'REQUEST.json', owner / 'RESPONSE.json'
        original = read(rx)
        require(receipt['origin'] == 'owner' and read(owner_request) == request
                and read(owner_response) == original and request['params'] == call_message(request['id'])['params'],
                'owner_and_consumer_stdio_wire_not_exact')
        product_req = owner / 'PRODUCT_REQUEST.json'
        product_res = owner / 'PRODUCT_RESPONSE.json'
        if not product_req.exists() or 'error' in original or original['result'].get('isError'):
            delivered.append({'attempt': index, 'transport_failure': True, 'stdio_TX': file_identity(tx),
                              'stdio_RX': file_identity(rx), 'owner_RX': file_identity(owner_response)})
            continue
        product_request = read(product_req)
        product_id = product_request['id']
        ir, itx, irx, ireceipt = installed[product_id]
        require(ir == product_request and ir['params'] == request['params'], 'installed_and_bridge_parameters_changed')
        product_response = read(irx)
        require(product_response == read(product_res) and product_response['result'] == original['result'],
                'installed_MCP_public_result_changed_in_bridge')
        inspected = inspect_content(original['result'])
        delivered.append({'attempt': index, 'public': inspected, 'transport_failure': False,
                          'installed_wire': {'TX': file_identity(itx), 'RX': file_identity(irx), 'receipt': ireceipt},
                          'actual_consumer_tool_transport': {'TX': file_identity(tx), 'RX': file_identity(rx), 'receipt': receipt,
                                                      'owner_RX': file_identity(owner_response)},
                          'actual_raster_attempts': stream[product_id]['raster_actual']})
    reuse = None
    if len(delivered) == 2 and all(not row['transport_failure'] for row in delivered):
        first, second = delivered
        reuse = {'same_scoped_frames_and_PNG_bytes': first['public']['images'] == second['public']['images'],
                 'same_capture_generation_and_binding': first['public']['capture_binding'] == second['public']['capture_binding'],
                 'repeat_new_raster_attempts': second['actual_raster_attempts'],
                 'repeat_product_frame_reuses': second['public']['image_delivery']['frame_reuses'],
                 'repeat_is_identical_full_region_task': True, 'targeted_continuation_executed': False}
    passed = all(not row['transport_failure'] and row['public']['all_cli_text_and_images_survive'] for row in delivered)
    passed = bool(passed and delivered[0]['actual_raster_attempts'] == 3 and reuse and
                 reuse['same_scoped_frames_and_PNG_bytes'] and reuse['same_capture_generation_and_binding'] and
                 reuse['repeat_new_raster_attempts'] == 0 and reuse['repeat_product_frame_reuses'] == 3)
    result = {'passed': passed, 'elapsed_ns': time.perf_counter_ns() - started, 'calls': delivered, 'repeat': reuse,
              'transport_scope': 'Actual installed MCP RPCs and thin diagnostic-client content. CLI item delivery is offline.',
              'actual_model_or_supplier_input_tested': False}
    save(output, result)
    print(json.dumps({'passed': passed, 'calls': len(delivered), 'repeat': reuse}))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('schema', 'preflight', 'verify'):
        handle = actions.add_parser(action)
        handle.add_argument('output', type=Path)
        if action == 'preflight':
            handle.add_argument('schema_receipt', type=Path)
        elif action == 'verify':
            handle.add_argument('slot', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_fixed_isolated_interpreter')
    if args.action == 'schema':
        schema(args.output)
    elif args.action == 'preflight':
        preflight(args.output, args.schema_receipt)
    else:
        raise SystemExit(verify(args.slot, args.output))
