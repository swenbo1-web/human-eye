"""Bounded offline review of the changed 002 entry points and fixed inputs."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
INTERFACE = ROOT / 'verification/m4_surface_scan_continuous_interface_fix_001'
PINNED = {
    'runtime/episode.py': 'e3bef0c338e6f6078e74a64a2b3fd5fc6ea92de0f34ade94410d7b9a10768757',
    'runtime/consumer_transport.py': '675d0d855635a3586fd60f90c73a70d0bf0968e2b8bf193d2446e77fc5849a5f',
    'compatibility.py': 'ad41521eccb2be5e61ca24d37e7e985128267cf959d818a1dd87cd84545d30c4',
}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    checks, sources = [], {}

    def check(name, condition, detail=None):
        checks.append({'check': name, 'passed': bool(condition), 'detail': detail})

    plan = read(BATCH / 'PLAN.json')
    check('new_cycle_and_admin', plan['cycle'] == 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002'
          and plan['admin_commit'] == '79ed3bff7c87d4ac68e2b2bf382de05d41b731c6')
    check('new_root_plan_bytes', sha(BATCH / 'inputs/ROOT_PLAN.md')
          == plan['root_plan_sha256'] == '43d19c8c94c4b4ec66ea5589f7ea64c21686501dab4dcfdc2d35d38a3c13a726')
    check('inherited_plan_bytes', sha(BATCH / 'inputs/INHERITED_PLAN.md')
          == plan['inherited_root_plan_sha256'] == '95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5')
    check('new_six_serial_slots', [row['cell'] for row in plan['sequence']] == ['N1', 'C1', 'C2', 'N2', 'N3', 'C3'])
    check('new_runtime_root', Path(plan['runtime_root']).resolve() == (ROOT / '.m4cc2').resolve())
    check('explicit_provider_gate', plan.get('model_consumer_enabled') is True)
    expected = {'episode_seconds': 590, 'turn_seconds': 450, 'actor_startup_seconds': 40,
                'tool_timeout_seconds': 30, 'episode_tool_attempts': 32,
                'episode_host_nonclose_requests': 128, 'episode_tool_response_bytes': 1048576,
                'code_bytes': 262144, 'image_count': 0, 'new_images': 0}
    check('same_absolute_budgets', all(type(plan.get(key)) is int and plan[key] == value
          for key, value in expected.items()))
    check('cost_sealed_and_usage_unconfirmed', plan['quality_before_cost'] is True
          and plan['usage_aggregation'] is None
          and plan['usage_semantics'] == 'unconfirmed_until_actual_resume_evidence')
    mapping_path = BATCH / 'private/ANON_MAP.json'
    check('new_mapping_bound', sha(mapping_path) == plan['anonymous_map_sha256'])
    old_mapping = read(ROOT / 'verification/m4_surface_scan_continuous_consumption_001/private/ANON_MAP.json')
    old_ids = {row['anonymous_episode_id'] for row in old_mapping['rows']}
    check('new_episode_identities', len({row['anonymous_episode_id'] for row in plan['sequence']}) == 6
          and not old_ids.intersection(row['anonymous_episode_id'] for row in plan['sequence']))
    for relative, expected_sha in PINNED.items():
        path = INTERFACE / relative
        sources[str(path)] = sha(path)
        check('fixed_interface_' + relative, sources[str(path)] == expected_sha)
    coordinator = load('_review_002_actual_interface_wrapper', INTERFACE / 'runtime/episode.py')
    check('actual_wrapper_has_no_pack', not hasattr(coordinator, 'pack'))
    check('legacy_pack_is_original_capture_function',
          Path(coordinator.legacy.pack.capture_cell.__code__.co_filename).resolve()
          == (ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py').resolve())
    check('actual_process_loop_archive_binding', coordinator.transport.consume_turn.__globals__['archive_turn']
          is coordinator.transport.archive_turn)
    check('actual_coordinator_transport_binding', coordinator.run_episode.__globals__['transport'] is coordinator.transport)
    driver_path = BATCH / 'runtime/driver.py'
    check('new_driver_present', driver_path.is_file())
    if driver_path.is_file():
        driver = load('_review_002_outer_driver', driver_path)
        sources[str(driver_path)] = sha(driver_path)
        check('outer_loads_fixed_wrapper', driver.COORDINATOR.resolve() == (INTERFACE / 'runtime/episode.py').resolve())
        check('outer_450_and_590_original_constants', driver.EPISODE_NS == 590 * 10**9 and driver.TURN_NS == 450 * 10**9)
        driver.contract(plan)
        check('outer_fixed_plan_contract', True)
        tree = ast.parse(driver_path.read_text(encoding='utf8'))
        run_one = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_one')
        run_text = ast.unparse(run_one)
        check('outer_explicit_legacy_pack_reference', 'coordinator.legacy.pack.capture_cell' in run_text)
        check('outer_uses_new_short_root', "plan['runtime_root']" in run_text)
        old_tree = ast.parse((ROOT / 'verification/m4_surface_scan_continuous_consumption_001/runtime/driver.py').read_bytes())
        for name in ('publish', 'run_batch'):
            old_node = next(node for node in old_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            new_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            check('existing_' + name + '_flow_preserved', ast.dump(old_node, include_attributes=False)
                  == ast.dump(new_node, include_attributes=False))
    offline = BATCH / 'runtime/offline/a01'
    result_path = offline / 'RESULT.json'
    check('targeted_offline_result_present', result_path.is_file())
    if result_path.is_file():
        result = read(result_path)
        check('three_changed_wiring_tests_passed', result.get('tests') == 3 and result.get('passed') is True
              and result.get('failures') == result.get('errors') == 0)
        records = {row['case']: row for row in result['records']}
        full = records['test_actual_wrapper_full_outer']
        check('actual_outer_synthetic_single_finish', full['finish_signals'] == 1
              and full['substituted_CLI_starts'] == 3 and full['outer_valid_completion'] is True)
        stopped = records['test_shared_fault_stops_fixed_remainder']
        check('actual_batch_shared_fault_stops_remainder', stopped['entered'] == ['N1']
              and stopped['execution_counts'] == {'planned': 18, 'completed': 0, 'failed': 1, 'not_run': 17}
              and stopped['stop_reasons'] == ['shared_success_binding_fault'])
        ordinary = records['test_tool_error_keeps_original_policy']
        check('actual_batch_normal_tool_error_continues', ordinary['entered'] == ['N1', 'C1', 'C2', 'N2', 'N3', 'C3']
              and ordinary['execution_counts'] == {'planned': 18, 'completed': 0, 'failed': 6, 'not_run': 12}
              and ordinary['stop_reasons'] == [])
        outer_folder = offline / 'r_full_outer/m4_surface_scan_continuous_consumption_002/episodes/N1'
        manifest_path = outer_folder / 'RUNTIME_MANIFEST.json'
        archive_path = outer_folder / 'ORIGINALS.zip'
        manifest = read(manifest_path)
        with zipfile.ZipFile(archive_path) as archive:
            actual = {name: {'bytes': len(archive.read(name)), 'sha256': hashlib.sha256(archive.read(name)).hexdigest()}
                      for name in archive.namelist()}
            check('full_outer_real_packer_archive_bytes', len(archive.namelist()) == len(set(archive.namelist()))
                  and actual == manifest['members'] and sha(archive_path) == manifest['archive_sha256'])
            check('full_outer_terminal_and_consumer_originals', {'owner/CLOSE.json', 'SOURCE_GUARD_AFTER.json',
                  'ACTUAL_WIRING.json', 'c/EPISODE_RESULT.json'} <= set(actual))
        outer = read(outer_folder / 'OUTER_RESULT.json')
        timing = read(outer_folder / 'FINAL_TIMING.json')
        check('full_outer_actual_postclose_and_publication', outer['owner_finish_calls'] == 1
              and outer['owner_finish']['confirmed'] is True and outer['postclose_verification']['passed'] is True
              and timing['outer_valid_completion'] is True and timing['within_590s'] is True)
        for path in (result_path, manifest_path, archive_path, outer_folder / 'OUTER_RESULT.json',
                     outer_folder / 'FINAL_TIMING.json', BATCH / 'runtime/test_wiring.py'):
            sources[str(path)] = sha(path)
    for path in (BATCH / 'PLAN.json', mapping_path, BATCH / 'inputs/ROOT_PLAN.md', Path(__file__)):
        sources[str(path)] = sha(path)
    result = {'scope': 'Offline changed-entry-point review only. Existing interface replays are reused.',
              'passed': all(row['passed'] for row in checks), 'checks': checks,
              'source_sha256': sources, 'cost_unsealed': False, 'usage_aggregation': None,
              'new_provider_model_product_Blender_runs': 0}
    (HERE / 'CHECK.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                                   encoding='utf8', newline='\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks)}))


if __name__ == '__main__':
    main()
