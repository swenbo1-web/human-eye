"""Verify the one prompt change and replay the sealed historical P1 originals."""

import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import zipfile


NS = Path(__file__).resolve().parents[1]
VERIFICATION = NS.parent
FORMAL = VERIFICATION / 'm4_cross_scale_live_task_formal_001'
RUNTIME = Path('D:/he_m4_cross_scale_live_task_formal_001').resolve()
SLOT = RUNTIME / 'slots/P1'
OLD_COMMIT = '9f743878d3a868575c5be43f00a9ba4e011b5161'
SCRIPT_ROOT = VERIFICATION / 'm1_source_region_facts_first_001/checks'
TOOL = 'human_eye_scene_observe'
ADDED_FIELD = b',"response_detail":"brief"'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Evidence:
    def __init__(self):
        self.pins = {}
        index = self.read(FORMAL / 'RUNTIME_INDEX.json',
                          'aa0e6e76930b58e4928683e6318428b72cedf30a3af1008cb12595b1bfba27d3')
        self.index = {row['path']: row for row in index['files']}
        require(len(self.index) == index['count'], 'ambiguous_historical_runtime_index')
        self.zip_path = RUNTIME / 'ORIGINAL_RUNTIME.zip'
        raw = self.raw(self.zip_path, index['archive']['sha256'])
        require(len(raw) == index['archive']['bytes'], 'historical_runtime_archive_size_changed')
        self.frozen = self.read(FORMAL / 'FROZEN.json',
                                '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c')
        self.previous_inputs = {Path(row['path']).resolve(): row for row in self.frozen['direct_inputs']}

    def raw(self, path, expected=None):
        path = path.resolve()
        data = path.read_bytes()
        pin = {'path': str(path), 'sha256': sha(data), 'bytes': len(data)}
        require(expected is None or pin['sha256'] == expected, 'historical_SHA_changed/' + str(path))
        require(self.pins.get(path, pin) == pin, 'input_changed_during_replay/' + str(path))
        self.pins[path] = pin
        return data

    def read(self, path, expected=None):
        return json.loads(self.raw(path, expected))

    def previous(self, path):
        pin = self.previous_inputs[path.resolve()]
        data = self.raw(path, pin['sha256'])
        require(len(data) == pin['bytes'], 'prior_frozen_input_length_changed/' + str(path))
        return data

    def archived(self, archive, path):
        relative = path.resolve().relative_to(RUNTIME).as_posix()
        pin = self.index[relative]
        raw = self.raw(path, pin['sha256'])
        require(len(raw) == pin['bytes'] and raw == archive.read(relative),
                'historical_file_and_runtime_archive_differ/' + relative)
        return raw


def checked_prompt(evidence):
    original = evidence.previous(FORMAL / 'inputs/PROMPT_P.txt')
    prompt = evidence.raw(NS / 'inputs/PROMPT_P.txt')
    common = evidence.previous(FORMAL / 'inputs/PROMPT_COMMON.txt')
    opener = TOOL.encode() + b'('
    require(original.startswith(common) and original.count(opener) == 1
            and prompt.count(opener) == 1, 'old_common_task_or_opening_call_changed')
    offset = original.index(b')', original.index(opener)) - 1
    require(original[offset:offset + 2] == b'})'
            and prompt == original[:offset] + ADDED_FIELD + original[offset:],
            'prompt_changes_other_than_single_top_level_detail_insertion')
    old_args = json.loads(original.split(opener)[1].split(b')')[0])
    new_args = json.loads(prompt.split(opener)[1].split(b')')[0])
    require('response_detail' not in old_args and new_args == {**old_args, 'response_detail': 'brief'},
            'recommended_opening_query_mismatch')
    schema = json.loads(evidence.previous(FORMAL / 'inputs/PRODUCT_SCHEMA.json'))
    require(schema['name'] == TOOL
            and set(schema['inputSchema']['properties']['response_detail']['enum']) == {'brief', 'full'},
            'retained_schema_does_not_allow_both_detail_modes')
    evidence.raw(NS / 'inputs/PLAN.md', 'a03c200bdb509008fb7d0ee2cf41c34573557ab12c925975f5baf26c420c2399')
    return old_args, new_args, {'offset': offset, 'literal': ADDED_FIELD.decode(),
                                'old_sha256': sha(original), 'new_sha256': sha(prompt),
                                'common_task_sha256': sha(common)}


