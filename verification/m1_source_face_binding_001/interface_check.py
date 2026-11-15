"""Inspect the actual producer and A/B command wiring without model execution."""
import importlib.util
from pathlib import Path
import json
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_m1_interface_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    output = HERE / 'offline_interface'
    output.mkdir(exist_ok=False)
    plan = launcher.read(HERE / 'PLAN.json')
    launcher.input_checks(plan)
    old = Path('D:/he_occluded_transfer_001/formal/RUN_RESULT.json')
    saved = launcher.read(old)
    checks = dict(actual_saved_six_route_schema=saved['schema']=='routed-task-benefit-six-route-v1',
        actual_saved_states_are_record_level='execution_state' not in saved and all('execution_state' in r for r in saved['records']),
        exact_common_run_slot_code=launcher.run_slot.__code__ is launcher.ACCEPTED_ROUTED.run_slot.__code__,
        new_order_registered=[s for s,_ in launcher.SEQUENCE]==['A1','B1','B2','A2','A3','B3'])
    bridge_spec = importlib.util.spec_from_file_location('_m1_interface_bridge', HERE / 'bridge.py')
    bridge = importlib.util.module_from_spec(bridge_spec)
    bridge_spec.loader.exec_module(bridge)
    tools = bridge.public_tools('P')
    checks['both_arms_same_five_product_tools'] = [t['name'] for t in tools] == [
        'execute_python','scene_data','render_views','read_images','active_observation']
    commands, proofs = {}, {}
    for arm in ('A','B'):
        slot = arm + '1'
        route, proof = launcher.connect_slot(plan, slot, 'P')
        proofs[arm] = proof()
        path = output / (slot + '_ACTOR_CONFIG.json')
        launcher.save(path, dict(group='P', max_render_attempts=6, max_tool_calls=12,
            worker_deadline_ns=time.perf_counter_ns()+450_000_000_000,
            input_manifest=plan['inputs']['manifests'][arm], output=str(launcher.EXTERNAL / 'formal' / slot / 'o')), exclusive=True)
        command = route.command_factory(HERE / 'actor.py', ['--config', str(path)])
        config = launcher.read(path)
        checks[arm + '_command_whole48_formal36'] = config['whole_render_cap']==48 and config['phase_render_cap']==36
        checks[arm + '_actual_P_role_and_arm'] = config['group']=='P' and config['comparison_arm']==arm
        checks[arm + '_actual_manifest_binding'] = config['input_manifest']==plan['inputs']['manifests'][arm]
        checks[arm + '_actual_selected_product_source'] = config['expected_product_source_sha256']==launcher.read(plan['products'][arm]['path'])['source_sha256']
        checks[arm + '_shared_dependency_same'] = config['runtime_binding']['shared_dependency']==launcher.shared_dependency()
        checks[arm + '_actual_base_python'] = command[:5]==[launcher.runtime_bindings()['base_python']['path'],'-I','-B','-X','utf8']
        checks[arm + '_actual_new_adapter_paths'] = command[5:7]==[str(HERE / 'bootstrap.py'),str(HERE / 'bridge.py')]
        commands[arm] = dict(command=command, config=config)
        process = subprocess.run([launcher.runtime_bindings()['base_python']['path'], '-I','-B','-X','utf8',
            str(HERE / 'isolation_check.py'), '--arm',arm], capture_output=True, text=True,
            encoding='utf-8', timeout=30, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        launcher.save(output / ('ISOLATION_' + arm + '.json'),
            dict(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr), exclusive=True)
        checks[arm + '_actual_private_path_and_library_checks'] = process.returncode==0 and json.loads(process.stdout)['passed'] is True
    assert all(checks.values()), {k:v for k,v in checks.items() if not v}
    launcher.save(HERE / 'RUNTIME_INTERFACE_CHECK.json', dict(schema='source-face-binding-runtime-interface-v1',
        passed=True, checks=checks, saved_actual_producer=dict(path=str(old),sha256=launcher.sha(old)),
        source_face_comparison_producer='source-face-binding-six-route-v1',
        public_arm_field='comparison_arm', actual_internal_execution_group='P',
        command_proofs=commands, pointer_proofs=proofs, actual_model_calls=0,
        actual_product_observations=0, actual_rasters=0, actual_isolation_check_processes=2,
        scope='Actual saved producer field positions, common code object, command factory and isolated ordinary Python checks. No actor/CLI/renderer execution.'), exclusive=True)
    print(json.dumps(dict(passed=True, checks=len(checks))))


if __name__ == '__main__':
    main()
