"""Minimal independent runtime reuse / in-memory GO check, no runtime launch."""
import ast
from contextlib import ExitStack
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = WT / 'verification/m4_selected_geometry_consumption_001'
OLD = WT / 'verification/m4_local_relation_consumption_001'
HEAD = '13f3b279f2a57581e3cebd032d64ec9e2bfdb0ae'
PLAN_SHA = 'bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096'
PINS = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    PINS[str(path)] = sha(data)
    return data


def read(path):
    return json.loads(raw(path))


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw(path), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def main():
    initial_head = subprocess.run(['git', '-C', str(WT), 'rev-parse', 'HEAD'], check=True,
                                  stdout=subprocess.PIPE).stdout.decode().strip()
    assert initial_head == HEAD
    plan_raw = raw(BATCH / 'PLAN.json')
    assert sha(plan_raw) == PLAN_SHA
    plan, old_plan = json.loads(plan_raw), read(OLD / 'PLAN.json')
    reuse = read(BATCH / 'runtime/REUSE_BINDINGS.json')
    unchanged = {}
    for name in ('actor.py', 'consumer_transport.py'):
        before, after = raw(OLD / 'runtime' / name), raw(BATCH / 'runtime' / name)
        assert before == after and sha(after) == reuse['files'][name]['current_sha256']
        unchanged[name] = sha(after)
    before, after = raw(OLD / 'runtime/driver.py'), raw(BATCH / 'runtime/driver.py')
    old_tree, new_tree = ast.parse(before), ast.parse(after)
    old_functions = {n.name: n for n in old_tree.body if isinstance(n, ast.FunctionDef)}
    new_functions = {n.name: n for n in new_tree.body if isinstance(n, ast.FunctionDef)}
    assert set(old_functions) == set(new_functions)
    function_equivalence = {name: ast.dump(old_functions[name], include_attributes=False) ==
                                  ast.dump(new_functions[name], include_attributes=False)
                            for name in new_functions}
    assert {name for name, same in function_equivalence.items() if not same} == {
        'arm_runtime', 'go_contract', 'preflight_inputs'}
    assert all(function_equivalence[name] for name in ('prepare', 'finish', 'snapshot_binding', 'run_models'))
    for name, prior_relative in [('driver.py', 'runtime/driver.py'), ('pack_quality.py', 'quality_handoff/pack_quality.py')]:
        previous = raw(OLD / prior_relative).decode()
        current = raw(BATCH / 'runtime' / name).decode()
        saved = raw(BATCH / 'runtime' / (name + '.diff')).decode()
        expected = ''.join(difflib.unified_diff(previous.splitlines(True), current.splitlines(True),
            fromfile=str((OLD / prior_relative).relative_to(WT)), tofile='runtime/' + name))
        assert saved == expected
    backend = WT / reuse['formal_backend']['path']
    backend_raw = raw(backend)
    assert sha(backend_raw) == reuse['formal_backend']['sha256']
    assert b'setprofile' not in backend_raw and b'qa_profile_schedule' not in backend_raw
    for relative, digest in plan['dispatch_input_sha256'].items():
        assert sha(raw(BATCH / relative)) == digest

    common_keys = ('model', 'requested_effort', 'max_session_seconds', 'total_cell_seconds',
        'actor_startup_seconds', 'tool_attempts', 'physical_RPC_limit', 'tool_response_bytes',
        'tool_timeout_s', 'code_bytes', 'image_count', 'new_images', 'tool_images', 'model_retries', 'CLI_sha256')
    assert all(plan[key] == old_plan[key] for key in common_keys)
    common_parameters = {key: plan[key] for key in common_keys}
    for key in ('prompt', 'image', 'scene', 'catalog', 'camera', 'directions'):
        assert raw(BATCH / plan['inputs'][key]) == raw(OLD / old_plan['inputs'][key])

    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append('forbidden process/socket/signal/write')
        raise AssertionError(attempts[-1])
    original_open = Path.open
    def read_only_open(path, mode='r', *args, **kwargs):
        if any(c in mode for c in 'wax+'):
            return forbidden(path, mode)
        return original_open(path, mode, *args, **kwargs)
    assert not (BATCH / 'GO.json').exists() and not (BATCH / 'STARTED.json').exists()
    rejection_records = []
    with ExitStack() as stack:
        for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
            stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
        for name in ('socket', 'create_connection'):
            stack.enter_context(patch.object(socket, name, side_effect=forbidden))
        for name in ('system', 'kill'):
            stack.enter_context(patch.object(os, name, side_effect=forbidden))
        stack.enter_context(patch.object(Path, 'open', read_only_open))
        driver = load(BATCH / 'runtime/driver.py', '_independent_sgc_driver')
        transport = load(BATCH / 'runtime/consumer_transport.py', '_independent_sgc_transport')
        good_go = {'task': driver.CYCLE, 'authorized': True, 'plan_sha256': PLAN_SHA, 'max_consumers': 9}
        driver.go_contract(good_go, plan, PLAN_SHA)
        mappings = []
        for slot in plan['sequence']:
            frozen_slot = copy.deepcopy(slot)
            private, ready, profile = driver.arm_runtime(plan, slot)
            assert slot == frozen_slot
            assert private['external_group'] == slot['group']
            assert private['group'] == ('N' if slot['group'] == 'N' else 'P')
            assert profile == ('G' if slot['group'] == 'G' else 'P')
            assert ready == read(BATCH / 'installations' / (profile + '_READY.json'))
            mappings.append({'slot': slot, 'actor_group': private['group'], 'profile': profile,
                             'source': None if private['group'] == 'N' else ready['source_sha256']})
        old_go = read(OLD / 'GO.json')
        for label, go in [('actual_old_GO', old_go), ('unauthorized', dict(good_go, authorized=False)),
                          ('wrong_PLAN', dict(good_go, plan_sha256='0' * 64)),
                          ('wrong_count', dict(good_go, max_consumers=8))]:
            try:
                driver.go_contract(go, plan, PLAN_SHA)
            except AssertionError as error:
                rejection_records.append({'case': label, 'rejected': True, 'message': str(error)})
            else:
                raise AssertionError('unexpected accepted GO: ' + label)
        wrong = copy.deepcopy(plan)
        wrong['arms']['G']['source_sha256'] = wrong['arms']['P']['source_sha256']
        try:
            driver.go_contract(good_go, wrong, PLAN_SHA)
        except AssertionError as error:
            rejection_records.append({'case': 'G_cross_source_mapping', 'rejected': True, 'message': str(error)})
        else:
            raise AssertionError('cross source accepted')
        # Execute real entry with only read(GO) substituted, to establish ordering.
        entry_reads = []
        def mocked_read(path):
            entry_reads.append(str(path))
            if Path(path) == BATCH / 'GO.json':
                return old_go
            if Path(path) == BATCH / 'PLAN.json':
                return plan
            raise AssertionError('unexpected read before GO rejection')
        with patch.object(driver, 'read', side_effect=mocked_read), patch.object(driver, 'load', side_effect=forbidden):
            try:
                driver.run_models()
            except AssertionError as error:
                assert str(error) == 'wrong_consumption_GO'
            else:
                raise AssertionError('entry accepted historical GO')
        assert entry_reads == [str(BATCH / 'GO.json'), str(BATCH / 'PLAN.json')]
        image = transport.initial_image_metadata(plan)
        assert sha(raw(transport.EXE)) == plan['CLI_sha256']
        settings = transport.settings()
        assert settings['model'] == plan['model'] and settings['model_reasoning_effort'] == plan['requested_effort']
        assert settings['forced_login_method'] == 'chatgpt'
        argvs = {}
        for external, internal in [('N', 'N'), ('P', 'P'), ('G', 'P')]:
            with patch.object(transport, 'read', return_value={'endpoint': 'INERT-NO-PROCESS', 'group': internal}):
                argvs[external] = transport.argv_for(plan['installation_ready']['dependency_python'],
                    HERE / 'inert_cell.json', HERE / 'inert_work', HERE / 'inert_final.txt',
                    initial_image=image['path'])
            assert argvs[external][argvs[external].index('--image') + 1] == image['path']
            assert argvs[external][argvs[external].index('-m') + 1] == plan['model']
        assert argvs['P'] == argvs['G']
        without_tools = lambda argv: [a for a in argv if not a.startswith('mcp_servers.arm_engine=')]
        assert without_tools(argvs['N']) == without_tools(argvs['P'])
        assert not attempts
    assert not (BATCH / 'GO.json').exists() and not (BATCH / 'STARTED.json').exists()
    assert all(sha(Path(name).read_bytes()) == digest for name, digest in PINS.items())
    result = {'passed': True, 'fixed_HEAD': HEAD, 'PLAN_sha256': PLAN_SHA,
        'unchanged_files': unchanged, 'driver_function_AST_equivalence': function_equivalence,
        'minimal_diffs_exact': True, 'dispatch_input_pins': len(plan['dispatch_input_sha256']),
        'mapping_count': len(mappings), 'mappings': mappings, 'common_parameters': common_parameters,
        'same_original_prompt_image_scene_catalog_camera_directions': True,
        'in_memory_current_GO_accepted': True, 'rejections': rejection_records,
        'actual_run_models_old_GO_rejected_before_load_write_or_launch': True,
        'entry_reads_before_rejection': entry_reads,
        'image': image, 'requested_settings': settings, 'inert_argv': argvs,
        'P_and_G_identical_argv_for_same_inert_paths': True,
        'N_argv_diff_only_tool_capability_configuration': True,
        'formal_backend_without_profiler': True, 'external_or_write_attempts': attempts,
        'actual_GO_created': False, 'STARTED_created': False, 'new_consumers': 0,
        'new_Blender_sessions': 0, 'new_product_processes': 0,
        'not_run': ['real current-GO dispatch', 'provider/image acceptance', 'Pro entitlement',
                    'resolved model/effort', 'full zero-start packager suite (separate reviewer)']}
    for name, value in [('RESULTS.json', result), ('INPUT_PINS.json', PINS)]:
        with (HERE / name).open('x', encoding='utf8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
    print(json.dumps({'passed': True, 'mappings': len(mappings), 'GO_rejections': len(rejection_records),
                      'actual_entry_old_GO_rejected': True, 'external_attempts': attempts}))


if __name__ == '__main__':
    main()
