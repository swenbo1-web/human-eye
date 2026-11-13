"""One reserved four-probe qualification of the frozen direct-base launcher."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import traceback


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'qualification'
SCENARIOS = ('normal', 'nonzero', 'timeout', 'receipt_failure')
STARTUP_SECONDS = 30
FINISH_SECONDS = 30
REGISTERED_WAIT_SECONDS = .25


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch = load('_active003_qualified_launch', HERE / 'launch.py')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def failure(error, stage):
    return {'stage': stage, 'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}


def verify_sources(frozen, freeze_sha):
    if sha(HERE / 'FROZEN.json') != freeze_sha:
        raise ValueError('qualification_source_freeze_changed')
    normalized = {Path(path).resolve(): wanted for path, wanted in frozen['runtime_sources'].items()}
    required = [HERE / name for name in ('launch.py', 'bootstrap.py', 'probe.py', 'qualify.py', 'runtime.py', 'validate.py', 'runner.py')]
    contract = launch.describe()
    required.extend(Path(row['path']) for row in contract['expected_dependencies'].values())
    required.append(Path(contract['base_executable']))
    if any(path.resolve() not in normalized for path in required):
        raise ValueError('actual_launch_graph_missing_from_freeze')
    for path, wanted in normalized.items():
        if sha(path) != wanted:
            raise ValueError('qualified_source_changed:' + str(path))
    if contract != frozen['launch_contract']:
        raise ValueError('frozen_launch_contract_changed')


def environment_checks(environment, handshake, contract, frozen, pid):
    if environment['process_id'] != pid or handshake['process_id'] != pid:
        raise ValueError('Popen_actual_PID_mismatch')
    if Path(environment['python_executable']).resolve() != Path(contract['base_executable']).resolve():
        raise ValueError('actual_base_executable_path')
    for key in ('base_executable', 'base_executable_sha256', 'bootstrap_path', 'bootstrap_sha256',
                'explicit_site_packages', 'product_install_root', 'dependency_manifest_path', 'dependency_manifest_sha256'):
        if environment[key] != contract[key]:
            raise ValueError('child_launch_contract:' + key)
    for key, expected in contract['expected_dependencies'].items():
        if environment[key] != expected:
            raise ValueError('actual_dependency:' + key)
    normalized = {Path(path).resolve(): wanted for path, wanted in frozen['runtime_sources'].items()}
    if (Path(handshake['probe_path']).resolve() != (HERE / 'probe.py').resolve()
            or handshake['probe_sha256'] != normalized[(HERE / 'probe.py').resolve()]):
        raise ValueError('actual_probe_source_binding')
    for path, wanted in environment['baseline_sources_sha256'].items():
        if normalized.get(Path(path).resolve()) != wanted:
            raise ValueError('actual_baseline_source_binding')
    if environment['launch_sha256'] != normalized[Path(environment['launch_path']).resolve()]:
        raise ValueError('actual_launch_source_binding')
    if environment['product_binding']['source_count'] != 138:
        raise ValueError('actual_product_source_count')


def run_case(scenario, frozen):
    started = time.perf_counter_ns()
    folder = OUTPUT / scenario
    folder.mkdir(exist_ok=False)
    run_id = 'M4-ACTIVE-COVERAGE-003-QUAL-' + scenario
    arguments = ['--scenario', scenario, '--output', str(folder.resolve()), '--run-id', run_id]
    row = {'scenario': scenario, 'run_id': run_id, 'output_directory': str(folder.resolve()),
           'state': 'running', 'passed': False, 'started_ns': started, 'errors': [],
           'process_started': False, 'Popen_pid': None, 'actual_pid': None,
           'cleanup': None, 'timeout_after_handshake': False, 'action_count': 0,
           'new_raster_calls': 0, 'new_model_provider_Blender_API_runs': 0}
    process = None
    try:
        command = launch.python_command(HERE / 'probe.py', arguments)
        row['command'] = command
        with (folder / 'stdout.bin').open('xb') as stdout, (folder / 'stderr.bin').open('xb') as stderr:
            try:
                row['before_Popen_ns'] = time.perf_counter_ns()
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                row['process_started'] = True
                row['Popen_pid'] = process.pid
                row['Popen_returned_ns'] = time.perf_counter_ns()
                save(folder / 'PARENT_START.json', {'command': command, 'Popen_pid': process.pid,
                     'started_ns': started, 'before_Popen_ns': row['before_Popen_ns'], 'run_id': run_id})
                startup_deadline = row['before_Popen_ns'] + STARTUP_SECONDS * 10**9
                while not (folder / 'HANDSHAKE.json').exists():
                    if process.poll() is not None:
                        if (folder / 'HANDSHAKE.json').exists():
                            break
                        raise RuntimeError('probe_exited_before_handshake')
                    if time.perf_counter_ns() >= startup_deadline:
                        raise TimeoutError('probe_startup_handshake_deadline')
                    time.sleep(.01)
                handshake = read(folder / 'HANDSHAKE.json')
                if (handshake['scenario'] != scenario or handshake['run_id'] != run_id
                        or Path(handshake['output_directory']).resolve() != folder.resolve()):
                    raise ValueError('actual_probe_identity_binding')
                environment = read(folder / 'ENVIRONMENT.json')
                if sha(folder / 'ENVIRONMENT.json') != handshake['environment_sha256']:
                    raise ValueError('handshake_environment_bytes')
                environment_checks(environment, handshake, frozen['launch_contract'], frozen, process.pid)
                row['actual_pid'] = handshake['process_id']
                row['handshake'] = handshake
                row['launch_environment'] = environment
                row['handshake_confirmed_ns'] = time.perf_counter_ns()
                if scenario == 'timeout':
                    if handshake['phase'] != 'waiting':
                        raise ValueError('timeout_probe_not_actually_waiting')
                    row['registered_wait_deadline_ns'] = row['handshake_confirmed_ns'] + int(REGISTERED_WAIT_SECONDS * 10**9)
                    remaining = max(0.001, (row['registered_wait_deadline_ns'] - time.perf_counter_ns()) / 1e9)
                    try:
                        process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        row['timeout_after_handshake'] = True
                    if not row['timeout_after_handshake']:
                        raise ValueError('timeout_probe_exited_without_registered_timeout')
                else:
                    process.wait(timeout=FINISH_SECONDS)
                row['wait_boundary_ns'] = time.perf_counter_ns()
            finally:
                if process is not None:
                    row['cleanup'] = launch.stop_process(process, timeout=5)
        row['streams_closed_ns'] = time.perf_counter_ns()
        row['parent_files_closed'] = stdout.closed and stderr.closed
        cleanup = row['cleanup']
        if not cleanup or cleanup['confirmed'] is not True:
            raise ValueError('actual_interpreter_cleanup_unconfirmed')
        row['exit_code'] = cleanup['exit_code']
        state = read(folder / 'STATE.json')
        row['child_state'] = state
        if (state['process_id'] != row['actual_pid'] or state['run_id'] != run_id
                or Path(state['output_directory']).resolve() != folder.resolve()):
            raise ValueError('actual_child_state_binding')
        audit = read(folder / 'AUDIT.json')
        events = [json.loads(line) for line in (folder / 'TRACE.jsonl').read_bytes().splitlines()]
        if [event['sequence'] for event in events] != list(range(1, len(events) + 1)):
            raise ValueError('probe_trace_sequence')
        if any(event['process_id'] != row['actual_pid'] or event['run_id'] != run_id for event in events):
            raise ValueError('probe_trace_actual_process_binding')
        if audit['forbidden_old_evidence_reads'] or audit['forbidden_old_writes']:
            raise ValueError('probe_old_evidence_violation')
        if any(folder.rglob('*.png')) or any(folder.rglob('*.npz')) or any(event['event'].startswith('render_') for event in events):
            raise ValueError('probe_must_produce_zero_images')
        receipt = read(folder / 'RECEIPT.json') if (folder / 'RECEIPT.json').exists() else None
        marker_events = [event for event in events if event['event'] == 'marker_written']
        if scenario == 'normal':
            if cleanup['exit_code'] != 0 or receipt is None or receipt['status'] != 'completed':
                raise ValueError('normal_receipt_or_exit')
            if (receipt['run_id'] != run_id or receipt['process_id'] != row['actual_pid']
                    or Path(receipt['output_directory']).resolve() != folder.resolve()
                    or receipt['environment_sha256'] != row['handshake']['environment_sha256']):
                raise ValueError('normal_receipt_binding')
            row['receipt_validation'] = {'passed': True}
        elif scenario == 'nonzero':
            if cleanup['exit_code'] in (None, 0) or state.get('type') != 'RegisteredProbeFailure' or receipt is not None:
                raise ValueError('registered_nonzero_not_preserved')
            row['receipt_validation'] = {'passed': False, 'reason': 'registered_nonzero_exception'}
        elif scenario == 'timeout':
            if not cleanup['kill_requested'] or cleanup['exit_code'] is None or not any(event['event'] == 'waiting' for event in events):
                raise ValueError('handshake_timeout_reaping_not_proven')
            row['receipt_validation'] = {'passed': False, 'reason': 'registered_timeout_after_waiting_handshake'}
        else:
            marker = read(folder / 'MARKER.json')
            if (cleanup['exit_code'] != 0 or receipt is not None or len(marker_events) != 1
                    or type(marker['action_count']) is not int or marker['action_count'] != 1
                    or marker['process_id'] != row['actual_pid'] or marker['run_id'] != run_id
                    or sha(folder / 'MARKER.json') != marker_events[0]['marker_sha256']):
                raise ValueError('marker_once_receipt_failure_not_preserved')
            row['action_count'] = 1
            row['action_state'] = 'executed_once_verified'
            row['receipt_validation'] = {'passed': False, 'reason': 'registered_missing_receipt_after_marker'}
        if scenario != 'receipt_failure' and ((folder / 'MARKER.json').exists() or marker_events):
            raise ValueError('unexpected_marker_action')
        row['state'] = 'completed'
        row['passed'] = True
    except BaseException as error:
        row['state'] = 'failed'
        row['errors'].append(failure(error, 'qualification_case'))
    row['readback_closed_ns'] = time.perf_counter_ns()
    try:
        row['files_sha256'] = {path.name: sha(path) for path in folder.iterdir() if path.is_file()}
        save(folder / 'CASE.json', row)
        closed = time.perf_counter_ns()
        save(folder / 'FINAL_TIMING.json', {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed-started,
             'scope': 'Command construction, actual child, original-handle cleanup, streams, readback and CASE write/close. Timing receipt publication is separate.'})
    except BaseException as error:
        row['state'], row['passed'] = 'failed', False
        row['errors'].append(failure(error, 'qualification_case_publication'))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.parse_args()
    started = time.perf_counter_ns()
    frozen = read(HERE / 'FROZEN.json')
    freeze_sha = sha(HERE / 'FROZEN.json')
    verify_sources(frozen, freeze_sha)
    OUTPUT.mkdir(exist_ok=True)
    save(OUTPUT / 'QUALIFICATION_STARTED.json', {'started_ns': started, 'scenarios': list(SCENARIOS),
         'maximum_child_processes': 4, 'source_freeze_sha256': freeze_sha})
    cases, errors = [], []
    for scenario in SCENARIOS:
        try:
            verify_sources(frozen, freeze_sha)
            row = run_case(scenario, frozen)
            cases.append(row)
            if row['passed'] is not True:
                break
        except BaseException as error:
            errors.append(failure(error, 'qualification_dispatch'))
            break
    for scenario in SCENARIOS[len(cases):]:
        cases.append({'scenario': scenario, 'state': 'not_run', 'passed': False})
    unchanged = True
    try:
        verify_sources(frozen, freeze_sha)
    except BaseException as error:
        unchanged = False
        errors.append(failure(error, 'final_qualification_integrity'))
    result = {'cycle': 'M4-ACTIVE-COVERAGE-003-LAUNCH-QUALIFICATION', 'cases': cases,
        'all_passed': all(case['passed'] is True for case in cases) and unchanged and not errors,
        'source_freeze_sha256': freeze_sha, 'source_files_sha256': frozen['runtime_sources'],
        'source_unchanged': unchanged, 'errors': errors,
        'actual_child_processes': sum(case.get('process_started', False) for case in cases),
        'marker_actions': sum(case.get('action_count', 0) for case in cases),
        'new_raster_calls': 0, 'new_model_provider_Blender_API_runs': 0,
        'timing': {'started_ns': started, 'work_closed_before_result_publication_ns': time.perf_counter_ns(),
                   'scope': 'Freeze checks, four registered probes, handle cleanup, readback and per-case publication. Final RESULTS publication is separate.'}}
    save(OUTPUT / 'RESULTS.json', result)
    closed = time.perf_counter_ns()
    save(OUTPUT / 'FINAL_TIMING.json', {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed-started,
         'scope': 'Qualification including RESULTS write/close. This timing receipt publication is separate.'})
    print(json.dumps({'all_passed': result['all_passed'], 'actual_child_processes': result['actual_child_processes'],
                      'marker_actions': result['marker_actions'], 'new_raster_calls': 0}))
    return 0 if result['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
