"""Replay exact archived tool bodies through the actual formal consumer adapter."""

import argparse
import copy
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EXTERNAL, NS, PRODUCT_BINDING, RECOVERY_EXTERNAL, read, save, sha


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def event_for(request, response):
    result = response['result']
    item = {'type': 'mcp_tool_call', 'id': 'preflight-tool-item', 'server': 'arm_engine',
            'tool': request['params']['name'], 'arguments': request['params']['arguments'],
            'status': 'failed' if result['isError'] else 'completed', 'error': None,
            'result': {'content': result['content'], 'structured_content': None}}
    return {'perf_ns': 1, 'type': 'item.completed', 'item': item}


def replay(folder, group, slot, scope, raw_event=None):
    output = folder / group
    output.mkdir(exist_ok=False)
    owner = slot / 'owner'
    attachments = slot / ('client/attachments' if raw_event is None else 'consumer/attachments')
    req_path = owner / 'tool_01/REQUEST.json'
    res_path = owner / 'tool_01/RESPONSE.json'
    request, response = read(req_path), read(res_path)
    matches = [tx.parent for tx in attachments.glob('bridge_*/*/TX.bin') if read(tx) == request]
    require(len(matches) == 1, 'exactly_one_original_tool_wire_match/' + group)
    wire = matches[0]
    require(read(wire / 'RX.bin') == response and (wire / 'RX.bin').read_bytes() == res_path.read_bytes(),
            'owner_and_stdio_original_bytes_differ/' + group)
    copied = output / 'attachments' / wire.parent.name / wire.name
    copied.mkdir(parents=True)
    pins = [req_path, res_path, owner / 'tool_01/RECEIPT.json']
    for name in ('TX.bin', 'RX.bin', 'RECEIPT.json'):
        source = wire / name
        pins.append(source)
        (copied / name).write_bytes(source.read_bytes())

    # Earlier assembly slot had subsequent calls. This projection contains
    # only the original matching attempt and its byte-exact owner envelopes.
    owner_output = folder / (group + '_owner')
    owner_attempt = owner_output / 'tool_01'
    owner_attempt.mkdir(parents=True)
    for p in (req_path, res_path, owner / 'tool_01/RECEIPT.json'):
        (owner_attempt / p.name).write_bytes(p.read_bytes())
    tool_file = owner / 'TOOLS.json'
    pins.append(tool_file)
    tools = [row for row in read(tool_file)['tools'] if row['attempt'] == 1]
    require(len(tools) == 1, 'missing_original_owner_first_attempt/' + group)
    save(owner_output / 'TOOLS.json', {'tools': tools})

    event = raw_event or event_for(request, response)
    classifier = scope['bridge_contract'].classify_tool_item
    require(classifier(event['item'], completed=True) == 'business', 'formal_tool_item_not_classified/' + group)
    started = {**event['item'], 'status': 'in_progress', 'result': None}
    require(classifier(started, completed=False) == 'business', 'formal_start_not_classified/' + group)
    bad_server = {**event['item'], 'server': 'unregistered_test_server'}
    require(classifier(bad_server, completed=True) == 'unexpected', 'unregistered_tool_classified_as_known/' + group)

    packed = scope['archive_turn'](output, {'group': 'N' if group == 'ordinary' else 'P',
                                  'audit_dir': str(owner_output)}, 1, [event])
    require(packed['business_binding_errors'] == [] and packed['stdio_attempts'] == 1,
            'formal_archive_rejected_original/' + group)
    [bound] = packed['result_contracts']
    require(bound['TX_sha256'] == sha(wire / 'TX.bin') and bound['RX_sha256'] == sha(wire / 'RX.bin'),
            'formal_archive_unbound_to_original/' + group)
    expectation = 'tool_error' if response['result']['isError'] else 'success'
    require(bound['matched'] and bound['classification'] == expectation
            and (packed['first_CLI_nonempty_successful_evidence_ns'] is None) == (expectation == 'tool_error'),
            'formal_archive_failed_to_separate_normal_error/' + group)
    body = event['item']['result']['content']
    require(body == response['result']['content'], 'CLI_event_content_appears_changed/' + group)
    images = scope['completed_images'](event['item'], event['perf_ns'], len(json.dumps(event).encode()))
    require(all(image['payload_valid'] for image in images)
            and [image['block_index'] for image in images] == [idx for idx, value in enumerate(body)
                                                                if value['type'] == 'image'],
            'formal_image_telemetry_lost_original_order/' + group)
    binder = scope['bridge_contract'].bind_tool_result
    mutations = {}

    def reject(reason, altered):
        checked = binder(response, altered)
        require(not checked['matched'], 'formal_controls_accepted_mismatch/' + reason)
        mutations[reason] = checked['reason']

    if len(images) >= 2:
        left, right = (image['block_index'] for image in images[:2])
        altered = copy.deepcopy(event['item'])
        blocks = altered['result']['content']
        blocks[left], blocks[right] = blocks[right], blocks[left]
        reject('PNG_order_changed', altered)
    altered = copy.deepcopy(event['item'])
    altered['result']['content'][0]['text'] += '\n'
    reject('original_text_changed', altered)
    if group == 'ordinary':
        require([blk['type'] for blk in body] == ['text', 'text', 'image', 'text', 'image'],
                'real_mixed_text_caption_fixture_changed')
        altered = copy.deepcopy(event['item'])
        altered['result']['content'][1]['text'] = altered['result']['content'][3]['text']
        reject('ordinary_caption_ref_changed', altered)
    altered = copy.deepcopy(event['item'])
    altered['status'] = 'completed' if expectation == 'tool_error' else 'failed'
    reject('formal_result_error_mask_changed', altered)
    item_types = [blk['type'] for blk in body]
    return {'classification': bound['classification'], 'item_types': item_types,
            'original_wire_pins': [file_pin(path) for path in pins], 'CLI_images': images,
            'original_response_sha256': sha(res_path), 'consumption_archive_sha256': packed['archive_sha256'],
            'matching_evidence_ns': packed['first_CLI_nonempty_successful_evidence_ns'],
            'rejects': mutations, 'formal_LEDGER_and_archive_verified': True}


