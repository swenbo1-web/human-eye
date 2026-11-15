"""Offline bridge, exact historical Python and fair batching regression."""

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
CHECKS = []


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pin(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def check(name, condition, detail=None):
    CHECKS.append({'name': name, 'passed': bool(condition), 'detail': detail})


class FakeBudget:
    def __init__(self):
        self.calls = []

    def reserve(self, kind, label, phase, upper):
        self.calls.append((kind, label, phase, upper))
        return 'synthetic-budget'


class FakeRuntime:
    def __init__(self, group):
        import numpy as np
        self.group = group
        self.budget = FakeBudget()
        self.public_requests = []
        self.product_tools = [json.loads((HERE / 'public_schema' / (group + '_scene_observe.json')).read_bytes())]
        self.cameras = {'views': [{'name': 'SCENE', 'size_px': [512, 512]}]}
        self.buffers = {'native-image-002': {'color': np.zeros((2, 2, 3), dtype=np.uint8),
            'depth': np.ones((2, 2)), 'owners': np.zeros((2, 2), dtype=np.int32)}}
        self.geometry_reads = 0
        self.original_public_values = []

    def public_request(self, arguments):
        value = {'result_kind': 'task_query', 'source_ref': 'synthetic-current', 'synthetic_scalar': 7}
        if arguments['query']['mode'] == 'active_observation':
            value = {'result_kind': 'active_observation', 'source_ref': 'synthetic-current', 'synthetic_observation': True}
            if 'task_query' in arguments['query']:
                value['task_result'] = {'result_kind': 'task_query', 'source_ref': 'synthetic-current', 'synthetic_scalar': 7}
        self.original_public_values.append(copy.deepcopy(value))
        content = [{'type': 'text', 'text': json.dumps(value)}]
        if arguments.get('include_image', True):
            # Fixed synthetic transport payload. No scene image is constructed.
            content.append({'type': 'image', 'mimeType': 'image/png',
                'data': base64.b64encode(b'synthetic-png-transport').decode()})
        rid = 'synthetic-public-' + str(len(self.public_requests) + 1)
        self.public_requests.append({'id': rid, 'arguments': copy.deepcopy(arguments)})
        return {'jsonrpc': '2.0', 'id': rid, 'result': {'isError': False, 'content': content}}

    def scene_data(self, selectors=None):
        self.geometry_reads += 1
        return {'objects': [], 'source_ref': 'synthetic-current'}


def main():
    bootstrap = load('_m5_pure_bootstrap', HERE / 'bootstrap.py')
    bootstrap.prepare_dependencies()
    bridge = load('_m5_pure_bridge', HERE / 'bridge.py')
    output = HERE / 'bridge_pure_01'
    output.mkdir(exist_ok=False)
    pair = {'mode': 'task', 'objects': [{'name': 'FixtureA'}, {'name': 'FixtureB'}],
            'requested_facts': ['surface_proximity']}
    observations = {'mode': 'active_observation', 'objects': [{'name': 'FixtureA'}]}
    owners = {}
    for group in ('A', 'B'):
        runtime = FakeRuntime(group)
        owner = bridge.Owner(runtime, {'group': group, 'label': group + 'synthetic', 'phase': 'qualification',
            'worker_deadline_ns': time.perf_counter_ns() + 30_000_000_000, 'output': str(output / group)})
        owners[group] = owner
        check(group + '_no_geometry_prefetch', runtime.geometry_reads == 0)
        if group == 'A':
            code = 'observation = observe(' + repr(observations) + ')\nmeasurement = task(' + repr(pair) + ')\nprint(observation)\nprint(measurement)'
        else:
            joint = dict(observations, task_query=pair)
            code = 'observation = observe(' + repr(joint) + ')\nmeasurement = observation["task_result"]\nprint(observation)'
        reply = owner.call({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'execute_python', 'arguments': {'code': code}}})
        expected = 2 if group == 'A' else 1
        check(group + '_one_outer_business_admission', runtime.budget.calls == [('business_tool', group + 'synthetic', 'qualification', 1)])
        check(group + '_actual_internal_call_count', len(runtime.public_requests) == expected)
        check(group + '_same_outer_image_delivery', sum(item['type'] == 'image' for item in reply['result']['content']) == 1)
        check(group + '_ordinary_execution_success', reply['result']['isError'] is False)
        check(group + '_original_public_JSON_preserved', owner.session.namespace['observation'] == runtime.original_public_values[0]
            and (group != 'A' or owner.session.namespace['measurement'] == runtime.original_public_values[1]))
        check(group + '_outer_to_internal_indices', owner.tools[-1]['internal_public_call_indices'] == list(range(1, expected + 1))
            and owner.tools[-1]['internal_public_call_range'] == {'index_base': 0, 'start_inclusive': 0, 'end_exclusive': expected})
        check(group + '_schema_exact_installed_snapshot', bridge.public_tools(group)[-1] == runtime.product_tools[0])
    session = owners['A'].session
    check('A_batch_keeps_observation_and_task_last_values_separate',
        json.loads(session.namespace['last_observation_json']) == session.namespace['observation']
        and json.loads(session.namespace['last_task_json']) == session.namespace['measurement'])
    check('B_joint_keeps_last_observation_as_joint_result',
        json.loads(owners['B'].session.namespace['last_observation_json']) == owners['B'].session.namespace['observation'])
    session.execute('retained_variable = 42')
    continued = session.execute('print(retained_variable)')
    check('ordinary_variables_persist', continued['error'] is None and continued['stdout'].strip() == '42')
    common = session.execute('from fractions import Fraction\nfrom shapely.geometry import Point\nprint(float(np.linalg.norm([3,4])), Fraction(1,2), Point(0,0).buffer(1).area > 3)')
    check('ordinary_numpy_Fraction_Shapely_supported', common['error'] is None)
    historical = (HERE / 'fixtures/ORIGINAL_N3_TYPE_NAME.py.txt').read_text(encoding='utf-8')
    old = load('_m5_old_python_guard_only', HERE.with_name('m4_target_task_consumption_001') / 'native_tools.py')
    try:
        old.validate_code(historical)
    except PermissionError as error:
        check('original_N3_code_reproduces_old_guard_failure', str(error) == 'consumer_private_attribute:__name__')
    else:
        check('original_N3_code_reproduces_old_guard_failure', False)
    session.namespace['data'] = {'objects': [{'name': 'Synthetic', 'vertices': [[0., 0., 0.], [1., 2., 3.]]}]}
    replay = session.execute(historical)
    check('unchanged_original_N3_code_executes_offline', replay['error'] is None and 'ndarray' in replay['stdout'], replay)
    check('dynamic_type_name_getattr_is_harmless', session.execute('print(getattr(type(np.zeros(1)), "__name__"))')['error'] is None)
    for code in ('print(observe.__globals__)', 'print(type(observe).__mro__)',
                 'print(getattr(observe,"__self__"))', 'import sys', 'import human_eye_plugin',
                 'print(np.__dict__)', 'print(type(observe).__name__.__class__)',
                 'open("D:/private_answers/TRUTH.json").read()'):
        rejected = session.execute(code)
        check('private_input_or_reflection_rejected_' + str(len(CHECKS)),
            rejected['error'] is not None and rejected['error']['type'] == 'PermissionError')
    native = load('_m5_native_guard_builder', HERE / 'native_consumer_audit.py')
    generated = native.installation_script(output / 'scratch', output / 'input.blend', output / 'product')
    check('native_Blender_guard_uses_same_type_name_fix', 'node.attr == "__name__"' in generated)
    compile(generated, '<synthetic-native-audit-install>', 'exec')
    check('native_audit_installation_compiles_without_Blender', True)
    launcher = load('_m5_pure_launcher', HERE / 'launcher.py')
    for group in ('A', 'B'):
        prompt = launcher.common_prompt(group)
        check(group + '_launcher_uses_fixed_exact_prompt', prompt == (HERE / 'inputs' / ('PROMPT_' + group + '.txt')).read_bytes())
        check(group + '_prompt_contains_exact_common_task_and_schema', (HERE / 'inputs/COMMON_TASK.txt').read_bytes() in prompt
            and (HERE / 'inputs/ANSWER_SCHEMA.json').read_bytes() in prompt)
    _, proof = launcher.consumer_adapter()
    check('accepted_CLI_event_loop_and_archive_reused', proof['event_loop_code_reused'] and proof['unified_archive_reused'])
    check('fixed_CLI_profile', (proof['model'], proof['reasoning_effort'], proof['service_tier']) == ('gpt-6.1-sol', 'medium', 'default'))
    check('adapter_creation_does_not_launch_model', proof['model_calls_during_adapter_creation'] == 0)
    for owner in owners.values():
        check(owner.group + '_unstarted_listener_closes_normally', owner.close()['confirmed'])
    report = {'schema': 'm5-task-bridge-pure-v1', 'passed_checked_scope': all(row['passed'] for row in CHECKS),
        'check_count': len(CHECKS), 'passed_count': sum(row['passed'] for row in CHECKS), 'checks': CHECKS,
        'source_pins': [pin(HERE / name) for name in ('bridge.py', 'native_tools.py', 'bootstrap.py',
            'native_consumer_audit.py', 'launcher.py', 'prepare_bridge.py', 'bridge_pure_checks.py')],
        'original_N3_provenance': pin(HERE / 'fixtures/ORIGINAL_N3_PROVENANCE.json'),
        'CLI_adapter_proof': proof, 'limitations': ['Fake runtime and synthetic transport image payload only. Live same-producer PNG, source and public schema equality require root qualification.'],
        'author_association': 'Author implemented the thin bridge adaptation and these pure checks. Independent actual qualification and grading belong to root and other agents.',
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'scene_rasters': 0, 'model_consumers': 0}}
    with (HERE / 'BRIDGE_PURE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(CHECKS),
        'failed': [row['name'] for row in CHECKS if not row['passed']]}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
