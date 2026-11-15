"""Directed checks for new context, relaxed quotas and rejection recovery only."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('m5_task_consumption_001')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pin(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')


def encoded(rows):
    return b''.join(json.dumps(row, sort_keys=True).encode() + b'\n' for row in rows)


def main():
    output = HERE / 'MIGRATION_PURE_01'
    output.mkdir(exist_ok=False)
    events, checks = [], []

    def prohibit_actual(event, args):
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'socket.connect', 'socket.bind'):
            events.append(event)
            raise RuntimeError('pure_control_forbids_actual_start_' + event)

    sys.addaudithook(prohibit_actual)
    bootstrap = load('_recovery_pure_bootstrap', HERE / 'bootstrap.py')
    bootstrap.prepare_dependencies()
    bridge = load('_recovery_pure_bridge', HERE / 'bridge.py')
    runtime_module = load('_recovery_pure_runtime', HERE / 'harness/owned_runtime.py')
    runtime_before = pin(HERE / 'harness/owned_runtime.py')
    budget_before = pin(HERE / 'harness/budget.py')

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    check('all_context_roots_are_new_batch', runtime_module.NAMESPACE == HERE
        and runtime_module.HERE == HERE / 'harness'
        and runtime_module.EXTERNAL.resolve() == Path('D:/he_m5_harness_recovery_001').resolve())
    candidate = ast.parse((OLD / 'recovery_candidate/owned_runtime.py').read_bytes())
    moved = ast.parse((HERE / 'harness/owned_runtime.py').read_bytes())
    helper = lambda tree: next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'correlate_archive')
    check('accepted_correlation_helper_body_unchanged', ast.dump(helper(candidate), include_attributes=False)
        == ast.dump(helper(moved), include_attributes=False))
    check('deadline_uses_original_owned_600_without_450_rule', 'self.consumer_deadline_ns = self.deadline_ns' in
        (HERE / 'harness/owned_runtime.py').read_text(encoding='utf-8'))

    class FakeBudget:
        def __init__(self):
            self.admissions = []

        def reserve(self, kind, label, phase, upper):
            self.admissions.append((kind, label, phase, upper))
            return 'synthetic-admission'

    class Client:
        def __init__(self, root):
            self.root, self.records, self.replies, self.service_index = root, [], [], 0

        def call(self, message):
            number = len(self.records) + 1
            started = time.perf_counter_ns()
            directory = self.root / 'mcp' / ('rpc_' + str(number).zfill(2))
            directory.mkdir(parents=True)
            if number <= 2:
                value = {'status': 'error', 'error': 'synthetic pre-service rejection'}
                is_error = True
            elif number == 3:
                self.service_index += 1
                value = {'status': 'error', 'error': 'synthetic service exception without archive'}
                is_error = True
            else:
                self.service_index += 1
                value = {'status': 'observed' if number == 4 else 'partial', 'result_kind': 'task_query',
                    'binding': {'objects': [{'object_id': 'synthetic-object', 'name': 'Synthetic'}]},
                    'facts': {'surface_proximity': {'status': 'measured', 'synthetic': True}}}
                is_error = False
                path = self.root / 'product_full' / ('call_' + str(self.service_index).zfill(3)) / 'SERVICE_RESULT.json'
                save(path, value)
                entry = {'index': self.service_index, 'started_ns': started,
                    'producer_returned_ns': time.perf_counter_ns(), 'path': str(path), 'sha256': pin(path)['sha256']}
                with (self.root / 'product_full/INDEX.jsonl').open('ab') as stream:
                    stream.write(encoded([entry]))
            response = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'isError': is_error,
                'content': [{'type': 'text', 'text': json.dumps(value)}]}}
            tx, rx = json.dumps(message).encode(), json.dumps(response).encode()
            (directory / 'TX.bin').write_bytes(tx)
            (directory / 'RX.bin').write_bytes(rx)
            closed = time.perf_counter_ns()
            self.records.append({'index': number, 'started_ns': started, 'stdin_flushed_ns': started,
                'received_complete_ns': closed, 'closed_ns': closed, 'TX_bytes': len(tx), 'RX_bytes': len(rx)})
            self.replies.append(response)
            return response

    runtime = runtime_module.RootRuntime()
    runtime.runroot = (output / 'runtime_mock').resolve()
    (runtime.runroot / 'product_full').mkdir(parents=True)
    runtime.deadline_ns = time.perf_counter_ns() + 600_000_000_000
    runtime.consumer_deadline_ns = runtime.deadline_ns
    runtime.native, runtime.poisoned = None, False
    runtime.group, runtime.label = 'A', 'migration-pure'
    runtime.binding = {'source_sha256': runtime_module.PRODUCT_SHA256['A']}
    runtime._product_calls, runtime.public_requests, runtime.source_reads = 0, [], []
    runtime.buffers, runtime.by_ref = {}, {}
    runtime.cameras = {'views': []}
    runtime.product_tools = [json.loads((HERE / 'public_schema/A_scene_observe.json').read_bytes())]
    runtime.budget = FakeBudget()
    runtime.client = Client(runtime.runroot)
    owner = bridge.Owner(runtime, {'group': 'A', 'label': 'migration-pure', 'phase': 'qualification',
        'worker_deadline_ns': runtime.deadline_ns, 'output': str(output / 'owner')})
    invalid = {'mode': 'task', 'target': {'name': 'Synthetic'}, 'candidates': [{'name': 'Other'}],
        'requested_facts': ['surface_proximity']}
    valid = {'mode': 'task', 'objects': [{'name': 'Synthetic'}, {'name': 'Other'}],
        'requested_facts': ['surface_proximity']}
    code1 = 'import json\nvalues=[]\nflags=[]\n'
    for query in (invalid, invalid, valid):
        code1 += 'values.append(task(' + repr(query) + '))\nflags.append(last_product_is_error)\n'
    code1 += 'print(json.dumps({"values":values,"flags":flags}))'
    codes = [code1,
        'value=task(' + repr(valid) + ')\nprint(json.dumps({"value":value,"flag":last_product_is_error}))',
        'value=task(' + repr(dict(valid, requested_facts=['surface_proximity', 'closed_solid_relation']))
        + ')\nprint(json.dumps({"value":value,"flag":last_product_is_error}))']
    delivered = []
    for number, code in enumerate(codes, 1):
        reply = owner.call({'jsonrpc': '2.0', 'id': number, 'method': 'tools/call',
            'params': {'name': 'execute_python', 'arguments': {'code': code}}})
        wrapper = json.loads(reply['result']['content'][0]['text'])
        delivered.append(json.loads(wrapper['stdout']))
        check('ordinary_Owner_Python_no_binding_error_' + str(number), wrapper['error'] is None)
    check('consecutive_rejections_and_service_exception_preserve_flags', delivered[0]['flags'] == [True, True, True])
    check('following_observed_and_partial_reach_outer_interface', [row['value']['status'] for row in delivered[1:]] == ['observed', 'partial']
        and all(row['flag'] is False for row in delivered[1:]))
    check('independent_public_and_gapped_service_indices',
        [row['internal_public_call_index'] for row in runtime.public_requests] == [1, 2, 3, 4, 5]
        and [row['producer_archive_index'] for row in runtime.public_requests] == [None, None, None, 2, 3])
    check('all_API_arguments_use_new_session_identifier', all(row['request']['params']['arguments']['session_id']
        == 'm5-harness-recovery-001' for row in runtime.public_requests))
    check('each_outer_call_admitted_once_despite_inner_batch', len(runtime.budget.admissions) == 3
        and owner.tools[0]['internal_public_call_indices'] == [1, 2, 3])
    check('successful_public_values_match_exact_internal_reply', delivered[1]['value']
        == json.loads(runtime.client.replies[3]['result']['content'][0]['text']) and delivered[2]['value']
        == json.loads(runtime.client.replies[4]['result']['content'][0]['text']))
    owner.calls = 12
    reply = owner.call({'jsonrpc': '2.0', 'id': 13, 'method': 'tools/call',
        'params': {'name': 'execute_python', 'arguments': {'code': 'print("scope migration")'}}})
    check('removed_old_model_twelve_outer_gate', reply['result']['isError'] is False and owner.calls == 13)
    check('server_identity_is_new_batch', owner.handle({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize'})
        ['result']['serverInfo']['name'] == 'm5-harness-recovery-001')

    root = runtime.runroot / 'product_full'
    old_entry = {'index': 2, 'started_ns': 10, 'producer_returned_ns': 20,
        'path': str(root / 'call_002/SERVICE_RESULT.json'), 'sha256': pin(root / 'call_002/SERVICE_RESULT.json')['sha256']}
    new_entry = {'index': 3, 'started_ns': 120, 'producer_returned_ns': 160,
        'path': str(root / 'call_003/SERVICE_RESULT.json'), 'sha256': pin(root / 'call_003/SERVICE_RESULT.json')['sha256']}
    for name, before, after, reason in (
        ('missing_success_record', b'', b'', 'same_producer_archive_missing'),
        ('multiple_new_records', b'', encoded([old_entry, new_entry]), 'same_producer_archive_multiple_new_entries'),
        ('changed_prefix', encoded([old_entry]), encoded([dict(old_entry, started_ns=11), new_entry]), 'same_producer_archive_prefix_changed'),
        ('cross_request_window', b'', encoded([dict(new_entry, started_ns=99)]), 'same_producer_archive_cross_request_window'),
        ('cross_slot_path', b'', encoded([dict(new_entry, path=str(output / 'other_slot/call_003/SERVICE_RESULT.json'))]), 'same_producer_archive_cross_slot_path'),
        ('changed_content_hash', b'', encoded([dict(new_entry, sha256='0' * 64)]), 'same_producer_archive_content_changed'),
    ):
        try:
            runtime_module.correlate_archive(before, after, 100, 200, False, root)
        except ValueError as error:
            check('new_root_reject_' + name, str(error) == reason)
        else:
            check('new_root_reject_' + name, False)
    budget = runtime_module.Budget(output / 'synthetic_budget')
    for _ in range(2):
        budget.reserve('Blender_start', 'synthetic', 'qualification')
    for _ in range(12):
        budget.reserve('raster_attempt', 'synthetic', 'qualification')
    for _ in range(13):
        budget.reserve('business_tool', 'synthetic', 'qualification')
    check('new_quota_has_no_old_per_slot_six_or_twelve_model_caps', budget.snapshot()['counts']['all_raster_upper'] == 12)
    for kind, reason in (('Blender_start', 'Blender_start_budget_exhausted'),
                         ('raster_attempt', 'recovery_total_raster_budget_exhausted'),
                         ('consumer_task', 'recovery_model_consumers_forbidden')):
        try:
            budget.reserve(kind, 'synthetic', 'formal')
        except RuntimeError as error:
            check('new_budget_' + kind, str(error) == reason)
        else:
            check('new_budget_' + kind, False)
    check('no_actual_execution_events', events == [])
    check('runtime_and_budget_sources_stable', runtime_before == pin(HERE / 'harness/owned_runtime.py')
        and budget_before == pin(HERE / 'harness/budget.py'))
    report = {'schema': 'm5-recovery-directed-migration-pure-v1',
        'passed_checked_scope': all(row['passed'] for row in checks), 'checks': checks,
        'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'input_pins': [pin(HERE / name) for name in ('bridge.py', 'native_tools.py', 'bootstrap.py',
            'native_consumer_audit.py', 'harness/owned_runtime.py', 'harness/budget.py', 'migration_pure_checks.py')],
        'historical_reference_only': [pin(OLD / 'recovery_candidate/PURE_01/RESULT.json'),
            pin(OLD / 'CANDIDATE_INDEPENDENT_REVIEW.json')],
        'scope': 'Only new context, changed deadlines/quotas, consecutive rejection and service-index gap through the normal Owner/Python API with a fake MCP client, plus six path/source counterexamples. Old matrices and old manifest members are not rerun.',
        'synthetic_reservation_scope': 'Unit budget files under MIGRATION_PURE_01 are synthetic admissions only. They create no Blender, raster or model. Actual trial budget remains solely in the new D runtime.',
        'author_association': 'Reviewer authored shared bridge migration and these controls. Another agent authored the harness candidate and runtime/budget migration. Root alone executes the actual A/B sessions.',
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'rasters': 0, 'models': 0, 'paid_APIs': 0}}
    save(HERE / 'MIGRATION_PURE.json', report)
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(checks),
        'failed': [row['name'] for row in checks if not row['passed']]}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