def archived_call(evidence, archive, ordinal, contract, cli_event, product_log, args):
    owner = SLOT / 'owner' / f'tool_{ordinal:02d}'
    request, response, product_args, product_request, product_response, receipt = (
        json.loads(evidence.archived(archive, owner / name)) for name in (
            'REQUEST.json', 'RESPONSE.json', 'PRODUCT_ARGUMENTS.json', 'PRODUCT_REQUEST.json',
            'PRODUCT_RESPONSE.json', 'PRODUCT_RECEIPT.json'))
    require(request['method'] == product_request['method'] == 'tools/call'
            and request['params']['name'] == product_request['params']['name'] == TOOL
            and request['params']['arguments'] == product_args == product_request['params']['arguments'] == args,
            'historical_arguments_changed_at_product_handoff')
    installed = [row for row in product_log if row['request']['id'] == product_request['id']]
    require(len(installed) == 1 and installed[0]['request'] == product_request
            and installed[0]['response'] == product_response and installed[0]['receipt'] == receipt['receipt']
            and installed[0]['producer_archive'] == receipt['producer_archive'],
            'historical_installed_rpc_or_receipt_changed')
    producer_pin = receipt['producer_archive']
    producer = evidence.archived(archive, Path(producer_pin['path']))
    require(sha(producer) == producer_pin['sha256'], 'historical_product_source_archive_mismatch')

    files = [path for path in (SLOT / 'consumer/attachments').glob('bridge_*/*/TX.bin')
             if evidence.index[path.relative_to(RUNTIME).as_posix()]['sha256'] == contract['TX_sha256']]
    require(len(files) == 1, 'ambiguous_historical_client_business_request')
    tx_path, = files
    tx = evidence.archived(archive, tx_path)
    rx = evidence.archived(archive, tx_path.with_name('RX.bin'))
    wire_receipt = json.loads(evidence.archived(archive, tx_path.with_name('RECEIPT.json')))
    result = response['result']
    require(wire_receipt == contract['receipt'] and wire_receipt['attempt'] == ordinal
            and sha(rx) == contract['RX_sha256'] and json.loads(tx) == request and json.loads(rx) == response
            and result == product_response['result'] and result['isError'] is False,
            'historical_owner_installed_and_stdio_wires_diverge')
    require(contract['matched'] is True and contract['tool'] == TOOL
            and cli_event['tool'] == TOOL and cli_event['status'] == 'completed' and cli_event['error'] is None
            and cli_event['arguments'] == args and cli_event['result']['content'] == result['content'],
            'historical_public_CLI_result_does_not_match_original_wire')
    body, *images = result['content']
    body_raw = body['text'].encode('utf-8')
    require(body['type'] == 'text' and len(images) == contract['CLI_images'] == 3
            and len(body_raw) == contract['source_text_UTF8_bytes'] == contract['CLI_text_UTF8_bytes'],
            'historical_cli_content_size_or_sequence_changed')
    return result, json.loads(body_raw), json.loads(producer), {
        'attempt': ordinal, 'arguments': args, 'response_wire_sha256': sha(rx),
        'text_bytes': len(body_raw), 'text_sha256': sha(body_raw), 'actual_public_CLI_exact': True,
        'response_wire_path': str(tx_path.with_name('RX.bin')),
    }


