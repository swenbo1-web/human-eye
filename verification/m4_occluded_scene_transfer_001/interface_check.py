"""Check the actual routed producer, shared tools and no-model command wiring."""

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_transfer_interface_launcher', HERE/'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    started = time.perf_counter_ns()
    output = HERE/'offline_interface'
    output.mkdir(exist_ok=False)
    plan = launcher.read(HERE/'PLAN.json')
    launcher.input_checks(plan)
    checks = {}
    saved_path = Path('D:/he_routed_001/formal/RUN_RESULT.json')
    saved = launcher.read(saved_path)
    checks['actual_routed_six_route_schema'] = saved['schema'] == 'routed-task-benefit-six-route-v1'
    checks['actual_routed_sequence'] = [(r['slot'],r['group']) for r in saved['records']] == launcher.SEQUENCE
    checks['actual_state_is_record_level'] = 'execution_state' not in saved and all('execution_state' in r for r in saved['records'])
    checks['actual_common_slot_clock_schema'] = all(r['slot_timing']['schema'] == 'routed-task-complete-slot-clock-v1' for r in saved['records'])
    checks['run_slot_original_code_object'] = launcher.run_slot.__code__ is launcher.ACCEPTED_ROUTED.run_slot.__code__
    checks['no_single_formal_terminal_reader'] = 'terminal_reader' not in (HERE/'launcher.py').read_text(encoding='utf-8')
    bridge_spec = importlib.util.spec_from_file_location('_transfer_interface_bridge', HERE/'bridge.py')
    bridge = importlib.util.module_from_spec(bridge_spec)
    bridge_spec.loader.exec_module(bridge)
    tools = {g:bridge.public_tools(g) for g in ('N','P')}
    checks['four_public_tools_identical'] = tools['N'] == tools['P'][:4]
    checks['only_P_extra_active'] = [t['name'] for t in tools['P'][4:]] == ['active_observation']
    checks['VIEW_bridge_byte_exact'] = launcher.sha(HERE/'bridge.py') == launcher.sha(launcher.VIEW/'bridge.py')
    new_tree = ast.parse((HERE/'native_tools.py').read_text(encoding='utf-8'))
    old_tree = ast.parse((launcher.VIEW/'native_tools.py').read_text(encoding='utf-8'))
    new_class = next(n for n in new_tree.body if isinstance(n, ast.ClassDef) and n.name=='ObservationSession')
    old_class = next(n for n in old_tree.body if isinstance(n, ast.ClassDef) and n.name=='ObservationSession')
    new_methods = {n.name:ast.dump(n,include_attributes=False) for n in new_class.body if isinstance(n,ast.FunctionDef)}
    old_methods = {n.name:ast.dump(n,include_attributes=False) for n in old_class.body if isinstance(n,ast.FunctionDef)}
    checks['only_native_audit_path_adapter_changed'] = {name for name in new_methods if new_methods[name] != old_methods[name]} == {'install_audit'}
    commands = {}
    proofs = {}
    for slot, group in [('N1','N'),('P1','P')]:
        route, proof = launcher.connect_slot(plan,slot,group)
        proofs[group] = proof()
        path = output/(slot+'_ACTOR_CONFIG.json')
        launcher.save(path,dict(group=group,max_render_attempts=6,max_tool_calls=12,
            worker_deadline_ns=time.perf_counter_ns()+450_000_000_000,
            output=str(launcher.EXTERNAL/'formal'/slot/'o')),exclusive=True)
        command = route.__globals__['launch'].python_command(HERE/'actor.py',['--config',str(path)])
        config = launcher.read(path)
        checks[group+'_actual_command_cap48'] = config['whole_render_cap']==48 and config['phase_render_cap']==36
        checks[group+'_actual_command_shared_dependency'] = config['runtime_binding']['shared_dependency']==launcher.shared_dependency()
        checks[group+'_actual_direct_base_runtime'] = command[:5] == [launcher.runtime_bindings()['base_python']['path'],'-I','-B','-X','utf8']
        checks[group+'_actual_adapter_paths'] = list(map(Path,command[5:7]))==[HERE/'bootstrap.py',HERE/'bridge.py']
        commands[group] = dict(command=command,config_sha256=launcher.sha(path),config=config)
        process = subprocess.run([launcher.runtime_bindings()['base_python']['path'],'-I','-B','-X','utf8',str(HERE/'isolation_check.py'),'--group',group],
            capture_output=True,text=True,encoding='utf-8',timeout=30,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        launcher.save(output/('ISOLATION_'+group+'.json'),dict(exit_code=process.returncode,stdout=process.stdout,stderr=process.stderr),exclusive=True)
        checks[group+'_actual_private_path_checks'] = process.returncode==0 and json.loads(process.stdout)['passed'] is True
    assert all(checks.values()), {k:v for k,v in checks.items() if not v}
    result = dict(schema='occluded-transfer-runtime-interface-check-v1',passed=True,checks=checks,
        saved_producer=dict(path=str(saved_path),sha256=launcher.sha(saved_path),records=6),
        command_proofs=commands,pointer_proofs=proofs,actual_model_calls=0,actual_product_observations=0,
        actual_rasters=0,actual_isolation_check_processes=2,
        scope='Read actual old producer and code-object bindings, construct commands without running actor or CLI, exercise ordinary library and path guard in two isolated no-observation processes.',
        started_ns=started,before_publication_ns=time.perf_counter_ns())
    launcher.save(HERE/'RUNTIME_INTERFACE_CHECK.json',result,exclusive=True)
    print(json.dumps(dict(passed=True,checks=len(checks),models=0,rasters=0,products=0)))


if __name__ == '__main__':
    main()