def file_pin(path):
    return {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}


def budget_controls(output):
    from budget import Budget, LIMITS
    ledger = Budget(output / 'offline_claim_test')
    require(LIMITS['all_rasters'] == 24 and LIMITS['Blender_start_attempts'] == LIMITS['consumer_tasks'] == 2,
            'paired_formal_limits_changed')
    for label in ('N1', 'P1'):
        for _ in range(12):
            ledger.reserve('raster_attempt', label)
            ledger.reserve('business_tool', label)
        ledger.reserve('Blender_start', label)
        ledger.reserve('consumer_task', label)
        rejected = {'raster_attempt': 'raster_budget_exhausted', 'business_tool': 'business_tool_budget_exhausted',
                    'Blender_start': 'registered_slot_already_admitted/Blender_start',
                    'consumer_task': 'registered_slot_already_admitted/consumer_task'}
        for kind, expected in rejected.items():
            try:
                ledger.reserve(kind, label)
            except RuntimeError as error:
                require(str(error) == expected, 'wrong_budget_exhaustion/' + kind)
            else:
                raise ValueError('ledger_exceeded_formal_limit/' + kind)
    try:
        ledger.reserve('Blender_start', 'QN', phase='qualification')
    except ValueError:
        pass
    else:
        raise ValueError('formal_ledger_admitted_qualification')
    return {'formal_limits': LIMITS, 'potential_claims_control_only': ledger.snapshot()['counts']}


def main(output):
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_the_fixed_interpreter_I_B')
    require(output.is_relative_to(EXTERNAL.resolve() / 'preflight'), 'offline_stage_outside_new_namespace')
    output.mkdir(parents=True, exist_ok=False)
    binding = read(PRODUCT_BINDING)
    shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from consumer import consumer_adapter

    turn, proof, _ = consumer_adapter()
    scope = turn.__globals__
    cases = {name: replay(output, name, RECOVERY_EXTERNAL / 'slots' / slot, scope)
             for name, slot in (('ordinary', 'QN'), ('product', 'QP'))}
    # Replay a normal tool error observed by the actual earlier CLI. The
    # assembly first-call gate causing it is outside this experiment.
    failure = Path('D:/he_m4_assembly_evidence_consumption_001/slots/A1')
    original_consumer = failure / 'consumer/CONSUMER.json'
    bad_events = [row for row in read(original_consumer)['tool_calls']
                  if row['item'].get('tool') == 'human_eye_scene_observe' and row['item'].get('status') == 'failed']
    require(len(bad_events) == 1, 'one_preceding_real_CLI_tool_error_required')
    cases['normal_error'] = replay(output, 'normal_error', failure, scope, raw_event=bad_events[0])
    cases['normal_error']['original_wire_pins'].append(file_pin(original_consumer))
    save(output / 'PREFLIGHT.json', {'passed': True, 'cases': cases, 'budget_control': budget_controls(output),
         'formal_execution_sources': proof['execution_sources'],
         'actual_model_runs': 0, 'actual_Blender_processes': 0, 'actual_raster': 0,
         'scope': 'Existing formal classifier, image telemetry, reply binder and archive invoked offline. '
                  'Current qualifying owner bodies in exact wire order are projected to the standard CLI envelope.'})
    print(output / 'PREFLIGHT.json', sha(output / 'PREFLIGHT.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output.resolve())
