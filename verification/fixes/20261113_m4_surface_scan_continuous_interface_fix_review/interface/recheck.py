"""Independent offline calls of actual old/new archive_turn implementations."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001'
OLD = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
FORMAL = ROOT / 'verification/m4_surface_scan_continuous_consumption_001'
OUT = Path(__file__).resolve().parent
RUN = OUT / 'run_01'
CHECKS, INPUTS, RESULTS = [], {}, []

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def raw(path):
    b = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(b), 'sha256': sha(b)}
    return b

def check(name, ok, detail=None):
    CHECKS.append({'name': name, 'passed': bool(ok), 'detail': detail})

def enc(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode() + b'\n'

def load(name, path):
    raw(path)
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m

def function(path, name):
    return next(n for n in ast.parse(raw(path).decode('utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name == name)

RUN.mkdir(parents=True, exist_ok=False)
head_before = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
check('fixed_delivery', head_before == 'b51dc02eb4f25966f983033b42dad3c9cfec9393')
new = load('_root_real_new_transport', B / 'runtime/consumer_transport.py')
old = load('_root_real_old_transport', OLD / 'runtime/consumer_transport.py')
episode = load('_root_real_new_episode', B / 'runtime/episode.py')
stop = load('_root_stop_recommendation', B / 'review/stop_recommendation.py')
check('new_consume_is_legacy_function', new.consume_turn is new.legacy.consume_turn)
check('new_consume_globals_archive', new.consume_turn.__globals__['archive_turn'] is new.archive_turn)
check('new_archive_globals_compatibility', new.archive_turn.__globals__['compatibility'] is new.compatibility)
check('episode_function_is_legacy', episode.run_episode is episode.legacy.run_episode)
check('episode_globals_transport', episode.run_episode.__globals__['transport'] is episode.transport)
check('episode_transport_consume_globals', episode.transport.consume_turn.__globals__['archive_turn'] is episode.transport.archive_turn)
check('episode_actual_new_archive_same_code', episode.transport.archive_turn.__code__.co_code == new.archive_turn.__code__.co_code)

old_fn = function(OLD / 'runtime/consumer_transport.py', 'archive_turn')
new_fn = function(B / 'runtime/consumer_transport.py', 'archive_turn')
normal = copy.deepcopy(new_fn)
changed = []
for n in ast.walk(normal):
    if isinstance(n, ast.If) and isinstance(n.test, ast.BoolOp) and isinstance(n.test.op, ast.And):
        expression = ast.unparse(n.test)
        if 'compatibility.successful_result_matches' in expression:
            check('new_test_exactly_one_extension', len(n.test.values) == 2 and isinstance(n.test.values[1], ast.UnaryOp) and isinstance(n.test.values[1].op, ast.Not))
            changed.append(expression)
            n.test = n.test.values[0]
check('one_AST_condition_changed', len(changed) == 1)
check('archive_AST_otherwise_identical', ast.dump(normal, include_attributes=False) == ast.dump(old_fn, include_attributes=False))

cases = []
for zpath in sorted((FORMAL / 'episodes').glob('*/ORIGINALS.zip')):
    archive_bytes = raw(zpath)
    with zipfile.ZipFile(zpath) as z:
        eraw = z.read('c/turns/BASE/events.jsonl')
        items = []
        for line in eraw.splitlines():
            e = json.loads(line).get('event', {})
            i = e.get('item', {})
            if e.get('type') == 'item.completed' and i.get('type') == 'mcp_tool_call':
                items.append((i, sha(line)))
        tools = json.loads(z.read('owner/TOOLS.json'))['tools']
        check('actual_archive_attempt_count:' + zpath.parent.name, len(tools) == len(items))
        for row, (item, event_sha) in zip(tools, items):
            prefix = 'owner/tool_' + str(row['attempt']).zfill(2) + '/'
            members = {n[len(prefix):]: z.read(n) for n in z.namelist() if n.startswith(prefix) and not n.endswith('/')}
            request = json.loads(members['REQUEST.json'])
            response = json.loads(members['RESPONSE.json'])
            name = 'actual_success_' + str(len(cases) + 1).zfill(2)
            check(name + ':request_identity', request['params']['name'] == item['tool'] and enc(request['params']['arguments']) == enc(item['arguments']))
            check(name + ':content_same', enc(response['result']['content']) == enc(item['result']['content']))
            cases.append({'name': name, 'kind': 'actual_success', 'request': request, 'response': response, 'item': item,
                          'owner_row': row, 'members': members, 'source': {'archive': str(zpath), 'archive_sha256': sha(archive_bytes),
                          'event_member': 'c/turns/BASE/events.jsonl', 'event_line_sha256': event_sha,
                          'request_member': prefix + 'REQUEST.json', 'request_sha256': sha(members['REQUEST.json']),
                          'response_member': prefix + 'RESPONSE.json', 'response_sha256': sha(members['RESPONSE.json'])}})
check('actual_success_count14', len(cases) == 14)

previous = ROOT / 'verification/m4_surface_scan_consumption_001'
for path in sorted(previous.glob('cells/*/owner/tool_*/*RESPONSE.json')):
    response = json.loads(path.read_bytes())
    if not isinstance(response.get('result'), dict) or response['result'].get('isError') is not True:
        continue
    response = json.loads(raw(path))
    request = json.loads(raw(path.parent / 'REQUEST.json'))
    epath = path.parents[2] / 'events.jsonl'
    matches = []
    for line in raw(epath).splitlines():
        e = json.loads(line).get('event', {})
        item = e.get('item', {})
        if e.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call' and item.get('tool') == request['params']['name'] and enc(item.get('arguments')) == enc(request['params']['arguments']):
            matches.append((item, sha(line)))
    check('historical_error_unique:' + path.parent.name + ':' + path.parents[2].name, len(matches) == 1)
    item, esha = matches[0]
    row = next(r for r in json.loads(raw(path.parents[1] / 'TOOLS.json'))['tools'] if r['attempt'] == int(path.parent.name.removeprefix('tool_')))
    cases.append({'name': 'actual_error_' + str(sum(x['kind'] == 'actual_error' for x in cases) + 1),
                  'kind': 'actual_error', 'request': request, 'response': response, 'item': item, 'owner_row': row,
                  'members': {p.name: raw(p) for p in path.parent.iterdir() if p.is_file()},
                  'source': {'request': str(path.parent / 'REQUEST.json'), 'response': str(path),
                             'events': str(epath), 'event_line_sha256': esha}})
check('actual_historical_error_count3', sum(x['kind'] == 'actual_error' for x in cases) == 3)

def run_archive(module, case, suffix, expected):
    root = RUN / case['name'] / suffix
    folder, owner = root / 'turn', root / 'owner'
    folder.mkdir(parents=True)
    number = case['owner_row']['attempt']
    original = owner / ('tool_' + str(number).zfill(2))
    original.mkdir(parents=True)
    for name, value in case['members'].items():
        target = original / name
        assert target.resolve().is_relative_to(original.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    # Metadata selects one recorded attempt; all actual tool original bytes stay exact.
    (owner / 'TOOLS.json').write_bytes(enc({'tools': [case['owner_row']]}))
    result = module.archive_turn(folder, {'audit_dir': str(owner)}, number, [{'item': case['item']}])
    errors = result['business_binding_errors']
    passed = not errors
    check(case['name'] + ':' + suffix + ':binding', passed == expected, errors)
    for name, value in case['members'].items():
        check(case['name'] + ':' + suffix + ':copy:' + name, (folder / 'owner_turn' / original.name / name).read_bytes() == value)
    check(case['name'] + ':' + suffix + ':archive_exists', Path(result['archive']).is_file())
    return {'binding_passed': passed, 'errors': errors, 'archive_sha256': result['archive_sha256']}

for case in cases:
    observed_old = run_archive(old, case, 'old', False)
    observed_new = run_archive(new, case, 'new', case['kind'] == 'actual_success')
    helper = new.compatibility.successful_result_matches(case['response'], case['item'])
    check(case['name'] + ':helper', helper == (case['kind'] == 'actual_success'))
    check(case['name'] + ':stop_original_fault', stop.shared_success_binding_fault('CLI_result_differs_from_owner', case['response'], case['item']) == (case['kind'] == 'actual_success'))
    check(case['name'] + ':no_stop_without_fault', not stop.shared_success_binding_fault(None, case['response'], case['item']))
    RESULTS.append({'name': case['name'], 'kind': case['kind'], 'source': case['source'], 'old': observed_old, 'new': observed_new, 'helper_success': helper})

base = cases[0]
variants = []
def variant(name, change, expected_new=False, expected_old=False, helper=False):
    case = copy.deepcopy(base)
    case.update(name='variant_' + name, kind='directed_variant')
    change(case)
    case['members']['REQUEST.json'] = enc(case['request'])
    case['members']['RESPONSE.json'] = enc(case['response'])
    old_result = run_archive(old, case, 'old', expected_old)
    new_result = run_archive(new, case, 'new', expected_new)
    try:
        helper_result = new.compatibility.successful_result_matches(case['response'], case['item'])
    except (ValueError, TypeError) as e:
        helper_result = False
    check(case['name'] + ':helper', helper_result == helper)
    variants.append({'name': name, 'old': old_result, 'new': new_result, 'helper_success': helper_result})

variant('owner_flag_true', lambda c: c['response']['result'].__setitem__('isError', True))
variant('owner_flag_zero', lambda c: c['response']['result'].__setitem__('isError', 0))
variant('owner_flag_null', lambda c: c['response']['result'].__setitem__('isError', None))
variant('owner_flag_missing', lambda c: c['response']['result'].pop('isError'))
variant('CLI_failed', lambda c: c['item'].__setitem__('status', 'failed'))
variant('CLI_status_missing', lambda c: c['item'].pop('status'))
variant('CLI_error_object', lambda c: c['item'].__setitem__('error', {'message': 'synthetic'}))
variant('CLI_error_false', lambda c: c['item'].__setitem__('error', False))
variant('CLI_error_missing', lambda c: c['item'].pop('error'))
variant('owner_RPC_error', lambda c: c['response'].__setitem__('error', {'code': -32000, 'message': 'synthetic'}))
variant('owner_result_missing', lambda c: c['response'].pop('result'))
variant('CLI_result_missing', lambda c: c['item'].pop('result'))
variant('CLI_content_missing', lambda c: c['item']['result'].pop('content'))
variant('CLI_content_changed', lambda c: c['item']['result']['content'].append({'type': 'text', 'text': 'changed'}))
variant('CLI_content_null', lambda c: c['item']['result'].__setitem__('content', None))
variant('both_content_string', lambda c: (c['response']['result'].__setitem__('content', 'x'), c['item']['result'].__setitem__('content', 'x')))
variant('content_numeric_type', lambda c: (c['response']['result'].__setitem__('content', [False]), c['item']['result'].__setitem__('content', [0])))
variant('content_order', lambda c: (c['response']['result'].__setitem__('content', ['a', 'b']), c['item']['result'].__setitem__('content', ['b', 'a'])))
variant('owner_nonnull_structured', lambda c: c['response']['result'].__setitem__('structuredContent', {'x': 1}))
variant('CLI_nonnull_structured', lambda c: c['item']['result'].__setitem__('structured_content', {'x': 1}))
variant('owner_unknown_field', lambda c: c['response']['result'].__setitem__('additional', {'x': 1}))
variant('CLI_unknown_field', lambda c: c['item']['result'].__setitem__('additional', {'x': 1}))
variant('request_argument_changed', lambda c: c['item']['arguments'].__setitem__('extra', 'changed'), helper=True)
variant('request_tool_changed', lambda c: c['item'].__setitem__('tool', 'changed'), helper=True)
variant('request_arguments_missing', lambda c: c['item'].pop('arguments'), helper=True)

def exact_error(c):
    c['response']['result']['isError'] = True
    c['item']['result'] = copy.deepcopy(c['response']['result'])
    c['item']['status'] = 'failed'
variant('legacy_exact_error_preserved', exact_error, expected_new=True, expected_old=True, helper=False)
def exact_rpc(c):
    c['response'] = {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32000, 'message': 'synthetic'}}
    c['item']['result'] = None
    c['item']['error'] = {'message': 'synthetic'}
    c['item']['status'] = 'failed'
variant('legacy_exact_null_RPC_preserved', exact_rpc, expected_new=True, expected_old=True, helper=False)
def exact_structured(c):
    c['response']['result']['structuredContent'] = {'x': 1}
    c['item']['result'] = copy.deepcopy(c['response']['result'])
variant('legacy_exact_structured_preserved', exact_structured, expected_new=True, expected_old=True, helper=False)
def same_success(c):
    c['item']['result'] = copy.deepcopy(c['response']['result'])
variant('legacy_exact_success', same_success, expected_new=True, expected_old=True, helper=True)
def business_nested(c):
    content = [{'type': 'text', 'text': '{"isError":true,"structured_content":{"n":2}}', 'extra': {'isError': True, 'structured_content': {'n': 3}}}]
    c['response']['result']['content'] = copy.deepcopy(content)
    c['item']['result']['content'] = copy.deepcopy(content)
variant('nested_business_fields_preserved', business_nested, expected_new=True, expected_old=False, helper=True)

stop_source = (B / 'review/stop_recommendation.py').read_text(encoding='utf8')
check('stop_recommendation_not_active_formal', 'No formal driver imports' in stop_source)
for reason in ('incorrect_answer', 'owner_and_CLI_attempt_count', 'owner_original_unreadable'):
    check('stop_bounded_reason:' + reason, not stop.shared_success_binding_fault(reason, base['response'], base['item']))
check('stop_request_fault', stop.shared_success_binding_fault('CLI_request_differs_from_owner', base['response'], base['item']))

head_after = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
check('HEAD_unchanged', head_before == head_after)
for path, identity in INPUTS.items():
    check('input_unchanged:' + path, sha(Path(path).read_bytes()) == identity['sha256'])
result = {'fixed_delivery': head_before, 'actual_success_attempts': 14, 'actual_historical_errors': 3,
          'directed_rejections': 25, 'legacy_and_business_controls': 5,
          'actual_archive_function_calls': 2 * (len(cases) + len(variants)),
          'checks': len(CHECKS), 'passed': all(x['passed'] for x in CHECKS), 'failed_checks': [x for x in CHECKS if not x['passed']],
          'actual_cases': RESULTS, 'directed_cases': variants, 'AST_changed_condition': changed,
          'limits': ['Actual archive_turn invoked; no author checker invoked.', 'Module imports and offline archive copies only; no consumer/Blender/product/provider started.',
                     'Process-loop integration fixture results are not rerun here; function globals and unchanged AST independently checked.',
                     'Old exact branch width intentionally preserved, not treated as this patch widening.',
                     'stop recommendation is executable pure predicate, not yet formal-driver integration; freeze that small connection in 002.']}
for filename, value in [('RESULTS.json', result), ('CHECKS.json', CHECKS), ('INPUT_HASHES.json', INPUTS)]:
    (OUT / filename).write_bytes(enc(value))
print(json.dumps({k:result[k] for k in ('checks','passed','actual_archive_function_calls','actual_success_attempts','actual_historical_errors','directed_rejections','legacy_and_business_controls','failed_checks')}, ensure_ascii=False))
