"""Verify the frozen preparation using file reads and pure QA contracts."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
EXPECTED_PLAN = '005fdb5fccbd8a0aff8b28b9159da488a6d00e050438a7ea1fa908a68bbe460a'


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    plan = read(BATCH / 'PLAN.json')
    freeze = read(BATCH / 'FREEZE.json')
    go = read(BATCH / 'GO.json')
    assert digest(BATCH / 'PLAN.json') == EXPECTED_PLAN == freeze['plan_sha256'] == go['plan_sha256']
    assert freeze['root_plan_sha256'] == digest(BATCH / 'ROOT_PLAN.md') == plan['root_plan_sha256']
    assert freeze['authorized_consumers'] == 6 and freeze['formal_authorized'] is True
    assert freeze['initial_images'] == freeze['new_images'] == 0
    assert freeze['source_count'] == plan['source_count'] == 137
    assert freeze['product_commit'] == plan['fixed_product_commit']
    assert freeze['source_sha256'] == plan['candidate_source_sha256']
    assert freeze['anonymous_map_sha256'] == plan['private_anonymous_map_sha256']
    driver = load('_review_final_driver', BATCH / 'runtime/driver.py')
    driver.go_contract(go, plan, EXPECTED_PLAN)
    driver.verify_frozen_inputs(plan)
    assert digest(BATCH / 'runtime/driver.py') == plan['preflight_driver_sha256']
    assert digest(BATCH / 'runtime/actor.py') == plan['actor_sha256']
    assert digest(BATCH / 'runtime/consumer_transport.py') == plan['consumer_transport_sha256']
    assert digest(BATCH / 'runtime/pack_quality.py') == plan['quality_handoff_script_sha256']
    budgets = {'max_session_seconds': 450, 'total_cell_seconds': 570, 'actor_startup_seconds': 40,
               'tool_attempts': 32, 'physical_RPC_limit': 128, 'tool_timeout_s': 30,
               'tool_response_bytes': 1048576, 'code_bytes': 262144}
    assert all(plan[key] == value for key, value in budgets.items())
    previous = ROOT / 'verification/m3_sufficient_separation_001/entry/run_01'
    assert digest(previous / 'native/input.blend') == digest(BATCH / plan['inputs']['scene'])
    assert digest(previous / 'ACTUAL_SNAPSHOT.json') == digest(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')
    listed = read(previous / 'TOOLS.json')['result']['tools']
    observe = [tool for tool in listed if tool['name'] == 'human_eye_scene_observe']
    assert read(BATCH / 'schemas/P_PUBLIC_TOOLS.json') == observe and len(observe) == 1
    base = ROOT / 'verification/native_plugin_complex_003/actor.py'
    tree = ast.parse(base.read_bytes())
    native = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'NATIVE' for target in node.targets)))
    assert read(BATCH / 'schemas/COMMON_NATIVE.json') == native
    assert read(BATCH / 'schemas/N_CONSUMER_TOOLS.json') == [native]
    assert read(BATCH / 'schemas/P_CONSUMER_TOOLS.json') == [native, observe[0]]
    transport = load('_review_final_transport', BATCH / 'runtime/consumer_transport.py')
    assert str(Path(transport.EXE).resolve()) in plan['external_input_sha256']
    assert digest(Path(transport.EXE)) == plan['CLI_sha256']
    configuration = read(BATCH / 'preflight/CONSUMER_CONFIGURATION.json')
    assert configuration['settings'] == transport.settings()
    assert configuration['initial_image'] == transport.initial_image_metadata(plan)
    assert configuration['tools_by_group'] == {key: sorted(value) for key, value in transport.TOOLS_BY_GROUP.items()}
    argv_record = read(BATCH / 'preflight/CLI_ARGV.json')
    for group, argv in argv_record['by_group'].items():
        assert all(flag in argv for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config'))
        assert '--image' not in argv
        configs = [tomllib.loads(argv[index + 1]) for index, value in enumerate(argv) if value == '-c']
        server = next(value['mcp_servers']['arm_engine'] for value in configs if 'mcp_servers' in value)
        assert set(server['tools']) == transport.TOOLS_BY_GROUP[group]
        assert all(value['approval_mode'] == 'approve' for value in server['tools'].values())
    prepared = read(BATCH / 'runtime/PREPARED_INPUT.json')
    assert prepared['initial_image'] == configuration['initial_image']
    assert prepared['prompt_sha256'] == plan['inputs']['prompt_sha256']
    assert prepared['model_consumers'] == prepared['tool_images'] == prepared['new_images'] == 0
    for item in plan['quality_materials']:
        assert digest(BATCH / item['path']) == item['sha256']
    result = {'passed': True, 'plan_sha256': EXPECTED_PLAN,
              'dispatch_files_verified': len(plan['dispatch_input_sha256']),
              'external_files_verified': len(plan['external_input_sha256']),
              'source_count': 137, 'six_slot_zero_image_contract': True,
              'full_ordinary_observe_schema_preserved': True,
              'common_native_schema_preserved': True, 'preauthorization_names_match': True,
              'actual_subprocesses': 0, 'model_calls': 0, 'Blender_sessions': 0,
              'review_source_sha256': digest(Path(__file__))}
    with (HERE / 'FINAL_STATIC_CHECK.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