def check_witnesses(full, brief, producer, full_result, brief_result):
    full_task = full['facts']['region_task']
    brief_task = brief['region_task']
    require(all(full_task[name] == brief_task[name] for name in ('schema', 'conditions', 'summary'))
            and len(full_task['rows']) == len(brief_task['rows']) == 3
            and all(full['binding'][name] == value for name, value in brief['binding'].items()),
            'historical_compaction_changed_task_or_shared_source_binding')
    require(full_result['content'][1:] == brief_result['content'][1:],
            'historical_full_and_brief_original_images_differ')
    compact_images = brief['images']
    images = [dict(zip(compact_images['columns'], row, strict=True)) for row in compact_images['rows']]
    original_frames = full['frames']
    require(len(images) == len(original_frames) == 3, 'historical_frame_declarations_missing')
    for position, (item, frame) in enumerate(zip(images, original_frames, strict=True), start=1):
        image = brief_result['content'][position]
        binary = base64.b64decode(image['data'], validate=True)
        require(image['type'] == 'image' and image['mimeType'] == 'image/png'
                and binary.startswith(b'\x89PNG\r\n\x1a\n') and item['native_content_block_index'] == position
                and item['image_sha256'] == sha(binary)
                and all(value == frame[name] for name, value in item.items()
                        if name != 'native_content_block_index'), 'historical_image_index_reference_or_PNG_mismatch')
        item['png_bytes'] = len(binary)

    known = {}
    pixels = brief['witness_pixels']
    pixel_records = [dict(zip(pixels['columns'], row, strict=True)) for row in pixels['rows']]
    for original, new in zip(full_task['rows'], brief_task['rows'], strict=True):
        name = new['object_name']
        require(name not in known and new['source_triangle_indices'] == [0, 1]
                and new['source']['parent_binding_sha256'] == brief['binding']['binding_sha256']
                and new['source']['parent_source_binding_sha256'] == brief['binding']['source_binding_sha256'],
                'historical_triangles_not_bound_to_compact_task_source')
        candidate = copy.deepcopy(new)
        witness = candidate['complete_witness']
        if witness is None:
            require(name == 'M06' and new['status'] == 'unknown'
                    and new['reason'] == 'positive_area_occlusion_all_front_views', 'historical_unknown_changed')
            known[name] = {'reason': new['reason']}
        else:
            position = witness.pop('native_content_block_index')
            bound = images[position - 1]
            require(all(witness[field] == bound[field] for field in ('scope_id', 'frame_identity', 'view_name', 'image_ref')),
                    'historical_local_witness_image_reference_changed')
            selected, = [entry for entry in pixel_records
                         if (entry['roi_id'], entry['scope_id'], entry['frame_identity']) ==
                         (new['roi_id'], witness['scope_id'], witness['frame_identity'])]
            require(selected['visible_surface_pixels'] >= 16 and selected['contrasting_boundary_pixels'] >= 4,
                    'historical_compact_witness_does_not_satisfy_pixel_budget')
            known[name] = {**bound, **selected}
        require(original == candidate, 'historical_region_row_changed_beyond_image_content_index')
    require(set(known) == {'M02', 'M06', 'M09'} and producer['work']['raster_attempts'] == 0
            and producer['work']['frame_reuses'] == 3, 'historical_cached_brief_work_identity_changed')
    return images, known


def check_presentation(evidence, original, results, calls):
    helper_path = SCRIPT_ROOT / 'client_budget_replay.py'
    evidence.previous(helper_path)
    helper = runpy.run_path(str(helper_path))
    policy = json.loads(evidence.previous(SCRIPT_ROOT / 'CLIENT_BUDGET_REVIEW.json'))['policy']
    for result, record in zip(results, calls, strict=True):
        saved, = [row for row in original['calls'] if row['attempt'] == record['attempt']]
        text = result['content'][0]['text']
        value = json.loads(text)
        facts = {key: value[key] for key in ('binding', 'region_task', 'images', 'witness_pixels') if key in value}
        if 'region_task' not in facts:
            facts['region_task'] = value['facts']['region_task']
        serialized = {key: json.dumps(data, ensure_ascii=False, separators=(',', ':')) for key, data in facts.items()}
        require(all(fragment in text for fragment in serialized.values()), 'historical_original_fact_serialization_changed')
        verdicts = []
        for duration in ('0.0000', '10.0000', '100.0000'):
            emitted = helper['model_items'](result, duration)
            mcp = helper['truncate_items'](emitted, policy['MCP_bytes'])
            final = helper['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
            retained = [item['text'] for item in final if item['type'] == 'input_text'][1:]
            verdicts.append({'header_bytes': len(emitted[0]['text'].encode()), 'all_items_unchanged': emitted == final,
                             'retained_body_bytes': sum(len(item.encode()) for item in retained),
                             'complete_field_retained': {key: any(fragment in item for item in retained)
                                                         for key, fragment in serialized.items()},
                             'all_images_unchanged': [item for item in emitted if item['type'] == 'input_image'] ==
                                                     [item for item in final if item['type'] == 'input_image']})
        mode = record['arguments']['response_detail']
        require(verdicts == saved['offline_presentation'] and saved['response_sha256'] == record['response_wire_sha256']
                and saved['response_detail'] == mode and saved['body_bytes'] == record['text_bytes']
                and all(row['all_images_unchanged'] and all(retained == (mode == 'brief')
                        for retained in row['complete_field_retained'].values()) for row in verdicts),
                'historical_fallback_replay_diverges_from_recorded_policy')
        record['offline_presentation'] = verdicts
    return policy


def prior_function(tree, name, scope, filename, class_name=None):
    if class_name is not None:
        tree = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(filename), 'exec'), scope)
    return scope[name]


