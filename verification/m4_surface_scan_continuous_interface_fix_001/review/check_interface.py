"""Independent bounded source and protocol checks, with no process execution."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def function(path, name):
    return next(node for node in ast.parse(path.read_text(encoding='utf8')).body
                if isinstance(node, ast.FunctionDef) and node.name == name)


def main():
    checks = []
    source_paths = set()
    stop_cases = []

    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})

    def stop_case(name, reason, owner, cli_item, expected, source_kind):
        actual = stop(reason, owner, cli_item)
        stop_cases.append({'case': name, 'source_kind': source_kind, 'binding_reason': reason,
                           'owner_isError': owner.get('result', {}).get('isError'),
                           'CLI_status': cli_item.get('status'), 'should_stop': actual, 'expected': expected})
        check(name, actual is expected)

    compat_path = BATCH / 'compatibility.py'
    transport_path = BATCH / 'runtime/consumer_transport.py'
    episode_path = BATCH / 'runtime/episode.py'
    old_transport = FIX1 / 'runtime/consumer_transport.py'
    source_paths.update((compat_path, transport_path, episode_path, old_transport, Path(__file__),
                         HERE / 'stop_recommendation.py'))
    episode = load('_independent_interface_episode', episode_path)
    transport = episode.transport
    success = transport.compatibility.successful_result_matches
    stop = load('_independent_interface_stop_proposal', HERE / 'stop_recommendation.py').shared_success_binding_fault
    check('original_process_loop_calls_new_archive', transport.consume_turn.__globals__['archive_turn'] is transport.archive_turn)
    check('original_coordinator_calls_new_transport', episode.run_episode.__globals__['transport'] is transport)
    check('original_process_function_reused', Path(transport.consume_turn.__code__.co_filename).resolve() == old_transport.resolve())

    old_archive = function(old_transport, 'archive_turn')
    expected_archive = copy.deepcopy(old_archive)
    replacement_count = 0
    for node in ast.walk(expected_archive):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "packer.encoded(response.get('result')) != packer.encoded(item.get('result'))":
            node.test = ast.BoolOp(op=ast.And(), values=[node.test, ast.UnaryOp(op=ast.Not(), operand=ast.Call(
                func=ast.Attribute(value=ast.Name(id='compatibility', ctx=ast.Load()),
                                   attr='successful_result_matches', ctx=ast.Load()),
                args=[ast.Name(id='response', ctx=ast.Load()), ast.Name(id='item', ctx=ast.Load())], keywords=[]))])
            replacement_count += 1
    check('archive_diff_is_only_narrow_fallback', replacement_count == 1 and
          ast.dump(expected_archive, include_attributes=False) == ast.dump(function(transport_path, 'archive_turn'), include_attributes=False))

    current_response_path = ROOT / '.m4cc1/C1/owner/tool_01/RESPONSE.json'
    current_consumer_path = ROOT / '.m4cc1/C1/c/turns/BASE/CONSUMER.json'
    source_paths.update((current_response_path, current_consumer_path))
    response = read(current_response_path)
    item = read(current_consumer_path)['tool_calls'][0]['item']

    def binding_matches(owner, cli_item):
        return (transport.packer.encoded(owner.get('result')) == transport.packer.encoded(cli_item.get('result'))
                or success(owner, cli_item))

    check('recorded_success_accepted', success(response, item) and binding_matches(response, item))
    check('recorded_success_old_binding_fault_would_stop', stop('CLI_result_differs_from_owner', response, item))
    check('fixed_success_no_binding_fault_does_not_stop', not stop(None, response, item))
    check('ordinary_wrong_answer_does_not_stop', not stop('incorrect_answer', response, item))
    check('generic_binding_stage_is_insufficient', not stop('business_original_binding', response, item))
    stop_case('recorded_success_old_result_binding_fault', 'CLI_result_differs_from_owner', response, item,
              True, 'recorded_success_with_original_binding_reason')
    stop_case('recorded_success_request_binding_fault', 'CLI_request_differs_from_owner', response, item,
              True, 'synthetic_binding_reason_on_recorded_success')
    stop_case('fixed_success_without_binding_fault', None, response, item, False,
              'recorded_success_after_narrow_compatibility')
    stop_case('ordinary_answer_error_without_binding_fault', 'incorrect_answer', response, item, False,
              'synthetic_content_error_reason')
    failed_item = copy.deepcopy(item)
    failed_item['status'] = 'failed'
    stop_case('CLI_failed_is_not_explicit_success', 'CLI_result_differs_from_owner', response, failed_item,
              False, 'synthetic_failed_status')
    same_success = copy.deepcopy(item)
    same_success['result'] = copy.deepcopy(response['result'])
    check('same_representation_success', success(response, same_success) and binding_matches(response, same_success))

    variants = []

    def variant(name, owner_change=None, item_change=None):
        owner, cli_item = copy.deepcopy(response), copy.deepcopy(item)
        if owner_change:
            owner_change(owner)
        if item_change:
            item_change(cli_item)
        variants.append((name, owner, cli_item))

    variant('owner_false_numeric_zero', lambda value: value['result'].__setitem__('isError', 0))
    variant('owner_false_empty_string', lambda value: value['result'].__setitem__('isError', ''))
    variant('owner_error_true', lambda value: value['result'].__setitem__('isError', True))
    variant('RPC_error_even_null', lambda value: value.__setitem__('error', None))
    variant('CLI_failed', item_change=lambda value: value.__setitem__('status', 'failed'))
    variant('CLI_nonnull_error', item_change=lambda value: value.__setitem__('error', 'transport failure'))
    variant('CLI_missing_error_field', item_change=lambda value: value.pop('error'))
    variant('CLI_unknown_result_field', item_change=lambda value: value['result'].__setitem__('unexpected', None))
    variant('CLI_nonempty_structured_content', item_change=lambda value: value['result'].__setitem__('structured_content', {'a': 1}))
    variant('CLI_structured_content_zero', item_change=lambda value: value['result'].__setitem__('structured_content', 0))
    variant('CLI_missing_content', item_change=lambda value: value['result'].pop('content'))
    variant('CLI_content_block_deleted', item_change=lambda value: value['result'].__setitem__('content', []))
    variant('CLI_text_changed', item_change=lambda value: value['result']['content'][0].__setitem__('text', 'changed'))
    for name, owner, cli_item in variants:
        check('success_predicate_rejects_' + name, not success(owner, cli_item))

    opaque_owner, opaque_item = copy.deepcopy(response), copy.deepcopy(item)
    content = [{'type': 'text', 'text': '{"isError":true,"structured_content":{"business":"opaque"}}'}]
    opaque_owner['result']['content'] = content
    opaque_item['result']['content'] = copy.deepcopy(content)
    check('opaque_business_strings_remain_exact', success(opaque_owner, opaque_item)
          and opaque_item['result']['content'] == content)

    error_inputs = [
        ('P1', 3, 'ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1'),
        ('P3', 3, 'ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1'),
        ('P3', 4, '16fc3b405b84c0f717020760983cafcadb40b8eb23a1c8844b4c76153e6272b3'),
    ]
    for cell, attempt, expected_sha in error_inputs:
        folder = ROOT / 'verification/m4_surface_scan_consumption_001/cells' / cell
        owner_path = folder / 'owner' / ('tool_' + str(attempt).zfill(2)) / 'RESPONSE.json'
        events_path = folder / 'events.jsonl'
        source_paths.update((owner_path, events_path))
        check(cell + '_' + str(attempt) + '_fixed_real_error_source', sha(owner_path) == expected_sha)
        owner = read(owner_path)
        events = [json.loads(line)['event'] for line in events_path.read_bytes().splitlines()]
        tools = [event['item'] for event in events if event.get('type') == 'item.completed'
                 and event.get('item', {}).get('type') == 'mcp_tool_call']
        error_item = tools[attempt - 1]
        label = cell + '_' + str(attempt)
        check(label + '_recorded_error_state', owner['result']['isError'] is True
              and error_item['status'] == 'failed' and error_item['error'] is None)
        check(label + '_real_error_rejected_as_success', not success(owner, error_item))
        check(label + '_cross_representation_failure_preserved', not binding_matches(owner, error_item))
        check(label + '_normal_error_is_not_shared_harness_stop', not stop('CLI_result_differs_from_owner', owner, error_item))
        stop_case(label + '_actual_tool_error_does_not_stop_batch', 'CLI_result_differs_from_owner',
                  owner, error_item, False, 'recorded_historical_tool_error')
        same_error = copy.deepcopy(error_item)
        same_error['result'] = copy.deepcopy(owner['result'])
        check(label + '_synthetic_same_representation_error_keeps_old_binding', binding_matches(owner, same_error)
              and not success(owner, same_error) and same_error['status'] == 'failed'
              and same_error['result']['isError'] is True)
    old_cli = ROOT / 'verification/m4_surface_scan_continuity_001/cli/continuity_cli.py'
    source_paths.add(old_cli)
    source = old_cli.read_text(encoding='utf8')
    check('existing_summary_not_replaced', Path(transport.legacy.cli.summarize_turn.__code__.co_filename).resolve() == old_cli.resolve())
    check('tool_failed_not_newly_forced_into_summary_error', 'mcp_tool_call' not in source)
    output = {
        'scope': 'Independent pure checks and AST/source binding. No provider/model/product/Blender/runtime-subprocess or Git operation.',
        'passed': all(row['passed'] for row in checks), 'checks': checks,
        'binding_match_is_tool_success': False, 'old_same_representation_error_policy_preserved': True,
        'stop_condition_is_recommendation_only': True, 'formal_driver_modified': False,
        'source_sha256': {str(path): sha(path) for path in sorted(source_paths)},
    }
    (HERE / 'CHECK.json').write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                   encoding='utf8', newline='\n')
    (HERE / 'STOP_CASES.json').write_text(json.dumps({
        'recommendation_only': True, 'formal_driver_modified': False, 'cases': stop_cases,
        'scope': 'A future frozen contract may map true to an existing stop_reason after sole cleanup. No rescheduling, correction or replacement is implemented.'},
        ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed': output['passed'], 'checks': len(checks)}))


if __name__ == '__main__':
    main()
