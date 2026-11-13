"""Candidate common result check wired into unchanged original driver code.

Only common_image_faults is derived. run_route and run_batch keep the original
code objects with private globals snapshots pointing at this consumer/check.
No online entry point, process service, model call or legacy mutation is added.
"""

from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
import importlib.util


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


consumer = load('_candidate_error_consumer', HERE / 'consumer.py')
LEGACY_SOURCE = ROOT / 'verification/m4_active_coverage_consumption_001/driver.py'
legacy = load('_error_contract_legacy_driver', LEGACY_SOURCE)
read = legacy.read
outer_accepted = legacy.outer_accepted
terminal_service_faults = legacy.terminal_service_faults
publish_route = legacy.publish_route


def common_image_faults(record, owner):
    """Use actual failed image construction or completed result mismatch only."""
    faults = []
    metrics_path = owner / 'METRICS.json'
    metrics = read(metrics_path) if metrics_path.exists() else {}
    render_attempts = metrics.get('common', {}).get('render_attempts')
    if type(render_attempts) is not int or not 0 <= render_attempts <= 6:
        faults.append({'reason': 'common_render_attempt_ledger_invalid', 'observed': render_attempts})
    if metrics.get('failed_image_constructions', 0):
        faults.append({'reason': 'registered_image_construction_failed', 'count': metrics['failed_image_constructions']})
    if metrics.get('post_construction_failures', 0):
        faults.append({'reason': 'constructed_image_delivery_preparation_failed', 'count': metrics['post_construction_failures']})
    if metrics.get('failed_or_unknown_socket_sends', 0):
        faults.append({'reason': 'actual_owner_socket_send_failed_or_unknown', 'count': metrics['failed_or_unknown_socket_sends']})
    if metrics.get('common', {}).get('runtime_faults'):
        faults.append({'reason': 'common_observation_runtime_failed', 'original_faults': metrics['common']['runtime_faults']})
    if record.get('unknown_image_payloads', 0):
        faults.append({'reason': 'CLI_completed_image_content_invalid', 'count': record['unknown_image_payloads']})
    tools_path = owner / 'TOOLS.json'
    original_tools = read(tools_path).get('tools', []) if tools_path.exists() else []
    tools = []
    for index, row in enumerate(original_tools):
        if type(row) is not dict or type(row.get('attempt')) is not int or row['attempt'] < 1:
            faults.append({'reason': 'owner_attempt_identity', 'row_index': index})
        else:
            tools.append(row)
    attempts = [row['attempt'] for row in tools]
    if attempts != list(range(1, len(tools) + 1)):
        faults.append({'reason': 'owner_attempt_order', 'attempts': attempts})
    for original in tools:
        if original.get('response_serialization_error'):
            faults.append({'reason': 'actual_tool_response_serialization_failed', 'attempt': original['attempt'],
                           'original_error': original['response_serialization_error']})
    completed = record.get('tool_calls', [])
    if len(tools) != len(completed):
        faults.append({'reason': 'owner_and_CLI_attempt_count', 'owner': len(tools), 'CLI': len(completed)})
        missing_owner_images = [row['attempt'] for row in tools[len(completed):]
                               if row.get('content_metrics', {}).get('image_blocks', 0)]
        extra_CLI_images = [call['item'].get('id') for call in completed[len(tools):]
                            if any(block.get('type') == 'image' for block in (call['item'].get('result') or {}).get('content', []))]
        if missing_owner_images or extra_CLI_images:
            faults.append({'reason': 'image_tool_completed_receipt_count_binding',
                           'owner_image_attempts_without_CLI_receipt': missing_owner_images,
                           'CLI_image_items_without_owner_receipt': extra_CLI_images,
                           'owner_tool_count': len(tools), 'CLI_completed_count': len(completed)})
    for original, observed in zip(tools, record.get('tool_calls', [])):
        response_path = owner / ('tool_' + str(original['attempt']).zfill(2)) / 'RESPONSE.json'
        if not response_path.exists():
            faults.append({'reason': 'owner_business_response_missing', 'attempt': original['attempt']})
            continue
        try:
            item = observed['item']
            request = read(response_path.parent / 'REQUEST.json')
            response = read(response_path)
            if (request['params']['name'] != item['tool'] or
                    consumer.packer.encoded(request['params']['arguments']) != consumer.packer.encoded(item['arguments'])):
                faults.append({'attempt': original['attempt'], 'reason': 'CLI_request_differs_from_owner'})
            request_id, response_id = request.get('id'), response.get('id')
            if (type(request_id) not in (str, int) or type(request_id) is not type(response_id)
                    or request_id != response_id):
                faults.append({'attempt': original['attempt'], 'reason': 'request_response_id_mismatch'})
            binding = consumer.result_contract.bind_tool_result(response, item)
            if not binding['matched']:
                faults.append({'attempt': original['attempt'], 'reason': 'CLI_result_differs_from_owner',
                               'result_contract': binding})
        except (OSError, ValueError, KeyError, TypeError) as error:
            faults.append({'attempt': original['attempt'], 'reason': 'owner_original_unreadable', 'error': repr(error)})
    return faults


_route_globals = dict(legacy.run_route.__globals__)
_route_globals.update(consumer=consumer, common_image_faults=common_image_faults)
run_route = types.FunctionType(legacy.run_route.__code__, _route_globals,
    legacy.run_route.__name__, legacy.run_route.__defaults__, legacy.run_route.__closure__)
run_route.__kwdefaults__ = (None if legacy.run_route.__kwdefaults__ is None
                          else dict(legacy.run_route.__kwdefaults__))
run_route.__module__ = __name__

_batch_globals = dict(legacy.run_batch.__globals__)
_batch_globals['run_route'] = run_route
run_batch = types.FunctionType(legacy.run_batch.__code__, _batch_globals,
    legacy.run_batch.__name__, legacy.run_batch.__defaults__, legacy.run_batch.__closure__)
run_batch.__kwdefaults__ = (None if legacy.run_batch.__kwdefaults__ is None
                          else dict(legacy.run_batch.__kwdefaults__))
run_batch.__module__ = __name__
