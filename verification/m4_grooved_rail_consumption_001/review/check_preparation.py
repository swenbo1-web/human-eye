"""Independent frozen preparation checks using saved inputs and mocked owners."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
OLD = ROOT / 'verification/m4_spatial_fact_consumption_001'
CYCLE = 'M4-GROOVED-RAIL-TRANSFER-001'
checks = {}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, value):
    checks[name] = bool(value)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rejected(operation):
    try:
        operation()
    except (AssertionError, ValueError):
        return True
    return False


def main():
    plan = read(BATCH / 'PLAN.json')
    freeze = read(BATCH / 'FREEZE.json')
    go = read(BATCH / 'GO.json')
    digest = sha(BATCH / 'PLAN.json')
    check('same_frozen_PLAN_FREEZE_GO', digest == freeze['plan_sha256'] == go['plan_sha256'])
    check('expected_current_plan_digest', digest == '6229c8b4eec4340ccb2dd11bef4ba45db3a65b4e5cac82d70e4c6254c920e4aa')
    check('new_cycle_and_six_direct_authorized_slots', plan['cycle_id'] == plan['batch'] == go['task'] == CYCLE
          and freeze['cycle_id'] == CYCLE and go['authorized'] is True and go['max_consumers'] == freeze['authorized_consumers'] == 6)
    check('all_dispatch_file_hashes', all(sha(BATCH / name) == value for name, value in plan['dispatch_input_sha256'].items()))
    check('all_external_file_hashes', all(sha(Path(name)) == value for name, value in plan['external_input_sha256'].items()))
    check('independent_identity_check_passed', read(HERE / 'INPUT_IDENTITY.json')['passed']
          and read(HERE / 'INPUT_IDENTITY.json')['reviewer_source_sha256'] == sha(HERE / 'check_identity.py'))
    check('protected_sources_and_qualification_files_stable', all(sha(Path(name)) == value
          for name, value in read(BATCH / 'preflight/PROTECTED_BEFORE.json').items()))
    binding = read(BATCH / 'preflight/SOURCE_BINDING.json')
    ready = read(BATCH / 'installations/P_READY.json')
    check('same_137_source_and_install_files', len(binding['source_manifest']) == 137 and all(
        sha(ROOT / row['path']) == sha(Path(ready['install_root']) / row['path']) == row['sha256'] for row in binding['source_manifest']))
    check('product_and_installation_identity', plan['fixed_product_commit'] == ready['commit'] == 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
          and plan['candidate_source_sha256'] == ready['source_sha256'] == '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
          and plan['installation_ready'] == plan['installations']['P'] == ready)
    check('asset_snapshot_truth_bindings', plan['inputs']['scene_sha256'] == '49c0dccb233181a97d6d1508cc2570c03c961dffd2f8c8ef4ba12ebae3f9ec67'
          and sha(BATCH / 'scoring/ACTUAL_SNAPSHOT.json') == '6bb073b9aa29e7eecc5aa74ad2330cbb8fb5c5e06c79e70bf71091a33470ff52'
          and sha(BATCH / 'scoring/TRUTH.json') == '2d072197f67f2d9860cb2ceb86c2782a7d4d2c3a71f1ed6d8be2487afc0eaa74')
    check('zero_image_contract', plan['image_count'] == plan['new_images'] == plan['tool_images'] == 0
          and plan['inputs']['image'] is None and plan['inputs']['image_bytes'] == 0 and plan['inputs']['image_sha256'] is None)
    expected_budgets = {'max_session_seconds': 450, 'total_cell_seconds': 570, 'actor_startup_seconds': 40,
                       'tool_attempts': 32, 'physical_RPC_limit': 128, 'tool_timeout_s': 30,
                       'tool_response_bytes': 1048576, 'code_bytes': 262144}
    check('original_budgets', all(plan[key] == value for key, value in expected_budgets.items()))
    sequence = plan['sequence']
    check('fixed_six_slot_sequence', len(sequence) == len({row['cell'] for row in sequence}) == 6
          and [row['group'] for row in sequence] == ['N', 'P', 'P', 'N', 'N', 'P']
          and [row['round'] for row in sequence] == [1, 1, 2, 2, 3, 3]
          and {row['task'] for row in sequence} == {'T1'})
    mapping = read(BATCH / 'private/ANON_MAP.json')
    check('six_pre_frozen_anonymous_slots', mapping['created_before_consumers'] is True
          and len(mapping['rows']) == len({row['anonymous_id'] for row in mapping['rows']}) == 6
          and {row['cell']: {k: row[k] for k in ('group', 'round', 'task')} for row in mapping['rows']}
          == {row['cell']: {k: row[k] for k in ('group', 'round', 'task')} for row in sequence}
          and sha(BATCH / 'private/ANON_MAP.json') == plan['private_anonymous_map_sha256'])
    check('no_formal_dispatch_in_preparation', not (BATCH / 'STARTED.json').exists() and not (BATCH / 'RUN_RESULT.json').exists())

    def source(name, old=False):
        return ((OLD if old else BATCH) / 'runtime' / name).read_text(encoding='utf8')

    check('actor_byte_identical', (BATCH / 'runtime/actor.py').read_bytes() == (OLD / 'runtime/actor.py').read_bytes())
    check('transport_single_workspace_replacement', source('consumer_transport.py') == source('consumer_transport.py', True).replace(
        '.m4_spatial_fact_consumption_001_runtime/work', '.m4_grooved_rail_consumption_001_runtime/work'))
    check('driver_only_cycle_and_slot_prefix_changed', source('driver.py') == source('driver.py', True).replace(
        "CYCLE='M4-SPATIAL-FACT-CONSUMPTION-001'", "CYCLE='M4-GROOVED-RAIL-TRANSFER-001'").replace("['spc'+str(index)", "['grc'+str(index)"))
    check('run_wrapper_only_private_module_label_changed', source('run_formal.py') == source('run_formal.py', True).replace(
        '_spatial_fact_formal_driver', '_grooved_rail_formal_driver'))
    check('packer_only_cycle_changed', source('pack_quality.py') == source('pack_quality.py', True).replace(
        'M4-SPATIAL-FACT-CONSUMPTION-001', CYCLE))
    actor = source('actor.py')
    check('ordinary_serve_full_response_and_owned_runtime_proof', "'serve','--config'" in actor
          and '--spatial-task-only' not in actor and 'result=answer.get(' in actor
          and 'runtime._windows_runtime_proof(' in actor and 'runtime._runtime_exit(self.runtime_handle)' in actor)
    driver = load('_grooved_independent_driver', BATCH / 'runtime/driver.py')
    transport = load('_grooved_independent_transport', BATCH / 'runtime/consumer_transport.py')
    old_transport = load('_grooved_previous_transport', OLD / 'runtime/consumer_transport.py')
    driver.verify_frozen_inputs(plan)
    driver.go_contract(go, plan, digest)
    check('driver_live_input_and_go_functions_pass', True)
    bad_go = copy.deepcopy(go)
    bad_go['task'] = 'M4-SPATIAL-FACT-CONSUMPTION-001'
    check('old_cycle_authority_rejected', rejected(lambda: driver.go_contract(bad_go, plan, digest)))
    bad_plan = copy.deepcopy(plan)
    bad_plan['sequence'][1]['cell'] = bad_plan['sequence'][0]['cell']
    check('duplicate_slot_rejected', rejected(lambda: driver.go_contract(go, bad_plan, digest)))
    bad_plan = copy.deepcopy(plan)
    bad_plan['sequence'][0]['group'] = 'P'
    check('changed_order_rejected', rejected(lambda: driver.go_contract(go, bad_plan, digest)))
    bad_go = copy.deepcopy(go)
    bad_go['max_consumers'] = 7
    check('expanded_sampling_rejected', rejected(lambda: driver.go_contract(bad_go, plan, digest)))
    snapshot = read(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')
    actual = {'unit_scale_m': snapshot['unit_scale_m'], 'objects': [
        {key: row[key] for key in ('name', 'vertices_local', 'matrix_world', 'faces')} for row in snapshot['objects']]}
    driver.snapshot_binding(actual, snapshot)
    check('actual_qualification_snapshot_normalizes_without_rewrite', True)
    for label, mutate in (
        ('unit', lambda data: data.update(unit_scale_m=0.001)),
        ('coordinate', lambda data: data['objects'][0]['vertices_local'][0].__setitem__(0, 999.0)),
        ('name', lambda data: data['objects'][0].update(name='WrongPart')),
        ('faces', lambda data: data['objects'][0]['faces'][0].reverse()),
    ):
        changed = copy.deepcopy(actual)
        mutate(changed)
        check('changed_snapshot_' + label + '_rejected', rejected(lambda: driver.snapshot_binding(changed, snapshot)))
    positives = ('quota exceeded', 'usage limit reached', 'rate limit reached', 'HTTP 429', 'HTTP/1.1 503', 'status code: 429', 'error code=503')
    negatives = ('pid 429', 'port 503', 'hash_ab429c', '429', '503')
    check('provider_explicit_failures_stop', all(driver.provider_unavailable(text) for text in positives))
    check('incidental_numbers_do_not_stop', not any(driver.provider_unavailable(text) for text in negatives))

    class FakeInput:
        def __init__(self, error):
            self.error = error
            self.closed = False

        def write(self, value):
            if self.error:
                raise BrokenPipeError('synthetic_pipe_failure')

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self, error):
            self.stdin = FakeInput(error)
            self.pid = -100
            self.returncode = None
            self.waits = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.waits += 1
            self.returncode = 0

    saved = []
    driver.save = lambda path, value: saved.append(value)
    for error in (False, True):
        fake = FakeProcess(error)
        result = driver.finish(HERE / 'uncreated_mock_owner', fake)
        check('mocked_finish_' + ('broken_pipe' if error else 'normal') + '_waits_and_closes',
              fake.stdin.closed and fake.waits == 1 and result['exit_code'] == 0
              and (result['finish_signal_error'] is not None) == error)
    check('settings_equal_previous_accepted_configuration', transport.settings() == old_transport.settings())
    check('zero_image_metadata', transport.initial_image_metadata(plan)['count'] == 0)
    check('fresh_empty_consumer_workspaces', all(not (ROOT / '.m4_grooved_rail_consumption_001_runtime/work' / row['cell']).exists()
          or not list((ROOT / '.m4_grooved_rail_consumption_001_runtime/work' / row['cell']).iterdir()) for row in sequence))
    argv = read(BATCH / 'preflight/CLI_ARGV.json')['argv_by_group']
    for group in ('N', 'P'):
        parts = argv[group]
        options = [parts[i + 1] for i, value in enumerate(parts) if value == '-c']
        parsed = tomllib.loads('\n'.join(options))
        allowed = {'execute_blender_code'} | ({'human_eye_scene_observe'} if group == 'P' else set())
        check(group + '_preauthorization_exact_names', set(parsed['mcp_servers']['arm_engine']['tools']) == allowed
              and all(item['approval_mode'] == 'approve' for item in parsed['mcp_servers']['arm_engine']['tools'].values()))
        check(group + '_CLI_text_only_and_fresh_configuration', '--image' not in parts and '-m' in parts
              and parts[parts.index('-m') + 1] == 'gpt-6.1-sol'
              and all(flag in parts for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config')))
    native_tree = ast.parse((ROOT / 'verification/native_plugin_complex_003/actor.py').read_bytes())
    native = ast.literal_eval(next(node.value for node in native_tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'NATIVE' for target in node.targets)))
    observe = read(BATCH / 'schemas/P_PUBLIC_TOOLS.json')
    check('common_native_and_full_observe_declarations', read(BATCH / 'schemas/COMMON_NATIVE.json') == native
          and read(BATCH / 'schemas/N_CONSUMER_TOOLS.json') == [native]
          and read(BATCH / 'schemas/P_CONSUMER_TOOLS.json') == [native, *observe]
          and observe == read(OLD / 'schemas/P_PUBLIC_TOOLS.json'))
    score = read(BATCH / 'scoring/SCORING_CONTRACT.json')
    old_score = read(OLD / 'scoring/SCORING_CONTRACT.json')
    preserved = ('primary_fixed_denominators', 'complete_correct', 'status_categories', 'distance_policy',
                 'witness_policy', 'evidence_policy', 'language_policy', 'fixed_sample_policy',
                 'anonymization_policy', 'administrative_projection_policy', 'quality_before_cost')
    check('same_quality_scoring_and_anonymity_policies', all(score[key] == old_score[key] for key in preserved))
    check('new_scoring_materials_and_candidates', score['cycle_id'] == CYCLE
          and score['input_materials']['candidate_scope'] == ['Part_A', 'Part_B', 'Part_C']
          and score['input_materials']['actual_snapshot_sha256'] == sha(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')
          and score['input_materials']['independent_truth_sha256'] == sha(BATCH / 'scoring/TRUTH.json'))
    bridge = read(BATCH / 'runtime/BRIDGE_REUSE.json')
    check('bridge_synthetic_methods_and_zero_start_checks', bridge['synthetic_checks']['passed']
          and bridge['zero_start_checks']['passed'] and bridge['real_process_launches'] == bridge['model_calls'] == bridge['product_launches'] == bridge['Blender_sessions'] == 0)
    quality = read(BATCH / 'quality/synthetic_01/RESULTS.json')
    check('anonymous_packager_synthetic_checks', all(row['passed'] for row in quality['checks']))
    check('hashes_stable_at_review_end', all(sha(BATCH / name) == value for name, value in plan['dispatch_input_sha256'].items())
          and all(sha(Path(name)) == value for name, value in plan['external_input_sha256'].items()))

    output = {'passed': all(checks.values()), 'checks': checks,
              'failed_checks': [name for name, value in checks.items() if not value],
              'plan_sha256': digest, 'dispatch_files_verified': len(plan['dispatch_input_sha256']),
              'external_files_verified': len(plan['external_input_sha256']), 'source_count': 137,
              'model_consumers': 0, 'Blender_sessions': 0, 'product_runs': 0,
              'real_CLI_launches': 0, 'mocked_owner_finish_cases': 2,
              'scope': 'Saved-file, exact-reuse, pure-function and mocked-owner checks. Existing native Python audit and image observation boundaries retain their registered scope.',
              'review_source_sha256': sha(Path(__file__))}
    with (HERE / 'FINAL_STATIC_CHECK.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': output['passed'], 'checks': len(checks), 'failed': output['failed_checks'],
                      'dispatch': output['dispatch_files_verified'], 'external': output['external_files_verified']}))


if __name__ == '__main__':
    main()