def check_retained_bridge(evidence, original_args, brief_args, results):
    """Exercise the retained owner and installed forwarder with an in-process fake wire."""
    def save(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def append(path, value):
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value) + '\n')

    bridge_path = FORMAL / 'bridge.py'
    runtime_path = FORMAL / 'harness/runtime.py'
    original_runtime = VERIFICATION / 'm4_live_source_region_task_003/harness/owned_runtime.py'
    scope = {'copy': copy, 'json': json, 'time': time, 'Path': Path, 'save': save, 'append': append,
             'read': lambda path: json.loads(path.read_bytes()), 'sha': lambda path: sha(path.read_bytes())}
    execute = prior_function(ast.parse(evidence.previous(bridge_path)), 'product', scope, bridge_path, 'Owner')
    dispatch = prior_function(ast.parse(evidence.previous(bridge_path)), 'dispatch',
                              {**scope, 'TOOL_NAMES': {'P': {TOOL}}, 'PRODUCT_TOOL': TOOL}, bridge_path, 'Owner')
    runtime_tree = ast.parse(evidence.previous(runtime_path))
    evidence.previous(original_runtime)
    reuse = prior_function(runtime_tree, 'reuse_method', {'PREVIOUS': original_runtime, 'ast': ast,
                           '_previous': SimpleNamespace(**scope)}, runtime_path)
    node = next(node for node in runtime_tree.body if isinstance(node, ast.ClassDef) and node.name == 'Runtime')
    assignment, = [item for item in node.body if isinstance(item, ast.Assign)
                   and [target.id for target in item.targets if isinstance(target, ast.Name)] == ['public_request']]
    forward = eval(compile(ast.Expression(body=assignment.value), str(runtime_path), 'eval'), {'reuse_method': reuse})

    outcomes = []
    with TemporaryDirectory(prefix='he_brief_transparent_') as directory:
        for mode, arguments, result in (('full', {**original_args, 'response_detail': 'full'}, results[0]),
                                        ('brief', brief_args, results[1]), ('omitted', original_args, results[1])):
            folder = Path(directory) / mode
            sink = folder / 'owner'
            sink.mkdir(parents=True)
            source = folder / 'product_full' / 'SERVICE_RESULT.json'
            source.parent.mkdir()
            save(source, {})

            def fake_send(request):
                received = time.perf_counter_ns()
                require(request['params'] == {'name': TOOL, 'arguments': arguments},
                        'retained_bridge_rewrote_or_dropped_legal_request/' + mode)
                archive = {'path': str(source), 'sha256': sha(source.read_bytes()),
                           'started_ns': received, 'producer_returned_ns': time.perf_counter_ns()}
                save(source.with_name('INDEX.jsonl'), archive)
                client.records.append({'mock': True})
                return {'jsonrpc': '2.0', 'id': request['id'], 'result': result}

            client = SimpleNamespace(records=[], call=fake_send)
            runtime = SimpleNamespace(folder=folder, client=client, check=lambda: None,
                                      public_requests=[], task_deadline=1)
            runtime.public_request = lambda arguments: forward(runtime, arguments)
            owner = SimpleNamespace(group='P', runtime=runtime)
            owner.product = lambda arguments, output: execute(owner, arguments, output)
            response = dispatch(owner, TOOL, arguments, {}, sink)
            sent = json.loads((sink / 'PRODUCT_REQUEST.json').read_bytes())['params']['arguments']
            require(response == result and sent == arguments and len(runtime.public_requests) == 1,
                    'retained_bridge_transparency_replay_failed/' + mode)
            outcomes.append({'mode': mode, 'arguments_unchanged': True, 'result_unchanged': True})
    return outcomes


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_python_I_B')
    evidence = Evidence()
    old_args, brief_args, prompt = checked_prompt(evidence)
    call_specs = ((1, {**old_args, 'response_detail': 'full'}), (11, brief_args))
    with zipfile.ZipFile(evidence.zip_path) as archive:
        archived_names = archive.namelist()
        require(len(archived_names) == len(evidence.index) and set(archived_names) == set(evidence.index),
                'historical_runtime_archive_index_differ')
        business = json.loads(evidence.archived(archive, SLOT / 'consumer/BUSINESS_SOURCE_BINDING.json'))
        cli_raw = evidence.archived(archive, SLOT / 'consumer/stdout.raw.bin')
        events = [entry['item'] for entry in map(json.loads, cli_raw.splitlines())
                  if entry.get('type') == 'item.completed' and entry.get('item', {}).get('type') == 'mcp_tool_call']
        product_log = [json.loads(line) for line in evidence.archived(archive, SLOT / 'PUBLIC_REQUESTS.jsonl').splitlines()]
        config = json.loads(evidence.archived(archive, SLOT / 'consumer/ACTUAL_CONFIGURATION.json'))
        require([config[key] for key in ('requested_model', 'requested_effort', 'requested_service_tier')]
                == ['gpt-6.1-sol', 'medium', 'default'], 'historical_requested_model_configuration_changed')
        records = []
        for ordinal, args in call_specs:
            contract, = [row for row in business['result_contracts'] if row['attempt'] == ordinal]
            event, = [row for row in events if row['id'] == contract['caller_identity']['CLI_event_item_id']]
            records.append(archived_call(evidence, archive, ordinal, contract, event, product_log, args))

    (full_result, full, full_producer, full_call), (brief_result, brief, brief_producer, brief_call) = records
    require(full_call['text_bytes'] == 359581 and brief_call['text_bytes'] == 10728
            and full_producer['work']['raster_attempts'] == 4, 'historical_full_or_brief_baseline_changed')
    images, witnesses = check_witnesses(full, brief, brief_producer, full_result, brief_result)
    old_presentation = evidence.read(FORMAL / 'checks/ACTUAL_CLI_PRESENTATION.json',
                                     '00a7eaea5086a771265f4c9365cb713ce60570d1fe7ce1acc06e6fb07fd01339')
    results, calls = (full_result, brief_result), (full_call, brief_call)
    policy = check_presentation(evidence, old_presentation, results, calls)
    bridge = check_retained_bridge(evidence, old_args, brief_args, results)
    out = {'schema': 'm4-cross-scale-brief-entry-offline-preflight-v1', 'passed': True,
           'historical_commit': OLD_COMMIT, 'historical_slot': 'P1', 'prompt_change': prompt,
           'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_installed_requests': 0,
           'actual_raster_attempts': 0, 'calls': calls, 'same_ordered_original_PNGs': images,
           'historical_region_evidence': witnesses, 'offline_presentation_policy': policy,
           'offline_bridge_transparency': bridge, 'actual_provider_model_input': None,
           'source_pins': sorted(evidence.pins.values(), key=lambda row: row['path'])}
    with (NS / 'checks/PREFLIGHT.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(out, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
    print('Offline preflight passed, pinned sources:', len(evidence.pins))


if __name__ == '__main__':
    main()
