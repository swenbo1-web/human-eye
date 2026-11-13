"""Offline interface review. No current group/time/usage reads or model calls."""
import copy
import hashlib
import json
from pathlib import Path

TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = TREE / 'verification/m4_surface_scan_continuous_consumption_001'
OUT = Path(__file__).resolve().parent
CHECKS = []
INPUTS = []

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, scope):
    raw = path.read_bytes()
    INPUTS.append({'scope': scope, 'sha256': digest(raw), 'bytes': len(raw),
                   'path_sha256': digest(str(path).encode())})
    return json.loads(raw)

def exact(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')) == json.dumps(b, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))

def check(name, passed):
    CHECKS.append({'name': name, 'passed': bool(passed)})

def narrow_success(owner, item):
    """Review prototype, NOT product code or general MCP error normalization.

    Accept only the evidenced success shape. Unobserved alternatives remain
    unsupported; they are not silently considered successful delivery.
    """
    if type(owner) is not dict or 'error' in owner or type(owner.get('result')) is not dict:
        return False
    result = owner['result']
    if set(result) != {'content', 'isError'} or result['isError'] is not False:
        return False
    if item.get('status') != 'completed' or 'error' not in item or item['error'] is not None:
        return False
    other = item.get('result')
    return (type(other) is dict and set(other) == {'content', 'structured_content'}
            and other['structured_content'] is None and exact(result['content'], other['content']))

rows = []
first_pair = None
for path in sorted((BATCH / 'quality/public').glob('episode_*/turn_*/tool_evidence.json')):
    value = read(path, 'current_anonymous_business_projection')
    completed = [x['event'] for x in value['public_tool_events'] if x['phase'] == 'item.completed']
    owner = value['owner_attempts']
    check(path.parent.parent.name + '/' + path.parent.name + ':attempt_count', len(owner) == len(completed))
    for attempt, item in zip(owner, completed):
        label = path.parent.parent.name + '/' + path.parent.name + '/' + str(attempt['order'])
        check(label + ':single_response', len(attempt['responses']) == 1)
        response = attempt['responses'][0]['value']
        request = attempt['request']
        check(label + ':request_equal', request['method'] == 'tools/call' and request['params']['name'] == item['tool'] and exact(request['params']['arguments'], item['arguments']))
        check(label + ':content_exact', exact(response['result']['content'], item['result']['content']))
        check(label + ':legacy_full_result_differs', not exact(response['result'], item['result']))
        check(label + ':owner_success_explicit', response['result'].get('isError') is False and attempt['is_error'] is False and attempt['owner_exception'] is None)
        check(label + ':narrow_success', narrow_success(response, item))
        check(label + ':source_hashes_present', bool(attempt['source_files']) and all(len(x['original_sha256']) == 64 for x in attempt['source_files']))
        rows.append({'anonymous_episode': path.parent.parent.name, 'turn': path.parent.name, 'attempt': attempt['order'],
                     'content_sha256': digest(json.dumps(response['result']['content'], ensure_ascii=False, sort_keys=True).encode()),
                     'owner_result_keys': sorted(response['result']), 'CLI_result_keys': sorted(item['result']),
                     'CLI_status': item['status'], 'owner_isError': response['result']['isError'],
                     'CLI_error': item['error'], 'CLI_structured_content': item['result']['structured_content']})
        first_pair = first_pair or (response, item)
check('actual_attempts_14', len(rows) == 14)

# Existing previous formal batch: inspect only protocol responses and tool event
# records. Never inspect current private mapping, cells, cost, or usage records.
old = TREE / 'verification/m4_surface_scan_consumption_001'
plan = read(old / 'PLAN.json', 'historical_fixed_CLI_plan')
check('historical_CLI_same_SHA', plan['CLI_sha256'] == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6')
historical_errors = []
for path in sorted(old.glob('cells/*/owner/tool_*/*RESPONSE.json')):
    response = json.loads(path.read_bytes())
    if type(response.get('result')) is not dict or response['result'].get('isError') is not True:
        continue
    response = read(path, 'historical_actual_error_owner')
    request = read(path.parent / 'REQUEST.json', 'historical_actual_error_request')
    event_path = path.parents[2] / 'events.jsonl'
    event_hash = digest(event_path.read_bytes())
    matches = []
    # Read only tool events, excluding final answers, all timing and usage values.
    for raw in event_path.read_bytes().splitlines():
        event = json.loads(raw).get('event', {})
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call' and item.get('tool') == request['params']['name'] and exact(item.get('arguments'), request['params']['arguments']):
            matches.append((raw, item))
    check('historical_error_unique_' + str(len(historical_errors)), len(matches) == 1)
    raw, item = matches[0]
    check('historical_error_refused_' + str(len(historical_errors)), not narrow_success(response, item))
    check('historical_error_preserved_' + str(len(historical_errors)), item['status'] == 'failed' and item['error'] is None and exact(response['result']['content'], item['result']['content']) and item['result']['structured_content'] is None)
    historical_errors.append({'owner_response_path': path.relative_to(TREE).as_posix(),
                              'owner_request_path': (path.parent / 'REQUEST.json').relative_to(TREE).as_posix(),
                              'CLI_event_file_path': event_path.relative_to(TREE).as_posix(),
                              'owner_response_sha256': digest(path.read_bytes()), 'request_sha256': digest((path.parent / 'REQUEST.json').read_bytes()),
                              'event_file_sha256': event_hash, 'event_line_sha256': digest(raw), 'owner_isError': True,
                              'CLI_status': item['status'], 'CLI_error': item['error'], 'content_exact': True,
                              'CLI_result_keys': sorted(item['result']), 'refused_as_success': not narrow_success(response, item)})
check('historical_actual_errors_3', len(historical_errors) == 3)

# Explicitly synthetic counterexamples verify the proposed predicate only.
# They do not prove unobserved CLI error conversion behavior.
mutations = []
def mutation(name, fn):
    owner, item = copy.deepcopy(first_pair)
    fn(owner, item)
    refused = not narrow_success(owner, item)
    check('synthetic_refusal:' + name, refused)
    mutations.append({'name': name, 'refused': refused, 'evidence': 'synthetic_predicate_counterexample_not_actual_CLI_mapping'})

mutation('owner_isError_true_cli_success', lambda o, i: o['result'].__setitem__('isError', True))
mutation('owner_error_flag_numeric_zero', lambda o, i: o['result'].__setitem__('isError', 0))
mutation('owner_error_flag_missing_unproven', lambda o, i: o['result'].pop('isError'))
mutation('RPC_error_with_result', lambda o, i: o.__setitem__('error', {'code': -32000, 'message': 'fixture'}))
mutation('CLI_transport_error', lambda o, i: i.__setitem__('error', {'message': 'fixture'}))
mutation('CLI_failed_status', lambda o, i: i.__setitem__('status', 'failed'))
mutation('CLI_missing_status', lambda o, i: i.pop('status'))
mutation('CLI_missing_error_field', lambda o, i: i.pop('error'))
mutation('content_change', lambda o, i: i['result']['content'].append({'type': 'text', 'text': 'changed'}))
mutation('CLI_nonnull_structured', lambda o, i: i['result'].__setitem__('structured_content', {'meaning': 1}))
mutation('owner_nonnull_structured', lambda o, i: o['result'].__setitem__('structuredContent', {'meaning': 1}))
mutation('CLI_unknown_nonnull_field', lambda o, i: i['result'].__setitem__('other', {'meaning': 1}))
mutation('owner_unknown_nonnull_field', lambda o, i: o['result'].__setitem__('other', {'meaning': 1}))
mutation('owner_result_missing', lambda o, i: o.pop('result'))
mutation('owner_content_missing', lambda o, i: o['result'].pop('content'))
mutation('CLI_result_null', lambda o, i: i.__setitem__('result', None))
mutation('RPC_error_only', lambda o, i: (o.pop('result'), o.__setitem__('error', {'code': -32000, 'message': 'fixture'})))

diag = read(BATCH / 'diagnostics/FORMAL_BINDING_DIAG.json', 'author_diagnostic_summary_only')
check('diagnostic_compared_count', diag['compared_binding_failure_attempts'] == len(rows))
for key in ('all_compared_requests_equal', 'all_compared_business_content_exact_equal', 'all_compared_cli_status_completed_without_error', 'all_omitted_isError_flags_false', 'all_added_structured_content_null', 'all_differences_limited_to_two_envelope_fields'):
    check('author_diagnostic:' + key, diag[key] is True)

result = {'scope': 'Independent offline anonymous interface review; current group/time/usage not accessed; no author verifier imported or executed.',
          'actual_success_attempts': rows, 'historical_real_error_examples': historical_errors,
          'synthetic_predicate_counterexamples': mutations,
          'check_count': len(CHECKS), 'passed': all(x['passed'] for x in CHECKS),
          'failed_checks': [x for x in CHECKS if not x['passed']],
          'limits': ['Current requests/responses checked from published anonymous projections, with recorded original source hashes; root binding audit owns raw archive/Git attestation.',
                     'Historical CLI hash bound by frozen plan and source check; this review does not re-execute binary.',
                     'No same-version actual RPC/transport or nonnull structuredContent mapping established; narrow success adapter refuses them.',
                     'Prototype is a review predicate, not implementation acceptance or retroactive correction of failed formal episodes.']}
result['fixed_CLI_binding'] = {'frozen_plan': (old / 'PLAN.json').relative_to(TREE).as_posix(),
                               'frozen_plan_sha256': digest((old / 'PLAN.json').read_bytes()),
                               'CLI_sha256': plan['CLI_sha256'],
                               'driver_path': (old / 'runtime/driver.py').relative_to(TREE).as_posix(),
                               'driver_sha256': digest((old / 'runtime/driver.py').read_bytes()),
                               'driver_source_check': "assert sha(transport.EXE) == plan['CLI_sha256']",
                               'scope': 'Frozen historical plan and pre-run driver hash check; no new CLI execution.'}
for filename, value in [('RESULTS.json', result), ('CHECKS.json', CHECKS), ('INPUT_HASHES.json', INPUTS)]:
    (OUT / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'checks': len(CHECKS), 'passed': result['passed'], 'actual_success_attempts': len(rows), 'historical_real_errors': len(historical_errors), 'synthetic_refusals': len(mutations), 'failed': result['failed_checks']}, ensure_ascii=False))
